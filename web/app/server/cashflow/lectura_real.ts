/**
 * H7: lecturas REAL del cashflow, escritas contra el contrato del circuito (tablas cf_cashflow_*, pendientes en Supabase).
 *
 * NO están conectadas: mientras las tablas no existan, GET /api/cashflow responde 503 «Pendiente de tablas en Supabase».
 * Para conectarlas hará falta (decisión de Pío): que el circuito cree las tablas con lectura para cf_lectura, añadir los
 * cuatro objetos a la lista cerrada (DISENO 2BN y OBJETOS_PERMITIDOS) y leerlas en una transacción READ ONLY.
 *
 * Solo SELECT. Solo las cuentas de la pantalla (PIO y RITA): la cuenta SL ni se lee. Falla cerrado: cualquier valor
 * con forma inesperada lanza error (nunca se inventa un 0).
 */
import type { Fila } from '../contrato.ts';
import { CUENTAS_CASHFLOW, esDecenaInicio, type DatosCashflow, type ImportacionCashflow } from './cashflow.ts';

export const OBJETOS_CASHFLOW = ['cf_cashflow_importaciones', 'cf_cashflow_cuentas', 'cf_cashflow_importes', 'cf_cashflow_saldos'] as const;

/** $1 = cuentas de la pantalla (text[]). */
export const SQL_CASHFLOW = {
  importaciones: `select vigente, importado_at, origen, estado
  from public.cf_cashflow_importaciones
  order by importado_at desc`,
  cuentas: `select codigo, farmacia
  from public.cf_cashflow_cuentas
  where codigo = any($1::text[])`,
  importes: `select cuenta, decena_inicio::text as decena_inicio, decena_fin::text as decena_fin, categoria, concepto, importe::text as importe
  from public.cf_cashflow_importes
  where cuenta = any($1::text[])
  order by cuenta, decena_inicio, categoria, concepto`,
  saldos: `select cuenta, decena_inicio::text as decena_inicio, saldo_formulas::text as saldo_formulas, saldo_bancos::text as saldo_bancos
  from public.cf_cashflow_saldos
  where cuenta = any($1::text[])
  order by cuenta, decena_inicio`,
} as const;

function texto(v: unknown, campo: string): string {
  if (typeof v !== 'string' || v.trim() === '') throw new Error(`CASHFLOW_VALOR_NO_VALIDO: ${campo}`);
  return v;
}
function importeReal(v: unknown, campo: string): number | null {
  if (v === null || v === undefined) return null;
  const n = typeof v === 'number' ? v : typeof v === 'string' && /^-?\d+(\.\d+)?$/.test(v.trim()) ? Number(v) : NaN;
  if (!Number.isFinite(n)) throw new Error(`CASHFLOW_IMPORTE_NO_VALIDO: ${campo}`);
  return n;
}
function decena(v: unknown, campo: string): string {
  const s = texto(v, campo).slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) throw new Error(`CASHFLOW_FECHA_NO_VALIDA: ${campo}`);
  return s;
}
function instante(v: unknown): string {
  const t = v instanceof Date ? v.getTime() : typeof v === 'string' ? Date.parse(v) : NaN;
  if (Number.isNaN(t)) throw new Error('CASHFLOW_FECHA_NO_VALIDA: importado_at');
  return new Date(t).toISOString();
}

/** Ejecuta las cuatro lecturas con `consultar` (una transacción READ ONLY del llamador) y convierte las filas. */
export async function leerCashflowReal(consultar: (sql: string, params: unknown[]) => Promise<Fila[]>): Promise<DatosCashflow> {
  const cuentasPantalla = [...CUENTAS_CASHFLOW];
  const [imps, cuentas, importes, saldos] = [
    await consultar(SQL_CASHFLOW.importaciones, []),
    await consultar(SQL_CASHFLOW.cuentas, [cuentasPantalla]),
    await consultar(SQL_CASHFLOW.importes, [cuentasPantalla]),
    await consultar(SQL_CASHFLOW.saldos, [cuentasPantalla]),
  ];
  const deCuenta = (v: unknown) => {
    const c = texto(v, 'cuenta');
    if (!(cuentasPantalla as string[]).includes(c)) throw new Error('CASHFLOW_CUENTA_NO_PEDIDA');
    return c;
  };
  return {
    importaciones: imps.map((r): ImportacionCashflow => {
      if (typeof r.vigente !== 'boolean') throw new Error('CASHFLOW_VALOR_NO_VALIDO: vigente');
      const at = instante(r.importado_at);
      // El contrato no tiene identificador: el instante lo es.
      return { importacion_id: at, vigente: r.vigente, importado_at: at, origen: texto(r.origen, 'origen'), estado: texto(r.estado, 'estado') };
    }),
    cuentas: cuentas.map((r) => ({ codigo: deCuenta(r.codigo), farmacia: r.farmacia === null ? null : texto(r.farmacia, 'farmacia') })),
    importes: importes.map((r) => {
      const d = decena(r.decena_inicio, 'decena_inicio');
      if (!esDecenaInicio(d)) throw new Error('CASHFLOW_DECENA_NO_VALIDA');
      return {
        cuenta: deCuenta(r.cuenta), decena_inicio: d, decena_fin: decena(r.decena_fin, 'decena_fin'),
        categoria: texto(r.categoria, 'categoria'), concepto: texto(r.concepto, 'concepto'), importe: importeReal(r.importe, 'importe'),
      };
    }),
    saldos: saldos.map((r) => ({
      cuenta: deCuenta(r.cuenta), decena_inicio: decena(r.decena_inicio, 'decena_inicio'),
      saldo_formulas: importeReal(r.saldo_formulas, 'saldo_formulas'), saldo_bancos: importeReal(r.saldo_bancos, 'saldo_bancos'),
    })),
  };
}
