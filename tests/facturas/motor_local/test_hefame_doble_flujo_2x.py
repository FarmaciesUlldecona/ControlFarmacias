from datetime import date
from decimal import Decimal
from pathlib import Path

from src.facturas.clasificacion_documental import (
    TipoFacturaDocumental,
    clasificar_factura_por_contenido,
)
from src.facturas.grupos_funcionales import (
    TipoEconomicoHefame,
    clasificar_grupo_hefame,
)
from src.facturas.motor_local.adaptadores.hplus_consumo import AdaptadorHplusConsumo
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.servicio import MotorDocumentoLocal, hash_funcional
from src.facturas.runtime_supabase.conciliacion import (
    AjusteDocumentalTrabajo,
    AlbaranDocumentalTrabajo,
    CandidatoAlbaranSupabase,
    MovimientoDocumentalTrabajo,
    buscar_candidato_albaran,
    canonicalizar_proveedor,
    conciliar_movimientos_documentales,
)


ROOT = Path(__file__).resolve().parents[3]
ANTIGUO = ROOT / "tmp/pdfs/hito_2i3/hefame_antiguo.pdf"
NUEVO = ROOT / "tmp/pdfs/hito_2i3/hefame_nuevo.pdf"


def extraer(path):
    return MotorDocumentoLocal(BackendPdfium()).extraer(path)


def test_f30004444_es_hefame_mercancia():
    r = extraer(ANTIGUO)
    identidad = r.cabecera["grupo_funcional"]
    assert identidad["tipo_economico"] == "HEFAME_MERCANCIA"
    assert identidad["nif_documental"] == "F30004444"
    assert len(r.albaranes) == 9


def test_b30462451_es_hefame_consumibles():
    r = extraer(NUEVO)
    identidad = r.cabecera["grupo_funcional"]
    assert identidad["tipo_economico"] == "HEFAME_CONSUMIBLES"
    assert identidad["nif_documental"] == "B30462451"


def test_ambos_comparten_grupo_funcional_hefame():
    assert {extraer(p).cabecera["grupo_funcional"]["grupo_funcional"] for p in (ANTIGUO, NUEVO)} == {"HEFAME"}


def test_identidades_fiscales_permanecen_separadas():
    resultados = [extraer(p) for p in (ANTIGUO, NUEVO)]
    assert [r.cabecera["proveedor"]["nif"]["valor"] for r in resultados] == ["F30004444", "B30462451"]
    assert resultados[0].cabecera["proveedor"]["nombre"]["valor"] != resultados[1].cabecera["proveedor"]["nombre"]["valor"]


def test_hefame_mercancia_exige_albaranes():
    sin_albaranes = clasificar_factura_por_contenido([], [], tipo_funcional="HEFAME_MERCANCIA")
    con_albaranes = clasificar_factura_por_contenido([object()], [], tipo_funcional="HEFAME_MERCANCIA")
    assert sin_albaranes.tipo == TipoFacturaDocumental.TIPO_NO_DEMOSTRADO
    assert sin_albaranes.requiere_revision
    assert con_albaranes.tipo == TipoFacturaDocumental.FACTURA_MERCANCIA


def test_hefame_consumibles_no_exige_albaranes_y_lista_vacia_es_valida():
    clasificacion = clasificar_factura_por_contenido([], [], tipo_funcional="HEFAME_CONSUMIBLES")
    assert clasificacion.tipo == TipoFacturaDocumental.FACTURA_GASTO_SERVICIO
    assert not clasificacion.mercancia_demostrada
    assert not clasificacion.requiere_revision


def test_consumibles_no_publica_albaranes_operativos_ni_no_localizados():
    r = extraer(NUEVO)
    assert r.albaranes == []
    assert len(r.facturas[0]["referencias_documentales"]) == 2
    assert all(not x["requiere_match_operativo"] for x in r.facturas[0]["referencias_documentales"])
    assert not any(i["codigo"] == "ALBARAN_NO_LOCALIZADO" for i in r.incidencias)


def test_mercancia_sin_trazabilidad_queda_pendiente():
    resultado = clasificar_factura_por_contenido([], [], tipo_funcional="HEFAME_MERCANCIA")
    assert resultado.requiere_revision and resultado.tipo == TipoFacturaDocumental.TIPO_NO_DEMOSTRADO


def test_consumibles_con_economia_completa_concilia_sin_albaranes():
    r = extraer(NUEVO)
    assert r.documento_completo_demostrado
    assert all(c["estado"] == "OK" for c in r.controles_conciliacion)
    resultado = conciliar_movimientos_documentales(
        Decimal("66.79"),
        [MovimientoDocumentalTrabajo("m1", "CONSUMIBLES", "SERVICIO", "CARGO", base=Decimal("55.20"))],
        ajustes=[AjusteDocumentalTrabajo("IVA_TOTAL", Decimal("11.59"), {"fuente": "PDF"})],
    )
    assert resultado.resultado == "CONCILIADA" and resultado.diferencia == Decimal("0.0000")


def test_filename_no_influye_en_reconocimiento_ni_hash_funcional():
    backend = BackendPdfium()
    documento = backend.cargar_pdf(NUEVO)
    adaptador = AdaptadorHplusConsumo()
    assert adaptador.reconocer(documento).estado == "RECONOCIDO"
    documento.ruta = "nombre_totalmente_ajeno.pdf"
    assert adaptador.reconocer(documento).estado == "RECONOCIDO"
    motor = MotorDocumentoLocal(backend)
    assert hash_funcional(motor.extraer(NUEVO)) == hash_funcional(motor.extraer(NUEVO))


def test_clasificacion_no_confunde_nif_ni_layout():
    assert clasificar_grupo_hefame(
        proveedor_documental="H+ Consumo", nif_documental="B30462451",
        layout="hefame-local", contenido_consumibles_demostrado=True,
    ) is None
    assert clasificar_grupo_hefame(
        proveedor_documental="HEFAME", nif_documental="F30004444",
        layout="hplus-consumo-local", contenido_consumibles_demostrado=True,
    ) is None


def test_alias_operativo_hefame_mercancia_no_fusiona_consumibles():
    assert canonicalizar_proveedor("HDAD.FMCTCA.MEDIT.,S.C.L.") == canonicalizar_proveedor("3.- HEFAME")
    assert canonicalizar_proveedor("ARTICULOS DE CONSUMO INTERHOGAR S.L.") != canonicalizar_proveedor("3.- HEFAME")


def test_hefame_mercancia_no_acepta_match_solo_por_importe_con_otro_numero():
    documental = AlbaranDocumentalTrabajo(
        "d1", "4127726806", date(2026, 8, 28), Decimal("3.45"), "CARGO",
    )
    candidato = CandidatoAlbaranSupabase(
        1, "PIO", "3", "3.- HEFAME", "OTRO-NUMERO",
        date(2026, 8, 28), Decimal("3.45"), Decimal("4.00"), "ACTIVO",
    )
    resultado = buscar_candidato_albaran(
        documental, [candidato], proveedor_literal="HDAD.FMCTCA.MEDIT.,S.C.L.",
    )
    assert resultado.estado == "NUMERO_AUSENTE"
    assert resultado.candidato is None


def test_extraccion_hplus_certificada_completa():
    r = extraer(NUEVO)
    assert r.documento["layout"] == "hplus-consumo-local"
    assert r.cabecera["numero_factura"]["valor"] == "1132029554"
    assert r.cabecera["fecha_factura"]["valor"] == "2026-08-31"
    assert r.cabecera["base_imponible_total"]["valor"] == 55.20
    assert r.cabecera["iva_total"]["valor"] == 11.59
    assert r.cabecera["recargo_equivalencia_total"]["valor"] == 0.0
    assert r.cabecera["importe_total"]["valor"] == 66.79
    assert r.vencimientos[0]["fecha"]["valor"] == "2026-09-05"
    assert r.vencimientos[0]["importe"]["valor"] == 66.79
    assert len(r.facturas[0]["lineas_consumibles"]) == 3
