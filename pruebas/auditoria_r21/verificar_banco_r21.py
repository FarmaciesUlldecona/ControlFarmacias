"""R21-D8: verificacion READ_ONLY del banco de Supabase (puerta del 2AT, sin escrituras).

Para cada factura de PIO con lineas de albaran, construye los detalles de conciliacion con el codigo de ``src``
(``RepositorioRuntimeSupabase.construir_detalles`` sobre el cliente de lectura del 2AT) dos veces, con R21 apagada y
encendida (R20 como en la BD), y lista toda diferencia por linea. Cuenta tambien las lineas que con R21 quedan
``AMBIGUO_R21``, ``CONFLICTO_R21`` o con ``DEMASIADOS_CANDIDATOS``. Esperado (DISENO §9.1): solo 08005707 / 08L82633
pasa de SIN_COINCIDENCIA a tres detalles UNO_A_VARIOS con regla R21. Si cambia algo mas, PARAR (R21-D8).

Uso: python -B pruebas/auditoria_r21/verificar_banco_r21.py <salida.json>   (salida fuera del repositorio)
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
            [d.tipo_relacion.value, d.albaran_id_contador, str(d.importe_aplicado), d.provenance.get("regla"),
             d.provenance.get("estado_matching"), d.provenance.get("motivo")])
    return por_linea


def leer(lector) -> dict:
    from src.facturas.runtime_supabase.lectura_readonly import r20_habilitada
    from src.facturas.runtime_supabase.modelos import FacturaTrabajo
    from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase

    cliente = ar._ClienteLectura(lector)
    r20 = r20_habilitada(lector)
    filas = lector.filas(
        "select f.id::text, f.numero_factura, f.documento_id::text, f.farmacia, f.importe_total::text, "
        "f.proveedor_id::text, f.estado_conciliacion_cf from public.facturas f where f.farmacia = 'PIO' "
        "and exists (select 1 from public.facturas_albaranes_extraidos e where e.factura_id = f.id) "
        "order by f.numero_factura")
    cambios, errores, r21_sin_casar = [], [], []
    for fid, numero, doc, farmacia, importe, proveedor, estado in filas:
        factura = FacturaTrabajo(factura_id=fid, documento_id=doc, farmacia=farmacia,
                                 importe_total=Decimal(importe) if importe else None, proveedor_id=proveedor)

        def detalles(r21: bool):
            return RepositorioRuntimeSupabase(cliente, r20_habilitada=lambda: r20,
                                              r21_habilitada=lambda: r21).construir_detalles(factura)

        try:
            sin, con = _huella(detalles(False)), _huella(detalles(True))
        except Exception as exc:  # noqa: BLE001 - se registra y se sigue
            errores.append({"factura": numero, "error": f"{type(exc).__name__}: {exc}"[:300]})
            continue
        for linea in sorted(set(sin) | set(con)):
            if sin.get(linea) != con.get(linea):
                cambios.append({"factura": numero, "estado_factura": estado, "linea": linea,
                                "sin_r21": sin.get(linea), "con_r21": con.get(linea)})
            for d in con.get(linea, []):
                if (d[4] or "").endswith("_R21") and not (d[4] or "").startswith("MATCH"):
                    r21_sin_casar.append({"factura": numero, "estado_factura": estado, "linea": linea,
                                          "estado": d[4], "motivo": d[5]})
    return {"r20_en_bd": r20, "facturas_revisadas": len(filas), "facturas_con_error": errores, "cambios": cambios,
            "r21_sin_casar": r21_sin_casar}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    _, datos = ar._ejecutar_lectura(leer)
    print(json.dumps({k: datos[k] for k in ("r20_en_bd", "facturas_revisadas", "cambios", "r21_sin_casar")},
                     ensure_ascii=False, indent=1, default=str))
    print("errores:", len(datos["facturas_con_error"]))
    print("sha256", ar._escribir(ar._salida_fuera_del_repo(sys.argv[1]), datos))
