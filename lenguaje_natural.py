"""Interpretación segura y tipada de órdenes naturales para V0.2.10.

Esta capa interpreta datos del canal de usuario; nunca decide reglas de negocio ni
ejecuta acciones. La autoridad permanece en SupervisorV02 y en los contratos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Protocol
import unicodedata
from uuid import UUID, uuid4


ORDEN_SCHEMA_VERSION = 1


class ErrorInterpretacion(RuntimeError):
    pass


class InterpretacionInvalida(ErrorInterpretacion, ValueError):
    pass


class CanalEntradaInvalido(ErrorInterpretacion):
    pass


class TipoIntencion(str, Enum):
    CREAR_TAREA = "CREAR_TAREA"
    CONTINUAR_TAREA = "CONTINUAR_TAREA"
    CONSULTAR_ESTADO = "CONSULTAR_ESTADO"
    RESPONDER_DECISION = "RESPONDER_DECISION"
    CANCELAR_TAREA = "CANCELAR_TAREA"
    PREPARAR_REINTENTO = "PREPARAR_REINTENTO"
    EJECUTAR_REINTENTO = "EJECUTAR_REINTENTO"
    CONSULTAR_RESULTADO = "CONSULTAR_RESULTADO"
    CONSULTAR_PRESUPUESTO = "CONSULTAR_PRESUPUESTO"
    CONSULTAR_CONSUMO = "CONSULTAR_CONSUMO"
    REGISTRAR_REGLA = "REGISTRAR_REGLA"
    DESACTIVAR_REGLA = "DESACTIVAR_REGLA"
    OTRA = "OTRA"


class TipoAccionNatural(str, Enum):
    CONSULTAR_ESTADO = "CONSULTAR_ESTADO"
    CONSULTAR_TAREAS = "CONSULTAR_TAREAS"
    CONSULTAR_DECISIONES = "CONSULTAR_DECISIONES"
    CONSULTAR_RESULTADO = "CONSULTAR_RESULTADO"
    CONSULTAR_PRESUPUESTO = "CONSULTAR_PRESUPUESTO"
    CONSULTAR_CONSUMO = "CONSULTAR_CONSUMO"
    COMPROBAR_GIT = "COMPROBAR_GIT"
    ANALIZAR_ALCANCE = "ANALIZAR_ALCANCE"
    MODIFICAR_ALCANCE = "MODIFICAR_ALCANCE"
    EJECUTAR_TESTS = "EJECUTAR_TESTS"
    COMMIT = "COMMIT"
    PUSH = "PUSH"
    CONTINUAR = "CONTINUAR"
    CANCELAR = "CANCELAR"
    RESPONDER_DECISION = "RESPONDER_DECISION"
    PREPARAR_REINTENTO = "PREPARAR_REINTENTO"
    EJECUTAR_REINTENTO = "EJECUTAR_REINTENTO"
    REGISTRAR_REGLA = "REGISTRAR_REGLA"
    DESACTIVAR_REGLA = "DESACTIVAR_REGLA"
    ESCRIBIR_FARMATIC = "ESCRIBIR_FARMATIC"
    OTRA = "OTRA"


class FuenteInterpretacion(str, Enum):
    PARSER_LOCAL = "PARSER_LOCAL"
    PROVEEDOR_INYECTADO = "PROVEEDOR_INYECTADO"


class CanalOrden(str, Enum):
    USUARIO_EXPLICITO = "USUARIO_EXPLICITO"
    ARCHIVO = "ARCHIVO"
    STDOUT = "STDOUT"
    README = "README"
    DOCUMENTO_EXTERNO = "DOCUMENTO_EXTERNO"


def _ahora_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalizar(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto.casefold())
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def _timestamp_valido(valor: str) -> bool:
    try:
        return datetime.fromisoformat(valor).tzinfo is not None
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True)
class AccionOrden:
    orden: int
    tipo: TipoAccionNatural | str
    alcance: str | None = None
    condicion: dict[str, Any] = field(default_factory=dict)
    datos: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.orden, bool) or not isinstance(self.orden, int) or self.orden < 1:
            raise InterpretacionInvalida("orden de acción debe ser entero positivo")
        try:
            object.__setattr__(self, "tipo", TipoAccionNatural(self.tipo))
        except ValueError as exc:
            raise InterpretacionInvalida("acción fuera del catálogo") from exc
        if not isinstance(self.condicion, dict) or not isinstance(self.datos, dict):
            raise InterpretacionInvalida("condicion/datos de acción deben ser objetos")

    def a_dict(self) -> dict[str, Any]:
        return {"orden": self.orden, "tipo": self.tipo.value, "alcance": self.alcance, "condicion": self.condicion, "datos": self.datos}

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> "AccionOrden":
        permitidos = {"orden", "tipo", "alcance", "condicion", "datos"}
        if set(datos) != permitidos:
            raise InterpretacionInvalida("campos inválidos en acción")
        return cls(**datos)


@dataclass(frozen=True)
class AutorizacionesOrden:
    escritura: bool
    commit: bool
    commit_condicionado_tests: bool
    push: bool

    def __post_init__(self) -> None:
        if not all(isinstance(v, bool) for v in (self.escritura, self.commit, self.commit_condicionado_tests, self.push)):
            raise InterpretacionInvalida("autorizaciones deben ser booleanas")
        if self.commit_condicionado_tests and not self.commit:
            raise InterpretacionInvalida("commit condicionado requiere commit autorizado")

    def a_dict(self) -> dict[str, bool]:
        return {"escritura": self.escritura, "commit": self.commit, "commit_condicionado_tests": self.commit_condicionado_tests, "push": self.push}

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> "AutorizacionesOrden":
        if set(datos) != {"escritura", "commit", "commit_condicionado_tests", "push"}:
            raise InterpretacionInvalida("campos inválidos en autorizaciones")
        return cls(**datos)


@dataclass(frozen=True)
class OrdenInterpretada:
    interpretation_id: str
    schema_version: int
    texto_original: str
    objetivo: str
    tipo_intencion: TipoIntencion | str
    repo_candidato: str | None
    worktree_candidato: str | None
    modo_solicitado: str
    acciones: tuple[AccionOrden, ...]
    restricciones: tuple[str, ...]
    autorizaciones: AutorizacionesOrden
    condiciones: tuple[str, ...]
    coste_maximo: float | None
    commit: bool
    push: bool
    task_id_referencia: str | None
    decision_id_referencia: str | None
    retry_id_referencia: str | None
    confianza: float
    ambigua: bool
    ambiguedades: tuple[str, ...]
    datos_faltantes: tuple[str, ...]
    referencias_no_resueltas: tuple[str, ...]
    timestamp: str
    metadata: dict[str, Any]
    fuente: FuenteInterpretacion | str

    def __post_init__(self) -> None:
        try:
            UUID(self.interpretation_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise InterpretacionInvalida("interpretation_id debe ser UUID") from exc
        if self.schema_version != ORDEN_SCHEMA_VERSION:
            raise InterpretacionInvalida("schema_version no soportada")
        if not isinstance(self.texto_original, str) or not self.texto_original.strip():
            raise InterpretacionInvalida("texto_original obligatorio")
        if not isinstance(self.objetivo, str):
            raise InterpretacionInvalida("objetivo debe ser texto")
        object.__setattr__(self, "tipo_intencion", TipoIntencion(self.tipo_intencion))
        if self.modo_solicitado not in {"read_only", "workspace_write"}:
            raise InterpretacionInvalida("modo_solicitado inválido")
        object.__setattr__(self, "acciones", tuple(self.acciones))
        ordenes = [item.orden for item in self.acciones]
        if ordenes != list(range(1, len(ordenes) + 1)):
            raise InterpretacionInvalida("acciones deben ser secuenciales desde 1")
        for campo in ("restricciones", "condiciones", "ambiguedades", "datos_faltantes", "referencias_no_resueltas"):
            valores = tuple(getattr(self, campo))
            if not all(isinstance(v, str) and v.strip() for v in valores):
                raise InterpretacionInvalida(f"{campo} debe contener textos")
            object.__setattr__(self, campo, valores)
        if not isinstance(self.autorizaciones, AutorizacionesOrden):
            raise InterpretacionInvalida("autorizaciones inválidas")
        if self.commit != self.autorizaciones.commit or self.push != self.autorizaciones.push:
            raise InterpretacionInvalida("commit/push incoherentes con autorizaciones")
        if self.modo_solicitado == "read_only" and self.autorizaciones.escritura:
            raise InterpretacionInvalida("read_only no puede autorizar escritura")
        tipos_accion = {accion.tipo for accion in self.acciones}
        if TipoAccionNatural.COMMIT in tipos_accion and not self.autorizaciones.commit:
            raise InterpretacionInvalida("acción COMMIT sin autorización representable")
        if TipoAccionNatural.PUSH in tipos_accion and not self.autorizaciones.push:
            raise InterpretacionInvalida("acción PUSH sin autorización representable")
        if (self.repo_candidato is None) != (self.worktree_candidato is None):
            raise InterpretacionInvalida("repo y worktree candidatos deben declararse juntos")
        if self.coste_maximo is not None and (isinstance(self.coste_maximo, bool) or self.coste_maximo < 0):
            raise InterpretacionInvalida("coste_maximo inválido")
        if isinstance(self.confianza, bool) or not 0 <= self.confianza <= 1:
            raise InterpretacionInvalida("confianza debe estar entre 0 y 1")
        if self.ambigua != bool(self.ambiguedades or self.referencias_no_resueltas):
            raise InterpretacionInvalida("marca ambigua incoherente")
        if not _timestamp_valido(self.timestamp):
            raise InterpretacionInvalida("timestamp inválido")
        if not isinstance(self.metadata, dict):
            raise InterpretacionInvalida("metadata debe ser objeto")
        object.__setattr__(self, "fuente", FuenteInterpretacion(self.fuente))

    @property
    def ejecutable(self) -> bool:
        return not self.ambigua and not self.datos_faltantes

    def a_dict(self) -> dict[str, Any]:
        return {
            "interpretation_id": self.interpretation_id, "schema_version": self.schema_version,
            "texto_original": self.texto_original, "objetivo": self.objetivo,
            "tipo_intencion": self.tipo_intencion.value, "repo_candidato": self.repo_candidato,
            "worktree_candidato": self.worktree_candidato, "modo_solicitado": self.modo_solicitado,
            "acciones": [a.a_dict() for a in self.acciones], "restricciones": list(self.restricciones),
            "autorizaciones": self.autorizaciones.a_dict(), "condiciones": list(self.condiciones),
            "coste_maximo": self.coste_maximo, "commit": self.commit, "push": self.push,
            "task_id_referencia": self.task_id_referencia, "decision_id_referencia": self.decision_id_referencia,
            "retry_id_referencia": self.retry_id_referencia, "confianza": self.confianza,
            "ambigua": self.ambigua, "ambiguedades": list(self.ambiguedades),
            "datos_faltantes": list(self.datos_faltantes), "referencias_no_resueltas": list(self.referencias_no_resueltas),
            "timestamp": self.timestamp, "metadata": self.metadata, "fuente": self.fuente.value,
        }

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> "OrdenInterpretada":
        esperados = {
            "interpretation_id", "schema_version", "texto_original", "objetivo", "tipo_intencion",
            "repo_candidato", "worktree_candidato", "modo_solicitado", "acciones", "restricciones",
            "autorizaciones", "condiciones", "coste_maximo", "commit", "push", "task_id_referencia",
            "decision_id_referencia", "retry_id_referencia", "confianza", "ambigua", "ambiguedades",
            "datos_faltantes", "referencias_no_resueltas", "timestamp", "metadata", "fuente",
        }
        if not isinstance(datos, dict) or set(datos) != esperados:
            extra = set(datos) - esperados if isinstance(datos, dict) else set()
            falta = esperados - set(datos) if isinstance(datos, dict) else esperados
            raise InterpretacionInvalida(f"schema estricto incumplido; extra={sorted(extra)}, falta={sorted(falta)}")
        copia = dict(datos)
        copia["acciones"] = tuple(AccionOrden.desde_dict(item) for item in copia["acciones"])
        copia["autorizaciones"] = AutorizacionesOrden.desde_dict(copia["autorizaciones"])
        return cls(**copia)


@dataclass(frozen=True)
class ContextoInterpretacion:
    tareas_candidatas: tuple[dict[str, Any], ...] = ()
    decisiones_pendientes: tuple[dict[str, Any], ...] = ()
    retries_preparados: tuple[dict[str, Any], ...] = ()
    repos_conocidos: dict[str, dict[str, Any]] = field(default_factory=dict)

    def para_proveedor(self) -> dict[str, Any]:
        return {
            "tareas": list(self.tareas_candidatas), "decisiones": list(self.decisiones_pendientes),
            "retries": list(self.retries_preparados), "repos": self.repos_conocidos,
        }


class ProveedorInterpretacion(Protocol):
    def interpretar(self, texto: str, contexto: dict[str, Any]) -> dict[str, Any]:
        """Devuelve JSON estricto; no ejecuta ni autoriza por sí mismo."""


class InterpreteOrdenNatural:
    def __init__(
        self,
        proveedor: ProveedorInterpretacion | None = None,
        *,
        preferir_proveedor: bool = False,
    ) -> None:
        self.proveedor = proveedor
        self.preferir_proveedor = preferir_proveedor

    def interpretar(
        self, texto: str, contexto: ContextoInterpretacion | None = None,
        *, canal: CanalOrden | str = CanalOrden.USUARIO_EXPLICITO,
    ) -> OrdenInterpretada:
        if CanalOrden(canal) is not CanalOrden.USUARIO_EXPLICITO:
            raise CanalEntradaInvalido("solo el canal explícito del usuario puede crear órdenes")
        if not isinstance(texto, str) or not texto.strip():
            raise InterpretacionInvalida("orden vacía")
        contexto = contexto or ContextoInterpretacion()
        if self.preferir_proveedor and self.proveedor is not None:
            return self._interpretar_proveedor(texto, contexto)
        local = self._parser_local(texto, contexto)
        if local is not None:
            return local
        if self.proveedor is None:
            return self._otra_ambigua(texto, "orden no cubierta por el parser local")
        return self._interpretar_proveedor(texto, contexto)

    def _interpretar_proveedor(
        self, texto: str, contexto: ContextoInterpretacion
    ) -> OrdenInterpretada:
        try:
            datos = self.proveedor.interpretar(texto, contexto.para_proveedor())
            orden = OrdenInterpretada.desde_dict(datos)
        except Exception as exc:
            raise InterpretacionInvalida(f"salida del proveedor inválida: {exc}") from exc
        if orden.texto_original != texto:
            raise InterpretacionInvalida("el proveedor alteró texto_original")
        if orden.fuente is not FuenteInterpretacion.PROVEEDOR_INYECTADO:
            raise InterpretacionInvalida("fuente del proveedor inválida")
        self._validar_no_amplia_permisos(texto, orden)
        return orden

    def _parser_local(self, texto: str, contexto: ContextoInterpretacion) -> OrdenInterpretada | None:
        normal = _normalizar(texto).strip()
        restricciones = self._restricciones(normal)
        coste = self._coste(normal)
        no_escritura = any(r in restricciones for r in (
            "SOLO_LECTURA", "SOLO_CONSULTA", "NO_CAMBIAR_NADA",
            "NO_MODIFICAR_ARCHIVOS", "NO_ESCRIBIR",
        ))
        no_commit = "NO_COMMIT" in restricciones
        no_push = "NO_PUSH" in restricciones
        commit_cond = (
            ("test" in normal or "prueb" in normal)
            and bool(re.search(r"commit\s+si\s+.*(?:pasan|bien|correct)", normal))
        )
        commit_explicito = ("commit" in normal and not no_commit)
        push_explicito = bool(re.search(r"\b(?:haz|hacer|realiza)\s+push\b", normal)) and not no_push
        alcance = self._alcance(texto, normal)
        repo = self._repo(alcance, contexto)

        intencion: TipoIntencion | None = None
        acciones: list[AccionOrden] = []
        objetivo = texto.strip()
        ambiguedades: list[str] = []
        faltantes: list[str] = []
        referencias: list[str] = []
        task_id = decision_id = retry_id = None
        modo = "read_only"

        if self._es_consulta_estado(normal):
            intencion = TipoIntencion.CONSULTAR_ESTADO
            tipo = TipoAccionNatural.CONSULTAR_DECISIONES if "decision" in normal else TipoAccionNatural.CONSULTAR_ESTADO
            acciones.append(AccionOrden(1, tipo))
        elif re.search(r"\b(?:resultado|ultimo run|como termino)\b", normal):
            intencion = TipoIntencion.CONSULTAR_RESULTADO
            acciones.append(AccionOrden(1, TipoAccionNatural.CONSULTAR_RESULTADO, alcance))
            if alcance:
                task_id, problema = self._resolver_tarea(contexto, alcance)
                if problema: referencias.append(problema)
        elif re.search(r"\b(?:continua|continuar|hazlo|la anterior|vuelve a probarlo)\b", normal):
            intencion = TipoIntencion.CONTINUAR_TAREA
            acciones.append(AccionOrden(1, TipoAccionNatural.CONTINUAR, alcance))
            task_id, problema = self._resolver_tarea(contexto, alcance)
            if problema: referencias.append(problema)
        elif re.search(r"\b(?:cancela|cancelar|para la tarea|para el benchmark)\b", normal):
            intencion = TipoIntencion.CANCELAR_TAREA
            acciones.append(AccionOrden(1, TipoAccionNatural.CANCELAR, alcance))
            task_id, problema = self._resolver_tarea(contexto, alcance)
            if problema: referencias.append(problema)
        elif re.search(r"\b(?:reintenta|prepara.*reintento|vuelve a intentar)\b", normal):
            intencion = TipoIntencion.EJECUTAR_REINTENTO if "ejecut" in normal or "reintenta" in normal else TipoIntencion.PREPARAR_REINTENTO
            acciones.append(AccionOrden(1, TipoAccionNatural.EJECUTAR_REINTENTO if intencion is TipoIntencion.EJECUTAR_REINTENTO else TipoAccionNatural.PREPARAR_REINTENTO))
            candidatos = contexto.retries_preparados
            if len(candidatos) == 1: retry_id = candidatos[0].get("retry_id")
            elif len(candidatos) > 1: referencias.append("múltiples retries candidatos")
            else: faltantes.append("retry_id")
        elif normal.startswith("desactiva") and "regla" in normal:
            intencion = TipoIntencion.DESACTIVAR_REGLA
            acciones.append(AccionOrden(1, TipoAccionNatural.DESACTIVAR_REGLA))
            faltantes.append("rule_id")
        elif "a partir de ahora" in normal or re.search(r"\bregistra.*regla\b", normal):
            intencion = TipoIntencion.REGISTRAR_REGLA
            acciones.append(AccionOrden(1, TipoAccionNatural.REGISTRAR_REGLA, alcance, datos={"candidata": texto.strip()}))
            ambiguedades.append("nueva regla funcional requiere confirmación estructurada")
        elif self._parece_respuesta(normal, contexto):
            intencion = TipoIntencion.RESPONDER_DECISION
            if "haz lo que veas" in normal or "como veas" in normal:
                ambiguedades.append("respuesta funcional insuficiente")
            elif len(contexto.decisiones_pendientes) == 1:
                decision_id = contexto.decisiones_pendientes[0].get("decision_id")
                task_id = contexto.decisiones_pendientes[0].get("task_id")
            elif len(contexto.decisiones_pendientes) > 1:
                referencias.append("múltiples decisiones pendientes")
            else:
                faltantes.append("decision_id")
            acciones.append(AccionOrden(1, TipoAccionNatural.RESPONDER_DECISION, datos={"respuesta": texto.strip()}))
        elif "farmatic" in normal and re.search(r"\b(?:corrige|modifica|escribe|actualiza|cambia)\b", normal):
            intencion = TipoIntencion.CREAR_TAREA
            modo = "workspace_write"
            acciones.append(AccionOrden(1, TipoAccionNatural.ESCRIBIR_FARMATIC, "FARMATIC"))
            faltantes.extend(["repo", "worktree"] if repo is None else [])
        elif re.search(r"\b(?:corrige|modifica|implementa|comprueba|revisa|analiza|ejecuta)\b", normal):
            intencion = TipoIntencion.CREAR_TAREA
            consulta_git = "repo" in normal and ("limpio" in normal or "estado" in normal) and not re.search(r"\b(?:corrige|modifica|implementa)\b", normal)
            modo = "read_only" if no_escritura or consulta_git or re.search(r"\b(?:analiza|revisa|comprueba)\b", normal) else "workspace_write"
            if consulta_git:
                acciones.append(AccionOrden(1, TipoAccionNatural.COMPROBAR_GIT, alcance))
            else:
                acciones.append(AccionOrden(1, TipoAccionNatural.MODIFICAR_ALCANCE, alcance))
                if "test" in normal or "prueb" in normal:
                    acciones.append(AccionOrden(len(acciones) + 1, TipoAccionNatural.EJECUTAR_TESTS, alcance))
                if commit_explicito:
                    condicion = {"tests_correctos": True} if commit_cond else {}
                    acciones.append(AccionOrden(len(acciones) + 1, TipoAccionNatural.COMMIT, alcance, condicion=condicion))
                if push_explicito:
                    acciones.append(AccionOrden(len(acciones) + 1, TipoAccionNatural.PUSH, alcance))
            if repo is None:
                faltantes.extend(["repo", "worktree"])
        else:
            return None

        if intencion is None:
            return None
        autorizaciones = AutorizacionesOrden(
            escritura=modo == "workspace_write" and not no_escritura,
            commit=commit_explicito and not no_commit,
            commit_condicionado_tests=commit_cond and not no_commit,
            push=push_explicito and not no_push,
        )
        condiciones = tuple(["TESTS_CORRECTOS"] if commit_cond else [])
        ambigua = bool(ambiguedades or referencias)
        return OrdenInterpretada(
            interpretation_id=str(uuid4()), schema_version=ORDEN_SCHEMA_VERSION,
            texto_original=texto, objetivo=objetivo, tipo_intencion=intencion,
            repo_candidato=repo.get("repo") if repo else None,
            worktree_candidato=repo.get("worktree") if repo else None,
            modo_solicitado=modo, acciones=tuple(acciones), restricciones=tuple(restricciones),
            autorizaciones=autorizaciones, condiciones=condiciones, coste_maximo=coste,
            commit=autorizaciones.commit, push=autorizaciones.push,
            task_id_referencia=task_id, decision_id_referencia=decision_id,
            retry_id_referencia=retry_id, confianza=.98 if not ambigua else .45,
            ambigua=ambigua, ambiguedades=tuple(ambiguedades), datos_faltantes=tuple(dict.fromkeys(faltantes)),
            referencias_no_resueltas=tuple(referencias), timestamp=_ahora_utc(),
            metadata={"alcance": alcance, "repo_contexto": repo or {}, "canal": CanalOrden.USUARIO_EXPLICITO.value},
            fuente=FuenteInterpretacion.PARSER_LOCAL,
        )

    @staticmethod
    def _restricciones(normal: str) -> list[str]:
        resultado = []
        if "solo lectura" in normal: resultado.append("SOLO_LECTURA")
        if "solo consulta" in normal: resultado.append("SOLO_CONSULTA")
        if re.search(r"\bno modifiques? (?:los )?archivos\b", normal): resultado.append("NO_MODIFICAR_ARCHIVOS")
        if re.search(r"\bno (?:cambies|modifiques) nada\b|\bno hagas cambios\b", normal): resultado.append("NO_CAMBIAR_NADA")
        if re.search(r"\bno escribas\b", normal): resultado.append("NO_ESCRIBIR")
        if re.search(r"\b(?:no hagas?|sin(?: hacer)?) commit\b", normal): resultado.append("NO_COMMIT")
        if re.search(r"\b(?:no hagas?|sin(?: hacer)?) push\b", normal): resultado.append("NO_PUSH")
        if re.search(r"\b(?:no uses|sin) codex\b", normal): resultado.append("NO_CODEX")
        if re.search(r"\b(?:no uses|sin) api\b|\bno llames? a servicios externos\b", normal): resultado.append("NO_API_EXTERNA")
        if re.search(r"\bno gastes\b", normal): resultado.append("NO_GASTAR")
        if "no toques el gold" in normal: resultado.append("NO_TOCAR_GOLD")
        if "no modifiques programa" in normal: resultado.append("NO_MODIFICAR_PROGRAMA")
        solo = re.search(r"\bsolo\s+(alliance|hefame|farmatic)\b", normal)
        if solo: resultado.append(f"SOLO_{solo.group(1).upper()}")
        return resultado

    @staticmethod
    def _coste(normal: str) -> float | None:
        centimos = re.search(r"(?:maximo|máximo|hasta)\s+(\d+(?:[.,]\d+)?)\s*cent", normal)
        if centimos: return float(centimos.group(1).replace(",", ".")) / 100
        euros = re.search(r"(?:maximo|máximo|hasta)\s+(\d+(?:[.,]\d+)?)\s*(?:eur|euro|€)", normal)
        return float(euros.group(1).replace(",", ".")) if euros else None

    @staticmethod
    def _alcance(texto: str, normal: str) -> str | None:
        for nombre in ("alliance", "hefame", "farmatic"):
            if nombre in normal: return nombre.upper()
        return None

    @staticmethod
    def _repo(alcance: str | None, contexto: ContextoInterpretacion) -> dict[str, Any] | None:
        if alcance is None: return None
        return contexto.repos_conocidos.get(alcance) or contexto.repos_conocidos.get(alcance.casefold())

    @staticmethod
    def _es_consulta_estado(normal: str) -> bool:
        return bool("?" in normal and re.search(r"\b(?:estado|que esta haciendo|tareas|esperando decision|locks|retries)\b", normal)) or normal in {"estado", "consulta el estado"}

    @staticmethod
    def _parece_respuesta(normal: str, contexto: ContextoInterpretacion) -> bool:
        return bool(contexto.decisiones_pendientes) and bool(re.match(r"^(?:si|sí|no|conserv|acept|rechaz|haz lo que veas|como veas)", normal))

    @staticmethod
    def _resolver_tarea(contexto: ContextoInterpretacion, alcance: str | None) -> tuple[str | None, str | None]:
        candidatas = list(contexto.tareas_candidatas)
        if alcance:
            candidatas = [t for t in candidatas if alcance.casefold() in json.dumps(t, ensure_ascii=False).casefold()]
        if len(candidatas) == 1: return candidatas[0].get("task_id"), None
        if len(candidatas) > 1: return None, "múltiples tareas candidatas"
        return None, "ninguna tarea candidata inequívoca"

    @staticmethod
    def _validar_no_amplia_permisos(texto: str, orden: OrdenInterpretada) -> None:
        normal = _normalizar(texto)
        no_escritura = (
            "solo lectura" in normal
            or "solo consulta" in normal
            or re.search(r"no (?:cambies|modifiques) nada|no hagas cambios", normal)
            or re.search(r"no modifiques? (?:los )?archivos", normal)
            or re.search(r"no escribas", normal)
        )
        if no_escritura and (orden.modo_solicitado != "read_only" or orden.autorizaciones.escritura):
            raise InterpretacionInvalida("el proveedor intentó ampliar read_only")
        if re.search(r"(?:no (?:hagas? )?|sin(?: hacer)? )push", normal) and orden.push:
            raise InterpretacionInvalida("el proveedor intentó autorizar push prohibido")
        if re.search(r"(?:no (?:hagas? )?|sin(?: hacer)? )commit", normal) and orden.commit:
            raise InterpretacionInvalida("el proveedor intentó autorizar commit prohibido")
        if any(a.tipo is TipoAccionNatural.OTRA and not orden.ambigua for a in orden.acciones):
            raise InterpretacionInvalida("acción desconocida presentada como segura")

    @staticmethod
    def _otra_ambigua(texto: str, causa: str) -> OrdenInterpretada:
        return OrdenInterpretada(
            str(uuid4()), ORDEN_SCHEMA_VERSION, texto, texto, TipoIntencion.OTRA,
            None, None, "read_only", (AccionOrden(1, TipoAccionNatural.OTRA),), (),
            AutorizacionesOrden(False, False, False, False), (), None, False, False,
            None, None, None, 0.0, True, (causa,), (), (causa,), _ahora_utc(),
            {"canal": CanalOrden.USUARIO_EXPLICITO.value}, FuenteInterpretacion.PARSER_LOCAL,
        )


class RegistroOrdenesNaturales:
    """Bitácora global append-only de órdenes explícitas, sin ingerir fuentes externas."""

    def __init__(self, directorio: str | Path) -> None:
        self.directorio = Path(directorio)
        self.path = self.directorio / "eventos.json"

    def registrar(self, tipo: str, datos: dict[str, Any]) -> None:
        eventos = self.listar()
        eventos.append({"tipo": tipo, "timestamp": _ahora_utc(), "datos": self._sanear(datos)})
        self._guardar(eventos)

    def listar(self) -> list[dict[str, Any]]:
        if not self.path.is_file(): return []
        try:
            datos = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ErrorInterpretacion(f"bitácora natural inválida: {exc}") from exc
        if not isinstance(datos, list): raise ErrorInterpretacion("bitácora natural debe ser lista")
        return datos

    @classmethod
    def _sanear(cls, valor: Any) -> Any:
        if isinstance(valor, dict):
            return {k: ("[REDACTED]" if any(s in k.casefold() for s in ("secret", "token", "password", "api_key")) else cls._sanear(v)) for k, v in valor.items()}
        if isinstance(valor, list): return [cls._sanear(v) for v in valor]
        return valor

    def _guardar(self, eventos: list[dict[str, Any]]) -> None:
        self.directorio.mkdir(parents=True, exist_ok=True)
        descriptor, nombre = tempfile.mkstemp(prefix=".eventos.", suffix=".tmp", dir=self.directorio)
        temporal = Path(nombre)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archivo:
                json.dump(eventos, archivo, ensure_ascii=False, indent=2, allow_nan=False)
                archivo.write("\n"); archivo.flush(); os.fsync(archivo.fileno())
            os.replace(temporal, self.path)
        except BaseException:
            temporal.unlink(missing_ok=True); raise
