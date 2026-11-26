/**
 * H7-AP1: apuntes manuales de Cashflow (migración 40). Fuente de verdad: web/docs/referencia/ESQUEMA_CASHFLOW.md
 * («Previsión: apuntes de la web»). Módulo puro: lo usan el servidor (FIXTURES y REAL), el front, check_fixtures y las
 * pruebas.
 *
 * Tablas (escribe cf_cashflow_web; lee cf_lectura, con la misma RLS):
 *   cf_cashflow_conceptos   conceptos nuevos (nombre 1–120, proveedor_cif opcional ^[A-Z0-9]{5,20}$) por cuenta y categoría.
 *   cf_cashflow_recurrentes concepto, importe > 0, nota ≤ 500, frecuencia MENSUAL|TRIMESTRAL|ANUAL, día 1–31 (si el mes no
 *                           lo tiene, el último día del mes), inicio (= primera ocurrencia) y fin opcional (≥ inicio).
 *   cf_cashflow_apuntes     suelto (importe > 0, fecha) o anulación de una ocurrencia (recurrente_id + fecha_ocurrencia,
 *                           sin importe); sustituido_factura_id + sustituido_vencimiento_orden al sustituirlo por un
 *                           vencimiento (confirmado por Marc, nunca automático).
 * Columnas comunes: id, cuenta (PIO|RITA), farmacia (la pone el trigger), categoria (RE …/RS … de la plantilla de la
 * vigente), autor (cf.autor), creado_at, anulado, anulado_por, anulado_at, motivo_anulacion. Nunca se borra: se anula
 * (con motivo); lo anulado no se reabre; editar = anular + crear en la misma transacción.
 *
 * El importe es siempre positivo: el sentido lo da el prefijo de la categoría (RE entra, RS sale).
 * Solo fechas futuras: posteriores al fin de la última decena con saldo de banco de la cuenta (FECHA_NO_FUTURA).
 * RITA (excepción del 17/11/2026): solo apuntes sobre su propia cuenta; nunca vencimientos ni facturas (la sustitución
 * solo existe en PIO, la cuenta con vencimientos del sistema).
 *
 * Las validaciones de la web repiten las de la BD con los mismos códigos (errores_bd.ts); la BD las vuelve a hacer.
 *
 * Solo sintaxis TypeScript borrable; sin dependencias del servidor (el front lo importa).
 */
import {
  CUENTAS_CASHFLOW, CUENTA_VENCIMIENTOS, clasificarCategoria, comercialDeConcepto, decenaDe, esFecha, finDecena, siguienteDecena, sumarMeses,
  type ApunteManualCashflow, type CuentaCashflow, type DatosCashflow, type ImportacionCashflow, type SaldoCashflow, type VencimientoCashflow,
} from './cashflow.ts';
import type { CodigoErrorCashflow } from './errores_bd.ts';

// ---------------------------------------------------------------------------
// Configuración (único punto)
// ---------------------------------------------------------------------------

export const FRECUENCIAS = ['MENSUAL', 'TRIMESTRAL', 'ANUAL'] as const;
export type Frecuencia = (typeof FRECUENCIAS)[number];
export const MESES_POR_FRECUENCIA: Readonly<Record<Frecuencia, number>> = { MENSUAL: 1, TRIMESTRAL: 3, ANUAL: 12 };
export const TEXTO_FRECUENCIA: Readonly<Record<Frecuencia, string>> = { MENSUAL: 'mensual', TRIMESTRAL: 'trimestral', ANUAL: 'anual' };
/** Sustitución: la factura coincide si su importe está a ±5 % del apunte (mismo concepto, misma decena o la siguiente). */
export const MARGEN_SUSTITUCION = 0.05;
/** Largos del esquema. */
export const LARGO = { nombre: 120, concepto: 255, nota: 500, motivo: 500 } as const;
export const CIF_CONCEPTO = /^[A-Z0-9]{5,20}$/;
/** Ventana de ocurrencias que se leen (REAL: cf_cashflow_ocurrencias): 12 meses atrás y 36 adelante. */
export const VENTANA_OCURRENCIAS = { meses_pasados: 12, meses_proximos: 36 } as const;
/** check:real: ocurrencias en los próximos 12 meses. */
export const MESES_DIAGNOSTICO_OCURRENCIAS = 12;
/** Próximas ocurrencias de cada recurrente que se listan en «Apuntes manuales». */
export const OCURRENCIAS_LISTADAS = 6;
/** Grupos de categorías del formulario «Añadir apunte» (por el nombre de la categoría de la plantilla). */
export const GRUPOS_CATEGORIA = ['Ingresos', 'Proveedores', 'Laboratorios', 'Gastos'] as const;
export type GrupoCategoria = (typeof GRUPOS_CATEGORIA)[number];

// ---------------------------------------------------------------------------
// Contrato (filas tal como las crea la migración 40)
// ---------------------------------------------------------------------------

interface Comunes {
  id: string;
  cuenta: CuentaCashflow;
  /** La pone el trigger (igual a la cuenta). */
  farmacia: string;
  categoria: string;
  autor: string;
  creado_at: string;
  anulado: boolean;
  anulado_por: string | null;
  anulado_at: string | null;
  motivo_anulacion: string | null;
}
export interface ConceptoCashflow extends Comunes {
  nombre: string;
  proveedor_cif: string | null;
}
export interface RecurrenteCashflow extends Comunes {
  concepto: string;
  importe: number;
  nota: string | null;
  frecuencia: Frecuencia;
  dia: number;
  inicio: string;
  fin: string | null;
}
export interface ApunteCashflow extends Comunes {
  fecha: string;
  concepto: string;
  /** null en la anulación de una ocurrencia. */
  importe: number | null;
  nota: string | null;
  recurrente_id: string | null;
  fecha_ocurrencia: string | null;
  sustituido_factura_id: string | null;
  sustituido_vencimiento_orden: number | null;
}
/** Una ocurrencia de un recurrente no anulado (cf_cashflow_ocurrencias): sin las anuladas una a una. */
export interface OcurrenciaCashflow {
  recurrente_id: string;
  cuenta: CuentaCashflow;
  farmacia: string;
  categoria: string;
  concepto: string;
  importe: number;
  fecha: string;
}
export interface PrevisionesCashflow {
  conceptos: ConceptoCashflow[];
  recurrentes: RecurrenteCashflow[];
  apuntes: ApunteCashflow[];
  /** Las de la ventana (REAL: cf_cashflow_ocurrencias(desde, hasta); FIXTURES: calcularOcurrencias, la misma regla). */
  ocurrencias: OcurrenciaCashflow[];
  ventana: { desde: string; hasta: string };
}
export interface EscrituraCashflow {
  habilitada: boolean;
  codigo: string | null;
  mensaje: string | null;
  /** Autor de los apuntes (cf.autor de cada transacción). */
  autor: string;
}

export const esCuentaCashflow = (c: unknown): c is CuentaCashflow => (CUENTAS_CASHFLOW as readonly unknown[]).includes(c);

// ---------------------------------------------------------------------------
// Ocurrencias
// ---------------------------------------------------------------------------

/** Último día del mes `ym` (YYYY-MM). */
const ultimoDia = (ym: string) => Number(finDecena(`${ym}-21`).slice(8));
/** Ocurrencia del mes `ym` con el día `dia`: si el mes no lo tiene, el último día del mes. */
export function fechaOcurrencia(ym: string, dia: number): string {
  return `${ym}-${String(Math.min(dia, ultimoDia(ym))).padStart(2, '0')}`;
}
/** ¿`inicio` es la primera ocurrencia de un recurrente con ese día? */
export const inicioEsOcurrencia = (dia: number, inicio: string) => fechaOcurrencia(inicio.slice(0, 7), dia) === inicio;

/** Fechas de un recurrente en [desde, hasta] (ambas incluidas), desde su inicio y hasta su fin. */
export function fechasRecurrente(r: Pick<RecurrenteCashflow, 'frecuencia' | 'dia' | 'inicio' | 'fin'>, desde: string, hasta: string): string[] {
  const out: string[] = [];
  const paso = MESES_POR_FRECUENCIA[r.frecuencia];
  if (!paso || !Number.isInteger(r.dia) || r.dia < 1 || r.dia > 31 || !esFecha(r.inicio)) return out;
  for (let n = 0; n < 1200; n++) {
    const f = fechaOcurrencia(sumarMeses(r.inicio.slice(0, 7), n * paso), r.dia);
    if (f > hasta || (r.fin !== null && f > r.fin)) break;
    if (f >= desde && f >= r.inicio) out.push(f);
  }
  return out;
}

const claveOcurrencia = (recurrente: string, fecha: string) => `${recurrente}|${fecha}`;
/** Ocurrencias anuladas una a una (apunte de anulación vigente), por recurrente y fecha. */
export function ocurrenciasAnuladas(apuntes: readonly ApunteCashflow[]): Map<string, ApunteCashflow> {
  const m = new Map<string, ApunteCashflow>();
  for (const a of apuntes) if (!a.anulado && a.recurrente_id !== null && a.fecha_ocurrencia !== null) m.set(claveOcurrencia(a.recurrente_id, a.fecha_ocurrencia), a);
  return m;
}
/**
 * Lo que devuelve cf_cashflow_ocurrencias(desde, hasta): ocurrencias de los recurrentes no anulados en el intervalo, sin
 * las anuladas una a una. (FIXTURES lo calcula aquí; REAL lo pide a la BD.)
 */
export function calcularOcurrencias(p: Pick<PrevisionesCashflow, 'recurrentes' | 'apuntes'>, desde: string, hasta: string): OcurrenciaCashflow[] {
  const anuladas = ocurrenciasAnuladas(p.apuntes);
  return p.recurrentes.filter((r) => !r.anulado).flatMap((r) => fechasRecurrente(r, desde, hasta)
    .filter((fecha) => !anuladas.has(claveOcurrencia(r.id, fecha)))
    .map((fecha) => ({ recurrente_id: r.id, cuenta: r.cuenta, farmacia: r.farmacia, categoria: r.categoria, concepto: r.concepto, importe: r.importe, fecha })))
    .sort((a, b) => a.fecha.localeCompare(b.fecha) || a.recurrente_id.localeCompare(b.recurrente_id));
}
/** Ventana de ocurrencias para una fecha de referencia. */
export function ventanaOcurrencias(hoy: string): { desde: string; hasta: string } {
  return {
    desde: `${sumarMeses(hoy.slice(0, 7), -VENTANA_OCURRENCIAS.meses_pasados)}-01`,
    hasta: finDecena(`${sumarMeses(hoy.slice(0, 7), VENTANA_OCURRENCIAS.meses_proximos)}-21`),
  };
}
export const previsionesVacias = (hoy: string): PrevisionesCashflow => ({ conceptos: [], recurrentes: [], apuntes: [], ocurrencias: [], ventana: ventanaOcurrencias(hoy) });

// ---------------------------------------------------------------------------
// Plantilla y fechas futuras (de lo importado, leído con cf_lectura)
// ---------------------------------------------------------------------------

/** La importación vigente: exactamente una, OK (si no, ninguna: falla cerrado). */
export function importacionVigente(imps: readonly ImportacionCashflow[]): ImportacionCashflow | null {
  const v = imps.filter((i) => i.vigente);
  return v.length === 1 && v[0].estado === 'OK' ? v[0] : null;
}
/** Fin de la última decena con saldo de banco de la cuenta en la vigente (null = ninguna: SIN_SALDO_DE_BANCO). */
export function limiteFuturo(d: { importaciones: readonly ImportacionCashflow[]; saldos: readonly SaldoCashflow[] }, cuenta: string): string | null {
  const v = importacionVigente(d.importaciones);
  if (v === null) return null;
  const ds = d.saldos.filter((s) => s.importacion_id === v.importacion_id && s.cuenta === cuenta && s.saldo_bancos !== null).map((s) => s.decena_inicio).sort();
  return ds.length === 0 ? null : finDecena(ds[ds.length - 1]);
}
/** Primer día futuro de la cuenta (el siguiente al límite), para el mínimo de los campos de fecha. */
export function primerDiaFuturo(limite: string): string {
  const t = Date.parse(`${limite}T00:00:00Z`) + 86400000;
  return new Date(t).toISOString().slice(0, 10);
}

const normal = (s: string) => s.normalize('NFD').replace(/\p{M}/gu, '').toUpperCase().replace(/\s+/g, ' ').trim();
/** Nombre como se guarda: sin espacios al principio ni al final y sin espacios repetidos. */
export const limpiarNombre = (s: string) => s.replace(/\s+/g, ' ').trim();
/** Mismo nombre para la BD: sin distinguir mayúsculas ni espacios repetidos. */
export const mismoNombre = (a: string, b: string) => limpiarNombre(a).toUpperCase() === limpiarNombre(b).toUpperCase();

export interface ConceptoPlantilla { nombre: string; nuevo: boolean; proveedor_cif: string | null }
export interface CategoriaPlantilla { categoria: string; grupo: GrupoCategoria; conceptos: ConceptoPlantilla[] }
/** Grupo del formulario: RE = ingresos; RS con «PROVEEDOR» o «LABORATORI» en el nombre; el resto, gastos. */
export function grupoCategoria(categoria: string): GrupoCategoria {
  if (/^RE\s/.test(categoria.trim())) return 'Ingresos';
  const n = normal(categoria);
  return /PROVEEDOR/.test(n) ? 'Proveedores' : /LABORATORI/.test(n) ? 'Laboratorios' : 'Gastos';
}
/**
 * Plantilla de una cuenta: categorías RE/RS de la importación vigente con sus conceptos (los del Excel y los nuevos sin
 * anular). Sin vigente, vacía.
 */
export function plantillaCuenta(d: Pick<DatosCashflow, 'importaciones' | 'importes'>, p: Pick<PrevisionesCashflow, 'conceptos'>, cuenta: string): CategoriaPlantilla[] {
  const v = importacionVigente(d.importaciones);
  if (v === null) return [];
  const cats = new Map<string, Map<string, ConceptoPlantilla>>();
  for (const f of d.importes) {
    if (f.importacion_id !== v.importacion_id || f.cuenta !== cuenta || clasificarCategoria(f.categoria) === null) continue;
    const m = cats.get(f.categoria) ?? new Map<string, ConceptoPlantilla>();
    cats.set(f.categoria, m);
    if (f.concepto !== null && !m.has(f.concepto)) m.set(f.concepto, { nombre: f.concepto, nuevo: false, proveedor_cif: null });
  }
  for (const c of p.conceptos) {
    if (c.anulado || c.cuenta !== cuenta) continue;
    const m = cats.get(c.categoria);
    if (!m) continue; // categoría que ya no está en la vigente
    if (![...m.values()].some((x) => mismoNombre(x.nombre, c.nombre))) m.set(c.nombre, { nombre: c.nombre, nuevo: true, proveedor_cif: c.proveedor_cif });
  }
  return [...cats].map(([categoria, m]) => ({
    categoria, grupo: grupoCategoria(categoria), conceptos: [...m.values()].sort((a, b) => a.nombre.localeCompare(b.nombre, 'es')),
  })).sort((a, b) => GRUPOS_CATEGORIA.indexOf(a.grupo) - GRUPOS_CATEGORIA.indexOf(b.grupo) || a.categoria.localeCompare(b.categoria, 'es'));
}
/** ¿Concepto de la plantilla (Excel o nuevo) para esa cuenta y categoría? Devuelve su texto exacto. */
export function conceptoEnPlantilla(pl: readonly CategoriaPlantilla[], categoria: string, concepto: string): string | null {
  return pl.find((c) => c.categoria === categoria)?.conceptos.find((x) => x.nombre === concepto)?.nombre ?? null;
}

// ---------------------------------------------------------------------------
// Alta (apunte suelto o recurrente, opcionalmente con concepto nuevo)
// ---------------------------------------------------------------------------

export type TipoAlta = 'SUELTO' | 'RECURRENTE';
export interface AltaApunte {
  tipo: TipoAlta;
  cuenta: string;
  categoria: string;
  /** Concepto existente (plantilla o nuevo ya creado); null si se crea uno nuevo. */
  concepto: string | null;
  concepto_nuevo: { nombre: string; proveedor_cif: string | null } | null;
  importe: number | null;
  nota: string | null;
  /** SUELTO. */
  fecha: string | null;
  /** RECURRENTE. */
  frecuencia: string | null;
  dia: number | null;
  inicio: string | null;
  fin: string | null;
}
export type Validacion<T> = { ok: true; datos: T } | { ok: false; errores: Record<string, string> };

const textoONull = (v: unknown): string | null | undefined => (v === null || v === undefined ? null : typeof v === 'string' ? (v.trim() === '' ? null : v) : undefined);
const fechaONull = (v: unknown): string | null | undefined => (v === null || v === undefined || v === '' ? null : esFecha(v) ? v : undefined);

/** Forma del cuerpo (tipos y largos). Las reglas de negocio, con los códigos de la BD, en comprobarAlta. */
export function validarAlta(body: unknown): Validacion<AltaApunte> {
  const b = (body && typeof body === 'object' ? body : {}) as Record<string, unknown>;
  const errores: Record<string, string> = {};
  const tipo = b.tipo === 'SUELTO' || b.tipo === 'RECURRENTE' ? b.tipo : null;
  if (tipo === null) errores.tipo = 'Elige apunte suelto o recurrente';
  const cuenta = typeof b.cuenta === 'string' ? b.cuenta : '';
  const categoria = typeof b.categoria === 'string' ? b.categoria : '';
  if (categoria === '') errores.categoria = 'Elige la categoría';
  const concepto = textoONull(b.concepto);
  if (concepto === undefined || (concepto !== null && concepto.length > LARGO.concepto)) errores.concepto = `Concepto de 1 a ${LARGO.concepto} caracteres`;
  let conceptoNuevo: AltaApunte['concepto_nuevo'] = null;
  if (b.concepto_nuevo !== null && b.concepto_nuevo !== undefined) {
    const n = b.concepto_nuevo as Record<string, unknown>;
    const nombre = typeof n?.nombre === 'string' ? limpiarNombre(n.nombre) : '';
    const cif = textoONull(n?.proveedor_cif);
    if (nombre === '' || nombre.length > LARGO.nombre) errores.concepto_nuevo = `Nombre del concepto nuevo de 1 a ${LARGO.nombre} caracteres`;
    if (cif === undefined || (cif !== null && !CIF_CONCEPTO.test(cif.trim().toUpperCase()))) errores.proveedor_cif = 'CIF de 5 a 20 letras o números, sin espacios ni guiones';
    conceptoNuevo = { nombre, proveedor_cif: typeof cif === 'string' ? cif.trim().toUpperCase() : null };
  }
  if ((concepto ?? null) === null && conceptoNuevo === null) errores.concepto = errores.concepto ?? 'Elige un concepto o crea uno nuevo';
  if (concepto && conceptoNuevo) errores.concepto = 'O un concepto existente o uno nuevo, no los dos';
  const importe = b.importe === null || b.importe === undefined || b.importe === '' ? null : typeof b.importe === 'number' && Number.isFinite(b.importe) ? b.importe : undefined;
  if (importe === undefined || (importe !== null && (Math.abs(importe) >= 1e12 || Math.round(importe * 100) / 100 !== importe))) errores.importe = 'Importe en euros, con 2 decimales como mucho';
  const nota = textoONull(b.nota);
  if (nota === undefined || (nota !== null && nota.length > LARGO.nota)) errores.nota = `Nota de ${LARGO.nota} caracteres como mucho`;
  const fecha = fechaONull(b.fecha);
  if (fecha === undefined) errores.fecha = 'Fecha no válida';
  const inicio = fechaONull(b.inicio);
  if (inicio === undefined) errores.inicio = 'Fecha «desde» no válida';
  const fin = fechaONull(b.fin);
  if (fin === undefined) errores.fin = 'Fecha «hasta» no válida';
  const dia = b.dia === null || b.dia === undefined || b.dia === '' ? null : typeof b.dia === 'number' && Number.isInteger(b.dia) ? b.dia : undefined;
  if (dia === undefined) errores.dia = 'Día del mes no válido';
  const frecuencia = b.frecuencia === null || b.frecuencia === undefined || b.frecuencia === '' ? null : typeof b.frecuencia === 'string' ? b.frecuencia : undefined;
  if (frecuencia === undefined) errores.frecuencia = 'Periodicidad no válida';
  if (Object.keys(errores).length > 0) return { ok: false, errores };
  return {
    ok: true,
    datos: {
      tipo: tipo as TipoAlta, cuenta, categoria, concepto: concepto ?? null, concepto_nuevo: conceptoNuevo,
      importe: importe ?? null, nota: nota === null ? null : (nota as string).trim(),
      fecha: tipo === 'SUELTO' ? fecha ?? null : null,
      frecuencia: tipo === 'RECURRENTE' ? frecuencia ?? null : null, dia: tipo === 'RECURRENTE' ? dia ?? null : null,
      inicio: tipo === 'RECURRENTE' ? inicio ?? null : null, fin: tipo === 'RECURRENTE' ? fin ?? null : null,
    },
  };
}

export interface ContextoCashflow {
  datos: Pick<DatosCashflow, 'importaciones' | 'cuentas' | 'importes' | 'saldos'>;
  previsiones: PrevisionesCashflow;
}
export interface FalloRegla { codigo: CodigoErrorCashflow; campo: string | null }

/**
 * Reglas del alta, en el orden de la BD y con sus códigos (la BD las vuelve a comprobar). `null` = se puede escribir.
 * Además, de la web: el concepto nuevo no repite uno de la categoría (CONCEPTO_YA_EXISTE) ni un CIF de la cuenta
 * (CIF_YA_ASIGNADO), y en un recurrente «desde» también es futuro.
 */
export function comprobarAlta(a: AltaApunte, ctx: ContextoCashflow): FalloRegla | null {
  const f = (codigo: CodigoErrorCashflow, campo: string | null = null): FalloRegla => ({ codigo, campo });
  if (!esCuentaCashflow(a.cuenta)) return f('CUENTA_NO_VALIDA', 'cuenta');
  if (!ctx.datos.cuentas.some((c) => c.codigo === a.cuenta && c.farmacia === a.cuenta)) return f('FARMACIA_NO_HABILITADA', 'cuenta');
  if (importacionVigente(ctx.datos.importaciones) === null) return f('SIN_IMPORTACION_VIGENTE');
  const pl = plantillaCuenta(ctx.datos, ctx.previsiones, a.cuenta);
  const cat = pl.find((c) => c.categoria === a.categoria);
  if (!cat) return f('CATEGORIA_FUERA_DE_PLANTILLA', 'categoria');
  if (a.concepto_nuevo !== null) {
    if (cat.conceptos.some((x) => mismoNombre(x.nombre, (a.concepto_nuevo as { nombre: string }).nombre))) return f('CONCEPTO_YA_EXISTE', 'concepto_nuevo');
    const cif = a.concepto_nuevo.proveedor_cif;
    if (cif !== null && ctx.previsiones.conceptos.some((c) => !c.anulado && c.cuenta === a.cuenta && c.proveedor_cif === cif)) return f('CIF_YA_ASIGNADO', 'proveedor_cif');
  } else if (a.concepto === null || conceptoEnPlantilla(pl, a.categoria, a.concepto) === null) {
    return f('CONCEPTO_DESCONOCIDO', 'concepto');
  }
  if (a.importe === null || a.importe <= 0) return f('IMPORTE_NO_POSITIVO', 'importe');
  const limite = limiteFuturo(ctx.datos, a.cuenta);
  if (a.tipo === 'SUELTO') {
    if (a.fecha === null) return f('FECHA_AUSENTE', 'fecha');
    if (limite === null) return f('SIN_SALDO_DE_BANCO');
    if (a.fecha <= limite) return f('FECHA_NO_FUTURA', 'fecha');
    return null;
  }
  if (a.frecuencia === null || !(FRECUENCIAS as readonly string[]).includes(a.frecuencia)) return f('FRECUENCIA_NO_VALIDA', 'frecuencia');
  if (a.dia === null || a.dia < 1 || a.dia > 31) return f('DIA_NO_VALIDO', 'dia');
  if (a.inicio === null) return f('INICIO_AUSENTE', 'inicio');
  if (a.fin !== null && a.fin < a.inicio) return f('FIN_ANTERIOR_A_INICIO', 'fin');
  if (!inicioEsOcurrencia(a.dia, a.inicio)) return f('INICIO_NO_ES_OCURRENCIA', 'inicio');
  if (limite === null) return f('SIN_SALDO_DE_BANCO');
  if (a.inicio <= limite) return f('FECHA_NO_FUTURA', 'inicio');
  return null;
}
/** Concepto con el que se guarda el apunte o el recurrente (el del concepto nuevo, si se crea). */
export const conceptoDeAlta = (a: AltaApunte): string => (a.concepto_nuevo !== null ? a.concepto_nuevo.nombre : a.concepto as string);

// ---------------------------------------------------------------------------
// Anular
// ---------------------------------------------------------------------------

export type TablaAnulable = 'APUNTE' | 'RECURRENTE';
/** Motivo obligatorio (1–500, sin contar espacios al principio y al final). */
export function validarMotivo(body: unknown): { ok: true; motivo: string } | { ok: false; codigo: 'MOTIVO_ANULACION_AUSENTE' | 'REGLA_TABLA' } {
  const m = (body as { motivo?: unknown } | null)?.motivo;
  const t = typeof m === 'string' ? m.trim() : '';
  if (t === '') return { ok: false, codigo: 'MOTIVO_ANULACION_AUSENTE' };
  if (t.length > LARGO.motivo) return { ok: false, codigo: 'REGLA_TABLA' };
  return { ok: true, motivo: t };
}
/** Un apunte suelto vigente (las anulaciones de ocurrencia no se anulan desde la web: lo anulado no se reabre). */
export function comprobarAnular(tabla: TablaAnulable, id: string, p: PrevisionesCashflow): FalloRegla | null {
  if (tabla === 'APUNTE') {
    const a = p.apuntes.find((x) => x.id === id);
    if (!a || a.recurrente_id !== null) return { codigo: 'APUNTE_NO_ENCONTRADO', campo: null };
    return a.anulado ? { codigo: 'SOLO_ANULAR', campo: null } : null;
  }
  const r = p.recurrentes.find((x) => x.id === id);
  if (!r) return { codigo: 'RECURRENTE_NO_ENCONTRADA', campo: null };
  return r.anulado ? { codigo: 'RECURRENTE_ANULADA', campo: null } : null;
}
/** Anular una ocurrencia: el recurrente vigente, una fecha que es ocurrencia vigente suya y futura. */
export function comprobarAnularOcurrencia(recurrenteId: string, fecha: string, ctx: ContextoCashflow): FalloRegla | null {
  const r = ctx.previsiones.recurrentes.find((x) => x.id === recurrenteId);
  if (!r) return { codigo: 'RECURRENTE_NO_ENCONTRADA', campo: null };
  if (r.anulado) return { codigo: 'RECURRENTE_ANULADA', campo: null };
  if (!esFecha(fecha) || fechasRecurrente(r, fecha, fecha).length !== 1 || ocurrenciasAnuladas(ctx.previsiones.apuntes).has(claveOcurrencia(r.id, fecha))) {
    return { codigo: 'OCURRENCIA_NO_VALIDA', campo: 'fecha_ocurrencia' };
  }
  const limite = limiteFuturo(ctx.datos, r.cuenta);
  if (limite === null) return { codigo: 'SIN_SALDO_DE_BANCO', campo: null };
  if (fecha <= limite) return { codigo: 'FECHA_NO_FUTURA', campo: 'fecha_ocurrencia' };
  return null;
}

// ---------------------------------------------------------------------------
// Sustitución (sugerida por la web; la confirma Marc, nunca es automática)
// ---------------------------------------------------------------------------

export interface CandidatoSustitucion {
  /** apunte:<id> o ocurrencia:<recurrente>|<fecha>, + el vencimiento. */
  clave: string;
  tipo: 'SUELTO' | 'OCURRENCIA';
  apunte_id: string | null;
  recurrente_id: string | null;
  fecha: string;
  cuenta: CuentaCashflow;
  categoria: string;
  concepto: string;
  importe: number;
  vencimiento: VencimientoCashflow & { vencimiento_orden: number; importe: number; fecha_vencimiento: string };
  /** |importe del vencimiento| − importe del apunte. */
  diferencia: number;
}
const cent = (x: number) => Math.round(x * 100);
/** Previsiones vigentes y futuras que se pueden sustituir: apuntes sueltos y ocurrencias. */
function previsionesFuturas(ctx: ContextoCashflow): { tipo: 'SUELTO' | 'OCURRENCIA'; apunte_id: string | null; recurrente_id: string | null; fecha: string; cuenta: CuentaCashflow; categoria: string; concepto: string; importe: number }[] {
  const p = ctx.previsiones;
  const sueltos = p.apuntes.filter((a) => !a.anulado && a.recurrente_id === null && a.importe !== null)
    .map((a) => ({ tipo: 'SUELTO' as const, apunte_id: a.id, recurrente_id: null, fecha: a.fecha, cuenta: a.cuenta, categoria: a.categoria, concepto: a.concepto, importe: a.importe as number }));
  const ocs = p.ocurrencias.map((o) => ({ tipo: 'OCURRENCIA' as const, apunte_id: null, recurrente_id: o.recurrente_id, fecha: o.fecha, cuenta: o.cuenta, categoria: o.categoria, concepto: o.concepto, importe: o.importe }));
  return [...sueltos, ...ocs].filter((x) => {
    const limite = limiteFuturo(ctx.datos, x.cuenta);
    return limite !== null && x.fecha > limite;
  });
}
/**
 * Facturas (vencimientos del sistema, solo PIO) que coinciden con un apunte: mismo concepto (el nombre comercial del
 * concepto, CORRESPONDENCIAS_PROVEEDOR, o el CIF de un concepto nuevo), vencimiento en la misma decena que el apunte o
 * en la siguiente e importe a ±5 % del apunte. Un vencimiento ya usado en una sustitución no vuelve a salir (la BD solo
 * deja que sustituya a un apunte). Con importe, fecha y orden; nunca un sentido no documentado ni un cargo negativo.
 */
export function candidatosSustitucion(ctx: ContextoCashflow, vencimientos: readonly VencimientoCashflow[]): CandidatoSustitucion[] {
  const p = ctx.previsiones;
  const usados = new Set(p.apuntes.filter((a) => a.sustituido_factura_id !== null).map((a) => `${a.sustituido_factura_id}|${a.sustituido_vencimiento_orden}`));
  const out: CandidatoSustitucion[] = [];
  for (const x of previsionesFuturas(ctx)) {
    if (x.cuenta !== CUENTA_VENCIMIENTOS) continue; // RITA: sin vencimientos ni facturas
    const c = clasificarCategoria(x.categoria);
    if (c === null) continue;
    const comercial = comercialDeConcepto(x.concepto);
    const cif = p.conceptos.find((k) => !k.anulado && k.cuenta === x.cuenta && k.categoria === x.categoria && mismoNombre(k.nombre, x.concepto))?.proveedor_cif ?? null;
    const d = decenaDe(x.fecha);
    const decenas = [d, siguienteDecena(d)];
    for (const v of vencimientos) {
      if (v.importe === null || v.fecha_vencimiento === null || v.vencimiento_orden === null || v.vencimiento_orden === undefined) continue;
      if (v.cargo_negativo || v.sentido !== (c.sentido === 'SALIDA' ? 'CARGO' : 'ABONO')) continue;
      if (usados.has(`${v.factura_id}|${v.vencimiento_orden}`)) continue;
      if (!decenas.includes(decenaDe(v.fecha_vencimiento.slice(0, 10)))) continue;
      const mismo = (comercial !== null && v.proveedor_comercial === comercial) || (cif !== null && v.proveedor_cif === cif);
      if (!mismo) continue;
      const dif = cent(Math.abs(v.importe)) - cent(x.importe);
      if (Math.abs(dif) > Math.round(cent(x.importe) * MARGEN_SUSTITUCION)) continue;
      out.push({
        ...x, clave: `${x.tipo === 'SUELTO' ? `apunte:${x.apunte_id}` : `ocurrencia:${x.recurrente_id}|${x.fecha}`}|${v.factura_id}|${v.vencimiento_orden}`,
        vencimiento: { ...v, vencimiento_orden: v.vencimiento_orden, importe: v.importe, fecha_vencimiento: v.fecha_vencimiento.slice(0, 10) }, diferencia: dif / 100,
      });
    }
  }
  return out.sort((a, b) => a.fecha.localeCompare(b.fecha) || a.clave.localeCompare(b.clave));
}
export interface PeticionSustitucion {
  apunte_id: string | null;
  recurrente_id: string | null;
  fecha_ocurrencia: string | null;
  factura_id: string;
  vencimiento_orden: number;
}
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const esUuid = (v: unknown): v is string => typeof v === 'string' && UUID.test(v);
export function validarSustitucion(body: unknown): Validacion<PeticionSustitucion> {
  const b = (body && typeof body === 'object' ? body : {}) as Record<string, unknown>;
  const errores: Record<string, string> = {};
  const apunte = b.apunte_id === undefined || b.apunte_id === null ? null : esUuid(b.apunte_id) ? b.apunte_id.toLowerCase() : undefined;
  const rec = b.recurrente_id === undefined || b.recurrente_id === null ? null : esUuid(b.recurrente_id) ? b.recurrente_id.toLowerCase() : undefined;
  const fecha = b.fecha_ocurrencia === undefined || b.fecha_ocurrencia === null ? null : esFecha(b.fecha_ocurrencia) ? b.fecha_ocurrencia : undefined;
  if (apunte === undefined || rec === undefined || fecha === undefined) errores.apunte = 'Apunte no válido';
  else if ((apunte === null) === (rec === null) || (rec !== null) !== (fecha !== null)) errores.apunte = 'Un apunte suelto o una ocurrencia (recurrente y fecha)';
  if (!esUuid(b.factura_id)) errores.factura_id = 'Factura no válida';
  if (typeof b.vencimiento_orden !== 'number' || !Number.isSafeInteger(b.vencimiento_orden) || b.vencimiento_orden < 0) errores.vencimiento_orden = 'Vencimiento no válido';
  if (Object.keys(errores).length > 0) return { ok: false, errores };
  return { ok: true, datos: { apunte_id: apunte ?? null, recurrente_id: rec ?? null, fecha_ocurrencia: fecha ?? null, factura_id: (b.factura_id as string).toLowerCase(), vencimiento_orden: b.vencimiento_orden as number } };
}
/** El candidato que pide la petición (null = ya no coincide: SUSTITUCION_NO_CANDIDATA). */
export function candidatoDe(cs: readonly CandidatoSustitucion[], s: PeticionSustitucion): CandidatoSustitucion | null {
  return cs.find((c) => c.vencimiento.factura_id.toLowerCase() === s.factura_id && c.vencimiento.vencimiento_orden === s.vencimiento_orden
    && (s.apunte_id !== null ? c.apunte_id === s.apunte_id : c.recurrente_id === s.recurrente_id && c.fecha === s.fecha_ocurrencia)) ?? null;
}
/** Motivo de la anulación por sustitución (lo que queda en la BD). */
export function motivoSustitucion(c: CandidatoSustitucion): string {
  return `Sustituido por la factura ${c.vencimiento.numero_factura ?? 'sin número'} (vencimiento ${c.vencimiento.vencimiento_orden}, ${c.vencimiento.fecha_vencimiento})`.slice(0, LARGO.motivo);
}

// ---------------------------------------------------------------------------
// Entrada del motor y lista de la pantalla
// ---------------------------------------------------------------------------

/** Apuntes sueltos vigentes (con importe) y ocurrencias, con su origen para el popup. */
export function apuntesMotor(p: PrevisionesCashflow): ApunteManualCashflow[] {
  const recs = new Map(p.recurrentes.map((r) => [r.id, r]));
  const sueltos = p.apuntes.filter((a) => !a.anulado && a.recurrente_id === null && a.importe !== null).map((a): ApunteManualCashflow => ({
    cuenta: a.cuenta, decena_inicio: decenaDe(a.fecha), categoria: a.categoria, concepto: a.concepto, importe: a.importe,
    origen: { tipo: 'SUELTO', id: a.id, fecha: a.fecha, nota: a.nota, autor: a.autor, creado_at: a.creado_at, importe: a.importe as number },
  }));
  const ocs = p.ocurrencias.flatMap((o): ApunteManualCashflow[] => {
    const r = recs.get(o.recurrente_id);
    return [{
      cuenta: o.cuenta, decena_inicio: decenaDe(o.fecha), categoria: o.categoria, concepto: o.concepto, importe: o.importe,
      origen: { tipo: 'OCURRENCIA', id: o.recurrente_id, fecha: o.fecha, nota: r?.nota ?? null, autor: r?.autor ?? '', creado_at: r?.creado_at ?? '', importe: o.importe },
    }];
  });
  return [...sueltos, ...ocs];
}

export interface ListaApuntes {
  sueltos: ApunteCashflow[];
  recurrentes: { recurrente: RecurrenteCashflow; proximas: string[]; anuladas: ApunteCashflow[] }[];
  /** Recuentos de lo que no se lista (anulados, sustituidos). */
  anulados: number;
  sustituidos: number;
}
/** «Apuntes manuales»: sueltos y recurrentes vigentes (filtro por cuenta), con las próximas ocurrencias futuras. */
export function listaApuntes(ctx: ContextoCashflow, cuenta: CuentaCashflow | null): ListaApuntes {
  const p = ctx.previsiones;
  const deCuenta = <T extends { cuenta: string }>(xs: readonly T[]) => xs.filter((x) => cuenta === null || x.cuenta === cuenta);
  const anuladas = ocurrenciasAnuladas(p.apuntes);
  return {
    sueltos: deCuenta(p.apuntes).filter((a) => !a.anulado && a.recurrente_id === null).sort((a, b) => a.fecha.localeCompare(b.fecha) || a.id.localeCompare(b.id)),
    recurrentes: deCuenta(p.recurrentes).filter((r) => !r.anulado).sort((a, b) => a.inicio.localeCompare(b.inicio) || a.id.localeCompare(b.id)).map((r) => {
      const limite = limiteFuturo(ctx.datos, r.cuenta);
      const proximas = p.ocurrencias.filter((o) => o.recurrente_id === r.id && limite !== null && o.fecha > limite).map((o) => o.fecha).slice(0, OCURRENCIAS_LISTADAS);
      return { recurrente: r, proximas, anuladas: [...anuladas.values()].filter((a) => a.recurrente_id === r.id).sort((a, b) => (a.fecha_ocurrencia ?? '').localeCompare(b.fecha_ocurrencia ?? '')) };
    }),
    anulados: deCuenta(p.apuntes).filter((a) => a.anulado && a.recurrente_id === null).length + deCuenta(p.recurrentes).filter((r) => r.anulado).length,
    sustituidos: deCuenta(p.apuntes).filter((a) => a.sustituido_factura_id !== null).length,
  };
}
