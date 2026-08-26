from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.facturas.normalizador_v2.adaptador_luna import AdaptadorLuna, ErrorLecturaLuna, ErrorSalidaLuna
from src.facturas.normalizador_v2.contrato_luna import MODELO_LUNA, PROMPT_B_SHA256, SCHEMA_B_SHA256


def _cabecera(valor, literal=None):
    if valor is None:
        return None
    literal = str(valor) if literal is None else literal
    return {
        "valor": valor,
        "literal": literal,
        "pagina": 1,
        "contexto_literal": literal,
        "span_contexto": {"inicio": 0, "fin": len(literal)},
    }


def factura(numero="F-1"):
    return {
        "tipo_documento": _cabecera("Factura"),
        "naturaleza_principal": "MERCANCIA",
        "requiere_conciliacion_albaranes": True,
        "pagina_inicio": 1,
        "pagina_fin": 1,
        "proveedor": {
            "nombre": _cabecera("Proveedor"),
            "nif": None,
            "direccion": None,
        },
        "numero_factura": _cabecera(numero),
        "fecha_factura": _cabecera("14/08/2026"),
        "base_imponible_total": _cabecera(100, "100"),
        "iva_total": _cabecera(21, "21"),
        "recargo_equivalencia_total": _cabecera(0, "0"),
        "otros_total": None,
        "importe_total": _cabecera(121, "121"),
        "moneda": _cabecera("EUR"),
        "vencimientos": [],
        "impuestos": [],
        "albaranes": [],
        "movimientos_comerciales": [],
        "destinatario": None,
        "forma_pago": None,
        "referencias_documentales": [],
        "discrepancias_documentales": [],
        "estructuras_documentales": [],
        "evidencias": [],
    }


class Cliente:
    def __init__(self, salida=None, error=None):
        self.salida, self.error, self.kwargs = salida, error, None
        self.responses = self

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(id="resp_1", model=MODELO_LUNA, status="completed", output_text=json.dumps(self.salida), usage={"input_tokens": 1000, "input_tokens_details": {"cached_tokens": 100}, "output_tokens": 500})


@pytest.fixture
def pdf(tmp_path: Path):
    ruta = tmp_path / "nombre-no-evidencia.pdf"
    ruta.write_bytes(b"%PDF-mock")
    return ruta


@pytest.mark.parametrize("cantidad", [0, 1, 3])
def test_extrae_cero_una_o_n_facturas_con_nombre_neutro(pdf, cantidad):
    cliente = Cliente({"facturas": [factura(f"F-{i}") for i in range(cantidad)]})
    resultado = AdaptadorLuna(cliente=cliente, reloj=iter([1.0, 1.25]).__next__).extraer(pdf)
    assert len(resultado.facturas) == cantidad
    assert resultado.metadata.response_id == "resp_1"
    assert resultado.metadata.input_tokens == 1000 and str(resultado.metadata.coste_usd) == "0.00391000"
    archivo = cliente.kwargs["input"][1]["content"][1]["filename"]
    assert archivo.startswith("documento_") and "nombre-no-evidencia" not in archivo
    assert cliente.kwargs["model"] == MODELO_LUNA and cliente.kwargs["text"]["format"]["strict"] is True


def test_salida_invalida_se_rechaza(pdf):
    with pytest.raises(ErrorSalidaLuna):
        AdaptadorLuna(cliente=Cliente({"facturas": [{"numero_factura": "incompleta"}]})).extraer(pdf)


@pytest.mark.parametrize("error,texto", [(RuntimeError("api"), "fallo de API"), (TimeoutError(), "timeout")])
def test_api_error_y_timeout_sin_reintento(pdf, error, texto):
    cliente = Cliente(error=error)
    with pytest.raises(ErrorLecturaLuna, match=texto):
        AdaptadorLuna(cliente=cliente, timeout=12).extraer(pdf)


def test_contrato_referencia_baseline_b_y_sin_cliente_al_importar():
    assert len(PROMPT_B_SHA256) == len(SCHEMA_B_SHA256) == 64
    assert MODELO_LUNA == "gpt-5.6-luna"
