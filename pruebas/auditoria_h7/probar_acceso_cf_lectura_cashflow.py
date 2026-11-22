"""Hito H7-D: prueba de acceso de cf_lectura a las tablas de Cashflow (migracion 38) por el pooler de Supabase.

Uso (terminal de Pio, despues de desplegar la 38; la contrasena SOLO en la variable de entorno CF_LECTURA_PASSWORD,
nunca como argumento ni impresa):
  python -B pruebas/auditoria_h7/probar_acceso_cf_lectura_cashflow.py <host_pooler> <puerto_pooler>

Usuario fijo ``cf_lectura.<project_ref>``. Patron de pruebas/auditoria_2bn_d/probar_acceso_cf_lectura.py (decision de
Pio, 2026-11-22). Comprueba:
- conecta (TLS) como cf_lectura, con transacciones de solo lectura por defecto;
- lee las cuatro tablas de Cashflow (conteos) con la RLS del modulo CASHFLOW: ve las cuentas PIO, RITA y SL, y en los
  saldos e importes solo farmacias del modulo o SL (sin farmacia); el modulo CASHFLOW es {PIO, RITA};
- facturas, documentos y albaranes siguen solo PIO (la excepcion de RITA es propia del modulo);
- un INSERT en importaciones, un UPDATE de cuentas, un DELETE de saldos y la RPC de importacion FALLAN (42501 o
  25006). Cada intento va en su propia transaccion READ WRITE que se deshace SIEMPRE, tambien si inesperadamente
  funcionara (entonces la prueba falla).
Sin salidas en disco ni conceptos o categorias en la salida (solo recuentos y codigos). Codigo 0 = todo OK; 3 = alguna
comprobacion fallida; 2 = sin contrasena o sin conexion.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT_REF = "vklaiuytvegkelgyspxc"
ROL = "cf_lectura"
USUARIO = f"{ROL}.{PROJECT_REF}"
VARIABLE = "CF_LECTURA_PASSWORD"
APPLICATION_NAME = "cf_h7d_prueba_acceso"
TABLAS = ("cf_cashflow_cuentas", "cf_cashflow_importaciones", "cf_cashflow_importes", "cf_cashflow_saldos")
DENEGADO = ("42501", "25006")  # insufficient_privilege, read_only_sql_transaction

FARMACIAS_FACTURAS = ("select array(select distinct farmacia from (select farmacia from public.documentos_facturas "
                      "union all select farmacia from public.facturas union all select farmacia "
                      "from public.albaranes) t order by 1)")
ESCRITURAS = {
    "insert_importacion": ("insert into public.cf_cashflow_importaciones (archivo_nombre, archivo_hash, origen, estado, "
                           "detalle_error, filas) values ('prueba-acceso-H7-D', repeat('0', 64), 'MANUAL', 'ERROR', "
                           "'PRUEBA', 0)"),
    "update_cuentas": "update public.cf_cashflow_cuentas set hoja = hoja where false",
    "delete_saldos": "delete from public.cf_cashflow_saldos where false",
    "rpc_importacion": ("select public.cf_cashflow_registrar_importacion('{}'::jsonb, '[]'::jsonb, '[]'::jsonb)"),
}


def _escritura_falla(conn, sentencia: str) -> dict:
    cur = conn.cursor()
    try:
        cur.execute("begin read write")
        cur.execute(sentencia)
    except Exception as error:  # noqa: BLE001 - se informa el SQLSTATE, nunca datos de conexion
        codigo = getattr(error, "pgcode", None)
        return {"falla": codigo in DENEGADO, "sqlstate": codigo,
                "mensaje": str(error).splitlines()[0] if str(error) else type(error).__name__}
    finally:
        conn.rollback()
    return {"falla": False, "sqlstate": None, "mensaje": "LA_ESCRITURA_NO_FALLO (deshecha)"}


def probar(host: str, puerto: int, usuario: str, contrasena: str, dbname: str = "postgres",
           sslmode: str = "require") -> dict:
    sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))
    import psycopg2

    conn = psycopg2.connect(host=host, port=puerto, dbname=dbname, user=usuario, password=contrasena,
                            sslmode=sslmode, connect_timeout=10, application_name=APPLICATION_NAME)
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("select current_user, current_setting('default_transaction_read_only')")
        rol, solo_lectura = cur.fetchone()
        conteos = {}
        for tabla in TABLAS:
            cur.execute(f"select count(*) from public.{tabla}")
            conteos[tabla] = cur.fetchone()[0]
        cur.execute("select array(select codigo from public.cf_cashflow_cuentas order by 1)")
        cuentas = list(cur.fetchone()[0])
        cur.execute("select array(select distinct coalesce(farmacia, 'SL') from public.cf_cashflow_saldos order by 1)")
        farmacias_saldos = list(cur.fetchone()[0])
        cur.execute("select array(select distinct farmacia from public.cf_cashflow_importes order by 1)")
        farmacias_importes = list(cur.fetchone()[0])
        cur.execute("select farmacias from public.cf_modulos_farmacias where modulo = 'CASHFLOW'")
        fila = cur.fetchone()
        modulo = list(fila[0]) if fila else []
        cur.execute(FARMACIAS_FACTURAS)
        farmacias_facturas = list(cur.fetchone()[0])
        conn.autocommit = False
        escrituras = {clave: _escritura_falla(conn, sentencia) for clave, sentencia in ESCRITURAS.items()}
    finally:
        conn.close()
    resultado = {
        "conecta_como_cf_lectura": rol == ROL,
        "solo_lectura_por_defecto": solo_lectura == "on",
        "conteos": conteos,
        "cuentas_visibles": cuentas,
        "farmacias_saldos": farmacias_saldos,
        "farmacias_importes": farmacias_importes,
        "modulo_cashflow": modulo,
        "facturas_solo_pio": farmacias_facturas in ([], ["PIO"]),
        **escrituras,
    }
    ok = (resultado["conecta_como_cf_lectura"] and resultado["solo_lectura_por_defecto"]
          and len(conteos) == len(TABLAS) and cuentas == ["PIO", "RITA", "SL"] and modulo == ["PIO", "RITA"]
          and set(farmacias_saldos) <= {"PIO", "RITA", "SL"} and set(farmacias_importes) <= {"PIO", "RITA"}
          and resultado["facturas_solo_pio"] and all(e["falla"] for e in escrituras.values()))
    resultado["veredicto"] = "ACCESO_OK" if ok else "ACCESO_CON_FALLOS"
    return resultado


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit("uso: probar_acceso_cf_lectura_cashflow.py <host_pooler> <puerto_pooler>")
    contrasena = os.environ.get(VARIABLE)
    if not contrasena:
        print(f"{VARIABLE} no definida: no se conecta")
        return 2
    try:
        resultado = probar(argv[0], int(argv[1]), USUARIO, contrasena)
    except Exception as error:  # noqa: BLE001
        print(f"SIN_CONEXION: {type(error).__name__}: {str(error).splitlines()[0] if str(error) else ''}")
        return 2
    print(json.dumps(resultado, ensure_ascii=False, indent=1, default=str))
    return 0 if resultado["veredicto"] == "ACCESO_OK" else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
