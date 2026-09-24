"""Autoridad documental comun previa a persistencia economica.

La resolucion usa exclusivamente campos documentales con evidencia. Los
metadatos tecnicos (nombre y ruta del archivo, hash o carpeta) no participan.
"""
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from types import MappingProxyType
import unicodedata


@dataclass(frozen=True)
class AutoridadDocumentalFarmacia:
    farmacia: str
    nif: str
    nombres: tuple[str, ...]


@dataclass(frozen=True)
class ResolucionFarmaciaDocumental:
    farmacia_documental: str | None
    estado: str
    campo_documental: str | None
    valor_observado: str | None
    autoridad_comparada: dict[str, object] | None
    provenance: dict[str, object] | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


# Unica identidad maestra autorizada. RITA no se incorpora sin autorizacion
# funcional expresa.
AUTORIDADES_DOCUMENTALES_FARMACIA = MappingProxyType({
    "PIO": AutoridadDocumentalFarmacia(
        farmacia="PIO",
        nif="40901058C",
        nombres=("PUIG SALOMÓN, PÍO",),
    ),
})


class ErrorFarmaciaDocumental(ValueError):
    requiere_revision = True


def _normalizar_nif(valor: str) -> str:
    return "".join(caracter for caracter in valor.upper() if caracter.isalnum())


def _normalizar_nombre(valor: str) -> str:
    sin_acentos = "".join(
        caracter
        for caracter in unicodedata.normalize("NFKD", valor)
        if not unicodedata.combining(caracter)
    )
    return " ".join(re.findall(r"[A-Z0-9]+", sin_acentos.upper()))


def _campo_con_evidencia(destinatario: Mapping, campo: str, normalizador):
    documentado = destinatario.get(campo) or {}
    if not isinstance(documentado, Mapping):
        return None
    valor = documentado.get("valor")
    if not isinstance(valor, str) or not valor.strip():
        return None
    valor_normalizado = normalizador(valor)
    for evidencia in documentado.get("evidencia") or []:
        if not isinstance(evidencia, Mapping):
            continue
        pagina, literal = evidencia.get("pagina"), evidencia.get("literal")
        if type(pagina) is not int or pagina < 1 or not isinstance(literal, str):
            continue
        if valor_normalizado and valor_normalizado in normalizador(literal):
            return valor, dict(evidencia)
    return None


def _autoridad_dict(autoridad: AutoridadDocumentalFarmacia) -> dict[str, object]:
    return {
        "farmacia": autoridad.farmacia,
        "nif": autoridad.nif,
        "nombres": list(autoridad.nombres),
    }


def resolver_farmacia_documental(factura) -> ResolucionFarmaciaDocumental:
    """Resuelve la farmacia con evidencia explicable y precedencia del NIF."""
    destinatario = factura.get("destinatario") or {}
    if not isinstance(destinatario, Mapping):
        return ResolucionFarmaciaDocumental(None, "NO_DEMOSTRABLE", None, None, None, None)

    nif = _campo_con_evidencia(destinatario, "nif", _normalizar_nif)
    nombre = _campo_con_evidencia(destinatario, "nombre", _normalizar_nombre)

    # El NIF es la prueba maestra y no requiere coincidencia literal del nombre.
    if nif is not None:
        nif_normalizado = _normalizar_nif(nif[0])
        for autoridad in AUTORIDADES_DOCUMENTALES_FARMACIA.values():
            if nif_normalizado == _normalizar_nif(autoridad.nif):
                return ResolucionFarmaciaDocumental(
                    autoridad.farmacia,
                    "RESUELTA",
                    "destinatario.nif",
                    nif[0],
                    _autoridad_dict(autoridad),
                    nif[1],
                )

    if nombre is not None:
        nombre_normalizado = _normalizar_nombre(nombre[0])
        for autoridad in AUTORIDADES_DOCUMENTALES_FARMACIA.values():
            if nombre_normalizado not in {
                _normalizar_nombre(autorizado) for autorizado in autoridad.nombres
            }:
                continue
            if nif is not None:
                return ResolucionFarmaciaDocumental(
                    None,
                    "CONTRADICTORIA",
                    "destinatario.nif",
                    nif[0],
                    _autoridad_dict(autoridad),
                    nif[1],
                )
            return ResolucionFarmaciaDocumental(
                autoridad.farmacia,
                "RESUELTA",
                "destinatario.nombre",
                nombre[0],
                _autoridad_dict(autoridad),
                nombre[1],
            )

    campo, observado, provenance = (
        ("destinatario.nif", nif[0], nif[1]) if nif is not None
        else ("destinatario.nombre", nombre[0], nombre[1]) if nombre is not None
        else (None, None, None)
    )
    return ResolucionFarmaciaDocumental(
        None, "NO_DEMOSTRABLE", campo, observado, None, provenance
    )


def farmacia_destinatario(factura):
    """Compatibilidad: farmacia resuelta o estado fail-closed."""
    resolucion = resolver_farmacia_documental(factura)
    return resolucion.farmacia_documental or resolucion.estado


def validar_farmacia_antes_de_persistir(operativa, documento):
    """Valida TODAS las facturas antes de permitir cualquier escritura economica.

No admite farmacia declarada por filename ni un override de revision manual.
Una resolucion fiscal alternativa requiere un contrato documental explicitado.
"""
    if not isinstance(documento, Mapping) or not documento.get("facturas"):
        raise ErrorFarmaciaDocumental("FARMACIA_DOCUMENTO_NO_DEMOSTRABLE")
    for factura in documento["facturas"]:
        if not isinstance(factura, Mapping):
            raise ErrorFarmaciaDocumental("FARMACIA_DOCUMENTO_NO_DEMOSTRABLE")
        resolucion = resolver_farmacia_documental(factura)
        if resolucion.estado == "CONTRADICTORIA":
            raise ErrorFarmaciaDocumental("FARMACIA_DOCUMENTO_CONTRADICTORIA")
        documental = resolucion.farmacia_documental
        if documental is None:
            raise ErrorFarmaciaDocumental("FARMACIA_DOCUMENTO_NO_DEMOSTRABLE")
        if documental != operativa:
            raise ErrorFarmaciaDocumental("FARMACIA_DOCUMENTO_CONTRADICTORIA")
    return "CONSISTENTE"
