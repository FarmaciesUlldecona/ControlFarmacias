from io import StringIO
import json
from pathlib import Path
import subprocess
import sys

import pytest

from cli_operativo import SesionCLI, construir_parser
from ejecucion_v02 import EjecutorCicloFake
from ejecutor_local import ResultadoEjecucionLocal
from interfaz_operativa import (
    ConfiguracionOperativa,
    ProveedorContextoOperativo,
    crear_orquestador_operativo,
)
from lenguaje_natural import OrdenInterpretada


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo(tmp_path: Path, nombre: str) -> tuple[Path, str]:
    repo = tmp_path / nombre
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    (repo / ".gitignore").write_text("estado/\n", encoding="utf-8")
    (repo / "modulo.py").write_text("VALOR = 1\n", encoding="utf-8")
    tests = repo / "tests"
    tests.mkdir()
    (tests / "test_cli_operativo_v0212.py").write_text(
        "def test_fixture():\n    assert True\n", encoding="utf-8"
    )
    (tests / "test_extractor_cofares.py").write_text(
        "def test_cofares():\n    assert True\n", encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=t@example.invalid",
         "commit", "-m", "fixture")
    return repo, _git(repo, "rev-parse", "HEAD")


class LocalFake:
    def __init__(self):
        self.llamadas = []

    def ejecutar(self, solicitud):
        self.llamadas.append(solicitud)
        return ResultadoEjecucionLocal(
            operacion=solicitud.operacion.value,
            exito=True,
            returncode=0,
            stdout="1 passed",
        )


@pytest.fixture
def entorno(tmp_path):
    orquestador, _ = _repo(tmp_path, "orquestador")
    programa, _ = _repo(tmp_path, "programa")
    (orquestador / "config.json").write_text(
        json.dumps({
            "repo": str(programa), "codex_exe": "codex", "modelo": "",
            "modelo_supervisor": "", "timeout_seconds": 30,
            "max_ciclos_default": 5, "rutas_protegidas": [".git/**", ".env"],
        }), encoding="utf-8",
    )
    _git(orquestador, "add", "config.json")
    _git(orquestador, "-c", "user.name=Test", "-c", "user.email=t@example.invalid",
         "commit", "-m", "config")
    config = ConfiguracionOperativa(orquestador, programa, Path(sys.executable), orquestador)
    fake = EjecutorCicloFake()
    local = LocalFake()
    app = crear_orquestador_operativo(
        config, ejecutor_factory=lambda _: fake, ejecutor_local=local
    )
    return app, fake, local, config


def _orden(entorno, texto: str):
    app, fake, local, _ = entorno
    assert app.iniciar().ok
    return app.procesar_orden(texto), fake, local, app


def _interpretar(config: ConfiguracionOperativa, texto: str) -> OrdenInterpretada:
    datos = ProveedorContextoOperativo().interpretar(
        texto, {"repos": config.repos_conocidos()}
    )
    return OrdenInterpretada.desde_dict(datos)


def test_a_estado_local_only_cero_codex(entorno):
    resultado, fake, _, _ = _orden(entorno, "estado")
    assert resultado.codigo == "LOCAL_STATUS_QUERY"
    assert fake.llamadas == []


def test_b_git_resuelve_orquestador_y_es_local(entorno):
    resultado, fake, _, _ = _orden(entorno, "comprueba git")
    assert resultado.codigo == "LOCAL_GIT_QUERY"
    assert resultado.datos["interpretacion"]["metadata"]["proyecto"] == "ORQUESTADOR"
    assert fake.llamadas == []


def test_c_presupuesto_es_local_y_humano(entorno):
    app, fake, _, _ = entorno
    salida = StringIO()
    sesion = SesionCLI(app, salida=salida)
    assert sesion.procesar("qué presupuesto queda") == 0
    texto = salida.getvalue()
    assert "LOCAL_WEEKLY_BUDGET_QUERY" in texto
    assert "3.80 EUR/semana" in texto
    assert fake.llamadas == []


def test_d_tests_focales_orquestador_son_locales(entorno):
    resultado, fake, local, _ = _orden(
        entorno, "ejecuta los tests focales del orquestador"
    )
    assert resultado.codigo == "LOCAL_TESTS_EXECUTED"
    assert resultado.datos["recursos"]["nivel_tests"] == "TEST_FOCAL"
    assert local.llamadas[0].rutas == ("tests/test_cli_operativo_v0212.py",)
    assert fake.llamadas == []


def test_e_este_modulo_usa_contexto_actual_resoluble(entorno):
    resultado, _, local, _ = _orden(entorno, "ejecuta los tests focales de este módulo")
    assert resultado.codigo == "LOCAL_TESTS_EXECUTED"
    assert local.llamadas


def test_f_referencia_ambigua_no_adivina(entorno):
    resultado, fake, _, _ = _orden(entorno, "corrige el asunto pendiente")
    assert resultado.codigo == "AMBIGUOUS_REFERENCE"
    assert resultado.requiere_intervencion and fake.llamadas == []


def test_f2_este_modulo_fuera_de_repos_pide_aclaracion(entorno, tmp_path):
    _, _, _, config = entorno
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    config_fuera = ConfiguracionOperativa(
        config.orquestador_repo, config.programa_repo, config.python, fuera
    )
    fake = EjecutorCicloFake()
    app = crear_orquestador_operativo(
        config_fuera, ejecutor_factory=lambda _: fake, ejecutor_local=LocalFake()
    )
    assert app.iniciar().ok
    resultado = app.procesar_orden("ejecuta los tests focales de este módulo")
    assert resultado.codigo == "AMBIGUOUS_REFERENCE"
    assert resultado.requiere_intervencion and fake.llamadas == []


def test_g_pequena_bootstrap_light_una_llamada_fake(entorno):
    resultado, fake, _, _ = _orden(
        entorno, "corrige un cambio pequeño en el orquestador y no hagas commit"
    )
    assert resultado.ok
    assert resultado.datos["recursos"]["nivel_recurso"] == "CODEX_LIGHT"
    assert len(fake.llamadas) == 1


def test_h_multiarchivo_bootstrap_standard(entorno):
    resultado, fake, _, _ = _orden(
        entorno, "modifica varios archivos del orquestador y valida los tests"
    )
    assert resultado.ok
    assert resultado.datos["recursos"]["nivel_recurso"] == "CODEX_STANDARD"
    assert resultado.datos["recursos"]["nivel_tests"] == "TEST_MODULO"
    assert len(fake.llamadas) == 1


def test_i_heavy_se_bloquea_antes_del_ejecutor(entorno):
    resultado, fake, _, _ = _orden(
        entorno, "audita de forma transversal varios módulos del orquestador"
    )
    assert resultado.codigo == "REQUIERE_OK_PIO_COSTE"
    assert resultado.datos["recursos"]["nivel_recurso"] == "CODEX_HEAVY"
    assert fake.llamadas == []


def test_j_farmatic_write_sigue_bloqueado(entorno):
    resultado, fake, _, _ = _orden(entorno, "modifica un dato en Farmatic")
    assert resultado.codigo == "ABSOLUTE_RULE_VIOLATION"
    assert fake.llamadas == []


@pytest.mark.parametrize("texto", ["haz commit", "haz push"])
def test_k_l_commit_push_sueltos_se_bloquean(texto, entorno):
    resultado, fake, _, _ = _orden(entorno, texto)
    assert resultado.requiere_intervencion
    assert resultado.codigo == "AMBIGUOUS_REFERENCE"
    assert fake.llamadas == []


@pytest.mark.parametrize("accion", ["haz commit", "haz push"])
def test_k_l_commit_push_en_orden_compuesta_detienen_todo(accion, entorno):
    resultado, fake, _, _ = _orden(
        entorno, f"corrige un cambio pequeño en el orquestador y {accion}"
    )
    assert resultado.codigo == "AMBIGUOUS_REFERENCE"
    assert resultado.requiere_intervencion and fake.llamadas == []


def test_m_json_es_valido_y_contiene_resultado_publico(entorno):
    app, _, _, _ = entorno
    salida = StringIO()
    sesion = SesionCLI(app, salida=salida)
    assert sesion.procesar("estado", como_json=True) == 0
    datos = json.loads(salida.getvalue())
    assert datos["resultado"]["codigo"] == "LOCAL_STATUS_QUERY"
    assert datos["presupuesto"]["codigo"] == "LOCAL_WEEKLY_BUDGET_QUERY"


def test_n_salida_humana_breve_sin_traceback(entorno):
    app, _, _, _ = entorno
    salida = StringIO()
    sesion = SesionCLI(app, salida=salida)
    sesion.procesar("estado")
    texto = salida.getvalue()
    assert "ORDEN: estado" in texto and "Traceback" not in texto
    assert '"datos"' not in texto


def test_o_interactivo_acepta_varias_ordenes_y_salir(entorno):
    app, fake, _, _ = entorno
    entrada = StringIO("estado\nqué presupuesto queda\nsalir\n")
    salida = StringIO()
    sesion = SesionCLI(app, entrada=entrada, salida=salida)
    assert sesion.interactivo() == 0
    assert salida.getvalue().count("ORDEN:") == 2
    assert fake.llamadas == []


def test_p_help_es_sencillo_y_menciona_seguridad():
    ayuda = construir_parser().format_help()
    assert "modo" not in ayuda.casefold() or "orden" in ayuda.casefold()
    assert "Farmatic" in ayuda and "--json" in ayuda


def test_p2_entrypoint_help_no_necesita_bootstrap(tmp_path):
    resultado = subprocess.run(
        [sys.executable, str(Path(__file__).parents[1] / "cli_operativo.py"), "--help"],
        cwd=tmp_path, capture_output=True, text=True, check=False,
    )
    assert resultado.returncode == 0
    assert "Farmatic" in resultado.stdout and "--json" in resultado.stdout


@pytest.mark.parametrize("termino", ["Cofares", "HEFAME", "normalizador"])
def test_q_programa_se_resuelve_para_terminos_productivos(termino, entorno):
    resultado, _, _, _ = _orden(
        entorno, f"corrige un cambio pequeño en {termino} y no hagas commit"
    )
    assert resultado.datos["interpretacion"]["metadata"]["proyecto"] == "PROGRAMA"


@pytest.mark.parametrize("texto", ["estado", "comprueba git del orquestador"])
def test_r_orquestador_se_resuelve(texto, entorno):
    resultado, _, _, _ = _orden(entorno, texto)
    if "git" in texto:
        assert resultado.datos["interpretacion"]["metadata"]["proyecto"] == "ORQUESTADOR"
    else:
        assert resultado.codigo == "LOCAL_STATUS_QUERY"


def test_s_orden_desconocida_falla_segura(entorno):
    resultado, fake, _, _ = _orden(entorno, "haz lo que consideres oportuno")
    assert resultado.requiere_intervencion and fake.llamadas == []


def test_t_aviso_presupuesto_cerca_es_visible(entorno):
    app, _, _, _ = entorno
    assert app.iniciar().ok
    app._arranque.contabilidad_recursos.registrar_coste_real(
        "previo", "3.04", task_id="previa", origen="fixture"
    )
    salida = StringIO()
    sesion = SesionCLI(app, salida=salida)
    sesion.procesar("qué presupuesto queda")
    assert "AVISO: presupuesto cerca del límite" in salida.getvalue()


def test_u_presupuesto_superado_bloquea(entorno):
    app, fake, _, _ = entorno
    assert app.iniciar().ok
    app._arranque.contabilidad_recursos.registrar_coste_real(
        "previo", "3.75", task_id="previa", origen="fixture"
    )
    # La estimación se inyecta en la interpretación como lo haría una orden con coste.
    proveedor = app._interprete_natural.proveedor
    original = proveedor.interpretar

    def con_coste(texto, contexto):
        datos = original(texto, contexto)
        datos["metadata"]["coste_estimado"] = 0.20
        return datos

    proveedor.interpretar = con_coste
    resultado = app.procesar_orden(
        "corrige un cambio pequeño en el orquestador y no hagas commit"
    )
    assert resultado.codigo == "REQUIERE_OK_PIO_COSTE"
    assert fake.llamadas == []


def test_v_entrada_shell_no_se_ejecuta(entorno):
    resultado, fake, _, _ = _orden(entorno, "powershell; Remove-Item -Recurse")
    assert resultado.requiere_intervencion and fake.llamadas == []


def test_w_orden_real_resuelve_programa_y_conserva_solo_lectura(entorno):
    texto = (
        "comprueba en Programa el estado actual de Alliance y dime si está "
        "preparado para iniciar el extractor local completo. No modifiques archivos."
    )
    resultado, fake, _, _ = _orden(entorno, texto)

    interpretacion = resultado.datos["interpretacion"]
    assert resultado.codigo != "AMBIGUOUS_REFERENCE"
    assert interpretacion["metadata"]["proyecto"] == "PROGRAMA"
    assert interpretacion["modo_solicitado"] == "read_only"
    assert "NO_MODIFICAR_ARCHIVOS" in interpretacion["restricciones"]
    assert interpretacion["autorizaciones"]["escritura"] is False
    assert len(fake.llamadas) <= 1


@pytest.mark.parametrize(
    "texto,proyecto",
    [
        ("comprueba en Programa el estado de Cofares", "PROGRAMA"),
        ("revisa HEFAME en Programa", "PROGRAMA"),
        ("revisa el normalizador", "PROGRAMA"),
        ("comprueba el estado del Orquestador", "ORQUESTADOR"),
        ("comprueba en el Orquestador el estado Git", "ORQUESTADOR"),
        ("revisa Programa y Alliance", "PROGRAMA"),
        ("revisa Programa, Cofares y HEFAME", "PROGRAMA"),
    ],
)
def test_x_repositorio_y_entidades_de_dominio_no_compiten(texto, proyecto, entorno):
    _, _, _, config = entorno
    orden = _interpretar(config, texto)
    assert not orden.ambigua
    assert orden.metadata["proyecto"] == proyecto


def test_y_programa_y_orquestador_no_fingen_un_repo_unico(entorno):
    _, _, _, config = entorno
    orden = _interpretar(config, "compara Programa y Orquestador")
    assert orden.ambigua
    assert orden.repo_candidato is None
    assert orden.worktree_candidato is None


@pytest.mark.parametrize("actual,proyecto", [("programa", "PROGRAMA"), ("orquestador", "ORQUESTADOR")])
def test_z_este_repo_usa_cwd(actual, proyecto, entorno):
    _, _, _, config = entorno
    cwd = config.programa_repo if actual == "programa" else config.orquestador_repo
    config_cwd = ConfiguracionOperativa(
        config.orquestador_repo, config.programa_repo, config.python, cwd
    )
    orden = _interpretar(config_cwd, "revisa este repo")
    assert not orden.ambigua
    assert orden.metadata["proyecto"] == proyecto


def test_aa_feedback_precede_a_una_tarea_codex(entorno):
    app, _, _, _ = entorno
    salida = StringIO()
    sesion = SesionCLI(app, salida=salida)
    sesion.procesar("comprueba Alliance")
    texto = salida.getvalue()
    assert "ORDEN ACEPTADA" in texto
    assert "PROYECTO: PROGRAMA" in texto
    assert "MODO: CODEX_STANDARD" in texto
    assert "CODEX: Se utilizará" in texto
    assert texto.index("ORDEN ACEPTADA") < texto.index("ORDEN: comprueba Alliance")


def test_ab_restriccion_sin_codex_devuelve_control_sin_invocarlo(entorno):
    resultado, fake, _, _ = _orden(entorno, "analiza Alliance sin Codex")
    assert resultado.codigo == "CODEX_PROHIBITED_BY_ORDER"
    assert resultado.requiere_intervencion
    assert fake.llamadas == []
