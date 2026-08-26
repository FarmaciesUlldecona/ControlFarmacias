from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from ..modelos import DocumentoLocal


@runtime_checkable
class BackendPdf(Protocol):
    id: str
    version: str

    def cargar_pdf(self, ruta: str | Path) -> DocumentoLocal:
        """Abre, lee paginas/texto/posiciones y cierra todos los recursos."""
        ...
