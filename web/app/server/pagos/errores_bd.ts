/**
 * H6-REAL: errores de las marcas de pago y de la forma de pago por proveedor, traducidos a un mensaje llano. Puro (sin
 * pg): lo usan las rutas (FIXTURES y REAL), el adaptador REAL y las pruebas. Nunca se muestra el texto técnico de la BD
 * ni se reintenta solo: la transacción ya está deshecha (ROLLBACK) cuando el error llega a Marc.
 *
 * Códigos:
 *  - Reglas de la web (antes de escribir; también los devuelve el almacén de FIXTURES): YA_PAGADO, FORMA_SIN_CIF,
 *    NO_DOMICILIADO_PREVISTO, VENCIMIENTO_*, MARCA_NO_ENCONTRADA, MARCA_YA_ANULADA, CIF_NO_ENCONTRADO, SIN_CAMBIOS,
 *    ESTADO_CAMBIADO, CREDENCIAL_PAGOS_AUSENTE.
 *  - Triggers de la migración 35 (P0001, el mensaje empieza por el código): AUTOR_AUSENTE, SOLO_ANULAR,
 *    FACTURA_NO_ENCONTRADA, FARMACIA_DISTINTA_DE_LA_FACTURA, FARMACIA_NO_HABILITADA, VENCIMIENTO_NO_ENCONTRADO,
 *    VENCIMIENTO_SIN_FECHA, VENCIMIENTO_SIN_IMPORTE, FECHA_PAGO_FUTURA, DOMICILIADO_NO_VALIDO.
 *  - PostgreSQL: 23505 (una vigente por clave), 23514 (check), 42501 (permiso; con «row-level security», RLS),
 *    57014 / 25P03 (tiempo), 53300 (conexiones) y errores de red.
 *
 * Solo sintaxis TypeScript borrable.
 */

export class ErrorPagosBd extends Error {
  codigo: CodigoErrorPagos;
  http: number;
  mensaje: string;
  constructor(codigo: CodigoErrorPagos, http: number, mensaje: string) {
    super(`${codigo}: ${mensaje}`);
    this.codigo = codigo;
    this.http = http;
    this.mensaje = mensaje;
  }
}

const NADA = 'No se ha guardado nada.';
const NINGUNO = 'No se ha marcado ninguno.';
export const MENSAJES_PAGOS = {
  // --- Reglas de la web --------------------------------------------------------------------------------------------
  VENCIMIENTO_NO_ENCONTRADO: { http: 404, mensaje: `Algún vencimiento ya no existe o no es de PIO. Pulsa Actualizar. ${NINGUNO}` },
  VENCIMIENTO_SIN_FECHA: { http: 409, mensaje: `Algún vencimiento no tiene fecha de vencimiento: no se puede marcar hasta que la tenga. ${NINGUNO}` },
  VENCIMIENTO_SIN_IMPORTE: { http: 409, mensaje: `Algún vencimiento no tiene importe (importe pendiente): no se puede marcar hasta que se complete. ${NINGUNO}` },
  YA_PAGADO: { http: 409, mensaje: `Algún vencimiento ya tiene una marca de pago (también las «a revisar»: anúlala antes). ${NINGUNO}` },
  NO_DOMICILIADO_PREVISTO: { http: 409, mensaje: 'Solo se confirman domiciliados ya vencidos y sin marca; la fecha de pago es la de vencimiento. No se ha confirmado ninguno.' },
  FORMA_SIN_CIF: { http: 400, mensaje: 'Alguna factura no tiene CIF: elige la forma de pago.' },
  MARCA_NO_ENCONTRADA: { http: 404, mensaje: 'Esa marca de pago no existe.' },
  MARCA_YA_ANULADA: { http: 409, mensaje: 'Esa marca de pago ya está anulada.' },
  CIF_NO_ENCONTRADO: { http: 404, mensaje: 'Ese CIF no aparece en los vencimientos de PIO.' },
  SIN_CAMBIOS: { http: 409, mensaje: 'Ese proveedor ya tiene esa forma de pago.' },
  ESTADO_CAMBIADO: { http: 409, mensaje: `Otro cambio se ha guardado antes. Pulsa Actualizar y vuelve a intentarlo. ${NADA}` },
  CREDENCIAL_PAGOS_AUSENTE: { http: 503, mensaje: 'Falta configurar la credencial de pagos: la pantalla funciona en solo lectura.' },
  // --- Triggers de la migración 35 -------------------------------------------------------------------------------------
  AUTOR_AUSENTE: { http: 500, mensaje: `La base de datos exige el autor del cambio y no ha llegado. ${NADA}` },
  SOLO_ANULAR: { http: 409, mensaje: `La base de datos solo permite anular una marca o una forma vigente; nada más se puede cambiar. ${NADA}` },
  FACTURA_NO_ENCONTRADA: { http: 404, mensaje: `La factura de ese vencimiento ya no existe. Pulsa Actualizar. ${NADA}` },
  FARMACIA_DISTINTA_DE_LA_FACTURA: { http: 409, mensaje: `La marca no es de la misma farmacia que la factura. ${NADA}` },
  FARMACIA_NO_HABILITADA: { http: 403, mensaje: `Esa farmacia no está habilitada para marcar pagos (solo PIO). ${NADA}` },
  FECHA_PAGO_FUTURA: { http: 400, mensaje: `La fecha de pago no puede ser posterior a hoy. ${NADA}` },
  DOMICILIADO_NO_VALIDO: { http: 409, mensaje: `Un domiciliado solo se confirma si ya ha vencido, con forma domiciliación y fecha de pago igual a la de vencimiento. ${NADA}` },
  // --- PostgreSQL --------------------------------------------------------------------------------------------------
  DUPLICADO: { http: 409, mensaje: `Ya hay una marca vigente para ese vencimiento o una forma vigente para ese CIF (otro cambio se ha guardado antes). Pulsa Actualizar. ${NADA}` },
  REGLA_TABLA: { http: 400, mensaje: `La base de datos ha rechazado los datos: no cumplen sus reglas (forma, origen, CIF o fechas). ${NADA}` },
  PERMISO_DENEGADO: { http: 403, mensaje: `La base de datos no permite este cambio a la web (permiso denegado). ${NADA}` },
  RLS_DENEGADO: { http: 403, mensaje: `La base de datos no permite ese registro para esa farmacia (política de seguridad). ${NADA}` },
  TIEMPO_AGOTADO: { http: 504, mensaje: `La operación ha tardado demasiado y la base de datos la ha cancelado. ${NADA}` },
  SIN_CONEXIONES: { http: 503, mensaje: 'La base de datos tiene ocupadas todas las conexiones permitidas. Espera un momento y vuelve a intentarlo.' },
  SIN_CONEXION: { http: 503, mensaje: 'No se ha podido conectar con la base de datos de pagos. Comprueba la conexión y vuelve a intentarlo.' },
  ERROR_BD: { http: 500, mensaje: `Error de la base de datos. ${NADA}` },
} as const satisfies Record<string, { http: number; mensaje: string }>;
export type CodigoErrorPagos = keyof typeof MENSAJES_PAGOS;

export const errorPagos = (codigo: CodigoErrorPagos) => new ErrorPagosBd(codigo, MENSAJES_PAGOS[codigo].http, MENSAJES_PAGOS[codigo].mensaje);

/** Códigos de los triggers (P0001): el mensaje de la BD empieza por uno de ellos. */
export const CODIGOS_TRIGGER = [
  'AUTOR_AUSENTE', 'SOLO_ANULAR', 'FACTURA_NO_ENCONTRADA', 'FARMACIA_DISTINTA_DE_LA_FACTURA', 'FARMACIA_NO_HABILITADA',
  'VENCIMIENTO_NO_ENCONTRADO', 'VENCIMIENTO_SIN_FECHA', 'VENCIMIENTO_SIN_IMPORTE', 'FECHA_PAGO_FUTURA', 'DOMICILIADO_NO_VALIDO',
] as const satisfies readonly CodigoErrorPagos[];

const POR_SQLSTATE: Readonly<Record<string, CodigoErrorPagos>> = {
  '23505': 'DUPLICADO', '23514': 'REGLA_TABLA', '42501': 'PERMISO_DENEGADO',
  '57014': 'TIEMPO_AGOTADO', '25P03': 'TIEMPO_AGOTADO', '53300': 'SIN_CONEXIONES',
};
const RED = new Set(['ECONNREFUSED', 'ENOTFOUND', 'ETIMEDOUT', 'ECONNRESET', 'EAI_AGAIN', 'EHOSTUNREACH']);

/** Traduce cualquier error (pg o propio) a ErrorPagosBd: código, HTTP y mensaje llano. Nunca expone SQL ni datos. */
export function traducirErrorPagos(e: unknown): ErrorPagosBd {
  if (e instanceof ErrorPagosBd) return e;
  const code = typeof (e as { code?: unknown })?.code === 'string' ? (e as { code: string }).code : '';
  const msg = e instanceof Error ? e.message : String(e);
  if (code === 'P0001') {
    // El código va al principio («VENCIMIENTO_SIN_IMPORTE» o «VENCIMIENTO_SIN_IMPORTE: …»); se elige el más largo.
    const k = [...CODIGOS_TRIGGER].sort((a, b) => b.length - a.length).find((c) => msg === c || msg.startsWith(`${c}:`) || msg.startsWith(`${c} `));
    return errorPagos(k ?? 'ERROR_BD');
  }
  if (code === '42501' && /row-level security/i.test(msg)) return errorPagos('RLS_DENEGADO');
  if (POR_SQLSTATE[code]) return errorPagos(POR_SQLSTATE[code]);
  if (RED.has(code) || /timeout exceeded when trying to connect|Connection terminated/i.test(msg)) return errorPagos('SIN_CONEXION');
  return errorPagos('ERROR_BD');
}
