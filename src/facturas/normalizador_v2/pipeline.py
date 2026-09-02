from __future__ import annotations

import copy
import hashlib
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pypdf import PdfReader

from .adaptador_luna import AdaptadorLuna, ErrorLecturaLuna, ResultadoLuna
from .modelos import (
    DocumentoNormalizado, EstadoValidacion, EstrategiaLectura, Incidencia,
    IntentoLectura, MetadataTecnica, Segmento, Severidad, TipoContenido,
)
from .multifactura import consolidar_facturas
from .normalizador_general import normalizar_candidato
from .observabilidad import SinkObservabilidad, TrazaObservabilidad, emitir_traza
from .reglas import aplicar_reglas_pequenas
from .splitter import (
    DecisionSplitter, ErrorSplitter, SenalesSegundaLectura, SplitterSelectivo,
    consolidar_lecturas, decidir_segunda_lectura, dividir_pdf,
)
from .validadores import peor_estado

VERSION_NORMALIZADOR = "2.2.0"
VERSION_CONFIGURACION = "v2.2-evidencia-estructural-1"
_CAMPO_NUMERO_ALBARAN = re.compile(r"^albaranes\[(\d+)\]\.numero$")


@dataclass(frozen=True, slots=True)
class SenalesCandidatoPreNormalizacion:
    multipagina: bool
    tabla_multipagina: bool
    continuidad_tabla: bool
    identificadores_visibles: int
    paginas_detalle: tuple[int, ...]
    subtotal_no_explicado: bool
    diferencia_material_sin_movimientos: bool
    densidad_alta: bool


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _tipo_contenido(lector: PdfReader) -> TipoContenido:
    con_texto = [bool((pagina.extract_text() or "").strip()) for pagina in lector.pages]
    if all(con_texto):
        return TipoContenido.PDF_NATIVO
    if any(con_texto):
        return TipoContenido.PDF_MIXTO
    return TipoContenido.PDF_IMAGEN


def _senales_candidato_pre_normalizacion(candidato: dict[str, Any]) -> SenalesCandidatoPreNormalizacion:
    paginas_albaran = sorted({
        int(e["pagina"])
        for e in candidato.get("evidencias", [])
        if str(e.get("campo", "")).startswith("albaranes[") and e.get("pagina") is not None
    } | {
        int(item["localizacion"]["pagina"])
        for item in candidato.get("albaranes", [])
        if isinstance(item.get("localizacion"), dict) and item["localizacion"].get("pagina") is not None
    })
    indices_evidenciados = {
        int(coincidencia.group(1))
        for evidencia in candidato.get("evidencias", [])
        if evidencia.get("literal")
        and (coincidencia := _CAMPO_NUMERO_ALBARAN.match(str(evidencia.get("campo", ""))))
    }
    indices_candidatos = {
        indice
        for indice, item in enumerate(candidato.get("albaranes", []))
        if item.get("numero") not in (None, "")
    }
    identificadores = len(indices_evidenciados | indices_candidatos)
    subtotal = any(d.get("tipo") == "SUBTOTAL_NO_EXPLICADO" for d in candidato.get("discrepancias_documentales", []))
    multipagina = int(candidato.get("pagina_fin", 1)) > int(candidato.get("pagina_inicio", 1))
    continuidad = len(paginas_albaran) > 1 and paginas_albaran == list(range(paginas_albaran[0], paginas_albaran[-1] + 1))
    return SenalesCandidatoPreNormalizacion(
        multipagina=multipagina,
        tabla_multipagina=len(paginas_albaran) > 1,
        continuidad_tabla=continuidad,
        identificadores_visibles=identificadores,
        paginas_detalle=tuple(paginas_albaran),
        subtotal_no_explicado=subtotal,
        diferencia_material_sin_movimientos=subtotal and not candidato.get("movimientos_comerciales"),
        densidad_alta=identificadores >= 100,
    )


def _senales_por_defecto(
    factura,
    candidato: dict[str, Any],
    precomputadas: SenalesCandidatoPreNormalizacion | None = None,
) -> SenalesSegundaLectura:
    pre = precomputadas or _senales_candidato_pre_normalizacion(candidato)
    return SenalesSegundaLectura(
        naturaleza=factura.naturaleza_principal,
        multipagina=pre.multipagina,
        tabla_multipagina=pre.tabla_multipagina,
        continuidad_tabla=pre.continuidad_tabla,
        filas_extraidas=len(factura.albaranes),
        identificadores_visibles=pre.identificadores_visibles,
        subtotal_no_explicado=pre.subtotal_no_explicado,
        diferencia_material_sin_movimientos=pre.diferencia_material_sin_movimientos,
        densidad_alta=pre.densidad_alta,
        formato_alliance_denso_demostrado=pre.densidad_alta and factura.proveedor is not None and factura.proveedor.alias_funcional == "ALLIANCE HEALTHCARE",
    )


def _remapear_candidato(candidato: dict[str, Any], paginas_originales: tuple[int, ...]) -> dict[str, Any]:
    salida = copy.deepcopy(candidato)
    for evidencia in salida.get("evidencias", []):
        local = int(evidencia["pagina"])
        if local < 1 or local > len(paginas_originales):
            raise ValueError("evidencia segmentada fuera de mapping")
        evidencia["pagina"] = paginas_originales[local - 1]
    for estructura in salida.get("estructuras_documentales", []):
        remapeadas = []
        for pagina in estructura.get("paginas", []):
            local = int(pagina)
            if local < 1 or local > len(paginas_originales):
                raise ValueError("estructura V2.3 segmentada fuera de mapping")
            remapeadas.append(paginas_originales[local - 1])
        estructura["paginas"] = remapeadas
        for elemento in estructura.get("elementos", []):
            local = int(elemento["pagina"])
            if local < 1 or local > len(paginas_originales):
                raise ValueError("elemento V2.3 segmentado fuera de mapping")
            elemento["pagina"] = paginas_originales[local - 1]
    for coleccion in ("vencimientos", "impuestos", "albaranes", "movimientos_comerciales", "referencias_documentales"):
        for fila in salida.get(coleccion, []):
            localizacion = fila.get("localizacion")
            if isinstance(localizacion, dict):
                local = int(localizacion["pagina"])
                if local < 1 or local > len(paginas_originales):
                    raise ValueError("localizacion V2.2 segmentada fuera de mapping")
                localizacion["pagina"] = paginas_originales[local - 1]
            contexto_fila = fila.get("contexto_fila")
            if isinstance(contexto_fila, dict):
                local = int(contexto_fila["pagina"])
                if local < 1 or local > len(paginas_originales):
                    raise ValueError("contexto V2.3 segmentado fuera de mapping")
                contexto_fila["pagina"] = paginas_originales[local - 1]
    inicio, fin = int(salida["pagina_inicio"]), int(salida["pagina_fin"])
    if inicio < 1 or fin > len(paginas_originales):
        raise ValueError("rango de factura segmentada fuera de mapping")
    salida["pagina_inicio"] = paginas_originales[inicio - 1]
    salida["pagina_fin"] = paginas_originales[fin - 1]
    return salida


def _normalizar_facturas(candidatos: tuple[dict[str, Any], ...]):
    normalizadas = tuple(normalizar_candidato(c) for c in candidatos)
    return normalizadas, tuple(aplicar_reglas_pequenas(f) for f in normalizadas)


def normalizar_pdf(
    path: str | Path,
    *,
    lector_luna: Any | None = None,
    splitter: SplitterSelectivo | None = None,
    detector_senales: Callable[[Any, dict[str, Any]], SenalesSegundaLectura] = _senales_por_defecto,
    directorio_segmentos: str | Path | None = None,
    ahora: Callable[[], datetime] = _utc,
    reloj: Callable[[], float] = time.perf_counter,
    directorio_observabilidad: str | Path | None = None,
    sink_observabilidad: SinkObservabilidad | None = None,
    configuracion_shadow_local: Any | None = None,
    motor_shadow_local: Any | None = None,
    sink_shadow_local: Any | None = None,
) -> DocumentoNormalizado:
    ruta = Path(path)
    inicio_dt, inicio_perf = ahora(), reloj()
    contenido = ruta.read_bytes()
    huella = hashlib.sha256(contenido).hexdigest()
    documento_id = "doc_" + huella[:24]
    correlacion_id = "corr_" + huella[:20]
    traza = TrazaObservabilidad(documento_id, ruta.name)
    candidatos_observados: list[dict[str, Any]] = []
    normalizaciones_observadas: list[dict[str, Any]] = []
    reglas_observadas: list[dict[str, Any]] = []
    intentos: list[IntentoLectura] = []
    segmentos_meta: list[Segmento] = []

    def finalizar(documento: DocumentoNormalizado) -> DocumentoNormalizado:
        traza.registrar("F_ESTADO_FINAL", documento)
        emitir_traza(traza, directorio=directorio_observabilidad, sink=sink_observabilidad)
        from src.facturas.motor_local.shadow import ejecutar_shadow_local_sobre_resultado
        return ejecutar_shadow_local_sobre_resultado(
            documento,
            ruta,
            configuracion=configuracion_shadow_local,
            motor_local=motor_shadow_local,
            observabilidad=sink_shadow_local,
        )
    try:
        pdf = PdfReader(ruta)
        numero_paginas = len(pdf.pages)
        if numero_paginas < 1:
            raise ValueError("PDF sin paginas")
        tipo = _tipo_contenido(pdf)
    except Exception as exc:
        fin = ahora()
        return finalizar(DocumentoNormalizado(
            documento_id=documento_id, archivo_origen=ruta.name, tipo_contenido=TipoContenido.PDF_NO_LEIBLE,
            numero_paginas=None, estado_documento=EstadoValidacion.ERROR_TECNICO, estrategia_lectura=EstrategiaLectura.LUNA_V2,
            facturas=[], metadata_tecnica=MetadataTecnica(
                version_normalizador=VERSION_NORMALIZADOR, version_configuracion=VERSION_CONFIGURACION,
                lector_primario="gpt-5.6-luna", intentos=[IntentoLectura(orden=1, estrategia=EstrategiaLectura.LUNA_V2, estado_tecnico="ERROR", motivo=type(exc).__name__, paginas_o_segmentos=[], version_lector="gpt-5.6-luna", duracion_ms=0)],
                huella_contenido=huella, inicio=inicio_dt.isoformat(), fin=fin.isoformat(), duracion_ms=max(0, round((reloj()-inicio_perf)*1000)), correlacion_id=correlacion_id,
            ),
        ))
    lector_luna = lector_luna or AdaptadorLuna()
    try:
        primaria: ResultadoLuna = lector_luna.extraer(ruta)
        intentos.append(IntentoLectura(orden=1, estrategia=EstrategiaLectura.LUNA_V2, estado_tecnico="COMPLETADO", motivo=None, paginas_o_segmentos=list(range(1, numero_paginas + 1)), version_lector=primaria.metadata.modelo_utilizado, duracion_ms=primaria.metadata.duracion_ms))
        candidatos_observados.append({"origen": "primaria", "facturas": primaria.facturas})
        traza.registrar("A_CANDIDATO_LUNA", candidatos_observados)
        pre_primarias = tuple(_senales_candidato_pre_normalizacion(c) for c in primaria.facturas)
        normalizadas, facturas_primarias = _normalizar_facturas(primaria.facturas)
        normalizaciones_observadas.append({"origen": "primaria", "facturas": normalizadas})
        reglas_observadas.append({"origen": "primaria", "facturas": facturas_primarias})
        traza.registrar("C_NORMALIZACION_GENERAL", normalizaciones_observadas)
        traza.registrar("D_REGLAS", reglas_observadas)
    except Exception as exc:
        fin = ahora()
        intentos.append(IntentoLectura(orden=1, estrategia=EstrategiaLectura.LUNA_V2, estado_tecnico="ERROR", motivo=type(exc).__name__, paginas_o_segmentos=list(range(1, numero_paginas + 1)), version_lector="gpt-5.6-luna", duracion_ms=max(0, round((reloj()-inicio_perf)*1000))))
        return finalizar(DocumentoNormalizado(
            documento_id=documento_id, archivo_origen=ruta.name, tipo_contenido=tipo, numero_paginas=numero_paginas,
            estado_documento=EstadoValidacion.ERROR_TECNICO, estrategia_lectura=EstrategiaLectura.LUNA_V2, facturas=[],
            metadata_tecnica=MetadataTecnica(version_normalizador=VERSION_NORMALIZADOR, version_configuracion=VERSION_CONFIGURACION, lector_primario="gpt-5.6-luna", intentos=intentos, huella_contenido=huella, inicio=inicio_dt.isoformat(), fin=fin.isoformat(), duracion_ms=max(0, round((reloj()-inicio_perf)*1000)), correlacion_id=correlacion_id),
        ))
    consolidada = consolidar_facturas(facturas_primarias)
    facturas = list(consolidada.facturas)
    decisiones: list[DecisionSplitter] = []
    senales_evaluadas: list[SenalesSegundaLectura] = []
    por_clave_raw = {
        f.factura_id: (raw, pre)
        for f, raw, pre in zip(facturas_primarias, primaria.facturas, pre_primarias, strict=False)
    }
    for factura in facturas:
        raw, pre = por_clave_raw.get(factura.factura_id, ({}, _senales_candidato_pre_normalizacion({})))
        senales = _senales_por_defecto(factura, raw, pre) if detector_senales is _senales_por_defecto else detector_senales(factura, raw)
        senales_evaluadas.append(senales)
        decisiones.append(decidir_segunda_lectura(senales))
    traza.registrar("B_DECISION_SEGUNDA_LECTURA", [
        {"factura_id": factura.factura_id, "senales": senales, "decision": decision}
        for factura, decision, senales in zip(facturas, decisiones, senales_evaluadas, strict=True)
    ])
    traza.registrar("E_CONSOLIDACION_SEGMENTADA", {"aplicada": False, "facturas": []})
    activar = any(d.activar for d in decisiones)
    estrategia = EstrategiaLectura.LUNA_V2
    if activar and splitter is None:
        facturas = [f.model_copy(update={"estado_validacion": EstadoValidacion.REQUIERE_SEGUNDA_LECTURA}) for f in facturas]
    elif activar and splitter is not None:
        estrategia = EstrategiaLectura.LUNA_V2_MAS_SPLITTER_SEGMENTADO
        try:
            rangos = splitter.segmentar(ruta)
            temporal = None
            if directorio_segmentos is None:
                temporal = tempfile.TemporaryDirectory(prefix="normalizador_v2_")
                directorio = Path(temporal.name)
            else:
                directorio = Path(directorio_segmentos)
            fisicos = dividir_pdf(ruta, rangos, directorio)
            segmentadas = []
            for indice, fisico in enumerate(fisicos, start=2):
                resultado = lector_luna.extraer(fisico.ruta)
                intentos.append(IntentoLectura(orden=indice, estrategia=estrategia, estado_tecnico="COMPLETADO", motivo=fisico.segmento_id, paginas_o_segmentos=[fisico.segmento_id], version_lector=resultado.metadata.modelo_utilizado, duracion_ms=resultado.metadata.duracion_ms))
                segmentos_meta.append(Segmento(segmento_id=fisico.segmento_id, pagina_inicio=fisico.paginas_originales[0], pagina_fin=fisico.paginas_originales[-1], estado="COMPLETADO"))
                remapeadas = tuple(_remapear_candidato(c, fisico.paginas_originales) for c in resultado.facturas)
                candidatos_observados.append({"origen": fisico.segmento_id, "facturas": remapeadas})
                traza.registrar("A_CANDIDATO_LUNA", candidatos_observados)
                normales_segmento, reglas_segmento = _normalizar_facturas(remapeadas)
                normalizaciones_observadas.append({"origen": fisico.segmento_id, "facturas": normales_segmento})
                reglas_observadas.append({"origen": fisico.segmento_id, "facturas": reglas_segmento})
                traza.registrar("C_NORMALIZACION_GENERAL", normalizaciones_observadas)
                traza.registrar("D_REGLAS", reglas_observadas)
                segmentadas.extend(reglas_segmento)
            facturas = list(consolidar_lecturas(facturas, segmentadas, source_sha=huella))
            traza.registrar("E_CONSOLIDACION_SEGMENTADA", {"aplicada": True, "facturas": facturas})
            if temporal is not None:
                temporal.cleanup()
        except Exception as exc:
            intentos.append(IntentoLectura(orden=len(intentos)+1, estrategia=estrategia, estado_tecnico="ERROR", motivo=type(exc).__name__, paginas_o_segmentos=[], version_lector="splitter", duracion_ms=0))
            facturas = [f.model_copy(update={"estado_validacion": EstadoValidacion.REQUIERE_REVISION, "incidencias": [*f.incidencias, Incidencia(codigo="SEGUNDA_LECTURA_FALLIDA", severidad=Severidad.ERROR, descripcion="La segunda lectura necesaria fallo", paginas=list(range(f.pagina_inicio, f.pagina_fin+1)), bloqueante=True)]}) for f in facturas]
    estado = peor_estado(f.estado_validacion for f in facturas) if facturas else EstadoValidacion.REQUIERE_REVISION
    fin_dt = ahora()
    return finalizar(DocumentoNormalizado(
        documento_id=documento_id, archivo_origen=ruta.name, tipo_contenido=tipo, numero_paginas=numero_paginas,
        estado_documento=estado, estrategia_lectura=estrategia, facturas=facturas,
        metadata_tecnica=MetadataTecnica(version_normalizador=VERSION_NORMALIZADOR, version_configuracion=VERSION_CONFIGURACION, lector_primario="gpt-5.6-luna", intentos=intentos, segmentos=segmentos_meta, huella_contenido=huella, inicio=inicio_dt.isoformat(), fin=fin_dt.isoformat(), duracion_ms=max(0, round((reloj()-inicio_perf)*1000)), correlacion_id=correlacion_id),
    ))
