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
TABLA_DOCUMENTOS = "documentos_facturas"

MAXIMO_INTENTOS = 3
ESPERAS_REINTENTO = [5, 15]

CARPETA_DATOS = Path("data")
ARCHIVO_INDICE = CARPETA_DATOS / "indice_facturas.sqlite"

TAMANO_PAGINA_SUPABASE = 1000

logger = obtener_logger(
    "importar_facturas_drive"
)


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
    Comprueba que el programa está configurado para PIO
    y que la carpeta de Google Drive está disponible.
    """

    if NOMBRE_FARMACIA != FARMACIA_ESPERADA:
        raise RuntimeError(
            "Configuración de farmacia incorrecta. "
            f"Se esperaba {FARMACIA_ESPERADA}, "
            f"pero config.py contiene {NOMBRE_FARMACIA}."
        )

    if not RUTA_FACTURAS.exists():
        raise FileNotFoundError(
            "No existe la carpeta de facturas: "
            f"{RUTA_FACTURAS}"
        )

    if not RUTA_FACTURAS.is_dir():
        raise NotADirectoryError(
            "La ruta de facturas no es una carpeta: "
            f"{RUTA_FACTURAS}"
        )


def normalizar_texto(
    texto: str,
) -> str:
    """
    Convierte el texto a mayúsculas y elimina acentos.
    """

    texto_normalizado = unicodedata.normalize(
        "NFKD",
        texto,
    )

    texto_sin_acentos = "".join(
        caracter
        for caracter in texto_normalizado
        if not unicodedata.combining(
            caracter
        )
    )

    return texto_sin_acentos.upper().strip()


def interpretar_ano(
    texto_ano: str,
) -> int | None:
    """
    Convierte años de dos o cuatro cifras.

    Ejemplos:
    26 -> 2026
    2027 -> 2027
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
    Interpreta nombres de carpetas mensuales.

    Ejemplos válidos:
    JUNY 26
    JULIOL 2026
    AGOST-26
    ENERO 27
    DICIEMBRE_2035
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
            mes_encontrado = (
                MESES_RECONOCIDOS[palabra]
            )
            break

    for palabra in palabras:
        if re.fullmatch(
            r"\d{2}|\d{4}",
            palabra,
        ):
            ano_posible = interpretar_ano(
                palabra
            )

            if ano_posible is not None:
                ano_encontrado = ano_posible
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
    Devuelve todas las carpetas mensuales desde junio de 2026
    en adelante, sin límite de fecha final.
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
            logger.info(
                "Carpeta anterior al inicio, ignorada | "
                "Carpeta: %s | Fecha: %s",
                carpeta.name,
                fecha_carpeta.isoformat(),
            )
            continue

        carpetas_validas.append(
            (
                fecha_carpeta,
                carpeta,
            )
        )

    carpetas_validas.sort(
        key=lambda elemento: (
            elemento[0],
            elemento[1].name.upper(),
        )
    )

    return [
        carpeta
        for _, carpeta in carpetas_validas
    ]


def obtener_facturas_pdf() -> list[Path]:
    """
    Localiza todos los PDF desde junio de 2026.

    Recorre las carpetas de las decenas y cualquier
    otra subcarpeta existente dentro del mes.
    """

    facturas: list[Path] = []

    carpetas_mensuales = (
        obtener_carpetas_mensuales_validas()
    )

    for carpeta_mes in carpetas_mensuales:
        for archivo in carpeta_mes.rglob("*"):
            if (
                archivo.is_file()
                and archivo.suffix.lower()
                == ".pdf"
            ):
                facturas.append(
                    archivo
                )

    facturas.sort(
        key=lambda archivo: str(
            archivo
        ).lower()
    )

    return facturas


def obtener_conexion_indice() -> sqlite3.Connection:
    """
    Abre el índice local utilizado para no volver
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
    Obtiene el registro local correspondiente a un PDF.
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
        (
            ruta_relativa,
        ),
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
    Crea o actualiza el registro local de un PDF.
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
            fecha_modificacion_ns =
                excluded.fecha_modificacion_ns,
            archivo_hash =
                excluded.archivo_hash,
            estado =
                excluded.estado,
            ultimo_error =
                excluded.ultimo_error,
            fecha_actualizacion =
                excluded.fecha_actualizacion
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
    Comprueba si el archivo conserva el mismo tamaño
    y la misma fecha de modificación.
    """

    if registro is None:
        return False

    return (
        int(
            registro["tamano"]
        ) == tamano
        and int(
            registro[
                "fecha_modificacion_ns"
            ]
        ) == fecha_modificacion_ns
    )


def obtener_hashes_documentos_supabase() -> set[str]:
    """
    Descarga una sola vez todos los hashes de los PDF
    registrados en documentos_facturas.

    Usa paginación para admitir miles de documentos.
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
            .table(TABLA_DOCUMENTOS)
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

        if len(
            filas
        ) < TAMANO_PAGINA_SUPABASE:
            break

        inicio += TAMANO_PAGINA_SUPABASE

    return hashes


def calcular_hash_archivo(
    ruta_archivo: Path,
) -> str:
    """
    Calcula el hash SHA-256 del PDF.
    """

    calculador = hashlib.sha256()

    with ruta_archivo.open(
        "rb"
    ) as archivo:
        while True:
            bloque = archivo.read(
                1024 * 1024
            )

            if not bloque:
                break

            calculador.update(
                bloque
            )

    return calculador.hexdigest()


def validar_pdf_nuevo(
    ruta_pdf: Path,
) -> None:
    """
    Valida únicamente archivos nuevos o modificados.
    """

    if not ruta_pdf.exists():
        raise FileNotFoundError(
            "El archivo no existe: "
            f"{ruta_pdf}"
        )

    if not ruta_pdf.is_file():
        raise ValueError(
            "La ruta no corresponde a un archivo: "
            f"{ruta_pdf}"
        )

    tamano_inicial = (
        ruta_pdf.stat().st_size
    )

    if tamano_inicial <= 0:
        raise ValueError(
            "El archivo PDF está vacío."
        )

    time.sleep(1)

    tamano_final = (
        ruta_pdf.stat().st_size
    )

    if tamano_inicial != tamano_final:
        raise RuntimeError(
            "El archivo todavía se está "
            "sincronizando o modificando."
        )

    with ruta_pdf.open(
        "rb"
    ) as archivo:
        cabecera = archivo.read(5)

    if cabecera != b"%PDF-":
        raise ValueError(
            "El archivo no contiene una "
            "cabecera PDF válida."
        )


def normalizar_nombre_storage(
    texto: str,
) -> str:
    """
    Genera nombres seguros para Supabase Storage.
    """

    texto_normalizado = unicodedata.normalize(
        "NFKD",
        texto,
    )

    texto_sin_acentos = "".join(
        caracter
        for caracter in texto_normalizado
        if not unicodedata.combining(
            caracter
        )
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
    ).strip(
        "._-"
    )

    return texto_limpio or "archivo"


def crear_ruta_storage(
    ruta_pdf: Path,
    archivo_hash: str,
) -> str:
    """
    Crea la ruta del PDF dentro del bucket privado.
    """

    ruta_relativa = ruta_pdf.relative_to(
        RUTA_FACTURAS
    )

    carpetas = [
        normalizar_nombre_storage(
            parte
        )
        for parte in ruta_relativa.parts[:-1]
    ]

    nombre_archivo = (
        normalizar_nombre_storage(
            ruta_pdf.stem
        )
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
    Obtiene el nombre de un archivo devuelto por Storage.
    """

    if isinstance(
        elemento,
        dict,
    ):
        nombre = elemento.get(
            "name"
        )
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
    cliente: Any,
    ruta_storage: str,
) -> bool:
    """
    Comprueba si un PDF ya existe en Storage.
    """

    ruta = PurePosixPath(
        ruta_storage
    )

    respuesta = (
        cliente
        .storage
        .from_(BUCKET_FACTURAS)
        .list(
            path=str(
                ruta.parent
            ),
            options={
                "search": ruta.name,
                "limit": 10,
            },
        )
    )

    return any(
        obtener_nombre_storage(
            elemento
        ) == ruta.name
        for elemento in respuesta
    )


def subir_pdf_storage(
    cliente: Any,
    ruta_pdf: Path,
    ruta_storage: str,
) -> None:
    """
    Sube el PDF al bucket privado facturas-pdf.
    """

    tipo_mime = (
        mimetypes.guess_type(
            ruta_pdf.name
        )[0]
        or "application/pdf"
    )

    with ruta_pdf.open(
        "rb"
    ) as archivo:
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


def registrar_documento_factura(
    cliente: Any,
    ruta_pdf: Path,
    ruta_storage: str,
    archivo_hash: str,
) -> None:
    """
    Registra el PDF físico en documentos_facturas.

    Todavía no crea facturas económicas.
    La lectura mediante IA se realizará en otro proceso.
    """

    datos = {
        "farmacia": NOMBRE_FARMACIA,
        "archivo_nombre": ruta_pdf.name,
        "archivo_ruta": ruta_storage,
        "archivo_hash": archivo_hash,
        "estado_lectura": "PENDIENTE",
        "requiere_revision": False,
        "datos_extraidos": {},
        "necesita_lectura_visual": False,
        "intentos_lectura": 0,
    }

    (
        cliente
        .table(TABLA_DOCUMENTOS)
        .insert(datos)
        .execute()
    )


def es_error_reintentable(
    error: Exception,
) -> bool:
    """
    Identifica errores temporales que pueden resolverse
    repitiendo la operación.
    """

    mensaje = str(
        error
    ).lower()

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


def importar_documento_nuevo(
    cliente: Any,
    conexion_indice: sqlite3.Connection,
    ruta_pdf: Path,
    ruta_relativa: str,
    tamano: int,
    fecha_modificacion_ns: int,
    archivo_hash: str,
) -> tuple[str, int, str | None]:
    """
    Sube y registra un documento nuevo.

    Realiza hasta tres intentos ante errores temporales.
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

                logger.info(
                    "PDF subido a Storage | "
                    "Archivo: %s | Ruta: %s",
                    ruta_relativa,
                    ruta_storage,
                )

            else:
                logger.warning(
                    "PDF ya existente en Storage "
                    "sin registro localizado | "
                    "Archivo: %s | Ruta: %s",
                    ruta_relativa,
                    ruta_storage,
                )

            registrar_documento_factura(
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
                "Documento importado | "
                "Archivo: %s | Intento: %s",
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
                "Error importando documento | "
                "Archivo: %s | "
                "Intento: %s/%s | "
                "Error: %s",
                ruta_relativa,
                intento,
                MAXIMO_INTENTOS,
                error,
            )

            if (
                not es_error_reintentable(
                    error
                )
                or intento
                == MAXIMO_INTENTOS
            ):
                break

            segundos = ESPERAS_REINTENTO[
                intento - 1
            ]

            logger.warning(
                "Documento pendiente de reintento | "
                "Archivo: %s | "
                "Próximo intento: %s/%s | "
                "Espera: %s segundos",
                ruta_relativa,
                intento + 1,
                MAXIMO_INTENTOS,
                segundos,
            )

            time.sleep(
                segundos
            )

    mensaje_error = (
        str(
            ultimo_error
        )
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

    logger.error(
        "Documento pendiente para otra ejecución | "
        "Archivo: %s | Error: %s",
        ruta_relativa,
        mensaje_error,
    )

    return (
        "ERROR",
        MAXIMO_INTENTOS,
        mensaje_error,
    )


def importar_facturas() -> None:
    """
    Importación incremental optimizada de PDF.

    Los archivos conocidos y sin cambios se omiten mediante
    el índice local.

    Los PDF nuevos se registran en documentos_facturas.

    Esta función no ejecuta todavía la lectura mediante IA
    ni crea filas en la nueva tabla facturas.
    """

    inicio_proceso = time.monotonic()

    validar_configuracion()

    logger.info(
        "Inicio de importación de documentos | "
        "Farmacia: %s | "
        "Ruta: %s | "
        "Fecha mínima: %s | "
        "Tabla: %s",
        NOMBRE_FARMACIA,
        RUTA_FACTURAS,
        FECHA_INICIO_IMPORTACION.isoformat(),
        TABLA_DOCUMENTOS,
    )

    conexion_indice = obtener_conexion_indice()
    cliente = obtener_cliente_supabase()

    try:
        hashes_supabase = (
            obtener_hashes_documentos_supabase()
        )

        facturas_pdf = obtener_facturas_pdf()
        total = len(
            facturas_pdf
        )

        print()
        print(
            "IMPORTACION DE DOCUMENTOS DE FACTURAS"
        )
        print(
            "------------------------------------"
        )
        print(
            f"Tabla de destino: {TABLA_DOCUMENTOS}"
        )
        print(
            f"PDF detectados: {total}"
        )
        print(
            "Documentos únicos registrados "
            f"en Supabase: {len(hashes_supabase)}"
        )
        print()

        omitidos_indice = 0
        existentes_supabase = 0
        importados = 0
        recuperados = 0
        modificados = 0
        errores = 0

        archivos_error: list[
            tuple[str, str]
        ] = []

        for posicion, ruta_pdf in enumerate(
            facturas_pdf,
            start=1,
        ):
            ruta_relativa = str(
                ruta_pdf.relative_to(
                    RUTA_FACTURAS
                )
            )

            datos_archivo = ruta_pdf.stat()

            tamano = (
                datos_archivo.st_size
            )

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
                and registro["estado"]
                == "IMPORTADA"
                and registro["archivo_hash"]
                in hashes_supabase
            ):
                omitidos_indice += 1
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
                    modificados += 1

                    logger.warning(
                        "Archivo modificado desde "
                        "la última ejecución | "
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
                        "  Documento ya registrado. "
                        "Índice local actualizado."
                    )

                    continue

                estado, intentos, error = (
                    importar_documento_nuevo(
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
                    importados += 1

                    hashes_supabase.add(
                        archivo_hash
                    )

                    if intentos > 1:
                        recuperados += 1

                    print(
                        "  Documento importado correctamente."
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

                mensaje_error = str(
                    error
                )

                hash_anterior = None

                if registro is not None:
                    hash_anterior = registro[
                        "archivo_hash"
                    ]

                guardar_registro_indice(
                    conexion_indice,
                    ruta_relativa,
                    tamano,
                    fecha_modificacion_ns,
                    hash_anterior,
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
            "Importación de documentos finalizada | "
            "Detectados: %s | "
            "Omitidos por índice: %s | "
            "Existentes añadidos al índice: %s | "
            "Importados: %s | "
            "Modificados: %s | "
            "Errores: %s | "
            "Duración: %.2f segundos",
            total,
            omitidos_indice,
            existentes_supabase,
            importados,
            modificados,
            errores,
            duracion,
        )

        print()
        print(
            "IMPORTACION FINALIZADA"
        )
        print(
            "----------------------"
        )
        print(
            f"PDF detectados: {total}"
        )
        print(
            "Omitidos sin abrir: "
            f"{omitidos_indice}"
        )
        print(
            "Existentes añadidos al índice: "
            f"{existentes_supabase}"
        )
        print(
            "Documentos nuevos importados: "
            f"{importados}"
        )
        print(
            "Recuperados tras reintento: "
            f"{recuperados}"
        )
        print(
            "Archivos modificados: "
            f"{modificados}"
        )
        print(
            f"Errores pendientes: {errores}"
        )
        print(
            f"Duración: {duracion:.1f} segundos"
        )

        if archivos_error:
            print()
            print(
                "ARCHIVOS CON ERROR"
            )
            print(
                "------------------"
            )

            for archivo, error in archivos_error:
                print(
                    f"- {archivo}"
                )
                print(
                    f"  Error: {error}"
                )

    finally:
        conexion_indice.close()


if __name__ == "__main__":
    importar_facturas()