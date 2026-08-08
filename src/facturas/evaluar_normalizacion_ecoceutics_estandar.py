"""Evaluacion independiente del caso Ecoceutics procesado por la ruta estandar."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
from typing import Any
import unicodedata


RAIZ = Path(__file__).resolve().parents[2]
RUTA_PATRON = (
    RAIZ
    / "pruebas/facturas/patron"
    / "pruebas_lectura_facturas_resultado_esperado_PATRON_OFICIAL_v1_0.json"
)
RUTA_BASE = (
    RAIZ
    / "pruebas/facturas/resultados/openai/muestra_completa/documento_02"
    / "comparacion_patron.json"
)
RUTA_NORMALIZADA = (
    RAIZ
    / "pruebas/facturas/resultados/openai/normalizacion_ecoceutics_estandar"
    / "factura_normalizada.json"
)
RUTA_SALIDA = RUTA_NORMALIZADA.parent
RUTAS_PRODUCCION = (
    RAIZ / "src/facturas/normalizadores/estandar.py",
    RAIZ / "src/facturas/normalizadores/documento.py",
    RAIZ / "src/facturas/normalizar_estandar.py",
    RAIZ / "src/facturas/configuraciones_estandar.py",
)


def cargar(ruta: Path) -> dict[str, Any]:
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encuentra el archivo requerido: {ruta}")
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


def atomos(valor: Any, prefijo: str = "") -> dict[str, Any]:
    if isinstance(valor, dict):
        resultado = {}
        for clave, dato in valor.items():
            if clave in {"procedencia", "orden_reconstruido", "pagina", "seccion"}:
                continue
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


def comparar(campo: str, esperado: Any, obtenido: Any) -> dict[str, Any]:
    esperados = atomos(esperado, campo)
    obtenidos = atomos(obtenido, campo)
    detalles = []
    conteo = Counter()
    for ruta in sorted(set(esperados) | set(obtenidos)):
        valor_esperado = esperados.get(ruta)
        valor_obtenido = obtenidos.get(ruta)
        if valor_esperado == valor_obtenido:
            estado = "CORRECTO"
        elif valor_obtenido is None or valor_obtenido == []:
            estado = "AUSENTE"
        elif valor_esperado is None or valor_esperado == []:
            estado = "INVENTADO"
        elif simplificar(valor_esperado) == simplificar(valor_obtenido):
            estado = "DIFERENCIA_FORMATO"
        else:
            estado = "INCORRECTO"
        conteo[estado] += 1
        detalles.append(
            {
                "ruta": ruta,
                "esperado": valor_esperado,
                "obtenido": valor_obtenido,
                "estado": estado,
            }
        )
    if set(conteo) == {"CORRECTO"}:
        estado_campo = "CORRECTO"
    elif conteo["INVENTADO"] and not (
        conteo["CORRECTO"] or conteo["INCORRECTO"]
    ):
        estado_campo = "INVENTADO"
    elif conteo["AUSENTE"] == sum(conteo.values()):
        estado_campo = "AUSENTE"
    elif conteo["CORRECTO"] or conteo["DIFERENCIA_FORMATO"]:
        estado_campo = "PARCIAL"
    else:
        estado_campo = "INCORRECTO"
    return {
        "campo": campo,
        "estado": estado_campo,
        "esperado": esperado,
        "obtenido": obtenido,
        "conteo_atomico": dict(conteo),
        "detalles": detalles,
    }


def verificar_aislamiento() -> dict[str, Any]:
    prohibidos = ("PATRON_OFICIAL", "facturas/patron", "cargar_patron", "evaluar_")
    hallazgos = []
    for ruta in RUTAS_PRODUCCION:
        texto = ruta.read_text(encoding="utf-8").replace("\\", "/").casefold()
        for prohibido in prohibidos:
            if prohibido.casefold() in texto:
                hallazgos.append({"archivo": str(ruta), "referencia": prohibido})
    return {"cumple": not hallazgos, "hallazgos": hallazgos}


def evaluar() -> tuple[Path, Path]:
    aislamiento = verificar_aislamiento()
    if not aislamiento["cumple"]:
        raise RuntimeError(
            f"Produccion contiene referencias prohibidas: {aislamiento['hallazgos']}"
        )
    documento = cargar(RUTA_NORMALIZADA)
    obtenido = documento["resultado_normalizado"]
    patron = cargar(RUTA_PATRON)
    documentos = [
        elemento
        for elemento in patron["documentos"]
        if elemento["archivo"] == documento["archivo_origen"]
    ]
    if len(documentos) != 1 or len(documentos[0]["facturas"]) != 1:
        raise RuntimeError("No se encontro exactamente un documento evaluable.")
    esperado = documentos[0]["facturas"][0]
    campos = sorted(set(esperado) | set(obtenido))
    comparaciones = [
        comparar(campo, esperado.get(campo), obtenido.get(campo)) for campo in campos
    ]
    conteo = Counter(comparacion["estado"] for comparacion in comparaciones)
    total = len(comparaciones)
    correctos = conteo["CORRECTO"]
    inventados = sum(
        comparacion["conteo_atomico"].get("INVENTADO", 0)
        for comparacion in comparaciones
    )
    resumen = {
        "campos_evaluados": total,
        "correctos": correctos,
        "incorrectos": conteo["INCORRECTO"],
        "parciales": conteo["PARCIAL"],
        "ausentes": conteo["AUSENTE"],
        "acierto_estricto": round(100 * correctos / total, 2),
        "cobertura": round(100 * (total - conteo["AUSENTE"]) / total, 2),
        "inventados": inventados,
    }
    base = cargar(RUTA_BASE)["resumen"]
    incidencias = cargar(RUTA_SALIDA / "incidencias.json")["incidencias"]
    salida = {
        "aislamiento": aislamiento,
        "antes_luna": base,
        "despues_estandar": resumen,
        "cantidad_incidencias": len(incidencias),
        "incidencias": incidencias,
        "validaciones_monetarias": documento["validaciones_monetarias"],
        "comparaciones": comparaciones,
    }
    RUTA_SALIDA.mkdir(parents=True, exist_ok=True)
    ruta_json = RUTA_SALIDA / "evaluacion_patron.json"
    ruta_md = RUTA_SALIDA / "evaluacion_patron.md"
    ruta_json.write_text(
        json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    diferencias = [
        comparacion
        for comparacion in comparaciones
        if comparacion["estado"] != "CORRECTO"
    ]
    lineas = [
        "# Evaluacion independiente de la ruta estandar",
        "",
        f"- Antes Luna: {base['correctos']}/{base['campos_evaluados']} correctos; "
        f"{base['acierto_estricto']:.2f} %; cobertura {base['cobertura']:.2f} %.",
        f"- Despues: {correctos}/{total} correctos.",
        f"- Acierto estricto: {resumen['acierto_estricto']:.2f} %.",
        f"- Cobertura: {resumen['cobertura']:.2f} %.",
        f"- Invenciones atomicas: {inventados}.",
        f"- Incidencias: {len(incidencias)}.",
        "",
        "## Diferencias",
        "",
    ]
    lineas.extend(
        f"- `{comparacion['campo']}`: {comparacion['estado']}"
        for comparacion in diferencias
    )
    ruta_md.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    print(f"Evaluacion JSON: {ruta_json}")
    print(f"Evaluacion Markdown: {ruta_md}")
    return ruta_json, ruta_md


if __name__ == "__main__":
    evaluar()
