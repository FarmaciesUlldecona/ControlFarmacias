import re


class ConsultaSQLNoPermitida(ValueError):
    """Se lanza cuando una consulta puede modificar SQL Server."""


PALABRAS_PROHIBIDAS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "CREATE",
    "ALTER",
    "DROP",
    "TRUNCATE",
    "EXEC",
    "EXECUTE",
    "CALL",
    "GRANT",
    "REVOKE",
    "DENY",
    "BACKUP",
    "RESTORE",
    "DBCC",
    "SHUTDOWN",
    "KILL",
    "RECONFIGURE",
    "BULK",
    "OPENROWSET",
    "OPENQUERY",
    "OPENDATASOURCE",
    "INTO",
    "USE",
    "SET",
    "DECLARE",
    "BEGIN",
    "COMMIT",
    "ROLLBACK",
    "SAVE",
    "WAITFOR",
}


def _ocultar_cadenas_e_identificadores(consulta: str) -> str:
    """
    Oculta textos entre comillas e identificadores entre corchetes.

    Así, por ejemplo, buscar el texto 'DELETE' no provoca un falso bloqueo.
    """

    resultado = re.sub(
        r"N?'(?:''|[^'])*'",
        "''",
        consulta,
        flags=re.IGNORECASE,
    )

    resultado = re.sub(
        r'"(?:""|[^"])*"',
        '""',
        resultado,
    )

    resultado = re.sub(
        r"\[(?:\]\]|[^\]])*\]",
        "[]",
        resultado,
    )

    return resultado


def validar_consulta_lectura(consulta: str) -> str:
    """
    Comprueba que una consulta sea exclusivamente de lectura.

    Solo permite consultas que comiencen por SELECT o WITH.
    Devuelve la consulta limpia cuando es válida.
    """

    if not isinstance(consulta, str):
        raise ConsultaSQLNoPermitida(
            "La consulta SQL debe ser un texto."
        )

    consulta_limpia = consulta.strip()

    if not consulta_limpia:
        raise ConsultaSQLNoPermitida(
            "La consulta SQL está vacía."
        )

    # No permitimos comentarios porque podrían utilizarse para ocultar código.
    if "--" in consulta_limpia:
        raise ConsultaSQLNoPermitida(
            "No se permiten comentarios SQL con --."
        )

    if "/*" in consulta_limpia or "*/" in consulta_limpia:
        raise ConsultaSQLNoPermitida(
            "No se permiten comentarios SQL con /* */."
        )

    # Permitimos únicamente un punto y coma final.
    if consulta_limpia.endswith(";"):
        consulta_limpia = consulta_limpia[:-1].rstrip()

    if ";" in consulta_limpia:
        raise ConsultaSQLNoPermitida(
            "No se permiten varias instrucciones SQL."
        )

    consulta_analizable = _ocultar_cadenas_e_identificadores(
        consulta_limpia
    )

    consulta_normalizada = re.sub(
        r"\s+",
        " ",
        consulta_analizable,
    ).strip().upper()

    if not re.match(r"^(SELECT|WITH)\b", consulta_normalizada):
        raise ConsultaSQLNoPermitida(
            "Solo se permiten consultas que comiencen por SELECT o WITH."
        )

    for palabra in PALABRAS_PROHIBIDAS:
        patron = rf"\b{re.escape(palabra)}\b"

        if re.search(patron, consulta_normalizada):
            raise ConsultaSQLNoPermitida(
                f"Operación SQL prohibida detectada: {palabra}"
            )

    if re.search(
        r"\bNEXT\s+VALUE\s+FOR\b",
        consulta_normalizada,
    ):
        raise ConsultaSQLNoPermitida(
            "No se permite avanzar secuencias de SQL Server."
        )

    return consulta_limpia


def ejecutar_pruebas() -> None:
    consultas_permitidas = [
        "SELECT TOP 10 * FROM Albaran",
        """
        SELECT IdContador, NumeroAlbaran
        FROM Albaran
        WHERE NumeroAlbaran = 'DELETE-123'
        """,
        """
        WITH UltimosAlbaranes AS (
            SELECT TOP 10 IdContador
            FROM Albaran
            ORDER BY IdContador DESC
        )
        SELECT *
        FROM UltimosAlbaranes
        """,
    ]

    consultas_prohibidas = [
        "UPDATE Albaran SET NumeroAlbaran = 'X'",
        "DELETE FROM Albaran",
        "INSERT INTO Albaran DEFAULT VALUES",
        "DROP TABLE Albaran",
        "SELECT * INTO CopiaAlbaran FROM Albaran",
        "EXEC sp_help 'Albaran'",
        "SELECT * FROM Albaran; DELETE FROM Albaran",
        "SELECT * FROM Albaran -- comentario",
        "WITH Datos AS (SELECT * FROM Albaran) DELETE FROM Datos",
    ]

    for consulta in consultas_permitidas:
        validar_consulta_lectura(consulta)

    for consulta in consultas_prohibidas:
        try:
            validar_consulta_lectura(consulta)
        except ConsultaSQLNoPermitida:
            continue

        raise AssertionError(
            f"La consulta debería haberse bloqueado: {consulta}"
        )

    print("OK: todas las consultas de lectura han sido aceptadas.")
    print("OK: todas las operaciones peligrosas han sido bloqueadas.")


if __name__ == "__main__":
    ejecutar_pruebas()