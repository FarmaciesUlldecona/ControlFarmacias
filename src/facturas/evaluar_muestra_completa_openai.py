from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from pypdf import PdfReader


RAIZ = Path(__file__).resolve().parents[2]
PATRON = RAIZ / "pruebas/facturas/patron/pruebas_lectura_facturas_resultado_esperado_PATRON_OFICIAL_v1_0.json"
SALIDA = RAIZ / "pruebas/facturas/resultados/openai/muestra_completa"
DOCUMENTOS = RAIZ / "pruebas/facturas/documentos"
GOOGLE_ALLIANCE = RAIZ / "pruebas/facturas/resultados/google/invoice_parser/comparacion_alliance.json"
LUNA_ALLIANCE = RAIZ / "pruebas/facturas/resultados/openai/comparativa_modelos/repeticion_01/gpt-5.6-luna"

BLOQUES = {
    "cabecera": {"tipo_documento", "categoria", "requiere_conciliacion_albaranes", "pagina_inicio", "pagina_fin", "numero_factura", "fecha_factura"},
    "proveedor": {"proveedor_nombre", "proveedor_cif"},
    "destinatario": {"destinatario"},
    "totales": {"base_imponible_total", "iva_total", "recargo_equivalencia_total", "importe_total"},
    "fiscalidad": {"impuestos"},
    "vencimientos": {"vencimientos"},
    "albaranes": {"albaranes"},
    "ajustes": {"ajustes"},
    "campos_especiales": {"fecha_cargo", "periodo_facturacion_inicio", "periodo_facturacion_fin", "nota_revision"},
}


def cargar(ruta: Path) -> dict[str, Any]:
    return json.loads(ruta.read_text(encoding="utf-8"))


def simplificar(valor: Any) -> Any:
    if isinstance(valor, str):
        texto = "".join(c for c in unicodedata.normalize("NFD", valor) if unicodedata.category(c) != "Mn")
        return re.sub(r"\s+", " ", texto).strip().casefold()
    return valor


def plano_extraido(valor: Any) -> Any:
    if isinstance(valor, dict):
        if set(valor).issuperset({"valor", "evidencias"}):
            return valor.get("valor")
        return {k: plano_extraido(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [plano_extraido(v) for v in valor]
    return valor


def atomos(valor: Any, prefijo: str = "") -> dict[str, Any]:
    if isinstance(valor, dict):
        resultado = {}
        for clave, dato in valor.items():
            ruta = f"{prefijo}.{clave}" if prefijo else clave
            resultado.update(atomos(dato, ruta))
        return resultado
    if isinstance(valor, list):
        if not valor:
            return {prefijo: []}
        resultado = {}
        for indice, dato in enumerate(valor):
            resultado.update(atomos(dato, f"{prefijo}[{indice}]"))
        return resultado
    return {prefijo: valor}


def estado_atomico(esperado: Any, obtenido: Any) -> str:
    if esperado == obtenido:
        return "CORRECTO"
    if obtenido is None or obtenido == []:
        return "AUSENTE"
    if esperado is None or esperado == []:
        return "INVENTADO"
    if simplificar(esperado) == simplificar(obtenido):
        return "DIFERENCIA_FORMATO"
    return "INCORRECTO"


def comparar_campo(nombre: str, esperado: Any, obtenido: Any) -> dict[str, Any]:
    e = atomos(esperado, nombre)
    o = atomos(obtenido, nombre)
    rutas = sorted(set(e) | set(o))
    detalles = []
    conteo = Counter()
    for ruta in rutas:
        estado = estado_atomico(e.get(ruta), o.get(ruta))
        conteo[estado] += 1
        detalles.append({"ruta": ruta, "esperado": e.get(ruta), "obtenido": o.get(ruta), "clasificacion": estado})
    if conteo and set(conteo) == {"CORRECTO"}:
        clasificacion = "CORRECTO"
    elif conteo["INVENTADO"] and not (conteo["CORRECTO"] or conteo["INCORRECTO"]):
        clasificacion = "INVENTADO"
    elif conteo["AUSENTE"] == sum(conteo.values()):
        clasificacion = "AUSENTE"
    elif conteo["CORRECTO"] or conteo["DIFERENCIA_FORMATO"]:
        clasificacion = "PARCIAL"
    else:
        clasificacion = "INCORRECTO"
    return {
        "campo": nombre, "valor_esperado": esperado, "valor_extraido": obtenido,
        "clasificacion": clasificacion, "conteo_atomico": dict(conteo), "detalles": detalles,
    }


def bloque_de(campo: str) -> str:
    return next(nombre for nombre, campos in BLOQUES.items() if campo in campos)


def verificar_evidencias(factura_bruta: dict[str, Any], ruta_pdf: Path) -> dict[str, int]:
    texto_pdf = "\n".join(p.extract_text() or "" for p in PdfReader(ruta_pdf).pages)
    texto_pdf = simplificar(texto_pdf)
    resultado = Counter()

    def recorrer(valor: Any) -> None:
        if isinstance(valor, dict):
            evidencias = valor.get("evidencias")
            if isinstance(evidencias, list):
                for evidencia in evidencias:
                    texto = evidencia.get("texto_visible", "")
                    if texto and simplificar(texto) in texto_pdf:
                        resultado["verificadas_en_texto_pdf"] += 1
                    else:
                        resultado["no_verificables_por_capa_textual"] += 1
            for dato in valor.values():
                recorrer(dato)
        elif isinstance(valor, list):
            for dato in valor:
                recorrer(dato)
    recorrer(factura_bruta)
    return dict(resultado)


def evaluar_documento(indice: int, documento_patron: dict[str, Any]) -> dict[str, Any]:
    carpeta = SALIDA / f"documento_{indice:02d}"
    extraccion = cargar(carpeta / "estructurado.json")
    metricas = cargar(carpeta / "metricas.json")
    metadatos = cargar(carpeta / "metadatos_entrada.json")
    bruta = extraccion["factura"]
    obtenida = plano_extraido(bruta)
    esperada = documento_patron["facturas"][0]
    campos = sorted(set(esperada) | set(obtenida))
    comparaciones = [comparar_campo(campo, esperada.get(campo), obtenida.get(campo)) for campo in campos]
    por_estado = Counter(x["clasificacion"] for x in comparaciones)
    por_bloque: dict[str, Counter] = defaultdict(Counter)
    atomicos = Counter()
    for comparacion in comparaciones:
        por_bloque[bloque_de(comparacion["campo"])][comparacion["clasificacion"]] += 1
        atomicos.update(comparacion["conteo_atomico"])
    total = len(comparaciones)
    cobertura = total - por_estado["AUSENTE"]
    requiere_tablas = bool(esperada.get("albaranes")) and next(x for x in comparaciones if x["campo"] == "albaranes")["clasificacion"] != "CORRECTO"
    resumen = {
        "campos_evaluados": total,
        "correctos": por_estado["CORRECTO"], "incorrectos": por_estado["INCORRECTO"],
        "ausentes": por_estado["AUSENTE"], "parciales": por_estado["PARCIAL"],
        "inventados": por_estado["INVENTADO"],
        "acierto_estricto": round(100 * por_estado["CORRECTO"] / total, 2),
        "cobertura": round(100 * cobertura / total, 2),
        "coste_real_usd": metricas["coste_total"], "duracion_segundos": metricas["duracion_segundos"],
        "requiere_extraccion_literal_tablas": requiere_tablas,
    }
    resultado = {
        "indice": indice, "archivo_original": metadatos["archivo_original_local"],
        "numero_factura_esperado": esperada["numero_factura"], "tipo_esperado": esperada["tipo_documento"],
        "proveedor_esperado": esperada["proveedor_nombre"], "paginas": metadatos["numero_paginas"],
        "resumen": resumen, "resultados_por_bloque": {k: dict(v) for k, v in por_bloque.items()},
        "conteo_atomico": dict(atomicos), "verificacion_evidencias": verificar_evidencias(bruta, DOCUMENTOS / metadatos["archivo_original_local"]),
        "comparaciones": comparaciones,
        "criterios": {
            "diferencia_formato": "Equivalencia tras ignorar mayúsculas, tildes y espacios.",
            "campo_negocio_python": ["categoria", "requiere_conciliacion_albaranes", "destinatario.id_farmacia", "destinatario.metodo_identificacion"],
            "datos_no_visibles": "Los null sin evidencia se contabilizan como ausentes, no inventados.",
        },
    }
    (carpeta / "comparacion_patron.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    diferencias = [x for x in comparaciones if x["clasificacion"] != "CORRECTO"]
    lineas = [
        f"# Evaluación ciega: documento_{indice:02d}", "",
        f"- Archivo local: `{metadatos['archivo_original_local']}`",
        f"- Factura o abono esperado: `{esperada['numero_factura']}`",
        f"- Proveedor esperado: {esperada['proveedor_nombre']}",
        f"- Coste: {metricas['coste_total']:.6f} USD",
        f"- Duración: {metricas['duracion_segundos']:.3f} s", "", "## Métricas", "",
        f"- Campos evaluados: {total}", f"- Correctos: {por_estado['CORRECTO']}",
        f"- Incorrectos: {por_estado['INCORRECTO']}", f"- Ausentes: {por_estado['AUSENTE']}",
        f"- Parciales: {por_estado['PARCIAL']}", f"- Inventados: {por_estado['INVENTADO']}",
        f"- Acierto estricto: {resumen['acierto_estricto']:.2f} %", f"- Cobertura: {resumen['cobertura']:.2f} %", "",
        "## Diferencias", "",
    ]
    lineas.extend(f"- `{x['campo']}`: **{x['clasificacion']}**" for x in diferencias)
    lineas.extend(["", "## Diagnóstico", "", f"- Extracción literal de tablas recomendada: {'sí' if requiere_tablas else 'no'}.", "- Los campos de categoría, conciliación e identificación interna deben resolverse en Python."])
    (carpeta / "analisis_patron.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return resultado


def evaluar() -> None:
    patron = cargar(PATRON)
    por_archivo = {d["archivo"]: d for d in patron["documentos"]}
    resultados = []
    for indice in range(1, 8):
        meta = cargar(SALIDA / f"documento_{indice:02d}/metadatos_entrada.json")
        resultados.append(evaluar_documento(indice, por_archivo[meta["archivo_original_local"]]))

    campos = Counter()
    proveedores: dict[str, Counter] = defaultdict(Counter)
    tipos: dict[str, Counter] = defaultdict(Counter)
    totales = Counter()
    for resultado in resultados:
        resumen = resultado["resumen"]
        for clave in ("campos_evaluados", "correctos", "incorrectos", "ausentes", "parciales", "inventados"):
            totales[clave] += resumen[clave]
        proveedor = resultado["proveedor_esperado"]
        tipo = resultado["tipo_esperado"]
        proveedores[proveedor].update({k: resumen[k] for k in ("campos_evaluados", "correctos", "incorrectos", "ausentes", "parciales", "inventados")})
        tipos[tipo].update({k: resumen[k] for k in ("campos_evaluados", "correctos", "incorrectos", "ausentes", "parciales", "inventados")})
        for comparacion in resultado["comparaciones"]:
            campos[f"{comparacion['campo']}::{comparacion['clasificacion']}"] += 1

    coste = sum(r["resumen"]["coste_real_usd"] for r in resultados)
    paginas = sum(r["paginas"] for r in resultados)
    metricas = [cargar(SALIDA / f"documento_{i:02d}/metricas.json") for i in range(1, 8)]
    tokens = {clave: sum(m[clave] for m in metricas) for clave in ("tokens_entrada", "tokens_entrada_cacheados", "tokens_salida", "tokens_razonamiento")}
    google = cargar(GOOGLE_ALLIANCE)
    alliance_luna = cargar(LUNA_ALLIANCE / "metricas.json")
    resumen_global = {
        "alcance": {
            "documentos_totales_integrados": 11,
            "nuevos_documentos_luna_homogeneos": 7,
            "alliance_previos": 4,
            "advertencia_metodologica": "Los cuatro Alliance previos se integran como antecedente Google; solo 08008427 dispone además de Luna general. No se mezclan sus campos en las tasas Luna de los siete nuevos.",
        },
        "siete_nuevos_luna": {
            **dict(totales),
            "acierto_estricto": round(100 * totales["correctos"] / totales["campos_evaluados"], 2),
            "cobertura": round(100 * (totales["campos_evaluados"] - totales["ausentes"]) / totales["campos_evaluados"], 2),
            "coste_total_usd": round(coste, 6), "coste_medio_usd": round(coste / 7, 6),
            "paginas_totales": paginas, **tokens,
            "documentos_requieren_tablas": sum(r["resumen"]["requiere_extraccion_literal_tablas"] for r in resultados),
            "porcentaje_requieren_tablas": round(100 * sum(r["resumen"]["requiere_extraccion_literal_tablas"] for r in resultados) / 7, 2),
            "porcentaje_resoluble_solo_extraccion_general": round(100 * sum(not r["resumen"]["requiere_extraccion_literal_tablas"] for r in resultados) / 7, 2),
        },
        "alliance_previo_google": google["resumen"],
        "alliance_08008427_luna_coste_usd": alliance_luna["coste_total_estimado"],
        "coste_openai_conocido_total_usd": round(coste + alliance_luna["coste_total_estimado"], 6),
        "paginas_totales_11_documentos": paginas + 11,
        "tokens_openai_conocidos": {
            "documentos_con_usage": 8,
            "tokens_entrada": tokens["tokens_entrada"] + alliance_luna["tokens_entrada"],
            "tokens_entrada_cacheados": tokens["tokens_entrada_cacheados"] + alliance_luna["tokens_entrada_cacheados"],
            "tokens_salida": tokens["tokens_salida"] + alliance_luna["tokens_salida"],
            "tokens_razonamiento": tokens["tokens_razonamiento"] + alliance_luna["tokens_razonamiento"],
            "nota": "No se atribuyen tokens OpenAI a los tres Alliance que solo tienen evaluación previa de Google.",
        },
        "resultados_por_documento": [{k: r[k] for k in ("indice", "archivo_original", "numero_factura_esperado", "tipo_esperado", "proveedor_esperado", "paginas", "resumen")} for r in resultados],
        "resultados_por_proveedor": {k: dict(v) for k, v in proveedores.items()},
        "resultados_por_tipo": {k: dict(v) for k, v in tipos.items()},
        "resultados_por_campo": dict(campos),
        "reglas_comunes_candidatas": ["fechas visibles a ISO", "importes españoles", "páginas técnicas", "campos internos de farmacia y categoría"],
        "reglas_especificas_candidatas": ["vencimientos por proveedor", "tablas de albaranes", "signos de abonos", "recargo de equivalencia", "ajustes y cuotas de servicio"],
    }
    (SALIDA / "resumen_global_11_facturas.json").write_text(json.dumps(resumen_global, ensure_ascii=False, indent=2), encoding="utf-8")
    lineas = ["# Resumen global de 11 facturas o abonos", "", "## Alcance", "", resumen_global["alcance"]["advertencia_metodologica"], "", "## Siete extracciones Luna nuevas", ""]
    for clave, valor in resumen_global["siete_nuevos_luna"].items():
        lineas.append(f"- {clave}: {valor}")
    lineas.extend(["", "## Resultados por documento", "", "| Documento | Proveedor | Tipo | Acierto | Cobertura | Coste USD | Tablas |", "|---|---|---|---:|---:|---:|---|"])
    for r in resultados:
        s = r["resumen"]
        lineas.append(f"| {r['numero_factura_esperado']} | {r['proveedor_esperado']} | {r['tipo_esperado']} | {s['acierto_estricto']:.2f}% | {s['cobertura']:.2f}% | {s['coste_real_usd']:.6f} | {'sí' if s['requiere_extraccion_literal_tablas'] else 'no'} |")
    lineas.extend(["", "## Alliance previo", "", f"- Google: {google['resumen']['correctos']} correctos de {google['resumen']['total_campos_evaluados']}; acierto {google['resumen']['porcentaje_acierto']:.2f}%; cobertura {google['resumen']['porcentaje_cobertura']:.2f}%.", f"- Coste OpenAI conocido para Alliance 08008427: {alliance_luna['coste_total_estimado']:.6f} USD.", "", "## Candidatos de normalización", "", "### Comunes", ""])
    lineas.extend(f"- {x}" for x in resumen_global["reglas_comunes_candidatas"])
    lineas.extend(["", "### Específicos por proveedor", ""])
    lineas.extend(f"- {x}" for x in resumen_global["reglas_especificas_candidatas"])
    (SALIDA / "resumen_global_11_facturas.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(json.dumps(resumen_global["siete_nuevos_luna"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    evaluar()
