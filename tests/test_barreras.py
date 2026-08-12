import subprocess
from pathlib import Path

import orquestador
from orquestador_snapshot import comparar_snapshots, tomar_snapshot


ROOT = Path(__file__).resolve().parents[1]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _repo_temporal(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / ".env").write_text("TEST_VALUE=dummy\n", encoding="utf-8")
    (repo / "permitido.txt").write_text("estado=inicial\n", encoding="utf-8")
    _git(repo, "add", ".env", "permitido.txt")
    _git(
        repo,
        "-c",
        "user.name=Prueba local",
        "-c",
        "user.email=prueba@example.invalid",
        "commit",
        "-m",
        "Snapshot inicial ficticio",
    )
    return repo


def _rutas_protegidas() -> list[str]:
    return orquestador.cargar_json(ROOT / "config.json")["rutas_protegidas"]


def test_modificar_env_activa_barrera_de_ruta_protegida(tmp_path):
    repo = _repo_temporal(tmp_path)
    antes = tomar_snapshot(repo)

    (repo / ".env").write_text("TEST_VALUE=changed_dummy\n", encoding="utf-8")

    despues = tomar_snapshot(repo)
    cambios = comparar_snapshots(antes, despues)
    ok, problemas = orquestador.validar_rutas(
        cambios.paths_cambiados,
        rutas_permitidas=[".env"],
        rutas_protegidas=_rutas_protegidas(),
        permitir_escritura=True,
    )

    assert cambios.paths_cambiados == {".env"}
    assert not ok
    assert problemas == ["Ruta protegida modificada: .env"]


def test_archivo_permitido_no_activa_regla_especifica_de_env(tmp_path):
    repo = _repo_temporal(tmp_path)
    antes = tomar_snapshot(repo)

    (repo / "permitido.txt").write_text("estado=modificado\n", encoding="utf-8")

    despues = tomar_snapshot(repo)
    cambios = comparar_snapshots(antes, despues)
    ok, problemas = orquestador.validar_rutas(
        cambios.paths_cambiados,
        rutas_permitidas=["permitido.txt"],
        rutas_protegidas=_rutas_protegidas(),
        permitir_escritura=True,
    )

    assert cambios.paths_cambiados == {"permitido.txt"}
    assert ok
    assert not any("Ruta protegida modificada" in problema for problema in problemas)
