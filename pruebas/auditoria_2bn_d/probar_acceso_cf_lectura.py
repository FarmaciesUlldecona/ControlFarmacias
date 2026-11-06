"""Hito 2BN-D: prueba de acceso del rol de solo lectura cf_lectura por el pooler de Supabase.

Uso (terminal de Pio; la contrasena SOLO en la variable de entorno CF_LECTURA_PASSWORD, nunca como argumento ni
impresa):
  python -B pruebas/auditoria_2bn_d/probar_acceso_cf_lectura.py <host_pooler> <puerto_pooler>

Usuario fijo ``cf_lectura.<project_ref>``. Comprueba: conecta (TLS), lee los conteos de facturas, conciliaciones y
documentos, solo ve PIO y un INSERT y una RPC de escritura FALLAN. Cada intento de escritura va en su propia
transaccion READ WRITE (para probar los privilegios, no solo el modo de solo lectura) que se deshace SIEMPRE, tambien
si inesperadamente funcionara (entonces la prueba falla). Sin salidas en disco. Codigo 0 = todo OK; 3 = alguna
comprobacion fallida; 2 = sin contrasena o sin conexion.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT_REF = "vklaiuytvegkelgyspxc"
USUARIO = f"cf_lectura.{PROJECT_REF}"
VARIABLE = "CF_LECTURA_PASSWORD"
APPLICATION_NAME = "cf_2bnd_prueba_acceso"

CONTEOS = ("select (select count(*) from public.facturas), (select count(*) from public.conciliaciones), "
           "(select count(*) from public.documentos_facturas)")
FARMACIAS = ("select array(select distinct farmacia from (select farmacia from public.documentos_facturas "
             "union all select farmacia from public.facturas union all select farmacia from public.albaranes) t "
             "order by 1)")
INSERT = "insert into public.historial_facturas default values"
RPC = "select public.cf_solicitar_reprocesado('00000000-0000-4000-8000-000000000000'::uuid, 'prueba 2BN-D')"
DENEGADO = ("42501", "25006")  # insufficient_privilege, read_only_sql_transaction


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
        cur.execute(CONTEOS)
        facturas, conciliaciones, documentos = cur.fetchone()
        cur.execute(FARMACIAS)
        farmacias = list(cur.fetchone()[0])
        conn.autocommit = False
        insert, rpc = _escritura_falla(conn, INSERT), _escritura_falla(conn, RPC)
    finally:
        conn.close()
    resultado = {
        "conecta_como_cf_lectura": rol == "cf_lectura",
        "solo_lectura_por_defecto": solo_lectura == "on",
        "conteos": {"facturas": facturas, "conciliaciones": conciliaciones, "documentos_facturas": documentos},
        "farmacias_visibles": farmacias,
        "solo_pio": farmacias == ["PIO"],
        "insert": insert,
        "rpc_escritura": rpc,
    }
    resultado["veredicto"] = "ACCESO_OK" if (resultado["conecta_como_cf_lectura"]
                                              and resultado["solo_lectura_por_defecto"] and resultado["solo_pio"]
                                              and insert["falla"] and rpc["falla"]) else "ACCESO_CON_FALLOS"
    return resultado


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit("uso: probar_acceso_cf_lectura.py <host_pooler> <puerto_pooler>")
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
