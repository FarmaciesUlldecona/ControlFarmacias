"""Tests del banco de pruebas 2AY (sin red, sin Supabase, sin Farmatic).

Ejecutar con: pytest pruebas/auditoria_2ay --basetemp=<dir>  (fuera de ``testpaths``).
"""
from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analisis_2ay as an  # noqa: E402
import banco_extraccion as be  # noqa: E402

ALLIANCE = be.ROOT / "pruebas/facturas/documentos/fixtures_2ap/alliance_apto_multifactura.pdf"


def test_cifs_en_texto_orden_y_sin_dni_de_la_farmacia():
    texto = "Emisor: B-17733601. Cliente NIF 40901058C. Otro ESA08008724 y B17733601"
    assert be.cifs_en_texto(texto) == ["B17733601", "A08008724"]


@pytest.mark.parametrize("caracteres,esperado", [
    ([10, 5], "TEXTO"), ([0, 0], "SIN_TEXTO"), ([0, 7], "MIXTO"), ([], "SIN_PAGINAS")])
def test_clasificar_capa_texto(caracteres, esperado):
    assert be.clasificar_capa_texto(caracteres) == esperado


def test_cuadre_fiscal():
    assert be.cuadre_fiscal(121.0, 100, 21, None, None) == {
        "evaluable": True, "suma": "121", "diferencia": "0.00", "cuadra_005": True}
    assert be.cuadre_fiscal(121.1, 100, 21, None, None)["cuadra_005"] is False
    assert be.cuadre_fiscal(None, 100, 21, None, None) == {"evaluable": False}


def test_tolerancias_candidatas():
    assert an.tolerancias(3) == {"T1": Decimal("0.05"), "T2": Decimal("0.03"), "T3": Decimal("0.03"),
                                 "R11": Decimal("0.05")}
    assert an.tolerancias(80) == {"T1": Decimal("0.05"), "T2": Decimal("0.80"), "T3": Decimal("0.50"),
                                  "R11": Decimal("0.50")}
    assert an.tolerancias(150)["T2"] == Decimal("1.00")


def _factura(**cambios):
    base = {"destinatario_con_evidencia": True, "destinatario_nif": "40901058-C", "destinatario_nombre": "",
            "incidencias_bloqueantes": [], "naturaleza_principal": "MERCANCIA", "total": "22.49",
            "base_imponible": "20.45", "iva": "2.04", "recargo_equivalencia": None, "otros": None,
            "proveedor_nombre": "ALLIANCE HEALTHCARE ESPANA, S.A.",
            "albaranes": [{"numero": "08M26924", "fecha": "2026-06-26", "importe_total": "12.45", "sentido": "CARGO"},
                          {"numero": "08C23236", "fecha": "2026-06-27", "importe_total": "10.04", "sentido": "CARGO"}],
            "movimientos": []}
    return {**base, **cambios}


def test_elegibilidad_replica_casos_principales():
    assert an.elegibilidad(_factura()) == ("APTA", "APTA_MERCANCIA")
    assert an.elegibilidad(_factura(albaranes=[])) == ("NO_APTA", "FALTAN_ALBARANES_MERCANCIA")
    assert an.elegibilidad(_factura(destinatario_nif="B12345678")) == ("NO_APTA", "FARMACIA_NO_CONSISTENTE")
    assert an.elegibilidad(_factura(destinatario_con_evidencia=False)) == ("NO_APTA", "FARMACIA_NO_DEMOSTRABLE")
    assert an.elegibilidad(_factura(naturaleza_principal=None)) == ("REQUIERE_REVISION", "TIPO_DOCUMENTAL_NO_DEMOSTRADO")
    mixta = _factura(naturaleza_principal="MIXTA", total="22.42",
                     movimientos=[{"descripcion": "SERVICIO", "sentido": "ABONO", "importe": "0.07", "base": None}],
                     base_imponible="20.38")
    assert an.elegibilidad(mixta) == ("APTA", "APTA_MIXTA")
    # Caso 08007969: 0,07 de diferencia documental supera la tolerancia fija 0,05.
    descuadre = {**mixta, "total": "22.49", "base_imponible": "20.45"}
    assert an.elegibilidad(descuadre) == ("NO_APTA", "TOTAL_NO_EXPLICADO")
    assert an.elegibilidad(descuadre, Decimal("0.10")) == ("APTA", "APTA_MIXTA")


def _operacional(numero, fecha, puc, contador):
    return {"id_contador": contador, "farmacia": "PIO", "id_proveedor": "2", "proveedor": "1.- SAFA",
            "numero_albaran": numero, "fecha": fecha, "importe_puc": puc, "importe_pvp": None, "estado": "PENDIENTE"}


def test_simular_conciliacion_reproduce_08007973():
    operacionales = an.candidatos_operacionales([
        _operacional("08M26924", "2026-06-26", "12.44", 280242), _operacional("08C23236", "2026-06-27", "10.05", 280269),
        _operacional("08M99999", "2026-09-01", "1.00", 1)])
    sim = an.simular_conciliacion(_factura(), operacionales)
    assert (sim["resultado_t1"], sim["diferencia"], sim["albaranes_casados"]) == ("CONCILIADA", "0.0000", 2)
    assert sim["matching"] == {"MATCH_UNICO": 2}


def test_simular_conciliacion_sin_albaranes_operacionales_da_diferencia():
    sim = an.simular_conciliacion(_factura(), [])
    assert (sim["resultado_t1"], sim["albaranes_casados"], sim["albaranes_sin_coincidencia"]) == ("DIFERENCIA", 0, 2)


def test_parche_2au_solo_en_memoria_y_se_restaura():
    sys.path.insert(0, str(be.ROOT))
    import src.facturas.motor_local.adaptadores.alliance as al

    tipos, clasificar = al.TIPOS_PEDIDO_MERCANCIA_ALLIANCE, al.clasificar_fila_economica_alliance
    fila = lambda tipo, sentido, total: {  # noqa: E731
        "sentido": {"valor": sentido, "evidencias": []}, "tipo_pedido": {"valor": tipo, "evidencias": []},
        "total": {"valor": total, "evidencias": []}}
    with be.parche_2au():
        assert al.clasificar_fila_economica_alliance(fila("DIRECTO", "CARGO", 10.0))["concepto"] == "ALBARAN_MERCANCIA"
        # 2AZ: la R10 final (COSTO TELEVENTA y SERVICIO COVID19 mercancia) ya esta en el adaptador.
        assert al.clasificar_fila_economica_alliance(fila("COSTO TELEVENTA", "CARGO", 6.51))["concepto"] == (
            "ALBARAN_MERCANCIA")
        assert al.clasificar_fila_economica_alliance(fila("ECOCEUTICS", "ABONO", -38.0))["concepto"] == "ABONO"
        assert al.clasificar_fila_economica_alliance(fila("SERVICIO COVID19", "CARGO", 15.91))["concepto"] == (
            "ALBARAN_MERCANCIA")
    assert al.TIPOS_PEDIDO_MERCANCIA_ALLIANCE is tipos and al.clasificar_fila_economica_alliance is clasificar
    assert clasificar(fila("TIPO NO CERTIFICADO", "CARGO", 10.0))["concepto"] == "NO_DEMOSTRABLE"


def test_salida_dentro_del_repositorio_rechazada():
    with pytest.raises(SystemExit, match="SALIDA_DENTRO_DEL_REPOSITORIO"):
        be._salida_fuera_del_repo(str(be.ROOT / "x.json"))


@pytest.mark.skipif(not ALLIANCE.exists(), reason="fixture local 2AP ausente (excluido de git)")
def test_cadena_oficial_alliance_autoriza_sin_red():
    resultado = be.analizar_documento(str(ALLIANCE))
    oficial = resultado["oficial"]
    assert (oficial["etapa_detencion"], oficial["motivo"], oficial["layout"]) == (
        "PREVIO_A_PERSISTIR_OK", "AUTORIZADO", "alliance-local")
    assert oficial["segmentos_autorizados"] and all(f["autorizable"] for f in oficial["facturas_normalizadas"])
    assert "simulado_2au" in resultado
