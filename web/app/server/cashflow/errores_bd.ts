/**
 * H7-AP1: errores de los apuntes manuales de Cashflow (migración 40), traducidos a un mensaje llano. Puro (sin pg): lo
 * usan el front (validación en pantalla), las rutas (FIXTURES y REAL), el adaptador REAL y las pruebas. Nunca se muestra
 * el texto técnico de la BD ni se reintenta solo: la transacción ya está deshecha (ROLLBACK) cuando el error llega a Marc.
 *
 * Códigos:
 *  - Validaciones de la BD (docs/referencia/ESQUEMA_CASHFLOW.md, P0001: el mensaje empieza por el código), todas:
 *    AUTOR_AUSENTE, CUENTA_NO_VALIDA, FARMACIA_NO_HABILITADA, SIN_IMPORTACION_VIGENTE, CATEGORIA_FUERA_DE_PLANTILLA,
 *    CONCEPTO_DESCONOCIDO, IMPORTE_NO_POSITIVO, FECHA_AUSENTE, SIN_SALDO_DE_BANCO, FECHA_NO_FUTURA, FRECUENCIA_NO_VALIDA,
 *    DIA_NO_VALIDO, INICIO_AUSENTE, FIN_ANTERIOR_A_INICIO, INICIO_NO_ES_OCURRENCIA, OCURRENCIA_NO_VALIDA,
 *    RECURRENTE_NO_ENCONTRADA, RECURRENTE_ANULADA, IMPORTE_EN_ANULACION_DE_OCURRENCIA, OCURRENCIA_SIN_RECURRENTE,
 *    SUSTITUCION_SOLO_AL_ANULAR, SUSTITUCION_INCOMPLETA, FACTURA_NO_ENCONTRADA, FARMACIA_DISTINTA_DE_LA_FACTURA,
 *    VENCIMIENTO_NO_ENCONTRADO, SOLO_ANULAR, MOTIVO_ANULACION_AUSENTE, BORRADO_NO_PERMITIDO.
 *  - Reglas de la web (antes de escribir; también los devuelve el almacén de FIXTURES): CREDENCIAL_CASHFLOW_AUSENTE,
 *    APUNTE_NO_ENCONTRADO, CONCEPTO_YA_EXISTE, CIF_YA_ASIGNADO, SUSTITUCION_NO_CANDIDATA, VENCIMIENTO_YA_SUSTITUYE.
 *  - PostgreSQL: 23505 (único), 23514 (check), 42501 (permiso; con «row-level security», RLS), 57014 / 25P03 (tiempo),
 *    53300 (conexiones) y errores de red.
 *
 * Solo sintaxis TypeScript borrable.
 */

export class ErrorCashflowBd extends Error {
  codigo: CodigoErrorCashflow;
  http: number;
  mensaje: string;
  constructor(codigo: CodigoErrorCashflow, http: number, mensaje: string) {
    super(`${codigo}: ${mensaje}`);
    this.codigo = codigo;
    this.http = http;
    this.mensaje = mensaje;
  }
}

const NADA = 'No se ha guardado nada.';
export const MENSAJE_FALTA_CREDENCIAL_CASHFLOW = 'Falta configurar la credencial de Cashflow: los apuntes manuales se ven, pero no se pueden crear ni anular.';

export const MENSAJES_CASHFLOW = {
  // --- Validaciones de la BD al dar de alta ------------------------------------------------------------------------
  AUTOR_AUSENTE: { http: 500, mensaje: `La base de datos exige el autor del cambio y no ha llegado. ${NADA}` },
  CUENTA_NO_VALIDA: { http: 400, mensaje: `La cuenta tiene que ser PIO o RITA. ${NADA}` },
  FARMACIA_NO_HABILITADA: { http: 403, mensaje: `Esa cuenta no está habilitada en el módulo Cashflow. ${NADA}` },
  SIN_IMPORTACION_VIGENTE: { http: 409, mensaje: `No hay ninguna importación vigente del Excel: sin ella no se pueden anotar apuntes. ${NADA}` },
  CATEGORIA_FUERA_DE_PLANTILLA: { http: 409, mensaje: `Esa categoría no está en el Excel vigente de esa cuenta. Pulsa Actualizar. ${NADA}` },
  CONCEPTO_DESCONOCIDO: { http: 409, mensaje: `Ese concepto no está en esa categoría (ni en el Excel vigente ni entre los conceptos nuevos). Elige uno o crea un concepto nuevo. ${NADA}` },
  IMPORTE_NO_POSITIVO: { http: 400, mensaje: `El importe tiene que ser mayor que 0 (el sentido, entrada o salida, lo da la categoría). ${NADA}` },
  FECHA_AUSENTE: { http: 400, mensaje: `Falta la fecha del apunte. ${NADA}` },
  SIN_SALDO_DE_BANCO: { http: 409, mensaje: `Esa cuenta no tiene ninguna decena con saldo de banco: no se sabe qué fechas son futuras. ${NADA}` },
  FECHA_NO_FUTURA: { http: 400, mensaje: `Solo fechas futuras: tienen que ser posteriores a la última decena con saldo de banco de la cuenta. ${NADA}` },
  FRECUENCIA_NO_VALIDA: { http: 400, mensaje: `La periodicidad tiene que ser mensual, trimestral o anual. ${NADA}` },
  DIA_NO_VALIDO: { http: 400, mensaje: `El día tiene que estar entre 1 y 31 (si el mes no lo tiene, cuenta el último día del mes). ${NADA}` },
  INICIO_AUSENTE: { http: 400, mensaje: `Falta la fecha «desde» del recurrente. ${NADA}` },
  FIN_ANTERIOR_A_INICIO: { http: 400, mensaje: `La fecha «hasta» no puede ser anterior a «desde». ${NADA}` },
  INICIO_NO_ES_OCURRENCIA: { http: 400, mensaje: `La fecha «desde» tiene que ser la primera ocurrencia: el día elegido de ese mes (o el último día, si el mes no lo tiene). ${NADA}` },
  OCURRENCIA_NO_VALIDA: { http: 409, mensaje: `Esa fecha no es una ocurrencia vigente del recurrente (o ya está anulada). Pulsa Actualizar. ${NADA}` },
  RECURRENTE_NO_ENCONTRADA: { http: 404, mensaje: `Ese recurrente ya no existe. Pulsa Actualizar. ${NADA}` },
  RECURRENTE_ANULADA: { http: 409, mensaje: `Ese recurrente ya está anulado. Pulsa Actualizar. ${NADA}` },
  IMPORTE_EN_ANULACION_DE_OCURRENCIA: { http: 400, mensaje: `Al anular una ocurrencia no se envía importe. ${NADA}` },
  OCURRENCIA_SIN_RECURRENTE: { http: 400, mensaje: `Para anular una ocurrencia hacen falta el recurrente y la fecha. ${NADA}` },
  SUSTITUCION_SOLO_AL_ANULAR: { http: 400, mensaje: `La sustitución por una factura solo se guarda al anular el apunte. ${NADA}` },
  SUSTITUCION_INCOMPLETA: { http: 400, mensaje: `Para sustituir hacen falta la factura y el vencimiento. ${NADA}` },
  FACTURA_NO_ENCONTRADA: { http: 404, mensaje: `Esa factura ya no existe. Pulsa Actualizar. ${NADA}` },
  FARMACIA_DISTINTA_DE_LA_FACTURA: { http: 409, mensaje: `La factura no es de la farmacia de la cuenta del apunte. ${NADA}` },
  VENCIMIENTO_NO_ENCONTRADO: { http: 404, mensaje: `Ese vencimiento ya no existe en la factura. Pulsa Actualizar. ${NADA}` },
  // --- Validaciones de la BD al anular -----------------------------------------------------------------------------
  SOLO_ANULAR: { http: 409, mensaje: `Solo se puede anular (y lo anulado no se reabre): para corregir, anula y crea otro. ${NADA}` },
  MOTIVO_ANULACION_AUSENTE: { http: 400, mensaje: `Escribe el motivo de la anulación. ${NADA}` },
  BORRADO_NO_PERMITIDO: { http: 405, mensaje: `Los apuntes no se borran nunca: se anulan. ${NADA}` },
  // --- Reglas de la web --------------------------------------------------------------------------------------------
  CREDENCIAL_CASHFLOW_AUSENTE: { http: 503, mensaje: MENSAJE_FALTA_CREDENCIAL_CASHFLOW },
  APUNTE_NO_ENCONTRADO: { http: 404, mensaje: `Ese apunte ya no existe. Pulsa Actualizar. ${NADA}` },
  CONCEPTO_YA_EXISTE: { http: 409, mensaje: `Ya hay un concepto con ese nombre en esa categoría: elígelo en la lista. ${NADA}` },
  CIF_YA_ASIGNADO: { http: 409, mensaje: `Ese CIF ya está en otro concepto de esa cuenta. ${NADA}` },
  SUSTITUCION_NO_CANDIDATA: { http: 409, mensaje: `Esa factura ya no coincide con el apunte (mismo concepto, misma decena o la siguiente, ±5 %). Pulsa Actualizar. ${NADA}` },
  VENCIMIENTO_YA_SUSTITUYE: { http: 409, mensaje: `Ese vencimiento ya sustituye a otro apunte. ${NADA}` },
  // --- PostgreSQL --------------------------------------------------------------------------------------------------
  DUPLICADO: { http: 409, mensaje: `Ya existe (un concepto con ese nombre o CIF, esa ocurrencia ya anulada o ese vencimiento ya usado): otro cambio se ha guardado antes. Pulsa Actualizar. ${NADA}` },
  REGLA_TABLA: { http: 400, mensaje: `La base de datos ha rechazado los datos: no cumplen sus reglas (largos, CIF, importe o fechas). ${NADA}` },
  PERMISO_DENEGADO: { http: 403, mensaje: `La base de datos no permite este cambio a la web (permiso denegado). ${NADA}` },
  RLS_DENEGADO: { http: 403, mensaje: `La base de datos no permite ese registro para esa cuenta (política de seguridad). ${NADA}` },
  TIEMPO_AGOTADO: { http: 504, mensaje: `La operación ha tardado demasiado y la base de datos la ha cancelado. ${NADA}` },
  SIN_CONEXIONES: { http: 503, mensaje: 'La base de datos tiene ocupadas todas las conexiones permitidas. Espera un momento y vuelve a intentarlo.' },
  SIN_CONEXION: { http: 503, mensaje: 'No se ha podido conectar con la base de datos de Cashflow. Comprueba la conexión y vuelve a intentarlo.' },
  ERROR_BD: { http: 500, mensaje: `Error de la base de datos. ${NADA}` },
} as const satisfies Record<string, { http: number; mensaje: string }>;
export type CodigoErrorCashflow = keyof typeof MENSAJES_CASHFLOW;

export const errorCashflow = (codigo: CodigoErrorCashflow) => new ErrorCashflowBd(codigo, MENSAJES_CASHFLOW[codigo].http, MENSAJES_CASHFLOW[codigo].mensaje);

/** Códigos de las validaciones de la BD (P0001; docs/referencia/ESQUEMA_CASHFLOW.md), en el orden del esquema. */
export const CODIGOS_BD_CASHFLOW = [
  'AUTOR_AUSENTE', 'CUENTA_NO_VALIDA', 'FARMACIA_NO_HABILITADA', 'SIN_IMPORTACION_VIGENTE', 'CATEGORIA_FUERA_DE_PLANTILLA',
  'CONCEPTO_DESCONOCIDO', 'IMPORTE_NO_POSITIVO', 'FECHA_AUSENTE', 'SIN_SALDO_DE_BANCO', 'FECHA_NO_FUTURA',
  'FRECUENCIA_NO_VALIDA', 'DIA_NO_VALIDO', 'INICIO_AUSENTE', 'FIN_ANTERIOR_A_INICIO', 'INICIO_NO_ES_OCURRENCIA',
  'OCURRENCIA_NO_VALIDA', 'RECURRENTE_NO_ENCONTRADA', 'RECURRENTE_ANULADA', 'IMPORTE_EN_ANULACION_DE_OCURRENCIA', 'OCURRENCIA_SIN_RECURRENTE',
  'SUSTITUCION_SOLO_AL_ANULAR', 'SUSTITUCION_INCOMPLETA', 'FACTURA_NO_ENCONTRADA', 'FARMACIA_DISTINTA_DE_LA_FACTURA', 'VENCIMIENTO_NO_ENCONTRADO',
  'SOLO_ANULAR', 'MOTIVO_ANULACION_AUSENTE', 'BORRADO_NO_PERMITIDO',
] as const satisfies readonly CodigoErrorCashflow[];

const POR_SQLSTATE: Readonly<Record<string, CodigoErrorCashflow>> = {
  '23505': 'DUPLICADO', '23514': 'REGLA_TABLA', '42501': 'PERMISO_DENEGADO',
  '57014': 'TIEMPO_AGOTADO', '25P03': 'TIEMPO_AGOTADO', '53300': 'SIN_CONEXIONES',
};
const RED = new Set(['ECONNREFUSED', 'ENOTFOUND', 'ETIMEDOUT', 'ECONNRESET', 'EAI_AGAIN', 'EHOSTUNREACH']);

/** Traduce cualquier error (pg o propio) a ErrorCashflowBd: código, HTTP y mensaje llano. Nunca expone SQL ni datos. */
export function traducirErrorCashflow(e: unknown): ErrorCashflowBd {
  if (e instanceof ErrorCashflowBd) return e;
  const code = typeof (e as { code?: unknown })?.code === 'string' ? (e as { code: string }).code : '';
  const msg = e instanceof Error ? e.message : String(e);
  if (code === 'P0001') {
    // El código va al principio («FECHA_NO_FUTURA» o «FECHA_NO_FUTURA: …»); se elige el más largo que encaje.
    const k = [...CODIGOS_BD_CASHFLOW].sort((a, b) => b.length - a.length).find((c) => msg === c || msg.startsWith(`${c}:`) || msg.startsWith(`${c} `));
    return errorCashflow(k ?? 'ERROR_BD');
  }
  if (code === '42501' && /row-level security/i.test(msg)) return errorCashflow('RLS_DENEGADO');
  if (POR_SQLSTATE[code]) return errorCashflow(POR_SQLSTATE[code]);
  if (RED.has(code) || /timeout exceeded when trying to connect|Connection terminated/i.test(msg)) return errorCashflow('SIN_CONEXION');
  return errorCashflow('ERROR_BD');
}
