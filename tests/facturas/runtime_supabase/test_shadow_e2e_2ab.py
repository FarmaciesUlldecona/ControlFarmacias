from pruebas.auditoria_2ab.shadow_e2e import ejecutar_shadow


def test_cinco_patrones_productivos_shadow_sin_dml():
    result = ejecutar_shadow()
    assert result["productivo_dml"] is False
    assert len(result["persistencia_memoria"]) == 7
    assert result["hefame_mercancia"]["validos"] == 2
    assert result["hefame_mercancia"]["ausentes"] == 5
    assert result["hefame_mercancia"]["incompatibles"] == 2
    assert result["hplus_consumo"]["albaranes_operativos"] == 0
