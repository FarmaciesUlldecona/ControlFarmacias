"""Identidad documental canonica PIO basada en SHA-256 unicos."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from src.facturas.importar_facturas_drive import (
    FECHA_INICIO_IMPORTACION,
    es_factura_rita,
    obtener_fecha_carpeta_mes,
)

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class ManifiestoCanonico:
    hashes: frozenset[str]
    sha256: str

    @property
    def total(self) -> int:
        return len(self.hashes)


def clasificar_ruta_indice(ruta_relativa: str) -> str:
    """Encaminamiento operativo, NO evidencia de farmacia economica."""
    ruta = Path(ruta_relativa)
    if not ruta.parts or ruta.suffix.casefold() != ".pdf":
        return "EXCLUIDO"
    fecha = obtener_fecha_carpeta_mes(ruta.parts[0])
    if fecha is None or fecha < FECHA_INICIO_IMPORTACION:
        return "EXCLUIDO"
    return "RITA" if es_factura_rita(ruta) else "PIO"


def _canonizar(hashes: Iterable[object]) -> ManifiestoCanonico:
    normalizados: set[str] = set()
    for valor in hashes:
        if not isinstance(valor, str) or SHA256_RE.fullmatch(valor) is None:
            raise ValueError("HASH_PIO_INVALIDO")
        normalizados.add(valor.lower())
    contenido = "\n".join(sorted(normalizados)).encode("ascii")
    return ManifiestoCanonico(
        hashes=frozenset(normalizados),
        sha256=hashlib.sha256(contenido).hexdigest(),
    )


def manifiesto_sqlite_pio(
    registros: Iterable[Mapping[str, object]],
) -> ManifiestoCanonico:
    return _canonizar(
        registro.get("archivo_hash")
        for registro in registros
        if registro.get("estado") == "IMPORTADA"
        and clasificar_ruta_indice(str(registro.get("ruta_relativa", ""))) == "PIO"
    )


def manifiesto_supabase_pio(hashes: Iterable[object]) -> ManifiestoCanonico:
    """Canoniza hashes de una consulta ya filtrada por farmacia='PIO'."""
    return _canonizar(hashes)


def reconciliado(
    sqlite: ManifiestoCanonico,
    supabase: ManifiestoCanonico,
) -> bool:
    return sqlite.hashes == supabase.hashes and sqlite.sha256 == supabase.sha256


def auditar_inventarios(registros, documentos) -> dict:
    """Guard puro sobre snapshots vivos; no modifica ni descarta historicos.

La farmacia documental, si se aporta, debe venir de evidencia del contenido.
El encaminamiento por nombre sigue siendo un control operativo separado.
"""
    registros, documentos = tuple(registros), tuple(documentos)
    local = manifiesto_sqlite_pio(registros)
    remoto = manifiesto_supabase_pio(
        d.get("archivo_hash") for d in documentos if d.get("farmacia") == "PIO"
    )
    rita = _canonizar(r.get("archivo_hash") for r in registros
                     if r.get("estado") == "IMPORTADA"
                     and clasificar_ruta_indice(str(r.get("ruta_relativa", ""))) == "RITA")
    conflictos = []
    for d in documentos:
        h = str(d.get("archivo_hash", "")).lower()
        farmacia = d.get("farmacia")
        nombre = d.get("archivo_nombre")
        ruta = d.get("ruta_relativa")
        cruzado = (farmacia == "PIO" and h in rita.hashes) or (farmacia == "RITA" and h in local.hashes)
        nombre_rita = bool(nombre and es_factura_rita(Path(nombre)))
        ruta_pio = bool(ruta and clasificar_ruta_indice(ruta) == "PIO")
        contenido = d.get("farmacia_documental")
        contradictorio = contenido in {"PIO", "RITA"} and contenido != farmacia
        if cruzado or contradictorio or (farmacia == "PIO" and nombre_rita) or (farmacia == "RITA" and ruta_pio):
            conflictos.append(d.get("id"))
    solo_local = sorted(local.hashes - remoto.hashes)
    solo_remoto = sorted(remoto.hashes - local.hashes)
    return {"ok": not (solo_local or solo_remoto or conflictos),
            "solo_sqlite_pio": solo_local, "solo_supabase_pio": solo_remoto,
            "conflictos_farmacia": conflictos,
            "manifiesto_sqlite": local.sha256, "manifiesto_supabase": remoto.sha256}
