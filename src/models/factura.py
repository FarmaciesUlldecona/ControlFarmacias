from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any


def convertir_decimal(valor: Any) -> Decimal | None:
    """
    Convierte números o textos numéricos a Decimal.

    Devuelve None cuando el valor recibido es None.
    """
    if valor is None:
        return None

    if isinstance(valor, Decimal):
        return valor

    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError(f"Importe decimal no válido: {valor!r}") from error


def convertir_fecha(valor: Any) -> date | None:
    """
    Convierte una fecha ISO YYYY-MM-DD a datetime.date.

    Devuelve None cuando el valor recibido es None.
    """
    if valor is None:
        return None

    if isinstance(valor, date):
        return valor

    if not isinstance(valor, str):
        raise ValueError(f"Fecha no válida: {valor!r}")

    try:
        return date.fromisoformat(valor)
    except ValueError as error:
        raise ValueError(
            f"Fecha no válida: {valor!r}. Debe usar formato YYYY-MM-DD."
        ) from error


def serializar_valor(valor: Any) -> Any:
    """
    Convierte fechas, decimales, listas y diccionarios a valores
    compatibles con JSON.
    """
    if isinstance(valor, Decimal):
        return float(valor)

    if isinstance(valor, date):
        return valor.isoformat()

    if isinstance(valor, list):
        return [serializar_valor(elemento) for elemento in valor]

    if isinstance(valor, dict):
        return {
            clave: serializar_valor(elemento)
            for clave, elemento in valor.items()
        }

    return valor


@dataclass(slots=True)
class DestinatarioFactura:
    id_farmacia: str | None
    nombre: str | None
    cif: str | None
    metodo_identificacion: str | None

    @classmethod
    def desde_diccionario(
        cls,
        datos: dict[str, Any] | None,
    ) -> DestinatarioFactura | None:
        if datos is None:
            return None

        return cls(
            id_farmacia=datos.get("id_farmacia"),
            nombre=datos.get("nombre"),
            cif=datos.get("cif"),
            metodo_identificacion=datos.get("metodo_identificacion"),
        )


@dataclass(slots=True)
class VencimientoFactura:
    orden: int
    fecha_vencimiento: date | None
    importe: Decimal | None
    origen_fecha: str | None = None
    nota: str | None = None

    @classmethod
    def desde_diccionario(
        cls,
        datos: dict[str, Any],
    ) -> VencimientoFactura:
        return cls(
            orden=int(datos["orden"]),
            fecha_vencimiento=convertir_fecha(
                datos.get("fecha_vencimiento")
            ),
            importe=convertir_decimal(datos.get("importe")),
            origen_fecha=datos.get("origen_fecha"),
            nota=datos.get("nota"),
        )


@dataclass(slots=True)
class ImpuestoFactura:
    orden: int
    base_imponible: Decimal | None
    tipo_iva: Decimal | None
    cuota_iva: Decimal | None
    tipo_recargo_equivalencia: Decimal | None
    cuota_recargo_equivalencia: Decimal | None
    nota: str | None = None

    @classmethod
    def desde_diccionario(
        cls,
        datos: dict[str, Any],
    ) -> ImpuestoFactura:
        return cls(
            orden=int(datos["orden"]),
            base_imponible=convertir_decimal(
                datos.get("base_imponible")
            ),
            tipo_iva=convertir_decimal(datos.get("tipo_iva")),
            cuota_iva=convertir_decimal(datos.get("cuota_iva")),
            tipo_recargo_equivalencia=convertir_decimal(
                datos.get("tipo_recargo_equivalencia")
            ),
            cuota_recargo_equivalencia=convertir_decimal(
                datos.get("cuota_recargo_equivalencia")
            ),
            nota=datos.get("nota"),
        )


@dataclass(slots=True)
class AlbaranFactura:
    orden: int
    numero_albaran: str | None
    fecha_albaran: date | None
    tipo_movimiento: str | None
    importe_base: Decimal | None
    importe_total: Decimal | None
    descripcion: str | None = None

    @classmethod
    def desde_diccionario(
        cls,
        datos: dict[str, Any],
    ) -> AlbaranFactura:
        return cls(
            orden=int(datos["orden"]),
            numero_albaran=datos.get("numero_albaran"),
            fecha_albaran=convertir_fecha(datos.get("fecha_albaran")),
            tipo_movimiento=datos.get("tipo_movimiento"),
            importe_base=convertir_decimal(datos.get("importe_base")),
            importe_total=convertir_decimal(datos.get("importe_total")),
            descripcion=datos.get("descripcion"),
        )


@dataclass(slots=True)
class AjusteFactura:
    orden: int
    tipo_ajuste: str | None
    descripcion: str | None
    importe: Decimal | None
    incluido_en_base: bool | None
    incluido_en_total: bool | None

    @classmethod
    def desde_diccionario(
        cls,
        datos: dict[str, Any],
    ) -> AjusteFactura:
        return cls(
            orden=int(datos["orden"]),
            tipo_ajuste=datos.get("tipo_ajuste"),
            descripcion=datos.get("descripcion"),
            importe=convertir_decimal(datos.get("importe")),
            incluido_en_base=datos.get("incluido_en_base"),
            incluido_en_total=datos.get("incluido_en_total"),
        )


@dataclass(slots=True)
class FacturaNormalizada:
    tipo_documento: str | None
    categoria: str | None
    requiere_conciliacion_albaranes: bool
    pagina_inicio: int
    pagina_fin: int

    proveedor_nombre: str | None
    proveedor_cif: str | None
    numero_factura: str | None
    fecha_factura: date | None

    base_imponible_total: Decimal | None
    iva_total: Decimal | None
    recargo_equivalencia_total: Decimal | None
    importe_total: Decimal | None

    vencimientos: list[VencimientoFactura] = field(default_factory=list)
    impuestos: list[ImpuestoFactura] = field(default_factory=list)
    albaranes: list[AlbaranFactura] = field(default_factory=list)
    ajustes: list[AjusteFactura] = field(default_factory=list)

    destinatario: DestinatarioFactura | None = None

    fecha_cargo: date | None = None
    periodo_facturacion_inicio: date | None = None
    periodo_facturacion_fin: date | None = None
    nota_revision: str | None = None

    @classmethod
    def desde_diccionario(
        cls,
        datos: dict[str, Any],
    ) -> FacturaNormalizada:
        return cls(
            tipo_documento=datos.get("tipo_documento"),
            categoria=datos.get("categoria"),
            requiere_conciliacion_albaranes=bool(
                datos.get("requiere_conciliacion_albaranes", False)
            ),
            pagina_inicio=int(datos["pagina_inicio"]),
            pagina_fin=int(datos["pagina_fin"]),
            proveedor_nombre=datos.get("proveedor_nombre"),
            proveedor_cif=datos.get("proveedor_cif"),
            numero_factura=datos.get("numero_factura"),
            fecha_factura=convertir_fecha(datos.get("fecha_factura")),
            base_imponible_total=convertir_decimal(
                datos.get("base_imponible_total")
            ),
            iva_total=convertir_decimal(datos.get("iva_total")),
            recargo_equivalencia_total=convertir_decimal(
                datos.get("recargo_equivalencia_total")
            ),
            importe_total=convertir_decimal(datos.get("importe_total")),
            vencimientos=[
                VencimientoFactura.desde_diccionario(elemento)
                for elemento in datos.get("vencimientos", [])
            ],
            impuestos=[
                ImpuestoFactura.desde_diccionario(elemento)
                for elemento in datos.get("impuestos", [])
            ],
            albaranes=[
                AlbaranFactura.desde_diccionario(elemento)
                for elemento in datos.get("albaranes", [])
            ],
            ajustes=[
                AjusteFactura.desde_diccionario(elemento)
                for elemento in datos.get("ajustes", [])
            ],
            destinatario=DestinatarioFactura.desde_diccionario(
                datos.get("destinatario")
            ),
            fecha_cargo=convertir_fecha(datos.get("fecha_cargo")),
            periodo_facturacion_inicio=convertir_fecha(
                datos.get("periodo_facturacion_inicio")
            ),
            periodo_facturacion_fin=convertir_fecha(
                datos.get("periodo_facturacion_fin")
            ),
            nota_revision=datos.get("nota_revision"),
        )

    def validar(self) -> list[str]:
        """
        Devuelve una lista de errores estructurales de la factura.

        Una lista vacía significa que la estructura es válida.
        """
        errores: list[str] = []

        if self.pagina_inicio < 1:
            errores.append("pagina_inicio debe ser igual o superior a 1.")

        if self.pagina_fin < self.pagina_inicio:
            errores.append(
                "pagina_fin no puede ser anterior a pagina_inicio."
            )

        if not self.tipo_documento:
            errores.append("Falta tipo_documento.")

        if not self.proveedor_nombre:
            errores.append("Falta proveedor_nombre.")

        if not self.numero_factura:
            errores.append("Falta numero_factura.")

        if self.destinatario is None:
            errores.append("Falta destinatario.")
        elif not self.destinatario.id_farmacia:
            errores.append("Falta destinatario.id_farmacia.")

        errores.extend(
            validar_ordenes(
                elementos=self.vencimientos,
                nombre_coleccion="vencimientos",
            )
        )
        errores.extend(
            validar_ordenes(
                elementos=self.impuestos,
                nombre_coleccion="impuestos",
            )
        )
        errores.extend(
            validar_ordenes(
                elementos=self.albaranes,
                nombre_coleccion="albaranes",
            )
        )
        errores.extend(
            validar_ordenes(
                elementos=self.ajustes,
                nombre_coleccion="ajustes",
            )
        )

        return errores

    def a_diccionario(self) -> dict[str, Any]:
        return serializar_valor(asdict(self))


@dataclass(slots=True)
class DocumentoFacturas:
    archivo: str
    tipo_contenido: str
    numero_paginas: int
    necesita_lectura_visual: bool
    cantidad_documentos_esperados: int
    facturas: list[FacturaNormalizada] = field(default_factory=list)

    @classmethod
    def desde_diccionario(
        cls,
        datos: dict[str, Any],
    ) -> DocumentoFacturas:
        return cls(
            archivo=str(datos["archivo"]),
            tipo_contenido=str(datos["tipo_contenido"]),
            numero_paginas=int(datos["numero_paginas"]),
            necesita_lectura_visual=bool(
                datos.get("necesita_lectura_visual", False)
            ),
            cantidad_documentos_esperados=int(
                datos["cantidad_documentos_esperados"]
            ),
            facturas=[
                FacturaNormalizada.desde_diccionario(elemento)
                for elemento in datos.get("facturas", [])
            ],
        )

    def validar(self) -> list[str]:
        errores: list[str] = []

        if not self.archivo.strip():
            errores.append("El documento no tiene nombre de archivo.")

        if self.numero_paginas < 1:
            errores.append(
                f"{self.archivo}: numero_paginas debe ser superior a 0."
            )

        if self.cantidad_documentos_esperados != len(self.facturas):
            errores.append(
                f"{self.archivo}: cantidad_documentos_esperados="
                f"{self.cantidad_documentos_esperados}, pero contiene "
                f"{len(self.facturas)} facturas."
            )

        for indice, factura in enumerate(self.facturas, start=1):
            for error in factura.validar():
                errores.append(
                    f"{self.archivo} - factura {indice}: {error}"
                )

        return errores

    def a_diccionario(self) -> dict[str, Any]:
        return serializar_valor(asdict(self))


@dataclass(slots=True)
class PatronFacturas:
    version_patron: str
    farmacia: str
    moneda: str
    criterios_generales: dict[str, Any]
    documentos: list[DocumentoFacturas] = field(default_factory=list)

    @classmethod
    def desde_diccionario(
        cls,
        datos: dict[str, Any],
    ) -> PatronFacturas:
        return cls(
            version_patron=str(datos["version_patron"]),
            farmacia=str(datos["farmacia"]),
            moneda=str(datos["moneda"]),
            criterios_generales=dict(
                datos.get("criterios_generales", {})
            ),
            documentos=[
                DocumentoFacturas.desde_diccionario(elemento)
                for elemento in datos.get("documentos", [])
            ],
        )

    def validar(self) -> list[str]:
        errores: list[str] = []

        if not self.version_patron.strip():
            errores.append("Falta version_patron.")

        if not self.farmacia.strip():
            errores.append("Falta farmacia.")

        if not self.moneda.strip():
            errores.append("Falta moneda.")

        archivos_encontrados: set[str] = set()

        for documento in self.documentos:
            if documento.archivo in archivos_encontrados:
                errores.append(
                    f"Documento duplicado en el patrón: "
                    f"{documento.archivo}"
                )

            archivos_encontrados.add(documento.archivo)
            errores.extend(documento.validar())

        return errores

    def total_archivos(self) -> int:
        return len(self.documentos)

    def total_facturas(self) -> int:
        return sum(
            len(documento.facturas)
            for documento in self.documentos
        )

    def a_diccionario(self) -> dict[str, Any]:
        return serializar_valor(asdict(self))


def validar_ordenes(
    elementos: list[Any],
    nombre_coleccion: str,
) -> list[str]:
    """
    Comprueba que los elementos estén numerados desde 1,
    sin duplicados ni saltos.
    """
    if not elementos:
        return []

    ordenes = [elemento.orden for elemento in elementos]
    ordenes_esperados = list(range(1, len(elementos) + 1))

    if ordenes != ordenes_esperados:
        return [
            f"{nombre_coleccion} tiene órdenes incorrectos: "
            f"{ordenes}. Se esperaba {ordenes_esperados}."
        ]

    return []