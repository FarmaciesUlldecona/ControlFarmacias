"""Hito 2BG: R19 con 08007970 real en PostgreSQL 17 local (plantilla "24", estado productivo).

PDF del 2AO (fixture local excluido de git). Albaranes con el PUC real de produccion (simulacion READ_ONLY del
2026-10-30): PUC = importe documental salvo las 22 lineas de ``PUC_REALES``; 08M26912 es 280247, proveedor
154 «6- PLATAF. ECO360 AH». Sin produccion ni Farmatic.
"""
from __future__ import annotations

import pytest

import src.facturas.runtime_supabase.conciliacion as conciliacion
from pg17_local import _lit
from test_integracion_pg17_2az import _preparar_2ao, _solo_primera
from test_integracion_pg17_2ba import _reservas, _vigente
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase
from src.facturas.runtime_supabase.worker_conciliacion import construir_worker_conciliacion

pytestmark = pytest.mark.pg17_local

PUC_REALES = {
    "08M23091": "11.77", "08C17420": "144.10", "08M23990": "47.97", "08M23991": "16.16", "08M24030": "3.56",
    "08C18525": "8.93", "08M24735": "10.51", "08M24786": "5.62", "08M24833": "22.12", "08C20306": "5.62",
    "08M25271": "9.84", "08M25779": "10.05", "08M25781": "10.05", "08M25932": "17.62", "08C21641": "84.52",
    "08C21646": "30.74", "08C21748": "5.64", "08C23219": "35.85", "08C23977": "19.69", "08C24122": "69.66",
    "08C24125": "80.02", "08M27917": "36.97",
}


def _albaranes_08007970(pg, factura_id) -> None:
    pg.sql(
        "insert into public.albaranes (farmacia,id_contador,id_proveedor,proveedor,numero_albaran,fecha,"
        "importe_pvp,importe_puc,descuento,estado) "
        "select 'PIO', 970000 + row_number() over (order by a.orden), '2', '1.- SAFA', a.numero_albaran, "
        "a.fecha_albaran, round(abs(a.importe_total) * 1.6, 2), abs(a.importe_total), 0, 'PENDIENTE' "
        f"from public.facturas_albaranes_extraidos a where a.factura_id = {_lit(factura_id)};")
    for numero, puc in PUC_REALES.items():
        pg.sql(f"update public.albaranes set importe_puc = {puc} where id_contador >= 970000 "
               f"and numero_albaran = {_lit(numero)};")
    pg.sql("update public.albaranes set id_contador = 280247, id_proveedor = '154', "
           "proveedor = '6- PLATAF. ECO360 AH', importe_puc = 39.05 "
           "where id_contador >= 970000 and numero_albaran = '08M26912';")


def _conciliar_08007970(pg, tmp_path):
    cliente, ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    objetivo = ids["08007970"]
    _albaranes_08007970(pg, objetivo)
    _solo_primera(pg, ids, "08007970")
    worker = construir_worker_conciliacion(RepositorioRuntimeSupabase(cliente), "conc-2bg")
    assert worker.ejecutar_una_manual() is True
    return objetivo


def test_caso_real_08007970_concilia_con_r19(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("24")
    objetivo = _conciliar_08007970(pg, tmp_path)
    c = _vigente(pg, objetivo)
    assert (c["resultado"], c["diferencia"], c["casados"]) == ("CONCILIADA", "-0.0700", 71)
    [eco] = pg.json("select d.albaran_id_contador, d.importe_aplicado::text as importe, "
                    "d.provenance->>'clase_numero' as clase from public.conciliacion_detalles d "
                    f"where d.conciliacion_id = {_lit(c['id'])} and d.albaran_id_contador = 280247")
    assert (eco["importe"], eco["clase"]) == ("39.0500", "EXACTA")
    reservas = {r["albaran_id_contador"]: r["factura_id"] for r in _reservas(pg)}
    assert reservas[280247] == objetivo and len(reservas) == 71


def test_08007970_sin_r19_sigue_en_diferencia(pg17_nueva_base, tmp_path, monkeypatch):
    """Control: sin R19 (alias e id retirados) el mismo escenario da la DIFERENCIA de produccion."""
    monkeypatch.setattr(conciliacion, "_ALIASES_ALLIANCE_AUTORIZADOS",
                        conciliacion._ALIASES_ALLIANCE_AUTORIZADOS - {"6PLATAFECO360AH"})
    monkeypatch.setattr(conciliacion, "_ID_PROVEEDOR_GRUPO_ALLIANCE", {})
    pg = pg17_nueva_base("24")
    objetivo = _conciliar_08007970(pg, tmp_path)
    c = _vigente(pg, objetivo)
    assert (c["resultado"], c["diferencia"], c["casados"]) == ("DIFERENCIA", "38.9800", 70)
    assert 280247 not in {r["albaran_id_contador"] for r in _reservas(pg)}
