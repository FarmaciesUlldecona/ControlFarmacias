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


class _Sesion:
    """Sesion ``psql`` persistente sobre ``docker exec -i`` (Hito 2BH).

    Cada ``docker exec`` cuesta ~0,22 s en Windows y la suite ``pg17_local`` hace ~9.500 llamadas; en una
    sesion persistente cuesta ~3 ms. Por llamada se conserva lo que daba un proceso nuevo:
    - ``ON_ERROR_STOP=1``: ante un error psql termina (lo anterior ya ejecutado queda, como antes) y se
      devuelve su stderr; la siguiente llamada abre otra sesion;
    - al terminar, ``rollback`` y ``discard all`` (rol, parametros, transaccion abierta, temporales, locks
      de sesion y planes), como cuando el proceso se cerraba.
    """

    TIMEOUT_SEGUNDOS = 180

    def __init__(self, contenedor: str, db: str):
        import queue
        import threading

        self.proceso = subprocess.Popen(
            ["docker", "exec", "-i", "-e", "PGAPPNAME=cf_pg17_test", contenedor, "psql", "-X", "-qAt",
             "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", db],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1)
        self.salida: "queue.Queue[str | None]" = queue.Queue()
        self.errores: list[str] = []
        self._hilos = [threading.Thread(target=self._leer, args=(self.proceso.stdout, self.salida.put), daemon=True),
                       threading.Thread(target=self._leer, args=(self.proceso.stderr, self.errores.append),
                                        daemon=True)]
        for hilo in self._hilos:
            hilo.start()

    @staticmethod
    def _leer(flujo, destino) -> None:
        for linea in flujo:
            destino(linea)
        destino(None)

    def viva(self) -> bool:
        return self.proceso.poll() is None

    def ejecutar(self, sentencia: str) -> str:
        import queue

        marca = "__CF_FIN_" + uuid.uuid4().hex + "__"
        del self.errores[:]
        # ";" cierra una ultima sentencia sin punto y coma (psql la ejecutaba al llegar a EOF).
        self.proceso.stdin.write(f"{sentencia}\n;\nrollback;\ndiscard all;\n\\echo {marca}\n")
        self.proceso.stdin.flush()
        lineas = []
        while True:
            try:
                linea = self.salida.get(timeout=self.TIMEOUT_SEGUNDOS)
            except queue.Empty:
                self.cerrar()
                raise RuntimeError("PSQL_TIMEOUT")
            if linea is None:  # psql termino: error con ON_ERROR_STOP
                self.cerrar()
                return self._fallo()
            if linea.rstrip("\r\n") == marca:
                return "".join(lineas).strip()
            lineas.append(linea)

    def _fallo(self):
        for hilo in self._hilos:
            hilo.join(timeout=10)
        raise RuntimeError("".join(e for e in self.errores if e is not None).strip())

    def cerrar(self) -> None:
        try:
            self.proceso.stdin.close()
        except OSError:
            pass
        try:
            self.proceso.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proceso.kill()
            self.proceso.wait()


_SESIONES: dict[tuple[str, str], _Sesion] = {}


def cerrar_sesiones(contenedor: str | None = None, db: str | None = None) -> None:
    """Cierra las sesiones persistentes (todas, las de un contenedor o las de una base)."""
    for clave in [k for k in _SESIONES if contenedor in (None, k[0]) and db in (None, k[1])]:
        _SESIONES.pop(clave).cerrar()


class _Pg:
    def __init__(self, contenedor: str, db: str):
        self.contenedor = contenedor
        self.db = db

    def sql(self, sentencia: str) -> str:
        clave = (self.contenedor, self.db)
        sesion = _SESIONES.get(clave)
        if sesion is None or not sesion.viva():
            sesion = _SESIONES[clave] = _Sesion(self.contenedor, self.db)
        try:
            return sesion.ejecutar(sentencia)
        except RuntimeError:
            _SESIONES.pop(clave, None)
            raise

    def json(self, consulta: str):
        return json.loads(self.sql(f"select coalesce(json_agg(t),'[]'::json)::text from ({consulta}) t;"))


MIGRACION_17 = MIG / "17_cf_replay_y_fallos_no_bloqueantes.sql"
ROLLBACK_17 = MIG / "17_cf_replay_y_fallos_no_bloqueantes.rollback.sql"
MIGRACION_18 = MIG / "18_cf_conciliacion_manual_atomica.sql"
ROLLBACK_18 = MIG / "18_cf_conciliacion_manual_atomica.rollback.sql"
MIGRACION_19 = MIG / "19_cf_privilegios_minimos.sql"
ROLLBACK_19 = MIG / "19_cf_privilegios_minimos.rollback.sql"
MIGRACION_20 = MIG / "20_cf_alliance_tolerancia_enriquecimiento.sql"
ROLLBACK_20 = MIG / "20_cf_alliance_tolerancia_enriquecimiento.rollback.sql"
MIGRACION_21 = MIG / "21_cf_exclusividad_albaranes.sql"
ROLLBACK_21 = MIG / "21_cf_exclusividad_albaranes.rollback.sql"
MIGRACION_22 = MIG / "22_cf_resincronizacion_albaranes.sql"
ROLLBACK_22 = MIG / "22_cf_resincronizacion_albaranes.rollback.sql"
MIGRACION_23 = MIG / "23_cf_aprobaciones_albaranes.sql"
ROLLBACK_23 = MIG / "23_cf_aprobaciones_albaranes.rollback.sql"
MIGRACION_24 = MIG / "24_cf_r17_recepcion.sql"
ROLLBACK_24 = MIG / "24_cf_r17_recepcion.rollback.sql"
MIGRACION_25 = MIG / "25_cf_claims_huerfanos_normalizacion.sql"
ROLLBACK_25 = MIG / "25_cf_claims_huerfanos_normalizacion.rollback.sql"
MIGRACION_26 = MIG / "26_cf_persistencia_multifactura_indexada.sql"
ROLLBACK_26 = MIG / "26_cf_persistencia_multifactura_indexada.rollback.sql"
MIGRACION_27 = MIG / "27_cf_reintento_tras_fallo_de_persistencia.sql"
ROLLBACK_27 = MIG / "27_cf_reintento_tras_fallo_de_persistencia.rollback.sql"
MIGRACION_28 = MIG / "28_cf_persistencia_multifactura_ligera.sql"
ROLLBACK_28 = MIG / "28_cf_persistencia_multifactura_ligera.rollback.sql"
MIGRACION_29 = MIG / "29_cf_rol_lectura.sql"
ROLLBACK_29 = MIG / "29_cf_rol_lectura.rollback.sql"


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
    """select/eq/gte/lte/order/limit/range/single e insert (sin update ni delete).

    ``rol``: si se indica (p. ej. ``service_role``), cada sentencia se ejecuta con
    ``set role`` como haria PostgREST con esa clave (Hito 2AX).
    """

    def __init__(self, pg: _Pg, tabla: str, rol: str | None = None):
        self.pg, self.tabla, self.columnas, self.filtros, self.limite = pg, tabla, "*", [], None
        self.orden, self.unica, self.rol, self.desde, self.fila = [], False, rol, None, None

    def select(self, columnas):
        self.columnas = columnas
        return self

    def eq(self, columna, valor):
        self.filtros.append(f"{columna}::text = {_lit(valor)}")
        return self

    def gte(self, columna, valor):
        self.filtros.append(f"{columna} >= {_lit(valor)}")
        return self

    def lte(self, columna, valor):
        self.filtros.append(f"{columna} <= {_lit(valor)}")
        return self

    def order(self, columna, desc=False):
        self.orden.append(f"{columna}{' desc' if desc else ''}")
        return self

    def limit(self, n):
        self.limite = int(n)
        return self

    def single(self):
        self.unica = True
        return self

    def range(self, inicio, fin):
        self.desde, self.limite = int(inicio), int(fin) - int(inicio) + 1
        return self

    def insert(self, fila: dict):
        self.fila = fila
        return self

    def _consulta(self, consulta: str):
        if self.rol is None:
            return self.pg.json(consulta)
        salida = self.pg.sql(
            f"set role {self.rol}; select coalesce(json_agg(t),'[]'::json)::text from ({consulta}) t;")
        return json.loads(salida)

    def _insertar(self):
        columnas = ", ".join(self.fila)
        valores = ", ".join(
            _lit(json.dumps(v, ensure_ascii=False)) if isinstance(v, (dict, list)) else _lit(v)
            for v in self.fila.values())
        sentencia = (f"insert into public.{self.tabla} ({columnas}) values ({valores}) returning *")
        prefijo = f"set role {self.rol}; " if self.rol else ""
        salida = self.pg.sql(
            f"{prefijo}with t as ({sentencia}) select coalesce(json_agg(t),'[]'::json)::text from t;")
        return _Respuesta(json.loads(salida))

    def execute(self):
        if self.fila is not None:
            return self._insertar()
        where = " where " + " and ".join(self.filtros) if self.filtros else ""
        orden = " order by " + ", ".join(self.orden) if self.orden else ""
        limite = f" limit {self.limite}" if self.limite else ""
        desde = f" offset {self.desde}" if self.desde else ""
        filas = self._consulta(f"select {self.columnas} from public.{self.tabla}{where}{orden}{limite}{desde}")
        if self.unica:
            if len(filas) != 1:
                raise RuntimeError(f"single(): {len(filas)} filas")
            return _Respuesta(filas[0])
        return _Respuesta(filas)


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
    def __init__(self, pg: _Pg, *, vigilar_flags: bool = False, compat_16: bool = False,
                 rol_tablas: str | None = None):
        self.pg = pg
        # rol_tablas (2AX): lecturas/inserciones REST con ese rol (p. ej. service_role).
        self.rol_tablas = rol_tablas
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
        return _Tabla(self.pg, tabla, self.rol_tablas)

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
            elif isinstance(valor, (dict, list)):  # 2AZ: p_enriquecimiento y otros jsonb
                texto = _lit(json.dumps(valor, ensure_ascii=False, default=str)) + "::jsonb"
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

VARIANTES = ("16", "17", "16_rollback", "18", "17_rollback", "19", "20", "20_rollback", "21", "21_rollback", "22", "22_rollback",
             "23", "23_rollback", "24", "24_rollback", "25", "25_rollback", "26", "26_rollback", "27", "27_rollback", "28", "28_rollback", "29", "29_rollback")


def construir_plantilla(contenedor: str, variante: str) -> str:
    """16: cadena 2AN; 17: 16 + migracion 17 aplicada dos veces; 16_rollback: 16 + 17 + rollback.

    18: 17 + migracion 18 aplicada dos veces; 17_rollback: 17 + 18 + rollback de la 18.
    19 (2AZ): 18 + rollback de la 19 (matriz y privilegios por defecto productivos, 2AX) + 19.
    20: 19 + migracion 20 aplicada dos veces; 20_rollback: 20 + rollback de la 20.
    21 (2BA): 20 + migracion 21 aplicada dos veces; 21_rollback: 21 + rollback de la 21.
    22 (2BD): 21 + migracion 22 aplicada dos veces; 22_rollback: 22 + rollback de la 22.
    23 (2BF): 22 + migracion 23 aplicada dos veces; 23_rollback: 23 + rollback de la 23.
    24 (2BE): 23 + migracion 24 aplicada dos veces; 24_rollback: 24 + rollback de la 24.
    25 (2BI): 24 + migracion 25 aplicada dos veces; 25_rollback: 25 + rollback de la 25.
    26 (2BK): 25 + migracion 26 aplicada dos veces; 26_rollback: 26 + rollback de la 26.
    27 (2BL): 26 + migracion 27 aplicada dos veces; 27_rollback: 27 + rollback de la 27.
    28 (2BM): 27 + migracion 28 aplicada dos veces; 28_rollback: 28 + rollback de la 28.
    29 (2BN): 28 + migracion 29 aplicada dos veces; 29_rollback: 29 + rollback de la 29.
    Idempotente: si la plantilla ya existe en el contenedor, se reutiliza.
    """
    assert variante in VARIANTES
    existente = _Pg(contenedor, "postgres").sql(
        f"select count(*) from pg_database where datname = 'cf_plantilla_{variante}'")
    if existente == "1":
        return f"cf_plantilla_{variante}"
    if variante in ("19", "20", "20_rollback", "21", "21_rollback", "22", "22_rollback", "23", "23_rollback",
                    "24", "24_rollback", "25", "25_rollback", "26", "26_rollback", "27", "27_rollback", "28", "28_rollback", "29", "29_rollback"):
        nombre = f"cf_plantilla_{variante}"
        base = construir_plantilla(contenedor, {"19": "18", "20": "19", "20_rollback": "20",
                                                 "21": "20", "21_rollback": "21",
                                                 "22": "21", "22_rollback": "22",
                                                 "23": "22", "23_rollback": "23",
                                                 "24": "23", "24_rollback": "24",
                                                 "25": "24", "25_rollback": "25",
                                                 "26": "25", "26_rollback": "26",
                                                 "27": "26", "27_rollback": "27",
                                                 "28": "27", "28_rollback": "28",
                                                 "29": "28", "29_rollback": "29"}[variante])
        cerrar_sesiones(contenedor, base)  # createdb -T exige que nadie este conectado al origen
        _docker("exec", contenedor, "createdb", "-U", "postgres", "-T", base, nombre)
        pg = _Pg(contenedor, nombre)
        if variante == "19":
            pg.sql(ROLLBACK_19.read_text(encoding="utf-8"))
            pg.sql(MIGRACION_19.read_text(encoding="utf-8"))
        elif variante == "20":
            pg.sql(MIGRACION_20.read_text(encoding="utf-8"))
            pg.sql(MIGRACION_20.read_text(encoding="utf-8"))
        elif variante == "20_rollback":
            pg.sql(ROLLBACK_20.read_text(encoding="utf-8"))
        elif variante == "21":
            pg.sql(MIGRACION_21.read_text(encoding="utf-8"))
            pg.sql(MIGRACION_21.read_text(encoding="utf-8"))
        elif variante == "21_rollback":
            pg.sql(ROLLBACK_21.read_text(encoding="utf-8"))
        elif variante == "22":
            pg.sql(MIGRACION_22.read_text(encoding="utf-8"))
            pg.sql(MIGRACION_22.read_text(encoding="utf-8"))
        elif variante == "22_rollback":
            pg.sql(ROLLBACK_22.read_text(encoding="utf-8"))
        elif variante == "23":
            pg.sql(MIGRACION_23.read_text(encoding="utf-8"))
            pg.sql(MIGRACION_23.read_text(encoding="utf-8"))
        elif variante == "23_rollback":
            pg.sql(ROLLBACK_23.read_text(encoding="utf-8"))
        elif variante == "24":
            pg.sql(MIGRACION_24.read_text(encoding="utf-8"))
            pg.sql(MIGRACION_24.read_text(encoding="utf-8"))
        elif variante == "24_rollback":
            pg.sql(ROLLBACK_24.read_text(encoding="utf-8"))
        elif variante == "25":
            pg.sql(MIGRACION_25.read_text(encoding="utf-8"))
            pg.sql(MIGRACION_25.read_text(encoding="utf-8"))
        elif variante == "25_rollback":
            pg.sql(ROLLBACK_25.read_text(encoding="utf-8"))
        elif variante == "26":
            pg.sql(MIGRACION_26.read_text(encoding="utf-8"))
            pg.sql(MIGRACION_26.read_text(encoding="utf-8"))
        elif variante == "26_rollback":
            pg.sql(ROLLBACK_26.read_text(encoding="utf-8"))
        elif variante == "27":
            pg.sql(MIGRACION_27.read_text(encoding="utf-8"))
            pg.sql(MIGRACION_27.read_text(encoding="utf-8"))
        elif variante == "27_rollback":
            pg.sql(ROLLBACK_27.read_text(encoding="utf-8"))
        elif variante == "28":
            pg.sql(MIGRACION_28.read_text(encoding="utf-8"))
            pg.sql(MIGRACION_28.read_text(encoding="utf-8"))
        elif variante == "28_rollback":
            pg.sql(ROLLBACK_28.read_text(encoding="utf-8"))
        elif variante == "29":
            pg.sql(MIGRACION_29.read_text(encoding="utf-8"))
            pg.sql(MIGRACION_29.read_text(encoding="utf-8"))
        else:
            pg.sql(ROLLBACK_29.read_text(encoding="utf-8"))
        cerrar_sesiones(contenedor, nombre)
        return nombre
    assert variante in VARIANTES
    nombre = f"cf_plantilla_{variante}"
    _docker("exec", contenedor, "createdb", "-U", "postgres", nombre)
    pg = _Pg(contenedor, nombre)
    for path in CADENA:
        pg.sql(_expandir(path))
    if variante in ("17", "18", "17_rollback"):
        pg.sql(MIGRACION_17.read_text(encoding="utf-8"))
        pg.sql(MIGRACION_17.read_text(encoding="utf-8"))
    if variante == "18":
        pg.sql(MIGRACION_18.read_text(encoding="utf-8"))
        pg.sql(MIGRACION_18.read_text(encoding="utf-8"))
    elif variante == "17_rollback":
        pg.sql(MIGRACION_18.read_text(encoding="utf-8"))
        pg.sql(ROLLBACK_18.read_text(encoding="utf-8"))
    elif variante == "16_rollback":
        pg.sql(MIGRACION_17.read_text(encoding="utf-8"))
        pg.sql(ROLLBACK_17.read_text(encoding="utf-8"))
    cerrar_sesiones(contenedor, nombre)
    return nombre


def base_desde(contenedor: str, plantilla: str) -> _Pg:
    db = "cf_caso_" + uuid.uuid4().hex[:12]
    cerrar_sesiones(contenedor, plantilla)  # el origen puede ser otra base de test con sesion abierta
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
