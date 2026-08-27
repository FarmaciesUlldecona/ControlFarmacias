from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal
from typing import Any


ESTADOS = {"COINCIDE", "DIFIERE", "SOLO_LOCAL", "SOLO_PIPELINE", "NO_COMPARABLE"}


def comparar_pipeline_local(resultado_oficial: Any, resultado_local: Any) -> dict[str, Any]:
    oficiales = _oficiales(resultado_oficial)
    filas_locales = list(resultado_local.albaranes)
    for factura in resultado_local.facturas:
        filas_locales.extend(factura["albaranes"])
    locales = [_fila_local(fila, i) for i, fila in enumerate(filas_locales)]
    conteo_o = Counter(f["numero"] for f in oficiales)
    conteo_l = Counter(f["numero"] for f in locales)
    numeros = sorted(set(conteo_o) | set(conteo_l), key=lambda value: (value is None, value or ""))
    filas: list[dict[str, Any]] = []
    for numero in numeros:
        grupo_o = [f for f in oficiales if f["numero"] == numero]
        grupo_l = [f for f in locales if f["numero"] == numero]
        if numero is None or len(grupo_o) > 1 or len(grupo_l) > 1:
            filas.append({"numero": numero, "estado": "NO_COMPARABLE", "pipeline": grupo_o, "local": grupo_l, "campos_distintos": []})
        elif not grupo_o:
            filas.append({"numero": numero, "estado": "SOLO_LOCAL", "pipeline": None, "local": grupo_l[0], "campos_distintos": []})
        elif not grupo_l:
            filas.append({"numero": numero, "estado": "SOLO_PIPELINE", "pipeline": grupo_o[0], "local": None, "campos_distintos": []})
        else:
            campos = [campo for campo in ("fecha", "base", "total", "tipo_pedido", "sentido") if grupo_o[0][campo] != grupo_l[0][campo]]
            filas.append({"numero": numero, "estado": "DIFIERE" if campos else "COINCIDE", "pipeline": grupo_o[0], "local": grupo_l[0], "campos_distintos": campos})
    resumen = {estado: sum(1 for fila in filas if fila["estado"] == estado) for estado in sorted(ESTADOS)}
    campos_distintos = Counter(campo for fila in filas for campo in fila["campos_distintos"])
    return {
        "albaranes_pipeline": len(oficiales),
        "albaranes_local": len(locales),
        "resumen": resumen,
        "campos_distintos": dict(sorted(campos_distintos.items())),
        "filas": filas,
    }


def _valor(documentado: Any) -> Any:
    return None if documentado is None else documentado.valor


def _fecha(valor: Any) -> str | None:
    if valor is None:
        return None
    if hasattr(valor, "iso"):
        valor = valor.iso or valor.literal
    if isinstance(valor, date):
        return valor.isoformat()
    texto = str(valor).strip()
    for sep in (".", "/", "-"):
        partes = texto.split(sep)
        if len(partes) == 3 and len(partes[0]) <= 2 and len(partes[2]) == 4:
            return f"{partes[2]}-{partes[1].zfill(2)}-{partes[0].zfill(2)}"
    return texto


def _decimal(valor: Any) -> str | None:
    if valor is None:
        return None
    return str(Decimal(str(valor)).quantize(Decimal("0.01")))


def _oficiales(documento: Any) -> list[dict[str, Any]]:
    salida = []
    for factura in getattr(documento, "facturas", ()):
        for indice, fila in enumerate(factura.albaranes):
            salida.append({
                "indice": indice,
                "numero": str(_valor(fila.numero)),
                "fecha": _fecha(_valor(fila.fecha)),
                "base": _decimal(_valor(fila.importe_base)),
                "total": _decimal(_valor(fila.importe_total)),
                "tipo_pedido": _valor(fila.tipo_pedido),
                "sentido": fila.sentido.value if fila.sentido is not None else None,
            })
    return salida


def _fila_local(fila: Any, indice: int) -> dict[str, Any]:
    base = sum((Decimal(str(v)) for v in fila.bases), Decimal("0")) if fila.bases else None
    return {
        "indice": indice,
        "numero": str(fila.numero_albaran),
        "fecha": _fecha(fila.fecha),
        "base": _decimal(base),
        "total": _decimal(fila.total),
        "tipo_pedido": fila.tipo_pedido,
        "sentido": fila.sentido,
    }
