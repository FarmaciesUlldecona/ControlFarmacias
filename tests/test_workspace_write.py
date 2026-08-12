import subprocess
from pathlib import Path

import orquestador
from orquestador_snapshot import comparar_snapshots, tomar_snapshot


ROOT = Path(__file__).resolve().parents[1]
RUTA_PERMITIDA = "sandbox_permitido/**"


def _crear_repo_temporal(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return repo


def _validar_delta_workspace_write(repo: Path, antes):
    despues = tomar_snapshot(repo)
    cambios = comparar_snapshots(antes, despues)
    rutas_protegidas = orquestador.cargar_json(ROOT / "config.json")[
        "rutas_protegidas"
    ]
    resultado = orquestador.validar_rutas(
        cambios.paths_cambiados,
        rutas_permitidas=[RUTA_PERMITIDA],
        rutas_protegidas=rutas_protegidas,
        permitir_escritura=True,
    )
    return cambios, resultado


def test_workspace_write_permite_archivo_dentro_de_ruta(tmp_path):
    repo = _crear_repo_temporal(tmp_path)
    antes = tomar_snapshot(repo)

    destino = repo / "sandbox_permitido" / "resultado.txt"
    destino.parent.mkdir()
    destino.write_text("contenido ficticio permitido\n", encoding="utf-8")

    cambios, (ok, problemas) = _validar_delta_workspace_write(repo, antes)

    assert cambios.paths_cambiados == {"sandbox_permitido/resultado.txt"}
    assert ok
    assert problemas == []


def test_workspace_write_bloquea_archivo_fuera_de_ruta(tmp_path):
    repo = _crear_repo_temporal(tmp_path)
    antes = tomar_snapshot(repo)

    (repo / "fuera_de_ruta.txt").write_text(
        "contenido ficticio fuera de allowlist\n", encoding="utf-8"
    )

    cambios, (ok, problemas) = _validar_delta_workspace_write(repo, antes)

    assert cambios.paths_cambiados == {"fuera_de_ruta.txt"}
    assert not ok
    assert problemas == ["Cambio fuera de la allowlist: fuera_de_ruta.txt"]
