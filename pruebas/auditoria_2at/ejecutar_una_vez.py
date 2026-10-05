"""Hito 2AT rev2 (Fase 4): UNICA llamada productiva a ``ejecutar_una_manual_conciliacion()``.

Requiere confirmacion expresa de Pio en chat. Patron de 2AO rev3. Antes de la
llamada exige, sin escribir nada:
  1. el preflight nuevo con veredicto PREFLIGHT_OK;
  2. la revalidacion (modo ``candidato`` con ``candidato_previo``) con veredicto
     CANDIDATO_OK, revalidacion identica y candidato n.o 1 == factura esperada;
  3. una comprobacion READ_ONLY inmediata: operacion (flags, tolerancia, workers,
     locks, claims, NORMALIZANDO), primer id del selector oficial == esperada y
     huella de su fila igual a la revalidada; y tareas programadas en estado
     distinto de Running y a 60 min o mas;
  4. cliente con project ref productivo y clave de rol service_role;
  5. que no exista el guard de ejecucion unica (se crea en exclusiva antes de
     llamar y no se borra nunca).
Si algo falla, sale SIN ejecutar. Nunca reintenta: cualquier excepcion se
registra y el script termina. No modifica flags ni activa automatismos.

Uso:
  python -B pruebas/auditoria_2at/ejecutar_una_vez.py <factura_esperada> <preflight.json>
      <revalidacion.json> <salida.json> <dir_temporal>
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

from auditoria_readonly import (  # noqa: E402
    COLUMNAS_HUELLA, MODO_CLAIM, PROJECT_REF, SQL_SELECTOR_OFICIAL, TOLERANCIA_CERTIFICADA, _Lector,
    _ejecutar_lectura, _operacion, _puertas_operacion, _puertas_tareas, _salida_fuera_del_repo, _tareas)

WORKER_ID = "cf-2at-manual-conciliacion"
NOMBRE_GUARD = "ejecucion_unica_2at.guard"


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


def _huella_factura(lector: _Lector, factura: str) -> str:
    return lector.valor(
        "select md5(to_jsonb(r)::text) from public.facturas t cross join lateral (select "
        + ", ".join(f"t.{c}" for c in COLUMNAS_HUELLA["facturas"]) + ") r where t.id = %s", (factura,))


def revalidar(esperada: str, preflight: dict, revalidacion: dict) -> dict:
    r: dict = {
        "preflight_ok": preflight.get("veredicto") == "PREFLIGHT_OK",
        "revalidacion_ok": (revalidacion.get("veredicto") == "CANDIDATO_OK"
                            and bool(revalidacion.get("revalidacion"))
                            and all(revalidacion["revalidacion"].values())),
        "revalidacion_candidato": (revalidacion.get("candidato_1") or {}).get("id"),
    }

    def leer(lector: _Lector) -> dict:
        out = _operacion(lector)
        oficial = [f[0] for f in lector.filas(SQL_SELECTOR_OFICIAL, {"modo": MODO_CLAIM})]
        out["selector_primero"] = oficial[0] if oficial else None
        out["huella_esperada_actual"] = _huella_factura(lector, esperada)
        return out

    _, inmediata = _ejecutar_lectura(leer)
    r["inmediata"] = {k: inmediata[k] for k in ("capturado_utc", "flags", "tolerancia_conciliacion",
                                                "locks_documentos", "claims_conciliacion", "normalizando",
                                                "workers", "selector_primero", "huella_esperada_actual")}
    r["fallos_operacion"] = _puertas_operacion(inmediata)
    tareas = _tareas()
    r["tareas"] = tareas
    r["fallos_tareas"] = _puertas_tareas(tareas, datetime.now(timezone.utc))
    r["ok"] = (
        r["preflight_ok"] and r["revalidacion_ok"]
        and r["revalidacion_candidato"] == esperada
        and inmediata["selector_primero"] == esperada
        and inmediata["huella_esperada_actual"] == revalidacion["candidato_1"]["huella_fila"]
        and not r["fallos_operacion"] and not r["fallos_tareas"]
    )
    return r


def _estado_posterior(factura: str) -> dict:
    def leer(lector: _Lector) -> dict:
        return {"factura": lector.json(
            "select jsonb_build_object('estado_conciliacion_cf', estado_conciliacion_cf, "
            "'conciliacion_intentos', conciliacion_intentos, 'conciliacion_intentos_fallo', "
            "conciliacion_intentos_fallo, 'conciliacion_proximo_at', conciliacion_proximo_at, "
            "'conciliacion_ultimo_error', conciliacion_ultimo_error, 'diferencia_albaranes', diferencia_albaranes, "
            "'bloqueado_por', conciliacion_bloqueado_por)::text from public.facturas where id = %s", (factura,)),
            "claims_conciliacion": lector.valor(
                "select count(*) from public.facturas where conciliacion_bloqueado_hasta > now() "
                "or conciliacion_bloqueado_por is not null")}
    return _ejecutar_lectura(leer)[1]


def main(esperada: str, preflight_ruta: Path, revalidacion_ruta: Path, salida: Path, directorio: Path) -> int:
    registro: dict = {"factura_esperada": esperada, "worker_id": WORKER_ID, "invocaciones": 0}

    def guardar() -> None:
        salida.write_text(json.dumps(registro, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    guard = salida.parent / NOMBRE_GUARD
    if guard.exists():
        registro["resultado"] = "NO_EJECUTADO_GUARD_EXISTENTE"
        guardar()
        raise SystemExit(f"GUARD_EXISTENTE: {guard}; la ejecucion unica ya se intento")

    registro["revalidacion"] = revalidar(
        esperada,
        json.loads(preflight_ruta.read_text(encoding="utf-8")),
        json.loads(revalidacion_ruta.read_text(encoding="utf-8")))
    if not registro["revalidacion"]["ok"]:
        registro["resultado"] = "NO_EJECUTADO_REVALIDACION_FALLIDA"
        guardar()
        raise SystemExit("REVALIDACION_FALLIDA: no se ejecuta")

    from dotenv import dotenv_values
    from src.facturas.runtime_supabase.compositor_manual import construir_worker_manual_productivo
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
    registro["configuracion"] = {"normalizacion_automatica": configuracion.normalizacion_automatica,
                                 "conciliacion_automatica": configuracion.conciliacion_automatica,
                                 "luna_habilitada": configuracion.luna_habilitada,
                                 "farmacias_habilitadas": list(configuracion.farmacias_habilitadas),
                                 "tolerancia_conciliacion": str(configuracion.tolerancia_conciliacion)}
    if (configuracion.normalizacion_automatica or configuracion.conciliacion_automatica
            or configuracion.luna_habilitada or configuracion.farmacias_habilitadas != ("PIO",)
            or configuracion.tolerancia_conciliacion != TOLERANCIA_CERTIFICADA):
        registro["resultado"] = "NO_EJECUTADO_CONFIGURACION_INESPERADA"
        guardar()
        raise SystemExit("CONFIGURACION_INESPERADA: no se ejecuta")

    try:
        worker = construir_worker_manual_productivo(cliente, configuracion, WORKER_ID, directorio)
        with open(guard, "x", encoding="utf-8") as g:  # exclusivo: segunda ejecucion imposible
            g.write(f"{_ahora()} {esperada} {WORKER_ID}\n")
        registro["inicio_utc"] = _ahora()
        registro["invocaciones"] = 1
        resultado = worker.ejecutar_una_manual_conciliacion()  # UNICA llamada productiva del hito 2AT.
        registro["fin_utc"] = _ahora()
        registro["resultado"] = "RETORNO"
        # facturas_conciliacion_reclamadas=0 es ambiguo (sin claim, o claim con fallo
        # registrado por cf_registrar_fallo_conciliacion): lo resuelve el postcheck.
        registro["retorno"] = {"documentos_reclamados": resultado.documentos_reclamados,
                               "facturas_conciliacion_reclamadas": resultado.facturas_conciliacion_reclamadas,
                               "automatismos_habilitados": resultado.automatismos_habilitados,
                               "modo_ejecucion": resultado.modo_ejecucion}
    except BaseException as exc:  # sin reintento: se registra y se termina
        registro["fin_utc"] = _ahora()
        registro["resultado"] = "EXCEPCION"
        registro["excepcion"] = f"{type(exc).__name__}: {exc}"
        registro["traza"] = traceback.format_exc()[-4000:]
    finally:
        shutil.rmtree(directorio, ignore_errors=True)
        registro["directorio_temporal_borrado"] = not directorio.exists()
        guardar()

    try:
        registro["estado_posterior_readonly"] = _estado_posterior(esperada)
    except Exception as exc:  # solo lectura informativa; el postcheck es la Fase 6
        registro["estado_posterior_readonly"] = {"error": f"{type(exc).__name__}: {exc}"}
    guardar()
    print(json.dumps({k: v for k, v in registro.items() if k != "traza"}, ensure_ascii=False, indent=1,
                     default=str))
    return 0 if registro["resultado"] == "RETORNO" else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]),
                  _salida_fuera_del_repo(sys.argv[4]), _salida_fuera_del_repo(sys.argv[5])))
