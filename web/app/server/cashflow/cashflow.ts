/**
 * H7: pantalla Cashflow. Módulo puro: lo usan el servidor (FIXTURES), el front (que recalcula al cambiar «Media / Excel»),
 * check_fixtures y las pruebas.
 *
 * Decisiones de Marc: el Excel es la referencia; la web solo lee (sin escrituras ni excepción nueva). Decenas y mes. Por
 * cuenta bancaria (PIO, RITA) más consolidado. RITA activa en Cashflow solo con datos bancarios: a RITA nunca se le suman
 * vencimientos del sistema; solo lo que trae la importación del Excel y sus saldos de banco.
 *
 * Contrato de datos (migración 38, en producción; H7-REAL):
 *   cf_cashflow_importaciones (id, archivo_nombre, origen NOCHE|MANUAL, estado OK|ERROR, detalle_error, filas, importado_at,
 *                              vigente: como máximo una, siempre OK; una ERROR es solo cabecera, nunca vigente)
 *   cf_cashflow_cuentas       (codigo PIO|RITA|SL, farmacia: null en SL)
 *   cf_cashflow_importes      (id, importacion_id, cuenta, farmacia, decena_inicio, decena_fin, categoria "RE …"/"RS …",
 *                              concepto | null, importe ≠ 0 con el signo de la celda; sin fila = 0)
 *   cf_cashflow_saldos        (id, importacion_id, cuenta, farmacia, decena_inicio —el fin se deduce—, saldo_inicial,
 *                              saldo_formulas, saldo_bancos | null = decena aún no cuadrada con el banco)
 *   Solo se usan los importes y saldos de la importación vigente (nunca se mezclan importaciones).
 *
 * Reglas:
 *   Real = decenas hasta la última con saldo_bancos de cada cuenta; saldo de partida = ese saldo_bancos.
 *   Previsión (H7-REAL-2), por cuenta y categoría, en cada decena futura, por orden de prioridad (ORDEN_PRIORIDAD):
 *     a) PIO: vencimientos del sistema (contrato H6) de los conceptos del Excel que corresponden por nombre comercial
 *        (CORRESPONDENCIAS_PROVEEDOR, único punto). Sustituyen lo anotado en el Excel para ese concepto y decena; si los dos
 *        existen y difieren, «posible duplicado o diferencia».
 *     a') Apunte manual: hueco preparado, sin datos todavía (llegará con tablas del circuito). Sustituye al Excel de su
 *        concepto y decena; nunca a los vencimientos.
 *     b) Lo anotado en las decenas futuras del Excel (RITA, y PIO para lo no cubierto por a).
 *     c) Si la categoría no tiene nada en esa decena (ni a, ni a', ni b): media de la misma posición de decena (1.ª, 2.ª o
 *        3.ª del mes) en los últimos N meses reales (N = CONFIG_CASHFLOW.meses_media, único punto). Todas las categorías
 *        RE y RS, también TPV, efectivo, SOE (cae en su decena) y «no relacionadas»; los traspasos, nunca (neutros).
 *     d) «RS Modelo …» (impuestos trimestrales): la misma decena del mismo mes del año anterior, no la media.
 *     Sin doble cómputo: con a, a' o b en esa categoría y decena no se añade media. H7-REAL-3: en las categorías con
 *     vencimientos del sistema, por concepto: lo previsto sustituye solo a su concepto y el resto lleva la «media del
 *     resto» (la de la categoría sin esos conceptos). «Media / Excel» por categoría: con
 *     «Excel», solo lo anotado (la media queda a la vista sin sumar).
 *   Saldo previsto = anterior + entradas − salidas. Traspasos entre cuentas propias: neutros en el consolidado. Los que no
 *   se compensan (traspasos a la SL, fondos…) no son aviso: solo una línea plegada con las decenas visibles.
 *   «No relacionadas con la farmacia»: cuentan en el saldo, no en el «cash flow generado farmacia».
 *   Importe ausente = null, nunca 0: no suma y se cuenta (el saldo queda «incompleto»).
 *
 * Signo (H7-2, decisión de Marc): el importe del Excel se usa con el signo de la celda, nunca en valor absoluto. RE suma
 * el valor tal cual; RS lo resta tal cual: un RS negativo (abono dentro de un proveedor, comisión devuelta) reduce las
 * salidas, y un RE negativo reduce las entradas. Categoría sin prefijo RE/RS: fuera, contada.
 *
 * H7-REAL:
 *   E7: en una decena real con saldo_bancos ≠ saldo_formulas se muestra la diferencia (informativa, nunca error).
 *   Cuadre de control: saldo_inicial + ΣRE − ΣRS = saldo_formulas por cuenta y decena (tolerancia 0,005 € por importe).
 *   Si no cuadra, aviso gris; la web no recalcula nada.
 *   Cuentas fuera de la pantalla (SL): contadas en «Fuera de la previsión».
 *
 * Solo sintaxis TypeScript borrable; sin dependencias del servidor (el front lo importa).
 */
import type { EstadoPago, Importe, SentidoVencimiento } from '../contrato.ts';
import { esPagado, type EstadoPagoVencimiento } from '../pagos/pagos.ts';

// ---------------------------------------------------------------------------
// Configuración (único punto)
// ---------------------------------------------------------------------------

export interface ConfigCashflow {
  /**
   * N de la media por posición de decena: últimos N meses reales (la misma decena del mes en cada uno). H7-REAL-8
   * (decisión de Pío, 25/11/2026): 12. Toda media: de categoría, «media del resto», por concepto y frente a vencimientos.
   */
  meses_media: number;
  /**
   * H7-REAL-5: los vencimientos del sistema de un concepto son un MÍNIMO (solo existen para facturas ya recibidas): en
   * cada decena futura cuenta el mayor en valor absoluto entre su suma y la media del concepto en esa posición de decena.
   * false = la regla anterior (los vencimientos sustituyen al concepto); solo para comparar en check:real.
   */
  vencimientos_como_minimo: boolean;
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
  meses_media: 12,
  vencimientos_como_minimo: true,
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

export const TEXTO_SIN_DATOS = 'Todavía no hay datos importados';
/** Concepto de una fila del Excel sin concepto (concepto null). */
export const CONCEPTO_VACIO = 'Sin concepto';
/** Tolerancia del cuadre de control, por importe sumado (en euros). */
export const TOLERANCIA_CUADRE_POR_IMPORTE = 0.005;
export const TEXTO_POSIBLE_DUPLICADO = 'posible duplicado o diferencia';

/**
 * Orden de la previsión de una decena futura (MANUAL: hueco preparado, sin datos todavía). H7-REAL-8: la previsión base
 * es la primera de MANUAL, EXCEL y MEDIA; los VENCIMIENTOS no van primero: se comparan con ella y gana el mayor en valor
 * absoluto (vencimientos como mínimo).
 */
export const ORDEN_PRIORIDAD = ['VENCIMIENTOS', 'MANUAL', 'EXCEL', 'MEDIA'] as const;
/** Cómo se estima una categoría sin nada en la decena: media por posición o, en los modelos trimestrales, año anterior. */
export type ReglaEstimacion = 'POSICION' | 'ANIO_ANTERIOR';
// H7-REAL-9: ya no hay selector «Media / Excel» por categoría (la regla Excel frente a media aplica siempre) ni línea de
// «Media calculada» de categoría (cada concepto lleva su media en su línea).

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
  // H7-REAL-7 (decisión de Pío, 25/11/2026): JNTL CONSUMER y JHONSON & JHONSON quedan como KENVUE (CONCEPTOS_EQUIVALENTES);
  // los vencimientos del sistema con nombre comercial KENVUE van a esa línea (proveedor_comercial.ts).
  { conceptos: ['KENVUE'], comercial: 'KENVUE' },
];

const normal = (s: string) => s.normalize('NFD').replace(/\p{M}/gu, '').toUpperCase().replace(/\s+/g, ' ').trim();

/**
 * H7-REAL-7 y H7-REAL-8 (decisiones de Pío, 25/11/2026): conceptos del Excel que son el mismo proveedor con otro nombre.
 * Único punto. Al leer los importes (real, Excel y, por tanto, media) se suman bajo `queda`, por cuenta y decena. Se
 * comparan sin mayúsculas, acentos ni espacios dobles. Un nombre truncado («…» al final) es un PREFIJO, tanto en el
 * alias como en el nombre que queda; el que queda es entonces el texto completo del Excel. Si un prefijo coincide con
 * ningún nombre o con más de uno distinto, ese par no se fusiona (falla cerrado) y se cuenta (resolverEquivalencias).
 */
export const CONCEPTOS_EQUIVALENTES: readonly { alias: string; queda: string }[] = [
  // H7-REAL-7
  { alias: 'JNTL CONSUMER (ORALDI…', queda: 'KENVUE' },
  { alias: 'JHONSON & JHONSON', queda: 'KENVUE' },
  // H7-REAL-8
  { alias: 'PROTECTFARMA', queda: 'PROTECFARMA' },
  { alias: 'SM NATURAL (SOLARAY)', queda: 'SOLARAY' },
  { alias: 'LAB. VILARDELL (NO USAR)', queda: 'LAB. VILARDELL' },
  { alias: 'BIODERMA (NAOS)', queda: 'BIODERMA' },
  { alias: 'DERMOFARM (CUMLAUDE)', queda: 'CUMLAUDE' },
  { alias: 'DERMOPHARMACIE I PERF…', queda: 'DERMOFARMACIA PERFUM…' },
  { alias: 'AREAFAR (ENNA CYCLE)', queda: 'AREAFAR' },
  { alias: 'EXPOFARM CREU, CASH', queda: 'EXPOFARM' },
  { alias: 'PEROXIDOS', queda: 'PEROXFARMA' },
];
/** Equivalencias resueltas contra los conceptos del Excel: texto del Excel → nombre que queda, y pares no fusionados. */
export interface EquivalenciasResueltas {
  mapa: ReadonlyMap<string, string>;
  /** Pares con algún prefijo que coincide con más de un nombre distinto (no se fusionan). */
  ambiguas: number;
  /** Pares con algún prefijo que no coincide con ningún nombre (no se fusionan). */
  sin_coincidencia: number;
}
const TRUNCADO = /(…|\.\.\.)$/;
/**
 * Resuelve CONCEPTOS_EQUIVALENTES contra los conceptos presentes. Nombre exacto: el que coincide (sin mayúsculas ni
 * acentos); si el que queda está en el Excel con otra grafía, se usa la del Excel (misma línea). Prefijo: exactamente un
 * nombre distinto o el par no se fusiona.
 */
export function resolverEquivalencias(conceptos: Iterable<string>, tabla: typeof CONCEPTOS_EQUIVALENTES = CONCEPTOS_EQUIVALENTES): EquivalenciasResueltas {
  const porNormal = new Map<string, string[]>();
  for (const c of new Set(conceptos)) porNormal.set(normal(c), [...(porNormal.get(normal(c)) ?? []), c]);
  const candidatos = (patron: string) => {
    const prefijo = TRUNCADO.test(patron);
    const p = normal(patron.replace(TRUNCADO, ''));
    return { prefijo, nombres: [...porNormal.keys()].filter((n) => (prefijo ? n.startsWith(p) : n === p)) };
  };
  const mapa = new Map<string, string>();
  let ambiguas = 0;
  let sinCoincidencia = 0;
  for (const e of tabla) {
    const a = candidatos(e.alias);
    const q = candidatos(e.queda);
    const fallos = [a, q].filter((x) => x.prefijo);
    if (fallos.some((x) => x.nombres.length > 1)) { ambiguas += 1; continue; }
    if (fallos.some((x) => x.nombres.length === 0)) { sinCoincidencia += 1; continue; }
    // Nombre que queda: el texto del Excel (truncado o con otra grafía); si no está, el de la tabla.
    const queda = q.nombres.length === 1 ? (porNormal.get(q.nombres[0]) as string[])[0] : e.queda;
    for (const n of a.nombres) {
      if (n === normal(queda)) continue;
      for (const original of porNormal.get(n) ?? []) mapa.set(original, queda);
    }
  }
  return { mapa, ambiguas, sin_coincidencia: sinCoincidencia };
}
/** Nombre que queda para un concepto del Excel (el mismo si no tiene equivalencia), dentro de `universo` (sus conceptos). */
export function conceptoEquivalente(concepto: string, universo: Iterable<string> = [concepto]): string {
  return resolverEquivalencias([concepto, ...universo]).mapa.get(concepto) ?? concepto;
}
/** Nombre comercial del sistema para un concepto del Excel (null = sin correspondencia). */
export function comercialDeConcepto(concepto: string): string | null {
  const n = normal(concepto);
  return CORRESPONDENCIAS_PROVEEDOR.find((c) => c.conceptos.some((x) => normal(x) === n))?.comercial ?? null;
}

/** Mismo concepto: igual sin mayúsculas ni acentos, o con el mismo nombre comercial (FEDERACIÓ = FEDEFARMA). */
export function mismoConcepto(a: string, b: string): boolean {
  return normal(a) === normal(b) || (comercialDeConcepto(a) !== null && comercialDeConcepto(a) === comercialDeConcepto(b));
}

export type SentidoMovimiento = 'ENTRADA' | 'SALIDA';
/**
 * TRASPASO = interno (PIO ↔ RITA): neutro en el consolidado y sin media. TRASPASO_EXTERNO (H7-REAL-4) = categoría de
 * traspasos con un concepto que no está en TRASPASOS_INTERNOS (a la SL, fondos, valores…): entrada o salida real, con
 * previsión (Excel y, si no, media por concepto) y en el saldo de su cuenta y del consolidado.
 */
export type ClaseMovimiento = 'FARMACIA' | 'NO_RELACIONADA' | 'TRASPASO' | 'TRASPASO_EXTERNO';
/**
 * H7-REAL-4 (decisión de Pío): conceptos de traspaso INTERNO entre PIO y RITA, por cuenta. Único punto. Se comparan sin
 * mayúsculas, acentos ni espacios. Cualquier otro concepto de una categoría de traspasos es externo.
 */
export const TRASPASOS_INTERNOS: Readonly<Record<string, readonly string[]>> = {
  PIO: ['TRANSFERENCIA DE RITA A PIO', 'La Caixa Rita', 'DEPOSITO CONECTADO'],
  RITA: ['TRASPÀS A PIO DEPOSITO CON.', 'DEPÓSITO CONECTADO'],
};
const compacto = (s: string) => normal(s).replace(/\s+/g, '');
/** ¿Concepto de traspaso interno (PIO ↔ RITA) de esa cuenta? */
export function esTraspasoInterno(cuenta: string, concepto: string | null): boolean {
  if (concepto === null) return false;
  const c = compacto(concepto);
  return (TRASPASOS_INTERNOS[cuenta] ?? []).some((x) => compacto(x) === c);
}
/** Clase de una fila: la de su categoría; en las de traspasos, interno o externo según el concepto. */
export function claseMovimiento(cuenta: string, categoria: string, concepto: string | null): { sentido: SentidoMovimiento; clase: ClaseMovimiento } | null {
  const c = clasificarCategoria(categoria);
  if (c === null || c.clase !== 'TRASPASO') return c;
  return { sentido: c.sentido, clase: esTraspasoInterno(cuenta, concepto) ? 'TRASPASO' : 'TRASPASO_EXTERNO' };
}
/** "RE …" = entrada, "RS …" = salida; traspasos y «no relacionadas» por su nombre. null = no reconocida. */
export function clasificarCategoria(categoria: string): { sentido: SentidoMovimiento; clase: ClaseMovimiento } | null {
  const m = /^(RE|RS)\s+(\S.*)$/.exec(categoria.trim());
  if (!m) return null;
  const resto = normal(m[2]);
  const clase: ClaseMovimiento = /TRASPAS/.test(resto) ? 'TRASPASO' : /NO RELACIONAD/.test(resto) ? 'NO_RELACIONADA' : 'FARMACIA';
  return { sentido: m[1] === 'RE' ? 'ENTRADA' : 'SALIDA', clase };
}
/** «RS Modelo …» (impuestos trimestrales): se estiman con el mismo mes del año anterior. */
export function esModeloTrimestral(categoria: string): boolean {
  return /^RS MODELO\b/.test(normal(categoria));
}
/**
 * Regla de estimación de una categoría (null = sin estimación por categoría: traspasos; los externos se estiman aparte,
 * por concepto, y los internos nunca).
 */
export function reglaEstimacion(categoria: string): ReglaEstimacion | null {
  const c = clasificarCategoria(categoria);
  if (c === null || c.clase === 'TRASPASO') return null;
  return esModeloTrimestral(categoria) ? 'ANIO_ANTERIOR' : 'POSICION';
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
  /** cf_cashflow_importaciones.id (uuid). */
  importacion_id: string;
  archivo_nombre: string;
  /** NOCHE | MANUAL. */
  origen: string;
  /** OK | ERROR. */
  estado: string;
  /** Solo en ERROR: códigos y celdas (nunca conceptos). */
  detalle_error: string | null;
  filas: number | null;
  importado_at: string;
  vigente: boolean;
}
export interface CuentaCashflowFila {
  codigo: string;
  farmacia: string | null;
}
export interface ImporteCashflow {
  id: string;
  importacion_id: string;
  cuenta: string;
  farmacia: string | null;
  decena_inicio: string;
  decena_fin: string;
  categoria: string;
  /** null = fila del Excel sin concepto (se muestra como CONCEPTO_VACIO). */
  concepto: string | null;
  importe: Importe;
}
export interface SaldoCashflow {
  id: string;
  importacion_id: string;
  cuenta: string;
  farmacia: string | null;
  /** El fin se deduce (días 10, 20 o fin de mes). */
  decena_inicio: string;
  saldo_inicial: Importe;
  saldo_formulas: Importe;
  saldo_bancos: Importe;
}
/** Filas de la importación vigente en cuentas fuera de la pantalla (SL): solo recuentos, nunca importes. */
export interface OtraCuentaCashflow {
  cuenta: string;
  importes: number;
  saldos: number;
}
/**
 * H7-REAL-2: apunte manual (prioridad entre los vencimientos y el Excel). Hueco preparado: todavía no hay tabla ni datos
 * (llegará con tablas del circuito); el servidor no envía ninguno.
 */
export interface ApunteManualCashflow {
  cuenta: string;
  decena_inicio: string;
  categoria: string;
  concepto: string | null;
  /** Con el signo de la celda, como el Excel (RE suma, RS resta). */
  importe: Importe;
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
  /** La vigente (si hay) y la última por importado_at. */
  importaciones: ImportacionCashflow[];
  cuentas: CuentaCashflowFila[];
  /** Solo de la importación vigente y de las cuentas de la pantalla. */
  importes: ImporteCashflow[];
  saldos: SaldoCashflow[];
  otras_cuentas: OtraCuentaCashflow[];
}
/** Respuesta de GET /api/cashflow: los datos de partida; el cálculo lo hace calcularCashflow (también en el front). */
export interface CashflowDTO extends DatosCashflow {
  farmacia: string;
  generado_at: string;
  /** Fecha de referencia (FIXTURES: la de la semilla; REAL: la del servidor, Europe/Madrid). */
  hoy: string;
  modo: 'FIXTURES' | 'REAL';
  config: ConfigCashflow;
  vencimientos: VencimientoCashflow[];
  pago: EstadoPago;
}

// ---------------------------------------------------------------------------
// Resultado
// ---------------------------------------------------------------------------

export type FuenteCelda = 'REAL' | 'VENCIMIENTOS' | 'MANUAL' | 'EXCEL' | 'MEDIA' | 'MIXTA';
export const TEXTO_FUENTE: Readonly<Record<FuenteCelda, string>> = {
  REAL: 'Real (Excel, decena con saldo de banco)',
  VENCIMIENTOS: 'Vencimientos del sistema',
  MANUAL: 'Apunte manual',
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
  regla: ReglaEstimacion;
  /** Posición (1.ª, 2.ª o 3.ª decena del mes) de la decena prevista. */
  posicion: 1 | 2 | 3;
  /** Decenas reales usadas, con el total de la categoría en cada una (0 = sin filas). */
  base: { clave: string; importe: number }[];
  /** POSICION: Σ base ÷ nº de decenas; ANIO_ANTERIOR: el total de la decena del año anterior. */
  media: Importe;
  /** Filas sin importe en la base (no suman). */
  sin_importe: number;
  /**
   * H7-REAL-3: conceptos que no entran en la media porque esa decena ya los prevé (vencimientos, apunte o Excel), en las
   * categorías con vencimientos: la cifra es la «media del resto». Vacío = media de toda la categoría.
   */
  excluidos: string[];
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
  /**
   * H7-REAL-8: con vencimientos, la otra cifra de la comparación (la que perdió): los vencimientos si ganó la previsión
   * base (apunte, Excel o media) y la previsión base si ganaron los vencimientos. null = sin comparación.
   */
  comparada: { fuente: 'VENCIMIENTOS' | 'MANUAL' | 'EXCEL' | 'MEDIA'; importe: number } | null;
  /** H7-REAL-9: Excel y media del concepto en la misma decena (gana el mayor en valor absoluto). null = no hubo los dos. */
  frente: { excel: number; media: number } | null;
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
  /** H7-REAL-7: conceptos del Excel sumados en esta línea por CONCEPTOS_EQUIVALENTES (vacío = ninguno). */
  incluye: string[];
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
  /** Traspasos internos (PIO ↔ RITA): en el consolidado deberían sumar 0. */
  traspasos: Importe;
  /** H7-REAL-4: traspasos externos (SL, fondos, valores…): cuentan en el saldo, también en el consolidado. */
  traspasos_externos: Importe;
  neto: Importe;
  saldo: Importe;
  saldo_bancos: Importe;
  saldo_formulas: Importe;
  /** E7: decena real con saldo_bancos ≠ saldo_formulas: banco − fórmulas (informativa). null = no hay diferencia. */
  diferencia_banco: Importe;
  /** Cuadre de control de la importación (por cuenta; en el consolidado, null). */
  cuadre: CuadreDecena | null;
  /** false = alguna cuenta no cuadra en esta decena; null = no se ha podido comprobar. */
  cuadra: boolean | null;
  desconocidos: number;
  /** Hay importes desconocidos en esta decena o antes (desde la partida). */
  incompleto: boolean;
}
/** saldo_inicial + ΣRE − ΣRS frente a saldo_formulas (valores de la importación, sin recalcular nada). */
export interface CuadreDecena {
  saldo_inicial: number;
  /** Σ de los RE tal cual (con su signo). */
  entradas: number;
  /** Σ de los RS tal cual (con su signo). */
  salidas: number;
  esperado: number;
  saldo_formulas: number;
  /** saldo_formulas − esperado. */
  diferencia: number;
  filas: number;
  cuadra: boolean;
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
  | 'SIN_SALDO_BANCO' | 'IMPORTACION_NO_CUADRA';
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
  /** Cuentas declaradas fuera de la pantalla (SL). */
  cuentas_fuera: string[];
  filas_otras_cuentas: number;
  /** Filas de una importación que no es la vigente (en REAL la lectura ya las filtra: debería ser 0). */
  filas_otra_importacion: number;
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
  /** Categorías con alguna cifra estimada (media o año anterior) en alguna cuenta. */
  categorias_media: string[];
  /** H7-REAL-8: equivalencias de concepto: filas sumadas bajo otro nombre (por cuenta) y pares no fusionados (suma de las cuentas). */
  equivalencias: { filas: Record<string, number>; ambiguas: number; sin_coincidencia: number };
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
  // Vigente: como máximo una y siempre OK (una ERROR nunca es vigente): si no, ninguna (falla cerrado).
  const vigentes = imps.filter((i) => i.vigente);
  const vigente = vigentes.length === 1 && config.estados_importacion_ok.includes(vigentes[0].estado) ? vigentes[0] : null;
  const ultima = [...imps].sort((a, b) => Date.parse(b.importado_at) - Date.parse(a.importado_at))[0] ?? null;
  const fv = vigente ? fechaMadrid(vigente.importado_at) : null;
  const dias = fv === null ? null : diasEntre(fv, hoy);
  const avisos: AvisoCashflow[] = [];
  const base = { decena: null, hasta: null, cuenta: null, cubre: null, importe: null, devolucion: null, decenas: [], incompleto: false };
  if (vigente === null) {
    avisos.push({ ...base, tipo: 'gris', codigo: 'SIN_IMPORTACION_VIGENTE',
      texto: vigentes.length === 0 ? 'No hay ninguna importación vigente del Excel.'
        : vigentes.length > 1 ? 'Hay más de una importación marcada como vigente: no se sabe cuál usar.'
          : 'La importación marcada como vigente no es correcta: no se usa.' });
  } else if (dias !== null && dias > config.dias_importacion_antigua) {
    avisos.push({ ...base, tipo: 'gris', codigo: 'IMPORTACION_ANTIGUA', texto: `La importación vigente del Excel tiene ${dias} días.` });
  }
  if (ultima !== null && !config.estados_importacion_ok.includes(ultima.estado)) {
    const detalle = ultima.detalle_error === null ? 'sin detalle' : ultima.detalle_error;
    avisos.push({ ...base, tipo: 'gris', codigo: 'IMPORTACION_FALLIDA',
      texto: `La última importación del Excel falló (${fechaMadrid(ultima.importado_at) ?? 'sin fecha'}; ${detalle}): ${vigente ? 'se muestran los datos de la vigente' : 'no hay ninguna vigente'}.` });
  }
  return { estado: { vigente, ultima, dias }, avisos };
}

// ---------------------------------------------------------------------------
// Cálculo
// ---------------------------------------------------------------------------

const claveLinea = (categoria: string, concepto: string) => `${categoria}\u0000${concepto}`;
const NEUTRO = { vencimientos: null, media: null, diferencia: false, desconocidos: 0, partes: [], comparada: null, frente: null } as const;

interface Valida extends Omit<ImporteCashflow, 'concepto'> {
  cuenta: CuentaCashflow; concepto: string; sentido: SentidoMovimiento; clase: ClaseMovimiento;
  /** H7-REAL-7: concepto tal como viene del Excel, si una equivalencia lo ha cambiado (null = el mismo). */
  alias: string | null;
}

/**
 * Estimación de una categoría en una decena futura (c y d de la previsión), con los totales reales de la categoría por
 * decena (céntimos, con signo). `primera`: primera decena con datos de la cuenta (antes no hay real: no cuenta como 0).
 *   POSICION:      últimas N decenas reales de la misma posición (1.ª, 2.ª o 3.ª del mes); sin filas = 0.
 *   ANIO_ANTERIOR: la misma decena del mismo mes del año anterior (tiene que ser real).
 * null = sin base (ninguna decena real que usar).
 */
export function estimarCategoria(
  regla: ReglaEstimacion, decena: string, porDecena: ReadonlyMap<string, { c: number; sin_importe: number }>,
  primera: string, ultimaReal: string, config: ConfigCashflow = CONFIG_CASHFLOW): DesgloseMedia | null {
  const posicion = ordinalDecena(decena);
  const de = (d: string) => porDecena.get(d) ?? { c: 0, sin_importe: 0 };
  let base: string[];
  if (regla === 'ANIO_ANTERIOR') {
    const d = `${sumarMeses(decena.slice(0, 7), -12)}-${decena.slice(8)}`;
    base = d >= primera && d <= ultimaReal ? [d] : [];
  } else {
    base = [];
    let d = ultimaReal;
    while (ordinalDecena(d) !== posicion) d = anteriorDecena(d);
    for (; base.length < config.meses_media && d >= primera; d = `${sumarMeses(d.slice(0, 7), -1)}-${d.slice(8)}`) base.unshift(d);
  }
  if (base.length === 0) return null;
  const total = base.reduce((a, d) => a + de(d).c, 0);
  return {
    regla, posicion, base: base.map((d) => ({ clave: d, importe: eur(de(d).c) })),
    media: eur(Math.round(total / base.length)), sin_importe: base.reduce((a, d) => a + de(d).sin_importe, 0), excluidos: [],
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

function resumen(lineas: readonly Linea[], d: string, real: boolean):
  Omit<ResumenDecena, 'saldo' | 'saldo_bancos' | 'saldo_formulas' | 'incompleto' | 'diferencia_banco' | 'cuadre' | 'cuadra'> {
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
    traspasos_externos: de((l) => l.clase === 'TRASPASO_EXTERNO'),
    neto: de(() => true),
    desconocidos: celdas.reduce((a, x) => a + x.c.desconocidos, 0),
  };
}

function ordenarLineas(ls: Linea[]): Linea[] {
  const rango = (l: Linea) => (l.clase === 'FARMACIA' ? 0 : l.clase === 'NO_RELACIONADA' ? 1 : l.clase === 'TRASPASO_EXTERNO' ? 2 : 3) * 2 + (l.sentido === 'ENTRADA' ? 0 : 1);
  return ls.sort((a, b) => rango(a) - rango(b) || a.categoria.localeCompare(b.categoria, 'es') || Number(a.media) - Number(b.media) || a.concepto.localeCompare(b.concepto, 'es'));
}

/** Calcula las vistas, los avisos y lo que queda fuera. `decenas`: horizonte (por defecto, el de los datos y las vistas). */
export function calcularCashflow(
  dto: Pick<CashflowDTO, 'hoy' | 'importaciones' | 'cuentas' | 'importes' | 'saldos' | 'vencimientos'> & Partial<Pick<CashflowDTO, 'otras_cuentas'>>
    & { config?: ConfigCashflow; apuntes_manuales?: readonly ApunteManualCashflow[] }): ResultadoCashflow {
  const config = dto.config ?? CONFIG_CASHFLOW;
  const hoy = dto.hoy;
  // Cuentas: solo PIO y RITA, y solo si figuran en cf_cashflow_cuentas (falla cerrado).
  const declaradas = new Set(dto.cuentas.map((c) => c.codigo));
  const cuentas = CUENTAS_CASHFLOW.filter((c) => declaradas.has(c));
  const esCuenta = (c: string): c is CuentaCashflow => (cuentas as readonly string[]).includes(c);
  const otras = dto.otras_cuentas ?? [];
  const fuera: FueraDeCashflow = {
    cuentas_fuera: [...new Set([...dto.cuentas.map((c) => c.codigo).filter((c) => !esCuenta(c)), ...otras.map((o) => o.cuenta)])].sort(),
    filas_otras_cuentas: otras.reduce((a, o) => a + o.importes + o.saldos, 0), filas_otra_importacion: 0,
    categorias_no_reconocidas: [], filas_no_reconocidas: 0, filas_decena_no_valida: 0,
    venc_sin_concepto: [], venc_no_suman: [], venc_sin_fecha: 0, venc_en_decenas_reales: [],
  };
  const imp = estadoImportacion(dto.importaciones, hoy, config);
  // Solo la importación vigente (sin vigente, ninguna fila): nunca se mezclan importaciones.
  const vigenteId = imp.estado.vigente?.importacion_id ?? null;
  const deVigente = <T extends { importacion_id: string }>(xs: readonly T[]) => {
    const si = xs.filter((x) => vigenteId !== null && x.importacion_id === vigenteId);
    fuera.filas_otra_importacion += xs.length - si.length;
    return si;
  };
  const validas: Valida[] = [];
  const noReconocidas = new Set<string>();
  const importesVigente = deVigente(dto.importes);
  // H7-REAL-7/8: equivalencias resueltas contra los conceptos de cada cuenta (su hoja del Excel) en la importación
  // vigente; un prefijo ambiguo o sin coincidencia deja ese par sin fusionar en esa cuenta (falla cerrado).
  const equivalenciasDe = new Map<string, EquivalenciasResueltas>();
  for (const c of CUENTAS_CASHFLOW) {
    equivalenciasDe.set(c, resolverEquivalencias(importesVigente.filter((f) => f.cuenta === c).flatMap((f) => (f.concepto === null ? [] : [f.concepto]))));
  }
  const mapaDe = (cuenta: string) => equivalenciasDe.get(cuenta)?.mapa ?? new Map<string, string>();
  for (const f0 of importesVigente) {
    const f = { ...f0, concepto: f0.concepto ?? CONCEPTO_VACIO };
    if (!esCuenta(f.cuenta)) { fuera.filas_otras_cuentas += 1; continue; }
    if (!esDecenaInicio(f.decena_inicio) || f.decena_fin !== finDecena(f.decena_inicio)) { fuera.filas_decena_no_valida += 1; continue; }
    const c = claseMovimiento(f.cuenta, f.categoria, f0.concepto);
    if (c === null) { fuera.filas_no_reconocidas += 1; noReconocidas.add(f.categoria); continue; }
    // H7-REAL-7: equivalencias de concepto al leer (la clase ya se ha decidido con el concepto del Excel).
    const queda = mapaDe(f.cuenta).get(f.concepto) ?? f.concepto;
    validas.push({ ...f, cuenta: f.cuenta, ...c, concepto: queda, alias: queda === f.concepto ? null : f.concepto });
  }
  fuera.categorias_no_reconocidas = [...noReconocidas].sort();
  const saldosVigente = deVigente(dto.saldos);
  const saldos = saldosVigente.filter((s) => esCuenta(s.cuenta) && esDecenaInicio(s.decena_inicio));
  fuera.filas_otras_cuentas += saldosVigente.filter((s) => !esCuenta(s.cuenta)).length;

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
  avisos.push(...imp.avisos);

  const vistas = {} as Record<VistaCuenta, ResultadoVista>;
  const categoriasMedia = new Set<string>();

  for (const cuenta of cuentas) {
    const filas = validas.filter((f) => f.cuenta === cuenta);
    const ss = new Map(saldos.filter((s) => s.cuenta === cuenta).map((s) => [s.decena_inicio, s]));
    const conBanco = [...ss.values()].filter((s) => s.saldo_bancos !== null).map((s) => s.decena_inicio).sort();
    const ultimaReal = conBanco.length ? conBanco[conBanco.length - 1] : null;
    const finReal = ultimaReal === null ? null : finDecena(ultimaReal);
    /** Primera decena con datos de la cuenta (antes no hay real: no entra en las medias). */
    const primeraCuenta: string | null = [...filas.map((f) => f.decena_inicio), ...ss.keys()].sort()[0] ?? null;
    const esReal = (d: string) => ultimaReal !== null && d <= ultimaReal;
    // Sin importación vigente no hay saldos que echar de menos («Todavía no hay datos importados»).
    if (ultimaReal === null && vigenteId !== null) avisos.push({ ...base, tipo: 'gris', codigo: 'SIN_SALDO_BANCO', cuenta, texto: `${cuenta}: ninguna decena tiene saldo de banco; no se puede calcular el saldo previsto.` });

    // Líneas del Excel.
    const lineas = new Map<string, Linea>();
    const linea = (categoria: string, concepto: string, sentido: SentidoMovimiento, clase: ClaseMovimiento, media = false): Linea => {
      const k = claveLinea(categoria, concepto);
      let l = lineas.get(k);
      if (!l) { l = { clave: k, categoria, concepto, sentido, clase, media, incluye: [], celdas: {} }; lineas.set(k, l); }
      return l;
    };
    const grupos = new Map<string, Valida[]>();
    for (const f of filas) {
      const k = `${claveLinea(f.categoria, f.concepto)}\u0000${f.decena_inicio}`;
      grupos.set(k, [...(grupos.get(k) ?? []), f]);
    }
    // H7-REAL-7: conceptos del Excel fusionados en cada línea (para el desglose: «incluye: …»).
    for (const f of filas) {
      if (f.alias === null) continue;
      const l = linea(f.categoria, f.concepto, f.sentido, f.clase);
      if (!l.incluye.includes(f.alias)) l.incluye = [...l.incluye, f.alias].sort((a, b) => a.localeCompare(b, 'es'));
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

    // a) Apuntes manuales (hueco preparado, sin datos todavía): sustituyen al Excel de su concepto y decena. Solo decenas
    // futuras (lo real es el Excel). H7-REAL-8: van antes que los vencimientos, que se comparan con ellos (b).
    for (const a of dto.apuntes_manuales ?? []) {
      if (a.cuenta !== cuenta || !esDecenaInicio(a.decena_inicio) || esReal(a.decena_inicio) || ultimaReal === null) continue;
      const c = claseMovimiento(cuenta, a.categoria, a.concepto);
      if (c === null) { fuera.filas_no_reconocidas += 1; noReconocidas.add(a.categoria); continue; }
      const l = linea(a.categoria, a.concepto === null ? CONCEPTO_VACIO : mapaDe(cuenta).get(a.concepto) ?? a.concepto, c.sentido, c.clase);
      const previa = l.celdas[a.decena_inicio];
      const s = sumar([...(previa?.fuente === 'MANUAL' ? [previa.importe] : []), a.importe === null ? null : eur(cent(signo(c) * a.importe))]);
      l.celdas[a.decena_inicio] = {
        ...NEUTRO, partes: [], cuenta, decena: a.decena_inicio, real: false, fuente: 'MANUAL', importe: s.suma, en_saldo: true,
        excel: previa?.excel ?? null, excel_filas: previa?.excel_filas ?? 0, desconocidos: (previa?.fuente === 'MANUAL' ? previa.desconocidos : 0) + s.desconocidos,
      };
    }

    // b) H7-REAL-9 (decisión de Pío, 25/11/2026): previsión base POR CONCEPTO en cada decena futura. El apunte manual manda;
    // si no, gana el mayor en valor absoluto entre el Excel y la media del concepto (últimos N meses reales, misma
    // posición de decena; «RS Modelo …»: el mismo mes del año anterior); sin Excel, la media; sin historia, el Excel.
    // Cada concepto lleva su propia media en su línea (no hay media de categoría: todo lo real tiene concepto), así que
    // un concepto anotado no deja sin media a los demás de su categoría, y nada se cuenta dos veces. Traspasos internos:
    // nunca (neutros). El Excel con importe desconocido no se compara (cuenta como desconocido).
    if (ultimaReal !== null) {
      const primera = primeraCuenta ?? ultimaReal;
      const conceptos = new Map<string, Valida>();
      for (const f of filas) if (!conceptos.has(claveLinea(f.categoria, f.concepto))) conceptos.set(claveLinea(f.categoria, f.concepto), f);
      for (const [k, f0] of conceptos) {
        if (f0.clase === 'TRASPASO') continue;
        const regla: ReglaEstimacion | null = f0.clase === 'TRASPASO_EXTERNO' ? 'POSICION' : reglaEstimacion(f0.categoria);
        const l = lineas.get(k);
        if (regla === null || !l) continue;
        const porDecena = new Map<string, { c: number; sin_importe: number }>();
        for (const f of filas) {
          if (f.categoria !== f0.categoria || f.concepto !== f0.concepto || !esReal(f.decena_inicio)) continue;
          const x = porDecena.get(f.decena_inicio) ?? { c: 0, sin_importe: 0 };
          if (f.importe === null) x.sin_importe += 1; else x.c += cent(signo(f) * f.importe);
          porDecena.set(f.decena_inicio, x);
        }
        for (const d of decenas) {
          if (esReal(d)) continue;
          const previa = l.celdas[d];
          if (previa?.fuente === 'MANUAL') continue;
          const m0 = estimarCategoria(regla, d, porDecena, primera, ultimaReal, config);
          const media = m0 !== null && m0.media !== null && cent(m0.media) !== 0 ? m0 : null;
          if (media === null) continue;
          if (previa === undefined) {
            l.celdas[d] = { ...NEUTRO, partes: [], cuenta, decena: d, real: false, fuente: 'MEDIA', importe: media.media, en_saldo: true, excel: null, excel_filas: 0, media };
          } else if (previa.importe !== null) {
            const frente = { excel: previa.importe, media: media.media as number };
            l.celdas[d] = Math.abs(cent(frente.media)) > Math.abs(cent(frente.excel))
              ? { ...previa, fuente: 'MEDIA', importe: frente.media, media, frente }
              : { ...previa, media, frente };
          }
          categoriasMedia.add(l.categoria);
        }
      }
    }

    // c) Vencimientos del sistema (solo PIO; RITA solo con datos bancarios).
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
        // H7-REAL-8/9: previsión base del concepto en esa decena (b: apunte manual, o el mayor entre Excel y media). Los
        // vencimientos (solo de facturas ya recibidas) se comparan con ella: gana el mayor en valor absoluto (a igualdad,
        // los vencimientos). Con el neto o la base desconocidos no se puede comparar: los vencimientos.
        const base = previa !== undefined && previa.importe !== null && (previa.fuente === 'MANUAL' || previa.fuente === 'EXCEL' || previa.fuente === 'MEDIA')
          ? { fuente: previa.fuente, importe: previa.importe } : null;
        const ganaBase = config.vencimientos_como_minimo && importe !== null && base !== null && Math.abs(cent(base.importe)) > Math.abs(cent(importe));
        l.celdas[d] = ganaBase && previa !== undefined
          ? { ...previa, vencimientos: dv, diferencia, desconocidos: 0, comparada: { fuente: 'VENCIMIENTOS', importe: importe as number } }
          : {
            ...NEUTRO, partes: [], cuenta, decena: d, real: false, fuente: 'VENCIMIENTOS', importe, en_saldo: true,
            excel, excel_filas: previa?.excel_filas ?? 0, vencimientos: dv, media: previa?.media ?? null, frente: previa?.frente ?? null,
            diferencia, desconocidos: dv.sin_importe,
            comparada: base === null || !config.vencimientos_como_minimo ? null : { fuente: base.fuente, importe: base.importe },
          };
      }
    }

    // Cuadre de control (H7-REAL): saldo_inicial + ΣRE − ΣRS = saldo_formulas, con los valores de la importación tal
    // cual (también traspasos y «no relacionadas»; sin medias ni vencimientos). Solo se comprueba, nunca se corrige.
    const filasPorDecena = new Map<string, Valida[]>();
    for (const f of filas) filasPorDecena.set(f.decena_inicio, [...(filasPorDecena.get(f.decena_inicio) ?? []), f]);
    const cuadreDe = (d: string): CuadreDecena | null => {
      const s = ss.get(d);
      if (!s || s.saldo_inicial === null || s.saldo_formulas === null) return null;
      const fs = filasPorDecena.get(d) ?? [];
      if (fs.some((f) => f.importe === null)) return null; // con un importe desconocido no se puede comprobar
      const suma = (sentido: SentidoMovimiento) => fs.filter((f) => f.sentido === sentido).reduce((a, f) => a + cent(f.importe as number), 0);
      const e = suma('ENTRADA');
      const sa = suma('SALIDA');
      const esperado = cent(s.saldo_inicial) + e - sa;
      const dif = cent(s.saldo_formulas) - esperado;
      return {
        saldo_inicial: s.saldo_inicial, entradas: eur(e), salidas: eur(sa), esperado: eur(esperado), saldo_formulas: s.saldo_formulas,
        diferencia: eur(dif), filas: fs.length, cuadra: Math.abs(dif) <= TOLERANCIA_CUADRE_POR_IMPORTE * 100 * fs.length + 1e-9,
      };
    };

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
      const bancos = s?.saldo_bancos ?? null;
      const formulas = s?.saldo_formulas ?? null;
      // E7: solo en decenas reales; informativa (el saldo real sigue siendo el del banco).
      const diferencia = real && bancos !== null && formulas !== null && !mismoImporte(bancos, formulas) ? eur(cent(bancos) - cent(formulas)) : null;
      const cuadre = cuadreDe(d);
      res[d] = {
        ...r, saldo: saldoD, saldo_bancos: bancos, saldo_formulas: formulas, diferencia_banco: diferencia, cuadre, cuadra: cuadre?.cuadra ?? null,
        incompleto: !real && incompleto,
      };
    }
    const noCuadran = decenas.filter((d) => res[d].cuadra === false);
    if (noCuadran.length > 0) {
      avisos.push({ ...base, tipo: 'gris', codigo: 'IMPORTACION_NO_CUADRA', cuenta, decena: noCuadran[0], hasta: noCuadran[noCuadran.length - 1],
        decenas: noCuadran.map((d) => ({ decena: d, importe: (res[d].cuadre as CuadreDecena).diferencia })),
        texto: `Datos de la importación no cuadran en ${cuenta}, ${noCuadran.join(', ')}.` });
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
      lc.incluye = [...new Set([...lc.incluye, ...l.incluye])].sort((a, b) => a.localeCompare(b, 'es'));
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
          comparada: partes.find((p) => p.comparada)?.comparada ?? null, frente: partes.length === 1 ? partes[0].frente : null,
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
      diferencia_banco: sumaOnull(partesV.map((v) => v.decenas[d].diferencia_banco).filter((x) => x !== null)),
      cuadre: null,
      cuadra: partesV.some((v) => v.decenas[d].cuadra === false) ? false : partesV.length > 0 && partesV.every((v) => v.decenas[d].cuadra === true) ? true : null,
      incompleto: partesV.some((v) => v.decenas[d].incompleto),
    };
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
  fuera.categorias_no_reconocidas = [...noReconocidas].sort();
  return {
    hoy, decenas, vistas, avisos, importacion: imp.estado, fuera,
    categorias_media: [...categoriasMedia].sort(),
    equivalencias: {
      filas: Object.fromEntries(cuentas.map((c) => [c, validas.filter((f) => f.cuenta === c && f.alias !== null).length])),
      ambiguas: cuentas.reduce((a, c) => a + (equivalenciasDe.get(c)?.ambiguas ?? 0), 0),
      sin_coincidencia: cuentas.reduce((a, c) => a + (equivalenciasDe.get(c)?.sin_coincidencia ?? 0), 0),
    },
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
  // H7-REAL-7: solo dentro del horizonte mostrado, el mismo que el indicador: los 12 meses previstos tras la última
  // decena real (antes salían avisos hasta el final de los datos del Excel).
  const finHorizonte = C.ultima_real === null ? null : moverDecena(C.ultima_real, 3 * MESES_INDICADOR);
  const enHorizonte = (d: string) => finHorizonte !== null && d <= finHorizonte;
  const previstas = decenas.filter((d) => !C.decenas[d].real && C.decenas[d].saldo !== null && enHorizonte(d));
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
      const devolucion = decenas.find((d) => d > fin && enHorizonte(d) && A.decenas[d].saldo !== null && (A.decenas[d].saldo as number) >= min) ?? null;
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
export type CampoResumen = 'entradas' | 'salidas' | 'farmacia' | 'no_relacionadas' | 'traspasos' | 'traspasos_externos' | 'neto';
export function resumenColumna(v: ResultadoVista, col: Columna, campo: CampoResumen): Importe {
  return sumaOnull(col.decenas.map((d) => v.decenas[d]?.[campo] ?? null).filter((x) => x !== null));
}
/** Saldo al cierre de la columna (el de su última decena). */
export function saldoColumna(v: ResultadoVista, col: Columna): {
  saldo: Importe; incompleto: boolean; bancos: Importe; formulas: Importe; diferencia_banco: Importe; no_cuadra: boolean;
} {
  const r = v.decenas[col.decenas[col.decenas.length - 1]];
  return {
    saldo: r?.saldo ?? null, incompleto: r?.incompleto ?? false, bancos: r?.saldo_bancos ?? null, formulas: r?.saldo_formulas ?? null,
    // E7 al cierre de la columna; el cuadre, en cualquiera de sus decenas.
    diferencia_banco: r?.diferencia_banco ?? null, no_cuadra: col.decenas.some((d) => v.decenas[d]?.cuadra === false),
  };
}
/** Avisos de saldo que tocan una columna. */
export function avisosColumna(avisos: readonly AvisoCashflow[], col: Columna): AvisoCashflow[] {
  return avisos.filter((a) => a.tipo !== 'gris' && a.decenas.some((x) => col.decenas.includes(x.decena)));
}
/**
 * H7-REAL-2: decenas de las columnas visibles cuyos traspasos no se compensan en el consolidado (traspasos a la SL,
 * fondos…). No es un aviso: solo una línea plegada en la tabla del consolidado.
 */
export function traspasosNoCompensados(v: ResultadoVista, cols: readonly Columna[]): { decena: string; importe: number }[] {
  return cols.flatMap((c) => c.decenas).flatMap((d) => {
    const t = v.decenas[d]?.traspasos ?? null;
    return t !== null && cent(t) !== 0 ? [{ decena: d, importe: t }] : [];
  });
}
/** Variación media mensual del saldo entre dos decenas (cierre de cada una). */
export interface TramoVariacion {
  desde: string;
  hasta: string;
  meses: number;
  saldo_desde: number;
  saldo_hasta: number;
  /** (saldo_hasta − saldo_desde) ÷ meses. */
  por_mes: number;
}
/** Meses del indicador de control (12: los últimos reales y los primeros previstos). */
export const MESES_INDICADOR = 12;
/**
 * H7-REAL-4: indicador de control de la previsión: variación media mensual REAL del saldo en los últimos 12 meses (o
 * desde la primera decena real con saldo, si hay menos) frente a la PREVISTA en los 12 siguientes (o hasta el final del
 * horizonte). Si la prevista se aleja mucho de la real, la previsión merece revisión. null = sin saldos para calcularla.
 */
export function variacionMensual(v: ResultadoVista, decenas: readonly string[]): { real: TramoVariacion | null; prevista: TramoVariacion | null } {
  const L = v.ultima_real;
  const s = (d: string) => v.decenas[d]?.saldo ?? null;
  if (L === null || s(L) === null) return { real: null, prevista: null };
  const tramo = (desde: string, hasta: string): TramoVariacion | null => {
    const n = rangoDecenas(desde, hasta).length - 1;
    const a = s(desde);
    const b = s(hasta);
    if (n <= 0 || a === null || b === null) return null;
    const meses = n / 3;
    return { desde, hasta, meses: Math.round(meses * 100) / 100, saldo_desde: a, saldo_hasta: b, por_mes: eur(Math.round((cent(b) - cent(a)) / meses)) };
  };
  const inicioReal = decenas.find((d) => d >= moverDecena(L, -3 * MESES_INDICADOR) && d <= L && v.decenas[d]?.real && s(d) !== null);
  const objetivo = moverDecena(L, 3 * MESES_INDICADOR);
  const finPrevisto = [...decenas].reverse().find((d) => d > L && d <= objetivo && s(d) !== null);
  return {
    real: inicioReal === undefined ? null : tramo(inicioReal, L),
    prevista: finPrevisto === undefined ? null : tramo(L, finPrevisto),
  };
}
/** Agrupa las líneas por categoría (en el orden de las líneas). */
export function porCategoria(ls: readonly Linea[]): { categoria: string; sentido: SentidoMovimiento; clase: ClaseMovimiento; lineas: Linea[] }[] {
  const out: { categoria: string; sentido: SentidoMovimiento; clase: ClaseMovimiento; lineas: Linea[] }[] = [];
  for (const l of ls) {
    // Por categoría y clase: una categoría de traspasos puede tener conceptos internos y externos (H7-REAL-4).
    const g = out.find((x) => x.categoria === l.categoria && x.clase === l.clase);
    if (g) g.lineas.push(l); else out.push({ categoria: l.categoria, sentido: l.sentido, clase: l.clase, lineas: [l] });
  }
  return out;
}
