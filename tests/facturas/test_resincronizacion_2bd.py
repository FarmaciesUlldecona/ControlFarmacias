"""Hito 2BD: resincronización de albaranes modificados, sin base de datos ni Farmatic.

Núcleo puro (``src/supabase_client/resincronizacion_albaranes``), sincronización nocturna con
la v2 apagada (comportamiento anterior) y encendida, modo informe sin escritura y consultas a
Farmatic (solo SELECT, recepción por proveedor y número del albarán).
"""
from __future__ import annotations

import ast
import importlib
from datetime import date, datetime
from pathlib import Path

import pytest

from src.facturas.runtime_supabase.conciliacion import _id_proveedor_comparable
from src.models.albaran import Albaran
from src.sql_explorer.seguridad_sql import validar_consulta_lectura
from src.supabase_client import resincronizacion_albaranes as resync

ROOT = Path(__file__).resolve().parents[2]
sincronizador = importlib.import_module("src.sincronizar_albaranes")
lectura = importlib.import_module("src.database.leer_albaranes")


def _albaran(contador=1, numero="08X00001", puc=10.0, pvp=15.0, dto=1.0, proveedor_id="0002", recep=5000,
             fecha=datetime(2026, 7, 1)):
    return Albaran(id_contador=contador, id_proveedor=proveedor_id, proveedor="1.- SAFA ", id_albaran=numero + " ",
                   fecha=fecha, importe_pvp=pvp, importe_puc=puc, dto=dto, id_recepcion=recep)


def _fila(**kw):
    return resync.payload_albaran(_albaran(**kw), "PIO", con_recepcion=True)


def _supabase(contador=1, numero="08X00001", puc="10.00", pvp="15.00", dto="1.00", proveedor_id="2",
              fecha="2026-07-01", **extra):
    return {"id_contador": contador, "farmacia": "PIO", "id_proveedor": proveedor_id, "proveedor": "1.- SAFA",
            "numero_albaran": numero, "fecha": fecha, "importe_puc": puc, "importe_pvp": pvp, "descuento": dto,
            **extra}


# --------------------------------------------------------------------------- núcleo

@pytest.mark.parametrize("valor", ["2", "0002", "0002 ", " 02", "0", "0000", "ABC", " ABC ", "", "  ", None, "00A1"])
def test_id_proveedor_comparable_es_la_regla_r9_de_conciliacion(valor):
    assert resync.id_proveedor_comparable(valor) == _id_proveedor_comparable(valor)


def test_iguales_aunque_el_proveedor_y_los_importes_tengan_otro_formato():
    farmatic = _fila(puc=504.0199999999, proveedor_id="0002 ")
    supabase = _supabase(puc="504.02", proveedor_id="2", id_recepcion=5000)
    plan = resync.planificar([farmatic], [supabase], set())
    assert plan.resumen() == {"nuevos": 0, "cambios": 0, "reaparecidos": 0, "ausentes": 0, "iguales": 1}


def test_cambio_de_puc_es_cambio_de_valor():
    plan = resync.planificar([_fila(puc=504.02)], [_supabase(puc="500.86", id_recepcion=5000)], set())
    [cambio] = plan.cambios
    assert cambio["diferencias"] == {"identidad": [], "valores": ["importe_puc"], "metadatos": []}
    assert resync.valores_rpc(cambio["fila"])["importe_puc"] == "504.02"


def test_cambio_de_numero_o_proveedor_es_identidad():
    plan = resync.planificar([_fila(numero="08X00002", proveedor_id="0101")],
                             [_supabase(id_recepcion=5000)], set())
    assert plan.cambios[0]["diferencias"]["identidad"] == ["numero_albaran", "id_proveedor"]


def test_recepcion_solo_se_compara_si_supabase_ya_tiene_la_columna():
    assert resync.planificar([_fila(recep=7)], [_supabase()], set()).iguales == 1  # esquema 21
    plan = resync.planificar([_fila(recep=7)], [_supabase(id_recepcion=None)], set())
    assert plan.cambios[0]["diferencias"]["metadatos"] == ["id_recepcion"]


def test_nuevos_ausentes_y_reaparecidos():
    plan = resync.planificar([_fila(contador=1), _fila(contador=3)],
                             [_supabase(contador=1, id_recepcion=5000), _supabase(contador=2, id_recepcion=5000),
                              _supabase(contador=3, id_recepcion=5000), _supabase(contador=4, id_recepcion=5000)],
                             ausentes_abiertos={3, 4})
    assert [f["id_contador"] for f in plan.nuevos] == []
    assert plan.ausentes == [2]  # 4 ya tiene la revisión abierta: no se vuelve a registrar
    assert [r["fila"]["id_contador"] for r in plan.reaparecidos] == [3]
    assert resync.planificar([_fila(contador=9)], [], set()).nuevos[0]["id_contador"] == 9


def test_ausente_que_farmatic_devuelve_por_contador_pasa_a_cambio():
    supabase = [_supabase(contador=2, fecha="2026-07-01", id_recepcion=5000)]
    plan = resync.planificar([], supabase, set())
    assert plan.ausentes == [2]
    plan = resync.confirmar_ausentes(plan, [_fila(contador=2, fecha=datetime(2025, 12, 1))], supabase)
    assert plan.ausentes == [] and plan.cambios[0]["diferencias"]["valores"] == ["fecha"]


def test_informe_prevé_revision_si_esta_reservado_o_cambia_la_identidad():
    plan = resync.planificar([_fila(contador=1, puc=11), _fila(contador=2, puc=12), _fila(contador=3, numero="Z")],
                             [_supabase(contador=c, id_recepcion=5000) for c in (1, 2, 3)], set())
    contenido = resync.informe(plan, {2: "factura-x"}, desde=date(2026, 4, 1), hasta=None, esquema_22=True)
    assert {c["id_contador"]: c["prevision"] for c in contenido["cambios"]} == {
        1: "ACTUALIZAR", 2: "REVISION:RESERVADO", 3: "REVISION:CAMBIO_IDENTIDAD"}
    assert contenido["cambios"][0]["campos"] == {"importe_puc": ["10.00", 11.0]}


# --------------------------------------------------------------------------- cliente falso

class _Respuesta:
    def __init__(self, data):
        self.data = data


class _Consulta:
    def __init__(self, cliente, tabla):
        self.cliente, self.tabla, self.filtros, self.rango, self.fila = cliente, tabla, [], None, None

    def select(self, _c):
        return self

    def eq(self, c, v):
        self.filtros.append(lambda f: str(f.get(c)) == str(v))
        return self

    def gte(self, c, v):
        self.filtros.append(lambda f: str(f.get(c)) >= str(v))
        return self

    def lte(self, c, v):
        self.filtros.append(lambda f: str(f.get(c)) <= str(v))
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, a, b):
        self.rango = (a, b)
        return self

    def insert(self, fila):
        self.fila = fila
        return self

    def execute(self):
        if self.fila is not None:
            self.cliente.escrituras.append(("insert", self.tabla, self.fila))
            return _Respuesta([self.fila])
        filas = [f for f in self.cliente.filas.get(self.tabla, []) if all(x(f) for x in self.filtros)]
        a, b = self.rango or (0, len(filas))
        return _Respuesta(filas[a:b + 1])


class _Cliente:
    def __init__(self, filas):
        self.filas, self.escrituras = filas, []

    def table(self, tabla):
        if tabla not in self.filas and tabla != "albaranes":
            raise RuntimeError(f"relation public.{tabla} does not exist")
        return _Consulta(self, tabla)

    def rpc(self, nombre, payload):
        self.escrituras.append(("rpc", nombre, payload))
        respuesta = {"accion": "ACTUALIZADO"} if nombre == "cf_resincronizar_albaran" else {"accion": "REVISION"}
        return _Diferida(respuesta)


class _Diferida:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return _Respuesta(self.data)


def test_ventana_se_amplia_a_las_facturas_no_conciliadas():
    cliente = _Cliente({"facturas": [{"id": "a", "farmacia": "PIO", "estado_conciliacion_cf": "PENDIENTE_CONCILIAR"},
                                     {"id": "b", "farmacia": "PIO", "estado_conciliacion_cf": "CONCILIADA"}],
                        "facturas_albaranes_extraidos": [{"id": 1, "factura_id": "a", "fecha_albaran": "2026-01-10"},
                                                         {"id": 2, "factura_id": "b", "fecha_albaran": "2025-01-01"}]})
    assert resync.fecha_inicio_ventana(cliente, "PIO", date(2026, 10, 22)) == date(2025, 12, 26)
    sin_abiertas = _Cliente({"facturas": [], "facturas_albaranes_extraidos": []})
    assert resync.fecha_inicio_ventana(sin_abiertas, "PIO", date(2026, 10, 22)) == date(2026, 4, 25)


def test_ejecutar_plan_inserta_nuevos_llama_a_las_rpc_y_no_se_detiene_por_un_error():
    plan = resync.planificar([_fila(contador=1, puc=11), _fila(contador=5)],
                             [_supabase(contador=1, id_recepcion=5000), _supabase(contador=2, id_recepcion=5000)],
                             set())
    cliente = _Cliente({})
    resumen = resync.ejecutar_plan(cliente, plan, "PIO", origen=resync.ORIGEN_VENTANA, ejecucion_id="t")
    assert [(e[0], e[1]) for e in cliente.escrituras] == [
        ("insert", "albaranes"), ("rpc", "cf_resincronizar_albaran"), ("rpc", "cf_registrar_albaran_ausente")]
    assert cliente.escrituras[0][2]["id_recepcion"] == 5000
    assert (resumen["insertados"], resumen["actualizados"], resumen["ausentes_registrados"]) == (1, 1, 1)

    class Falla(_Cliente):
        def rpc(self, nombre, payload):
            raise RuntimeError("caida")

    resumen = resync.ejecutar_plan(Falla({}), plan, "PIO", origen=resync.ORIGEN_VENTANA, ejecucion_id="t")
    assert resumen["insertados"] == 1 and len(resumen["errores"]) == 2


# --------------------------------------------------------------------------- sincronización nocturna

@pytest.fixture
def nocturna(monkeypatch):
    llamadas = {"nuevos": [], "guardados": [], "resync": 0}
    monkeypatch.setattr(sincronizador, "obtener_ultimo_id_contador", lambda _f: 0)
    monkeypatch.setattr(sincronizador, "obtener_nuevos_albaranes",
                        lambda _u: llamadas["nuevos"].append("v1") or [_albaran(recep=None)])
    monkeypatch.setattr(sincronizador, "obtener_nuevos_albaranes_con_recepcion",
                        lambda _u: llamadas["nuevos"].append("v2") or [_albaran(recep=777)])
    monkeypatch.setattr(sincronizador, "guardar_albaran", lambda p: llamadas["guardados"].append(p) or [p])

    def resync_falso(hoy=None):
        llamadas["resync"] += 1
        return {"errores": []}

    monkeypatch.setattr(sincronizador, "resincronizar_modificados", resync_falso)
    return llamadas


def test_v2_apagada_mantiene_el_comportamiento_anterior(nocturna, monkeypatch):
    monkeypatch.delenv(resync.VARIABLE_ACTIVACION, raising=False)
    assert sincronizador.sincronizar_albaranes() == 0
    assert nocturna["nuevos"] == ["v1"] and nocturna["resync"] == 0
    assert "id_recepcion" not in nocturna["guardados"][0]


def test_v2_encendida_guarda_recepcion_y_resincroniza(nocturna, monkeypatch):
    monkeypatch.setenv(resync.VARIABLE_ACTIVACION, "1")
    assert sincronizador.sincronizar_albaranes() == 0
    assert nocturna["nuevos"] == ["v2"] and nocturna["resync"] == 1
    assert nocturna["guardados"][0]["id_recepcion"] == 777


def test_fallo_de_la_resincronizacion_no_deshace_los_nuevos(nocturna, monkeypatch):
    monkeypatch.setenv(resync.VARIABLE_ACTIVACION, "1")
    monkeypatch.setattr(sincronizador, "resincronizar_modificados",
                        lambda hoy=None: (_ for _ in ()).throw(RuntimeError("sin la 22")))
    assert sincronizador.sincronizar_albaranes() == sincronizador.CODIGO_RESYNC_CON_ERRORES
    assert len(nocturna["guardados"]) == 1


def test_informe_no_escribe_y_funciona_sin_la_22(monkeypatch, tmp_path):
    cliente = _Cliente({"facturas": [], "facturas_albaranes_extraidos": [],
                        "albaranes": [_supabase(contador=1), _supabase(contador=2)],
                        "conciliacion_albaranes_reservados": []})
    original = resync.leer_supabase

    def sin_columna(cli, farmacia, desde, hasta, *, con_recepcion):
        if con_recepcion:
            raise RuntimeError("column albaranes.id_recepcion does not exist")
        return original(cli, farmacia, desde, hasta, con_recepcion=False)

    monkeypatch.setattr(resync, "leer_supabase", sin_columna)
    monkeypatch.setattr(sincronizador, "obtener_cliente_supabase", lambda: cliente)
    monkeypatch.setattr(sincronizador, "obtener_albaranes_entre_fechas",
                        lambda d, h: [_albaran(contador=1, puc=11), _albaran(contador=3)])
    monkeypatch.setattr(sincronizador, "obtener_albaranes_por_contadores", lambda cs: [])
    contenido = sincronizador.generar_informe(tmp_path / "informe.json", hoy=date(2026, 10, 22))
    assert cliente.escrituras == []
    assert contenido["esquema_22"] is False
    assert contenido["resumen"] == {"nuevos": 1, "cambios": 1, "reaparecidos": 0, "ausentes": 1, "iguales": 0}
    assert (tmp_path / "informe.json").exists()


def test_informe_rechaza_salida_dentro_del_repositorio():
    with pytest.raises(SystemExit, match="SALIDA_DENTRO_DEL_REPOSITORIO"):
        sincronizador.main(["--informe", str(ROOT / "informe.json")])


# --------------------------------------------------------------------------- Farmatic: solo lectura

class _CursorFalso:
    def __init__(self, registro):
        self.registro = registro

    def execute(self, consulta, *parametros):
        self.registro.append((validar_consulta_lectura(consulta), parametros))

    def fetchall(self):
        return []


class _ConexionFalsa:
    def __init__(self, registro):
        self.registro = registro

    def cursor(self):
        return _CursorFalso(self.registro)

    def close(self):
        pass


def test_consultas_2bd_son_select_y_enlazan_la_recepcion_por_el_albaran(monkeypatch):
    registro: list = []
    monkeypatch.setattr(lectura, "obtener_conexion", lambda: _ConexionFalsa(registro))
    lectura.obtener_nuevos_albaranes_con_recepcion(10)
    lectura.obtener_albaranes_entre_fechas(date(2026, 4, 1), date(2026, 6, 1))
    lectura.obtener_albaranes_por_contadores(list(range(1, 1201)))
    assert len(registro) == 2 + 3  # 1.200 contadores en lotes de 500
    for consulta, _ in registro:
        texto = " ".join(consulta.split())
        assert texto.upper().startswith("SELECT")
        assert "FROM dbo.AlbaranRecep AS ar WHERE ar.IdProveedor = a.IdProveedor AND ar.IdAlbaran = a.IdAlbaran" in texto
        assert "XProv_IdProveedor" not in texto and "dbo.Recep " not in texto
    assert [len(p) for _, p in registro[2:]] == [500, 500, 200]


def test_conversion_lleva_la_recepcion_si_la_consulta_la_trae():
    class Fila:
        IdContador, IdProveedor, Proveedor, IdAlbaran = 1, "0002 ", "SAFA ", "08X "
        Fecha, ImportePVP, ImportePUC, Dto = datetime(2026, 7, 1), 2.0, 1.0, 0.0

    assert lectura.convertir_fila_en_albaran(Fila()).id_recepcion is None
    Fila.IdRecepcion = 50898
    assert lectura.convertir_fila_en_albaran(Fila()).id_recepcion == 50898


def test_tarea_nocturna_sigue_sin_importar_runtime_supabase():
    """Garantía del 2BA-D: el nuevo núcleo no arrastra la conciliación a la tarea nocturna."""
    for modulo in ("src/supabase_client/resincronizacion_albaranes.py", "src/sincronizar_albaranes.py"):
        arbol = ast.parse((ROOT / modulo).read_text(encoding="utf-8"))
        importados = {n.module for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and n.module}
        importados |= {a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
        assert not [m for m in importados if "runtime_supabase" in m], modulo
