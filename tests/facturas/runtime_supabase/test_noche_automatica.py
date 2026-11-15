"""Hito AUTO-A: piezas del orquestador nocturno y del compositor automatico, sin base de datos ni Docker.

Diseno: pruebas/auditoria_auto_alliance/DISENO.md. Lo que toca la base (claims, snapshot, simulacion, migracion 32)
se prueba en ``test_integracion_pg17_32_auto_alliance.py``.
"""
from __future__ import annotations

import datetime as dt
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

from src.facturas.runtime_supabase import noche_automatica as na
from src.facturas.runtime_supabase.clasificacion_fallos import NO_SOPORTADO, clasificar_fallo
from src.facturas.runtime_supabase.compositor_automatico import (
    AUTORIDAD_COMPOSITOR_AUTOMATICO,
    ExtractorDocumentalAutorizadoAutomatico,
    autoridad_automatica_habilitada,
)
from src.facturas.runtime_supabase.compositor_manual import CAMPOS_REQUERIDOS_MANUAL, autoridad_manual_habilitada
from src.facturas.runtime_supabase.lectura_readonly import LectorReadOnly

HOY = dt.date(2026, 11, 13)


# --------------------------------------------------------------------------- limites (D5)


def _noche(modo, resultado, dia):
    return {"fecha": f"2026-11-{dia:02d}", "modo": modo, "resultado": resultado}


@pytest.mark.parametrize("previas, esperado", [
    ([], (5, 5)),
    ([_noche("REAL", "NOCHE_OK", 12), _noche("REAL", "FIN_LIMITE", 11)], (5, 5)),
    ([_noche("REAL", "NOCHE_OK", 12), _noche("REAL", "FIN_LIMITE", 11), _noche("REAL", "NOCHE_OK", 10)], (20, 20)),
    # Las noches SOMBRA no cuentan ni cortan.
    ([_noche("REAL", "NOCHE_OK", 12), _noche("SOMBRA", "NOCHE_OK", 11), _noche("REAL", "NOCHE_OK", 10),
      _noche("REAL", "NOCHE_OK", 9)], (20, 20)),
    ([_noche("SOMBRA", "NOCHE_OK", d) for d in (12, 11, 10, 9)], (5, 5)),
    # Una PARADA reinicia la cuenta: hacen falta 3 buenas despues de ella.
    ([_noche("REAL", "NOCHE_OK", 12), _noche("REAL", "NOCHE_OK", 11), _noche("REAL", "PARADA", 10),
      _noche("REAL", "NOCHE_OK", 9), _noche("REAL", "NOCHE_OK", 8), _noche("REAL", "NOCHE_OK", 7)], (5, 5)),
])
def test_limites_por_historial(previas, esperado):
    assert na.limites_por_historial(previas) == esperado


# --------------------------------------------------------------------------- puertas


def _tareas(ultima="2026-11-13T20:30:30.0000000Z", resultado=0, *, quitar=None):
    tareas = [{"nombre": n, "ultima": ultima, "resultado": resultado} for n in na.TAREAS_PREVIAS if n != quitar]
    return {"tareas": tareas}


def test_puertas_tareas_de_esta_noche_ok():
    fecha = dt.datetime.fromisoformat("2026-11-13T20:30:30+00:00").astimezone().date()
    assert na.puertas_tareas(_tareas(), fecha) == []


@pytest.mark.parametrize("info, fallo", [
    (_tareas(resultado=na.RESULTADO_EN_EJECUCION), "TAREA_EN_EJECUCION"),
    (_tareas(resultado=1), "TAREA_CON_ERROR"),
    (_tareas(ultima="2026-11-10T20:30:30.0000000Z"), "TAREA_NO_EJECUTADA_ESTA_NOCHE"),
    (_tareas(ultima=None), "TAREA_SIN_EJECUCION"),
    (_tareas(quitar=na.TAREAS_PREVIAS[1]), "TAREA_NO_ENCONTRADA"),
    ({"error": "sin permiso"}, "TAREAS_NO_DETERMINABLES"),
])
def test_puertas_tareas_paran(info, fallo):
    fecha = dt.datetime.fromisoformat("2026-11-13T20:30:30+00:00").astimezone().date()
    assert any(f.startswith(fallo) for f in na.puertas_tareas(info, fecha))


CFG_OK = {"luna_habilitada": False, "farmacias_habilitadas": ["PIO"], "normalizacion_automatica": True,
          "conciliacion_automatica": True, "tolerancia_conciliacion": "0.0500",
          "conciliacion_tolerancia_suelo": "0.0500", "conciliacion_tolerancia_por_albaran": "0.0100",
          "conciliacion_tolerancia_tope": "0.5000"}
OP_OK = {"locks_documentos": 0, "claims_conciliacion": 0, "normalizando": 0}
MARCAS_OK = {"x": True}


def _puertas(modo="REAL", cfg=None, op=None, marcas=None, git=(), previas=()):
    noche = na.Noche(fecha=HOY, modo=modo, inicio=dt.datetime.now(dt.timezone.utc))
    fecha = dt.datetime.fromisoformat("2026-11-13T20:30:30+00:00").astimezone().date()
    return na.puertas(noche, {**CFG_OK, **(cfg or {})}, {**OP_OK, **(op or {})}, marcas or MARCAS_OK, _tareas(),
                      list(git), list(previas), fecha)


def test_puertas_ok_en_real():
    assert _puertas() == []


def test_puertas_ok_en_sombra_con_flags_apagados():
    assert _puertas("SOMBRA", {"normalizacion_automatica": False, "conciliacion_automatica": False}) == []


@pytest.mark.parametrize("kwargs, fallo", [
    ({"modo": "SOMBRA"}, "SOMBRA_CON_FLAGS_ENCENDIDOS"),
    ({"cfg": {"normalizacion_automatica": False, "conciliacion_automatica": False}}, "REAL_CON_FLAGS_APAGADOS"),
    ({"cfg": {"luna_habilitada": True}}, "LUNA_NO_APAGADA"),
    ({"cfg": {"farmacias_habilitadas": ["PIO", "RITA"]}}, "FARMACIAS_NO_SOLO_PIO"),
    ({"cfg": {"conciliacion_tolerancia_tope": "0.6000"}}, "TOLERANCIA_NO_CERTIFICADA"),
    ({"cfg": {"tolerancia_conciliacion": "0.0600"}}, "TOLERANCIA_NO_CERTIFICADA"),
    ({"op": {"normalizando": 1}}, "NORMALIZANDO_DISTINTO_DE_0"),
    ({"op": {"claims_conciliacion": 2}}, "CLAIMS_CONCILIACION_DISTINTO_DE_0"),
    ({"marcas": {"cf_noches_automaticas": False}}, "MIGRACION_AUSENTE"),
    ({"git": ["GIT_ARBOL_NO_LIMPIO"]}, "GIT_ARBOL_NO_LIMPIO"),
    ({"previas": [_noche("REAL", "EN_CURSO", 12)]}, "NOCHE_ANTERIOR_SIN_CERRAR"),
])
def test_puertas_paran(kwargs, fallo):
    assert any(f.startswith(fallo) for f in _puertas(**kwargs))


# --------------------------------------------------------------------------- postcheck por fila (2AX)


def test_postcheck_solo_filas_de_lo_procesado():
    pre = {"documentos_facturas": {"d1": ["h1", "d1", None], "d2": ["h2", "d2", None]},
           "facturas": {"f9": ["h9", "d9", "f9"]},
           "albaranes": {"a1": ["ha", None, None]}}
    post = {"documentos_facturas": {"d1": ["h1b", "d1", None], "d2": ["h2", "d2", None]},
            # factura nueva del documento procesado y factura conciliada
            "facturas": {"f9": ["h9b", "d9", "f9"], "f1": ["hf", "d1", "f1"]},
            "conciliacion_detalles": {"x": ["hx", None, "f9"]},
            "albaranes": {"a1": ["ha", None, None]}}
    informe = na.postcheck_por_fila(pre, post, {"d1"}, {"f9"})
    assert informe["veredicto"] == "POSTCHECK_OK"
    assert informe["filas_cambiadas_por_tabla"] == {"documentos_facturas": 1, "facturas": 2,
                                                    "conciliacion_detalles": 1}


@pytest.mark.parametrize("tabla, fila", [
    ("albaranes", {"a1": ["otra", None, None]}),           # albaran cambiado: nadie es dueno
    ("documentos_facturas", {"d2": ["h2b", "d2", None]}),  # documento no procesado
    ("facturas", {}),                                       # fila desaparecida de una factura ajena
])
def test_postcheck_fila_ajena_es_parada(tabla, fila):
    pre = {"documentos_facturas": {"d2": ["h2", "d2", None]}, "facturas": {"f8": ["h8", "d8", "f8"]},
           "albaranes": {"a1": ["ha", None, None]}}
    post = {k: dict(v) for k, v in pre.items()}
    post[tabla] = fila
    informe = na.postcheck_por_fila(pre, post, {"d1"}, {"f9"})
    assert informe["veredicto"] == "POSTCHECK_FILAS_AJENAS"
    assert informe["filas_ajenas"][0]["tabla"] == tabla


def test_trabajadores_fuera_del_2ax_y_comparados_aparte():
    """Mejora aprobada por Pio (2026-11-13): Trabajadores se informa aparte y nunca hace fallar el postcheck."""
    assert na.TABLAS_TRABAJADORES <= na.TABLAS_FUERA_DEL_SNAPSHOT
    pre = {"tablas": {"trabajadoras": {"t1": "h1"}, "festivos": {}}}
    post = {"tablas": {"trabajadoras": {"t1": "h1b", "t2": "h2"}, "festivos": {}}}
    assert na.cambios_trabajadores(pre, post) == {"afecta_al_veredicto": False,
                                                  "filas_cambiadas_por_tabla": {"trabajadoras": 2}}
    # Sin lectura (p. ej. sin privilegio) solo se anota; no hay veredicto.
    informe = na.cambios_trabajadores(pre, {"error": "InsufficientPrivilege"})
    assert informe == {"afecta_al_veredicto": False, "no_comparable": {"pre": None, "post": "InsufficientPrivilege"}}


class _LectorRoto:
    def __enter__(self):
        raise RuntimeError("sin privilegio")

    def __exit__(self, *_):
        return False


def test_snapshot_trabajadores_no_corta_la_noche():
    entorno = na.Entorno(abrir_lectura=_LectorRoto, cliente=None, tareas=dict, puerta_git=lambda: (None, []),
                         construir_worker=lambda cfg: None, directorio_informes=Path("."))
    assert na.snapshot_trabajadores(entorno) == {"error": "RuntimeError"}


# --------------------------------------------------------------------------- criterios


@pytest.mark.parametrize("nombre, alliance", [
    ("ALLIANCE HEALTHCARE ESPANA", True), ("1.- SAFA", True), ("6- PLATAF. ECO360 AH", True), ("CENCORA", True),
    ("3.- HEFAME", False), ("COFARES", False), (None, False)])
def test_es_alliance_con_el_criterio_de_la_conciliacion(nombre, alliance):
    assert na.es_alliance({"proveedor_nombre": nombre, "proveedor_literal": None}) is alliance


def test_numeros_de_un_cambio_r18():
    assert na._numeros_de_cambio("numero_albaran", "0008D33181") == {"8D33181"}
    assert na._numeros_de_cambio("identidad", '{"numero_albaran": "08D33182", "proveedor": "SAFA"}') == {"8D33182"}
    assert na._numeros_de_cambio("importe_puc", "12.30") == set()
    assert na._numeros_de_cambio("numero_albaran", None) == set()


# --------------------------------------------------------------------------- compositor automatico (D1)


def test_autoridad_automatica_solo_alliance_certificada():
    assert dict(AUTORIDAD_COMPOSITOR_AUTOMATICO) and all(
        v == ("alliance-local", "1.3.1") for v in AUTORIDAD_COMPOSITOR_AUTOMATICO.values())
    assert autoridad_automatica_habilitada("alliance-local", "1.3.1") is True
    # Pio, 2026-11-14: la 1.3.0 (sin "ENCARGO") deja de estar certificada para la ruta automatica.
    assert autoridad_automatica_habilitada("alliance-local", "1.3.0") is False
    assert autoridad_automatica_habilitada("alliance-local", "1.2.0") is False
    assert autoridad_automatica_habilitada("alliance-local", None) is False
    for layout in ("hefame-local", "cofares-local", "fedefarma-local", None, "inventado"):
        assert autoridad_automatica_habilitada(layout, "1.3.1") is False
    # El compositor manual no cambia.
    assert autoridad_manual_habilitada("alliance-local") is True


class _Local:
    def __init__(self, layout, version):
        self.documento = {"layout": layout, "layout_version": version, "sha256": "0" * 64, "pages": 1,
                          "source": "x.pdf"}
        self.incidencias, self.facturas, self.documento_completo_demostrado = [], [], True


@pytest.mark.parametrize("layout, version", [("alliance-local", "1.2.0"), ("alliance-local", "1.3.0"),
                                             ("hefame-local", "1.0.0")])
def test_extractor_automatico_sin_autoridad_es_no_soportado(layout, version):
    extractor = ExtractorDocumentalAutorizadoAutomatico(crear_motor=lambda: type(
        "M", (), {"extraer": lambda self, ruta: _Local(layout, version)})())
    etapa = extractor.extraer(Path("x.pdf"), CAMPOS_REQUERIDOS_MANUAL)
    assert etapa.valores == {}
    assert etapa.provenance["motivo"] == "PROVEEDOR_NO_SOPORTADO_AUTOMATICO"
    assert clasificar_fallo("DocumentoNoAptoManual", "PROVEEDOR_NO_SOPORTADO_AUTOMATICO") == NO_SOPORTADO


def test_extractor_automatico_sin_layout_conserva_el_motivo_del_manual():
    extractor = ExtractorDocumentalAutorizadoAutomatico(crear_motor=lambda: type(
        "M", (), {"extraer": lambda self, ruta: _Local(None, None)})())
    assert extractor.extraer(Path("x.pdf"), CAMPOS_REQUERIDOS_MANUAL).provenance["motivo"] == "PROVEEDOR_NO_RECONOCIDO"


def test_compositor_automatico_rechaza_luna_y_farmacias():
    from src.facturas.runtime_supabase.compositor_automatico import construir_worker_automatico_productivo
    from src.facturas.runtime_supabase.modelos import ConfiguracionRuntime

    with pytest.raises(ValueError, match="LUNA"):
        construir_worker_automatico_productivo(object(), ConfiguracionRuntime(luna_habilitada=True), "w", Path("."))
    with pytest.raises(ValueError, match="SOLO_PIO"):
        construir_worker_automatico_productivo(
            object(), ConfiguracionRuntime(farmacias_habilitadas=("PIO", "RITA")), "w", Path("."))
    with pytest.raises(ValueError, match="TOLERANCIA"):
        construir_worker_automatico_productivo(
            object(), ConfiguracionRuntime(tolerancia_conciliacion=Decimal("0.0600")), "w", Path("."))


# --------------------------------------------------------------------------- lector READ_ONLY


class _Cursor:
    def __init__(self, ro="on", iso="repeatable read"):
        self.ro, self.iso, self.ejecutadas = ro, iso, []

    def execute(self, sql, params=None):
        self.ejecutadas.append(sql)

    def fetchall(self):
        return [(self.ro, self.iso)]


def test_lector_exige_sesion_read_only_y_solo_select():
    with pytest.raises(PermissionError, match="SESION_NO_READ_ONLY"):
        LectorReadOnly(_Cursor(ro="off"))
    lector = LectorReadOnly(_Cursor())
    for sentencia in ("update public.facturas set x = 1", "insert into t values (1)", "delete from t",
                      "select 1; delete from t" if False else "call f()"):
        with pytest.raises(PermissionError, match="SENTENCIA_NO_SELECT"):
            lector.filas(sentencia)


# --------------------------------------------------------------------------- puerta git y main


def _git(ruta, *args):
    return subprocess.run(["git", "-C", str(ruta), "-c", "user.name=t", "-c", "user.email=t@local", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repos(tmp_path):
    origen = tmp_path / "origen.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origen)], check=True)
    trabajo = tmp_path / "trabajo"
    subprocess.run(["git", "clone", "-q", str(origen), str(trabajo)], check=True, capture_output=True)
    (trabajo / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(trabajo, "add", ".")
    _git(trabajo, "commit", "-q", "-m", "inicial")
    _git(trabajo, "branch", "-M", "main")
    _git(trabajo, "push", "-q", "origin", "main")
    return trabajo


def test_puerta_git_limpia_e_igual(repos):
    commit, fallos = na.puerta_git(repos)
    assert fallos == [] and len(commit) == 40


def test_puerta_git_arbol_sucio(repos):
    (repos / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert na.puerta_git(repos)[1] == ["GIT_ARBOL_NO_LIMPIO"]


def test_puerta_git_por_delante_solo_documentacion(repos):
    (repos / "docs").mkdir()
    (repos / "docs" / "n.md").write_text("nota\n", encoding="utf-8")
    _git(repos, "add", ".")
    _git(repos, "commit", "-q", "-m", "doc")
    assert na.puerta_git(repos)[1] == []
    (repos / "b.py").write_text("y = 1\n", encoding="utf-8")
    _git(repos, "add", ".")
    _git(repos, "commit", "-q", "-m", "codigo")
    assert na.puerta_git(repos)[1] == ["GIT_HEAD_DISTINTO_DE_ORIGIN_MAIN"]


def test_puerta_git_sin_repositorio(tmp_path):
    commit, fallos = na.puerta_git(tmp_path)
    assert commit is None and fallos[0].startswith("GIT_NO_DETERMINABLE")


def test_main_rechaza_modo_e_informes_dentro_del_repositorio():
    with pytest.raises(SystemExit, match="uso"):
        na.main(["OTRO", "C:/x"])
    with pytest.raises(SystemExit, match="INFORMES_DENTRO_DEL_REPOSITORIO"):
        na.main(["SOMBRA", str(na.ROOT / "informes")])


# Claves FICTICIAS con el formato real de Supabase (no son credenciales; nunca se lee el fichero de credenciales).
CLAVE_SECRETA_FICTICIA = "sb_secret_" + "F1ct1c1aNoValida0123456789ab"
CLAVE_PUBLICABLE_FICTICIA = "sb_publishable_" + "F1ct1c1aNoValida0123456789ab"
TOKEN_FICTICIO = "eyJhbGciOiJIUzI1NiJ9.eyJmaWN0aWNpYSI6dHJ1ZX0.ZmljdGljaWE"


@pytest.mark.parametrize("clave, servicio", [
    (CLAVE_SECRETA_FICTICIA, True),          # sb_secret_ = clave de servicio
    (CLAVE_PUBLICABLE_FICTICIA, False),      # sb_publishable_ = anon: rechazada
    (TOKEN_FICTICIO, False),                 # otro formato (token): rechazado
    ("sb_secret_", False), (" " + CLAVE_SECRETA_FICTICIA, False), ("", False), (None, False),
    ("SB_SECRET_" + "x" * 20, False), ("clave-cualquiera", False),
])
def test_solo_sb_secret_es_clave_de_servicio(clave, servicio):
    """DECISION DE PIO (2026-11-14): causa de la parada de la primera noche de sombra (CLIENTE_NO_DEMOSTRADO)."""
    assert na._es_clave_de_servicio(clave) is servicio


@pytest.mark.parametrize("clave, acepta", [
    (CLAVE_SECRETA_FICTICIA, True), (CLAVE_PUBLICABLE_FICTICIA, False), (TOKEN_FICTICIO, False)])
def test_cliente_productivo_con_claves_ficticias(monkeypatch, clave, acepta):
    """Sin red ni fichero de credenciales: dotenv y la fabrica de clientes, sustituidos."""
    import dotenv
    import src.supabase_client.conexion_supabase as conexion_supabase

    entorno = {"SUPABASE_URL": f"https://{na.PROJECT_REF}.supabase.co", "SUPABASE_KEY": clave}
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: True)
    monkeypatch.setattr(dotenv, "dotenv_values", lambda *a, **k: dict(entorno))
    monkeypatch.setattr(conexion_supabase, "obtener_cliente_supabase", lambda: "CLIENTE_FICTICIO")
    if acepta:
        assert na._cliente_productivo() == "CLIENTE_FICTICIO"
    else:
        with pytest.raises(SystemExit, match="CLIENTE_NO_DEMOSTRADO"):
            na._cliente_productivo()
    # Otro proyecto: rechazado aunque la clave sea secreta.
    entorno.update(SUPABASE_URL="https://otroproyecto.supabase.co", SUPABASE_KEY=CLAVE_SECRETA_FICTICIA)
    with pytest.raises(SystemExit, match="CLIENTE_NO_DEMOSTRADO"):
        na._cliente_productivo()


def test_bat_lanza_el_orquestador_en_sombra():
    bat = (na.ROOT / "ejecutar_automatizacion_alliance.bat").read_text(encoding="utf-8")
    # Decision de Pio (2026-11-13): registro como el .bat de importacion, con la ruta completa de Python.
    log = "logs\\automatizacion_alliance.log"
    assert ("C:\\ControlFarmacias\\Programa\\.venv\\Scripts\\python.exe -m src.facturas.runtime_supabase."
            f"noche_automatica SOMBRA C:\\ControlFarmacias\\noches_auto >> {log} 2>&1") in bat
    assert "if not exist logs mkdir logs" in bat
    assert f"echo INICIO: %date% %time% >> {log}" in bat
    assert "set CODIGO_SALIDA=%ERRORLEVEL%" in bat
    assert f"echo CODIGO DE SALIDA: %CODIGO_SALIDA% >> {log}" in bat
    assert f"echo FIN: %date% %time% >> {log}" in bat
    assert bat.rstrip().endswith("exit /b %CODIGO_SALIDA%")
    assert "noche_automatica REAL" not in bat
