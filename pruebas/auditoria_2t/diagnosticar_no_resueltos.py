"""Detalle READ ONLY de los candidatos no resueltos en el Hito 2T."""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))

import psycopg2

sys.path.insert(0, str(ROOT))
from src.facturas.runtime_supabase.conciliacion import canonicalizar_proveedor, normalizar_numero_albaran


NUMEROS = (
    "08C52355", "08M44966", "08C56226",
    "08P10588", "08C61794", "08C61795", "08P10623",
    "08C52171", "08C59254", "08M49141", "08Z34777",
    "08C57517",
)

DOCUMENTALES = (
    ("08C52355", date(2026, 7, 23), Decimal("1.42")),
    ("08M44966", date(2026, 7, 23), Decimal("1.37")),
    ("08C56226", date(2026, 7, 27), Decimal("52.70")),
    ("08P10588", date(2026, 7, 30), Decimal("-823.46")),
    ("08C61794", date(2026, 7, 31), Decimal("-122.27")),
    ("08C61795", date(2026, 7, 31), Decimal("-414.76")),
    ("08P10623", date(2026, 7, 31), Decimal("-2414.19")),
    ("08C52171", date(2026, 7, 23), Decimal("12.21")),
    ("08C59254", date(2026, 7, 29), Decimal("6.37")),
    ("08M49141", date(2026, 7, 30), Decimal("11.50")),
    ("08Z34777", date(2026, 7, 31), Decimal("191.54")),
    ("08C57517", date(2026, 7, 28), Decimal("13.54")),
)


def main() -> None:
    conexion = psycopg2.connect(
        os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"], sslmode="require",
        connect_timeout=10, application_name="cf_2t_no_resueltos_readonly",
    )
    conexion.set_session(readonly=True)
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                select numero_albaran,id_contador,farmacia,id_proveedor,proveedor,
                       fecha,importe_puc,importe_pvp,estado
                from public.albaranes
                where farmacia='PIO' and fecha between '2026-07-08' and '2026-08-15'
                order by numero_albaran,fecha,id_contador
                """
            )
            filas = cursor.fetchall()
            salida = {}
            for numero, fecha, importe in DOCUMENTALES:
                candidatos = []
                for fila in filas:
                    if canonicalizar_proveedor(fila[4]) != canonicalizar_proveedor("ALLIANCE HEALTHCARE ESPAÑA, S.A."):
                        continue
                    puc, pvp = fila[6], fila[7]
                    importe_ok = any(
                        valor is not None and abs(abs(Decimal(valor)) - abs(importe)) <= Decimal("0.05")
                        for valor in (puc, pvp)
                    )
                    numero_exacto = normalizar_numero_albaran(fila[0]) == normalizar_numero_albaran(numero)
                    ventana = abs((fila[5] - fecha).days) <= 15
                    if ventana and (importe_ok or numero_exacto):
                        candidatos.append({
                            "id_contador": fila[1], "numero": fila[0], "id_proveedor": fila[3],
                            "proveedor": fila[4], "fecha": fila[5], "puc": puc, "pvp": pvp,
                            "importe_ok_abs": importe_ok, "numero_exacto": numero_exacto,
                            "fecha_exacta": fila[5] == fecha,
                        })
                salida[numero] = candidatos
            print(json.dumps(salida, default=str, ensure_ascii=False))
    finally:
        conexion.rollback()
        conexion.close()


if __name__ == "__main__":
    main()
