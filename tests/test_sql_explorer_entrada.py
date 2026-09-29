"""
Tests de la lectura común de entrada de src/sql_explorer (BOM U+FEFF).

No conectan con Farmatic: cada test sustituye ``input`` y la primera función
que accedería a SQL Server.
"""

import ast
import builtins
import subprocess
import sys
from pathlib import Path

import pytest

from src.sql_explorer import (
    analizar_tabla,
    buscar_columnas,
    buscar_objetos,
    buscar_registros,
    clave_primaria,
    describir_tabla,
    valores_columna,
    ver_tabla,
)
from src.sql_explorer.entrada import leer_texto, limpiar_texto


BOM = "﻿"

DIRECTORIO_SQL_EXPLORER = (
    Path(__file__).resolve().parents[1] / "src" / "sql_explorer"
)


class _FinDeLaPrueba(Exception):
    """Detiene la herramienta tras capturar el valor leído."""


# 1. limpiar_texto


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        (f"{BOM}Familia", "Familia"),
        (f" {BOM} Familia \t", "Familia"),
        (f"{BOM}{BOM}Familia{BOM}", "Familia"),
        ("Familia\r\n", "Familia"),
        (f"{BOM}Familia\r", "Familia"),
        ("Familia", "Familia"),
        ("dbo.Albaran", "dbo.Albaran"),
        (f"Fami{BOM}lia", f"Fami{BOM}lia"),
        ("Familia  de producto", "Familia  de producto"),
        ("", ""),
        (BOM, ""),
        (f" {BOM} \r\n", ""),
    ],
)
def test_limpiar_texto(entrada: str, esperado: str) -> None:
    assert limpiar_texto(entrada) == esperado


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        (f"{BOM}  valor ", "  valor "),
        (f"  valor {BOM}", "  valor "),
        ("   ", "   "),
        (BOM, ""),
        (f"va{BOM}lor", f"va{BOM}lor"),
    ],
)
def test_limpiar_texto_sin_recortar_espacios(
    entrada: str,
    esperado: str,
) -> None:
    assert limpiar_texto(entrada, recortar_espacios=False) == esperado


# 2. leer_texto


def test_leer_texto_elimina_bom_y_retorno_de_carro(monkeypatch) -> None:
    mensajes: list[str] = []

    def input_falso(mensaje: str = "") -> str:
        mensajes.append(mensaje)
        return f"{BOM}Familia\r"

    monkeypatch.setattr(builtins, "input", input_falso)

    assert leer_texto("Texto: ") == "Familia"
    assert mensajes == ["Texto: "]


def test_leer_texto_sin_recortar_conserva_espacios(monkeypatch) -> None:
    monkeypatch.setattr(builtins, "input", lambda mensaje="": f"{BOM} a ")

    assert leer_texto("Valor: ", recortar_espacios=False) == " a "


def test_valor_filtro_por_tuberia_sin_bom_ni_fin_de_linea() -> None:
    """buscar_registros.py: el valor del filtro conserva los espacios.

    Se ejecuta en un proceso real con los bytes que canaliza Windows
    PowerShell 5.1 (BOM UTF-8 + texto + CRLF), para comprobar que no quedan
    ni U+FEFF ni \\r ni \\n residuales. No conecta con Farmatic.
    """

    codigo = (
        "from src.sql_explorer.buscar_registros import solicitar_valor_filtro; "
        "print(ascii(solicitar_valor_filtro({'necesita_valor': True})))"
    )

    resultado = subprocess.run(
        [sys.executable, "-B", "-c", codigo],
        input=b"\xef\xbb\xbf valor con espacios \r\n",
        capture_output=True,
        cwd=Path(__file__).resolve().parents[1],
        timeout=60,
    )

    assert resultado.returncode == 0, resultado.stderr.decode(errors="replace")

    ultima_linea = resultado.stdout.decode("ascii").splitlines()[-1]

    assert ultima_linea.split(": ", 1)[-1] == repr(" valor con espacios ")


# 3. buscar_objetos


INVENTARIO_FALSO = [
    {"esquema": "dbo", "nombre": "Familia", "tipo": "BASE TABLE"},
    {"esquema": "dbo", "nombre": "SubFamilia", "tipo": "BASE TABLE"},
    {"esquema": "dbo", "nombre": "VFamilias", "tipo": "VIEW"},
    {"esquema": "dbo", "nombre": "Albaran", "tipo": "BASE TABLE"},
]


@pytest.fixture
def inventario_falso(monkeypatch) -> None:
    monkeypatch.setattr(
        buscar_objetos,
        "obtener_tablas_y_vistas",
        lambda: list(INVENTARIO_FALSO),
    )


def test_buscar_objetos_con_bom_equivale_a_sin_bom(inventario_falso) -> None:
    sin_bom = buscar_objetos.buscar_objetos("Familia")
    con_bom = buscar_objetos.buscar_objetos(f"{BOM}Familia\r\n")

    assert len(sin_bom) == 3
    assert con_bom == sin_bom


@pytest.mark.parametrize("texto", [BOM, f" {BOM} ", ""])
def test_buscar_objetos_rechaza_texto_vacio_tras_limpiar(
    inventario_falso,
    texto: str,
) -> None:
    with pytest.raises(ValueError):
        buscar_objetos.buscar_objetos(texto)


# 4. Cada herramienta recibe el valor limpio en su primera lectura


def _capturar(capturados: list, detener: bool = True):
    def funcion_falsa(*args, **kwargs):
        capturados.append(args[-1] if args else kwargs)

        if detener:
            raise _FinDeLaPrueba

        return None

    return funcion_falsa


class _ConexionFalsa:
    def close(self) -> None:
        pass


CASOS_HERRAMIENTAS = [
    # (módulo, función de entrada, función a sustituir, se detiene)
    (buscar_objetos, "ejecutar_programa", "mostrar_resultados", True),
    (buscar_columnas, "ejecutar", "mostrar_resultados", True),
    (describir_tabla, "ejecutar", "mostrar_tabla", True),
    (clave_primaria, "ejecutar", "mostrar_clave_primaria", True),
    (valores_columna, "valores_columna", "localizar_objeto", False),
    (ver_tabla, "ver_tabla", "localizar_objeto", False),
    (buscar_registros, "buscar_registros", "localizar_objeto", False),
    (analizar_tabla, "analizar_tabla", "resolver_tabla", False),
]


@pytest.mark.parametrize(
    ("modulo", "entrada", "sustituida", "detener"),
    CASOS_HERRAMIENTAS,
    ids=[caso[0].__name__.rsplit(".", 1)[-1] for caso in CASOS_HERRAMIENTAS],
)
def test_herramienta_recibe_valor_sin_bom(
    monkeypatch,
    modulo,
    entrada: str,
    sustituida: str,
    detener: bool,
) -> None:
    capturados: list = []

    monkeypatch.setattr(
        builtins,
        "input",
        lambda mensaje="": f"{BOM}Familia\r",
    )
    monkeypatch.setattr(
        modulo,
        sustituida,
        _capturar(capturados, detener),
    )

    if modulo is analizar_tabla:
        monkeypatch.setattr(
            analizar_tabla,
            "obtener_conexion",
            lambda: _ConexionFalsa(),
        )

        def escritura_prohibida(*args, **kwargs):
            raise AssertionError("el test no debe escribir informes")

        monkeypatch.setattr(
            analizar_tabla,
            "guardar_informe",
            escritura_prohibida,
        )

    if detener:
        with pytest.raises(_FinDeLaPrueba):
            getattr(modulo, entrada)()
    else:
        getattr(modulo, entrada)()

    assert capturados == ["Familia"]


# 5. Test estático: ninguna llamada a input() fuera de entrada.py


def _llamadas_a_input(ruta: Path) -> list[int]:
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    lineas: list[int] = []

    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue

        funcion = nodo.func

        if isinstance(funcion, ast.Name) and funcion.id == "input":
            lineas.append(nodo.lineno)
        elif isinstance(funcion, ast.Attribute) and funcion.attr == "input":
            lineas.append(nodo.lineno)

    return lineas


def test_no_hay_input_directo_fuera_de_entrada() -> None:
    archivos = sorted(DIRECTORIO_SQL_EXPLORER.glob("*.py"))

    assert archivos, "no se encontraron módulos en src/sql_explorer"

    infracciones = [
        f"{ruta.name}:{linea}"
        for ruta in archivos
        if ruta.name != "entrada.py"
        for linea in _llamadas_a_input(ruta)
    ]

    assert infracciones == [], (
        "Usa leer_texto de src/sql_explorer/entrada.py en lugar de input(): "
        + ", ".join(infracciones)
    )


def test_entrada_py_contiene_la_unica_llamada_a_input() -> None:
    assert _llamadas_a_input(DIRECTORIO_SQL_EXPLORER / "entrada.py")
