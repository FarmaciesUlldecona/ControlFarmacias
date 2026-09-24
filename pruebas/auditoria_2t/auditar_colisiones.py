"""Auditoria READ ONLY de aliases autorizados para el Hito 2T."""

from __future__ import annotations

import json
import os
import sys
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tmp_pg_probe_deps")]

import psycopg2


ALIASES = (
    "SAFA",
    "1.- SAFA",
    "ALLIANCE",
    "ALLIANCE HEALTHCARE",
    "ALLIANCE HEALTHCARE ESPAÑA",
    "ALLIANCE HEALTHCARE ESPAÑA, S.A.",
    "CENCORA",
)


def normalizar(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", valor).encode("ascii", "ignore").decode()
    return "".join(caracter for caracter in texto.upper() if caracter.isalnum())


def main() -> None:
    conexion = psycopg2.connect(
        os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"],
        sslmode="require",
        connect_timeout=10,
        application_name="cf_2t_colisiones_readonly",
    )
    conexion.set_session(readonly=True, autocommit=False)
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                select p.id::text, p.codigo, p.nombre, p.farmatic_id_proveedor,
                       p.nivel_confianza, p.activo, a.alias
                from public.proveedores p
                left join public.proveedores_alias a on a.proveedor_id = p.id
                order by p.codigo, a.alias
                """
            )
            proveedores = cursor.fetchall()
            cursor.execute(
                """
                select proveedor, id_proveedor, count(*), min(fecha), max(fecha)
                from public.albaranes
                where proveedor ilike '%SAFA%'
                   or proveedor ilike '%ALLIANCE%'
                   or proveedor ilike '%CENCORA%'
                group by proveedor, id_proveedor
                order by proveedor, id_proveedor
                """
            )
            albaranes = cursor.fetchall()
            cursor.execute(
                "select count(*) from public.albaranes where farmacia = 'PIO' and id_proveedor = '2'"
            )
            pio_id_2 = cursor.fetchone()[0]

        objetivos = {normalizar(alias) for alias in ALIASES}
        colisiones = [
            fila
            for fila in proveedores
            if fila[6] is not None and normalizar(fila[6]) in objetivos
        ]
        print(json.dumps({
            "aliases_autorizados": ALIASES,
            "proveedores": proveedores,
            "albaranes_relevantes": albaranes,
            "pio_id_2": pio_id_2,
            "colisiones_alias_normalizado": colisiones,
        }, default=str, ensure_ascii=False))
    finally:
        conexion.rollback()
        conexion.close()


if __name__ == "__main__":
    main()
