from __future__ import annotations

import json
from pathlib import Path

from src.facturas.motores.simulado import MotorSimulado


RUTA_PROYECTO = Path(__file__).resolve().parents[1]

RUTA_DOCUMENTOS_PRUEBA = (
    RUTA_PROYECTO
    / "pruebas"
    / "facturas"
    / "documentos"
)


def buscar_primer_pdf() -> Path:
    """
    Localiza el primer PDF disponible en la carpeta
    de documentos de prueba.
    """
    if not RUTA_DOCUMENTOS_PRUEBA.exists():
        raise FileNotFoundError(
            f"No existe la carpeta de documentos: "
            f"{RUTA_DOCUMENTOS_PRUEBA}"
        )

    archivos_pdf = sorted(
        ruta
        for ruta in RUTA_DOCUMENTOS_PRUEBA.rglob("*.pdf")
        if ruta.is_file()
    )

    if not archivos_pdf:
        raise FileNotFoundError(
            f"No se han encontrado archivos PDF en: "
            f"{RUTA_DOCUMENTOS_PRUEBA}"
        )

    return archivos_pdf[0]


def mostrar_resultado(
    titulo: str,
    resultado,
) -> None:
    print()
    print(titulo)
    print("-" * len(titulo))
    print(f"Archivo: {resultado.archivo}")
    print(
        f"Procesado correctamente: "
        f"{resultado.procesado_correctamente}"
    )
    print(
        f"Motor: {resultado.motor.proveedor} / "
        f"{resultado.motor.nombre_modelo}"
    )
    print(
        f"Tiempo: "
        f"{resultado.metricas.tiempo_segundos:.4f} segundos"
    )
    print(
        f"Coste estimado: "
        f"{resultado.metricas.coste_estimado_eur}"
    )
    print(
        f"Confianza global: "
        f"{resultado.metricas.confianza_global}"
    )

    if resultado.documento_normalizado is not None:
        print(
            f"Facturas detectadas: "
            f"{len(resultado.documento_normalizado.facturas)}"
        )

    if resultado.errores:
        print("Errores:")

        for error in resultado.errores:
            print(
                f"- {error.codigo}: {error.mensaje}"
            )

            if error.detalle:
                print(f"  Detalle: {error.detalle}")


def guardar_resultado_json(
    resultado,
) -> Path:
    """
    Guarda el resultado simulado para comprobar que
    puede serializarse correctamente a JSON.
    """
    ruta_salida = (
        RUTA_PROYECTO
        / "pruebas"
        / "facturas"
        / "resultados"
        / "simulado"
        / "resultado_motor_simulado.json"
    )

    ruta_salida.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with ruta_salida.open(
        mode="w",
        encoding="utf-8",
    ) as archivo:
        json.dump(
            resultado.a_diccionario(),
            archivo,
            ensure_ascii=False,
            indent=2,
        )

    return ruta_salida


def ejecutar_pruebas() -> None:
    motor = MotorSimulado()

    ruta_pdf = buscar_primer_pdf()

    resultado_correcto = motor.procesar(ruta_pdf)

    mostrar_resultado(
        titulo="PRUEBA 1 - PDF EXISTENTE",
        resultado=resultado_correcto,
    )

    errores_resultado = resultado_correcto.validar()

    if errores_resultado:
        print()
        print("Errores de validación del resultado:")

        for error in errores_resultado:
            print(f"- {error}")

        raise SystemExit(1)

    ruta_json = guardar_resultado_json(
        resultado_correcto
    )

    print(f"Resultado guardado en: {ruta_json}")

    resultado_inexistente = motor.procesar(
        RUTA_DOCUMENTOS_PRUEBA
        / "archivo_que_no_existe.pdf"
    )

    mostrar_resultado(
        titulo="PRUEBA 2 - ARCHIVO INEXISTENTE",
        resultado=resultado_inexistente,
    )

    if resultado_inexistente.procesado_correctamente:
        raise SystemExit(
            "La prueba del archivo inexistente debería haber fallado."
        )

    print()
    print("RESULTADO FINAL")
    print("---------------")
    print("Todas las pruebas del motor común han finalizado correctamente.")


if __name__ == "__main__":
    ejecutar_pruebas()