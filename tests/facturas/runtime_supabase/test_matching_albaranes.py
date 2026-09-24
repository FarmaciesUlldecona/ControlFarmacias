from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.facturas.runtime_supabase.conciliacion import (
    AlbaranDocumentalTrabajo,
    CandidatoAlbaranSupabase,
    buscar_candidato_albaran,
    comparar_numeros_albaran,
    detalle_desde_busqueda,
)
from src.facturas.runtime_supabase.modelos import (
    TipoRelacionConciliacion,
    conservar_id_proveedor,
)


def documental(
    numero: str = "9319977575",
    importe: str = "448.00",
    fecha: date = date(2026, 7, 29),
    sentido: str | None = None,
) -> AlbaranDocumentalTrabajo:
    return AlbaranDocumentalTrabajo("extraido-1", numero, fecha, Decimal(importe), sentido)


def candidato(
    *,
    contador: int = 285484,
    proveedor: str = "LOGISTAPHARMA",
    id_proveedor: str = "158",
    numero: str = "19977575",
    fecha: date = date(2026, 8, 4),
    puc: str = "448.00",
) -> CandidatoAlbaranSupabase:
    return CandidatoAlbaranSupabase(
        contador,
        "PIO",
        id_proveedor,
        proveedor,
        numero,
        fecha,
        Decimal(puc),
        Decimal("1048.40"),
        "PENDIENTE",
    )


def buscar(doc=None, rows=None, **kwargs):
    return buscar_candidato_albaran(
        doc or documental(),
        [candidato()] if rows is None else rows,
        proveedor_literal=kwargs.pop("proveedor_literal", "LOGISTA PHARMA S.A.U."),
        **kwargs,
    )


def test_numero_exacto_produce_match() -> None:
    result = buscar(doc=documental(numero="19977575"))
    assert result.estado == "MATCH_UNICO"
    assert result.coincidencia_numero == "EXACTA"


def test_variante_legitima_de_separadores_produce_match() -> None:
    result = buscar(
        doc=documental(numero="AB-0001"),
        rows=[candidato(numero="ab 0001")],
    )
    assert comparar_numeros_albaran("AB-0001", "ab 0001") == "EXACTA"
    assert result.estado == "MATCH_UNICO"
    assert result.coincidencia_numero == "EXACTA"


def test_afijo_no_se_declara_equivalente_sin_regla_demostrada() -> None:
    result = buscar()
    assert comparar_numeros_albaran("9319977575", "19977575") == "DIFERENTE"
    assert result.estado == "MATCH_UNICO"
    assert result.coincidencia_numero == "DIFERENTE"


@pytest.mark.parametrize("importe", ["447.95", "448.05"])
def test_importe_en_frontera_inclusiva_de_cinco_centimos_produce_match(importe: str) -> None:
    assert buscar(rows=[candidato(puc=importe)]).estado == "MATCH_UNICO"


def test_importe_superior_a_cinco_centimos_no_es_igualdad_economica() -> None:
    result = buscar(rows=[candidato(puc="448.051")])
    assert result.estado == "SIN_COINCIDENCIA"
    assert result.candidatos_importe == 0


def test_proveedor_distinto_no_produce_match() -> None:
    result = buscar(rows=[candidato(proveedor="OTRO PROVEEDOR")])
    assert result.estado == "SIN_COINCIDENCIA"
    assert result.candidatos_proveedor == 0


def test_sentido_desconocido_no_elimina_candidato() -> None:
    result = buscar(doc=documental(sentido=None))
    detail = detalle_desde_busqueda(documental(sentido=None), result)
    assert result.estado == "MATCH_UNICO"
    assert detail.tipo_relacion == TipoRelacionConciliacion.UNO_A_UNO


def test_candidato_inexistente_genera_sin_coincidencia() -> None:
    result = buscar(rows=[])
    detail = detalle_desde_busqueda(documental(), result)
    assert result.estado == "SIN_COINCIDENCIA"
    assert detail.tipo_relacion == TipoRelacionConciliacion.SIN_COINCIDENCIA


def test_multiples_candidatos_equivalentes_quedan_ambiguos() -> None:
    rows = [
        candidato(contador=1, numero="19977575"),
        candidato(contador=2, numero="19977575"),
    ]
    result = buscar(doc=documental(numero="19977575"), rows=rows)
    assert result.estado == "AMBIGUO"
    assert result.candidato is None


@pytest.mark.parametrize("literal", ["00158", "ABC158", "158"])
def test_id_proveedor_conserva_ceros_y_letras(literal: str) -> None:
    assert conservar_id_proveedor(literal) == literal
    assert candidato(id_proveedor=literal).id_proveedor == literal


def test_caso_sintetico_equivalente_logista_448() -> None:
    result = buscar()
    detail = detalle_desde_busqueda(documental(), result)
    assert result.estado == "MATCH_UNICO"
    assert result.candidato is not None
    assert result.candidato.id_contador == 285484
    assert result.importe_compatible == Decimal("448.0000")
    assert result.coincidencia_numero == "DIFERENTE"
    assert detail.importe_aplicado == Decimal("448.0000")
    assert detail.coincidencia_numero_literal is False


def test_numero_no_exacto_no_bloquea_evidencia_economica_unica() -> None:
    result = buscar(rows=[candidato(numero="OTRO-IDENTIFICADOR")])
    assert result.estado == "MATCH_UNICO"
    assert result.coincidencia_numero == "DIFERENTE"


def test_farmatic_id_proveedor_tiene_prioridad_y_es_literal() -> None:
    result = buscar(
        rows=[candidato(id_proveedor="00158", proveedor="NOMBRE DISTINTO")],
        farmatic_id_proveedor="00158",
    )
    assert result.estado == "MATCH_UNICO"


@pytest.mark.parametrize("dias", [-15, 15])
def test_limite_inclusivo_de_ventana_temporal_produce_match(dias: int) -> None:
    base = date(2026, 7, 29)
    row = candidato(fecha=date.fromordinal(base.toordinal() + dias))
    assert buscar(rows=[row]).estado == "MATCH_UNICO"


def test_fuera_de_ventana_temporal_no_produce_match() -> None:
    assert buscar(rows=[candidato(fecha=date(2026, 8, 14))]).estado == "SIN_COINCIDENCIA"
