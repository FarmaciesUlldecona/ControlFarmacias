"""Hito 2AY, fase 1.1: lectura READ_ONLY de Supabase para el banco de pruebas de extraccion.

Uso:
  python -B pruebas/auditoria_2ay/supabase_readonly.py <salida.json>

Vuelca (solo farmacia PIO) documentos_facturas, facturas, albaranes y
proveedores con la puerta de solo lectura certificada en 2AT
(``pruebas/auditoria_2at/auditoria_readonly.py``: project ref demostrado, sesion
READ_ONLY REPEATABLE READ, solo SELECT/WITH, rollback). La salida contiene
datos de negocio: debe escribirse fuera del repositorio. No toca Farmatic.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "auditoria_2at"))

from auditoria_readonly import _Lector, _ejecutar_lectura, _escribir, _salida_fuera_del_repo  # noqa: E402

CONSULTAS = {
    "documentos": (
        "select jsonb_build_object('id', id::text, 'archivo_nombre', archivo_nombre, 'archivo_ruta', archivo_ruta, "
        "'archivo_hash', archivo_hash, 'fecha_importacion', fecha_importacion::text, 'estado_lectura', estado_lectura, "
        "'estado_persistencia', estado_persistencia, 'ultima_clase_fallo', ultima_clase_fallo, "
        "'intentos_fallo_normalizacion', intentos_fallo_normalizacion, 'ultimo_error_codigo', ultimo_error_codigo, "
        "'numero_paginas', numero_paginas)::text from public.documentos_facturas where farmacia = 'PIO' "
        "order by fecha_importacion, id"),
    "facturas": (
        "select jsonb_build_object('id', id::text, 'documento_id', documento_id::text, 'farmacia', farmacia, "
        "'numero_factura', numero_factura, 'fecha_factura', fecha_factura::text, "
        "'importe_total', importe_total::text, 'base_imponible_total', base_imponible_total::text, "
        "'iva_total', iva_total::text, 'recargo_equivalencia_total', recargo_equivalencia_total::text, "
        "'proveedor_literal', proveedor_literal, 'proveedor_nombre', proveedor_nombre, 'proveedor_cif', proveedor_cif, "
        "'tipo_documento', tipo_documento, 'categoria', categoria, 'proyeccion_clave', proyeccion_clave, "
        "'identidad_economica_clave', datos_extraidos->>'identidad_economica_clave', "
        "'naturaleza_principal', datos_extraidos->>'naturaleza_principal', "
        "'estado_normalizacion', estado_normalizacion, 'estado_conciliacion_cf', estado_conciliacion_cf)::text "
        "from public.facturas where farmacia = 'PIO' order by fecha_factura, id"),
    "albaranes": (
        "select jsonb_build_object('id_contador', id_contador, 'farmacia', farmacia, 'id_proveedor', id_proveedor, "
        "'proveedor', proveedor, 'numero_albaran', numero_albaran, 'fecha', fecha::text, "
        "'importe_puc', importe_puc::text, 'importe_pvp', importe_pvp::text, 'estado', estado)::text "
        "from public.albaranes where farmacia = 'PIO' order by id_contador"),
    "proveedores": "select to_jsonb(p)::text from public.proveedores p order by 1",
}


def leer(lector: _Lector) -> dict:
    return {nombre: [json.loads(f[0]) for f in lector.filas(sql)] for nombre, sql in CONSULTAS.items()}


if __name__ == "__main__":
    salida = _salida_fuera_del_repo(sys.argv[1])
    _, datos = _ejecutar_lectura(leer)
    sha = _escribir(salida, datos)
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in datos.items()}, ensure_ascii=False))
    print("sha256", sha)
