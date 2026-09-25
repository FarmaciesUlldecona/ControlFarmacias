"""Hito 2AO rev3: preflight, snapshot y postcheck productivos ESTRICTAMENTE READ_ONLY.

Uso:
  python pruebas/auditoria_2ao/snapshot_readonly.py snapshot <salida.json>
  python pruebas/auditoria_2ao/snapshot_readonly.py comparar <pre.json> <post.json> [<documento_id>]

``snapshot`` abre una sesion ``readonly=True`` tras demostrar el project ref y
vuelca operacion, conteos, candidatos del ordering oficial, huellas POR FILA sobre
listas EXPLICITAS de columnas de datos y el contenido completo de las tablas.
No llama a ninguna RPC. ``comparar`` no se conecta a nada.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
PROJECT_REF = "vklaiuytvegkelgyspxc"

# Columnas de DATOS por tabla. Se excluyen columnas tecnicas: marcas de
# actualizacion (fecha_actualizacion/updated_at), estado de claim/reintento de
# conciliacion y las columnas tecnicas anadidas por la migracion 17
# (intentos_fallo_normalizacion, ultima_clase_fallo, clase_fallo).
COLUMNAS_HUELLA: dict[str, tuple[str, ...]] = {
    "facturas": (
        "id", "documento_id", "farmacia", "pagina_inicio", "pagina_fin", "tipo_documento", "categoria",
        "requiere_conciliacion_albaranes", "id_proveedor_albaranes", "proveedor_nombre", "proveedor_cif",
        "numero_factura", "fecha_factura", "moneda", "base_imponible_total", "iva_total",
        "recargo_equivalencia_total", "importe_total", "cuadre_fiscal_correcto", "diferencia_cuadre",
        "confianza_extraccion", "requiere_revision", "motivo_revision", "estado_conciliacion",
        "diferencia_albaranes", "diferencia_aceptada_automaticamente", "estado_pago", "validada_manualmente",
        "validada_por", "fecha_validacion", "observaciones", "datos_extraidos", "fecha_creacion",
        "proyeccion_clave", "proveedor_id", "proveedor_literal", "estado_normalizacion",
        "estado_conciliacion_cf", "estado_revision", "normalizacion_ejecucion_id", "provenance",
    ),
    "normalizacion_ejecuciones": (
        "id", "documento_id", "idempotency_key", "intento", "disparador", "estado", "proveedor_id",
        "extractor_usado", "normalizador_version", "resultado_hash", "uso_ocr", "uso_luna", "luna_modelo",
        "luna_campos", "tokens_entrada", "tokens_salida", "tokens_total", "coste_luna", "pasos",
        "resultado_json", "worker_id", "iniciado_at", "finalizado_at", "created_at", "error_codigo",
        "error_detalle",
    ),
    "conciliaciones": (
        "id", "factura_id", "intento", "disparador", "estado", "es_actual", "tolerancia", "importe_factura",
        "importe_explicado", "diferencia", "resultado", "estrategia", "provenance", "worker_id",
        "iniciado_at", "finalizado_at", "created_at", "error_codigo", "error_detalle",
    ),
    "conciliacion_detalles": (
        "id", "conciliacion_id", "orden", "factura_albaran_extraido_id", "factura_movimiento_id",
        "albaran_farmacia", "albaran_id_contador", "numero_albaran_documental", "numero_albaran_farmatic",
        "coincidencia_numero_literal", "tipo_relacion", "importe_documental", "importe_farmatic",
        "importe_aplicado", "diferencia", "estado", "provenance", "created_at",
    ),
    "facturas_vencimientos": (
        "id", "factura_id", "fecha_vencimiento", "importe", "orden", "confianza_extraccion", "fecha_creacion",
        "provenance", "literal",
    ),
    "facturas_movimientos": (
        "id", "factura_id", "normalizacion_ejecucion_id", "orden", "categoria", "descripcion_literal",
        "sentido", "base", "iva", "recargo_equivalencia", "importe", "independiente", "conciliable_farmatic",
        "provenance", "created_at",
    ),
    "documentos_facturas": (
        "id", "farmacia", "archivo_nombre", "archivo_ruta", "archivo_hash", "estado_lectura",
        "requiere_revision", "observaciones", "datos_extraidos", "fecha_importacion", "numero_paginas",
        "cantidad_documentos_detectados", "tipo_contenido", "texto_extraido", "necesita_lectura_visual",
        "intentos_lectura", "ultimo_error_lectura", "fecha_inicio_lectura", "fecha_fin_lectura",
        "proximo_reintento_at", "bloqueado_hasta", "bloqueado_por", "ultimo_error_codigo",
        "reprocesar_solicitado_at", "procesamiento_version", "inventario_facturas", "estado_persistencia",
    ),
    # Tablas hijas adicionales (no pedidas explicitamente; se vigilan igual).
    "facturas_impuestos": (
        "id", "factura_id", "concepto", "base_imponible", "tipo_iva", "cuota_iva", "tipo_recargo_equivalencia",
        "cuota_recargo_equivalencia", "orden", "confianza_extraccion", "fecha_creacion", "total_tramo",
        "provenance", "literal",
    ),
    "facturas_ajustes": (
        "id", "factura_id", "tipo_ajuste", "descripcion", "importe", "incluido_en_base", "incluido_en_total",
        "orden", "confianza_extraccion", "fecha_creacion", "provenance", "literal",
    ),
    "facturas_albaranes_extraidos": (
        "id", "factura_id", "numero_albaran", "fecha_albaran", "tipo_movimiento", "importe_base",
        "importe_total", "descripcion", "orden", "confianza_extraccion", "fecha_creacion", "provenance",
        "literal",
    ),
    "facturas_incidencias": (
        "id", "documento_id", "factura_id", "normalizacion_ejecucion_id", "codigo", "categoria", "severidad",
        "bloqueante", "mensaje_usuario", "detalle_tecnico", "estado", "provenance", "created_at",
        "resuelta_at", "resuelta_por",
    ),
    "historial_facturas": (
        "id", "documento_id", "factura_id", "evento", "origen", "actor", "estado_anterior", "estado_nuevo",
        "detalle", "created_at",
    ),
}

# Como localizar el documento dueno de cada fila (para atribuir filas nuevas o cambios).
DUENO = {
    "documentos_facturas": "t.id",
    "normalizacion_ejecuciones": "t.documento_id",
    "facturas": "t.documento_id",
    "facturas_incidencias": "coalesce(t.documento_id,(select f.documento_id from public.facturas f where f.id=t.factura_id))",
    "historial_facturas": "coalesce(t.documento_id,(select f.documento_id from public.facturas f where f.id=t.factura_id))",
    "conciliaciones": "(select f.documento_id from public.facturas f where f.id=t.factura_id)",
    "conciliacion_detalles": ("(select f.documento_id from public.conciliaciones c join public.facturas f "
                              "on f.id=c.factura_id where c.id=t.conciliacion_id)"),
}
for _t in ("facturas_vencimientos", "facturas_movimientos", "facturas_impuestos", "facturas_ajustes",
           "facturas_albaranes_extraidos"):
    DUENO[_t] = "(select f.documento_id from public.facturas f where f.id=t.factura_id)"

SQL_ELEGIBLES = (
    "select d.id::text, d.archivo_hash, d.fecha_importacion::text, d.estado_lectura, d.estado_persistencia, "
    "d.reprocesar_solicitado_at::text, d.proximo_reintento_at::text, d.intentos_fallo_normalizacion "
    "from public.documentos_facturas d cross join public.cf_configuracion c "
    "where c.id = true and d.farmacia = any(c.farmacias_habilitadas) "
    "and d.estado_lectura in ('PENDIENTE','ERROR') "
    "and coalesce(d.proximo_reintento_at,'-infinity'::timestamptz) <= now() "
    "and coalesce(d.bloqueado_hasta,'-infinity'::timestamptz) <= now() "
    "order by (d.reprocesar_solicitado_at is not null) desc, d.fecha_importacion, d.id"
)


def _conectar():
    sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))
    from dotenv import dotenv_values
    import psycopg2

    dsn = os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"]
    app = urlparse(dotenv_values(ROOT / ".env").get("SUPABASE_URL", ""))
    db = urlparse(dsn)
    ref = (app.hostname or "").split(".")[0]
    assert ref == PROJECT_REF and (
        db.hostname == f"db.{ref}.supabase.co"
        or ((db.hostname or "").endswith(".pooler.supabase.com")
            and unquote(db.username or "").endswith("." + ref))
    ), "DESTINO_PRODUCTIVO_NO_DEMOSTRADO"
    conn = psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name="cf_2ao_readonly")
    conn.set_session(readonly=True, autocommit=False)
    return ref, conn


def snapshot(salida: Path) -> None:
    ref, conn = _conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("set local statement_timeout='120s'")

            def rows(sql):
                cur.execute(sql)
                return cur.fetchall()

            out = {"project_ref": ref,
                   "transaction_read_only": rows("select current_setting('transaction_read_only')")[0][0],
                   "capturado_utc": rows("select now()::text")[0][0],
                   "columnas_huella": COLUMNAS_HUELLA}
            out["migracion_17"] = rows(
                "select to_regprocedure('public.cf_cerrar_replay_normalizacion(uuid,text,uuid,text)') is not null,"
                "to_regprocedure('public.cf_registrar_fallo_normalizacion(uuid,text,text,text,text,text,text)') is not null,"
                "exists(select 1 from information_schema.columns where table_schema='public' "
                "and table_name='documentos_facturas' and column_name='intentos_fallo_normalizacion'),"
                "pg_get_constraintdef((select oid from pg_constraint where conrelid='public.documentos_facturas'::regclass "
                "and contype='c' and pg_get_constraintdef(oid) like '%PROVEEDOR_NO_SOPORTADO%' limit 1)) is not null")[0]
            out["selector_nucleo"] = rows(
                "select pg_get_functiondef('public.cf_reclamar_documento_normalizacion_nucleo'::regproc)")[0][0]
            out["flags"] = list(rows(
                "select normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas::text "
                "from public.cf_configuracion where id=true")[0])
            out["cf_configuracion"] = rows("select to_jsonb(c)::text from public.cf_configuracion c")[0][0]
            out["locks"] = list(rows(
                "select (select count(*) from public.documentos_facturas where bloqueado_hasta>now()),"
                "(select count(*) from public.facturas where conciliacion_bloqueado_hasta>now())")[0])
            out["claims"] = rows("select count(*) from public.documentos_facturas where bloqueado_por is not null")[0][0]
            out["workers"] = rows(
                "select application_name,state,count(*) from pg_stat_activity where pid<>pg_backend_pid() and "
                "(application_name ilike '%worker%' or application_name ilike '%runtime%') group by 1,2 order by 1,2")
            out["documentos_por_estado"] = rows(
                "select farmacia,estado_lectura,estado_persistencia,count(*) from public.documentos_facturas "
                "group by 1,2,3 order by 1,2,3")
            out["normalizando"] = rows(
                "select count(*) from public.documentos_facturas where estado_lectura='NORMALIZANDO'")[0][0]
            out["error"] = rows("select count(*) from public.documentos_facturas where estado_lectura='ERROR'")[0][0]
            out["proveedor_no_soportado"] = rows(
                "select count(*) from public.documentos_facturas where estado_lectura='PROVEEDOR_NO_SOPORTADO'")[0][0]
            out["con_intentos_fallo"] = rows(
                "select count(*) from public.documentos_facturas where intentos_fallo_normalizacion>0 "
                "or ultima_clase_fallo is not null")[0][0]
            out["conteos"] = {t: rows(f"select count(*) from public.{t}")[0][0] for t in COLUMNAS_HUELLA}
            elegibles = rows(SQL_ELEGIBLES)
            out["elegibles"] = {"total": len(elegibles), "primeros_5": [list(e) for e in elegibles[:5]]}
            out["hefame_0563834757"] = rows(
                "select f.id::text, md5(to_jsonb(f)::text) from public.facturas f where f.numero_factura='0563834757'")
            huellas = {}
            for tabla, columnas in COLUMNAS_HUELLA.items():
                lista = ",".join(f"t.{c}" for c in columnas)
                huellas[tabla] = {
                    r[0]: [r[1], r[2]] for r in rows(
                        f"select t.id::text, md5(to_jsonb(r)::text), ({DUENO[tabla]})::text "
                        f"from public.{tabla} t cross join lateral (select {lista}) r order by t.id")
                }
            out["huellas_por_fila"] = huellas
            out["volcado"] = {t: [r[0] for r in rows(f"select to_jsonb(t)::text from public.{t} t order by t.id")]
                              for t in COLUMNAS_HUELLA}
    finally:
        conn.rollback()
        conn.close()
    salida.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    resumen = {k: out[k] for k in ("project_ref", "transaction_read_only", "capturado_utc", "migracion_17",
                                    "flags", "locks", "claims", "workers", "documentos_por_estado",
                                    "normalizando", "error", "proveedor_no_soportado", "con_intentos_fallo",
                                    "conteos", "elegibles", "hefame_0563834757")}
    print(json.dumps(resumen, ensure_ascii=False, indent=1, default=str))


def comparar(pre_ruta: Path, post_ruta: Path, documento: str | None) -> None:
    pre = json.loads(pre_ruta.read_text(encoding="utf-8"))
    post = json.loads(post_ruta.read_text(encoding="utf-8"))
    informe = {"documento_reclamado": documento, "tablas": {}, "diferencias_no_explicadas": []}
    for tabla in COLUMNAS_HUELLA:
        a, b = pre["huellas_por_fila"][tabla], post["huellas_por_fila"][tabla]
        nuevas = sorted(set(b) - set(a))
        borradas = sorted(set(a) - set(b))
        cambiadas = sorted(k for k in set(a) & set(b) if a[k][0] != b[k][0])
        informe["tablas"][tabla] = {"antes": len(a), "despues": len(b), "nuevas": len(nuevas),
                                    "borradas": len(borradas), "cambiadas": len(cambiadas),
                                    "nuevas_ids": nuevas, "cambiadas_ids": cambiadas}
        for k in borradas:
            informe["diferencias_no_explicadas"].append([tabla, "BORRADA", k])
        for k in nuevas:
            if b[k][1] != documento:
                informe["diferencias_no_explicadas"].append([tabla, "NUEVA_AJENA", k, b[k][1]])
        for k in cambiadas:
            if b[k][1] != documento or a[k][1] != documento:
                informe["diferencias_no_explicadas"].append([tabla, "CAMBIADA_AJENA", k, b[k][1]])
    informe["hefame_intacta"] = pre["hefame_0563834757"] == post["hefame_0563834757"]
    informe["flags_identicos"] = pre["flags"] == post["flags"]
    informe["cf_configuracion_identica"] = pre["cf_configuracion"] == post["cf_configuracion"]
    informe["post_operacion"] = {k: post[k] for k in ("flags", "locks", "claims", "workers", "normalizando",
                                                     "error", "proveedor_no_soportado", "con_intentos_fallo")}
    informe["conteos"] = {t: [pre["conteos"][t], post["conteos"][t]] for t in COLUMNAS_HUELLA}
    informe["documentos_por_estado"] = {"antes": pre["documentos_por_estado"], "despues": post["documentos_por_estado"]}
    informe["elegibles"] = {"antes": pre["elegibles"], "despues": post["elegibles"]}
    print(json.dumps(informe, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    if sys.argv[1] == "snapshot":
        snapshot(Path(sys.argv[2]))
    elif sys.argv[1] == "comparar":
        comparar(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4] if len(sys.argv) > 4 else None)
    else:
        raise SystemExit("modo desconocido")
