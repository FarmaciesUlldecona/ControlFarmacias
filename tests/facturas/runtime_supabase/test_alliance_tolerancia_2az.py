"""Hito 2AZ: R10 (tipos de pedido Alliance y filas 0,00), D8, R14 (vencimientos), D11
(emparejamiento solo por PUC sin numero exacto), R11 (tolerancia proporcional),
R12 (construccion pura del enriquecimiento) y comprobaciones estaticas de la 20.

Las filas de R10 usan literales reales del corpus PIO. Los casos con PDF real usan
fixtures locales excluidos de git (skip si faltan). Sin red, Supabase ni Farmatic.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.facturas.motor_local.adaptadores import alliance as al
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.servicio import MotorDocumentoLocal
from src.facturas.runtime_supabase.conciliacion import (
    AlbaranDocumentalTrabajo, CandidatoAlbaranSupabase, ReglaTolerancia, buscar_candidato_albaran, conciliar_importes)
from src.facturas.runtime_supabase.enriquecimiento import clave_idempotente_enriquecimiento, construir_enriquecimiento
from src.facturas.runtime_supabase.modelos import DetalleConciliacion, TipoRelacionConciliacion
from src.facturas.runtime_supabase.multifactura import adaptar_resultado_local

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "pruebas/facturas/documentos/fixtures_2ap"
PDF_2AO = FIXTURES / "alliance_2ao_cinco_facturas.pdf"
PDF_08007501 = FIXTURES / "alliance_2az_08007501.pdf"
PDF_08011733 = FIXTURES / "alliance_2az_08011733.pdf"
ALBARANES = FIXTURES / "albaranes_2az.json"
MIG20 = ROOT / "sql/migrations/20_cf_alliance_tolerancia_enriquecimiento.sql"
ROLLBACK20 = ROOT / "sql/migrations/20_cf_alliance_tolerancia_enriquecimiento.rollback.sql"
SAFA = "1.- SAFA"
ALLIANCE = "ALLIANCE HEALTHCARE ESPANA, S.A."


def _fila(tipo, sentido, total):
    return {"sentido": {"valor": sentido, "evidencias": []}, "tipo_pedido": {"valor": tipo, "evidencias": []},
            "total": {"valor": total, "evidencias": []}}


# ----------------------------------------------------------------- R10 con filas reales del corpus

@pytest.mark.parametrize("tipo,sentido,total,concepto", [
    ("DIRECTO", "CARGO", 191.84, "ALBARAN_MERCANCIA"),              # 08C18299 (08007971)
    ("ENCARGO VACUNAS", "CARGO", 415.61, "ALBARAN_MERCANCIA"),      # 08008834
    ("MIS RESERVAS", "CARGO", 35.2, "ALBARAN_MERCANCIA"),           # 08010085
    ("TELEVENTA 2", "CARGO", 175.15, "ALBARAN_MERCANCIA"),          # 08006570
    ("COSTO TELEVENTA", "CARGO", 6.51, "ALBARAN_MERCANCIA"),        # 08B96275 (08007501)
    ("SERVICIO COVID19", "CARGO", 15.91, "ALBARAN_MERCANCIA"),      # 08D32860 (08011733)
    ("ECOCEUTICS", "ABONO", -59.42, "ABONO"),                       # 08B83180 (08006571)
    ("ECOCEUTICS", "CARGO", 12.0, "ALBARAN_MERCANCIA"),             # certificado previo
    ("COSTO TELEVENTA", "CARGO", 0.0, "INFORMATIVA_IMPORTE_CERO"),  # 08B96274 / 08B79008
    ("DIRECTO", "ABONO", 0.0, "INFORMATIVA_IMPORTE_CERO"),
    ("TIPO DESCONOCIDO", "CARGO", 10.0, "NO_DEMOSTRABLE"),
    ("DIRECTO", "ABONO", -5.0, "NO_DEMOSTRABLE"),                   # abono no certificado
])
def test_r10_clasificacion_con_filas_reales(tipo, sentido, total, concepto):
    r = al.clasificar_fila_economica_alliance(_fila(tipo, sentido, total))
    assert r["concepto"] == concepto
    if concepto == "ABONO":
        assert r["categoria_movimiento"] == "ABONO_COMERCIAL"
    if concepto == "NO_DEMOSTRABLE" and tipo == "TIPO DESCONOCIDO":
        assert al.MOTIVO_NO_PROMOCION[r["regla"]] == "TIPO_PEDIDO_NO_CERTIFICADO"


def _extraer(pdf: Path):
    if not pdf.exists():
        pytest.skip(f"fixture local ausente (excluido de git): {pdf.name}")
    local = MotorDocumentoLocal(BackendPdfium()).extraer(pdf)
    return local, adaptar_resultado_local(local)


def _raw(local, numero):
    return next(f for f in local.facturas if f["cabecera"]["numero_factura"]["valor"] == numero)


def _norm(doc, numero):
    return next(f for f in doc["facturas"] if f["numero_factura"]["valor"] == numero)


def test_d8_tipo_no_certificado_lleva_motivo_y_literal(monkeypatch):
    if not PDF_2AO.exists():
        pytest.skip("fixture 2AO ausente")
    monkeypatch.setattr(al, "TIPOS_PEDIDO_MERCANCIA_ALLIANCE", al.TIPOS_PEDIDO_MERCANCIA_ALLIANCE - {"DIRECTO"})
    local, _ = _extraer(PDF_2AO)
    raw = _raw(local, "08007971")
    [inc] = [i for i in raw["incidencias"] if i["codigo"] == "CANDIDATO_ALBARAN_NO_PROMOVIDO"]
    assert inc == {"codigo": "CANDIDATO_ALBARAN_NO_PROMOVIDO", "cantidad": 3, "bloqueante": False,
                   "motivo": "TIPO_PEDIDO_NO_CERTIFICADO", "tipos_pedido": ["DIRECTO"]}
    assert raw["albaranes"] == []


def test_r10_08007971_promueve_los_3_directo():
    local, doc = _extraer(PDF_2AO)
    raw = _raw(local, "08007971")
    assert [a["numero_albaran"]["valor"] for a in raw["albaranes"]] == ["08C18299", "08M24229", "08M25574"]
    assert not [i for i in raw["incidencias"] if i["codigo"] == "CANDIDATO_ALBARAN_NO_PROMOVIDO"]
    assert local.documento["layout_version"] == "1.3.0"
    assert doc["metadata_tecnica"]["version_normalizador"] == "multifactura-local-2"


def test_r10_08007501_costo_televenta_promovido_y_ceros_informativos():
    local, doc = _extraer(PDF_08007501)
    raw = _raw(local, "08007501")
    assert [(a["numero_albaran"]["valor"], a["total"]["valor"]) for a in raw["albaranes"]] == [("08B96275", 6.51)]
    [inc] = [i for i in raw["incidencias"] if i["codigo"] == "FILA_IMPORTE_CERO_INFORMATIVA"]
    assert (inc["bloqueante"], inc["referencias"]) == (False, ["08B96274"])
    f = _norm(doc, "08007501")
    assert f["naturaleza_principal"] == "MERCANCIA" and len(f["albaranes"]) == 1
    assert f["movimientos_comerciales"] == []
    assert f["estado_validacion"] in {"VALIDADA", "VALIDADA_CON_INCIDENCIAS"}
    assert not any(i["bloqueante"] for i in f["incidencias"])
    # Elegibilidad (replica de la migracion 14 del banco 2AY): APTA_MERCANCIA.
    sys.path.insert(0, str(ROOT / "pruebas/auditoria_2ay"))
    from analisis_2ay import elegibilidad
    from banco_extraccion import _resumen_normalizada
    assert elegibilidad(_resumen_normalizada(f)) == ("APTA", "APTA_MERCANCIA")


def _operacionales():
    if not ALBARANES.exists():
        pytest.skip("instantanea local de albaranes ausente")
    sys.path.insert(0, str(ROOT / "pruebas/auditoria_2ay"))
    from analisis_2ay import candidatos_operacionales
    return candidatos_operacionales(json.loads(ALBARANES.read_text(encoding="utf-8"))["albaranes"])


def test_r10_08011733_servicio_covid19_promovido_y_diferencia_2_16():
    local, doc = _extraer(PDF_08011733)
    raw = _raw(local, "08011733")
    assert "08D32860" in [a["numero_albaran"]["valor"] for a in raw["albaranes"]]
    sys.path.insert(0, str(ROOT / "pruebas/auditoria_2ay"))
    from analisis_2ay import elegibilidad, simular_conciliacion
    from banco_extraccion import _resumen_normalizada
    f = _resumen_normalizada(_norm(doc, "08011733"))
    assert elegibilidad(f) == ("APTA", "APTA_MIXTA")  # el hueco documental de 15,91 desaparece
    sim = simular_conciliacion(f, _operacionales())
    assert Decimal(sim["diferencia"]) == Decimal("2.1600")  # 2,11 (08D28707 ambiguo) + 0,05 redondeos
    assert sim["matching"].get("AMBIGUO") == 1 and sim["albaranes_sin_coincidencia"] == 1


# ----------------------------------------------------------------- R14

def test_r14_vencimientos_de_las_5_facturas_del_2ao_igual_al_total():
    _, doc = _extraer(PDF_2AO)
    importes = {f["numero_factura"]["valor"]: ([v["importe"]["valor"] for v in f["vencimientos"]],
                                               f["totales"]["total"]["valor"]) for f in doc["facturas"]}
    assert set(importes) == {"08007969", "08007970", "08007971", "08007972", "08007973"}
    for numero, (vencimientos, total) in importes.items():
        assert vencimientos == [total], numero
    for f in doc["facturas"]:
        [v] = f["vencimientos"]
        assert {e["pagina"] for e in v["importe"]["evidencia"]} == {f["pagina_inicio"]}
        assert not [i for i in f["incidencias"] if i["codigo"] == "IMPORTE_VENCIMIENTO_NO_DOCUMENTADO"]


def test_r14_fechas_contradictorias_entre_hojas_quedan_sin_importe(monkeypatch):
    if not PDF_2AO.exists():
        pytest.skip("fixture 2AO ausente")
    # Se prueba sobre la salida cruda: si las hojas muestran fechas distintas, ninguna conserva importe.
    adaptador = al.AdaptadorAlliance()
    local = MotorDocumentoLocal(BackendPdfium()).extraer(PDF_2AO)
    raw = _raw(local, "08007970")
    assert len(raw["vencimientos"]) > 1 and len({v["fecha"]["valor"] for v in raw["vencimientos"]}) == 1
    documento = BackendPdfium().cargar_pdf(PDF_2AO)
    paginas = [p for p in documento.paginas if raw["segmento"]["paginas"][0] <= p.numero <= raw["segmento"]["paginas"][1]]
    contador = iter(range(1000))
    monkeypatch.setattr(al, "fecha_iso", lambda _texto: f"2026-01-{next(contador) % 28 + 1:02d}")
    venc = adaptador._vencimientos(documento, paginas)
    assert len({v["fecha"]["valor"] for v in venc}) > 1
    assert all(v["importe"] is None and v.get("contradictorio") for v in venc)


# ----------------------------------------------------------------- D11

def _cand(numero, fecha, puc, pvp, contador, id_proveedor="2"):
    return CandidatoAlbaranSupabase(contador, "PIO", id_proveedor, SAFA, numero, date.fromisoformat(fecha),
                                    Decimal(puc) if puc is not None else None, Decimal(pvp) if pvp is not None else None)


def _doc(numero, fecha, importe, sentido="CARGO"):
    return AlbaranDocumentalTrabajo("d", numero, date.fromisoformat(fecha), Decimal(importe), sentido)


def test_d11_sin_numero_exacto_no_casa_por_pvp():
    """08007501: sin 08B96275 en Supabase no casa con 08B96475 (PUC 2,09, PVP 6,49)."""
    candidatos = [_cand("08B96475", "2026-06-11", "2.09", "6.49", 278041)]
    r = buscar_candidato_albaran(_doc("08B96275", "2026-06-11", "6.51"), candidatos, proveedor_literal=ALLIANCE)
    assert r.estado == "SIN_COINCIDENCIA" and r.candidato is None


def test_d11_con_numero_exacto_casa_por_numero():
    candidatos = [_cand("08B96475", "2026-06-11", "2.09", "6.49", 278041),
                  _cand("08B96275", "2026-06-11", "6.51", "9.00", 999001)]
    r = buscar_candidato_albaran(_doc("08B96275", "2026-06-11", "6.51"), candidatos, proveedor_literal=ALLIANCE)
    assert (r.estado, r.coincidencia_numero, r.candidato.id_contador, r.importe_compatible) == (
        "MATCH_UNICO", "EXACTA", 999001, Decimal("6.5100"))


def test_d11_casos_de_control_siguen_igual():
    # Q039904/2026 <-> 08C18299: numero distinto, casa por PUC exacto.
    r = buscar_candidato_albaran(_doc("08C18299", "2026-06-23", "191.84"),
                                 [_cand("Q039904/2026", "2026-06-23", "191.84", "313.29", 279694)],
                                 proveedor_literal=ALLIANCE)
    assert (r.estado, r.coincidencia_numero, r.candidato.id_contador) == ("MATCH_UNICO", "DIFERENTE", 279694)
    # 08007973: dos albaranes por numero exacto (PUC 12,44 y 10,05).
    for numero, fecha, importe, puc, contador in (("08M26924", "2026-06-26", "12.45", "12.44", 280242),
                                                   ("08C23236", "2026-06-27", "10.04", "10.05", 280269)):
        r = buscar_candidato_albaran(_doc(numero, fecha, importe), [_cand(numero, fecha, puc, "1.00", contador)],
                                     proveedor_literal=ALLIANCE)
        assert (r.estado, r.coincidencia_numero, r.candidato.id_contador) == ("MATCH_UNICO", "EXACTA", contador)
    # 08D28707: dos candidatos con PUC 2,11 y numero distinto -> sigue AMBIGUO.
    r = buscar_candidato_albaran(_doc("08D28707", "2026-09-22", "2.11"),
                                 [_cand("Q040658/2026", "2026-09-22", "2.11", "3.12", 1),
                                  _cand("08M82343", "2026-09-22", "2.11", "6.57", 2)], proveedor_literal=ALLIANCE)
    assert r.estado == "AMBIGUO" and r.candidato is None


def test_d11_con_instantanea_real_08007501_queda_sin_casar():
    candidatos = _operacionales()
    assert not [c for c in candidatos if c.numero_albaran == "08B96275"]  # volcado del 2026-10-06
    r = buscar_candidato_albaran(_doc("08B96275", "2026-06-11", "6.51"),
                                 [c for c in candidatos if abs((c.fecha - date(2026, 6, 11)).days) <= 15],
                                 proveedor_literal=ALLIANCE)
    assert r.estado == "SIN_COINCIDENCIA"


# ----------------------------------------------------------------- R11

@pytest.mark.parametrize("n,tolerancia", [(0, "0.05"), (1, "0.05"), (5, "0.05"), (20, "0.20"), (71, "0.50"),
                                          (200, "0.50")])
def test_r11_valores(n, tolerancia):
    assert ReglaTolerancia().para(n) == Decimal(tolerancia)


def test_r11_regla_fuera_de_rango_falla_cerrado():
    for kwargs in ({"suelo": "0"}, {"suelo": "0.60", "tope": "0.50"}, {"tope": "1.10"}, {"por_albaran": "0.06"}):
        with pytest.raises(ValueError, match="REGLA_TOLERANCIA_FUERA_DE_RANGO"):
            ReglaTolerancia(**{k: Decimal(v) for k, v in kwargs.items()})


def _detalles(n, importe="1.00"):
    return [DetalleConciliacion(tipo_relacion=TipoRelacionConciliacion.UNO_A_UNO, importe_aplicado=Decimal(importe),
                                albaran_farmacia="PIO", albaran_id_contador=i, factura_albaran_extraido_id=f"a{i}")
            for i in range(n)]


def test_r11_conciliar_importes_registra_tolerancia_aplicada():
    r = conciliar_importes(Decimal("71.08"), _detalles(71), regla=ReglaTolerancia())
    assert (r.resultado, r.diferencia, r.tolerancia, r.albaranes_casados) == (
        "CONCILIADA", Decimal("0.0800"), Decimal("0.5000"), 71)
    assert r.regla_tolerancia == {"suelo": "0.0500", "por_albaran": "0.0100", "tope": "0.5000",
                                  "albaranes_casados": 71, "tolerancia": "0.5000"}
    # Con la tolerancia fija previa (T1) la misma factura seria DIFERENCIA.
    assert conciliar_importes(Decimal("71.08"), _detalles(71)).resultado == "DIFERENCIA"
    # Suelo: 1 albaran y 0,03 de diferencia sigue conciliando (08010887).
    assert conciliar_importes(Decimal("1.03"), _detalles(1), regla=ReglaTolerancia()).resultado == "CONCILIADA"


def test_r11_misma_regla_en_ruta_manual_y_automatica():
    from src.facturas.runtime_supabase.modelos import FacturaTrabajo
    from src.facturas.runtime_supabase.repositorios import payload_conciliacion
    from src.facturas.runtime_supabase.worker_conciliacion import construir_worker_conciliacion

    class Repo:
        def __init__(self):
            self.guardados = []

        def reclamar_factura(self, w):
            return FacturaTrabajo("f-auto", "d", "PIO", Decimal("20.15"))

        def reclamar_factura_manual_one_shot(self, w):
            return FacturaTrabajo("f-man", "d", "PIO", Decimal("20.15"))

        def construir_detalles(self, factura):
            return tuple(_detalles(20))

        def guardar_conciliacion(self, factura, worker_id, resultado, disparador="AUTOMATICO"):
            self.guardados.append((disparador, payload_conciliacion(resultado)))

        def fallar_conciliacion(self, *a, **k):
            raise AssertionError("no debe fallar")

    repo = Repo()
    worker = construir_worker_conciliacion(repo, "w")
    assert worker.ejecutar_una() is True and worker.ejecutar_una_manual() is True
    assert [(d, p["resultado"], p["tolerancia"], p["tolerancia_regla"]["albaranes_casados"]) for d, p in repo.guardados] \
        == [("AUTOMATICO", "CONCILIADA", "0.2000", 20), ("MANUAL_ONE_SHOT", "CONCILIADA", "0.2000", 20)]


# ----------------------------------------------------------------- R12 (construccion pura)

def _datos_persistidos(f: dict, *, albaranes=(), importe_vencimiento=None):
    persistida = json.loads(json.dumps(f))
    persistida["albaranes"] = []
    for v in persistida["vencimientos"]:
        v["importe"] = importe_vencimiento
    return {"factura": {"id": "f1", "numero_factura": "08007971", "fecha_factura": "2026-06-30",
                        "importe_total": 364.47, "proveedor_cif": None, "estado_conciliacion_cf": "PENDIENTE_CONCILIAR",
                        "datos_extraidos": persistida},
            "documento": {"id": "doc-1", "archivo_hash": "a" * 64, "farmacia": "PIO"},
            "albaranes": [{"numero_albaran": n} for n in albaranes], "movimientos": []}


def test_r12_construye_albaranes_y_vencimiento_nulo():
    _, doc = _extraer(PDF_2AO)
    f = _norm(doc, "08007971")
    payload = construir_enriquecimiento(_datos_persistidos(f), doc)
    assert [a["numero"]["valor"] for a in payload["albaranes"]] == ["08C18299", "08M24229", "08M25574"]
    assert [(v["fecha"]["valor"]["iso"], v["importe"]["valor"]) for v in payload["vencimientos"]] == [
        ("2026-09-30", f["totales"]["total"]["valor"])]
    assert payload["identidad"]["proveedor_cif"] == "A50004324" and payload["movimientos"] == []
    clave = clave_idempotente_enriquecimiento("f1", payload)
    assert clave.startswith("enriquecimiento:f1:") and clave == clave_idempotente_enriquecimiento("f1", payload)


def test_r12_no_propone_vencimiento_con_importe_ni_albaranes_ya_presentes():
    _, doc = _extraer(PDF_2AO)
    f = _norm(doc, "08007971")
    datos = _datos_persistidos(f, albaranes=("08C18299",), importe_vencimiento={"valor": "364.47"})
    payload = construir_enriquecimiento(datos, doc)
    assert [a["numero"]["valor"] for a in payload["albaranes"]] == ["08M24229", "08M25574"]
    assert payload["vencimientos"] == []
    with pytest.raises(ValueError, match="SIN_FILAS_NUEVAS"):
        construir_enriquecimiento(_datos_persistidos(f, albaranes=("08C18299", "08M24229", "08M25574"),
                                                     importe_vencimiento={"valor": "364.47"}), doc)


def test_r12_identidad_distinta_falla_cerrado():
    _, doc = _extraer(PDF_2AO)
    datos = _datos_persistidos(_norm(doc, "08007971"))
    datos["factura"]["importe_total"] = 364.48
    with pytest.raises(ValueError, match="IDENTIDAD_NO_COINCIDE:importe_total"):
        construir_enriquecimiento(datos, doc)


# ----------------------------------------------------------------- migracion 20 (estatico)

def _fuera_de_cuerpos(sql: str) -> str:
    return re.sub(r"\$\$.*?\$\$", "", re.sub(r"--[^\n]*", "", sql), flags=re.S).casefold()


def test_migracion_20_privilegios_y_sin_dml():
    sql = MIG20.read_text(encoding="utf-8")
    exterior = _fuera_de_cuerpos(sql)
    for firma in ("cf_enriquecer_factura(uuid, text, text, jsonb)", "cf_persistir_conciliacion(uuid, text, text, text, jsonb)"):
        assert re.search(rf"revoke all on function public\.{re.escape(firma)}\s+from public, anon, authenticated;", exterior)
        grants = re.findall(rf"grant execute on function public\.{re.escape(firma)}\s+to ([a-z_, ]+);", exterior)
        assert grants == ["service_role"]
    assert "grant" not in exterior.replace("grant execute on function", "")
    assert not re.search(r"\b(insert into|update public\.|delete from|truncate|drop table)\b", exterior)
    assert sql.count("security definer") == 2 and sql.count("set search_path = public") == 2
    assert "cf_reclamar_factura_conciliacion_nucleo" not in sql and "cf_evaluar_elegibilidad_conciliacion" not in sql
    assert exterior.strip().startswith("begin;") and exterior.strip().endswith("commit;")


def test_migracion_20_generada_de_forma_determinista():
    sys.path.insert(0, str(ROOT / "pruebas/auditoria_2az"))
    import generar_migracion_20 as gen

    assert gen.persistir_conciliacion_20() in MIG20.read_text(encoding="utf-8")
    assert gen.funcion_18("cf_persistir_conciliacion") in ROLLBACK20.read_text(encoding="utf-8")
    assert "drop function if exists public.cf_enriquecer_factura(uuid, text, text, jsonb);" in ROLLBACK20.read_text(
        encoding="utf-8")
