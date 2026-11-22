"""R20: verificacion READ_ONLY del banco de Supabase (puerta del 2AT, sin escrituras).

Para cada factura de PIO con lineas de albaran, construye los detalles de conciliacion con el codigo de ``src``
(``RepositorioRuntimeSupabase.construir_detalles`` sobre el cliente de lectura del 2AT) dos veces, con R20 apagado y
encendido, y lista toda diferencia por linea. Esperado (diseno §2.2): solo 08013495 / 08D79747 pasa de
SIN_COINCIDENCIA a dos detalles UNO_A_VARIOS con regla R20.

Uso: python -B pruebas/auditoria_r20/verificar_banco_r20.py <salida.json>   (salida fuera del repositorio)
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))
import auditoria_readonly as ar  # noqa: E402


def _huella(detalles) -> dict[str, list]:
    por_linea: dict[str, list] = {}
    for d in detalles:
        clave = d.factura_albaran_extraido_id or f"mov:{d.factura_movimiento_id}"
        por_linea.setdefault(clave, []).append(
            [d.tipo_relacion.value, d.albaran_id_contador, str(d.importe_aplicado), d.provenance.get("regla")])
    return por_linea


def leer(lector) -> dict:
    from src.facturas.runtime_supabase.modelos import FacturaTrabajo
    from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase

    cliente = ar._ClienteLectura(lector)
    filas = lector.filas(
        "select f.id::text, f.numero_factura, f.documento_id::text, f.farmacia, f.importe_total::text, "
        "f.proveedor_id::text, f.estado_conciliacion_cf from public.facturas f where f.farmacia = 'PIO' "
        "and exists (select 1 from public.facturas_albaranes_extraidos e where e.factura_id = f.id) "
        "order by f.numero_factura")
    cambios, errores = [], []
    for fid, numero, doc, farmacia, importe, proveedor, estado in filas:
        factura = FacturaTrabajo(factura_id=fid, documento_id=doc, farmacia=farmacia,
                                 importe_total=Decimal(importe) if importe else None, proveedor_id=proveedor)
        try:
            sin = _huella(RepositorioRuntimeSupabase(cliente, r20_habilitada=lambda: False).construir_detalles(factura))
            con = _huella(RepositorioRuntimeSupabase(cliente, r20_habilitada=lambda: True).construir_detalles(factura))
        except Exception as exc:  # noqa: BLE001 - se registra y se sigue: no cambia por R20
            errores.append({"factura": numero, "error": f"{type(exc).__name__}: {exc}"[:300]})
            continue
        for linea in sorted(set(sin) | set(con)):
            if sin.get(linea) != con.get(linea):
                cambios.append({"factura": numero, "estado_factura": estado, "linea": linea,
                                "sin_r20": sin.get(linea), "con_r20": con.get(linea)})
    return {"facturas_revisadas": len(filas), "facturas_con_error_igual_en_ambos": errores, "cambios": cambios}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    _, datos = ar._ejecutar_lectura(leer)
    print(json.dumps({k: datos[k] for k in ("facturas_revisadas", "cambios")}, ensure_ascii=False, indent=1,
                     default=str))
    print("errores:", len(datos["facturas_con_error_igual_en_ambos"]))
    print("sha256", ar._escribir(ar._salida_fuera_del_repo(sys.argv[1]), datos))
