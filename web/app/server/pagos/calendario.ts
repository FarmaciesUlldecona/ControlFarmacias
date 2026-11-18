/**
 * H6-4: vencimientos en calendario. Agregación por día, semana (lunes a domingo), mes y año, peor estado del periodo,
 * rejilla del mes y filtro de la lista por un periodo del calendario. Módulo puro (front y pruebas).
 *
 * Total de un periodo = misma regla de totales de H6 (bloqueTotal): cargos − |abonos|; no suman los importes
 * pendientes, el sentido no documentado ni los cargos con importe negativo, que se cuentan aparte. Incluye lo ya
 * pagado: es todo lo que vence ese día. null si nada suma (nunca un 0 inventado).
 *
 * Color del periodo = peor estado (decisión de Marc): VENCIDO_SIN_PAGAR (rojo) > A_REVISAR (naranja, H6-REAL) >
 * DOMICILIADO_PREVISTO (violeta) > ABONO_PENDIENTE_COMPENSAR (azul) > PENDIENTE (neutro) > pagado (verde).
 *
 * Los vencimientos sin fecha no caben en el calendario: se cuentan aparte (sinFecha).
 *
 * H6-5: un día con pagos se marca siempre (color y globo), aunque nada sume; entonces dice por qué (textoSinTotal).
 * Resumen del periodo visible por grupos de estado que cuadran con el total (resumenPeriodo) y fechas con pagos fuera
 * del periodo visible (vecinosConPagos).
 *
 * Solo sintaxis TypeScript borrable.
 */
import {
  bloqueDe, bloqueTotal, esFechaIso, excluidosTotal, lunesIso, sumarDiasIso,
  type BloqueTotal, type EstadoPagoVencimiento, type FilaVencimientoPago,
} from './pagos.ts';

// ---------------------------------------------------------------------------
// Peor estado y color
// ---------------------------------------------------------------------------

/** Del peor al mejor. Pagado (a mano o por banco) es el mejor. */
export const ORDEN_PEOR: readonly EstadoPagoVencimiento[] = [
  'VENCIDO_SIN_PAGAR', 'A_REVISAR', 'DOMICILIADO_PREVISTO', 'ABONO_PENDIENTE_COMPENSAR', 'PENDIENTE', 'PAGADO_MANUAL', 'PAGADO_BANCO',
];
export type ColorDia = 'rojo' | 'naranja' | 'domiciliado' | 'azul' | 'neutro' | 'verde';
export const COLOR_DIA: Readonly<Record<EstadoPagoVencimiento, ColorDia>> = {
  VENCIDO_SIN_PAGAR: 'rojo', A_REVISAR: 'naranja', DOMICILIADO_PREVISTO: 'domiciliado', ABONO_PENDIENTE_COMPENSAR: 'azul',
  PENDIENTE: 'neutro', PAGADO_MANUAL: 'verde', PAGADO_BANCO: 'verde',
};
/** Leyenda del calendario, en el orden de prioridad. */
export const LEYENDA_COLOR: readonly { color: ColorDia; texto: string }[] = [
  { color: 'rojo', texto: 'Vencido sin pagar' },
  { color: 'naranja', texto: 'Marca a revisar' },
  { color: 'domiciliado', texto: 'Domiciliado previsto' },
  { color: 'azul', texto: 'Abono pendiente de compensar' },
  { color: 'neutro', texto: 'Pendiente' },
  { color: 'verde', texto: 'Pagado' },
];

/** Peor estado de un conjunto (null si está vacío). */
export function peorEstado(estados: Iterable<EstadoPagoVencimiento>): EstadoPagoVencimiento | null {
  let peor: EstadoPagoVencimiento | null = null;
  for (const e of estados) if (peor === null || ORDEN_PEOR.indexOf(e) < ORDEN_PEOR.indexOf(peor)) peor = e;
  return peor;
}

// ---------------------------------------------------------------------------
// Fechas
// ---------------------------------------------------------------------------

export type Escala = 'dia' | 'semana' | 'mes' | 'anio';
const fechaDe = (x: { fecha_vencimiento: string | null }) => x.fecha_vencimiento?.slice(0, 10) ?? null;

export function primeroDeMes(f: string): string { return `${f.slice(0, 7)}-01`; }
export function ultimoDeMes(f: string): string {
  const [a, m] = f.slice(0, 7).split('-').map(Number);
  return new Date(Date.UTC(a, m, 0)).toISOString().slice(0, 10);
}
export function sumarMeses(f: string, n: number): string {
  const [a, m] = f.slice(0, 7).split('-').map(Number);
  const d = new Date(Date.UTC(a, m - 1 + n, 1));
  return d.toISOString().slice(0, 10);
}

/** Clave del periodo que contiene una fecha: el día, el lunes de la semana, YYYY-MM o YYYY. */
export function claveDe(fecha: string, escala: Escala): string {
  if (escala === 'dia') return fecha.slice(0, 10);
  if (escala === 'semana') return lunesIso(fecha.slice(0, 10));
  return escala === 'mes' ? fecha.slice(0, 7) : fecha.slice(0, 4);
}

/** Primer y último día (inclusive) del periodo de una clave. */
export function rangoDe(clave: string, escala: Escala): { desde: string; hasta: string } {
  if (escala === 'dia') return { desde: clave, hasta: clave };
  if (escala === 'semana') return { desde: clave, hasta: sumarDiasIso(clave, 6) };
  if (escala === 'mes') return { desde: `${clave}-01`, hasta: ultimoDeMes(`${clave}-01`) };
  return { desde: `${clave}-01-01`, hasta: `${clave}-12-31` };
}

/** Semanas (lunes a domingo) que cubren el mes de la fecha: 4 a 6 filas de 7 días. */
export function rejillaMes(fecha: string): string[][] {
  const fin = ultimoDeMes(fecha);
  const semanas: string[][] = [];
  for (let l = lunesIso(primeroDeMes(fecha)); l <= fin; l = sumarDiasIso(l, 7)) {
    semanas.push(Array.from({ length: 7 }, (_, i) => sumarDiasIso(l, i)));
  }
  return semanas;
}

/** Número de semana ISO 8601 de una fecha. */
export function semanaIso(fecha: string): number {
  const d = new Date(`${fecha.slice(0, 10)}T00:00:00Z`);
  const jueves = new Date(d);
  jueves.setUTCDate(d.getUTCDate() + 3 - ((d.getUTCDay() + 6) % 7));
  const enero4 = new Date(Date.UTC(jueves.getUTCFullYear(), 0, 4));
  return 1 + Math.round(((jueves.getTime() - enero4.getTime()) / 86400000 - 3 + ((enero4.getUTCDay() + 6) % 7)) / 7);
}

// ---------------------------------------------------------------------------
// Vistas del calendario
// ---------------------------------------------------------------------------

export const VISTAS_CALENDARIO = [
  { v: 'dia', texto: 'Día' }, { v: 'semana', texto: 'Semana' }, { v: 'mes', texto: 'Mes' }, { v: 'anio', texto: 'Año' },
] as const;
export type VistaCalendario = (typeof VISTAS_CALENDARIO)[number]['v'];
export const VISTA_POR_DEFECTO: VistaCalendario = 'mes';
export function esVista(v: unknown): v is VistaCalendario {
  return VISTAS_CALENDARIO.some((x) => x.v === v);
}

/** Periodo que muestra una vista anclada en una fecha. */
export function periodoVista(vista: VistaCalendario, fecha: string): { desde: string; hasta: string } {
  return rangoDe(claveDe(fecha, vista), vista);
}
/** Fecha ancla tras avanzar n periodos (n negativo: atrás). */
export function moverVista(vista: VistaCalendario, fecha: string, n: number): string {
  if (vista === 'dia') return sumarDiasIso(fecha, n);
  if (vista === 'semana') return sumarDiasIso(lunesIso(fecha), 7 * n);
  if (vista === 'mes') return sumarMeses(fecha, n);
  return `${Number(fecha.slice(0, 4)) + n}-01-01`;
}

// ---------------------------------------------------------------------------
// Agregación
// ---------------------------------------------------------------------------

export type FilaCalendario = Pick<FilaVencimientoPago, 'fecha_vencimiento' | 'importe' | 'sentido' | 'estado_pago' | 'forma_pago'>;

export interface ResumenCalendario {
  clave: string;
  desde: string;
  hasta: string;
  /** Todos los vencimientos del periodo (también los que no suman): el número del globo. */
  pagos: number;
  /** Cargos − |abonos| de lo que suma; neto null si nada suma. */
  total: BloqueTotal;
  sin_importe: number;
  sentido_no_documentado: number;
  cargo_negativo: number;
  peor: EstadoPagoVencimiento | null;
  color: ColorDia | null;
}

/** Resumen de un periodo con sus filas (ya filtradas por fecha). */
export function resumir(filas: readonly FilaCalendario[], clave: string, escala: Escala): ResumenCalendario {
  const peor = peorEstado(filas.map((f) => f.estado_pago));
  return {
    clave, ...rangoDe(clave, escala),
    pagos: filas.length,
    total: bloqueTotal(filas),
    ...excluidosTotal(filas),
    peor, color: peor === null ? null : COLOR_DIA[peor],
  };
}

/** Filas agrupadas por la clave del periodo (sin fecha: fuera). */
export function agrupar<T extends Pick<FilaCalendario, 'fecha_vencimiento'>>(filas: readonly T[], escala: Escala): Map<string, T[]> {
  const m = new Map<string, T[]>();
  for (const f of filas) {
    const fecha = fechaDe(f);
    if (fecha === null) continue;
    const k = claveDe(fecha, escala);
    const g = m.get(k);
    if (g) g.push(f); else m.set(k, [f]);
  }
  return m;
}

/** Resumen de cada periodo con vencimientos (solo los que tienen alguno). */
export function agregar(filas: readonly FilaCalendario[], escala: Escala): Map<string, ResumenCalendario> {
  return new Map([...agrupar(filas, escala)].map(([k, g]) => [k, resumir(g, k, escala)]));
}

/** Vencimientos sin fecha: no aparecen en el calendario. */
export function sinFecha(filas: readonly Pick<FilaCalendario, 'fecha_vencimiento'>[]): number {
  return filas.filter((f) => fechaDe(f) === null).length;
}

export type Intensidad = 0 | 1 | 2 | 3 | 4;
export interface MesDelAnio extends ResumenCalendario {
  /** 0 = sin importe que sume; 1–4 = cuartos del mayor |total| mensual del año. */
  intensidad: Intensidad;
}

/** Los 12 meses de un año (también los vacíos) con su intensidad por importe. */
export function resumenAnio(filas: readonly FilaCalendario[], anio: string): MesDelAnio[] {
  const porMes = agrupar(filas.filter((f) => fechaDe(f)?.slice(0, 4) === anio), 'mes');
  const meses = Array.from({ length: 12 }, (_, i) => {
    const k = `${anio}-${String(i + 1).padStart(2, '0')}`;
    return resumir(porMes.get(k) ?? [], k, 'mes');
  });
  const max = Math.max(0, ...meses.map((m) => Math.abs(m.total.neto ?? 0)));
  return meses.map((m) => {
    const a = Math.abs(m.total.neto ?? 0);
    const intensidad = (max === 0 || a === 0 ? 0 : Math.min(4, Math.max(1, Math.ceil((4 * a) / max)))) as Intensidad;
    return { ...m, intensidad };
  });
}

// ---------------------------------------------------------------------------
// H6-5: periodo sin total, resumen del periodo visible y periodos vecinos con pagos
// ---------------------------------------------------------------------------

/**
 * Texto de un periodo con pagos pero sin nada que sume (total null): lo que lo impide, nunca «—» ni 0. Prioridad:
 * importe pendiente > cargo con importe negativo > sentido no documentado. null si algo suma o no hay pagos.
 */
export function textoSinTotal(r: Pick<ResumenCalendario, 'total' | 'sin_importe' | 'cargo_negativo' | 'sentido_no_documentado'>): { largo: string; corto: string } | null {
  if (r.total.neto !== null) return null;
  if (r.sin_importe > 0) return { largo: 'importe pendiente', corto: 'pend.' };
  if (r.cargo_negativo > 0) return { largo: 'importe negativo', corto: 'neg.' };
  if (r.sentido_no_documentado > 0) return { largo: 'sentido no documentado', corto: 'no doc.' };
  return null;
}

/**
 * Grupos del resumen del periodo (H6-6, decisión de Marc: por ESTADO, la misma regla que la cabecera de totales,
 * bloqueDe). Pagado = PAGADO_MANUAL y PAGADO_BANCO; Domiciliado previsto = solo DOMICILIADO_PREVISTO (domiciliado y ya
 * vencido, sin marca); Falta por pagar = PENDIENTE (no vencido, cualquier forma, también domiciliación) +
 * VENCIDO_SIN_PAGAR; Abonos pendientes de compensar = ABONO_PENDIENTE_COMPENSAR (aparte). Un vencimiento, un grupo.
 */
export type GrupoResumen = 'pagado' | 'domiciliado' | 'falta' | 'abonos' | 'revisar';
/** H6-REAL: «A revisar» (marca que ya no coincide con el vencimiento), su propio grupo: nunca como pagado. */
export const GRUPOS_RESUMEN: readonly GrupoResumen[] = ['pagado', 'domiciliado', 'falta', 'abonos', 'revisar'];
export function grupoResumen(f: Pick<FilaCalendario, 'estado_pago'>): GrupoResumen {
  const b = bloqueDe(f);
  return b === 'por_pagar' ? 'falta' : b;
}
export interface GrupoResumenPeriodo extends BloqueTotal {
  /** Todos los vencimientos del grupo (también los que no suman). */
  pagos: number;
}
export interface ResumenPeriodo {
  desde: string;
  hasta: string;
  pagos: number;
  /** Misma regla de totales de H6; neto null si nada suma. */
  total: BloqueTotal;
  grupos: Record<GrupoResumen, GrupoResumenPeriodo>;
  sin_importe: number;
  sentido_no_documentado: number;
  cargo_negativo: number;
  /** Pagado + Domiciliado + Falta por pagar + Abonos = Total (al céntimo). */
  cuadra: boolean;
}
const centimos = (v: number | null) => Math.round((v ?? 0) * 100);

/** Resumen de los vencimientos con fecha en [desde, hasta] (los sin fecha no entran en ningún periodo). */
export function resumenPeriodo(filas: readonly FilaCalendario[], desde: string, hasta: string): ResumenPeriodo {
  const en = filas.filter((f) => { const x = fechaDe(f); return x !== null && x >= desde && x <= hasta; });
  const grupos = Object.fromEntries(GRUPOS_RESUMEN.map((g) => {
    const fs = en.filter((f) => grupoResumen(f) === g);
    return [g, { ...bloqueTotal(fs), pagos: fs.length }];
  })) as Record<GrupoResumen, GrupoResumenPeriodo>;
  const total = bloqueTotal(en);
  const cuadra = centimos(total.neto) === GRUPOS_RESUMEN.reduce((s, g) => s + centimos(grupos[g].neto), 0);
  return { desde, hasta, pagos: en.length, total, grupos, ...excluidosTotal(en), cuadra };
}

/**
 * Fechas con pagos más cercanas fuera de [desde, hasta]: para avisar cuando el periodo visible está vacío pero lo
 * filtrado tiene pagos en otras fechas (p. ej. «Vencido sin pagar» siempre cae antes de hoy).
 */
export function vecinosConPagos(filas: readonly Pick<FilaCalendario, 'fecha_vencimiento'>[], desde: string, hasta: string): { antes: string | null; despues: string | null; fuera: number } {
  let antes: string | null = null;
  let despues: string | null = null;
  let fuera = 0;
  for (const f of filas) {
    const x = fechaDe(f);
    if (x === null || (x >= desde && x <= hasta)) continue;
    fuera += 1;
    if (x < desde && (antes === null || x > antes)) antes = x;
    if (x > hasta && (despues === null || x < despues)) despues = x;
  }
  return { antes, despues, fuera };
}

// ---------------------------------------------------------------------------
// Filtro de la lista por un periodo del calendario (?cal=dia:2026-11-04 | semana:2026-11-02 | mes:2026-11)
// ---------------------------------------------------------------------------

export interface FiltroCalendario { escala: 'dia' | 'semana' | 'mes'; clave: string; desde: string; hasta: string }

/** Lee el parámetro; falla cerrado: cualquier valor no válido no filtra (null). */
export function leerFiltroCalendario(valor: string | null): FiltroCalendario | null {
  if (!valor) return null;
  const [escala, clave, ...resto] = valor.split(':');
  if (resto.length || !clave) return null;
  if (escala === 'dia' && esFechaIso(clave)) return { escala, clave, ...rangoDe(clave, 'dia') };
  if (escala === 'semana' && esFechaIso(clave) && lunesIso(clave) === clave) return { escala, clave, ...rangoDe(clave, 'semana') };
  if (escala === 'mes' && /^\d{4}-\d{2}$/.test(clave) && esFechaIso(`${clave}-01`)) return { escala, clave, ...rangoDe(clave, 'mes') };
  return null;
}
export function valorFiltroCalendario(escala: FiltroCalendario['escala'], clave: string): string {
  return `${escala}:${clave}`;
}
/** true si el vencimiento cae en el periodo (sin fecha: nunca). */
export function cumpleCalendario(x: Pick<FilaCalendario, 'fecha_vencimiento'>, filtro: FiltroCalendario | null): boolean {
  if (filtro === null) return true;
  const f = fechaDe(x);
  return f !== null && f >= filtro.desde && f <= filtro.hasta;
}
