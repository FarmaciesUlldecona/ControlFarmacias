"""Contexto mínimo, incremental y auditable para ejecuciones Codex V0.2.11."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
from typing import Any, Iterable


NIVELES_CODEX = frozenset({"LOCAL_ONLY", "CODEX_LIGHT", "CODEX_STANDARD", "CODEX_HEAVY"})


@dataclass(frozen=True)
class LimiteContextoCodex:
    max_archivos: int
    max_fragmentos: int
    max_caracteres: int
    max_llamadas: int


LIMITES_CONTEXTO: dict[str, LimiteContextoCodex] = {
    "LOCAL_ONLY": LimiteContextoCodex(0, 0, 0, 0),
    "CODEX_LIGHT": LimiteContextoCodex(3, 6, 12_000, 2),
    "CODEX_STANDARD": LimiteContextoCodex(8, 16, 40_000, 2),
    "CODEX_HEAVY": LimiteContextoCodex(16, 32, 80_000, 1),
}


@dataclass(frozen=True)
class FragmentoContextoCodex:
    ruta: str
    motivo: str
    linea_inicio: int | None = None
    linea_fin: int | None = None

    def __post_init__(self) -> None:
        if not self.ruta.strip() or not self.motivo.strip():
            raise ValueError("ruta y motivo del fragmento son obligatorios")
        if (self.linea_inicio is None) != (self.linea_fin is None):
            raise ValueError("el rango debe incluir inicio y fin")
        if self.linea_inicio is not None and (
            self.linea_inicio < 1 or self.linea_fin < self.linea_inicio
        ):
            raise ValueError("rango de líneas inválido")


@dataclass(frozen=True)
class AmpliacionContextoCodex:
    motivo: str
    fragmentos: tuple[FragmentoContextoCodex, ...]


@dataclass(frozen=True)
class PlanContextoCodex:
    task_id: str
    nivel_recurso: str
    objetivo: str
    restricciones: tuple[str, ...]
    reglas_absolutas: tuple[str, ...]
    decisiones_aplicables: tuple[str, ...]
    tests_relevantes: tuple[str, ...]
    errores_concretos: tuple[str, ...]
    contexto_retry: dict[str, Any]
    recursos: dict[str, Any]
    contexto_base: tuple[FragmentoContextoCodex, ...]
    ampliaciones_contexto: tuple[AmpliacionContextoCodex, ...] = ()
    archivos_omitidos: tuple[str, ...] = ()
    retry: bool = False
    session_id: str | None = None
    sesion_reutilizada: bool = False
    soporte_reanudacion_cli: bool = False

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.objetivo.strip():
            raise ValueError("task_id y objetivo son obligatorios")
        if self.nivel_recurso not in NIVELES_CODEX:
            raise ValueError(f"nivel de recurso no soportado: {self.nivel_recurso}")
        if self.sesion_reutilizada and not self.soporte_reanudacion_cli:
            raise ValueError("no se puede fingir reutilización de sesión CLI")
        if not isinstance(self.contexto_retry, dict) or not isinstance(self.recursos, dict):
            raise ValueError("contexto_retry y recursos deben ser objetos")

    @property
    def fragmentos(self) -> tuple[FragmentoContextoCodex, ...]:
        return self.contexto_base + tuple(
            fragmento
            for ampliacion in self.ampliaciones_contexto
            for fragmento in ampliacion.fragmentos
        )

    @property
    def archivos(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.ruta for item in self.fragmentos))

    def a_dict(self) -> dict[str, Any]:
        datos = asdict(self)
        datos["metricas"] = self.metricas()
        return datos

    def metricas(self) -> dict[str, Any]:
        serializado = json.dumps(
            {
                "objetivo": self.objetivo,
                "restricciones": self.restricciones,
                "reglas_absolutas": self.reglas_absolutas,
                "decisiones_aplicables": self.decisiones_aplicables,
                "tests_relevantes": self.tests_relevantes,
                "errores_concretos": self.errores_concretos,
                "contexto_retry": self.contexto_retry,
                "recursos": self.recursos,
                "fragmentos": [asdict(item) for item in self.fragmentos],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return {
            "nivel_recurso": self.nivel_recurso,
            "contexto_archivos": len(self.archivos),
            "contexto_fragmentos": len(self.fragmentos),
            "contexto_caracteres": len(serializado),
            "archivos_omitidos": list(self.archivos_omitidos),
            "contexto_ampliado": bool(self.ampliaciones_contexto),
            "motivo_ampliacion": (
                self.ampliaciones_contexto[-1].motivo
                if self.ampliaciones_contexto else None
            ),
            "session_id": self.session_id,
            "sesion_reutilizada": self.sesion_reutilizada,
            "soporte_reanudacion_cli": self.soporte_reanudacion_cli,
            "retry": self.retry,
        }

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> "PlanContextoCodex":
        copia = dict(datos)
        copia.pop("metricas", None)
        copia["contexto_base"] = tuple(
            FragmentoContextoCodex(**item) for item in copia.get("contexto_base", ())
        )
        copia["ampliaciones_contexto"] = tuple(
            AmpliacionContextoCodex(
                item["motivo"],
                tuple(FragmentoContextoCodex(**fragmento) for fragmento in item["fragmentos"]),
            )
            for item in copia.get("ampliaciones_contexto", ())
        )
        for campo in (
            "restricciones", "reglas_absolutas", "decisiones_aplicables",
            "tests_relevantes", "errores_concretos", "archivos_omitidos",
        ):
            copia[campo] = tuple(copia.get(campo, ()))
        copia["contexto_retry"] = dict(copia.get("contexto_retry", {}))
        copia["recursos"] = dict(copia.get("recursos", {}))
        return cls(**copia)


def crear_plan_contexto(
    *,
    task_id: str,
    nivel_recurso: str,
    objetivo: str,
    restricciones: Iterable[str] = (),
    reglas_absolutas: Iterable[str] = (),
    decisiones_aplicables: Iterable[str] = (),
    archivos_candidatos: Iterable[str | dict[str, Any]] = (),
    tests_relevantes: Iterable[str] = (),
    errores_concretos: Iterable[str] = (),
    contexto_retry: dict[str, Any] | None = None,
    recursos: dict[str, Any] | None = None,
    retry: bool = False,
    session_id: str | None = None,
) -> PlanContextoCodex:
    limite = LIMITES_CONTEXTO[nivel_recurso]
    candidatos = tuple(_fragmento(item) for item in archivos_candidatos)
    seleccionados: list[FragmentoContextoCodex] = []
    omitidos: list[str] = []
    archivos: set[str] = set()
    for candidato in candidatos:
        nuevo_archivo = candidato.ruta not in archivos
        if len(seleccionados) >= limite.max_fragmentos or (
            nuevo_archivo and len(archivos) >= limite.max_archivos
        ):
            omitidos.append(candidato.ruta)
            continue
        seleccionados.append(candidato)
        archivos.add(candidato.ruta)
    plan = PlanContextoCodex(
        task_id=task_id,
        nivel_recurso=nivel_recurso,
        objetivo=objetivo,
        restricciones=tuple(dict.fromkeys(str(item) for item in restricciones if str(item))),
        reglas_absolutas=tuple(dict.fromkeys(str(item) for item in reglas_absolutas if str(item))),
        decisiones_aplicables=tuple(dict.fromkeys(str(item) for item in decisiones_aplicables if str(item))),
        tests_relevantes=tuple(dict.fromkeys(str(item) for item in tests_relevantes if str(item))),
        errores_concretos=tuple(str(item) for item in errores_concretos if str(item)),
        contexto_retry=dict(contexto_retry or {}),
        recursos=dict(recursos or {}),
        contexto_base=tuple(seleccionados),
        archivos_omitidos=tuple(dict.fromkeys(omitidos)),
        retry=retry,
        session_id=session_id,
    )
    if limite.max_caracteres and plan.metricas()["contexto_caracteres"] > limite.max_caracteres:
        raise ValueError("el contexto estructurado supera el límite de caracteres")
    return plan


def ampliar_contexto(
    plan: PlanContextoCodex,
    *,
    task_id: str,
    motivo: str,
    fragmentos: Iterable[str | dict[str, Any]] = (),
    errores_concretos: Iterable[str] = (),
) -> PlanContextoCodex:
    if task_id != plan.task_id:
        raise ValueError("no se puede mezclar contexto entre tareas")
    if not motivo.strip():
        raise ValueError("motivo de ampliación obligatorio")
    limite = LIMITES_CONTEXTO[plan.nivel_recurso]
    existentes = {(item.ruta, item.linea_inicio, item.linea_fin) for item in plan.fragmentos}
    archivos = set(plan.archivos)
    nuevos: list[FragmentoContextoCodex] = []
    omitidos = list(plan.archivos_omitidos)
    for item in (_fragmento(valor) for valor in fragmentos):
        clave = (item.ruta, item.linea_inicio, item.linea_fin)
        if clave in existentes:
            continue
        nuevo_archivo = item.ruta not in archivos
        if len(plan.fragmentos) + len(nuevos) >= limite.max_fragmentos or (
            nuevo_archivo and len(archivos) >= limite.max_archivos
        ):
            omitidos.append(item.ruta)
            continue
        nuevos.append(item)
        existentes.add(clave)
        archivos.add(item.ruta)
    ampliacion = AmpliacionContextoCodex(motivo, tuple(nuevos))
    actualizado = PlanContextoCodex(
        **{
            **{campo: getattr(plan, campo) for campo in plan.__dataclass_fields__},
            "errores_concretos": tuple(
                dict.fromkeys((*plan.errores_concretos, *(str(x) for x in errores_concretos if str(x))))
            ),
            "ampliaciones_contexto": (*plan.ampliaciones_contexto, ampliacion),
            "archivos_omitidos": tuple(dict.fromkeys(omitidos)),
        }
    )
    if limite.max_caracteres and actualizado.metricas()["contexto_caracteres"] > limite.max_caracteres:
        raise ValueError("la ampliación supera el límite de caracteres")
    return actualizado


def _fragmento(valor: str | dict[str, Any]) -> FragmentoContextoCodex:
    if isinstance(valor, str):
        return FragmentoContextoCodex(_ruta_relativa(valor), "CANDIDATO_DECLARADO")
    if not isinstance(valor, dict):
        raise ValueError("fragmento de contexto inválido")
    return FragmentoContextoCodex(
        _ruta_relativa(str(valor["ruta"])),
        str(valor.get("motivo") or "CANDIDATO_DECLARADO"),
        valor.get("linea_inicio"),
        valor.get("linea_fin"),
    )


def _ruta_relativa(valor: str) -> str:
    ruta = Path(valor)
    return ruta.as_posix()
