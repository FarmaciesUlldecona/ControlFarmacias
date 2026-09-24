"""Cierre productivo READ_ONLY del Hito 2V."""
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))
import psycopg2

DOC = "ffee3c1c-ebcc-4287-99b2-79ccbae45f22"


def main():
    c = psycopg2.connect(os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"], sslmode="require",
                         connect_timeout=10, application_name="cf_2v_cierre_readonly")
    c.set_session(readonly=True)
    try:
        with c.cursor() as q:
            q.execute("select normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas from public.cf_configuracion where id=true")
            flags = q.fetchone()
            q.execute(
                """select f.numero_factura,f.importe_total,f.estado_normalizacion,
                f.estado_conciliacion_cf,f.estado_revision,f.normalizacion_ejecucion_id::text,
                (select count(*) from public.facturas_albaranes_extraidos a where a.factura_id=f.id),
                (select count(*) from public.facturas_movimientos m where m.factura_id=f.id),
                c.id::text,c.resultado,c.importe_explicado,c.diferencia,
                (select count(*) from public.conciliacion_detalles cd where cd.conciliacion_id=c.id),
                (select count(*) from public.conciliacion_detalles cd where cd.conciliacion_id=c.id and cd.albaran_id_contador is not null)
                from public.facturas f
                left join public.conciliaciones c on c.factura_id=f.id and c.es_actual
                order by f.numero_factura"""
            )
            facturas = q.fetchall()
            q.execute(
                "select estado_lectura,estado_persistencia,cantidad_documentos_detectados,tipo_contenido,"
                "jsonb_array_length(inventario_facturas),numero_paginas,bloqueado_por,bloqueado_hasta>now() "
                "from public.documentos_facturas where id=%s", (DOC,)
            )
            documento = q.fetchone()
            q.execute(
                "select (select count(*) from public.facturas),"
                "(select count(*) from public.facturas where estado_normalizacion='NORMALIZADA'),"
                "(select count(*) from public.facturas where estado_conciliacion_cf='CONCILIADA'),"
                "(select count(*) from public.facturas where proveedor_literal ilike '%%HEFAME%%'),"
                "(select count(*) from public.facturas where farmacia='RITA'),"
                "(select count(*) from public.documentos_facturas where bloqueado_hasta>now()),"
                "(select count(*) from public.facturas where conciliacion_bloqueado_hasta>now())"
            )
            aislamiento = q.fetchone()
            q.execute(
                "select count(*),count(*) filter(where worker_id='manual-hito-2v-renormalizacion-08009277') "
                "from public.normalizacion_ejecuciones"
            )
            ejecuciones = q.fetchone()
            q.execute(
                "select count(*) from public.normalizacion_ejecuciones where worker_id='manual-hito-2v-renormalizacion-08009277' "
                "and documento_id<>%s", (DOC,)
            )
            otros_documentos = q.fetchone()[0]
            q.execute(
                """select i.normalizacion_ejecucion_id::text,i.codigo,i.bloqueante,count(*)
                from public.facturas_incidencias i join public.facturas f on f.id=i.factura_id
                where f.documento_id=%s and f.numero_factura='08009277'
                group by i.normalizacion_ejecucion_id,i.codigo,i.bloqueante
                order by i.normalizacion_ejecucion_id::text,i.codigo""", (DOC,)
            )
            incidencias = q.fetchall()
        assert flags == (False, False, False, ["PIO"])
        assert len(facturas) == 5
        assert all(x[2:5] == ("NORMALIZADA", "CONCILIADA", "NO_REQUERIDA") for x in facturas)
        objetivo = next(x for x in facturas if x[0] == "08009277")
        assert objetivo[1] == Decimal("10111.5500")
        assert objetivo[5:8] == ("4ce09682-d80a-4f7b-9ad8-d5256a3f4d6c", 160, 7)
        assert objetivo[9:14] == ("CONCILIADA", Decimal("10111.5800"), Decimal("-0.0300"), 167, 160)
        previas = {x[0]: x for x in facturas if x[0] in {"5011640669", "5460017198"}}
        assert previas["5011640669"][1:5] == (Decimal("448.0000"), "NORMALIZADA", "CONCILIADA", "NO_REQUERIDA")
        assert previas["5460017198"][1:5] == (Decimal("177.7400"), "NORMALIZADA", "CONCILIADA", "NO_REQUERIDA")
        assert documento == ("NORMALIZADA", "COMPLETA", 3, "LOTE_FACTURAS", 3, 11, None, None), documento
        assert aislamiento == (5, 5, 5, 0, 0, 0, 0)
        assert ejecuciones[1] == 1 and otros_documentos == 0
        assert not any(x[2] for x in incidencias)
        print(json.dumps({
            "flags": flags, "facturas": facturas, "documento": documento,
            "aislamiento": aislamiento, "ejecuciones": ejecuciones,
            "otros_documentos_procesados_2v": otros_documentos,
            "incidencias_08009277": incidencias,
        }, default=str, ensure_ascii=False))
    finally:
        c.rollback()
        c.close()


if __name__ == "__main__":
    main()
