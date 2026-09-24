"""Conciliacion 2K atomica y exclusiva de la factura Logista revalidada."""
import json
import os
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))

import psycopg2
from psycopg2.extras import Json

from src.facturas.runtime_supabase.conciliacion import (
    AlbaranDocumentalTrabajo,
    CandidatoAlbaranSupabase,
    buscar_candidato_albaran,
    conciliar_importes,
    detalle_desde_busqueda,
)

DOCUMENTO_ID = "0387e00a-e861-48f0-88ad-9236b92078e8"
FACTURA_ID = "14f7808e-cb2b-41fd-94fb-6eb82703de21"
WORKER = "manual-hito-2k-conciliacion"


def main():
    dry_run = "--dry-run" in sys.argv[1:]
    conexion = psycopg2.connect(os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"])
    try:
        with conexion.cursor() as cursor:
            cursor.execute("set local lock_timeout = '5s'")
            cursor.execute("set local statement_timeout = '60s'")
            cursor.execute(
                "select normalizacion_automatica,conciliacion_automatica,"
                "luna_habilitada,farmacias_habilitadas "
                "from public.cf_configuracion where id=true"
            )
            if cursor.fetchone() != (False, False, False, ["PIO"]):
                raise RuntimeError("flags productivos no seguros")
            cursor.execute(
                "select f.farmacia,f.importe_total,f.proveedor_literal,"
                "n.resultado_json->>'documento_completo_demostrado' "
                "from public.facturas f join public.normalizacion_ejecuciones n "
                "on n.id=f.normalizacion_ejecucion_id "
                "where f.id=%s and f.documento_id=%s for update of f",
                (FACTURA_ID, DOCUMENTO_ID),
            )
            factura = cursor.fetchone()
            esperado = ("PIO", Decimal("448.0000"), "LOGISTA PHARMA S.A.U.", "true")
            if factura != esperado:
                raise RuntimeError("factura sin contrato documental 2J.1")
            cursor.execute(
                "select id::text,numero_albaran,fecha_albaran,importe_total,tipo_movimiento "
                "from public.facturas_albaranes_extraidos "
                "where factura_id=%s order by orden",
                (FACTURA_ID,),
            )
            extraidos = cursor.fetchall()
            if len(extraidos) != 1:
                raise RuntimeError("numero de albaranes documentales distinto de uno")
            fila = extraidos[0]
            documental = AlbaranDocumentalTrabajo(*fila)
            inicio = documental.fecha - timedelta(days=15)
            fin = documental.fecha + timedelta(days=15)
            cursor.execute(
                "select id_contador,farmacia,id_proveedor::text,proveedor,numero_albaran,"
                "fecha,importe_puc,importe_pvp,estado from public.albaranes "
                "where farmacia='PIO' and fecha between %s and %s",
                (inicio, fin),
            )
            candidatos = [CandidatoAlbaranSupabase(*row) for row in cursor.fetchall()]
            busqueda = buscar_candidato_albaran(
                documental,
                candidatos,
                proveedor_literal=factura[2],
                farmatic_id_proveedor=None,
            )
            candidato = busqueda.candidato
            autorizado = (
                busqueda.estado == "MATCH_UNICO"
                and candidato is not None
                and candidato.id_contador == 285484
                and busqueda.coincidencia_numero == "DIFERENTE"
                and busqueda.importe_compatible == Decimal("448.0000")
                and (candidato.fecha - documental.fecha).days == 6
            )
            if not autorizado:
                raise RuntimeError(f"matching no autorizado: {busqueda}")
            detalle = detalle_desde_busqueda(documental, busqueda)
            resultado = conciliar_importes(
                factura[1], [detalle], tolerancia=Decimal("0.05")
            )
            if resultado.resultado != "CONCILIADA" or resultado.diferencia != 0:
                raise RuntimeError(f"resultado economico no autorizado: {resultado}")
            cursor.execute(
                "select id::text,intento,resultado,importe_explicado,diferencia,es_actual "
                "from public.conciliaciones where factura_id=%s order by intento for update",
                (FACTURA_ID,),
            )
            anteriores = cursor.fetchall()
            historico_esperado = (
                1, "DIFERENCIA", Decimal("0.0000"), Decimal("448.0000"), True
            )
            if len(anteriores) != 1 or anteriores[0][1:] != historico_esperado:
                raise RuntimeError("conciliacion historica fuera del estado esperado")
            historica_id = anteriores[0][0]
            cursor.execute(
                "update public.conciliaciones set es_actual=false "
                "where id=%s and es_actual=true",
                (historica_id,),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("no se pudo cerrar la actualidad del intento historico")
            cursor.execute(
                "insert into public.conciliaciones "
                "(factura_id,intento,disparador,estado,es_actual,tolerancia,importe_factura,"
                "importe_explicado,diferencia,resultado,estrategia,provenance,worker_id,finalizado_at) "
                "values (%s,2,'MANUAL','COMPLETADA',true,%s,%s,%s,%s,%s,%s,%s,%s,now()) "
                "returning id::text",
                (
                    FACTURA_ID,
                    resultado.tolerancia,
                    resultado.importe_factura,
                    resultado.importe_explicado,
                    resultado.diferencia,
                    resultado.resultado,
                    "PROVEEDOR_FECHA_IMPORTE_CANDIDATO_UNICO",
                    Json({
                        "fuente": "ALBARANES_SUPABASE",
                        "farmatic_consultado": False,
                        "contrato_documental": "2J.1",
                        "numeros_equivalentes": False,
                    }),
                    WORKER,
                ),
            )
            nueva_id = cursor.fetchone()[0]
            cursor.execute(
                "insert into public.conciliacion_detalles "
                "(conciliacion_id,orden,factura_albaran_extraido_id,albaran_farmacia,"
                "albaran_id_contador,numero_albaran_documental,numero_albaran_farmatic,"
                "coincidencia_numero_literal,tipo_relacion,importe_documental,importe_farmatic,"
                "importe_aplicado,diferencia,estado,provenance) "
                "values (%s,1,%s,%s,%s,%s,%s,false,'UNO_A_UNO',%s,%s,%s,0,'COINCIDE',%s)",
                (
                    nueva_id,
                    documental.id,
                    candidato.farmacia,
                    candidato.id_contador,
                    documental.numero,
                    candidato.numero_albaran,
                    documental.importe,
                    busqueda.importe_compatible,
                    detalle.importe_aplicado,
                    Json(dict(detalle.provenance)),
                ),
            )
            cursor.execute(
                "update public.facturas set estado_conciliacion_cf='CONCILIADA',"
                "diferencia_albaranes=%s,conciliacion_intentos=2,"
                "conciliacion_bloqueado_hasta=null,conciliacion_bloqueado_por=null,"
                "conciliacion_reintento_solicitado_at=null,updated_at=now() "
                "where id=%s",
                (resultado.diferencia, FACTURA_ID),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("factura objetivo no actualizada")
            cursor.execute("select count(*) from public.facturas")
            if cursor.fetchone()[0] != 1:
                raise RuntimeError("se altero el total de facturas")
            cursor.execute(
                "select count(*) from public.conciliaciones where factura_id=%s",
                (FACTURA_ID,),
            )
            if cursor.fetchone()[0] != 2:
                raise RuntimeError("numero final de conciliaciones incorrecto")
        if dry_run:
            conexion.rollback()
        else:
            conexion.commit()
        print(json.dumps({
            "conciliacion_id": nueva_id,
            "resultado": resultado.resultado,
            "importe_explicado": str(resultado.importe_explicado),
            "diferencia": str(resultado.diferencia),
            "candidato": 285484,
            "coincidencia_numero": "DIFERENTE",
            "diferencia_fecha_dias": 6,
            "dry_run": dry_run,
        }, sort_keys=True))
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


if __name__ == "__main__":
    main()
