"""Calculo local en memoria de la composicion economica de 08009277."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.servicio import MotorDocumentoLocal


PDF = ROOT / "pruebas/facturas/documentos/2o_gold_standard/ALLIANCE VTO 30.9-6.10-6.11 PIO.pdf"
SHA = "7b806565a4f09e182c5ec9d75b40b959fd39c4af86da77b7a8cb745c6e1192b2"
OBJETIVOS = {"08P10588", "08C61794", "08P10623", "08Z34777"}


def valor(campo) -> Decimal:
    return Decimal(str(campo["valor"]))


def main() -> None:
    assert hashlib.sha256(PDF.read_bytes()).hexdigest() == SHA
    documento = MotorDocumentoLocal(BackendPdfium()).extraer(PDF)
    factura = next(item for item in documento.facturas if item["segmento"]["identidad"] == "08009277")
    grupos = defaultdict(lambda: {"cantidad": 0, "base": Decimal("0"), "total": Decimal("0"), "numeros": []})
    objetivos = {}
    for albaran in factura["albaranes"]:
        sentido = albaran["sentido"]["valor"]
        tipo = albaran["tipo_pedido"]["valor"]
        numero = albaran["numero_albaran"]["valor"]
        clave = (sentido, tipo)
        grupos[clave]["cantidad"] += 1
        grupos[clave]["base"] += valor(albaran["base"])
        grupos[clave]["total"] += valor(albaran["total"])
        grupos[clave]["numeros"].append(numero)
        if numero in OBJETIVOS:
            objetivos[numero] = albaran
    movimientos = [
        {
            "descripcion": item["descripcion_literal"]["valor"],
            "sentido": item["sentido"]["valor"] if isinstance(item.get("sentido"), dict) else item.get("sentido"),
            "base": valor(item["base"]) if item.get("base") else None,
            "importe": valor(item["importe"]) if item.get("importe") else None,
        }
        for item in factura["movimientos"]
    ]
    print(json.dumps({
        "total_factura": str(valor(factura["cabecera"]["importe_total"])),
        "grupos": {
            f"{sentido}|{tipo}": {
                "cantidad": datos["cantidad"],
                "base": str(datos["base"]),
                "total": str(datos["total"]),
                "numeros": datos["numeros"],
            }
            for (sentido, tipo), datos in grupos.items()
        },
        "objetivos": objetivos,
        "movimientos_independientes": movimientos,
        "relaciones_documentales": factura.get("relaciones_documentales", []),
    }, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
