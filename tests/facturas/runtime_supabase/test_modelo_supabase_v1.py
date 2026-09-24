from __future__ import annotations

import re
from pathlib import Path

import pytest


RAIZ = Path(__file__).resolve().parents[3]
MIGRACIONES = RAIZ / "sql" / "migrations"
PREFLIGHT = RAIZ / "sql" / "preflight" / "preflight_supabase_controlfarmacias.sql"
POSTFLIGHT = RAIZ / "sql" / "preflight" / "postflight_supabase_v1.sql"
POSTFLIGHT_06B = RAIZ / "sql" / "preflight" / "postflight_06b_integridad_albaranes.sql"

TABLAS_LEGACY = {
    "documentos_facturas",
    "facturas",
    "facturas_vencimientos",
    "facturas_impuestos",
    "facturas_albaranes_extraidos",
    "facturas_ajustes",
    "albaranes",
}

TABLAS_V1 = {
    "proveedores",
    "proveedores_alias",
    "cf_configuracion",
    "normalizacion_ejecuciones",
    "facturas_movimientos",
    "facturas_incidencias",
    "historial_facturas",
    "conciliaciones",
    "conciliacion_detalles",
}


def _sql(nombre: str) -> str:
    return (MIGRACIONES / nombre).read_text(encoding="utf-8")


def _afirmar_solo_select(ruta: Path) -> str:
    texto = ruta.read_text(encoding="utf-8")
    sin_comentarios = re.sub(r"--.*?$", "", texto, flags=re.MULTILINE)
    sentencias = [item.strip().casefold() for item in sin_comentarios.split(";") if item.strip()]
    assert sentencias
    assert all(item.startswith("select") for item in sentencias)
    assert not re.search(
        r"\b(insert|update|delete|merge|create|alter|drop|truncate|call|do)\b",
        sin_comentarios,
        flags=re.IGNORECASE,
    )
    return sin_comentarios


def _tablas_publicas_referenciadas_directamente(sql: str) -> set[str]:
    return {
        coincidencia.casefold()
        for coincidencia in re.findall(
            r"\b(?:from|join)\s+public\.([a-z_][a-z0-9_]*)",
            sql,
            flags=re.IGNORECASE,
        )
    }


def test_preflight_contiene_exclusivamente_consultas_select() -> None:
    _afirmar_solo_select(PREFLIGHT)


def test_postflight_contiene_exclusivamente_consultas_select() -> None:
    _afirmar_solo_select(POSTFLIGHT)


def test_postflight_06b_contiene_exclusivamente_consultas_select() -> None:
    _afirmar_solo_select(POSTFLIGHT_06B)


def test_preflight_legacy_no_depende_de_objetos_v1() -> None:
    sql = _afirmar_solo_select(PREFLIGHT)
    referencias = _tablas_publicas_referenciadas_directamente(sql)
    assert referencias <= TABLAS_LEGACY
    assert referencias == TABLAS_LEGACY
    assert not referencias & TABLAS_V1
    assert "to_regclass('public.' || esperado.object_name)" in sql
    assert "'cf_configuracion'" in sql
    assert "'OPCIONAL_ANTES_07'" in sql


def test_postflight_v1_depende_de_configuracion_y_modelo_07_a_12() -> None:
    sql = _afirmar_solo_select(POSTFLIGHT)
    referencias = _tablas_publicas_referenciadas_directamente(sql)
    assert TABLAS_V1 <= referencias
    assert "from public.cf_configuracion" in sql.casefold()
    assert "normalizacion_automatica = false" in sql.casefold()
    assert "conciliacion_automatica = false" in sql.casefold()
    assert "luna_habilitada = false" in sql.casefold()
    assert "farmacias_habilitadas = array['pio']::text[]" in sql.casefold()

    for columna in (
        "proximo_reintento_at",
        "proyeccion_clave",
        "estado_normalizacion",
        "estado_conciliacion_cf",
        "estado_revision",
        "normalizacion_ejecucion_id",
        "conciliacion_reintento_solicitado_at",
        "provenance",
        "literal",
    ):
        assert f"'{columna}'" in sql


def test_postflight_enumera_constraints_indices_policies_vistas_y_rpc_v1() -> None:
    sql = POSTFLIGHT.read_text(encoding="utf-8").casefold()
    for objeto in (
        "normalizacion_ejecuciones_documento_idempotency_unico",
        "facturas_incidencias_ambito_check",
        "conciliacion_detalles_albaran_operacional_check",
        "proveedores_codigo_ci_unico",
        "facturas_documento_proyeccion_clave_unico",
        "conciliaciones_actual_factura_unico",
        "cf_configuracion_authenticated_select",
        "conciliacion_detalles_authenticated_select",
        "v_facturas_listado",
        "v_dashboard_diario",
        "v_vencimientos_calendario",
        "v_proveedores_estado",
        "cf_persistir_normalizacion",
        "cf_evaluar_elegibilidad_conciliacion",
        "cf_reintentar_todas_pendientes",
    ):
        assert f"'{objeto}'" in sql


def test_preflight_y_postflight_cubren_catalogos_requeridos() -> None:
    preflight = PREFLIGHT.read_text(encoding="utf-8").casefold()
    postflight = POSTFLIGHT.read_text(encoding="utf-8").casefold()
    for fragmento in (
        "information_schema.columns",
        "pg_constraint",
        "pg_indexes",
        "pg_policies",
        "information_schema.role_table_grants",
        "storage.buckets",
    ):
        assert fragmento in preflight
        assert fragmento in postflight
    for fragmento in (
        "information_schema.routines",
        "information_schema.role_routine_grants",
        "pg_get_viewdef",
    ):
        assert fragmento in postflight


def test_ausencia_cf_configuracion_tiene_semantica_segun_fase() -> None:
    preflight = PREFLIGHT.read_text(encoding="utf-8").casefold()
    postflight = POSTFLIGHT.read_text(encoding="utf-8").casefold()
    assert "from public.cf_configuracion" not in preflight
    assert "join public.cf_configuracion" not in preflight
    assert "from public.cf_configuracion" in postflight


def test_migraciones_06b_y_07_a_13_existen_en_orden() -> None:
    esperadas = [
        "06b_cf_integridad_albaranes.sql",
        "07_cf_proveedores_config.sql",
        "08_cf_core_facturas.sql",
        "08b_cf_estado_lectura_compatibilidad.sql",
        "09_cf_normalizacion_runtime.sql",
        "10_cf_movimientos_incidencias_historial.sql",
        "11_cf_conciliacion.sql",
        "12_cf_views_rls_rpc.sql",
        "13_cf_backfill_compatibilidad.sql",
        "14_cf_claim_conciliacion_v2.sql",
        "15_cf_multifactura.sql",
        "16_cf_worker_manual_one_shot.sql",
    ]
    assert [ruta.name for ruta in sorted(MIGRACIONES.glob("*_cf_*.sql"))] == esperadas


def test_migracion_06b_es_idempotente_conservadora_y_semantica() -> None:
    sql = _sql("06b_cf_integridad_albaranes.sql").casefold()
    assert "from pg_index" in sql
    assert "i.indisunique" in sql
    assert "i.indisvalid" in sql
    assert "i.indpred is null" in sql
    assert "i.indexprs is null" in sql
    assert "i.indnkeyatts = 2" in sql
    assert "array['farmacia', 'id_contador']::name[]" in sql
    assert "group by farmacia, id_contador" in sql
    assert "having count(*) > 1" in sql
    assert "migracion_06b_bloqueada" in sql
    assert "add constraint albaranes_farmacia_id_contador_unico" in sql
    assert "unique (farmacia, id_contador)" in sql
    assert not re.search(r"\b(?:insert\s+into|update|delete\s+from)\s+public\.albaranes\b", sql)


def test_preflight_06b_evalua_garantia_por_columnas_y_no_por_nombre() -> None:
    preflight = PREFLIGHT.read_text(encoding="utf-8").casefold()
    postflight = POSTFLIGHT_06B.read_text(encoding="utf-8").casefold()
    for sql in (preflight, postflight):
        assert "from pg_index" in sql
        assert "i.indisunique" in sql
        assert "i.indnkeyatts = 2" in sql
        assert "array['farmacia', 'id_contador']::name[]" in sql
        assert "garantia_unique_efectiva" in sql
        assert "duplicados_materiales" in sql
        assert "apto_despliegue_v1" in sql
    assert "albaranes_farmacia_id_contador_unico" not in preflight


def test_estados_text_check_y_sin_postgresql_enum() -> None:
    sql = "\n".join(_sql(ruta.name) for ruta in sorted(MIGRACIONES.glob("*_cf_*.sql")))
    assert "create type" not in sql.casefold()
    for estado in (
        "PENDIENTE",
        "NORMALIZANDO",
        "NORMALIZADA",
        "REQUIERE_REVISION",
        "PENDIENTE_CONCILIAR",
        "CONCILIADA",
        "NO_REQUERIDA",
        "PENDIENTE_REVISION_PIO",
        "VALIDADA_PIO",
    ):
        assert f"'{estado}'" in sql


def test_configuracion_inicial_no_activa_procesos_ni_luna() -> None:
    sql = _sql("07_cf_proveedores_config.sql").casefold()
    assert "normalizacion_automatica boolean not null default false" in sql
    assert "conciliacion_automatica boolean not null default false" in sql
    assert "luna_habilitada boolean not null default false" in sql
    assert "farmacias_habilitadas text[] not null default array['pio']::text[]" in sql
    assert "preflight_indice_pio_reconciliado boolean not null default false" in sql
    assert "values (true, false, false, false, 0.0500)" in sql


def test_dinero_y_coste_tienen_precision_requerida() -> None:
    sql = "\n".join(
        _sql(nombre)
        for nombre in (
            "08_cf_core_facturas.sql",
            "09_cf_normalizacion_runtime.sql",
            "10_cf_movimientos_incidencias_historial.sql",
            "11_cf_conciliacion.sql",
        )
    ).casefold()
    assert "numeric(14,4)" in sql
    assert "coste_luna numeric(12,6)" in sql


def test_locks_son_atomicos_y_respetan_interruptores() -> None:
    normalizacion = _sql("09_cf_normalizacion_runtime.sql").casefold()
    conciliacion = _sql("11_cf_conciliacion.sql").casefold()
    assert "for update of d skip locked" in normalizacion
    assert "c.normalizacion_automatica" in normalizacion
    assert "reprocesar_solicitado_at is not null" in normalizacion
    assert "for update of f skip locked" in conciliacion
    assert "c.conciliacion_automatica" in conciliacion
    assert "conciliacion_reintento_solicitado_at is not null" in conciliacion


def test_schema_admite_multifactura_sin_fusionar_documentos() -> None:
    core = _sql("08_cf_core_facturas.sql")
    legacy = (MIGRACIONES / "06_reestructurar_documentos_y_facturas.sql").read_text(
        encoding="utf-8"
    )
    backfill = _sql("13_cf_backfill_compatibilidad.sql")
    assert "documento_id uuid not null" in legacy
    assert "facturas_documento_numero_pagina_unico" in legacy
    assert "POSIBLE_DUPLICADO" in backfill
    assert "fusion_automatica', false" in backfill
    assert "drop column documento_id" not in core.casefold()


def test_provenance_y_resultado_completo_se_conservan() -> None:
    normalizacion = _sql("09_cf_normalizacion_runtime.sql")
    movimientos = _sql("10_cf_movimientos_incidencias_historial.sql")
    core = _sql("08_cf_core_facturas.sql")
    assert "resultado_json jsonb" in normalizacion
    assert "pasos jsonb" in normalizacion
    assert "provenance jsonb" in movimientos
    assert "provenance jsonb" in core


def test_id_proveedor_real_se_modela_como_texto_literal() -> None:
    proveedores = _sql("07_cf_proveedores_config.sql").casefold()
    core = _sql("08_cf_core_facturas.sql").casefold()
    assert "farmatic_id_proveedor text" in proveedores
    assert "alter column id_proveedor_albaranes type text" in core
    assert "farmatic_id_proveedor bigint" not in proveedores


def test_persistencia_normalizacion_es_una_rpc_transaccional_e_idempotente() -> None:
    sql = _sql("12_cf_views_rls_rpc.sql").casefold()
    runtime = (RAIZ / "src" / "facturas" / "runtime_supabase" / "repositorios.py").read_text(
        encoding="utf-8"
    )
    assert "create or replace function public.cf_persistir_normalizacion" in sql
    assert "for update" in sql
    assert "idempotency_key" in sql
    assert "on conflict (documento_id, proyeccion_clave) do update" in sql
    assert "jsonb_array_elements(coalesce(v_documento_normalizado->'facturas'" in sql
    assert "delete from public.normalizacion_ejecuciones" not in sql
    assert "delete from public.historial_facturas" not in sql
    assert 'rpc("cf_persistir_normalizacion"' in runtime
    import inspect
    from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase
    persistencia = inspect.getsource(RepositorioRuntimeSupabase.persistir_normalizacion)
    assert '.table("normalizacion_ejecuciones")' not in persistencia
    assert 'rpc("cf_persistir_normalizacion"' in persistencia


def test_proyeccion_actual_reemplaza_hijos_sin_borrar_historia() -> None:
    sql = _sql("12_cf_views_rls_rpc.sql").casefold()
    for tabla in (
        "facturas_vencimientos",
        "facturas_impuestos",
        "facturas_albaranes_extraidos",
        "facturas_movimientos",
    ):
        assert f"delete from public.{tabla} where factura_id = v_factura_id" in sql
    assert "resultado_json" in sql
    assert "proyeccion_normalizacion_reemplazada" in sql


def test_estado_documento_es_tecnico_y_no_agrega_revision_economica() -> None:
    sql = _sql("12_cf_views_rls_rpc.sql").casefold()
    core = _sql("08_cf_core_facturas.sql").casefold()
    assert "set estado_lectura = 'normalizada'" in sql
    assert "v_estado_factura = 'requiere_revision'" in sql
    assert "estado tecnico agregado del pdf" in core
    assert "then 'factura_unica'" in sql
    assert "else 'lote_facturas'" in sql
    assert "else 'otro'" in sql


def test_backfill_13_permanece_bloqueado_hasta_reconciliacion() -> None:
    sql = _sql("13_cf_backfill_compatibilidad.sql").casefold()
    config = _sql("07_cf_proveedores_config.sql").casefold()
    assert "cf_preflight_pio_valido()" in sql
    assert "preflight_indice_pio_reconciliado" in config
    assert "c.preflight_pio_hashes_sqlite = c.preflight_pio_hashes_supabase" in config
    assert "preflight_pio_manifest_sqlite_sha256" in config
    assert "preflight_pio_manifest_supabase_sha256" in config
    assert "count(distinct archivo_hash)" in config
    assert "string_agg(archivo_hash, e'\\n' order by archivo_hash)" in config
    assert "c.preflight_pio_manifest_supabase_sha256 = m.sha256" in config
    assert "c.farmacias_habilitadas = array['pio']::text[]" in config
    assert "migracion_13_bloqueada" in sql
    assert "raise exception" in sql
    assert "rita_excluida_del_despliegue_pio" in sql
    assert "where farmacia = 'pio'" in sql


def test_claims_automaticos_restringen_farmacia_configurada() -> None:
    normalizacion = _sql("09_cf_normalizacion_runtime.sql").casefold()
    conciliacion = _sql("11_cf_conciliacion.sql").casefold()
    assert "d.farmacia = any(c.farmacias_habilitadas)" in normalizacion
    assert "f.farmacia = any(c.farmacias_habilitadas)" in conciliacion


def test_vistas_y_rpc_respetan_aislamiento_de_farmacia() -> None:
    sql = _sql("12_cf_views_rls_rpc.sql").casefold()
    assert sql.count("farmacia = any(") >= 20
    for tabla in (
        "documentos_facturas",
        "facturas",
        "facturas_vencimientos",
        "facturas_impuestos",
        "facturas_albaranes_extraidos",
        "facturas_ajustes",
        "normalizacion_ejecuciones",
        "facturas_movimientos",
        "facturas_incidencias",
        "historial_facturas",
        "conciliaciones",
        "conciliacion_detalles",
    ):
        assert f"alter table public.{tabla} enable row level security" in sql


def test_rita_sigue_preparada_pero_no_habilitada() -> None:
    sql = _sql("07_cf_proveedores_config.sql").casefold()
    assert "array['pio']::text[]" in sql
    assert "array['pio', 'rita']::text[]" in sql


def test_preflight_incluye_grants_de_tablas_y_rutinas() -> None:
    sql = PREFLIGHT.read_text(encoding="utf-8").casefold()
    assert "information_schema.role_table_grants" in sql
    assert "information_schema.role_routine_grants" in sql


def test_paquete_staging_autocontenido_y_sin_destino_productivo() -> None:
    staging = RAIZ / "sql" / "staging"
    esperados = [
        "00_baseline_controlfarmacias.sql",
        "01_seed_controlfarmacias.sql",
        "02_validar_migraciones.sql",
        "03_test_rpc_normalizacion.sql",
        "04_test_concurrencia_idempotencia.sql",
        "05_test_conciliacion.sql",
        "06_test_backfill_pio.sql",
        "07_test_claim_conciliacion_v2.sql",
    ]
    assert [ruta.name for ruta in sorted(staging.glob("*.sql"))] == esperados
    texto = "\n".join((staging / nombre).read_text(encoding="utf-8") for nombre in esperados)
    assert "SUPABASE_URL" not in texto
    assert "SUPABASE_KEY" not in texto
    assert "SINTETICO" in texto
    assert "cf_persistir_normalizacion" in texto
    assert "rollback incompleto" in texto
    assert "idempotency_key" in texto
    assert "for update skip locked" in texto.casefold()
    assert "0.0500" in texto and "0.0501" in texto
    assert "RITA" in texto and "POSIBLE_DUPLICADO" in texto


def test_runbook_staging_contiene_secuencia_y_destruccion() -> None:
    ruta = RAIZ / "docs" / "SUPABASE_V1_CERTIFICACION_STAGING.md"
    texto = ruta.read_text(encoding="utf-8")
    for paso in range(7, 14):
        assert f"{paso:02d}_cf_" in texto or paso == 13
    assert "STAGING_DATABASE_URL" in texto
    assert "SUPABASE_URL" in texto
    assert "dos sesiones" in texto.casefold()
    assert "destruir" in texto.casefold()


def test_conciliacion_no_crea_fk_con_albaranes_id() -> None:
    sql = _sql("11_cf_conciliacion.sql").casefold()
    assert "albaran_farmacia text" in sql
    assert "albaran_id_contador bigint" in sql
    assert not re.search(r"references\s+public\.albaranes", sql)
    assert "uno_a_varios" in sql
    assert "varios_a_uno" in sql
    assert "movimiento_no_farmatic" in sql


def test_historial_es_append_only() -> None:
    sql = _sql("10_cf_movimientos_incidencias_historial.sql").casefold()
    assert "before update or delete on public.historial_facturas" in sql
    assert "historial_facturas es append-only" in sql


def test_rls_solo_concede_select_generico_a_authenticated() -> None:
    sql = _sql("12_cf_views_rls_rpc.sql").casefold()
    nuevas = (
        "proveedores",
        "proveedores_alias",
        "cf_configuracion",
        "normalizacion_ejecuciones",
        "facturas_movimientos",
        "facturas_incidencias",
        "historial_facturas",
        "conciliaciones",
        "conciliacion_detalles",
    )
    for tabla in nuevas:
        assert f"alter table public.{tabla} enable row level security" in sql
        assert f"grant select on table public.{tabla} to authenticated" in sql
    assert "for insert to authenticated" not in sql
    assert "for update to authenticated" not in sql
    assert "for delete to authenticated" not in sql
    assert "set public = false" in sql
    assert "where id = 'facturas-pdf'" in sql


@pytest.mark.parametrize(
    "rpc",
    (
        "cf_validar_factura",
        "cf_desvalidar_factura",
        "cf_solicitar_reprocesado",
        "cf_solicitar_reintento_conciliacion",
        "cf_reintentar_todas_pendientes",
    ),
)
def test_rpc_sensibles_preparadas(rpc: str) -> None:
    sql = _sql("12_cf_views_rls_rpc.sql")
    assert f"function public.{rpc}" in sql
    assert f"create or replace function public.{rpc}" in sql


@pytest.mark.parametrize(
    "vista",
    (
        "v_facturas_listado",
        "v_dashboard_diario",
        "v_vencimientos_calendario",
        "v_proveedores_estado",
    ),
)
def test_vistas_security_invoker(vista: str) -> None:
    sql = _sql("12_cf_views_rls_rpc.sql")
    patron = rf"create or replace view public\.{vista}\s+with \(security_invoker = true\)"
    assert re.search(patron, sql, flags=re.IGNORECASE)


def test_consultas_farmatic_siguen_siendo_solo_select() -> None:
    codigo = (RAIZ / "src" / "database" / "leer_albaranes.py").read_text(encoding="utf-8")
    consultas = re.findall(r'consulta\s*=\s*"""(.*?)"""', codigo, flags=re.DOTALL)
    assert len(consultas) == 2
    for consulta in consultas:
        limpia = consulta.strip().casefold()
        assert limpia.startswith("select")
        assert not re.search(
            r"\b(insert|update|delete|merge|create|alter|drop|truncate|exec|execute)\b",
            limpia,
        )
