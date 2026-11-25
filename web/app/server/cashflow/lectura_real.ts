/**
 * H7-REAL: lecturas REAL del cashflow (migración 38, en producción) con cf_lectura. Solo SELECT, en una transacción READ
 * ONLY y REPEATABLE READ del llamador (una sola foto: la vigente y sus filas no pueden cambiar a mitad de la lectura).
 *
 *   1. Importaciones: la vigente (where vigente) y la última por importado_at (para el aviso de una ERROR posterior).
 *   2. Cuentas: cf_cashflow_cuentas (PIO, RITA, SL).
 *   3. Importes y saldos SOLO de la importación vigente y de las cuentas de la pantalla (PIO, RITA). Sin vigente, no se
 *      leen («Todavía no hay datos importados»).
 *   4. Otras cuentas (SL): solo recuentos de filas de la vigente, nunca importes.
 *
 * Falla cerrado: cualquier valor con forma inesperada, más de una vigente, una vigente que no es OK, una fila de otra
 * importación, una farmacia que no es la de su cuenta o un saldo repetido lanzan error (nunca se inventa un 0).
 */
import type { Fila, ValorDiagnostico } from '../contrato.ts';
import {
  CONFIG_CASHFLOW, CUENTAS_CASHFLOW, MESES_INDICADOR, calcularCashflow, comercialDeConcepto, esDecenaInicio, fechaMadrid, moverDecena, variacionMensual,
  type Celda, type ResultadoCashflow, type VencimientoCashflow,
  type CuentaCashflowFila, type DatosCashflow, type ImportacionCashflow, type ImporteCashflow, type OtraCuentaCashflow, type SaldoCashflow,
} from './cashflow.ts';

export const OBJETOS_CASHFLOW = ['cf_cashflow_importaciones', 'cf_cashflow_cuentas', 'cf_cashflow_importes', 'cf_cashflow_saldos'] as const;

/** importes, saldos y otras_cuentas: $1 = id de la importación vigente (uuid), $2 = cuentas de la pantalla (text[]). */
export const SQL_CASHFLOW = {
  importaciones: `select i.id::text as id, i.archivo_nombre, i.origen, i.estado, i.detalle_error::text as detalle_error, i.filas, i.importado_at, i.vigente
  from public.cf_cashflow_importaciones i
  where i.vigente
     or i.id = (select u.id from public.cf_cashflow_importaciones u order by u.importado_at desc, u.id desc limit 1)
  order by i.importado_at desc, i.id desc`,
  cuentas: `select c.codigo, c.farmacia
  from public.cf_cashflow_cuentas c
  order by c.codigo`,
  importes: `select m.id::text as id, m.importacion_id::text as importacion_id, m.cuenta, m.farmacia, m.decena_inicio::text as decena_inicio,
         m.decena_fin::text as decena_fin, m.categoria, m.concepto, m.importe::text as importe
  from public.cf_cashflow_importes m
  where m.importacion_id = $1::uuid and m.cuenta = any($2::text[])
  order by m.cuenta, m.decena_inicio, m.categoria, m.concepto nulls last, m.id`,
  saldos: `select s.id::text as id, s.importacion_id::text as importacion_id, s.cuenta, s.farmacia, s.decena_inicio::text as decena_inicio,
         s.saldo_inicial::text as saldo_inicial, s.saldo_formulas::text as saldo_formulas, s.saldo_bancos::text as saldo_bancos
  from public.cf_cashflow_saldos s
  where s.importacion_id = $1::uuid and s.cuenta = any($2::text[])
  order by s.cuenta, s.decena_inicio`,
  otras_cuentas: `select x.cuenta, sum(x.importes)::int as importes, sum(x.saldos)::int as saldos
  from (
    select m.cuenta, count(*) as importes, 0::bigint as saldos
      from public.cf_cashflow_importes m
     where m.importacion_id = $1::uuid and not (m.cuenta = any($2::text[]))
     group by m.cuenta
    union all
    select s.cuenta, 0::bigint, count(*)
      from public.cf_cashflow_saldos s
     where s.importacion_id = $1::uuid and not (s.cuenta = any($2::text[]))
     group by s.cuenta
  ) x
  group by x.cuenta
  order by x.cuenta`,
} as const;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
/** Largo máximo del detalle de error que se muestra (son códigos y celdas). */
export const LARGO_DETALLE_ERROR = 300;

function texto(v: unknown, campo: string): string {
  if (typeof v !== 'string' || v.trim() === '') throw new Error(`CASHFLOW_VALOR_NO_VALIDO: ${campo}`);
  return v;
}
function textoONull(v: unknown, campo: string): string | null {
  if (v === null || v === undefined) return null;
  if (typeof v !== 'string') throw new Error(`CASHFLOW_VALOR_NO_VALIDO: ${campo}`);
  return v.trim() === '' ? null : v;
}
function importeReal(v: unknown, campo: string): number | null {
  if (v === null || v === undefined) return null;
  const n = typeof v === 'number' ? v : typeof v === 'string' && /^-?\d+(\.\d+)?$/.test(v.trim()) ? Number(v) : NaN;
  if (!Number.isFinite(n)) throw new Error(`CASHFLOW_IMPORTE_NO_VALIDO: ${campo}`);
  return n;
}
function entero(v: unknown, campo: string): number {
  const n = typeof v === 'number' ? v : typeof v === 'string' && /^\d+$/.test(v.trim()) ? Number(v) : NaN;
  if (!Number.isSafeInteger(n) || n < 0) throw new Error(`CASHFLOW_VALOR_NO_VALIDO: ${campo}`);
  return n;
}
function decena(v: unknown, campo: string): string {
  const s = texto(v, campo).slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) throw new Error(`CASHFLOW_FECHA_NO_VALIDA: ${campo}`);
  return s;
}
/** timestamptz llega como texto de Postgres ("2026-11-10 07:45:00.123+00"): a ISO. */
function instante(v: unknown): string {
  const t = v instanceof Date ? v.getTime()
    : typeof v === 'string' ? Date.parse(v.trim().replace(' ', 'T').replace(/([+-]\d{2})$/, '$1:00')) : NaN;
  if (Number.isNaN(t)) throw new Error('CASHFLOW_FECHA_NO_VALIDA: importado_at');
  return new Date(t).toISOString();
}
function uuid(v: unknown, campo: string): string {
  const s = texto(v, campo);
  if (!UUID.test(s)) throw new Error(`CASHFLOW_VALOR_NO_VALIDO: ${campo}`);
  return s.toLowerCase();
}

function importacion(r: Fila): ImportacionCashflow {
  if (typeof r.vigente !== 'boolean') throw new Error('CASHFLOW_VALOR_NO_VALIDO: vigente');
  const estado = texto(r.estado, 'estado');
  if (estado !== 'OK' && estado !== 'ERROR') throw new Error('CASHFLOW_VALOR_NO_VALIDO: estado');
  const origen = texto(r.origen, 'origen');
  if (origen !== 'NOCHE' && origen !== 'MANUAL') throw new Error('CASHFLOW_VALOR_NO_VALIDO: origen');
  const detalle = textoONull(r.detalle_error, 'detalle_error');
  return {
    importacion_id: uuid(r.id, 'id'), archivo_nombre: texto(r.archivo_nombre, 'archivo_nombre'), origen, estado,
    // Solo en ERROR (códigos y celdas); en OK no se muestra aunque venga.
    detalle_error: estado === 'ERROR' && detalle !== null ? detalle.slice(0, LARGO_DETALLE_ERROR) : null,
    filas: r.filas === null || r.filas === undefined ? null : entero(r.filas, 'filas'),
    importado_at: instante(r.importado_at), vigente: r.vigente,
  };
}

/**
 * Ejecuta las lecturas con `consultar` (una transacción READ ONLY y REPEATABLE READ del llamador) y convierte las filas.
 */
export async function leerCashflowReal(consultar: (sql: string, params: unknown[]) => Promise<Fila[]>): Promise<DatosCashflow> {
  const cuentasPantalla = [...CUENTAS_CASHFLOW] as string[];
  const importaciones = (await consultar(SQL_CASHFLOW.importaciones, [])).map(importacion);
  const vigentes = importaciones.filter((i) => i.vigente);
  if (vigentes.length > 1) throw new Error('CASHFLOW_VARIAS_VIGENTES');
  const vigente = vigentes[0] ?? null;
  if (vigente !== null && vigente.estado !== 'OK') throw new Error('CASHFLOW_VIGENTE_NO_OK');
  if (importaciones.length > 2) throw new Error('CASHFLOW_IMPORTACIONES_INESPERADAS');

  const cuentas: CuentaCashflowFila[] = (await consultar(SQL_CASHFLOW.cuentas, [])).map((r) => {
    const codigo = texto(r.codigo, 'codigo');
    const farmacia = textoONull(r.farmacia, 'farmacia');
    // PIO y RITA son cada una su farmacia (falla cerrado).
    if (cuentasPantalla.includes(codigo) && farmacia !== codigo) throw new Error('CASHFLOW_FARMACIA_NO_CUADRA');
    return { codigo, farmacia };
  });
  if (vigente === null) return { importaciones, cuentas, importes: [], saldos: [], otras_cuentas: [] };

  const id = vigente.importacion_id;
  const params = [id, cuentasPantalla];
  const farmaciaDe = new Map(cuentas.map((c) => [c.codigo, c.farmacia]));
  const comunes = (r: Fila) => {
    const cuenta = texto(r.cuenta, 'cuenta');
    if (!cuentasPantalla.includes(cuenta)) throw new Error('CASHFLOW_CUENTA_NO_PEDIDA');
    if (uuid(r.importacion_id, 'importacion_id') !== id) throw new Error('CASHFLOW_OTRA_IMPORTACION');
    const farmacia = textoONull(r.farmacia, 'farmacia');
    if (!farmaciaDe.has(cuenta) || farmacia !== farmaciaDe.get(cuenta)) throw new Error('CASHFLOW_FARMACIA_NO_CUADRA');
    const d = decena(r.decena_inicio, 'decena_inicio');
    if (!esDecenaInicio(d)) throw new Error('CASHFLOW_DECENA_NO_VALIDA');
    return { id: texto(r.id, 'id'), importacion_id: id, cuenta, farmacia, decena_inicio: d };
  };
  const importes: ImporteCashflow[] = (await consultar(SQL_CASHFLOW.importes, params)).map((r) => ({
    ...comunes(r), decena_fin: decena(r.decena_fin, 'decena_fin'), categoria: texto(r.categoria, 'categoria'),
    concepto: textoONull(r.concepto, 'concepto'), importe: importeReal(r.importe, 'importe'),
  }));
  const vistos = new Set<string>();
  const saldos: SaldoCashflow[] = (await consultar(SQL_CASHFLOW.saldos, params)).map((r) => {
    const c = comunes(r);
    const k = `${c.cuenta}|${c.decena_inicio}`;
    if (vistos.has(k)) throw new Error('CASHFLOW_SALDO_REPETIDO');
    vistos.add(k);
    return {
      ...c, saldo_inicial: importeReal(r.saldo_inicial, 'saldo_inicial'), saldo_formulas: importeReal(r.saldo_formulas, 'saldo_formulas'),
      saldo_bancos: importeReal(r.saldo_bancos, 'saldo_bancos'),
    };
  });
  const otras_cuentas: OtraCuentaCashflow[] = (await consultar(SQL_CASHFLOW.otras_cuentas, params)).map((r) => {
    const cuenta = texto(r.cuenta, 'cuenta');
    if (cuentasPantalla.includes(cuenta)) throw new Error('CASHFLOW_CUENTA_NO_PEDIDA');
    return { cuenta, importes: entero(r.importes, 'importes'), saldos: entero(r.saldos, 'saldos') };
  });
  return { importaciones, cuentas, importes, saldos, otras_cuentas };
}

/** Cuentas con recuento propio en el diagnóstico; cualquier otra suma en «otras». */
const CUENTAS_DIAGNOSTICO = ['PIO', 'RITA', 'SL'] as const;

/** Etiqueta de diagnóstico de una categoría: minúsculas, sin tildes, `_` por lo demás (nunca un importe ni un concepto). */
export function claveCategoria(categoria: string): string {
  const s = categoria.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  return (s === '' ? 'sin_nombre' : s).slice(0, 60);
}
const normalDiag = (s: string | null) => (s ?? '').normalize('NFD').replace(/\p{M}/gu, '').toUpperCase().replace(/\s+/g, ' ').trim();
/** Categoría canónica del efectivo y textos que lo delatan en otra categoría o en el concepto (COBRO EFECTIU…). */
const CATEGORIA_EFECTIVO = 'RE COBRO EFECTIVO';
const PARECE_EFECTIVO = /EFECTIU|EFECTIVO|METAL·?LIC|METALICO/;

/**
 * check:real: diagnóstico del cashflow, solo números y sí/no (nunca importes, conceptos ni detalle de errores):
 * vigente sí/no, días desde la vigente, última ERROR sí/no, filas de importes y saldos por cuenta, decenas reales con
 * diferencia banco/fórmulas (E7) y decenas que no cuadran.
 * H7-REAL-2: por cuenta (PIO, RITA) y categoría, nº de importes reales (decena con saldo de banco) y anotados a futuro:
 * `cat_<cuenta>_<categoría>_reales|_futuros` (la etiqueta de la categoría, nunca el concepto ni el importe). Efectivo:
 * `efectivo_<cuenta>_reales|_futuros` (categoría «RE Cobro efectivo») y `efectivo_<cuenta>_en_otra_categoria` (filas
 * cuyo concepto o categoría parecen efectivo, p. ej. «COBRO EFECTIU», pero con otra categoría).
 */
export function diagnosticoCashflow(d: DatosCashflow, hoy: string, vencimientos: readonly VencimientoCashflow[] = []): Record<string, ValorDiagnostico> {
  const r = calcularCashflow({ ...d, hoy, vencimientos: [...vencimientos] });
  const vigente = r.importacion.vigente;
  const out: Record<string, ValorDiagnostico> = { vigente: vigente !== null };
  if (vigente !== null) {
    const fv = fechaMadrid(vigente.importado_at);
    out.dias_desde_vigente = fv === null ? 0 : Math.max(0, Math.round((Date.parse(`${hoy}T00:00:00Z`) - Date.parse(`${fv}T00:00:00Z`)) / 86400000));
  }
  out.ultima_error = r.importacion.ultima !== null && r.importacion.ultima.estado === 'ERROR';
  const cuenta = (c: string) => ((CUENTAS_DIAGNOSTICO as readonly string[]).includes(c) ? c.toLowerCase() : 'otras');
  for (const c of [...CUENTAS_DIAGNOSTICO.map((x) => x.toLowerCase()), 'otras']) { out[`importes_${c}`] = 0; out[`saldos_${c}`] = 0; }
  const sumar = (k: string, n: number) => { out[k] = (out[k] as number) + n; };
  for (const f of d.importes) sumar(`importes_${cuenta(f.cuenta)}`, 1);
  for (const s of d.saldos) sumar(`saldos_${cuenta(s.cuenta)}`, 1);
  for (const o of d.otras_cuentas) { sumar(`importes_${cuenta(o.cuenta)}`, o.importes); sumar(`saldos_${cuenta(o.cuenta)}`, o.saldos); }
  let dif = 0;
  let noCuadran = 0;
  for (const c of CUENTAS_CASHFLOW) {
    const v = r.vistas[c];
    if (!v) continue;
    for (const x of Object.values(v.decenas)) {
      if (x.diferencia_banco !== null) dif += 1;
      if (x.cuadra === false) noCuadran += 1;
    }
  }
  out.decenas_diferencia_banco_formulas = dif;
  out.decenas_no_cuadran = noCuadran;
  for (const c of CUENTAS_CASHFLOW) {
    const k = c.toLowerCase();
    out[`efectivo_${k}_reales`] = 0;
    out[`efectivo_${k}_futuros`] = 0;
    out[`efectivo_${k}_en_otra_categoria`] = 0;
  }
  const porCategoria = new Map<string, number>();
  for (const f of d.importes) {
    if (!(CUENTAS_CASHFLOW as readonly string[]).includes(f.cuenta)) continue;
    const k = f.cuenta.toLowerCase();
    const ultima = r.vistas[f.cuenta as (typeof CUENTAS_CASHFLOW)[number]]?.ultima_real ?? null;
    const cuando = ultima !== null && f.decena_inicio <= ultima ? 'reales' : 'futuros';
    const clave = `cat_${k}_${claveCategoria(f.categoria)}_${cuando}`;
    porCategoria.set(clave, (porCategoria.get(clave) ?? 0) + 1);
    if (normalDiag(f.categoria) === CATEGORIA_EFECTIVO) sumar(`efectivo_${k}_${cuando}`, 1);
    else if (PARECE_EFECTIVO.test(normalDiag(f.categoria)) || PARECE_EFECTIVO.test(normalDiag(f.concepto))) sumar(`efectivo_${k}_en_otra_categoria`, 1);
  }
  for (const [clave, n] of [...porCategoria].sort(([a], [b]) => a.localeCompare(b))) out[clave] = n;

  // H7-REAL-5: vencimientos como mínimo. Por cuenta y concepto con vencimientos (su nombre comercial de
  // CORRESPONDENCIAS_PROVEEDOR, nunca el texto del Excel): decenas futuras en que ganó la media y en que ganaron los
  // vencimientos. Indicador consolidado (variación media mensual, real 12 meses y prevista 12 meses) antes y después del
  // cambio, en euros enteros sin signo + sí/no «negativa» (la barrera de check:real solo admite enteros ≥ 0).
  out.vencimientos_leidos = vencimientos.length;
  const gana = new Map<string, number>();
  for (const c of CUENTAS_CASHFLOW) {
    for (const l of r.vistas[c]?.lineas ?? []) {
      for (const x of Object.values(l.celdas)) {
        if (x.real || x.vencimientos === null) continue;
        const k = `${claveCategoria(x.vencimientos.comercial)}_${c.toLowerCase()}`;
        // H7-REAL-8: la previsión base que gana puede ser la media, el Excel o el apunte manual.
        for (const q of ['gana_media', 'gana_excel', 'gana_manual', 'ganan_vencimientos']) if (!gana.has(`venc_${q}_${k}`)) gana.set(`venc_${q}_${k}`, 0);
        const q = `venc_${x.fuente === 'VENCIMIENTOS' ? 'ganan_vencimientos' : `gana_${x.fuente.toLowerCase()}`}_${k}`;
        gana.set(q, (gana.get(q) as number) + 1);
      }
    }
  }
  for (const [k, n] of [...gana].sort(([a], [b]) => a.localeCompare(b))) out[k] = n;
  // H7-REAL-9: Excel frente a media del concepto (gana el mayor en valor absoluto), por cuenta y mayorista (su nombre
  // comercial de CORRESPONDENCIAS_PROVEEDOR, nunca el texto del Excel): decenas futuras en que ganó cada uno.
  const frente = new Map<string, number>();
  for (const c of CUENTAS_CASHFLOW) {
    for (const l of r.vistas[c]?.lineas ?? []) {
      const comercial = comercialDeConcepto(l.concepto);
      if (comercial === null || !MAYORISTAS.includes(comercial)) continue;
      const k = `${claveCategoria(comercial)}_${c.toLowerCase()}`;
      for (const q of ['excel_gana_media', 'media_gana_excel']) if (!frente.has(`${q}_${k}`)) frente.set(`${q}_${k}`, 0);
      for (const x of Object.values(l.celdas)) {
        if (x.real || x.frente === null) continue;
        const q = `${Math.abs(x.frente.media) > Math.abs(x.frente.excel) ? 'media_gana_excel' : 'excel_gana_media'}_${k}`;
        frente.set(q, (frente.get(q) as number) + 1);
      }
    }
  }
  for (const [k, n] of [...frente].sort(([a], [b]) => a.localeCompare(b))) out[k] = n;
  const antes = calcularCashflow({ ...d, hoy, vencimientos: [...vencimientos], config: { ...CONFIG_CASHFLOW, vencimientos_como_minimo: false } });
  for (const [cuando, x] of [['antes', antes], ['despues', r]] as const) {
    const v = variacionMensual(x.vistas.CONSOLIDADO, x.decenas);
    for (const [tramo, t] of [['real', v.real], ['prevista', v.prevista]] as const) {
      out[`indicador_${cuando}_${tramo}_disponible`] = t !== null;
      if (t === null) continue;
      out[`indicador_${cuando}_${tramo}_eur_mes`] = Math.round(Math.abs(t.por_mes));
      out[`indicador_${cuando}_${tramo}_negativa`] = t.por_mes < 0;
    }
  }
  Object.assign(out, diagnosticoPrevision(r, vencimientos));
  // H7-REAL-8: media de 3 meses (la anterior) frente a la de 12 (decisión de Pío, 25/11/2026): indicador consolidado y
  // variación prevista por cuenta, mismo formato (entero sin signo + _negativa).
  const r3 = calcularCashflow({ ...d, hoy, vencimientos: [...vencimientos], config: { ...CONFIG_CASHFLOW, meses_media: 3 } });
  const r12 = CONFIG_CASHFLOW.meses_media === 12 ? r : calcularCashflow({ ...d, hoy, vencimientos: [...vencimientos], config: { ...CONFIG_CASHFLOW, meses_media: 12 } });
  for (const [m, x] of [['media3', r3], ['media12', r12]] as const) {
    const v = variacionMensual(x.vistas.CONSOLIDADO, x.decenas);
    eurMes(out, `indicador_${m}_real`, v.real === null ? null : Math.round(v.real.por_mes * 100));
    eurMes(out, `indicador_${m}_prevista`, v.prevista === null ? null : Math.round(v.prevista.por_mes * 100));
    for (const c of CUENTAS_CASHFLOW) {
      const vc = x.vistas[c];
      const t = vc ? variacionMensual(vc, x.decenas).prevista : null;
      eurMes(out, `prev_${c.toLowerCase()}_variacion_prevista_${m}`, t === null ? null : Math.round(t.por_mes * 100));
    }
  }
  return out;
}

/** Fuente de una cifra prevista, para la «fuente dominante» del diagnóstico (minúsculas: etiqueta permitida). */
function fuenteDiagnostico(c: Celda): string {
  if (c.fuente === 'MEDIA') return c.media?.regla === 'ANIO_ANTERIOR' ? 'anio_anterior' : 'media';
  return c.fuente.toLowerCase();
}
/** Importe mensual en euros enteros sin signo + sí/no «negativa» (la barrera de check:real solo admite enteros ≥ 0). */
function eurMes(out: Record<string, ValorDiagnostico>, k: string, centimosMes: number | null): void {
  out[`${k}_disponible`] = centimosMes !== null;
  if (centimosMes === null) return;
  out[`${k}_eur_mes`] = Math.round(Math.abs(centimosMes) / 100);
  out[`${k}_negativa`] = centimosMes < 0;
}
/** H7-REAL-9: mayoristas (nombre comercial de CORRESPONDENCIAS_PROVEEDOR) del diagnóstico «Excel frente a media». */
export const MAYORISTAS: readonly string[] = ['ALLIANCE', 'HEFAME', 'COFARES', 'FEDEFARMA', 'LOGISTA PHARMA'];
/** Hasta 10 categorías por cuenta en «mayor diferencia». */
export const TOP_DIFERENCIA_PREVISION = 10;
/** H7-REAL-7: proveedores del grupo KENVUE (decisión de Pío, 25/11/2026) en los vencimientos: por el nombre. */
const PARECE_KENVUE = /JNTL|KENVUE|J(OH|HO)NSON/;

/**
 * H7-REAL-7: diagnóstico de la previsión (solo informa; no cambia ninguna regla). Ventanas del indicador: los 12 meses
 * reales hasta la última decena real de la cuenta y los 12 previstos tras ella (o lo que haya). Por cuenta (PIO, RITA) y
 * categoría (sin los traspasos internos, neutros), lo que entra en el saldo:
 *   prev_<cuenta>_<categoría>_real|_prevista: media mensual (`_eur_mes` entero sin signo, `_negativa`, `_disponible`);
 *   prev_<cuenta>_<categoría>_fuente: fuente dominante de la previsión (vencimientos, manual, excel, media, anio_anterior;
 *     ninguna si no hay previsión), por importe absoluto;
 *   prev_<cuenta>_top_diferencia: las 10 categorías con mayor |prevista − real| mensual, de mayor a menor;
 *   prev_<cuenta>_variacion_real|_prevista: variación media mensual del saldo de la cuenta (como el indicador);
 *   prev_<cuenta>_solo_prevision / _solo_real: categorías con previsión y ningún real en 12 meses, y al revés.
 * Equivalencias de concepto: `equivalencias_filas_<cuenta>` (filas del Excel sumadas bajo otro nombre) y, de los
 * vencimientos del sistema que parecen KENVUE por el nombre, cuántos tienen nombre comercial KENVUE y cuántos no.
 * Nunca un concepto ni un proveedor por su nombre: categorías como etiqueta (claveCategoria).
 */
export function diagnosticoPrevision(r: ResultadoCashflow, vencimientos: readonly VencimientoCashflow[]): Record<string, ValorDiagnostico> {
  const out: Record<string, ValorDiagnostico> = {};
  for (const cuenta of CUENTAS_CASHFLOW) {
    const k = cuenta.toLowerCase();
    const v = r.vistas[cuenta];
    const L = v?.ultima_real ?? null;
    out[`prev_${k}_disponible`] = v !== undefined && L !== null;
    if (!v || L === null) continue;
    const desde = moverDecena(L, -3 * MESES_INDICADOR);
    const hasta = moverDecena(L, 3 * MESES_INDICADOR);
    const reales = r.decenas.filter((x) => x > desde && x <= L && v.decenas[x]?.real);
    const previstas = r.decenas.filter((x) => x > L && x <= hasta);
    const cats = new Map<string, { real: number; prev: number; nReal: number; fuentes: Map<string, number> }>();
    for (const l of v.lineas) {
      if (l.clase === 'TRASPASO') continue;
      const ck = claveCategoria(l.clase === 'TRASPASO_EXTERNO' ? `${l.categoria} externo` : l.categoria);
      const x = cats.get(ck) ?? { real: 0, prev: 0, nReal: 0, fuentes: new Map<string, number>() };
      cats.set(ck, x);
      for (const dd of reales) {
        const c = l.celdas[dd];
        if (!c || !c.en_saldo || c.importe === null) continue;
        x.real += Math.round(c.importe * 100);
        x.nReal += 1;
      }
      for (const dd of previstas) {
        const c = l.celdas[dd];
        if (!c || !c.en_saldo || c.importe === null) continue;
        const ct = Math.round(c.importe * 100);
        x.prev += ct;
        const f = fuenteDiagnostico(c);
        x.fuentes.set(f, (x.fuentes.get(f) ?? 0) + Math.abs(ct));
      }
    }
    const mesesReal = reales.length / 3;
    const mesesPrev = previstas.length / 3;
    const diferencias: { ck: string; dif: number }[] = [];
    const soloPrev: string[] = [];
    const soloReal: string[] = [];
    for (const [ck, x] of [...cats].sort(([a], [b]) => a.localeCompare(b))) {
      const realMes = mesesReal > 0 ? x.real / mesesReal : null;
      const prevMes = mesesPrev > 0 ? x.prev / mesesPrev : null;
      eurMes(out, `prev_${k}_${ck}_real`, realMes);
      eurMes(out, `prev_${k}_${ck}_prevista`, prevMes);
      const dom = [...x.fuentes].filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0];
      out[`prev_${k}_${ck}_fuente`] = [dom ? dom[0] : 'ninguna'];
      diferencias.push({ ck, dif: Math.abs((prevMes ?? 0) - (realMes ?? 0)) });
      const hayPrev = [...x.fuentes.values()].some((n) => n > 0);
      if (hayPrev && x.nReal === 0) soloPrev.push(ck);
      if (!hayPrev && x.nReal > 0) soloReal.push(ck);
    }
    out[`prev_${k}_top_diferencia`] = diferencias.sort((a, b) => b.dif - a.dif || a.ck.localeCompare(b.ck)).slice(0, TOP_DIFERENCIA_PREVISION).map((x) => x.ck);
    out[`prev_${k}_solo_prevision`] = soloPrev;
    out[`prev_${k}_solo_real`] = soloReal;
    const vm = variacionMensual(v, r.decenas);
    eurMes(out, `prev_${k}_variacion_real`, vm.real === null ? null : Math.round(vm.real.por_mes * 100));
    eurMes(out, `prev_${k}_variacion_prevista`, vm.prevista === null ? null : Math.round(vm.prevista.por_mes * 100));
  }
  for (const cuenta of CUENTAS_CASHFLOW) out[`equivalencias_filas_${cuenta.toLowerCase()}`] = r.equivalencias.filas[cuenta] ?? 0;
  // H7-REAL-8: pares no fusionados por un prefijo que coincide con varios nombres o con ninguno (falla cerrado).
  out.equivalencias_ambiguas = r.equivalencias.ambiguas;
  out.equivalencias_sin_coincidencia = r.equivalencias.sin_coincidencia;
  const kenvue = vencimientos.filter((x) => PARECE_KENVUE.test(normalDiag(x.proveedor_nombre)) || x.proveedor_comercial === 'KENVUE');
  out.kenvue_venc_con_comercial = kenvue.filter((x) => x.proveedor_comercial === 'KENVUE').length;
  out.kenvue_venc_sin_comercial = kenvue.filter((x) => x.proveedor_comercial !== 'KENVUE').length;
  return out;
}
