from pathlib import Path

import orquestador_snapshot as snapshot


def _git_falso(monkeypatch, estado):
    def ejecutar(_repo: Path, *args: str, allow_failure: bool = False) -> bytes:
        del allow_failure
        comando = tuple(args)
        if comando == ("rev-parse", "--verify", "HEAD"):
            return estado["head"].encode() + b"\n"
        if comando == ("symbolic-ref", "--short", "-q", "HEAD"):
            return estado["rama"].encode() + b"\n"
        cached = "--cached" in comando
        if "--raw" in comando:
            return estado["staged_raw" if cached else "unstaged_raw"]
        if "--name-only" in comando:
            paths = estado["staged" if cached else "unstaged"]
            return b"\0".join(path.encode() for path in paths) + (b"\0" if paths else b"")
        raise AssertionError(comando)

    monkeypatch.setattr(snapshot, "_git_bytes", ejecutar)


def _estado(**cambios):
    base = {
        "head": "a" * 40,
        "rama": "main",
        "staged": [],
        "unstaged": [],
        "staged_raw": b"",
        "unstaged_raw": b"",
    }
    base.update(cambios)
    return base


def _capturar(tmp_path, monkeypatch, estado):
    _git_falso(monkeypatch, estado)
    return snapshot.tomar_snapshot(tmp_path)


def test_a_tracked_limpio_sin_cambio(tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("igual", encoding="utf-8")
    antes = _capturar(tmp_path, monkeypatch, _estado())
    despues = _capturar(tmp_path, monkeypatch, _estado())
    assert not snapshot.comparar_snapshots(antes, despues).hay_cambios


def test_b_tracked_previamente_modificado_sin_cambio(tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("modificado previo", encoding="utf-8")
    estado = _estado(unstaged=["a.txt"], unstaged_raw=b"M a.txt previo")
    antes = _capturar(tmp_path, monkeypatch, estado)
    despues = _capturar(tmp_path, monkeypatch, estado)
    assert not snapshot.comparar_snapshots(antes, despues).hay_cambios


def test_c_tracked_previamente_modificado_cambia(tmp_path, monkeypatch):
    path = tmp_path / "a.txt"
    path.write_text("modificado previo", encoding="utf-8")
    antes = _capturar(tmp_path, monkeypatch, _estado(unstaged=["a.txt"], unstaged_raw=b"uno"))
    path.write_text("modificado durante ciclo", encoding="utf-8")
    despues = _capturar(tmp_path, monkeypatch, _estado(unstaged=["a.txt"], unstaged_raw=b"dos"))
    diff = snapshot.comparar_snapshots(antes, despues)
    assert diff.modificados == {"a.txt"}


def test_d_untracked_previo_sin_cambio(tmp_path, monkeypatch):
    (tmp_path / "previo.txt").write_text("igual", encoding="utf-8")
    antes = _capturar(tmp_path, monkeypatch, _estado())
    despues = _capturar(tmp_path, monkeypatch, _estado())
    assert not snapshot.comparar_snapshots(antes, despues).hay_cambios


def test_e_nuevo_untracked(tmp_path, monkeypatch):
    antes = _capturar(tmp_path, monkeypatch, _estado())
    (tmp_path / "nuevo.txt").write_text("nuevo", encoding="utf-8")
    despues = _capturar(tmp_path, monkeypatch, _estado())
    assert snapshot.comparar_snapshots(antes, despues).creados == {"nuevo.txt"}


def test_f_eliminado(tmp_path, monkeypatch):
    path = tmp_path / "borrado.txt"
    path.write_text("adios", encoding="utf-8")
    antes = _capturar(tmp_path, monkeypatch, _estado())
    path.unlink()
    despues = _capturar(tmp_path, monkeypatch, _estado())
    assert snapshot.comparar_snapshots(antes, despues).eliminados == {"borrado.txt"}


def test_g_cambio_head(tmp_path, monkeypatch):
    antes = _capturar(tmp_path, monkeypatch, _estado(head="a" * 40))
    despues = _capturar(tmp_path, monkeypatch, _estado(head="b" * 40))
    assert snapshot.comparar_snapshots(antes, despues).cambio_head


def test_h_cambio_rama(tmp_path, monkeypatch):
    antes = _capturar(tmp_path, monkeypatch, _estado(rama="main"))
    despues = _capturar(tmp_path, monkeypatch, _estado(rama="otra"))
    assert snapshot.comparar_snapshots(antes, despues).cambio_rama


def test_i_cambio_staging_sin_cambio_contenido(tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("mismo contenido", encoding="utf-8")
    antes = _capturar(
        tmp_path,
        monkeypatch,
        _estado(unstaged=["a.txt"], unstaged_raw=b"diff de a"),
    )
    despues = _capturar(
        tmp_path,
        monkeypatch,
        _estado(staged=["a.txt"], staged_raw=b"diff de a"),
    )
    diff = snapshot.comparar_snapshots(antes, despues)
    assert diff.cambio_staged
    assert diff.paths_cambiados == {"a.txt"}
    assert not diff.modificados
