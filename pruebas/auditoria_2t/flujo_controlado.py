"""Hito 2T: alias autorizado y conciliacion controlada de tres facturas Alliance."""

from __future__ import annotations

import json
import os
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tmp_pg_probe_deps")]

import psycopg2
from psycopg2.extras import Json

from src.facturas.runtime_supabase.conciliacion import (
    AlbaranDocumentalTrabajo,
    CandidatoAlbaranSupabase,
    buscar_candidato_albaran,
    dinero,
)


DOCUMENTO = "ffee3c1c-ebcc-4287-99b2-79ccbae45f22"
NUMEROS = ("08009278", "08009277", "08009279")
CODIGO = "ALLIANCE_HEALTHCARE_CENCORA"
NOMBRE = "ALLIANCE HEALTHCARE / CENCORA"
AUTORIDAD = "AUTORIZACION_FUNCIONAL_PIO"
ALIASES = (
    "SAFA",
    "1.- SAFA",
    "ALLIANCE",
    "ALLIANCE HEALTHCARE",
    "ALLIANCE HEALTHCARE ESPAÑA",
    "ALLIANCE HEALTHCARE ESPAÑA, S.A.",
    "CENCORA",
)


def conectar(*, readonly: bool = False):
    conexion = psycopg2.connect(
        os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"],
        sslmode="require",
        connect_timeout=10,
        application_name=f"cf_2t_{'readonly' if readonly else 'controlado'}",
    )
    conexion.set_session(readonly=readonly, autocommit=False)
    return conexion


def precheck() -> dict:
    conexion = conectar(readonly=True)
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "select normalizacion_automatica, conciliacion_automatica, luna_habilitada, "
                "farmacias_habilitadas from public.cf_configuracion where id"
            )
            flags = cursor.fetchone()
            cursor.execute(
                "select numero_factura, importe_total, estado_normalizacion, "
                "estado_conciliacion_cf, estado_revision, proveedor_literal, proveedor_id::text "
                "from public.facturas order by numero_factura"
            )
            facturas = cursor.fetchall()
            cursor.execute(
                "select count(*) from public.facturas where proveedor_literal ilike '%HEFAME%'"
            )
            hefame = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.facturas where farmacia = 'RITA'")
            rita = cursor.fetchone()[0]
            cursor.execute(
                "select (select count(*) from public.documentos_facturas where bloqueado_hasta > now()), "
                "(select count(*) from public.facturas where conciliacion_bloqueado_hasta > now())"
            )
            locks = cursor.fetchone()
        assert flags == (False, False, False, ["PIO"])
        assert len(facturas) == 5
        previas = [fila for fila in facturas if fila[0] not in NUMEROS]
        objetivo = [fila for fila in facturas if fila[0] in NUMEROS]
        assert {(x[0], x[2], x[3]) for x in previas} == {
            ("5011640669", "NORMALIZADA", "CONCILIADA"),
            ("5460017198", "NORMALIZADA", "CONCILIADA"),
        }
        assert len(objetivo) == 3
        assert all(x[2:5] == ("NORMALIZADA", "PENDIENTE_CONCILIAR", "NO_REQUERIDA") for x in objetivo)
        assert hefame == 0 and rita == 0 and locks == (0, 0)
        resultado = {
            "flags": flags,
            "facturas": facturas,
            "hefame": hefame,
            "rita": rita,
            "locks": locks,
        }
        print(json.dumps(resultado, default=str, ensure_ascii=False))
        return resultado
    finally:
        conexion.rollback()
        conexion.close()


def persistir_alias() -> None:
    precheck()
    conexion = conectar()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("select count(*) from public.proveedores")
            assert cursor.fetchone()[0] == 0
            cursor.execute("select count(*) from public.proveedores_alias")
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                "insert into public.proveedores(codigo,nombre,farmatic_id_proveedor,extractor_codigo,nivel_confianza,activo) "
                "values (%s,%s,null,null,'PIO_VALIDADO',true) returning id::text",
                (CODIGO, NOMBRE),
            )
            proveedor_id = cursor.fetchone()[0]
            for alias in ALIASES:
                cursor.execute(
                    "insert into public.proveedores_alias(proveedor_id,alias) values (%s,%s)",
                    (proveedor_id, alias),
                )
            cursor.execute(
                """
                update public.facturas
                   set proveedor_id = %s,
                       provenance = provenance || %s::jsonb,
                       updated_at = now()
                 where documento_id = %s
                   and numero_factura = any(%s)
                   and proveedor_literal = 'ALLIANCE HEALTHCARE ESPANA, S.A.'
                returning numero_factura
                """,
                (
                    proveedor_id,
                    Json({
                        "canonicalizacion_proveedor": {
                            "proveedor_codigo": CODIGO,
                            "regla": AUTORIDAD,
                            "aliases_autorizados": list(ALIASES),
                        }
                    }),
                    DOCUMENTO,
                    list(NUMEROS),
                ),
            )
            actualizadas = sorted(fila[0] for fila in cursor.fetchall())
            assert actualizadas == sorted(NUMEROS)
            cursor.execute(
                "select array_agg(alias order by alias), count(*) from public.proveedores_alias where proveedor_id=%s",
                (proveedor_id,),
            )
            aliases, cantidad = cursor.fetchone()
            assert cantidad == len(ALIASES) and set(aliases) == set(ALIASES)
        conexion.commit()
        print(json.dumps({
            "alias_funcional_registrado": True,
            "proveedor_id": proveedor_id,
            "codigo": CODIGO,
            "nombre": NOMBRE,
            "aliases": ALIASES,
            "provenance": AUTORIDAD,
            "facturas_asociadas": actualizadas,
        }, ensure_ascii=False))
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def construir_matching() -> dict[str, dict]:
    conexion = conectar(readonly=True)
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "select id::text, numero_factura, importe_total, proveedor_literal "
                "from public.facturas where documento_id=%s order by pagina_inicio",
                (DOCUMENTO,),
            )
            facturas = cursor.fetchall()
            assert [fila[1] for fila in facturas] == list(NUMEROS)
            salida = {}
            for factura_id, numero_factura, total, proveedor_literal in facturas:
                cursor.execute(
                    "select id::text,numero_albaran,fecha_albaran,importe_total,tipo_movimiento "
                    "from public.facturas_albaranes_extraidos where factura_id=%s order by orden",
                    (factura_id,),
                )
                documentales = cursor.fetchall()
                fechas = [fila[2] for fila in documentales if fila[2] is not None]
                inicio, fin = min(fechas) - timedelta(days=15), max(fechas) + timedelta(days=15)
                cursor.execute(
                    "select id_contador,farmacia,id_proveedor,proveedor,numero_albaran,fecha,importe_puc,importe_pvp,estado "
                    "from public.albaranes where farmacia='PIO' and fecha between %s and %s",
                    (inicio, fin),
                )
                candidatos = tuple(CandidatoAlbaranSupabase(*fila) for fila in cursor.fetchall())
                detalles = []
                for aid, num, fecha, importe, sentido in documentales:
                    documental = AlbaranDocumentalTrabajo(aid, num, fecha, Decimal(importe), sentido)
                    match = buscar_candidato_albaran(
                        documental,
                        candidatos,
                        proveedor_literal=proveedor_literal,
                    )
                    clase = (
                        "EXACTO" if match.estado == "MATCH_UNICO" and match.coincidencia_numero == "EXACTA"
                        else "ECONOMICO_UNICO" if match.estado == "MATCH_UNICO"
                        else "AMBIGUO" if match.estado == "AMBIGUO"
                        else "NO_LOCALIZADO"
                    )
                    detalles.append({
                        "factura_albaran_extraido_id": aid,
                        "numero": num,
                        "fecha": fecha,
                        "importe_documental": dinero(importe),
                        "sentido": sentido,
                        "clase": clase,
                        "match": match,
                    })
                cursor.execute(
                    "select id::text,descripcion_literal,importe,sentido from public.facturas_movimientos "
                    "where factura_id=%s order by orden",
                    (factura_id,),
                )
                movimientos = cursor.fetchall()
                explicado_albaranes = sum(
                    (
                        -abs(dinero(item["match"].importe_compatible))
                        if item["sentido"] == "ABONO"
                        else dinero(item["match"].importe_compatible)
                        for item in detalles if item["match"].candidato
                    ),
                    Decimal("0.0000"),
                )
                explicado_movimientos = sum(
                    (abs(dinero(fila[2])) if fila[3] == "CARGO" else -abs(dinero(fila[2])) for fila in movimientos),
                    Decimal("0.0000"),
                )
                explicado = dinero(explicado_albaranes + explicado_movimientos)
                salida[numero_factura] = {
                    "factura_id": factura_id,
                    "total": dinero(total),
                    "documentales": detalles,
                    "movimientos": movimientos,
                    "resumen": {
                        clase: sum(item["clase"] == clase for item in detalles)
                        for clase in ("EXACTO", "ECONOMICO_UNICO", "AMBIGUO", "NO_LOCALIZADO")
                    },
                    "importe_explicado": explicado,
                    "diferencia": dinero(Decimal(total) - explicado),
                }
            return salida
    finally:
        conexion.rollback()
        conexion.close()


def mostrar_matching() -> None:
    matching = construir_matching()
    resumen = {}
    for numero, datos in matching.items():
        resumen[numero] = {
            "albaranes": len(datos["documentales"]),
            **datos["resumen"],
            "movimientos": len(datos["movimientos"]),
            "importe_explicado": datos["importe_explicado"],
            "diferencia": datos["diferencia"],
            "no_resueltos": [
                {
                    "numero": item["numero"],
                    "fecha": item["fecha"],
                    "importe": item["importe_documental"],
                    "clase": item["clase"],
                    "candidatos": item["match"].candidatos_finales,
                }
                for item in datos["documentales"]
                if item["clase"] in {"AMBIGUO", "NO_LOCALIZADO"}
            ],
        }
    print(json.dumps(resumen, default=str, ensure_ascii=False))


def conciliar(numero_objetivo: str) -> None:
    if numero_objetivo not in NUMEROS:
        raise ValueError("factura fuera del alcance 2T")
    datos = construir_matching()[numero_objetivo]
    conexion = conectar()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "select numero_factura,estado_normalizacion,estado_conciliacion_cf,estado_revision,proveedor_literal "
                "from public.facturas where id=%s for update",
                (datos["factura_id"],),
            )
            factura = cursor.fetchone()
            assert factura == (
                numero_objetivo,
                "NORMALIZADA",
                "PENDIENTE_CONCILIAR",
                "NO_REQUERIDA",
                "ALLIANCE HEALTHCARE ESPANA, S.A.",
            )
            cursor.execute("select coalesce(max(intento),0)+1 from public.conciliaciones where factura_id=%s", (datos["factura_id"],))
            intento = cursor.fetchone()[0]
            resultado = "CONCILIADA" if abs(datos["diferencia"]) <= Decimal("0.0500") else "DIFERENCIA"
            cursor.execute("update public.conciliaciones set es_actual=false where factura_id=%s and es_actual", (datos["factura_id"],))
            cursor.execute(
                """
                insert into public.conciliaciones(
                    factura_id,intento,disparador,estado,es_actual,tolerancia,
                    importe_factura,importe_explicado,diferencia,resultado,
                    estrategia,provenance,worker_id,finalizado_at
                ) values (%s,%s,'MANUAL','COMPLETADA',true,.05,%s,%s,%s,%s,
                          'MATCHING_CERTIFICADO_V2',%s,'manual-hito-2t-conciliacion',now())
                returning id::text
                """,
                (
                    datos["factura_id"], intento, datos["total"], datos["importe_explicado"],
                    datos["diferencia"], resultado,
                    Json({
                        "fuente": "SUPABASE_ALBARANES",
                        "proveedor_canonico": CODIGO,
                        "regla_alias": AUTORIDAD,
                        "tolerancia": "0.0500",
                        "ventana_dias": 15,
                        "matching": datos["resumen"],
                        "equivalencias_numero_inventadas": False,
                    }),
                ),
            )
            conciliacion_id = cursor.fetchone()[0]
            orden = 0
            for item in datos["documentales"]:
                orden += 1
                match = item["match"]
                candidato = match.candidato
                aplicado = (
                    -abs(dinero(match.importe_compatible))
                    if candidato and item["sentido"] == "ABONO"
                    else dinero(match.importe_compatible)
                    if candidato
                    else Decimal("0.0000")
                )
                cursor.execute(
                    """
                    insert into public.conciliacion_detalles(
                        conciliacion_id,orden,factura_albaran_extraido_id,
                        albaran_farmacia,albaran_id_contador,numero_albaran_documental,
                        numero_albaran_farmatic,coincidencia_numero_literal,tipo_relacion,
                        importe_documental,importe_farmatic,importe_aplicado,diferencia,estado,provenance
                    ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        conciliacion_id, orden, item["factura_albaran_extraido_id"],
                        candidato.farmacia if candidato else None,
                        candidato.id_contador if candidato else None,
                        item["numero"], candidato.numero_albaran if candidato else None,
                        match.coincidencia_numero == "EXACTA",
                        "UNO_A_UNO" if candidato else "SIN_COINCIDENCIA",
                        item["importe_documental"], match.importe_compatible, aplicado,
                        dinero(item["importe_documental"] - aplicado),
                        "COINCIDE" if candidato else "DIFERENCIA",
                        Json({
                            "fuente": "ALBARANES_SUPABASE",
                            "regla_alias": AUTORIDAD,
                            "estado_matching": item["clase"],
                            "candidatos_finales": match.candidatos_finales,
                            "proveedor_literal_operacional": candidato.proveedor if candidato else None,
                            "id_proveedor_literal": candidato.id_proveedor if candidato else None,
                            "fecha_documental": item["fecha"].isoformat(),
                            "fecha_operacional": candidato.fecha.isoformat() if candidato else None,
                        }),
                    ),
                )
            for movimiento_id, descripcion, importe, sentido in datos["movimientos"]:
                orden += 1
                aplicado = abs(dinero(importe)) if sentido == "CARGO" else -abs(dinero(importe))
                cursor.execute(
                    """
                    insert into public.conciliacion_detalles(
                        conciliacion_id,orden,factura_movimiento_id,coincidencia_numero_literal,
                        tipo_relacion,importe_documental,importe_aplicado,diferencia,estado,provenance
                    ) values (%s,%s,%s,false,'MOVIMIENTO_NO_FARMATIC',%s,%s,0,%s,%s)
                    """,
                    (
                        conciliacion_id, orden, movimiento_id, importe, aplicado,
                        "COINCIDE" if resultado == "CONCILIADA" else "DIFERENCIA",
                        Json({
                            "fuente": "MOVIMIENTO_DOCUMENTAL",
                            "concepto_literal": descripcion,
                            "sentido": sentido,
                            "regla_alias": AUTORIDAD,
                        }),
                    ),
                )
            estado = "CONCILIADA" if resultado == "CONCILIADA" else "PENDIENTE_CONCILIAR"
            cursor.execute(
                """
                update public.facturas
                   set estado_conciliacion_cf=%s,diferencia_albaranes=%s,
                       conciliacion_intentos=%s,conciliacion_bloqueado_hasta=null,
                       conciliacion_bloqueado_por=null,conciliacion_reintento_solicitado_at=null,
                       updated_at=now()
                 where id=%s
                """,
                (estado, datos["diferencia"], intento, datos["factura_id"]),
            )
        conexion.commit()
        print(json.dumps({
            "factura": numero_objetivo,
            "conciliacion_id": conciliacion_id,
            "intento": intento,
            "resultado": resultado,
            "estado": estado,
            "matching": datos["resumen"],
            "importe_explicado": datos["importe_explicado"],
            "diferencia": datos["diferencia"],
        }, default=str, ensure_ascii=False))
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def cierre() -> None:
    conexion = conectar(readonly=True)
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "select p.codigo,p.nombre,p.farmatic_id_proveedor,p.nivel_confianza,p.activo,"
                "array_agg(a.alias order by a.alias) from public.proveedores p join public.proveedores_alias a "
                "on a.proveedor_id=p.id where p.codigo=%s group by p.id",
                (CODIGO,),
            )
            proveedor = cursor.fetchone()
            cursor.execute(
                """
                select f.numero_factura,f.importe_total,f.estado_normalizacion,
                       f.estado_conciliacion_cf,f.estado_revision,f.proveedor_literal,
                       p.codigo,c.resultado,c.importe_explicado,c.diferencia,
                       count(cd.id),count(cd.albaran_id_contador),
                       count(*) filter(where cd.tipo_relacion='SIN_COINCIDENCIA')
                from public.facturas f
                left join public.proveedores p on p.id=f.proveedor_id
                left join public.conciliaciones c on c.factura_id=f.id and c.es_actual
                left join public.conciliacion_detalles cd on cd.conciliacion_id=c.id
                group by f.id,p.codigo,c.id order by f.numero_factura
                """
            )
            facturas = cursor.fetchall()
            cursor.execute(
                "select normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas "
                "from public.cf_configuracion where id"
            )
            flags = cursor.fetchone()
            cursor.execute(
                "select (select count(*) from public.facturas),"
                "(select count(*) from public.facturas where proveedor_literal ilike '%HEFAME%'),"
                "(select count(*) from public.facturas where farmacia='RITA'),"
                "(select count(*) from public.documentos_facturas where bloqueado_hasta>now()),"
                "(select count(*) from public.facturas where conciliacion_bloqueado_hasta>now())"
            )
            aislamiento = cursor.fetchone()
        assert proveedor is not None and proveedor[2] is None and proveedor[3:5] == ("PIO_VALIDADO", True)
        assert set(proveedor[5]) == set(ALIASES)
        assert flags == (False, False, False, ["PIO"])
        assert aislamiento == (5, 0, 0, 0, 0)
        previas = [fila for fila in facturas if fila[0] not in NUMEROS]
        assert {(x[0], x[1], x[2], x[3]) for x in previas} == {
            ("5011640669", Decimal("448.0000"), "NORMALIZADA", "CONCILIADA"),
            ("5460017198", Decimal("177.7400"), "NORMALIZADA", "CONCILIADA"),
        }
        print(json.dumps({"proveedor": proveedor, "facturas": facturas, "flags": flags, "aislamiento": aislamiento}, default=str, ensure_ascii=False))
    finally:
        conexion.rollback()
        conexion.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("fase requerida")
    fase = sys.argv[1]
    if fase == "precheck":
        precheck()
    elif fase == "persistir_alias":
        persistir_alias()
    elif fase == "match":
        mostrar_matching()
    elif fase == "conciliar" and len(sys.argv) == 3:
        conciliar(sys.argv[2])
    elif fase == "cierre":
        cierre()
    else:
        raise SystemExit("fase no admitida")
