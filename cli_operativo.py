"""CLI natural para Pio: `cf "orden"` o modo interactivo `cf`."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from interfaz_operativa import (
    ConfiguracionOperativa,
    crear_orquestador_operativo,
    resultado_humano,
    resultado_json,
)


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cf",
        description="Envía órdenes naturales seguras al Orquestador ControlFarmacias.",
        epilog=(
            'Ejemplos: cf "estado" | cf "comprueba git" | '
            'cf "qué presupuesto queda" | cf "ejecuta los tests focales del orquestador". '
            "Las tareas HEAVY, el coste, commit y push pueden requerir autorización. "
            "Farmatic es siempre solo lectura."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Muestra el resultado estructurado completo.")
    parser.add_argument("orden", nargs="*", help="Orden natural para el Orquestador.")
    return parser


class SesionCLI:
    def __init__(self, app, *, entrada=sys.stdin, salida=sys.stdout) -> None:
        self.app = app
        self.entrada = entrada
        self.salida = salida
        self.inicio = app.iniciar()

    def procesar(self, orden: str, *, como_json: bool = False) -> int:
        callback = None if como_json else self._mostrar_orden_aceptada
        resultado = self.app.procesar_orden(orden, al_aceptar=callback)
        presupuesto = self.app.consultar_presupuesto()
        texto = (
            resultado_json(orden, resultado, presupuesto)
            if como_json else resultado_humano(orden, resultado, presupuesto)
        )
        print(texto, file=self.salida)
        return 0 if resultado.ok else 2 if resultado.requiere_intervencion else 1

    def _mostrar_orden_aceptada(self, datos: dict[str, object]) -> None:
        print("ORDEN ACEPTADA", file=self.salida)
        print(f"PROYECTO: {datos.get('proyecto') or 'No aplica'}", file=self.salida)
        print(f"MODO: {datos.get('nivel_recurso') or 'No clasificado'}", file=self.salida)
        print(
            "CODEX: Se utilizará" if datos.get("requiere_codex") else "CODEX: No se utilizará",
            file=self.salida,
        )
        print("ESTADO: Ejecutando análisis...", file=self.salida, flush=True)

    def interactivo(self, *, como_json: bool = False) -> int:
        print("ControlFarmacias Orquestador V0.2.12", file=self.salida)
        print("Escribe una orden. Escribe 'salir' para cerrar.", file=self.salida)
        while True:
            print("> ", end="", file=self.salida, flush=True)
            linea = self.entrada.readline()
            if linea == "":
                return 0
            orden = linea.strip()
            if not orden:
                continue
            if orden.casefold() in {"salir", "exit", "quit"}:
                return 0
            self.procesar(orden, como_json=como_json)


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    configuracion = ConfiguracionOperativa(cwd=Path.cwd())
    try:
        app = crear_orquestador_operativo(configuracion)
        sesion = SesionCLI(app)
        orden = " ".join(args.orden).strip()
        return sesion.procesar(orden, como_json=args.json) if orden else sesion.interactivo(como_json=args.json)
    except (OSError, ValueError) as exc:
        print(f"No se pudo iniciar cf: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
