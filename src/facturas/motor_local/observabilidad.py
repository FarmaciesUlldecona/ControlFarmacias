from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Protocol


class DestinoObservabilidadLocal(Protocol):
    def registrar(self, evento: dict[str, Any]) -> None: ...


@dataclass
class ObservabilidadMemoria:
    eventos: list[dict[str, Any]]

    def registrar(self, evento: dict[str, Any]) -> None:
        self.eventos.append(evento)


class ObservabilidadArchivoLocal:
    def __init__(self, directorio: Path):
        self.directorio = Path(directorio)

    def registrar(self, evento: dict[str, Any]) -> None:
        self.directorio.mkdir(parents=True, exist_ok=True)
        sello = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        sha = str(evento.get("sha_documento", "sin_sha"))
        destino = self.directorio / f"{sello}_{sha[:16]}.json"
        destino.write_text(json.dumps(evento, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
