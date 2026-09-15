import pytest

from src.database.conexion_sql import (
    ConexionSQLNoSegura,
    ConexionSoloLectura,
    certificar_conexion_solo_lectura,
)
from src.sql_explorer.seguridad_sql import (
    ConsultaSQLNoPermitida,
    validar_consulta_lectura,
)


class CursorFalso:
    def __init__(self, fila=None):
        self.fila = fila
        self.consultas = []
        self.closed = False
        self.description = []

    def execute(self, consulta, *parametros):
        self.consultas.append((consulta, parametros))
        return self

    def fetchone(self):
        return self.fila

    def close(self):
        self.closed = True


class ConexionFalsa:
    def __init__(self, fila=None):
        self.cursor_falso = CursorFalso(fila)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cursor_falso

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


FILA_CERTIFICADA = (
    r"MOSTRADOR\ControlFarmaciasRO",
    r"MOSTRADOR\ControlFarmaciasRO",
    "Farmatic",
    0,
    0,
    1,
    0,
    0,
    1,
    0,
    0,
    0,
    0,
    0,
    0,
)


@pytest.mark.parametrize(
    "consulta",
    [
        "SELECT * FROM Albaran WITH (UPDLOCK)",
        "SELECT * FROM Albaran WITH (HOLDLOCK)",
        "SELECT * FROM Albaran WITH (XLOCK)",
        "SELECT * FROM Albaran OPTION (MAXDOP 0)",
        "SELECT * INTO Copia FROM Albaran",
        "WITH Datos AS (SELECT * FROM Albaran) UPDATE Datos SET x = 1",
    ],
)
def test_validador_bloquea_consultas_disruptivas(consulta):
    with pytest.raises(ConsultaSQLNoPermitida):
        validar_consulta_lectura(consulta)


def test_cursor_central_valida_incluso_si_el_llamador_no_lo_hace():
    conexion_real = ConexionFalsa()
    conexion = ConexionSoloLectura(conexion_real)

    with pytest.raises(ConsultaSQLNoPermitida):
        conexion.cursor().execute("DELETE FROM Albaran")

    assert conexion_real.cursor_falso.consultas == []


def test_cursor_central_permite_select_parametrizado():
    conexion_real = ConexionFalsa()
    conexion = ConexionSoloLectura(conexion_real)

    cursor = conexion.cursor()
    resultado = cursor.execute(
        "SELECT * FROM Albaran WHERE IdContador = ?",
        7,
    )

    assert resultado is cursor
    assert conexion_real.cursor_falso.consultas == [
        ("SELECT * FROM Albaran WHERE IdContador = ?", (7,))
    ]


def test_conexion_no_permite_commit_ni_executemany():
    conexion = ConexionSoloLectura(ConexionFalsa())

    with pytest.raises(ConsultaSQLNoPermitida):
        conexion.commit()

    with pytest.raises(ConsultaSQLNoPermitida):
        conexion.cursor().executemany(
            "SELECT * FROM Albaran WHERE IdContador = ?",
            [(1,), (2,)],
        )


def test_certificacion_acepta_identidad_y_permisos_correctos():
    conexion = ConexionFalsa(FILA_CERTIFICADA)

    certificar_conexion_solo_lectura(conexion)

    consulta, parametros = conexion.cursor_falso.consultas[0]
    assert consulta.lstrip().startswith("SELECT")
    assert parametros == ()
    assert conexion.cursor_falso.closed is True


@pytest.mark.parametrize(
    "indice,valor",
    [
        (0, r"MOSTRADOR\Usuari"),
        (3, 1),
        (4, 1),
        (5, 0),
        (6, 1),
        (9, 1),
        (10, 1),
        (11, 1),
        (12, 1),
        (13, 1),
        (14, 1),
    ],
)
def test_certificacion_rechaza_cualquier_permiso_peligroso(
    indice,
    valor,
):
    fila = list(FILA_CERTIFICADA)
    fila[indice] = valor
    conexion = ConexionFalsa(tuple(fila))

    with pytest.raises(ConexionSQLNoSegura):
        certificar_conexion_solo_lectura(conexion)
