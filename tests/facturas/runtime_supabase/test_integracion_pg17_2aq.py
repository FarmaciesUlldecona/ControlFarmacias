"""Hito 2AQ: extremo a extremo del compositor manual sobre PostgreSQL 17 REAL local.

Contenedor ``postgres:17-alpine`` desechable, ``--network none``, sin puertos y en
tmpfs; se accede exclusivamente con ``docker exec psql``. Migraciones aplicadas
desde cero con la cadena certificada en 2AN (baseline 00 incluye 06; staging 06
incluye 13). Storage simulado en memoria sirviendo los fixtures reales 2AP.
Las RPC se ejecutan con ``set role service_role`` para respetar los grants.
Skip si Docker, la imagen o los fixtures no estan disponibles.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from src.facturas.runtime_supabase.compositor_manual import construir_worker_manual_productivo
from src.facturas.runtime_supabase.modelos import ConfiguracionRuntime


pytestmark = pytest.mark.pg17_local

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


@pytest.fixture(scope="module")
def pg17(tmp_path_factory):
    if shutil.which("docker") is None:
        pytest.skip("Docker no disponible")
    if _docker("image", "inspect", IMAGEN, comprobar=False).returncode:
        pytest.skip(f"imagen local {IMAGEN} no disponible")
    if not ALLIANCE.exists() or not HEFAME.exists():
        pytest.skip("fixtures reales 2AP ausentes")
    nombre = "cf-2aq-" + uuid.uuid4().hex[:12]
    _docker("run", "-d", "--rm", "--name", nombre, "--label", "controlfarmacias.certificacion=2aq",
            "--network", "none", "--tmpfs", "/var/lib/postgresql/data",
            "-e", "POSTGRES_PASSWORD=local-only", IMAGEN)
    try:
        for _ in range(120):
            if _docker("exec", nombre, "pg_isready", "-U", "postgres", "-q", comprobar=False).returncode == 0:
                break
            subprocess.run(["python", "-c", "import time;time.sleep(0.5)"])
        info = json.loads(_docker("inspect", nombre).stdout)[0]
        assert info["HostConfig"]["NetworkMode"] == "none" and not info["HostConfig"]["PortBindings"]
        _docker("exec", nombre, "createdb", "-U", "postgres", "cf_2aq_plantilla")
        plantilla = _Pg(nombre, "cf_2aq_plantilla")
        for path in CADENA:
            plantilla.sql(_expandir(path))
        yield nombre
    finally:
        _docker("rm", "-f", nombre, comprobar=False)


_contador = iter(range(10_000))


@pytest.fixture
def base(pg17):
    db = f"cf_2aq_caso_{next(_contador)}"
    _docker("exec", pg17, "createdb", "-U", "postgres", "-T", "cf_2aq_plantilla", db)
    return _Pg(pg17, db)


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
    def __init__(self, pg: _Pg):
        self.pg = pg
        self.objetos: dict[tuple[str, str], bytes] = {}
        self.descargas: list[str] = []
        self.rpcs: list[tuple[str, dict]] = []
        self.storage = _Storage(self)

    def table(self, tabla):
        return _Tabla(self.pg, tabla)

    def rpc(self, nombre, payload):
        self.rpcs.append((nombre, payload))
        return _Diferida(lambda: self._rpc(nombre, payload))

    def _rpc(self, nombre, payload):
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
# 2.1 a 2.6
# --------------------------------------------------------------------------


def test_pg17_esquema_y_flags(base):
    assert base.sql("show server_version").startswith("17.")
    assert base.sql(FLAGS_SQL) == FLAGS_ESPERADOS
    assert base.sql(
        "select to_regprocedure('public.cf_reclamar_documento_normalizacion_manual_one_shot(text,integer)') is not null,"
        "to_regprocedure('public.cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[],text)') is not null,"
        "has_function_privilege('service_role','public.cf_reclamar_documento_normalizacion_nucleo(text,integer,text)','execute'),"
        "(select pg_get_constraintdef(oid) like '%MANUAL_ONE_SHOT%' from pg_constraint "
        " where conname='normalizacion_ejecuciones_disparador_check')") == "t|t|f|t"


def test_pg17_2_1_alliance_apto(base, tmp_path):
    cliente = ClientePg17(base)
    alliance = _registrar(base, cliente, ALLIANCE.read_bytes(), 1)
    segundo = _registrar(base, cliente, HEFAME.read_bytes(), 2)
    resto, facturas_previas = _huella_resto(base, alliance), _huella_facturas(base)
    conciliaciones = base.sql("select count(*) from public.conciliaciones")
    resultado = _worker(cliente, tmp_path).ejecutar_una_manual()
    assert resultado.documentos_reclamados == 1
    assert resultado.facturas_conciliacion_reclamadas == 0
    assert [n for n, _ in cliente.rpcs] == [
        "cf_reclamar_documento_normalizacion_manual_one_shot", "cf_persistir_documento_multifactura"]
    assert cliente.descargas == [f"PIO/2AQ/{alliance}.pdf"]
    facturas = _facturas_de(base, alliance)
    assert [(f["numero_factura"], f["total"]) for f in facturas] == [
        ("08011303", "9670.9200"), ("08011304", "4195.2400"), ("08011305", "141.2100")]
    assert {f["estado_conciliacion_cf"] for f in facturas} == {"PENDIENTE_CONCILIAR"}
    ejecuciones = _ejecuciones(base, alliance)
    assert [(e["disparador"], e["modo"], e["estado"]) for e in ejecuciones] == [
        ("MANUAL_ONE_SHOT", "MANUAL_ONE_SHOT", "COMPLETADA")]
    estado = _estado(base, alliance)
    assert (estado["estado_lectura"], estado["estado_persistencia"]) == ("NORMALIZADA", "COMPLETA")
    assert estado["bloqueado_por"] is None and estado["bloqueado_hasta"] is None
    assert _huella_resto(base, alliance) == resto
    assert _estado(base, segundo)["estado_lectura"] == "PENDIENTE"
    assert base.sql("select count(*) from public.conciliaciones") == conciliaciones
    assert base.sql("select count(*) from public.facturas") == str(3 + 3)
    assert facturas_previas != _huella_facturas(base)
    assert _locks(base) == "0|0"
    assert base.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_pg17_2_2_hefame_no_soportado_y_cabeza_de_cola(base, tmp_path):
    cliente = ClientePg17(base)
    hefame = _registrar(base, cliente, HEFAME.read_bytes(), 1)
    alliance = _registrar(base, cliente, ALLIANCE.read_bytes(), 2)
    resto, facturas_previas = _huella_resto(base, hefame), _huella_facturas(base)
    resultado = _worker(cliente, tmp_path).ejecutar_una_manual()
    assert resultado.documentos_reclamados == 0
    assert [n for n, _ in cliente.rpcs] == [
        "cf_reclamar_documento_normalizacion_manual_one_shot", "cf_registrar_fallo_normalizacion"]
    ejecuciones = _ejecuciones(base, hefame)
    assert [(e["disparador"], e["estado"], e["error_codigo"], e["error_detalle"]) for e in ejecuciones] == [
        ("MANUAL_ONE_SHOT", "ERROR", "DocumentoNoAptoManual", "PROVEEDOR_NO_SOPORTADO_MANUAL")]
    estado = _estado(base, hefame)
    assert estado["estado_lectura"] == "ERROR"
    assert estado["estado_persistencia"] == "PENDIENTE"
    assert estado["ultimo_error_codigo"] == "DocumentoNoAptoManual"
    assert estado["proximo_reintento_at"] is None
    assert estado["bloqueado_por"] is None and estado["bloqueado_hasta"] is None
    assert _facturas_de(base, hefame) == [] and _facturas_de(base, alliance) == []
    assert _huella_facturas(base) == facturas_previas
    assert _huella_resto(base, hefame) == resto
    assert _estado(base, alliance)["estado_lectura"] == "PENDIENTE"
    # Sin backoff ni penalizacion: el documento fallido sigue siendo el candidato n.1.
    assert _siguiente_candidato(base) == hefame
    assert _locks(base) == "0|0"
    assert base.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_pg17_2_3_sha_incorrecto(base, tmp_path):
    cliente = ClientePg17(base)
    alliance = _registrar(base, cliente, ALLIANCE.read_bytes(), 1, hash_registrado="f" * 64)
    segundo = _registrar(base, cliente, HEFAME.read_bytes(), 2)
    _worker(cliente, tmp_path).ejecutar_una_manual()
    ejecuciones = _ejecuciones(base, alliance)
    assert [(e["estado"], e["error_detalle"]) for e in ejecuciones] == [("ERROR", "SHA256_NO_COINCIDE")]
    estado = _estado(base, alliance)
    assert estado["estado_lectura"] == "ERROR" and estado["bloqueado_por"] is None
    assert _facturas_de(base, alliance) == []
    assert not (tmp_path / "a" / f"{alliance}.pdf").exists()
    assert _estado(base, segundo)["estado_lectura"] == "PENDIENTE"
    assert _locks(base) == "0|0"
    assert base.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_pg17_2_4_multifactura_con_factura_incompleta(base, tmp_path):
    cliente = ClientePg17(base)
    documento = _registrar(base, cliente, _truncado(tmp_path, list(range(8))), 1)
    segundo = _registrar(base, cliente, HEFAME.read_bytes(), 2)
    _worker(cliente, tmp_path).ejecutar_una_manual()
    assert [(f["numero_factura"]) for f in _facturas_de(base, documento)] == ["08011303", "08011304"]
    estado = _estado(base, documento)
    assert (estado["estado_lectura"], estado["estado_persistencia"]) == ("REVISION", "PARCIAL")
    inventario = {i["componentes"][1]: i["estado"] for i in estado["inventario_facturas"]}
    assert inventario == {"08011304": "PERSISTIDAS", "08011303": "PERSISTIDAS",
                          "08011305": "REQUIERE_REVISION"}
    historial = base.json(
        "select evento,estado_nuevo->>'estado_persistencia' as persistencia from public.historial_facturas "
        f"where documento_id={_lit(documento)} and evento='INVENTARIO_MULTIFACTURA'")
    assert historial == [{"evento": "INVENTARIO_MULTIFACTURA", "persistencia": "PARCIAL"}]
    assert estado["bloqueado_por"] is None
    # REVISION no es reclamable: el siguiente candidato ya no es este documento.
    assert _siguiente_candidato(base) == segundo
    assert _locks(base) == "0|0"
    assert base.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_pg17_limite_conocido_factura_entera_omitida(base, tmp_path):
    cliente = ClientePg17(base)
    documento = _registrar(base, cliente, _truncado(tmp_path, list(range(7))), 1)
    _worker(cliente, tmp_path).ejecutar_una_manual()
    assert [f["numero_factura"] for f in _facturas_de(base, documento)] == ["08011303", "08011304"]
    estado = _estado(base, documento)
    # LIMITE CONOCIDO: la omision de la factura entera no deja rastro documental.
    assert (estado["estado_lectura"], estado["estado_persistencia"]) == ("NORMALIZADA", "COMPLETA")
    assert len(estado["inventario_facturas"]) == 2


def test_pg17_2_5_idempotencia(base, tmp_path):
    cliente = ClientePg17(base)
    alliance = _registrar(base, cliente, ALLIANCE.read_bytes(), 1)
    _worker(cliente, tmp_path, "uno").ejecutar_una_manual()
    facturas = _huella_facturas(base)
    primera = [p for n, p in cliente.rpcs if n == "cf_persistir_documento_multifactura"][0]
    base.sql(f"select public.cf_solicitar_reprocesado({_lit(alliance)}::uuid,'PIO-LOCAL-2AQ');")
    assert _siguiente_candidato(base) == alliance
    _worker(cliente, tmp_path, "dos").ejecutar_una_manual()
    segunda = [p for n, p in cliente.rpcs if n == "cf_persistir_documento_multifactura"][1]
    assert primera["p_idempotency_key"] == segunda["p_idempotency_key"]
    assert primera["p_resultado_hash"] == segunda["p_resultado_hash"]
    assert _huella_facturas(base) == facturas
    assert base.sql(
        f"select count(*) from public.facturas where documento_id={_lit(alliance)}") == "3"
    assert len(_ejecuciones(base, alliance)) == 1
    # HALLAZGO 2AQ (divergencia con el simulador 2AP): el replay idempotente de la
    # RPC multifactura retorna antes de actualizar el documento. El claim del
    # segundo worker queda retenido y el documento en NORMALIZANDO; al expirar el
    # lock no vuelve a ser reclamable (NORMALIZANDO no es PENDIENTE/ERROR).
    estado = _estado(base, alliance)
    assert (estado["estado_lectura"], estado["estado_persistencia"]) == ("NORMALIZANDO", "COMPLETA")
    assert estado["bloqueado_por"] == "manual-2aq-dos" and estado["bloqueado_hasta"] is not None
    assert _locks(base) == "1|0"
    base.sql(f"update public.documentos_facturas set bloqueado_hasta=now()-interval '1 second' where id={_lit(alliance)};")
    assert _siguiente_candidato(base) != alliance
    assert base.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_pg17_2_6_flags_constantes_durante_todo(base, tmp_path):
    cliente = ClientePg17(base)
    _registrar(base, cliente, ALLIANCE.read_bytes(), 1)
    observadas = []
    original = cliente._rpc

    def espia(nombre, payload):
        observadas.append(base.sql(FLAGS_SQL))
        salida = original(nombre, payload)
        observadas.append(base.sql(FLAGS_SQL))
        return salida

    cliente._rpc = espia
    _worker(cliente, tmp_path).ejecutar_una_manual()
    assert observadas and set(observadas) == {FLAGS_ESPERADOS}
