/**
 * H7: pantalla Cashflow. Módulo puro: lo usan el servidor (FIXTURES), el front (que recalcula al cambiar «Media / Excel»),
 * check_fixtures y las pruebas.
 *
 * Decisiones de Marc: el Excel es la referencia; la web solo lee (sin escrituras ni excepción nueva). Decenas y mes. Por
 * cuenta bancaria (PIO, RITA) más consolidado. RITA activa en Cashflow solo con datos bancarios: a RITA nunca se le suman
 * vencimientos del sistema; solo lo que trae la importación del Excel y sus saldos de banco.
 *
 * Contrato de datos (lo crea el circuito; tablas pendientes en Supabase):
 *   cf_cashflow_importaciones (vigente, importado_at, origen, estado)
 *   cf_cashflow_cuentas       (codigo PIO|RITA|SL, farmacia)
 *   cf_cashflow_importes      (cuenta, decena_inicio, decena_fin, categoria "RE …"/"RS …", concepto, importe)
 *   cf_cashflow_saldos        (cuenta, decena_inicio, saldo_formulas, saldo_bancos | null)
 *
 * Reglas:
 *   Real = decenas hasta la última con saldo_bancos de cada cuenta; saldo de partida = ese saldo_bancos.
 *   Previsión por (cuenta, concepto, decena), con su fuente:
 *     a) PIO: vencimientos del sistema (contrato H6) de los conceptos del Excel que corresponden por nombre comercial
 *        (CORRESPONDENCIAS_PROVEEDOR, único punto). Sustituyen lo anotado en el Excel para ese concepto y decena; si los dos
 *        existen y difieren, «posible duplicado o diferencia».
 *     b) Lo anotado en las decenas futuras del Excel (RITA, y PIO para lo no cubierto por a).
 *     c) TPV y efectivo: media de las últimas N decenas reales; SOE: media de los últimos N meses reales, en la decena en
 *        que cobra habitualmente. N en CONFIG_CASHFLOW. «Media / Excel» por categoría (las dos cifras siempre a la vista).
 *   Saldo previsto = anterior + entradas − salidas. Traspasos entre cuentas propias: neutros en el consolidado.
 *   «No relacionadas con la farmacia»: cuentan en el saldo, no en el «cash flow generado farmacia».
 *   Importe ausente = null, nunca 0: no suma y se cuenta (el saldo queda «incompleto»).
 *
 * Signo (H7-2, decisión de Marc): el importe del Excel se usa con el signo de la celda, nunca en valor absoluto. RE suma
 * el valor tal cual; RS lo resta tal cual: un RS negativo (abono dentro de un proveedor, comisión devuelta) reduce las
 * salidas, y un RE negativo reduce las entradas. Categoría sin prefijo RE/RS: fuera, contada.
 *
 * Solo sintaxis TypeScript borrable; sin dependencias del servidor (el front lo importa).
 */
import type { EstadoPago, Importe, SentidoVencimiento } from '../contrato.ts';
import { esPagado, type EstadoPagoVencimiento } from '../pagos/pagos.ts';

// ---------------------------------------------------------------------------
// Configuración (único punto)
// ---------------------------------------------------------------------------

export interface ConfigCashflow {
  /** N de la media de TPV y efectivo (decenas reales). */
  decenas_media: number;
  /** N de la media de la SOE (meses reales completos). */
  meses_media_soe: number;
  /** Aviso gris si la importación vigente tiene más de estos días. */
  dias_importacion_antigua: number;
  /** Saldo mínimo de los avisos. */
  saldo_minimo: number;
  decenas_pasadas: number;
  decenas_proximas: number;
  meses_pasados: number;
  meses_proximos: number;
  /** Valores de `estado` de una importación correcta (cualquier otro = falló). */
  estados_importacion_ok: readonly string[];
}
export const CONFIG_CASHFLOW: ConfigCashflow = {
  decenas_media: 6,
  meses_media_soe: 3,
  dias_importacion_antigua: 5,
  saldo_minimo: 0,
  decenas_pasadas: 3,
  decenas_proximas: 9,
  meses_pasados: 3,
  meses_proximos: 9,
  estados_importacion_ok: ['OK'],
};

export const CUENTAS_CASHFLOW = ['PIO', 'RITA'] as const;
export type CuentaCashflow = (typeof CUENTAS_CASHFLOW)[number];
export type VistaCuenta = CuentaCashflow | 'CONSOLIDADO';
export const VISTAS_CUENTA: readonly VistaCuenta[] = ['PIO', 'RITA', 'CONSOLIDADO'];
/** Única cuenta a la que se suman vencimientos del sistema (RITA: solo datos bancarios). */
export const CUENTA_VENCIMIENTOS: CuentaCashflow = 'PIO';

export const TEXTO_H7_PENDIENTE = 'Pendiente de tablas en Supabase';
export const ERROR_H7_PENDIENTE = 'H7_PENDIENTE';
export const TEXTO_POSIBLE_DUPLICADO = 'posible duplicado o diferencia';

/** Categorías con previsión por media (las tres del Excel). */
export type UnidadMedia = 'decenas' | 'meses';
export const CATEGORIAS_MEDIA: Readonly<Record<string, UnidadMedia>> = {
  'RE Cobro TPV': 'decenas',
  'RE Cobro efectivo': 'decenas',
  'RE Cobro SOE': 'meses',
};
export type Eleccion = 'media' | 'excel';
export type Elecciones = Readonly<Record<string, Eleccion>>;
export const ELECCION_POR_DEFECTO: Eleccion = 'media';
/** Concepto de la línea que lleva la media (no viene del Excel). */
export const CONCEPTO_MEDIA = 'Media calculada';

/** Categoría donde se crea la línea de un proveedor del sistema que el Excel no tiene. */
export const CATEGORIA_PROVEEDORES = 'RS Proveedores';
/**
 * Correspondencias concepto del Excel → nombre comercial del sistema (H5-8). Único punto. El primer concepto de cada
 * entrada es el que se usa si el Excel no lo tiene.
 */
export const CORRESPONDENCIAS_PROVEEDOR: readonly { conceptos: readonly string[]; comercial: string }[] = [
  { conceptos: ['ALLIANCE'], comercial: 'ALLIANCE' },
  { conceptos: ['HEFAME'], comercial: 'HEFAME' },
  { conceptos: ['COFARES'], comercial: 'COFARES' },
  { conceptos: ['FEDERACIÓ', 'FEDERACIO', 'FEDEFARMA'], comercial: 'FEDEFARMA' },
  { conceptos: ['LOGISTA'], comercial: 'LOGISTA PHARMA' },
];

const normal = (s: string) => s.normalize('NFD').replace(/\p{M}/gu, '').toUpperCase().replace(/\s+/g, ' ').trim();
/** Nombre comercial del sistema para un concepto del Excel (null = sin correspondencia). */
export function comercialDeConcepto(concepto: string): string | null {
  const n = normal(concepto);
  return CORRESPONDENCIAS_PROVEEDOR.find((c) => c.conceptos.some((x) => normal(x) === n))?.comercial ?? null;
}

export type SentidoMovimiento = 'ENTRADA' | 'SALIDA';
export type ClaseMovimiento = 'FARMACIA' | 'NO_RELACIONADA' | 'TRASPASO';
/** "RE …" = entrada, "RS …" = salida; traspasos y «no relacionadas» por su nombre. null = no reconocida. */
export function clasificarCategoria(categoria: string): { sentido: SentidoMovimiento; clase: ClaseMovimiento } | null {
  const m = /^(RE|RS)\s+(\S.*)$/.exec(categoria.trim());
  if (!m) return null;
  const resto = normal(m[2]);
  const clase: ClaseMovimiento = /TRASPAS/.test(resto) ? 'TRASPASO' : /NO RELACIONAD/.test(resto) ? 'NO_RELACIONADA' : 'FARMACIA';
  return { sentido: m[1] === 'RE' ? 'ENTRADA' : 'SALIDA', clase };
}

// ---------------------------------------------------------------------------
// Decenas (ISO YYYY-MM-DD, sin zona): 1–10, 11–20 y 21–fin de mes
// ---------------------------------------------------------------------------

const DIA_INICIO = ['01', '11', '21'];
function finDeMes(ym: string): string {
  const [a, m] = ym.split('-').map(Number);
  return new Date(Date.UTC(a, m, 0)).toISOString().slice(0, 10);
}
export function esFecha(v: unknown): v is string {
  if (typeof v !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
  const d = new Date(`${v}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === v;
}
export function esDecenaInicio(v: unknown): v is string {
  return esFecha(v) && DIA_INICIO.includes(v.slice(8));
}
export function decenaDe(fecha: string): string {
  const d = Number(fecha.slice(8, 10));
  return `${fecha.slice(0, 8)}${d <= 10 ? '01' : d <= 20 ? '11' : '21'}`;
}
export function finDecena(inicio: string): string {
  const dd = inicio.slice(8);
  return dd === '01' ? `${inicio.slice(0, 8)}10` : dd === '11' ? `${inicio.slice(0, 8)}20` : finDeMes(inicio.slice(0, 7));
}
export function sumarMeses(ym: string, n: number): string {
  const [a, m] = ym.split('-').map(Number);
  const d = new Date(Date.UTC(a, m - 1 + n, 1));
  return d.toISOString().slice(0, 7);
}
export function siguienteDecena(inicio: string): string {
  const dd = inicio.slice(8);
  if (dd === '01') return `${inicio.slice(0, 8)}11`;
  if (dd === '11') return `${inicio.slice(0, 8)}21`;
  return `${sumarMeses(inicio.slice(0, 7), 1)}-01`;
}
export function anteriorDecena(inicio: string): string {
  const dd = inicio.slice(8);
  if (dd === '21') return `${inicio.slice(0, 8)}11`;
  if (dd === '11') return `${inicio.slice(0, 8)}01`;
  return `${sumarMeses(inicio.slice(0, 7), -1)}-21`;
}
export function moverDecena(inicio: string, n: number): string {
  let d = inicio;
  for (let i = 0; i < Math.abs(n); i++) d = n > 0 ? siguienteDecena(d) : anteriorDecena(d);
  return d;
}
/** 1, 2 o 3 (decena del mes). */
export function ordinalDecena(inicio: string): 1 | 2 | 3 {
  return (DIA_INICIO.indexOf(inicio.slice(8)) + 1) as 1 | 2 | 3;
}
export function decenasDelMes(ym: string): string[] {
  return DIA_INICIO.map((d) => `${ym}-${d}`);
}
/** Decenas de `desde` a `hasta`, ambas incluidas. */
export function rangoDecenas(desde: string, hasta: string): string[] {
  const out: string[] = [];
  for (let d = desde; d <= hasta; d = siguienteDecena(d)) out.push(d);
  return out;
}
function diasEntre(a: string, b: string): number {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86400000);
}
/** Fecha (Europe/Madrid) de un instante. */
export function fechaMadrid(instante: string): string | null {
  const t = Date.parse(instante);
  if (Number.isNaN(t)) return null;
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Madrid', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(t));
}

// ---------------------------------------------------------------------------
// Contrato (filas tal como las crea el circuito)
// ---------------------------------------------------------------------------

export interface ImportacionCashflow {
  importacion_id: string;
  vigente: boolean;
  importado_at: string;
  origen: string;
  estado: string;
}
export interface CuentaCashflowFila {
  codigo: string;
  farmacia: string | null;
}
export interface ImporteCashflow {
  cuenta: string;
  decena_inicio: string;
  decena_fin: string;
  categoria: string;
  concepto: string;
  importe: Importe;
}
export interface SaldoCashflow {
  cuenta: string;
  decena_inicio: string;
  saldo_formulas: Importe;
  saldo_bancos: Importe;
}
/** Vencimiento del sistema (contrato H6, solo PIO) con lo que necesita el cashflow. */
export interface VencimientoCashflow {
  vencimiento_id: string;
  factura_id: string;
  numero_factura: string | null;
  proveedor_comercial: string | null;
  proveedor_nombre: string;
  fecha_vencimiento: string | null;
  importe: Importe;
  sentido: SentidoVencimiento;
  estado_pago: EstadoPagoVencimiento;
  /** Fecha de la marca de pago vigente (null = sin marca). */
  fecha_pago: string | null;
  cargo_negativo: boolean;
}
export interface DatosCashflow {
  importaciones: ImportacionCashflow[];
  cuentas: CuentaCashflowFila[];
  importes: ImporteCashflow[];
  saldos: SaldoCashflow[];
}
/** Respuesta de GET /api/cashflow: los datos de partida; el cálculo lo hace calcularCashflow (también en el front). */
export interface CashflowDTO extends DatosCashflow {
  farmacia: string;
  generado_at: string;
  /** Fecha de referencia (FIXTURES: la de la semilla; REAL: la del servidor). */
  hoy: string;
  modo: 'FIXTURES' | 'REAL';
  config: ConfigCashflow;
  vencimientos: VencimientoCashflow[];
  pago: EstadoPago;
}

// ---------------------------------------------------------------------------
// Resultado
// ---------------------------------------------------------------------------

export type FuenteCelda = 'REAL' | 'VENCIMIENTOS' | 'EXCEL' | 'MEDIA' | 'MIXTA';
export const TEXTO_FUENTE: Readonly<Record<FuenteCelda, string>> = {
  REAL: 'Real (Excel, decena con saldo de banco)',
  VENCIMIENTOS: 'Vencimientos del sistema',
  EXCEL: 'Anotado en el Excel',
  MEDIA: 'Media calculada',
  MIXTA: 'Varias fuentes',
};

export interface DesgloseVencimientos {
  comercial: string;
  /** Los que suman. */
  incluidos: VencimientoCashflow[];
  /** Σ cargos − Σ |abonos| de los incluidos con importe (null si ninguno lo tiene). */
  neto: Importe;
  sin_importe: number;
  no_documentado: VencimientoCashflow[];
  cargo_negativo: VencimientoCashflow[];
  /** Pagados (marca) antes del último saldo de banco: ya están en el saldo. */
  ya_en_banco: VencimientoCashflow[];
}
export interface DesgloseMedia {
  unidad: UnidadMedia;
  /** Decenas (o meses) que entran en la media, con su total. */
  base: { clave: string; importe: number }[];
  media: Importe;
  /** SOE: decena del mes en que cobra habitualmente. */
  decena_habitual: 1 | 2 | 3 | null;
}
export interface Celda {
  cuenta: CuentaCashflow;
  decena: string;
  real: boolean;
  fuente: FuenteCelda;
  /** Movimiento con signo (+ entrada, − salida). null = importe desconocido. */
  importe: Importe;
  /** false = cifra a la vista que no entra en el saldo (Excel sustituido por la media o al revés). */
  en_saldo: boolean;
  /** Anotado en el Excel para esta línea y decena (con signo). null = sin fila o sin importe. */
  excel: Importe;
  excel_filas: number;
  vencimientos: DesgloseVencimientos | null;
  media: DesgloseMedia | null;
  /** Vencimientos y Excel distintos (o no comparables): «posible duplicado o diferencia». */
  diferencia: boolean;
  /** Importes desconocidos (null) de la celda. */
  desconocidos: number;
  /** Consolidado: celdas de cada cuenta. */
  partes: Celda[];
}
export interface Linea {
  clave: string;
  categoria: string;
  concepto: string;
  sentido: SentidoMovimiento;
  clase: ClaseMovimiento;
  /** Línea de la media (no viene del Excel). */
  media: boolean;
  celdas: Record<string, Celda>;
}
export interface ResumenDecena {
  decena: string;
  real: boolean;
  /** Σ de lo que entra en el saldo; null = ningún movimiento. */
  entradas: Importe;
  salidas: Importe;
  /** Cash flow generado farmacia (sin «no relacionadas» ni traspasos). */
  farmacia: Importe;
  no_relacionadas: Importe;
  traspasos: Importe;
  neto: Importe;
  saldo: Importe;
  saldo_bancos: Importe;
  saldo_formulas: Importe;
  desconocidos: number;
  /** Hay importes desconocidos en esta decena o antes (desde la partida). */
  incompleto: boolean;
}
export interface ResultadoVista {
  vista: VistaCuenta;
  ultima_real: string | null;
  saldo_partida: Importe;
  lineas: Linea[];
  decenas: Record<string, ResumenDecena>;
}
export type CodigoAviso =
  | 'CUENTA_CUBIERTA' | 'CONSOLIDADO_NEGATIVO' | 'IMPORTACION_ANTIGUA' | 'IMPORTACION_FALLIDA' | 'SIN_IMPORTACION_VIGENTE'
  | 'SIN_SALDO_BANCO' | 'TRASPASO_SIN_CONTRAPARTIDA';
export interface AvisoCashflow {
  tipo: 'naranja' | 'rojo' | 'gris';
  codigo: CodigoAviso;
  texto: string;
  /** Primera decena del episodio. */
  decena: string | null;
  hasta: string | null;
  cuenta: CuentaCashflow | null;
  cubre: CuentaCashflow | null;
  /** Naranja: mayor importe cubierto; rojo: mayor importe que falta. */
  importe: Importe;
  /** Naranja: primera decena en que la cuenta recupera saldo suficiente (null = no dentro del horizonte). */
  devolucion: string | null;
  /** Detalle por decena. */
  decenas: { decena: string; importe: number }[];
  /** Saldo calculado con importes desconocidos. */
  incompleto: boolean;
}
export interface FueraDeCashflow {
  filas_otras_cuentas: number;
  categorias_no_reconocidas: string[];
  filas_no_reconocidas: number;
  filas_decena_no_valida: number;
  venc_sin_concepto: VencimientoCashflow[];
  /** Con concepto, pero ninguno de su decena suma (ya en el banco, sentido no documentado, cargo negativo). */
  venc_no_suman: VencimientoCashflow[];
  venc_sin_fecha: number;
  /** Sin pagar con fecha en decenas reales: no entran en la previsión (lo real es el Excel). */
  venc_en_decenas_reales: VencimientoCashflow[];
}
export interface EstadoImportacion {
  vigente: ImportacionCashflow | null;
  ultima: ImportacionCashflow | null;
  dias: number | null;
}
export interface ResultadoCashflow {
  hoy: string;
  decenas: string[];
  vistas: Record<VistaCuenta, ResultadoVista>;
  avisos: AvisoCashflow[];
  importacion: EstadoImportacion;
  fuera: FueraDeCashflow;
  elecciones: Record<string, Eleccion>;
  /** Categorías con media en alguna cuenta. */
  categorias_media: string[];
}

// ---------------------------------------------------------------------------
// Sumas en céntimos
// ---------------------------------------------------------------------------

const cent = (x: number) => Math.round(x * 100);
const eur = (c: number) => c / 100;
/** Σ de importes conocidos (null si no hay ninguno) y nº de desconocidos. */
export function sumar(vs: readonly Importe[]): { suma: Importe; desconocidos: number } {
  let c: number | null = null;
  let desconocidos = 0;
  for (const v of vs) {
    if (v === null) desconocidos += 1;
    else c = (c ?? 0) + cent(v);
  }
  return { suma: c === null ? null : eur(c), desconocidos };
}
const sumaOnull = (vs: readonly Importe[]) => sumar(vs).suma;
export const mismoImporte = (a: number, b: number) => cent(a) === cent(b);

// ---------------------------------------------------------------------------
// Importación
// ---------------------------------------------------------------------------

export function estadoImportacion(imps: readonly ImportacionCashflow[], hoy: string, config: ConfigCashflow = CONFIG_CASHFLOW): { estado: EstadoImportacion; avisos: AvisoCashflow[] } {
  const vigentes = imps.filter((i) => i.vigente);
  const vigente = vigentes.length === 1 ? vigentes[0] : null;
  const ultima = [...imps].sort((a, b) => Date.parse(b.importado_at) - Date.parse(a.importado_at))[0] ?? null;
  const fv = vigente ? fechaMadrid(vigente.importado_at) : null;
  const dias = fv === null ? null : diasEntre(fv, hoy);
  const avisos: AvisoCashflow[] = [];
  const base = { decena: null, hasta: null, cuenta: null, cubre: null, importe: null, devolucion: null, decenas: [], incompleto: false };
  if (vigente === null) {
    avisos.push({ ...base, tipo: 'gris', codigo: 'SIN_IMPORTACION_VIGENTE',
      texto: vigentes.length === 0 ? 'No hay ninguna importación vigente del Excel.' : 'Hay más de una importación marcada como vigente: no se sabe cuál usar.' });
  } else if (dias !== null && dias > config.dias_importacion_antigua) {
    avisos.push({ ...base, tipo: 'gris', codigo: 'IMPORTACION_ANTIGUA', texto: `La importación vigente del Excel tiene ${dias} días.` });
  }
  if (ultima !== null && !config.estados_importacion_ok.includes(ultima.estado)) {
    avisos.push({ ...base, tipo: 'gris', codigo: 'IMPORTACION_FALLIDA', texto: `La última importación del Excel falló (${fechaMadrid(ultima.importado_at) ?? 'sin fecha'}): se muestran los datos de la vigente.` });
  }
  return { estado: { vigente, ultima, dias }, avisos };
}

// ---------------------------------------------------------------------------
// Cálculo
// ---------------------------------------------------------------------------

const claveLinea = (categoria: string, concepto: string) => `${categoria}\u0000${concepto}`;
const NEUTRO = { vencimientos: null, media: null, diferencia: false, desconocidos: 0, partes: [] } as const;

interface Valida extends ImporteCashflow { cuenta: CuentaCashflow; sentido: SentidoMovimiento; clase: ClaseMovimiento }

/** Media de una categoría para una cuenta. */
function calcularMedia(filas: readonly Valida[], unidad: UnidadMedia, ultimaReal: string | null, config: ConfigCashflow): DesgloseMedia {
  const vacia: DesgloseMedia = { unidad, base: [], media: null, decena_habitual: null };
  if (ultimaReal === null) return vacia;
  const porDecena = new Map<string, number>();
  for (const f of filas) {
    if (f.decena_inicio > ultimaReal || f.importe === null) continue;
    porDecena.set(f.decena_inicio, (porDecena.get(f.decena_inicio) ?? 0) + cent(signo(f) * f.importe));
  }
  const primera = [...porDecena.keys()].sort()[0];
  if (primera === undefined) return vacia;
  if (unidad === 'decenas') {
    // Últimas N decenas reales (desde la primera con datos): una decena sin filas cuenta como 0.
    const base: { clave: string; importe: number }[] = [];
    for (let d = ultimaReal; base.length < config.decenas_media && d >= primera; d = anteriorDecena(d)) base.unshift({ clave: d, importe: eur(porDecena.get(d) ?? 0) });
    return { unidad, base, media: eur(Math.round(base.reduce((a, x) => a + cent(x.importe), 0) / base.length)), decena_habitual: null };
  }
  // Meses: los completos (sus tres decenas reales) con datos de la categoría; los últimos N.
  const meses = new Map<string, { total: number; mayor: { ordinal: 1 | 2 | 3; c: number } }>();
  for (const [d, c] of porDecena) {
    const ym = d.slice(0, 7);
    if (`${ym}-21` > ultimaReal) continue;
    const m = meses.get(ym) ?? { total: 0, mayor: { ordinal: ordinalDecena(d), c } };
    m.total += c;
    if (Math.abs(c) > Math.abs(m.mayor.c)) m.mayor = { ordinal: ordinalDecena(d), c };
    meses.set(ym, m);
  }
  const ultimos = [...meses.entries()].sort(([a], [b]) => a.localeCompare(b)).slice(-config.meses_media_soe);
  if (ultimos.length === 0) return vacia;
  // Decena habitual: la más frecuente entre esos meses (empate: la más tardía).
  const veces = [0, 0, 0, 0];
  for (const [, m] of ultimos) veces[m.mayor.ordinal] += 1;
  const habitual = ([3, 2, 1] as const).reduce((mejor, o) => (veces[o] > veces[mejor] ? o : mejor), 3 as 1 | 2 | 3);
  return {
    unidad,
    base: ultimos.map(([ym, m]) => ({ clave: ym, importe: eur(m.total) })),
    media: eur(Math.round(ultimos.reduce((a, [, m]) => a + m.total, 0) / ultimos.length)),
    decena_habitual: habitual,
  };
}
const signo = (f: { sentido: SentidoMovimiento }) => (f.sentido === 'ENTRADA' ? 1 : -1);

function desgloseVencimientos(comercial: string, vs: readonly VencimientoCashflow[], finReal: string | null): DesgloseVencimientos {
  const ya = vs.filter((v) => v.fecha_pago !== null && finReal !== null && v.fecha_pago <= finReal);
  const resto = vs.filter((v) => !ya.includes(v));
  const noDoc = resto.filter((v) => v.importe !== null && v.sentido === 'NO_DOCUMENTADO');
  const neg = resto.filter((v) => v.cargo_negativo);
  const incluidos = resto.filter((v) => !noDoc.includes(v) && !neg.includes(v));
  const cargos = sumar(incluidos.filter((v) => v.sentido === 'CARGO').map((v) => v.importe));
  const abonos = sumar(incluidos.filter((v) => v.sentido === 'ABONO').map((v) => (v.importe === null ? null : -Math.abs(v.importe))));
  const neto = sumaOnull([cargos.suma, abonos.suma].filter((x) => x !== null));
  return { comercial, incluidos, neto, sin_importe: cargos.desconocidos + abonos.desconocidos, no_documentado: noDoc, cargo_negativo: neg, ya_en_banco: ya };
}

function resumen(lineas: readonly Linea[], d: string, real: boolean): Omit<ResumenDecena, 'saldo' | 'saldo_bancos' | 'saldo_formulas' | 'incompleto'> {
  const celdas = lineas.map((l) => ({ l, c: l.celdas[d] })).filter((x) => x.c !== undefined && x.c.en_saldo);
  const de = (f: (l: Linea) => boolean) => sumaOnull(celdas.filter((x) => f(x.l)).map((x) => x.c.importe).filter((v) => v !== null));
  return {
    decena: d,
    real,
    entradas: de((l) => l.clase === 'FARMACIA' && l.sentido === 'ENTRADA'),
    salidas: de((l) => l.clase === 'FARMACIA' && l.sentido === 'SALIDA'),
    farmacia: de((l) => l.clase === 'FARMACIA'),
    no_relacionadas: de((l) => l.clase === 'NO_RELACIONADA'),
    traspasos: de((l) => l.clase === 'TRASPASO'),
    neto: de(() => true),
    desconocidos: celdas.reduce((a, x) => a + x.c.desconocidos, 0),
  };
}

function ordenarLineas(ls: Linea[]): Linea[] {
  const rango = (l: Linea) => (l.clase === 'FARMACIA' ? 0 : l.clase === 'NO_RELACIONADA' ? 1 : 2) * 2 + (l.sentido === 'ENTRADA' ? 0 : 1);
  return ls.sort((a, b) => rango(a) - rango(b) || a.categoria.localeCompare(b.categoria, 'es') || Number(a.media) - Number(b.media) || a.concepto.localeCompare(b.concepto, 'es'));
}

/** Calcula las vistas, los avisos y lo que queda fuera. `decenas`: horizonte (por defecto, el de los datos y las vistas). */
export function calcularCashflow(dto: Pick<CashflowDTO, 'hoy' | 'importaciones' | 'cuentas' | 'importes' | 'saldos' | 'vencimientos'> & { config?: ConfigCashflow },
  elecciones: Elecciones = {}): ResultadoCashflow {
  const config = dto.config ?? CONFIG_CASHFLOW;
  const hoy = dto.hoy;
  // Cuentas: solo PIO y RITA, y solo si figuran en cf_cashflow_cuentas (falla cerrado).
  const declaradas = new Set(dto.cuentas.map((c) => c.codigo));
  const cuentas = CUENTAS_CASHFLOW.filter((c) => declaradas.has(c));
  const esCuenta = (c: string): c is CuentaCashflow => (cuentas as readonly string[]).includes(c);
  const fuera: FueraDeCashflow = {
    filas_otras_cuentas: 0, categorias_no_reconocidas: [], filas_no_reconocidas: 0, filas_decena_no_valida: 0,
    venc_sin_concepto: [], venc_no_suman: [], venc_sin_fecha: 0, venc_en_decenas_reales: [],
  };
  const validas: Valida[] = [];
  const noReconocidas = new Set<string>();
  for (const f of dto.importes) {
    if (!esCuenta(f.cuenta)) { fuera.filas_otras_cuentas += 1; continue; }
    if (!esDecenaInicio(f.decena_inicio) || f.decena_fin !== finDecena(f.decena_inicio)) { fuera.filas_decena_no_valida += 1; continue; }
    const c = clasificarCategoria(f.categoria);
    if (c === null) { fuera.filas_no_reconocidas += 1; noReconocidas.add(f.categoria); continue; }
    validas.push({ ...f, cuenta: f.cuenta, ...c });
  }
  fuera.categorias_no_reconocidas = [...noReconocidas].sort();
  const saldos = dto.saldos.filter((s) => esCuenta(s.cuenta) && esDecenaInicio(s.decena_inicio));
  fuera.filas_otras_cuentas += dto.saldos.filter((s) => !esCuenta(s.cuenta)).length;

  // Horizonte: de la primera decena con datos (o de la ventana) a la última (o a la ventana).
  const actual = decenaDe(hoy);
  const mesActual = hoy.slice(0, 7);
  const extremos = [
    ...validas.map((f) => f.decena_inicio), ...saldos.map((s) => s.decena_inicio),
    moverDecena(actual, -config.decenas_pasadas), moverDecena(actual, config.decenas_proximas - 1),
    `${sumarMeses(mesActual, -config.meses_pasados)}-01`, `${sumarMeses(mesActual, config.meses_proximos - 1)}-21`,
  ].sort();
  const decenas = rangoDecenas(extremos[0], extremos[extremos.length - 1]);

  const avisos: AvisoCashflow[] = [];
  const base = { decena: null, hasta: null, cuenta: null, cubre: null, importe: null, devolucion: null, decenas: [], incompleto: false };
  const imp = estadoImportacion(dto.importaciones, hoy, config);
  avisos.push(...imp.avisos);

  const eleccionDe = (cat: string): Eleccion => elecciones[cat] ?? ELECCION_POR_DEFECTO;
  const vistas = {} as Record<VistaCuenta, ResultadoVista>;
  const categoriasMedia = new Set<string>();

  for (const cuenta of cuentas) {
    const filas = validas.filter((f) => f.cuenta === cuenta);
    const ss = new Map(saldos.filter((s) => s.cuenta === cuenta).map((s) => [s.decena_inicio, s]));
    const conBanco = [...ss.values()].filter((s) => s.saldo_bancos !== null).map((s) => s.decena_inicio).sort();
    const ultimaReal = conBanco.length ? conBanco[conBanco.length - 1] : null;
    const finReal = ultimaReal === null ? null : finDecena(ultimaReal);
    const esReal = (d: string) => ultimaReal !== null && d <= ultimaReal;
    if (ultimaReal === null) avisos.push({ ...base, tipo: 'gris', codigo: 'SIN_SALDO_BANCO', cuenta, texto: `${cuenta}: ninguna decena tiene saldo de banco; no se puede calcular el saldo previsto.` });

    // Líneas del Excel.
    const lineas = new Map<string, Linea>();
    const linea = (categoria: string, concepto: string, sentido: SentidoMovimiento, clase: ClaseMovimiento, media = false): Linea => {
      const k = claveLinea(categoria, concepto);
      let l = lineas.get(k);
      if (!l) { l = { clave: k, categoria, concepto, sentido, clase, media, celdas: {} }; lineas.set(k, l); }
      return l;
    };
    const grupos = new Map<string, Valida[]>();
    for (const f of filas) {
      const k = `${claveLinea(f.categoria, f.concepto)}\u0000${f.decena_inicio}`;
      grupos.set(k, [...(grupos.get(k) ?? []), f]);
    }
    for (const g of grupos.values()) {
      const f = g[0];
      const l = linea(f.categoria, f.concepto, f.sentido, f.clase);
      const s = sumar(g.map((x) => (x.importe === null ? null : signo(x) * x.importe)));
      const real = esReal(f.decena_inicio);
      l.celdas[f.decena_inicio] = {
        ...NEUTRO, partes: [], cuenta, decena: f.decena_inicio, real, fuente: real ? 'REAL' : 'EXCEL',
        importe: s.desconocidos > 0 && s.suma === null ? null : s.suma, en_saldo: true, excel: s.suma, excel_filas: g.length, desconocidos: s.desconocidos,
      };
    }

    // a) Vencimientos del sistema (solo PIO; RITA solo con datos bancarios).
    if (cuenta === CUENTA_VENCIMIENTOS) {
      const porClave = new Map<string, VencimientoCashflow[]>();
      for (const v of dto.vencimientos) {
        if (v.fecha_vencimiento === null) { fuera.venc_sin_fecha += 1; continue; }
        const d = decenaDe(v.fecha_vencimiento.slice(0, 10));
        if (esReal(d) || ultimaReal === null) {
          if (!esPagado(v.estado_pago)) fuera.venc_en_decenas_reales.push(v); // A_REVISAR tampoco cuenta como pagado
          continue;
        }
        const corr = v.proveedor_comercial === null ? undefined : CORRESPONDENCIAS_PROVEEDOR.find((c) => c.comercial === v.proveedor_comercial);
        if (!corr) { fuera.venc_sin_concepto.push(v); continue; }
        const k = `${corr.comercial}\u0000${d}`;
        porClave.set(k, [...(porClave.get(k) ?? []), v]);
      }
      for (const [k, vs] of porClave) {
        const [comercial, d] = k.split('\u0000');
        // Línea del Excel con ese nombre comercial (primero en RS Proveedores); si no hay, se crea.
        const candidatas = [...lineas.values()].filter((l) => !l.media && comercialDeConcepto(l.concepto) === comercial);
        const l = candidatas.find((x) => x.categoria === CATEGORIA_PROVEEDORES) ?? candidatas[0]
          ?? linea(CATEGORIA_PROVEEDORES, CORRESPONDENCIAS_PROVEEDOR.find((c) => c.comercial === comercial)!.conceptos[0], 'SALIDA', 'FARMACIA');
        const dv = desgloseVencimientos(comercial, vs, finReal);
        // Ninguno suma (ya en el banco, sentido no documentado o cargo negativo): manda el Excel; se cuentan aparte.
        if (dv.incluidos.length === 0) { fuera.venc_no_suman.push(...vs); continue; }
        const previa = l.celdas[d];
        // neto = lo que se paga (cargos − abonos): en una línea de salida resta.
        const importe = dv.neto === null ? null : eur(cent(signo(l) * dv.neto));
        const excel = previa?.excel ?? null;
        const diferencia = previa !== undefined && previa.excel_filas > 0 && (importe === null || excel === null || !mismoImporte(importe, excel));
        l.celdas[d] = {
          ...NEUTRO, partes: [], cuenta, decena: d, real: false, fuente: 'VENCIMIENTOS', importe, en_saldo: true,
          excel, excel_filas: previa?.excel_filas ?? 0, vencimientos: dv, diferencia, desconocidos: dv.sin_importe,
        };
      }
    }

    // c) Medias (TPV, efectivo, SOE).
    for (const [cat, unidad] of Object.entries(CATEGORIAS_MEDIA)) {
      const fc = filas.filter((f) => f.categoria === cat);
      if (fc.length === 0) continue;
      categoriasMedia.add(cat);
      const m = calcularMedia(fc, unidad, ultimaReal, config);
      const usar = eleccionDe(cat) === 'media' && m.media !== null;
      const lm = linea(cat, CONCEPTO_MEDIA, fc[0].sentido, fc[0].clase, true);
      for (const d of decenas) {
        if (esReal(d) || ultimaReal === null) continue;
        if (unidad === 'meses' && ordinalDecena(d) !== m.decena_habitual) continue;
        lm.celdas[d] = { ...NEUTRO, partes: [], cuenta, decena: d, real: false, fuente: 'MEDIA', importe: m.media, en_saldo: usar, excel: null, excel_filas: 0, media: m };
      }
      if (usar) {
        for (const l of lineas.values()) {
          if (l.categoria !== cat || l.media) continue;
          for (const c of Object.values(l.celdas)) if (!c.real) c.en_saldo = false;
        }
      }
    }

    // Saldos.
    const ls = ordenarLineas([...lineas.values()]);
    const res: Record<string, ResumenDecena> = {};
    let saldo: Importe = null;
    let incompleto = false;
    for (const d of decenas) {
      const real = esReal(d);
      const r = resumen(ls, d, real);
      const s = ss.get(d);
      let saldoD: Importe;
      if (real) {
        // Real: el saldo del banco de la decena (null si falta: no se rellena).
        saldoD = s?.saldo_bancos ?? null;
        saldo = saldoD;
        incompleto = false;
      } else {
        // Previsto: anterior + entradas − salidas (desde el saldo de partida).
        if (saldo !== null) saldo = eur(cent(saldo) + cent(r.neto ?? 0));
        incompleto = incompleto || r.desconocidos > 0;
        saldoD = saldo;
      }
      res[d] = { ...r, saldo: saldoD, saldo_bancos: s?.saldo_bancos ?? null, saldo_formulas: s?.saldo_formulas ?? null, incompleto: !real && incompleto };
    }
    vistas[cuenta] = { vista: cuenta, ultima_real: ultimaReal, saldo_partida: ultimaReal === null ? null : ss.get(ultimaReal)?.saldo_bancos ?? null, lineas: ls, decenas: res };
  }

  // Consolidado: suma de las cuentas; traspasos fuera (neutros).
  const partesV = cuentas.map((c) => vistas[c]);
  const lineasC = new Map<string, Linea>();
  for (const v of partesV) {
    for (const l of v.lineas) {
      if (l.clase === 'TRASPASO') continue;
      let lc = lineasC.get(l.clave);
      if (!lc) { lc = { ...l, celdas: {} }; lineasC.set(l.clave, lc); }
      for (const [d, c] of Object.entries(l.celdas)) {
        const prev = lc.celdas[d];
        const partes = [...(prev?.partes ?? []), c];
        const cuentan = partes.filter((p) => p.en_saldo);
        const s = sumar(cuentan.map((p) => p.importe));
        const fuentes = new Set(cuentan.map((p) => p.fuente));
        lc.celdas[d] = {
          ...NEUTRO, cuenta: c.cuenta, decena: d, real: partes.every((p) => p.real),
          fuente: fuentes.size === 1 ? [...fuentes][0] : fuentes.size === 0 ? c.fuente : 'MIXTA',
          // Si ninguna parte entra en el saldo (cifra a la vista sin sumar), la suma de todas las partes.
          importe: cuentan.length === 0 ? sumar(partes.map((p) => p.importe)).suma : s.suma, en_saldo: cuentan.length > 0,
          excel: sumaOnull(partes.map((p) => p.excel).filter((x) => x !== null)), excel_filas: partes.reduce((a, p) => a + p.excel_filas, 0),
          diferencia: partes.some((p) => p.diferencia), desconocidos: cuentan.reduce((a, p) => a + p.desconocidos, 0), partes,
          media: partes.find((p) => p.media)?.media ?? null, vencimientos: partes.find((p) => p.vencimientos)?.vencimientos ?? null,
        };
      }
    }
  }
  const lsC = ordenarLineas([...lineasC.values()]);
  const resC: Record<string, ResumenDecena> = {};
  for (const d of decenas) {
    const real = partesV.length > 0 && partesV.every((v) => v.decenas[d].real);
    const r = resumen(lsC, d, real);
    const saldosD = partesV.map((v) => v.decenas[d].saldo);
    const sum = (f: (x: ResumenDecena) => Importe) => {
      const vs = partesV.map((v) => f(v.decenas[d]));
      return vs.some((x) => x === null) ? null : eur(vs.reduce((a: number, x) => a + cent(x as number), 0));
    };
    resC[d] = {
      ...r, traspasos: sumaOnull(partesV.map((v) => v.decenas[d].traspasos).filter((x) => x !== null)),
      saldo: partesV.length === 0 || saldosD.some((x) => x === null) ? null : eur(saldosD.reduce((a: number, x) => a + cent(x as number), 0)),
      saldo_bancos: sum((x) => x.saldo_bancos), saldo_formulas: sum((x) => x.saldo_formulas),
      incompleto: partesV.some((v) => v.decenas[d].incompleto),
    };
    const t = resC[d].traspasos;
    if (t !== null && t !== 0 && partesV.length > 1) {
      avisos.push({ ...base, tipo: 'gris', codigo: 'TRASPASO_SIN_CONTRAPARTIDA', decena: d, hasta: d, importe: t,
        texto: 'Los traspasos entre cuentas de esta decena no se compensan: revisa el Excel.' });
    }
  }
  const ultimasC = partesV.map((v) => v.ultima_real);
  vistas.CONSOLIDADO = {
    vista: 'CONSOLIDADO',
    ultima_real: ultimasC.length && ultimasC.every((x) => x !== null) ? (ultimasC as string[]).sort()[0] : null,
    saldo_partida: sumaOnull(partesV.map((v) => v.saldo_partida)),
    lineas: lsC,
    decenas: resC,
  };

  avisos.push(...avisosSaldo(vistas, cuentas, decenas, config));
  return {
    hoy, decenas, vistas, avisos, importacion: imp.estado, fuera,
    elecciones: Object.fromEntries([...categoriasMedia].map((c) => [c, eleccionDe(c)])),
    categorias_media: [...categoriasMedia].sort(),
  };
}

/**
 * Avisos de saldo (solo decenas previstas, saldo mínimo de la configuración):
 *   naranja: una cuenta queda por debajo y la otra la cubre (el consolidado no baja del mínimo). Episodio = decenas
 *            seguidas; importe = el mayor cubierto; devolución = primera decena posterior en que la cuenta recupera.
 *   rojo:    el consolidado queda por debajo; importe = lo que falta (el mayor del episodio).
 */
function avisosSaldo(vistas: Record<VistaCuenta, ResultadoVista>, cuentas: readonly CuentaCashflow[], decenas: readonly string[], config: ConfigCashflow): AvisoCashflow[] {
  const min = config.saldo_minimo;
  const base = { cubre: null, devolucion: null };
  const out: AvisoCashflow[] = [];
  const episodios = (marcas: { decena: string; importe: number; incompleto: boolean }[]) => {
    const eps: { decena: string; importe: number; incompleto: boolean }[][] = [];
    for (const m of marcas) {
      const ult = eps[eps.length - 1];
      if (ult && siguienteDecena(ult[ult.length - 1].decena) === m.decena) ult.push(m); else eps.push([m]);
    }
    return eps;
  };
  const C = vistas.CONSOLIDADO;
  const previstas = decenas.filter((d) => !C.decenas[d].real && C.decenas[d].saldo !== null);
  const rojas = previstas.filter((d) => (C.decenas[d].saldo as number) < min);
  for (const ep of episodios(rojas.map((d) => ({ decena: d, importe: eur(cent(min) - cent(C.decenas[d].saldo as number)), incompleto: C.decenas[d].incompleto })))) {
    const mayor = Math.max(...ep.map((x) => x.importe));
    out.push({
      ...base, tipo: 'rojo', codigo: 'CONSOLIDADO_NEGATIVO', decena: ep[0].decena, hasta: ep[ep.length - 1].decena, cuenta: null, importe: mayor,
      decenas: ep.map(({ decena, importe }) => ({ decena, importe })), incompleto: ep.some((x) => x.incompleto),
      texto: 'El saldo consolidado queda en negativo.',
    });
  }
  if (cuentas.length < 2) return out;
  for (const a of cuentas) {
    const b = cuentas.find((x) => x !== a)!;
    const A = vistas[a];
    const marcas = previstas
      .filter((d) => A.decenas[d].saldo !== null && (A.decenas[d].saldo as number) < min && !rojas.includes(d))
      .map((d) => ({ decena: d, importe: eur(cent(min) - cent(A.decenas[d].saldo as number)), incompleto: A.decenas[d].incompleto }));
    for (const ep of episodios(marcas)) {
      const fin = ep[ep.length - 1].decena;
      const devolucion = decenas.find((d) => d > fin && A.decenas[d].saldo !== null && (A.decenas[d].saldo as number) >= min) ?? null;
      const mayor = Math.max(...ep.map((x) => x.importe));
      out.push({
        tipo: 'naranja', codigo: 'CUENTA_CUBIERTA', decena: ep[0].decena, hasta: fin, cuenta: a, cubre: b, importe: mayor, devolucion,
        decenas: ep.map(({ decena, importe }) => ({ decena, importe })), incompleto: ep.some((x) => x.incompleto),
        texto: `${a} queda en negativo y ${b} la cubre.`,
      });
    }
  }
  return out.sort((x, y) => (x.decena ?? '').localeCompare(y.decena ?? ''));
}

// ---------------------------------------------------------------------------
// Vistas: columnas (decenas o meses) y agregados por columna
// ---------------------------------------------------------------------------

export type Escala = 'decenas' | 'mes';
export interface Columna {
  clave: string;
  escala: Escala;
  desde: string;
  hasta: string;
  decenas: string[];
  /** Contiene hoy. */
  actual: boolean;
}
/** Decenas: las 3 pasadas y las 9 próximas (con la actual). Mes: los 3 pasados y los 9 próximos (con el actual). */
export function columnasVista(hoy: string, escala: Escala, config: ConfigCashflow = CONFIG_CASHFLOW): Columna[] {
  if (escala === 'decenas') {
    const actual = decenaDe(hoy);
    return rangoDecenas(moverDecena(actual, -config.decenas_pasadas), moverDecena(actual, config.decenas_proximas - 1))
      .map((d) => ({ clave: d, escala, desde: d, hasta: finDecena(d), decenas: [d], actual: d === actual }));
  }
  const out: Columna[] = [];
  for (let i = -config.meses_pasados; i < config.meses_proximos; i++) {
    const ym = sumarMeses(hoy.slice(0, 7), i);
    out.push({ clave: ym, escala, desde: `${ym}-01`, hasta: finDeMes(ym), decenas: decenasDelMes(ym), actual: i === 0 });
  }
  return out;
}

export type TipoColumna = 'real' | 'previsto' | 'mixto';
export interface CeldaColumna {
  importe: Importe;
  tipo: TipoColumna;
  fuentes: FuenteCelda[];
  diferencia: boolean;
  desconocidos: number;
  /** Cifra a la vista que no entra en el saldo (la otra opción de «Media / Excel»). */
  sin_usar: Importe;
  celdas: Celda[];
}
function tipoDe(reales: boolean[]): TipoColumna {
  return reales.every((x) => x) ? 'real' : reales.some((x) => x) ? 'mixto' : 'previsto';
}
export function tipoColumna(v: ResultadoVista, col: Columna): TipoColumna {
  return tipoDe(col.decenas.map((d) => v.decenas[d]?.real ?? false));
}
/** Celda de una línea en una columna (null = sin movimientos). */
export function celdaColumna(l: Linea, col: Columna, v: ResultadoVista): CeldaColumna | null {
  const cs = col.decenas.map((d) => l.celdas[d]).filter((c): c is Celda => c !== undefined);
  if (cs.length === 0) return null;
  const usadas = cs.filter((c) => c.en_saldo);
  const s = sumar(usadas.map((c) => c.importe));
  return {
    importe: s.suma, tipo: tipoColumna(v, col), fuentes: [...new Set(cs.map((c) => c.fuente))],
    diferencia: cs.some((c) => c.diferencia), desconocidos: usadas.reduce((a, c) => a + c.desconocidos, 0),
    sin_usar: sumaOnull(cs.filter((c) => !c.en_saldo).map((c) => c.importe).filter((x) => x !== null)), celdas: cs,
  };
}
/** Total de una categoría en una columna. */
export function totalCategoria(ls: readonly Linea[], col: Columna, v: ResultadoVista): CeldaColumna | null {
  const cs = ls.map((l) => celdaColumna(l, col, v)).filter((c): c is CeldaColumna => c !== null);
  if (cs.length === 0) return null;
  return {
    importe: sumaOnull(cs.map((c) => c.importe).filter((x) => x !== null)), tipo: tipoColumna(v, col),
    fuentes: [...new Set(cs.flatMap((c) => c.fuentes))], diferencia: cs.some((c) => c.diferencia),
    desconocidos: cs.reduce((a, c) => a + c.desconocidos, 0),
    sin_usar: sumaOnull(cs.map((c) => c.sin_usar).filter((x) => x !== null)), celdas: cs.flatMap((c) => c.celdas),
  };
}
export type CampoResumen = 'entradas' | 'salidas' | 'farmacia' | 'no_relacionadas' | 'traspasos' | 'neto';
export function resumenColumna(v: ResultadoVista, col: Columna, campo: CampoResumen): Importe {
  return sumaOnull(col.decenas.map((d) => v.decenas[d]?.[campo] ?? null).filter((x) => x !== null));
}
/** Saldo al cierre de la columna (el de su última decena). */
export function saldoColumna(v: ResultadoVista, col: Columna): { saldo: Importe; incompleto: boolean; bancos: Importe; formulas: Importe } {
  const r = v.decenas[col.decenas[col.decenas.length - 1]];
  return { saldo: r?.saldo ?? null, incompleto: r?.incompleto ?? false, bancos: r?.saldo_bancos ?? null, formulas: r?.saldo_formulas ?? null };
}
/** Avisos de saldo que tocan una columna. */
export function avisosColumna(avisos: readonly AvisoCashflow[], col: Columna): AvisoCashflow[] {
  return avisos.filter((a) => a.tipo !== 'gris' && a.decenas.some((x) => col.decenas.includes(x.decena)));
}
/** Agrupa las líneas por categoría (en el orden de las líneas). */
export function porCategoria(ls: readonly Linea[]): { categoria: string; sentido: SentidoMovimiento; clase: ClaseMovimiento; lineas: Linea[] }[] {
  const out: { categoria: string; sentido: SentidoMovimiento; clase: ClaseMovimiento; lineas: Linea[] }[] = [];
  for (const l of ls) {
    const g = out.find((x) => x.categoria === l.categoria);
    if (g) g.lineas.push(l); else out.push({ categoria: l.categoria, sentido: l.sentido, clase: l.clase, lineas: [l] });
  }
  return out;
}
