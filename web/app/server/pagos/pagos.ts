/**
 * H6: pantalla Vencimientos. Estados de pago por vencimiento, forma de pago por proveedor (por CIF), marcas de pago
 * manuales, totales por semana y mes, y filtros. Módulo puro: lo usan el servidor (rutas y almacén en memoria de
 * FIXTURES) y el front (filtros y totales sobre lo filtrado).
 *
 * Excepción autorizada por Marc: la web podrá escribir SOLO en tablas nuevas de marcas de pago y forma de pago por
 * proveedor (rol propio, a crear por el circuito); nunca en facturas, vencimientos ni conciliación. En H6, solo
 * FIXTURES: en REAL la lista y los estados son de solo lectura (cf_lectura) y la escritura responde 503
 * «Pendiente de tablas en Supabase» (propuesta: docs/propuesta_tablas_h6_pagos.sql, sin aplicar).
 *
 * Estados (por vencimiento):
 *   PENDIENTE             no vencido y sin marca (también sin fecha: no se puede afirmar que haya vencido).
 *   VENCIDO_SIN_PAGAR     vencido, forma no domiciliada (TRANSFERENCIA, EFECTIVO, COMPENSACION_ABONO o sin
 *                         determinar por falta de CIF) y sin marca. Rojo.
 *   DOMICILIADO_PREVISTO  vencido, forma DOMICILIACION y sin marca. Color propio (no rojo).
 *   PAGADO_MANUAL         con marca vigente: «pagado (marcado a mano)», fecha y forma.
 *   PAGADO_BANCO          reservado (sin datos bancarios en esta fase): sin lógica.
 * Vencido = fecha de vencimiento anterior a hoy (el mismo día aún no ha vencido).
 *
 * Totales (por semana ISO o por mes): cargos menos abonos (neto = Σ cargos − Σ |abonos|), separando lo «por pagar»
 * (sin marca, forma no domiciliada) de lo «domiciliado previsto» (sin marca, forma DOMICILIACION) y de lo ya pagado.
 * Importe ausente (null) nunca suma: se cuenta en «importe pendiente». Sentido no documentado nunca suma como cargo
 * ni como abono (regla H4c-2 de Pío): se cuenta aparte. H6-3: un cargo con importe negativo tampoco suma (aviso
 * «importe negativo: revisar», contado aparte); un abono vencido sin marca es ABONO_PENDIENTE_COMPENSAR (azul) y, al
 * marcarlo, «compensado / cobrado (marcado a mano)» con COMPENSACION_ABONO por defecto.
 *
 * Solo sintaxis TypeScript borrable.
 */
import { sumaConocida, type EstadoPago, type Importe, type SentidoVencimiento, type VencimientoListado, type VencimientosDTO } from '../contrato.ts';

// ---------------------------------------------------------------------------
// Formas de pago
// ---------------------------------------------------------------------------

export const FORMAS_PAGO = ['DOMICILIACION', 'TRANSFERENCIA', 'EFECTIVO', 'COMPENSACION_ABONO'] as const;
export type FormaPago = (typeof FORMAS_PAGO)[number];
/** Sin configuración para el CIF: domiciliación. */
export const FORMA_POR_DEFECTO: FormaPago = 'DOMICILIACION';
/** Factura sin CIF: forma sin determinar (a efectos de estado, como TRANSFERENCIA). */
export type FormaEfectiva = FormaPago | 'SIN_DETERMINAR';
export const TEXTO_FORMA: Readonly<Record<FormaEfectiva, string>> = {
  DOMICILIACION: 'Domiciliación', TRANSFERENCIA: 'Transferencia', EFECTIVO: 'Efectivo',
  COMPENSACION_ABONO: 'Compensación con abono', SIN_DETERMINAR: 'Sin determinar',
};

// ---------------------------------------------------------------------------
// Estados
// ---------------------------------------------------------------------------

export const ESTADOS_PAGO = ['PENDIENTE', 'VENCIDO_SIN_PAGAR', 'DOMICILIADO_PREVISTO', 'ABONO_PENDIENTE_COMPENSAR', 'PAGADO_MANUAL', 'PAGADO_BANCO'] as const;
export type EstadoPagoVencimiento = (typeof ESTADOS_PAGO)[number];
/** Color de cada estado: los de la web más uno propio para lo domiciliado previsto (no rojo: no es una incidencia). */
export type ColorEstadoPago = 'azul' | 'rojo' | 'domiciliado' | 'verde' | 'gris';
export interface DefinicionEstado { texto: string; color: ColorEstadoPago; implementado: boolean; descripcion: string }
export const DICCIONARIO_ESTADOS: Readonly<Record<EstadoPagoVencimiento, DefinicionEstado>> = {
  PENDIENTE: { texto: 'Pendiente', color: 'azul', implementado: true, descripcion: 'Aún no ha vencido y no tiene marca de pago.' },
  VENCIDO_SIN_PAGAR: { texto: 'Vencido sin pagar', color: 'rojo', implementado: true, descripcion: 'Ha vencido, no se paga por domiciliación y nadie lo ha marcado como pagado.' },
  DOMICILIADO_PREVISTO: { texto: 'Domiciliado previsto', color: 'domiciliado', implementado: true, descripcion: 'Ha vencido y se paga por domiciliación: el banco debería haberlo cargado. Confírmalo.' },
  // H6-3 (Marc): un abono vencido es dinero a favor: nunca rojo ni «domiciliado previsto».
  ABONO_PENDIENTE_COMPENSAR: { texto: 'Abono pendiente de compensar', color: 'azul', implementado: true, descripcion: 'Abono vencido sin marca: falta compensarlo o cobrarlo.' },
  PAGADO_MANUAL: { texto: 'pagado (marcado a mano)', color: 'verde', implementado: true, descripcion: 'Marcado como pagado a mano, con fecha y forma.' },
  // Reservado para cuando haya datos bancarios: sin lógica en esta fase.
  PAGADO_BANCO: { texto: 'Pagado (banco)', color: 'gris', implementado: false, descripcion: 'Reservado: sin datos bancarios en esta fase.' },
};
/** Estados que la pantalla puede asignar hoy (PAGADO_BANCO queda solo en el diccionario). */
export const ESTADOS_IMPLEMENTADOS = ESTADOS_PAGO.filter((e) => DICCIONARIO_ESTADOS[e].implementado);

export const TEXTO_SENTIDO: Readonly<Record<SentidoVencimiento, string>> = { CARGO: 'Cargo', ABONO: 'Abono', NO_DOCUMENTADO: 'No documentado' };

export const TEXTO_H6_PENDIENTE = 'Pendiente de tablas en Supabase';
export const ERROR_H6_PENDIENTE = 'H6_PENDIENTE';
/** Máximo de vencimientos por petición de marcado (el cuerpo de la petición está limitado a 4 KB). */
export const MAX_VENCIMIENTOS_PETICION = 80;

// ---------------------------------------------------------------------------
// Fechas (ISO YYYY-MM-DD, sin zona)
// ---------------------------------------------------------------------------

export function esFechaIso(v: unknown): v is string {
  if (typeof v !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
  const d = new Date(`${v}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === v;
}
export function sumarDiasIso(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
export function lunesIso(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return sumarDiasIso(iso, -((d.getUTCDay() + 6) % 7));
}
function finDeMes(ym: string): string {
  const [a, m] = ym.split('-').map(Number);
  return new Date(Date.UTC(a, m, 0)).toISOString().slice(0, 10);
}
const fechaDe = (v: { fecha_vencimiento: string | null }) => v.fecha_vencimiento?.slice(0, 10) ?? null;

// ---------------------------------------------------------------------------
// Forma efectiva y estado
// ---------------------------------------------------------------------------

/** CIF comparable válido para la configuración (como normalizarCif: solo A-Z y 0-9). */
export function esCifComparable(v: unknown): v is string {
  return typeof v === 'string' && /^[A-Z0-9]{5,20}$/.test(v);
}

export interface FormaResuelta { forma: FormaEfectiva; por_defecto: boolean; sin_cif: boolean }
/** Forma de un CIF: la configurada vigente; si no hay, DOMICILIACION; sin CIF, sin determinar. */
export function formaEfectiva(cif: string | null, formas: ReadonlyMap<string, FormaPago>): FormaResuelta {
  if (cif === null) return { forma: 'SIN_DETERMINAR', por_defecto: false, sin_cif: true };
  const f = formas.get(cif);
  return f === undefined ? { forma: FORMA_POR_DEFECTO, por_defecto: true, sin_cif: false } : { forma: f, por_defecto: false, sin_cif: false };
}

/** true si la fecha de vencimiento es anterior a hoy. Sin fecha: false (no se afirma que haya vencido). */
export function estaVencido(fecha: string | null, hoy: string): boolean {
  return fecha !== null && fecha.slice(0, 10) < hoy;
}

/**
 * Estado de un vencimiento. Sin determinar (sin CIF) cuenta como no domiciliado: rojo si ha vencido.
 * H6-3: un ABONO vencido sin marca es ABONO_PENDIENTE_COMPENSAR (nunca VENCIDO_SIN_PAGAR ni DOMICILIADO_PREVISTO).
 */
export function estadoPago(fecha: string | null, forma: FormaEfectiva, marcado: boolean, hoy: string,
  sentido: SentidoVencimiento = 'CARGO'): EstadoPagoVencimiento {
  if (marcado) return 'PAGADO_MANUAL';
  if (!estaVencido(fecha, hoy)) return 'PENDIENTE';
  if (sentido === 'ABONO') return 'ABONO_PENDIENTE_COMPENSAR';
  return forma === 'DOMICILIACION' ? 'DOMICILIADO_PREVISTO' : 'VENCIDO_SIN_PAGAR';
}

/** H6-3: texto del estado; un abono marcado es «compensado / cobrado (marcado a mano)». */
export const TEXTO_ABONO_COMPENSADO = 'compensado / cobrado (marcado a mano)';
export function textoEstadoPago(estado: EstadoPagoVencimiento, sentido: SentidoVencimiento): string {
  return estado === 'PAGADO_MANUAL' && sentido === 'ABONO' ? TEXTO_ABONO_COMPENSADO : DICCIONARIO_ESTADOS[estado].texto;
}

/** H6-3: forma por defecto al marcar: la del proveedor; un abono, COMPENSACION_ABONO. */
export function formaPorDefectoMarca(x: Pick<FilaVencimientoPago, 'sentido' | 'forma_pago'>): FormaEfectiva {
  return x.sentido === 'ABONO' ? 'COMPENSACION_ABONO' : x.forma_pago;
}

/** H6-3: cargo con importe negativo (sentido CARGO por la regla de Pío): aviso y fuera de los totales. */
export function esCargoNegativo(x: Pick<FilaVencimientoPago, 'sentido' | 'importe'>): boolean {
  return x.sentido === 'CARGO' && x.importe !== null && x.importe < 0;
}
export const TEXTO_CARGO_NEGATIVO = 'importe negativo: revisar';

// ---------------------------------------------------------------------------
// Marcas y configuración
// ---------------------------------------------------------------------------

export type OrigenMarca = 'MANUAL' | 'DOMICILIADOS';
export interface MarcaPago {
  marca_id: string;
  vencimiento_id: string;
  fecha_pago: string;
  forma: FormaPago;
  /** MANUAL = «Marcar pagado»; DOMICILIADOS = «Confirmar domiciliados». */
  origen: OrigenMarca;
  anulada: boolean;
  creada_at: string;
  creada_por: string;
  anulada_at: string | null;
  anulada_por: string | null;
}
export interface FormaProveedor {
  cif: string;
  forma: FormaPago;
  anulada: boolean;
  creada_at: string;
  creada_por: string;
  anulada_at: string | null;
  anulada_por: string | null;
}
export type AccionPago = 'MARCA' | 'ANULA_MARCA' | 'FORMA' | 'FORMA_POR_DEFECTO';
export interface EventoPago {
  evento_id: number;
  accion: AccionPago;
  autor: string;
  at: string;
  vencimiento_id: string | null;
  marca_id: string | null;
  cif: string | null;
  fecha_pago: string | null;
  forma: FormaPago | null;
  forma_anterior: FormaPago | null;
  origen: OrigenMarca | null;
}

/** Marca vigente mostrada en la fila. */
export type MarcaVista = Pick<MarcaPago, 'marca_id' | 'fecha_pago' | 'forma' | 'origen' | 'creada_at' | 'creada_por'>;

export interface FilaVencimientoPago extends VencimientoListado {
  estado_pago: EstadoPagoVencimiento;
  forma_pago: FormaEfectiva;
  /** true si el CIF no tiene configuración (DOMICILIACION por defecto). */
  forma_por_defecto: boolean;
  /** Factura sin CIF: forma sin determinar; se trata como TRANSFERENCIA (rojo si vence) con aviso «sin CIF». */
  sin_cif: boolean;
  vencido: boolean;
  marca: MarcaVista | null;
  /** H6-3: sentido CARGO con importe negativo: aviso «importe negativo: revisar» y fuera de los totales. */
  cargo_negativo: boolean;
}

/** Filas de la pantalla: estado, forma y marca vigente de cada vencimiento. No cambia importes ni fechas. */
export function filasPagos(vs: readonly VencimientoListado[], formas: ReadonlyMap<string, FormaPago>,
  marcas: ReadonlyMap<string, MarcaPago>, hoy: string): FilaVencimientoPago[] {
  return vs.map((v) => {
    const f = formaEfectiva(v.proveedor_cif_comparable, formas);
    const m = marcas.get(v.vencimiento_id) ?? null;
    return {
      ...v,
      estado_pago: estadoPago(v.fecha_vencimiento, f.forma, m !== null, hoy, v.sentido),
      cargo_negativo: esCargoNegativo(v),
      forma_pago: f.forma, forma_por_defecto: f.por_defecto, sin_cif: f.sin_cif,
      vencido: estaVencido(v.fecha_vencimiento, hoy),
      marca: m === null ? null : { marca_id: m.marca_id, fecha_pago: m.fecha_pago, forma: m.forma, origen: m.origen, creada_at: m.creada_at, creada_por: m.creada_por },
    };
  });
}

// ---------------------------------------------------------------------------
// Totales por semana y mes
// ---------------------------------------------------------------------------

export interface BloqueTotal {
  /** Cargos menos abonos. null si no hay ningún importe conocido (nunca 0 inventado). */
  neto: Importe;
  cargos: Importe;
  /** Suma de abonos en negativo (−|importe|). */
  abonos: Importe;
  /** Vencimientos que suman (importe conocido y sentido CARGO o ABONO). */
  vencimientos: number;
}
export interface TotalPeriodo {
  /** Lunes de la semana o YYYY-MM; null = vencimientos sin fecha. */
  clave: string | null;
  desde: string | null;
  hasta: string | null;
  vencimientos: number;
  /**
   * H6-6 (decisión de Marc): agrupación por ESTADO. «Falta por pagar» = PENDIENTE (no vencido, cualquier forma,
   * también domiciliación) + VENCIDO_SIN_PAGAR.
   */
  por_pagar: BloqueTotal;
  /** Solo DOMICILIADO_PREVISTO (domiciliado y ya vencido, sin marca). */
  domiciliado: BloqueTotal;
  /** PAGADO_MANUAL (y PAGADO_BANCO). */
  pagado: BloqueTotal;
  /** ABONO_PENDIENTE_COMPENSAR: aparte. */
  abonos: BloqueTotal;
  /** Importe ausente: excluido de los totales. */
  sin_importe: number;
  /** Sentido no documentado con importe: excluido de los totales (no se sabe si es cargo o abono). */
  sentido_no_documentado: number;
  /** H6-3: cargos con importe negativo: excluidos de los totales («importe negativo: revisar»). */
  cargo_negativo: number;
}
export type FilaTotal = Pick<FilaVencimientoPago, 'fecha_vencimiento' | 'importe' | 'sentido' | 'estado_pago' | 'forma_pago'>;
/** Recuentos de lo que no suma en un total (siempre a la vista). */
export function excluidosTotal(g: readonly Pick<FilaTotal, 'importe' | 'sentido'>[]): { sin_importe: number; sentido_no_documentado: number; cargo_negativo: number } {
  return {
    sin_importe: g.filter((x) => x.importe === null).length,
    sentido_no_documentado: g.filter((x) => x.importe !== null && x.sentido === 'NO_DOCUMENTADO').length,
    cargo_negativo: g.filter(esCargoNegativo).length,
  };
}
export type Periodo = 'semana' | 'mes';

/**
 * Bloque de totales (regla única de H6, también para el calendario de H6-4): suman los importes conocidos de sentido
 * CARGO o ABONO, salvo los cargos con importe negativo; neto = Σ cargos − Σ |abonos|; null si no suma nada.
 */
export function bloqueTotal(fs: readonly FilaTotal[]): BloqueTotal {
  return bloque(fs);
}
function bloque(fs: readonly FilaTotal[]): BloqueTotal {
  const suman = fs.filter((x) => x.importe !== null && x.sentido !== 'NO_DOCUMENTADO' && !esCargoNegativo(x));
  const cargos = sumaConocida(suman.filter((x) => x.sentido === 'CARGO').map((x) => x.importe)).suma;
  const abonos = sumaConocida(suman.filter((x) => x.sentido === 'ABONO').map((x) => -Math.abs(x.importe as number))).suma;
  const neto = sumaConocida([cargos, abonos].filter((x) => x !== null)).suma;
  return { neto, cargos, abonos, vencimientos: suman.length };
}

/**
 * Bloque al que va cada fila en los totales (H6-6: por estado; la misma regla en la cabecera de totales y en el resumen
 * del periodo del calendario). Cada vencimiento va a un solo bloque.
 */
export type Bloque = 'pagado' | 'domiciliado' | 'por_pagar' | 'abonos';
export const BLOQUE_DE_ESTADO: Readonly<Record<EstadoPagoVencimiento, Bloque>> = {
  PAGADO_MANUAL: 'pagado', PAGADO_BANCO: 'pagado', DOMICILIADO_PREVISTO: 'domiciliado',
  PENDIENTE: 'por_pagar', VENCIDO_SIN_PAGAR: 'por_pagar', ABONO_PENDIENTE_COMPENSAR: 'abonos',
};
export function bloqueDe(x: Pick<FilaTotal, 'estado_pago'>): Bloque {
  return BLOQUE_DE_ESTADO[x.estado_pago];
}

/** Totales de un conjunto de filas (todo lo filtrado o un periodo). */
export function totalGeneral(g: readonly FilaTotal[]): Omit<TotalPeriodo, 'clave' | 'desde' | 'hasta'> {
  return {
    vencimientos: g.length,
    por_pagar: bloque(g.filter((x) => bloqueDe(x) === 'por_pagar')),
    domiciliado: bloque(g.filter((x) => bloqueDe(x) === 'domiciliado')),
    pagado: bloque(g.filter((x) => bloqueDe(x) === 'pagado')),
    abonos: bloque(g.filter((x) => bloqueDe(x) === 'abonos')),
    ...excluidosTotal(g),
  };
}

/** Totales por semana (lunes a domingo) o por mes, en orden; los sin fecha, al final. */
export function totalesPorPeriodo(fs: readonly FilaTotal[], periodo: Periodo): TotalPeriodo[] {
  const grupos = new Map<string, FilaTotal[]>();
  for (const x of fs) {
    const f = fechaDe(x);
    const k = f === null ? '' : periodo === 'semana' ? lunesIso(f) : f.slice(0, 7);
    grupos.set(k, [...(grupos.get(k) ?? []), x]);
  }
  return [...grupos.entries()]
    .sort(([a], [b]) => (a === '' ? 1 : b === '' ? -1 : a.localeCompare(b)))
    .map(([k, g]) => ({
      clave: k === '' ? null : k,
      desde: k === '' ? null : periodo === 'semana' ? k : `${k}-01`,
      hasta: k === '' ? null : periodo === 'semana' ? sumarDiasIso(k, 6) : finDeMes(k),
      ...totalGeneral(g),
    }));
}

// ---------------------------------------------------------------------------
// Filtros (front y pruebas)
// ---------------------------------------------------------------------------

export const PERIODOS = [
  { clave: 'atrasados', texto: 'Atrasados' },
  { clave: 'semana', texto: 'Esta semana' },
  { clave: 'mes', texto: 'Este mes' },
  { clave: 'p30', texto: 'Próximos 30 días' },
  { clave: 'p60', texto: 'Próximos 60 días' },
  { clave: 'p90', texto: 'Próximos 90 días' },
  { clave: 'rango', texto: 'Rango' },
] as const;
export type ClavePeriodo = (typeof PERIODOS)[number]['clave'];

/**
 * Filtro de fecha. Atrasados = vencido y sin marca de pago. Esta semana = lunes a domingo de hoy. Este mes = el mes de
 * hoy. Próximos N días = de hoy a hoy + N. Rango = desde/hasta inclusive (cualquiera puede faltar). Sin fecha: fuera
 * de cualquier filtro de fecha.
 */
export function cumplePeriodo(x: Pick<FilaVencimientoPago, 'fecha_vencimiento' | 'estado_pago'>, periodo: string, hoy: string,
  rango: { desde?: string; hasta?: string } = {}): boolean {
  if (periodo === '') return true;
  const f = fechaDe(x);
  if (f === null) return false;
  switch (periodo) {
    case 'atrasados': return f < hoy && x.estado_pago !== 'PAGADO_MANUAL' && x.estado_pago !== 'PAGADO_BANCO';
    case 'semana': { const l = lunesIso(hoy); return f >= l && f <= sumarDiasIso(l, 6); }
    case 'mes': return f.slice(0, 7) === hoy.slice(0, 7);
    case 'p30': return f >= hoy && f <= sumarDiasIso(hoy, 30);
    case 'p60': return f >= hoy && f <= sumarDiasIso(hoy, 60);
    case 'p90': return f >= hoy && f <= sumarDiasIso(hoy, 90);
    case 'rango': return (!esFechaIso(rango.desde) || f >= rango.desde) && (!esFechaIso(rango.hasta) || f <= rango.hasta);
    default: return true;
  }
}

/** Minúsculas y sin acentos. */
export function textoPlano(s: string): string {
  return s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().trim();
}

/** Búsqueda por proveedor (nombre comercial, razón social, literal), CIF (también con guiones o puntos) o nº de factura. */
export function cumpleBusquedaPago(x: Pick<FilaVencimientoPago, 'proveedor_comercial' | 'proveedor_razon_social' | 'proveedor' | 'proveedor_cif_comparable' | 'numero_factura'>, q: string): boolean {
  if (q.trim() === '') return true;
  const cifQ = q.toUpperCase().replace(/[^A-Z0-9]/g, '');
  if (cifQ.length >= 5 && /\d/.test(cifQ) && x.proveedor_cif_comparable?.includes(cifQ)) return true;
  const texto = textoPlano([x.proveedor_comercial ?? '', x.proveedor_razon_social ?? '', x.proveedor ?? '',
    x.proveedor_cif_comparable ?? '', x.numero_factura ?? ''].join(' '));
  return textoPlano(q).split(/\s+/).every((p) => texto.includes(p));
}

// ---------------------------------------------------------------------------
// DTO de la pantalla
// ---------------------------------------------------------------------------

export interface ProveedorPagoVista {
  cif: string;
  nombre: string;
  razon_social: string | null;
  forma: FormaPago;
  por_defecto: boolean;
  vencimientos: number;
  sin_pagar: number;
}
export interface EventoPagoVista extends EventoPago {
  /** Sentido del vencimiento (H6-3: un abono se «compensa / cobra»). */
  sentido: SentidoVencimiento | null;
  numero_factura: string | null;
  fecha_vencimiento: string | null;
  proveedor_nombre: string | null;
}
export interface PantallaVencimientosDTO {
  farmacia: string;
  generado_at: string;
  /** Fecha de referencia de los estados (REAL: la del servidor; FIXTURES: la de la semilla). */
  hoy: string;
  modo: 'FIXTURES' | 'REAL';
  /** false en REAL: sin tablas de marcas ni de formas (todo en solo lectura). */
  marcas_disponibles: boolean;
  mensaje_pendiente: string | null;
  filas: FilaVencimientoPago[];
  proveedores: ProveedorPagoVista[];
  sin_cif: { vencimientos: number };
  historial: EventoPagoVista[];
  /** Banco: sin datos bancarios en esta fase (gris). */
  pago: EstadoPago;
}

export interface FuentePagos {
  hoy: string;
  formas: ReadonlyMap<string, FormaPago>;
  marcas: ReadonlyMap<string, MarcaPago>;
  historial: readonly EventoPago[];
}

const nombreFila = (v: Pick<VencimientoListado, 'proveedor_comercial' | 'proveedor_razon_social' | 'proveedor'>) =>
  v.proveedor_comercial ?? v.proveedor_razon_social ?? v.proveedor ?? 'Proveedor sin identificar';

/** Construye la pantalla a partir del contrato `vencimientos` y de las marcas y formas (vacías en REAL). */
export function construirPantalla(dto: VencimientosDTO, fuente: FuentePagos | null, opciones: { hoy: string; modo: 'FIXTURES' | 'REAL' }): PantallaVencimientosDTO {
  const hoy = fuente?.hoy ?? opciones.hoy;
  // Orden de la lista: fecha de vencimiento (sin fecha, al final), nº de factura y orden del vencimiento.
  const filas = filasPagos(dto.vencimientos, fuente?.formas ?? new Map(), fuente?.marcas ?? new Map(), hoy)
    .map((f, i) => ({ f, i }))
    .sort((a, b) => (fechaDe(a.f) ?? '9999').localeCompare(fechaDe(b.f) ?? '9999')
      || (a.f.numero_factura ?? '').localeCompare(b.f.numero_factura ?? '') || (a.f.orden ?? 0) - (b.f.orden ?? 0) || a.i - b.i)
    .map((x) => x.f);
  const porCif = new Map<string, FilaVencimientoPago[]>();
  for (const f of filas) if (f.proveedor_cif_comparable !== null) porCif.set(f.proveedor_cif_comparable, [...(porCif.get(f.proveedor_cif_comparable) ?? []), f]);
  const proveedores: ProveedorPagoVista[] = [...porCif.entries()].map(([cif, fs]) => ({
    cif,
    nombre: nombreFila(fs[0]),
    razon_social: fs[0].proveedor_razon_social,
    forma: fs[0].forma_pago as FormaPago,
    por_defecto: fs[0].forma_por_defecto,
    vencimientos: fs.length,
    sin_pagar: fs.filter((x) => x.estado_pago !== 'PAGADO_MANUAL').length,
  })).sort((a, b) => a.nombre.localeCompare(b.nombre, 'es') || a.cif.localeCompare(b.cif));
  const venc = new Map(dto.vencimientos.map((v) => [v.vencimiento_id, v]));
  const nombreCif = new Map(proveedores.map((p) => [p.cif, p.nombre]));
  const historial: EventoPagoVista[] = [...(fuente?.historial ?? [])].sort((a, b) => b.at.localeCompare(a.at) || b.evento_id - a.evento_id).map((e) => {
    const v = e.vencimiento_id === null ? undefined : venc.get(e.vencimiento_id);
    return {
      ...e,
      sentido: v?.sentido ?? null,
      numero_factura: v?.numero_factura ?? null,
      fecha_vencimiento: v?.fecha_vencimiento ?? null,
      proveedor_nombre: v ? nombreFila(v) : e.cif === null ? null : nombreCif.get(e.cif) ?? null,
    };
  });
  return {
    farmacia: dto.farmacia, generado_at: dto.generado_at, hoy, modo: opciones.modo,
    marcas_disponibles: fuente !== null, mensaje_pendiente: fuente === null ? TEXTO_H6_PENDIENTE : null,
    filas, proveedores, sin_cif: { vencimientos: filas.filter((f) => f.sin_cif).length }, historial, pago: dto.pago,
  };
}

// ---------------------------------------------------------------------------
// Validación de peticiones (falla cerrado: claves exactas)
// ---------------------------------------------------------------------------

type Errores = Record<string, string>;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const esObjeto = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === 'object' && !Array.isArray(v);

function listaIds(v: unknown, errores: Errores): string[] {
  if (!Array.isArray(v) || v.length === 0) { errores.vencimientos = 'Selecciona al menos un vencimiento'; return []; }
  if (v.length > MAX_VENCIMIENTOS_PETICION) { errores.vencimientos = `Como máximo ${MAX_VENCIMIENTOS_PETICION} vencimientos a la vez`; return []; }
  if (!v.every((x) => typeof x === 'string' && UUID.test(x))) { errores.vencimientos = 'Identificador de vencimiento no válido'; return []; }
  if (new Set(v).size !== v.length) { errores.vencimientos = 'Vencimiento repetido'; return []; }
  return v as string[];
}

export interface PeticionMarcar { vencimientos: string[]; fecha_pago: string; forma: FormaPago | null }
/** { vencimientos: uuid[], fecha_pago: 'YYYY-MM-DD' (≤ hoy), forma: FormaPago | null (null = la de cada proveedor) }. */
export function validarMarcar(cuerpo: unknown, hoy: string): { ok: true; datos: PeticionMarcar } | { ok: false; errores: Errores } {
  const errores: Errores = {};
  if (!esObjeto(cuerpo) || Object.keys(cuerpo).some((k) => !['vencimientos', 'fecha_pago', 'forma'].includes(k))) return { ok: false, errores: { cuerpo: 'Petición no válida' } };
  const ids = listaIds(cuerpo.vencimientos, errores);
  const fecha = cuerpo.fecha_pago;
  if (!esFechaIso(fecha)) errores.fecha_pago = 'Fecha no válida';
  else if (fecha > hoy) errores.fecha_pago = 'La fecha de pago no puede ser posterior a hoy';
  else if (fecha < '2000-01-01') errores.fecha_pago = 'Fecha no válida';
  const forma = cuerpo.forma ?? null;
  if (!('forma' in cuerpo) || (forma !== null && !(FORMAS_PAGO as readonly unknown[]).includes(forma))) errores.forma = 'Forma de pago no válida';
  if (Object.keys(errores).length) return { ok: false, errores };
  return { ok: true, datos: { vencimientos: ids, fecha_pago: fecha as string, forma: forma as FormaPago | null } };
}

/** { vencimientos: uuid[] } (solo DOMICILIADO_PREVISTO; lo comprueba la ruta). */
export function validarDomiciliados(cuerpo: unknown): { ok: true; vencimientos: string[] } | { ok: false; errores: Errores } {
  const errores: Errores = {};
  if (!esObjeto(cuerpo) || Object.keys(cuerpo).some((k) => k !== 'vencimientos')) return { ok: false, errores: { cuerpo: 'Petición no válida' } };
  const ids = listaIds(cuerpo.vencimientos, errores);
  return Object.keys(errores).length ? { ok: false, errores } : { ok: true, vencimientos: ids };
}

/** { forma: FormaPago | null } (null = volver a la forma por defecto: anula la configuración vigente). */
export function validarFormaProveedor(cuerpo: unknown): { ok: true; forma: FormaPago | null } | { ok: false; errores: Errores } {
  if (!esObjeto(cuerpo) || Object.keys(cuerpo).length !== 1 || !('forma' in cuerpo)
    || (cuerpo.forma !== null && !(FORMAS_PAGO as readonly unknown[]).includes(cuerpo.forma))) {
    return { ok: false, errores: { forma: 'Forma de pago no válida' } };
  }
  return { ok: true, forma: cuerpo.forma as FormaPago | null };
}

/** { confirmar: true }. */
export function validarConfirmacion(cuerpo: unknown): boolean {
  return esObjeto(cuerpo) && Object.keys(cuerpo).length === 1 && cuerpo.confirmar === true;
}

// ---------------------------------------------------------------------------
// Almacén en memoria (FIXTURES). Nunca borra: anula. Una marca vigente por vencimiento y una forma vigente por CIF.
// ---------------------------------------------------------------------------

export interface SemillaPagos {
  hoy: string;
  formas: Omit<FormaProveedor, 'anulada_at' | 'anulada_por'>[] | FormaProveedor[];
  marcas: MarcaPago[];
}
export interface ItemMarca { vencimiento_id: string; fecha_pago: string; forma: FormaPago; origen: OrigenMarca }

export interface AlmacenPagos {
  hoy: string;
  fuente(): FuentePagos;
  /** Todo o nada: si alguno ya tiene marca vigente, no marca ninguno. */
  marcar(items: readonly ItemMarca[], autor: string): MarcaPago[] | 'YA_PAGADO';
  anular(marcaId: string, autor: string): MarcaPago | 'MARCA_NO_ENCONTRADA' | 'MARCA_YA_ANULADA';
  /** forma null = volver a la forma por defecto (anula la vigente). */
  fijarForma(cif: string, forma: FormaPago | null, autor: string): { cif: string; forma: FormaPago; por_defecto: boolean } | 'SIN_CAMBIOS';
  /** Todas las marcas (también anuladas) y formas: para las pruebas. */
  datos(): { marcas: MarcaPago[]; formas: FormaProveedor[] };
}

export function crearAlmacenPagos(semilla: SemillaPagos, o: { ahora?: () => string; nuevoId?: () => string } = {}): AlmacenPagos {
  if (!esFechaIso(semilla.hoy)) throw new Error('SEMILLA_PAGOS_HOY_NO_VALIDO');
  const ahora = o.ahora ?? (() => new Date().toISOString());
  const nuevoId = o.nuevoId ?? (() => crypto.randomUUID());
  const marcas: MarcaPago[] = semilla.marcas.map((m) => ({ ...m }));
  const formas: FormaProveedor[] = semilla.formas.map((f) => ({ anulada_at: null, anulada_por: null, ...f }));
  const historial: EventoPago[] = [];
  let n = 0;
  const evento = (e: Omit<EventoPago, 'evento_id'>) => { historial.push({ evento_id: ++n, ...e }); };
  const base = { vencimiento_id: null, marca_id: null, cif: null, fecha_pago: null, forma: null, forma_anterior: null, origen: null };
  // Historial de la semilla, en orden de fecha.
  const sembrado: Omit<EventoPago, 'evento_id'>[] = [];
  // Un cambio de forma anula la anterior y crea la nueva en el mismo instante: un solo evento FORMA con la anterior.
  const sustituida = (f: FormaProveedor) => formas.find((x) => x !== f && x.cif === f.cif && x.anulada && x.anulada_at === f.creada_at);
  const sustituta = (f: FormaProveedor) => formas.find((x) => x !== f && x.cif === f.cif && x.creada_at === f.anulada_at);
  for (const f of formas) {
    sembrado.push({ ...base, accion: 'FORMA', autor: f.creada_por, at: f.creada_at, cif: f.cif, forma: f.forma, forma_anterior: sustituida(f)?.forma ?? null });
    if (f.anulada && f.anulada_at && !sustituta(f)) sembrado.push({ ...base, accion: 'FORMA_POR_DEFECTO', autor: f.anulada_por ?? f.creada_por, at: f.anulada_at, cif: f.cif, forma_anterior: f.forma });
  }
  for (const m of marcas) {
    sembrado.push({ ...base, accion: 'MARCA', autor: m.creada_por, at: m.creada_at, vencimiento_id: m.vencimiento_id, marca_id: m.marca_id, fecha_pago: m.fecha_pago, forma: m.forma, origen: m.origen });
    if (m.anulada && m.anulada_at) sembrado.push({ ...base, accion: 'ANULA_MARCA', autor: m.anulada_por ?? m.creada_por, at: m.anulada_at, vencimiento_id: m.vencimiento_id, marca_id: m.marca_id, fecha_pago: m.fecha_pago, forma: m.forma, origen: m.origen });
  }
  sembrado.sort((a, b) => a.at.localeCompare(b.at)).forEach(evento);
  const vigentes = () => new Map(marcas.filter((m) => !m.anulada).map((m) => [m.vencimiento_id, m]));
  const formasVigentes = () => new Map(formas.filter((f) => !f.anulada).map((f) => [f.cif, f.forma]));
  if (vigentes().size !== marcas.filter((m) => !m.anulada).length) throw new Error('SEMILLA_PAGOS_MARCA_DUPLICADA');
  if (formasVigentes().size !== formas.filter((f) => !f.anulada).length) throw new Error('SEMILLA_PAGOS_FORMA_DUPLICADA');

  return {
    hoy: semilla.hoy,
    fuente: () => ({ hoy: semilla.hoy, formas: formasVigentes(), marcas: vigentes(), historial: [...historial] }),
    marcar(items, autor) {
      const v = vigentes();
      if (items.some((i) => v.has(i.vencimiento_id))) return 'YA_PAGADO';
      const at = ahora();
      return items.map((i) => {
        const m: MarcaPago = { marca_id: nuevoId(), ...i, anulada: false, creada_at: at, creada_por: autor, anulada_at: null, anulada_por: null };
        marcas.push(m);
        evento({ ...base, accion: 'MARCA', autor, at, vencimiento_id: m.vencimiento_id, marca_id: m.marca_id, fecha_pago: m.fecha_pago, forma: m.forma, origen: m.origen });
        return { ...m };
      });
    },
    anular(marcaId, autor) {
      const m = marcas.find((x) => x.marca_id === marcaId);
      if (!m) return 'MARCA_NO_ENCONTRADA';
      if (m.anulada) return 'MARCA_YA_ANULADA';
      const at = ahora();
      Object.assign(m, { anulada: true, anulada_at: at, anulada_por: autor });
      evento({ ...base, accion: 'ANULA_MARCA', autor, at, vencimiento_id: m.vencimiento_id, marca_id: m.marca_id, fecha_pago: m.fecha_pago, forma: m.forma, origen: m.origen });
      return { ...m };
    },
    fijarForma(cif, forma, autor) {
      const actual = formas.find((f) => f.cif === cif && !f.anulada);
      if ((actual?.forma ?? null) === forma) return 'SIN_CAMBIOS';
      const at = ahora();
      if (actual) Object.assign(actual, { anulada: true, anulada_at: at, anulada_por: autor });
      if (forma === null) {
        evento({ ...base, accion: 'FORMA_POR_DEFECTO', autor, at, cif, forma_anterior: actual?.forma ?? null });
        return { cif, forma: FORMA_POR_DEFECTO, por_defecto: true };
      }
      formas.push({ cif, forma, anulada: false, creada_at: at, creada_por: autor, anulada_at: null, anulada_por: null });
      evento({ ...base, accion: 'FORMA', autor, at, cif, forma, forma_anterior: actual?.forma ?? null });
      return { cif, forma, por_defecto: false };
    },
    datos: () => ({ marcas: marcas.map((m) => ({ ...m })), formas: formas.map((f) => ({ ...f })) }),
  };
}
