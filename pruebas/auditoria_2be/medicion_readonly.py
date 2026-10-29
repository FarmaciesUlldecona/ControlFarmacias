"""Hito 2BE, paso 1: medicion de R17 (linea PDF = albaran de su numero + 1 interno de la misma recepcion).

Uso:
  python -B pruebas/auditoria_2be/medicion_readonly.py volcado <salida.json>
  python -B pruebas/auditoria_2be/medicion_readonly.py medir <motor_banco.json> <volcado.json> <salida.json>
  python -B pruebas/auditoria_2be/medicion_readonly.py verificar <motor_banco.json> <volcado.json> <medicion.json> <salida.json>

``volcado`` lee Supabase (solo PIO) con la puerta READ_ONLY del 2AT: albaranes con ``id_recepcion``,
reservas vigentes con su factura, ausentes en Farmatic (2BD) y facturas. No toca Farmatic.
``medir`` no se conecta a nada: concilia el banco Alliance del 2AZ con ``buscar_albaranes_factura`` de
src (como ``verificar_banco_2ba.py``, partiendo de las reservas vigentes de produccion) y, para cada
linea sin casar, busca parejas R17: albaran de su numero (EXACTA o LETRA_FINAL, +-15 dias) + un albaran
con numeracion interna ``[A-Z]\\d{6}/\\d{4}`` de la misma recepcion, ambos libres, mismo proveedor y suma
de PUC dentro de la tolerancia por linea. Mide tambien el riesgo de casado falso: parejas ambiguas,
parejas por azar con internos de OTRA recepcion y internos que casarian 1:1 con otra linea.
``verificar`` (tras implementar R17) concilia el mismo banco con el codigo de src (``id_recepcion`` en los
candidatos, ``detalles_desde_busqueda``) y exige las mismas lineas R17 y los mismos resultados que la
medicion aprobada por Pio. Salidas fuera del repositorio.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2ay"))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2ba"))

TOLERANCIA_LINEA = Decimal("0.05")

CONSULTAS = {
    "albaranes": (
        "select jsonb_build_object('id_contador', id_contador, 'farmacia', farmacia, 'id_proveedor', id_proveedor, "
        "'proveedor', proveedor, 'numero_albaran', numero_albaran, 'fecha', fecha::text, "
        "'importe_puc', importe_puc::text, 'importe_pvp', importe_pvp::text, 'estado', estado, "
        "'id_recepcion', id_recepcion)::text from public.albaranes where farmacia = 'PIO' order by id_contador"),
    "reservas": (
        "select jsonb_build_object('albaran_farmacia', r.albaran_farmacia, 'albaran_id_contador', "
        "r.albaran_id_contador, 'factura_id', r.factura_id::text, 'numero_factura', f.numero_factura)::text "
        "from public.conciliacion_albaranes_reservados r join public.facturas f on f.id = r.factura_id "
        "order by r.albaran_id_contador"),
    "presencia": (
        "select jsonb_build_object('id', id, 'id_contador', id_contador, 'valor_nuevo', valor_nuevo)::text "
        "from public.albaranes_cambios where farmacia = 'PIO' and campo = 'presencia' order by id"),
    "facturas": (
        "select jsonb_build_object('id', id::text, 'numero_factura', numero_factura, 'fecha_factura', "
        "fecha_factura::text, 'importe_total', importe_total::text, 'estado_conciliacion_cf', "
        "estado_conciliacion_cf)::text from public.facturas where farmacia = 'PIO' order by fecha_factura, id"),
}


def volcado(salida: Path) -> int:
    from auditoria_readonly import _ejecutar_lectura, _escribir

    def leer(lector) -> dict:
        return {nombre: [json.loads(f[0]) for f in lector.filas(sql)] for nombre, sql in CONSULTAS.items()}

    _, datos = _ejecutar_lectura(leer)
    sha = _escribir(salida, datos)
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in datos.items()}, ensure_ascii=False))
    print("sha256", sha)
    return 0


# --------------------------------------------------------------------------- medicion (sin conexion)

def _parejas(doc, libres, recepcion, *, alliance, mismo_recepcion=True, por_recepcion=None, todos=None):
    """Parejas (A, B): A = albaran de su numero; B = interno libre; suma de PUC dentro de la tolerancia."""
    from src.facturas.runtime_supabase.conciliacion import (
        VENTANA_FECHA_DIAS, VENTANA_SIN_NUMERO_DIAS, _NUMERO_INTERNO_FARMATIC, _id_proveedor_comparable,
        clasificar_numero_albaran, dinero)

    if doc.fecha is None or doc.importe is None:
        return []
    esperado = dinero(doc.importe)
    clases = {r.id_contador: clasificar_numero_albaran(doc.numero, r.numero_albaran, alliance=alliance)
              for r in libres}
    con_numero = [r for r in libres if clases[r.id_contador] in ("EXACTA", "LETRA_FINAL")
                  and abs((r.fecha - doc.fecha).days) <= VENTANA_FECHA_DIAS]
    if any(clases[r.id_contador] == "EXACTA" for r in con_numero):
        con_numero = [r for r in con_numero if clases[r.id_contador] == "EXACTA"]
    out = []
    for a in con_numero:
        if a.importe_puc is None:
            continue
        if mismo_recepcion:
            rec = recepcion.get(a.id_contador)
            if rec is None:
                continue
            bs = [b for b in por_recepcion.get(rec, []) if b.id_contador != a.id_contador]
        else:  # control de azar: internos de OTRA recepcion, +-3 dias de la linea
            rec = recepcion.get(a.id_contador)
            bs = [b for b in todos if b.id_contador != a.id_contador and recepcion.get(b.id_contador) != rec
                  and abs((b.fecha - doc.fecha).days) <= VENTANA_SIN_NUMERO_DIAS]
        for b in bs:
            if (b.importe_puc is None or not _NUMERO_INTERNO_FARMATIC.match(b.numero_albaran.strip().upper())
                    or _id_proveedor_comparable(b.id_proveedor) != _id_proveedor_comparable(a.id_proveedor)):
                continue
            suma = dinero(a.importe_puc) + dinero(b.importe_puc)
            if abs(suma - esperado) <= TOLERANCIA_LINEA:
                out.append((a, b, suma, clases[a.id_contador]))
    return out


def medir(motor: Path, volcado_ruta: Path, salida: Path) -> int:
    from analisis_2ay import candidatos_operacionales, elegibilidad
    from verificar_banco_2ba import REGLA, lineas_sumadas
    from src.facturas.runtime_supabase.conciliacion import (
        AlbaranDocumentalTrabajo, MovimientoDocumentalTrabajo, PROVEEDOR_CANONICO_ALLIANCE, _clave_albaran,
        _filas_del_proveedor, _importe_compatible, buscar_albaranes_factura, conciliar_importes,
        construir_detalles_movimientos_documentales, detalle_desde_busqueda, dinero)

    docs_banco = json.loads(motor.read_text(encoding="utf-8"))["documentos"]
    v = json.loads(volcado_ruta.read_text(encoding="utf-8"))
    ultimo: dict[int, str] = {}
    for p in v["presencia"]:
        ultimo[int(p["id_contador"])] = p["valor_nuevo"]
    ausentes = {c for c, x in ultimo.items() if x == "AUSENTE"}
    filas = [a for a in v["albaranes"] if int(a["id_contador"]) not in ausentes]
    operacionales = candidatos_operacionales(filas)
    recepcion = {int(a["id_contador"]): a.get("id_recepcion") for a in filas}
    vigentes = {(r["albaran_farmacia"], int(r["albaran_id_contador"])): r["numero_factura"] for r in v["reservas"]}
    facturas = [f for d in docs_banco for f in (d.get("oficial") or {}).get("facturas_normalizadas") or []
                if f.get("autorizable")]
    numeros = {f["numero"]: {a.get("numero") for a in f.get("albaranes", []) if a.get("numero")} for f in facturas}
    produccion = {f["numero_factura"]: f for f in v["facturas"]}

    ocupados = dict(vigentes)
    obtenido, lineas_r17, ambiguas, azar, conflictos_internos = {}, [], [], [], []
    for f in sorted(facturas, key=lambda x: (x.get("fecha") or "9999", x["numero"])):
        el = elegibilidad(f, REGLA.para(lineas_sumadas(f)))
        if el[0] != "APTA":
            obtenido[f["numero"]] = {"resultado": f"NO_APTA:{el[1]}"}
            continue
        otras = {k for k, n in ocupados.items() if n != f["numero"]}
        numeros_otras = set().union(*(x for k, x in numeros.items() if k != f["numero"]))
        naturaleza = f.get("naturaleza_principal")
        detalles = []
        if naturaleza in {"SERVICIOS", "MIXTA"}:
            movs = [MovimientoDocumentalTrabajo(
                id=f"m{i}", concepto_literal=str(m.get("descripcion")), tipo=str(m.get("tipo")), sentido=m.get("sentido"),
                importe=Decimal(str(m["importe"])) if m.get("importe") is not None else None,
                base=Decimal(str(m["base"])) if m.get("base") is not None else None)
                for i, m in enumerate(f.get("movimientos", []), 1)]
            md = construir_detalles_movimientos_documentales(movs)
            if md is None:
                obtenido[f["numero"]] = {"resultado": "FALLO:TRAZABILIDAD_SERVICIO_INSUFICIENTE"}
                continue
            detalles.extend(md)
        docs = [AlbaranDocumentalTrabajo(
            f"a{i}", a.get("numero"), date.fromisoformat(a["fecha"]) if a.get("fecha") else None,
            Decimal(str(a["importe_total"])) if a.get("importe_total") is not None else None, a.get("sentido"))
            for i, a in enumerate(f.get("albaranes", []), 1)] if naturaleza in {"MERCANCIA", "MIXTA"} else []
        resultados = buscar_albaranes_factura(docs, operacionales, proveedor_literal=f.get("proveedor_nombre"),
                                              ocupados=otras, numeros_otras_facturas=numeros_otras)
        det_1a1 = [detalle_desde_busqueda(d, r) for d, r in zip(docs, resultados)]
        r_antes = conciliar_importes(Decimal(str(f["total"])), [*detalles, *det_1a1], regla=REGLA)
        propios = {_clave_albaran(x.candidato) for x in resultados
                   if x.candidato is not None and x.importe_compatible is not None}

        provider_key, by_provider = _filas_del_proveedor(tuple(operacionales), f.get("proveedor_nombre"), None)
        alliance = provider_key == PROVEEDOR_CANONICO_ALLIANCE
        por_recepcion = defaultdict(list)
        for r in by_provider:
            if recepcion.get(r.id_contador) is not None:
                por_recepcion[recepcion[r.id_contador]].append(r)
        sumas_r17: list[Decimal] = []
        casados_r17 = 0
        usados_r17: set = set()
        for d, x in zip(docs, resultados):
            if x.candidato is not None and x.importe_compatible is not None:
                continue
            bloqueados = otras | propios | usados_r17
            libres = [r for r in by_provider if _clave_albaran(r) not in bloqueados]
            libres_por_rec = {k: [r for r in rs if _clave_albaran(r) not in bloqueados]
                              for k, rs in por_recepcion.items()}
            parejas = _parejas(d, libres, recepcion, alliance=alliance, por_recepcion=libres_por_rec)
            control = _parejas(d, libres, recepcion, alliance=alliance, mismo_recepcion=False, todos=libres)
            if control:
                azar.append({"factura": f["numero"], "numero_pdf": d.numero, "importe_pdf": str(d.importe),
                             "parejas_otra_recepcion": len(control)})
            if not parejas:
                continue
            item = {"factura": f["numero"], "numero_pdf": d.numero, "fecha_pdf": d.fecha.isoformat(),
                    "importe_pdf": str(d.importe), "estado_1a1": x.estado,
                    "parejas": [{"a": (a.id_contador, a.numero_albaran, str(a.importe_puc), clase, a.fecha.isoformat()),
                                 "b": (b.id_contador, b.numero_albaran, str(b.importe_puc), b.fecha.isoformat()),
                                 "id_recepcion": recepcion[a.id_contador],
                                 "albaranes_en_recepcion": len(por_recepcion[recepcion[a.id_contador]]),
                                 "suma": str(s), "diferencia": str(dinero(d.importe) - s)}
                                for a, b, s, clase in parejas]}
            if len(parejas) > 1:
                ambiguas.append(item)
                continue
            a, b, s, _ = parejas[0]
            # Riesgo: el interno B casaria 1:1 por PUC con otra linea documental (+-3 dias) de alguna factura.
            for g in facturas:
                for la in g.get("albaranes", []):
                    if la.get("importe_total") is None or not la.get("fecha") or (g["numero"], la.get("numero")) == (
                            f["numero"], d.numero):
                        continue
                    doc_g = AlbaranDocumentalTrabajo("x", la.get("numero"), date.fromisoformat(la["fecha"]),
                                                     Decimal(str(la["importe_total"])), la.get("sentido"))
                    if abs((b.fecha - doc_g.fecha).days) <= 3 and _importe_compatible(
                            dinero(doc_g.importe), b, TOLERANCIA_LINEA, solo_puc=True) is not None:
                        conflictos_internos.append({"r17": [f["numero"], d.numero, b.id_contador, b.numero_albaran],
                                                    "otra_linea": [g["numero"], la.get("numero"), la["importe_total"]]})
            lineas_r17.append(item)
            usados_r17 |= {_clave_albaran(a), _clave_albaran(b)}
            sumas_r17.append(s)
            casados_r17 += 1
        r_despues = r_antes
        if casados_r17:
            from src.facturas.runtime_supabase.modelos import DetalleConciliacion, TipoRelacionConciliacion
            # Cada linea R17 cuenta como 1 albaran casado a efectos de R11 (n = lineas casadas + R17).
            sinteticos = [DetalleConciliacion(tipo_relacion=TipoRelacionConciliacion.UNO_A_UNO, importe_aplicado=s,
                                              factura_albaran_extraido_id=f"r17-{i}",
                                              provenance={"fuente": "MEDICION_R17"})
                          for i, s in enumerate(sumas_r17)]
            base = [*detalles, *det_1a1]
            r_despues = conciliar_importes(Decimal(str(f["total"])), base + sinteticos, regla=REGLA)
        reservados = propios | usados_r17
        for k in reservados:
            ocupados[k] = f["numero"]
        obtenido[f["numero"]] = {
            "antes": {"resultado": r_antes.resultado, "diferencia": str(r_antes.diferencia),
                      "casados": r_antes.albaranes_casados, "tolerancia": str(r_antes.tolerancia)},
            "despues": {"resultado": r_despues.resultado, "diferencia": str(r_despues.diferencia),
                        "casados": r_despues.albaranes_casados, "tolerancia": str(r_despues.tolerancia)},
            "lineas_r17": casados_r17,
            "en_produccion": (produccion.get(f["numero"]) or {}).get("estado_conciliacion_cf")}

    cambian = {n: o for n, o in obtenido.items() if "antes" in o and o["antes"] != o["despues"]}
    resumen = {
        "albaranes": len(v["albaranes"]), "con_id_recepcion": sum(1 for a in v["albaranes"] if a.get("id_recepcion")),
        "ausentes_excluidos": len(ausentes), "reservas_vigentes": len(vigentes), "facturas_banco": len(obtenido),
        "lineas_r17_unicas": len(lineas_r17), "lineas_r17_ambiguas": len(ambiguas),
        "facturas_r17": sorted({x["factura"] for x in lineas_r17}),
        "facturas_que_cambian": {n: {"antes": o["antes"], "despues": o["despues"], "lineas_r17": o["lineas_r17"],
                                     "en_produccion": o["en_produccion"]} for n, o in cambian.items()},
        "riesgo": {"lineas_con_pareja_de_otra_recepcion": len(azar),
                   "internos_r17_que_casarian_1a1_con_otra_linea": len(conflictos_internos)},
    }
    salida.write_text(json.dumps({"resumen": resumen, "lineas_r17": lineas_r17, "ambiguas": ambiguas, "azar": azar,
                                  "conflictos_internos": conflictos_internos, "obtenido": obtenido},
                                 ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=1, default=str))
    return 0


def verificar(motor: Path, volcado_ruta: Path, medicion: Path, salida: Path) -> int:
    from analisis_2ay import elegibilidad
    from verificar_banco_2ba import REGLA, lineas_sumadas
    from src.facturas.runtime_supabase.conciliacion import (
        AlbaranDocumentalTrabajo, CandidatoAlbaranSupabase, MovimientoDocumentalTrabajo, _clave_albaran,
        buscar_albaranes_factura, conciliar_importes, construir_detalles_movimientos_documentales,
        detalles_desde_busqueda)

    docs_banco = json.loads(motor.read_text(encoding="utf-8"))["documentos"]
    v = json.loads(volcado_ruta.read_text(encoding="utf-8"))
    aprobada = json.loads(medicion.read_text(encoding="utf-8"))
    ultimo: dict[int, str] = {}
    for p in v["presencia"]:
        ultimo[int(p["id_contador"])] = p["valor_nuevo"]
    operacionales = [CandidatoAlbaranSupabase(
        int(a["id_contador"]), a["farmacia"], str(a["id_proveedor"]), str(a["proveedor"]), str(a["numero_albaran"]),
        date.fromisoformat(a["fecha"]), Decimal(a["importe_puc"]) if a.get("importe_puc") is not None else None,
        Decimal(a["importe_pvp"]) if a.get("importe_pvp") is not None else None, a.get("estado"),
        id_recepcion=a.get("id_recepcion")) for a in v["albaranes"] if ultimo.get(int(a["id_contador"])) != "AUSENTE"]
    ocupados = {(r["albaran_farmacia"], int(r["albaran_id_contador"])): r["numero_factura"] for r in v["reservas"]}
    facturas = [f for d in docs_banco for f in (d.get("oficial") or {}).get("facturas_normalizadas") or []
                if f.get("autorizable")]
    numeros = {f["numero"]: {a.get("numero") for a in f.get("albaranes", []) if a.get("numero")} for f in facturas}
    obtenido, lineas = {}, []
    for f in sorted(facturas, key=lambda x: (x.get("fecha") or "9999", x["numero"])):
        el = elegibilidad(f, REGLA.para(lineas_sumadas(f)))
        if el[0] != "APTA":
            obtenido[f["numero"]] = {"resultado": f"NO_APTA:{el[1]}"}
            continue
        otras = {k for k, n in ocupados.items() if n != f["numero"]}
        numeros_otras = set().union(*(x for k, x in numeros.items() if k != f["numero"]))
        detalles = []
        if f.get("naturaleza_principal") in {"SERVICIOS", "MIXTA"}:
            md = construir_detalles_movimientos_documentales([MovimientoDocumentalTrabajo(
                id=f"m{i}", concepto_literal=str(m.get("descripcion")), tipo=str(m.get("tipo")), sentido=m.get("sentido"),
                importe=Decimal(str(m["importe"])) if m.get("importe") is not None else None,
                base=Decimal(str(m["base"])) if m.get("base") is not None else None)
                for i, m in enumerate(f.get("movimientos", []), 1)])
            if md is None:
                obtenido[f["numero"]] = {"resultado": "FALLO:TRAZABILIDAD_SERVICIO_INSUFICIENTE"}
                continue
            detalles.extend(md)
        docs = [AlbaranDocumentalTrabajo(
            f"a{i}", a.get("numero"), date.fromisoformat(a["fecha"]) if a.get("fecha") else None,
            Decimal(str(a["importe_total"])) if a.get("importe_total") is not None else None, a.get("sentido"))
            for i, a in enumerate(f.get("albaranes", []), 1)] if f.get("naturaleza_principal") in {"MERCANCIA", "MIXTA"}             else []
        resultados = buscar_albaranes_factura(docs, operacionales, proveedor_literal=f.get("proveedor_nombre"),
                                              ocupados=otras, numeros_otras_facturas=numeros_otras)
        detalles.extend(x for d, r in zip(docs, resultados) for x in detalles_desde_busqueda(d, r))
        r = conciliar_importes(Decimal(str(f["total"])), detalles, regla=REGLA)
        for d, x in zip(docs, resultados):
            if x.estado == "MATCH_R17":
                lineas.append([f["numero"], d.numero, x.candidato.id_contador, x.complementario.id_contador])
        for x in resultados:
            if x.candidato is not None and x.importe_compatible is not None:
                ocupados[_clave_albaran(x.candidato)] = f["numero"]
                if x.complementario is not None:
                    ocupados[_clave_albaran(x.complementario)] = f["numero"]
        obtenido[f["numero"]] = {"resultado": r.resultado, "diferencia": str(r.diferencia),
                                 "casados": r.albaranes_casados}
    esperadas = sorted([x["factura"], x["numero_pdf"], x["parejas"][0]["a"][0], x["parejas"][0]["b"][0]]
                       for x in aprobada["lineas_r17"])
    diferencias = [{"numero": n, "medicion": {k: m["despues"][k] for k in ("resultado", "diferencia", "casados")},
                    "src": obtenido[n]} for n, m in aprobada["obtenido"].items()
                   if "despues" in m and {k: m["despues"][k] for k in ("resultado", "diferencia", "casados")}
                   != obtenido[n]]
    informe = {"lineas_r17_src": sorted(lineas), "lineas_iguales_a_la_medicion": sorted(lineas) == esperadas,
               "diferencias_de_resultado": diferencias, "obtenido": obtenido}
    salida.write_text(json.dumps(informe, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: informe[k] for k in ("lineas_iguales_a_la_medicion", "diferencias_de_resultado")} |
                     {"lineas_r17_src": len(lineas)}, ensure_ascii=False, indent=1, default=str))
    return 0 if informe["lineas_iguales_a_la_medicion"] and not diferencias else 1


if __name__ == "__main__":
    from auditoria_readonly import _salida_fuera_del_repo

    if sys.argv[1] == "volcado":
        sys.exit(volcado(_salida_fuera_del_repo(sys.argv[2])))
    if sys.argv[1] == "medir":
        sys.exit(medir(Path(sys.argv[2]), Path(sys.argv[3]), _salida_fuera_del_repo(sys.argv[4])))
    if sys.argv[1] == "verificar":
        sys.exit(verificar(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), _salida_fuera_del_repo(sys.argv[5])))
    raise SystemExit("modo desconocido")
