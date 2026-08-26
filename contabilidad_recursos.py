"""Contabilidad semanal local y durable de recursos del Orquestador V0.2.11."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import ROUND_CEILING, Decimal, InvalidOperation
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
from typing import Any, Callable


PRESUPUESTO_SEMANAL_PREDETERMINADO = Decimal("3.80")
UMBRAL_PROXIMIDAD_PORCENTAJE = Decimal("80.00")
MONEDA_RECURSOS = "EUR"
PRESUPUESTO_SCHEMA_VERSION = 1
CENTIMO = Decimal("0.01")


class ErrorContabilidadRecursos(RuntimeError):
    """La contabilidad no puede procesarse sin perder garantías."""


class DatoMonetarioInvalido(ErrorContabilidadRecursos, ValueError):
    """Un importe no cumple el contrato monetario."""


def _importe(valor: Decimal | str | int, campo: str) -> Decimal:
    if isinstance(valor, bool) or isinstance(valor, float):
        raise DatoMonetarioInvalido(f"{campo} debe proporcionarse como Decimal, texto o entero")
    try:
        resultado = Decimal(valor)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DatoMonetarioInvalido(f"{campo} no es un importe válido") from exc
    if not resultado.is_finite() or resultado < 0:
        raise DatoMonetarioInvalido(f"{campo} debe ser finito y no negativo")
    if resultado != resultado.quantize(CENTIMO):
        raise DatoMonetarioInvalido(f"{campo} admite como máximo dos decimales")
    return resultado.quantize(CENTIMO)


def _dinero(valor: Decimal) -> str:
    return format(valor.quantize(CENTIMO), ".2f")


def _ahora_local() -> datetime:
    return datetime.now().astimezone()


@dataclass(frozen=True)
class SemanaNatural:
    semana_id: str
    inicio: datetime
    fin: datetime

    @classmethod
    def desde_fecha(cls, fecha: datetime) -> "SemanaNatural":
        if fecha.tzinfo is None:
            raise ErrorContabilidadRecursos("la fecha debe incluir zona horaria")
        local = fecha.astimezone()
        lunes = local.date() - timedelta(days=local.weekday())
        inicio = datetime.combine(lunes, time.min, tzinfo=local.tzinfo)
        fin = inicio + timedelta(days=7) - timedelta(microseconds=1)
        iso = lunes.isocalendar()
        return cls(f"{iso.year}-W{iso.week:02d}", inicio, fin)


@dataclass(frozen=True)
class ResumenPresupuestoSemanal:
    semana_id: str
    inicio: str
    fin: str
    moneda: str
    presupuesto_total: Decimal
    coste_real_acumulado: Decimal
    coste_comprometido: Decimal
    presupuesto_disponible: Decimal
    porcentaje_consumido: Decimal
    consumo_relevante: Decimal
    umbral_proximidad_porcentaje: Decimal
    umbral_proximidad_importe: Decimal
    estado_presupuesto: str
    aviso_proximidad: bool
    limite_alcanzado_o_superado: bool
    ejecuciones_con_coste: int
    autorizaciones_excepcionales: int
    costes_desconocidos_registrados: int
    actualizado_en: str

    def a_dict(self) -> dict[str, Any]:
        return {
            "semana_id": self.semana_id,
            "inicio": self.inicio,
            "fin": self.fin,
            "moneda": self.moneda,
            "presupuesto_total": _dinero(self.presupuesto_total),
            "coste_real_acumulado": _dinero(self.coste_real_acumulado),
            "coste_comprometido": _dinero(self.coste_comprometido),
            "presupuesto_disponible": _dinero(self.presupuesto_disponible),
            "porcentaje_consumido": format(
                self.porcentaje_consumido.quantize(Decimal("0.01")), ".2f"
            ),
            "consumo_relevante": _dinero(self.consumo_relevante),
            "umbral_proximidad_porcentaje": format(
                self.umbral_proximidad_porcentaje.quantize(Decimal("0.01")), ".2f"
            ),
            "umbral_proximidad_importe": _dinero(self.umbral_proximidad_importe),
            "estado_presupuesto": self.estado_presupuesto,
            "aviso_proximidad": self.aviso_proximidad,
            "limite_alcanzado_o_superado": self.limite_alcanzado_o_superado,
            "ejecuciones_con_coste": self.ejecuciones_con_coste,
            "autorizaciones_excepcionales": self.autorizaciones_excepcionales,
            "costes_desconocidos_registrados": self.costes_desconocidos_registrados,
            "actualizado_en": self.actualizado_en,
        }


@dataclass(frozen=True)
class ResultadoContable:
    exito: bool
    codigo: str
    idempotente: bool
    resumen: ResumenPresupuestoSemanal
    datos: dict[str, Any]


class ContabilidadRecursos:
    """Store JSON semanal con operaciones idempotentes y aritmética Decimal."""

    def __init__(
        self,
        directorio: str | Path,
        *,
        presupuesto_predeterminado: Decimal | str | int = PRESUPUESTO_SEMANAL_PREDETERMINADO,
        reloj: Callable[[], datetime] | None = None,
    ) -> None:
        self.directorio = Path(directorio)
        self._presupuesto_inicial = _importe(
            presupuesto_predeterminado, "presupuesto_predeterminado"
        )
        self._reloj = reloj or _ahora_local
        self._lock = RLock()

    def consultar_presupuesto(
        self, *, fecha: datetime | None = None, semana_id: str | None = None
    ) -> ResumenPresupuestoSemanal:
        with self._lock:
            if semana_id is not None:
                estado = self._cargar_semana_existente(semana_id)
            else:
                estado = self._cargar_o_inicializar(fecha or self._reloj())
            return self._resumen(estado)

    def establecer_presupuesto_semanal(
        self,
        importe: Decimal | str | int,
        *,
        motivo: str | None = None,
        fecha: datetime | None = None,
    ) -> ResultadoContable:
        nuevo = _importe(importe, "presupuesto_semanal")
        with self._lock:
            estado = self._cargar_o_inicializar(fecha or self._reloj())
            anterior = Decimal(estado["presupuesto_total"])
            if anterior == nuevo:
                return ResultadoContable(
                    True, "WEEKLY_BUDGET_UNCHANGED", True,
                    self._resumen(estado),
                    {"anterior": _dinero(anterior), "nuevo": _dinero(nuevo)},
                )
            estado["presupuesto_total"] = _dinero(nuevo)
            evento = self._evento(
                "WEEKLY_BUDGET_UPDATED",
                {
                    "anterior": _dinero(anterior),
                    "nuevo": _dinero(nuevo),
                    "motivo": motivo,
                },
            )
            estado["eventos"].append(evento)
            self._guardar(estado)
            return ResultadoContable(
                True, "WEEKLY_BUDGET_UPDATED", False,
                self._resumen(estado), evento,
            )

    def comprobar_presupuesto(
        self,
        coste_estimado: Decimal | str | int,
        *,
        referencia: str,
        fecha: datetime | None = None,
    ) -> ResultadoContable:
        coste = _importe(coste_estimado, "coste_estimado")
        if not isinstance(referencia, str) or not referencia.strip():
            raise ErrorContabilidadRecursos("referencia obligatoria")
        with self._lock:
            estado = self._cargar_o_inicializar(fecha or self._reloj())
            resumen = self._resumen(estado)
            cabe = coste <= resumen.presupuesto_disponible
            exceso = max(Decimal("0.00"), coste - resumen.presupuesto_disponible)
            clave = f"CHECK:{referencia}:{_dinero(coste)}"
            evento_existente = self._evento_por_clave(estado, clave)
            if evento_existente is None:
                estado["eventos"].append(
                    self._evento(
                        "RESOURCE_BUDGET_CHECKED",
                        {
                            "referencia": referencia,
                            "coste_estimado": _dinero(coste),
                            "presupuesto_total": _dinero(resumen.presupuesto_total),
                            "coste_real_acumulado": _dinero(
                                resumen.coste_real_acumulado
                            ),
                            "coste_comprometido": _dinero(
                                resumen.coste_comprometido
                            ),
                            "presupuesto_disponible": _dinero(
                                resumen.presupuesto_disponible
                            ),
                            "porcentaje_consumido": format(
                                resumen.porcentaje_consumido.quantize(
                                    Decimal("0.01")
                                ),
                                ".2f",
                            ),
                            "estado_presupuesto": resumen.estado_presupuesto,
                            "aviso_proximidad": resumen.aviso_proximidad,
                            "limite_alcanzado_o_superado": (
                                resumen.limite_alcanzado_o_superado
                            ),
                            "cabe": cabe,
                            "exceso_estimado": _dinero(exceso),
                        },
                        clave=clave,
                    )
                )
                self._guardar(estado)
                resumen = self._resumen(estado)
            return ResultadoContable(
                cabe,
                "PRESUPUESTO_DISPONIBLE" if cabe else "PRESUPUESTO_SEMANAL_INSUFICIENTE",
                evento_existente is not None,
                resumen,
                {
                    "referencia": referencia,
                    "coste_estimado": _dinero(coste),
                    "exceso_estimado": _dinero(exceso),
                    "cabe": cabe,
                },
            )

    def reservar_coste(
        self,
        referencia: str,
        importe: Decimal | str | int,
        *,
        task_id: str | None = None,
        run_id: str | None = None,
        retry_id: str | None = None,
        nivel_recurso: str | None = None,
        autorizacion_excepcional: bool = False,
        fecha: datetime | None = None,
    ) -> ResultadoContable:
        coste = _importe(importe, "coste_reservado")
        if not isinstance(referencia, str) or not referencia.strip():
            raise ErrorContabilidadRecursos("referencia de reserva obligatoria")
        with self._lock:
            estado = self._cargar_o_inicializar(fecha or self._reloj())
            existente = estado["reservas"].get(referencia)
            if existente is not None:
                return ResultadoContable(
                    True, "RESOURCE_COST_ALREADY_RESERVED", True,
                    self._resumen(estado), dict(existente),
                )
            reserva = {
                "referencia": referencia,
                "importe": _dinero(coste),
                "task_id": task_id,
                "run_id": run_id,
                "retry_id": retry_id,
                "nivel_recurso": nivel_recurso,
                "autorizacion_excepcional": autorizacion_excepcional,
                "estado": "ACTIVA",
                "creada_en": self._timestamp(),
                "liberada_en": None,
                "motivo_liberacion": None,
            }
            estado["reservas"][referencia] = reserva
            evento = self._evento("RESOURCE_COST_RESERVED", dict(reserva))
            estado["eventos"].append(evento)
            if autorizacion_excepcional:
                self._registrar_autorizacion_excepcional(
                    estado, referencia, task_id=task_id, retry_id=retry_id
                )
            self._guardar(estado)
            return ResultadoContable(
                True, "RESOURCE_COST_RESERVED", False,
                self._resumen(estado), dict(reserva),
            )

    def liberar_reserva(
        self,
        *,
        referencia: str | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
        retry_id: str | None = None,
        motivo: str = "liberación explícita",
        fecha: datetime | None = None,
    ) -> ResultadoContable:
        with self._lock:
            estado = self._cargar_o_inicializar(fecha or self._reloj())
            reserva = self._buscar_reserva(
                estado, referencia=referencia, task_id=task_id,
                run_id=run_id, retry_id=retry_id, solo_activa=True,
            )
            if reserva is None:
                return ResultadoContable(
                    True, "RESOURCE_COST_RESERVATION_ALREADY_RELEASED", True,
                    self._resumen(estado), {},
                )
            reserva["estado"] = "LIBERADA"
            reserva["liberada_en"] = self._timestamp()
            reserva["motivo_liberacion"] = motivo
            evento = self._evento(
                "RESOURCE_COST_RESERVATION_RELEASED",
                {
                    "referencia": reserva["referencia"],
                    "importe": reserva["importe"],
                    "motivo": motivo,
                },
            )
            estado["eventos"].append(evento)
            self._guardar(estado)
            return ResultadoContable(
                True, "RESOURCE_COST_RESERVATION_RELEASED", False,
                self._resumen(estado), dict(reserva),
            )

    def registrar_coste_real(
        self,
        run_id: str,
        importe: Decimal | str | int,
        *,
        task_id: str | None,
        origen: str,
        retry_id: str | None = None,
        nivel_recurso: str | None = None,
        fecha: datetime | None = None,
    ) -> ResultadoContable:
        coste = _importe(importe, "coste_real")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ErrorContabilidadRecursos("run_id obligatorio")
        if not isinstance(origen, str) or not origen.strip():
            raise ErrorContabilidadRecursos("origen del coste obligatorio")
        with self._lock:
            estado = self._cargar_o_inicializar(fecha or self._reloj())
            existente = estado["costes_reales"].get(run_id)
            if existente is not None:
                return ResultadoContable(
                    True, "RESOURCE_COST_ALREADY_RECORDED", True,
                    self._resumen(estado), dict(existente),
                )
            reserva = self._buscar_reserva(
                estado, task_id=task_id, run_id=run_id,
                retry_id=retry_id, solo_activa=True,
            )
            estimacion = Decimal(reserva["importe"]) if reserva else None
            if reserva is not None:
                reserva["estado"] = "LIBERADA"
                reserva["liberada_en"] = self._timestamp()
                reserva["motivo_liberacion"] = "coste real registrado"
                estado["eventos"].append(
                    self._evento(
                        "RESOURCE_COST_RESERVATION_RELEASED",
                        {
                            "referencia": reserva["referencia"],
                            "importe": reserva["importe"],
                            "motivo": "coste real registrado",
                        },
                    )
                )
            registro = {
                "run_id": run_id,
                "task_id": task_id,
                "retry_id": retry_id,
                "importe": _dinero(coste),
                "moneda": MONEDA_RECURSOS,
                "origen": origen,
                "nivel_recurso": nivel_recurso,
                "coste_estimado": _dinero(estimacion) if estimacion is not None else None,
                "diferencia_estimado_real": (
                    _dinero(coste - estimacion) if estimacion is not None else None
                ),
                "autorizacion_excepcional": bool(
                    reserva and reserva.get("autorizacion_excepcional")
                ),
                "timestamp": self._timestamp(),
            }
            estado["costes_reales"][run_id] = registro
            desconocido = next(
                (
                    item
                    for item in estado["costes_desconocidos"].values()
                    if item.get("run_id") == run_id
                    or (retry_id is not None and item.get("retry_id") == retry_id)
                    or (task_id is not None and item.get("task_id") == task_id)
                ),
                None,
            )
            if desconocido is not None:
                desconocido["resuelto"] = True
                desconocido["resuelto_en"] = self._timestamp()
            estado["eventos"].append(self._evento("RESOURCE_COST_RECORDED", registro))
            self._guardar(estado)
            return ResultadoContable(
                True, "RESOURCE_COST_RECORDED", False,
                self._resumen(estado), dict(registro),
            )

    def registrar_coste_desconocido(
        self,
        referencia: str,
        *,
        task_id: str | None = None,
        run_id: str | None = None,
        retry_id: str | None = None,
        nivel_recurso: str | None = None,
        fecha: datetime | None = None,
    ) -> ResultadoContable:
        if not isinstance(referencia, str) or not referencia.strip():
            raise ErrorContabilidadRecursos("referencia de coste desconocido obligatoria")
        with self._lock:
            estado = self._cargar_o_inicializar(fecha or self._reloj())
            existente = estado["costes_desconocidos"].get(referencia)
            if existente is not None:
                return ResultadoContable(
                    True, "COSTE_DESCONOCIDO_ALREADY_RECORDED", True,
                    self._resumen(estado), dict(existente),
                )
            registro = {
                "referencia": referencia,
                "task_id": task_id,
                "run_id": run_id,
                "retry_id": retry_id,
                "nivel_recurso": nivel_recurso,
                "estado": "COSTE_DESCONOCIDO",
                "timestamp": self._timestamp(),
                "resuelto": False,
                "resuelto_en": None,
            }
            estado["costes_desconocidos"][referencia] = registro
            estado["eventos"].append(
                self._evento("RESOURCE_COST_UNKNOWN_RECORDED", registro)
            )
            self._guardar(estado)
            return ResultadoContable(
                True, "COSTE_DESCONOCIDO", False,
                self._resumen(estado), dict(registro),
            )

    def consultar_consumo(
        self, *, semana_id: str | None = None, historico: bool = False
    ) -> dict[str, Any]:
        with self._lock:
            if historico:
                semanas = [
                    self._cargar_semana_existente(path.stem)
                    for path in sorted(self.directorio.glob("????-W??.json"))
                ] if self.directorio.exists() else []
                return {
                    "historico": [self._detalle_consumo(item) for item in semanas]
                }
            estado = (
                self._cargar_semana_existente(semana_id)
                if semana_id else self._cargar_o_inicializar(self._reloj())
            )
            return self._detalle_consumo(estado)

    def _cargar_o_inicializar(self, fecha: datetime) -> dict[str, Any]:
        semana = SemanaNatural.desde_fecha(fecha)
        path = self.directorio / f"{semana.semana_id}.json"
        if path.is_file():
            return self._leer(path)
        presupuesto = self._presupuesto_configurado()
        timestamp = self._timestamp()
        estado = {
            "schema_version": PRESUPUESTO_SCHEMA_VERSION,
            "semana_id": semana.semana_id,
            "inicio": semana.inicio.isoformat(),
            "fin": semana.fin.isoformat(),
            "moneda": MONEDA_RECURSOS,
            "presupuesto_inicial": _dinero(presupuesto),
            "presupuesto_total": _dinero(presupuesto),
            "reservas": {},
            "costes_reales": {},
            "costes_desconocidos": {},
            "autorizaciones_excepcionales": {},
            "eventos": [
                self._evento(
                    "WEEKLY_BUDGET_INITIALIZED",
                    {"presupuesto_total": _dinero(presupuesto)},
                    timestamp=timestamp,
                )
            ],
            "actualizado_en": timestamp,
        }
        self._guardar(estado)
        return estado

    def _presupuesto_configurado(self) -> Decimal:
        self.directorio.mkdir(parents=True, exist_ok=True)
        path = self.directorio / "configuracion.json"
        if path.is_file():
            try:
                datos = json.loads(path.read_text(encoding="utf-8"))
                return _importe(datos["presupuesto_semanal_predeterminado"], "configuración")
            except (OSError, json.JSONDecodeError, KeyError, DatoMonetarioInvalido) as exc:
                raise ErrorContabilidadRecursos(f"configuración de presupuesto inválida: {exc}") from exc
        datos = {
            "schema_version": 1,
            "moneda": MONEDA_RECURSOS,
            "presupuesto_semanal_predeterminado": _dinero(self._presupuesto_inicial),
        }
        self._guardar_json(path, datos)
        return self._presupuesto_inicial

    def _cargar_semana_existente(self, semana_id: str) -> dict[str, Any]:
        if not isinstance(semana_id, str) or not semana_id:
            raise ErrorContabilidadRecursos("semana_id obligatorio")
        path = self.directorio / f"{semana_id}.json"
        if not path.is_file():
            raise ErrorContabilidadRecursos(f"semana no encontrada: {semana_id}")
        return self._leer(path)

    def _leer(self, path: Path) -> dict[str, Any]:
        try:
            datos = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ErrorContabilidadRecursos(f"presupuesto ilegible: {path}: {exc}") from exc
        requeridos = {
            "schema_version", "semana_id", "inicio", "fin", "moneda",
            "presupuesto_inicial", "presupuesto_total", "reservas",
            "costes_reales", "costes_desconocidos",
            "autorizaciones_excepcionales", "eventos", "actualizado_en",
        }
        if set(datos) != requeridos or datos["schema_version"] != PRESUPUESTO_SCHEMA_VERSION:
            raise ErrorContabilidadRecursos(f"schema semanal inválido: {path}")
        for campo in ("presupuesto_inicial", "presupuesto_total"):
            _importe(datos[campo], campo)
        if datos["moneda"] != MONEDA_RECURSOS:
            raise ErrorContabilidadRecursos("moneda semanal no soportada")
        return datos

    def _guardar(self, estado: dict[str, Any]) -> None:
        estado["actualizado_en"] = self._timestamp()
        self._guardar_json(self.directorio / f"{estado['semana_id']}.json", estado)

    def _guardar_json(self, destino: Path, datos: dict[str, Any]) -> None:
        destino.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporal = tempfile.mkstemp(
            prefix=f".{destino.stem}.", suffix=".tmp", dir=destino.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archivo:
                json.dump(datos, archivo, ensure_ascii=False, indent=2, sort_keys=True)
                archivo.write("\n")
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, destino)
        except Exception:
            try:
                os.unlink(temporal)
            except OSError:
                pass
            raise

    def _resumen(self, estado: dict[str, Any]) -> ResumenPresupuestoSemanal:
        total = Decimal(estado["presupuesto_total"])
        real = sum(
            (Decimal(item["importe"]) for item in estado["costes_reales"].values()),
            Decimal("0.00"),
        )
        comprometido = sum(
            (
                Decimal(item["importe"])
                for item in estado["reservas"].values()
                if item["estado"] == "ACTIVA"
            ),
            Decimal("0.00"),
        )
        disponible = total - real - comprometido
        consumido = real + comprometido
        porcentaje = (
            consumido * Decimal("100") / total
            if total != 0
            else (Decimal("0") if consumido == 0 else Decimal("100"))
        )
        umbral_importe = (
            total * UMBRAL_PROXIMIDAD_PORCENTAJE / Decimal("100")
        ).quantize(CENTIMO, rounding=ROUND_CEILING)
        limite_alcanzado = consumido >= total
        aviso_proximidad = (
            consumido * Decimal("100")
            >= total * UMBRAL_PROXIMIDAD_PORCENTAJE
            and not limite_alcanzado
        )
        if limite_alcanzado:
            estado_presupuesto = "limite_alcanzado_o_superado"
        elif aviso_proximidad:
            estado_presupuesto = "cerca_del_limite"
        else:
            estado_presupuesto = "normal"
        return ResumenPresupuestoSemanal(
            semana_id=estado["semana_id"],
            inicio=estado["inicio"],
            fin=estado["fin"],
            moneda=estado["moneda"],
            presupuesto_total=total,
            coste_real_acumulado=real,
            coste_comprometido=comprometido,
            presupuesto_disponible=disponible,
            porcentaje_consumido=porcentaje,
            consumo_relevante=consumido,
            umbral_proximidad_porcentaje=UMBRAL_PROXIMIDAD_PORCENTAJE,
            umbral_proximidad_importe=umbral_importe,
            estado_presupuesto=estado_presupuesto,
            aviso_proximidad=aviso_proximidad,
            limite_alcanzado_o_superado=limite_alcanzado,
            ejecuciones_con_coste=len(estado["costes_reales"]),
            autorizaciones_excepcionales=len(estado["autorizaciones_excepcionales"]),
            costes_desconocidos_registrados=len(estado["costes_desconocidos"]),
            actualizado_en=estado["actualizado_en"],
        )

    def _detalle_consumo(self, estado: dict[str, Any]) -> dict[str, Any]:
        return {
            "presupuesto": self._resumen(estado).a_dict(),
            "costes_reales": list(estado["costes_reales"].values()),
            "reservas": list(estado["reservas"].values()),
            "costes_desconocidos": list(estado["costes_desconocidos"].values()),
            "autorizaciones_excepcionales": list(
                estado["autorizaciones_excepcionales"].values()
            ),
        }

    @staticmethod
    def _buscar_reserva(
        estado: dict[str, Any], *, referencia: str | None = None,
        task_id: str | None = None, run_id: str | None = None,
        retry_id: str | None = None, solo_activa: bool = False,
    ) -> dict[str, Any] | None:
        candidatas = list(estado["reservas"].values())
        for campo, valor in (
            ("referencia", referencia), ("run_id", run_id),
            ("retry_id", retry_id), ("task_id", task_id),
        ):
            if valor is None:
                continue
            encontrada = next(
                (
                    item for item in candidatas
                    if item.get(campo) == valor
                    and (not solo_activa or item["estado"] == "ACTIVA")
                ),
                None,
            )
            if encontrada is not None:
                return encontrada
        return None

    def _registrar_autorizacion_excepcional(
        self, estado: dict[str, Any], referencia: str,
        *, task_id: str | None, retry_id: str | None,
    ) -> None:
        if referencia in estado["autorizaciones_excepcionales"]:
            return
        registro = {
            "referencia": referencia,
            "task_id": task_id,
            "retry_id": retry_id,
            "tipo": "AUTORIZACION_EXCEPCIONAL_SOBRE_PRESUPUESTO",
            "timestamp": self._timestamp(),
        }
        estado["autorizaciones_excepcionales"][referencia] = registro
        estado["eventos"].append(
            self._evento("RESOURCE_COST_AUTHORIZATION_GRANTED", registro)
        )

    @staticmethod
    def _evento_por_clave(estado: dict[str, Any], clave: str) -> dict[str, Any] | None:
        return next(
            (item for item in estado["eventos"] if item.get("clave") == clave), None
        )

    def _evento(
        self, tipo: str, datos: dict[str, Any], *, clave: str | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        return {
            "tipo": tipo,
            "timestamp": timestamp or self._timestamp(),
            "clave": clave,
            "datos": datos,
        }

    def _timestamp(self) -> str:
        fecha = self._reloj()
        if fecha.tzinfo is None:
            raise ErrorContabilidadRecursos("el reloj debe devolver fecha con zona horaria")
        return fecha.astimezone().isoformat()
