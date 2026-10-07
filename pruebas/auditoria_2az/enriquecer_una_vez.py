"""Hito 2AZ (R12): UNICA llamada productiva a ``WorkerEnriquecimiento.ejecutar(factura)``.

NO se ejecuta en el hito 2AZ (solo se ensaya en local). Requiere migracion 20
desplegada y confirmacion expresa de Pio en chat. Patron de 2AT
``ejecutar_una_vez.py``. Antes de la llamada exige, sin escribir nada:
  1. comprobacion READ_ONLY: migracion 20 presente, operacion segura (flags,
     tolerancia, workers, locks, claims, NORMALIZANDO), la factura existe, esta
     PENDIENTE_CONCILIAR y sin claim; tareas programadas a 60 min o mas;
  2. cliente con project ref productivo y clave de rol service_role;
  3. configuracion f|f|f|{PIO};
  4. que no exista el guard de ejecucion unica de esa factura (se crea en
     exclusiva antes de llamar y no se borra nunca).
Si algo falla, sale SIN ejecutar. Nunca reintenta.

Uso:
  python -B pruebas/auditoria_2az/enriquecer_una_vez.py <factura_esperada> <salida.json> <dir_temporal>
"""
from __future__ import annotations

import base64
import json
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))

from auditoria_readonly import (  # noqa: E402
    PROJECT_REF, _Lector, _ejecutar_lectura, _operacion, _puertas_operacion, _puertas_tareas,
    _salida_fuera_del_repo, _tareas)

WORKER_ID = "cf-2az-enriquecimiento"


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rol_clave(clave: str) -> str | None:
    # Copia literal de pruebas/auditoria_2ao/ejecutar_una_vez.py.
    if clave.startswith("sb_secret_"):
        return "service_role"
    if clave.startswith("sb_publishable_"):
        return "anon"
    try:
        cuerpo = clave.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4))).get("role")
    except Exception:
        return None


def _estado_factura(lector: _Lector, factura: str) -> dict:
    return lector.json(
        "select jsonb_build_object('existe', count(*) = 1, 'estado', max(estado_conciliacion_cf), "
        "'claim', bool_or(conciliacion_bloqueado_por is not null), "
        "'albaranes', (select count(*) from public.facturas_albaranes_extraidos a where a.factura_id = %s), "
        "'vencimientos_sin_importe', (select count(*) from public.facturas_vencimientos v "
        "  where v.factura_id = %s and v.importe is null), "
        "'enriquecimientos', (select count(*) from public.historial_facturas h "
        "  where h.factura_id = %s and h.evento = 'FACTURA_ENRIQUECIDA'))::text "
        "from public.facturas where id = %s", (factura, factura, factura, factura))


def revalidar(factura: str) -> dict:
    def leer(lector: _Lector) -> dict:
        out = _operacion(lector)
        out["migracion_20"] = lector.valor(
            "select to_regprocedure('public.cf_enriquecer_factura(uuid,text,text,jsonb)') is not null")
        out["factura"] = _estado_factura(lector, factura)
        return out

    _, inmediata = _ejecutar_lectura(leer)
    tareas = _tareas()
    r = {"inmediata": {k: inmediata[k] for k in ("capturado_utc", "flags", "locks_documentos",
                                                 "claims_conciliacion", "normalizando", "workers",
                                                 "migracion_20", "factura")},
         "fallos_operacion": _puertas_operacion(inmediata), "tareas": tareas,
         "fallos_tareas": _puertas_tareas(tareas, datetime.now(timezone.utc))}
    f = inmediata["factura"]
    r["ok"] = (inmediata["migracion_20"] is True and f["existe"] and f["estado"] == "PENDIENTE_CONCILIAR"
               and not f["claim"] and not r["fallos_operacion"] and not r["fallos_tareas"])
    return r


def main(factura: str, salida: Path, directorio: Path) -> int:
    registro: dict = {"factura_esperada": factura, "worker_id": WORKER_ID, "invocaciones": 0}

    def guardar() -> None:
        salida.write_text(json.dumps(registro, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    guard = salida.parent / f"enriquecimiento_unico_{factura}.guard"
    if guard.exists():
        registro["resultado"] = "NO_EJECUTADO_GUARD_EXISTENTE"
        guardar()
        raise SystemExit(f"GUARD_EXISTENTE: {guard}")

    registro["revalidacion"] = revalidar(factura)
    if not registro["revalidacion"]["ok"]:
        registro["resultado"] = "NO_EJECUTADO_REVALIDACION_FALLIDA"
        guardar()
        raise SystemExit("REVALIDACION_FALLIDA: no se ejecuta")

    from dotenv import dotenv_values
    from src.facturas.runtime_supabase.compositor_manual import construir_worker_enriquecimiento_manual
    from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase
    from src.supabase_client.conexion_supabase import obtener_cliente_supabase

    env = dotenv_values(ROOT / ".env")
    ref = (urlparse(env.get("SUPABASE_URL", "")).hostname or "").split(".")[0]
    rol = _rol_clave(env.get("SUPABASE_KEY", ""))
    registro["cliente"] = {"project_ref": ref, "rol_clave": rol}
    if ref != PROJECT_REF or rol != "service_role":
        registro["resultado"] = "NO_EJECUTADO_CLIENTE_NO_DEMOSTRADO"
        guardar()
        raise SystemExit("CLIENTE_NO_DEMOSTRADO: no se ejecuta")

    cliente = obtener_cliente_supabase()
    configuracion = RepositorioRuntimeSupabase(cliente).obtener_configuracion()
    if (configuracion.normalizacion_automatica or configuracion.conciliacion_automatica
            or configuracion.luna_habilitada or configuracion.farmacias_habilitadas != ("PIO",)):
        registro["resultado"] = "NO_EJECUTADO_CONFIGURACION_INESPERADA"
        guardar()
        raise SystemExit("CONFIGURACION_INESPERADA: no se ejecuta")

    try:
        worker = construir_worker_enriquecimiento_manual(cliente, configuracion, WORKER_ID, directorio)
        with open(guard, "x", encoding="utf-8") as g:  # exclusivo: segunda ejecucion imposible
            g.write(f"{_ahora()} {factura} {WORKER_ID}\n")
        registro["inicio_utc"] = _ahora()
        registro["invocaciones"] = 1
        registro["retorno"] = worker.ejecutar(factura)  # UNICA llamada productiva.
        registro["fin_utc"] = _ahora()
        registro["resultado"] = "RETORNO"
    except BaseException as exc:  # sin reintento
        registro["fin_utc"] = _ahora()
        registro["resultado"] = "EXCEPCION"
        registro["excepcion"] = f"{type(exc).__name__}: {exc}"
        registro["traza"] = traceback.format_exc()[-4000:]
    finally:
        shutil.rmtree(directorio, ignore_errors=True)
        registro["directorio_temporal_borrado"] = not directorio.exists()
        guardar()

    try:
        registro["estado_posterior_readonly"] = _ejecutar_lectura(lambda l: {"factura": _estado_factura(l, factura)})[1]
    except Exception as exc:
        registro["estado_posterior_readonly"] = {"error": f"{type(exc).__name__}: {exc}"}
    guardar()
    print(json.dumps({k: v for k, v in registro.items() if k != "traza"}, ensure_ascii=False, indent=1, default=str))
    return 0 if registro["resultado"] == "RETORNO" else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], _salida_fuera_del_repo(sys.argv[2]), _salida_fuera_del_repo(sys.argv[3])))
