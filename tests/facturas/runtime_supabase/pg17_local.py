"""Harness PostgreSQL 17 local para tests de integracion (Hitos 2AQ y 2AR).

Contenedor ``postgres:17-alpine`` desechable, ``--network none``, sin puertos y en
tmpfs; acceso exclusivo con ``docker exec psql``. Cadena certificada en 2AN
(baseline 00 incluye 06; staging 06 incluye 13). Storage simulado en memoria con
los fixtures reales 2AP. Las RPC se ejecutan con ``set role service_role``.
Sin conexion a produccion.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import uuid
from pathlib import Path

from src.facturas.runtime_supabase.compositor_manual import construir_worker_manual_productivo
from src.facturas.runtime_supabase.modelos import ConfiguracionRuntime


ROOT = Path(__file__).resolve().parents[3]
MIG = ROOT / "sql/migrations"
STG = ROOT / "sql/staging"
FIXTURES = ROOT / "pruebas/facturas/documentos/fixtures_2ap"
ALLIANCE = FIXTURES / "alliance_apto_multifactura.pdf"
HEFAME = FIXTURES / "hefame_no_autorizado.pdf"
IMAGEN = "postgres:17-alpine"
CADENA = [
    STG / "00_baseline_controlfarmacias.sql",
    *(MIG / n for n in (
        "06b_cf_integridad_albaranes.sql", "07_cf_proveedores_config.sql",
        "08_cf_core_facturas.sql", "08b_cf_estado_lectura_compatibilidad.sql",
        "09_cf_normalizacion_runtime.sql", "10_cf_movimientos_incidencias_historial.sql",
        "11_cf_conciliacion.sql", "12_cf_views_rls_rpc.sql",
    )),
    STG / "01_seed_controlfarmacias.sql",
    STG / "06_test_backfill_pio.sql",
    *(MIG / n for n in (
        "14_cf_claim_conciliacion_v2.sql", "15_cf_multifactura.sql",
        "16_cf_worker_manual_one_shot.sql",
    )),
]
FLAGS_SQL = (
    "select normalizacion_automatica,conciliacion_automatica,luna_habilitada,"
    "farmacias_habilitadas from public.cf_configuracion where id"
)
FLAGS_ESPERADOS = "f|f|f|{PIO}"


def _docker(*args, entrada=None, comprobar=True):
    r = subprocess.run(["docker", *args], input=entrada, text=True, encoding="utf-8",
                       capture_output=True, timeout=180)
    if comprobar and r.returncode:
        raise RuntimeError(r.stderr.strip())
    return r


def _expandir(path: Path) -> str:
    lineas = []
    for linea in path.read_text(encoding="utf-8").splitlines():
        if linea.startswith("\\ir "):
            lineas.append(_expandir((path.parent / linea[4:].strip()).resolve()))
        else:
            lineas.append(linea)
    return "\n".join(lineas)


class _Pg:
    def __init__(self, contenedor: str, db: str):
        self.contenedor = contenedor
        self.db = db

    def sql(self, sentencia: str) -> str:
        r = _docker("exec", "-i", self.contenedor, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
                    "-U", "postgres", "-d", self.db, entrada=sentencia, comprobar=False)
        if r.returncode:
            raise RuntimeError(r.stderr.strip())
        return r.stdout.strip()

    def json(self, consulta: str):
        return json.loads(self.sql(f"select coalesce(json_agg(t),'[]'::json)::text from ({consulta}) t;"))


MIGRACION_17 = MIG / "17_cf_replay_y_fallos_no_bloqueantes.sql"
ROLLBACK_17 = MIG / "17_cf_replay_y_fallos_no_bloqueantes.rollback.sql"


def esquema(pg: "_Pg") -> str:
    """Volcado de esquema sin las lineas restrict/unrestrict aleatorias de pg_dump."""
    salida = _docker("exec", pg.contenedor, "pg_dump", "-U", "postgres", "-s", pg.db).stdout
    return "\n".join(l for l in salida.splitlines() if not re.match(r"\\(un)?restrict ", l))


# --------------------------------------------------------------------------
# Cliente Supabase minimo sobre PostgreSQL real + Storage simulado
# --------------------------------------------------------------------------


def _lit(valor) -> str:
    if valor is None:
        return "null"
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, int):
        return str(valor)
    return "'" + str(valor).replace("'", "''") + "'"


class _Respuesta:
    def __init__(self, data):
        self.data = data


class _Diferida:
    def __init__(self, funcion):
        self._funcion = funcion

    def execute(self):
        return _Respuesta(self._funcion())


class _Tabla:
    def __init__(self, pg: _Pg, tabla: str):
        self.pg, self.tabla, self.columnas, self.filtros, self.limite = pg, tabla, "*", [], None

    def select(self, columnas):
        self.columnas = columnas
        return self

    def eq(self, columna, valor):
        self.filtros.append(f"{columna}::text = {_lit(valor)}")
        return self

    def limit(self, n):
        self.limite = int(n)
        return self

    def execute(self):
        where = " where " + " and ".join(self.filtros) if self.filtros else ""
        limite = f" limit {self.limite}" if self.limite else ""
        return _Respuesta(self.pg.json(
            f"select {self.columnas} from public.{self.tabla}{where}{limite}"))


class _Bucket:
    def __init__(self, cliente, nombre):
        self.cliente, self.nombre = cliente, nombre

    def download(self, ruta):
        self.cliente.descargas.append(ruta)
        if (self.nombre, ruta) not in self.cliente.objetos:
            raise RuntimeError("Object not found")
        return self.cliente.objetos[(self.nombre, ruta)]


class _Storage:
    def __init__(self, cliente):
        self.cliente = cliente

    def from_(self, nombre):
        return _Bucket(self.cliente, nombre)


class ClientePg17:
    def __init__(self, pg: _Pg, *, vigilar_flags: bool = False, compat_16: bool = False):
        self.pg = pg
        self.vigilar_flags = vigilar_flags
        # compat_16: reproduce el cliente anterior a 2AR (sin p_clase_fallo), unico
        # compatible con el esquema 16. El Python 2AR exige la migracion 17.
        self.compat_16 = compat_16
        self.flags_observadas: list[str] = []
        self.objetos: dict[tuple[str, str], bytes] = {}
        self.descargas: list[str] = []
        self.rpcs: list[tuple[str, dict]] = []
        self.storage = _Storage(self)

    def table(self, tabla):
        return _Tabla(self.pg, tabla)

    def rpc(self, nombre, payload):
        self.rpcs.append((nombre, payload))
        return _Diferida(lambda: self._rpc_vigilado(nombre, payload))

    def _rpc_vigilado(self, nombre, payload):
        if self.vigilar_flags:
            self.flags_observadas.append(self.pg.sql(FLAGS_SQL))
        try:
            return self._rpc(nombre, payload)
        finally:
            if self.vigilar_flags:
                self.flags_observadas.append(self.pg.sql(FLAGS_SQL))

    def _rpc(self, nombre, payload):
        if self.compat_16:
            payload = {k: v for k, v in payload.items() if k != "p_clase_fallo"}
        argumentos = []
        for clave, valor in payload.items():
            if clave == "p_resultado":
                texto = _lit(json.dumps(valor, ensure_ascii=False, default=str)) + "::jsonb"
            elif clave == "p_segmentos_autorizados":
                texto = ("array[" + ",".join(_lit(v) for v in valor) + "]::text[]") if valor else "'{}'::text[]"
            else:
                texto = _lit(valor)
            argumentos.append(f"{clave} => {texto}")
        filas = json.loads(self.pg.sql(
            "set role service_role; "
            f"select coalesce(json_agg(r),'[]'::json)::text from public.{nombre}({', '.join(argumentos)}) r;"
        ))
        if nombre.startswith("cf_reclamar"):
            return filas
        return filas[0] if filas else None


# --------------------------------------------------------------------------
# Utilidades de escenario
# --------------------------------------------------------------------------


def _registrar(pg: _Pg, cliente: ClientePg17, pdf_bytes: bytes, orden: int, *, hash_registrado=None):
    documento_id = str(uuid.uuid4())
    ruta = f"PIO/2AQ/{documento_id}.pdf"
    sha = hash_registrado or hashlib.sha256(pdf_bytes).hexdigest()
    pg.sql(
        "insert into public.documentos_facturas(id,farmacia,archivo_nombre,archivo_ruta,archivo_hash,fecha_importacion) "
        f"values ({_lit(documento_id)},'PIO','no-es-evidencia.pdf',{_lit(ruta)},{_lit(sha)},"
        f"timestamptz '2000-01-01' + interval '{orden} minutes');"
    )
    cliente.objetos[("facturas-pdf", ruta)] = pdf_bytes
    return documento_id


def _truncado(tmp_path: Path, conservar: list[int]) -> bytes:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(ALLIANCE))
    for indice in sorted(set(range(len(pdf))) - set(conservar), reverse=True):
        pdf.del_page(indice)
    destino = tmp_path / "truncado.pdf"
    pdf.save(str(destino))
    pdf.close()
    return destino.read_bytes()


def _estado(pg: _Pg, documento_id: str) -> dict:
    return pg.json(
        "select estado_lectura,estado_persistencia,bloqueado_por,bloqueado_hasta,"
        "ultimo_error_codigo,proximo_reintento_at,inventario_facturas "
        f"from public.documentos_facturas where id={_lit(documento_id)}")[0]


def _huella_resto(pg: _Pg, excluido: str) -> str:
    return pg.sql(
        "select md5(coalesce(string_agg(to_jsonb(d)::text,'' order by id),'')) "
        f"from public.documentos_facturas d where id<>{_lit(excluido)};")


def _huella_facturas(pg: _Pg) -> str:
    return pg.sql(
        "select md5(coalesce(string_agg(to_jsonb(f)::text,'' order by id),'')) from public.facturas f;")


def _locks(pg: _Pg) -> str:
    return pg.sql(
        "select (select count(*) from public.documentos_facturas where bloqueado_hasta>now() or bloqueado_por is not null),"
        "(select count(*) from public.facturas where conciliacion_bloqueado_hasta>now());")


def _siguiente_candidato(pg: _Pg) -> str:
    """Reproduce READ_ONLY el ordering oficial del nucleo (modo MANUAL_ONE_SHOT)."""
    return pg.sql(
        "select d.id from public.documentos_facturas d cross join public.cf_configuracion c "
        "where c.id = true and d.farmacia = any(c.farmacias_habilitadas) "
        "and d.estado_lectura in ('PENDIENTE','ERROR') "
        "and coalesce(d.proximo_reintento_at,'-infinity'::timestamptz) <= now() "
        "and coalesce(d.bloqueado_hasta,'-infinity'::timestamptz) <= now() "
        "order by (d.reprocesar_solicitado_at is not null) desc, d.fecha_importacion, d.id limit 1;")


def _worker(cliente: ClientePg17, tmp_path: Path, nombre: str = "a"):
    return construir_worker_manual_productivo(
        cliente, ConfiguracionRuntime(), f"manual-2aq-{nombre}", tmp_path / nombre)


def _facturas_de(pg: _Pg, documento_id: str):
    return pg.json(
        "select numero_factura,importe_total::text as total,estado_normalizacion,estado_conciliacion_cf "
        f"from public.facturas where documento_id={_lit(documento_id)} order by numero_factura")


def _ejecuciones(pg: _Pg, documento_id: str):
    return pg.json(
        "select disparador,estado,idempotency_key,error_codigo,error_detalle,"
        "resultado_json#>>'{provenance_ejecucion,modo_ejecucion}' as modo "
        f"from public.normalizacion_ejecuciones where documento_id={_lit(documento_id)} order by intento")


# --------------------------------------------------------------------------
# Plantillas por variante de esquema
# --------------------------------------------------------------------------

VARIANTES = ("16", "17", "16_rollback")


def construir_plantilla(contenedor: str, variante: str) -> str:
    """16: cadena 2AN; 17: 16 + migracion 17 aplicada dos veces; 16_rollback: 16 + 17 + rollback."""
    assert variante in VARIANTES
    nombre = f"cf_plantilla_{variante}"
    _docker("exec", contenedor, "createdb", "-U", "postgres", nombre)
    pg = _Pg(contenedor, nombre)
    for path in CADENA:
        pg.sql(_expandir(path))
    if variante == "17":
        pg.sql(MIGRACION_17.read_text(encoding="utf-8"))
        pg.sql(MIGRACION_17.read_text(encoding="utf-8"))
    elif variante == "16_rollback":
        pg.sql(MIGRACION_17.read_text(encoding="utf-8"))
        pg.sql(ROLLBACK_17.read_text(encoding="utf-8"))
    return nombre


def base_desde(contenedor: str, plantilla: str) -> _Pg:
    db = "cf_caso_" + uuid.uuid4().hex[:12]
    _docker("exec", contenedor, "createdb", "-U", "postgres", "-T", plantilla, db)
    return _Pg(contenedor, db)


def orden_de_claims(pg: _Pg, n: int) -> list[str]:
    """Ordering real: n claims manuales consecutivos con el selector oficial."""
    ids = []
    for i in range(n):
        filas = pg.json(
            "select id from public.cf_reclamar_documento_normalizacion_manual_one_shot("
            f"'orden-{i}', 300)")
        if not filas:
            break
        ids.append(filas[0]["id"])
    return ids
