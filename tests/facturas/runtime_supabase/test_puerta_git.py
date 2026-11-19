"""Puerta git comun (2026-11-19): main del remoto con ls-remote, git simulado, y despliegues con commit subido."""
from __future__ import annotations

import importlib.util
import subprocess
import uuid
from pathlib import Path

import pytest

from src.facturas.runtime_supabase import puerta_git as pg

ROOT = Path(__file__).resolve().parents[3]
HEAD, REMOTO, LOCAL = "a" * 40, "b" * 40, "c" * 40


class GitSimulado:
    """Responde a cada orden git segun un diccionario; registra las ordenes recibidas."""

    def __init__(self, **respuestas):
        self.respuestas = {
            "rev-parse HEAD": (0, HEAD), "status --porcelain": (0, ""),
            "rev-parse --verify --quiet origin/main": (0, LOCAL),
            f"ls-remote origin {pg.RAMA_REMOTA}": (0, f"{REMOTO}\t{pg.RAMA_REMOTA}\n"),
            f"cat-file -e {REMOTO}^{{commit}}": (0, ""),
            f"merge-base --is-ancestor {REMOTO} HEAD": (0, ""),
            f"diff --name-only {REMOTO}..HEAD": (0, "docs/a.md\npruebas/x/DISENO.md\n"),
            **respuestas,
        }
        self.ordenes: list[tuple[str, int]] = []

    def __call__(self, args, raiz, timeout):
        orden = " ".join(args)
        self.ordenes.append((orden, timeout))
        respuesta = self.respuestas.get(orden, (128, ""))
        if isinstance(respuesta, Exception):
            raise respuesta
        codigo, salida = respuesta
        return subprocess.CompletedProcess(args, codigo, salida, "")


def test_lee_el_main_del_remoto_con_ls_remote_y_timeout():
    git = GitSimulado()
    head, fallos, estado = pg.puerta(Path("."), git)
    assert (head, fallos) == (HEAD, [])
    assert (estado["origin_local"], estado["origin_remoto"]) == (LOCAL, REMOTO)
    assert (f"ls-remote origin {pg.RAMA_REMOTA}", pg.TIMEOUT_REMOTO_S) in git.ordenes
    assert not any(o.startswith("fetch") for o, _ in git.ordenes)


@pytest.mark.parametrize("respuestas, fallo", [
    ({f"ls-remote origin {pg.RAMA_REMOTA}": subprocess.TimeoutExpired("git", 20)},
     "GIT_ORIGEN_NO_DETERMINABLE:TimeoutExpired"),
    ({f"ls-remote origin {pg.RAMA_REMOTA}": (128, "")}, "GIT_ORIGEN_NO_DETERMINABLE:LS_REMOTE_CODIGO_128"),
    ({f"ls-remote origin {pg.RAMA_REMOTA}": (0, "")}, "GIT_ORIGEN_NO_DETERMINABLE:LS_REMOTE_SIN_MAIN"),
    ({f"ls-remote origin {pg.RAMA_REMOTA}": (0, f"zz\t{pg.RAMA_REMOTA}\n")},
     "GIT_ORIGEN_NO_DETERMINABLE:LS_REMOTE_SIN_MAIN"),
    ({f"cat-file -e {REMOTO}^{{commit}}": (1, "")}, "GIT_ORIGEN_DESCONOCIDO_LOCALMENTE"),
    ({f"merge-base --is-ancestor {REMOTO} HEAD": (1, "")}, "GIT_HEAD_NO_DESCIENDE_DE_ORIGIN"),
    ({f"diff --name-only {REMOTO}..HEAD": (0, "docs/a.md\nsrc/b.py\n.claude/x.md\n")},
     "GIT_COMMITS_NO_DOCUMENTALES:src/b.py"),
    ({"status --porcelain": (0, " M src/x.py")}, "GIT_ARBOL_NO_LIMPIO"),
    ({"rev-parse HEAD": (128, "")}, "GIT_NO_DETERMINABLE:RuntimeError: git rev-parse: codigo 128"),
    ({"rev-parse HEAD": OSError("sin git")}, "GIT_NO_DETERMINABLE:OSError: sin git"),
])
def test_falla_cerrado(respuestas, fallo):
    assert fallo in pg.puerta(Path("."), GitSimulado(**respuestas))[1]


def test_igual_al_remoto_aunque_la_referencia_local_este_desfasada():
    git = GitSimulado(**{"rev-parse HEAD": (0, REMOTO)})
    assert pg.puerta(Path("."), git)[1] == []


def test_sin_referencia_local_decide_el_remoto():
    git = GitSimulado(**{"rev-parse --verify --quiet origin/main": (1, "")})
    _, fallos, estado = pg.puerta(Path("."), git)
    assert fallos == [] and estado["origin_local"] is None


def test_no_lanza_fetch_ni_cambia_referencias():
    git = GitSimulado()
    pg.puerta(Path("."), git)
    pg.commit_en_origen(HEAD, Path("."), git)
    prohibidas = ("fetch", "pull", "push", "update-ref", "checkout", "reset", "commit")
    assert not any(o.split()[0] in prohibidas for o, _ in git.ordenes)


# --------------------------------------------------------------------------- despliegues


def _git_despliegue(**extra):
    return GitSimulado(**{
        f"rev-parse --verify --quiet {HEAD}^{{commit}}": (0, HEAD),
        f"rev-parse --verify --quiet {HEAD[:7]}^{{commit}}": (0, HEAD),
        f"merge-base --is-ancestor {HEAD} {REMOTO}": (0, ""), **extra})


def test_despliegue_con_commit_subido():
    assert pg.commit_en_origen(HEAD, Path("."), _git_despliegue()) == []
    assert pg.commit_en_origen(HEAD[:7], Path("."), _git_despliegue()) == []


@pytest.mark.parametrize("commit, extra, fallo", [
    (HEAD, {f"merge-base --is-ancestor {HEAD} {REMOTO}": (1, "")}, f"GIT_COMMIT_NO_SUBIDO:{HEAD}"),
    ("d" * 40, {}, f"GIT_COMMIT_DESCONOCIDO:{'d' * 40}"),
    ("--all", {}, "GIT_COMMIT_DESCONOCIDO:--all"),
    (HEAD, {f"ls-remote origin {pg.RAMA_REMOTA}": (2, "")}, "GIT_ORIGEN_NO_DETERMINABLE:LS_REMOTE_CODIGO_2"),
    (HEAD, {f"cat-file -e {REMOTO}^{{commit}}": (1, "")}, "GIT_ORIGEN_DESCONOCIDO_LOCALMENTE"),
])
def test_despliegue_falla_cerrado(commit, extra, fallo):
    assert pg.commit_en_origen(commit, Path("."), _git_despliegue(**extra)) == [fallo]
    with pytest.raises(SystemExit, match="PUERTA_GIT_DESPLIEGUE"):
        pg.exigir_commit_en_origen(commit, Path("."), _git_despliegue(**extra))


DESPLIEGUES_3X = ("pruebas/auditoria_trab/desplegar_31.py", "pruebas/auditoria_auto_alliance/desplegar_32.py",
                  "pruebas/auditoria_trab/desplegar_33.py", "pruebas/auditoria_trab/desplegar_34.py",
                  "pruebas/auditoria_h6/desplegar_35.py", "pruebas/auditoria_r20/desplegar_36.py")


@pytest.mark.parametrize("relativa", DESPLIEGUES_3X)
def test_cli_de_despliegue_exige_commit_subido_antes_de_main(relativa, monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location(f"despliegue_{uuid.uuid4().hex[:6]}", ROOT / relativa)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    llamadas = []
    monkeypatch.setattr(modulo, "main", lambda *a: llamadas.append(a))

    def rechazar(commit, raiz):
        raise SystemExit(f"PUERTA_GIT_DESPLIEGUE:GIT_COMMIT_NO_SUBIDO:{commit}")

    monkeypatch.setattr(pg, "exigir_commit_en_origen", rechazar)
    with pytest.raises(SystemExit, match="GIT_COMMIT_NO_SUBIDO"):
        modulo.cli([HEAD, "0" * 64, str(tmp_path / "s.json")])
    assert llamadas == []
    monkeypatch.setattr(pg, "exigir_commit_en_origen", lambda commit, raiz: None)
    modulo.cli([HEAD, "0" * 64, str(tmp_path / "s.json")])
    assert llamadas == [(HEAD, "0" * 64, tmp_path / "s.json")]
