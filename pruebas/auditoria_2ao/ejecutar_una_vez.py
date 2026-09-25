"""Hito 2AO rev3: UNICA llamada productiva a ``ejecutar_una_manual()``.

Requiere confirmacion expresa de Pio en chat. Antes de la llamada revalida
READ_ONLY flags, locks, claims, NORMALIZANDO y que el candidato n.o 1 del ordering
oficial es el documento confirmado; si algo difiere, sale SIN ejecutar. Nunca
reintenta: cualquier excepcion se registra y el script termina.

Uso: python pruebas/auditoria_2ao/ejecutar_una_vez.py <documento_esperado> <salida.json> <dir_temporal>
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

from snapshot_readonly import PROJECT_REF, SQL_ELEGIBLES, _conectar  # noqa: E402

WORKER_ID = "cf-2ao-manual-one-shot"


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def revalidar(esperado: str) -> dict:
    _, conn = _conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("select current_setting('transaction_read_only')")
            ro = cur.fetchone()[0]
            cur.execute("select normalizacion_automatica,conciliacion_automatica,luna_habilitada,"
                        "farmacias_habilitadas::text from public.cf_configuracion where id")
            flags = list(cur.fetchone())
            cur.execute(
                "select (select count(*) from public.documentos_facturas where bloqueado_hasta>now()),"
                "(select count(*) from public.facturas where conciliacion_bloqueado_hasta>now()),"
                "(select count(*) from public.documentos_facturas where bloqueado_por is not null),"
                "(select count(*) from public.documentos_facturas where estado_lectura='NORMALIZANDO')")
            locks_doc, locks_fac, claims, normalizando = cur.fetchone()
            cur.execute(SQL_ELEGIBLES)
            elegibles = cur.fetchall()
    finally:
        conn.rollback()
        conn.close()
    r = {"read_only": ro, "flags": flags, "locks": [locks_doc, locks_fac], "claims": claims,
         "normalizando": normalizando, "elegibles": len(elegibles),
         "candidato_1": elegibles[0][0] if elegibles else None,
         "candidato_2": elegibles[1][0] if len(elegibles) > 1 else None}
    r["ok"] = (ro == "on" and flags == [False, False, False, "{PIO}"] and r["locks"] == [0, 0]
               and claims == 0 and normalizando == 0 and r["candidato_1"] == esperado)
    return r


def _rol_clave(clave: str) -> str | None:
    # Formato nuevo de Supabase: las claves secretas ``sb_secret_`` sustituyen a la
    # JWT legacy de service_role (la publicable ``sb_publishable_`` equivale a anon).
    if clave.startswith("sb_secret_"):
        return "service_role"
    if clave.startswith("sb_publishable_"):
        return "anon"
    try:
        cuerpo = clave.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4))).get("role")
    except Exception:
        return None


def main(esperado: str, salida: Path, directorio: Path) -> None:
    registro: dict = {"documento_esperado": esperado, "worker_id": WORKER_ID, "invocaciones": 0}
    registro["revalidacion"] = revalidar(esperado)
    if not registro["revalidacion"]["ok"]:
        registro["resultado"] = "NO_EJECUTADO_REVALIDACION_FALLIDA"
        salida.write_text(json.dumps(registro, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
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
        salida.write_text(json.dumps(registro, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        raise SystemExit("CLIENTE_NO_DEMOSTRADO: no se ejecuta")

    cliente = obtener_cliente_supabase()
    repositorio = RepositorioRuntimeSupabase(cliente)
    configuracion = repositorio.obtener_configuracion()
    registro["configuracion"] = {"normalizacion_automatica": configuracion.normalizacion_automatica,
                                 "conciliacion_automatica": configuracion.conciliacion_automatica,
                                 "luna_habilitada": configuracion.luna_habilitada,
                                 "farmacias_habilitadas": list(configuracion.farmacias_habilitadas)}
    try:
        worker = construir_worker_manual_productivo(cliente, configuracion, WORKER_ID, directorio)
        registro["inicio_utc"] = _ahora()
        registro["invocaciones"] = 1
        resultado = worker.ejecutar_una_manual()  # UNICA llamada productiva autorizada del hito 2AO.
        registro["fin_utc"] = _ahora()
        registro["resultado"] = "RETORNO"
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
        salida.write_text(json.dumps(registro, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in registro.items() if k != "traza"}, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]))
