"""Simulador en memoria de las RPC de conciliacion de la migracion 18 (Hito 2AV).

Reproduce R5 (claim AUTOMATICO / MANUAL_ONE_SHOT con el mismo ordering), R6
(cierre atomico con clave idempotente y replay que libera el claim), R7 (fallo
con backoff 1h/6h/24h y REVISION_CONCILIACION al 4.o) y R8 (disparador validado
contra el modo del claim). La elegibilidad se declara por factura (``apta``).
No simula tiempo real: ``backoff_futuro`` indica un ``conciliacion_proximo_at``
posterior a ahora y ``avanzar_tiempo`` lo vence.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field


MAX_INTENTOS = 4
BACKOFF_HORAS = (1, 6, 24)


class _Respuesta:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


@dataclass
class FacturaSimulada:
    id: str
    fecha_factura: str
    apta: bool = True
    estado: str = "PENDIENTE_CONCILIAR"
    reintento: bool = False
    backoff_futuro: bool = False
    bloqueado_por: str | None = None
    intentos_fallo: int = 0
    ultimo_backoff_horas: int | None = None
    conciliaciones: list[dict] = field(default_factory=list)


class SupabaseConciliacionMemoria:
    def __init__(self, *, conciliacion_automatica: bool = False):
        self.conciliacion_automatica = conciliacion_automatica
        self.facturas: dict[str, FacturaSimulada] = {}
        self.historial: list[tuple[str, str, dict]] = []
        self.rpcs: list[tuple[str, dict]] = []

    def anadir(self, factura_id: str, fecha: str, *, apta: bool = True) -> None:
        self.facturas[factura_id] = FacturaSimulada(factura_id, fecha, apta=apta)

    def rpc(self, nombre, payload):
        self.rpcs.append((nombre, copy.deepcopy(payload)))
        return _Respuesta(getattr(self, "_" + nombre)(payload))

    # R5 ---------------------------------------------------------------
    def _claim(self, worker, modo):
        candidatas = [
            f for f in self.facturas.values()
            if (modo == "MANUAL_ONE_SHOT" or self.conciliacion_automatica or f.reintento)
            and f.estado == "PENDIENTE_CONCILIAR" and f.apta
            and not f.backoff_futuro and f.bloqueado_por is None
        ]
        candidatas.sort(key=lambda f: (not f.reintento, f.fecha_factura, f.id))
        if not candidatas:
            return []
        f = candidatas[0]
        f.bloqueado_por = worker
        self.historial.append(("CONCILIACION_CLAIM", f.id, {"modo_ejecucion": modo, "actor": worker}))
        return [{"id": f.id, "documento_id": "d-" + f.id, "farmacia": "PIO",
                 "importe_total": "10.0000", "proveedor_id": None}]

    def _cf_reclamar_factura_conciliacion(self, payload):
        return self._claim(payload["p_worker_id"], "AUTOMATICO")

    def _cf_reclamar_factura_conciliacion_manual_one_shot(self, payload):
        return self._claim(payload["p_worker_id"], "MANUAL_ONE_SHOT")

    def expirar_lock(self, factura_id):
        self.facturas[factura_id].bloqueado_por = None

    # R6 / R8 ----------------------------------------------------------
    def _cf_persistir_conciliacion(self, payload):
        f = self.facturas[payload["p_factura_id"]]
        worker, clave, disparador = payload["p_worker_id"], payload["p_idempotency_key"], payload["p_disparador"]
        if disparador not in {"AUTOMATICO", "MANUAL_ONE_SHOT"}:
            raise RuntimeError("DISPARADOR_CONCILIACION_NO_ADMITIDO")
        existente = next((c for c in f.conciliaciones if c["idempotency_key"] == clave), None)
        if existente is not None:
            liberado = f.bloqueado_por == worker
            if liberado:
                f.estado = "CONCILIADA" if existente["resultado"] == "CONCILIADA" else "PENDIENTE_CONCILIAR"
                f.bloqueado_por = None
                f.reintento = False
            self.historial.append(("CONCILIACION_REPLAY_IDEMPOTENTE", f.id, {"claim_liberado": liberado}))
            return existente["id"]
        if f.bloqueado_por != worker:
            raise RuntimeError("claim no pertenece al worker")
        modo = next((d["modo_ejecucion"] for e, i, d in reversed(self.historial)
                     if e == "CONCILIACION_CLAIM" and i == f.id and d["actor"] == worker), None)
        if modo != disparador:
            raise RuntimeError("DISPARADOR_NO_COINCIDE_CON_CLAIM")
        for c in f.conciliaciones:
            c["es_actual"] = False
        nueva = {"id": f"c-{f.id}-{len(f.conciliaciones) + 1}", "intento": len(f.conciliaciones) + 1,
                 "idempotency_key": clave, "disparador": disparador, "es_actual": True,
                 "resultado": payload["p_resultado"]["resultado"],
                 "detalles": len(payload["p_resultado"]["detalles"])}
        f.conciliaciones.append(nueva)
        f.estado = "CONCILIADA" if nueva["resultado"] == "CONCILIADA" else "PENDIENTE_CONCILIAR"
        f.bloqueado_por, f.reintento, f.intentos_fallo, f.backoff_futuro = None, False, 0, False
        self.historial.append(("CONCILIACION_PERSISTIDA", f.id, {"intento": nueva["intento"]}))
        return nueva["id"]

    # R7 ---------------------------------------------------------------
    def _cf_registrar_fallo_conciliacion(self, payload):
        f = self.facturas[payload["p_factura_id"]]
        if payload["p_clase_fallo"] not in {"DEFECTO_DOCUMENTO", "TRANSITORIO"}:
            raise RuntimeError("CLASE_FALLO_NO_ADMITIDA")
        if f.bloqueado_por != payload["p_worker_id"]:
            return False
        f.intentos_fallo = 1 if f.reintento else f.intentos_fallo + 1
        if f.intentos_fallo >= MAX_INTENTOS:
            f.estado, f.backoff_futuro, f.ultimo_backoff_horas = "REVISION_CONCILIACION", False, None
        else:
            f.estado, f.backoff_futuro = "PENDIENTE_CONCILIAR", True
            f.ultimo_backoff_horas = BACKOFF_HORAS[min(f.intentos_fallo, len(BACKOFF_HORAS)) - 1]
        f.bloqueado_por, f.reintento = None, False
        self.historial.append(("CONCILIACION_ERROR", f.id, {"intentos_fallo": f.intentos_fallo}))
        return True

    def avanzar_tiempo(self, factura_id):
        self.facturas[factura_id].backoff_futuro = False

    def solicitar_reintento(self, factura_id):
        """Equivale a cf_solicitar_reintento_conciliacion (no redefinida por la 18)."""
        f = self.facturas[factura_id]
        f.estado, f.reintento, f.backoff_futuro, f.bloqueado_por = "PENDIENTE_CONCILIAR", True, False, None

    def estado(self, factura_id):
        f = self.facturas[factura_id]
        return {"estado": f.estado, "intentos_fallo": f.intentos_fallo, "bloqueado": f.bloqueado_por is not None,
                "conciliaciones": len(f.conciliaciones), "backoff_horas": f.ultimo_backoff_horas}
