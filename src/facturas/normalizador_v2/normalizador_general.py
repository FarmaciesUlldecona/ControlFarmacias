from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from src.facturas.normalizadores.comun import AliasProveedor, fecha_visible_a_iso, importe_espanol_a_decimal

from .modelos import (
    AlbaranDocumental, DerivacionCampo, DiscrepanciaDocumental, EstadoValidacion, Evidencia,
    FacturaNormalizada, FechaDocumental, FormaPago, Incidencia, MovimientoComercial,
    FuenteDerivacion, NaturalezaPrincipal, OrigenDerivacion, ReferenciaDocumental, ResultadoControl, ResultadoValidacion,
    Sentido, Severidad, Tercero, TipoDiscrepancia, TipoMovimiento, TipoReferencia,
    Totales, TramoImpuesto, ValorDocumentado, Vencimiento,
)
from .validadores import ContextoValidacion, validar_factura

VERSION_NORMALIZACION = "normalizador-v2.general.3"
ALIASES_PROVEEDOR = (
    AliasProveedor("ALLIANCE HEALTHCARE", ("ALLIANCE", "CENCORA", "AH")),
    AliasProveedor("ECOCEUTICS / HYGIE31", ("ECOCEUTICS", "HYGIE31")),
)


_FAMILIAS = {
    "vencimientos", "impuestos", "albaranes", "movimientos_comerciales",
    "referencias_documentales", "discrepancias_documentales",
}
_ALIAS_FAMILIA = {"fecha_vencimiento": ("vencimientos", "fecha")}
_RUTA_FILA_CRITICA = re.compile(
    r"^(vencimientos|impuestos|albaranes|movimientos_comerciales|referencias_documentales)\[(\d+)\]\.([^.]+)$"
)


def _texto_comparable(valor: Any) -> str:
    texto = unicodedata.normalize("NFKC", str(valor)).casefold()
    return " ".join(texto.split())


def _partes_campo(campo: str) -> tuple[str, str | None]:
    partes = [p for p in re.split(r"\.|\[|\]", campo) if p and not p.isdigit()]
    if not partes:
        return "", None
    alias = _ALIAS_FAMILIA.get(partes[0])
    if alias:
        return alias
    return partes[0], partes[-1] if len(partes) > 1 else None


def _literal_demuestra(valor: Any, literal: str, convertir: Callable[[Any], Any] | None) -> bool:
    """Equivalencia conservadora: literal textual o token tipado visible."""
    buscado = _texto_comparable(valor)
    visible = _texto_comparable(literal)
    if buscado and buscado in visible:
        return True
    if convertir is _decimal:
        esperado = _decimal(valor)
        tokens = re.findall(r"(?<![\w])[-+]?\d[\d. ]*(?:,\d+)?%?[-+]?(?![\w])", literal)
        for token in tokens:
            try:
                if _decimal(token.replace("%", "").strip()) == esperado:
                    return True
            except (TypeError, ValueError):
                continue
    if convertir is _fecha:
        esperado = _fecha(valor).iso
        for token in re.findall(r"\b\d{1,2}[-./]\d{1,2}[-./]\d{4}\b", literal):
            if _fecha(token).iso == esperado:
                return True
    return False


class _ResolvedorEvidencia:
    """Ruta exacta primero; fallback solo documental, localizado, ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Âºnico y compatible."""

    def __init__(self, candidato: dict[str, Any]):
        self.candidato = candidato
        self.evidencias = [
            item for item in candidato.get("evidencias", [])
            if item.get("campo") and item.get("literal")
            and isinstance(item.get("pagina"), int)
            and candidato["pagina_inicio"] <= item["pagina"] <= candidato["pagina_fin"]
        ]
        self.asignaciones: dict[int, list[tuple[str, str]]] = {}
        self.localizadores_v21_usados: set[tuple[Any, ...]] = set()
        self.localizadores_v21_conteo: dict[tuple[Any, ...], int] = {}
        for item in self.evidencias:
            if not self._es_v21(item) or not isinstance(item.get("localizador"), dict):
                continue
            localizador = item["localizador"]
            firma = (
                item["pagina"], _texto_comparable(item["literal"]),
                _texto_comparable(localizador.get("contexto_literal")) if localizador.get("contexto_literal") else None,
                localizador.get("ocurrencia_en_pagina"),
            )
            self.localizadores_v21_conteo[firma] = self.localizadores_v21_conteo.get(firma, 0) + 1
        self.identidades_fila_v22: dict[tuple[Any, ...], int] = {}
        reclamos_span: dict[tuple[Any, ...], set[str]] = {}
        criticos = {
            "vencimientos": ("fecha", "importe"), "impuestos": ("descripcion_literal",),
            "albaranes": ("numero",), "movimientos_comerciales": ("descripcion_literal",),
            "referencias_documentales": ("identificador",),
        }
        for coleccion in ("vencimientos", "impuestos", "albaranes", "movimientos_comerciales", "referencias_documentales"):
            for fila in candidato.get(coleccion, []):
                localizacion = fila.get("localizacion")
                if not isinstance(localizacion, dict):
                    continue
                firma = self._firma_localizacion_v22(localizacion)
                if firma is not None:
                    identidad = (
                        coleccion, firma,
                        tuple(
                            (_texto_comparable(fila[n].get("valor")), _texto_comparable(fila[n].get("literal")))
                            for n in criticos[coleccion] if isinstance(fila.get(n), dict)
                        ),
                    )
                    self.identidades_fila_v22[identidad] = self.identidades_fila_v22.get(identidad, 0) + 1
                    for nombre, documentado in fila.items():
                        if not isinstance(documentado, dict) or set(documentado) != {"valor", "literal"}:
                            continue
                        span = firma + (_texto_comparable(documentado["literal"]), nombre)
                        reclamos_span.setdefault(span, set()).add(_texto_comparable(documentado["valor"]))
        self.spans_incompatibles = {span for span, valores in reclamos_span.items() if len(valores) > 1}
        self.estructuras_v23: dict[str, dict[str, Any]] = {}
        self.elementos_v23: dict[str, tuple[str, dict[str, Any]]] = {}
        self.ids_v23_duplicados: set[str] = set()
        self.filas_v23_ambiguas: set[tuple[Any, ...]] = set()
        self.spans_v23_incompatibles: set[tuple[Any, ...]] = set()
        self.identidades_v23: dict[tuple[Any, ...], int] = {}
        self._preparar_v23()

    @staticmethod
    def _span_v23(span: Any) -> tuple[int, int] | None:
        if not isinstance(span, dict) or set(span) != {"inicio", "fin"}:
            return None
        inicio, fin = span.get("inicio"), span.get("fin")
        if any(isinstance(x, bool) or not isinstance(x, int) for x in (inicio, fin)) or inicio < 0 or fin <= inicio:
            return None
        return inicio, fin

    def _preparar_v23(self) -> None:
        estructuras = self.candidato.get("estructuras_documentales")
        if not isinstance(estructuras, list):
            return
        for estructura in estructuras:
            if not isinstance(estructura, dict) or not isinstance(estructura.get("id"), str):
                continue
            eid = estructura["id"]
            if eid in self.estructuras_v23:
                self.ids_v23_duplicados.add(eid)
            self.estructuras_v23[eid] = estructura
            for elemento in estructura.get("elementos", []):
                if not isinstance(elemento, dict) or not isinstance(elemento.get("id"), str):
                    continue
                item_id = elemento["id"]
                if item_id in self.elementos_v23:
                    self.ids_v23_duplicados.add(item_id)
                self.elementos_v23[item_id] = (eid, elemento)
        firmas: dict[tuple[Any, ...], set[str]] = {}
        reclamos: dict[tuple[Any, ...], set[str]] = {}
        for coleccion in ("vencimientos", "impuestos", "albaranes", "movimientos_comerciales", "referencias_documentales"):
            for fila in self.candidato.get(coleccion, []):
                contexto = fila.get("contexto_fila") if isinstance(fila, dict) else None
                if not isinstance(contexto, dict):
                    continue
                span_fila = self._span_v23(contexto.get("span_pagina"))
                posicion = contexto.get("posicion")
                if span_fila is None or not isinstance(posicion, dict):
                    continue
                firma = (
                    contexto.get("pagina"), span_fila,
                    posicion.get("segmento"), posicion.get("fila"), posicion.get("zona"),
                )
                firmas.setdefault(firma, set()).add(str(contexto.get("estructura_id")))
                criticos = {
                    "vencimientos": ("fecha", "importe"), "impuestos": ("descripcion_literal", "base"),
                    "albaranes": ("numero",), "movimientos_comerciales": ("descripcion_literal",),
                    "referencias_documentales": ("identificador",),
                }
                identidad = (
                    coleccion, firma,
                    tuple(
                        (_texto_comparable(fila[n].get("valor")), _texto_comparable(fila[n].get("literal")),
                         tuple((fila[n].get("span_fila") or {}).get(k) for k in ("inicio", "fin")))
                        for n in criticos[coleccion] if isinstance(fila.get(n), dict)
                    ),
                )
                self.identidades_v23[identidad] = self.identidades_v23.get(identidad, 0) + 1
                for nombre, documentado in fila.items():
                    if not isinstance(documentado, dict) or set(documentado) != {"valor", "literal", "span_fila"}:
                        continue
                    if nombre in {"tipo", "sentido"}:
                        continue
                    span_campo = self._span_v23(documentado.get("span_fila"))
                    if span_campo is None:
                        continue
                    clave = firma[:2] + span_campo + (_texto_comparable(documentado.get("literal")),)
                    reclamos.setdefault(clave, set()).add(_texto_comparable(documentado.get("valor")))
        self.filas_v23_ambiguas = {firma for firma, ids in firmas.items() if len(ids) != 1}
        self.spans_v23_incompatibles = {span for span, valores in reclamos.items() if len(valores) > 1}

    @staticmethod
    def _sentido_canonico(elemento: dict[str, Any]) -> str | None:
        literal = unicodedata.normalize("NFKC", str(elemento.get("literal", ""))).strip().upper()
        if literal in {"CARGO", "CARGOS"}:
            return "CARGO"
        if literal in {"ABONO", "ABONOS"}:
            return "ABONO"
        return None

    def _sentido_directo_valido_v23(self, fila: dict[str, Any]) -> bool:
        documentado = fila.get("sentido")
        contexto = fila.get("contexto_fila")
        if not isinstance(documentado, dict) or not isinstance(contexto, dict):
            return False
        if set(documentado) != {"valor", "literal", "span_fila"}:
            return False
        span = self._span_v23(documentado.get("span_fila"))
        literal = documentado.get("literal")
        literal_fila = contexto.get("literal_fila")
        if span is None or not isinstance(literal, str) or not isinstance(literal_fila, str):
            return False
        inicio, fin = span
        return (
            fin <= len(literal_fila)
            and literal_fila[inicio:fin] == literal
            and self._sentido_canonico({"literal": literal}) == documentado.get("valor")
        )

    def _sentido_externo_v23(self, fila: dict[str, Any]) -> tuple[str, tuple[str, dict[str, Any]]] | None:
        """Excepcion cerrada: una sola seccion externa aporta exclusivamente el sentido."""
        if self._sentido_directo_valido_v23(fila):
            return None
        contexto = fila.get("contexto_fila")
        if not isinstance(contexto, dict):
            return None
        eid = contexto.get("estructura_id")
        ids = contexto.get("elementos_contexto_ids")
        sentido_id = contexto.get("elemento_sentido_id")
        if not isinstance(ids, list) or not isinstance(sentido_id, str) or sentido_id not in ids:
            return None
        externas = [item_id for item_id in ids if self.elementos_v23.get(item_id, (None,))[0] != eid]
        if externas != [sentido_id] or sentido_id in self.ids_v23_duplicados:
            return None
        fuente = self.elementos_v23.get(sentido_id)
        if fuente is None or fuente[0] == eid or fuente[0] not in self.estructuras_v23:
            return None
        elemento = fuente[1]
        propuesto = (fila.get("sentido") or {}).get("valor") if isinstance(fila.get("sentido"), dict) else None
        canonico = self._sentido_canonico(elemento)
        if (
            elemento.get("tipo") != "SECCION"
            or elemento.get("pagina") != contexto.get("pagina")
            or self._span_v23(elemento.get("span_pagina")) is None
            or canonico is None
            or elemento.get("valor_sentido") != canonico
            or propuesto != canonico
        ):
            return None
        return sentido_id, fuente

    def _contexto_v23(self, fila: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], tuple[Any, ...]] | None:
        contexto = fila.get("contexto_fila")
        if not isinstance(contexto, dict):
            return None
        eid = contexto.get("estructura_id")
        estructura = self.estructuras_v23.get(eid)
        if estructura is None or eid in self.ids_v23_duplicados:
            return None
        pagina = contexto.get("pagina")
        paginas = estructura.get("paginas")
        if not isinstance(paginas, list) or len(set(paginas)) != len(paginas) or pagina not in paginas:
            return None
        if not isinstance(pagina, int) or not self.candidato["pagina_inicio"] <= pagina <= self.candidato["pagina_fin"]:
            return None
        span_pagina = self._span_v23(contexto.get("span_pagina"))
        literal_fila = contexto.get("literal_fila")
        posicion = contexto.get("posicion")
        if span_pagina is None or not isinstance(literal_fila, str) or not literal_fila.strip() or not isinstance(posicion, dict):
            return None
        if set(posicion) != {"segmento", "fila", "zona"} or not isinstance(posicion.get("zona"), str) or not posicion["zona"].strip():
            return None
        if any(isinstance(posicion.get(k), bool) or not isinstance(posicion.get(k), int) or posicion[k] < 1 for k in ("segmento", "fila")):
            return None
        firma = (pagina, span_pagina, posicion["segmento"], posicion["fila"], posicion["zona"])
        if firma in self.filas_v23_ambiguas:
            return None
        ids = contexto.get("elementos_contexto_ids")
        if not isinstance(ids, list) or len(ids) != len(set(ids)):
            return None
        externa = self._sentido_externo_v23(fila)
        externa_id = externa[0] if externa is not None else None
        for item_id in ids:
            resuelto = self.elementos_v23.get(item_id)
            if resuelto is None or item_id in self.ids_v23_duplicados:
                return None
            if resuelto[0] != eid and item_id != externa_id:
                return None
        sentido_id = contexto.get("elemento_sentido_id")
        if sentido_id is not None and sentido_id not in ids:
            return None
        return contexto, estructura, firma

    def _fuente_sentido_v23(
        self, contexto: dict[str, Any], propuesto: str,
    ) -> tuple[str, tuple[str, dict[str, Any]]] | None:
        """Resuelve una unica fuente semantica vinculada; nunca corrige por nombre o posicion."""
        fila = next((fila for coleccion in ("albaranes", "movimientos_comerciales")
                     for fila in self.candidato.get(coleccion, []) if fila.get("contexto_fila") is contexto), None)
        externa = self._sentido_externo_v23(fila) if fila is not None else None
        if externa is not None:
            return externa if self._sentido_canonico(externa[1][1]) == propuesto else None

        item_id = contexto.get("elemento_sentido_id")
        fuente = self.elementos_v23.get(item_id)
        if (
            fila is not None
            and self._sentido_directo_valido_v23(fila)
            and fuente is not None
            and fuente[0] == contexto["estructura_id"]
            and item_id in contexto.get("elementos_contexto_ids", [])
            and item_id not in self.ids_v23_duplicados
        ):
            candidatas_ids = [item_id]
        else:
            candidatas_ids = list(contexto.get("elementos_contexto_ids", []))

        candidatas: list[tuple[str, tuple[str, dict[str, Any]], str]] = []
        for contexto_id in candidatas_ids:
            candidata = self.elementos_v23.get(contexto_id)
            if candidata is None or candidata[0] != contexto["estructura_id"] or contexto_id in self.ids_v23_duplicados:
                continue
            elemento = candidata[1]
            sentido = self._sentido_canonico(elemento)
            if elemento.get("tipo") != "SECCION" or elemento.get("pagina") != contexto.get("pagina") or sentido is None:
                continue
            if elemento.get("valor_sentido") == sentido:
                candidatas.append((contexto_id, candidata, sentido))

        if len(candidatas) != 1 or candidatas[0][2] != propuesto:
            return None
        return candidatas[0][0], candidatas[0][1]

    def _resolver_v23(self, campo: str, documentado: dict[str, Any], convertir: Callable[[Any], Any] | None) -> list[Evidencia]:
        coincidencia = _RUTA_FILA_CRITICA.match(campo)
        if coincidencia is None or set(documentado) != {"valor", "literal", "span_fila"}:
            return []
        coleccion, indice_texto, hoja = coincidencia.groups()
        indice = int(indice_texto)
        filas = self.candidato.get(coleccion, [])
        if indice >= len(filas) or filas[indice].get(hoja) is not documentado:
            return []
        fila = filas[indice]
        resuelto = self._contexto_v23(fila)
        if resuelto is None:
            return []
        contexto, _, firma = resuelto
        criticos = {
            "vencimientos": ("fecha", "importe"), "impuestos": ("descripcion_literal", "base"),
            "albaranes": ("numero",), "movimientos_comerciales": ("descripcion_literal",),
            "referencias_documentales": ("identificador",),
        }
        identidad = (
            coleccion, firma,
            tuple(
                (_texto_comparable(fila[n].get("valor")), _texto_comparable(fila[n].get("literal")),
                 tuple((fila[n].get("span_fila") or {}).get(k) for k in ("inicio", "fin")))
                for n in criticos[coleccion] if isinstance(fila.get(n), dict)
            ),
        )
        if self.identidades_v23.get(identidad) != 1:
            return []
        valor, literal = documentado.get("valor"), documentado.get("literal")
        if valor is None or not isinstance(literal, str) or not literal.strip():
            return []
        span = self._span_v23(documentado.get("span_fila"))
        pagina = contexto["pagina"]
        if span is not None and hoja != "sentido":
            inicio, fin = span
            if fin > len(contexto["literal_fila"]) or contexto["literal_fila"][inicio:fin] != literal:
                literal_fila = contexto["literal_fila"]
                ocurrencias = [
                    i
                    for i in range(len(literal_fila))
                    if literal_fila.startswith(literal, i)
                ]
                if len(ocurrencias) != 1 or not _literal_demuestra(valor, literal, convertir):
                    return []
                inicio = ocurrencias[0]
                fin = inicio + len(literal)
                return [
                    Evidencia(
                        pagina=pagina,
                        literal=literal,
                        ubicacion={
                            "span_fila_inferido": {"inicio": inicio, "fin": fin},
                            "estructura_id": contexto["estructura_id"],
                            "posicion": contexto["posicion"],
                        },
                    )
                ]
            clave = firma[:2] + span + (_texto_comparable(literal),)
            if clave in self.spans_v23_incompatibles or not _literal_demuestra(valor, literal, convertir):
                return []
            return [Evidencia(pagina=pagina, literal=literal, ubicacion={"span_fila": documentado["span_fila"], "estructura_id": contexto["estructura_id"]})]
        if hoja != "sentido":
            literal_fila = contexto["literal_fila"]
            ocurrencias = [
                i
                for i in range(len(literal_fila))
                if literal_fila.startswith(literal, i)
            ]
            if len(ocurrencias) != 1 or not _literal_demuestra(valor, literal, convertir):
                return []
            inicio = ocurrencias[0]
            fin = inicio + len(literal)
            return [
                Evidencia(
                    pagina=pagina,
                    literal=literal,
                    ubicacion={
                        "span_fila_inferido": {"inicio": inicio, "fin": fin},
                        "estructura_id": contexto["estructura_id"],
                        "posicion": contexto["posicion"],
                    },
                )
            ]
        propuesto = str(valor)
        if hoja == "sentido" and self._sentido_directo_valido_v23(fila):
            inicio, fin = span  # validado por _sentido_directo_valido_v23
            return [Evidencia(
                pagina=pagina, literal=literal,
                ubicacion={"span_fila": {"inicio": inicio, "fin": fin}, "estructura_id": contexto["estructura_id"]},
            )]
        resuelta = self._fuente_sentido_v23(contexto, propuesto)
        if resuelta is None:
            return []
        item_id, fuente = resuelta

        elemento = fuente[1]
        literal_fuente = elemento.get("literal")
        encontrados = set(re.findall(r"(?<!\w)(CARGOS?|ABONOS?)(?!\w)", str(literal_fuente), re.IGNORECASE))
        sentidos = {"CARGO" if x.casefold().startswith("cargo") else "ABONO" for x in encontrados}
        if len(sentidos) != 1 or propuesto not in sentidos or elemento.get("valor_sentido") != propuesto:
            return []
        if elemento.get("pagina") not in self.estructuras_v23[fuente[0]].get("paginas", []) or self._span_v23(elemento.get("span_pagina")) is None:
            return []
        return [
            Evidencia(pagina=int(elemento["pagina"]), literal=str(literal_fuente), ubicacion={"span_pagina": elemento["span_pagina"], "estructura_id": fuente[0], "elemento_id": item_id}),
            Evidencia(pagina=pagina, literal=contexto["literal_fila"], ubicacion={"span_pagina": contexto["span_pagina"], "estructura_id": fuente[0], "posicion": contexto["posicion"]}),
        ]

    @staticmethod
    def _es_v21(item: dict[str, Any]) -> bool:
        return any(clave in item for clave in ("valor", "localizador"))

    @staticmethod
    def _firma_localizacion_v22(localizacion: dict[str, Any]) -> tuple[Any, ...] | None:
        pagina = localizacion.get("pagina")
        contexto = localizacion.get("contexto_literal")
        ocurrencia = localizacion.get("ocurrencia_en_pagina")
        if not isinstance(pagina, int) or isinstance(pagina, bool) or pagina < 1:
            return None
        if not isinstance(contexto, str) or not contexto.strip():
            return None
        if not isinstance(ocurrencia, int) or isinstance(ocurrencia, bool) or ocurrencia < 1:
            return None
        return pagina, _texto_comparable(contexto), ocurrencia

    def _resolver_v22(self, campo: str, documentado: dict[str, Any], convertir: Callable[[Any], Any] | None) -> list[Evidencia]:
        coincidencia = _RUTA_FILA_CRITICA.match(campo)
        if coincidencia is None or set(documentado) != {"valor", "literal"}:
            return []
        coleccion, indice_texto, hoja = coincidencia.groups()
        indice = int(indice_texto)
        filas = self.candidato.get(coleccion, [])
        if indice >= len(filas) or filas[indice].get(hoja) is not documentado:
            return []
        localizacion = filas[indice].get("localizacion")
        if not isinstance(localizacion, dict):
            return []
        firma = self._firma_localizacion_v22(localizacion)
        if firma is None:
            return []
        criticos = {
            "vencimientos": ("fecha", "importe"), "impuestos": ("descripcion_literal",),
            "albaranes": ("numero",), "movimientos_comerciales": ("descripcion_literal",),
            "referencias_documentales": ("identificador",),
        }
        identidad = (
            coleccion, firma,
            tuple(
                (_texto_comparable(filas[indice][n].get("valor")), _texto_comparable(filas[indice][n].get("literal")))
                for n in criticos[coleccion] if isinstance(filas[indice].get(n), dict)
            ),
        )
        if self.identidades_fila_v22.get(identidad) != 1:
            return []
        pagina, contexto, _ = firma
        if not self.candidato["pagina_inicio"] <= pagina <= self.candidato["pagina_fin"]:
            return []
        literal = documentado.get("literal")
        valor = documentado.get("valor")
        if valor is None or not isinstance(literal, str) or not literal.strip():
            return []
        if firma + (_texto_comparable(literal), hoja) in self.spans_incompatibles:
            return []
        if _texto_comparable(literal) not in contexto or not _literal_demuestra(valor, literal, convertir):
            return []
        return [Evidencia(pagina=pagina, literal=literal)]

    def _resolver_v21(self, campo: str, valor: Any, convertir: Callable[[Any], Any] | None) -> list[Evidencia]:
        candidatas = [item for item in self.evidencias if self._es_v21(item) and item.get("campo") == campo]
        validas: list[tuple[dict[str, Any], tuple[Any, ...]]] = []
        for item in candidatas:
            if "valor" not in item or not isinstance(item.get("localizador"), dict):
                continue
            localizador = item["localizador"]
            contexto = localizador.get("contexto_literal")
            ocurrencia = localizador.get("ocurrencia_en_pagina")
            if contexto in (None, "") and not isinstance(ocurrencia, int):
                continue
            if contexto not in (None, "") and _texto_comparable(item["literal"]) not in _texto_comparable(contexto):
                continue
            try:
                esperado = convertir(valor) if convertir else valor
                declarado = convertir(item["valor"]) if convertir else item["valor"]
            except (TypeError, ValueError):
                continue
            if isinstance(declarado, bool) != isinstance(esperado, bool):
                continue
            if declarado != esperado or not _literal_demuestra(valor, item["literal"], convertir):
                continue
            firma = (
                item["pagina"], _texto_comparable(item["literal"]),
                _texto_comparable(contexto) if contexto else None, ocurrencia,
            )
            validas.append((item, firma))
        if len(validas) != 1 or self.localizadores_v21_conteo.get(validas[0][1]) != 1 or validas[0][1] in self.localizadores_v21_usados:
            return []
        item, firma = validas[0]
        self.localizadores_v21_usados.add(firma)
        return [Evidencia(pagina=item["pagina"], literal=item["literal"])]

    def _resolver_cabecera_v23(
        self,
        campo: str,
        documentado: dict[str, Any],
        convertir: Callable[[Any], Any] | None,
    ) -> list[Evidencia]:
        if set(documentado) != {"valor", "literal", "pagina", "contexto_literal", "span_contexto"}:
            return []

        valor = documentado.get("valor")
        literal = documentado.get("literal")
        pagina = documentado.get("pagina")
        contexto = documentado.get("contexto_literal")
        span = self._span_v23(documentado.get("span_contexto"))

        if valor is None:
            return []
        if not isinstance(literal, str) or not literal.strip():
            return []
        if not isinstance(contexto, str) or not contexto.strip():
            return []
        if isinstance(pagina, bool) or not isinstance(pagina, int):
            return []
        if not self.candidato["pagina_inicio"] <= pagina <= self.candidato["pagina_fin"]:
            return []
        if span is None:
            return []

        inicio, fin = span
        if fin > len(contexto):
            return []
        if contexto[inicio:fin] != literal:
            return []
        if contexto.count(literal) != 1:
            return []
        if not _literal_demuestra(valor, literal, convertir):
            return []

        return [
            Evidencia(
                pagina=pagina,
                literal=literal,
                ubicacion={
                    "span_contexto": documentado["span_contexto"],
                    "contexto_literal": contexto,
                    "campo": campo,
                },
            )
        ]

    def buscar(self, campo: str, valor: Any, convertir: Callable[[Any], Any] | None) -> list[Evidencia]:
        if isinstance(valor, dict) and set(valor) == {"valor", "literal", "pagina", "contexto_literal", "span_contexto"}:
            return self._resolver_cabecera_v23(campo, valor, convertir)
        if isinstance(valor, dict) and any(clave in valor for clave in ("span_fila",)):
            return self._resolver_v23(campo, valor, convertir)
        if isinstance(valor, dict) and any(clave in valor for clave in ("valor", "literal")):
            return self._resolver_v22(campo, valor, convertir)

        # Precedencia por campo: una evidencia V2.1 exacta presente debe ser
        # valida; nunca se enmascara con un fallback historico mas permisivo.
        if any(self._es_v21(item) and item.get("campo") == campo for item in self.evidencias):
            return self._resolver_v21(campo, valor, convertir)

        # Fallback historico V2: conserva exactamente las garantias anteriores.
        evidencias_v2 = [item for item in self.evidencias if not self._es_v21(item)]
        exactas = [item for item in evidencias_v2 if item["campo"] == campo]
        if len(exactas) == 1:
            item = exactas[0]
            return [Evidencia(pagina=item["pagina"], literal=item["literal"])]
        if exactas:
            return []

        familia, hoja = _partes_campo(campo)
        if familia not in _FAMILIAS:
            return []
        compatibles = []
        for indice, item in enumerate(evidencias_v2):
            familia_e, hoja_e = _partes_campo(str(item["campo"]))
            if familia_e != familia:
                continue
            # Una hoja explÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â­cita distinta pertenece a otro dato, no es un alias tÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â©cnico.
            if hoja_e is not None and hoja_e != hoja:
                continue
            if _literal_demuestra(valor, item["literal"], convertir):
                compatibles.append((indice, item))
        if len(compatibles) != 1:
            return []

        indice, item = compatibles[0]
        firma = (campo, _texto_comparable(valor))
        previas = self.asignaciones.setdefault(indice, [])
        # Una sola evidencia no puede respaldar dos items con el mismo valor indistinguible.
        if any(valor_previo == firma[1] and campo_previo != campo for campo_previo, valor_previo in previas):
            return []
        previas.append(firma)
        return [Evidencia(pagina=item["pagina"], literal=item["literal"])]


def _documentado(candidato: dict[str, Any], campo: str, valor: Any, convertir: Callable[[Any], Any] | None = None, *, resolvedor: _ResolvedorEvidencia | None = None):
    if valor is None:
        return None
    resolvedor = resolvedor or _ResolvedorEvidencia(candidato)
    evidencias = resolvedor.buscar(campo, valor, convertir)
    if not evidencias:
        return None
    valor_efectivo = valor["valor"] if isinstance(valor, dict) and set(valor) in (
        {"valor", "literal"},
        {"valor", "literal", "span_fila"},
        {"valor", "literal", "pagina", "contexto_literal", "span_contexto"},
    ) else valor
    convertido = convertir(valor_efectivo) if convertir else valor_efectivo
    return ValorDocumentado(valor=convertido, literal=evidencias[0].literal, evidencia=evidencias)


def _clasificacion_critica(doc: Callable[[str, Any], Any], campo: str, valor: Any) -> Any:
    """Los enums V2.2 tambien se demuestran; V2/V2.1 conservan su scalar historico."""
    if isinstance(valor, dict) and set(valor) in ({"valor", "literal"}, {"valor", "literal", "span_fila"}):
        documentado = doc(campo, valor)
        return documentado.valor if documentado is not None else None
    return valor


def _valor_propuesto(valor: Any) -> Any:
    return valor.get("valor") if isinstance(valor, dict) else valor


def _sentido_v23(
    campo: str, item: dict[str, Any], valor: Any, doc: Callable[[str, Any], Any], resolvedor: _ResolvedorEvidencia,
) -> tuple[str | None, DerivacionCampo | None]:
    if not isinstance(valor, dict) or set(valor) != {"valor", "literal", "span_fila"}:
        return None, None
    documentado = doc(campo, valor)
    if documentado is None:
        return None, None
    propuesto = str(documentado.valor)
    contexto_resuelto = resolvedor._contexto_v23(item)
    if contexto_resuelto is None:
        return None, None
    contexto = contexto_resuelto[0]
    if resolvedor._sentido_directo_valido_v23(item):
        fuente = FuenteDerivacion(campo=f"{campo.rsplit('.', 1)[0]}.contexto_fila.literal_fila", valor=valor["literal"], evidencias=documentado.evidencia)
        return propuesto, DerivacionCampo(campo=campo, valor_final=propuesto, regla_id="sentido.literal_explicito_fila.v2", origen=OrigenDerivacion.LITERAL_EXPLICITO, fuentes=[fuente])
    resuelta = resolvedor._fuente_sentido_v23(contexto, propuesto)
    if resuelta is None:
        return None, None
    item_id, fuente = resuelta

    elemento = fuente[1]
    fuentes = [
        FuenteDerivacion(campo=f"estructuras_documentales.{contexto['estructura_id']}.elementos.{item_id}", valor=elemento["literal"], evidencias=[documentado.evidencia[0]]),
        FuenteDerivacion(campo=f"{campo.rsplit('.', 1)[0]}.contexto_fila", valor=contexto["literal_fila"], evidencias=[documentado.evidencia[1]]),
    ]
    return propuesto, DerivacionCampo(campo=campo, valor_final=propuesto, regla_id="sentido.estructura_documental_inequivoca.v1", origen=OrigenDerivacion.DERIVACION_DETERMINISTA, fuentes=fuentes)


def _sentido_literal_fila(campo: str, item: dict[str, Any], valor: Any) -> tuple[str | None, DerivacionCampo | None]:
    """Acepta solo un sentido explicitamente visible, unico y compatible en la fila."""
    localizacion = item.get("localizacion")
    if not isinstance(localizacion, dict):
        return None, None
    contexto = localizacion.get("contexto_literal")
    pagina = localizacion.get("pagina")
    if not isinstance(contexto, str) or not isinstance(pagina, int):
        return None, None
    encontrados = list(re.finditer(r"(?<!\w)(CARGOS?|ABONOS?)(?!\w)", contexto, re.IGNORECASE))
    sentidos = {"CARGO" if m.group(1).casefold().startswith("cargo") else "ABONO" for m in encontrados}
    propuesto = _valor_propuesto(valor)
    if len(sentidos) != 1 or propuesto not in sentidos:
        return None, None
    literal = encontrados[0].group(1)
    fuente = FuenteDerivacion(
        campo=f"{campo.rsplit('.', 1)[0]}.localizacion.contexto_literal", valor=literal,
        evidencias=[Evidencia(pagina=pagina, literal=literal)],
    )
    return propuesto, DerivacionCampo(
        campo=campo, valor_final=propuesto, regla_id="sentido.literal_explicito_fila.v1",
        origen=OrigenDerivacion.LITERAL_EXPLICITO, fuentes=[fuente],
    )


def _derivacion_desde_fuente(
    *, campo: str, valor_final: str, regla_id: str, campo_fuente: str, fuente: ValorDocumentado[Any],
) -> DerivacionCampo:
    return DerivacionCampo(
        campo=campo, valor_final=valor_final, regla_id=regla_id,
        origen=OrigenDerivacion.DERIVACION_DETERMINISTA,
        fuentes=[FuenteDerivacion(campo=campo_fuente, valor=fuente.valor, evidencias=fuente.evidencia)],
    )


def _decimal(valor: Any) -> Decimal:
    if isinstance(valor, str) and re.fullmatch(r"[-+]?\d+\.\d+", valor.strip()):
        return Decimal(valor.strip())
    convertido = importe_espanol_a_decimal(valor)
    if convertido is None:
        raise ValueError("importe documental vacio")
    return convertido


def _fecha(valor: Any) -> FechaDocumental:
    literal = str(valor)
    try:
        iso = fecha_visible_a_iso(literal)
    except ValueError:
        iso = None
        for formato in ("%d/%m/%Y", "%d.%m.%Y"):
            try:
                iso = datetime.strptime(literal, formato).date().isoformat()
                break
            except ValueError:
                pass
    return FechaDocumental(literal=literal, iso=iso)


def _alias(nombre: str) -> str:
    for regla in ALIASES_PROVEEDOR:
        normalizado = regla.normalizar(nombre)
        if normalizado == regla.nombre_canonico:
            return normalizado
    return nombre


def _tercero(candidato: dict[str, Any], campo: str, datos: dict[str, Any] | None, resolvedor: _ResolvedorEvidencia) -> Tercero | None:
    if datos is None:
        return None
    nombre = _documentado(candidato, f"{campo}.nombre", datos.get("nombre"), resolvedor=resolvedor)
    nif = _documentado(candidato, f"{campo}.nif", datos.get("nif"), resolvedor=resolvedor)
    direccion = _documentado(candidato, f"{campo}.direccion", datos.get("direccion"), resolvedor=resolvedor)
    if nombre is None and nif is None and direccion is None:
        return None
    return Tercero(nombre=nombre, nif=nif, direccion=direccion, alias_funcional=_alias(nombre.valor) if nombre else None)


def _id_factura(candidato: dict[str, Any], proveedor: Tercero | None, numero: ValorDocumentado[str] | None) -> str:
    identidad = {
        "proveedor": proveedor.alias_funcional if proveedor else None,
        "numero": numero.valor if numero else None,
        "pagina_inicio": candidato["pagina_inicio"],
        "pagina_fin": candidato["pagina_fin"],
    }
    return "fac_" + hashlib.sha256(json.dumps(identidad, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]


def normalizar_candidato(candidato: dict[str, Any], *, contexto: ContextoValidacion | None = None) -> FacturaNormalizada:
    resolvedor = _ResolvedorEvidencia(candidato)
    def doc(campo: str, valor: Any, convertir: Callable[[Any], Any] | None = None):
        return _documentado(candidato, campo, valor, convertir, resolvedor=resolvedor)

    proveedor = _tercero(candidato, "proveedor", candidato.get("proveedor"), resolvedor)
    numero = doc("numero_factura", candidato.get("numero_factura"))
    incidencias: list[Incidencia] = []
    derivaciones: list[DerivacionCampo] = []
    if candidato.get("numero_factura") is not None and numero is None:
        incidencias.append(Incidencia(codigo="VALOR_SIN_EVIDENCIA", severidad=Severidad.ERROR, descripcion="numero_factura sin evidencia localizable", paginas=[], bloqueante=True))

    totales = Totales(
        moneda=doc("moneda", candidato.get("moneda")),
        base_imponible=doc("base_imponible_total", candidato.get("base_imponible_total"), _decimal),
        iva=doc("iva_total", candidato.get("iva_total"), _decimal),
        recargo_equivalencia=doc("recargo_equivalencia_total", candidato.get("recargo_equivalencia_total"), _decimal),
        otros=doc("otros_total", candidato.get("otros_total"), _decimal),
        total=doc("importe_total", candidato.get("importe_total"), _decimal),
    )
    vencimientos = []
    for i, item in enumerate(candidato.get("vencimientos", [])):
        fecha = doc(f"vencimientos[{i}].fecha", item.get("fecha"), _fecha)
        importe = doc(f"vencimientos[{i}].importe", item.get("importe"), _decimal)
        if fecha is not None or importe is not None:
            vencimientos.append(Vencimiento(orden=item["orden"], fecha=fecha, importe=importe, medio_pago=doc(f"vencimientos[{i}].medio_pago", item.get("medio_pago"))))
    impuestos = []
    for i, item in enumerate(candidato.get("impuestos", [])):
        kwargs = {nombre: doc(f"impuestos[{i}].{nombre}", item.get(nombre), _decimal if nombre not in {"descripcion_literal"} else None) for nombre in ("descripcion_literal", "base", "tipo_iva", "cuota_iva", "tipo_recargo_equivalencia", "cuota_recargo_equivalencia", "total_tramo")}
        if any(valor is not None for valor in kwargs.values()):
            impuestos.append(TramoImpuesto(orden=item["orden"], **kwargs))
    albaranes = []
    for i, item in enumerate(candidato.get("albaranes", [])):
        numero_albaran = doc(f"albaranes[{i}].numero", item.get("numero"))
        campo_sentido = f"albaranes[{i}].sentido"
        sentido, traza_sentido = _sentido_v23(campo_sentido, item, item.get("sentido"), doc, resolvedor)
        if sentido is None and not (isinstance(item.get("sentido"), dict) and "span_fila" in item["sentido"]):
            sentido = _clasificacion_critica(doc, campo_sentido, item.get("sentido"))
        if sentido is None:
            sentido, traza_sentido = _sentido_literal_fila(campo_sentido, item, item.get("sentido"))
        if numero_albaran is None:
            continue
        if traza_sentido is not None:
            derivaciones.append(traza_sentido)
        if sentido is None:
            evidencias_numero = list(numero_albaran.evidencia)
            incidencias.append(Incidencia(
                codigo="SENTIDO_NO_DOCUMENTADO",
                severidad=Severidad.AVISO,
                descripcion="El documento demuestra el albaran, pero no CARGO/ABONO",
                paginas=sorted({e.pagina for e in evidencias_numero}),
                bloqueante=False,
                evidencias=evidencias_numero,
            ))
        albaranes.append(AlbaranDocumental(orden=item["orden"], fecha=doc(f"albaranes[{i}].fecha", item.get("fecha"), _fecha), numero=numero_albaran, sentido=Sentido(sentido) if sentido is not None else None, tipo_pedido=doc(f"albaranes[{i}].tipo_pedido", item.get("tipo_pedido")), importe_base=doc(f"albaranes[{i}].importe_base", item.get("importe_base"), _decimal), importe_total=doc(f"albaranes[{i}].importe_total", item.get("importe_total"), _decimal)))
    movimientos = []
    for i, item in enumerate(candidato.get("movimientos_comerciales", [])):
        campo_tipo = f"movimientos_comerciales[{i}].tipo"
        campo_descripcion = f"movimientos_comerciales[{i}].descripcion_literal"
        campo_sentido = f"movimientos_comerciales[{i}].sentido"
        tipo = _clasificacion_critica(doc, campo_tipo, item.get("tipo"))
        descripcion = doc(campo_descripcion, item.get("descripcion_literal"))
        sentido, traza_v23 = _sentido_v23(campo_sentido, item, item.get("sentido"), doc, resolvedor)
        if sentido is None and not (isinstance(item.get("sentido"), dict) and "span_fila" in item["sentido"]):
            sentido = _clasificacion_critica(doc, campo_sentido, item.get("sentido"))
        trazas_movimiento: list[DerivacionCampo] = []
        if traza_v23 is not None:
            trazas_movimiento.append(traza_v23)
        if sentido is None:
            sentido, traza_literal = _sentido_literal_fila(campo_sentido, item, item.get("sentido"))
            if traza_literal is not None:
                trazas_movimiento.append(traza_literal)
        if descripcion is not None and tipo is None:
            from .reglas import clasificacion_conceptual_documental
            clasificacion = clasificacion_conceptual_documental(str(descripcion.valor))
            if clasificacion is not None:
                tipo_derivado, regla_id = clasificacion
                if tipo is None and _valor_propuesto(item.get("tipo")) == tipo_derivado:
                    tipo = tipo_derivado
                    trazas_movimiento.append(_derivacion_desde_fuente(
                        campo=campo_tipo, valor_final=str(tipo_derivado), regla_id=regla_id,
                        campo_fuente=campo_descripcion, fuente=descripcion,
                    ))
        if descripcion is None:
            continue
        if tipo is None:
            tipo = TipoMovimiento.OTRO
        derivaciones.extend(trazas_movimiento)
        movimientos.append(MovimientoComercial(orden=item["orden"], tipo=TipoMovimiento(tipo), descripcion_literal=descripcion, sentido=Sentido(sentido) if sentido is not None else None, base=doc(f"movimientos_comerciales[{i}].base", item.get("base"), _decimal), iva=doc(f"movimientos_comerciales[{i}].iva", item.get("iva"), _decimal), recargo_equivalencia=doc(f"movimientos_comerciales[{i}].recargo_equivalencia", item.get("recargo_equivalencia"), _decimal), importe=doc(f"movimientos_comerciales[{i}].importe", item.get("importe"), _decimal)))
    referencias = []
    for i, item in enumerate(candidato.get("referencias_documentales", [])):
        tipo = _clasificacion_critica(doc, f"referencias_documentales[{i}].tipo", item.get("tipo"))
        identificador = doc(f"referencias_documentales[{i}].identificador", item.get("identificador"))
        if tipo is not None and identificador is not None:
            referencias.append(ReferenciaDocumental(orden=item["orden"], tipo=TipoReferencia(tipo), identificador=identificador, descripcion_literal=doc(f"referencias_documentales[{i}].descripcion_literal", item.get("descripcion_literal"))))
    discrepancias = [DiscrepanciaDocumental(tipo=TipoDiscrepancia(item["tipo"]), descripcion=item["descripcion"], importe_diferencia=_decimal(item["importe_diferencia"]) if item.get("importe_diferencia") is not None else None, material=item["material"]) for item in candidato.get("discrepancias_documentales", [])]
    forma = doc("forma_pago", candidato.get("forma_pago"))
    inicial = FacturaNormalizada(
        factura_id=_id_factura(candidato, proveedor, numero),
        tipo_documento=doc("tipo_documento", candidato.get("tipo_documento")),
        naturaleza_principal=NaturalezaPrincipal(candidato["naturaleza_principal"]),
        estado_validacion=EstadoValidacion.REQUIERE_REVISION,
        requiere_conciliacion_albaranes=bool(candidato["requiere_conciliacion_albaranes"]),
        pagina_inicio=candidato["pagina_inicio"], pagina_fin=candidato["pagina_fin"],
        proveedor=proveedor, numero_factura=numero,
        fecha_factura=doc("fecha_factura", candidato.get("fecha_factura"), _fecha),
        destinatario=_tercero(candidato, "destinatario", candidato.get("destinatario"), resolvedor),
        totales=totales, vencimientos=vencimientos, impuestos=impuestos, albaranes=albaranes,
        movimientos_comerciales=movimientos,
        forma_pago=FormaPago(descripcion_literal=forma) if forma else None,
        referencias_documentales=referencias, derivaciones=derivaciones,
        discrepancias_documentales=discrepancias,
        incidencias=incidencias,
        validaciones=[ResultadoValidacion(codigo="NORMALIZACION", resultado=ResultadoControl.OK, descripcion="adaptacion intermedia", regla_version=VERSION_NORMALIZACION)],
    )
    evaluacion = validar_factura(inicial, contexto)
    return inicial.model_copy(update={"estado_validacion": evaluacion.estado, "validaciones": list(evaluacion.validaciones), "discrepancias_documentales": list(evaluacion.discrepancias), "incidencias": list(evaluacion.incidencias)})
