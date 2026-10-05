"""Hito 2AT rev2: preflight, snapshot, candidato y postcheck ESTRICTAMENTE READ_ONLY.

Uso:
  python -B pruebas/auditoria_2at/auditoria_readonly.py preflight <salida.json>
  python -B pruebas/auditoria_2at/auditoria_readonly.py snapshot <salida.json>
  python -B pruebas/auditoria_2at/auditoria_readonly.py candidato <salida.json> [<candidato_previo.json>]
  python -B pruebas/auditoria_2at/auditoria_readonly.py comparar <pre.json> <post.json> <factura_id>

Patron certificado de 2AO/2AW: se demuestra el project ref antes de conectar, la
sesion es ``readonly=True`` (REPEATABLE READ, una sola transaccion por modo), cada
sentencia se valida como SELECT/WITH, no se llama a ninguna RPC de escritura, no
hay DML y se cierra siempre con rollback. Las salidas se escriben FUERA del
repositorio (se rechaza cualquier ruta dentro de el).

- ``preflight`` (Fase 1): puertas de operacion, migraciones 18/19, flags,
  propietarios de ``public``, tareas programadas (solo lectura), columnas de huella
  y conteos. Termina con PREFLIGHT_OK o PARADO_EN_PREFLIGHT.
- ``snapshot`` (Fase 2): operacion, conteos y huella por fila sobre columnas
  EXPLICITAS (``COLUMNAS_HUELLA``) con volcado de esas columnas.
- ``candidato`` (Fase 3, y revalidacion de la Fase 4 con ``candidato_previo``):
  reproduce el selector y el ordering oficiales del claim manual sin bloquear filas,
  comprueba que los cuerpos productivos del nucleo y de la elegibilidad son los de
  las migraciones 18 y 14, y simula localmente, SIN claim, el camino de
  ``WorkerConciliacion._procesar`` con el ``construir_detalles`` productivo sobre
  un cliente de solo lectura que no expone ``rpc``, ``insert``, ``update`` ni
  ``delete``.
- ``comparar`` (Fase 6): no se conecta a nada.

Este script no toca Farmatic.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
PROJECT_REF = "vklaiuytvegkelgyspxc"
APPLICATION_NAME = "cf_2at_readonly"
MODO_CLAIM = "MANUAL_ONE_SHOT"
TOLERANCIA_CERTIFICADA = Decimal("0.0500")
FLAGS_ESPERADOS = [False, False, False, "{PIO}"]
TAREAS_ESPERADAS = ("ControlFarmacias - Importar facturas", "Sincronización ControlFarmacias")
MARGEN_TAREAS = timedelta(minutes=60)

# Columnas declaradas ANTES de ejecutar. Se incluyen tambien las columnas tecnicas
# (claim, reintento, marcas de actualizacion): fuera de la factura reclamada nada
# debe cambiar. El preflight exige que coincidan exactamente con produccion.
COLUMNAS_HUELLA: dict[str, tuple[str, ...]] = {
    "facturas": (
        "id", "documento_id", "farmacia", "pagina_inicio", "pagina_fin", "tipo_documento", "categoria",
        "requiere_conciliacion_albaranes", "id_proveedor_albaranes", "proveedor_nombre", "proveedor_cif",
        "numero_factura", "fecha_factura", "moneda", "base_imponible_total", "iva_total",
        "recargo_equivalencia_total", "importe_total", "cuadre_fiscal_correcto", "diferencia_cuadre",
        "confianza_extraccion", "requiere_revision", "motivo_revision", "estado_conciliacion",
        "diferencia_albaranes", "diferencia_aceptada_automaticamente", "estado_pago", "validada_manualmente",
        "validada_por", "fecha_validacion", "observaciones", "datos_extraidos", "fecha_creacion",
        "fecha_actualizacion", "proyeccion_clave", "proveedor_id", "proveedor_literal", "estado_normalizacion",
        "estado_conciliacion_cf", "estado_revision", "normalizacion_ejecucion_id", "provenance",
        "conciliacion_intentos", "conciliacion_proximo_at", "conciliacion_bloqueado_hasta",
        "conciliacion_bloqueado_por", "conciliacion_ultimo_error", "updated_at",
        "conciliacion_reintento_solicitado_at", "conciliacion_intentos_fallo", "conciliacion_ultima_clase_fallo",
    ),
    "conciliaciones": (
        "id", "factura_id", "intento", "disparador", "estado", "es_actual", "tolerancia", "importe_factura",
        "importe_explicado", "diferencia", "resultado", "estrategia", "provenance", "worker_id",
        "iniciado_at", "finalizado_at", "created_at", "error_codigo", "error_detalle", "idempotency_key",
    ),
    "conciliacion_detalles": (
        "id", "conciliacion_id", "orden", "factura_albaran_extraido_id", "factura_movimiento_id",
        "albaran_farmacia", "albaran_id_contador", "numero_albaran_documental", "numero_albaran_farmatic",
        "coincidencia_numero_literal", "tipo_relacion", "importe_documental", "importe_farmatic",
        "importe_aplicado", "diferencia", "estado", "provenance", "created_at",
    ),
    "facturas_albaranes_extraidos": (
        "id", "factura_id", "numero_albaran", "fecha_albaran", "tipo_movimiento", "importe_base",
        "importe_total", "descripcion", "orden", "confianza_extraccion", "fecha_creacion", "provenance",
        "literal",
    ),
    "facturas_movimientos": (
        "id", "factura_id", "normalizacion_ejecucion_id", "orden", "categoria", "descripcion_literal",
        "sentido", "base", "iva", "recargo_equivalencia", "importe", "independiente", "conciliable_farmatic",
        "provenance", "created_at", "updated_at",
    ),
    "albaranes": (
        "id", "farmacia", "id_contador", "id_proveedor", "proveedor", "numero_albaran", "fecha",
        "importe_pvp", "importe_puc", "descuento", "estado", "observaciones", "fecha_importacion",
        "fecha_actualizacion",
    ),
    "historial_facturas": (
        "id", "documento_id", "factura_id", "evento", "origen", "actor", "estado_anterior", "estado_nuevo",
        "detalle", "created_at",
    ),
}

# Factura duena de cada fila (para atribuir filas nuevas o cambiadas en la Fase 6).
DUENO_FACTURA = {
    "facturas": "t.id",
    "conciliaciones": "t.factura_id",
    "conciliacion_detalles": "(select c.factura_id from public.conciliaciones c where c.id = t.conciliacion_id)",
    "facturas_albaranes_extraidos": "t.factura_id",
    "facturas_movimientos": "t.factura_id",
    "albaranes": "null",
    "historial_facturas": "t.factura_id",
}

TABLAS_CONTEO = ("facturas", "conciliaciones", "conciliacion_detalles", "facturas_albaranes_extraidos",
                 "facturas_movimientos", "historial_facturas", "albaranes", "documentos_facturas")

MARCAS = (
    "select jsonb_build_object("
    "'18_nucleo', to_regprocedure('public.cf_reclamar_factura_conciliacion_nucleo(text,integer,text)') is not null,"
    "'18_manual', to_regprocedure('public.cf_reclamar_factura_conciliacion_manual_one_shot(text,integer)') is not null,"
    "'18_persistir', to_regprocedure('public.cf_persistir_conciliacion(uuid,text,text,text,jsonb)') is not null,"
    "'18_fallo', to_regprocedure('public.cf_registrar_fallo_conciliacion(uuid,text,text,text,text,text)') is not null,"
    "'18_columna_idempotency', exists(select 1 from information_schema.columns where table_schema='public' "
    "  and table_name='conciliaciones' and column_name='idempotency_key'),"
    "'18_columna_intentos_fallo', exists(select 1 from information_schema.columns where table_schema='public' "
    "  and table_name='facturas' and column_name='conciliacion_intentos_fallo'),"
    "'19_anon_sin_select_facturas', not has_table_privilege('anon','public.facturas','SELECT'),"
    "'19_authenticated_sin_select_facturas', not has_table_privilege('authenticated','public.facturas','SELECT'),"
    "'19_service_role_sin_update_facturas', not has_table_privilege('service_role','public.facturas','UPDATE'),"
    "'19_service_role_sin_insert_conciliaciones', not has_table_privilege('service_role','public.conciliaciones','INSERT'),"
    "'19_validar_factura_solo_propietario', not has_function_privilege('service_role',"
    "  'public.cf_validar_factura(uuid,text)','EXECUTE'))::text"
)

# Lo que necesitara la ruta manual de la Fase 4 con service_role (lectura y RPC).
PRIVILEGIOS_RUTA_MANUAL = (
    "select jsonb_build_object("
    + ",".join(f"'select_{t}', has_table_privilege('service_role','public.{t}','SELECT')"
               for t in ("facturas", "proveedores", "facturas_movimientos", "facturas_albaranes_extraidos",
                         "albaranes", "normalizacion_ejecuciones", "cf_configuracion"))
    + ",'execute_claim_manual', has_function_privilege('service_role',"
      "'public.cf_reclamar_factura_conciliacion_manual_one_shot(text,integer)','EXECUTE')"
      ",'execute_persistir', has_function_privilege('service_role',"
      "'public.cf_persistir_conciliacion(uuid,text,text,text,jsonb)','EXECUTE')"
      ",'execute_fallo', has_function_privilege('service_role',"
      "'public.cf_registrar_fallo_conciliacion(uuid,text,text,text,text,text)','EXECUTE'))::text"
)

# Igual que la comprobacion de propietarios de 2AX (funciones de extensiones excluidas).
SQL_PROPIETARIOS = """
with obj as (
  select case c.relkind when 'S' then 'secuencia' when 'v' then 'vista' when 'm' then 'vista_materializada'
              when 'f' then 'tabla_foranea' else 'tabla' end as tipo,
         c.relname::text as nombre, pg_get_userbyid(c.relowner) as owner
    from pg_class c where c.relnamespace = 'public'::regnamespace and c.relkind in ('r','p','v','m','S','f')
  union all
  select 'funcion', p.oid::regprocedure::text, pg_get_userbyid(p.proowner)
    from pg_proc p where p.pronamespace = 'public'::regnamespace
     and not exists (select 1 from pg_depend d where d.objid = p.oid and d.deptype = 'e')
)
select jsonb_build_object(
  'por_tipo', (select coalesce(jsonb_object_agg(tipo, n), '{}'::jsonb)
                 from (select tipo, count(*) n from obj group by tipo) x),
  'owner_distinto_de_postgres', (select coalesce(jsonb_agg(jsonb_build_array(tipo, nombre, owner)
                                   order by tipo, nombre), '[]'::jsonb) from obj where owner <> 'postgres'))::text
"""

# Selector oficial (migracion 18, nucleo) con p_modo_ejecucion = MANUAL_ONE_SHOT,
# SIN "for update skip locked" y SIN limit: no bloquea ni reclama nada.
SQL_SELECTOR_OFICIAL = """
select f.id
  from public.facturas f
  cross join public.cf_configuracion c
  cross join lateral public.cf_evaluar_elegibilidad_conciliacion(f.id) e
 where c.id = true
   and f.farmacia = any(c.farmacias_habilitadas)
   and (
       %(modo)s = 'MANUAL_ONE_SHOT'
       or c.conciliacion_automatica
       or f.conciliacion_reintento_solicitado_at is not null
   )
   and f.estado_conciliacion_cf = 'PENDIENTE_CONCILIAR'
   and e.estado = 'APTA'
   and coalesce(f.conciliacion_proximo_at, '-infinity'::timestamptz) <= now()
   and coalesce(f.conciliacion_bloqueado_hasta, '-infinity'::timestamptz) <= now()
 order by
   (f.conciliacion_reintento_solicitado_at is not null) desc,
   f.fecha_factura nulls last,
   f.id
"""

# Todas las facturas en el mismo ordering, con cada filtro del selector por separado.
SQL_TODAS_CON_FILTROS = """
select jsonb_build_object(
  'id', f.id::text, 'numero_factura', f.numero_factura, 'farmacia', f.farmacia,
  'proveedor_nombre', f.proveedor_nombre, 'proveedor_literal', f.proveedor_literal,
  'proveedor_id', f.proveedor_id::text, 'fecha_factura', f.fecha_factura::text,
  'importe_total', f.importe_total::text, 'categoria', f.categoria,
  'naturaleza_principal', f.datos_extraidos->>'naturaleza_principal',
  'estado_conciliacion_cf', f.estado_conciliacion_cf,
  'reintento_solicitado_at', f.conciliacion_reintento_solicitado_at::text,
  'proximo_at', f.conciliacion_proximo_at::text, 'bloqueado_hasta', f.conciliacion_bloqueado_hasta::text,
  'intentos', f.conciliacion_intentos, 'intentos_fallo', f.conciliacion_intentos_fallo,
  'elegibilidad', e.estado, 'razon', e.razon,
  'f_farmacia', f.farmacia = any(c.farmacias_habilitadas),
  'f_estado', f.estado_conciliacion_cf = 'PENDIENTE_CONCILIAR',
  'f_apta', e.estado = 'APTA',
  'f_backoff', coalesce(f.conciliacion_proximo_at, '-infinity'::timestamptz) <= now(),
  'f_lock', coalesce(f.conciliacion_bloqueado_hasta, '-infinity'::timestamptz) <= now())::text
  from public.facturas f
  cross join public.cf_configuracion c
  cross join lateral public.cf_evaluar_elegibilidad_conciliacion(f.id) e
 where c.id = true
 order by (f.conciliacion_reintento_solicitado_at is not null) desc, f.fecha_factura nulls last, f.id
"""

_SOLO_LECTURA = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


# --------------------------------------------------------------------------- utilidades

def _salida_fuera_del_repo(ruta: str) -> Path:
    destino = Path(ruta).resolve()
    if destino == ROOT or ROOT in destino.parents:
        raise SystemExit(f"SALIDA_DENTRO_DEL_REPOSITORIO: {destino}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    return destino


def _escribir(destino: Path, datos: dict) -> str:
    destino.write_text(json.dumps(datos, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return hashlib.sha256(destino.read_bytes()).hexdigest()


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
    conn = psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name=APPLICATION_NAME)
    conn.set_session(isolation_level="REPEATABLE READ", readonly=True, autocommit=False)
    return ref, conn


class _Lector:
    """Unica puerta a la base: solo SELECT/WITH dentro de la transaccion READ_ONLY."""

    def __init__(self, cur) -> None:
        self._cur = cur
        cur.execute("set local statement_timeout = '120s'")
        ro, iso = self.fila("select current_setting('transaction_read_only'), "
                            "current_setting('transaction_isolation')")
        if ro != "on" or iso != "repeatable read":
            raise SystemExit(f"SESION_NO_READ_ONLY: read_only={ro} isolation={iso}")

    def filas(self, sql: str, params=None) -> list[tuple]:
        if not _SOLO_LECTURA.match(sql):
            raise PermissionError("SENTENCIA_NO_SELECT")
        self._cur.execute(sql, params)
        return self._cur.fetchall()

    def fila(self, sql: str, params=None) -> tuple:
        resultado = self.filas(sql, params)
        if len(resultado) != 1:
            raise RuntimeError(f"SE_ESPERABA_UNA_FILA: {len(resultado)}")
        return resultado[0]

    def valor(self, sql: str, params=None):
        return self.fila(sql, params)[0]

    def json(self, sql: str, params=None):
        return json.loads(self.valor(sql, params))


def _ejecutar_lectura(funcion) -> tuple[str, dict]:
    ref, conn = _conectar()
    try:
        with conn.cursor() as cur:
            lector = _Lector(cur)
            datos = {"project_ref": ref, "transaction_read_only": "on", "isolation": "repeatable read",
                     "current_user": lector.valor("select current_user::text"),
                     "capturado_utc": lector.valor("select now()::text")}
            datos.update(funcion(lector))
    finally:
        conn.rollback()
        conn.close()
    return ref, datos


def _operacion(lector: _Lector) -> dict:
    out = {}
    out["flags"] = list(lector.fila(
        "select normalizacion_automatica, conciliacion_automatica, luna_habilitada, "
        "farmacias_habilitadas::text from public.cf_configuracion where id"))
    out["cf_configuracion"] = lector.valor("select to_jsonb(c)::text from public.cf_configuracion c")
    out["tolerancia_conciliacion"] = str(lector.valor(
        "select tolerancia_conciliacion from public.cf_configuracion where id"))
    out["locks_documentos"] = lector.valor(
        "select count(*) from public.documentos_facturas where bloqueado_hasta > now() or bloqueado_por is not null")
    out["claims_conciliacion"] = lector.valor(
        "select count(*) from public.facturas where conciliacion_bloqueado_hasta > now() "
        "or conciliacion_bloqueado_por is not null")
    out["normalizando"] = lector.valor(
        "select count(*) from public.documentos_facturas where estado_lectura = 'NORMALIZANDO'")
    out["workers"] = [list(r) for r in lector.filas(
        "select application_name, state, count(*) from pg_stat_activity where pid <> pg_backend_pid() and "
        "(application_name ilike '%worker%' or application_name ilike '%runtime%') group by 1, 2 order by 1, 2")]
    out["facturas_por_estado_conciliacion_cf"] = [list(r) for r in lector.filas(
        "select estado_conciliacion_cf, count(*) from public.facturas group by 1 order by 1")]
    out["reintentos_conciliacion_solicitados"] = lector.valor(
        "select count(*) from public.facturas where conciliacion_reintento_solicitado_at is not null")
    out["facturas_con_backoff_futuro"] = lector.valor(
        "select count(*) from public.facturas where conciliacion_proximo_at > now()")
    out["facturas_con_intentos_fallo"] = lector.valor(
        "select count(*) from public.facturas where conciliacion_intentos_fallo > 0")
    out["conteos"] = {t: lector.valor(f"select count(*) from public.{t}") for t in TABLAS_CONTEO}
    out["conciliaciones_por_disparador"] = [list(r) for r in lector.filas(
        "select disparador, count(*) from public.conciliaciones group by 1 order by 1")]
    out["hefame_0563834757"] = [list(r) for r in lector.filas(
        "select id::text, estado_conciliacion_cf from public.facturas where numero_factura = '0563834757'")]
    return out


def _puertas_operacion(op: dict) -> list[str]:
    fallos = []
    if op["flags"] != FLAGS_ESPERADOS:
        fallos.append(f"FLAGS_INESPERADOS: {op['flags']}")
    if Decimal(op["tolerancia_conciliacion"]) != TOLERANCIA_CERTIFICADA:
        fallos.append(f"TOLERANCIA_NO_CERTIFICADA: {op['tolerancia_conciliacion']}")
    for clave in ("locks_documentos", "claims_conciliacion", "normalizando"):
        if op[clave] != 0:
            fallos.append(f"{clave.upper()}_DISTINTO_DE_0: {op[clave]}")
    if op["workers"]:
        fallos.append(f"WORKERS_ACTIVOS: {op['workers']}")
    return fallos


def _tareas() -> dict:
    """Estado de las tareas programadas, solo lectura (Get-ScheduledTask/Info)."""
    ps = (
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8;"
        "$t = @(Get-ScheduledTask -TaskName '*ControlFarmacias*' -ErrorAction Stop | ForEach-Object {"
        " $i = $_ | Get-ScheduledTaskInfo -ErrorAction Stop;"
        " [pscustomobject]@{ nombre = $_.TaskName; estado = [string]$_.State;"
        "  proxima = $(if ($i.NextRunTime) { $i.NextRunTime.ToUniversalTime().ToString('o') } else { $null });"
        "  ultima = $(if ($i.LastRunTime) { $i.LastRunTime.ToUniversalTime().ToString('o') } else { $null });"
        "  resultado = $i.LastTaskResult } });"
        "ConvertTo-Json -InputObject $t -Depth 3"
    )
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, timeout=60)
    if r.returncode:
        return {"error": r.stderr.decode("utf-8", "replace").strip()[:500], "tareas": []}
    tareas = json.loads(r.stdout.decode("utf-8-sig") or "[]")
    return {"tareas": tareas if isinstance(tareas, list) else [tareas]}


def _puertas_tareas(info: dict, ahora: datetime) -> list[str]:
    if "error" in info:
        return [f"TAREAS_NO_DETERMINABLES: {info['error']}"]
    fallos = []
    nombres = {unicodedata.normalize("NFC", t["nombre"]) for t in info["tareas"]}
    for esperada in TAREAS_ESPERADAS:
        if unicodedata.normalize("NFC", esperada) not in nombres:
            fallos.append(f"TAREA_NO_ENCONTRADA: {esperada}")
    for t in info["tareas"]:
        if t["estado"] == "Running":
            fallos.append(f"TAREA_EN_EJECUCION: {t['nombre']}")
        if t.get("proxima"):
            proxima = datetime.fromisoformat(t["proxima"].replace("Z", "+00:00"))
            if proxima - ahora < MARGEN_TAREAS:
                fallos.append(f"TAREA_A_MENOS_DE_60_MIN: {t['nombre']} {t['proxima']}")
    return fallos


# --------------------------------------------------------------------------- Fase 1

def preflight(salida: Path) -> int:
    tareas = _tareas()
    ahora_tareas = datetime.now(timezone.utc)

    def leer(lector: _Lector) -> dict:
        out = {"marcas": lector.json(MARCAS),
               "privilegios_ruta_manual": lector.json(PRIVILEGIOS_RUTA_MANUAL),
               "propietarios": lector.json(SQL_PROPIETARIOS)}
        out.update(_operacion(lector))
        reales = {}
        for tabla in COLUMNAS_HUELLA:
            reales[tabla] = [r[0] for r in lector.filas(
                "select column_name::text from information_schema.columns "
                "where table_schema = 'public' and table_name = %s order by ordinal_position", (tabla,))]
        out["columnas_huella"] = {
            t: {"declaradas_ausentes": sorted(set(COLUMNAS_HUELLA[t]) - set(reales[t])),
                "reales_no_declaradas": sorted(set(reales[t]) - set(COLUMNAS_HUELLA[t]))}
            for t in COLUMNAS_HUELLA}
        return out

    _, datos = _ejecutar_lectura(leer)
    datos["tareas"] = tareas
    datos["tareas_consultadas_utc"] = ahora_tareas.isoformat()

    fallos = []
    fallos += [f"MARCA_FALSA: {k}" for k, v in datos["marcas"].items() if v is not True]
    fallos += [f"PRIVILEGIO_RUTA_MANUAL_AUSENTE: {k}" for k, v in datos["privilegios_ruta_manual"].items()
               if v is not True]
    if datos["propietarios"]["owner_distinto_de_postgres"]:
        fallos.append(f"OWNER_DISTINTO_DE_POSTGRES: {datos['propietarios']['owner_distinto_de_postgres']}")
    fallos += _puertas_operacion(datos)
    fallos += _puertas_tareas(tareas, ahora_tareas)
    for tabla, dif in datos["columnas_huella"].items():
        if dif["declaradas_ausentes"] or dif["reales_no_declaradas"]:
            fallos.append(f"COLUMNAS_HUELLA_NO_COINCIDEN: {tabla} {dif}")
    datos["fallos"] = fallos
    datos["veredicto"] = "PREFLIGHT_OK" if not fallos else "PARADO_EN_PREFLIGHT"

    sha = _escribir(salida, datos)
    resumen = {k: v for k, v in datos.items() if k != "cf_configuracion"}
    print(json.dumps(resumen, ensure_ascii=False, indent=1, default=str))
    print("sha256", sha)
    return 0 if not fallos else 3


# --------------------------------------------------------------------------- Fase 2

def snapshot(salida: Path) -> int:
    def leer(lector: _Lector) -> dict:
        out = _operacion(lector)
        out["columnas_huella"] = COLUMNAS_HUELLA
        huellas, volcado = {}, {}
        for tabla, columnas in COLUMNAS_HUELLA.items():
            lista = ", ".join(f"t.{c}" for c in columnas)
            filas = lector.filas(
                f"select t.id::text, md5(to_jsonb(r)::text), ({DUENO_FACTURA[tabla]})::text, to_jsonb(r)::text "
                f"from public.{tabla} t cross join lateral (select {lista}) r order by t.id")
            huellas[tabla] = {f[0]: [f[1], f[2]] for f in filas}
            volcado[tabla] = {f[0]: f[3] for f in filas}
        out["huellas_por_fila"] = huellas
        out["volcado"] = volcado
        return out

    _, datos = _ejecutar_lectura(leer)
    datos["fallos_operacion"] = _puertas_operacion(datos)
    sha = _escribir(salida, datos)
    resumen = {k: v for k, v in datos.items() if k not in ("huellas_por_fila", "volcado", "cf_configuracion",
                                                           "columnas_huella")}
    resumen["filas_por_tabla"] = {t: len(h) for t, h in datos["huellas_por_fila"].items()}
    print(json.dumps(resumen, ensure_ascii=False, indent=1, default=str))
    print("sha256", sha)
    return 0 if not datos["fallos_operacion"] else 3


# --------------------------------------------------------------------------- Fase 3

class _Respuesta:
    def __init__(self, data) -> None:
        self.data = data


class _ConsultaLectura:
    """Subconjunto de solo lectura del query builder de supabase-py usado por
    ``RepositorioRuntimeSupabase.construir_detalles`` y la revalidacion de
    ``guardar_conciliacion``. Devuelve JSON como PostgREST (fechas en ISO,
    numericos como numero JSON)."""

    TABLAS = frozenset({"facturas", "proveedores", "facturas_movimientos", "facturas_albaranes_extraidos",
                        "albaranes", "normalizacion_ejecuciones"})

    def __init__(self, lector: _Lector, tabla: str) -> None:
        if tabla not in self.TABLAS:
            raise PermissionError(f"TABLA_NO_AUTORIZADA_EN_SIMULACION: {tabla}")
        self._lector, self._tabla = lector, tabla
        self._columnas: list[str] = []
        self._filtros: list[str] = []
        self._params: list = []
        self._orden: str | None = None
        self._single = False

    @staticmethod
    def _ident(nombre: str) -> str:
        if not _IDENT.match(nombre):
            raise PermissionError(f"IDENTIFICADOR_NO_VALIDO: {nombre!r}")
        return nombre

    def select(self, columnas: str):
        self._columnas = [self._ident(c.strip()) for c in columnas.split(",")]
        return self

    def _filtro(self, columna: str, operador: str, valor):
        self._filtros.append(f"t.{self._ident(columna)} {operador} %s")
        self._params.append(valor)
        return self

    def eq(self, columna, valor):
        return self._filtro(columna, "=", valor)

    def gte(self, columna, valor):
        return self._filtro(columna, ">=", valor)

    def lte(self, columna, valor):
        return self._filtro(columna, "<=", valor)

    def order(self, columna: str):
        self._orden = self._ident(columna)
        return self

    def single(self):
        self._single = True
        return self

    def execute(self) -> _Respuesta:
        lista = ", ".join(f"t.{c}" for c in self._columnas)
        where = " and ".join(self._filtros) or "true"
        orden = f" order by t.{self._orden}" if self._orden else ""
        sql = (f"select to_jsonb(r)::text from public.{self._tabla} t "
               f"cross join lateral (select {lista}) r where {where}{orden}")
        filas = [json.loads(f[0]) for f in self._lector.filas(sql, tuple(self._params))]
        if self._single:
            if len(filas) != 1:
                raise RuntimeError(f"SINGLE_SIN_FILA_UNICA: {self._tabla} {len(filas)}")
            return _Respuesta(filas[0])
        return _Respuesta(filas)


class _ClienteLectura:
    """Cliente sustituto SOLO lectura: sin rpc, insert, update, delete ni storage."""

    def __init__(self, lector: _Lector) -> None:
        self._lector = lector

    def table(self, nombre: str) -> _ConsultaLectura:
        return _ConsultaLectura(self._lector, nombre)


def _cuerpo_local(archivo: Path, funcion: str) -> str:
    texto = archivo.read_text(encoding="utf-8").replace("\r\n", "\n")
    inicio = texto.index(f"create or replace function public.{funcion}(")
    apertura = texto.index("$$", inicio) + 2
    return texto[apertura:texto.index("$$", apertura)].strip()


def _cuerpo_remoto(lector: _Lector, firma: str) -> str:
    definicion = lector.valor("select pg_get_functiondef(%s::regprocedure)", (firma,)).replace("\r\n", "\n")
    marca = re.search(r"AS (\$[A-Za-z_]*\$)", definicion)
    apertura = marca.end()
    return definicion[apertura:definicion.index(marca.group(1), apertura)].strip()


def _simular(lector: _Lector, factura_id: str) -> dict:
    """Camino de WorkerConciliacion._procesar(MANUAL_ONE_SHOT) sin claim ni escrituras."""
    sys.path.insert(0, str(ROOT))
    from src.facturas.completitud_documental import validar_documento_antes_de_persistir
    from src.facturas.runtime_supabase.clasificacion_fallos import clasificar_fallo_conciliacion
    from src.facturas.runtime_supabase.conciliacion import conciliar_importes
    from src.facturas.runtime_supabase.modelos import FacturaTrabajo
    from src.facturas.runtime_supabase.repositorios import (
        RepositorioRuntimeSupabase, clave_idempotente_conciliacion, payload_conciliacion)

    cliente = _ClienteLectura(lector)
    repositorio = RepositorioRuntimeSupabase(cliente)
    # Fila tal como la devolveria la RPC de claim (setof facturas), sin reclamar.
    fila = json.loads(lector.valor("select to_jsonb(f)::text from public.facturas f where f.id = %s",
                                   (factura_id,)))
    # Replica literal de RepositorioRuntimeSupabase._reclamar_factura.
    factura = FacturaTrabajo(
        factura_id=str(fila["id"]),
        documento_id=str(fila["documento_id"]),
        farmacia=str(fila["farmacia"]),
        importe_total=(Decimal(str(fila["importe_total"])) if fila.get("importe_total") is not None else None),
        proveedor_id=(str(fila["proveedor_id"]) if fila.get("proveedor_id") else None),
    )
    out: dict = {"factura_trabajo": {"factura_id": factura.factura_id, "documento_id": factura.documento_id,
                                     "farmacia": factura.farmacia, "importe_total": str(factura.importe_total),
                                     "proveedor_id": factura.proveedor_id}}
    if factura.importe_total is None:
        out["camino"] = "FALLO"
        out["fallo"] = {"codigo": "IMPORTE_FACTURA_AUSENTE",
                        "clase": clasificar_fallo_conciliacion("IMPORTE_FACTURA_AUSENTE", "")}
        return out
    try:
        detalles = repositorio.construir_detalles(factura)
        resultado = conciliar_importes(factura.importe_total, detalles, tolerancia=TOLERANCIA_CERTIFICADA)
        # Replica literal de la revalidacion previa a la RPC en guardar_conciliacion.
        rev = cliente.table("facturas").select("normalizacion_ejecucion_id,farmacia") \
            .eq("id", factura.factura_id).single().execute().data
        if rev.get("farmacia") != factura.farmacia:
            raise ValueError("FARMACIA_DOCUMENTO_CONTRADICTORIA")
        ejecucion = cliente.table("normalizacion_ejecuciones").select("resultado_json") \
            .eq("id", rev.get("normalizacion_ejecucion_id")).single().execute().data
        validar_documento_antes_de_persistir(factura.farmacia, ejecucion.get("resultado_json"))
        payload = payload_conciliacion(resultado)
    except Exception as exc:  # mismo criterio que WorkerConciliacion._procesar
        out["camino"] = "FALLO"
        out["fallo"] = {"codigo": type(exc).__name__, "detalle": str(exc),
                        "clase": clasificar_fallo_conciliacion(type(exc).__name__, str(exc))}
        return out

    out["camino"] = "PERSISTIR"
    out["resultado"] = resultado.resultado
    out["importe_factura"] = str(resultado.importe_factura)
    out["importe_explicado"] = str(resultado.importe_explicado)
    out["diferencia"] = str(resultado.diferencia)
    out["tolerancia"] = str(resultado.tolerancia)
    out["idempotency_key_prevista"] = clave_idempotente_conciliacion(factura.factura_id, MODO_CLAIM, payload)
    out["payload_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()

    extraidos = {r["id"]: r for r in cliente.table("facturas_albaranes_extraidos")
                 .select("id,numero_albaran,fecha_albaran,importe_total,tipo_movimiento")
                 .eq("factura_id", factura.factura_id).order("orden").execute().data}
    movimientos = {r["id"]: r for r in cliente.table("facturas_movimientos")
                   .select("id,categoria,descripcion_literal,sentido,importe,base")
                   .eq("factura_id", factura.factura_id).order("orden").execute().data}
    lineas, casados, sin_coincidencia = [], 0, 0
    suma_albaranes = suma_movimientos = Decimal("0")
    for orden, d in enumerate(resultado.detalles, start=1):
        linea = {"orden": orden, "tipo_relacion": d.tipo_relacion.value, "importe_aplicado": str(d.importe_aplicado),
                 "provenance": dict(d.provenance)}
        if d.factura_albaran_extraido_id:
            linea["albaran_documental"] = extraidos.get(d.factura_albaran_extraido_id)
            suma_albaranes += Decimal(str(d.importe_aplicado))
        if d.factura_movimiento_id:
            linea["movimiento"] = movimientos.get(d.factura_movimiento_id)
            suma_movimientos += Decimal(str(d.importe_aplicado))
        if d.albaran_id_contador is not None:
            linea["albaran_operacional"] = lector.json(
                "select to_jsonb(r)::text from public.albaranes t cross join lateral (select t.id_contador, "
                "t.farmacia, t.id_proveedor, t.proveedor, t.numero_albaran, t.fecha, t.importe_puc, t.importe_pvp, "
                "t.estado) r where t.farmacia = %s and t.id_contador = %s",
                (d.albaran_farmacia, d.albaran_id_contador))
        casados += d.tipo_relacion.value == "UNO_A_UNO"
        sin_coincidencia += d.tipo_relacion.value == "SIN_COINCIDENCIA"
        lineas.append(linea)
    out["resumen_detalles"] = {
        "detalles": len(lineas), "albaranes_documentales": len(extraidos), "albaranes_casados_1a1": casados,
        "albaranes_sin_coincidencia": sin_coincidencia, "movimientos": len(movimientos),
        "importe_albaranes_aplicado": str(suma_albaranes), "importe_movimientos_aplicado": str(suma_movimientos)}
    out["detalles"] = lineas
    return out


def _estado_previsto(lector: _Lector, factura_id: str, simulacion: dict) -> dict:
    """Transicion que aplicarian cf_persistir_conciliacion / cf_registrar_fallo_conciliacion (migracion 18)."""
    intentos_fallo, reintento, intento_max = lector.fila(
        "select f.conciliacion_intentos_fallo, f.conciliacion_reintento_solicitado_at is not null, "
        "(select coalesce(max(c.intento), 0) from public.conciliaciones c where c.factura_id = f.id) "
        "from public.facturas f where f.id = %s", (factura_id,))
    maximo, backoff = lector.fila(
        "select conciliacion_max_intentos, conciliacion_backoff::text[] from public.cf_configuracion where id")
    previas_actuales = [r[0] for r in lector.filas(
        "select id::text from public.conciliaciones where factura_id = %s and es_actual", (factura_id,))]
    if simulacion["camino"] == "PERSISTIR" and simulacion["resultado"] == "CONCILIADA":
        return {"estado_conciliacion_cf": "CONCILIADA", "conciliacion_intentos_fallo": 0,
                "conciliacion_proximo_at": None, "intento_conciliacion": intento_max + 1,
                "conciliaciones_que_pasan_a_no_actual": previas_actuales}
    fallos = 1 if reintento else intentos_fallo + 1
    revision = fallos >= maximo
    out = {"estado_conciliacion_cf": "REVISION_CONCILIACION" if revision else "PENDIENTE_CONCILIAR",
           "conciliacion_intentos_fallo": fallos, "max_intentos": maximo,
           "proximo_reintento": None if revision else f"now() + {backoff[min(fallos, len(backoff)) - 1]}",
           "clase_fallo": "DIFERENCIA" if simulacion["camino"] == "PERSISTIR" else simulacion["fallo"]["clase"]}
    if simulacion["camino"] == "PERSISTIR":
        out["intento_conciliacion"] = intento_max + 1
        out["conciliaciones_que_pasan_a_no_actual"] = previas_actuales
    else:
        out["sin_fila_en_conciliaciones"] = True
    return out


def candidato(salida: Path, previo: Path | None) -> int:
    def leer(lector: _Lector) -> dict:
        out = _operacion(lector)
        cuerpos = {
            "nucleo_igual_a_migracion_18": _cuerpo_remoto(
                lector, "public.cf_reclamar_factura_conciliacion_nucleo(text,integer,text)") == _cuerpo_local(
                ROOT / "sql/migrations/18_cf_conciliacion_manual_atomica.sql",
                "cf_reclamar_factura_conciliacion_nucleo"),
            "manual_one_shot_igual_a_migracion_18": _cuerpo_remoto(
                lector, "public.cf_reclamar_factura_conciliacion_manual_one_shot(text,integer)") == _cuerpo_local(
                ROOT / "sql/migrations/18_cf_conciliacion_manual_atomica.sql",
                "cf_reclamar_factura_conciliacion_manual_one_shot"),
            "elegibilidad_igual_a_migracion_14": _cuerpo_remoto(
                lector, "public.cf_evaluar_elegibilidad_conciliacion(uuid)") == _cuerpo_local(
                ROOT / "sql/migrations/14_cf_claim_conciliacion_v2.sql", "cf_evaluar_elegibilidad_conciliacion"),
        }
        out["cuerpos_productivos"] = cuerpos
        todas = [json.loads(r[0]) for r in lector.filas(SQL_TODAS_CON_FILTROS)]
        elegibles, no_elegibles = [], []
        for f in todas:
            motivos = []
            if not f["f_farmacia"]:
                motivos.append(f"FARMACIA_NO_HABILITADA:{f['farmacia']}")
            if not f["f_estado"]:
                motivos.append(f"ESTADO:{f['estado_conciliacion_cf']}")
            if not f["f_apta"]:
                motivos.append(f"ELEGIBILIDAD:{f['elegibilidad']}:{f['razon']}")
            if not f["f_backoff"]:
                motivos.append(f"BACKOFF_HASTA:{f['proximo_at']}")
            if not f["f_lock"]:
                motivos.append(f"BLOQUEADA_HASTA:{f['bloqueado_hasta']}")
            f = {k: v for k, v in f.items() if not k.startswith("f_")}
            (no_elegibles if motivos else elegibles).append({**f, **({"motivos": motivos} if motivos else {})})
        oficial = [r[0] for r in lector.filas(SQL_SELECTOR_OFICIAL, {"modo": MODO_CLAIM})]
        out["selector_oficial_ids"] = oficial
        out["selector_reproducido_coincide"] = oficial == [f["id"] for f in elegibles]
        out["criterio_ordering"] = ("(conciliacion_reintento_solicitado_at is not null) desc, "
                                    "fecha_factura nulls last, id")
        out["elegibles"] = [{"posicion": i, **f} for i, f in enumerate(elegibles, start=1)]
        out["no_elegibles"] = no_elegibles
        if oficial:
            numero_1 = oficial[0]
            out["candidato_1"] = {
                "id": numero_1,
                "huella_fila": lector.valor(
                    "select md5(to_jsonb(r)::text) from public.facturas t cross join lateral (select "
                    + ", ".join(f"t.{c}" for c in COLUMNAS_HUELLA["facturas"]) + ") r where t.id = %s",
                    (numero_1,)),
            }
            out["simulacion"] = _simular(lector, numero_1)
            out["estado_previsto"] = _estado_previsto(lector, numero_1, out["simulacion"])
        else:
            out["candidato_1"] = None
        return out

    _, datos = _ejecutar_lectura(leer)
    fallos = _puertas_operacion(datos)
    fallos += [f"CUERPO_PRODUCTIVO_DISTINTO: {k}" for k, v in datos["cuerpos_productivos"].items() if not v]
    if not datos["selector_reproducido_coincide"]:
        fallos.append("SELECTOR_REPRODUCIDO_NO_COINCIDE_CON_EL_OFICIAL")
    if datos["candidato_1"] is None:
        fallos.append("SIN_CANDIDATO")
    if previo is not None:
        anterior = json.loads(previo.read_text(encoding="utf-8"))
        datos["revalidacion"] = {
            "candidato_igual": (anterior.get("candidato_1") or {}).get("id") == (datos["candidato_1"] or {}).get("id"),
            "huella_fila_igual": anterior.get("candidato_1") == datos["candidato_1"],
            "simulacion_igual": anterior.get("simulacion") == datos.get("simulacion"),
            "elegibles_iguales": [e["id"] for e in anterior.get("elegibles", [])]
                                 == [e["id"] for e in datos["elegibles"]],
        }
        fallos += [f"REVALIDACION_DISTINTA: {k}" for k, v in datos["revalidacion"].items() if not v]
    datos["fallos"] = fallos
    datos["veredicto"] = "CANDIDATO_OK" if not fallos else "PARAR"
    sha = _escribir(salida, datos)
    print(json.dumps({k: v for k, v in datos.items() if k != "cf_configuracion"},
                     ensure_ascii=False, indent=1, default=str))
    print("sha256", sha)
    return 0 if not fallos else 3


# --------------------------------------------------------------------------- Fase 6

def comparar(pre_ruta: Path, post_ruta: Path, factura: str) -> int:
    pre = json.loads(pre_ruta.read_text(encoding="utf-8"))
    post = json.loads(post_ruta.read_text(encoding="utf-8"))
    if pre["columnas_huella"] != post["columnas_huella"]:
        raise SystemExit("COLUMNAS_HUELLA_DISTINTAS_ENTRE_SNAPSHOTS")
    nuevas_permitidas = {"conciliaciones", "conciliacion_detalles", "historial_facturas"}
    informe: dict = {"factura_reclamada": factura, "tablas": {}, "diferencias_no_explicadas": [],
                     "cambios_factura_reclamada": {}}
    facturas_cambiadas = set()
    for tabla in COLUMNAS_HUELLA:
        a, b = pre["huellas_por_fila"][tabla], post["huellas_por_fila"][tabla]
        va, vb = pre["volcado"][tabla], post["volcado"][tabla]
        nuevas = sorted(set(b) - set(a))
        borradas = sorted(set(a) - set(b))
        cambiadas = sorted(k for k in set(a) & set(b) if a[k][0] != b[k][0])
        informe["tablas"][tabla] = {"antes": len(a), "despues": len(b), "nuevas": len(nuevas),
                                    "borradas": len(borradas), "cambiadas": len(cambiadas),
                                    "nuevas_ids": nuevas, "cambiadas_ids": cambiadas}
        for k in borradas:
            informe["diferencias_no_explicadas"].append([tabla, "BORRADA", k])
        for k in nuevas:
            if tabla not in nuevas_permitidas or b[k][1] != factura:
                informe["diferencias_no_explicadas"].append([tabla, "NUEVA_NO_PERMITIDA", k, b[k][1]])
        for k in cambiadas:
            antes, despues = json.loads(va[k]), json.loads(vb[k])
            columnas = sorted(c for c in despues if antes.get(c) != despues.get(c))
            if tabla == "facturas":
                facturas_cambiadas.add(k)
            explicada = (
                (tabla == "facturas" and k == factura)
                or (tabla == "conciliaciones" and a[k][1] == factura and b[k][1] == factura
                    and columnas == ["es_actual"] and antes["es_actual"] is True and despues["es_actual"] is False)
            )
            if explicada:
                informe["cambios_factura_reclamada"][f"{tabla}:{k}"] = {
                    c: [antes.get(c), despues.get(c)] for c in columnas}
            else:
                informe["diferencias_no_explicadas"].append([tabla, "CAMBIADA_NO_PERMITIDA", k, columnas])
    claims_nuevos = sorted({json.loads(post["volcado"]["historial_facturas"][k])["factura_id"]
                            for k in informe["tablas"]["historial_facturas"]["nuevas_ids"]
                            if json.loads(post["volcado"]["historial_facturas"][k])["evento"]
                            == "CONCILIACION_CLAIM"})
    informe["facturas_cambiadas"] = sorted(facturas_cambiadas)
    informe["facturas_con_claim_nuevo"] = claims_nuevos
    informe["facturas_reclamadas_max_1"] = len(set(claims_nuevos) | facturas_cambiadas) <= 1
    informe["conciliaciones_nuevas"] = [json.loads(post["volcado"]["conciliaciones"][k])
                                        for k in informe["tablas"]["conciliaciones"]["nuevas_ids"]]
    informe["flags_identicos"] = pre["flags"] == post["flags"]
    informe["cf_configuracion_identica"] = pre["cf_configuracion"] == post["cf_configuracion"]
    informe["operacion_post"] = {k: post[k] for k in ("flags", "locks_documentos", "claims_conciliacion",
                                                      "normalizando", "workers")}
    informe["operacion_como_antes"] = all(pre[k] == post[k] for k in ("locks_documentos", "claims_conciliacion",
                                                                      "normalizando", "workers"))
    informe["conteos"] = {t: [pre["conteos"][t], post["conteos"][t]] for t in TABLAS_CONTEO}
    informe["facturas_por_estado_conciliacion_cf"] = {"antes": pre["facturas_por_estado_conciliacion_cf"],
                                                      "despues": post["facturas_por_estado_conciliacion_cf"]}
    ok = (not informe["diferencias_no_explicadas"] and informe["facturas_reclamadas_max_1"]
          and informe["flags_identicos"] and informe["cf_configuracion_identica"]
          and informe["operacion_como_antes"])
    informe["veredicto"] = "POSTCHECK_OK" if ok else "POSTCHECK_CON_DIFERENCIAS"
    print(json.dumps(informe, ensure_ascii=False, indent=1, default=str))
    return 0 if ok else 3


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else ""
    if modo == "preflight":
        sys.exit(preflight(_salida_fuera_del_repo(sys.argv[2])))
    elif modo == "snapshot":
        sys.exit(snapshot(_salida_fuera_del_repo(sys.argv[2])))
    elif modo == "candidato":
        sys.exit(candidato(_salida_fuera_del_repo(sys.argv[2]),
                           Path(sys.argv[3]) if len(sys.argv) > 3 else None))
    elif modo == "comparar":
        sys.exit(comparar(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]))
    else:
        raise SystemExit("modo desconocido")
