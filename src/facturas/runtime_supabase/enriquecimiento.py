"""R12 (Hito 2AZ): enriquecimiento de facturas ya persistidas (camino propio, NO reprocesado).

Añade a una factura NO conciliada los albaranes y movimientos que una version
anterior del extractor no promovio y rellena importes de vencimiento NULL con el
valor demostrado por R14. Nunca modifica ni borra filas existentes ni importes de
la factura. La unica escritura es la RPC transaccional ``cf_enriquecer_factura``
(migracion 20), que revalida identidad, documento, SHA, estado e idempotencia.
No crea clientes ni se ejecuta al importarse.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from src.facturas.completitud_documental import validar_documento_antes_de_persistir

from .conciliacion import normalizar_numero_albaran
from .modelos import DocumentoTrabajo


def _valor(campo):
    return campo.get("valor") if isinstance(campo, dict) else None


def _cif(valor) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(valor or "").upper())


def _fecha_iso(campo) -> str | None:
    valor = _valor(campo)
    return valor.get("iso") if isinstance(valor, dict) else valor


def _importe(valor) -> Decimal | None:
    return None if valor in (None, "") else Decimal(str(valor)).quantize(Decimal("0.0001"))


def _clave_movimiento(descripcion, sentido, importe) -> tuple:
    return (str(descripcion or "").strip().upper(), sentido, _importe(importe))


def construir_enriquecimiento(datos: dict[str, Any], documento_normalizado: dict[str, Any]) -> dict[str, Any]:
    """Payload de ``cf_enriquecer_factura``. Pura: falla cerrado con ValueError."""
    factura, documento = datos["factura"], datos["documento"]
    persistida = factura.get("datos_extraidos") or {}
    clave = persistida.get("identidad_economica_clave")
    if not clave:
        raise ValueError("IDENTIDAD_PERSISTIDA_AUSENTE")
    candidatas = [f for f in documento_normalizado.get("facturas", []) if f.get("identidad_economica_clave") == clave]
    if len(candidatas) != 1:
        raise ValueError("FACTURA_NO_LOCALIZADA_EN_EXTRACCION")
    nueva = candidatas[0]
    cif_persistido = _cif(factura.get("proveedor_cif") or _valor((persistida.get("proveedor") or {}).get("nif")))
    identidad = {
        "numero_factura": _valor(nueva.get("numero_factura")),
        "fecha_factura": _fecha_iso(nueva.get("fecha_factura")),
        "importe_total": str(_importe(_valor((nueva.get("totales") or {}).get("total")))),
        "proveedor_cif": _cif(_valor((nueva.get("proveedor") or {}).get("nif"))),
        "identidad_economica_clave": clave,
    }
    for campo, persistido in (("numero_factura", factura.get("numero_factura")),
                              ("fecha_factura", str(factura.get("fecha_factura"))),
                              ("importe_total", str(_importe(factura.get("importe_total")))),
                              ("proveedor_cif", cif_persistido)):
        if identidad[campo] != persistido:
            raise ValueError(f"IDENTIDAD_NO_COINCIDE:{campo}")

    existentes = {normalizar_numero_albaran(a.get("numero_albaran")) for a in datos.get("albaranes", [])}
    albaranes = [a for a in nueva.get("albaranes", []) if normalizar_numero_albaran(_valor(a.get("numero"))) not in existentes]

    movimientos = []
    if persistida.get("naturaleza_principal") == "MIXTA":
        presentes = {_clave_movimiento(m.get("descripcion_literal"), m.get("sentido"), m.get("importe"))
                     for m in datos.get("movimientos", [])}
        movimientos = [m for m in nueva.get("movimientos_comerciales", [])
                       if _clave_movimiento(_valor(m.get("descripcion_literal")), m.get("sentido"),
                                            _valor(m.get("importe"))) not in presentes]

    sin_importe = {_fecha_iso(v.get("fecha")) for v in persistida.get("vencimientos", []) if v.get("importe") is None}
    vencimientos = [{"fecha": v["fecha"], "importe": v["importe"]} for v in nueva.get("vencimientos", [])
                    if v.get("importe") is not None and _fecha_iso(v.get("fecha")) in sin_importe]

    if not albaranes and not movimientos and not vencimientos:
        raise ValueError("SIN_FILAS_NUEVAS")
    return {
        "documento_id": documento["id"],
        "archivo_hash": documento["archivo_hash"],
        "normalizador_version": (documento_normalizado.get("metadata_tecnica") or {}).get("version_normalizador"),
        "identidad": identidad,
        "albaranes": albaranes,
        "movimientos": movimientos,
        "vencimientos": vencimientos,
    }


def clave_idempotente_enriquecimiento(factura_id: str, payload: dict[str, Any]) -> str:
    canonico = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return f"enriquecimiento:{factura_id}:{hashlib.sha256(canonico.encode()).hexdigest()}"


@dataclass(slots=True)
class WorkerEnriquecimiento:
    """Enriquece UNA factura indicada explicitamente (uso manual one-shot)."""

    repositorio: Any
    materializar_pdf: Callable[[DocumentoTrabajo], Path]
    extractor: Any
    worker_id: str
    campos_requeridos: frozenset[str]
    campo_documento: str

    def ejecutar(self, factura_id: str) -> dict[str, Any]:
        datos = self.repositorio.datos_para_enriquecer(factura_id)
        factura, documento = datos["factura"], datos["documento"]
        if factura.get("estado_conciliacion_cf") != "PENDIENTE_CONCILIAR":
            raise ValueError("FACTURA_NO_PENDIENTE_DE_CONCILIAR")
        trabajo = DocumentoTrabajo(
            documento_id=str(documento["id"]), archivo_ruta=str(documento["archivo_ruta"]),
            archivo_nombre=str(documento["archivo_nombre"]), farmacia=str(documento["farmacia"]))
        ruta = self.materializar_pdf(trabajo)  # verifica el SHA registrado
        etapa = self.extractor.extraer(ruta, self.campos_requeridos)
        if etapa.provenance.get("motivo") != "AUTORIZADO":
            raise ValueError(f"EXTRACCION_NO_AUTORIZADA:{etapa.provenance.get('motivo')}")
        normalizado = etapa.valores[self.campo_documento]
        validar_documento_antes_de_persistir(trabajo.farmacia, normalizado)
        payload = construir_enriquecimiento(datos, normalizado)
        clave = clave_idempotente_enriquecimiento(factura_id, payload)
        respuesta = self.repositorio.enriquecer_factura(factura_id, self.worker_id, clave, payload)
        return {"factura_id": factura_id, "idempotency_key": clave, "albaranes": len(payload["albaranes"]),
                "movimientos": len(payload["movimientos"]), "vencimientos": len(payload["vencimientos"]),
                "respuesta": respuesta}
