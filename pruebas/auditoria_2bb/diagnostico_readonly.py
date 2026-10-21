"""Hito 2BB: diagnostico ESTRICTAMENTE READ_ONLY de la diferencia de conciliacion de una factura.

Uso:
  python -B pruebas/auditoria_2bb/diagnostico_readonly.py <numero_factura> <salida.json>

Puerta certificada del 2AT (project ref demostrado, sesion READ_ONLY REPEATABLE READ, solo
SELECT/WITH, rollback). Simula la conciliacion con ``_simular`` (camino del worker sin claim) y
la descompone linea a linea: albaranes documentales (lo extraido del PDF) frente a los
operacionales de ``Supabase.albaranes`` (espejo de Farmatic), movimientos, incidencias de la
normalizacion (filas no promovidas) y candidatos de las lineas sin casar. Sin DML, sin RPC de
escritura, sin Farmatic. La salida contiene datos de negocio: fuera del repositorio.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))

from auditoria_readonly import _Lector, _ejecutar_lectura, _escribir, _salida_fuera_del_repo, _simular  # noqa: E402

CERO = Decimal("0")


def _d(v) -> Decimal:
    return CERO if v is None else Decimal(str(v))


def _incidencias(resultado_json, numero: str) -> list:
    """Incidencias de la factura ``numero`` dentro del resultado de la normalizacion (estructura libre)."""
    encontradas = []

    def visitar(nodo, dentro: bool):
        if isinstance(nodo, dict):
            propio = dentro or numero in {str(v) for v in nodo.values() if isinstance(v, (str, int))}
            for k, v in nodo.items():
                if k == "incidencias" and propio and isinstance(v, list):
                    encontradas.extend(v)
                else:
                    visitar(v, propio)
        elif isinstance(nodo, list):
            for x in nodo:
                visitar(x, dentro)

    visitar(resultado_json, False)
    unicas, vistas = [], set()
    for i in encontradas:
        clave = json.dumps(i, sort_keys=True, ensure_ascii=False, default=str)
        if clave not in vistas:
            vistas.add(clave)
            unicas.append(i)
    return unicas


def diagnostico(numero: str, salida: Path) -> int:
    def leer(lector: _Lector) -> dict:
        [fila] = [json.loads(r[0]) for r in lector.filas(
            "select jsonb_build_object('id', f.id::text, 'numero_factura', f.numero_factura, "
            "'fecha_factura', f.fecha_factura::text, 'importe_total', f.importe_total::text, "
            "'base_imponible_total', f.base_imponible_total::text, 'iva_total', f.iva_total::text, "
            "'recargo_equivalencia_total', f.recargo_equivalencia_total::text, "
            "'otros', f.datos_extraidos #>> '{totales,otros,valor}', "
            "'naturaleza_principal', f.datos_extraidos->>'naturaleza_principal', 'categoria', f.categoria, "
            "'estado_conciliacion_cf', f.estado_conciliacion_cf, 'proveedor_literal', f.proveedor_literal, "
            "'normalizacion_ejecucion_id', f.normalizacion_ejecucion_id::text)::text "
            "from public.facturas f where f.numero_factura = %s and f.farmacia = 'PIO'", (numero,))]
        out = {"factura": fila,
               "elegibilidad": list(lector.fila("select e.estado, e.razon from "
                                                "public.cf_evaluar_elegibilidad_conciliacion(%s::uuid) e",
                                                (fila["id"],)))}
        out["simulacion"] = _simular(lector, fila["id"])
        resultado_json = lector.json("select coalesce(resultado_json, 'null'::jsonb)::text "
                                     "from public.normalizacion_ejecuciones where id = %s::uuid",
                                     (fila["normalizacion_ejecucion_id"],))
        out["incidencias_normalizacion"] = _incidencias(resultado_json, numero)
        # Candidatos de las lineas sin casar: mismo numero (cualquier fecha) o mismo PUC a +-15 dias.
        candidatos = {}
        for linea in out["simulacion"].get("detalles", []):
            doc = linea.get("albaran_documental")
            if not doc or linea["tipo_relacion"] != "SIN_COINCIDENCIA":
                continue
            fecha = date.fromisoformat(doc["fecha_albaran"]) if doc.get("fecha_albaran") else None
            candidatos[doc["numero_albaran"] or f"orden-{linea['orden']}"] = [json.loads(r[0]) for r in lector.filas(
                "select jsonb_build_object('id_contador', a.id_contador, 'id_proveedor', a.id_proveedor, "
                "'proveedor', a.proveedor, 'numero_albaran', a.numero_albaran, 'fecha', a.fecha::text, "
                "'importe_puc', a.importe_puc::text, 'importe_pvp', a.importe_pvp::text, 'estado', a.estado, "
                "'reservado_por', (select f.numero_factura from public.conciliacion_albaranes_reservados r "
                "  join public.facturas f on f.id = r.factura_id "
                "  where r.albaran_farmacia = a.farmacia and r.albaran_id_contador = a.id_contador))::text "
                "from public.albaranes a where a.farmacia = 'PIO' and ("
                "  upper(replace(a.numero_albaran, ' ', '')) like '%%' || upper(replace(%s, ' ', '')) || '%%'"
                "  or (abs(a.importe_puc) = abs(%s::numeric) and a.fecha between %s::date and %s::date)) "
                "order by a.fecha, a.id_contador",
                (doc["numero_albaran"] or "", doc["importe_total"] or 0,
                 (fecha or date(1900, 1, 1)) - timedelta(days=15), (fecha or date(1900, 1, 1)) + timedelta(days=15)))]
        out["candidatos_lineas_sin_casar"] = candidatos
        return out

    _, datos = _ejecutar_lectura(leer)
    sim = datos["simulacion"]
    total = _d(datos["factura"]["importe_total"])
    filas, sin_casar, por_linea, movimientos = [], [], [], []
    suma_doc_albaranes = suma_doc_movimientos = suma_aplicado = CERO
    for linea in sim.get("detalles", []):
        aplicado = _d(linea["importe_aplicado"])
        suma_aplicado += aplicado
        prov = linea.get("provenance", {})
        if linea.get("albaran_documental"):
            doc = linea["albaran_documental"]
            importe_doc = _d(doc["importe_total"])
            if doc.get("tipo_movimiento") == "ABONO":
                importe_doc = -abs(importe_doc)
            suma_doc_albaranes += importe_doc
            op = linea.get("albaran_operacional") or {}
            fila = {"orden": linea["orden"], "numero_pdf": doc["numero_albaran"], "fecha_pdf": doc["fecha_albaran"],
                    "importe_pdf": str(importe_doc), "tipo": doc.get("tipo_movimiento"),
                    "numero_farmatic": op.get("numero_albaran"), "fecha_farmatic": op.get("fecha"),
                    "puc_farmatic": op.get("importe_puc"), "pvp_farmatic": op.get("importe_pvp"),
                    "id_contador": op.get("id_contador"), "aplicado": str(aplicado),
                    "diferencia_linea": str(importe_doc - aplicado), "estado_matching": prov.get("estado_matching"),
                    "clase_numero": prov.get("clase_numero"), "relacion": linea["tipo_relacion"]}
            filas.append(fila)
            if linea["tipo_relacion"] == "SIN_COINCIDENCIA":
                sin_casar.append(fila)
            elif importe_doc != aplicado:
                por_linea.append(fila)
        elif linea.get("movimiento"):
            m = linea["movimiento"]
            importe_doc = _d(m.get("importe"))
            importe_doc = -abs(importe_doc) if m.get("sentido") == "ABONO" else abs(importe_doc)
            suma_doc_movimientos += importe_doc
            movimientos.append({"orden": linea["orden"], "categoria": m.get("categoria"),
                                "descripcion": m.get("descripcion_literal"), "sentido": m.get("sentido"),
                                "importe_pdf": str(importe_doc), "aplicado": str(aplicado),
                                "diferencia_linea": str(importe_doc - aplicado), "relacion": linea["tipo_relacion"]})
        else:
            movimientos.append({"orden": linea["orden"], "relacion": linea["tipo_relacion"], "aplicado": str(aplicado),
                                "provenance": prov})
    componentes = {
        "residual_documental_total_menos_lineas": str(total - suma_doc_albaranes - suma_doc_movimientos),
        "albaranes_sin_casar": str(sum((_d(f["importe_pdf"]) for f in sin_casar), CERO)),
        "diferencias_por_linea_casadas": str(sum((_d(f["diferencia_linea"]) for f in por_linea), CERO)),
        "diferencias_movimientos": str(sum((_d(m.get("diferencia_linea")) for m in movimientos), CERO)),
    }
    explicacion = sum((_d(v) for v in componentes.values()), CERO)
    datos["descomposicion"] = {
        "importe_factura": str(total), "suma_pdf_albaranes": str(suma_doc_albaranes),
        "suma_pdf_movimientos": str(suma_doc_movimientos), "importe_explicado": str(suma_aplicado),
        "diferencia_simulada": sim.get("diferencia"), "componentes": componentes,
        "suma_componentes": str(explicacion),
        "cuadra": sim.get("diferencia") is not None and explicacion == _d(sim["diferencia"]),
        "albaranes_sin_casar": sin_casar, "lineas_casadas_con_diferencia": por_linea, "movimientos": movimientos,
    }
    datos["tabla_lineas"] = filas
    sha = _escribir(salida, datos)
    resumen = {"factura": datos["factura"], "elegibilidad": datos["elegibilidad"],
               "simulacion": {k: sim.get(k) for k in ("camino", "resultado", "importe_explicado", "diferencia",
                                                       "tolerancia", "resumen_detalles", "fallo")},
               "descomposicion": datos["descomposicion"],
               "incidencias_normalizacion": datos["incidencias_normalizacion"],
               "candidatos_lineas_sin_casar": datos["candidatos_lineas_sin_casar"]}
    print(json.dumps(resumen, ensure_ascii=False, indent=1, default=str))
    print("sha256", sha)
    return 0


if __name__ == "__main__":
    sys.exit(diagnostico(sys.argv[1], _salida_fuera_del_repo(sys.argv[2])))
