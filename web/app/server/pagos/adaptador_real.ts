/**
 * H6-REAL: adaptador REAL de las marcas de pago y de la forma de pago por proveedor (migración 35 en producción). Solo lo
 * ejecuta Pío (dev:real / check:real).
 *
 *  - Lectura (pantalla Vencimientos): con cf_lectura, que tiene SELECT en las tres tablas (LectorPagos, de
 *    server/adaptador_real.ts: transacción READ ONLY y ROLLBACK). Funciona aunque falte la credencial de pagos.
 *  - Escritura: credencial propia CF_PAGOS_USER y CF_PAGOS_PASSWORD en web/app/.env.web (gitignored; Code nunca la lee
 *    ni la crea); host, puerto, base y CA compartidos con cf_lectura. Rol cf_pagos_web, pool propio de 2 conexiones y
 *    TLS con verificación de la CA. Sin credencial: solo lectura, con «Falta configurar la credencial de pagos».
 *  - Cada escritura, en su transacción con set_config('cf.autor', <autor>, true) dentro. Ante cualquier error: ROLLBACK
 *    y mensaje llano (errores_bd.ts). Nunca se reintenta.
 *  - La web nunca envía fecha_vencimiento ni importe de la marca (los copia el trigger). Único UPDATE: anulada = true
 *    sobre una fila vigente; corregir = anular + insertar en la misma transacción; nunca DELETE.
 *  - Historial: pagos_historial (lo escribe el trigger). Las filas de una misma transacción comparten created_at: un
 *    cambio de forma (anular la vigente + insertar la nueva) es un solo evento FORMA con la forma anterior.
 *
 * Solo sintaxis TypeScript borrable.
 */
import { isAbsolute, join } from 'node:path';
import pg from 'pg';
import { FARMACIA } from '../contrato.ts';
import { RUTA_CA_DEFECTO, leerCertificadoCA } from '../adaptador_real.ts';
import { instante, type ClienteBd, type Fila, type PoolBd } from '../rrhh/adaptador_real.ts';
import type { AlmacenPagosAsync } from './almacen.ts';
import { ErrorPagosBd, errorPagos, traducirErrorPagos } from './errores_bd.ts';
import {
  FORMAS_PAGO, FORMA_POR_DEFECTO, MENSAJE_FALTA_CREDENCIAL_PAGOS, ORIGENES_MARCA, claveVencimiento, hoyMadrid,
  type EventoPago, type FormaPago, type FuentePagos, type MarcaPago,
} from './pagos.ts';
import { SQL_PAGOS } from './sql.ts';

// ---------------------------------------------------------------------------
// Configuración (credencial en .env.web; Code nunca la lee ni la crea)
// ---------------------------------------------------------------------------

export const VARIABLES_PAGOS = ['CF_PAGOS_USER', 'CF_PAGOS_PASSWORD'] as const;
const VARIABLES_COMPARTIDAS = ['CF_LECTURA_HOST', 'CF_LECTURA_PORT', 'CF_LECTURA_DB'] as const;
export const ROL_PAGOS = 'cf_pagos_web';
export const MAX_CONEXIONES_PAGOS = 2;

export type ConfigPagos = { ok: true; config: pg.PoolConfig } | { ok: false; codigo: string; mensaje: string };

const OID = { INT8: 20, NUMERIC: 1700, DATE: 1082, TIMESTAMP: 1114, TIMESTAMPTZ: 1184 };
const TIPOS_TEXTO = new Set<number>([OID.INT8, OID.NUMERIC, OID.DATE, OID.TIMESTAMP, OID.TIMESTAMPTZ]);
const tipos = {
  getTypeParser(oid: number, formato?: 'text' | 'binary') {
    if (TIPOS_TEXTO.has(oid)) return (v: string) => v;
    return pg.types.getTypeParser(oid, formato);
  },
};

/**
 * Configuración del pool de escritura. Falla cerrado: sin CF_PAGOS_USER / CF_PAGOS_PASSWORD → «Falta configurar la
 * credencial de pagos»; usuario distinto de cf_pagos_web (directo o del pooler) → no conecta; sin CA válida → no conecta.
 */
export function configuracionPagos(env: Record<string, string | undefined>, leerCA: (ruta: string) => string = leerCertificadoCA): ConfigPagos {
  if (VARIABLES_PAGOS.some((v) => !env[v])) return { ok: false, codigo: 'CREDENCIAL_PAGOS_AUSENTE', mensaje: MENSAJE_FALTA_CREDENCIAL_PAGOS };
  const faltan = VARIABLES_COMPARTIDAS.filter((v) => !env[v]);
  if (faltan.length) return { ok: false, codigo: 'ENV_WEB_INCOMPLETO', mensaje: `Falta configurar la conexión (${faltan.join(', ')})` };
  const usuario = env.CF_PAGOS_USER as string;
  if (usuario !== ROL_PAGOS && !usuario.startsWith(`${ROL_PAGOS}.`)) {
    return { ok: false, codigo: 'USUARIO_NO_CF_PAGOS_WEB', mensaje: `La credencial de pagos debe ser del rol ${ROL_PAGOS}` };
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
      host: env.CF_LECTURA_HOST, port: puerto, database: env.CF_LECTURA_DB, user: usuario, password: env.CF_PAGOS_PASSWORD,
      ssl: { rejectUnauthorized: true, ca }, max: MAX_CONEXIONES_PAGOS, idleTimeoutMillis: 30_000, connectionTimeoutMillis: 10_000,
      application_name: 'cf_web_pagos', types: tipos,
    },
  };
}

export function crearPoolPagos(config: pg.PoolConfig): PoolBd {
  const pool = new pg.Pool(config);
  pool.on('error', (e) => console.warn(`Pagos: conexión cerrada por la base de datos (${String((e as { code?: string }).code ?? '')})`));
  return {
    connect: async () => {
      const c = await pool.connect();
      return { query: (sql, params) => c.query(sql, params as unknown[]), release: (d) => c.release(d) };
    },
    end: () => pool.end(),
  };
}

// ---------------------------------------------------------------------------
// Mapeo de filas (falla cerrado ante un valor no previsto)
// ---------------------------------------------------------------------------

const fecha = (v: unknown) => (v instanceof Date ? v.toISOString() : String(v)).slice(0, 10);
const deLista = <T extends string>(lista: readonly T[], v: unknown, campo: string): T => {
  if (!(lista as readonly unknown[]).includes(v)) throw new Error(`VALOR_NO_PREVISTO: ${campo}`);
  return v as T;
};
const numero = (v: unknown, campo: string): number => {
  const n = Number(v);
  if (v === null || v === undefined || !Number.isFinite(n)) throw new Error(`VALOR_NO_PREVISTO: ${campo}`);
  return n;
};
const jsonb = (v: unknown): Fila | null => (v === null || v === undefined ? null : typeof v === 'string' ? JSON.parse(v) as Fila : v as Fila);

export function filaAMarca(r: Fila, autores: { alta?: string | null; anula?: string | null } = {}): MarcaPago {
  const anulada = r.anulada === true;
  const orden = numero(r.vencimiento_orden, 'vencimiento_orden');
  if (!Number.isInteger(orden)) throw new Error('VALOR_NO_PREVISTO: vencimiento_orden');
  return {
    marca_id: String(r.id), farmacia: String(r.farmacia), factura_id: String(r.factura_id), vencimiento_orden: orden,
    fecha_vencimiento: fecha(r.fecha_vencimiento), importe: numero(r.importe, 'importe'), fecha_pago: fecha(r.fecha_pago),
    forma: deLista(FORMAS_PAGO, r.forma, 'forma'), origen: deLista(ORIGENES_MARCA, r.origen, 'origen'), anulada,
    creada_at: instante(r.created_at), creada_por: autores.alta ?? null,
    anulada_at: anulada ? instante(r.updated_at) : null, anulada_por: anulada ? autores.anula ?? null : null,
  };
}

const tablaDe = (h: Fila) => String(h.tabla ?? '').replace(/^public\./, '');
const esAnulacion = (h: Fila) => String(h.operacion).toUpperCase() === 'UPDATE' && jsonb(h.despues)?.anulada === true && jsonb(h.antes)?.anulada !== true;

/**
 * Historial de pagos_historial (en cualquier orden): eventos de la pantalla y autor de alta de cada marca. Las filas de
 * otras tablas o con operaciones que no son alta ni anulación no generan evento.
 */
export function historialPagos(filas: readonly Fila[]): { eventos: EventoPago[]; autorAlta: Map<string, string> } {
  const eventos: EventoPago[] = [];
  const autorAlta = new Map<string, string>();
  const base = { factura_id: null, vencimiento_orden: null, marca_id: null, cif: null, fecha_pago: null, forma: null, forma_anterior: null, origen: null };
  const formas = filas.filter((h) => tablaDe(h) === 'proveedores_forma_pago');
  const mismaTx = (a: Fila, b: Fila) => String(a.created_at) === String(b.created_at);
  filas.forEach((h, i) => {
    const evento_id = Number.isSafeInteger(Number(h.id)) ? Number(h.id) : i + 1;
    const op = String(h.operacion).toUpperCase();
    const at = instante(h.created_at);
    const autor = String(h.autor ?? '');
    const d = jsonb(h.despues);
    if (tablaDe(h) === 'vencimientos_marcas_pago' && d) {
      const m = {
        factura_id: String(d.factura_id), vencimiento_orden: Number(d.vencimiento_orden), marca_id: String(d.id),
        fecha_pago: fecha(d.fecha_pago), forma: deLista(FORMAS_PAGO, d.forma, 'forma'), origen: deLista(ORIGENES_MARCA, d.origen, 'origen'),
      };
      if (op === 'INSERT') { autorAlta.set(m.marca_id, autor); eventos.push({ ...base, ...m, evento_id, accion: 'MARCA', autor, at }); }
      else if (esAnulacion(h)) eventos.push({ ...base, ...m, evento_id, accion: 'ANULA_MARCA', autor, at });
      return;
    }
    if (tablaDe(h) === 'proveedores_forma_pago' && d) {
      const cif = String(d.cif);
      if (op === 'INSERT') {
        const previa = formas.find((x) => x !== h && esAnulacion(x) && mismaTx(x, h) && String(jsonb(x.despues)?.cif) === cif);
        const anterior = previa ? deLista(FORMAS_PAGO, jsonb(previa.antes)?.forma, 'forma') : null;
        eventos.push({ ...base, evento_id, accion: 'FORMA', autor, at, cif, forma: deLista(FORMAS_PAGO, d.forma, 'forma'), forma_anterior: anterior });
      } else if (esAnulacion(h)) {
        // Anular + insertar en la misma transacción = cambio de forma (ya contado en el FORMA de la inserción).
        const sustituta = formas.some((x) => x !== h && String(x.operacion).toUpperCase() === 'INSERT' && mismaTx(x, h) && String(jsonb(x.despues)?.cif) === cif);
        if (!sustituta) eventos.push({ ...base, evento_id, accion: 'FORMA_POR_DEFECTO', autor, at, cif, forma_anterior: deLista(FORMAS_PAGO, jsonb(h.antes)?.forma, 'forma') });
      }
    }
  });
  return { eventos, autorAlta };
}

export interface FilasPagos { marcas: Fila[]; formas: Fila[]; historial: Fila[] }
/** Lectura con cf_lectura (server/adaptador_real.ts: READ ONLY y ROLLBACK). */
export type LectorPagos = () => Promise<FilasPagos>;

/** Fuente de la pantalla desde las filas leídas: marcas vigentes por (factura_id, orden), formas vigentes por CIF e historial. */
export function fuenteDesdeFilas(hoy: string, f: FilasPagos): FuentePagos {
  const { eventos, autorAlta } = historialPagos(f.historial);
  const marcas = new Map<string, MarcaPago>();
  for (const r of f.marcas) {
    const m = filaAMarca(r, { alta: autorAlta.get(String(r.id)) ?? null });
    if (m.anulada) continue;
    const k = claveVencimiento(m.factura_id, m.vencimiento_orden);
    if (marcas.has(k)) throw new Error('MARCAS_VIGENTES_DUPLICADAS'); // la BD lo impide: falla cerrado
    marcas.set(k, m);
  }
  const formas = new Map<string, FormaPago>();
  for (const r of f.formas) {
    if (r.anulada === true) continue;
    const cif = String(r.cif);
    if (formas.has(cif)) throw new Error('FORMAS_VIGENTES_DUPLICADAS');
    formas.set(cif, deLista(FORMAS_PAGO, r.forma, 'forma'));
  }
  return { hoy, formas, marcas, historial: eventos };
}

// ---------------------------------------------------------------------------
// Almacén REAL
// ---------------------------------------------------------------------------

export type AlmacenPagosReal = AlmacenPagosAsync & {
  /** check:real: la credencial de pagos conecta y lee su tabla (READ ONLY). Solo el recuento. */
  probarCredencial(): Promise<{ formas: number }>;
};

export function crearAlmacenPagosReal(o: { lector: LectorPagos; pool: PoolBd | null; hoy?: () => string }): AlmacenPagosReal {
  const { lector, pool } = o;
  const hoy = o.hoy ?? (() => hoyMadrid());

  async function conCliente<T>(trabajo: (c: ClienteBd) => Promise<T>): Promise<T> {
    if (pool === null) throw errorPagos('CREDENCIAL_PAGOS_AUSENTE');
    let c: ClienteBd;
    try { c = await pool.connect(); } catch (e) { throw traducirErrorPagos(e); }
    let roto = false;
    try { return await trabajo(c); } catch (e) { roto = true; throw e; } finally { c.release(roto); }
  }
  /** Una transacción con el autor fijado DENTRO (set_config local); error → ROLLBACK, mensaje llano, sin reintento. */
  const escribir = <T>(quien: string, trabajo: (c: ClienteBd) => Promise<T>) => conCliente(async (c) => {
    if (quien.trim() === '' || quien.length > 60) throw new Error('AUTOR_NO_VALIDO');
    try {
      await c.query('begin');
      await c.query(SQL_PAGOS.autor, [quien]);
      const r = await trabajo(c);
      await c.query('commit');
      return r;
    } catch (e) {
      try { await c.query('rollback'); } catch { /* conexión rota: se descarta */ }
      throw traducirErrorPagos(e);
    }
  });

  return {
    hoy,
    sinEscritura: pool === null ? { codigo: 'CREDENCIAL_PAGOS_AUSENTE', mensaje: MENSAJE_FALTA_CREDENCIAL_PAGOS } : null,
    fuente: async () => fuenteDesdeFilas(hoy(), await lector()),

    /** INSERT … ON CONFLICT … WHERE NOT anulada DO NOTHING: si alguna ya tenía marca vigente, ROLLBACK de todas. */
    marcar: (items, autor) => escribir(autor, async (c) => {
      const r = await c.query(SQL_PAGOS.insertarMarcas, [FARMACIA, items.map((i) => i.factura_id), items.map((i) => i.vencimiento_orden),
        items.map((i) => i.fecha_pago), items.map((i) => i.forma), items.map((i) => i.origen)]);
      if (r.rows.length !== items.length) throw errorPagos('YA_PAGADO');
      const marcas = r.rows.map((f) => filaAMarca(f, { alta: autor }));
      const pos = (m: MarcaPago) => items.findIndex((i) => i.factura_id === m.factura_id && i.vencimiento_orden === m.vencimiento_orden);
      return marcas.sort((a, b) => pos(a) - pos(b));
    }),

    anular: (marcaId, autor) => escribir(autor, async (c) => {
      const f = (await c.query(SQL_PAGOS.anularMarca, [marcaId, FARMACIA])).rows[0];
      if (f) return filaAMarca(f, { anula: autor });
      const previa = (await c.query(SQL_PAGOS.marcaPorId, [marcaId, FARMACIA])).rows[0];
      throw errorPagos(previa ? 'MARCA_YA_ANULADA' : 'MARCA_NO_ENCONTRADA');
    }),

    /** Cambiar = anular la vigente + insertar la nueva (misma transacción); null = solo anular (vuelve a domiciliación). */
    fijarForma: (cif, forma, autor) => escribir(autor, async (c) => {
      const previa = (await c.query(SQL_PAGOS.formaBloqueo, [FARMACIA, cif])).rows[0];
      const actual = previa ? deLista(FORMAS_PAGO, previa.forma, 'forma') : null;
      if (actual === forma) throw errorPagos('SIN_CAMBIOS');
      if (previa && !(await c.query(SQL_PAGOS.anularForma, [String(previa.id)])).rows[0]) throw errorPagos('ESTADO_CAMBIADO');
      if (forma === null) return { cif, forma: FORMA_POR_DEFECTO, por_defecto: true };
      if (!(await c.query(SQL_PAGOS.insertarForma, [FARMACIA, cif, forma])).rows[0]) throw errorPagos('ESTADO_CAMBIADO');
      return { cif, forma, por_defecto: false };
    }),

    probarCredencial: () => conCliente(async (c) => {
      try {
        await c.query('begin transaction read only');
        const n = Number((await c.query(SQL_PAGOS.prueba, [FARMACIA])).rows[0]?.formas);
        await c.query('rollback');
        if (!Number.isSafeInteger(n) || n < 0) throw new Error('DIAGNOSTICO_NO_ES_RECUENTO: formas');
        return { formas: n };
      } catch (e) {
        try { await c.query('rollback'); } catch { /* conexión rota */ }
        throw e instanceof ErrorPagosBd ? e : traducirErrorPagos(e);
      }
    }),

    cerrar: async () => { await pool?.end(); },
  };
}
