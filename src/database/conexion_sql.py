from __future__ import annotations

import logging
import os
from typing import Any

import pyodbc

from src.sql_explorer.seguridad_sql import (
    ConsultaSQLNoPermitida,
    validar_consulta_lectura,
)


LOGIN_SOLO_LECTURA_PREDETERMINADO = (
    r"MOSTRADOR\ControlFarmaciasRO"
)
TIMEOUT_CONEXION_SEGUNDOS = 5
TIMEOUT_CONSULTA_SEGUNDOS = 30


class ConexionSQLNoSegura(RuntimeError):
    """La conexión no cumple la política obligatoria de solo lectura."""


CONSULTA_CERTIFICACION = """
SELECT
    SUSER_SNAME() AS IdentidadSQL,
    ORIGINAL_LOGIN() AS IdentidadOriginal,
    DB_NAME() AS BaseDatos,
    IS_SRVROLEMEMBER('sysadmin') AS EsSysadmin,
    IS_MEMBER('db_owner') AS EsDbOwner,
    IS_MEMBER('db_datareader') AS EsDbDatareader,
    IS_MEMBER('db_datawriter') AS EsDbDatawriter,
    IS_MEMBER('db_ddladmin') AS EsDbDdladmin,
    HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'SELECT') AS PuedeSelect,
    HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'INSERT') AS PuedeInsert,
    HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'UPDATE') AS PuedeUpdate,
    HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'DELETE') AS PuedeDelete,
    HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'ALTER') AS PuedeAlter,
    HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'EXECUTE') AS PuedeExecute,
    HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'CONTROL') AS PuedeControl
"""


class CursorSoloLectura:
    """Envuelve un cursor ODBC y valida todas sus consultas."""

    _ATRIBUTOS_BLOQUEADOS = frozenset({
        "commit",
        "execute",
        "executemany",
    })

    def __init__(self, cursor: Any):
        self._cursor = cursor

    def execute(self, consulta: str, *parametros: Any):
        consulta_segura = validar_consulta_lectura(consulta)
        self._cursor.execute(consulta_segura, *parametros)
        return self

    def executemany(self, *_args: Any, **_kwargs: Any):
        raise ConsultaSQLNoPermitida(
            "executemany está deshabilitado en conexiones de solo lectura."
        )

    def __iter__(self):
        return iter(self._cursor)

    def __enter__(self):
        return self

    def __exit__(self, _tipo, _valor, _traza):
        self.close()

    def __getattr__(self, nombre: str):
        if nombre.casefold() in self._ATRIBUTOS_BLOQUEADOS:
            raise ConsultaSQLNoPermitida(
                f"{nombre} no se expone desde el cursor de solo lectura."
            )
        return getattr(self._cursor, nombre)


class ConexionSoloLectura:
    """Expone una conexión que no permite confirmar escrituras."""

    _ATRIBUTOS_BLOQUEADOS = frozenset({
        "commit",
        "execute",
        "executemany",
    })

    def __init__(self, conexion: Any):
        self._conexion = conexion

    def cursor(self, *args: Any, **kwargs: Any) -> CursorSoloLectura:
        return CursorSoloLectura(
            self._conexion.cursor(*args, **kwargs)
        )

    def commit(self):
        raise ConsultaSQLNoPermitida(
            "commit está deshabilitado en conexiones de solo lectura."
        )

    def rollback(self):
        return self._conexion.rollback()

    def close(self):
        return self._conexion.close()

    def __enter__(self):
        return self

    def __exit__(self, _tipo, _valor, _traza):
        self.close()

    def __getattr__(self, nombre: str):
        if nombre.casefold() in self._ATRIBUTOS_BLOQUEADOS:
            raise ConsultaSQLNoPermitida(
                f"{nombre} no se expone desde la conexión de solo lectura."
            )
        return getattr(self._conexion, nombre)


def _login_solo_lectura_esperado() -> str:
    return os.environ.get(
        "CONTROLFARMACIAS_SQL_LOGIN_RO",
        LOGIN_SOLO_LECTURA_PREDETERMINADO,
    ).strip()


def certificar_conexion_solo_lectura(conexion: Any) -> None:
    """Rechaza una conexión que pueda modificar Farmatic."""

    consulta_segura = validar_consulta_lectura(
        CONSULTA_CERTIFICACION
    )
    cursor = conexion.cursor()

    try:
        cursor.execute(consulta_segura)
        fila = cursor.fetchone()
    finally:
        cursor.close()

    if fila is None:
        raise ConexionSQLNoSegura(
            "SQL Server no devolvió la certificación de permisos."
        )

    login_esperado = _login_solo_lectura_esperado()
    identidad = str(fila[0] or "")
    identidad_original = str(fila[1] or "")
    base_datos = str(fila[2] or "")

    comprobaciones = {
        "identidad SQL dedicada": (
            identidad.casefold() == login_esperado.casefold()
        ),
        "identidad original dedicada": (
            identidad_original.casefold()
            == login_esperado.casefold()
        ),
        "base Farmatic": base_datos.casefold() == "farmatic",
        "sin sysadmin": fila[3] == 0,
        "sin db_owner": fila[4] == 0,
        "con db_datareader": fila[5] == 1,
        "sin db_datawriter": fila[6] == 0,
        "sin db_ddladmin": fila[7] == 0,
        "con SELECT": fila[8] == 1,
        "sin INSERT": fila[9] == 0,
        "sin UPDATE": fila[10] == 0,
        "sin DELETE": fila[11] == 0,
        "sin ALTER": fila[12] == 0,
        "sin EXECUTE": fila[13] == 0,
        "sin CONTROL": fila[14] == 0,
    }
    fallos = [
        nombre
        for nombre, correcto in comprobaciones.items()
        if not correcto
    ]

    if fallos:
        detalle = ", ".join(fallos)
        raise ConexionSQLNoSegura(
            "Conexión Farmatic rechazada por seguridad: "
            f"{detalle}. Identidad detectada: {identidad!r}."
        )


    logging.getLogger("sincronizar_albaranes").info(
        "Certificacion Farmatic READ_ONLY superada | "
        "Identidad SQL: %s | Identidad original: %s | Base: %s | "
        "SELECT: si | INSERT/UPDATE/DELETE/ALTER/EXECUTE/CONTROL: no | "
        "sysadmin/db_owner/db_datawriter/db_ddladmin: no",
        identidad,
        identidad_original,
        base_datos,
    )


def obtener_conexion() -> ConexionSoloLectura:
    conexion = pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        "SERVER=MOSTRADOR;"
        "DATABASE=Farmatic;"
        "Trusted_Connection=yes;"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
        "ApplicationIntent=ReadOnly;"
        "APP=ControlFarmacias Solo Lectura;",
        timeout=TIMEOUT_CONEXION_SEGUNDOS,
        autocommit=False,
    )
    conexion.timeout = TIMEOUT_CONSULTA_SEGUNDOS

    try:
        certificar_conexion_solo_lectura(conexion)
    except Exception:
        conexion.close()
        raise

    return ConexionSoloLectura(conexion)
