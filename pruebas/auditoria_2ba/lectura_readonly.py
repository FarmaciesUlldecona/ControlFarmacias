"""Hito 2BA: lectura READ_ONLY de Supabase para medir R15/R15b/R15c.

Uso:
  python -B pruebas/auditoria_2ba/lectura_readonly.py <salida.json>

Vuelca (solo farmacia PIO) las lineas de las conciliaciones (con su provenance:
numeros y fechas documental/operacional) y los albaranes extraidos de todas las
facturas, con la puerta de solo lectura certificada en 2AT
(``pruebas/auditoria_2at/auditoria_readonly.py``). La salida contiene datos de
negocio: debe escribirse fuera del repositorio. No toca Farmatic.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "auditoria_2at"))

from auditoria_readonly import _Lector, _ejecutar_lectura, _escribir, _salida_fuera_del_repo  # noqa: E402

CONSULTAS = {
    "detalles": (
        "select jsonb_build_object('conciliacion_id', c.id::text, 'numero_factura', f.numero_factura, "
        "'fecha_factura', f.fecha_factura::text, 'es_actual', c.es_actual, 'intento', c.intento, "
        "'resultado', c.resultado, 'diferencia', c.diferencia::text, 'tolerancia', c.tolerancia::text, "
        "'orden', d.orden, 'tipo_relacion', d.tipo_relacion, 'importe_aplicado', d.importe_aplicado::text, "
        "'albaran_farmacia', d.albaran_farmacia, 'albaran_id_contador', d.albaran_id_contador, "
        "'factura_albaran_extraido_id', d.factura_albaran_extraido_id::text, "
        "'numero_documental', coalesce(e.numero_albaran, d.provenance->>'numero_documental'), "
        "'fecha_documental', coalesce(e.fecha_albaran::text, d.provenance->>'fecha_documental'), "
        "'numero_farmatic', a.numero_albaran, 'fecha_farmatic', a.fecha::text, "
        "'puc', a.importe_puc::text, 'pvp', a.importe_pvp::text, 'proveedor_farmatic', a.proveedor, "
        "'provenance', d.provenance)::text "
        "from public.conciliaciones c join public.facturas f on f.id = c.factura_id "
        "join public.conciliacion_detalles d on d.conciliacion_id = c.id "
        "left join public.facturas_albaranes_extraidos e on e.id = d.factura_albaran_extraido_id "
        "left join public.albaranes a on a.farmacia = d.albaran_farmacia and a.id_contador = d.albaran_id_contador "
        "where f.farmacia = 'PIO' order by f.numero_factura, c.intento, d.orden"),
    "albaranes_extraidos": (
        "select jsonb_build_object('factura_id', e.factura_id::text, 'numero_factura', f.numero_factura, "
        "'numero_albaran', e.numero_albaran, 'fecha_albaran', e.fecha_albaran::text)::text "
        "from public.facturas_albaranes_extraidos e join public.facturas f on f.id = e.factura_id "
        "where f.farmacia = 'PIO' order by f.numero_factura, e.numero_albaran"),
}


def leer(lector: _Lector) -> dict:
    return {nombre: [json.loads(f[0]) for f in lector.filas(sql)] for nombre, sql in CONSULTAS.items()}


if __name__ == "__main__":
    salida = _salida_fuera_del_repo(sys.argv[1])
    _, datos = _ejecutar_lectura(leer)
    sha = _escribir(salida, datos)
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in datos.items()}, ensure_ascii=False))
    print("sha256", sha)
