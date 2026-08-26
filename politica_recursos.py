"""Política determinista de recursos y nivel de pruebas para Orquestador V0.2.11."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
import math
from typing import Any


class ErrorPoliticaRecursos(ValueError):
    """La solicitud de recursos no cumple el contrato esperado."""


class NivelRecurso(str, Enum):
    LOCAL_ONLY = "LOCAL_ONLY"
    CODEX_LIGHT = "CODEX_LIGHT"
    CODEX_STANDARD = "CODEX_STANDARD"
    CODEX_HEAVY = "CODEX_HEAVY"


class NivelTests(str, Enum):
    TEST_FOCAL = "TEST_FOCAL"
    TEST_MODULO = "TEST_MODULO"
    SUITE_COMPLETA = "SUITE_COMPLETA"


class TipoTrabajo(str, Enum):
    DETERMINISTA = "DETERMINISTA"
    ADMINISTRATIVO = "ADMINISTRATIVO"
    DESARROLLO = "DESARROLLO"
    DEBUG = "DEBUG"
    REFACTOR = "REFACTOR"
    AUDITORIA = "AUDITORIA"


ACCIONES_LOCAL_ONLY = frozenset(
    {
        "CONSULTAR_ESTADO",
        "CONSULTAR_RESULTADO",
        "CONSULTAR_PRESUPUESTO",
        "CONSULTAR_CONSUMO",
        "GIT_STATUS",
        "GIT_BRANCH",
        "GIT_HEAD",
        "CALCULAR_SHA256",
        "COMPROBAR_HASH",
        "COMPROBAR_ARCHIVO",
        "LISTAR_ARCHIVOS",
        "VALIDAR_JSON",
        "PY_COMPILE",
        "EJECUTAR_TESTS",
        "ELIMINAR_TEMPORAL_AUTORIZADO",
        "CERRAR_RUN_ADMINISTRATIVO",
    }
)


@dataclass(frozen=True)
class SolicitudRecursos:
    tipo_trabajo: TipoTrabajo
    accion: str
    archivos_afectados: int = 0
    requiere_escritura_codigo: bool = False
    requiere_razonamiento: bool = False
    multiples_modulos: bool = False
    riesgo_transversal: bool = False
    cierre_hito: bool = False
    commit_importante: bool = False
    infraestructura_comun: bool = False
    incertidumbre_alta: bool = False
    problema_dificil: bool = False
    escalado_significativo: bool = False
    nivel_tests_explicito: NivelTests | None = None
    nivel_tests_anterior: NivelTests | None = None
    nivel_recurso_anterior: NivelRecurso | None = None
    retry: bool = False
    estrategia_retry: str | None = None
    repite_trabajo: bool = False
    potencial_nuevo_coste: bool = False
    coste_estimado: int | float | Decimal | None = None
    presupuesto_disponible: int | float | Decimal | None = None
    motivo_escalado: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tipo_trabajo", TipoTrabajo(self.tipo_trabajo))

        if self.nivel_tests_explicito is not None:
            object.__setattr__(
                self,
                "nivel_tests_explicito",
                NivelTests(self.nivel_tests_explicito),
            )
        if self.nivel_tests_anterior is not None:
            object.__setattr__(self, "nivel_tests_anterior", NivelTests(self.nivel_tests_anterior))
        if self.nivel_recurso_anterior is not None:
            object.__setattr__(
                self, "nivel_recurso_anterior", NivelRecurso(self.nivel_recurso_anterior)
            )

        if not isinstance(self.accion, str) or not self.accion.strip():
            raise ErrorPoliticaRecursos("accion debe ser texto no vacío")

        object.__setattr__(self, "accion", self.accion.strip().upper())

        if (
            not isinstance(self.archivos_afectados, int)
            or isinstance(self.archivos_afectados, bool)
            or self.archivos_afectados < 0
        ):
            raise ErrorPoliticaRecursos(
                "archivos_afectados debe ser un entero no negativo"
            )

        campos_booleanos = (
            "requiere_escritura_codigo",
            "requiere_razonamiento",
            "multiples_modulos",
            "riesgo_transversal",
            "cierre_hito",
            "commit_importante",
            "infraestructura_comun",
            "incertidumbre_alta",
            "problema_dificil",
            "escalado_significativo",
            "retry",
            "repite_trabajo",
            "potencial_nuevo_coste",
        )
        for campo in campos_booleanos:
            if not isinstance(getattr(self, campo), bool):
                raise ErrorPoliticaRecursos(f"{campo} debe ser booleano")

        for campo in ("coste_estimado", "presupuesto_disponible"):
            valor = getattr(self, campo)
            if valor is not None:
                tipo_valido = (
                    not isinstance(valor, bool)
                    and isinstance(valor, (int, float, Decimal))
                )
                finito = (
                    valor.is_finite()
                    if isinstance(valor, Decimal)
                    else math.isfinite(valor)
                    if tipo_valido
                    else False
                )
                if not tipo_valido or not finito or valor < 0:
                    raise ErrorPoliticaRecursos(
                        f"{campo} debe ser no negativo o null"
                    )
        if self.estrategia_retry is not None and not (
            isinstance(self.estrategia_retry, str) and self.estrategia_retry.strip()
        ):
            raise ErrorPoliticaRecursos("estrategia_retry debe ser texto o null")
        if self.motivo_escalado is not None and not (
            isinstance(self.motivo_escalado, str) and self.motivo_escalado.strip()
        ):
            raise ErrorPoliticaRecursos("motivo_escalado debe ser texto o null")


@dataclass(frozen=True)
class EvaluacionRecursos:
    nivel_recurso: NivelRecurso
    nivel_tests: NivelTests | None
    requiere_codex: bool
    requiere_ok_pio_coste: bool
    motivos: tuple[str, ...]
    tipo_trabajo: TipoTrabajo | None = None
    archivos_afectados: int = 0
    multiples_modulos: bool = False
    riesgo_transversal: bool = False
    nivel_recurso_anterior: NivelRecurso | None = None
    retry: bool = False
    estrategia_retry: str | None = None
    repite_trabajo: bool = False
    potencial_nuevo_coste: bool = False
    coste_estimado: int | float | Decimal | None = None
    presupuesto_disponible: int | float | Decimal | None = None
    motivo_escalado: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "nivel_recurso",
            NivelRecurso(self.nivel_recurso),
        )
        if self.nivel_tests is not None:
            object.__setattr__(
                self,
                "nivel_tests",
                NivelTests(self.nivel_tests),
            )
        if self.tipo_trabajo is not None:
            object.__setattr__(self, "tipo_trabajo", TipoTrabajo(self.tipo_trabajo))
        if self.nivel_recurso_anterior is not None:
            object.__setattr__(
                self, "nivel_recurso_anterior", NivelRecurso(self.nivel_recurso_anterior)
            )

        if not isinstance(self.requiere_codex, bool):
            raise ErrorPoliticaRecursos("requiere_codex debe ser booleano")

        if not isinstance(self.requiere_ok_pio_coste, bool):
            raise ErrorPoliticaRecursos(
                "requiere_ok_pio_coste debe ser booleano"
            )

        object.__setattr__(self, "motivos", tuple(self.motivos))

        if not self.motivos or not all(
            isinstance(item, str) and item.strip() for item in self.motivos
        ):
            raise ErrorPoliticaRecursos(
                "motivos debe contener al menos una explicación"
            )

        esperado_codex = self.nivel_recurso is not NivelRecurso.LOCAL_ONLY
        if self.requiere_codex != esperado_codex:
            raise ErrorPoliticaRecursos(
                "requiere_codex es incoherente con nivel_recurso"
            )

    def a_dict(self) -> dict[str, Any]:
        motivo_barrera = self._motivo_barrera_coste()
        return {
            "nivel_recurso": self.nivel_recurso.value,
            "nivel_tests": self.nivel_tests.value if self.nivel_tests else None,
            "requiere_codex": self.requiere_codex,
            "requiere_ok_pio_coste": self.requiere_ok_pio_coste,
            "tipo_trabajo": self.tipo_trabajo.value if self.tipo_trabajo else None,
            "archivos_afectados": self.archivos_afectados,
            "multiples_modulos": self.multiples_modulos,
            "riesgo_transversal": self.riesgo_transversal,
            "nivel_recurso_anterior": (
                self.nivel_recurso_anterior.value if self.nivel_recurso_anterior else None
            ),
            "nivel_anterior": (
                self.nivel_recurso_anterior.value if self.nivel_recurso_anterior else None
            ),
            "nivel_nuevo": self.nivel_recurso.value,
            "retry": self.retry,
            "estrategia_retry": self.estrategia_retry,
            "repite_trabajo": self.repite_trabajo,
            "potencial_nuevo_coste": self.potencial_nuevo_coste,
            "coste_estimado": (
                str(self.coste_estimado)
                if isinstance(self.coste_estimado, Decimal)
                else self.coste_estimado
            ),
            "presupuesto_disponible": (
                str(self.presupuesto_disponible)
                if isinstance(self.presupuesto_disponible, Decimal)
                else self.presupuesto_disponible
            ),
            "presupuesto_autorizado": (
                str(self.presupuesto_disponible)
                if isinstance(self.presupuesto_disponible, Decimal)
                else self.presupuesto_disponible
            ),
            "motivo_clasificacion": list(self.motivos),
            "motivo_escalado": self.motivo_escalado,
            "motivo_barrera_coste": motivo_barrera,
        }

    def _motivo_barrera_coste(self) -> str | None:
        if not self.requiere_ok_pio_coste:
            return None
        if self.nivel_recurso is NivelRecurso.CODEX_HEAVY:
            return "CODEX_HEAVY requiere autorización de coste previa"
        if (
            self.coste_estimado is not None
            and self.presupuesto_disponible is not None
            and self.coste_estimado > self.presupuesto_disponible
        ):
            return "el coste estimado supera el presupuesto autorizado"
        if self.retry and self.repite_trabajo and self.potencial_nuevo_coste:
            return "el retry repite trabajo y puede generar coste adicional"
        return "existe potencial de coste adicional no cubierto"


class PoliticaRecursos:
    """Clasificador local, determinista y conservador."""

    @classmethod
    def evaluar(cls, solicitud: SolicitudRecursos) -> EvaluacionRecursos:
        nivel_recurso, motivos_recurso = cls._clasificar_recurso(solicitud)
        nivel_tests, motivos_tests = cls._clasificar_tests(
            solicitud,
            nivel_recurso,
        )

        motivo_escalado = solicitud.motivo_escalado
        if (
            motivo_escalado is None
            and solicitud.nivel_recurso_anterior
            in {NivelRecurso.CODEX_LIGHT, NivelRecurso.CODEX_STANDARD}
            and nivel_recurso is NivelRecurso.CODEX_HEAVY
        ):
            motivo_escalado = (
                f"escalado de {solicitud.nivel_recurso_anterior.value} a CODEX_HEAVY"
            )

        return EvaluacionRecursos(
            nivel_recurso=nivel_recurso,
            nivel_tests=nivel_tests,
            requiere_codex=nivel_recurso is not NivelRecurso.LOCAL_ONLY,
            requiere_ok_pio_coste=cls._requiere_ok_coste(solicitud, nivel_recurso),
            motivos=tuple((*motivos_recurso, *motivos_tests)),
            tipo_trabajo=solicitud.tipo_trabajo,
            archivos_afectados=solicitud.archivos_afectados,
            multiples_modulos=solicitud.multiples_modulos,
            riesgo_transversal=solicitud.riesgo_transversal,
            nivel_recurso_anterior=solicitud.nivel_recurso_anterior,
            retry=solicitud.retry,
            estrategia_retry=solicitud.estrategia_retry,
            repite_trabajo=solicitud.repite_trabajo,
            potencial_nuevo_coste=solicitud.potencial_nuevo_coste,
            coste_estimado=solicitud.coste_estimado,
            presupuesto_disponible=solicitud.presupuesto_disponible,
            motivo_escalado=motivo_escalado,
        )

    @staticmethod
    def _requiere_ok_coste(
        solicitud: SolicitudRecursos, nivel_recurso: NivelRecurso
    ) -> bool:
        if nivel_recurso is NivelRecurso.CODEX_HEAVY:
            return True
        if (
            solicitud.coste_estimado is not None
            and solicitud.presupuesto_disponible is not None
            and solicitud.coste_estimado > solicitud.presupuesto_disponible
        ):
            return True
        if solicitud.retry and solicitud.repite_trabajo and solicitud.potencial_nuevo_coste:
            return True
        return False

    @staticmethod
    def _clasificar_recurso(
        solicitud: SolicitudRecursos,
    ) -> tuple[NivelRecurso, tuple[str, ...]]:
        accion = solicitud.accion

        if (
            accion in ACCIONES_LOCAL_ONLY
            and not solicitud.requiere_escritura_codigo
            and not solicitud.requiere_razonamiento
        ):
            return (
                NivelRecurso.LOCAL_ONLY,
                ("acción incluida explícitamente en la lista LOCAL_ONLY",),
            )

        if solicitud.retry and solicitud.nivel_recurso_anterior is not None:
            return (
                solicitud.nivel_recurso_anterior,
                ("el retry conserva conservadoramente el nivel de recurso anterior",),
            )

        if solicitud.riesgo_transversal:
            return (
                NivelRecurso.CODEX_HEAVY,
                ("la operación declara riesgo transversal",),
            )

        if (
            solicitud.incertidumbre_alta
            or solicitud.problema_dificil
            or solicitud.escalado_significativo
        ):
            return (
                NivelRecurso.CODEX_HEAVY,
                ("complejidad, incertidumbre o escalado significativo declarado",),
            )

        if solicitud.tipo_trabajo is TipoTrabajo.REFACTOR:
            if solicitud.multiples_modulos or solicitud.archivos_afectados >= 5:
                return (
                    NivelRecurso.CODEX_HEAVY,
                    ("refactor de alcance amplio",),
                )
            return (
                NivelRecurso.CODEX_STANDARD,
                ("refactor acotado que requiere razonamiento sobre código",),
            )

        if solicitud.tipo_trabajo is TipoTrabajo.AUDITORIA:
            if solicitud.multiples_modulos or solicitud.archivos_afectados >= 5:
                return (
                    NivelRecurso.CODEX_HEAVY,
                    ("auditoría profunda o transversal",),
                )
            return (
                NivelRecurso.CODEX_STANDARD,
                ("auditoría técnica que requiere contexto de código",),
            )

        if solicitud.tipo_trabajo in {
            TipoTrabajo.DESARROLLO,
            TipoTrabajo.DEBUG,
        }:
            if solicitud.multiples_modulos or solicitud.archivos_afectados >= 3:
                return (
                    NivelRecurso.CODEX_STANDARD,
                    ("trabajo de código sobre varios archivos o módulos",),
                )
            if solicitud.archivos_afectados == 1:
                return (
                    NivelRecurso.CODEX_LIGHT,
                    ("cambio de código pequeño y acotado",),
                )
            if solicitud.archivos_afectados == 0:
                return (
                    NivelRecurso.CODEX_STANDARD,
                    ("alcance de archivos desconocido; se mantiene nivel conservador",),
                )
            return (
                NivelRecurso.CODEX_STANDARD,
                ("trabajo de código con alcance superior a un archivo",),
            )

        if solicitud.tipo_trabajo in {
            TipoTrabajo.DETERMINISTA,
            TipoTrabajo.ADMINISTRATIVO,
        }:
            if (
                not solicitud.requiere_escritura_codigo
                and not solicitud.requiere_razonamiento
            ):
                return (
                    NivelRecurso.CODEX_LIGHT,
                    (
                        "la operación no está en la lista LOCAL_ONLY; "
                        "se escala conservadoramente",
                    ),
                )

        return (
            NivelRecurso.CODEX_STANDARD,
            (
                "no hay evidencia suficiente para clasificar la operación "
                "como local o ligera",
            ),
        )

    @staticmethod
    def _clasificar_tests(
        solicitud: SolicitudRecursos,
        nivel_recurso: NivelRecurso,
    ) -> tuple[NivelTests | None, tuple[str, ...]]:
        if solicitud.nivel_tests_explicito is not None:
            return (
                solicitud.nivel_tests_explicito,
                ("nivel de tests solicitado explícitamente",),
            )

        if (
            solicitud.cierre_hito
            or solicitud.commit_importante
            or solicitud.riesgo_transversal
            or solicitud.infraestructura_comun
        ):
            return (
                NivelTests.SUITE_COMPLETA,
                (
                    "cierre de hito, commit importante o riesgo transversal "
                    "o infraestructura común requiere suite completa",
                ),
            )

        if nivel_recurso is NivelRecurso.CODEX_HEAVY:
            return (
                NivelTests.SUITE_COMPLETA,
                ("trabajo CODEX_HEAVY requiere validación completa",),
            )

        if solicitud.accion == "EJECUTAR_TESTS":
            if solicitud.multiples_modulos:
                return (
                    NivelTests.TEST_MODULO,
                    ("ejecución de tests sobre alcance de módulo",),
                )
            return (
                NivelTests.TEST_FOCAL,
                ("ejecución de tests sin riesgo transversal declarado",),
            )

        if nivel_recurso is NivelRecurso.LOCAL_ONLY:
            return (
                None,
                ("la operación local no requiere validación adicional",),
            )

        if (
            nivel_recurso is NivelRecurso.CODEX_STANDARD
            or solicitud.multiples_modulos
            or solicitud.archivos_afectados >= 2
        ):
            return (
                NivelTests.TEST_MODULO,
                ("el cambio afecta varios archivos o módulos",),
            )

        return (
            NivelTests.TEST_FOCAL,
            ("el cambio es acotado y comienza con tests focales",),
        )


def evaluar_recursos(**datos: Any) -> EvaluacionRecursos:
    """Atajo tipado para construir y evaluar una solicitud."""

    return PoliticaRecursos.evaluar(SolicitudRecursos(**datos))
