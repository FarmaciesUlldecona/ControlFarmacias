import hashlib
import mimetypes
import re
import sqlite3
import time
import unicodedata
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from config.config import NOMBRE_FARMACIA
from src.supabase_client.conexion_supabase import obtener_cliente_supabase
from src.utils.logger import obtener_logger


RUTA_FACTURAS = Path(
    r"G:\Mi unidad\FACTURES PIO"
)

FECHA_INICIO_IMPORTACION = date(2026, 6, 1)

FARMACIA_ESPERADA = "PIO"
BUCKET_FACTURAS = "facturas-pdf"

MAXIMO_INTENTOS = 3
ESPERAS_REINTENTO = [5, 15]

CARPETA_DATOS = Path("data")
ARCHIVO_INDICE = CARPETA_DATOS / "indice_facturas.sqlite"

TAMANO_PAGINA_SUPABASE = 1000

logger = obtener_logger("importar_facturas_drive")


MESES_RECONOCIDOS = {
    # Catalán
    "GENER": 1,
    "FEBRER": 2,
    "MARC": 3,
    "ABRIL": 4,
    "MAIG": 5,
    "JUNY": 6,
    "JULIOL": 7,
    "AGOST": 8,
    "SETEMBRE": 9,
    "OCTUBRE": 10,
    "NOVEMBRE": 11,
    "DESEMBRE": 12,

    # Castellano
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "SETIEMBRE": 9,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}


def validar_configuracion() -> None:
    """
    Impide importar facturas bajo una farmacia incorrecta.
    """

    if NOMBRE_FARMACIA != FARMACIA_ESPERADA:
        raise RuntimeError(
            "Configuración de farmacia incorrecta. "
            f"Se esperaba {FARMACIA_ESPERADA}, "
            f"pero config.py contiene {NOMBRE_FARMACIA}."
        )

    if not RUTA_FACTURAS.exists():
        raise FileNotFoundError(
            f"No existe la carpeta de facturas: {RUTA_FACTURAS}"
        )


def normalizar_texto(texto: str) -> str:
    """
    Convierte a mayúsculas y elimina acentos.
    """

    texto_normalizado = unicodedata.normalize(
        "NFKD",
        texto,
    )

    texto_sin_acentos = "".join(
        caracter
        for caracter in texto_normalizado
        if not unicodedata.combining(caracter)
    )

    return texto_sin_acentos.upper().strip()


def interpretar_ano(texto_ano: str) -> int | None:
    """
    Convierte años de dos o cuatro cifras.
    """

    try:
        ano = int(texto_ano)
    except ValueError:
        return None

    if 0 <= ano <= 99:
        return 2000 + ano

    if 2000 <= ano <= 9999:
        return ano

    return None


def obtener_fecha_carpeta_mes(
    nombre_carpeta: str,
) -> date | None:
    """
    Interpreta carpetas como JUNY 26, AGOST 2026 o GENER 27.
    """

    nombre_normalizado = normalizar_texto(
        nombre_carpeta
    )

    nombre_separado = re.sub(
        r"[^A-Z0-9]+",
        " ",
        nombre_normalizado,
    ).strip()

    palabras = nombre_separado.split()

    mes_encontrado: int | None = None
    ano_encontrado: int | None = None

    for palabra in palabras:
        if palabra in MESES_RECONOCIDOS:
            mes_encontrado = MESES_RECONOCIDOS[
                palabra
            ]
            break

    for palabra in palabras:
        if re.fullmatch(r"\d{2}|\d{4}", palabra):
            ano_encontrado = interpretar_ano(
                palabra
            )

            if ano_encontrado is not None:
                break

    if (
        mes_encontrado is None
        or ano_encontrado is None
    ):
        return None

    try:
        return date(
            ano_encontrado,
            mes_encontrado,
            1,
        )
    except ValueError:
        return None


def obtener_carpetas_mensuales_validas() -> list[Path]:
    """
    Obtiene todas las carpetas desde junio de 2026,
    sin límite de fecha final.
    """

    carpetas_validas: list[
        tuple[date, Path]
    ] = []

    for carpeta in RUTA_FACTURAS.iterdir():
        if not carpeta.is_dir():
            continue

        fecha_carpeta = obtener_fecha_carpeta_mes(
            carpeta.name
        )

        if fecha_carpeta is None:
            logger.warning(
                "Carpeta ignorada por nombre no reconocido | "
                "Carpeta: %s",
                carpeta.name,
            )
            continue

        if fecha_carpeta < FECHA_INICIO_IMPORTACION:
            continue

        carpetas_validas.append(
            (
                fecha_carpeta,
                carpeta,
            )
        )

    carpetas_validas.sort(
        key=lambda elemento: elemento[0]
    )

    return [
        carpeta
        for _, carpeta in carpetas_validas
    ]


def obtener_facturas_pdf() -> list[Path]:
    """
    Localiza todos los PDF desde junio de 2026.
    """

    facturas: list[Path] = []

    for carpeta_mes in obtener_carpetas_mensuales_validas():
        for archivo in carpeta_mes.rglob("*"):
            if (
                archivo.is_file()
                and archivo.suffix.lower() == ".pdf"
            ):
                facturas.append(archivo)

    facturas.sort(
        key=lambda archivo: str(archivo).lower()
    )

    return facturas


def obtener_conexion_indice() -> sqlite3.Connection:
    """
    Abre el índice local utilizado para evitar volver
    a leer archivos que no han cambiado.
    """

    CARPETA_DATOS.mkdir(
        parents=True,
        exist_ok=True,
    )

    conexion = sqlite3.connect(
        ARCHIVO_INDICE
    )

    conexion.row_factory = sqlite3.Row

    conexion.execute(
        """
        CREATE TABLE IF NOT EXISTS archivos_facturas (
            ruta_relativa TEXT PRIMARY KEY,
            tamano INTEGER NOT NULL,
            fecha_modificacion_ns INTEGER NOT NULL,
            archivo_hash TEXT,
            estado TEXT NOT NULL,
            ultimo_error TEXT,
            fecha_actualizacion TEXT NOT NULL
        )
        """
    )

    conexion.commit()

    return conexion


def obtener_registro_indice(
    conexion: sqlite3.Connection,
    ruta_relativa: str,
) -> sqlite3.Row | None:
    """
    Obtiene el registro local de un PDF.
    """

    cursor = conexion.execute(
        """
        SELECT
            ruta_relativa,
            tamano,
            fecha_modificacion_ns,
            archivo_hash,
            estado,
            ultimo_error
        FROM archivos_facturas
        WHERE ruta_relativa = ?
        """,
        (ruta_relativa,),
    )

    return cursor.fetchone()


def guardar_registro_indice(
    conexion: sqlite3.Connection,
    ruta_relativa: str,
    tamano: int,
    fecha_modificacion_ns: int,
    archivo_hash: str | None,
    estado: str,
    ultimo_error: str | None = None,
) -> None:
    """
    Crea o actualiza el estado local del archivo.
    """

    conexion.execute(
        """
        INSERT INTO archivos_facturas (
            ruta_relativa,
            tamano,
            fecha_modificacion_ns,
            archivo_hash,
            estado,
            ultimo_error,
            fecha_actualizacion
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ruta_relativa)
        DO UPDATE SET
            tamano = excluded.tamano,
            fecha_modificacion_ns = excluded.fecha_modificacion_ns,
            archivo_hash = excluded.archivo_hash,
            estado = excluded.estado,
            ultimo_error = excluded.ultimo_error,
            fecha_actualizacion = excluded.fecha_actualizacion
        """,
        (
            ruta_relativa,
            tamano,
            fecha_modificacion_ns,
            archivo_hash,
            estado,
            ultimo_error,
            datetime.now().isoformat(
                timespec="seconds"
            ),
        ),
    )

    conexion.commit()


def archivo_no_ha_cambiado(
    registro: sqlite3.Row | None,
    tamano: int,
    fecha_modificacion_ns: int,
) -> bool:
    """
    Comprueba si el archivo tiene el mismo tamaño
    y la misma fecha de modificación que en la última ejecución.
    """

    if registro is None:
        return False

    return (
        int(registro["tamano"]) == tamano
        and int(
            registro["fecha_modificacion_ns"]
        ) == fecha_modificacion_ns
    )


def obtener_hashes_supabase() -> set[str]:
    """
    Descarga una sola vez todos los hashes de facturas
    de la farmacia desde Supabase.

    Usa paginación para admitir miles de facturas.
    """

    cliente = obtener_cliente_supabase()

    hashes: set[str] = set()
    inicio = 0

    while True:
        fin = (
            inicio
            + TAMANO_PAGINA_SUPABASE
            - 1
        )

        respuesta = (
            cliente
            .table("facturas")
            .select("archivo_hash")
            .eq(
                "farmacia",
                NOMBRE_FARMACIA,
            )
            .range(
                inicio,
                fin,
            )
            .execute()
        )

        filas = respuesta.data or []

        for fila in filas:
            archivo_hash = fila.get(
                "archivo_hash"
            )

            if archivo_hash:
                hashes.add(
                    str(archivo_hash)
                )

        if len(filas) < TAMANO_PAGINA_SUPABASE:
            break

        inicio += TAMANO_PAGINA_SUPABASE

    return hashes


def calcular_hash_archivo(
    ruta_archivo: Path,
) -> str:
    """
    Calcula el SHA-256 del PDF.
    """

    calculador = hashlib.sha256()

    with ruta_archivo.open("rb") as archivo:
        while True:
            bloque = archivo.read(
                1024 * 1024
            )

            if not bloque:
                break

            calculador.update(bloque)

    return calculador.hexdigest()


def validar_pdf_nuevo(
    ruta_pdf: Path,
) -> None:
    """
    Valida únicamente los archivos nuevos o modificados.
    """

    if not ruta_pdf.exists():
        raise FileNotFoundError(
            f"El archivo no existe: {ruta_pdf}"
        )

    if not ruta_pdf.is_file():
        raise ValueError(
            f"No es un archivo: {ruta_pdf}"
        )

    tamano_inicial = ruta_pdf.stat().st_size

    if tamano_inicial <= 0:
        raise ValueError(
            "El PDF está vacío."
        )

    time.sleep(1)

    tamano_final = ruta_pdf.stat().st_size

    if tamano_inicial != tamano_final:
        raise RuntimeError(
            "El archivo todavía se está sincronizando."
        )

    with ruta_pdf.open("rb") as archivo:
        cabecera = archivo.read(5)

    if cabecera != b"%PDF-":
        raise ValueError(
            "El archivo no contiene una cabecera PDF válida."
        )


def normalizar_nombre_storage(
    texto: str,
) -> str:
    """
    Genera nombres seguros para Storage.
    """

    texto_normalizado = unicodedata.normalize(
        "NFKD",
        texto,
    )

    texto_sin_acentos = "".join(
        caracter
        for caracter in texto_normalizado
        if not unicodedata.combining(caracter)
    )

    texto_limpio = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        texto_sin_acentos,
    )

    texto_limpio = re.sub(
        r"_+",
        "_",
        texto_limpio,
    ).strip("._-")

    return texto_limpio or "archivo"


def crear_ruta_storage(
    ruta_pdf: Path,
    archivo_hash: str,
) -> str:
    """
    Crea la ruta del archivo dentro del bucket.
    """

    ruta_relativa = ruta_pdf.relative_to(
        RUTA_FACTURAS
    )

    carpetas = [
        normalizar_nombre_storage(parte)
        for parte in ruta_relativa.parts[:-1]
    ]

    nombre_archivo = normalizar_nombre_storage(
        ruta_pdf.stem
    )

    nombre_storage = (
        f"{nombre_archivo}_"
        f"{archivo_hash[:12]}.pdf"
    )

    return str(
        PurePosixPath(
            NOMBRE_FARMACIA,
            *carpetas,
            nombre_storage,
        )
    )


def obtener_nombre_storage(
    elemento: Any,
) -> str | None:
    """
    Obtiene el nombre de una respuesta de Storage.
    """

    if isinstance(elemento, dict):
        nombre = elemento.get("name")
    else:
        nombre = getattr(
            elemento,
            "name",
            None,
        )

    if nombre is None:
        return None

    return str(nombre)


def archivo_existe_en_storage(
    cliente,
    ruta_storage: str,
) -> bool:
    """
    Comprueba si un archivo ya existe en Storage.
    Solo se utiliza para archivos nuevos.
    """

    ruta = PurePosixPath(
        ruta_storage
    )

    respuesta = (
        cliente
        .storage
        .from_(BUCKET_FACTURAS)
        .list(
            path=str(ruta.parent),
            options={
                "search": ruta.name,
                "limit": 10,
            },
        )
    )

    return any(
        obtener_nombre_storage(elemento)
        == ruta.name
        for elemento in respuesta
    )


def subir_pdf_storage(
    cliente,
    ruta_pdf: Path,
    ruta_storage: str,
) -> None:
    """
    Sube el PDF al bucket privado.
    """

    tipo_mime = (
        mimetypes.guess_type(
            ruta_pdf.name
        )[0]
        or "application/pdf"
    )

    with ruta_pdf.open("rb") as archivo:
        (
            cliente
            .storage
            .from_(BUCKET_FACTURAS)
            .upload(
                path=ruta_storage,
                file=archivo,
                file_options={
                    "content-type": tipo_mime,
                    "cache-control": "3600",
                    "upsert": "false",
                },
            )
        )


def registrar_factura(
    cliente,
    ruta_pdf: Path,
    ruta_storage: str,
    archivo_hash: str,
) -> None:
    """
    Crea el registro inicial en Supabase.
    """

    datos = {
        "farmacia": NOMBRE_FARMACIA,
        "archivo_nombre": ruta_pdf.name,
        "archivo_ruta": ruta_storage,
        "archivo_hash": archivo_hash,
        "estado_lectura": "PENDIENTE",
        "estado_conciliacion": "PENDIENTE",
        "estado_pago": "SIN_PAGAR",
        "requiere_revision": False,
        "validada_manualmente": False,
        "datos_extraidos": {},
    }

    (
        cliente
        .table("facturas")
        .insert(datos)
        .execute()
    )


def es_error_reintentable(
    error: Exception,
) -> bool:
    """
    Identifica errores temporales.
    """

    mensaje = str(error).lower()

    textos_reintentables = (
        "timed out",
        "timeout",
        "connection",
        "temporarily",
        "temporary",
        "network",
        "read operation",
        "write operation",
        "server disconnected",
        "connection reset",
        "remote protocol",
        "broken pipe",
        "502",
        "503",
        "504",
    )

    return any(
        texto in mensaje
        for texto in textos_reintentables
    )


def importar_archivo_nuevo(
    cliente,
    conexion_indice: sqlite3.Connection,
    ruta_pdf: Path,
    ruta_relativa: str,
    tamano: int,
    fecha_modificacion_ns: int,
    archivo_hash: str,
) -> tuple[str, int, str | None]:
    """
    Sube y registra un archivo nuevo con tres intentos.
    """

    ultimo_error: Exception | None = None

    for intento in range(
        1,
        MAXIMO_INTENTOS + 1,
    ):
        try:
            ruta_storage = crear_ruta_storage(
                ruta_pdf,
                archivo_hash,
            )

            if not archivo_existe_en_storage(
                cliente,
                ruta_storage,
            ):
                subir_pdf_storage(
                    cliente,
                    ruta_pdf,
                    ruta_storage,
                )

            registrar_factura(
                cliente,
                ruta_pdf,
                ruta_storage,
                archivo_hash,
            )

            guardar_registro_indice(
                conexion_indice,
                ruta_relativa,
                tamano,
                fecha_modificacion_ns,
                archivo_hash,
                "IMPORTADA",
            )

            logger.info(
                "Factura importada | Archivo: %s | Intento: %s",
                ruta_relativa,
                intento,
            )

            return (
                "IMPORTADA",
                intento,
                None,
            )

        except Exception as error:
            ultimo_error = error

            logger.exception(
                "Error importando factura | "
                "Archivo: %s | Intento: %s/%s | Error: %s",
                ruta_relativa,
                intento,
                MAXIMO_INTENTOS,
                error,
            )

            if (
                not es_error_reintentable(error)
                or intento == MAXIMO_INTENTOS
            ):
                break

            segundos = ESPERAS_REINTENTO[
                intento - 1
            ]

            time.sleep(segundos)

    mensaje_error = (
        str(ultimo_error)
        if ultimo_error is not None
        else "Error desconocido"
    )

    guardar_registro_indice(
        conexion_indice,
        ruta_relativa,
        tamano,
        fecha_modificacion_ns,
        archivo_hash,
        "ERROR",
        mensaje_error,
    )

    return (
        "ERROR",
        MAXIMO_INTENTOS,
        mensaje_error,
    )


def importar_facturas() -> None:
    """
    Importación incremental optimizada.

    Los PDF conocidos y sin cambios se descartan mediante
    el índice local sin volver a abrirlos ni consultar Supabase.
    """

    inicio_proceso = time.monotonic()

    validar_configuracion()

    logger.info(
        "Inicio de importación optimizada | "
        "Farmacia: %s | Ruta: %s",
        NOMBRE_FARMACIA,
        RUTA_FACTURAS,
    )

    conexion_indice = obtener_conexion_indice()
    cliente = obtener_cliente_supabase()

    try:
        hashes_supabase = obtener_hashes_supabase()
        facturas = obtener_facturas_pdf()

        total = len(facturas)

        print()
        print("IMPORTACION OPTIMIZADA DE FACTURAS")
        print("----------------------------------")
        print(f"PDF encontrados: {total}")
        print(
            "Facturas registradas en Supabase: "
            f"{len(hashes_supabase)}"
        )
        print()

        omitidas_indice = 0
        existentes_supabase = 0
        importadas = 0
        recuperadas = 0
        modificadas = 0
        errores = 0

        archivos_error: list[
            tuple[str, str]
        ] = []

        for posicion, ruta_pdf in enumerate(
            facturas,
            start=1,
        ):
            ruta_relativa = str(
                ruta_pdf.relative_to(
                    RUTA_FACTURAS
                )
            )

            datos_archivo = ruta_pdf.stat()
            tamano = datos_archivo.st_size
            fecha_modificacion_ns = (
                datos_archivo.st_mtime_ns
            )

            registro = obtener_registro_indice(
                conexion_indice,
                ruta_relativa,
            )

            sin_cambios = archivo_no_ha_cambiado(
                registro,
                tamano,
                fecha_modificacion_ns,
            )

            if (
                sin_cambios
                and registro is not None
                and registro["estado"] == "IMPORTADA"
                and registro["archivo_hash"]
                in hashes_supabase
            ):
                omitidas_indice += 1
                continue

            print(
                f"[{posicion}/{total}] "
                f"{ruta_relativa}"
            )

            try:
                validar_pdf_nuevo(
                    ruta_pdf
                )

                archivo_hash = calcular_hash_archivo(
                    ruta_pdf
                )

                if (
                    registro is not None
                    and not sin_cambios
                ):
                    modificadas += 1

                    logger.warning(
                        "Archivo modificado desde la última ejecución | "
                        "Archivo: %s",
                        ruta_relativa,
                    )

                if archivo_hash in hashes_supabase:
                    guardar_registro_indice(
                        conexion_indice,
                        ruta_relativa,
                        tamano,
                        fecha_modificacion_ns,
                        archivo_hash,
                        "IMPORTADA",
                    )

                    existentes_supabase += 1

                    print(
                        "  Ya estaba registrada. "
                        "Añadida al índice local."
                    )

                    continue

                estado, intentos, error = (
                    importar_archivo_nuevo(
                        cliente,
                        conexion_indice,
                        ruta_pdf,
                        ruta_relativa,
                        tamano,
                        fecha_modificacion_ns,
                        archivo_hash,
                    )
                )

                if estado == "IMPORTADA":
                    importadas += 1
                    hashes_supabase.add(
                        archivo_hash
                    )

                    if intentos > 1:
                        recuperadas += 1

                    print(
                        "  Importada correctamente."
                    )

                else:
                    errores += 1

                    archivos_error.append(
                        (
                            ruta_relativa,
                            error
                            or "Error desconocido",
                        )
                    )

                    print(
                        "  ERROR pendiente."
                    )

            except Exception as error:
                errores += 1

                mensaje_error = str(error)

                guardar_registro_indice(
                    conexion_indice,
                    ruta_relativa,
                    tamano,
                    fecha_modificacion_ns,
                    (
                        registro["archivo_hash"]
                        if registro is not None
                        else None
                    ),
                    "ERROR",
                    mensaje_error,
                )

                logger.exception(
                    "Error procesando PDF | "
                    "Archivo: %s | Error: %s",
                    ruta_relativa,
                    error,
                )

                archivos_error.append(
                    (
                        ruta_relativa,
                        mensaje_error,
                    )
                )

        duracion = (
            time.monotonic()
            - inicio_proceso
        )

        logger.info(
            "Importación optimizada finalizada | "
            "Detectadas: %s | "
            "Omitidas por índice: %s | "
            "Existentes añadidas al índice: %s | "
            "Importadas: %s | "
            "Modificadas: %s | "
            "Errores: %s | "
            "Duración: %.2f segundos",
            total,
            omitidas_indice,
            existentes_supabase,
            importadas,
            modificadas,
            errores,
            duracion,
        )

        print()
        print("IMPORTACION FINALIZADA")
        print("----------------------")
        print(f"PDF detectados: {total}")
        print(
            "Omitidos sin abrir: "
            f"{omitidas_indice}"
        )
        print(
            "Existentes añadidos al índice: "
            f"{existentes_supabase}"
        )
        print(f"Importadas nuevas: {importadas}")
        print(
            "Recuperadas tras reintento: "
            f"{recuperadas}"
        )
        print(
            "Archivos modificados: "
            f"{modificadas}"
        )
        print(f"Errores pendientes: {errores}")
        print(f"Duración: {duracion:.1f} segundos")

        if archivos_error:
            print()
            print("ARCHIVOS CON ERROR")
            print("------------------")

            for archivo, error in archivos_error:
                print(f"- {archivo}")
                print(f"  Error: {error}")

    finally:
        conexion_indice.close()


if __name__ == "__main__":
    importar_facturas()