"""Hito 2AT rev2, paso 1: verificacion READ_ONLY de las ejecuciones nocturnas con la migracion 19.

Uso:
  python -B pruebas/auditoria_2at/verificacion_nocturna_readonly.py <salida.json>

Cuenta las filas nuevas de ``documentos_facturas`` y ``albaranes`` desde el
despliegue de la 19 (2026-09-29 07:07:46 UTC), agrupadas por noche (hora de
Madrid), y el IdContador maximo. Usa la misma puerta de solo lectura que
``auditoria_readonly.py`` (project ref demostrado, sesion READ_ONLY, solo
SELECT/WITH, rollback). No toca Farmatic.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from auditoria_readonly import _Lector, _ejecutar_lectura, _escribir, _salida_fuera_del_repo  # noqa: E402

DESPLIEGUE_19 = "2026-09-29 07:07:46+00"


def leer(lector: _Lector) -> dict:
    out = {"desde": DESPLIEGUE_19}
    for tabla in ("documentos_facturas", "albaranes"):
        out[tabla] = {
            "nuevas_total": lector.valor(
                f"select count(*) from public.{tabla} where fecha_importacion >= %s::timestamptz", (DESPLIEGUE_19,)),
            "por_dia_madrid": [[str(d), n] for d, n in lector.filas(
                f"select (fecha_importacion at time zone 'Europe/Madrid')::date, count(*) from public.{tabla} "
                f"where fecha_importacion >= %s::timestamptz group by 1 order by 1", (DESPLIEGUE_19,))],
        }
    out["albaranes"]["id_contador_max"] = lector.valor("select max(id_contador) from public.albaranes")
    out["documentos_facturas"]["nuevos"] = [list(r) for r in lector.filas(
        "select archivo_nombre, fecha_importacion::text, estado_lectura from public.documentos_facturas "
        "where fecha_importacion >= %s::timestamptz order by fecha_importacion", (DESPLIEGUE_19,))]
    return out


if __name__ == "__main__":
    salida = _salida_fuera_del_repo(sys.argv[1])
    _, datos = _ejecutar_lectura(leer)
    sha = _escribir(salida, datos)
    print(json.dumps(datos, ensure_ascii=False, indent=1, default=str))
    print("sha256", sha)
