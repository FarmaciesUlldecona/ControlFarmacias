"""Catálogo único de workspaces del Orquestador operativo."""

from __future__ import annotations

from pathlib import Path


ORQUESTADOR_ACTIVO = Path(
    r"C:\ControlFarmacias\ControlFarmacias_Orquestador_V0_2_dev"
)
PROGRAMA = Path(r"C:\ControlFarmacias\Programa")

# Es la raíz histórica que aloja también el git-dir común del worktree activo.
# No forma parte de REPOS_OPERATIVOS y nunca se ofrece como destino por defecto.
ORQUESTADOR_V01_HISTORICO = Path(
    r"C:\ControlFarmacias\ControlFarmacias_Orquestador_V0_1_3"
)

REPOS_OPERATIVOS = {
    "ORQUESTADOR": ORQUESTADOR_ACTIVO,
    "PROGRAMA": PROGRAMA,
}


def repo_operativo_para_cwd(
    cwd: str | Path,
    repos_operativos: dict[str, str | Path] | None = None,
) -> str | None:
    """Devuelve el nombre operativo solo si ``cwd`` está dentro de él."""

    actual = Path(cwd).resolve()
    for nombre, raiz in (repos_operativos or REPOS_OPERATIVOS).items():
        try:
            actual.relative_to(Path(raiz).resolve())
            return nombre
        except ValueError:
            continue
    return None
