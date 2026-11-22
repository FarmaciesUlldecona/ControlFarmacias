/**
 * H8: pantalla Conciliación (doble comprobación por factura). Puro: no conecta a nada ni recalcula diferencias ni
 * tolerancias (siempre las del motor). Lo usan el front, las pruebas y check_fixtures.
 *
 *  (1) albaranes ↔ factura: el motor existente (estado_conciliacion_cf y conciliación vigente);
 *  (2) banco ↔ pago: Norma 43, futura. Hoy siempre «sin datos bancarios» (gris).
 *
 * Solo sintaxis TypeScript borrable.
 */
import type { Color, ConciliacionBandejaDTO, EstadoBanco, FacturaBandeja, Importe, RevisarNoche, SinFactura } from './contrato.ts';
import { DICCIONARIO_CASADO, claveCasado, coincideImporte, etiquetaConciliacion, etiquetaResultadoMotor } from './detalle.ts';

// ---------------------------------------------------------------------------
// Marca 1: albaranes ↔ factura
// ---------------------------------------------------------------------------

export type ClaveMarcaAlbaranes = 'CONCILIADA' | 'DIFERENCIA' | 'PENDIENTE' | 'REVISION' | 'OTRO';
export interface MarcaAlbaranes {
  clave: ClaveMarcaAlbaranes;
  simbolo: '✓' | '✗' | '○' | '!' | '?';
  texto: string;
  color: Color;
  /** Diferencia del motor (conciliación vigente), tal cual; null si no hay o no es evaluable. */
  diferencia_motor: Importe;
}

export const MARCAS_ALBARANES: Record<ClaveMarcaAlbaranes, Omit<MarcaAlbaranes, 'diferencia_motor' | 'clave'>> = {
  CONCILIADA: { simbolo: '✓', texto: 'conciliada', color: 'verde' },
  DIFERENCIA: { simbolo: '✗', texto: 'con diferencia', color: 'rojo' },
  PENDIENTE: { simbolo: '○', texto: 'pendiente', color: 'azul' },
  REVISION: { simbolo: '!', texto: 'en revisión', color: 'naranja' },
  // Estado que el código no conoce: gris con el literal (nunca se inventa un significado).
  OTRO: { simbolo: '?', texto: 'estado no reconocido', color: 'gris' },
};
export const OPCIONES_MARCA_ALBARANES: ClaveMarcaAlbaranes[] = ['CONCILIADA', 'DIFERENCIA', 'PENDIENTE', 'REVISION'];

type FacturaMarca = Pick<FacturaBandeja, 'estado_conciliacion_cf' | 'conciliacion'>;

/**
 * ✓ conciliada (CONCILIADA) | ✗ con diferencia (pendiente con resultado del motor distinto de CONCILIADA: DIFERENCIA o
 * NO_EVALUABLE) | ○ pendiente (pendiente sin resultado) | ! en revisión (REVISION_CONCILIACION).
 */
export function marcaAlbaranes(fa: FacturaMarca): MarcaAlbaranes {
  const c = fa.conciliacion;
  const res = c?.resultado ?? null;
  let clave: ClaveMarcaAlbaranes;
  if (fa.estado_conciliacion_cf === 'CONCILIADA') clave = 'CONCILIADA';
  else if (fa.estado_conciliacion_cf === 'REVISION_CONCILIACION') clave = 'REVISION';
  else if (fa.estado_conciliacion_cf === 'PENDIENTE_CONCILIAR') clave = res !== null && res !== 'CONCILIADA' ? 'DIFERENCIA' : 'PENDIENTE';
  else clave = 'OTRO';
  const base = MARCAS_ALBARANES[clave];
  const texto = clave === 'DIFERENCIA' && res === 'NO_EVALUABLE' ? etiquetaResultadoMotor(res).texto.toLowerCase()
    : clave === 'OTRO' ? fa.estado_conciliacion_cf : base.texto;
  return { clave, ...base, texto, diferencia_motor: res === 'NO_EVALUABLE' ? null : c?.diferencia ?? null };
}

// ---------------------------------------------------------------------------
// Marca 2: banco ↔ pago (Norma 43, futura)
// ---------------------------------------------------------------------------

export interface MarcaBanco { clave: EstadoBanco['estado']; simbolo: '✓' | '○'; texto: string; color: Color }
export function marcaBanco(b: EstadoBanco): MarcaBanco {
  return b.estado === 'PAGADO_BANCO'
    ? { clave: 'PAGADO_BANCO', simbolo: '✓', texto: 'pagado (banco)', color: 'verde' }
    : { clave: 'SIN_DATOS_BANCARIOS', simbolo: '○', texto: 'sin datos bancarios', color: 'gris' };
}

// ---------------------------------------------------------------------------
// Resumen en euros de la doble comprobación
// ---------------------------------------------------------------------------

export interface TramoResumen { facturas: number; importe: Importe }
export interface ResumenDoble {
  verificado_doble: TramoResumen;
  solo_albaranes: TramoResumen;
  /** Banco sí, albaranes no (hoy imposible: no hay datos bancarios). */
  solo_banco: TramoResumen;
  ninguna: TramoResumen;
  /** Facturas sin importe: fuera de los totales, solo recuento. */
  sin_importe: number;
}

const r4 = (v: number) => Math.round(v * 10000) / 10000;

export function resumenDoble(fs: readonly FacturaBandeja[]): ResumenDoble {
  const t = (): TramoResumen => ({ facturas: 0, importe: null });
  const out: ResumenDoble = { verificado_doble: t(), solo_albaranes: t(), solo_banco: t(), ninguna: t(), sin_importe: 0 };
  for (const fa of fs) {
    if (fa.importe_total === null) { out.sin_importe += 1; continue; }
    const alb = marcaAlbaranes(fa).clave === 'CONCILIADA';
    const ban = fa.banco.estado === 'PAGADO_BANCO';
    const tramo = alb && ban ? out.verificado_doble : alb ? out.solo_albaranes : ban ? out.solo_banco : out.ninguna;
    tramo.facturas += 1;
    tramo.importe = r4((tramo.importe ?? 0) + fa.importe_total);
  }
  return out;
}

// ---------------------------------------------------------------------------
// «Para revisar» de la noche: facturas señaladas
// ---------------------------------------------------------------------------

export function facturasRevisarNoche(r: RevisarNoche): Set<string> {
  return new Set(r.elementos.map((e) => e.factura_id).filter((x): x is string => x !== null));
}

// ---------------------------------------------------------------------------
// Filtros de «Doble comprobación» (en la URL, como Facturas)
// ---------------------------------------------------------------------------

export interface FiltrosDoble { proveedor: string; estado: string; q: string }

/** estado: clave de marca de albaranes o «noche» (en «para revisar» de la última noche). */
export function cumpleFiltrosDoble(fa: FacturaBandeja, f: FiltrosDoble, noche: Set<string>): boolean {
  if (f.proveedor && fa.proveedor_grupo !== f.proveedor) return false;
  if (f.estado === 'noche' ? !noche.has(fa.factura_id) : f.estado && marcaAlbaranes(fa).clave !== f.estado) return false;
  const q = f.q.trim();
  if (q) {
    const plano = (s: string | null) => (s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    const t = plano(q);
    const textos = [fa.numero_factura, fa.proveedor_comercial, fa.proveedor_razon_social, fa.proveedor_etiqueta, fa.proveedor].map(plano);
    if (!textos.some((x) => x.includes(t)) && !coincideImporte(q, [fa.importe_total])) return false;
  }
  return true;
}

// ---------------------------------------------------------------------------
// Pestaña «Albaranes»: bandeja por proveedor → motivo, ordenada por dinero en riesgo
// ---------------------------------------------------------------------------

export type ClaveMotivo = 'REVISION' | 'NO_LOCALIZADO' | 'DIFERENCIA' | 'NO_EVALUABLE' | 'PENDIENTE';
/** Texto llano del diccionario existente (detalle.ts). */
export const MOTIVOS_BANDEJA: Record<ClaveMotivo, { texto: string; color: Color }> = {
  REVISION: { texto: etiquetaConciliacion('REVISION_CONCILIACION').texto, color: 'naranja' },
  NO_LOCALIZADO: { texto: DICCIONARIO_CASADO['SIN:SIN_COINCIDENCIA'].texto, color: 'rojo' },
  DIFERENCIA: { texto: etiquetaResultadoMotor('DIFERENCIA').texto, color: 'rojo' },
  NO_EVALUABLE: { texto: etiquetaResultadoMotor('NO_EVALUABLE').texto, color: 'rojo' },
  PENDIENTE: { texto: etiquetaConciliacion('PENDIENTE_CONCILIAR').texto, color: 'azul' },
};
const ORDEN_MOTIVO: ClaveMotivo[] = ['REVISION', 'NO_LOCALIZADO', 'DIFERENCIA', 'NO_EVALUABLE', 'PENDIENTE'];

/** Motivo principal de una factura no conciliada: revisión > albarán no localizado > diferencia > no evaluable > pendiente. */
export function motivoBandeja(fa: FacturaBandeja): ClaveMotivo {
  if (fa.estado_conciliacion_cf === 'REVISION_CONCILIACION') return 'REVISION';
  if (fa.lineas.some((l) => { const k = claveCasado(l); return k === 'SIN:SIN_COINCIDENCIA' || k === 'SIN:OTRO' || k === 'SIN:NUMERO_AUSENTE'; })) return 'NO_LOCALIZADO';
  const res = fa.conciliacion?.resultado ?? null;
  if (res === 'DIFERENCIA') return 'DIFERENCIA';
  if (res === 'NO_EVALUABLE') return 'NO_EVALUABLE';
  return 'PENDIENTE';
}

/** Dinero en riesgo: vencimiento más próximo primero (sin fecha al final), luego importe mayor (sin importe al final). */
export function compararRiesgo(a: FacturaBandeja, b: FacturaBandeja): number {
  const fa = a.vencimiento_proximo?.fecha_vencimiento ?? null;
  const fb = b.vencimiento_proximo?.fecha_vencimiento ?? null;
  if (fa !== fb) {
    if (fa === null) return 1;
    if (fb === null) return -1;
    return fa.localeCompare(fb);
  }
  const ia = a.importe_total;
  const ib = b.importe_total;
  if (ia !== ib) {
    if (ia === null) return 1;
    if (ib === null) return -1;
    return ib - ia;
  }
  return (a.numero_factura ?? '').localeCompare(b.numero_factura ?? '') || a.factura_id.localeCompare(b.factura_id);
}

export interface GrupoMotivo { clave: ClaveMotivo; texto: string; color: Color; facturas: FacturaBandeja[] }
export interface GrupoBandeja { proveedor_grupo: string; facturas: number; importe: Importe; sin_importe: number; motivos: GrupoMotivo[] }

/** Facturas no conciliadas, por proveedor → motivo, del dinero en mayor riesgo al menor. */
export function bandejaAlbaranes(fs: readonly FacturaBandeja[]): GrupoBandeja[] {
  const pend = fs.filter((fa) => fa.estado_conciliacion_cf !== 'CONCILIADA').sort(compararRiesgo);
  const grupos = new Map<string, GrupoBandeja>();
  for (const fa of pend) {
    const g = grupos.get(fa.proveedor_grupo) ?? { proveedor_grupo: fa.proveedor_grupo, facturas: 0, importe: null, sin_importe: 0, motivos: [] };
    const k = motivoBandeja(fa);
    let m = g.motivos.find((x) => x.clave === k);
    if (!m) { m = { clave: k, ...MOTIVOS_BANDEJA[k], facturas: [] }; g.motivos.push(m); }
    m.facturas.push(fa);
    g.facturas += 1;
    if (fa.importe_total === null) g.sin_importe += 1; else g.importe = r4((g.importe ?? 0) + fa.importe_total);
    grupos.set(fa.proveedor_grupo, g);
  }
  // Los motivos de cada proveedor y los proveedores quedan en el orden de su factura de más riesgo (pend ya ordenado);
  // a igualdad de riesgo, el motivo más grave primero.
  for (const g of grupos.values()) {
    g.motivos.sort((a, b) => compararRiesgo(a.facturas[0], b.facturas[0]) || ORDEN_MOTIVO.indexOf(a.clave) - ORDEN_MOTIVO.indexOf(b.clave));
  }
  return [...grupos.values()];
}

/** «se cobra el dd/mm»: enlace al día del vencimiento en Vencimientos. */
export function enlaceVencimiento(fecha: string): string {
  return `/vencimientos?vista=dia&fecha=${fecha.slice(0, 10)}`;
}

// ---------------------------------------------------------------------------
// Pestaña «Albaranes»: cabecera y cobertura por proveedor
// ---------------------------------------------------------------------------

export interface Cobertura { facturado: Importe; conciliado: Importe; sin_importe: number; ratio: number | null }
function cobertura(fs: readonly FacturaBandeja[]): Cobertura {
  let facturado: number | null = null;
  let conciliado: number | null = null;
  let sin = 0;
  for (const fa of fs) {
    if (fa.importe_total === null) { sin += 1; continue; }
    facturado = r4((facturado ?? 0) + fa.importe_total);
    if (fa.estado_conciliacion_cf === 'CONCILIADA') conciliado = r4((conciliado ?? 0) + fa.importe_total);
  }
  if (facturado !== null && conciliado === null) conciliado = 0;
  return { facturado, conciliado, sin_importe: sin, ratio: facturado !== null && conciliado !== null && facturado !== 0 ? conciliado / facturado : null };
}

export interface CabeceraAlbaranes { cobertura: Cobertura; conciliadas: number; pendientes: number; en_revision: number }
export function cabeceraAlbaranes(d: Pick<ConciliacionBandejaDTO, 'facturas'>): CabeceraAlbaranes {
  const fs = d.facturas;
  return {
    cobertura: cobertura(fs),
    conciliadas: fs.filter((x) => x.estado_conciliacion_cf === 'CONCILIADA').length,
    pendientes: fs.filter((x) => x.estado_conciliacion_cf === 'PENDIENTE_CONCILIAR').length,
    en_revision: fs.filter((x) => x.estado_conciliacion_cf === 'REVISION_CONCILIACION').length,
  };
}

/** H8-5: albaranes de Farmatic pendientes de automatizar (grupo «sin lector» de Sin factura) de un mismo nombre. */
export interface PendientesFarmatic { albaranes: number; importe: Importe; sin_importe: number }
export type FilaCobertura =
  | { tipo: 'LECTOR'; clave: string; proveedor_grupo: string; nombre: string | null; nombre_mostrado: string; facturas: number;
      cobertura: Cobertura; pendientes: PendientesFarmatic | null }
  | { tipo: 'SIN_LECTOR'; clave: string; proveedor: string; albaranes: number; importe: Importe; sin_importe: number };

/** H8-5: clave de comparación de nombres (mayúsculas, sin acentos, solo A-Z/0-9): «LOGISTA PHARMA» = «LOGISTAPHARMA». */
export function claveNombreProveedor(s: string): string {
  return s.normalize('NFD').replace(/\p{M}/gu, '').toUpperCase().replace(/[^A-Z0-9]/g, '');
}
const NOMBRE_SIN_IDENTIFICAR = 'Proveedor sin identificar';

/**
 * Proveedores con facturas leídas (barra de cobertura) y, después, los «sin lector» de Farmatic (sin barra).
 * H8-4: agrupa con el mismo nombre comercial que la lista (proveedor_comercial: por CIF y, si falta, por el literal y
 * sus correspondencias). Una factura sin comercial va con el comercial de su grupo (CIF o id) si lo tiene; si no, en su
 * grupo. Así una factura HEFAME sin CIF ni id cae en HEFAME, no en «Proveedor sin identificar». Los traspasos entre
 * farmacias no entran.
 * H8-5: una sola fila por nombre comercial (o, sin comercial, por el nombre mostrado: la etiqueta del grupo). Los
 * albaranes «pendientes de automatizar» de Farmatic con ese mismo nombre van en la misma fila (`pendientes`); solo los
 * que no casan con ninguna factura leída salen como «sin lector», también una fila por nombre. Los albaranes sin
 * proveedor comparable («Proveedor sin identificar») nunca se juntan con nada.
 */
export function coberturaProveedores(fs: readonly FacturaBandeja[], sf: SinFactura): FilaCobertura[] {
  const comercialDeGrupo = new Map<string, string>();
  const etiquetaDeGrupo = new Map<string, string>();
  for (const fa of fs) {
    if (fa.proveedor_grupo === 'sin_identificar') continue;
    if (fa.proveedor_comercial && !comercialDeGrupo.has(fa.proveedor_grupo)) comercialDeGrupo.set(fa.proveedor_grupo, fa.proveedor_comercial);
    if (!etiquetaDeGrupo.has(fa.proveedor_grupo)) etiquetaDeGrupo.set(fa.proveedor_grupo, fa.proveedor_etiqueta);
  }
  const por = new Map<string, { grupo: string; nombre: string | null; mostrado: string; xs: FacturaBandeja[] }>();
  for (const fa of fs) {
    const nombre = fa.proveedor_comercial ?? comercialDeGrupo.get(fa.proveedor_grupo) ?? null;
    const identificado = nombre !== null || fa.proveedor_grupo !== 'sin_identificar';
    const mostrado = nombre ?? (identificado ? etiquetaDeGrupo.get(fa.proveedor_grupo) ?? fa.proveedor_etiqueta : NOMBRE_SIN_IDENTIFICAR);
    const clave = identificado ? `nombre:${claveNombreProveedor(mostrado)}` : 'sin_identificar';
    const e = por.get(clave) ?? { grupo: fa.proveedor_grupo, nombre, mostrado, xs: [] };
    // El grupo de referencia (para el nombre de respaldo) es el primero que no sea «sin identificar».
    if (e.grupo === 'sin_identificar') e.grupo = fa.proveedor_grupo;
    if (e.nombre === null && nombre !== null) { e.nombre = nombre; e.mostrado = nombre; }
    e.xs.push(fa);
    por.set(clave, e);
  }
  // Pendientes de automatizar por nombre: a la fila de facturas de ese nombre; si no hay, una fila «sin lector».
  const sinLector = new Map<string, FilaCobertura & { tipo: 'SIN_LECTOR' }>();
  const pendientesDe = new Map<string, PendientesFarmatic>();
  const sumar = (r: { albaranes: number; importe: Importe; sin_importe: number }, s: { albaranes: number; importe: Importe; sin_importe: number }) => {
    r.albaranes += s.albaranes;
    r.sin_importe += s.sin_importe;
    if (s.importe !== null) r.importe = Math.round(((r.importe ?? 0) + s.importe) * 10000) / 10000;
  };
  for (const s of sf.sin_lector) {
    const clave = s.identificado ? `nombre:${claveNombreProveedor(s.proveedor)}` : 'farmatic:sin_identificar';
    if (s.identificado && por.has(clave)) {
      const p = pendientesDe.get(clave) ?? { albaranes: 0, importe: null, sin_importe: 0 };
      sumar(p, s);
      pendientesDe.set(clave, p);
      continue;
    }
    const f = sinLector.get(clave) ?? { tipo: 'SIN_LECTOR', clave, proveedor: s.proveedor, albaranes: 0, importe: null, sin_importe: 0 };
    sumar(f, s);
    sinLector.set(clave, f);
  }
  const lector: FilaCobertura[] = [...por.entries()].map(([clave, e]) => ({ tipo: 'LECTOR', clave, proveedor_grupo: e.grupo, nombre: e.nombre,
    nombre_mostrado: e.mostrado, facturas: e.xs.length, cobertura: cobertura(e.xs), pendientes: pendientesDe.get(clave) ?? null }));
  lector.sort((a, b) => {
    const x = a.tipo === 'LECTOR' ? a.cobertura.facturado : null;
    const y = b.tipo === 'LECTOR' ? b.cobertura.facturado : null;
    return (x === null ? 1 : 0) - (y === null ? 1 : 0) || (y ?? 0) - (x ?? 0) || a.clave.localeCompare(b.clave);
  });
  return [...lector, ...sinLector.values()];
}

/** Recuento de alertas de albaranes por tipo (Inicio: solo recuento con enlace). */
export function recuentoAlertas(d: Pick<ConciliacionBandejaDTO, 'alertas'>): { duplicados: number; no_en_farmatic: number; correcciones: number; total: number } {
  const n = (t: string) => d.alertas.filter((a) => a.tipo === t).length;
  const r = { duplicados: n('POSIBLE_DUPLICADO_FARMATIC'), no_en_farmatic: n('ALBARAN_FACTURADO_NO_EN_FARMATIC'), correcciones: n('CORRECCION_APROBADA') };
  return { ...r, total: r.duplicados + r.no_en_farmatic + r.correcciones };
}
