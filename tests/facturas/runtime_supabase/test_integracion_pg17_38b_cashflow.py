"""Hito 38-B: importacion del Excel de cashflow contra PostgreSQL 17 local (plantilla "38").

Excel FICTICIO (``excel_cashflow_ficticio``), ningun dato real. La escritura es SOLO la RPC de la 38, llamada por el
cliente de prueba con el rol del sistema (como el cliente de la noche en produccion); las lecturas, con una sesion
READ_ONLY real por psycopg2. Se comprueba:
- SIMULAR no escribe nada; REAL registra OK (importes con su signo, saldos, vigente) o ERROR (solo la cabecera);
- C5: en la primera importacion y con categorias nuevas, la noche no escribe; la manual las acepta;
- C6: el mismo fichero da SIN_CAMBIOS; el hash de una importacion anterior para sin escribir;
- un rechazo de la RPC se registra como ERROR aparte; un resultado incierto para sin registrar nada;
- puertas (tareas, noche EN_CURSO, git en REAL, carpeta, migracion 38) y postcheck por fila (filas ajenas);
- el informe no contiene conceptos ni categorias.
Sin produccion ni Farmatic.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import excel_cashflow_ficticio as ef
import pg17_local as pgl
from excel_cashflow_ficticio import HOJA_PIO
from pg17_local import ROOT, ClientePg17, base_desde
from src.cashflow import importar_cashflow as ic
from src.facturas.runtime_supabase.lectura_readonly import sesion_lectura

pytestmark = pytest.mark.pg17_local

CONTEOS = ("select (select count(*) from public.cf_cashflow_importaciones) || '|' || "
           "(select count(*) from public.cf_cashflow_importes) || '|' || "
           "(select count(*) from public.cf_cashflow_saldos)")


@pytest.fixture(scope="module")
def contenedor_tcp(pg17_contenedor_tcp):
    """Hito SUITE (D5): contenedor TCP limpio por modulo; plantillas 38 y 37."""
    nombre, puerto = pg17_contenedor_tcp
    return nombre, puerto, pgl.construir_plantilla(nombre, "38")


def _conectar(puerto, db):
    sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))
    import psycopg2

    return psycopg2.connect(host="127.0.0.1", port=puerto, dbname=db, user="postgres", password="local-only",
                            connect_timeout=10)


@pytest.fixture
def cf(contenedor_tcp, tmp_path):
    nombre, puerto, plantilla = contenedor_tcp
    pg = base_desde(nombre, plantilla)
    conexion = _conectar(puerto, pg.db)
    carpeta = tmp_path / "CASHFLOW"
    carpeta.mkdir()
    estado = {"tareas": {"tareas": [{"nombre": "ControlFarmacias - Importar facturas", "estado": "Ready"}]},
              "git": ("head", [])}
    cliente = ClientePg17(pg)

    def entorno(cliente_=None, conexion_=None, carpeta_=None):
        c = conexion_ or conexion
        return ic.Entorno(abrir_lectura=lambda: sesion_lectura(c), cliente=cliente_ or cliente,
                          tareas=lambda: estado["tareas"], puerta_git=lambda: estado["git"],
                          carpeta_excel=carpeta_ or carpeta, directorio=tmp_path / "cf")

    def importar(origen="MANUAL", modo="REAL", aceptar=None, **kw):
        if aceptar is None:
            aceptar = origen == "MANUAL"
        return ic.importar(origen, modo, aceptar, entorno(**kw))

    yield SimpleNamespace(pg=pg, cliente=cliente, estado=estado, carpeta=carpeta, importar=importar,
                          entorno=entorno, puerto=puerto, nombre=nombre, tmp=tmp_path)
    conexion.close()


def _excel(cf, cambiar=None):
    return ef.excel(cf.carpeta, cambiar=cambiar)


def _vigentes(pg) -> list[str]:
    return [f["id"] for f in pg.json("select id from public.cf_cashflow_importaciones where vigente")]


def _sin_contenido(informe: dict) -> None:
    """El informe no lleva conceptos ni categorias (los del Excel ficticio llevan la palabra 'ficti')."""
    carpeta = Path(informe["copia"]).parents[1] / "informes" if informe.get("copia") else None
    texto = json.dumps(informe, ensure_ascii=False)
    assert "ficti" not in texto.replace("ficticio.xlsm", "")
    assert "Cobros" not in texto and "Pagos" not in texto and "Devoluciones" not in texto
    if carpeta:
        for ruta in carpeta.rglob("*"):
            if ruta.is_file():
                contenido = ruta.read_text(encoding="utf-8")
                assert "Cobros" not in contenido and "Concepto" not in contenido


def _primera(cf) -> dict:
    _excel(cf)
    codigo, informe = cf.importar("MANUAL", "REAL", True)
    assert (codigo, informe["resultado"]) == (ic.CODIGO_OK, "OK"), informe
    return informe


# --------------------------------------------------------------------------- SIMULAR y REAL


def test_simular_no_escribe_nada(cf):
    _excel(cf)
    codigo, informe = cf.importar("NOCHE", "SIMULAR")
    assert (codigo, informe["resultado"], informe["categorias_nuevas"]) == (
        ic.CODIGO_CATEGORIAS, "CATEGORIAS_NUEVAS_SIN_ACEPTAR", 4)
    codigo, informe = cf.importar("MANUAL", "SIMULAR", True)
    assert (codigo, informe["resultado"], informe["registrado"]) == (ic.CODIGO_OK, "SIMULADO_OK", False)
    assert (informe["lectura"]["importes"], informe["lectura"]["saldos"]) == (7, 11)
    assert cf.cliente.rpcs == []
    assert cf.pg.sql(CONTEOS) == "0|0|0"
    _sin_contenido(informe)


def test_simular_un_excel_invalido_no_escribe(cf):
    _excel(cf, lambda h, _: h["RITA"].__setitem__("H9", 351))
    codigo, informe = cf.importar("MANUAL", "SIMULAR", True)
    assert (codigo, informe["resultado"], informe["detalle_error"]) == (
        ic.CODIGO_ERROR, "SIMULADO_ERROR", "CUADRE_NO_VALIDO:RITA:H")
    assert cf.cliente.rpcs == [] and cf.pg.sql(CONTEOS) == "0|0|0"


def test_la_primera_importacion_nocturna_no_acepta_categorias_nuevas(cf):
    _excel(cf)
    codigo, informe = cf.importar("NOCHE", "REAL")
    assert (codigo, informe["resultado"], informe["hay_vigente"]) == (
        ic.CODIGO_CATEGORIAS, "CATEGORIAS_NUEVAS_SIN_ACEPTAR", False)
    assert cf.cliente.rpcs == [] and cf.pg.sql(CONTEOS) == "0|0|0"


def test_importacion_manual_real_ok(cf):
    informe = _primera(cf)
    assert informe["registrado"] and informe["postcheck"] == {"veredicto": "POSTCHECK_OK", "problemas": []}
    assert [n for n, _ in cf.cliente.rpcs] == [ic.RPC]
    respuesta = informe["respuesta_rpc"]
    assert (respuesta["importes"], respuesta["saldos"], respuesta["vigente"]) == (7, 11, True)
    assert _vigentes(cf.pg) == [respuesta["importacion_id"]]
    cabecera = cf.pg.json("select archivo_nombre, archivo_hash, origen, estado, filas, detalle_error "
                          "from public.cf_cashflow_importaciones")[0]
    copia = Path(informe["copia"])
    assert cabecera == {"archivo_nombre": "CASHFLOW 2026 ficticio.xlsm",
                        "archivo_hash": hashlib.sha256(copia.read_bytes()).hexdigest(), "origen": "MANUAL",
                        "estado": "OK", "filas": 7, "detalle_error": None}
    assert copia.parent == cf.tmp / "cf" / "copias"
    # E1: el importe con el signo de la celda; la farmacia, la de la cuenta.
    assert cf.pg.sql("select string_agg(cuenta || ':' || coalesce(farmacia, '-') || ':' || decena_inicio || ':' "
                     "|| fila_excel || ':' || importe, ',' order by cuenta, decena_inicio, fila_excel) "
                     "from public.cf_cashflow_importes") == (
        "PIO:PIO:2026-01-01:5:1000.00,PIO:PIO:2026-01-01:6:300.00,PIO:PIO:2026-01-01:7:-50.00,"
        "PIO:PIO:2026-01-11:5:200.10,PIO:PIO:2026-02-01:6:100.00,"
        "RITA:RITA:2026-01-01:5:200.00,RITA:RITA:2026-02-01:5:50.50")
    # E5 (SL sin la primera decena) y E7 (bancos distinto o vacio).
    assert cf.pg.sql("select string_agg(cuenta || ':' || decena_inicio || ':' || saldo_inicial || ':' || "
                     "saldo_formulas || ':' || coalesce(saldo_bancos::text, '-'), ',' order by cuenta, decena_inicio) "
                     "from public.cf_cashflow_saldos where cuenta <> 'PIO'") == (
        "RITA:2026-01-01:100.00:300.00:299.00,RITA:2026-01-11:300.00:300.00:-,RITA:2026-01-21:300.00:300.00:-,"
        "RITA:2026-02-01:300.00:350.50:-,SL:2026-01-11:0.00:0.00:-,SL:2026-01-21:0.00:0.00:-,"
        "SL:2026-02-01:0.00:0.00:-")
    _sin_contenido(informe)
    carpeta = next((cf.tmp / "cf" / "informes").rglob("informe.json")).parent
    assert sorted(p.name for p in carpeta.iterdir()) == ["SHA256SUMS.txt", "informe.json", "resumen.txt"]
    assert hashlib.sha256((carpeta / "informe.json").read_bytes()).hexdigest() == informe["informe_sha256"]


def test_redondeo_llega_a_la_rpc_con_su_margen(cf):
    def cambiar(hojas, _):
        hojas[HOJA_PIO]["E5"], hojas[HOJA_PIO]["E7"], hojas[HOJA_PIO]["E9"] = 100.004, -100.004, 1450.008
    _excel(cf, cambiar)
    codigo, informe = cf.importar("MANUAL", "REAL", True)
    assert (codigo, informe["resultado"]) == (ic.CODIGO_OK, "OK"), informe
    assert len(informe["lectura"]["avisos_redondeo"]) == 3
    assert cf.pg.sql("select string_agg(importe::text, ',' order by fila_excel) from public.cf_cashflow_importes "
                     "where cuenta = 'PIO' and decena_inicio = '2026-01-11'") == "100.00,-100.00"
    assert cf.pg.sql("select saldo_formulas from public.cf_cashflow_saldos "
                     "where cuenta = 'PIO' and decena_inicio = '2026-01-11'") == "1450.01"


def test_celdas_igual_vacias_con_aviso_en_el_informe_y_se_importa(cf):
    """E2 ampliada (decision de Pio, 2026-11-22): '=' exacto en un importe cuenta como vacio, con aviso y recuento."""
    def cambiar(hojas, _):
        hojas[HOJA_PIO]["F6"] = ef.Texto("=")
        hojas["RITA"]["E5"] = ef.Texto("=")
    _excel(cf, cambiar)
    codigo, informe = cf.importar("MANUAL", "REAL", True)
    assert (codigo, informe["resultado"]) == (ic.CODIGO_OK, "OK"), informe
    assert informe["lectura"]["avisos_celdas_igual_vacias"] == {"n": 2, "posiciones": [f"{HOJA_PIO}:F6", "RITA:E5"]}
    assert cf.pg.sql(CONTEOS) == "1|7|11"
    resumen = next((cf.tmp / "cf" / "informes").rglob("resumen.txt")).read_text(encoding="utf-8")
    assert "celdas '=' vacias: 2" in resumen


# --------------------------------------------------------------------------- C6 y versiones


def test_el_mismo_fichero_da_sin_cambios(cf):
    _primera(cf)
    antes = cf.pg.sql(CONTEOS)
    codigo, informe = cf.importar("NOCHE", "REAL")
    assert (codigo, informe["resultado"], informe["registrado"]) == (ic.CODIGO_OK, "SIN_CAMBIOS", False)
    assert len(cf.cliente.rpcs) == 1 and cf.pg.sql(CONTEOS) == antes


def test_una_version_nueva_sustituye_a_la_vigente_sin_aceptar_nada(cf):
    primera = _primera(cf)["respuesta_rpc"]["importacion_id"]

    def cambiar(hojas, _):
        hojas["RITA"]["H5"], hojas["RITA"]["H9"] = 51.5, 351.5
    _excel(cf, cambiar)
    codigo, informe = cf.importar("NOCHE", "REAL")
    assert (codigo, informe["resultado"], informe["categorias_nuevas"]) == (ic.CODIGO_OK, "OK", 0), informe
    assert informe["respuesta_rpc"]["anterior"] == primera
    assert _vigentes(cf.pg) == [informe["respuesta_rpc"]["importacion_id"]]
    assert cf.pg.sql("select string_agg(origen || ':' || estado || ':' || vigente, ',' order by importado_at) "
                     "from public.cf_cashflow_importaciones") == "MANUAL:OK:false,NOCHE:OK:true"
    assert informe["postcheck"]["veredicto"] == "POSTCHECK_OK"
    assert cf.pg.sql(CONTEOS) == "2|14|22"


def test_el_hash_de_una_importacion_anterior_para_sin_escribir(cf):
    _primera(cf)
    original = (cf.carpeta / "CASHFLOW 2026 ficticio.xlsm").read_bytes()
    _excel(cf, lambda h, _: (h["RITA"].__setitem__("H5", 51.5), h["RITA"].__setitem__("H9", 351.5)))
    assert cf.importar("NOCHE", "REAL")[1]["resultado"] == "OK"
    (cf.carpeta / "CASHFLOW 2026 ficticio.xlsm").write_bytes(original)
    antes = cf.pg.sql(CONTEOS)
    codigo, informe = cf.importar("NOCHE", "REAL")
    assert (codigo, informe["resultado"], informe["motivo"]) == (
        ic.CODIGO_PARADA, "PARADA", "HASH_DE_UNA_IMPORTACION_ANTERIOR")
    assert len(cf.cliente.rpcs) == 2 and cf.pg.sql(CONTEOS) == antes


# --------------------------------------------------------------------------- C5


def test_una_categoria_nueva_para_la_noche_y_la_acepta_la_manual(cf):
    _primera(cf)

    def cambiar(hojas, _):
        hojas["RITA"]["E6"], hojas["RITA"]["E9"] = 10, 290  # RITA usa por primera vez una categoria de salida
    _excel(cf, cambiar)
    antes = cf.pg.sql(CONTEOS)
    codigo, informe = cf.importar("NOCHE", "REAL")
    assert (codigo, informe["resultado"], informe["categorias_nuevas"]) == (
        ic.CODIGO_CATEGORIAS, "CATEGORIAS_NUEVAS_SIN_ACEPTAR", 1)
    assert cf.pg.sql(CONTEOS) == antes
    assert cf.importar("MANUAL", "REAL", False)[1]["resultado"] == "CATEGORIAS_NUEVAS_SIN_ACEPTAR"
    codigo, informe = cf.importar("MANUAL", "REAL", True)
    assert (codigo, informe["resultado"]) == (ic.CODIGO_OK, "OK")
    assert cf.pg.sql(CONTEOS) == "2|15|22"


def test_una_categoria_de_una_importacion_ok_anterior_no_es_nueva_aunque_no_este_en_la_vigente(cf):
    """C5 (decision de Pio, 2026-11-22): nueva = no aparece en NINGUNA importacion OK anterior de esa cuenta."""
    _primera(cf)  # PIO usa la categoria de devoluciones (D7 = -50)

    def sin_devolucion(hojas, cacheados):
        hojas[HOJA_PIO]["D7"] = None
        cacheados[(HOJA_PIO, "D9")] = 1200
    _excel(cf, sin_devolucion)
    codigo, informe = cf.importar("NOCHE", "REAL")
    assert (codigo, informe["resultado"], informe["categorias_nuevas"]) == (ic.CODIGO_OK, "OK", 0), informe
    assert cf.pg.sql("select count(*) from public.cf_cashflow_importes i join public.cf_cashflow_importaciones m "
                     "on m.id = i.importacion_id where m.vigente and i.categoria like 'RS Devol%'") == "0"

    def vuelve(hojas, cacheados):
        hojas[HOJA_PIO]["D7"] = -60
        cacheados[(HOJA_PIO, "D9")] = 1260
    _excel(cf, vuelve)
    codigo, informe = cf.importar("NOCHE", "REAL")
    assert (codigo, informe["resultado"], informe["categorias_nuevas"]) == (ic.CODIGO_OK, "OK", 0), informe
    assert cf.pg.sql(CONTEOS) == "3|20|33"  # 7 + 6 + 7 importes, 11 saldos cada una


def test_un_error_anterior_no_hace_conocida_ninguna_categoria(cf):
    _excel(cf, lambda h, _: h["RITA"].__setitem__("H9", 351))
    assert cf.importar("MANUAL", "REAL", True)[1]["resultado"] == "ERROR"
    _excel(cf)
    codigo, informe = cf.importar("NOCHE", "REAL")
    assert (codigo, informe["resultado"], informe["categorias_nuevas"]) == (
        ic.CODIGO_CATEGORIAS, "CATEGORIAS_NUEVAS_SIN_ACEPTAR", 4)


# --------------------------------------------------------------------------- ERROR


def test_un_excel_invalido_registra_solo_la_cabecera_y_conserva_la_vigente(cf):
    vigente = _primera(cf)["respuesta_rpc"]["importacion_id"]
    _excel(cf, lambda h, _: h["RITA"].__setitem__("H9", 351))
    codigo, informe = cf.importar("NOCHE", "REAL")
    assert (codigo, informe["resultado"], informe["registrado"]) == (ic.CODIGO_ERROR, "ERROR", True)
    assert informe["postcheck"]["veredicto"] == "POSTCHECK_OK"
    error = cf.pg.json("select estado, detalle_error, filas, vigente, origen from public.cf_cashflow_importaciones "
                       "where estado = 'ERROR'")
    assert error == [{"estado": "ERROR", "detalle_error": "CUADRE_NO_VALIDO:RITA:H", "filas": 0, "vigente": False,
                      "origen": "NOCHE"}]
    assert _vigentes(cf.pg) == [vigente] and cf.pg.sql(CONTEOS) == "2|7|11"
    # C6: el mismo ERROR no se repite cada noche.
    assert cf.importar("NOCHE", "REAL")[1]["resultado"] == "SIN_CAMBIOS"
    assert cf.pg.sql(CONTEOS) == "2|7|11"


def test_un_rechazo_de_la_rpc_se_registra_como_error_aparte(cf, monkeypatch):
    _excel(cf)
    real = ic.leer_excel

    def sin_un_saldo(ruta):
        lectura = real(ruta)
        lectura.saldos = [s for s in lectura.saldos if not (s["cuenta"] == "PIO" and s["decena_inicio"] == "2026-01-01")]
        return lectura
    monkeypatch.setattr(ic, "leer_excel", sin_un_saldo)
    codigo, informe = cf.importar("MANUAL", "REAL", True)
    assert (codigo, informe["resultado"], informe["rechazo_rpc"]) == (ic.CODIGO_ERROR, "ERROR", "IMPORTES_SIN_SALDO")
    assert cf.pg.json("select estado, detalle_error, vigente from public.cf_cashflow_importaciones") == [
        {"estado": "ERROR", "detalle_error": "RPC_RECHAZO:IMPORTES_SIN_SALDO", "vigente": False}]
    assert cf.pg.sql(CONTEOS) == "1|0|0" and len(cf.cliente.rpcs) == 2
    assert informe["postcheck"]["veredicto"] == "POSTCHECK_OK"


def test_un_resultado_incierto_para_sin_registrar_nada(cf):
    _excel(cf)

    class Cortado:
        rpcs = []

        def rpc(self, nombre, payload):
            self.rpcs.append(nombre)
            return SimpleNamespace(execute=lambda: (_ for _ in ()).throw(ConnectionError("conexion cortada")))
    codigo, informe = cf.importar("MANUAL", "REAL", True, cliente_=Cortado())
    assert (codigo, informe["resultado"], informe["motivo"], informe["registrado"]) == (
        ic.CODIGO_PARADA, "PARADA", "RPC_RESULTADO_INCIERTO:ConnectionError", False)
    assert cf.pg.sql(CONTEOS) == "0|0|0"


@pytest.mark.parametrize("ficheros, detalle", [
    ([], "EXCEL_NO_ENCONTRADO"), (["CASHFLOW a.xlsm", "CASHFLOW b.xlsm"], "EXCEL_AMBIGUO:2")])
def test_sin_fichero_o_ambiguo_solo_informe(cf, ficheros, detalle):
    for nombre in ficheros:
        ef.excel(cf.carpeta, nombre)
    codigo, informe = cf.importar("NOCHE", "REAL")
    assert (codigo, informe["resultado"], informe["detalle_error"], informe["registrado"]) == (
        ic.CODIGO_ERROR, "ERROR", detalle, False)
    assert cf.cliente.rpcs == [] and cf.pg.sql(CONTEOS) == "0|0|0"


# --------------------------------------------------------------------------- puertas y postcheck


def _en_ejecucion(cf, nombre):
    cf.estado["tareas"] = {"tareas": [{"nombre": nombre, "estado": "Running"}]}


@pytest.mark.parametrize("preparar, origen, modo, fallo", [
    (lambda cf: _en_ejecucion(cf, "ControlFarmacias - Automatizacion Alliance"), "NOCHE", "REAL",
     "TAREA_EN_EJECUCION:ControlFarmacias - Automatizacion Alliance"),
    (lambda cf: _en_ejecucion(cf, ic.TAREA_CASHFLOW), "MANUAL", "SIMULAR",
     f"TAREA_EN_EJECUCION:{ic.TAREA_CASHFLOW}"),
    (lambda cf: cf.estado.__setitem__("tareas", {"error": "sin acceso"}), "MANUAL", "SIMULAR",
     "TAREAS_NO_DETERMINABLES"),
    (lambda cf: cf.estado.__setitem__("git", ("head", ["ARBOL_SUCIO"])), "NOCHE", "REAL", "ARBOL_SUCIO"),
    (lambda cf: cf.pg.sql("insert into public.cf_noches_automaticas (fecha, modo, resultado) "
                          "values (current_date, 'REAL', 'EN_CURSO')"), "MANUAL", "REAL", "NOCHE_EN_CURSO:1"),
])
def test_puertas_paran_sin_escribir(cf, preparar, origen, modo, fallo):
    _excel(cf)
    preparar(cf)
    codigo, informe = cf.importar(origen, modo)
    assert (codigo, informe["resultado"]) == (ic.CODIGO_PARADA, "PARADA")
    assert fallo in informe["puertas"]
    assert cf.cliente.rpcs == [] and cf.pg.sql(CONTEOS) == "0|0|0"


def test_la_propia_tarea_de_cashflow_no_para_la_noche_y_git_no_cuenta_al_simular(cf):
    _excel(cf)
    _en_ejecucion(cf, ic.TAREA_CASHFLOW)
    assert cf.importar("NOCHE", "SIMULAR")[1]["puertas"] == []
    cf.estado["git"] = ("head", ["ARBOL_SUCIO"])
    cf.estado["tareas"] = {"tareas": []}
    assert cf.importar("MANUAL", "SIMULAR", True)[1]["resultado"] == "SIMULADO_OK"


def test_carpeta_inexistente_para(cf):
    codigo, informe = cf.importar("NOCHE", "REAL", carpeta_=cf.tmp / "no_existe")
    assert codigo == ic.CODIGO_PARADA and "CARPETA_EXCEL_NO_EXISTE" in informe["puertas"]


def test_sin_la_38_para(cf):
    pg37 = base_desde(cf.nombre, pgl.construir_plantilla(cf.nombre, "37"))
    conexion = _conectar(cf.puerto, pg37.db)
    try:
        _excel(cf)
        codigo, informe = cf.importar("MANUAL", "SIMULAR", True, conexion_=conexion)
    finally:
        conexion.close()
    assert codigo == ic.CODIGO_PARADA and informe["puertas"] == ["MIGRACION_38_AUSENTE"]


def test_el_postcheck_detecta_una_fila_ajena_y_para(cf):
    _excel(cf)
    real = cf.cliente

    class Intruso:
        rpcs = []

        def rpc(self, nombre, payload):
            diferida = real.rpc(nombre, payload)

            def ejecutar():
                respuesta = diferida.execute()
                pgl._registrar(cf.pg, real, b"%PDF documento ajeno", 1)
                return respuesta
            return SimpleNamespace(execute=ejecutar)
    codigo, informe = cf.importar("MANUAL", "REAL", True, cliente_=Intruso())
    assert (codigo, informe["resultado"]) == (ic.CODIGO_PARADA, "PARADA")
    assert informe["registrado"] and "FILAS_AJENAS:documentos_facturas" in informe["postcheck"]["problemas"]
    assert informe["motivo"] == "POSTCHECK_FALLIDO"
