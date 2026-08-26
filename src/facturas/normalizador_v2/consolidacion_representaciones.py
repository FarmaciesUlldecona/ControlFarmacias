from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
import hashlib
import json
from typing import Any, Iterable

from pydantic import BaseModel

from .modelos import (
    EstadoValidacion, Evidencia, FacturaNormalizada, Incidencia, Severidad,
    ValorDocumentado,
)
from .validadores import validar_factura


class EstadoEquivalencia(StrEnum):
    MISMA_FACTURA_DEMOSTRADA = "MISMA_FACTURA_DEMOSTRADA"
    FACTURAS_DISTINTAS_DEMOSTRADAS = "FACTURAS_DISTINTAS_DEMOSTRADAS"
    EQUIVALENCIA_INSUFICIENTE = "EQUIVALENCIA_INSUFICIENTE"
    CONFLICTO_DOCUMENTAL = "CONFLICTO_DOCUMENTAL"


@dataclass(frozen=True)
class IdentidadRepresentacionDocumental:
    source_sha: str | None
    paginas: tuple[int, int]
    numero_factura: str | None
    fecha_factura: str | None
    importe_total: str | None
    proveedor_nif: str | None
    destinatario_nif: str | None
    evidencias: dict[str, tuple[dict[str, Any], ...]]


@dataclass(frozen=True)
class RepresentacionFactura:
    factura: FacturaNormalizada
    origen: str
    source_sha: str | None
    segmento_id: str | None = None


@dataclass(frozen=True)
class EvaluacionEquivalencia:
    estado: EstadoEquivalencia
    anclas_compartidas: tuple[str, ...]
    conflictos: tuple[str, ...]
    razones: tuple[str, ...]


@dataclass(frozen=True)
class GrupoFacturaDocumental:
    origenes: tuple[str, ...]
    identidades: tuple[IdentidadRepresentacionDocumental, ...]
    estado: EstadoEquivalencia
    evidencias: dict[str, tuple[dict[str, Any], ...]]
    conflictos: tuple[str, ...]
    factura_consolidada: FacturaNormalizada | None


@dataclass(frozen=True)
class ResultadoConsolidacionRepresentaciones:
    facturas: tuple[FacturaNormalizada, ...]
    grupos: tuple[GrupoFacturaDocumental, ...]
    consolidadas: int
    conflictos: tuple[str, ...]


def identidad_representacion(representacion: RepresentacionFactura) -> IdentidadRepresentacionDocumental:
    f = representacion.factura
    numero, ev_numero = _vd(f.numero_factura)
    fecha, ev_fecha = _fecha(f)
    total, ev_total = _vd(f.totales.total)
    proveedor, ev_proveedor = _vd(f.proveedor.nif if f.proveedor else None)
    destino, ev_destino = _vd(f.destinatario.nif if f.destinatario else None)
    evidencias = {
        campo: tuple(e.model_dump(mode="json") for e in valores)
        for campo, valores in {
            "numero_factura": ev_numero, "fecha_factura": ev_fecha,
            "importe_total": ev_total, "proveedor_nif": ev_proveedor,
            "destinatario_nif": ev_destino,
        }.items() if valores
    }
    evidencias["paginas"] = ({"inicio": f.pagina_inicio, "fin": f.pagina_fin, "origen": representacion.origen},)
    if representacion.source_sha:
        evidencias["source_sha"] = ({"sha": representacion.source_sha, "origen": "CONTENIDO_PDF"},)
    return IdentidadRepresentacionDocumental(
        representacion.source_sha, (f.pagina_inicio, f.pagina_fin),
        str(numero) if numero is not None else None, fecha,
        _normalizar_decimal(total), str(proveedor) if proveedor is not None else None,
        str(destino) if destino is not None else None, evidencias,
    )


def evaluar_equivalencia(a: RepresentacionFactura, b: RepresentacionFactura) -> EvaluacionEquivalencia:
    ia, ib = identidad_representacion(a), identidad_representacion(b)
    if not ia.source_sha or not ib.source_sha or not ia.numero_factura or not ib.numero_factura:
        return EvaluacionEquivalencia(EstadoEquivalencia.EQUIVALENCIA_INSUFICIENTE, (), (), ("FALTA_SHA_O_NUMERO_DOCUMENTADO",))
    if ia.source_sha != ib.source_sha:
        return EvaluacionEquivalencia(EstadoEquivalencia.FACTURAS_DISTINTAS_DEMOSTRADAS, (), (), ("SHA_DOCUMENTAL_DISTINTO",))
    if ia.numero_factura != ib.numero_factura:
        return EvaluacionEquivalencia(EstadoEquivalencia.FACTURAS_DISTINTAS_DEMOSTRADAS, (), (), ("NUMERO_FACTURA_DISTINTO",))
    if not _solapan(ia.paginas, ib.paginas):
        return EvaluacionEquivalencia(EstadoEquivalencia.FACTURAS_DISTINTAS_DEMOSTRADAS, (), (), ("PAGINAS_NO_SOLAPADAS",))
    compartidas = ["source_sha", "numero_factura", "paginas_solapadas"]
    conflictos = []
    apoyos = 0
    for campo in ("fecha_factura", "importe_total", "proveedor_nif", "destinatario_nif"):
        va, vb = getattr(ia, campo), getattr(ib, campo)
        if va is None or vb is None:
            continue
        if va != vb:
            conflictos.append(campo)
        else:
            compartidas.append(campo)
            apoyos += 1
    if conflictos:
        return EvaluacionEquivalencia(EstadoEquivalencia.CONFLICTO_DOCUMENTAL, tuple(compartidas), tuple(conflictos), ("ANCLAS_DOCUMENTALES_CONTRADICTORIAS",))
    if apoyos < 2:
        return EvaluacionEquivalencia(EstadoEquivalencia.EQUIVALENCIA_INSUFICIENTE, tuple(compartidas), (), ("MENOS_DE_DOS_ANCLAS_SECUNDARIAS_COMPARTIDAS",))
    return EvaluacionEquivalencia(EstadoEquivalencia.MISMA_FACTURA_DEMOSTRADA, tuple(compartidas), (), ("IDENTIDAD_FISICA_DEMOSTRADA",))


def consolidar_representaciones(representaciones: Iterable[RepresentacionFactura]) -> ResultadoConsolidacionRepresentaciones:
    reps = sorted(representaciones, key=lambda r: _hash_factura(r.factura))
    pendientes = set(range(len(reps)))
    grupos: list[GrupoFacturaDocumental] = []
    facturas: list[FacturaNormalizada] = []
    conflictos_globales: list[str] = []
    consolidadas = 0
    while pendientes:
        inicial = min(pendientes)
        componente = {inicial}
        cambio = True
        while cambio:
            cambio = False
            for i in list(pendientes - componente):
                if any(_mismo_ambito_candidato(reps[i], reps[j]) for j in componente):
                    componente.add(i); cambio = True
        pendientes -= componente
        miembros = [reps[i] for i in sorted(componente)]
        pares = [evaluar_equivalencia(miembros[i], miembros[j]) for i in range(len(miembros)) for j in range(i + 1, len(miembros))]
        if len(miembros) > 1 and any(p.estado == EstadoEquivalencia.CONFLICTO_DOCUMENTAL for p in pares):
            estado_grupo = EstadoEquivalencia.CONFLICTO_DOCUMENTAL
        elif len(miembros) > 1 and all(p.estado == EstadoEquivalencia.MISMA_FACTURA_DEMOSTRADA for p in pares):
            estado_grupo = EstadoEquivalencia.MISMA_FACTURA_DEMOSTRADA
        else:
            estado_grupo = EstadoEquivalencia.EQUIVALENCIA_INSUFICIENTE
        if len(miembros) == 1:
            factura = miembros[0].factura
            grupos.append(_grupo(miembros, estado_grupo, (), factura))
            facturas.append(factura)
            continue
        if estado_grupo != EstadoEquivalencia.MISMA_FACTURA_DEMOSTRADA:
            codigo = ("CONFLICTO_ENTRE_REPRESENTACIONES" if estado_grupo == EstadoEquivalencia.CONFLICTO_DOCUMENTAL
                      else "EQUIVALENCIA_DOCUMENTAL_INSUFICIENTE")
            conflictos_pares = sorted({campo for par in pares for campo in par.conflictos})
            conflictos_globales.extend(conflictos_pares)
            for miembro in miembros:
                factura = _incidencia(miembro.factura, codigo, True)
                grupos.append(_grupo([miembro], estado_grupo, tuple(conflictos_pares), factura)); facturas.append(factura)
            continue
        anotadas = [_anotar_modelo(m.factura, m.origen) for m in miembros]
        consolidada, conflictos = _fusionar_facturas(anotadas, [identidad_representacion(m) for m in miembros])
        if conflictos:
            conflictos_globales.extend(conflictos)
            for miembro in miembros:
                factura = _incidencia(miembro.factura, "CONFLICTO_ENTRE_REPRESENTACIONES", True)
                grupos.append(_grupo([miembro], EstadoEquivalencia.CONFLICTO_DOCUMENTAL, tuple(conflictos), factura)); facturas.append(factura)
            continue
        consolidada = _incidencia(consolidada, "REPRESENTACIONES_CONSOLIDADAS", False, origenes=[m.origen for m in miembros])
        evaluacion = validar_factura(consolidada)
        consolidada = consolidada.model_copy(update={"estado_validacion": evaluacion.estado, "validaciones": list(evaluacion.validaciones), "discrepancias_documentales": list(evaluacion.discrepancias), "incidencias": list(evaluacion.incidencias)})
        grupos.append(_grupo(miembros, EstadoEquivalencia.MISMA_FACTURA_DEMOSTRADA, (), consolidada))
        facturas.append(consolidada); consolidadas += len(miembros) - 1
    facturas.sort(key=lambda f: (f.pagina_inicio, f.pagina_fin, f.factura_id))
    return ResultadoConsolidacionRepresentaciones(tuple(facturas), tuple(grupos), consolidadas, tuple(sorted(set(conflictos_globales))))


def _fusionar_facturas(facturas: list[FacturaNormalizada], identidades: list[IdentidadRepresentacionDocumental]):
    conflictos: list[str] = []
    base = facturas[0]
    for otra in facturas[1:]:
        updates = {}
        for campo in ("tipo_documento", "proveedor", "numero_factura", "fecha_factura", "destinatario", "totales", "forma_pago"):
            updates[campo] = _fusionar_any(getattr(base, campo), getattr(otra, campo), campo, conflictos)
        for campo in ("albaranes", "movimientos_comerciales", "impuestos", "referencias_documentales", "derivaciones", "discrepancias_documentales"):
            updates[campo] = _fusionar_coleccion([*getattr(base, campo), *getattr(otra, campo)], campo, conflictos)
        # Esta coleccion ya dispone de una regla multipagina conservadora: identidad
        # fisica demostrada, atributos compatibles y conservacion de procedencias.
        from .splitter import _fusionar_vencimientos
        updates["vencimientos"] = [
            _normalizar_evidencias_modelo(vencimiento)
            for vencimiento in _fusionar_vencimientos(
                [*base.vencimientos, *otra.vencimientos], source_sha=identidades[0].source_sha,
            )
        ]
        if base.naturaleza_principal != otra.naturaleza_principal:
            conflictos.append("naturaleza_principal")
        updates["requiere_conciliacion_albaranes"] = base.requiere_conciliacion_albaranes or otra.requiere_conciliacion_albaranes
        updates["pagina_inicio"] = min(base.pagina_inicio, otra.pagina_inicio)
        updates["pagina_fin"] = max(base.pagina_fin, otra.pagina_fin)
        updates["incidencias"] = _fusionar_coleccion([*base.incidencias, *otra.incidencias], "incidencias", conflictos)
        base = base.model_copy(update=updates)
    identidad = identidades[0]
    canon = json.dumps({"sha": identidad.source_sha, "paginas": identidad.paginas, "numero": identidad.numero_factura, "fecha": identidad.fecha_factura, "total": identidad.importe_total}, sort_keys=True, separators=(",", ":"))
    return base.model_copy(update={"factura_id": "fac_" + hashlib.sha256(canon.encode()).hexdigest()[:24]}), sorted(set(conflictos))


def _fusionar_any(a, b, path: str, conflictos: list[str]):
    if a is None: return b
    if b is None: return a
    if isinstance(a, ValorDocumentado) and isinstance(b, ValorDocumentado):
        if _canon(a.valor) != _canon(b.valor):
            conflictos.append(path); return a
        evidencias = _fusionar_evidencias([*a.evidencia, *b.evidencia])
        literal = min((a.literal, b.literal), key=lambda v: (len(v), v))
        return a.model_copy(update={"literal": literal, "evidencia": evidencias})
    if isinstance(a, BaseModel) and isinstance(b, BaseModel) and type(a) is type(b):
        updates = {nombre: _fusionar_any(getattr(a, nombre), getattr(b, nombre), f"{path}.{nombre}", conflictos) for nombre in type(a).model_fields}
        return a.model_copy(update=updates)
    if a == b: return a
    conflictos.append(path)
    return a


def _fusionar_coleccion(items: list[Any], path: str, conflictos: list[str]) -> list[Any]:
    salida: list[Any] = []
    for item in items:
        clave = _semantica(item)
        firmas = _firmas_evidencia(item)
        compatibles = [i for i, actual in enumerate(salida) if _semantica(actual) == clave and firmas and (_firmas_evidencia(actual) & firmas)]
        if len(compatibles) == 1:
            salida[compatibles[0]] = _fusionar_any(salida[compatibles[0]], item, f"{path}[]", conflictos)
        elif not any(_canon(actual) == _canon(item) for actual in salida):
            salida.append(item)
    return salida


def _anotar_modelo(valor, origen: str):
    if isinstance(valor, ValorDocumentado):
        return valor.model_copy(update={"evidencia": [_anotar_evidencia(e, origen) for e in valor.evidencia]})
    if isinstance(valor, BaseModel):
        return valor.model_copy(update={nombre: _anotar_modelo(getattr(valor, nombre), origen) for nombre in type(valor).model_fields})
    if isinstance(valor, list): return [_anotar_modelo(v, origen) for v in valor]
    if isinstance(valor, tuple): return tuple(_anotar_modelo(v, origen) for v in valor)
    return valor


def _anotar_evidencia(e: Evidencia, origen: str) -> Evidencia:
    ubicacion = dict(e.ubicacion or {})
    ubicacion["procedencias_representacion"] = sorted(set([*ubicacion.get("procedencias_representacion", []), origen]))
    return e.model_copy(update={"ubicacion": ubicacion})


def _fusionar_evidencias(items: list[Evidencia]) -> list[Evidencia]:
    salida: dict[str, Evidencia] = {}
    for e in items:
        dump = e.model_dump(mode="json")
        ubicacion = dict(dump.get("ubicacion") or {})
        origenes = ubicacion.pop("procedencias_representacion", [])
        dump["ubicacion"] = ubicacion or None
        clave = json.dumps(dump, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        if clave not in salida:
            salida[clave] = e
        else:
            prev = salida[clave]
            loc = dict(prev.ubicacion or {})
            loc["procedencias_representacion"] = sorted(set([*loc.get("procedencias_representacion", []), *origenes, *(e.ubicacion or {}).get("procedencias_representacion", [])]))
            salida[clave] = prev.model_copy(update={"ubicacion": loc})
    return sorted(salida.values(), key=lambda e: (e.pagina, e.literal, _canon(e.ubicacion)))


def _normalizar_evidencias_modelo(valor):
    if isinstance(valor, ValorDocumentado):
        return valor.model_copy(update={"evidencia": _fusionar_evidencias(list(valor.evidencia))})
    if isinstance(valor, BaseModel):
        return valor.model_copy(update={
            nombre: _normalizar_evidencias_modelo(getattr(valor, nombre))
            for nombre in type(valor).model_fields
        })
    if isinstance(valor, list):
        return [_normalizar_evidencias_modelo(v) for v in valor]
    if isinstance(valor, tuple):
        return tuple(_normalizar_evidencias_modelo(v) for v in valor)
    return valor


def _semantica(valor) -> str:
    def limpiar(v):
        if isinstance(v, dict):
            if {"valor", "literal", "evidencia"}.issubset(v): return limpiar(v["valor"])
            return {k: limpiar(x) for k, x in v.items() if k not in {"evidencia", "orden"}}
        if isinstance(v, list): return [limpiar(x) for x in v]
        return v
    return json.dumps(limpiar(valor.model_dump(mode="json")), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _firmas_evidencia(valor) -> set[str]:
    firmas = set()
    def visitar(v):
        if isinstance(v, ValorDocumentado):
            for e in v.evidencia:
                d = e.model_dump(mode="json"); u = dict(d.get("ubicacion") or {}); u.pop("procedencias_representacion", None); d["ubicacion"] = u or None
                firmas.add(json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
        elif isinstance(v, BaseModel):
            for nombre in type(v).model_fields: visitar(getattr(v, nombre))
        elif isinstance(v, (list, tuple)):
            for x in v: visitar(x)
    visitar(valor); return firmas


def _grupo(miembros, estado, conflictos, factura):
    ids = tuple(identidad_representacion(m) for m in miembros)
    evidencias = {f"{i}:{campo}": valores for i, identidad in enumerate(ids) for campo, valores in identidad.evidencias.items()}
    return GrupoFacturaDocumental(tuple(sorted(m.origen for m in miembros)), ids, estado, evidencias, conflictos, factura)


def _mismo_ambito_candidato(a: RepresentacionFactura, b: RepresentacionFactura) -> bool:
    """Agrupa para resolver; no afirma equivalencia documental."""
    ia, ib = identidad_representacion(a), identidad_representacion(b)
    return bool(
        ia.source_sha and ib.source_sha and ia.source_sha == ib.source_sha
        and ia.numero_factura and ia.numero_factura == ib.numero_factura
        and _solapan(ia.paginas, ib.paginas)
    )


def _incidencia(factura, codigo, bloqueante, *, origenes=None):
    descripcion = codigo if not origenes else f"{codigo}: {', '.join(sorted(origenes))}"
    incidencia = Incidencia(codigo=codigo, severidad=Severidad.ERROR if bloqueante else Severidad.INFO, descripcion=descripcion, paginas=list(range(factura.pagina_inicio, factura.pagina_fin + 1)), bloqueante=bloqueante)
    estado = EstadoValidacion.REQUIERE_REVISION if bloqueante else factura.estado_validacion
    return factura.model_copy(update={"estado_validacion": estado, "incidencias": [*factura.incidencias, incidencia]})


def _vd(valor): return (None, ()) if valor is None or not valor.evidencia else (valor.valor, tuple(valor.evidencia))
def _fecha(f):
    if f.fecha_factura is None or not f.fecha_factura.evidencia: return None, ()
    v=f.fecha_factura.valor; return (v.iso.isoformat() if v.iso else v.literal), tuple(f.fecha_factura.evidencia)
def _normalizar_decimal(v): return None if v is None else str(Decimal(str(v)).normalize())
def _solapan(a,b): return not (a[1] < b[0] or b[1] < a[0])
def _canon(v): return json.dumps(v.model_dump(mode="json") if isinstance(v, BaseModel) else v, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
def _hash_factura(f): return hashlib.sha256(f.json_estable().encode()).hexdigest()
