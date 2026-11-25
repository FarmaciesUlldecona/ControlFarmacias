/**
 * Adaptador REAL: lee Supabase con el rol cf_lectura (migración 29). Solo lo ejecuta Pío.
 *
 *  - Parámetros desde web/app/.env.web (gitignored): CF_LECTURA_HOST, CF_LECTURA_PORT,
 *    CF_LECTURA_USER, CF_LECTURA_DB, CF_LECTURA_PASSWORD. Nunca el .env de Programa,
 *    service_role ni ControlFarmaciasRO.
 *  - pg Pool con max 2 conexiones y TLS con verificación de certificado (rejectUnauthorized true)
 *    contra la CA de Supabase: web/app/certs/supabase-ca.crt o la ruta de CF_LECTURA_CA. Sin CA válida
 *    no se conecta ("falta certificado CA"). El .crt solo se lee, nunca se modifica.
 *  - Cada bloque se lee en una transacción READ ONLY (REPEATABLE READ: una sola foto) que
 *    termina siempre con ROLLBACK.
 *  - Solo ejecuta las consultas del contrato (CONSULTAS), con farmacia fija PIO.
 *  - H6-REAL: además, lectura de las tablas de pagos de la migración 35 (vencimientos_marcas_pago,
 *    proveedores_forma_pago, pagos_historial; cf_lectura tiene SELECT en las tres) y su diagnóstico (solo recuentos).
 *  - H7-REAL: lectura del cashflow de la migración 38 (cf_cashflow_importaciones, _cuentas, _importes, _saldos; SELECT
 *    para cf_lectura con RLS PIO, RITA —módulo CASHFLOW— y SL), en REPEATABLE READ READ ONLY, y su diagnóstico.
 */
import { X509Certificate } from 'node:crypto';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { isAbsolute, join } from 'node:path';
import pg from 'pg';
import {
  CATEGORIAS_TIPO_DOCUMENTAL, COLUMNA_DIAGNOSTICO_GRUPO, CONSULTAS, CONSULTAS_CHECK, FARMACIA, GRUPOS_SIN_FACTURA, UUID_RE, contratoDesdeConsultas, resumenCasado, resumenDuplicados, resumenPar08C66676,
  type Contrato, type EjecutorBloque, type Fila, type NombreConsulta, type ValorDiagnostico,
} from './contrato.ts';
import { COLUMNAS_DIAGNOSTICO_PAGOS, SQL_PAGOS } from './pagos/sql.ts';
import { hoyMadrid } from './pagos/pagos.ts';
import type { DatosCashflow, VencimientoCashflow } from './cashflow/cashflow.ts';
import { diagnosticoCashflow, leerCashflowReal } from './cashflow/lectura_real.ts';

export const RUTA_ENV_WEB = join(import.meta.dirname, '..', '.env.web');
/** Ruta por defecto de la CA; configurable con CF_LECTURA_CA (absoluta o relativa a web/app). */
export const RUTA_CA_DEFECTO = join(import.meta.dirname, '..', 'certs', 'supabase-ca.crt');

/** Solo lectura del .crt: comprueba que existe y que es un certificado X.509 PEM vigente. */
export function leerCertificadoCA(ruta: string): string {
  if (!existsSync(ruta) || !statSync(ruta).isFile()) throw new Error(`FALTA_CERTIFICADO_CA: falta certificado CA (${ruta})`);
  const pem = readFileSync(ruta, 'utf8');
  if (!pem.includes('-----BEGIN CERTIFICATE-----')) throw new Error(`CERTIFICADO_CA_NO_VALIDO: el fichero no es un certificado PEM (${ruta})`);
  let cert: X509Certificate;
  try {
    cert = new X509Certificate(pem);
  } catch {
    throw new Error(`CERTIFICADO_CA_NO_VALIDO: no se puede leer como X.509 (${ruta})`);
  }
  if (!cert.ca) throw new Error(`CERTIFICADO_CA_NO_VALIDO: el certificado no es de una CA (${ruta})`);
  if (Date.parse(cert.validTo) < Date.now()) throw new Error(`CERTIFICADO_CA_CADUCADO: ${cert.validTo} (${ruta})`);
  return pem;
}

function rutaCA(): string {
  const v = process.env.CF_LECTURA_CA;
  if (!v) return RUTA_CA_DEFECTO;
  return isAbsolute(v) ? v : join(import.meta.dirname, '..', v);
}
const VARIABLES = ['CF_LECTURA_HOST', 'CF_LECTURA_PORT', 'CF_LECTURA_USER', 'CF_LECTURA_DB', 'CF_LECTURA_PASSWORD'] as const;
const OID = { INT8: 20, NUMERIC: 1700, DATE: 1082, TIMESTAMP: 1114, TIMESTAMPTZ: 1184 };

/** int8, numeric y fechas se reciben como texto (sin pérdida ni desplazamiento de zona); el contrato los convierte. */
const TIPOS_TEXTO = new Set<number>([OID.INT8, OID.NUMERIC, OID.DATE, OID.TIMESTAMP, OID.TIMESTAMPTZ]);
const tipos = {
  getTypeParser(oid: number, formato?: 'text' | 'binary') {
    if (TIPOS_TEXTO.has(oid)) return (v: string) => v;
    return pg.types.getTypeParser(oid, formato);
  },
};

function configuracionConexion(): pg.PoolConfig {
  if (!existsSync(RUTA_ENV_WEB)) throw new Error('ENV_WEB_AUSENTE: falta web/app/.env.web (ver .env.web.example)');
  process.loadEnvFile(RUTA_ENV_WEB);
  const faltan = VARIABLES.filter((v) => !process.env[v]);
  if (faltan.length) throw new Error(`ENV_WEB_INCOMPLETO: ${faltan.join(', ')}`);
  const usuario = process.env.CF_LECTURA_USER as string;
  // Falla cerrado: el usuario debe ser cf_lectura (directo o por el pooler: cf_lectura.<project_ref>).
  if (usuario !== 'cf_lectura' && !usuario.startsWith('cf_lectura.')) throw new Error('USUARIO_NO_CF_LECTURA');
  const puerto = Number(process.env.CF_LECTURA_PORT);
  if (!Number.isInteger(puerto) || puerto <= 0) throw new Error('CF_LECTURA_PORT_NO_VALIDO');
  const ca = leerCertificadoCA(rutaCA()); // sin CA válida: no se conecta
  return {
    host: process.env.CF_LECTURA_HOST,
    port: puerto,
    user: usuario,
    database: process.env.CF_LECTURA_DB,
    password: process.env.CF_LECTURA_PASSWORD,
    // TLS obligatorio con verificación de la cadena y del nombre del servidor (equivale a sslmode=verify-full).
    ssl: { rejectUnauthorized: true, ca },
    max: 2,
    idleTimeoutMillis: 30_000,
    connectionTimeoutMillis: 10_000,
    application_name: 'cf_web_fase1',
    types: tipos,
  };
}

export interface AdaptadorReal {
  contrato: Contrato;
  /**
   * Ejecuta una consulta del contrato dentro de una transacción READ ONLY (para check:real). Las consultas
   * por factura usan la factura PIO más reciente, elegida aquí dentro; su id nunca sale de esta función.
   * `factura`: 'reciente' si se usó una factura real; 'ninguna' si PIO no tiene facturas (id inexistente).
   */
  probar(n: NombreConsulta): Promise<{ columnas: number; filas: number; factura?: 'reciente' | 'ninguna' }>;
  /** Recuentos de diagnóstico del bloque proveedores (solo números). */
  diagnosticoProveedores(): Promise<Record<string, number>>;
  /**
   * H5-4: un diagnóstico (recuentos, sí/no, nombres de columna), cada uno en su propia transacción READ ONLY: si uno
   * falla, los demás siguen (antes compartían transacción y el error de uno abortaba todos).
   */
  diagnostico(nombre: NombreDiagnostico): Promise<Record<string, ValorDiagnostico>>;
  /** H6-REAL: filas vigentes de marcas y formas, e historial, de PIO (cf_lectura tiene SELECT en las tres tablas). */
  leerPagos(): Promise<{ marcas: Fila[]; formas: Fila[]; historial: Fila[] }>;
  /** H6-REAL (check:real): recuentos de pagos (marcas vigentes, anuladas, a revisar, huérfanas; formas vigentes; historial). */
  diagnosticoPagos(): Promise<Record<string, number>>;
  /** H7-REAL: cashflow de la importación vigente (cf_cashflow_*, migración 38), en una sola foto READ ONLY. */
  leerCashflow(): Promise<DatosCashflow>;
  /** H7-REAL (check:real): diagnóstico del cashflow, solo números y sí/no. H7-REAL-5: con los vencimientos de PIO. */
  diagnosticoCashflow(vencimientos?: readonly VencimientoCashflow[]): Promise<Record<string, ValorDiagnostico>>;
  cerrar(): Promise<void>;
}

/** Id de factura inexistente: solo si PIO no tiene ninguna factura (no devuelve filas). */
const UUID_NULO = '00000000-0000-0000-0000-000000000000';
/** Columnas que puede devolver el diagnóstico (todas son recuentos). */
const COLUMNAS_DIAGNOSTICO = ['facturas', 'facturas_sin_proveedor_id', 'grupos_proveedor_id',
  'literales_distintos_sin_proveedor_id', 'proveedores_catalogo', 'facturas_cif_columna', 'facturas_cif_datos_extraidos',
  'cif_distintos', 'facturas_sin_cif', 'facturas_sin_cif_con_id_r9'];
const COLUMNAS_VENCIMIENTOS = ['vencimientos', 'vencimientos_importe_null', 'vencimientos_null_con_incidencia',
  'vencimientos_null_sin_incidencia', 'facturas_con_incidencia', 'incidencias_importe_vencimiento', 'vencimientos_null_sin_cif',
  'vencimientos_tipo_documento_null', 'vencimientos_tipo_documental_null', 'vencimientos_tipo_otro',
  'vencimientos_sentido_no_documentado',
  // H6-3: solo recuentos.
  'vencimientos_cargo_importe_negativo', 'vencimientos_abono', 'vencimientos_abono_vencidos', 'vencimientos_abono_no_vencidos',
  'vencimientos_abono_sin_fecha'];
/** H5-4: diagnósticos de la comprobación REAL, en orden de impresión; cada uno en su propia transacción. */
export const NOMBRES_DIAGNOSTICO = ['vencimientos', 'documentos', 'tipo_documento', 'sentido', 'casado', 'estado_linea', 'duplicados',
  'par_08C66676', 'noche', 'sin_factura'] as const;
/**
 * H8: albaranes no reservados por ninguna conciliación vigente (solo recuentos). H8-3: el total (contado aparte) y un
 * recuento por grupo de GRUPOS_SIN_FACTURA, exhaustivos y excluyentes; después, proveedores por bloque.
 */
const COLUMNAS_GRUPOS_SIN_FACTURA = GRUPOS_SIN_FACTURA.map((g) => COLUMNA_DIAGNOSTICO_GRUPO[g]);
// H8-4: + traspasos entre farmacias (grupo) y proveedores con conciliación sin fecha de inicio y de traspaso (el de
// traspaso debería ser 1: confirma que la configuración identifica un único proveedor de Farmatic).
export const COLUMNAS_SIN_FACTURA = ['total', ...COLUMNAS_GRUPOS_SIN_FACTURA, 'proveedores_con_conciliacion',
  'proveedores_leido_sin_conciliacion', 'proveedores_sin_lector', 'proveedores_con_conciliacion_sin_desde', 'proveedores_traspaso'];

/**
 * H8-3: error de recuentos incoherentes que lleva los recuentos (solo números) para que check:real los imprima igualmente
 * y se vea la diferencia.
 */
export class ErrorRecuentosIncoherentes extends Error {
  readonly recuentos: Record<string, number>;
  constructor(nombre: string, recuentos: Record<string, number>) {
    super(`DIAGNOSTICO_RECUENTOS_INCOHERENTES: ${nombre}`);
    this.recuentos = recuentos;
  }
}

/** H8: resumen del diagnóstico sin_factura. Falla cerrado si no son recuentos o si los grupos no suman el total. */
export function resumenSinFactura(fila: Record<string, unknown>): Record<string, number> {
  const d: Record<string, number> = {};
  for (const col of COLUMNAS_SIN_FACTURA) d[col] = recuento(fila[col], col);
  const suma = COLUMNAS_GRUPOS_SIN_FACTURA.reduce((a, c) => a + d[c], 0);
  if (suma !== d.total) throw new ErrorRecuentosIncoherentes('sin_factura', { ...d, suma_grupos: suma, diferencia: Math.abs(d.total - suma) });
  return d;
}
/** H8: «para revisar» de la última noche (migración 36), solo recuentos. */
export const COLUMNAS_NOCHE = ['noches', 'lista_no_valida', 'elementos', 'diferencia', 'no_alliance', 'r18_pendiente', 'defecto',
  'otros_tipos', 'fuera_de_pio'];

/**
 * H8: resumen del diagnóstico noche (una fila de recuentos). Falla cerrado si algún valor no es un recuento o si los
 * tipos y fuera_de_pio no reparten exactamente los elementos.
 */
export function resumenNoche(fila: Record<string, unknown>): Record<string, number> {
  const d: Record<string, number> = {};
  for (const col of COLUMNAS_NOCHE) d[col] = recuento(fila[col], col);
  const suma = d.diferencia + d.no_alliance + d.r18_pendiente + d.defecto + d.otros_tipos + d.fuera_de_pio;
  if (suma !== d.elementos || d.noches > 1 || d.lista_no_valida > d.noches) throw new Error('DIAGNOSTICO_RECUENTOS_INCOHERENTES: noche');
  return d;
}
/** H5-7: líneas vigentes por estado de línea (migración 30) y con diferencia null. */
export const COLUMNAS_ESTADO_LINEA = ['lineas', 'coincide', 'diferencia', 'no_evaluable', 'sin_valor', 'otros_valores', 'diferencia_null'];
export type NombreDiagnostico = (typeof NOMBRES_DIAGNOSTICO)[number];

/** H4d-3: casos de sentido por origen. */
export const COLUMNAS_SENTIDO = ['vencimiento_regla', 'incidencia_sentido_no_documentado', 'incidencia_sentido_no_etiquetado'];
/** H4c-2: facturas + una columna por etiqueta fija (CATEGORIAS_TIPO_DOCUMENTAL). */
const COLUMNAS_TIPO_DOCUMENTO = ['facturas', ...CATEGORIAS_TIPO_DOCUMENTAL];
const COLUMNAS_DOCUMENTOS = ['pdf', 'pdf_sin_factura', 'pdf_sin_factura_con_proveedor_id',
  'pdf_sin_factura_con_proveedor_catalogo', 'pdf_sin_factura_sin_proveedor'];
/** Tipos numéricos de pg (numeric, float4, float8): "columnas de importe" del par 08C66676. */
const OID_IMPORTE = new Set([OID.NUMERIC, 700, 701]);

function recuento(v: unknown, col: string): number {
  const n = Number(v);
  if (typeof v === 'boolean' || v === null || !Number.isSafeInteger(n) || n < 0) throw new Error(`DIAGNOSTICO_NO_ES_RECUENTO: ${col}`);
  return n;
}

/**
 * H5-7: resumen del diagnóstico estado_linea (una fila de recuentos). Falla cerrado si algún valor no es un recuento o si
 * los cinco grupos de estado no reparten exactamente todas las líneas.
 */
export function resumenEstadoLinea(fila: Record<string, unknown>): Record<string, number> {
  const d: Record<string, number> = {};
  for (const col of COLUMNAS_ESTADO_LINEA) d[col] = recuento(fila[col], col);
  const suma = d.coincide + d.diferencia + d.no_evaluable + d.sin_valor + d.otros_valores;
  if (suma !== d.lineas || d.diferencia_null > d.lineas) throw new Error('DIAGNOSTICO_RECUENTOS_INCOHERENTES: estado_linea');
  return d;
}

/** Última barrera: un diagnóstico solo puede contener recuentos, sí/no o nombres de columna. */
export function validarDiagnostico(d: Record<string, ValorDiagnostico>): Record<string, ValorDiagnostico> {
  for (const [k, v] of Object.entries(d)) {
    const ok = typeof v === 'boolean'
      || (typeof v === 'number' && Number.isSafeInteger(v) && v >= 0)
      || (Array.isArray(v) && v.every((x) => (typeof x === 'number' && Number.isSafeInteger(x) && x >= 0)
        || (typeof x === 'string' && /^[a-z_][a-z0-9_]{0,62}$/.test(x))));
    if (!ok) throw new Error(`DIAGNOSTICO_VALOR_NO_PERMITIDO: ${k}`);
  }
  return d;
}

export function crearAdaptadorReal(): AdaptadorReal {
  const pool = new pg.Pool(configuracionConexion());

  const enTransaccion: EjecutorBloque = async (trabajo) => {
    const cliente = await pool.connect();
    try {
      await cliente.query('begin transaction isolation level repeatable read read only');
      await cliente.query("set local statement_timeout = '20s'");
      const ro = await cliente.query<{ ro: string }>("select current_setting('transaction_read_only') as ro");
      if (ro.rows[0]?.ro !== 'on') throw new Error('TRANSACCION_NO_READ_ONLY');
      return await trabajo(async (n, idFactura) => {
        const c = CONSULTAS[n];
        const params: string[] = c.porFactura ? [FARMACIA, idFactura ?? UUID_NULO] : [FARMACIA];
        const r = await cliente.query<Fila>(c.sql, params);
        return r.rows;
      });
    } finally {
      try { await cliente.query('rollback'); } finally { cliente.release(); }
    }
  };

  /**
   * Ejecuta una consulta en una transacción READ ONLY propia, siempre con ROLLBACK. `foto`: REPEATABLE READ (todas las
   * consultas ven el mismo estado; H7-REAL, cashflow).
   */
  async function soloLectura<T>(trabajo: (cliente: pg.PoolClient) => Promise<T>, foto = false): Promise<T> {
    const cliente = await pool.connect();
    try {
      await cliente.query(foto ? 'begin transaction isolation level repeatable read read only' : 'begin transaction read only');
      const ro = await cliente.query<{ ro: string }>("select current_setting('transaction_read_only') as ro");
      if (ro.rows[0]?.ro !== 'on') throw new Error('TRANSACCION_NO_READ_ONLY');
      return await trabajo(cliente);
    } finally {
      try { await cliente.query('rollback'); } finally { cliente.release(); }
    }
  }

  /** H7-REAL: las lecturas del cashflow en una sola foto (la vigente y sus filas, coherentes). */
  const leerCashflow = () => soloLectura(async (cliente) => {
    await cliente.query("set local statement_timeout = '20s'");
    return leerCashflowReal(async (sql, params) => (await cliente.query<Fila>(sql, params)).rows);
  }, true);

  // Id de la factura más reciente: se elige una vez y se queda en este cierre (nunca se devuelve ni imprime).
  let facturaReciente: Promise<string | null> | null = null;
  const elegirFactura = () => (facturaReciente ??= soloLectura(async (cliente) => {
    const r = await cliente.query<Fila>(CONSULTAS_CHECK.factura_reciente.sql, [FARMACIA]);
    const id = r.rows[0]?.factura_id;
    if (id === undefined) return null;
    if (typeof id !== 'string' || !UUID_RE.test(id)) throw new Error('FACTURA_RECIENTE_ID_NO_VALIDO');
    return id;
  }));

  return {
    contrato: contratoDesdeConsultas(enTransaccion),
    async probar(n) {
      const c = CONSULTAS[n];
      const id = c.porFactura ? await elegirFactura() : null;
      return soloLectura(async (cliente) => {
        const r = await cliente.query(c.sql, c.porFactura ? [FARMACIA, id ?? UUID_NULO] : [FARMACIA]);
        // Solo recuentos: las filas no salen de esta función.
        const res = { columnas: r.fields.length, filas: r.rows.length };
        return c.porFactura ? { ...res, factura: id === null ? 'ninguna' as const : 'reciente' as const } : res;
      });
    },
    diagnosticoProveedores: () => soloLectura(async (cliente) => {
      const r = await cliente.query<Fila>(CONSULTAS_CHECK.diagnostico_proveedores.sql, [FARMACIA]);
      if (r.rows.length !== 1) throw new Error(`DIAGNOSTICO_FILAS_INESPERADAS: ${r.rows.length}`);
      const out: Record<string, number> = {};
      for (const col of COLUMNAS_DIAGNOSTICO) {
        const n = Number(r.rows[0][col]);
        if (!Number.isSafeInteger(n) || n < 0) throw new Error(`DIAGNOSTICO_NO_ES_RECUENTO: ${col}`);
        out[col] = n;
      }
      return out;
    }),
    diagnostico: (nombre) => soloLectura(async (cliente) => {
      const una = async (sql: string): Promise<Fila> => {
        const r = await cliente.query<Fila>(sql, [FARMACIA]);
        if (r.rows.length !== 1) throw new Error(`DIAGNOSTICO_FILAS_INESPERADAS: ${r.rows.length}`);
        return r.rows[0];
      };
      const recuentos = (fila: Fila, columnas: readonly string[]) => {
        const out: Record<string, ValorDiagnostico> = {};
        for (const col of columnas) out[col] = recuento(fila[col], col);
        return out;
      };
      switch (nombre) {
        case 'vencimientos': {
          const f = await una(CONSULTAS_CHECK.diagnostico_vencimientos.sql);
          const venc = recuentos(f, COLUMNAS_VENCIMIENTOS);
          const grupos = f.nulls_por_grupo_cif;
          if (!Array.isArray(grupos)) throw new Error('DIAGNOSTICO_NO_ES_RECUENTO: nulls_por_grupo_cif');
          venc.nulls_por_grupo_cif = grupos.map((n) => recuento(n, 'nulls_por_grupo_cif'));
          return validarDiagnostico(venc);
        }
        case 'documentos': return validarDiagnostico(recuentos(await una(CONSULTAS_CHECK.diagnostico_documentos.sql), COLUMNAS_DOCUMENTOS));
        case 'tipo_documento': return validarDiagnostico(recuentos(await una(CONSULTAS_CHECK.diagnostico_tipo_documento.sql), COLUMNAS_TIPO_DOCUMENTO));
        case 'sentido': return validarDiagnostico(recuentos(await una(CONSULTAS_CHECK.diagnostico_sentido.sql), COLUMNAS_SENTIDO));
        case 'casado': {
          const r = await cliente.query<Fila>(CONSULTAS_CHECK.diagnostico_casado.sql, [FARMACIA]);
          return validarDiagnostico(resumenCasado(r.rows));
        }
        case 'estado_linea': return validarDiagnostico(resumenEstadoLinea(await una(CONSULTAS_CHECK.diagnostico_estado_linea.sql)));
        case 'duplicados': {
          const r = await cliente.query<Fila>(CONSULTAS.alertas_duplicado_farmatic.sql, [FARMACIA]);
          return validarDiagnostico(resumenDuplicados(r.rows));
        }
        case 'par_08C66676': {
          const r = await cliente.query<Fila>(CONSULTAS_CHECK.diagnostico_par_08c66676.sql, [FARMACIA]);
          const columnasImporte = r.fields.filter((f) => OID_IMPORTE.has(f.dataTypeID)).map((f) => f.name);
          return validarDiagnostico(resumenPar08C66676(r.rows, columnasImporte));
        }
        case 'noche': return validarDiagnostico(resumenNoche(await una(CONSULTAS_CHECK.diagnostico_noche.sql)));
        case 'sin_factura': return validarDiagnostico(resumenSinFactura(await una(CONSULTAS_CHECK.diagnostico_sin_factura.sql)));
      }
    }),
    // H6-REAL: marcas, formas e historial de pagos con cf_lectura (READ ONLY, ROLLBACK). Solo PIO.
    leerPagos: () => soloLectura(async (cliente) => ({
      marcas: (await cliente.query<Fila>(SQL_PAGOS.marcasVigentes, [FARMACIA])).rows,
      formas: (await cliente.query<Fila>(SQL_PAGOS.formasVigentes, [FARMACIA])).rows,
      historial: (await cliente.query<Fila>(SQL_PAGOS.historial, [FARMACIA])).rows,
    })),
    diagnosticoPagos: () => soloLectura(async (cliente) => {
      const r = await cliente.query<Fila>(SQL_PAGOS.diagnostico, [FARMACIA]);
      if (r.rows.length !== 1) throw new Error(`DIAGNOSTICO_FILAS_INESPERADAS: ${r.rows.length}`);
      const out: Record<string, number> = {};
      for (const col of COLUMNAS_DIAGNOSTICO_PAGOS) out[col] = recuento(r.rows[0][col], col);
      return out;
    }),
    leerCashflow,
    diagnosticoCashflow: async (vencimientos = []) => validarDiagnostico(diagnosticoCashflow(await leerCashflow(), hoyMadrid(), vencimientos)),
    cerrar: () => pool.end(),
  };
}
