from __future__ import annotations

from typing import Any

from .splitter import REGION_SPLITTER, VERSION_SPLITTER, RangoSegmento


class ServicioGoogleDocumentAI:
    """Frontera perezosa del Custom Splitter; no persiste IDs ni credenciales."""

    def __init__(self) -> None:
        self._cliente: Any | None = None
        self._version_name: str | None = None

    def _resolver(self) -> tuple[Any, str]:
        if self._cliente is not None and self._version_name is not None:
            return self._cliente, self._version_name
        import google.auth
        from google.api_core.client_options import ClientOptions
        from google.cloud import documentai_v1 as documentai

        credenciales, proyecto = google.auth.default()
        if credenciales is None or not proyecto:
            raise RuntimeError("ADC no proporciona credenciales y proyecto")
        cliente = documentai.DocumentProcessorServiceClient(
            credentials=credenciales,
            client_options=ClientOptions(api_endpoint="eu-documentai.googleapis.com"),
        )
        parent = f"projects/{proyecto}/locations/{REGION_SPLITTER}"
        procesadores = [p for p in cliente.list_processors(parent=parent) if str(p.type_) == "CUSTOM_SPLITTING_PROCESSOR"]
        if len(procesadores) != 1:
            raise RuntimeError("no hay exactamente un Custom Splitter EU")
        versiones = [v for v in cliente.list_processor_versions(parent=procesadores[0].name) if v.name.rsplit("/", 1)[-1] == VERSION_SPLITTER]
        if len(versiones) != 1 or int(versiones[0].state) != 1:
            raise RuntimeError("version exacta del Splitter no desplegada")
        self._cliente, self._version_name = cliente, versiones[0].name
        return cliente, self._version_name

    def procesar(self, pdf: bytes, *, region: str, version: str, timeout: float):
        if region != REGION_SPLITTER or version != VERSION_SPLITTER:
            raise ValueError("region o version no aprobada")
        from google.cloud import documentai_v1 as documentai

        cliente, nombre_version = self._resolver()
        respuesta = cliente.process_document(
            request=documentai.ProcessRequest(
                name=nombre_version,
                raw_document=documentai.RawDocument(content=pdf, mime_type="application/pdf"),
            ),
            retry=None,
            timeout=timeout,
        )
        segmentos = []
        for indice, entidad in enumerate(respuesta.document.entities, start=1):
            refs = list(getattr(getattr(entidad, "page_anchor", None), "page_refs", ()))
            paginas = sorted({int(ref.page) + 1 for ref in refs})
            if not paginas:
                raise RuntimeError("segmento sin paginas")
            segmentos.append(RangoSegmento(f"segmento_{indice:02d}", paginas[0], paginas[-1], float(entidad.confidence)))
        return segmentos
