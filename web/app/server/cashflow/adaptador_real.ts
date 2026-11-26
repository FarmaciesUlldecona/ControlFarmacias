/**
 * H7-AP1: adaptador REAL de la escritura de los apuntes manuales de Cashflow (migración 40, en producción desde el
 * 2026-11-26; docs/referencia/ESQUEMA_CASHFLOW.md). Solo lo ejecuta Pío (dev:real / check:real).
 *
 *  - Lectura: con cf_lectura, junto con el cashflow y en su misma transacción READ ONLY (server/adaptador_real.ts y
 *    lectura_real.ts: leerPrevisionesReal). Funciona aunque falte la credencial de Cashflow.
 *  - Escritura: credencial propia CF_CASHFLOW_USER y CF_CASHFLOW_PASSWORD en web/app/.env.web (gitignored; Code nunca la
 *    lee ni la crea); host, puerto, base y CA compartidos con cf_lectura. Rol cf_cashflow_web (por el pooler,
 *    cf_cashflow_web.<project_ref>), pool propio de 2 conexiones (el rol admite 5) y TLS con verificación de la CA. Sin
 *    credencial: solo lectura, con «Falta configurar la credencial de Cashflow» (CREDENCIAL_CASHFLOW_AUSENTE).
 *  - Una transacción por operación con set_config('cf.autor', <autor>, true) dentro. Ante cualquier error: ROLLBACK y
 *    mensaje llano (errores_bd.ts). Nunca se reintenta.
 *  - Nunca DELETE: anular (anulado = true + motivo_anulacion); editar = anular + insertar en la misma transacción.
 *
 * Solo sintaxis TypeScript borrable.
 */
import { isAbsolute, join } from 'node:path';
import pg from 'pg';
import { RUTA_CA_DEFECTO, leerCertificadoCA } from '../adaptador_real.ts';
import type { ClienteBd, PoolBd } from '../rrhh/adaptador_real.ts';
import { conceptoDeAlta, type AltaApunte, type ApunteCashflow, type RecurrenteCashflow, type TablaAnulable } from './apuntes.ts';
import { almacenSinEscritura, type AlmacenCashflowAsync, type ResultadoAlta, type Sustitucion } from './almacen.ts';
import { ErrorCashflowBd, MENSAJE_FALTA_CREDENCIAL_CASHFLOW, errorCashflow, traducirErrorCashflow } from './errores_bd.ts';
import { filaAApunte, filaAConcepto, filaARecurrente } from './lectura_real.ts';
import { SQL_ESCRITURA_APUNTES as SQL } from './sql_apuntes.ts';

// ---------------------------------------------------------------------------
// Configuración (credencial en .env.web; Code nunca la lee ni la crea)
// ---------------------------------------------------------------------------

export const VARIABLES_CASHFLOW = ['CF_CASHFLOW_USER', 'CF_CASHFLOW_PASSWORD'] as const;
const VARIABLES_COMPARTIDAS = ['CF_LECTURA_HOST', 'CF_LECTURA_PORT', 'CF_LECTURA_DB'] as const;
export const ROL_CASHFLOW = 'cf_cashflow_web';
export const MAX_CONEXIONES_CASHFLOW = 2;

export type ConfigCashflowBd = { ok: true; config: pg.PoolConfig } | { ok: false; codigo: string; mensaje: string };

const OID = { INT8: 20, NUMERIC: 1700, DATE: 1082, TIMESTAMP: 1114, TIMESTAMPTZ: 1184 };
const TIPOS_TEXTO = new Set<number>([OID.INT8, OID.NUMERIC, OID.DATE, OID.TIMESTAMP, OID.TIMESTAMPTZ]);
const tipos = {
  getTypeParser(oid: number, formato?: 'text' | 'binary') {
    if (TIPOS_TEXTO.has(oid)) return (v: string) => v;
    return pg.types.getTypeParser(oid, formato);
  },
};

/**
 * Configuración del pool de escritura. Falla cerrado: sin CF_CASHFLOW_USER / CF_CASHFLOW_PASSWORD →
 * CREDENCIAL_CASHFLOW_AUSENTE; usuario distinto de cf_cashflow_web (directo o del pooler) → no conecta; sin CA válida → no
 * conecta.
 */
export function configuracionCashflow(env: Record<string, string | undefined>, leerCA: (ruta: string) => string = leerCertificadoCA): ConfigCashflowBd {
  if (VARIABLES_CASHFLOW.some((v) => !env[v])) return { ok: false, codigo: 'CREDENCIAL_CASHFLOW_AUSENTE', mensaje: MENSAJE_FALTA_CREDENCIAL_CASHFLOW };
  const faltan = VARIABLES_COMPARTIDAS.filter((v) => !env[v]);
  if (faltan.length) return { ok: false, codigo: 'ENV_WEB_INCOMPLETO', mensaje: `Falta configurar la conexión (${faltan.join(', ')})` };
  const usuario = env.CF_CASHFLOW_USER as string;
  if (usuario !== ROL_CASHFLOW && !usuario.startsWith(`${ROL_CASHFLOW}.`)) {
    return { ok: false, codigo: 'USUARIO_NO_CF_CASHFLOW_WEB', mensaje: `La credencial de Cashflow debe ser del rol ${ROL_CASHFLOW}` };
  }
  const puerto = Number(env.CF_LECTURA_PORT);
  if (!Number.isInteger(puerto) || puerto <= 0 || puerto > 65535) return { ok: false, codigo: 'PUERTO_NO_VALIDO', mensaje: 'Puerto de la base de datos no válido' };
  const v = env.CF_LECTURA_CA;
  const rutaCA = !v ? RUTA_CA_DEFECTO : isAbsolute(v) ? v : join(import.meta.dirname, '..', '..', v);
  let ca: string;
  try { ca = leerCA(rutaCA); } catch (e) {
    return { ok: false, codigo: 'CERTIFICADO_CA', mensaje: `Certificado CA no válido: ${(e instanceof Error ? e.message : String(e)).split(':')[0]}` };
  }
  return {
    ok: true,
    config: {
      host: env.CF_LECTURA_HOST, port: puerto, database: env.CF_LECTURA_DB, user: usuario, password: env.CF_CASHFLOW_PASSWORD,
      ssl: { rejectUnauthorized: true, ca }, max: MAX_CONEXIONES_CASHFLOW, idleTimeoutMillis: 30_000, connectionTimeoutMillis: 10_000,
      application_name: 'cf_web_cashflow', types: tipos,
    },
  };
}

export function crearPoolCashflow(config: pg.PoolConfig): PoolBd {
  const pool = new pg.Pool(config);
  pool.on('error', (e) => console.warn(`Cashflow: conexión cerrada por la base de datos (${String((e as { code?: string }).code ?? '')})`));
  return {
    connect: async () => {
      const c = await pool.connect();
      return { query: (sql, params) => c.query(sql, params as unknown[]), release: (d) => c.release(d) };
    },
    end: () => pool.end(),
  };
}

// ---------------------------------------------------------------------------
// Almacén REAL
// ---------------------------------------------------------------------------

export type AlmacenCashflowReal = AlmacenCashflowAsync & {
  /** check:real: la credencial de Cashflow conecta y lee sus tablas (READ ONLY, sin escribir). Solo el recuento. */
  probarCredencial(): Promise<{ filas: number }>;
};

const importeTexto = (x: number) => x.toFixed(2);

export function crearAlmacenCashflowReal(o: { pool: PoolBd | null }): AlmacenCashflowReal {
  const { pool } = o;
  if (pool === null) {
    return { ...almacenSinEscritura(), probarCredencial: async () => { throw errorCashflow('CREDENCIAL_CASHFLOW_AUSENTE'); } };
  }

  async function conCliente<T>(trabajo: (c: ClienteBd) => Promise<T>): Promise<T> {
    let c: ClienteBd;
    try { c = await (pool as PoolBd).connect(); } catch (e) { throw traducirErrorCashflow(e); }
    let roto = false;
    try { return await trabajo(c); } catch (e) { roto = true; throw e; } finally { c.release(roto); }
  }
  /** Una transacción con el autor fijado DENTRO (set_config local); error → ROLLBACK, mensaje llano, sin reintento. */
  const escribir = <T>(autor: string, trabajo: (c: ClienteBd) => Promise<T>) => conCliente(async (c) => {
    if (autor.trim() === '' || autor.length > 60) throw errorCashflow('AUTOR_AUSENTE');
    try {
      await c.query('begin');
      await c.query(SQL.autor, [autor]);
      const r = await trabajo(c);
      await c.query('commit');
      return r;
    } catch (e) {
      try { await c.query('rollback'); } catch { /* conexión rota: se descarta */ }
      throw traducirErrorCashflow(e);
    }
  });
  const una = async (c: ClienteBd, sql: string, params: unknown[]) => (await c.query(sql, params)).rows[0];

  async function darDeAlta(c: ClienteBd, a: AltaApunte): Promise<ResultadoAlta> {
    const concepto = a.concepto_nuevo === null ? null
      : filaAConcepto(await una(c, SQL.insertarConcepto, [a.cuenta, a.categoria, a.concepto_nuevo.nombre, a.concepto_nuevo.proveedor_cif]));
    const nombre = conceptoDeAlta(a);
    if (a.tipo === 'SUELTO') {
      const f = await una(c, SQL.insertarApunte, [a.cuenta, a.categoria, nombre, a.fecha, a.importe === null ? null : importeTexto(a.importe), a.nota]);
      return { concepto, apunte: filaAApunte(f), recurrente: null };
    }
    const f = await una(c, SQL.insertarRecurrente, [a.cuenta, a.categoria, nombre, a.importe === null ? null : importeTexto(a.importe), a.nota, a.frecuencia, a.dia, a.inicio, a.fin]);
    return { concepto, apunte: null, recurrente: filaARecurrente(f) };
  }
  /** UPDATE … where not anulado returning; sin fila: no existe o ya estaba anulada (nunca se reabre). */
  async function anularFila(c: ClienteBd, tabla: TablaAnulable, id: string, motivo: string, sustitucion: Sustitucion | null = null): Promise<ApunteCashflow | RecurrenteCashflow> {
    if (motivo.trim() === '') throw errorCashflow('MOTIVO_ANULACION_AUSENTE');
    if (tabla === 'APUNTE') {
      const f = sustitucion === null
        ? await una(c, SQL.anularApunte, [id, motivo.trim()])
        : await una(c, SQL.sustituirApunte, [id, motivo.trim(), sustitucion.factura_id, sustitucion.vencimiento_orden]);
      if (f) return filaAApunte(f);
      const previa = await una(c, SQL.apuntePorId, [id]);
      throw errorCashflow(!previa || previa.recurrente_id !== null ? 'APUNTE_NO_ENCONTRADO' : 'SOLO_ANULAR');
    }
    const f = await una(c, SQL.anularRecurrente, [id, motivo.trim()]);
    if (f) return filaARecurrente(f);
    const previa = await una(c, SQL.recurrentePorId, [id]);
    throw errorCashflow(previa ? 'RECURRENTE_ANULADA' : 'RECURRENTE_NO_ENCONTRADA');
  }

  return {
    sinEscritura: null,
    alta: (a, autor) => escribir(autor, (c) => darDeAlta(c, a)),
    editar: (anterior, motivo, a, autor) => escribir(autor, async (c) => {
      const anulado = await anularFila(c, anterior.tabla, anterior.id, motivo);
      return { ...(await darDeAlta(c, a)), anulado };
    }),
    anular: (tabla, id, motivo, autor) => escribir(autor, (c) => anularFila(c, tabla, id, motivo)),
    anularOcurrencia: (recurrenteId, fecha, motivo, autor, sustitucion) => escribir(autor, async (c) => {
      if (motivo.trim() === '') throw errorCashflow('MOTIVO_ANULACION_AUSENTE');
      return filaAApunte(await una(c, SQL.anularOcurrencia, [recurrenteId, fecha, motivo.trim(), sustitucion?.factura_id ?? null, sustitucion?.vencimiento_orden ?? null]));
    }),
    sustituirApunte: (apunteId, motivo, sustitucion, autor) => escribir(autor, async (c) => anularFila(c, 'APUNTE', apunteId, motivo, sustitucion) as Promise<ApunteCashflow>),

    probarCredencial: () => conCliente(async (c) => {
      try {
        await c.query('begin transaction read only');
        const n = Number((await una(c, SQL.prueba, []))?.filas);
        await c.query('rollback');
        if (!Number.isSafeInteger(n) || n < 0) throw new Error('DIAGNOSTICO_NO_ES_RECUENTO: filas');
        return { filas: n };
      } catch (e) {
        try { await c.query('rollback'); } catch { /* conexión rota */ }
        throw e instanceof ErrorCashflowBd ? e : traducirErrorCashflow(e);
      }
    }),

    cerrar: async () => { await pool.end(); },
  };
}
