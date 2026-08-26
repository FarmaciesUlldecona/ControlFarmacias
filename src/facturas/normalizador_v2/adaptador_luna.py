from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from .contrato_luna import (
    CONTRATO_VERSION_V24, MODELO_LUNA, PROMPT_LUNA_V24, schema_luna_v24,
)

PRECIO_ENTRADA_MTOK = Decimal("1.00")
PRECIO_ENTRADA_CACHE_MTOK = Decimal("0.10")
PRECIO_SALIDA_MTOK = Decimal("6.00")


class ErrorLecturaLuna(RuntimeError):
    pass


class ErrorSalidaLuna(ErrorLecturaLuna):
    pass


@dataclass(frozen=True, slots=True)
class MetadataLuna:
    response_id: str
    modelo_solicitado: str
    modelo_utilizado: str
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    coste_usd: Decimal
    duracion_ms: int
    contrato_version: str = CONTRATO_VERSION_V24


@dataclass(frozen=True, slots=True)
class ResultadoLuna:
    facturas: tuple[dict[str, Any], ...]
    metadata: MetadataLuna


def _tipo_correcto(valor: Any, esperado: str) -> bool:
    if esperado == "null":
        return valor is None
    if esperado == "object":
        return isinstance(valor, dict)
    if esperado == "array":
        return isinstance(valor, list)
    if esperado == "string":
        return isinstance(valor, str)
    if esperado == "boolean":
        return isinstance(valor, bool)
    if esperado == "integer":
        return isinstance(valor, int) and not isinstance(valor, bool)
    if esperado == "number":
        return isinstance(valor, (int, Decimal)) and not isinstance(valor, bool)
    return False


def _validar_schema(valor: Any, schema: dict, ruta: str = "$") -> None:
    if "anyOf" in schema:
        errores = []
        for opcion in schema["anyOf"]:
            try:
                _validar_schema(valor, opcion, ruta)
                return
            except ErrorSalidaLuna as exc:
                errores.append(str(exc))
        raise ErrorSalidaLuna(f"{ruta}: no cumple ninguna alternativa")
    tipos = schema.get("type")
    if isinstance(tipos, list):
        if not any(_tipo_correcto(valor, tipo) for tipo in tipos):
            raise ErrorSalidaLuna(f"{ruta}: tipo invalido")
    elif tipos and not _tipo_correcto(valor, tipos):
        raise ErrorSalidaLuna(f"{ruta}: se esperaba {tipos}")
    if "enum" in schema and valor not in schema["enum"]:
        raise ErrorSalidaLuna(f"{ruta}: valor fuera del enum")
    if isinstance(valor, int) and "minimum" in schema and valor < schema["minimum"]:
        raise ErrorSalidaLuna(f"{ruta}: menor que el minimo")
    if isinstance(valor, dict):
        requeridos = set(schema.get("required", []))
        faltantes = requeridos - set(valor)
        if faltantes:
            raise ErrorSalidaLuna(f"{ruta}: faltan campos {sorted(faltantes)}")
        if schema.get("additionalProperties") is False:
            extras = set(valor) - set(schema.get("properties", {}))
            if extras:
                raise ErrorSalidaLuna(f"{ruta}: campos extra {sorted(extras)}")
        for clave, contenido in valor.items():
            if clave in schema.get("properties", {}):
                _validar_schema(contenido, schema["properties"][clave], f"{ruta}.{clave}")
    if isinstance(valor, list) and "items" in schema:
        for indice, elemento in enumerate(valor):
            _validar_schema(elemento, schema["items"], f"{ruta}[{indice}]")
    if isinstance(valor, str) and "minLength" in schema and len(valor) < schema["minLength"]:
        raise ErrorSalidaLuna(f"{ruta}: texto mas corto que el minimo")


def _usage(response: Any) -> tuple[int, int, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0, 0
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump(mode="json", exclude_none=True)
    elif not isinstance(usage, dict):
        usage = vars(usage)
    detalles = usage.get("input_tokens_details") or {}
    if not isinstance(detalles, dict):
        detalles = vars(detalles)
    return int(usage.get("input_tokens", 0)), int(detalles.get("cached_tokens", 0)), int(usage.get("output_tokens", 0))


def calcular_coste(input_tokens: int, cached_tokens: int, output_tokens: int) -> Decimal:
    coste = (Decimal(input_tokens - cached_tokens) * PRECIO_ENTRADA_MTOK + Decimal(cached_tokens) * PRECIO_ENTRADA_CACHE_MTOK + Decimal(output_tokens) * PRECIO_SALIDA_MTOK) / Decimal(1_000_000)
    return coste.quantize(Decimal("0.00000001"))


class AdaptadorLuna:
    def __init__(self, *, cliente: Any | None = None, timeout: float = 600.0, reloj: Callable[[], float] = time.perf_counter):
        self._cliente = cliente
        self.timeout = timeout
        self._reloj = reloj

    def _cliente_efectivo(self):
        if self._cliente is not None:
            return self._cliente
        from openai import OpenAI
        self._cliente = OpenAI(max_retries=0, timeout=self.timeout)
        return self._cliente

    def extraer(self, pdf: str | Path) -> ResultadoLuna:
        ruta = Path(pdf)
        contenido = ruta.read_bytes()
        nombre_neutro = f"documento_{hashlib.sha256(contenido).hexdigest()[:12]}.pdf"
        data_url = "data:application/pdf;base64," + base64.b64encode(contenido).decode("ascii")
        inicio = self._reloj()
        try:
            response = self._cliente_efectivo().responses.create(
                model=MODELO_LUNA,
                reasoning={"effort": "medium"},
                max_output_tokens=32768,
                store=False,
                input=[
                    {"role": "system", "content": [{"type": "input_text", "text": PROMPT_LUNA_V24}]},
                    {"role": "user", "content": [{"type": "input_text", "text": "Procesa el documento adjunto."}, {"type": "input_file", "filename": nombre_neutro, "file_data": data_url}]},
                ],
                text={"format": {"type": "json_schema", "name": "facturas_v24_intermedio", "strict": True, "schema": schema_luna_v24()}},
            )
        except TimeoutError as exc:
            raise ErrorLecturaLuna("timeout en lectura Luna; no se reintento") from exc
        except Exception as exc:
            raise ErrorLecturaLuna(f"fallo de API {type(exc).__name__}; no se reintento") from exc
        duracion_ms = max(0, round((self._reloj() - inicio) * 1000))
        if getattr(response, "status", None) != "completed" or not getattr(response, "output_text", None):
            raise ErrorSalidaLuna("respuesta incompleta o sin salida estructurada")
        try:
            salida = json.loads(response.output_text, parse_float=Decimal)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ErrorSalidaLuna("JSON estructurado invalido") from exc
        _validar_schema(salida, schema_luna_v24())
        entrada, cache, salida_tokens = _usage(response)
        metadata = MetadataLuna(
            response_id=str(response.id), modelo_solicitado=MODELO_LUNA,
            modelo_utilizado=str(response.model), input_tokens=entrada, cached_tokens=cache,
            output_tokens=salida_tokens, coste_usd=calcular_coste(entrada, cache, salida_tokens),
            duracion_ms=duracion_ms,
            contrato_version=CONTRATO_VERSION_V24,
        )
        return ResultadoLuna(tuple(salida["facturas"]), metadata)
