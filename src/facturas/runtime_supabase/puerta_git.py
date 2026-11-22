"""Puerta git comun de las ejecuciones productivas: noche (AUTO-ALLIANCE), series 2BJ y 2BP, y despliegues.

REGLAS_CRITICAS («Puerta git antes de una ejecucion productiva»): arbol limpio y HEAD = main del remoto, o por
delante solo con documentacion (``docs/`` o ``*.md``; DECISION DE PIO, 2026-11-05).

Correccion del 2026-11-19 (propuesta del 18/11, encargo de Pio): el main del remoto se lee del propio remoto con
``git ls-remote origin refs/heads/main`` (20 s como maximo, sin pedir credenciales), no de la referencia local
``origin/main``, que solo se actualiza con un fetch y podia dar un falso OK (el 18/11 la referencia local seguia en
885150d con 1ca8cc3 ya subido). Falla cerrado:

- remoto ilegible -> ``GIT_ORIGEN_NO_DETERMINABLE``;
- sha del remoto que no existe en el repositorio local (falta un fetch) -> ``GIT_ORIGEN_DESCONOCIDO_LOCALMENTE``;
- HEAD distinto del remoto: este debe ser ancestro de HEAD (``GIT_HEAD_NO_DESCIENDE_DE_ORIGIN``) y lo pendiente solo
  documentacion (``GIT_COMMITS_NO_DOCUMENTALES``).

Despliegues: el commit indicado debe estar ya contenido en el main del remoto (``commit_en_origen``).

Solo lectura: no hace fetch ni cambia referencias. ``ejecutar`` es inyectable (git simulado en los tests).
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Callable

RAMA_REMOTA = "refs/heads/main"
TIMEOUT_REMOTO_S = 20
TIMEOUT_LOCAL_S = 30
_SHA = re.compile(r"[0-9a-f]{40}")

Ejecutor = Callable[[list[str], Path, int], subprocess.CompletedProcess]


def _ejecutar(args: list[str], raiz: Path, timeout: int) -> subprocess.CompletedProcess:
    entorno = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    return subprocess.run(["git", *args], cwd=raiz, capture_output=True, text=True, timeout=timeout, env=entorno,
                          stdin=subprocess.DEVNULL)


def es_documentacion(ruta: str) -> bool:
    return ruta.startswith("docs/") or ruta.endswith(".md")


def leer_origen_remoto(raiz: Path, ejecutar: Ejecutor = _ejecutar) -> tuple[str | None, str | None]:
    """(sha del main del remoto, None) o (None, motivo)."""
    try:
        r = ejecutar(["ls-remote", "origin", RAMA_REMOTA], raiz, TIMEOUT_REMOTO_S)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, type(exc).__name__
    if r.returncode:
        return None, f"LS_REMOTE_CODIGO_{r.returncode}"
    shas = [p[0] for p in (linea.split() for linea in r.stdout.splitlines())
            if len(p) == 2 and p[1] == RAMA_REMOTA and _SHA.fullmatch(p[0])]
    if len(shas) != 1:
        return None, "LS_REMOTE_SIN_MAIN"
    return shas[0], None


def _conocido(raiz: Path, sha: str, ejecutar: Ejecutor) -> bool:
    return ejecutar(["cat-file", "-e", f"{sha}^{{commit}}"], raiz, TIMEOUT_LOCAL_S).returncode == 0


def estado(raiz: Path, ejecutar: Ejecutor = _ejecutar) -> dict:
    """Estado git para la puerta (se guarda en el informe): head, origin_local, origin_remoto y lo pendiente."""
    def git(*args: str) -> str:
        r = ejecutar(list(args), raiz, TIMEOUT_LOCAL_S)
        if r.returncode:
            raise RuntimeError(f"git {args[0]}: codigo {r.returncode}")
        return r.stdout.strip()

    try:
        out: dict = {"head": git("rev-parse", "HEAD"), "status": git("status", "--porcelain")}
        local = ejecutar(["rev-parse", "--verify", "--quiet", "origin/main"], raiz, TIMEOUT_LOCAL_S)
        out["origin_local"] = local.stdout.strip() if local.returncode == 0 else None
        remoto, error = leer_origen_remoto(raiz, ejecutar)
        out["origin_remoto"] = remoto
        if error:
            out["error_origen"] = error
            return out
        out["origin_conocido"] = _conocido(raiz, remoto, ejecutar)
        if out["origin_conocido"] and remoto != out["head"]:
            out["origin_ancestro"] = ejecutar(["merge-base", "--is-ancestor", remoto, "HEAD"], raiz,
                                              TIMEOUT_LOCAL_S).returncode == 0
            out["cambios"] = [p for p in git("diff", "--name-only", f"{remoto}..HEAD").splitlines() if p]
        return out
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def evaluar(g: dict) -> list[str]:
    """Fallos de la puerta para un ``estado``; lista vacia = puerta abierta."""
    if "error" in g:
        return [f"GIT_NO_DETERMINABLE:{g['error']}"]
    fallos = []
    if g["status"]:
        fallos.append("GIT_ARBOL_NO_LIMPIO")
    if g.get("error_origen") or not g.get("origin_remoto"):
        return fallos + [f"GIT_ORIGEN_NO_DETERMINABLE:{g.get('error_origen') or 'SIN_SHA'}"]
    if not g.get("origin_conocido"):
        return fallos + ["GIT_ORIGEN_DESCONOCIDO_LOCALMENTE"]
    if g["head"] != g["origin_remoto"]:
        no_doc = [c for c in g.get("cambios", []) if not es_documentacion(c)]
        if not g.get("origin_ancestro"):
            fallos.append("GIT_HEAD_NO_DESCIENDE_DE_ORIGIN")
        elif no_doc:
            fallos.append(f"GIT_COMMITS_NO_DOCUMENTALES:{','.join(no_doc[:10])}")
    return fallos


def puerta(raiz: Path, ejecutar: Ejecutor = _ejecutar) -> tuple[str | None, list[str], dict]:
    """(head o None, fallos, estado)."""
    g = estado(raiz, ejecutar)
    return g.get("head"), evaluar(g), g


def commit_en_origen(commit: str, raiz: Path, ejecutar: Ejecutor = _ejecutar) -> list[str]:
    """Despliegues: el commit indicado debe estar ya en el main del remoto (subido por Pio)."""
    remoto, error = leer_origen_remoto(raiz, ejecutar)
    if error:
        return [f"GIT_ORIGEN_NO_DETERMINABLE:{error}"]
    if not _conocido(raiz, remoto, ejecutar):
        return ["GIT_ORIGEN_DESCONOCIDO_LOCALMENTE"]
    if not re.fullmatch(r"[0-9a-f]{7,40}", commit or ""):
        return [f"GIT_COMMIT_DESCONOCIDO:{commit}"]
    resuelto = ejecutar(["rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"], raiz, TIMEOUT_LOCAL_S)
    if resuelto.returncode or not _SHA.fullmatch(resuelto.stdout.strip()):
        return [f"GIT_COMMIT_DESCONOCIDO:{commit}"]
    if ejecutar(["merge-base", "--is-ancestor", resuelto.stdout.strip(), remoto], raiz,
                TIMEOUT_LOCAL_S).returncode != 0:
        return [f"GIT_COMMIT_NO_SUBIDO:{commit}"]
    return []


def exigir_commit_en_origen(commit: str, raiz: Path, ejecutar: Ejecutor = _ejecutar) -> None:
    fallos = commit_en_origen(commit, raiz, ejecutar)
    if fallos:
        raise SystemExit("PUERTA_GIT_DESPLIEGUE:" + ";".join(fallos))
