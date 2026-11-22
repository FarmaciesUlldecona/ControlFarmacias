"""Hito 38-B: lectura y validacion del Excel de cashflow, sin base de datos (DISENO §2, §4 y §7.3).

Excel FICTICIO generado en el test (``excel_cashflow_ficticio``), ningun dato real. Casos de §7.3: estructura
cambiada, formula sin valor, cuadre roto, cuadre con RS positivos y negativos, signo, decenas, texto de formula y solo
espacios como vacio, otro texto como ERROR, redondeo half-up con aviso (importes y saldos), hoja de plantilla sin
importes y con importes, SL sin saldo en la primera decena (E5) y saldo de bancos distinto (E7). Ademas: seleccion del
fichero (C1), copia estable, codigos de rechazo de la RPC, postcheck de Cashflow, argumentos y fuente.
"""
from __future__ import annotations

import ast
import inspect
from decimal import Decimal

import pytest

import excel_cashflow_ficticio as ef
from excel_cashflow_ficticio import HOJA_PIO
from src.cashflow import importar_cashflow as ic


def _leer(tmp_path, cambiar=None):
    return ic.leer_excel(ef.excel(tmp_path, cambiar=cambiar))


def _error(tmp_path, cambiar) -> str:
    with pytest.raises(ic.ErrorExcel) as exc:
        _leer(tmp_path, cambiar)
    return str(exc.value)


# --------------------------------------------------------------------------- lectura valida


def test_libro_base_importes_saldos_signo_y_e5_e7(tmp_path):
    lectura = _leer(tmp_path)
    assert (len(lectura.importes), len(lectura.saldos)) == (7, 11)
    pio = [(f["decena_inicio"], f["fila_excel"], f["importe"]) for f in lectura.importes if f["cuenta"] == "PIO"]
    # El importe conserva el signo de la celda (E1): el RS de -50 se guarda negativo.
    assert sorted(pio) == [("2026-01-01", 5, "1000.00"), ("2026-01-01", 6, "300.00"), ("2026-01-01", 7, "-50.00"),
                           ("2026-01-11", 5, "200.10"), ("2026-02-01", 6, "100.00")]
    assert {f["decena_fin"] for f in lectura.importes if f["decena_inicio"] == "2026-01-01"} == {"2026-01-10"}
    assert not any("redondeado" in f for f in lectura.importes)
    assert lectura.decenas_sin_saldo_e5 == ["SL:D"]
    assert [s["decena_inicio"] for s in lectura.saldos if s["cuenta"] == "SL"] == [
        "2026-01-11", "2026-01-21", "2026-02-01"]
    # E7: saldo de bancos distinto del de formulas o vacio, nunca ERROR.
    rita_d = next(s for s in lectura.saldos if s["cuenta"] == "RITA" and s["decena_inicio"] == "2026-01-01")
    assert (rita_d["saldo_formulas"], rita_d["saldo_bancos"]) == ("300.00", "299.00")
    assert lectura.por_cuenta["PIO"] == {"decenas": 4, "filas": 5, "entradas": 2, "salidas": 3,
                                         "suma_control": "1550.10", "decenas_cuadran": 4,
                                         "decenas_sin_saldo_bancos": 2}
    assert lectura.hojas_ignoradas == ["Banco_4", "Otra hoja"]
    assert lectura.avisos_redondeo == [] and lectura.celdas_texto_vacias == []


def test_el_saldo_de_formulas_guardado_de_una_formula_se_lee(tmp_path):
    lectura = _leer(tmp_path)
    assert next(s for s in lectura.saldos if s["cuenta"] == "PIO" and s["decena_inicio"] == "2026-01-01") == {
        "cuenta": "PIO", "decena_inicio": "2026-01-01", "saldo_inicial": "500.00", "saldo_formulas": "1250.00",
        "saldo_bancos": None}


def test_rs_positivos_y_negativos_cuadran_con_re_menos_rs(tmp_path):
    def cambiar(hojas, _):
        hojas[HOJA_PIO]["D7"] = 50  # devolucion convertida en salida: 500 + 1000 - 300 - 50 = 1150
    with pytest.raises(ic.ErrorExcel, match=f"CUADRE_NO_VALIDO:{HOJA_PIO}:D"):
        _leer(tmp_path, cambiar)

    def cuadra(hojas, cacheados):
        hojas[HOJA_PIO]["D7"] = 50
        cacheados[(HOJA_PIO, "D9")] = 1150
        hojas[HOJA_PIO]["E4"] = 1150
        hojas[HOJA_PIO]["E9"] = 1350.1
        hojas[HOJA_PIO]["E10"] = None
    lectura = _leer(tmp_path / "b", cuadra)
    assert next(s for s in lectura.saldos if s["cuenta"] == "PIO" and s["decena_inicio"] == "2026-01-01")[
        "saldo_formulas"] == "1150.00"


def test_redondeo_half_up_con_aviso_y_marca_redondeado(tmp_path):
    """E3: mas de 2 decimales se redondea al centimo half-up, con aviso, y el importe va marcado ``redondeado``. El
    cuadre exacto usa el valor sin redondear: 1250 + 200,104 - 1450,10 = 0,004, menos de medio centimo."""
    def cambiar(hojas, _):
        hojas[HOJA_PIO]["E5"] = 200.104
    lectura = _leer(tmp_path, cambiar)
    fila = next(f for f in lectura.importes if f["cuenta"] == "PIO" and f["decena_inicio"] == "2026-01-11")
    assert (fila["importe"], fila["redondeado"]) == ("200.10", True)
    assert lectura.avisos_redondeo == [{"celda": f"{HOJA_PIO}:E5", "original": "200.104", "redondeado": "200.10"}]
    assert ic._centimos(Decimal("0.125")) == (Decimal("0.13"), True)
    assert ic._centimos(Decimal("-0.125")) == (Decimal("-0.13"), True)
    assert ic._centimos(Decimal("1450.1000000001")) == (Decimal("1450.10"), False)


def test_saldo_con_mas_de_2_decimales_se_redondea_con_aviso(tmp_path):
    def cambiar(hojas, _):
        hojas[HOJA_PIO]["F10"] = 1449.123
    lectura = _leer(tmp_path, cambiar)
    saldo = next(s for s in lectura.saldos if s["cuenta"] == "PIO" and s["decena_inicio"] == "2026-01-21")
    assert saldo["saldo_bancos"] == "1449.12"
    assert lectura.avisos_redondeo == [{"celda": f"{HOJA_PIO}:F10", "original": "1449.123", "redondeado": "1449.12"}]


def test_cuadre_redondeado_como_la_rpc_margen_por_importe_y_ninguno_por_saldo(tmp_path):
    """Antes de llamar a la RPC se repite su cuadre con los valores al centimo: 0,005 por importe redondeado de esa
    cuenta y decena, y ninguno por saldo redondeado (decision de Pio, 2026-11-22)."""
    def con_margen(hojas, _):
        # Crudo: 1250 + 100,004 - (-100,004) = 1450,008. Al centimo: 1250 + 100,00 + 100,00 - 1450,01 = -0,01,
        # dentro de 2 x 0,005.
        hojas[HOJA_PIO]["E5"], hojas[HOJA_PIO]["E7"], hojas[HOJA_PIO]["E9"] = 100.004, -100.004, 1450.008
    lectura = _leer(tmp_path, con_margen)
    assert len(lectura.avisos_redondeo) == 3

    def sin_margen_por_saldo(hojas, _):
        # Crudo: 1250,005 + 200,1 - 1450,1049 = 0,0001. Al centimo: 1250,01 + 200,10 - 1450,10 = 0,01 sin ningun
        # importe redondeado: la RPC lo rechazaria (CUADRE_NO_VALIDO).
        hojas[HOJA_PIO]["E4"], hojas[HOJA_PIO]["E9"] = 1250.005, 1450.1049
    assert _error(tmp_path / "b", sin_margen_por_saldo) == f"CUADRE_REDONDEADO_NO_VALIDO:{HOJA_PIO}:E"


def test_texto_de_formula_y_solo_espacios_cuentan_como_vacias(tmp_path):
    def cambiar(hojas, cacheados):
        hojas[HOJA_PIO]["E6"] = '=IF(1,"x","")'
        cacheados[(HOJA_PIO, "E6")] = "x"
        hojas["RITA"]["E5"] = "   "
    lectura = _leer(tmp_path, cambiar)
    assert lectura.celdas_texto_vacias == [f"{HOJA_PIO}:E6", "RITA:E5"]
    assert len(lectura.importes) == 7


def test_un_importe_que_es_exactamente_igual_cuenta_como_vacio_con_aviso(tmp_path):
    """E2 ampliada (decision de Pio, 2026-11-22): contenido exactamente '=' (texto, no formula) = vacio, con aviso."""
    def cambiar(hojas, _):
        hojas[HOJA_PIO]["E6"] = ef.Texto("=")
        hojas["RITA"]["F5"] = ef.Texto("=")
    lectura = _leer(tmp_path, cambiar)
    assert lectura.celdas_igual_vacias == [f"{HOJA_PIO}:E6", "RITA:F5"]
    assert lectura.celdas_texto_vacias == [] and len(lectura.importes) == 7


@pytest.mark.parametrize("texto", ["==", "= ", " =", "=x", "-"])
def test_otro_texto_parecido_sigue_siendo_error(tmp_path, texto):
    def cambiar(hojas, _):
        hojas["RITA"]["E5"] = ef.Texto(texto)
    assert _error(tmp_path, cambiar) == "TEXTO_EN_IMPORTE:RITA:E5"


def test_un_igual_en_un_saldo_sigue_siendo_error(tmp_path):
    def cambiar(hojas, _):
        hojas["RITA"]["E10"] = ef.Texto("=")
    assert _error(tmp_path, cambiar) == "TEXTO_EN_SALDO:RITA:E10"


@pytest.mark.parametrize("valor, codigo", [("ver nota", "TEXTO_EN_IMPORTE"), (True, "TIPO_NO_ADMITIDO")])
def test_otro_texto_o_tipo_en_un_importe_es_error(tmp_path, valor, codigo):
    def cambiar(hojas, _):
        hojas["RITA"]["E5"] = valor
    assert _error(tmp_path, cambiar) == f"{codigo}:RITA:E5"


def test_texto_en_un_saldo_es_error_y_el_de_formula_es_vacio(tmp_path):
    def cambiar(hojas, _):
        hojas["RITA"]["E10"] = "pendiente"
    assert _error(tmp_path, cambiar) == "TEXTO_EN_SALDO:RITA:E10"

    def formula(hojas, cacheados):
        hojas["RITA"]["E10"] = '=IF(1,"","")'
        cacheados[("RITA", "E10")] = " "
    lectura = _leer(tmp_path / "b", formula)
    assert next(s for s in lectura.saldos if s["cuenta"] == "RITA" and s["decena_inicio"] == "2026-01-11")[
        "saldo_bancos"] is None


def test_hoja_de_plantilla_sin_importes_se_ignora_y_con_importes_es_error(tmp_path):
    _leer(tmp_path)

    def cambiar(hojas, cacheados):
        hojas["Banco_4"]["E6"] = 75
        del cacheados[("Banco_4", "E6")]
    assert _error(tmp_path / "b", cambiar) == "HOJA_IGNORADA_CON_IMPORTES:Banco_4"

    def sin_valor(hojas, cacheados):
        del cacheados[("Banco_4", "E6")]
    assert _error(tmp_path / "c", sin_valor) == "HOJA_IGNORADA_CON_FORMULA_SIN_VALOR:Banco_4:E6"


def test_hoja_no_listada_se_ignora_aunque_tenga_numeros_y_texto(tmp_path):
    def cambiar(hojas, _):
        hojas["Otra hoja"]["F9"] = 99
    assert len(_leer(tmp_path, cambiar).importes) == 7


def test_sl_sin_saldo_en_la_primera_decena_solo_sin_importes(tmp_path):
    def cambiar(hojas, _):
        hojas["SL"]["D5"] = 10
    assert _error(tmp_path, cambiar) == "SALDO_AUSENTE:SL:D4"

    def otra_decena(hojas, _):
        hojas["RITA"]["D4"] = None
    assert _error(tmp_path / "b", otra_decena) == "SALDO_AUSENTE:RITA:D4"

    def otra_hoja(hojas, _):
        hojas[HOJA_PIO]["H9"] = None
    assert _error(tmp_path / "c", otra_hoja) == f"SALDO_AUSENTE:{HOJA_PIO}:H9"


# --------------------------------------------------------------------------- fallo cerrado


def test_formula_sin_valor_guardado_es_error(tmp_path):
    def cambiar(hojas, cacheados):
        del cacheados[(HOJA_PIO, "D9")]
    assert _error(tmp_path, cambiar) == f"FORMULA_SIN_VALOR:{HOJA_PIO}:D9:1"


def test_cuadre_roto_es_error(tmp_path):
    def cambiar(hojas, _):
        hojas["RITA"]["H9"] = 350.6
    assert _error(tmp_path, cambiar) == "CUADRE_NO_VALIDO:RITA:H"


def _sin_hoja(hojas, _):
    del hojas["RITA"]


def _encabezado_texto(hojas, _):
    hojas["SL"]["E2"] = "11 de enero"


def _no_consecutivas(hojas, _):
    import datetime as dt
    for nombre in ("SL",):
        hojas[nombre]["H2"], hojas[nombre]["H3"] = dt.datetime(2026, 2, 11), dt.datetime(2026, 2, 20)


def _decena_mal(hojas, _):
    import datetime as dt
    hojas["SL"]["H3"] = dt.datetime(2026, 2, 9)


def _sin_fila_saldo(hojas, _):
    hojas["RITA"]["B10"] = "Saldo segun el banco"
    hojas["RITA"]["D10"] = None


def _fila_saldo_repetida(hojas, _):
    hojas["RITA"]["B11"] = "Saldo inicial"


def _sin_prefijo(hojas, _):
    hojas["RITA"]["A6"] = "Pagos ficticios"


def _importe_sin_categoria(hojas, cacheados):
    hojas["RITA"]["E8"] = 12  # tecleado sobre la fila de totales (sin categoria), en lugar de la formula
    del cacheados[("RITA", "E8")]


@pytest.mark.parametrize("cambiar, codigo", [
    (_sin_hoja, "HOJA_AUSENTE:RITA"),
    (_encabezado_texto, "ENCABEZADO_NO_FECHA:SL:E"),
    (_no_consecutivas, "DECENAS_NO_CONSECUTIVAS:SL:F:H"),
    (_decena_mal, "DECENA_NO_VALIDA:SL:H"),
    (_sin_fila_saldo, "FILA_SALDO_AUSENTE:RITA:saldo_bancos"),
    (_fila_saldo_repetida, "FILA_SALDO_REPETIDA:RITA:saldo_inicial"),
    (_sin_prefijo, "CATEGORIA_SIN_PREFIJO:RITA:A6"),
    (_importe_sin_categoria, "IMPORTE_SIN_CATEGORIA:RITA:E8"),
])
def test_estructura_cambiada_es_error(tmp_path, cambiar, codigo):
    assert _error(tmp_path, cambiar) == codigo


def test_un_fichero_que_no_es_excel_es_error(tmp_path):
    ruta = tmp_path / "CASHFLOW.xlsm"
    ruta.write_bytes(b"no es un libro")
    with pytest.raises(ic.ErrorExcel, match="EXCEL_ILEGIBLE"):
        ic.leer_excel(ruta)


def test_los_codigos_de_error_no_llevan_conceptos_ni_categorias(tmp_path):
    def cambiar(hojas, _):
        hojas["RITA"]["A6"] = "Sin prefijo secreto"
    codigo = _error(tmp_path, cambiar)
    assert "secreto" not in codigo and "ficticio" not in codigo


# --------------------------------------------------------------------------- seleccion y copia (C1)


def test_seleccion_exige_un_unico_xlsm_que_empieza_por_cashflow(tmp_path):
    with pytest.raises(ic.ErrorExcel, match="EXCEL_NO_ENCONTRADO"):
        ic.seleccionar_fichero(tmp_path)
    (tmp_path / "~$CASHFLOW 2026.xlsm").write_bytes(b"temporal")
    (tmp_path / "CASHFLOW 2026.xlsx").write_bytes(b"otra extension")
    (tmp_path / "copia CASHFLOW.xlsm").write_bytes(b"otro prefijo")
    with pytest.raises(ic.ErrorExcel, match="EXCEL_NO_ENCONTRADO"):
        ic.seleccionar_fichero(tmp_path)
    unico = tmp_path / "CASHFLOW 2026 v3.xlsm"
    unico.write_bytes(b"x")
    assert ic.seleccionar_fichero(tmp_path) == unico
    (tmp_path / "CASHFLOW antiguo.XLSM").write_bytes(b"y")
    with pytest.raises(ic.ErrorExcel, match="EXCEL_AMBIGUO:2"):
        ic.seleccionar_fichero(tmp_path)


def test_copia_estable_con_el_mismo_sha(tmp_path):
    import datetime as dt
    import hashlib

    original = tmp_path / "origen" / "CASHFLOW.xlsm"
    original.parent.mkdir()
    original.write_bytes(b"contenido del libro")
    copia, sha = ic.copiar_estable(original, tmp_path / "copias", dt.date(2026, 11, 22))
    assert sha == hashlib.sha256(b"contenido del libro").hexdigest()
    assert copia == tmp_path / "copias" / f"2026-11-22_{sha[:8]}.xlsm"
    assert copia.read_bytes() == original.read_bytes()


def test_copia_inestable_es_error(tmp_path, monkeypatch):
    import datetime as dt

    original = tmp_path / "CASHFLOW.xlsm"
    original.write_bytes(b"a")
    valores = iter(["1" * 64, "2" * 64, "2" * 64])
    monkeypatch.setattr(ic, "_sha256", lambda _ruta: next(valores))
    with pytest.raises(ic.ErrorExcel, match="COPIA_NO_ESTABLE"):
        ic.copiar_estable(original, tmp_path / "copias", dt.date(2026, 11, 22))


# --------------------------------------------------------------------------- RPC y postcheck


@pytest.mark.parametrize("texto, codigo", [
    ("ERROR:  CUADRE_NO_VALIDO\nCONTEXT:  PL/pgSQL function", "CUADRE_NO_VALIDO"),
    ("{'message': 'FILAS_NO_COINCIDEN:3:4', 'code': 'P0001'}", "FILAS_NO_COINCIDEN"),
    ("ERROR:  CLAVE_NO_ADMITIDA:importes", "CLAVE_NO_ADMITIDA:importes"),
    ('new row for relation "x" violates check constraint "y"', "RESTRICCION_DE_TABLA"),
    ("ConnectionResetError: conexion cortada", None),
    ("ERROR:  permission denied for function", None),
])
def test_codigo_de_rechazo_de_la_rpc(texto, codigo):
    assert ic._codigo_rechazo(RuntimeError(texto)) == codigo


def _snap(importaciones=None, importes=None, saldos=None):
    return {"cuentas": {"PIO": "a", "RITA": "b", "SL": "c"}, "importaciones": dict(importaciones or {}),
            "importes": dict(importes or {}), "saldos": dict(saldos or {})}


def test_postcheck_cashflow_admite_solo_las_filas_de_la_importacion():
    pre = _snap({"vieja": ["h1", True]}, {"1": ["x", "vieja"]}, {"1": ["y", "vieja"]})
    post = _snap({"vieja": ["h2", False], "nueva": ["h3", True]}, {"1": ["x", "vieja"], "2": ["z", "nueva"]},
                 {"1": ["y", "vieja"], "2": ["w", "nueva"], "3": ["v", "nueva"]})
    assert ic.postcheck_cashflow(pre, post, "nueva", "vieja", 1, 2) == []
    assert ic.postcheck_cashflow(pre, post, "nueva", None, 1, 2) == ["IMPORTACION_CAMBIADA:vieja"]
    assert ic.postcheck_cashflow(pre, post, "nueva", "vieja", 1, 1) == ["SALDOS_NUEVOS_INESPERADOS:2"]
    ajena = _snap({"vieja": ["h2", False], "nueva": ["h3", True]}, {"1": ["x2", "vieja"], "2": ["z", "nueva"]},
                  {"1": ["y", "vieja"], "2": ["w", "nueva"], "3": ["v", "nueva"]})
    assert ic.postcheck_cashflow(pre, ajena, "nueva", "vieja", 1, 2) == ["IMPORTES_CAMBIADOS_O_DESAPARECIDOS"]
    assert ic.postcheck_cashflow(pre, pre, None, None, 0, 0) == []
    assert ic.postcheck_cashflow(pre, post, None, None, 0, 0)[0] == "IMPORTACIONES_NUEVAS_INESPERADAS:1"


# --------------------------------------------------------------------------- argumentos y fuente


@pytest.mark.parametrize("argv", [[], ["NOCHE"], ["NOCHE", "REAL", "--aceptar-categorias-nuevas"],
                                  ["MANUAL", "BORRAR"], ["OTRO", "REAL"], ["MANUAL", "REAL", "--forzar"]])
def test_argumentos_no_admitidos(argv):
    with pytest.raises(SystemExit, match="uso:"):
        ic.main(argv)


def test_importar_valida_origen_modo_y_aceptacion():
    for args in (("NOCHE", "BORRAR", False), ("OTRO", "REAL", False), ("NOCHE", "REAL", True)):
        with pytest.raises(ValueError):
            ic.importar(*args, entorno=None)


def test_la_unica_escritura_es_la_rpc_de_la_38():
    fuente = inspect.getsource(ic)
    minusculas = fuente.lower()
    for prohibido in (".table(", ".insert(", "insert into", ".update(", ".delete(", ".upsert(", "set role",
                      "obtener_conexion", "pyodbc", "conexion_sql"):
        assert prohibido not in minusculas, prohibido
    llamadas = [n for n in ast.walk(ast.parse(fuente))
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "rpc"]
    assert len(llamadas) == 1 and ast.unparse(llamadas[0].args[0]) == "RPC"
    assert ic.RPC == "cf_cashflow_registrar_importacion"


def test_el_bat_lanza_la_importacion_nocturna_real_sin_aceptar_categorias():
    bat = (ic.ROOT / "ejecutar_importacion_cashflow.bat").read_text(encoding="utf-8")
    assert "-m src.cashflow.importar_cashflow NOCHE REAL >> logs\\importacion_cashflow.log 2>&1" in bat
    assert "--aceptar" not in bat
    assert "C:\\ControlFarmacias\\Programa\\.venv\\Scripts\\python.exe" in bat
    assert "exit /b %CODIGO_SALIDA%" in bat
