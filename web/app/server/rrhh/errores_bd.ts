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
 * TA3-REAL (migración 34: guardias_semana, guardias_festivo, festivos):
 *  - P0001 PERSONA_NO_VALIDA:<id>:<fecha> y NO_ES_FESTIVO:<fecha> (triggers): mensaje llano con la fecha (dd/mm/aaaa),
 *    nunca el id ni el texto técnico.
 *  - 23514 por restricción: guardias_semana_*, guardias_festivo_*, festivos_*.
 *  - 23505 por índice: guardias_semana_lunes_unico, guardias_festivo_fecha_unico, festivos_unico.
 *  - 23503 en las tablas de guardias: persona de otra farmacia (FK (persona, farmacia)).
 *  - 42501 por RLS («row-level security»): mensaje propio, distinto del permiso denegado.
 * El nombre de la restricción sale de `constraint` (pg) o, si no viene, del texto del error; nunca se muestra.
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
  // TA3-REAL (migración 34)
  PERSONA_NO_VALIDA: { http: 409, mensaje: `Esa persona no es de esa farmacia o no está de alta ese día. ${NADA}` },
  NO_ES_FESTIVO: { http: 409, mensaje: `Ese día no es un festivo común de las dos farmacias. ${NADA}` },
  GUARDIA_SEMANA_REGLA: { http: 400, mensaje: `La guardia semanal no cumple las reglas: la semana empieza en lunes; PIO y RITA llevan persona de guardia, OTRA ninguna; el apoyo del sábado es opcional y otra persona. ${NADA}` },
  GUARDIA_FESTIVO_REGLA: { http: 400, mensaje: `La guardia del festivo no cumple las reglas: PIO y RITA llevan persona; OTRA, ninguna. ${NADA}` },
  FESTIVO_REGLA: { http: 400, mensaje: `El festivo no cumple las reglas: nombre de 1 a 100 caracteres y ámbito nacional, autonómico o local. ${NADA}` },
  GUARDIA_SEMANA_DUPLICADA: { http: 409, mensaje: `Esa semana ya tiene guardia (otro cambio se ha guardado antes). Actualiza y vuelve a intentarlo. ${NADA}` },
  GUARDIA_FESTIVO_DUPLICADA: { http: 409, mensaje: `Ese festivo ya tiene guardia (otro cambio se ha guardado antes). Actualiza y vuelve a intentarlo. ${NADA}` },
  FESTIVO_DUPLICADO: { http: 409, mensaje: `Ese día ya es festivo. ${NADA}` },
  PERSONA_OTRA_FARMACIA: { http: 409, mensaje: `Esa persona no es de la farmacia de guardia. ${NADA}` },
  RLS_DENEGADO: { http: 403, mensaje: `La base de datos no permite ese registro para esa farmacia (política de seguridad). ${NADA}` },
} as const satisfies Record<string, { http: number; mensaje: string }>;
export type CodigoErrorBd = keyof typeof MENSAJES_BD;

const POR_SQLSTATE: Readonly<Record<string, CodigoErrorBd>> = {
  '42501': 'PERMISO_DENEGADO', '23505': 'DUPLICADO', '23514': 'REGLA_TABLA', '23503': 'REGISTRO_RELACIONADO',
  '57014': 'TIEMPO_AGOTADO', '25P03': 'TIEMPO_AGOTADO', '53300': 'SIN_CONEXIONES',
};
const RED = new Set(['ECONNREFUSED', 'ENOTFOUND', 'ETIMEDOUT', 'ECONNRESET', 'EAI_AGAIN', 'EHOSTUNREACH']);

export const errorBd = (codigo: CodigoErrorBd) => new ErrorRrhhBd(codigo, MENSAJES_BD[codigo].http, MENSAJES_BD[codigo].mensaje);

/** 'YYYY-MM-DD' → 'dd/mm/aaaa'; cualquier otra cosa → null (no se muestra). */
const fechaLlana = (v: string | undefined) => (v && /^\d{4}-\d{2}-\d{2}$/.test(v) ? `${v.slice(8, 10)}/${v.slice(5, 7)}/${v.slice(0, 4)}` : null);

/** Nombre de la restricción: `constraint` de pg o, si falta, el que cita el texto («… constraint "x"»). */
function restriccion(e: unknown, msg: string): string {
  const c = (e as { constraint?: unknown })?.constraint;
  if (typeof c === 'string') return c;
  return /constraint "([a-z0-9_]+)"/i.exec(msg)?.[1] ?? '';
}

/** TA3-REAL: errores de las tablas de guardias y festivos (null si no es de ellas). */
function errorTa3(code: string, msg: string, nombre: string): ErrorRrhhBd | null {
  if (code === 'P0001') {
    const [k, , fecha] = msg.split(':');
    if (k === 'PERSONA_NO_VALIDA' || k === 'NO_ES_FESTIVO') {
      const e = errorBd(k);
      const f = fechaLlana(k === 'NO_ES_FESTIVO' ? msg.split(':')[1] : fecha);
      if (f === null) return e;
      const m = k === 'PERSONA_NO_VALIDA'
        ? `Esa persona no es de esa farmacia o no está de alta el ${f}. ${NADA}`
        : `El ${f} no es un festivo común de las dos farmacias. ${NADA}`;
      return new ErrorRrhhBd(k, e.http, m);
    }
    return null;
  }
  if (code === '23514') {
    if (nombre.startsWith('guardias_semana_')) return errorBd('GUARDIA_SEMANA_REGLA');
    if (nombre.startsWith('guardias_festivo_')) return errorBd('GUARDIA_FESTIVO_REGLA');
    if (nombre.startsWith('festivos_')) return errorBd('FESTIVO_REGLA');
  }
  if (code === '23505') {
    if (nombre === 'guardias_semana_lunes_unico') return errorBd('GUARDIA_SEMANA_DUPLICADA');
    if (nombre === 'guardias_festivo_fecha_unico') return errorBd('GUARDIA_FESTIVO_DUPLICADA');
    if (nombre === 'festivos_unico') return errorBd('FESTIVO_DUPLICADO');
  }
  if (code === '23503' && (nombre.startsWith('guardias_semana_') || nombre.startsWith('guardias_festivo_'))) return errorBd('PERSONA_OTRA_FARMACIA');
  if (code === '42501' && /row-level security/i.test(msg)) return errorBd('RLS_DENEGADO');
  return null;
}

/** Traduce cualquier error de pg a ErrorRrhhBd (código propio, HTTP y mensaje llano). Nunca expone datos ni SQL. */
export function traducirErrorBd(e: unknown): ErrorRrhhBd {
  if (e instanceof ErrorRrhhBd) return e;
  const code = typeof (e as { code?: unknown })?.code === 'string' ? (e as { code: string }).code : '';
  const msg = e instanceof Error ? e.message : String(e);
  const ta3 = errorTa3(code, msg, restriccion(e, msg));
  if (ta3) return ta3;
  if (code === 'P0001') {
    for (const k of ['AUTOR_AUSENTE', 'FARMACIA_NO_HABILITADA_EN_MODULO', 'EVENTO_FUERA_DEL_ALTA'] as const) if (msg.startsWith(k)) return errorBd(k);
    return errorBd('ERROR_BD');
  }
  if (POR_SQLSTATE[code]) return errorBd(POR_SQLSTATE[code]);
  if (RED.has(code) || /timeout exceeded when trying to connect|Connection terminated/i.test(msg)) return errorBd('SIN_CONEXION');
  return errorBd('ERROR_BD');
}
