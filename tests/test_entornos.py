import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest

from entornos import (
    ConflictoWorktree,
    EntornoTarea,
    ErrorPersistenciaLock,
    GestorEntornos,
    LiberacionNoPermitida,
    PropietarioReservaIncorrecto,
    normalizar_worktree,
    validar_entorno,
)
from tareas_persistentes import EstadoTarea, GestorTareas, ModoTarea, crear_contrato


def _git(repo, *args):
    resultado = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return resultado.stdout.strip()


def _repo(tmp_path, nombre="repo"):
    repo = tmp_path / nombre
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "base.txt")
    _git(
        repo,
        "-c",
        "user.name=Prueba local",
        "-c",
        "user.email=prueba@example.invalid",
        "commit",
        "-m",
        "Base",
    )
    return repo, _git(repo, "rev-parse", "HEAD")


def _contrato():
    return crear_contrato(
        objetivo="Validar y reservar entorno",
        condiciones_finalizacion="Entorno gestionado",
    )


def _tarea(gestor, repo, head, modo=ModoTarea.READ_ONLY):
    return gestor.crear_tarea(
        orden_original="Reserva el entorno",
        repo=str(repo),
        worktree=str(repo),
        rama="main",
        commit_inicial=head,
        modo=modo,
        contrato=_contrato(),
    )


def _gestores(tmp_path):
    tareas = GestorTareas(tmp_path / "estado" / "tareas")
    entornos = GestorEntornos(tareas, tmp_path / "estado" / "locks")
    return tareas, entornos


def test_session_id_generado_es_uuid_valido_y_estable(tmp_path):
    tareas, entornos = _gestores(tmp_path)

    generado = entornos.session_id

    assert str(UUID(generado)) == generado
    assert entornos.session_id == generado


def test_session_id_explicito_valido_se_persiste_y_recupera(tmp_path):
    repo, head = _repo(tmp_path)
    tareas = GestorTareas(tmp_path / "estado" / "tareas")
    session_id = str(uuid4())
    entornos = GestorEntornos(
        tareas,
        tmp_path / "estado" / "locks",
        session_id=session_id,
    )
    tarea = _tarea(tareas, repo, head)

    reserva = entornos.reservar_worktree(tarea.id)
    lock = next(entornos.directorio_locks.glob("*.json"))
    reiniciado = GestorEntornos(tareas, entornos.directorio_locks)

    assert reserva.session_id == session_id
    assert json.loads(lock.read_text(encoding="utf-8"))["session_id"] == session_id
    assert reiniciado.session_id != session_id
    assert reiniciado.obtener_reserva(repo).session_id == session_id


@pytest.mark.parametrize("session_id", ["sesion-humana", "", "2026-08-14"])
def test_session_id_invalido_sigue_siendo_rechazado(tmp_path, session_id):
    tareas = GestorTareas(tmp_path / "estado" / "tareas")

    with pytest.raises(ErrorPersistenciaLock, match="session_id debe ser un UUID válido"):
        GestorEntornos(
            tareas,
            tmp_path / "estado" / "locks",
            session_id=session_id,
        )


def test_reservar_persistir_recuperar_consultar_y_listar(tmp_path):
    repo, head = _repo(tmp_path)
    tareas, entornos = _gestores(tmp_path)
    tarea = _tarea(tareas, repo, head)

    reserva = entornos.reservar_worktree(tarea.id)
    archivos = list(entornos.directorio_locks.glob("*.json"))

    assert len(archivos) == 1
    assert json.loads(archivos[0].read_text(encoding="utf-8"))["task_id"] == tarea.id
    nuevo_gestor = GestorEntornos(tareas, entornos.directorio_locks)
    assert nuevo_gestor.obtener_reserva(repo) == reserva
    assert nuevo_gestor.listar_reservas() == [reserva]
    assert nuevo_gestor.comprobar_conflicto(repo, "otra-tarea") == reserva
    assert nuevo_gestor.comprobar_conflicto(repo, tarea.id) is None


@pytest.mark.parametrize(
    ("modo_a", "modo_b"),
    [
        (ModoTarea.READ_ONLY, ModoTarea.READ_ONLY),
        (ModoTarea.READ_ONLY, ModoTarea.WORKSPACE_WRITE),
        (ModoTarea.WORKSPACE_WRITE, ModoTarea.WORKSPACE_WRITE),
    ],
)
def test_rechaza_cualquier_segunda_tarea_en_mismo_worktree(
    tmp_path, modo_a, modo_b
):
    repo, head = _repo(tmp_path)
    tareas, entornos = _gestores(tmp_path)
    primera = _tarea(tareas, repo, head, modo_a)
    segunda = _tarea(tareas, repo, head, modo_b)
    entornos.reservar_worktree(primera.id)

    with pytest.raises(ConflictoWorktree) as error:
        entornos.reservar_worktree(segunda.id)

    assert error.value.reserva.task_id == primera.id
    assert tareas.cargar(segunda.id).historial[-1].tipo == "WORKTREE_CONFLICT"
    assert entornos.obtener_reserva(repo).task_id == primera.id


def test_dos_worktrees_y_tareas_distintas_tienen_reservas_independientes(tmp_path):
    repo_a, head_a = _repo(tmp_path, "repo_a")
    repo_b, head_b = _repo(tmp_path, "repo_b")
    tareas, entornos = _gestores(tmp_path)
    tarea_a = _tarea(tareas, repo_a, head_a)
    tarea_b = _tarea(tareas, repo_b, head_b, ModoTarea.WORKSPACE_WRITE)

    lock_a = entornos.reservar_worktree(tarea_a.id)
    lock_b = entornos.reservar_worktree(tarea_b.id)

    assert lock_a.task_id != lock_b.task_id
    assert lock_a.worktree_normalizado != lock_b.worktree_normalizado
    assert {lock.task_id for lock in entornos.listar_reservas()} == {
        tarea_a.id,
        tarea_b.id,
    }


def test_normaliza_variantes_windows_equivalentes(tmp_path):
    repo, head = _repo(tmp_path)
    tareas, entornos = _gestores(tmp_path)
    tarea = _tarea(tareas, repo, head)
    reserva = entornos.reservar_worktree(tarea.id)
    variante = str(repo).upper().replace("\\", "/") + "/./"

    assert normalizar_worktree(variante) == normalizar_worktree(repo)
    assert entornos.obtener_reserva(variante) == reserva


@pytest.mark.parametrize("terminal", [EstadoTarea.FINALIZADA, EstadoTarea.CANCELADA])
def test_tarea_terminal_libera_lock_y_registra_evento(tmp_path, terminal):
    repo, head = _repo(tmp_path)
    tareas, entornos = _gestores(tmp_path)
    tarea = _tarea(tareas, repo, head)
    entornos.reservar_worktree(tarea.id)
    if terminal is EstadoTarea.FINALIZADA:
        tareas.actualizar_estado(tarea.id, EstadoTarea.TRABAJANDO)
    tareas.actualizar_estado(tarea.id, terminal)

    liberada = entornos.liberar_worktree(tarea.id, repo)

    assert liberada.task_id == tarea.id
    assert entornos.obtener_reserva(repo) is None
    assert tareas.cargar(tarea.id).historial[-1].tipo == "WORKTREE_RELEASED"


def test_no_libera_tarea_activa_ni_lock_de_otra_tarea(tmp_path):
    repo, head = _repo(tmp_path)
    tareas, entornos = _gestores(tmp_path)
    propietaria = _tarea(tareas, repo, head)
    ajena = _tarea(tareas, repo, head)
    entornos.reservar_worktree(propietaria.id)

    with pytest.raises(LiberacionNoPermitida):
        entornos.liberar_worktree(propietaria.id, repo)
    with pytest.raises(PropietarioReservaIncorrecto):
        entornos.liberar_worktree(ajena.id, repo)
    assert entornos.obtener_reserva(repo).task_id == propietaria.id


def test_lock_conserva_metadata_de_auditoria_git(tmp_path):
    repo, head = _repo(tmp_path)
    tareas, entornos = _gestores(tmp_path)
    tarea = _tarea(tareas, repo, head, ModoTarea.WORKSPACE_WRITE)

    reserva = entornos.reservar_worktree(tarea.id)

    assert reserva.task_id == tarea.id
    assert reserva.repo == str(repo)
    assert reserva.worktree == str(repo)
    assert reserva.rama_esperada == "main"
    assert reserva.head_esperado == head
    assert reserva.modo is ModoTarea.WORKSPACE_WRITE
    assert reserva.fecha_creacion == reserva.ultima_actualizacion
    assert reserva.session_id == entornos.session_id
    assert reserva.process_id > 0
    assert reserva.rama_ultima_validacion == "main"
    assert reserva.head_ultima_validacion == head


def test_validacion_detecta_path_inexistente_y_repo_invalido(tmp_path):
    inexistente = EntornoTarea(
        repo=str(tmp_path / "no_repo"),
        worktree=str(tmp_path / "no_worktree"),
        rama="main",
        commit_inicial="a" * 40,
        modo=ModoTarea.READ_ONLY,
    )
    resultado_inexistente = validar_entorno(inexistente)
    assert not resultado_inexistente.path_existe
    assert "path inexistente" in resultado_inexistente.discrepancias[0]

    directorio = tmp_path / "directorio"
    directorio.mkdir()
    invalido = EntornoTarea(
        repo=str(directorio),
        worktree=str(directorio),
        rama="main",
        commit_inicial="a" * 40,
        modo=ModoTarea.READ_ONLY,
    )
    resultado_invalido = validar_entorno(invalido)
    assert resultado_invalido.path_existe
    assert not resultado_invalido.repositorio_git_valido
    assert "repositorio Git inválido" in resultado_invalido.discrepancias[0]


def test_validacion_registra_branch_head_y_estado_git(tmp_path):
    repo, head = _repo(tmp_path)
    (repo / "sin_seguimiento.txt").write_text("cambio\n", encoding="utf-8")
    entorno = EntornoTarea(str(repo), str(repo), "main", head, ModoTarea.READ_ONLY)

    resultado = validar_entorno(entorno)

    assert resultado.es_valido
    assert resultado.rama_actual == "main"
    assert resultado.head_actual == head
    assert resultado.estado_git == ("?? sin_seguimiento.txt",)


def test_integridad_detecta_cambio_de_branch_y_registra_mismatch(tmp_path):
    repo, head = _repo(tmp_path)
    tareas, entornos = _gestores(tmp_path)
    tarea = _tarea(tareas, repo, head)
    entornos.reservar_worktree(tarea.id)
    _git(repo, "branch", "otra")
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/otra")

    resultado = entornos.comprobar_integridad_entorno(repo)

    assert not resultado.es_valido
    assert resultado.rama_actual == "otra"
    assert any("rama distinta" in detalle for detalle in resultado.discrepancias)
    assert tareas.cargar(tarea.id).historial[-1].tipo == "ENVIRONMENT_MISMATCH"


def test_integridad_detecta_cambio_de_head(tmp_path):
    repo, head = _repo(tmp_path)
    tareas, entornos = _gestores(tmp_path)
    tarea = _tarea(tareas, repo, head)
    entornos.reservar_worktree(tarea.id)
    (repo / "nuevo.txt").write_text("nuevo\n", encoding="utf-8")
    _git(repo, "add", "nuevo.txt")
    _git(
        repo,
        "-c",
        "user.name=Prueba local",
        "-c",
        "user.email=prueba@example.invalid",
        "commit",
        "-m",
        "Nuevo HEAD",
    )

    resultado = entornos.comprobar_integridad_entorno(repo)

    assert not resultado.es_valido
    assert resultado.head_actual != head
    assert any("HEAD distinto" in detalle for detalle in resultado.discrepancias)


def test_eventos_de_validacion_y_lock_quedan_en_historial(tmp_path):
    repo, head = _repo(tmp_path)
    tareas, entornos = _gestores(tmp_path)
    tarea = _tarea(tareas, repo, head)

    entornos.reservar_worktree(tarea.id)
    tipos = [evento.tipo for evento in tareas.cargar(tarea.id).historial]

    assert tipos[-2:] == ["ENVIRONMENT_VALIDATED", "WORKTREE_LOCKED"]


def test_reinicio_detecta_posible_huerfano_sin_eliminarlo(tmp_path):
    repo, head = _repo(tmp_path)
    tareas, entornos = _gestores(tmp_path)
    tarea = _tarea(tareas, repo, head)
    reserva = entornos.reservar_worktree(tarea.id)

    reiniciado = GestorEntornos(tareas, entornos.directorio_locks)
    diagnostico = reiniciado.diagnosticar_locks()[0]

    assert diagnostico.posible_huerfano
    assert "otra sesión" in diagnostico.motivos[0]
    assert reiniciado.obtener_reserva(repo) == reserva
    assert len(reiniciado.listar_reservas()) == 1


def test_carrera_concurrente_solo_permite_un_propietario(tmp_path, monkeypatch):
    repo, head = _repo(tmp_path)
    tareas = GestorTareas(tmp_path / "estado" / "tareas")
    locks = tmp_path / "estado" / "locks"
    tarea_a = _tarea(tareas, repo, head)
    tarea_b = _tarea(tareas, repo, head)
    gestor_a = GestorEntornos(tareas, locks)
    gestor_b = GestorEntornos(tareas, locks)
    barrera = Barrier(2)
    crear_original = GestorEntornos._crear_exclusivo

    def crear_sincronizado(self, reserva):
        barrera.wait(timeout=10)
        return crear_original(self, reserva)

    monkeypatch.setattr(GestorEntornos, "_crear_exclusivo", crear_sincronizado)

    def intentar(gestor, task_id):
        try:
            return gestor.reservar_worktree(task_id)
        except ConflictoWorktree as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        resultados = list(
            executor.map(
                lambda argumentos: intentar(*argumentos),
                [(gestor_a, tarea_a.id), (gestor_b, tarea_b.id)],
            )
        )

    assert sum(not isinstance(resultado, ConflictoWorktree) for resultado in resultados) == 1
    assert sum(isinstance(resultado, ConflictoWorktree) for resultado in resultados) == 1
    assert len(gestor_a.listar_reservas()) == 1
