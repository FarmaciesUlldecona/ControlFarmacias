"""Hito 2BG, paso 1: medicion de la regla ECO360 = Alliance/SAFA en conciliacion (sin implementar).

Uso:
  python -B pruebas/auditoria_2bg/medicion_readonly.py lectura <salida.json>
  python -B pruebas/auditoria_2bg/medicion_readonly.py medir <motor_banco.json> <volcado.json> <lectura.json> <salida.json>

``lectura`` (puerta READ_ONLY del 2AT, solo PIO, sin Farmatic): proveedores de ``albaranes`` cuyo nombre
contiene PLATAF o ECO (id, nombre, n.o de albaranes) y los albaranes de esos proveedores cuyo numero aparece
como linea documental de alguna factura en Supabase. El volcado de albaranes, reservas y facturas es el de
``pruebas/auditoria_2be/medicion_readonly.py volcado``.

``medir`` no se conecta a nada: concilia el banco Alliance del 2AZ con el codigo de ``src`` (igual que el
``verificar`` del 2BE, R17 incluido, partiendo de las reservas vigentes) dos veces:
- ``actual``: el codigo tal cual;
- ``regla``: con la regla propuesta aplicada SOLO aqui (parche en memoria, ``src`` no cambia): el proveedor
  ECO360 canonicaliza al grupo Alliance (camino por nombre) y su id de Farmatic compara como el de SAFA
  (camino por id y mismo proveedor de R17).
Informa de las facturas que cambian, de cada casado nuevo con un albaran ECO360 (clase de numero, fechas,
importes) y de las lineas R17 cuya pareja mezcla los dos ids de Farmatic. Salidas fuera del repositorio.
"""
from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2ay"))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2ba"))

FILTRO_PLATAFORMAS = "(proveedor ilike '%PLATAF%' or proveedor ilike '%ECO%')"
# Proveedor ECO360 de Farmatic (diagnostico READ_ONLY de 08007970, 2026-10-30) e id de SAFA.
ECO360_NOMBRE_CANONICO = "6PLATAFECO360AH"
ECO360_ID = "154"
SAFA_ID = "2"


def lectura(salida: Path) -> int:
    from auditoria_readonly import _ejecutar_lectura, _escribir

    def leer(lector) -> dict:
        proveedores = [json.loads(r[0]) for r in lector.filas(
            "select jsonb_build_object('id_proveedor', id_proveedor, 'proveedor', proveedor, 'albaranes', count(*), "
            "'primera', min(fecha)::text, 'ultima', max(fecha)::text)::text from public.albaranes "
            f"where farmacia = 'PIO' and {FILTRO_PLATAFORMAS} group by id_proveedor, proveedor "
            "order by id_proveedor, proveedor")]
        en_facturas = [json.loads(r[0]) for r in lector.filas(
            "select jsonb_build_object('id_contador', a.id_contador, 'id_proveedor', a.id_proveedor, "
            "'proveedor', a.proveedor, 'numero_albaran', a.numero_albaran, 'fecha', a.fecha::text, "
            "'importe_puc', a.importe_puc::text, 'factura', f.numero_factura, 'proveedor_factura', "
            "f.proveedor_literal, 'estado_factura', f.estado_conciliacion_cf, 'importe_linea', "
            "e.importe_total::text, 'fecha_linea', e.fecha_albaran::text)::text "
            "from public.albaranes a join public.facturas_albaranes_extraidos e "
            "on upper(btrim(e.numero_albaran)) = upper(btrim(a.numero_albaran)) "
            "join public.facturas f on f.id = e.factura_id "
            f"where a.farmacia = 'PIO' and {FILTRO_PLATAFORMAS.replace('proveedor', 'a.proveedor')} "
            "order by a.id_contador")]
        return {"proveedores_plataforma": proveedores, "albaranes_plataforma_en_facturas": en_facturas}

    _, datos = _ejecutar_lectura(leer)
    sha = _escribir(salida, datos)
    print(json.dumps(datos, ensure_ascii=False, indent=1, default=str))
    print("sha256", sha)
    return 0


@contextmanager
def _regla_eco360():
    """La regla propuesta, en memoria: nombre ECO360 -> grupo Alliance; id 154 compara como 2."""
    import src.facturas.runtime_supabase.conciliacion as c

    canonicalizar, comparable = c.canonicalizar_proveedor, c._id_proveedor_comparable

    def canonicalizar_regla(valor):
        k = canonicalizar(valor)
        return c.PROVEEDOR_CANONICO_ALLIANCE if k == ECO360_NOMBRE_CANONICO else k

    def comparable_regla(valor):
        k = comparable(valor)
        return SAFA_ID if k == ECO360_ID else k

    c.canonicalizar_proveedor, c._id_proveedor_comparable = canonicalizar_regla, comparable_regla
    try:
        yield
    finally:
        c.canonicalizar_proveedor, c._id_proveedor_comparable = canonicalizar, comparable


def _conciliar_banco(facturas, operacionales, reservas) -> dict:
    """El ``verificar`` del 2BE (codigo de src, R17 incluido), devolviendo tambien cada casado."""
    from analisis_2ay import elegibilidad
    from verificar_banco_2ba import REGLA, lineas_sumadas
    from src.facturas.runtime_supabase.conciliacion import (
        AlbaranDocumentalTrabajo, MovimientoDocumentalTrabajo, _clave_albaran, buscar_albaranes_factura,
        conciliar_importes, construir_detalles_movimientos_documentales, detalles_desde_busqueda)

    ocupados = dict(reservas)
    numeros = {f["numero"]: {a.get("numero") for a in f.get("albaranes", []) if a.get("numero")} for f in facturas}
    obtenido = {}
    for f in sorted(facturas, key=lambda x: (x.get("fecha") or "9999", x["numero"])):
        el = elegibilidad(f, REGLA.para(lineas_sumadas(f)))
        if el[0] != "APTA":
            obtenido[f["numero"]] = {"resultado": f"NO_APTA:{el[1]}", "casados": {}}
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
                obtenido[f["numero"]] = {"resultado": "FALLO:TRAZABILIDAD_SERVICIO_INSUFICIENTE", "casados": {}}
                continue
            detalles.extend(md)
        docs = [AlbaranDocumentalTrabajo(
            f"a{i}", a.get("numero"), date.fromisoformat(a["fecha"]) if a.get("fecha") else None,
            Decimal(str(a["importe_total"])) if a.get("importe_total") is not None else None, a.get("sentido"))
            for i, a in enumerate(f.get("albaranes", []), 1)] if f.get("naturaleza_principal") in {"MERCANCIA", "MIXTA"} \
            else []
        resultados = buscar_albaranes_factura(docs, operacionales, proveedor_literal=f.get("proveedor_nombre"),
                                              ocupados=otras, numeros_otras_facturas=numeros_otras)
        detalles.extend(x for d, r in zip(docs, resultados) for x in detalles_desde_busqueda(d, r))
        r = conciliar_importes(Decimal(str(f["total"])), detalles, regla=REGLA)
        casados = {}
        for i, (d, x) in enumerate(zip(docs, resultados)):
            if x.candidato is None or x.importe_compatible is None:
                continue
            albaranes = [x.candidato] + ([x.complementario] if x.complementario is not None else [])
            casados[f"{i}:{d.numero}"] = {
                "linea": [d.numero, d.fecha.isoformat() if d.fecha else None, str(d.importe)],
                "estado": x.estado, "clase_numero": getattr(x, "clase_numero", None),
                "albaranes": [[a.id_contador, a.id_proveedor, a.proveedor, a.numero_albaran, a.fecha.isoformat(),
                               str(a.importe_puc)] for a in albaranes]}
            for a in albaranes:
                ocupados[_clave_albaran(a)] = f["numero"]
        obtenido[f["numero"]] = {"resultado": r.resultado, "diferencia": str(r.diferencia),
                                 "casados_n": r.albaranes_casados, "casados": casados}
    return obtenido


def _es_eco360(albaran) -> bool:
    from src.facturas.runtime_supabase.conciliacion import _id_proveedor_comparable, canonicalizar_proveedor

    return _id_proveedor_comparable(albaran[1]) == ECO360_ID or canonicalizar_proveedor(albaran[2]) == ECO360_NOMBRE_CANONICO


def medir(motor: Path, volcado_ruta: Path, lectura_ruta: Path, salida: Path) -> int:
    from src.facturas.runtime_supabase.conciliacion import CandidatoAlbaranSupabase

    docs_banco = json.loads(motor.read_text(encoding="utf-8"))["documentos"]
    v = json.loads(volcado_ruta.read_text(encoding="utf-8"))
    leido = json.loads(lectura_ruta.read_text(encoding="utf-8"))
    ultimo: dict[int, str] = {}
    for p in v["presencia"]:
        ultimo[int(p["id_contador"])] = p["valor_nuevo"]
    operacionales = [CandidatoAlbaranSupabase(
        int(a["id_contador"]), a["farmacia"], str(a["id_proveedor"]), str(a["proveedor"]), str(a["numero_albaran"]),
        date.fromisoformat(a["fecha"]), Decimal(a["importe_puc"]) if a.get("importe_puc") is not None else None,
        Decimal(a["importe_pvp"]) if a.get("importe_pvp") is not None else None, a.get("estado"),
        id_recepcion=a.get("id_recepcion")) for a in v["albaranes"] if ultimo.get(int(a["id_contador"])) != "AUSENTE"]
    reservas = {(r["albaran_farmacia"], int(r["albaran_id_contador"])): r["numero_factura"] for r in v["reservas"]}
    facturas = [f for d in docs_banco for f in (d.get("oficial") or {}).get("facturas_normalizadas") or []
                if f.get("autorizable")]
    produccion = {f["numero_factura"]: f.get("estado_conciliacion_cf") for f in v["facturas"]}

    actual = _conciliar_banco(facturas, operacionales, reservas)
    with _regla_eco360():
        regla = _conciliar_banco(facturas, operacionales, reservas)

    def resumen(o):
        return {k: o.get(k) for k in ("resultado", "diferencia", "casados_n")}

    cambian = {n: {"actual": resumen(actual[n]), "regla": resumen(regla[n]), "en_produccion": produccion.get(n)}
               for n in actual if resumen(actual[n]) != resumen(regla[n])}
    casados_eco360, casados_perdidos, r17_mixtas = [], [], []
    for n in regla:
        nuevos = {k: x for k, x in regla[n]["casados"].items() if actual[n]["casados"].get(k) != x}
        for k, x in nuevos.items():
            item = {"factura": n, **x, "actual": actual[n]["casados"].get(k)}
            if any(_es_eco360(a) for a in x["albaranes"]):
                casados_eco360.append(item)
            else:
                casados_perdidos.append(item)  # cambio en un casado sin ECO360: efecto colateral a revisar
            if len(x["albaranes"]) == 2 and len({a[1].strip().lstrip("0") for a in x["albaranes"]}) == 2:
                r17_mixtas.append(item)
        for k, x in actual[n]["casados"].items():
            if k not in regla[n]["casados"]:
                casados_perdidos.append({"factura": n, "perdido": x})
    ids_eco360 = {int(a["id_contador"]) for a in v["albaranes"]
                  if str(a["id_proveedor"]).strip().lstrip("0") == ECO360_ID}
    informe = {
        "proveedores_plataforma": leido["proveedores_plataforma"],
        "albaranes_eco360": len(ids_eco360),
        "albaranes_plataforma_en_facturas_supabase": leido["albaranes_plataforma_en_facturas"],
        "facturas_banco": len(actual),
        "facturas_que_cambian": cambian,
        "casados_nuevos_eco360": casados_eco360,
        "efectos_colaterales": casados_perdidos,
        "r17_mixtas": r17_mixtas,
        "veredicto": "PARAR_R17_MIXTAS" if r17_mixtas else ("REVISAR_COLATERALES" if casados_perdidos else "MEDICION_OK"),
    }
    salida.write_text(json.dumps(informe, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: informe[k] for k in ("albaranes_eco360", "facturas_banco", "facturas_que_cambian",
                                              "r17_mixtas", "veredicto")}
                     | {"casados_nuevos_eco360": len(casados_eco360), "efectos_colaterales": len(casados_perdidos)},
                     ensure_ascii=False, indent=1, default=str))
    return 0 if informe["veredicto"] == "MEDICION_OK" else 3


if __name__ == "__main__":
    from auditoria_readonly import _salida_fuera_del_repo

    if sys.argv[1] == "lectura":
        sys.exit(lectura(_salida_fuera_del_repo(sys.argv[2])))
    if sys.argv[1] == "medir":
        sys.exit(medir(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), _salida_fuera_del_repo(sys.argv[5])))
    raise SystemExit("modo desconocido")
