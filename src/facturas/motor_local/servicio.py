from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .adaptadores.base import AdaptadorBase
from .adaptadores.registro import adaptadores_productivos
from .backend.base import BackendPdf
from .conciliacion import evaluar_conciliaciones
from .modelos import DocumentoExtraidoLocal
from .segmentacion.segmentador import segmentar


class MotorDocumentoLocal:
    id = "controlfarmacias-local-engine"
    version = "0.4.0"

    def __init__(self, backend: BackendPdf, adaptadores: tuple[AdaptadorBase, ...] | None = None):
        self.backend = backend
        self.adaptadores = adaptadores if adaptadores is not None else adaptadores_productivos()

    def extraer(self, ruta: str | Path) -> DocumentoExtraidoLocal:
        documento = self.backend.cargar_pdf(ruta)
        segmentos, audit = segmentar(documento)
        reconocimientos = [(adapter, adapter.reconocer(documento)) for adapter in self.adaptadores]
        validos = [(a, r) for a, r in reconocimientos if r.estado == "RECONOCIDO"]
        incidencias = []
        adaptador = None
        if validos:
            mejor = max(r.puntuacion for _, r in validos)
            ganadores = [(a, r) for a, r in validos if r.puntuacion == mejor]
            if len(ganadores) == 1:
                adaptador = ganadores[0][0]
            else:
                incidencias.append({"codigo": "LAYOUT_AMBIGUO", "estado": "AMBIGUO"})
        else:
            incidencias.append({"codigo": "LAYOUT_NO_RECONOCIDO", "estado": "NO_RECONOCIDO"})
        cabecera = adaptador.extraer_cabecera(documento, segmentos) if adaptador else {}
        albaranes = adaptador.extraer_albaranes(documento, segmentos) if adaptador else []
        movimientos = adaptador.extraer_movimientos(documento, segmentos) if adaptador else []
        impuestos = adaptador.extraer_impuestos(documento, segmentos) if adaptador else []
        vencimientos = adaptador.extraer_vencimientos(documento, segmentos) if adaptador else []
        otros = adaptador.extraer_otros(documento, segmentos) if adaptador else []
        controles_conciliacion = evaluar_conciliaciones(adaptador.declarar_conciliaciones(
            documento,
            segmentos,
            cabecera=cabecera,
            albaranes=albaranes,
            movimientos=movimientos,
            impuestos=impuestos,
            vencimientos=vencimientos,
            otros=otros,
        )) if adaptador else []
        if adaptador:
            incidencias.extend(adaptador.incidencias_extraccion(documento, segmentos))
        albaranes, duplicados = _deduplicar_albaranes(albaranes)
        if duplicados:
            incidencias.append({"codigo": "FILAS_DUPLICADAS_EVIDENCIA_IDENTICA", "cantidad": duplicados})
        evidencias = _recoger_evidencias([
            cabecera, albaranes, movimientos, impuestos, vencimientos, otros, controles_conciliacion,
        ])
        capacidades = adaptador.capacidades if adaptador else {
            k: "NO_SOPORTADO" for k in ["segmentacion", "cabecera", "albaranes", "movimientos", "impuestos", "vencimientos"]
        }
        return DocumentoExtraidoLocal(
            documento={
                "sha256": documento.sha_documento,
                "source": documento.ruta,
                "pages": len(documento.paginas),
                "layout": adaptador.id if adaptador else None,
                "layout_version": adaptador.version if adaptador else None,
                "segmentation_audit": audit,
                "reconocimientos": [
                    {
                        "adaptador": adapter.id,
                        "version": adapter.version,
                        "estado": reconocimiento.estado,
                        "puntuacion": reconocimiento.puntuacion,
                        "evidencias": reconocimiento.evidencias,
                    }
                    for adapter, reconocimiento in reconocimientos
                ],
            },
            segmentos=segmentos,
            cabecera=cabecera,
            albaranes=albaranes,
            movimientos=movimientos,
            impuestos=impuestos,
            vencimientos=vencimientos,
            otros=otros,
            controles_conciliacion=controles_conciliacion,
            incidencias=incidencias,
            evidencias=evidencias,
            capacidades=capacidades,
            motor={"id": self.id, "version": self.version, "backend": self.backend.id, "backend_version": self.backend.version},
        )


def serializar_canonico(resultado: DocumentoExtraidoLocal) -> bytes:
    return json.dumps(resultado.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def hash_funcional(resultado: DocumentoExtraidoLocal) -> str:
    return hashlib.sha256(serializar_canonico(resultado)).hexdigest()


def _deduplicar_albaranes(rows):
    output, seen, duplicates = [], set(), 0
    for row in rows:
        number_ev = row.evidencias.get("numero_albaran")
        key = (row.numero_albaran, row.pagina, tuple(number_ev.bbox or []) if number_ev else None)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        output.append(row)
    return output, duplicates


def _recoger_evidencias(valor):
    from .modelos import EvidenciaLocal

    salida, vistas = [], set()

    def visitar(item):
        if isinstance(item, EvidenciaLocal):
            clave = (
                item.sha_documento, item.pagina, item.literal,
                tuple(item.bbox or ()), item.regla, item.columna,
            )
            if clave not in vistas:
                vistas.add(clave)
                salida.append(item)
        elif isinstance(item, dict):
            for contenido in item.values():
                visitar(contenido)
        elif isinstance(item, (list, tuple)):
            for contenido in item:
                visitar(contenido)
        elif hasattr(item, "evidencias"):
            visitar(item.evidencias)

    visitar(valor)
    return salida
