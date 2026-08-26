from __future__ import annotations

from decimal import Decimal

from src.facturas.normalizador_v2.modelos import (
    EstadoValidacion, Evidencia, FacturaNormalizada, NaturalezaPrincipal,
    ResultadoControl, ResultadoValidacion, Tercero, Totales, ValorDocumentado,
)
from src.facturas.normalizador_v2.multifactura import consolidar_facturas


def vd(valor):
    return ValorDocumentado(valor=valor, literal=str(valor), evidencia=[Evidencia(pagina=1, literal=str(valor))])


def fac(numero, total, pagina, *, tipo="Factura", factura_id=None):
    return FacturaNormalizada(
        factura_id=factura_id or f"f-{pagina}-{numero}", tipo_documento=vd(tipo),
        naturaleza_principal=NaturalezaPrincipal.MERCANCIA, estado_validacion=EstadoValidacion.VALIDADA,
        requiere_conciliacion_albaranes=True, pagina_inicio=pagina, pagina_fin=pagina,
        proveedor=Tercero(nombre=vd("FEDEFARMA"), alias_funcional="FEDEFARMA"),
        numero_factura=vd(numero) if numero is not None else None, totales=Totales(total=vd(Decimal(total))),
        validaciones=[ResultadoValidacion(codigo="X", resultado=ResultadoControl.OK, descripcion="x", regla_version="v2")],
    )


def test_cero_facturas():
    assert consolidar_facturas([]).facturas == ()


def test_tres_facturas_y_portada_fedefarma_no_cuatro():
    entrada = [fac(None, "409.58", 1, tipo="Portada resumen"), fac("F1", "19.96", 2), fac("F2", "81.07", 3), fac("F3", "308.55", 4)]
    resultado = consolidar_facturas(entrada)
    assert [f.numero_factura.valor for f in resultado.facturas] == ["F1", "F2", "F3"]
    assert len(resultado.descartes) == 1 and resultado.descartes[0].suma_facturas == Decimal("409.58")


def test_portada_no_se_descarta_si_no_cuadra():
    resultado = consolidar_facturas([fac(None, "400", 1, tipo="Resumen"), fac("F1", "19.96", 2)])
    assert len(resultado.facturas) == 2 and resultado.descartes == ()


def test_identificadores_compuestos_se_preservan_y_no_fusionan():
    resultado = consolidar_facturas([fac("P PA 2620-2173388", "10", 1), fac("P RE 2605-0221864", "10", 2)])
    assert [f.numero_factura.valor for f in resultado.facturas] == ["P PA 2620-2173388", "P RE 2605-0221864"]


def test_duplicado_identico_se_reduce_deterministicamente():
    a = fac("F1", "10", 1, factura_id="a")
    b = fac("F1", "10", 1, factura_id="b")
    resultado = consolidar_facturas([b, a])
    assert len(resultado.facturas) == 1 and resultado.facturas[0].factura_id == "a"


def test_conflicto_misma_clave_se_conserva_como_revision_determinista():
    resultado = consolidar_facturas([fac("F1", "11", 2, factura_id="b"), fac("F1", "10", 1, factura_id="a")])
    assert len(resultado.facturas) == 1
    assert resultado.facturas[0].totales.total.valor == Decimal("10")
    assert resultado.facturas[0].estado_validacion == EstadoValidacion.REQUIERE_REVISION
    assert resultado.conflictos == ("FEDEFARMA|F1",)


def test_fecha_importe_no_fusionan_numeros_distintos():
    resultado = consolidar_facturas([fac("F1", "10", 1), fac("F2", "10", 2)])
    assert len(resultado.facturas) == 2
