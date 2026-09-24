"""Shadow local del selector manual one-shot; no conecta ni escribe en produccion."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


MODO = "MANUAL_ONE_SHOT"
PRIMER_DOCUMENTO_ID = "ae53897a-355a-488f-bc3e-1783f39e0f13"
PRIMER_SHA = "4faa899bda8fdb08f9f425b31074dbfb521a3c6051efacb2f3ee5e7259d9d9f1"
PRIMERA_IMPORTACION = datetime.fromisoformat("2026-07-25T10:05:44.218056+00:00")
NUEVOS_IMPORTADOS = (
    (
        "2ad45d18-846b-499d-8bc6-ad9c3e105584",
        "4243688f2939325a4fd3a6ba57ea824114728b0a8e47e34b68a6616500d25b76",
        "2026-09-23T16:34:07.760924+00:00",
    ),
    (
        "96b836ce-1253-411c-9dba-64e111dc72a2",
        "fbc3205d21616541b476fe9250550cce111607f0b3f5d4fb3aed0ebb78710c9d",
        "2026-09-23T16:34:09.268527+00:00",
    ),
)


@dataclass(frozen=True, slots=True)
class Candidato:
    documento_id: str
    sha: str
    fecha_importacion: datetime
    farmacia: str = "PIO"
    estado_lectura: str = "PENDIENTE"
    reprocesado: bool = False
    reintento_habilitado: bool = True
    lock_expirado: bool = True


def _candidatos() -> list[Candidato]:
    items = [Candidato(PRIMER_DOCUMENTO_ID, PRIMER_SHA, PRIMERA_IMPORTACION)]
    for indice in range(1, 133):
        identidad = str(uuid.uuid5(uuid.NAMESPACE_URL, f"cf-shadow-2al-{indice}"))
        sha = hashlib.sha256(f"cf-shadow-2al-{indice}".encode()).hexdigest()
        items.append(
            Candidato(
                identidad,
                sha,
                PRIMERA_IMPORTACION + timedelta(seconds=indice),
            )
        )
    items.extend(
        Candidato(documento_id, sha, datetime.fromisoformat(importado_at))
        for documento_id, sha, importado_at in NUEVOS_IMPORTADOS
    )
    return items


def _selector_compartido(
    candidatos: list[Candidato],
    *,
    normalizacion_automatica: bool,
    modo: str,
) -> Candidato | None:
    disponibles = [
        item
        for item in candidatos
        if item.farmacia == "PIO"
        and item.estado_lectura in {"PENDIENTE", "ERROR"}
        and item.reintento_habilitado
        and item.lock_expirado
        and (
            normalizacion_automatica
            or item.reprocesado
            or modo == MODO
        )
    ]
    disponibles.sort(
        key=lambda item: (
            not item.reprocesado,
            item.fecha_importacion,
            item.documento_id,
        )
    )
    return disponibles[0] if disponibles else None


def ejecutar_shadow() -> dict[str, object]:
    candidatos = _candidatos()
    automatico = _selector_compartido(
        candidatos,
        normalizacion_automatica=False,
        modo="AUTOMATICO",
    )
    manual = _selector_compartido(
        candidatos,
        normalizacion_automatica=False,
        modo=MODO,
    )
    assert automatico is None
    assert manual is not None
    assert manual.documento_id == PRIMER_DOCUMENTO_ID
    posiciones_nuevos = {
        item.sha: candidatos_ordenados + 1
        for candidatos_ordenados, item in enumerate(
            sorted(
                candidatos,
                key=lambda candidato: (
                    not candidato.reprocesado,
                    candidato.fecha_importacion,
                    candidato.documento_id,
                ),
            )
        )
        if item.sha in {sha for _, sha, _ in NUEVOS_IMPORTADOS}
    }

    # El shadow no inventa evidencia del PDF real. La barrera documental debe
    # detener el candidato elegido y nunca probar el segundo.
    evidencia_documental_disponible = False
    persistencias = 0
    resultado = "FAIL_CLOSED_EVIDENCIA_DOCUMENTAL_NO_SIMULADA"
    if evidencia_documental_disponible:  # pragma: no cover - contrato negativo
        persistencias = 1
        resultado = "PERSISTENCIA_MEMORIA"

    return {
        "modo": MODO,
        "documentos_pio": 140,
        "candidatos_simulados": len(candidatos),
        "flag_normalizacion_automatica": False,
        "selector_automatico": None,
        "documento_elegido": manual.documento_id,
        "sha": manual.sha,
        "ordering": [
            "reprocesar_solicitado_at DESC",
            "fecha_importacion ASC",
            "id ASC",
        ],
        "fecha_importacion": manual.fecha_importacion.isoformat(),
        "candidatos_reclamados": 1,
        "segundo_candidato_probado": False,
        "persistencias_productivas": 0,
        "persistencias_memoria": persistencias,
        "provenance": MODO,
        "posiciones_documentos_nuevos": posiciones_nuevos,
        "resultado": resultado,
        "produccion_modificada": False,
    }


if __name__ == "__main__":
    print(json.dumps(ejecutar_shadow(), ensure_ascii=False, sort_keys=True))
