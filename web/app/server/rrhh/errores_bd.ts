/**
 * TA-REAL: errores de la base de datos del módulo Trabajadores traducidos a un mensaje llano. Puro (sin pg): lo usan
 * el adaptador RRHH_REAL, las rutas y las pruebas. Nunca se reintenta solo: el error llega a Marc tal cual, con la
 * transacción ya deshecha (ROLLBACK).
 *
 * Códigos (migración 31 y PostgreSQL):
 *  - P0001 AUTOR_AUSENTE / FARMACIA_NO_HABILITADA_EN_MODULO / EVENTO_FUERA_DEL_ALTA (triggers del módulo).
 *  - 42501 permiso denegado; 23505 duplicado; 23514 regla de la tabla (check); 23503 registro relacionado ausente.
 *  - 57014 consulta cancelada (statement_timeout 60 s) / 25P03 transacción inactiva cancelada (60 s).
 *  - 53300 demasiadas conexiones (el rol admite 5).
 *
 * Solo sintaxis TypeScript borrable.
 */

export class ErrorRrhhBd extends Error {
  codigo: string;
  http: number;
  mensaje: string;
  constructor(codigo: string, http: number, mensaje: string) {
    super(`${codigo}: ${mensaje}`);
    this.codigo = codigo;
    this.http = http;
    this.mensaje = mensaje;
  }
}

const NADA = 'No se ha guardado nada.';
export const MENSAJES_BD = {
  AUTOR_AUSENTE: { http: 500, mensaje: `La base de datos exige el autor del cambio y no ha llegado. ${NADA}` },
  FARMACIA_NO_HABILITADA_EN_MODULO: { http: 403, mensaje: `Esa farmacia no está habilitada en el módulo de Trabajadores. ${NADA}` },
  EVENTO_FUERA_DEL_ALTA: { http: 409, mensaje: `Ese día está fuera del alta o la baja de la persona. ${NADA}` },
  PERMISO_DENEGADO: { http: 403, mensaje: `La base de datos no permite este cambio a la web (permiso denegado). ${NADA}` },
  DUPLICADO: { http: 409, mensaje: `Ya existe un registro igual (por ejemplo, otra ficha con el mismo nombre en esa farmacia). ${NADA}` },
  REGLA_TABLA: { http: 400, mensaje: `La base de datos ha rechazado los datos: no cumplen sus reglas (horas, fechas o valores). ${NADA}` },
  REGISTRO_RELACIONADO: { http: 409, mensaje: `Falta el registro relacionado (la ficha no existe o es de otra farmacia). ${NADA}` },
  TIEMPO_AGOTADO: { http: 504, mensaje: `La operación ha tardado más de 60 s y la base de datos la ha cancelado. ${NADA} Prueba con un periodo más corto.` },
  SIN_CONEXIONES: { http: 503, mensaje: 'La base de datos tiene ocupadas todas las conexiones permitidas. Espera un momento y vuelve a intentarlo.' },
  SIN_CONEXION: { http: 503, mensaje: 'No se ha podido conectar con la base de datos de Trabajadores. Comprueba la conexión y vuelve a intentarlo.' },
  ERROR_BD: { http: 500, mensaje: `Error de la base de datos. ${NADA}` },
} as const satisfies Record<string, { http: number; mensaje: string }>;
export type CodigoErrorBd = keyof typeof MENSAJES_BD;

const POR_SQLSTATE: Readonly<Record<string, CodigoErrorBd>> = {
  '42501': 'PERMISO_DENEGADO', '23505': 'DUPLICADO', '23514': 'REGLA_TABLA', '23503': 'REGISTRO_RELACIONADO',
  '57014': 'TIEMPO_AGOTADO', '25P03': 'TIEMPO_AGOTADO', '53300': 'SIN_CONEXIONES',
};
const RED = new Set(['ECONNREFUSED', 'ENOTFOUND', 'ETIMEDOUT', 'ECONNRESET', 'EAI_AGAIN', 'EHOSTUNREACH']);

export const errorBd = (codigo: CodigoErrorBd) => new ErrorRrhhBd(codigo, MENSAJES_BD[codigo].http, MENSAJES_BD[codigo].mensaje);

/** Traduce cualquier error de pg a ErrorRrhhBd (código propio, HTTP y mensaje llano). Nunca expone datos ni SQL. */
export function traducirErrorBd(e: unknown): ErrorRrhhBd {
  if (e instanceof ErrorRrhhBd) return e;
  const code = typeof (e as { code?: unknown })?.code === 'string' ? (e as { code: string }).code : '';
  const msg = e instanceof Error ? e.message : String(e);
  if (code === 'P0001') {
    for (const k of ['AUTOR_AUSENTE', 'FARMACIA_NO_HABILITADA_EN_MODULO', 'EVENTO_FUERA_DEL_ALTA'] as const) if (msg.startsWith(k)) return errorBd(k);
    return errorBd('ERROR_BD');
  }
  if (POR_SQLSTATE[code]) return errorBd(POR_SQLSTATE[code]);
  if (RED.has(code) || /timeout exceeded when trying to connect|Connection terminated/i.test(msg)) return errorBd('SIN_CONEXION');
  return errorBd('ERROR_BD');
}
