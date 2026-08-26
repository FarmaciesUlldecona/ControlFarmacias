from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

from pypdf import PdfReader, PdfWriter

from .modelos import EstadoValidacion, FacturaNormalizada, NaturalezaPrincipal, ValorDocumentado, Vencimiento
from .multifactura import consolidar_facturas
from .validadores import clave_funcional, validar_factura

REGION_SPLITTER = "eu"
VERSION_SPLITTER = "pretrained-splitter-v1.5-2025-07-14"
VERSION_DECISOR = "normalizador-v2.splitter-selectivo.1"


@dataclass(frozen=True, slots=True)
class ConfiguracionSplitter:
    region: str = REGION_SPLITTER
    version: str = VERSION_SPLITTER
    max_invocaciones_por_pdf: int = 1
    max_segmentos: int = 30
    max_paginas_por_segmento: int = 30
    reintentos: int = 0
    timeout_segundos: float = 600.0


@dataclass(frozen=True, slots=True)
class SenalesSegundaLectura:
    naturaleza: NaturalezaPrincipal
    multipagina: bool = False
    tabla_multipagina: bool = False
    continuidad_tabla: bool = False
    filas_extraidas: int = 0
    identificadores_visibles: int = 0
    subtotal_no_explicado: bool = False
    diferencia_material_sin_movimientos: bool = False
    densidad_alta: bool = False
    formato_alliance_denso_demostrado: bool = False
    perdida_prefijo_compuesto_fedefarma: bool = False


@dataclass(frozen=True, slots=True)
class DecisionSplitter:
    activar: bool
    estado: EstadoValidacion
    senales_estructurales: tuple[str, ...]
    senales_incompletitud: tuple[str, ...]
    motivo: str
    regla_version: str = VERSION_DECISOR


@dataclass(frozen=True, slots=True)
class RangoSegmento:
    segmento_id: str
    pagina_inicio: int
    pagina_fin: int
    confianza: float | None = None

    @property
    def paginas(self) -> tuple[int, ...]:
        return tuple(range(self.pagina_inicio, self.pagina_fin + 1))


@dataclass(frozen=True, slots=True)
class SegmentoFisico:
    segmento_id: str
    ruta: Path
    paginas_originales: tuple[int, ...]


class ServicioSplitter(Protocol):
    def procesar(self, pdf: bytes, *, region: str, version: str, timeout: float) -> Iterable[RangoSegmento]: ...


class ErrorSplitter(RuntimeError):
    pass


def decidir_segunda_lectura(s: SenalesSegundaLectura) -> DecisionSplitter:
    compatible = s.naturaleza in (NaturalezaPrincipal.MERCANCIA, NaturalezaPrincipal.MIXTA)
    estructurales = []
    if s.tabla_multipagina:
        estructurales.append("tabla_multipagina")
    if s.continuidad_tabla:
        estructurales.append("continuidad_tabla")
    if s.identificadores_visibles > s.filas_extraidas:
        estructurales.append("conteo_visible_incompatible")
    if s.densidad_alta and s.multipagina:
        estructurales.append("densidad_multipagina")
    incompletitud = []
    if s.identificadores_visibles > s.filas_extraidas:
        incompletitud.append("filas_omitidas_frente_conteo_visible")
    if s.subtotal_no_explicado:
        incompletitud.append("subtotal_no_explicado")
    if s.diferencia_material_sin_movimientos:
        incompletitud.append("diferencia_material_sin_movimientos")
    formato_cerrado = s.formato_alliance_denso_demostrado and s.multipagina and s.densidad_alta
    activar = compatible and not s.perdida_prefijo_compuesto_fedefarma and ((bool(estructurales) and bool(incompletitud)) or formato_cerrado)
    if activar:
        motivo = "señales estructurales y de resultado incompleto combinadas" if incompletitud else "formato Alliance denso demostrado con multipagina y densidad"
        estado = EstadoValidacion.REQUIERE_SEGUNDA_LECTURA
    elif s.perdida_prefijo_compuesto_fedefarma:
        motivo, estado = "representacion de clave compuesta FEDEFARMA; no omision estructural", EstadoValidacion.REQUIERE_REVISION
    else:
        motivo, estado = "no se cumplen señales combinadas", EstadoValidacion.VALIDADA
    return DecisionSplitter(activar, estado, tuple(estructurales), tuple(incompletitud), motivo)


def validar_segmentos(segmentos: Iterable[RangoSegmento], total_paginas: int, config: ConfiguracionSplitter | None = None) -> tuple[RangoSegmento, ...]:
    config = config or ConfiguracionSplitter()
    salida = tuple(sorted(segmentos, key=lambda s: (s.pagina_inicio, s.pagina_fin, s.segmento_id)))
    if not salida or len(salida) > config.max_segmentos:
        raise ErrorSplitter("numero de segmentos fuera de limites")
    asignadas = []
    ids = set()
    for segmento in salida:
        if segmento.segmento_id in ids or segmento.pagina_inicio < 1 or segmento.pagina_fin < segmento.pagina_inicio:
            raise ErrorSplitter("segmento invalido o duplicado")
        if len(segmento.paginas) > config.max_paginas_por_segmento or segmento.pagina_fin > total_paginas:
            raise ErrorSplitter("segmento excede paginas o limites")
        ids.add(segmento.segmento_id)
        asignadas.extend(segmento.paginas)
    if asignadas != list(range(1, total_paginas + 1)):
        raise ErrorSplitter("segmentos no forman una cobertura contigua, completa y sin solapes")
    return salida


class SplitterSelectivo:
    def __init__(self, servicio: ServicioSplitter, config: ConfiguracionSplitter | None = None):
        self.servicio = servicio
        self.config = config or ConfiguracionSplitter()

    def segmentar(self, pdf: str | Path) -> tuple[RangoSegmento, ...]:
        ruta = Path(pdf)
        total_paginas = len(PdfReader(ruta).pages)
        try:
            candidatos = self.servicio.procesar(ruta.read_bytes(), region=self.config.region, version=self.config.version, timeout=self.config.timeout_segundos)
        except Exception as exc:
            raise ErrorSplitter(f"fallo splitter {type(exc).__name__}; sin reintento") from exc
        return validar_segmentos(candidatos, total_paginas, self.config)


def dividir_pdf(pdf: str | Path, segmentos: Iterable[RangoSegmento], destino: str | Path) -> tuple[SegmentoFisico, ...]:
    origen = Path(pdf)
    lector = PdfReader(origen)
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    salida = []
    for segmento in segmentos:
        escritor = PdfWriter()
        for pagina in segmento.paginas:
            escritor.add_page(lector.pages[pagina - 1])
        ruta = destino / f"{segmento.segmento_id}.pdf"
        with ruta.open("wb") as archivo:
            escritor.write(archivo)
        salida.append(SegmentoFisico(segmento.segmento_id, ruta, segmento.paginas))
    return tuple(salida)


def _unicos(items: Iterable[Any], clave) -> list[Any]:
    salida, vistas = [], set()
    for item in items:
        identidad = clave(item)
        if identidad not in vistas:
            vistas.add(identidad)
            salida.append(item)
    return salida


def _valor(valor: Any) -> Any:
    if valor is None:
        return None
    contenido = valor.valor
    if hasattr(contenido, "model_dump"):
        contenido = contenido.model_dump(mode="json")
    return json.dumps(contenido, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fecha_vencimiento(vencimiento: Any) -> str | None:
    if vencimiento.fecha is None:
        return None
    fecha = vencimiento.fecha.valor
    return fecha.iso.isoformat() if fecha.iso is not None else fecha.literal


def _union_documental(items: Iterable[Any], clave_identidad) -> list[Any]:
    """Conserva orden documental y solo colapsa identidades completas o copias exactas."""
    salida: list[Any] = []
    identidades_completas: set[tuple[Any, ...]] = set()
    exactos: set[str] = set()
    for item in items:
        exacto = item.json_estable()
        identidad = clave_identidad(item)
        completa = all(parte is not None for parte in identidad)
        if exacto in exactos or (completa and identidad in identidades_completas):
            continue
        salida.append(item)
        exactos.add(exacto)
        if completa:
            identidades_completas.add(identidad)
    return salida


def _evidencias_unicas(*valores: ValorDocumentado[Any] | None) -> list[Any]:
    salida, vistas = [], set()
    for valor in valores:
        if valor is None:
            continue
        for evidencia in valor.evidencia:
            clave = evidencia.json_estable()
            if clave not in vistas:
                vistas.add(clave)
                salida.append(evidencia)
    return salida


def _fusionar_valor(a: ValorDocumentado[Any] | None, b: ValorDocumentado[Any] | None) -> ValorDocumentado[Any] | None:
    if a is None:
        return b
    if b is None:
        return a
    return a.model_copy(update={"evidencia": _evidencias_unicas(a, b)})


def _ubicaciones_fila(valor: ValorDocumentado[Any] | None) -> set[tuple[Any, ...]]:
    firmas = set()
    if valor is None:
        return firmas
    for evidencia in valor.evidencia:
        ubicacion = evidencia.ubicacion or {}
        estructura = ubicacion.get("estructura_id")
        posicion = ubicacion.get("posicion")
        tramo = ubicacion.get("span_fila") or ubicacion.get("span_fila_inferido")
        if estructura is not None and (posicion is not None or tramo is not None):
            firmas.add((evidencia.pagina, estructura, json.dumps(posicion, sort_keys=True, default=str), json.dumps(tramo, sort_keys=True, default=str)))
    return firmas


def _ocurrencias_reales_distintas(a: Vencimiento, b: Vencimiento) -> bool:
    firmas_a = _ubicaciones_fila(a.fecha) | _ubicaciones_fila(a.importe) | _ubicaciones_fila(a.medio_pago)
    firmas_b = _ubicaciones_fila(b.fecha) | _ubicaciones_fila(b.importe) | _ubicaciones_fila(b.medio_pago)
    for fa in firmas_a:
        for fb in firmas_b:
            if fa[0] == fb[0] and fa[1] == fb[1] and fa != fb:
                return True
    return False


def _valor_compatible(a: ValorDocumentado[Any] | None, b: ValorDocumentado[Any] | None) -> bool:
    return a is None or b is None or _valor(a) == _valor(b)


def _evidencia_no_contradice(valor: ValorDocumentado[Any] | None) -> bool:
    if valor is None:
        return True
    esperado = str(valor.valor.literal if hasattr(valor.valor, "literal") else valor.valor).casefold()
    esperado = " ".join(esperado.split())
    return all(esperado in " ".join(e.literal.casefold().split()) for e in valor.evidencia)


def _vencimientos_compatibles(a: Vencimiento, b: Vencimiento) -> bool:
    if a.fecha is None or b.fecha is None or _fecha_vencimiento(a) != _fecha_vencimiento(b):
        return False
    campos = (a.fecha, a.importe, a.medio_pago, b.fecha, b.importe, b.medio_pago)
    return (
        _valor_compatible(a.importe, b.importe)
        and _valor_compatible(a.medio_pago, b.medio_pago)
        and all(_evidencia_no_contradice(valor) for valor in campos)
        and not _ocurrencias_reales_distintas(a, b)
    )


def _fusionar_vencimientos(items: Iterable[Vencimiento], *, source_sha: str) -> list[Vencimiento]:
    """Fusion semantica fail-closed dentro de una identidad documental ya emparejada."""
    salida: list[Vencimiento] = []
    for item in items:
        compatibles = [i for i, actual in enumerate(salida) if _vencimientos_compatibles(actual, item)]
        if len(compatibles) != 1:
            salida.append(item)
            continue
        indice = compatibles[0]
        actual = salida[indice]
        salida[indice] = actual.model_copy(update={
            "fecha": _fusionar_valor(actual.fecha, item.fecha),
            "importe": _fusionar_valor(actual.importe, item.importe),
            "medio_pago": _fusionar_valor(actual.medio_pago, item.medio_pago),
        })
    return salida


def _numero_identidad(factura: FacturaNormalizada) -> str | None:
    if factura.numero_factura is None:
        return None
    return " ".join(factura.numero_factura.valor.upper().split())


def _proveedor_identidad(factura: FacturaNormalizada) -> str | None:
    clave = clave_funcional(factura)
    return clave[0] if clave is not None else None


def _valor_fecha_factura(factura: FacturaNormalizada) -> str | None:
    if factura.fecha_factura is None:
        return None
    fecha = factura.fecha_factura.valor
    return fecha.iso.isoformat() if fecha.iso is not None else fecha.literal


def _apoyo_sin_contradiccion(a: FacturaNormalizada, b: FacturaNormalizada) -> bool:
    """Apoyo documental, nunca identidad: exige al menos una igualdad y ninguna contradicción."""
    pares = [
        (_valor_fecha_factura(a), _valor_fecha_factura(b)),
        (_valor(a.totales.total), _valor(b.totales.total)),
        (_valor(a.tipo_documento), _valor(b.tipo_documento)),
    ]
    comparables = [(x, y) for x, y in pares if x is not None and y is not None]
    if any(x != y for x, y in comparables):
        return False
    paginas_solapan = not (a.pagina_fin < b.pagina_inicio or b.pagina_fin < a.pagina_inicio)
    return paginas_solapan or any(x == y for x, y in comparables)


def _indice_emparejable(base: list[FacturaNormalizada], candidata: FacturaNormalizada) -> int | None:
    clave = clave_funcional(candidata)
    exactas = [i for i, factura in enumerate(base) if clave is not None and clave_funcional(factura) == clave]
    if len(exactas) == 1:
        return exactas[0]
    if exactas:
        return None

    numero = _numero_identidad(candidata)
    if numero is None:
        return None
    proveedor = _proveedor_identidad(candidata)
    auxiliares = []
    for i, factura in enumerate(base):
        if _numero_identidad(factura) != numero:
            continue
        proveedor_base = _proveedor_identidad(factura)
        # El apoyo solo opera si falta proveedor; nunca salva proveedores contradictorios.
        if proveedor is not None and proveedor_base is not None:
            continue
        if _apoyo_sin_contradiccion(factura, candidata):
            auxiliares.append(i)
    return auxiliares[0] if len(auxiliares) == 1 else None


def _preferir_primaria(primario: Any, segmentado: Any) -> Any:
    return primario if primario is not None else segmentado


def _consolidar_lecturas_legacy(
    primarias: Iterable[FacturaNormalizada], segmentadas: Iterable[FacturaNormalizada], *, source_sha: str | None = None,
) -> tuple[FacturaNormalizada, ...]:
    base = list(consolidar_facturas(primarias).facturas)
    sin_emparejar = []
    for candidata in segmentadas:
        indice = _indice_emparejable(base, candidata)
        if indice is None:
            sin_emparejar.append(candidata)
            continue
        primaria = base[indice]
        totales = primaria.totales.model_copy(update={
            nombre: _preferir_primaria(getattr(primaria.totales, nombre), getattr(candidata.totales, nombre))
            for nombre in ("moneda", "base_imponible", "iva", "recargo_equivalencia", "otros", "total")
        })
        actualizada = primaria.model_copy(update={
            "pagina_inicio": min(primaria.pagina_inicio, candidata.pagina_inicio),
            "pagina_fin": max(primaria.pagina_fin, candidata.pagina_fin),
            "proveedor": _preferir_primaria(primaria.proveedor, candidata.proveedor),
            "numero_factura": _preferir_primaria(primaria.numero_factura, candidata.numero_factura),
            "fecha_factura": _preferir_primaria(primaria.fecha_factura, candidata.fecha_factura),
            "tipo_documento": _preferir_primaria(primaria.tipo_documento, candidata.tipo_documento),
            "destinatario": _preferir_primaria(primaria.destinatario, candidata.destinatario),
            "forma_pago": _preferir_primaria(primaria.forma_pago, candidata.forma_pago),
            "totales": totales,
              "albaranes": _unicos([*primaria.albaranes, *candidata.albaranes], lambda a: (a.numero.valor, a.fecha.valor.literal if a.fecha else None, a.sentido)),
            "movimientos_comerciales": _unicos([*primaria.movimientos_comerciales, *candidata.movimientos_comerciales], lambda m: (m.descripcion_literal.valor, m.sentido, m.importe.valor if m.importe else None)),
            "referencias_documentales": _unicos([*primaria.referencias_documentales, *candidata.referencias_documentales], lambda r: (r.tipo, r.identificador.valor)),
            "vencimientos": (
                _fusionar_vencimientos([*primaria.vencimientos, *candidata.vencimientos], source_sha=source_sha)
                if source_sha
                else _union_documental(
                    [*primaria.vencimientos, *candidata.vencimientos],
                    lambda v: (_fecha_vencimiento(v), _valor(v.importe)),
                )
            ),
            "impuestos": _union_documental(
                [*primaria.impuestos, *candidata.impuestos],
                lambda i: (_valor(i.base), _valor(i.tipo_iva), _valor(i.cuota_iva), _valor(i.tipo_recargo_equivalencia), _valor(i.cuota_recargo_equivalencia)),
            ),
            "discrepancias_documentales": _union_documental(
                [*primaria.discrepancias_documentales, *candidata.discrepancias_documentales],
                lambda d: (d.tipo, d.descripcion, d.importe_diferencia),
            ),
        })
        evaluacion = validar_factura(actualizada)
        base[indice] = actualizada.model_copy(update={"estado_validacion": evaluacion.estado, "validaciones": list(evaluacion.validaciones), "discrepancias_documentales": list(evaluacion.discrepancias), "incidencias": list(evaluacion.incidencias)})
    return consolidar_facturas([*base, *sin_emparejar]).facturas


def consolidar_lecturas(
    primarias: Iterable[FacturaNormalizada], segmentadas: Iterable[FacturaNormalizada], *, source_sha: str | None = None,
) -> tuple[FacturaNormalizada, ...]:
    """Consolida representaciones documentales; conserva el modo legacy solo sin SHA."""
    primarias, segmentadas = tuple(primarias), tuple(segmentadas)
    if source_sha is None:
        return _consolidar_lecturas_legacy(primarias, segmentadas, source_sha=None)
    from .consolidacion_representaciones import RepresentacionFactura, consolidar_representaciones
    representaciones = [
        *(RepresentacionFactura(f, "lectura_primaria", source_sha) for f in primarias),
        *(RepresentacionFactura(f, "lectura_segmentada", source_sha) for f in segmentadas),
    ]
    return consolidar_representaciones(representaciones).facturas
