"""Snapshots comparables del workspace y del estado observable de Git."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import subprocess


SIN_HEAD = "<SIN_HEAD>"


class SnapshotError(RuntimeError):
    """No se pudo obtener un snapshot fiable del workspace."""


def _normalizar(path: str) -> str:
    normalizado = path.replace("\\", "/")
    while normalizado.startswith("./"):
        normalizado = normalizado[2:]
    return normalizado


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_bytes(repo: Path, *args: str, allow_failure: bool = False) -> bytes:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        check=False,
    )
    if proc.returncode and not allow_failure:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise SnapshotError(f"Git falló ({' '.join(args)}): {stderr}")
    return proc.stdout


def _paths_git(repo: Path, *args: str) -> frozenset[str]:
    raw = _git_bytes(repo, *args)
    return frozenset(
        _normalizar(item.decode("utf-8", errors="surrogateescape"))
        for item in raw.split(b"\0")
        if item
    )


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class WorkspaceSnapshot:
    archivos: dict[str, str]
    head: str
    rama: str
    staged_paths: frozenset[str]
    unstaged_paths: frozenset[str]
    staged_fingerprint: str
    unstaged_fingerprint: str

    def estado_git(self) -> dict[str, object]:
        return {
            "branch": self.rama,
            "head": self.head,
            "staged": sorted(self.staged_paths),
            "unstaged": sorted(self.unstaged_paths),
        }


@dataclass(frozen=True)
class SnapshotDiff:
    creados: frozenset[str]
    eliminados: frozenset[str]
    modificados: frozenset[str]
    cambio_head: bool
    cambio_rama: bool
    cambio_staged: bool
    cambio_unstaged: bool
    paths_git_cambiados: frozenset[str]

    @property
    def paths_cambiados(self) -> set[str]:
        return set(
            self.creados
            | self.eliminados
            | self.modificados
            | self.paths_git_cambiados
        )

    @property
    def hay_cambios(self) -> bool:
        return bool(
            self.paths_cambiados
            or self.cambio_head
            or self.cambio_rama
            or self.cambio_staged
            or self.cambio_unstaged
        )


def tomar_snapshot(repo: Path) -> WorkspaceSnapshot:
    """Captura contenido de archivos y estado Git sin modificar el repositorio."""
    repo = repo.resolve()
    archivos: dict[str, str] = {}
    try:
        for root, dirs, names in os.walk(repo, followlinks=False):
            dirs[:] = [name for name in dirs if name != ".git"]
            root_path = Path(root)
            for name in names:
                path = root_path / name
                rel = path.relative_to(repo).as_posix()
                archivos[rel] = _sha256(path)
    except OSError as exc:
        raise SnapshotError(f"No se pudo hashear el workspace {repo}: {exc}") from exc

    head_raw = _git_bytes(repo, "rev-parse", "--verify", "HEAD", allow_failure=True)
    head = head_raw.decode("ascii", errors="replace").strip() or SIN_HEAD
    branch_raw = _git_bytes(
        repo, "symbolic-ref", "--short", "-q", "HEAD", allow_failure=True
    )
    rama = branch_raw.decode("utf-8", errors="replace").strip()

    staged_raw = _git_bytes(repo, "diff", "--cached", "--raw", "--no-abbrev", "-z")
    unstaged_raw = _git_bytes(repo, "diff", "--raw", "--no-abbrev", "-z")
    return WorkspaceSnapshot(
        archivos=archivos,
        head=head,
        rama=rama,
        staged_paths=_paths_git(repo, "diff", "--cached", "--name-only", "-z"),
        unstaged_paths=_paths_git(repo, "diff", "--name-only", "-z"),
        staged_fingerprint=_hash_bytes(staged_raw),
        unstaged_fingerprint=_hash_bytes(unstaged_raw),
    )


def comparar_snapshots(
    antes: WorkspaceSnapshot, despues: WorkspaceSnapshot
) -> SnapshotDiff:
    antes_paths = set(antes.archivos)
    despues_paths = set(despues.archivos)
    comunes = antes_paths & despues_paths
    staged_changed = antes.staged_fingerprint != despues.staged_fingerprint
    unstaged_changed = antes.unstaged_fingerprint != despues.unstaged_fingerprint
    git_paths: set[str] = set()
    if staged_changed:
        git_paths.update(antes.staged_paths | despues.staged_paths)
    if unstaged_changed:
        git_paths.update(antes.unstaged_paths | despues.unstaged_paths)

    return SnapshotDiff(
        creados=frozenset(despues_paths - antes_paths),
        eliminados=frozenset(antes_paths - despues_paths),
        modificados=frozenset(
            path for path in comunes if antes.archivos[path] != despues.archivos[path]
        ),
        cambio_head=antes.head != despues.head,
        cambio_rama=antes.rama != despues.rama,
        cambio_staged=staged_changed,
        cambio_unstaged=unstaged_changed,
        paths_git_cambiados=frozenset(git_paths),
    )
