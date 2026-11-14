"""Orquestador nocturno de la automatizacion Alliance (Hito AUTO-A; diseno en
``pruebas/auditoria_auto_alliance/DISENO.md``, decisiones D1-D7 de Pio, 2026-11-12).

Uso (tarea programada de las 22:15 como Usuari, con ``ejecutar_automatizacion_alliance.bat``):
  python -m src.facturas.runtime_supabase.noche_automatica <SOMBRA|REAL> <directorio_informes>

Una noche:
  guard (fila de cf_noches_automaticas; una por fecha local) -> puertas -> snapshot pre por fila
  -> normalizacion (hasta N documentos) -> conciliacion (hasta M facturas) -> snapshot post
  -> postcheck 2AX por fila -> informe en fichero + actualizacion de la fila.

- ``SOMBRA``: flags apagados; solo lectura mas la fila de resumen (unica escritura, decision de Pio). Informa de
  lo que haria: documentos en cola y simulacion del n.o 1 de conciliacion.
- ``REAL``: ruta AUTOMATICA (claims ``AUTOMATICO``, que exigen los flags en la BD) con el compositor automatico
  (autoridad solo Alliance certificada, D1). Cada fase solo corre con su flag encendido.

Paradas (cortan la noche): puerta fallida, excepcion, huerfano (NORMALIZANDO o claim vivo), documento o factura
reclamados distintos del previsto, resultado real distinto del simulado, fila ajena cambiada. Para revisar (fin de
la conciliacion de esa noche, sin reclamar): n.o 1 que simula un resultado distinto de CONCILIADA (D2), que no es
Alliance o con una revision R18 pendiente. Defectos (R3) y no soportados (R2): se anotan. Limites (D5): 5 + 5 hasta
3 noches REAL buenas seguidas, despues 20 + 20; 60 minutos. Nunca se reintenta ni se arregla nada.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, ContextManager

from .conciliacion import PROVEEDOR_CANONICO_ALLIANCE, canonicalizar_proveedor
from .lectura_readonly import (
    SQL_COLA_NORMALIZACION,
    SQL_SELECTOR_CONCILIACION,
    LectorReadOnly,
    simular_conciliacion,
)
from .modelos import ConfiguracionRuntime

ROOT = Path(__file__).resolve().parents[3]
PROJECT_REF = "vklaiuytvegkelgyspxc"
WORKER_BASE = "cf-auto-alliance"
TABLA_RESUMEN = "cf_noches_automaticas"
MODOS = ("SOMBRA", "REAL")
LIMITES_INICIALES = (5, 5)
LIMITES_PLENOS = (20, 20)
NOCHES_BUENAS_PARA_PLENOS = 3
MINUTOS_MAXIMOS = 60
TAREAS_PREVIAS = ("ControlFarmacias - Importar facturas", "Sincronización ControlFarmacias")
RESULTADO_EN_EJECUCION = 267009
# Valores certificados (R11, 2AZ; tolerancia documental 0,05).
TOLERANCIAS_CERTIFICADAS = {
    "tolerancia_conciliacion": Decimal("0.0500"),
    "conciliacion_tolerancia_suelo": Decimal("0.0500"),
    "conciliacion_tolerancia_por_albaran": Decimal("0.0100"),
    "conciliacion_tolerancia_tope": Decimal("0.5000"),
}
# Funciones y tablas que deben existir (migraciones 18, 21, 25, 30, 31 y 32).
FUNCIONES_REQUERIDAS = ("cf_reclamar_documento_normalizacion", "cf_reclamar_factura_conciliacion_nucleo",
                        "cf_persistir_conciliacion", "cf_recuperar_claim_huerfano_normalizacion",
                        "cf_detalles_por_linea")
TABLAS_REQUERIDAS = ("conciliacion_albaranes_reservados", "cf_modulos_farmacias", TABLA_RESUMEN)
# Modulo de Trabajadores (migracion 31): lo escribe la web y es ajeno a facturas. Mejora aprobada por Pio
# (2026-11-13): en los postchecks se informa aparte y no hace fallar el veredicto. Tambien lo usan las series 2BJ/2BP.
TABLAS_TRABAJADORES = frozenset({
    "cf_modulos_farmacias", "trabajadoras", "convenio_anual", "eventos_calendario", "guardias_farmacia", "festivos",
    "trabajadores_historial"})
# Fuera del snapshot 2AX: la propia tabla de resumen y Trabajadores (este se lee aparte, ``snapshot_trabajadores``).
TABLAS_FUERA_DEL_SNAPSHOT = frozenset({TABLA_RESUMEN}) | TABLAS_TRABAJADORES

CODIGO_OK, CODIGO_PARADA, CODIGO_YA_EJECUTADA = 0, 3, 4


class Parada(Exception):
    """Corta la noche entera."""


# --------------------------------------------------------------------------- entorno inyectable


@dataclass(slots=True)
class Entorno:
    abrir_lectura: Callable[[], ContextManager[LectorReadOnly]]
    cliente: Any
    tareas: Callable[[], dict]
    puerta_git: Callable[[], tuple[str | None, list[str]]]
    construir_worker: Callable[[ConfiguracionRuntime], Any]
    directorio_informes: Path
    reloj: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc)
    fecha_local: Callable[[dt.datetime], dt.date] = lambda t: t.astimezone().date()


@dataclass(slots=True)
class Noche:
    fecha: dt.date
    modo: str
    inicio: dt.datetime
    commit: str | None = None
    limites: dict = field(default_factory=dict)
    resultado: str = "EN_CURSO"
    motivo: str | None = None
    documentos: list = field(default_factory=list)
    conciliaciones: list = field(default_factory=list)
    para_revisar: list = field(default_factory=list)
    sombra: dict = field(default_factory=dict)
    puertas: list = field(default_factory=list)
    postcheck: dict = field(default_factory=dict)
    cola_restante: dict = field(default_factory=dict)
    fin_por_limite: bool = False

    def contadores(self) -> dict[str, int]:
        return {
            "documentos_reclamados": len(self.documentos),
            "alliance_persistidos": sum(d["clase"] == "ALLIANCE" for d in self.documentos),
            "facturas_creadas": sum(d.get("facturas", 0) for d in self.documentos),
            "no_soportados": sum(d["clase"] == "NO_SOPORTADO" for d in self.documentos),
            "defectos": sum(d["clase"] == "DEFECTO" for d in self.documentos),
            "conciliadas": len(self.conciliaciones),
        }


# --------------------------------------------------------------------------- lecturas


def _configuracion(lector: LectorReadOnly) -> dict:
    return lector.json("select to_jsonb(c)::text from public.cf_configuracion c where id")


def _operacion(lector: LectorReadOnly) -> dict:
    return {
        "locks_documentos": lector.valor(
            "select count(*) from public.documentos_facturas where bloqueado_hasta > now() "
            "or bloqueado_por is not null"),
        "claims_conciliacion": lector.valor(
            "select count(*) from public.facturas where conciliacion_bloqueado_hasta > now() "
            "or conciliacion_bloqueado_por is not null"),
        "normalizando": lector.valor(
            "select count(*) from public.documentos_facturas where estado_lectura = 'NORMALIZANDO'"),
    }


def _marcas(lector: LectorReadOnly) -> dict:
    funciones = {f: lector.valor("select exists(select 1 from pg_proc where pronamespace = 'public'::regnamespace "
                                 "and proname = %s)", (f,)) for f in FUNCIONES_REQUERIDAS}
    tablas = {t: lector.valor("select to_regclass(%s) is not null", (f"public.{t}",)) for t in TABLAS_REQUERIDAS}
    return {**funciones, **tablas}


def _noches_previas(lector: LectorReadOnly, fecha: dt.date) -> list[dict]:
    return [json.loads(f[0]) for f in lector.filas(
        f"select jsonb_build_object('fecha', fecha::text, 'modo', modo, 'resultado', resultado)::text "
        f"from public.{TABLA_RESUMEN} where fecha < %s order by fecha desc", (fecha,))]


def limites_por_historial(previas: list[dict]) -> tuple[int, int]:
    """D5: 5 + 5 hasta 3 noches REAL buenas seguidas (las mas recientes); una PARADA reinicia la cuenta."""
    buenas = 0
    for noche in previas:  # mas reciente primero
        if noche["modo"] != "REAL":
            continue
        if noche["resultado"] in ("NOCHE_OK", "FIN_LIMITE"):
            buenas += 1
            continue
        break
    return LIMITES_PLENOS if buenas >= NOCHES_BUENAS_PARA_PLENOS else LIMITES_INICIALES


def _cola_normalizacion(lector: LectorReadOnly, modo_claim: str) -> list[list]:
    return [list(r) for r in lector.filas(SQL_COLA_NORMALIZACION, {"modo": modo_claim})]


def _cola_conciliacion(lector: LectorReadOnly, modo_claim: str) -> list[str]:
    return [r[0] for r in lector.filas(SQL_SELECTOR_CONCILIACION, {"modo": modo_claim})]


def _documento(lector: LectorReadOnly, documento_id: str) -> dict:
    return lector.json(
        "select jsonb_build_object('estado_lectura', d.estado_lectura, 'bloqueado_por', d.bloqueado_por, "
        "'bloqueado_hasta', d.bloqueado_hasta::text, 'intentos', d.intentos_fallo_normalizacion, "
        "'huella', md5(to_jsonb(d)::text), "
        "'facturas', (select count(*) from public.facturas f where f.documento_id = d.id))::text "
        "from public.documentos_facturas d where d.id = %s", (documento_id,))


def _ultima_ejecucion(lector: LectorReadOnly, documento_id: str) -> dict:
    filas = lector.filas(
        "select (to_jsonb(e) - 'resultado_json')::text from public.normalizacion_ejecuciones e "
        "where e.documento_id = %s order by e.created_at desc, e.id desc limit 1", (documento_id,))
    if not filas:
        return {}
    fila = json.loads(filas[0][0])
    return {k: (v[:300] if isinstance(v, str) else v) for k, v in fila.items()
            if k in ("estado", "error_codigo", "error_mensaje", "motivo", "clase_fallo", "disparador", "intento")}


def _factura(lector: LectorReadOnly, factura_id: str) -> dict:
    return lector.json(
        "select jsonb_build_object('estado', f.estado_conciliacion_cf, 'numero_factura', f.numero_factura, "
        "'bloqueado_por', f.conciliacion_bloqueado_por, "
        "'idempotency_key', (select c.idempotency_key from public.conciliaciones c "
        "  where c.factura_id = f.id and c.es_actual))::text "
        "from public.facturas f where f.id = %s", (factura_id,))


def es_alliance(simulacion: dict) -> bool:
    """Grupo Alliance/SAFA/Cencora con el mismo criterio que la conciliacion (R19)."""
    return any(canonicalizar_proveedor(simulacion.get(k)) == PROVEEDOR_CANONICO_ALLIANCE
               for k in ("proveedor_nombre", "proveedor_literal"))


def _sin_ceros(valor: Any) -> str | None:
    if not isinstance(valor, str) or not valor.strip():
        return None
    return valor.strip().lstrip("0") or "0"


def _numeros_de_cambio(campo: str, valor: str | None) -> set[str]:
    if valor is None:
        return set()
    try:
        dato = json.loads(valor)
    except ValueError:
        dato = valor
    if isinstance(dato, dict):
        numero = _sin_ceros(dato.get("numero_albaran"))
        return {numero} if numero else set()
    if campo == "numero_albaran":
        numero = _sin_ceros(dato if isinstance(dato, str) else None)
        return {numero} if numero else set()
    return set()


def revisiones_r18_que_afectan(lector: LectorReadOnly, factura_id: str) -> list[dict]:
    """R18 pendientes (REVISION sin aprobacion aplicada posterior) cuyo albaran casa con una linea del PDF de la
    factura (numero actual, anterior o nuevo, sin ceros a la izquierda) o esta reservado por ella."""
    pendientes = lector.filas(
        "select c.id::text, c.farmacia, c.id_contador, c.campo, c.valor_anterior::text, c.valor_nuevo::text, "
        "a.numero_albaran from public.albaranes_cambios c left join public.albaranes a "
        "on a.farmacia = c.farmacia and a.id_contador = c.id_contador where c.accion = 'REVISION' "
        "and not exists (select 1 from public.albaranes_aprobaciones_aplicadas x where x.farmacia = c.farmacia "
        "  and x.id_contador = c.id_contador and x.aplicada_at >= c.detectado_at)")
    if not pendientes:
        return []
    lineas = {_sin_ceros(r[0]) for r in lector.filas(
        "select numero_albaran from public.facturas_albaranes_extraidos where factura_id = %s", (factura_id,))}
    lineas.discard(None)
    reservas = {(r[0], int(r[1])) for r in lector.filas(
        "select albaran_farmacia, albaran_id_contador from public.conciliacion_albaranes_reservados "
        "where factura_id = %s", (factura_id,))}
    afectan = []
    for cambio_id, farmacia, id_contador, campo, anterior, nuevo, actual in pendientes:
        numeros = {_sin_ceros(actual)} | _numeros_de_cambio(campo, anterior) | _numeros_de_cambio(campo, nuevo)
        numeros.discard(None)
        if numeros & lineas or (farmacia, int(id_contador)) in reservas:
            afectan.append({"cambio_id": cambio_id, "farmacia": farmacia, "id_contador": id_contador,
                            "campo": campo})
    return afectan


# --------------------------------------------------------------------------- snapshot y postcheck 2AX por fila


def snapshot_por_fila(lector: LectorReadOnly) -> dict[str, dict[str, list]]:
    """Huella de cada fila de cada tabla base de public (salvo las excluidas) con su documento y factura duenos."""
    tablas = [r[0] for r in lector.filas(
        "select table_name::text from information_schema.tables where table_schema = 'public' "
        "and table_type = 'BASE TABLE' order by 1")]
    out: dict[str, dict[str, list]] = {}
    for tabla in tablas:
        if tabla in TABLAS_FUERA_DEL_SNAPSHOT:
            continue
        columnas = {r[0] for r in lector.filas(
            "select column_name::text from information_schema.columns where table_schema = 'public' "
            "and table_name = %s", (tabla,))}
        doc = ("t.id::text" if tabla == "documentos_facturas"
               else "t.documento_id::text" if "documento_id" in columnas else "null")
        if tabla == "facturas":
            fac = "t.id::text"
        elif "factura_id" in columnas:
            fac = "t.factura_id::text"
        elif "conciliacion_id" in columnas:
            fac = "(select c.factura_id::text from public.conciliaciones c where c.id = t.conciliacion_id)"
        else:
            fac = "null"
        filas = lector.filas(
            f"select coalesce(to_jsonb(t)->>'id', md5(to_jsonb(t)::text)), md5(to_jsonb(t)::text), {doc}, {fac} "
            f'from public."{tabla}" t')
        out[tabla] = {k: [h, d, f] for k, h, d, f in filas}
    return out


def snapshot_trabajadores(entorno: Entorno) -> dict:
    """Huella por fila de las tablas de Trabajadores, en su propia sesion READ_ONLY.

    Solo informativo: si no se puede leer (por ejemplo, sin privilegio de lectura) se anota el error y la noche sigue;
    nunca comparte la transaccion del snapshot 2AX.
    """
    try:
        with entorno.abrir_lectura() as lector:
            existentes = {r[0] for r in lector.filas(
                "select table_name::text from information_schema.tables where table_schema = 'public' "
                "and table_type = 'BASE TABLE'")}
            return {"tablas": {tabla: dict(lector.filas(
                f'select coalesce(to_jsonb(t)->>\'id\', md5(to_jsonb(t)::text)), md5(to_jsonb(t)::text) '
                f'from public."{tabla}" t')) for tabla in sorted(TABLAS_TRABAJADORES & existentes)}}
    except Exception as exc:  # noqa: BLE001 - informativo: no afecta a la noche
        return {"error": f"{type(exc).__name__}"}


def cambios_trabajadores(pre: dict | None, post: dict | None) -> dict:
    """Filas de Trabajadores cambiadas, nuevas o desaparecidas por tabla. Se informa aparte; no es veredicto."""
    informe: dict = {"afecta_al_veredicto": False}
    if not pre or not post or "error" in pre or "error" in post:
        informe["no_comparable"] = {"pre": (pre or {}).get("error", "AUSENTE" if not pre else None),
                                    "post": (post or {}).get("error", "AUSENTE" if not post else None)}
        return informe
    cambios = {}
    for tabla in sorted(set(pre["tablas"]) | set(post["tablas"])):
        a, b = pre["tablas"].get(tabla, {}), post["tablas"].get(tabla, {})
        distintas = sum(1 for k in set(a) | set(b) if a.get(k) != b.get(k))
        if distintas:
            cambios[tabla] = distintas
    informe["filas_cambiadas_por_tabla"] = cambios
    return informe


def postcheck_por_fila(pre: dict, post: dict, documentos: set[str], facturas: set[str]) -> dict:
    """2AX: solo cambian (o aparecen, o desaparecen) filas de los documentos y facturas procesados esa noche."""
    facturas_de_documentos = {f for filas in (pre.get("facturas", {}), post.get("facturas", {}))
                              for _, d, f in filas.values() if d in documentos}
    duenas = facturas | facturas_de_documentos
    cambios, ajenas = {}, []
    for tabla in sorted(set(pre) | set(post)):
        a, b = pre.get(tabla, {}), post.get(tabla, {})
        distintas = [k for k in set(a) | set(b) if a.get(k, [None])[0] != b.get(k, [None])[0]]
        if not distintas:
            continue
        cambios[tabla] = len(distintas)
        for k in distintas:
            _, d, f = b.get(k) or a.get(k)
            if d not in documentos and f not in duenas:
                ajenas.append({"tabla": tabla, "fila": k})
    return {"filas_cambiadas_por_tabla": cambios, "filas_ajenas": ajenas[:50],
            "veredicto": "POSTCHECK_OK" if not ajenas else "POSTCHECK_FILAS_AJENAS"}


# --------------------------------------------------------------------------- puertas


def puertas(noche: Noche, cfg: dict, op: dict, marcas: dict, tareas: dict, fallos_git: list[str],
            previas: list[dict], fecha: dt.date) -> list[str]:
    fallos = list(fallos_git)
    if cfg.get("luna_habilitada") is not False:
        fallos.append("LUNA_NO_APAGADA")
    if list(cfg.get("farmacias_habilitadas") or []) != ["PIO"]:
        fallos.append(f"FARMACIAS_NO_SOLO_PIO:{cfg.get('farmacias_habilitadas')}")
    auto = (cfg.get("normalizacion_automatica"), cfg.get("conciliacion_automatica"))
    if noche.modo == "SOMBRA" and auto != (False, False):
        fallos.append(f"SOMBRA_CON_FLAGS_ENCENDIDOS:{auto}")
    if noche.modo == "REAL" and not any(auto):
        fallos.append("REAL_CON_FLAGS_APAGADOS")
    for clave, certificado in TOLERANCIAS_CERTIFICADAS.items():
        if cfg.get(clave) is None or Decimal(str(cfg[clave])) != certificado:
            fallos.append(f"TOLERANCIA_NO_CERTIFICADA:{clave}={cfg.get(clave)}")
    for clave, valor in op.items():
        if valor != 0:
            fallos.append(f"{clave.upper()}_DISTINTO_DE_0:{valor}")
    fallos += [f"MIGRACION_AUSENTE:{k}" for k, v in marcas.items() if not v]
    fallos += [f"NOCHE_ANTERIOR_SIN_CERRAR:{p['fecha']}" for p in previas if p["resultado"] == "EN_CURSO"]
    fallos += puertas_tareas(tareas, fecha)
    return fallos


def puertas_tareas(info: dict, fecha: dt.date) -> list[str]:
    """Las dos tareas de esta noche terminadas con codigo 0 (fecha local de su ultima ejecucion = hoy)."""
    if "error" in info:
        return [f"TAREAS_NO_DETERMINABLES:{info['error']}"]
    por_nombre = {unicodedata.normalize("NFC", t["nombre"]): t for t in info.get("tareas", [])}
    fallos = []
    for nombre in TAREAS_PREVIAS:
        tarea = por_nombre.get(unicodedata.normalize("NFC", nombre))
        if tarea is None:
            fallos.append(f"TAREA_NO_ENCONTRADA:{nombre}")
            continue
        if tarea.get("resultado") == RESULTADO_EN_EJECUCION:
            fallos.append(f"TAREA_EN_EJECUCION:{nombre}")
        elif tarea.get("resultado") != 0:
            fallos.append(f"TAREA_CON_ERROR:{nombre}:{tarea.get('resultado')}")
        ultima = tarea.get("ultima")
        if not ultima:
            fallos.append(f"TAREA_SIN_EJECUCION:{nombre}")
            continue
        momento = dt.datetime.fromisoformat(str(ultima))  # 'o' de PowerShell (UTC, 7 decimales)
        if momento.tzinfo is None:
            momento = momento.replace(tzinfo=dt.timezone.utc)
        if momento.astimezone().date() != fecha:
            fallos.append(f"TAREA_NO_EJECUTADA_ESTA_NOCHE:{nombre}:{ultima}")
    return fallos


# --------------------------------------------------------------------------- fases


def _fase_normalizacion(entorno: Entorno, noche: Noche, worker, limite: int, fin: dt.datetime) -> None:
    while len(noche.documentos) < limite:
        if entorno.reloj() >= fin:
            noche.fin_por_limite = True
            return
        with entorno.abrir_lectura() as lector:
            cola = _cola_normalizacion(lector, "AUTOMATICO")
            if not cola:
                return
            previsto = cola[0][0]
            antes = _documento(lector, previsto)
        reclamado = worker.normalizacion.ejecutar_una()
        with entorno.abrir_lectura() as lector:
            despues = _documento(lector, previsto)
            op = _operacion(lector)
            cfg = _configuracion(lector)
            ejecucion = _ultima_ejecucion(lector, previsto)
        if despues["huella"] == antes["huella"]:
            if not reclamado and not cfg.get("normalizacion_automatica"):
                noche.motivo = "FLAG_NORMALIZACION_APAGADO_DURANTE_LA_NOCHE"
                return
            raise Parada(f"DOCUMENTO_RECLAMADO_DISTINTO_DEL_PREVISTO:{previsto}")
        if despues["estado_lectura"] == "NORMALIZANDO" or despues["bloqueado_por"] or any(op.values()):
            raise Parada(f"HUERFANO_O_CLAIM_VIVO:{previsto}:{op}")
        estado = despues["estado_lectura"]
        clase = {"NORMALIZADA": "ALLIANCE", "PROVEEDOR_NO_SOPORTADO": "NO_SOPORTADO",
                 "ERROR": "DEFECTO", "REVISION": "DEFECTO"}.get(estado)
        if clase is None:
            raise Parada(f"ESTADO_DOCUMENTO_INESPERADO:{previsto}:{estado}")
        registro = {"documento_id": previsto, "estado": estado, "clase": clase, "facturas": despues["facturas"],
                    "intentos": despues["intentos"], "ejecucion": ejecucion}
        noche.documentos.append(registro)
        if clase == "DEFECTO":
            noche.para_revisar.append({"tipo": "DEFECTO", "documento_id": previsto, "estado": estado,
                                       "intentos": despues["intentos"], "ejecucion": ejecucion})
    noche.fin_por_limite = True


def _n1_conciliacion(lector: LectorReadOnly, modo_claim: str) -> tuple[str | None, dict | None, str | None]:
    """Devuelve (factura, simulacion, motivo_para_revisar) del n.o 1 del orden oficial."""
    cola = _cola_conciliacion(lector, modo_claim)
    if not cola:
        return None, None, None
    factura = cola[0]
    simulacion = simular_conciliacion(lector, factura, "AUTOMATICO")
    if not es_alliance(simulacion):
        return factura, simulacion, "NO_ALLIANCE"
    r18 = revisiones_r18_que_afectan(lector, factura)
    if r18:
        simulacion["r18"] = r18
        return factura, simulacion, "R18_PENDIENTE"
    if simulacion.get("camino") != "PERSISTIR" or simulacion.get("resultado") != "CONCILIADA":
        return factura, simulacion, "DIFERENCIA"
    return factura, simulacion, None


def _anotar_para_revisar(noche: Noche, factura: str, simulacion: dict, motivo: str) -> None:
    noche.para_revisar.append({
        "tipo": motivo, "factura_id": factura, "numero_factura": simulacion.get("numero_factura"),
        "resultado_simulado": simulacion.get("resultado") or simulacion.get("camino"),
        "diferencia": simulacion.get("diferencia"), "fallo": simulacion.get("fallo"),
        "r18": simulacion.get("r18")})


def _fase_conciliacion(entorno: Entorno, noche: Noche, worker, limite: int, fin: dt.datetime) -> None:
    while len(noche.conciliaciones) < limite:
        if entorno.reloj() >= fin:
            noche.fin_por_limite = True
            return
        with entorno.abrir_lectura() as lector:
            factura, simulacion, motivo = _n1_conciliacion(lector, "AUTOMATICO")
        if factura is None:
            return
        if motivo is not None:
            _anotar_para_revisar(noche, factura, simulacion, motivo)
            return
        reclamada = worker.conciliacion.ejecutar_una()
        with entorno.abrir_lectura() as lector:
            despues = _factura(lector, factura)
            op = _operacion(lector)
            cfg = _configuracion(lector)
        if not reclamada and despues["estado"] == "PENDIENTE_CONCILIAR" and not cfg.get("conciliacion_automatica"):
            noche.motivo = "FLAG_CONCILIACION_APAGADO_DURANTE_LA_NOCHE"
            return
        if despues["bloqueado_por"] or any(op.values()):
            raise Parada(f"CLAIM_VIVO_TRAS_CONCILIAR:{factura}:{op}")
        if (despues["estado"] != "CONCILIADA"
                or despues["idempotency_key"] != simulacion["idempotency_key_prevista"]):
            raise Parada(f"RESULTADO_REAL_DISTINTO_DEL_SIMULADO:{factura}:{despues}")
        noche.conciliaciones.append({"factura_id": factura, "numero_factura": simulacion.get("numero_factura"),
                                     "diferencia": simulacion.get("diferencia"),
                                     "idempotency_key": despues["idempotency_key"]})
    noche.fin_por_limite = True


def _fase_sombra(entorno: Entorno, noche: Noche, limite_docs: int, limite_conc: int) -> None:
    """Lo que haria la noche con los flags encendidos (selector sin el interruptor), sin reclamar nada."""
    with entorno.abrir_lectura() as lector:
        cola_docs = _cola_normalizacion(lector, "MANUAL_ONE_SHOT")
        cola_conc = _cola_conciliacion(lector, "MANUAL_ONE_SHOT")
        factura, simulacion, motivo = _n1_conciliacion(lector, "MANUAL_ONE_SHOT")
    noche.sombra = {
        "documentos_que_reclamaria": [{"documento_id": d[0], "estado": d[1], "fecha_importacion": d[2]}
                                      for d in cola_docs[:limite_docs]],
        "conciliacion_n1": simulacion,
        "conciliacion_n1_motivo_para_revisar": motivo,
        "facturas_siguientes_no_simuladas": cola_conc[1:limite_conc],
    }
    if factura is not None and motivo is not None:
        _anotar_para_revisar(noche, factura, simulacion, motivo)


# --------------------------------------------------------------------------- noche completa


def _fila_resumen(noche: Noche, informe_sha: str | None) -> dict:
    return {"resultado": noche.resultado, "motivo": (noche.motivo or None) and noche.motivo[:2000],
            "fin": dt.datetime.now(dt.timezone.utc).isoformat(), **noche.contadores(),
            "para_revisar": noche.para_revisar, "cola_restante": noche.cola_restante,
            "informe_sha256": informe_sha}


def _escribir_informe(entorno: Entorno, noche: Noche) -> str:
    carpeta = Path(entorno.directorio_informes) / noche.fecha.isoformat()
    carpeta.mkdir(parents=True, exist_ok=True)
    informe = {
        "fecha": noche.fecha.isoformat(), "modo": noche.modo, "inicio": noche.inicio.isoformat(),
        "commit": noche.commit, "limites": noche.limites, "resultado": noche.resultado, "motivo": noche.motivo,
        "puertas": noche.puertas, "contadores": noche.contadores(), "documentos": noche.documentos,
        "conciliaciones": noche.conciliaciones, "para_revisar": noche.para_revisar, "sombra": noche.sombra,
        "postcheck": noche.postcheck, "cola_restante": noche.cola_restante,
    }
    ruta = carpeta / "informe.json"
    ruta.write_text(json.dumps(informe, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    c = noche.contadores()
    resumen = [
        f"Noche {noche.fecha} ({noche.modo}): {noche.resultado}" + (f" - {noche.motivo}" if noche.motivo else ""),
        f"Documentos: {c['documentos_reclamados']} (Alliance {c['alliance_persistidos']}, facturas "
        f"{c['facturas_creadas']}; no soportados {c['no_soportados']}; defectos {c['defectos']})",
        f"Conciliadas: {c['conciliadas']}",
        f"Para revisar: {len(noche.para_revisar)}",
        *(f"  - {p['tipo']}: {p.get('numero_factura') or p.get('documento_id')}" for p in noche.para_revisar),
        f"Cola restante: {noche.cola_restante}",
        f"Postcheck: {noche.postcheck.get('veredicto', 'NO_EJECUTADO')}",
    ]
    (carpeta / "resumen.txt").write_text("\n".join(resumen) + "\n", encoding="utf-8")
    sha = hashlib.sha256(ruta.read_bytes()).hexdigest()
    sumas = [f"{hashlib.sha256((carpeta / n).read_bytes()).hexdigest()} *{n}" for n in ("informe.json", "resumen.txt")]
    (carpeta / "SHA256SUMS.txt").write_text("\n".join(sumas) + "\n", encoding="utf-8")
    return sha


def ejecutar_noche(modo: str, entorno: Entorno) -> int:
    if modo not in MODOS:
        raise ValueError(f"MODO_NO_ADMITIDO:{modo}")
    inicio = entorno.reloj()
    noche = Noche(fecha=entorno.fecha_local(inicio), modo=modo, inicio=inicio)
    commit, fallos_git = entorno.puerta_git()
    noche.commit = commit
    with entorno.abrir_lectura() as lector:
        previas = _noches_previas(lector, noche.fecha)
    docs, conc = limites_por_historial(previas)
    noche.limites = {"documentos": docs, "conciliaciones": conc, "minutos": MINUTOS_MAXIMOS}

    # Guard: una sola noche por fecha (clave primaria). Si ya existe, no se hace nada mas.
    try:
        entorno.cliente.table(TABLA_RESUMEN).insert({
            "fecha": noche.fecha.isoformat(), "modo": modo, "inicio": inicio.isoformat(),
            "resultado": "EN_CURSO", "commit_codigo": commit, "limites": noche.limites}).execute()
    except Exception as exc:
        noche.resultado, noche.motivo = "PARADA", f"NOCHE_YA_EJECUTADA_O_RESUMEN_NO_ESCRIBIBLE:{type(exc).__name__}"
        _escribir_informe(entorno, noche)
        return CODIGO_YA_EJECUTADA

    pre: dict | None = None
    pre_trabajadores: dict | None = None
    try:
        with entorno.abrir_lectura() as lector:
            cfg, op, marcas = _configuracion(lector), _operacion(lector), _marcas(lector)
        noche.puertas = puertas(noche, cfg, op, marcas, entorno.tareas(), fallos_git, previas, noche.fecha)
        if noche.puertas:
            raise Parada("PUERTAS:" + ";".join(noche.puertas))
        with entorno.abrir_lectura() as lector:
            pre = snapshot_por_fila(lector)
        pre_trabajadores = snapshot_trabajadores(entorno)
        fin = inicio + dt.timedelta(minutes=MINUTOS_MAXIMOS)
        if modo == "SOMBRA":
            _fase_sombra(entorno, noche, docs, conc)
        else:
            configuracion = ConfiguracionRuntime(
                normalizacion_automatica=bool(cfg["normalizacion_automatica"]),
                conciliacion_automatica=bool(cfg["conciliacion_automatica"]),
                luna_habilitada=bool(cfg["luna_habilitada"]),
                farmacias_habilitadas=tuple(cfg["farmacias_habilitadas"]),
                tolerancia_conciliacion=Decimal(str(cfg["tolerancia_conciliacion"])),
                tolerancia_suelo=Decimal(str(cfg["conciliacion_tolerancia_suelo"])),
                tolerancia_por_albaran=Decimal(str(cfg["conciliacion_tolerancia_por_albaran"])),
                tolerancia_tope=Decimal(str(cfg["conciliacion_tolerancia_tope"])))
            worker = entorno.construir_worker(configuracion)
            if configuracion.normalizacion_automatica:
                _fase_normalizacion(entorno, noche, worker, docs, fin)
            if configuracion.conciliacion_automatica:
                _fase_conciliacion(entorno, noche, worker, conc, fin)
        noche.resultado = "FIN_LIMITE" if noche.fin_por_limite else "NOCHE_OK"
    except Parada as parada:
        noche.resultado, noche.motivo = "PARADA", str(parada)
    except Exception as exc:  # noqa: BLE001 - cualquier excepcion corta la noche (2BK: postcheck igualmente)
        noche.resultado, noche.motivo = "PARADA", f"EXCEPCION:{type(exc).__name__}:{exc}"
    finally:
        try:
            with entorno.abrir_lectura() as lector:
                if pre is not None:
                    post = snapshot_por_fila(lector)
                    noche.postcheck = postcheck_por_fila(
                        pre, post, {d["documento_id"] for d in noche.documentos},
                        {c["factura_id"] for c in noche.conciliaciones})
                noche.cola_restante = {
                    "documentos": len(_cola_normalizacion(lector, "MANUAL_ONE_SHOT")),
                    "facturas_conciliables": len(_cola_conciliacion(lector, "MANUAL_ONE_SHOT"))}
        except Exception as exc:  # noqa: BLE001
            noche.postcheck = {"veredicto": "POSTCHECK_NO_EJECUTADO", "error": f"{type(exc).__name__}: {exc}"}
        if pre is not None and noche.postcheck is not None:
            # Despues de cerrar la sesion anterior: las sesiones comparten conexion y no se anidan.
            noche.postcheck["trabajadores"] = cambios_trabajadores(pre_trabajadores, snapshot_trabajadores(entorno))
        if noche.postcheck and noche.postcheck.get("veredicto") != "POSTCHECK_OK":
            noche.resultado = "PARADA"
            noche.motivo = ((noche.motivo + "; ") if noche.motivo else "") + noche.postcheck["veredicto"]
    sha = _escribir_informe(entorno, noche)
    try:
        entorno.cliente.table(TABLA_RESUMEN).update(_fila_resumen(noche, sha)).eq(
            "fecha", noche.fecha.isoformat()).execute()
    except Exception:  # noqa: BLE001 - la fila queda EN_CURSO: la noche siguiente se para (DISENO §6, fila no escribible)
        return CODIGO_PARADA
    return CODIGO_PARADA if noche.resultado == "PARADA" else CODIGO_OK


# --------------------------------------------------------------------------- produccion


def _conexion_lectura_productiva():
    sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))
    from urllib.parse import unquote, urlparse

    from dotenv import dotenv_values
    import psycopg2

    dsn = os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"]
    app = urlparse(dotenv_values(ROOT / ".env").get("SUPABASE_URL", ""))
    db = urlparse(dsn)
    ref = (app.hostname or "").split(".")[0]
    if not (ref == PROJECT_REF and (
            db.hostname == f"db.{ref}.supabase.co"
            or ((db.hostname or "").endswith(".pooler.supabase.com")
                and unquote(db.username or "").endswith("." + ref)))):
        raise SystemExit("DESTINO_PRODUCTIVO_NO_DEMOSTRADO")
    return psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name="cf_auto_alliance_lectura")


def _rol_de_clave(clave: str) -> str | None:
    try:
        carga = clave.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4))).get("role")
    except Exception:  # noqa: BLE001
        return None


def _cliente_productivo():
    from urllib.parse import urlparse

    from dotenv import dotenv_values, load_dotenv
    from src.supabase_client.conexion_supabase import obtener_cliente_supabase

    load_dotenv(ROOT / ".env")
    env = dotenv_values(ROOT / ".env")
    ref = (urlparse(env.get("SUPABASE_URL", "")).hostname or "").split(".")[0]
    clave = env.get("SUPABASE_KEY", "") or ""
    if ref != PROJECT_REF or _rol_de_clave(clave) in (None, "anon", "authenticated"):
        raise SystemExit("CLIENTE_NO_DEMOSTRADO")
    return obtener_cliente_supabase()


def _tareas_productivas() -> dict:
    nombres = ",".join("'" + n.replace("'", "''") + "'" for n in TAREAS_PREVIAS)
    ps = (
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8;"
        f"$t = @(foreach ($n in @({nombres})) {{ $i = Get-ScheduledTaskInfo -TaskName $n -ErrorAction Stop;"
        " [pscustomobject]@{ nombre = $n;"
        "  ultima = $(if ($i.LastRunTime) { $i.LastRunTime.ToUniversalTime().ToString('o') } else { $null });"
        "  resultado = $i.LastTaskResult } });"
        "ConvertTo-Json -InputObject $t -Depth 3")
    codificado = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", codificado],
                       capture_output=True, timeout=60)
    if r.returncode:
        return {"error": r.stderr.decode("utf-8", "replace").strip()[:500]}
    tareas = json.loads(r.stdout.decode("utf-8-sig") or "[]")
    return {"tareas": tareas if isinstance(tareas, list) else [tareas]}


def puerta_git(raiz: Path = ROOT) -> tuple[str | None, list[str]]:
    """Arbol limpio y HEAD = origin/main, o por delante solo con documentacion (REGLAS_CRITICAS)."""
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=raiz, capture_output=True, text=True, check=True).stdout.strip()

    try:
        head, origen = git("rev-parse", "HEAD"), git("rev-parse", "origin/main")
        fallos = []
        if git("status", "--porcelain"):
            fallos.append("GIT_ARBOL_NO_LIMPIO")
        if head != origen:
            ancestro = subprocess.run(["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"], cwd=raiz,
                                      capture_output=True).returncode == 0
            pendientes = [p for p in git("diff", "--name-only", "origin/main..HEAD").splitlines() if p]
            if not ancestro or any(not (p.startswith("docs/") or p.endswith(".md")) for p in pendientes):
                fallos.append("GIT_HEAD_DISTINTO_DE_ORIGIN_MAIN")
        return head, fallos
    except Exception as exc:  # noqa: BLE001
        return None, [f"GIT_NO_DETERMINABLE:{type(exc).__name__}"]


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in MODOS:
        raise SystemExit("uso: python -m src.facturas.runtime_supabase.noche_automatica <SOMBRA|REAL> <dir>")
    from .compositor_automatico import construir_worker_automatico_productivo
    from .lectura_readonly import sesion_lectura

    directorio = Path(argv[1]).resolve()
    if directorio == ROOT or ROOT in directorio.parents:
        raise SystemExit("INFORMES_DENTRO_DEL_REPOSITORIO")
    conexion = _conexion_lectura_productiva()
    cliente = _cliente_productivo()
    trabajo = directorio / "_trabajo"
    try:
        entorno = Entorno(
            abrir_lectura=lambda: sesion_lectura(conexion),
            cliente=cliente,
            tareas=_tareas_productivas,
            puerta_git=puerta_git,
            construir_worker=lambda cfg: construir_worker_automatico_productivo(cliente, cfg, WORKER_BASE, trabajo),
            directorio_informes=directorio,
        )
        return ejecutar_noche(argv[0], entorno)
    finally:
        conexion.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
