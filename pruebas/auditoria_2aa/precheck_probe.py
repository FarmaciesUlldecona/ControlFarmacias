"""Precheck READ ONLY del hito 2AA."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))
import psycopg2

HASHES = (
    "39beca0337f40e79b83966c636a50230eacbc00e55278ffd1afae5e0b0100d5a",
    "51ae2e5c8e311d9fb19e95d42ea7f8c6873524d3e32a2034eabbb1e834be45dd",
)


def main():
    connection = psycopg2.connect(
        os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"], sslmode="require",
        connect_timeout=10, application_name="cf_2aa_precheck_readonly",
    )
    connection.set_session(readonly=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "select id::text,archivo_nombre,archivo_hash,farmacia,estado_lectura,"
                "estado_persistencia,bloqueado_por,bloqueado_hasta,reprocesar_solicitado_at "
                "from public.documentos_facturas where archivo_hash=any(%s) order by archivo_hash",
                (list(HASHES),),
            )
            documents = cursor.fetchall()
            cursor.execute(
                "select codigo,nombre,farmatic_id_proveedor,nivel_confianza,activo "
                "from public.proveedores order by codigo"
            )
            providers = cursor.fetchall()
            cursor.execute(
                "select id_proveedor,proveedor,count(*) from public.albaranes "
                "where farmacia='PIO' and (proveedor ilike '%HEFAME%' or id_proveedor='3') "
                "group by id_proveedor,proveedor order by id_proveedor,proveedor"
            )
            hefame_operational = cursor.fetchall()
            cursor.execute(
                "select count(*) from pg_stat_activity where pid<>pg_backend_pid() "
                "and (application_name ilike '%worker%' or application_name ilike '%runtime%')"
            )
            workers = cursor.fetchone()[0]
        print(json.dumps({
            "documents": documents, "providers": providers,
            "hefame_operational": hefame_operational, "workers": workers,
        }, default=str, ensure_ascii=False))
    finally:
        connection.rollback()
        connection.close()


if __name__ == "__main__":
    main()
