"""Interfaz operativa V0.2.12: contexto determinista y bootstrap seguro."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Callable
import unicodedata
from uuid import uuid4

from ejecucion_v02 import EjecutorCiclo, EjecutorCicloReal
from ejecutor_local import EjecutorLocal
from fachada_v02 import OrquestadorV02, ResultadoPublicoV02
from lenguaje_natural import (
    AccionOrden,
    AutorizacionesOrden,
    FuenteInterpretacion,
    ORDEN_SCHEMA_VERSION,
    OrdenInterpretada,
    TipoAccionNatural,
    TipoIntencion,
)
from repositorios import ORQUESTADOR_ACTIVO, PROGRAMA, repo_operativo_para_cwd


ORQUESTADOR_REPO = ORQUESTADOR_ACTIVO
PROGRAMA_REPO = PROGRAMA
PYTHON_CONTROLFARMACIAS = Path(r"C:\ControlFarmacias\Programa\.venv\Scripts\python.exe")


def _normalizar(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto.casefold())
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def _git(repo: Path, *args: str) -> str:
    resultado = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True,
        check=False, timeout=30, shell=False,
    )
    if resultado.returncode != 0:
        raise ValueError(f"Git no disponible para {repo}: {resultado.stderr.strip()}")
    return resultado.stdout.strip()


@dataclass(frozen=True)
class ConfiguracionOperativa:
    orquestador_repo: Path = ORQUESTADOR_REPO
    programa_repo: Path = PROGRAMA_REPO
    python: Path = PYTHON_CONTROLFARMACIAS
    cwd: Path | None = None

    def __post_init__(self) -> None:
        for campo in ("orquestador_repo", "programa_repo", "python"):
            object.__setattr__(self, campo, Path(getattr(self, campo)).resolve())
        if self.cwd is not None:
            object.__setattr__(self, "cwd", Path(self.cwd).resolve())

    def repos_conocidos(self) -> dict[str, dict[str, Any]]:
        orquestador = self._repo(
            "ORQUESTADOR", self.orquestador_repo,
            ("*.py", "tests/**", "schemas/**", "prompts/**", "*.md", "*.ps1", "*.cmd"),
        )
        programa = self._repo(
            "PROGRAMA", self.programa_repo,
            ("src/**", "tests/**", "pruebas/**"),
        )
        repos = {"ORQUESTADOR": orquestador, "PROGRAMA": programa}
        actual = self._actual(orquestador, programa)
        if actual is not None:
            repos["ACTUAL"] = actual
        return repos

    @staticmethod
    def _repo(nombre: str, ruta: Path, permitidas: tuple[str, ...]) -> dict[str, Any]:
        if not ruta.is_dir():
            raise ValueError(f"workspace {nombre} no disponible: {ruta}")
        return {
            "nombre": nombre,
            "repo": str(ruta),
            "worktree": str(ruta),
            "rama": _git(ruta, "branch", "--show-current"),
            "commit_inicial": _git(ruta, "rev-parse", "HEAD"),
            "rutas_permitidas": list(permitidas),
            "rutas_protegidas": [
                ".env", ".env.*", "**/.env", "**/.env.*",
                ".git/**", ".codex/**", ".agents/**",
            ],
        }

    def _actual(
        self, orquestador: dict[str, Any], programa: dict[str, Any]
    ) -> dict[str, Any] | None:
        nombre = repo_operativo_para_cwd(
            self.cwd or Path.cwd(),
            {"ORQUESTADOR": orquestador["repo"], "PROGRAMA": programa["repo"]},
        )
        return {"ORQUESTADOR": orquestador, "PROGRAMA": programa}.get(nombre)


class ProveedorContextoOperativo:
    """Proveedor local determinista; no usa IA, red ni comandos libres."""

    _ENTIDADES_PROGRAMA = {
        "alliance": "ALLIANCE", "cencora": "CENCORA", "cofares": "COFARES",
        "hefame": "HEFAME", "fedefarma": "FEDEFARMA",
        "normalizador": "NORMALIZADOR", "normalizadores": "NORMALIZADOR",
        "factura": "FACTURAS", "facturas": "FACTURAS",
        "albaran": "ALBARANES", "albaranes": "ALBARANES",
        "proveedor": "PROVEEDORES", "proveedores": "PROVEEDORES",
        "conciliacion": "CONCILIACION", "banco": "BANCO",
        "cashflow": "CASHFLOW", "pedido": "PEDIDOS", "pedidos": "PEDIDOS",
        "laboratorio": "LABORATORIOS", "laboratorios": "LABORATORIOS",
        "supabase": "SUPABASE", "farmatic": "FARMATIC",
    }
    _TERMINOS_ORQUESTADOR = (
        "orquestador", "cf", "cli", "routing", "local_only", "codex_light",
        "codex_standard", "codex_heavy", "supervisor", "launcher",
    )

    def interpretar(self, texto: str, contexto: dict[str, Any]) -> dict[str, Any]:
        normal = _normalizar(texto).strip()
        repos = dict(contexto.get("repos") or {})
        if self._parece_shell(normal):
            return self._ambigua(texto, "la entrada parece un comando de shell, no una orden natural").a_dict()
        if self._es_estado_global(normal):
            return self._consulta(texto, TipoIntencion.CONSULTAR_ESTADO, TipoAccionNatural.CONSULTAR_ESTADO).a_dict()
        if self._es_presupuesto(normal):
            return self._consulta(texto, TipoIntencion.CONSULTAR_PRESUPUESTO, TipoAccionNatural.CONSULTAR_PRESUPUESTO).a_dict()
        if self._es_consumo(normal):
            return self._consulta(texto, TipoIntencion.CONSULTAR_CONSUMO, TipoAccionNatural.CONSULTAR_CONSUMO).a_dict()
        if self._solicita_commit_push(normal):
            return self._ambigua(texto, "commit/push requiere una tarea y autorización explícita verificable").a_dict()

        proyecto, conflicto = self._proyecto(normal, repos)
        if conflicto:
            return self._ambigua(texto, conflicto).a_dict()
        if self._es_git(normal):
            proyecto = proyecto or repos.get("ORQUESTADOR")
            return self._git_orden(texto, proyecto).a_dict() if proyecto else self._ambigua(texto, "no se pudo resolver el repositorio").a_dict()
        if "farmatic" in normal and self._es_escritura(normal):
            proyecto = repos.get("PROGRAMA")
            return self._tarea(texto, normal, proyecto, farmatic=True).a_dict()
        if self._es_escritura(normal):
            if proyecto is None:
                return self._ambigua(texto, "no se pudo resolver con seguridad el proyecto de destino").a_dict()
            if self._es_solo_lectura(normal):
                return self._ambigua(texto, "la orden combina escritura y una restricción de solo lectura").a_dict()
            return self._tarea(texto, normal, proyecto).a_dict()
        if self._es_tests(normal):
            if proyecto is None:
                return self._ambigua(texto, "'este módulo' no tiene un contexto de proyecto resoluble").a_dict()
            return self._tests(texto, normal, proyecto).a_dict()
        if self._es_auditoria(normal) or self._es_consulta_proyecto(normal):
            if proyecto is None:
                return self._ambigua(texto, "no se pudo resolver con seguridad el proyecto de destino").a_dict()
            return self._tarea(texto, normal, proyecto, solo_lectura=True).a_dict()
        return self._ambigua(texto, "orden no cubierta por las reglas operativas locales").a_dict()

    @staticmethod
    def _consulta(texto: str, intencion: TipoIntencion, accion: TipoAccionNatural) -> OrdenInterpretada:
        return ProveedorContextoOperativo._crear(
            texto, intencion, (AccionOrden(1, accion),), None, "read_only",
            metadata={"nivel_recurso_esperado": "LOCAL_ONLY"},
        )

    @staticmethod
    def _git_orden(texto: str, repo: dict[str, Any]) -> OrdenInterpretada:
        return ProveedorContextoOperativo._crear(
            texto, TipoIntencion.CREAR_TAREA,
            (AccionOrden(1, TipoAccionNatural.COMPROBAR_GIT, repo["nombre"]),),
            repo, "read_only", metadata={"archivos_afectados": 0},
        )

    def _tests(self, texto: str, normal: str, repo: dict[str, Any]) -> OrdenInterpretada:
        rutas = self._tests_focales(Path(repo["repo"]), normal, repo["nombre"])
        if not rutas:
            return self._ambigua(texto, "no se encontraron tests focales inequívocos")
        return self._crear(
            texto, TipoIntencion.CREAR_TAREA,
            (AccionOrden(1, TipoAccionNatural.EJECUTAR_TESTS, repo["nombre"],
                         datos={"rutas": list(rutas)}),),
            repo, "read_only",
            metadata={"archivos_afectados": 0, "nivel_tests_explicito": "TEST_FOCAL"},
        )

    def _tarea(
        self, texto: str, normal: str, repo: dict[str, Any], *,
        farmatic: bool = False, solo_lectura: bool = False,
    ) -> OrdenInterpretada:
        acciones = [AccionOrden(
            1,
            TipoAccionNatural.ESCRIBIR_FARMATIC if farmatic
            else TipoAccionNatural.ANALIZAR_ALCANCE if solo_lectura
            else TipoAccionNatural.MODIFICAR_ALCANCE,
            "FARMATIC" if farmatic else repo["nombre"],
        )]
        if "test" in normal or "valid" in normal or "prueb" in normal:
            acciones.append(AccionOrden(len(acciones) + 1, TipoAccionNatural.EJECUTAR_TESTS, repo["nombre"]))
        pequeno = bool(re.search(r"\b(?:pequen|acotad|unico archivo|un archivo)\w*\b", normal))
        multi = bool(re.search(r"\b(?:multiarchivo|varios archivos|varios modulos|multiples modulos)\b", normal))
        heavy = self._es_auditoria(normal) and (multi or "transversal" in normal or "profunda" in normal)
        archivos = 8 if heavy else 3 if multi else 1 if pequeno else 0
        metadata = {
            "archivos_afectados": archivos,
            "multiples_modulos": multi or heavy,
            "riesgo_transversal": heavy,
            "tipo_trabajo": "AUDITORIA" if self._es_auditoria(normal) else "DESARROLLO",
            "entidades": list(self._entidades(normal)),
            "requiere_razonamiento": solo_lectura,
        }
        restricciones = self._restricciones(normal)
        if solo_lectura: restricciones.append("SOLO_LECTURA")
        return self._crear(
            texto, TipoIntencion.CREAR_TAREA, tuple(acciones), repo,
            "read_only" if solo_lectura else "workspace_write",
            metadata=metadata, restricciones=tuple(dict.fromkeys(restricciones)),
            escritura=not solo_lectura,
        )

    @staticmethod
    def _crear(
        texto: str,
        intencion: TipoIntencion,
        acciones: tuple[AccionOrden, ...],
        repo: dict[str, Any] | None,
        modo: str,
        *,
        metadata: dict[str, Any],
        restricciones: tuple[str, ...] = (),
        escritura: bool = False,
    ) -> OrdenInterpretada:
        meta = {**metadata, "canal": "USUARIO_EXPLICITO"}
        if repo is not None:
            meta.update({"proyecto": repo["nombre"], "repo_contexto": repo})
        return OrdenInterpretada(
            interpretation_id=str(uuid4()), schema_version=ORDEN_SCHEMA_VERSION,
            texto_original=texto, objetivo=texto.strip(), tipo_intencion=intencion,
            repo_candidato=repo["repo"] if repo else None,
            worktree_candidato=repo["worktree"] if repo else None,
            modo_solicitado=modo, acciones=acciones, restricciones=restricciones,
            autorizaciones=AutorizacionesOrden(escritura, False, False, False),
            condiciones=("validación local correcta",) if escritura else (),
            coste_maximo=None, commit=False, push=False,
            task_id_referencia=None, decision_id_referencia=None,
            retry_id_referencia=None, confianza=1.0, ambigua=False,
            ambiguedades=(), datos_faltantes=(), referencias_no_resueltas=(),
            timestamp=datetime.now(timezone.utc).isoformat(), metadata=meta,
            fuente=FuenteInterpretacion.PROVEEDOR_INYECTADO,
        )

    @staticmethod
    def _ambigua(texto: str, motivo: str) -> OrdenInterpretada:
        return OrdenInterpretada(
            str(uuid4()), ORDEN_SCHEMA_VERSION, texto, texto, TipoIntencion.OTRA,
            None, None, "read_only", (AccionOrden(1, TipoAccionNatural.OTRA),), (),
            AutorizacionesOrden(False, False, False, False), (), None, False, False,
            None, None, None, 0.0, True, (motivo,), (), (motivo,),
            datetime.now(timezone.utc).isoformat(),
            {"canal": "USUARIO_EXPLICITO"}, FuenteInterpretacion.PROVEEDOR_INYECTADO,
        )

    @staticmethod
    def _tests_focales(repo: Path, normal: str, nombre: str) -> tuple[str, ...]:
        tests = repo / "tests"
        if not tests.is_dir(): return ()
        claves = [item for item in ("cofares", "hefame", "fedefarma", "normalizador") if item in normal]
        candidatos: list[Path] = []
        for clave in claves:
            candidatos.extend(sorted(tests.rglob(f"test_*{clave}*.py")))
        if not candidatos and nombre == "ORQUESTADOR":
            preferido = tests / "test_cli_operativo_v0212.py"
            respaldo = tests / "test_lenguaje_natural_v0210.py"
            candidatos = [item for item in (preferido, respaldo) if item.is_file()]
        return tuple(item.relative_to(repo).as_posix() for item in candidatos[:4])

    def _proyecto(
        self, normal: str, repos: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None]:
        if re.search(r"\bv0[._ -]?1[._ -]?3\b|controlfarmacias_orquestador_v0_1_3", normal):
            return None, "V0.1.3 es histórico y no es un destino operativo nuevo"
        programa_explicito = bool(re.search(
            r"\b(?:repo(?:sitorio)?\s+(?:de(?:l)?\s+)?programa|controlfarmacias\s+programa|en\s+(?:el\s+)?programa|programa)\b",
            normal,
        ))
        orquestador_explicito = bool(re.search(
            r"\b(?:repo(?:sitorio)?\s+(?:de(?:l)?\s+)?orquestador|en\s+(?:el\s+)?orquestador|orquestador)\b",
            normal,
        ))
        if programa_explicito and orquestador_explicito:
            return None, "la orden nombra Programa y Orquestador como destinos incompatibles"
        if programa_explicito: return repos.get("PROGRAMA"), None
        if orquestador_explicito: return repos.get("ORQUESTADOR"), None

        entidades = self._entidades(normal)
        dominio_orquestador = self._menciona_dominio_orquestador(normal)
        if entidades and dominio_orquestador:
            return None, "la orden mezcla dominios de Programa y Orquestador sin destino explícito"
        if entidades: return repos.get("PROGRAMA"), None
        if dominio_orquestador: return repos.get("ORQUESTADOR"), None
        if re.search(r"\b(?:este repo|este repositorio|este modulo|aqui|rama actual)\b", normal):
            actual = repos.get("ACTUAL")
            return (actual, None) if actual else (None, "el directorio actual no está dentro de un repositorio conocido")
        return None, None

    @staticmethod
    def _es_estado_global(normal: str) -> bool:
        return normal in {"estado", "consulta el estado"} or "que esta haciendo el orquestador" in normal

    @staticmethod
    def _es_presupuesto(normal: str) -> bool:
        return "presupuesto" in normal or ("cuanto" in normal and "queda" in normal)

    @staticmethod
    def _es_consumo(normal: str) -> bool:
        return bool(re.search(r"\b(?:cuanto|que)\s+(?:hemos\s+)?gastad\w*\b", normal))

    @staticmethod
    def _es_git(normal: str) -> bool:
        return "git" in normal or ("rama actual" in normal and "comprueba" in normal)

    @staticmethod
    def _es_tests(normal: str) -> bool:
        return bool(
            re.search(r"\b(?:ejecuta|lanza|corre|pasa)\w*\b.*\b(?:test|tests|pruebas)\b", normal)
            or re.search(r"\b(?:valida|prueba)\w*\b", normal)
            or re.search(r"\bcomprueba\b.*\b(?:funciona|regresiones)\b", normal)
        )

    @staticmethod
    def _es_escritura(normal: str) -> bool:
        return bool(re.search(
            r"\b(?:corrige|arregla|modifica|cambia|implementa|anade|crea|adapta|"
            r"mejora|completa|termina|prepara|desarrolla|actualiza|escribe)\b",
            normal,
        ))

    @staticmethod
    def _es_auditoria(normal: str) -> bool:
        return bool(re.search(r"\b(?:audita|auditoria|examina)\b", normal))

    @staticmethod
    def _es_consulta_proyecto(normal: str) -> bool:
        return bool(
            re.search(r"\b(?:comprueba|revisa|mira|consulta|analiza|dime|verifica|averigua|examina)\b", normal)
            or re.search(r"\b(?:estado|situacion|como va|como esta|esta preparado|esta listo|que falta)\b", normal)
        )

    @classmethod
    def _entidades(cls, normal: str) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            entidad for termino, entidad in cls._ENTIDADES_PROGRAMA.items()
            if re.search(rf"\b{re.escape(termino)}\b", normal)
        ))

    @classmethod
    def _menciona_dominio_orquestador(cls, normal: str) -> bool:
        if any(re.search(rf"\b{re.escape(item)}\b", normal) for item in cls._TERMINOS_ORQUESTADOR):
            return True
        return bool(re.search(
            r"\b(?:comando\s+cf|parser\s+del\s+orquestador|presupuesto\s+codex)\b",
            normal,
        ))

    @staticmethod
    def _es_solo_lectura(normal: str) -> bool:
        return bool(
            re.search(r"\b(?:solo lectura|solo consulta|no escribas|no hagas cambios)\b", normal)
            or re.search(r"\bno modifiques? (?:los )?archivos\b", normal)
            or re.search(r"\bno (?:cambies|modifiques) nada\b", normal)
        )

    @staticmethod
    def _restricciones(normal: str) -> list[str]:
        patrones = (
            ("NO_MODIFICAR_ARCHIVOS", r"\bno modifiques? (?:los )?archivos\b"),
            ("NO_CAMBIAR_NADA", r"\bno (?:cambies|modifiques) nada\b|\bno hagas cambios\b"),
            ("SOLO_CONSULTA", r"\bsolo consulta\b"),
            ("NO_ESCRIBIR", r"\bno escribas\b"),
            ("NO_COMMIT", r"\b(?:no hagas?|sin) commit\b|\bsin hacer commit\b"),
            ("NO_PUSH", r"\b(?:no hagas?|sin) push\b|\bsin hacer push\b"),
            ("NO_CODEX", r"\b(?:no uses|sin) codex\b"),
            ("NO_API_EXTERNA", r"\b(?:no uses|sin) api\b|\bno llames? a servicios externos\b"),
            ("NO_GASTAR", r"\bno gastes\b"),
        )
        resultado = [nombre for nombre, patron in patrones if re.search(patron, normal)]
        if "solo lectura" in normal: resultado.append("SOLO_LECTURA")
        return list(dict.fromkeys(resultado))

    @staticmethod
    def _solicita_commit_push(normal: str) -> bool:
        commit = "commit" in normal and not re.search(r"(?:no (?:hagas? )?|sin(?: hacer)? )commit", normal)
        push = "push" in normal and not re.search(r"(?:no (?:hagas? )?|sin(?: hacer)? )push", normal)
        return bool(commit or push)

    @staticmethod
    def _parece_shell(normal: str) -> bool:
        return bool(re.search(r"(?:;|&&|\|\||\bpowershell\b|\bcmd /c\b|\binvoke-expression\b|\brm -|\bdel /)", normal))


def crear_orquestador_operativo(
    configuracion: ConfiguracionOperativa,
    *,
    ejecutor_factory: Callable[[Any], EjecutorCiclo] | None = None,
    ejecutor_local: EjecutorLocal | None = None,
) -> OrquestadorV02:
    motor_config = json.loads(
        (configuracion.orquestador_repo / "config.json").read_text(encoding="utf-8")
    )
    factory = ejecutor_factory or (
        lambda _: EjecutorCicloReal(configuracion.orquestador_repo, motor_config)
    )
    local = ejecutor_local or EjecutorLocal(
        python_executable=configuracion.python,
        pytest_basetemp=Path(tempfile.gettempdir()) / f"cf_pytest_{os.getpid()}",
    )
    return OrquestadorV02(
        configuracion.orquestador_repo,
        ejecutor_factory=factory,
        proveedor_interpretacion=ProveedorContextoOperativo(),
        preferir_proveedor_interpretacion=True,
        repos_conocidos=configuracion.repos_conocidos(),
        ejecutor_local=local,
    )


def resultado_json(
    orden: str, resultado: ResultadoPublicoV02, presupuesto: ResultadoPublicoV02 | None
) -> str:
    return json.dumps(
        {
            "orden": orden,
            "resultado": asdict(resultado),
            "presupuesto": asdict(presupuesto) if presupuesto else None,
        },
        ensure_ascii=False, indent=2, default=str,
    )


def resultado_humano(
    orden: str, resultado: ResultadoPublicoV02, presupuesto: ResultadoPublicoV02 | None
) -> str:
    recursos = dict(resultado.datos.get("recursos") or {})
    interpretacion = dict(resultado.datos.get("interpretacion") or {})
    proyecto = dict(interpretacion.get("metadata") or {}).get("proyecto")
    nivel = recursos.get("nivel_recurso")
    if nivel is None and resultado.codigo.startswith("LOCAL_"):
        nivel = "LOCAL_ONLY"
    llamadas = recursos.get("llamadas_codex_ejecutadas")
    codex = "No utilizado" if nivel == "LOCAL_ONLY" or llamadas == 0 else "Utilizado" if llamadas else "Según ejecución"
    lineas = [
        f"ORDEN: {orden}",
        f"RESULTADO: {resultado.mensaje}",
        f"CÓDIGO: {resultado.codigo}",
        f"PROYECTO: {proyecto or 'No aplica'}",
        f"MODO: {nivel or 'No clasificado'}",
        f"CODEX: {codex}",
    ]
    if presupuesto and presupuesto.ok:
        datos = presupuesto.datos.get("presupuesto") or {}
        lineas.extend([
            f"PRESUPUESTO: {datos.get('presupuesto_total', 'desconocido')} EUR/semana",
            f"DISPONIBLE: {datos.get('presupuesto_disponible', 'desconocido')} EUR",
        ])
        if datos.get("aviso_proximidad") is True:
            lineas.append("AVISO: presupuesto cerca del límite.")
    if resultado.requiere_intervencion:
        lineas.append("DETENIDO: necesita autorización o aclaración de Pio.")
        if resultado.decision_id:
            lineas.append(f"DECISIÓN: {resultado.decision_id}")
    if resultado.errores:
        lineas.append("ERRORES: " + "; ".join(resultado.errores))
    return "\n".join(lineas)
