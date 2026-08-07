from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
import json
import re
from pathlib import Path
from typing import Any
import unicodedata

from src.facturas.motores.openai.benchmark_luna_terra_sol import CASOS, MODELOS_BENCHMARK, SALIDA


RAIZ = Path(__file__).resolve().parents[2]
PATRON = RAIZ / "pruebas/facturas/patron/pruebas_lectura_facturas_resultado_esperado_PATRON_OFICIAL_v1_0.json"
SALIDA_EVALUACION = SALIDA / "evaluacion"
CAMPOS = (
    "tipo_documento", "categoria", "requiere_conciliacion_albaranes",
    "pagina_inicio", "pagina_fin", "proveedor_nombre", "proveedor_cif",
    "numero_factura", "fecha_factura", "base_imponible_total", "iva_total",
    "recargo_equivalencia_total", "importe_total", "vencimientos", "impuestos",
    "albaranes", "ajustes", "destinatario", "fecha_cargo",
    "periodo_facturacion_inicio", "periodo_facturacion_fin", "nota_revision",
)


def cargar(ruta: Path) -> dict[str, Any]:
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encuentra el archivo: {ruta}")
    return json.loads(ruta.read_text(encoding="utf-8"))


def simplificar(valor: Any) -> Any:
    if not isinstance(valor, str):
        return valor
    sin_tildes = "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", valor)
        if unicodedata.category(caracter) != "Mn"
    )
    return re.sub(r"\s+", " ", sin_tildes).strip().casefold()


def plano(valor: Any) -> Any:
    if isinstance(valor, dict):
        if set(valor).issuperset({"valor", "evidencias"}):
            return valor.get("valor")
        return {clave: plano(dato) for clave, dato in valor.items()}
    if isinstance(valor, list):
        return [plano(dato) for dato in valor]
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


def comparar_campo(campo: str, esperado: Any, obtenido: Any) -> dict[str, Any]:
    esperados = atomos(esperado, campo)
    obtenidos = atomos(obtenido, campo)
    conteo = Counter()
    detalles = []
    for ruta in sorted(set(esperados) | set(obtenidos)):
        estado = estado_atomico(esperados.get(ruta), obtenidos.get(ruta))
        conteo[estado] += 1
        detalles.append(
            {
                "ruta": ruta,
                "esperado": esperados.get(ruta),
                "obtenido": obtenidos.get(ruta),
                "estado": estado,
            }
        )
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
        "campo": campo,
        "clasificacion": clasificacion,
        "conteo_atomico": dict(conteo),
        "detalles": detalles,
    }


def localizar_esperado(patron: dict[str, Any], caso: Any) -> dict[str, Any]:
    if caso.clave == "alliance_08008427":
        encontradas = []

        def recorrer(valor: Any) -> None:
            if isinstance(valor, dict):
                if valor.get("numero_factura") == "08008427":
                    encontradas.append(valor)
                for dato in valor.values():
                    recorrer(dato)
            elif isinstance(valor, list):
                for dato in valor:
                    recorrer(dato)

        recorrer(patron)
        if len(encontradas) != 1:
            raise RuntimeError(f"Se encontraron {len(encontradas)} facturas Alliance 08008427.")
        return encontradas[0]
    documentos = [x for x in patron["documentos"] if x["archivo"] == caso.archivo]
    if len(documentos) != 1 or len(documentos[0]["facturas"]) != 1:
        raise RuntimeError(f"No existe un unico resultado esperado para {caso.clave}.")
    return documentos[0]["facturas"][0]


def _metricas_albaranes(esperados: list[dict[str, Any]], obtenidos: list[dict[str, Any]]) -> dict[str, int]:
    numeros_obtenidos = [x.get("numero_albaran") for x in obtenidos if x.get("numero_albaran")]
    conteo_obtenidos = Counter(numeros_obtenidos)
    por_numero = {x.get("numero_albaran"): x for x in obtenidos if x.get("numero_albaran")}
    numeros_esperados = {x.get("numero_albaran") for x in esperados if x.get("numero_albaran")}
    coincidentes = numeros_esperados & set(por_numero)
    campos_importe = ("importe_base", "importe_total")
    return {
        "esperados": len(esperados),
        "extraidos": len(obtenidos),
        "numeros_correctos": len(coincidentes),
        "ausentes": len(numeros_esperados - set(por_numero)),
        "duplicados": sum(cantidad - 1 for cantidad in conteo_obtenidos.values() if cantidad > 1),
        "inventados": len(set(por_numero) - numeros_esperados),
        "fechas_correctas": sum(
            por_numero[e["numero_albaran"]].get("fecha_albaran") == e.get("fecha_albaran")
            for e in esperados if e.get("numero_albaran") in coincidentes
        ),
        "importes_correctos": sum(
            por_numero[e["numero_albaran"]].get(campo) == e.get(campo)
            for e in esperados if e.get("numero_albaran") in coincidentes
            for campo in campos_importe if e.get(campo) is not None
        ),
        "ordenes_correctos": sum(
            por_numero[e["numero_albaran"]].get("orden") == e.get("orden")
            for e in esperados if e.get("numero_albaran") in coincidentes
        ),
    }


def evaluar_general(patron: dict[str, Any]) -> list[dict[str, Any]]:
    resultados = []
    for caso in CASOS:
        esperado = localizar_esperado(patron, caso)
        for modelo in MODELOS_BENCHMARK:
            directorio = SALIDA / "general" / f"caso_{caso.indice:02d}" / modelo
            estructura = cargar(directorio / "estructurado.json")
            metricas = cargar(directorio / "metricas.json")
            factura_bruta = estructura.get("factura")
            if factura_bruta is None:
                resultado = {
                    "caso": caso.clave,
                    "modelo": modelo,
                    "estado_llamada": "failed",
                    "resumen": None,
                    "albaranes": None,
                    "metricas": metricas,
                    "comparaciones": [],
                }
            else:
                obtenido = plano(factura_bruta)
                comparaciones = [
                    comparar_campo(campo, esperado.get(campo), obtenido.get(campo))
                    for campo in CAMPOS
                ]
                conteo = Counter(x["clasificacion"] for x in comparaciones)
                total = len(comparaciones)
                inventados = sum(
                    x["conteo_atomico"].get("INVENTADO", 0) for x in comparaciones
                )
                resumen = {
                    "campos_evaluados": total,
                    "correctos": conteo["CORRECTO"],
                    "incorrectos": conteo["INCORRECTO"],
                    "parciales": conteo["PARCIAL"],
                    "ausentes": conteo["AUSENTE"],
                    "inventados": inventados,
                    "acierto_estricto": round(100 * conteo["CORRECTO"] / total, 2),
                    "cobertura": round(100 * (total - conteo["AUSENTE"]) / total, 2),
                    "incidencias_previsibles": sum(
                        x["clasificacion"] != "CORRECTO" for x in comparaciones
                    ),
                }
                resultado = {
                    "caso": caso.clave,
                    "modelo": modelo,
                    "estado_llamada": metricas.get("estado"),
                    "resumen": resumen,
                    "albaranes": _metricas_albaranes(
                        esperado.get("albaranes", []), obtenido.get("albaranes", [])
                    ),
                    "metricas": metricas,
                    "comparaciones": comparaciones,
                }
            salida = SALIDA_EVALUACION / "general" / f"caso_{caso.indice:02d}"
            salida.mkdir(parents=True, exist_ok=True)
            (salida / f"{modelo}.json").write_text(
                json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            resultados.append(resultado)
    return resultados


def _decimal_es(texto: Any) -> Decimal | None:
    if not isinstance(texto, str) or not texto.strip():
        return None
    valor = texto.strip().replace("€", "").replace(" ", "")
    negativo = valor.startswith("-") or valor.endswith("-")
    valor = valor.strip("-").replace(".", "").replace(",", ".")
    try:
        numero = Decimal(valor)
    except InvalidOperation:
        return None
    return -numero if negativo else numero


def _fecha_es(texto: str) -> str | None:
    coincidencia = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", texto.strip())
    return f"{coincidencia[3]}-{coincidencia[2]}-{coincidencia[1]}" if coincidencia else None


def _filas_literales(transcripcion: dict[str, Any]) -> list[dict[str, Any]]:
    filas = []
    for orden_tabla, tabla in enumerate(transcripcion.get("tablas", []), start=1):
        titulo = str(tabla.get("titulo_visible") or "").strip().upper()
        if titulo not in {"CARGOS", "ABONOS"}:
            continue
        for fila in tabla.get("filas", []):
            celdas = list(fila.get("celdas", []))
            if len(celdas) != 5:
                continue
            filas.append(
                {
                    "pagina": tabla.get("pagina"),
                    "orden_tabla": orden_tabla,
                    "orden_visual": fila.get("orden_visual"),
                    "titulo": titulo,
                    "fecha": celdas[0],
                    "descripcion": celdas[1],
                    "numero": celdas[2],
                    "base": celdas[3],
                    "total": celdas[4],
                }
            )
    return filas


def evaluar_tablas(patron: dict[str, Any]) -> list[dict[str, Any]]:
    esperado_factura = localizar_esperado(patron, CASOS[0])
    esperados_negocio = {
        fila["numero_albaran"]: fila for fila in esperado_factura.get("albaranes", [])
    }
    luna = cargar(SALIDA / "alliance_tablas/gpt-5.6-luna/estructurado.json")
    referencia = _filas_literales(luna["transcripcion"])
    referencia_por_numero = {fila["numero"]: fila for fila in referencia}
    resultados = []
    for modelo in MODELOS_BENCHMARK:
        directorio = SALIDA / "alliance_tablas" / modelo
        estructura = cargar(directorio / "estructurado.json")
        metricas = cargar(directorio / "metricas.json")
        transcripcion = estructura.get("transcripcion")
        if transcripcion is None:
            resultado = {
                "modelo": modelo,
                "estado_llamada": "failed",
                "resumen": None,
                "metricas": metricas,
            }
        else:
            filas = _filas_literales(transcripcion)
            numeros = [fila["numero"] for fila in filas]
            conteo = Counter(numeros)
            por_numero = {fila["numero"]: fila for fila in filas}
            comunes = set(referencia_por_numero) & set(por_numero)
            signos_correctos = sum(
                (_decimal_es(por_numero[numero][campo]) or Decimal("0")).is_signed()
                == (_decimal_es(referencia_por_numero[numero][campo]) or Decimal("0")).is_signed()
                for numero in comunes for campo in ("base", "total")
            )
            resumen = {
                "filas_esperadas": len(referencia),
                "filas_obtenidas": len(filas),
                "numeros_correctos": len(comunes),
                "fechas_correctas": sum(
                    _fecha_es(por_numero[numero]["fecha"])
                    == esperados_negocio.get(numero, {}).get("fecha_albaran")
                    for numero in comunes
                ),
                "descripciones_correctas": sum(
                    por_numero[numero]["descripcion"]
                    == referencia_por_numero[numero]["descripcion"]
                    for numero in comunes
                ),
                "bases_correctas": sum(
                    _decimal_es(por_numero[numero]["base"])
                    == Decimal(str(esperados_negocio.get(numero, {}).get("importe_base")))
                    for numero in comunes
                    if esperados_negocio.get(numero, {}).get("importe_base") is not None
                ),
                "totales_correctos": sum(
                    _decimal_es(por_numero[numero]["total"])
                    == Decimal(str(esperados_negocio.get(numero, {}).get("importe_total")))
                    for numero in comunes
                    if esperados_negocio.get(numero, {}).get("importe_total") is not None
                ),
                "signos_correctos": signos_correctos,
                "paginas_correctas": sum(
                    por_numero[numero]["pagina"] == referencia_por_numero[numero]["pagina"]
                    for numero in comunes
                ),
                "posiciones_correctas": sum(
                    (
                        por_numero[numero]["pagina"],
                        por_numero[numero]["titulo"],
                        por_numero[numero]["orden_visual"],
                    )
                    == (
                        referencia_por_numero[numero]["pagina"],
                        referencia_por_numero[numero]["titulo"],
                        referencia_por_numero[numero]["orden_visual"],
                    )
                    for numero in comunes
                ),
                "duplicados": sum(cantidad - 1 for cantidad in conteo.values() if cantidad > 1),
                "ausentes": len(set(referencia_por_numero) - set(por_numero)),
                "inventados": len(set(por_numero) - set(referencia_por_numero)),
            }
            resultado = {
                "modelo": modelo,
                "estado_llamada": metricas.get("estado", metricas.get("estado_final")),
                "resumen": resumen,
                "metricas": metricas,
            }
        SALIDA_EVALUACION.mkdir(parents=True, exist_ok=True)
        (SALIDA_EVALUACION / f"tablas_{modelo}.json").write_text(
            json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        resultados.append(resultado)
    return resultados


def _coste(metricas: dict[str, Any]) -> float:
    valor = metricas.get("coste_total_usd")
    if valor is None:
        valor = metricas.get("coste_total_estimado_usd")
    if valor is None:
        valor = metricas.get("coste_total_estimado")
    if valor is None:
        valor = metricas.get("coste_total")
    return float(valor) if valor is not None else 0.0


def _coste_disponible(metricas: dict[str, Any]) -> bool:
    return any(
        metricas.get(clave) is not None
        for clave in (
            "coste_total_usd",
            "coste_total_estimado_usd",
            "coste_total_estimado",
            "coste_total",
        )
    )


def resumir(generales: list[dict[str, Any]], tablas: list[dict[str, Any]]) -> dict[str, Any]:
    por_modelo = {}
    proyecciones = {}
    for modelo in MODELOS_BENCHMARK:
        todos = [x for x in generales if x["modelo"] == modelo]
        resultados = [x for x in todos if x["resumen"]]
        fallidos = len(todos) - len(resultados)
        total_campos = len(todos) * len(CAMPOS)
        correctos = sum(x["resumen"]["correctos"] for x in resultados)
        ausentes = sum(x["resumen"]["ausentes"] for x in resultados) + fallidos * len(CAMPOS)
        coste_general = sum(_coste(x["metricas"]) for x in todos)
        literal = next(x for x in tablas if x["modelo"] == modelo)
        coste_literal = _coste(literal["metricas"])
        media_general = coste_general / len(resultados) if resultados else 0.0
        por_modelo[modelo] = {
            "llamadas_generales_correctas": len(resultados),
            "llamadas_generales_fallidas": fallidos,
            "campos_evaluados": total_campos,
            "correctos": correctos,
            "acierto_estricto": round(100 * correctos / total_campos, 2) if total_campos else 0.0,
            "cobertura": round(100 * (total_campos - ausentes) / total_campos, 2) if total_campos else 0.0,
            "invenciones": sum(x["resumen"]["inventados"] for x in resultados),
            "incidencias_previsibles": sum(x["resumen"]["incidencias_previsibles"] for x in resultados),
            "coste_general_usd": round(coste_general, 6),
            "coste_literal_usd": round(coste_literal, 6),
            "coste_muestra_usd": round(coste_general + coste_literal, 6),
            "coste_medio_factura_general_usd": round(media_general, 6),
            "costes_no_disponibles": sum(
                not _coste_disponible(x["metricas"]) for x in todos
            ),
        }
        escenarios = {}
        for porcentaje in (0.2, 0.4, 0.6):
            mensual = media_general * 60 + coste_literal * 60 * porcentaje
            escenarios[f"literal_{int(porcentaje * 100)}"] = {
                "mensual_60_facturas_usd": round(mensual, 2),
                "anual_usd": round(mensual * 12, 2),
            }
        proyecciones[modelo] = escenarios
    return {"por_modelo": por_modelo, "proyecciones": proyecciones}


def escribir_resumen(
    generales: list[dict[str, Any]], tablas: list[dict[str, Any]], agregado: dict[str, Any]
) -> None:
    resumen = {
        "metodologia": {
            "modelos": list(MODELOS_BENCHMARK),
            "documentos": [caso.clave for caso in CASOS],
            "resultados_generales": 15,
            "resultados_tablas": 3,
            "llamadas_nuevas": 17,
            "resultados_reutilizados": 1,
            "normalizadores_aplicados": False,
            "patron_aislado_de_extractores": True,
        },
        **agregado,
        "resultados_generales": [
            {clave: valor for clave, valor in resultado.items() if clave != "comparaciones"}
            for resultado in generales
        ],
        "resultados_tablas": tablas,
    }
    SALIDA_EVALUACION.mkdir(parents=True, exist_ok=True)
    (SALIDA_EVALUACION / "resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lineas = [
        "# Benchmark controlado Luna / Terra / Sol",
        "",
        "## Metodología",
        "",
        "- 5 documentos y 3 modelos: 15 resultados de extracción general.",
        "- Alliance añade 3 resultados de extracción literal de tablas.",
        "- 17 llamadas nuevas y 1 artefacto Luna literal estrictamente comparable reutilizado.",
        "- Sin normalizadores específicos y con el patrón aislado de los extractores.",
        "- Una llamada Terra de Alliance general falló y se conserva como fallo, sin reintento.",
        "",
        "## Resultado agregado general",
        "",
        "| Modelo | Llamadas OK/error | Correctos | Acierto | Cobertura | Invenciones | Incidencias | Coste conocido muestra |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for modelo, datos in agregado["por_modelo"].items():
        lineas.append(
            f"| {modelo} | {datos['llamadas_generales_correctas']}/{datos['llamadas_generales_fallidas']} | "
            f"{datos['correctos']}/{datos['campos_evaluados']} | "
            f"{datos['acierto_estricto']:.2f}% | {datos['cobertura']:.2f}% | "
            f"{datos['invenciones']} | {datos['incidencias_previsibles']} | "
            f"{datos['coste_muestra_usd']:.6f} USD |"
        )
    lineas.extend(["", "## Resultados por documento", "", "| Caso | Modelo | Acierto | Cobertura | Invenciones | Coste |", "|---|---|---:|---:|---:|---:|"])
    for resultado in generales:
        if resultado["resumen"]:
            datos = resultado["resumen"]
            lineas.append(
                f"| {resultado['caso']} | {resultado['modelo']} | {datos['acierto_estricto']:.2f}% | "
                f"{datos['cobertura']:.2f}% | {datos['inventados']} | {_coste(resultado['metricas']):.6f} USD |"
            )
        else:
            lineas.append(f"| {resultado['caso']} | {resultado['modelo']} | ERROR | ERROR | - | N/D |")
    lineas.extend(["", "## Alliance tablas literales", ""])
    for resultado in tablas:
        lineas.append(f"### {resultado['modelo']}")
        lineas.append("")
        lineas.append(json.dumps(resultado["resumen"], ensure_ascii=False) if resultado["resumen"] else "Llamada fallida.")
        lineas.append("")
    lineas.extend([
        "## Costes y proyecciones",
        "",
        "El coste medio general se calcula sobre llamadas completadas. Cada escenario suma una segunda llamada literal al 20 %, 40 % o 60 % de 60 facturas mensuales. El coste de la llamada Terra fallida no está disponible; su total de muestra es un mínimo conocido.",
        "",
        "| Modelo | Media general | Literal Alliance | 20 % mes/año | 40 % mes/año | 60 % mes/año |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for modelo, datos in agregado["por_modelo"].items():
        escenarios = agregado["proyecciones"][modelo]
        c20 = escenarios["literal_20"]
        c40 = escenarios["literal_40"]
        c60 = escenarios["literal_60"]
        lineas.append(
            f"| {modelo} | {datos['coste_medio_factura_general_usd']:.6f} USD | "
            f"{datos['coste_literal_usd']:.6f} USD | "
            f"{c20['mensual_60_facturas_usd']:.2f}/{c20['anual_usd']:.2f} USD | "
            f"{c40['mensual_60_facturas_usd']:.2f}/{c40['anual_usd']:.2f} USD | "
            f"{c60['mensual_60_facturas_usd']:.2f}/{c60['anual_usd']:.2f} USD |"
        )
    (SALIDA_EVALUACION / "resumen.md").write_text("\n".join(lineas), encoding="utf-8")
    print(json.dumps(agregado, ensure_ascii=False, indent=2))


def evaluar() -> None:
    patron = cargar(PATRON)
    generales = evaluar_general(patron)
    tablas = evaluar_tablas(patron)
    agregado = resumir(generales, tablas)
    escribir_resumen(generales, tablas, agregado)


if __name__ == "__main__":
    evaluar()
