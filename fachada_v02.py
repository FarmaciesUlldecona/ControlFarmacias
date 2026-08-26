"""Fachada operativa pública única del Orquestador ControlFarmacias V0.2.8."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

from arranque import EstadoGlobalOrquestador, ResultadoArranque, ServicioArranque
from decisiones_persistentes import EstadoDecision
from ejecucion_v02 import EjecutorCiclo, ServicioDecisiones
from entornos import (
    ConflictoWorktree,
    EntornoTarea,
    ErrorEntorno,
    validar_entorno,
)
from contabilidad_recursos import (
    DatoMonetarioInvalido,
    ErrorContabilidadRecursos,
)
from ejecutor_local import (
    EjecutorLocal,
    ErrorSolicitudLocal,
    OperacionLocal,
    SolicitudEjecucionLocal,
)
from reintentos_persistentes import ResultadoOperacionReintento
from lenguaje_natural import (
    CanalEntradaInvalido,
    ContextoInterpretacion,
    ErrorInterpretacion,
    InterpreteOrdenNatural,
    InterpretacionInvalida,
    OrdenInterpretada,
    ProveedorInterpretacion,
    RegistroOrdenesNaturales,
    TipoAccionNatural,
    TipoIntencion,
)
from orquestador_snapshot import SnapshotError, tomar_snapshot
from politica_recursos import (
    EvaluacionRecursos,
    PoliticaRecursos,
    SolicitudRecursos,
    TipoTrabajo,
)
from reglas_persistentes import ReglaInvalida, TipoRegla
from runs_persistentes import EstadoInternoRun, RunPersistente
from supervisor_v02 import DecisionSupervisor, SolicitudAccion
from tareas_persistentes import (
    CapacidadCheckpoint,
    EstadoTarea,
    ModoTarea,
    Tarea,
    crear_contrato,
)


@dataclass(frozen=True)
class ResultadoPublicoV02:
    ok: bool
    codigo: str
    mensaje: str
    task_id: str | None = None
    run_id: str | None = None
    decision_id: str | None = None
    estado_tarea: str | None = None
    estado_global: str | None = None
    requiere_intervencion: bool = False
    datos: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    errores: tuple[str, ...] = ()


@dataclass(frozen=True)
class EspecificacionTareaV02:
    orden_original: str
    objetivo: str
    repo: str
    worktree: str
    rama: str
    commit_inicial: str
    modo: ModoTarea | str = ModoTarea.READ_ONLY
    acciones_permitidas: tuple[str, ...] = ()
    rutas_permitidas: tuple[str, ...] = ()
    acciones_prohibidas: tuple[str, ...] = ()
    rutas_protegidas: tuple[str, ...] = ()
    condicion_finalizacion: str = "Resultado revisado"
    restricciones_adicionales: tuple[str, ...] = ()
    commit_autorizado: bool = False
    push_autorizado: bool = False
    presupuesto_api: int | float | None = None
    capacidad_checkpoint: CapacidadCheckpoint | str = CapacidadCheckpoint.NONE
    clave_idempotencia: str | None = None


@dataclass(frozen=True)
class ResumenSistemaV02:
    estado_global: str
    tareas_activas: int
    tareas_esperando_decision: int
    tareas_bloqueadas: int
    tareas_recuperando: int
    worktrees_ocupados: int
    decisiones_pendientes: int
    retries_preparados: int
    warnings: tuple[str, ...]


class OrquestadorV02:
    """Única API que necesita un consumidor normal de V0.2."""

    def __init__(
        self,
        base_dir: str | Path,
        *,
        ejecutor_factory: Callable[[Tarea], EjecutorCiclo] | None = None,
        inspector_procesos: Any | None = None,
        proveedor_interpretacion: ProveedorInterpretacion | None = None,
        preferir_proveedor_interpretacion: bool = False,
        repos_conocidos: dict[str, dict[str, Any]] | None = None,
        ejecutor_local: EjecutorLocal | None = None,
    ) -> None:
        self._ejecutor_factory = ejecutor_factory
        self._arranque = ServicioArranque(
            base_dir,
            ejecutor_factory=ejecutor_factory,
            inspector_procesos=inspector_procesos,
        )
        self._interprete_natural = InterpreteOrdenNatural(
            proveedor_interpretacion,
            preferir_proveedor=preferir_proveedor_interpretacion,
        )
        self._ejecutor_local = ejecutor_local or EjecutorLocal()
        self._repos_conocidos = {
            str(nombre).upper(): dict(datos)
            for nombre, datos in (repos_conocidos or {}).items()
        }
        self._registro_natural = RegistroOrdenesNaturales(
            Path(base_dir) / "estado" / "ordenes_naturales"
        )

    def iniciar(self) -> ResultadoPublicoV02:
        resultado = self._arranque.iniciar_orquestador()
        return self._resultado_arranque(resultado)

    def estado(self) -> EstadoGlobalOrquestador:
        return self._arranque.obtener_estado_global()

    def procesar_orden(self, texto: str) -> ResultadoPublicoV02:
        """Interpreta únicamente el canal explícito y despacha operaciones seguras."""
        no_listo = self._requiere_listo()
        if no_listo:
            return no_listo
        order_id = self._nuevo_order_id()
        self._registro_natural.registrar(
            "NATURAL_ORDER_RECEIVED",
            {"order_id": order_id, "texto_original": texto, "canal": "USUARIO_EXPLICITO"},
        )
        try:
            orden = self._interprete_natural.interpretar(
                texto, self._contexto_interpretacion()
            )
        except (InterpretacionInvalida, CanalEntradaInvalido, ErrorInterpretacion, ValueError) as exc:
            self._registro_natural.registrar(
                "INTERPRETATION_INVALID",
                {"order_id": order_id, "motivo": str(exc)},
            )
            return self._error(
                "INTERPRETATION_INVALID", str(exc),
                requiere_intervencion=True,
                datos={"order_id": order_id},
            )
        self._registro_natural.registrar(
            "NATURAL_ORDER_INTERPRETED",
            {"order_id": order_id, "interpretacion": orden.a_dict()},
        )
        if orden.ambigua or orden.datos_faltantes:
            codigo = "AMBIGUOUS_REFERENCE" if orden.referencias_no_resueltas else "INTERPRETATION_INCOMPLETE"
            self._registro_natural.registrar(
                "AMBIGUOUS_REFERENCE" if orden.ambigua else "NATURAL_ORDER_REJECTED",
                {
                    "order_id": order_id,
                    "ambiguedades": list(orden.ambiguedades),
                    "datos_faltantes": list(orden.datos_faltantes),
                    "referencias_no_resueltas": list(orden.referencias_no_resueltas),
                },
            )
            return self._error(
                codigo, "la orden no es ejecutable sin aclaración",
                requiere_intervencion=True,
                datos={"order_id": order_id, "interpretacion": orden.a_dict()},
            )
        resultado = self._despachar_orden_natural(orden)
        self._registro_natural.registrar(
            "NATURAL_ORDER_EXECUTED",
            {
                "order_id": order_id, "interpretation_id": orden.interpretation_id,
                "tipo_intencion": orden.tipo_intencion.value,
                "task_id": resultado.task_id, "decision_id": resultado.decision_id,
                "run_id": resultado.run_id, "codigo": resultado.codigo,
            },
        )
        if resultado.task_id:
            try:
                self._arranque.gestor_tareas.anadir_evento(
                    resultado.task_id, "NATURAL_ORDER_EXECUTED",
                    {"order_id": order_id, "interpretation_id": orden.interpretation_id, "codigo": resultado.codigo},
                )
            except Exception:
                pass
        return replace(
            resultado,
            datos={**resultado.datos, "order_id": order_id, "interpretacion": orden.a_dict()},
        )

    def _despachar_orden_natural(self, orden: OrdenInterpretada) -> ResultadoPublicoV02:
        if orden.tipo_intencion is TipoIntencion.CONSULTAR_ESTADO:
            resumen = self.resumen_sistema()
            return self._ok(
                "LOCAL_STATUS_QUERY", "consulta resuelta desde estado persistente",
                datos={"resumen": resumen.__dict__},
            )
        if orden.tipo_intencion is TipoIntencion.CONSULTAR_RESULTADO:
            if orden.task_id_referencia is None:
                return self._error("TASK_REFERENCE_REQUIRED", "falta tarea inequívoca", requiere_intervencion=True)
            run = self._arranque.gestor_runs.obtener_ultimo_run(orden.task_id_referencia)
            return self._ok(
                "LOCAL_RESULT_QUERY", "resultado consultado localmente",
                task_id=orden.task_id_referencia, run_id=run.run_id if run else None,
                datos={"run": run.a_dict() if run else None},
            )
        if orden.tipo_intencion is TipoIntencion.CONSULTAR_PRESUPUESTO:
            return self.consultar_presupuesto()
        if orden.tipo_intencion is TipoIntencion.CONTINUAR_TAREA:
            return self.ejecutar_tarea(orden.task_id_referencia)
        if orden.tipo_intencion is TipoIntencion.CANCELAR_TAREA:
            return self.cancelar_tarea(orden.task_id_referencia)
        if orden.tipo_intencion is TipoIntencion.RESPONDER_DECISION:
            return self.responder_decision(
                orden.task_id_referencia, texto=orden.texto_original
            )
        if orden.tipo_intencion is TipoIntencion.PREPARAR_REINTENTO:
            return self.preparar_reintento(orden.task_id_referencia)
        if orden.tipo_intencion is TipoIntencion.EJECUTAR_REINTENTO:
            return self.ejecutar_reintento(orden.retry_id_referencia)
        if orden.tipo_intencion in {TipoIntencion.REGISTRAR_REGLA, TipoIntencion.DESACTIVAR_REGLA}:
            return self._error(
                "STRUCTURED_CONFIRMATION_REQUIRED",
                "las reglas permanentes requieren datos estructurados explícitos",
                requiere_intervencion=True,
            )
        if orden.tipo_intencion is not TipoIntencion.CREAR_TAREA:
            return self._error("UNSUPPORTED_NATURAL_INTENT", "intención no ejecutable", requiere_intervencion=True)
        if len(orden.acciones) == 1 and orden.acciones[0].tipo is TipoAccionNatural.COMPROBAR_GIT:
            try:
                snapshot = tomar_snapshot(Path(orden.worktree_candidato))
            except (SnapshotError, OSError) as exc:
                return self._error("LOCAL_QUERY_FAILED", str(exc))
            evaluacion_recursos = self._evaluar_recursos_orden(orden)
            return self._ok(
                "LOCAL_GIT_QUERY", "estado Git consultado sin crear tarea ni lanzar Codex",
                datos={
                    "rama": snapshot.rama,
                    "head": snapshot.head,
                    "limpio": not (snapshot.staged_paths or snapshot.unstaged_paths),
                    "recursos": self._datos_recursos(evaluacion_recursos),
                },
            )

        evaluacion_recursos = self._evaluar_recursos_orden(orden)

        if not evaluacion_recursos.requiere_codex:
            if (
                len(orden.acciones) == 1
                and orden.acciones[0].tipo is TipoAccionNatural.EJECUTAR_TESTS
            ):
                accion = orden.acciones[0]
                rutas_solicitadas = accion.datos.get("rutas", ())
                if "ruta" in accion.datos:
                    rutas_solicitadas = (accion.datos["ruta"],)
                if isinstance(rutas_solicitadas, list):
                    rutas_solicitadas = tuple(rutas_solicitadas)
                if not isinstance(rutas_solicitadas, tuple):
                    rutas_solicitadas = ()
                try:
                    solicitud_local = SolicitudEjecucionLocal(
                        operacion=OperacionLocal.EJECUTAR_TESTS,
                        raiz=orden.worktree_candidato,
                        rutas=rutas_solicitadas,
                        nivel_tests=evaluacion_recursos.nivel_tests,
                        timeout_segundos=accion.datos.get(
                            "timeout_segundos", 120.0
                        ),
                    )
                    resultado_local = self._ejecutor_local.ejecutar(solicitud_local)
                except (ErrorSolicitudLocal, TypeError, OSError) as exc:
                    return self._error(
                        "LOCAL_EXECUTION_FAILED",
                        "la solicitud de ejecución local no es válida",
                        datos={
                            "recursos": self._datos_recursos(evaluacion_recursos),
                            "ejecucion_local": {
                                "operacion": OperacionLocal.EJECUTAR_TESTS.value,
                                "exito": False,
                                "returncode": None,
                                "stdout": "",
                                "stderr": "",
                                "timeout": False,
                                "error": str(exc),
                                "datos": {},
                            },
                        },
                    )
                datos = {
                    "recursos": self._datos_recursos(evaluacion_recursos),
                    "ejecucion_local": resultado_local.a_dict(),
                }
                if resultado_local.exito:
                    return self._ok(
                        "LOCAL_TESTS_EXECUTED",
                        "tests ejecutados localmente sin lanzar Codex",
                        datos=datos,
                    )
                return self._error(
                    "LOCAL_EXECUTION_FAILED",
                    "la ejecución local de tests no terminó correctamente",
                    datos=datos,
                )
            return self._error(
                "LOCAL_EXECUTOR_REQUIRED",
                "la política exige ejecución local y esta acción todavía no tiene ejecutor local",
                datos={"recursos": self._datos_recursos(evaluacion_recursos)},
            )

        repo_info = dict(orden.metadata.get("repo_contexto") or {})
        try:
            especificacion = EspecificacionTareaV02(
                orden_original=orden.texto_original, objetivo=orden.objetivo,
                repo=orden.repo_candidato, worktree=orden.worktree_candidato,
                rama=repo_info["rama"], commit_inicial=repo_info["commit_inicial"],
                modo=orden.modo_solicitado,
                acciones_permitidas=tuple(a.tipo.value for a in orden.acciones),
                rutas_permitidas=tuple(repo_info.get("rutas_permitidas", ())),
                acciones_prohibidas=tuple(
                    item for item, prohibida in (("COMMIT", not orden.commit), ("PUSH", not orden.push)) if prohibida
                ),
                rutas_protegidas=tuple(repo_info.get("rutas_protegidas", ())),
                condicion_finalizacion="; ".join(orden.condiciones) or "orden natural completada",
                restricciones_adicionales=orden.restricciones,
                commit_autorizado=orden.commit, push_autorizado=orden.push,
                presupuesto_api=orden.coste_maximo,
            )
        except (KeyError, TypeError, ValueError) as exc:
            return self._error("INTERPRETATION_INCOMPLETE", f"contexto de repo insuficiente: {exc}", requiere_intervencion=True)
        creada = self.crear_tarea(especificacion)
        if not creada.ok:
            return creada
        self._arranque.gestor_tareas.anadir_evento(
            creada.task_id, "NATURAL_ORDER_INTERPRETED",
            {"interpretation_id": orden.interpretation_id, "interpretacion": orden.a_dict()},
        )
        self._arranque.gestor_tareas.anadir_evento(
            creada.task_id,
            "RESOURCE_CLASSIFIED",
            self._datos_recursos(evaluacion_recursos),
        )
        for accion in orden.acciones:
            solicitud = self._solicitud_desde_accion_natural(creada.task_id, accion, orden)
            evaluada = self.evaluar_accion(solicitud)
            if evaluada.codigo in {"ACTION_BLOCKED", "ABSOLUTE_RULE_VIOLATION"}:
                tarea = self._arranque.gestor_tareas.cargar(creada.task_id)
                if tarea.estado is not EstadoTarea.BLOQUEADA:
                    self._arranque.gestor_tareas.actualizar_estado(tarea, EstadoTarea.BLOQUEADA)
                return replace(
                    evaluada, datos={**evaluada.datos, "tarea_creada": True}
                )
            if evaluada.requiere_intervencion:
                return evaluada
        resultado = self.ejecutar_tarea(creada.task_id)
        return replace(
            resultado,
            datos={
                **resultado.datos,
                "recursos": {
                    **self._datos_recursos(evaluacion_recursos),
                    **dict(resultado.datos.get("recursos") or {}),
                },
            },
        )

    def _contexto_interpretacion(self) -> ContextoInterpretacion:
        tareas = tuple(
            {
                "task_id": tarea.id, "objetivo": tarea.objetivo, "repo": tarea.repo,
                "worktree": tarea.worktree, "estado": tarea.estado.value,
            }
            for tarea in self._arranque.gestor_tareas.listar()
            if not tarea.es_terminal
        )
        decisiones = tuple(
            {
                "decision_id": decision.decision_id, "task_id": decision.task_id,
                "pregunta": decision.pregunta, "opciones": list(decision.opciones_permitidas),
            }
            for tarea in self._arranque.gestor_tareas.listar()
            for decision in [self._arranque.gestor_decisiones.obtener_decision_pendiente(tarea.id)]
            if decision is not None
        )
        retries = tuple(
            {"retry_id": item.retry_id, "task_id": item.task_id, "estado": item.estado.value}
            for item in self._arranque.servicio_reintentos.listar_reintentos()
            if item.estado.value == "PREPARADO"
        )
        return ContextoInterpretacion(tareas, decisiones, retries, self._repos_conocidos)

    @staticmethod
    def _evaluar_recursos_orden(orden: OrdenInterpretada) -> EvaluacionRecursos:
        """Clasifica recursos sin ejecutar Codex ni realizar llamadas externas."""

        tipos = tuple(accion.tipo for accion in orden.acciones)
        metadata = orden.metadata

        requiere_escritura = any(
            tipo in {
                TipoAccionNatural.MODIFICAR_ALCANCE,
                TipoAccionNatural.ESCRIBIR_FARMATIC,
            }
            for tipo in tipos
        )

        requiere_razonamiento = requiere_escritura or any(
            tipo is TipoAccionNatural.OTRA for tipo in tipos
        )

        accion = (
            "GIT_STATUS"
            if len(tipos) == 1 and tipos[0] is TipoAccionNatural.COMPROBAR_GIT
            else "EJECUTAR_TESTS"
            if len(tipos) == 1 and tipos[0] is TipoAccionNatural.EJECUTAR_TESTS
            else tipos[0].value
            if len(tipos) == 1
            else "ORDEN_COMPUESTA"
        )

        archivos_afectados = metadata.get("archivos_afectados", 0)
        if (
            not isinstance(archivos_afectados, int)
            or isinstance(archivos_afectados, bool)
            or archivos_afectados < 0
        ):
            archivos_afectados = 0

        tipo_trabajo = metadata.get("tipo_trabajo")
        if tipo_trabajo is None:
            tipo_trabajo = (
                TipoTrabajo.DESARROLLO
                if requiere_escritura
                else TipoTrabajo.DETERMINISTA
            )

        return PoliticaRecursos.evaluar(
            SolicitudRecursos(
                tipo_trabajo=tipo_trabajo,
                accion=accion,
                archivos_afectados=archivos_afectados,
                requiere_escritura_codigo=requiere_escritura,
                requiere_razonamiento=requiere_razonamiento,
                multiples_modulos=metadata.get("multiples_modulos") is True,
                riesgo_transversal=metadata.get("riesgo_transversal") is True,
                cierre_hito=metadata.get("cierre_hito") is True,
                commit_importante=metadata.get("commit_importante") is True,
                infraestructura_comun=metadata.get("infraestructura_comun") is True,
                incertidumbre_alta=metadata.get("incertidumbre_alta") is True,
                problema_dificil=metadata.get("problema_dificil") is True,
                escalado_significativo=metadata.get("escalado_significativo") is True,
                nivel_tests_explicito=metadata.get("nivel_tests_explicito"),
                nivel_tests_anterior=metadata.get("nivel_tests_anterior"),
                nivel_recurso_anterior=metadata.get("nivel_recurso_anterior"),
                coste_estimado=metadata.get("coste_estimado"),
                presupuesto_disponible=orden.coste_maximo,
                motivo_escalado=metadata.get("motivo_escalado"),
            )
        )

    @staticmethod
    def _datos_recursos(evaluacion: EvaluacionRecursos) -> dict[str, Any]:
        datos = evaluacion.a_dict()
        datos["motivos"] = list(evaluacion.motivos)
        return datos

    @staticmethod
    def _solicitud_desde_accion_natural(task_id: str, accion: Any, orden: OrdenInterpretada) -> SolicitudAccion:
        if accion.tipo is TipoAccionNatural.ESCRIBIR_FARMATIC:
            return SolicitudAccion(task_id, "UPDATE", "FARMATIC", contexto=orden.texto_original, clasificacion="TECNICA", metadata={"canal": "USUARIO_EXPLICITO"})
        if accion.tipo is TipoAccionNatural.COMMIT:
            return SolicitudAccion(task_id, "COMMIT", "GIT", datos={"tests_correctos": bool(accion.condicion.get("tests_correctos", True))}, autorizacion_requerida="COMMIT", contexto=orden.texto_original)
        if accion.tipo is TipoAccionNatural.PUSH:
            return SolicitudAccion(task_id, "PUSH", "GIT", autorizacion_requerida="PUSH", contexto=orden.texto_original)
        return SolicitudAccion(task_id, "EJECUTAR_TEST" if accion.tipo is TipoAccionNatural.EJECUTAR_TESTS else "MODIFICAR_CLASE_EN_ALCANCE", accion.alcance or "REPO", datos={"ruta": None}, contexto=orden.texto_original, clasificacion="TECNICA")

    @staticmethod
    def _nuevo_order_id() -> str:
        from uuid import uuid4
        return str(uuid4())

    def crear_tarea(
        self, especificacion: EspecificacionTareaV02
    ) -> ResultadoPublicoV02:
        no_listo = self._requiere_listo()
        if no_listo:
            return no_listo
        if not isinstance(especificacion, EspecificacionTareaV02):
            return self._error("INVALID_TASK_SPEC", "especificación de tarea inválida")
        if especificacion.clave_idempotencia:
            existente = self._tarea_por_clave(especificacion.clave_idempotencia)
            if existente is not None:
                return self._resultado_tarea(
                    True, "TASK_ALREADY_CREATED", "tarea ya creada", existente,
                    datos={"idempotente": True},
                )
        try:
            modo = ModoTarea(especificacion.modo)
            capacidad = CapacidadCheckpoint(especificacion.capacidad_checkpoint)
            entorno = EntornoTarea(
                repo=especificacion.repo,
                worktree=especificacion.worktree,
                rama=especificacion.rama,
                commit_inicial=especificacion.commit_inicial,
                modo=modo,
            )
            validacion = validar_entorno(entorno)
            if not validacion.es_valido:
                return self._error(
                    "INVALID_ENVIRONMENT",
                    "el entorno contratado no es válido",
                    errores=validacion.discrepancias,
                    datos=validacion.datos_evento(),
                )
            ocupante = self._arranque.gestor_entornos.obtener_reserva(
                especificacion.worktree
            )
            if ocupante is not None:
                return self._error(
                    "WORKTREE_BUSY",
                    "el worktree ya está reservado",
                    task_id=ocupante.task_id,
                    requiere_intervencion=True,
                )
            contrato = crear_contrato(
                objetivo=especificacion.objetivo,
                acciones_permitidas=especificacion.acciones_permitidas,
                rutas_permitidas=especificacion.rutas_permitidas,
                acciones_prohibidas=especificacion.acciones_prohibidas,
                rutas_protegidas=especificacion.rutas_protegidas,
                condiciones_finalizacion=especificacion.condicion_finalizacion,
                restricciones_adicionales=especificacion.restricciones_adicionales,
                commit_autorizado=especificacion.commit_autorizado,
                push_autorizado=especificacion.push_autorizado,
                presupuesto_api=especificacion.presupuesto_api,
            )
            tarea = self._arranque.gestor_tareas.crear_tarea(
                orden_original=especificacion.orden_original,
                repo=especificacion.repo,
                worktree=especificacion.worktree,
                rama=especificacion.rama,
                commit_inicial=especificacion.commit_inicial,
                modo=modo,
                contrato=contrato,
                capacidad_checkpoint=capacidad,
            )
            if especificacion.clave_idempotencia:
                self._arranque.gestor_tareas.anadir_evento(
                    tarea.id,
                    "PUBLIC_TASK_IDEMPOTENCY_KEY",
                    {"clave": especificacion.clave_idempotencia},
                )
            self._arranque.gestor_entornos.reservar_worktree(tarea.id)
            tarea = self._arranque.gestor_tareas.cargar(tarea.id)
            return self._resultado_tarea(
                True,
                "TASK_CREATED",
                "tarea creada y worktree reservado",
                tarea,
                datos={"entorno_validado": True, "lock_reservado": True},
            )
        except ConflictoWorktree as exc:
            if "tarea" in locals():
                self._bloquear_compensacion(tarea, "conflicto concurrente de worktree")
            return self._error(
                "WORKTREE_BUSY",
                "otro propietario ganó la reserva concurrente",
                task_id=exc.reserva.task_id,
                requiere_intervencion=True,
            )
        except (ValueError, ErrorEntorno) as exc:
            if "tarea" in locals():
                self._bloquear_compensacion(tarea, str(exc))
            return self._error(
                "INVALID_ENVIRONMENT", str(exc), requiere_intervencion=True
            )

    def obtener_tarea(self, task_id: str) -> ResultadoPublicoV02:
        try:
            tarea = self._arranque.gestor_tareas.cargar(task_id)
        except Exception:
            return self._error("TASK_NOT_FOUND", "tarea no encontrada", task_id=task_id)
        return self._resultado_tarea(True, "TASK_FOUND", "tarea encontrada", tarea)

    def listar_tareas(self) -> ResultadoPublicoV02:
        tareas = self._arranque.gestor_tareas.listar()
        return self._ok(
            "TASKS_LISTED",
            "tareas listadas",
            datos={"tareas": [self._tarea_dict(item) for item in tareas]},
        )

    def ejecutar_tarea(
        self,
        task_id: str,
        *,
        ejecutor: EjecutorCiclo | None = None,
        clave_idempotencia: str | None = None,
        autorizacion_coste: bool = False,
    ) -> ResultadoPublicoV02:
        no_listo = self._requiere_listo()
        if no_listo:
            return no_listo
        try:
            tarea = self._arranque.gestor_tareas.cargar(task_id)
        except Exception:
            return self._error("TASK_NOT_FOUND", "tarea no encontrada", task_id=task_id)
        if tarea.es_terminal:
            return self._resultado_tarea(
                False, "TASK_TERMINAL", "la tarea es terminal", tarea
            )
        if tarea.estado is EstadoTarea.BLOQUEADA:
            return self._resultado_tarea(
                False, "TASK_BLOCKED", "la tarea está bloqueada", tarea,
                requiere_intervencion=True,
            )
        pendiente = self._arranque.gestor_decisiones.obtener_decision_pendiente(task_id)
        if pendiente is not None:
            return self._resultado_tarea(
                False,
                "DECISION_REQUIRED",
                "la tarea espera una decisión",
                tarea,
                decision_id=pendiente.decision_id,
                requiere_intervencion=True,
            )
        clasificacion_recursos = self._clasificacion_recursos_tarea(tarea)
        barrera_coste = self._barrera_coste_pendiente(tarea)
        comprobacion_presupuesto = None
        coste_estimado = None
        if (
            clasificacion_recursos is not None
            and clasificacion_recursos.get("requiere_codex") is True
            and clasificacion_recursos.get("coste_estimado") is not None
        ):
            try:
                coste_estimado = self._decimal_monetario(
                    clasificacion_recursos["coste_estimado"]
                )
                comprobacion_presupuesto = (
                    self._arranque.contabilidad_recursos.comprobar_presupuesto(
                        coste_estimado,
                        referencia=tarea.id,
                    )
                )
            except (
                DatoMonetarioInvalido,
                ErrorContabilidadRecursos,
                InvalidOperation,
            ) as exc:
                return self._resultado_tarea(
                    False,
                    "INVALID_RESOURCE_COST",
                    str(exc),
                    tarea,
                    requiere_intervencion=True,
                )
        presupuesto_insuficiente = (
            comprobacion_presupuesto is not None
            and not comprobacion_presupuesto.exito
        )
        metricas_recursos = dict(clasificacion_recursos or {})
        if comprobacion_presupuesto is not None:
            metricas_recursos.update(comprobacion_presupuesto.resumen.a_dict())
            metricas_recursos["coste_estimado_operacion"] = (
                comprobacion_presupuesto.datos["coste_estimado"]
            )
            metricas_recursos["sobre_presupuesto"] = presupuesto_insuficiente
            metricas_recursos["exceso_estimado"] = (
                comprobacion_presupuesto.datos["exceso_estimado"]
            )
        if (
            barrera_coste is not None or presupuesto_insuficiente
        ) and not autorizacion_coste:
            if presupuesto_insuficiente:
                metricas_recursos["motivo_barrera_coste"] = (
                    "PRESUPUESTO_SEMANAL_INSUFICIENTE"
                )
            self._evento_tarea_unico(
                tarea.id,
                "RESOURCE_COST_AUTHORIZATION_REQUIRED",
                metricas_recursos,
            )
            return self._resultado_tarea(
                False,
                "REQUIERE_OK_PIO_COSTE",
                "la operación requiere autorización de coste antes de ejecutarse",
                tarea,
                requiere_intervencion=True,
                datos={"recursos": metricas_recursos},
            )
        if barrera_coste is not None or presupuesto_insuficiente:
            metricas_recursos["autorizacion_excepcional"] = presupuesto_insuficiente
            self._evento_tarea_unico(
                tarea.id,
                "RESOURCE_COST_AUTHORIZATION_GRANTED",
                metricas_recursos,
            )
            tarea = self._arranque.gestor_tareas.cargar(tarea.id)
        if clave_idempotencia:
            run_existente = self._run_por_clave(tarea, clave_idempotencia)
            if run_existente is not None:
                return self._resultado_run(
                    True, "RUN_ALREADY_EXECUTED", "ejecución ya aplicada",
                    tarea, run_existente, datos={"idempotente": True},
                )
        if ejecutor is None and self._ejecutor_factory is None:
            return self._resultado_tarea(
                False, "EXECUTOR_REQUIRED", "no hay ejecutor configurado", tarea
            )
        if clasificacion_recursos is not None and clasificacion_recursos.get(
            "requiere_codex"
        ) is True:
            if coste_estimado is not None:
                reserva_coste = self._arranque.contabilidad_recursos.reservar_coste(
                    tarea.id,
                    coste_estimado,
                    task_id=tarea.id,
                    nivel_recurso=clasificacion_recursos.get("nivel_recurso"),
                    autorizacion_excepcional=presupuesto_insuficiente,
                )
                metricas_recursos.update(reserva_coste.resumen.a_dict())
                metricas_recursos["reserva_coste"] = reserva_coste.datos.get(
                    "importe"
                )
        ejecutor_final = ejecutor or self._crear_ejecutor(tarea)
        if ejecutor_final is None:
            self._arranque.contabilidad_recursos.liberar_reserva(
                task_id=task_id,
                motivo="ejecutor no disponible",
            )
            return self._resultado_tarea(
                False, "EXECUTOR_REQUIRED", "no hay ejecutor configurado", tarea
            )
        preparacion = self._arranque.gestor_runs.preparar_run(task_id)
        if not preparacion.exito or preparacion.run is None:
            self._arranque.contabilidad_recursos.liberar_reserva(
                task_id=task_id,
                motivo="preparación de run rechazada",
            )
            return self._resultado_tarea(
                False,
                self._codigo_precondicion(preparacion.errores),
                "no se pudo preparar el run",
                self._arranque.gestor_tareas.cargar(task_id),
                requiere_intervencion=True,
                errores=preparacion.errores,
            )
        if (
            clasificacion_recursos is not None
            and clasificacion_recursos.get("requiere_codex") is True
            and coste_estimado is None
        ):
            desconocido = (
                self._arranque.contabilidad_recursos.registrar_coste_desconocido(
                    preparacion.run.run_id,
                    task_id=tarea.id,
                    run_id=preparacion.run.run_id,
                    nivel_recurso=clasificacion_recursos.get("nivel_recurso"),
                )
            )
            metricas_recursos.update(desconocido.resumen.a_dict())
            metricas_recursos["coste_desconocido"] = True
        controlada = self._arranque.ejecutar_run_controlado(
            preparacion.run.run_id, ejecutor_final
        )
        if not controlada.exito or controlada.ejecucion is None:
            return self._resultado_tarea(
                False, controlada.codigo, "ejecución rechazada", tarea,
                run_id=preparacion.run.run_id,
                errores=controlada.errores,
            )
        completada = controlada.ejecucion
        if clave_idempotencia:
            self._arranque.gestor_tareas.anadir_evento(
                task_id,
                "PUBLIC_EXECUTION_IDEMPOTENCY_KEY",
                {"clave": clave_idempotencia, "run_id": completada.resultado.run_id},
            )
        tarea = self._arranque.gestor_tareas.cargar(task_id)
        evaluacion = completada.evaluacion_supervisor
        ejecucion_visible = completada
        while ejecucion_visible.auto_resume is not None:
            ejecucion_visible = ejecucion_visible.auto_resume
        decision_visible = ejecucion_visible.decision or completada.decision
        evaluacion_visible = ejecucion_visible.evaluacion_supervisor or evaluacion
        if evaluacion_visible and evaluacion_visible.decision is DecisionSupervisor.BLOCK:
            codigo = "ACTION_BLOCKED"
        elif decision_visible is not None:
            codigo = "DECISION_REQUIRED"
        else:
            codigo = "ACTION_AUTO_APPROVED" if completada.auto_resume is not None else "RUN_COMPLETED"
        return self._resultado_run(
            codigo != "ACTION_BLOCKED",
            codigo,
            "ciclo ejecutado y persistido",
            tarea,
            self._arranque.gestor_runs.obtener_run(ejecucion_visible.resultado.run_id),
            decision_id=(decision_visible.decision_id if decision_visible else None),
            requiere_intervencion=(decision_visible is not None or codigo == "ACTION_BLOCKED"),
            datos={
                "estado_interno": ejecucion_visible.resultado.estado_interno.value,
                "resumen": ejecucion_visible.resultado.resumen,
                "evaluacion_supervisor": evaluacion_visible.a_dict() if evaluacion_visible else None,
                "auto_resume": completada.auto_resume is not None,
                "recursos": metricas_recursos,
            },
        )

    def evaluar_accion(self, solicitud: SolicitudAccion) -> ResultadoPublicoV02:
        """Expone una evaluación determinista sin ejecutar la acción."""
        no_listo = self._requiere_listo()
        if no_listo:
            return no_listo
        try:
            evaluacion = self._arranque.supervisor.evaluar(solicitud)
            tarea = self._arranque.gestor_tareas.cargar(solicitud.task_id)
        except Exception as exc:
            return self._error("INVALID_SUPERVISOR_REQUEST", str(exc))
        return self._resultado_tarea(
            evaluacion.decision is not DecisionSupervisor.BLOCK,
            evaluacion.codigo,
            evaluacion.motivo,
            tarea,
            decision_id=evaluacion.decision_id,
            requiere_intervencion=evaluacion.decision in {
                DecisionSupervisor.REQUIRE_PIO, DecisionSupervisor.BLOCK
            },
            datos={"evaluacion": evaluacion.a_dict()},
            warnings=evaluacion.warnings,
        )

    def listar_reglas(self, *, solo_activas: bool = True) -> ResultadoPublicoV02:
        reglas = self._arranque.gestor_reglas.listar_reglas(
            activas=True if solo_activas else None
        )
        return self._ok(
            "RULES_LISTED", "reglas listadas",
            datos={"reglas": [item.a_dict() for item in reglas]},
        )

    def registrar_regla(
        self, *, nombre: str, ambito: str, condicion: dict[str, Any],
        accion: dict[str, Any], prioridad: int, origen: str,
        metadata: dict[str, Any] | None = None,
    ) -> ResultadoPublicoV02:
        """Registra únicamente una regla permanente solicitada explícitamente."""
        try:
            regla = self._arranque.gestor_reglas.crear_regla(
                nombre=nombre, ambito=ambito, condicion=condicion,
                accion=accion, prioridad=prioridad, origen=origen,
                metadata=metadata, tipo=TipoRegla.FUNCIONAL,
            )
        except (ReglaInvalida, ValueError) as exc:
            return self._error("INVALID_RULE", str(exc))
        return self._ok(
            "RULE_REGISTERED", "regla funcional explícita registrada",
            datos={"regla": regla.a_dict()},
        )

    def desactivar_regla(self, rule_id: str, *, motivo: str = "desactivación explícita") -> ResultadoPublicoV02:
        try:
            regla = self._arranque.gestor_reglas.desactivar_regla(rule_id, motivo=motivo)
        except Exception as exc:
            return self._error("RULE_DEACTIVATION_REJECTED", str(exc))
        return self._ok(
            "RULE_DEACTIVATED", "regla desactivada sin borrar su histórico",
            datos={"regla": regla.a_dict()},
        )

    def obtener_evaluacion(self, task_id: str, evaluation_id: str) -> ResultadoPublicoV02:
        try:
            tarea = self._arranque.gestor_tareas.cargar(task_id)
        except Exception:
            return self._error("TASK_NOT_FOUND", "tarea no encontrada", task_id=task_id)
        evento = next(
            (item for item in reversed(tarea.historial)
             if item.tipo == "SUPERVISOR_EVALUATED"
             and item.datos.get("evaluation_id") == evaluation_id),
            None,
        )
        if evento is None:
            return self._resultado_tarea(False, "EVALUATION_NOT_FOUND", "evaluación no encontrada", tarea)
        return self._resultado_tarea(
            True, "EVALUATION_FOUND", "evaluación encontrada", tarea,
            datos={"evaluacion": evento.datos["evaluacion"]},
        )

    def obtener_tarea_activa(self) -> ResultadoPublicoV02:
        activas = [item for item in self._arranque.gestor_tareas.listar() if not item.es_terminal]
        if not activas:
            return self._error("NO_ACTIVE_TASK", "no hay tarea activa")
        tarea = sorted(activas, key=lambda item: (item.fecha_actualizacion, item.id))[-1]
        return self._resultado_tarea(True, "ACTIVE_TASK_FOUND", "tarea activa", tarea)

    def obtener_decision_pendiente(
        self, task_id: str | None = None
    ) -> ResultadoPublicoV02:
        try:
            tareas = (
                [self._arranque.gestor_tareas.cargar(task_id)]
                if task_id is not None
                else self._arranque.gestor_tareas.listar()
            )
        except Exception:
            return self._error("TASK_NOT_FOUND", "tarea no encontrada", task_id=task_id)
        for tarea in tareas:
            decision = self._arranque.gestor_decisiones.obtener_decision_pendiente(tarea.id)
            if decision is not None:
                return self._ok(
                    "DECISION_PENDING",
                    "decisión pendiente encontrada",
                    task_id=tarea.id,
                    run_id=decision.run_id,
                    decision_id=decision.decision_id,
                    estado_tarea=tarea.estado.value,
                    requiere_intervencion=True,
                    datos={
                        "pregunta": decision.pregunta,
                        "contexto": decision.contexto,
                        "opciones": list(decision.opciones_permitidas),
                    },
                )
        return self._error("NO_PENDING_DECISION", "no hay decisión pendiente")

    def responder_decision(
        self,
        task_id: str,
        *,
        opcion: str | None = None,
        texto: str | None = None,
        ejecutor: EjecutorCiclo | None = None,
    ) -> ResultadoPublicoV02:
        no_listo = self._requiere_listo()
        if no_listo:
            return no_listo
        try:
            tarea = self._arranque.gestor_tareas.cargar(task_id)
        except Exception:
            return self._error("TASK_NOT_FOUND", "tarea no encontrada", task_id=task_id)
        decision = self._arranque.gestor_decisiones.obtener_decision_pendiente(task_id)
        if decision is None:
            aplicada = next(
                (
                    item for item in reversed(
                        self._arranque.gestor_decisiones.listar_decisiones(task_id)
                    )
                    if item.estado is EstadoDecision.APLICADA
                ),
                None,
            )
            if aplicada is not None:
                run = self._arranque.gestor_runs.obtener_run(aplicada.resume_run_id)
                return self._resultado_run(
                    True, "DECISION_ALREADY_APPLIED", "decisión ya aplicada",
                    tarea, run, decision_id=aplicada.decision_id,
                    datos={"idempotente": True},
                )
            return self._resultado_tarea(
                False, "INVALID_DECISION", "no existe decisión pendiente", tarea
            )
        ejecutor_final = ejecutor or self._crear_ejecutor(tarea)
        if ejecutor_final is None:
            return self._resultado_tarea(
                False, "EXECUTOR_REQUIRED", "no hay ejecutor configurado", tarea,
                decision_id=decision.decision_id,
            )
        try:
            reanudacion = ServicioDecisiones(
                self._arranque.gestor_decisiones, self._arranque.gestor_runs
            ).responder_y_reanudar(
                decision.decision_id,
                ejecutor_final,
                opcion=opcion,
                texto=texto,
                task_id_esperado=task_id,
                run_id_esperado=decision.run_id,
            )
        except Exception as exc:
            return self._resultado_tarea(
                False, "INVALID_DECISION", str(exc),
                self._arranque.gestor_tareas.cargar(task_id),
                decision_id=decision.decision_id,
                requiere_intervencion=True,
            )
        tarea = self._arranque.gestor_tareas.cargar(task_id)
        return self._resultado_run(
            True,
            "DECISION_APPLIED",
            "decisión persistida y resume ejecutado",
            tarea,
            reanudacion.run,
            decision_id=reanudacion.decision.decision_id,
            datos={"idempotente": reanudacion.idempotente},
        )

    def cancelar_tarea(self, task_id: str) -> ResultadoPublicoV02:
        try:
            tarea = self._arranque.gestor_tareas.cargar(task_id)
        except Exception:
            return self._error("TASK_NOT_FOUND", "tarea no encontrada", task_id=task_id)
        if tarea.estado is EstadoTarea.CANCELADA:
            return self._resultado_tarea(
                True, "TASK_ALREADY_CANCELLED", "tarea ya cancelada", tarea,
                datos={"idempotente": True},
            )
        if tarea.estado is EstadoTarea.FINALIZADA:
            return self._resultado_tarea(
                False, "TASK_TERMINAL", "tarea ya finalizada", tarea
            )
        run = self._arranque.gestor_runs.obtener_ultimo_run(task_id)
        if run is not None and run.estado_interno is EstadoInternoRun.INICIADO:
            proceso, _ = self._arranque.servicio_recuperacion._proceso_persistido(run)
            if proceso is not None:
                observado = self._arranque.servicio_recuperacion.inspector_procesos.inspeccionar(
                    proceso["pid"]
                )
                if observado.existe:
                    return self._resultado_tarea(
                        False,
                        "ACTIVE_PROCESS_CONTROL_REQUIRED",
                        "hay un proceso activo; no se realiza kill agresivo",
                        tarea,
                        run_id=run.run_id,
                        requiere_intervencion=True,
                    )
        pendiente = self._arranque.gestor_decisiones.obtener_decision_pendiente(task_id)
        if pendiente is not None:
            self._arranque.gestor_decisiones.cancelar_decision(pendiente.decision_id)
        tarea = self._arranque.gestor_tareas.actualizar_estado(task_id, EstadoTarea.CANCELADA)
        reserva = self._arranque.gestor_entornos.obtener_reserva(tarea.worktree)
        if reserva is not None and reserva.task_id == task_id:
            self._arranque.gestor_entornos.liberar_worktree(task_id, tarea.worktree)
        self._arranque.contabilidad_recursos.liberar_reserva(
            task_id=task_id,
            motivo="tarea cancelada antes del cierre de coste",
            fecha=(
                datetime.fromisoformat(run.ultima_actualizacion)
                if run is not None else None
            ),
        )
        return self._resultado_tarea(
            True,
            "TASK_CANCELLED",
            "tarea cancelada; histórico conservado y lock liberado",
            self._arranque.gestor_tareas.cargar(task_id),
            run_id=run.run_id if run else None,
        )

    def preparar_reintento(
        self, task_id: str, checkpoint_id: str | None = None
    ) -> ResultadoPublicoV02:
        no_listo = self._requiere_listo()
        if no_listo:
            return no_listo
        resultado = self._arranque.servicio_reintentos.preparar_reintento(
            task_id, checkpoint_id
        )
        return self._resultado_retry(resultado)

    def ejecutar_reintento(
        self,
        retry_id: str,
        *,
        ejecutor: EjecutorCiclo | None = None,
        autorizacion_coste: bool = False,
        coste_estimado: Decimal | str | int | None = None,
    ) -> ResultadoPublicoV02:
        resultado = self._arranque.servicio_reintentos.ejecutar_reintento(
            retry_id,
            ejecutor,
            autorizacion_coste=autorizacion_coste,
            coste_estimado=coste_estimado,
        )
        return self._resultado_retry(resultado)

    def consultar_presupuesto(
        self, *, semana_id: str | None = None
    ) -> ResultadoPublicoV02:
        """Consulta LOCAL_ONLY del presupuesto semanal persistente."""
        try:
            resumen = self._arranque.contabilidad_recursos.consultar_presupuesto(
                semana_id=semana_id
            )
        except ErrorContabilidadRecursos as exc:
            return self._error("BUDGET_QUERY_FAILED", str(exc))
        return self._ok(
            "LOCAL_WEEKLY_BUDGET_QUERY",
            "presupuesto semanal consultado localmente",
            datos={
                "presupuesto": resumen.a_dict(),
                "recursos": {
                    "nivel_recurso": "LOCAL_ONLY",
                    "requiere_codex": False,
                },
            },
        )

    def consultar_consumo(
        self,
        *,
        semana_id: str | None = None,
        historico: bool = False,
    ) -> ResultadoPublicoV02:
        """Consulta LOCAL_ONLY del consumo actual, semanal o histórico."""
        try:
            consumo = self._arranque.contabilidad_recursos.consultar_consumo(
                semana_id=semana_id,
                historico=historico,
            )
        except ErrorContabilidadRecursos as exc:
            return self._error("CONSUMPTION_QUERY_FAILED", str(exc))
        return self._ok(
            "LOCAL_RESOURCE_CONSUMPTION_QUERY",
            "consumo de recursos consultado localmente",
            datos={
                "consumo": consumo,
                "recursos": {
                    "nivel_recurso": "LOCAL_ONLY",
                    "requiere_codex": False,
                },
            },
        )

    def establecer_presupuesto_semanal(
        self,
        importe: Decimal | str | int,
        *,
        motivo: str | None = None,
    ) -> ResultadoPublicoV02:
        """Actualiza explícitamente el techo de la semana actual."""
        try:
            resultado = (
                self._arranque.contabilidad_recursos.establecer_presupuesto_semanal(
                    importe,
                    motivo=motivo,
                )
            )
        except (DatoMonetarioInvalido, ErrorContabilidadRecursos) as exc:
            return self._error("INVALID_WEEKLY_BUDGET", str(exc))
        return self._ok(
            resultado.codigo,
            "presupuesto semanal actualizado explícitamente",
            datos={
                "presupuesto": resultado.resumen.a_dict(),
                "idempotente": resultado.idempotente,
                "evento": resultado.datos,
            },
        )

    def registrar_coste_real(
        self,
        run_id: str,
        importe: Decimal | str | int,
        *,
        origen: str,
    ) -> ResultadoPublicoV02:
        """Registra coste real explícito sin derivarlo de una estimación."""
        try:
            run = self._arranque.gestor_runs.obtener_run(run_id)
            if run.resultado is None:
                return self._error(
                    "RUN_RESULT_REQUIRED",
                    "el run debe tener resultado antes de registrar coste real",
                    run_id=run_id,
                    task_id=run.task_id,
                )
            tarea = self._arranque.gestor_tareas.cargar(run.task_id)
            clasificacion = self._clasificacion_recursos_tarea(tarea) or {}
            fecha = datetime.fromisoformat(run.resultado.timestamp)
            resultado = self._arranque.contabilidad_recursos.registrar_coste_real(
                run_id,
                importe,
                task_id=run.task_id,
                retry_id=run.retry_id,
                origen=origen,
                nivel_recurso=clasificacion.get("nivel_recurso"),
                fecha=fecha,
            )
        except (DatoMonetarioInvalido, ErrorContabilidadRecursos, ValueError) as exc:
            return self._error("INVALID_RESOURCE_COST", str(exc), run_id=run_id)
        return self._ok(
            resultado.codigo,
            "coste real registrado localmente",
            task_id=run.task_id,
            run_id=run_id,
            datos={
                "presupuesto": resultado.resumen.a_dict(),
                "coste": resultado.datos,
                "idempotente": resultado.idempotente,
            },
        )

    def resumen_sistema(self) -> ResumenSistemaV02:
        tareas = self._arranque.gestor_tareas.listar()
        decisiones = [
            decision
            for tarea in tareas
            for decision in self._arranque.gestor_decisiones.listar_decisiones(tarea.id)
            if decision.estado is EstadoDecision.PENDIENTE
        ]
        retries = self._arranque.servicio_reintentos.listar_reintentos()
        warnings = list(self._arranque.servicio_recuperacion.ultimo_diagnostico_locks)
        return ResumenSistemaV02(
            estado_global=self.estado().value,
            tareas_activas=sum(not item.es_terminal for item in tareas),
            tareas_esperando_decision=sum(item.estado is EstadoTarea.ESPERANDO_DECISION for item in tareas),
            tareas_bloqueadas=sum(item.estado is EstadoTarea.BLOQUEADA for item in tareas),
            tareas_recuperando=sum(item.estado is EstadoTarea.RECUPERANDO for item in tareas),
            worktrees_ocupados=len(self._arranque.gestor_entornos.listar_reservas()),
            decisiones_pendientes=len(decisiones),
            retries_preparados=sum(item.estado.value == "PREPARADO" for item in retries),
            warnings=tuple(warnings),
        )

    def _crear_ejecutor(self, tarea: Tarea) -> EjecutorCiclo | None:
        return self._ejecutor_factory(tarea) if self._ejecutor_factory else None

    @staticmethod
    def _clasificacion_recursos_tarea(tarea: Tarea) -> dict[str, Any] | None:
        evento = next(
            (
                item for item in reversed(tarea.historial)
                if item.tipo == "RESOURCE_CLASSIFIED"
            ),
            None,
        )
        return dict(evento.datos) if evento is not None else None

    @staticmethod
    def _barrera_coste_pendiente(tarea: Tarea) -> dict[str, Any] | None:
        indice_clasificacion = next(
            (
                indice
                for indice in range(len(tarea.historial) - 1, -1, -1)
                if tarea.historial[indice].tipo == "RESOURCE_CLASSIFIED"
            ),
            None,
        )
        if indice_clasificacion is None:
            return None
        clasificacion = tarea.historial[indice_clasificacion]
        if clasificacion.datos.get("requiere_ok_pio_coste") is not True:
            return None
        if any(
            evento.tipo == "RESOURCE_COST_AUTHORIZATION_GRANTED"
            for evento in tarea.historial[indice_clasificacion + 1 :]
        ):
            return None
        return dict(clasificacion.datos)

    def _evento_tarea_unico(
        self, task_id: str, tipo: str, datos: dict[str, Any]
    ) -> None:
        tarea = self._arranque.gestor_tareas.cargar(task_id)
        if any(evento.tipo == tipo and evento.datos == datos for evento in tarea.historial):
            return
        self._arranque.gestor_tareas.anadir_evento(task_id, tipo, datos)

    @staticmethod
    def _decimal_monetario(valor: Any) -> Decimal:
        if isinstance(valor, bool):
            raise DatoMonetarioInvalido("el importe no puede ser booleano")
        if isinstance(valor, Decimal):
            return valor
        return Decimal(str(valor))

    def _requiere_listo(self) -> ResultadoPublicoV02 | None:
        if self.estado() is EstadoGlobalOrquestador.LISTO:
            return None
        return self._error(
            "ORCHESTRATOR_NOT_READY",
            "el Orquestador debe completar iniciar() y quedar LISTO",
            requiere_intervencion=self.estado() is EstadoGlobalOrquestador.BLOQUEADO,
        )

    def _tarea_por_clave(self, clave: str) -> Tarea | None:
        return next(
            (
                tarea for tarea in self._arranque.gestor_tareas.listar()
                if any(
                    evento.tipo == "PUBLIC_TASK_IDEMPOTENCY_KEY"
                    and evento.datos.get("clave") == clave
                    for evento in tarea.historial
                )
            ),
            None,
        )

    def _run_por_clave(self, tarea: Tarea, clave: str) -> RunPersistente | None:
        evento = next(
            (
                item for item in reversed(tarea.historial)
                if item.tipo == "PUBLIC_EXECUTION_IDEMPOTENCY_KEY"
                and item.datos.get("clave") == clave
            ),
            None,
        )
        return (
            self._arranque.gestor_runs.obtener_run(evento.datos["run_id"])
            if evento else None
        )

    def _bloquear_compensacion(self, tarea: Tarea, causa: str) -> None:
        actual = self._arranque.gestor_tareas.cargar(tarea.id)
        if actual.estado is not EstadoTarea.BLOQUEADA:
            self._arranque.gestor_tareas.actualizar_estado(actual, EstadoTarea.BLOQUEADA)
        self._arranque.gestor_tareas.anadir_evento(
            tarea.id, "PUBLIC_TASK_CREATION_COMPENSATED", {"causa": causa}
        )

    def _resultado_arranque(self, resultado: ResultadoArranque) -> ResultadoPublicoV02:
        return ResultadoPublicoV02(
            ok=resultado.estado_global is EstadoGlobalOrquestador.LISTO,
            codigo=("ORCHESTRATOR_READY" if resultado.estado_global is EstadoGlobalOrquestador.LISTO else "ORCHESTRATOR_BLOCKED"),
            mensaje="arranque y recuperación completados",
            estado_global=resultado.estado_global.value,
            requiere_intervencion=resultado.estado_global is EstadoGlobalOrquestador.BLOQUEADO,
            datos=resultado.a_dict(),
            warnings=resultado.warnings,
            errores=resultado.errores,
        )

    def _resultado_retry(self, resultado: ResultadoOperacionReintento) -> ResultadoPublicoV02:
        plan = resultado.retry
        run = resultado.run
        tarea = (
            self._arranque.gestor_tareas.cargar(plan.task_id) if plan else None
        )
        return ResultadoPublicoV02(
            ok=resultado.exito,
            codigo=resultado.codigo,
            mensaje=("operación de retry completada" if resultado.exito else "operación de retry rechazada"),
            task_id=plan.task_id if plan else None,
            run_id=run.run_id if run else (plan.run_nuevo_id if plan else None),
            estado_tarea=tarea.estado.value if tarea else None,
            estado_global=self.estado().value,
            requiere_intervencion=not resultado.exito,
            datos={
                "retry_id": plan.retry_id if plan else None,
                "estado_retry": plan.estado.value if plan else None,
                "estrategia": plan.estrategia.value if plan else None,
                "checkpoint_id": plan.checkpoint_id if plan else None,
                "idempotente": resultado.idempotente,
                "recursos": dict(resultado.metricas_recursos),
            },
            errores=resultado.errores,
        )

    @staticmethod
    def _codigo_precondicion(errores: tuple[str, ...]) -> str:
        texto = " ".join(errores).casefold()
        if "terminal" in texto:
            return "TASK_TERMINAL"
        if "bloque" in texto:
            return "TASK_BLOCKED"
        if "lock" in texto:
            return "WORKTREE_BUSY"
        return "INVALID_ENVIRONMENT"

    @staticmethod
    def _tarea_dict(tarea: Tarea) -> dict[str, Any]:
        return {
            "task_id": tarea.id,
            "objetivo": tarea.objetivo,
            "estado": tarea.estado.value,
            "worktree": tarea.worktree,
            "capacidad_checkpoint": tarea.capacidad_checkpoint.value,
        }

    def _resultado_tarea(
        self,
        ok: bool,
        codigo: str,
        mensaje: str,
        tarea: Tarea,
        *,
        run_id: str | None = None,
        decision_id: str | None = None,
        requiere_intervencion: bool = False,
        datos: dict[str, Any] | None = None,
        warnings: tuple[str, ...] = (),
        errores: tuple[str, ...] = (),
    ) -> ResultadoPublicoV02:
        return ResultadoPublicoV02(
            ok, codigo, mensaje, tarea.id, run_id, decision_id,
            tarea.estado.value, self.estado().value, requiere_intervencion,
            datos or self._tarea_dict(tarea), warnings, errores,
        )

    def _resultado_run(
        self,
        ok: bool,
        codigo: str,
        mensaje: str,
        tarea: Tarea,
        run: RunPersistente | None,
        *,
        decision_id: str | None = None,
        requiere_intervencion: bool = False,
        datos: dict[str, Any] | None = None,
    ) -> ResultadoPublicoV02:
        return self._resultado_tarea(
            ok, codigo, mensaje, tarea,
            run_id=run.run_id if run else None,
            decision_id=decision_id,
            requiere_intervencion=requiere_intervencion,
            datos=datos,
        )

    def _ok(self, codigo: str, mensaje: str, **kwargs: Any) -> ResultadoPublicoV02:
        return ResultadoPublicoV02(
            True, codigo, mensaje,
            estado_global=self.estado().value,
            **kwargs,
        )

    def _error(
        self,
        codigo: str,
        mensaje: str,
        *,
        errores: tuple[str, ...] = (),
        **kwargs: Any,
    ) -> ResultadoPublicoV02:
        return ResultadoPublicoV02(
            False, codigo, mensaje,
            estado_global=self.estado().value,
            errores=errores,
            **kwargs,
        )
