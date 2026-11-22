"""Hito 38-B: importacion del Excel de cashflow de Pio a Supabase (pruebas/auditoria_h7/DISENO.md §2, §4 y §9;
decisiones de Pio C1-C8, E1-E7, propuestas de redondeo aprobadas y respuestas del 2026-11-22).

Uso (tarea de las 23:45 como Usuari con ``ejecutar_importacion_cashflow.bat``, o Pio a mano):
  python -m src.cashflow.importar_cashflow <NOCHE|MANUAL> <SIMULAR|REAL> [--aceptar-categorias-nuevas]

Una importacion:
  puertas (git en REAL, ninguna tarea en ejecucion, ninguna noche EN_CURSO, migracion 38, carpeta)
  -> seleccion del fichero (C1) -> copia estable fuera del repositorio (nunca se abre el original)
  -> mismo hash que la ultima importacion: SIN_CAMBIOS (C6) -> lectura y validacion del Excel (§2.2-§2.4)
  -> categorias nuevas (C5) -> SIMULAR: informe sin escribir nada / REAL: la RPC de la 38 y postcheck por fila.

- La unica escritura es la RPC ``cf_cashflow_registrar_importacion`` (migracion 38) con el cliente del sistema que usa
  la noche; nunca un INSERT directo. Las lecturas, en una sesion READ_ONLY. Farmatic no interviene.
- Un Excel no valido es ``ERROR``: en REAL se registra solo la cabecera (la vigente anterior se conserva), con un
  detalle de codigos y posiciones de celda, nunca conceptos ni categorias. Si la RPC rechaza un ``OK`` (vuelve a
  validarlo todo en la BD), se registra un ``ERROR`` aparte con su codigo.
- Sin fichero, con mas de uno o con una copia inestable no hay hash que registrar: solo informe (codigo 2).
- Categorias nuevas (C5; decision de Pio del 2026-11-22): una (cuenta, categoria) que no aparece en ninguna
  importacion OK anterior de esa cuenta (no solo en la vigente). Sin
  ``--aceptar-categorias-nuevas`` (solo en MANUAL) no se escribe nada (codigo 4): asi Pio puede aceptar ese mismo
  fichero, cuyo hash quedaria bloqueado si se registrara como ``ERROR``.
- Informe en ``C:\\ControlFarmacias\\cashflow\\informes\\<fecha>\\<hora>_<origen>_<modo>\\`` (informe.json,
  resumen.txt, SHA256SUMS.txt): recuentos, sumas de control, posiciones de celda y avisos de redondeo; nunca conceptos
  ni categorias.
Codigos de salida: 0 OK, SIN_CAMBIOS o simulacion OK; 2 ERROR; 3 PARADA; 4 categorias nuevas sin aceptar.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Callable, ContextManager

ROOT = Path(__file__).resolve().parents[2]
CARPETA_EXCEL = Path(r"C:\GoogleDrive\CASHFLOW")
DIRECTORIO_CASHFLOW = Path(r"C:\ControlFarmacias\cashflow")
PREFIJO_FICHERO = "CASHFLOW"
EXTENSION = ".xlsm"
ORIGENES = ("NOCHE", "MANUAL")
MODOS = ("SIMULAR", "REAL")
OPCION_ACEPTAR = "--aceptar-categorias-nuevas"
TAREA_CASHFLOW = "ControlFarmacias - Importar Cashflow"
RPC = "cf_cashflow_registrar_importacion"
TABLAS_CASHFLOW = ("cf_cashflow_cuentas", "cf_cashflow_importaciones", "cf_cashflow_importes", "cf_cashflow_saldos")
FIRMA_RPC = "public.cf_cashflow_registrar_importacion(jsonb,jsonb,jsonb)"
# La hoja de PIO lleva tilde (U+00CD): se compone con chr para que el fuente sea ASCII.
HOJAS = {"P" + chr(0xCD) + "O": "PIO", "RITA": "RITA", "SL": "SL"}
HOJA_SL = "SL"
HOJAS_PLANTILLA = re.compile(r"^Banco_\d+$")
ETIQUETAS_SALDO = {"saldo_inicial": "saldo inicial", "saldo_formulas": "saldo final segun formulas",
                   "saldo_bancos": "saldo final segun bancos"}
PRIMERA_COLUMNA_DECENA = 4
PRIMERA_FILA_DATOS = 4
CENTIMO = Decimal("0.01")
UMBRAL_REDONDEO = Decimal("0.000001")
MEDIO_CENTIMO = Decimal("0.005")

CODIGO_OK, CODIGO_ERROR, CODIGO_PARADA, CODIGO_CATEGORIAS = 0, 2, 3, 4

# Codigos con los que la RPC de la 38 rechaza una importacion (DISENO §9) y rechazos de los checks de la tabla.
CODIGOS_RPC = (
    "IMPORTACION_NO_VALIDA", "CLAVE_NO_ADMITIDA", "IMPORTES_O_SALDOS_NO_VALIDOS", "IMPORTE_INCOMPLETO",
    "SALDO_INCOMPLETO", "HASH_YA_IMPORTADO", "ERROR_CON_DATOS", "FILAS_NO_COINCIDEN", "IMPORTACION_OK_VACIA",
    "CUENTA_DESCONOCIDA", "DECENA_NO_VALIDA", "CATEGORIA_SIN_PREFIJO", "IMPORTE_CERO",
    "IMPORTE_CON_MAS_DE_2_DECIMALES", "SALDO_CON_MAS_DE_2_DECIMALES", "SALDO_REPETIDO", "IMPORTES_SIN_SALDO",
    "CUADRE_NO_VALIDO")


class ErrorExcel(Exception):
    """El Excel no es valido: la importacion es ERROR. El mensaje es un codigo con posiciones, sin contenido."""


# --------------------------------------------------------------------------- entorno inyectable


@dataclass(slots=True)
class Entorno:
    abrir_lectura: Callable[[], ContextManager[Any]]
    cliente: Any
    tareas: Callable[[], dict]
    puerta_git: Callable[[], tuple]
    carpeta_excel: Path = CARPETA_EXCEL
    directorio: Path = DIRECTORIO_CASHFLOW
    reloj: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc)


@dataclass(slots=True)
class Lectura:
    importes: list[dict] = field(default_factory=list)
    saldos: list[dict] = field(default_factory=list)
    por_cuenta: dict = field(default_factory=dict)
    avisos_redondeo: list[dict] = field(default_factory=list)
    celdas_texto_vacias: list[str] = field(default_factory=list)
    decenas_sin_saldo_e5: list[str] = field(default_factory=list)
    hojas_ignoradas: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- lectura del Excel


def _norm(texto) -> str:
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return " ".join(t.split())


def _es_numero(v) -> bool:
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


def _decimal(v) -> Decimal:
    return Decimal(repr(v)) if isinstance(v, float) else Decimal(v)


def _centimos(d: Decimal) -> tuple[Decimal, bool]:
    """(valor al centimo half-up, si se ha redondeado de verdad: mas de 2 decimales significativos, E3)."""
    redondeado = d.quantize(CENTIMO, rounding=ROUND_HALF_UP)
    return redondeado, abs(d - redondeado) > UMBRAL_REDONDEO


def _letra(columna: int) -> str:
    from openpyxl.utils import get_column_letter

    return get_column_letter(columna)


def _decena_valida(inicio: dt.date, fin: dt.date) -> bool:
    if inicio.day in (1, 11):
        return fin == inicio + dt.timedelta(days=9)
    if inicio.day == 21:
        siguiente = (inicio.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        return fin == siguiente - dt.timedelta(days=1)
    return False


class _Hoja:
    """Valores guardados y celdas con formula de una hoja (dos cargas del libro: con y sin data_only)."""

    def __init__(self, nombre: str, ws_valores, ws_formulas) -> None:
        self.nombre = nombre
        self.valores = {(c.row, c.column): c.value for fila in ws_valores.iter_rows() for c in fila
                        if c.value is not None}
        self.formulas = {(c.row, c.column) for fila in ws_formulas.iter_rows() for c in fila if c.data_type == "f"}
        self.max_fila = max([ws_valores.max_row, ws_formulas.max_row])
        self.max_columna = max([ws_valores.max_column, ws_formulas.max_column])

    def celda(self, fila: int, columna: int) -> str:
        return f"{self.nombre}:{_letra(columna)}{fila}"

    def formulas_sin_valor(self) -> list[tuple[int, int]]:
        return sorted(k for k in self.formulas if self.valores.get(k) is None)

    def decenas(self) -> list[tuple[int, dt.date, dt.date]]:
        """Columnas de decena desde la D: filas 2 (inicio) y 3 (fin) con fecha; se saltan las TOTAL y las vacias."""
        out = []
        for col in range(PRIMERA_COLUMNA_DECENA, self.max_columna + 1):
            cabecera = [self.valores.get((r, col)) for r in (1, 2, 3)]
            if any(isinstance(v, str) and _norm(v).startswith("total") for v in cabecera):
                continue
            inicio, fin = cabecera[1], cabecera[2]
            if inicio is None and fin is None:
                continue
            if not (isinstance(inicio, dt.datetime) and isinstance(fin, dt.datetime)):
                raise ErrorExcel(f"ENCABEZADO_NO_FECHA:{self.nombre}:{_letra(col)}")
            out.append((col, inicio.date(), fin.date()))
        if not out:
            raise ErrorExcel(f"SIN_DECENAS:{self.nombre}")
        for (c1, _, f1), (c2, i2, _) in zip(out, out[1:]):
            if i2 != f1 + dt.timedelta(days=1):
                raise ErrorExcel(f"DECENAS_NO_CONSECUTIVAS:{self.nombre}:{_letra(c1)}:{_letra(c2)}")
        for col, inicio, fin in out:
            if not _decena_valida(inicio, fin):
                raise ErrorExcel(f"DECENA_NO_VALIDA:{self.nombre}:{_letra(col)}")
        return out


def _valor_importe(hoja: _Hoja, fila: int, col: int, lectura: Lectura):
    """Decimal sin redondear, o None si la celda cuenta como vacia (vacia, 0, texto de formula o solo espacios, E2)."""
    v = hoja.valores.get((fila, col))
    if v is None:
        return None
    if isinstance(v, str):
        if (fila, col) in hoja.formulas or not v.strip():
            lectura.celdas_texto_vacias.append(hoja.celda(fila, col))
            return None
        raise ErrorExcel(f"TEXTO_EN_IMPORTE:{hoja.celda(fila, col)}")
    if not _es_numero(v):
        raise ErrorExcel(f"TIPO_NO_ADMITIDO:{hoja.celda(fila, col)}")
    d = _decimal(v)
    return None if d == 0 else d


def _valor_saldo(hoja: _Hoja, fila: int, col: int):
    """Decimal sin redondear o None (vacia, texto de formula o solo espacios); otro texto es ERROR."""
    v = hoja.valores.get((fila, col))
    if v is None:
        return None
    if isinstance(v, str):
        if (fila, col) in hoja.formulas or not v.strip():
            return None
        raise ErrorExcel(f"TEXTO_EN_SALDO:{hoja.celda(fila, col)}")
    if not _es_numero(v):
        raise ErrorExcel(f"TIPO_NO_ADMITIDO:{hoja.celda(fila, col)}")
    return _decimal(v)


def _comprobar_plantilla(hoja: _Hoja) -> None:
    """E4: una hoja ignorada (Banco_N) con algun importe distinto de 0 en una fila de categoria es ERROR."""
    try:
        decenas = hoja.decenas()
    except ErrorExcel:
        decenas = [(c, None, None) for c in range(PRIMERA_COLUMNA_DECENA, hoja.max_columna + 1)]
    for fila in range(PRIMERA_FILA_DATOS, hoja.max_fila + 1):
        a = hoja.valores.get((fila, 1))
        if a is None or not str(a).strip():
            continue
        for col, _, _ in decenas:
            if (fila, col) in hoja.formulas and hoja.valores.get((fila, col)) is None:
                raise ErrorExcel(f"HOJA_IGNORADA_CON_FORMULA_SIN_VALOR:{hoja.celda(fila, col)}")
            v = hoja.valores.get((fila, col))
            if _es_numero(v) and v != 0:
                raise ErrorExcel(f"HOJA_IGNORADA_CON_IMPORTES:{hoja.nombre}")


def _leer_hoja(hoja: _Hoja, cuenta: str, lectura: Lectura) -> None:
    sin_valor = hoja.formulas_sin_valor()
    if sin_valor:
        raise ErrorExcel(f"FORMULA_SIN_VALOR:{hoja.celda(*sin_valor[0])}:{len(sin_valor)}")
    decenas = hoja.decenas()
    filas_saldo: dict[str, list[int]] = {k: [] for k in ETIQUETAS_SALDO}
    netos_crudos: dict[int, Decimal] = {}
    netos: dict[int, Decimal] = {}
    redondeados: dict[int, int] = {}
    con_importes: set[int] = set()
    resumen = {"decenas": len(decenas), "filas": 0, "entradas": 0, "salidas": 0, "suma_control": Decimal(0),
               "decenas_cuadran": 0, "decenas_sin_saldo_bancos": 0}
    for fila in range(PRIMERA_FILA_DATOS, hoja.max_fila + 1):
        a, b = hoja.valores.get((fila, 1)), hoja.valores.get((fila, 2))
        if a is not None and str(a).strip():
            categoria = str(a).strip()
            if not (categoria.startswith("RE ") or categoria.startswith("RS ")):
                raise ErrorExcel(f"CATEGORIA_SIN_PREFIJO:{hoja.celda(fila, 1)}")
            entrada = categoria.startswith("RE ")
            for col, inicio, fin in decenas:
                crudo = _valor_importe(hoja, fila, col, lectura)
                if crudo is None:
                    continue
                importe, redondeado = _centimos(crudo)
                if importe == 0:
                    raise ErrorExcel(f"IMPORTE_CERO_TRAS_REDONDEO:{hoja.celda(fila, col)}")
                if redondeado:
                    lectura.avisos_redondeo.append({"celda": hoja.celda(fila, col), "original": str(crudo),
                                                    "redondeado": str(importe)})
                    redondeados[col] = redondeados.get(col, 0) + 1
                fila_importe = {"cuenta": cuenta, "decena_inicio": inicio.isoformat(),
                                "decena_fin": fin.isoformat(), "categoria": categoria,
                                "concepto": None if b is None else str(b).strip(), "importe": str(importe),
                                "fila_excel": fila}
                if redondeado:
                    fila_importe["redondeado"] = True
                lectura.importes.append(fila_importe)
                signo = 1 if entrada else -1
                netos_crudos[col] = netos_crudos.get(col, Decimal(0)) + signo * crudo
                netos[col] = netos.get(col, Decimal(0)) + signo * importe
                con_importes.add(col)
                resumen["filas"] += 1
                resumen["entradas" if entrada else "salidas"] += 1
                resumen["suma_control"] += importe
            continue
        if b is not None:
            etiqueta = _norm(b)
            for clave, texto in ETIQUETAS_SALDO.items():
                if etiqueta == texto:
                    filas_saldo[clave].append(fila)
                    break
            else:
                _sin_categoria(hoja, fila, decenas)
        else:
            _sin_categoria(hoja, fila, decenas)
    for clave, filas in filas_saldo.items():
        if not filas:
            raise ErrorExcel(f"FILA_SALDO_AUSENTE:{hoja.nombre}:{clave}")
        if len(filas) > 1:
            raise ErrorExcel(f"FILA_SALDO_REPETIDA:{hoja.nombre}:{clave}")
    fi, ff, fb = (filas_saldo[k][0] for k in ("saldo_inicial", "saldo_formulas", "saldo_bancos"))
    primera = decenas[0][0]
    for col, inicio, _ in decenas:
        si, sf, sb = _valor_saldo(hoja, fi, col), _valor_saldo(hoja, ff, col), _valor_saldo(hoja, fb, col)
        if si is None or sf is None:
            # E5: SL sin saldo en la primera decena, aceptado si esa decena no tiene importes.
            if hoja.nombre == HOJA_SL and col == primera and col not in con_importes:
                lectura.decenas_sin_saldo_e5.append(f"{hoja.nombre}:{_letra(col)}")
                continue
            raise ErrorExcel(f"SALDO_AUSENTE:{hoja.celda(fi if si is None else ff, col)}")
        # E1, con los valores guardados sin redondear (E3): saldo inicial + RE - RS = saldo segun formulas.
        if abs(si + netos_crudos.get(col, Decimal(0)) - sf) >= MEDIO_CENTIMO:
            raise ErrorExcel(f"CUADRE_NO_VALIDO:{hoja.nombre}:{_letra(col)}")
        saldo = {"cuenta": cuenta, "decena_inicio": inicio.isoformat()}
        valores_redondeados = {}
        for clave, crudo, fila in (("saldo_inicial", si, fi), ("saldo_formulas", sf, ff), ("saldo_bancos", sb, fb)):
            if crudo is None:
                saldo[clave] = None
                continue
            valor, redondeado = _centimos(crudo)
            if redondeado:
                lectura.avisos_redondeo.append({"celda": hoja.celda(fila, col), "original": str(crudo),
                                                "redondeado": str(valor)})
            saldo[clave] = str(valor)
            valores_redondeados[clave] = valor
        # Cuadre de la RPC con los valores ya redondeados: 0,005 por importe redondeado y ninguno por saldo.
        diferencia = (valores_redondeados["saldo_inicial"] + netos.get(col, Decimal(0))
                      - valores_redondeados["saldo_formulas"])
        if abs(diferencia) > MEDIO_CENTIMO * redondeados.get(col, 0):
            raise ErrorExcel(f"CUADRE_REDONDEADO_NO_VALIDO:{hoja.nombre}:{_letra(col)}")
        lectura.saldos.append(saldo)
        resumen["decenas_cuadran"] += 1
        if sb is None:
            resumen["decenas_sin_saldo_bancos"] += 1
    resumen["suma_control"] = str(resumen["suma_control"])
    lectura.por_cuenta[cuenta] = resumen


def _sin_categoria(hoja: _Hoja, fila: int, decenas) -> None:
    """Filas sin categoria (totales, cuadre): solo formulas. Un importe tecleado sin categoria es ERROR (§2.4)."""
    for col, _, _ in decenas:
        v = hoja.valores.get((fila, col))
        if _es_numero(v) and v != 0 and (fila, col) not in hoja.formulas:
            raise ErrorExcel(f"IMPORTE_SIN_CATEGORIA:{hoja.celda(fila, col)}")


def leer_excel(ruta: Path) -> Lectura:
    """Lee y valida la copia del Excel (sin macros: openpyxl no las ejecuta, keep_vba=False). ErrorExcel si no vale."""
    import openpyxl

    try:
        libro_v = openpyxl.load_workbook(ruta, data_only=True, keep_vba=False)
        libro_f = openpyxl.load_workbook(ruta, data_only=False, keep_vba=False)
    except Exception as exc:  # noqa: BLE001 - un fichero ilegible es ERROR
        raise ErrorExcel(f"EXCEL_ILEGIBLE:{type(exc).__name__}") from exc
    try:
        lectura = Lectura()
        nombres = {unicodedata.normalize("NFC", n): n for n in libro_v.sheetnames}
        for esperada, cuenta in HOJAS.items():
            real = nombres.get(unicodedata.normalize("NFC", esperada))
            if real is None:
                raise ErrorExcel(f"HOJA_AUSENTE:{esperada}")
            _leer_hoja(_Hoja(esperada, libro_v[real], libro_f[real]), cuenta, lectura)
        for nombre in libro_v.sheetnames:
            if HOJAS_PLANTILLA.match(nombre):
                _comprobar_plantilla(_Hoja(nombre, libro_v[nombre], libro_f[nombre]))
            if unicodedata.normalize("NFC", nombre) not in {unicodedata.normalize("NFC", h) for h in HOJAS}:
                lectura.hojas_ignoradas.append(nombre)
        if not lectura.importes or not lectura.saldos:
            raise ErrorExcel("IMPORTACION_VACIA")
        return lectura
    finally:
        libro_v.close()
        libro_f.close()


# --------------------------------------------------------------------------- fichero y copia


def seleccionar_fichero(carpeta: Path) -> Path:
    """C1: el unico .xlsm de la carpeta cuyo nombre empieza por CASHFLOW, sin contar los temporales ~$."""
    candidatos = sorted(p for p in carpeta.iterdir() if p.is_file() and p.suffix.lower() == EXTENSION
                        and p.name.upper().startswith(PREFIJO_FICHERO) and not p.name.startswith("~$"))
    if not candidatos:
        raise ErrorExcel("EXCEL_NO_ENCONTRADO")
    if len(candidatos) > 1:
        raise ErrorExcel(f"EXCEL_AMBIGUO:{len(candidatos)}")
    return candidatos[0]


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def copiar_estable(original: Path, copias: Path, fecha: dt.date) -> tuple[Path, str]:
    """Copia el original (nunca se abre en Excel ni se escribe) y exige el mismo SHA-256 antes, despues y en la copia."""
    try:
        antes = _sha256(original)
        copias.mkdir(parents=True, exist_ok=True)
        destino = copias / f"{fecha.isoformat()}_{antes[:8]}{EXTENSION}"
        shutil.copyfile(original, destino)
        despues, copia = _sha256(original), _sha256(destino)
    except OSError as exc:
        raise ErrorExcel(f"COPIA_FALLIDA:{type(exc).__name__}") from exc
    if not antes == despues == copia:
        raise ErrorExcel("COPIA_NO_ESTABLE")
    return destino, copia


# --------------------------------------------------------------------------- lecturas en la BD (READ_ONLY)


def _lecturas_previas(lector) -> dict:
    out = {"migracion_38": all(lector.valor("select to_regclass(%s) is not null", (f"public.{t}",))
                               for t in TABLAS_CASHFLOW)
           and lector.valor("select to_regprocedure(%s) is not null", (FIRMA_RPC,)),
           "noches_en_curso": lector.valor("select count(*) from public.cf_noches_automaticas "
                                           "where resultado = 'EN_CURSO'")}
    if not out["migracion_38"]:
        return out
    ultima = lector.filas("select archivo_hash from public.cf_cashflow_importaciones "
                          "order by importado_at desc, id desc limit 1")
    out["ultimo_hash"] = ultima[0][0] if ultima else None
    out["hashes"] = {r[0] for r in lector.filas("select archivo_hash from public.cf_cashflow_importaciones")}
    # C5 (decision de Pio, 2026-11-22): conocidas = las de cualquier importacion OK anterior, por cuenta.
    out["categorias_conocidas"] = {(r[0], r[1]) for r in lector.filas(
        "select distinct i.cuenta, i.categoria from public.cf_cashflow_importes i "
        "join public.cf_cashflow_importaciones m on m.id = i.importacion_id where m.estado = 'OK'")}
    out["hay_vigente"] = lector.valor("select count(*) from public.cf_cashflow_importaciones where vigente") == 1
    return out


def snapshot_cashflow(lector) -> dict:
    """Huella por fila de las tablas de Cashflow, con la importacion duena de cada importe y saldo."""
    return {
        "cuentas": dict(lector.filas("select codigo, md5(to_jsonb(t)::text) from public.cf_cashflow_cuentas t")),
        "importaciones": {r[0]: [r[1], r[2]] for r in lector.filas(
            "select id::text, md5(to_jsonb(t)::text), vigente from public.cf_cashflow_importaciones t")},
        "importes": {str(r[0]): [r[1], r[2]] for r in lector.filas(
            "select id, md5(to_jsonb(t)::text), importacion_id::text from public.cf_cashflow_importes t")},
        "saldos": {str(r[0]): [r[1], r[2]] for r in lector.filas(
            "select id, md5(to_jsonb(t)::text), importacion_id::text from public.cf_cashflow_saldos t")},
    }


def postcheck_cashflow(pre: dict, post: dict, nueva: str | None, anterior: str | None,
                       importes: int, saldos: int) -> list[str]:
    """Solo cambian las filas de esta importacion: la cabecera nueva, sus importes y saldos y el vigente de la
    anterior (que pasa a false). Devuelve la lista de problemas (vacia si todo cuadra)."""
    problemas = []
    if pre["cuentas"] != post["cuentas"]:
        problemas.append("CUENTAS_CAMBIADAS")
    a, b = pre["importaciones"], post["importaciones"]
    if set(a) - set(b):
        problemas.append("IMPORTACIONES_DESAPARECIDAS")
    nuevas = set(b) - set(a)
    if nuevas != ({nueva} if nueva else set()):
        problemas.append(f"IMPORTACIONES_NUEVAS_INESPERADAS:{len(nuevas)}")
    for clave in set(a) & set(b):
        if a[clave] != b[clave] and not (clave == anterior and a[clave][1] is True and b[clave][1] is False):
            problemas.append(f"IMPORTACION_CAMBIADA:{clave}")
    for tabla, esperadas in (("importes", importes), ("saldos", saldos)):
        a, b = pre[tabla], post[tabla]
        if any(a[k] != b.get(k) for k in a):
            problemas.append(f"{tabla.upper()}_CAMBIADOS_O_DESAPARECIDOS")
        nuevas_filas = [b[k] for k in set(b) - set(a)]
        if any(f[1] != nueva for f in nuevas_filas) or len(nuevas_filas) != esperadas:
            problemas.append(f"{tabla.upper()}_NUEVOS_INESPERADOS:{len(nuevas_filas)}")
    return problemas


# --------------------------------------------------------------------------- RPC


def _codigo_rechazo(exc: Exception) -> str | None:
    """Codigo de rechazo de la RPC o de un check de la tabla (la transaccion se deshizo entera); None si no se sabe
    que paso (por ejemplo, un corte de red: el resultado es incierto)."""
    texto = str(exc)
    for token in re.findall(r"[A-Z][A-Z0-9_]+(?::[a-z]+)?", texto):
        if token.split(":", 1)[0] in CODIGOS_RPC:
            return token
    if "violates check constraint" in texto:
        return "RESTRICCION_DE_TABLA"
    return None


def _llamar_rpc(cliente, cabecera: dict, importes: list[dict], saldos: list[dict]) -> dict:
    return cliente.rpc(RPC, {"p_importacion": cabecera, "p_importes": importes, "p_saldos": saldos}).execute().data


# --------------------------------------------------------------------------- importacion


def _puertas(entorno: Entorno, origen: str, modo: str, previas: dict) -> list[str]:
    fallos = []
    if modo == "REAL":
        resultado_git = entorno.puerta_git()
        fallos += list(resultado_git[1])
    info = entorno.tareas()
    if "error" in info:
        fallos.append("TAREAS_NO_DETERMINABLES")
    else:
        for tarea in info.get("tareas", []):
            if tarea.get("estado") == "Running" and not (origen == "NOCHE" and tarea.get("nombre") == TAREA_CASHFLOW):
                fallos.append(f"TAREA_EN_EJECUCION:{tarea.get('nombre')}")
    if previas.get("noches_en_curso"):
        fallos.append(f"NOCHE_EN_CURSO:{previas['noches_en_curso']}")
    if not previas.get("migracion_38"):
        fallos.append("MIGRACION_38_AUSENTE")
    if not Path(entorno.carpeta_excel).is_dir():
        fallos.append("CARPETA_EXCEL_NO_EXISTE")
    return fallos


def importar(origen: str, modo: str, aceptar_categorias_nuevas: bool, entorno: Entorno) -> tuple[int, dict]:
    if origen not in ORIGENES or modo not in MODOS:
        raise ValueError(f"ARGUMENTOS_NO_ADMITIDOS:{origen}:{modo}")
    if aceptar_categorias_nuevas and origen != "MANUAL":
        raise ValueError("ACEPTAR_CATEGORIAS_SOLO_EN_MANUAL")
    inicio = entorno.reloj()
    informe: dict = {"origen": origen, "modo": modo, "aceptar_categorias_nuevas": aceptar_categorias_nuevas,
                     "inicio": inicio.isoformat(), "registrado": False}
    codigo = _importar(origen, modo, aceptar_categorias_nuevas, entorno, informe)
    informe["fin"] = entorno.reloj().isoformat()
    informe["codigo_salida"] = codigo
    informe["informe_sha256"] = _escribir_informe(entorno, informe, inicio)
    return codigo, informe


def _importar(origen: str, modo: str, aceptar: bool, entorno: Entorno, informe: dict) -> int:
    with entorno.abrir_lectura() as lector:
        previas = _lecturas_previas(lector)
    informe["puertas"] = _puertas(entorno, origen, modo, previas)
    if informe["puertas"]:
        informe["resultado"] = "PARADA"
        informe["motivo"] = "PUERTAS"
        return CODIGO_PARADA
    try:
        original = seleccionar_fichero(Path(entorno.carpeta_excel))
        informe["archivo_nombre"] = original.name
        copia, sha = copiar_estable(original, Path(entorno.directorio) / "copias",
                                    entorno.reloj().astimezone().date())
    except ErrorExcel as exc:
        informe["resultado"], informe["detalle_error"] = "ERROR", str(exc)
        return CODIGO_ERROR
    informe["archivo_hash"], informe["copia"] = sha, str(copia)
    if sha == previas["ultimo_hash"]:
        informe["resultado"] = "SIN_CAMBIOS"
        return CODIGO_OK
    if sha in previas["hashes"]:
        informe["resultado"], informe["motivo"] = "PARADA", "HASH_DE_UNA_IMPORTACION_ANTERIOR"
        return CODIGO_PARADA

    cabecera = {"archivo_nombre": original.name, "archivo_hash": sha, "origen": origen}
    try:
        lectura = leer_excel(copia)
    except ErrorExcel as exc:
        return _registrar_error(entorno, modo, cabecera, str(exc), informe)
    informe["lectura"] = {
        "por_cuenta": lectura.por_cuenta, "importes": len(lectura.importes), "saldos": len(lectura.saldos),
        "avisos_redondeo": lectura.avisos_redondeo,
        "celdas_texto_vacias": {"n": len(lectura.celdas_texto_vacias), "posiciones": lectura.celdas_texto_vacias},
        "decenas_sin_saldo_e5": lectura.decenas_sin_saldo_e5, "hojas_ignoradas": len(lectura.hojas_ignoradas)}
    nuevas = {(f["cuenta"], f["categoria"]) for f in lectura.importes} - previas["categorias_conocidas"]
    informe["categorias_nuevas"] = len(nuevas)
    informe["hay_vigente"] = previas["hay_vigente"]
    if nuevas and not aceptar:
        informe["resultado"] = "CATEGORIAS_NUEVAS_SIN_ACEPTAR"
        return CODIGO_CATEGORIAS
    if modo == "SIMULAR":
        informe["resultado"] = "SIMULADO_OK"
        return CODIGO_OK
    return _registrar_ok(entorno, cabecera, lectura, informe)


def _registrar_error(entorno: Entorno, modo: str, cabecera: dict, detalle: str, informe: dict) -> int:
    informe["detalle_error"] = detalle
    if modo == "SIMULAR":
        informe["resultado"] = "SIMULADO_ERROR"
        return CODIGO_ERROR
    return _escribir(entorno, {**cabecera, "estado": "ERROR", "detalle_error": detalle, "filas": 0}, [], [],
                     informe, "ERROR")


def _registrar_ok(entorno: Entorno, cabecera: dict, lectura: Lectura, informe: dict) -> int:
    return _escribir(entorno, {**cabecera, "estado": "OK", "detalle_error": None, "filas": len(lectura.importes)},
                     lectura.importes, lectura.saldos, informe, "OK")


def _escribir(entorno: Entorno, cabecera: dict, importes: list, saldos: list, informe: dict, estado: str) -> int:
    """Una llamada a la RPC entre dos snapshots READ_ONLY; si rechaza un OK, un ERROR aparte con su codigo."""
    from src.facturas.runtime_supabase.noche_automatica import snapshot_por_fila

    with entorno.abrir_lectura() as lector:
        pre_resto, pre = snapshot_por_fila(lector), snapshot_cashflow(lector)
    respuesta = None
    try:
        respuesta = _llamar_rpc(entorno.cliente, cabecera, importes, saldos)
    except Exception as exc:  # noqa: BLE001
        rechazo = _codigo_rechazo(exc)
        if rechazo is None:
            informe["resultado"], informe["motivo"] = "PARADA", f"RPC_RESULTADO_INCIERTO:{type(exc).__name__}"
        elif estado == "OK":
            informe["rechazo_rpc"] = rechazo
            detalle = f"RPC_RECHAZO:{rechazo}"
            informe["detalle_error"] = detalle
            try:
                respuesta = _llamar_rpc(entorno.cliente, {**cabecera, "estado": "ERROR", "detalle_error": detalle,
                                                          "filas": 0}, [], [])
                estado = "ERROR"
            except Exception as exc2:  # noqa: BLE001
                informe["resultado"] = "PARADA"
                informe["motivo"] = f"ERROR_NO_REGISTRADO:{_codigo_rechazo(exc2) or type(exc2).__name__}"
        else:
            informe["resultado"], informe["motivo"] = "PARADA", f"ERROR_NO_REGISTRADO:{rechazo}"
    if respuesta is not None:
        informe["registrado"] = True
        informe["respuesta_rpc"] = respuesta
        informe["resultado"] = estado
    with entorno.abrir_lectura() as lector:
        post_resto, post = snapshot_por_fila(lector), snapshot_cashflow(lector)
    nueva = (respuesta or {}).get("importacion_id")
    problemas = postcheck_cashflow(pre, post, nueva, (respuesta or {}).get("anterior"),
                                   (respuesta or {}).get("importes", 0), (respuesta or {}).get("saldos", 0))
    ajenas = sorted(t for t in set(pre_resto) | set(post_resto) if pre_resto.get(t) != post_resto.get(t))
    if ajenas:
        problemas.append("FILAS_AJENAS:" + ",".join(ajenas))
    informe["postcheck"] = {"veredicto": "POSTCHECK_OK" if not problemas else "POSTCHECK_FALLIDO",
                            "problemas": problemas}
    if problemas or informe["resultado"] == "PARADA":
        if problemas:
            informe["resultado"] = "PARADA"
            informe["motivo"] = ";".join(filter(None, [informe.get("motivo"), "POSTCHECK_FALLIDO"]))
        return CODIGO_PARADA
    return CODIGO_OK if estado == "OK" else CODIGO_ERROR


# --------------------------------------------------------------------------- informe


def _escribir_informe(entorno: Entorno, informe: dict, inicio: dt.datetime) -> str:
    local = inicio.astimezone()
    carpeta = (Path(entorno.directorio) / "informes" / local.date().isoformat()
               / f"{local.strftime('%H%M%S')}{local.microsecond // 1000:03d}_{informe['origen']}_{informe['modo']}")
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / "informe.json"
    ruta.write_text(json.dumps(informe, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    lectura = informe.get("lectura") or {}
    resumen = [
        f"Cashflow {informe['origen']} {informe['modo']}: {informe.get('resultado')}"
        + (f" - {informe['motivo']}" if informe.get("motivo") else ""),
        f"Fichero: {informe.get('archivo_nombre', '-')} ({(informe.get('archivo_hash') or '-')[:12]})",
        f"Detalle: {informe.get('detalle_error') or '-'}",
        f"Importes: {lectura.get('importes', 0)}; saldos: {lectura.get('saldos', 0)}; "
        f"avisos de redondeo: {len(lectura.get('avisos_redondeo', []))}; "
        f"categorias nuevas: {informe.get('categorias_nuevas', '-')}",
        f"Registrado: {informe.get('registrado')}; postcheck: "
        f"{(informe.get('postcheck') or {}).get('veredicto', 'NO_EJECUTADO')}",
    ]
    (carpeta / "resumen.txt").write_text("\n".join(resumen) + "\n", encoding="utf-8")
    sha = _sha256(ruta)
    sumas = [f"{_sha256(carpeta / n)} *{n}" for n in ("informe.json", "resumen.txt")]
    (carpeta / "SHA256SUMS.txt").write_text("\n".join(sumas) + "\n", encoding="utf-8")
    return sha


# --------------------------------------------------------------------------- produccion


def _tareas_productivas() -> dict:
    """Estado de las tareas de ControlFarmacias, solo lectura (Get-ScheduledTask)."""
    ps = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8;"
          "$t = @(Get-ScheduledTask -TaskName '*ControlFarmacias*' -ErrorAction Stop | ForEach-Object {"
          " [pscustomobject]@{ nombre = $_.TaskName; estado = [string]$_.State } });"
          "ConvertTo-Json -InputObject $t -Depth 3")
    codificado = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", codificado],
                           capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": type(exc).__name__}
    if r.returncode:
        return {"error": r.stderr.decode("utf-8", "replace").strip()[:500]}
    tareas = json.loads(r.stdout.decode("utf-8-sig") or "[]")
    return {"tareas": tareas if isinstance(tareas, list) else [tareas]}


def main(argv: list[str]) -> int:
    opciones = [a for a in argv if a.startswith("--")]
    posicionales = [a for a in argv if not a.startswith("--")]
    if (len(posicionales) != 2 or posicionales[0] not in ORIGENES or posicionales[1] not in MODOS
            or set(opciones) - {OPCION_ACEPTAR}
            or (OPCION_ACEPTAR in opciones and posicionales[0] != "MANUAL")):
        raise SystemExit("uso: python -m src.cashflow.importar_cashflow <NOCHE|MANUAL> <SIMULAR|REAL> "
                         f"[{OPCION_ACEPTAR} (solo MANUAL)]")
    if DIRECTORIO_CASHFLOW == ROOT or ROOT in DIRECTORIO_CASHFLOW.parents:
        raise SystemExit("DIRECTORIO_DENTRO_DEL_REPOSITORIO")
    from src.facturas.runtime_supabase import noche_automatica as na
    from src.facturas.runtime_supabase.lectura_readonly import sesion_lectura

    conexion = na._conexion_lectura_productiva()
    try:
        # SIMULAR no escribe en la BD: no necesita el cliente del sistema.
        cliente = na._cliente_productivo() if posicionales[1] == "REAL" else None
        entorno = Entorno(abrir_lectura=lambda: sesion_lectura(conexion), cliente=cliente,
                          tareas=_tareas_productivas, puerta_git=na.puerta_git)
        codigo, informe = importar(posicionales[0], posicionales[1], OPCION_ACEPTAR in opciones, entorno)
    finally:
        conexion.close()
    print(json.dumps({k: informe.get(k) for k in ("resultado", "motivo", "detalle_error", "registrado",
                                                  "categorias_nuevas", "informe_sha256")}, ensure_ascii=False))
    return codigo


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
