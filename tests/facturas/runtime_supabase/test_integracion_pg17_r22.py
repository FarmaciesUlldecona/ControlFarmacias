"""R22 (DECISION DE PIO, 2026-11-24; caso E, 08005257) en PostgreSQL 17 local, plantilla "38" (estado productivo).

Sin migracion: la BD ya acepta un detalle ``MOVIMIENTO_NO_FARMATIC`` con origen en la linea del PDF
(``conciliacion_detalles_origen_check``, 14) y lo trata como NO_EVALUABLE (``cf_detalles_por_linea``, 30).
Escenario: PDF real del 2AO (fixture local excluido de git), 08007969 con albaranes sinteticos (PUC = importe
documental). Se quita el albaran de 08C20268 (504,02), la factura pasa a MIXTA con un movimiento ABONO -504,02 y su
total se ajusta al neto del par. El worker real persiste CONCILIADA con el par R22, sin reservar nada por esa linea.
Sin el abono exacto del mismo concepto (D6), o con dos, la linea sigue sin casar y la factura queda en DIFERENCIA.
Sin produccion ni Farmatic.
"""
from __future__ import annotations

import pytest

from pg17_local import _lit
from test_integracion_pg17_2az import (  # noqa: F401 (fixture)
    _operacionales_sinteticos, _preparar_2ao, _solo_primera, contenedor_tcp)
from test_integracion_pg17_2ba import _reservas, _vigente
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase
from src.facturas.runtime_supabase.worker_conciliacion import construir_worker_conciliacion

pytestmark = pytest.mark.pg17_local

LINEA = "08C20268"
IMPORTE = "504.0200"


@pytest.fixture
def base38(pg17_nueva_base):
    return pg17_nueva_base("38")


def _escenario(pg, tmp_path, abonos: list[str], literal: str = "ECOCEUTICS"):
    cliente, ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    objetivo = ids["08007969"]
    _operacionales_sinteticos(pg, objetivo, 0, 940000)
    [linea] = pg.json("select id::text, importe_total::text as importe from public.facturas_albaranes_extraidos "
                      f"where factura_id = {_lit(objetivo)} and numero_albaran = {_lit(LINEA)}")
    assert linea["importe"] == IMPORTE
    pg.sql(f"delete from public.albaranes where id_contador >= 940000 and numero_albaran = {_lit(LINEA)};")
    # D6: la linea y su abono, del mismo concepto/laboratorio (como 08005257: ECOCEUTICS en los dos).
    pg.sql(f"update public.facturas_albaranes_extraidos set descripcion = 'ECOCEUTICS' where id = {_lit(linea['id'])};")
    pg.sql("update public.facturas set datos_extraidos = jsonb_set(coalesce(datos_extraidos, '{}'::jsonb), "
           f"'{{naturaleza_principal}}', '\"MIXTA\"') where id = {_lit(objetivo)};")
    # Los movimientos del PDF (ignorados mientras era MERCANCIA) fuera: solo el par a probar.
    pg.sql(f"delete from public.facturas_movimientos where factura_id = {_lit(objetivo)};")
    for orden, importe in enumerate(abonos, 1):
        pg.sql("insert into public.facturas_movimientos (factura_id, orden, categoria, descripcion_literal, sentido, "
               f"base, importe) values ({_lit(objetivo)}, {orden}, 'OTRO', {_lit(literal)}, 'ABONO', -453.39, {importe});")
    # Total = lineas del PDF + movimientos (con un solo abono exacto, el neto del par es 0); base = total - IVA - RE
    # - otros (fiscalidad coherente). Asi la factura es APTA en todos los escenarios.
    pg.sql("update public.facturas f set importe_total = x.total + m.total, base_imponible_total = x.total + m.total "
           "- coalesce(f.iva_total, 0) - coalesce(f.recargo_equivalencia_total, 0) "
           "- coalesce(nullif(f.datos_extraidos #>> '{totales,otros,valor}', '')::numeric, 0) "
           "from (select sum(case when tipo_movimiento = 'ABONO' then -abs(importe_total) else abs(importe_total) end) "
           f"as total from public.facturas_albaranes_extraidos where factura_id = {_lit(objetivo)}) x, "
           f"(select sum(importe) as total from public.facturas_movimientos where factura_id = {_lit(objetivo)}) m "
           f"where f.id = {_lit(objetivo)};")
    _solo_primera(pg, ids, "08007969")
    assert pg.json("select estado, razon from public.cf_evaluar_elegibilidad_conciliacion("
                   f"{_lit(objetivo)}::uuid)") == [{"estado": "APTA", "razon": "APTA_MIXTA"}]
    worker = construir_worker_conciliacion(RepositorioRuntimeSupabase(cliente), "conc-r22")
    assert worker.ejecutar_una_manual() is True
    return objetivo, linea["id"]


def _detalles(pg, conciliacion_id):
    return pg.json("select tipo_relacion, importe_aplicado::text as aplicado, importe_documental::text as pdf, "
                   "importe_farmatic::text as farmatic, estado, factura_albaran_extraido_id::text as linea, "
                   "factura_movimiento_id::text as movimiento, albaran_id_contador, provenance->>'regla' as regla "
                   f"from public.conciliacion_detalles where conciliacion_id = {_lit(conciliacion_id)} order by orden")


def test_el_par_r22_concilia_sin_reservar_la_linea(base38, tmp_path):
    pg = base38
    objetivo, linea = _escenario(pg, tmp_path, ["-504.02"])
    c = _vigente(pg, objetivo)
    assert (c["resultado"], c["diferencia"]) == ("CONCILIADA", "0.0000")
    detalles = _detalles(pg, c["id"])
    r22 = [d for d in detalles if d["regla"] == "R22"]
    assert len(r22) == 2
    [par_linea] = [d for d in r22 if d["linea"] == linea]
    [par_abono] = [d for d in r22 if d["movimiento"]]
    assert (par_linea["tipo_relacion"], par_linea["aplicado"], par_linea["pdf"], par_linea["farmatic"],
            par_linea["estado"], par_linea["albaran_id_contador"]) == (
        "MOVIMIENTO_NO_FARMATIC", IMPORTE, IMPORTE, None, "NO_EVALUABLE", None)
    assert (par_abono["tipo_relacion"], par_abono["aplicado"]) == ("MOVIMIENTO_NO_FARMATIC", "-504.0200")
    assert not any(d["tipo_relacion"] == "SIN_COINCIDENCIA" for d in detalles)
    reservas = _reservas(pg)
    assert reservas and all(r["factura_id"] == objetivo for r in reservas)
    assert len(reservas) == sum(d["albaran_id_contador"] is not None for d in detalles)


@pytest.mark.parametrize("abonos,literal", [(["-504.01"], "ECOCEUTICS"), (["-504.02", "-504.02"], "ECOCEUTICS"),
                                            (["-504.02"], "HEEL")],
                         ids=["importe_distinto", "dos_abonos", "concepto_distinto"])
def test_sin_par_unico_la_linea_sigue_sin_casar(base38, tmp_path, abonos, literal):
    pg = base38
    objetivo, linea = _escenario(pg, tmp_path, abonos, literal)
    c = _vigente(pg, objetivo)
    assert c["resultado"] == "DIFERENCIA"
    detalles = _detalles(pg, c["id"])
    assert not any(d["regla"] == "R22" for d in detalles)
    assert [d["tipo_relacion"] for d in detalles if d["linea"] == linea] == ["SIN_COINCIDENCIA"]
