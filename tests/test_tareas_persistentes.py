import json
import time
from dataclasses import replace
from uuid import UUID

import pytest

from tareas_persistentes import (
    ErrorPersistenciaTarea,
    ErrorValidacionTarea,
    EstadoTarea,
    GestorTareas,
    ModoTarea,
    TransicionEstadoInvalida,
    crear_contrato,
)


def _contrato():
    return crear_contrato(
        objetivo="Implementar persistencia",
        acciones_permitidas=["crear", "probar"],
        rutas_permitidas=["src/**", "tests/test_x.py"],
        acciones_prohibidas=["push", "desplegar"],
        rutas_protegidas=[".env", "secrets/**"],
        condiciones_finalizacion="Tests correctos",
        restricciones_adicionales=["sin red"],
        commit_autorizado=True,
        push_autorizado=False,
        presupuesto_api=12.75,
    )


def _crear(gestor):
    return gestor.crear_tarea(
        orden_original="Haz la tarea aprobada",
        repo="ControlFarmacias",
        worktree="C:/repo/worktree",
        rama="v0.2-dev",
        commit_inicial="a" * 40,
        modo=ModoTarea.WORKSPACE_WRITE,
        contrato=_contrato(),
    )


def test_creacion_id_persistencia_json_e_historial(tmp_path):
    gestor = GestorTareas(tmp_path / "estado" / "tareas")
    tarea = _crear(gestor)

    UUID(tarea.id)
    path = gestor.directorio / f"{tarea.id}.json"
    assert path.is_file()
    datos = json.loads(path.read_text(encoding="utf-8"))
    assert datos["id"] == tarea.id
    assert [evento.tipo for evento in tarea.historial] == [
        "TASK_CREATED",
        "CONTRACT_CREATED",
    ]


def test_carga_conserva_todos_los_datos_y_contrato(tmp_path):
    gestor = GestorTareas(tmp_path)
    original = _crear(gestor)
    cargada = gestor.cargar(original.id)

    assert cargada == original
    assert cargada.contrato == _contrato()
    assert cargada.rutas_permitidas == ("src/**", "tests/test_x.py")
    assert cargada.rutas_protegidas == (".env", "secrets/**")
    assert cargada.commit_autorizado is True
    assert cargada.push_autorizado is False
    assert cargada.presupuesto_api == 12.75


def test_recuperacion_con_instancia_nueva_del_gestor(tmp_path):
    original = _crear(GestorTareas(tmp_path))
    cargada = GestorTareas(tmp_path).cargar(original.id)
    assert cargada == original


def test_ids_y_archivos_son_distintos_y_listar_funciona(tmp_path):
    gestor = GestorTareas(tmp_path)
    primera = _crear(gestor)
    segunda = _crear(gestor)

    assert primera.id != segunda.id
    assert (tmp_path / f"{primera.id}.json").is_file()
    assert (tmp_path / f"{segunda.id}.json").is_file()
    assert {tarea.id for tarea in gestor.listar()} == {primera.id, segunda.id}


def test_cambio_estado_actualiza_fecha_y_registra_evento(tmp_path):
    gestor = GestorTareas(tmp_path)
    tarea = _crear(gestor)
    time.sleep(0.001)
    actualizada = gestor.actualizar_estado(tarea, EstadoTarea.TRABAJANDO)

    assert actualizada.estado is EstadoTarea.TRABAJANDO
    assert actualizada.fecha_actualizacion > tarea.fecha_actualizacion
    evento = actualizada.historial[-1]
    assert evento.tipo == "STATUS_CHANGED"
    assert evento.datos == {
        "estado_anterior": "PREPARANDO",
        "estado_nuevo": "TRABAJANDO",
    }
    assert gestor.cargar(tarea.id) == actualizada


def test_anadir_evento_es_persistente(tmp_path):
    gestor = GestorTareas(tmp_path)
    tarea = _crear(gestor)
    actualizada = gestor.anadir_evento(tarea.id, "NOTA", {"detalle": "prueba"})
    assert actualizada.historial[-1].a_dict()["datos"] == {"detalle": "prueba"}
    assert gestor.cargar(tarea.id).historial[-1].tipo == "NOTA"


def test_rechaza_estado_inexistente(tmp_path):
    gestor = GestorTareas(tmp_path)
    with pytest.raises(ErrorValidacionTarea, match="estado inexistente"):
        gestor.actualizar_estado(_crear(gestor), "INVENTADO")


def test_rechaza_transicion_invalida(tmp_path):
    gestor = GestorTareas(tmp_path)
    with pytest.raises(TransicionEstadoInvalida):
        gestor.actualizar_estado(_crear(gestor), EstadoTarea.FINALIZADA)


@pytest.mark.parametrize("terminal", [EstadoTarea.FINALIZADA, EstadoTarea.CANCELADA])
def test_estados_terminales_no_vuelven_a_trabajando(tmp_path, terminal):
    gestor = GestorTareas(tmp_path)
    tarea = gestor.actualizar_estado(_crear(gestor), EstadoTarea.TRABAJANDO)
    tarea = gestor.actualizar_estado(tarea, terminal)

    assert tarea.es_terminal
    assert gestor.es_terminal(tarea.id)
    with pytest.raises(TransicionEstadoInvalida):
        gestor.actualizar_estado(tarea, EstadoTarea.TRABAJANDO)


def test_historial_persistido_no_se_puede_reescribir_ni_truncar(tmp_path):
    gestor = GestorTareas(tmp_path)
    tarea = _crear(gestor)

    with pytest.raises(ErrorPersistenciaTarea, match="append-only"):
        gestor.guardar(replace(tarea, historial=tuple(reversed(tarea.historial))))
    with pytest.raises(ErrorPersistenciaTarea, match="truncar"):
        gestor.guardar(replace(tarea, historial=tarea.historial[:1]))


def test_guardar_no_permite_saltar_control_de_transiciones(tmp_path):
    gestor = GestorTareas(tmp_path)
    tarea = _crear(gestor)

    with pytest.raises(ErrorPersistenciaTarea, match="STATUS_CHANGED"):
        gestor.guardar(replace(tarea, estado=EstadoTarea.TRABAJANDO))


def test_listar_sin_directorio_devuelve_lista_vacia(tmp_path):
    assert GestorTareas(tmp_path / "no_existe").listar() == []
