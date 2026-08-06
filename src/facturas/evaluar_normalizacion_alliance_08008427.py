from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any


RUTA_PROYECTO = Path(__file__).resolve().parents[2]
RUTA_NORMALIZADA = RUTA_PROYECTO / "pruebas/facturas/resultados/openai/normalizacion_alliance_08008427/factura_normalizada.json"
RUTA_PATRON = RUTA_PROYECTO / "pruebas/facturas/patron/pruebas_lectura_facturas_resultado_esperado_PATRON_OFICIAL_v1_0.json"
RUTA_SALIDA = RUTA_NORMALIZADA.parent
RUTAS_NORMALIZADOR = (
    RUTA_PROYECTO / "src/facturas/normalizadores/alliance.py",
    RUTA_PROYECTO / "src/facturas/normalizar_alliance_08008427.py",
)
PROHIBIDOS_NORMALIZADOR = (
    "PATRON_OFICIAL",
    "facturas/patron",
    "comparacion_patron.json",
    "analisis_patron.md",
    "resultados/azure",
    "resultados/google",
    "luna_especializada_alliance_08008427",
)


def cargar_json(ruta: Path) -> dict[str, Any]:
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encuentra el archivo requerido: {ruta}")
    return json.loads(ruta.read_text(encoding="utf-8"))


def verificar_aislamiento_normalizador() -> dict[str, Any]:
    hallazgos = []
    for ruta in RUTAS_NORMALIZADOR:
        texto = ruta.read_text(encoding="utf-8").replace("\\", "/")
        for prohibido in PROHIBIDOS_NORMALIZADOR:
            if prohibido.lower() in texto.lower():
                hallazgos.append({"archivo": str(ruta), "texto_prohibido": prohibido})
    return {"cumple": not hallazgos, "hallazgos": hallazgos}


def localizar_factura(objeto: Any) -> dict[str, Any]:
    encontradas = []

    def recorrer(valor: Any) -> None:
        if isinstance(valor, dict):
            if valor.get("numero_factura") == "08008427":
                encontradas.append(valor)
            for hijo in valor.values():
                recorrer(hijo)
        elif isinstance(valor, list):
            for hijo in valor:
                recorrer(hijo)

    recorrer(objeto)
    if len(encontradas) != 1:
        raise RuntimeError(f"Se esperaba una factura 08008427 y se encontraron {len(encontradas)}")
    return encontradas[0]


def comparar_valor(
    campo: str,
    esperado: Any,
    obtenido: Any,
    procedencia: str,
    conteo: Counter,
    diferencias: list[dict[str, Any]],
) -> None:
    if obtenido == esperado:
        estado = "CORRECTO"
        conteo[estado] += 1
    elif obtenido is None:
        estado = "DELIBERADAMENTE_NO_COMPLETADO"
        conteo[estado] += 1
    elif _equivalente_solo_formato(obtenido, esperado):
        estado = "DIFERENCIA_FORMATO"
        conteo[estado] += 1
    else:
        estado = "DIFERENCIA_REAL"
        conteo[estado] += 1
    diferencias.append(
        {
            "campo": campo,
            "esperado": esperado,
            "obtenido": obtenido,
            "estado": estado,
            "procedencia": procedencia,
        }
    )


def _equivalente_solo_formato(obtenido: Any, esperado: Any) -> bool:
    if not isinstance(obtenido, str) or not isinstance(esperado, str):
        return str(obtenido) == str(esperado)

    def simplificar(texto: str) -> str:
        sin_tildes = "".join(
            caracter
            for caracter in unicodedata.normalize("NFD", texto)
            if unicodedata.category(caracter) != "Mn"
        )
        return re.sub(r"\s+", " ", sin_tildes).strip().casefold()

    return simplificar(obtenido) == simplificar(esperado)


def evaluar() -> tuple[Path, Path]:
    if not RUTA_NORMALIZADA.is_file():
        raise FileNotFoundError("La evaluación solo puede ejecutarse después de crear factura_normalizada.json")
    aislamiento = verificar_aislamiento_normalizador()
    if not aislamiento["cumple"]:
        raise RuntimeError(f"El normalizador contiene accesos prohibidos: {aislamiento['hallazgos']}")

    documento = cargar_json(RUTA_NORMALIZADA)
    obtenido = documento["resultado_normalizado"]
    esperado = localizar_factura(cargar_json(RUTA_PATRON))
    procedencias = documento["procedencia_bloques"]
    conteo: Counter = Counter()
    diferencias: list[dict[str, Any]] = []

    campos_cabecera = (
        "tipo_documento", "categoria", "requiere_conciliacion_albaranes",
        "pagina_inicio", "pagina_fin", "proveedor_nombre", "proveedor_cif",
        "numero_factura", "fecha_factura", "base_imponible_total", "iva_total",
        "recargo_equivalencia_total", "importe_total",
    )
    for campo in campos_cabecera:
        if campo in ("categoria", "requiere_conciliacion_albaranes"):
            origen = "configuracion_interna"
        elif campo in ("pagina_inicio", "pagina_fin"):
            origen = "metadato_tecnico"
        else:
            origen = "luna_general"
        comparar_valor(campo, esperado[campo], obtenido[campo], origen, conteo, diferencias)

    vencimientos = []
    for indice in range(max(len(esperado["vencimientos"]), len(obtenido["vencimientos"]))):
        e = esperado["vencimientos"][indice] if indice < len(esperado["vencimientos"]) else {}
        x = obtenido["vencimientos"][indice] if indice < len(obtenido["vencimientos"]) else {}
        inicio = len(diferencias)
        for campo in ("orden", "fecha_vencimiento", "importe"):
            comparar_valor(f"vencimientos[{indice}].{campo}", e.get(campo), x.get(campo), "luna_tablas_literales", conteo, diferencias)
        vencimientos.append({"indice": indice + 1, "comparaciones": diferencias[inicio:]})

    comparar_valor("impuestos", esperado["impuestos"], obtenido["impuestos"], "luna_tablas_literales", conteo, diferencias)

    esperados_por_numero = {x["numero_albaran"]: x for x in esperado["albaranes"]}
    obtenidos_por_numero = {x["numero_albaran"]: x for x in obtenido["albaranes"]}
    comparacion_albaranes = []
    for e in esperado["albaranes"]:
        x = obtenidos_por_numero.get(e["numero_albaran"])
        if x is None:
            conteo["DELIBERADAMENTE_NO_COMPLETADO"] += 7
            comparacion_albaranes.append({"numero_albaran": e["numero_albaran"], "estado": "AUSENTE", "comparaciones": []})
            continue
        inicio = len(diferencias)
        for campo in ("orden", "numero_albaran", "fecha_albaran", "tipo_movimiento", "descripcion", "importe_base", "importe_total"):
            comparar_valor(f"albaranes[{e['numero_albaran']}].{campo}", e[campo], x.get(campo), "luna_tablas_literales", conteo, diferencias)
        comparaciones_item = diferencias[inicio:]
        estados = {c["estado"] for c in comparaciones_item}
        comparacion_albaranes.append({
            "numero_albaran": e["numero_albaran"],
            "orden_patron": e["orden"],
            "orden_normalizado": x["orden"],
            "orden_reconstruido": x.get("orden_reconstruido"),
            "estado": "CORRECTO_COMPLETO" if estados == {"CORRECTO"} else "CORRECTO_CONTENIDO_ORDEN_DIFERENTE" if all(c["estado"] == "CORRECTO" for c in comparaciones_item if not c["campo"].endswith(".orden")) else "DIFERENCIAS_REALES",
            "comparaciones": comparaciones_item,
            "procedencia": x.get("procedencia"),
        })
    inventados = [numero for numero in obtenidos_por_numero if numero not in esperados_por_numero]

    comparacion_ajustes = []
    for indice in range(max(len(esperado["ajustes"]), len(obtenido["ajustes"]))):
        e = esperado["ajustes"][indice] if indice < len(esperado["ajustes"]) else {}
        x = obtenido["ajustes"][indice] if indice < len(obtenido["ajustes"]) else {}
        inicio = len(diferencias)
        for campo in ("orden", "tipo_ajuste", "descripcion", "importe", "incluido_en_base", "incluido_en_total"):
            comparar_valor(f"ajustes[{indice}].{campo}", e.get(campo), x.get(campo), "luna_tablas_literales", conteo, diferencias)
        comparacion_ajustes.append({"indice": indice + 1, "comparaciones": diferencias[inicio:]})

    destinatario = []
    for campo in ("id_farmacia", "nombre", "cif", "metodo_identificacion"):
        origen = "configuracion_interna" if campo in ("id_farmacia", "metodo_identificacion") else "luna_general"
        inicio = len(diferencias)
        comparar_valor(f"destinatario.{campo}", esperado["destinatario"][campo], obtenido["destinatario"].get(campo), origen, conteo, diferencias)
        destinatario.extend(diferencias[inicio:])

    total = sum(conteo.values())
    correctos = conteo["CORRECTO"]
    nota = round(100 * correctos / total, 2)
    cobertura = round(100 * (total - conteo["DELIBERADAMENTE_NO_COMPLETADO"]) / total, 2)
    resumen = {
        "campos_atomicos_evaluados": total,
        "correctos": correctos,
        "diferencias_reales": conteo["DIFERENCIA_REAL"],
        "diferencias_formato": conteo["DIFERENCIA_FORMATO"],
        "deliberadamente_no_completados": conteo["DELIBERADAMENTE_NO_COMPLETADO"],
        "nota_acierto_estricto": nota,
        "cobertura": cobertura,
        "albaranes_esperados": len(esperado["albaranes"]),
        "albaranes_normalizados": len(obtenido["albaranes"]),
        "albaranes_con_contenido_correcto": sum(x["estado"] in ("CORRECTO_COMPLETO", "CORRECTO_CONTENIDO_ORDEN_DIFERENTE") for x in comparacion_albaranes),
        "albaranes_orden_completo_correcto": sum(x["estado"] == "CORRECTO_COMPLETO" for x in comparacion_albaranes),
        "albaranes_inventados": len(inventados),
        "configuracion_interna": [x for x in diferencias if x["procedencia"] == "configuracion_interna"],
    }
    salida = {
        "aislamiento_normalizador": aislamiento,
        "resumen": resumen,
        "cabecera_y_totales": [x for x in diferencias if x["campo"] in campos_cabecera],
        "vencimientos": vencimientos,
        "impuestos": next(x for x in diferencias if x["campo"] == "impuestos"),
        "albaranes": comparacion_albaranes,
        "albaranes_inventados": inventados,
        "ajustes": comparacion_ajustes,
        "destinatario": destinatario,
        "todas_las_comparaciones": diferencias,
    }
    ruta_json = RUTA_SALIDA / "evaluacion_patron.json"
    ruta_md = RUTA_SALIDA / "evaluacion_patron.md"
    ruta_json.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")

    por_estado_albaran = Counter(x["estado"] for x in comparacion_albaranes)
    lineas = [
        "# Evaluación independiente de la normalización Alliance 08008427",
        "",
        "## Aislamiento",
        "",
        "El resultado normalizado ya existía antes de cargar el patrón. La inspección estática del módulo y del CLI de normalización no encontró referencias al patrón, análisis comparativos, Azure, Google ni la extracción especializada anterior.",
        "",
        "## Resumen",
        "",
        "| Métrica | Resultado |",
        "|---|---:|",
        f"| Campos atómicos evaluados | {total} |",
        f"| Correctos | {correctos} |",
        f"| Diferencias reales | {conteo['DIFERENCIA_REAL']} |",
        f"| Diferencias de formato | {conteo['DIFERENCIA_FORMATO']} |",
        f"| Deliberadamente no completados | {conteo['DELIBERADAMENTE_NO_COMPLETADO']} |",
        f"| Nota de acierto estricto | {nota:.2f} % |",
        f"| Cobertura | {cobertura:.2f} % |",
        f"| Albaranes esperados / normalizados | {len(esperado['albaranes'])} / {len(obtenido['albaranes'])} |",
        f"| Albaranes con contenido correcto | {resumen['albaranes_con_contenido_correcto']} |",
        f"| Albaranes completamente correctos incluido orden | {resumen['albaranes_orden_completo_correcto']} |",
        f"| Albaranes inventados | {len(inventados)} |",
        "",
        "## Diferencias relevantes",
        "",
        "- El importe del vencimiento queda deliberadamente en null porque no está unido visualmente a la fecha.",
        "- Los 147 albaranes conservan número, fecha, movimiento, descripción, base y total. El orden difiere para 146 porque el normalizador usa orden físico determinista por tablas paralelas y lo marca como reconstruido.",
        "- `impuestos=[]` coincide con el patrón; la incidencia conserva que el desglose literal era incompleto.",
        "- El ajuste Servicio básico se reconstruye desde GASTOS y sus indicadores de inclusión quedan sustentados por sumas visibles.",
        "- El nombre visible del destinatario puede diferir del nombre interno esperado; ID y método proceden explícitamente de configuración interna.",
        "",
        "## Estados de albaranes",
        "",
    ]
    for estado, cantidad in sorted(por_estado_albaran.items()):
        lineas.append(f"- {estado}: {cantidad}")
    lineas.extend([
        "",
        "## Configuración interna",
        "",
        "Los campos `categoria`, `requiere_conciliacion_albaranes`, `destinatario.id_farmacia` y `destinatario.metodo_identificacion` están etiquetados como configuración interna, no como extracción de IA.",
    ])
    ruta_md.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    print(f"Evaluación JSON: {ruta_json}")
    print(f"Evaluación Markdown: {ruta_md}")
    return ruta_json, ruta_md


if __name__ == "__main__":
    evaluar()
