from __future__ import annotations

from pathlib import Path

import pytest

from interfaz_operativa import ProveedorContextoOperativo
from lenguaje_natural import OrdenInterpretada, TipoAccionNatural, TipoIntencion


ORDENES_NATURALES = (
    ("mira cómo está Alliance", "PROGRAMA", False, "read_only"),
    ("comprueba Alliance", "PROGRAMA", False, "read_only"),
    ("dime si Alliance está preparado", "PROGRAMA", False, "read_only"),
    ("revisa en Programa el estado de Alliance", "PROGRAMA", False, "read_only"),
    ("comprueba en Programa el estado actual de Alliance y dime si está preparado para iniciar el extractor local completo. No modifiques archivos.", "PROGRAMA", False, "read_only"),
    ("revisa Cofares y dime qué queda pendiente", "PROGRAMA", False, "read_only"),
    ("cómo va Hefame", "PROGRAMA", False, "read_only"),
    ("comprueba si Fedefarma está listo para empezar", "PROGRAMA", False, "read_only"),
    ("mira el normalizador", "PROGRAMA", False, "read_only"),
    ("dime qué falta en el normalizador de Cofares", "PROGRAMA", False, "read_only"),
    ("revisa las facturas sin modificar nada", "PROGRAMA", False, "read_only"),
    ("comprueba los albaranes", "PROGRAMA", False, "read_only"),
    ("mira cómo está el orquestador", "ORQUESTADOR", False, "read_only"),
    ("comprueba git del orquestador", "ORQUESTADOR", False, "read_only"),
    ("dime qué presupuesto queda", None, False, "read_only"),
    ("cuánto hemos gastado de Codex esta semana", None, False, "read_only"),
    ("ejecuta los tests del orquestador", "ORQUESTADOR", False, "read_only"),
    ("pasa los tests focales", None, True, "read_only"),
    ("revisa este repo", "ORQUESTADOR", False, "read_only"),
    ("comprueba este módulo", "ORQUESTADOR", False, "read_only"),
    ("corrige Cofares y valida que quede bien, pero no hagas commit", "PROGRAMA", False, "workspace_write"),
    ("arregla el extractor de Alliance sin hacer push", "PROGRAMA", False, "workspace_write"),
    ("mejora Hefame y pasa los tests", "PROGRAMA", False, "workspace_write"),
    ("solo dime cómo está Fedefarma, no cambies nada", "PROGRAMA", False, "read_only"),
    ("audita el normalizador pero no modifiques archivos", "PROGRAMA", False, "read_only"),
    ("haz commit", None, True, "read_only"),
    ("no hagas commit", None, True, "read_only"),
    ("haz push", None, True, "read_only"),
    ("no hagas push", None, True, "read_only"),
    ("modifica Farmatic", "PROGRAMA", False, "workspace_write"),
    ("verifica Cencora", "PROGRAMA", False, "read_only"),
    ("consulta la situación de Cofares", "PROGRAMA", False, "read_only"),
    ("analiza el proveedor HEFAME", "PROGRAMA", False, "read_only"),
    ("averigua qué falta en Fedefarma", "PROGRAMA", False, "read_only"),
    ("examina las facturas", "PROGRAMA", False, "read_only"),
    ("revisa los proveedores", "PROGRAMA", False, "read_only"),
    ("mira la conciliación", "PROGRAMA", False, "read_only"),
    ("comprueba el banco", "PROGRAMA", False, "read_only"),
    ("cómo está el cashflow", "PROGRAMA", False, "read_only"),
    ("verifica los pedidos", "PROGRAMA", False, "read_only"),
    ("examina los laboratorios", "PROGRAMA", False, "read_only"),
    ("revisa Supabase", "PROGRAMA", False, "read_only"),
    ("consulta Farmatic en solo lectura", "PROGRAMA", False, "read_only"),
    ("revisa el comando cf", "ORQUESTADOR", False, "read_only"),
    ("analiza la CLI", "ORQUESTADOR", False, "read_only"),
    ("comprueba el routing", "ORQUESTADOR", False, "read_only"),
    ("mira LOCAL_ONLY", "ORQUESTADOR", False, "read_only"),
    ("revisa CODEX_LIGHT", "ORQUESTADOR", False, "read_only"),
    ("analiza CODEX_STANDARD", "ORQUESTADOR", False, "read_only"),
    ("audita CODEX_HEAVY", "ORQUESTADOR", False, "read_only"),
    ("comprueba el supervisor", "ORQUESTADOR", False, "read_only"),
    ("revisa el parser del orquestador", "ORQUESTADOR", False, "read_only"),
    ("mira el launcher", "ORQUESTADOR", False, "read_only"),
    ("arregla Cofares", "PROGRAMA", False, "workspace_write"),
    ("implementa la mejora de HEFAME", "PROGRAMA", False, "workspace_write"),
    ("añade soporte al normalizador", "PROGRAMA", False, "workspace_write"),
    ("crea el adaptador de Fedefarma", "PROGRAMA", False, "workspace_write"),
    ("adapta el proveedor Alliance", "PROGRAMA", False, "workspace_write"),
    ("completa el extractor de Alliance", "PROGRAMA", False, "workspace_write"),
    ("termina la integración de Cencora", "PROGRAMA", False, "workspace_write"),
    ("prepara el normalizador de Cofares", "PROGRAMA", False, "workspace_write"),
    ("desarrolla el parser del orquestador", "ORQUESTADOR", False, "workspace_write"),
    ("revisa Alliance, solo consulta", "PROGRAMA", False, "read_only"),
    ("consulta Cofares y no escribas", "PROGRAMA", False, "read_only"),
    ("analiza HEFAME sin Codex", "PROGRAMA", False, "read_only"),
    ("revisa Fedefarma sin API", "PROGRAMA", False, "read_only"),
    ("mira Alliance y no llames a servicios externos", "PROGRAMA", False, "read_only"),
    ("comprueba Cofares y no gastes", "PROGRAMA", False, "read_only"),
    ("revisa en ControlFarmacias Programa las facturas", "PROGRAMA", False, "read_only"),
    ("analiza en el repo del Orquestador la CLI", "ORQUESTADOR", False, "read_only"),
    ("mira aquí", "ORQUESTADOR", False, "read_only"),
    ("comprueba este repositorio", "ORQUESTADOR", False, "read_only"),
    ("revisa Cofares y HEFAME", "PROGRAMA", False, "read_only"),
    ("comprueba Alliance, Cencora y Fedefarma", "PROGRAMA", False, "read_only"),
    ("arregla eso", None, True, "read_only"),
    ("mira aquello", None, True, "read_only"),
    ("trabaja en Programa y Orquestador a la vez", None, True, "read_only"),
    ("haz lo que creas", None, True, "read_only"),
    ("revisa Alliance y el routing", None, True, "read_only"),
    ("trabaja en V0.1.3", None, True, "read_only"),
)


@pytest.fixture
def contexto(tmp_path: Path) -> dict:
    orquestador = tmp_path / "orquestador"
    programa = tmp_path / "programa"
    for repo in (orquestador, programa):
        (repo / "tests").mkdir(parents=True)
    (orquestador / "tests" / "test_cli_operativo_v0212.py").write_text("", encoding="utf-8")
    for nombre in ("cofares", "hefame", "fedefarma", "normalizador"):
        (programa / "tests" / f"test_{nombre}.py").write_text("", encoding="utf-8")

    def datos(nombre: str, repo: Path) -> dict:
        return {
            "nombre": nombre, "repo": str(repo), "worktree": str(repo),
            "rama": "test", "commit_inicial": "0" * 40,
            "rutas_permitidas": ["**"], "rutas_protegidas": [".git/**"],
        }

    actual = datos("ORQUESTADOR", orquestador)
    return {"repos": {
        "ORQUESTADOR": actual,
        "PROGRAMA": datos("PROGRAMA", programa),
        "ACTUAL": actual,
    }}


@pytest.mark.parametrize("texto,proyecto,ambigua,modo", ORDENES_NATURALES)
def test_bateria_de_ordenes_naturales(texto, proyecto, ambigua, modo, contexto):
    orden = OrdenInterpretada.desde_dict(
        ProveedorContextoOperativo().interpretar(texto, contexto)
    )
    assert orden.ambigua is ambigua
    assert orden.modo_solicitado == modo
    assert orden.metadata.get("proyecto") == proyecto


def test_bateria_supera_sesenta_frases():
    assert len(ORDENES_NATURALES) >= 60
    assert len({texto for texto, *_ in ORDENES_NATURALES}) == len(ORDENES_NATURALES)


def test_workspace_y_entidades_quedan_separados(contexto):
    orden = OrdenInterpretada.desde_dict(
        ProveedorContextoOperativo().interpretar(
            "comprueba el normalizador de Fedefarma", contexto
        )
    )
    assert orden.metadata["proyecto"] == "PROGRAMA"
    assert orden.metadata["entidades"] == ["FEDEFARMA", "NORMALIZADOR"]
    assert orden.acciones[0].tipo is TipoAccionNatural.ANALIZAR_ALCANCE


def test_restricciones_naturales_y_negaciones(contexto):
    texto = "revisa Alliance sin Codex, sin API, no hagas commit y no hagas push"
    orden = OrdenInterpretada.desde_dict(
        ProveedorContextoOperativo().interpretar(texto, contexto)
    )
    assert {"NO_CODEX", "NO_API_EXTERNA", "NO_COMMIT", "NO_PUSH"} <= set(orden.restricciones)
    assert not orden.commit and not orden.push and not orden.autorizaciones.escritura


def test_farmatic_write_se_mantiene_como_accion_bloqueable(contexto):
    orden = OrdenInterpretada.desde_dict(
        ProveedorContextoOperativo().interpretar("modifica Farmatic", contexto)
    )
    assert orden.acciones[0].tipo is TipoAccionNatural.ESCRIBIR_FARMATIC
    assert orden.tipo_intencion is TipoIntencion.CREAR_TAREA


def test_cwd_fuera_de_repos_conocidos_requiere_aclaracion(contexto):
    contexto = {"repos": {k: v for k, v in contexto["repos"].items() if k != "ACTUAL"}}
    orden = OrdenInterpretada.desde_dict(
        ProveedorContextoOperativo().interpretar("revisa este repo", contexto)
    )
    assert orden.ambigua and orden.repo_candidato is None
