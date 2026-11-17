/**
 * H6-4: lista de Vencimientos con las mismas capacidades de filtrado que Facturas (pestañas por estado de la factura,
 * filtros, búsqueda también por importe y orden por columna) además de los filtros de H6 (periodo, estado de pago,
 * forma de pago). Módulo puro (front y pruebas). No cambia importes ni estados: solo filtra y ordena.
 *
 * Diferencias con Facturas, por los datos de cada vencimiento: no hay fecha de factura ni la diferencia del motor
 * (no forman parte del contrato `vencimientos`), así que esos dos filtros no existen aquí.
 *
 * Solo sintaxis TypeScript borrable.
 */
import { coincideImporte } from '../detalle.ts';
import { razonSocialSecundaria } from '../proveedor_comercial.ts';
import { ORDEN_PEOR } from './calendario.ts';
import { TEXTO_FORMA, cumpleBusquedaPago, textoPlano, type FilaVencimientoPago } from './pagos.ts';

// ---------------------------------------------------------------------------
// Pestañas (las de Facturas, por el estado de la factura del vencimiento)
// ---------------------------------------------------------------------------

type EstadosFactura = Pick<FilaVencimientoPago, 'estado_normalizacion' | 'estado_conciliacion_cf' | 'estado_revision'>;
export const PESTANAS_VENCIMIENTOS: readonly { clave: string; texto: string; cumple: (f: EstadosFactura) => boolean }[] = [
  { clave: 'todas', texto: 'Todas', cumple: () => true },
  { clave: 'conciliadas', texto: 'Conciliadas', cumple: (f) => f.estado_conciliacion_cf === 'CONCILIADA' },
  { clave: 'pendientes', texto: 'Pendientes de conciliar', cumple: (f) => f.estado_conciliacion_cf === 'PENDIENTE_CONCILIAR' },
  // Igual que Facturas e Inicio: normalización o conciliación en revisión.
  { clave: 'revision', texto: 'En revisión', cumple: (f) => f.estado_normalizacion === 'REQUIERE_REVISION' || f.estado_conciliacion_cf === 'REVISION_CONCILIACION' },
  { clave: 'no-revisadas', texto: 'No revisadas por Pío', cumple: (f) => f.estado_revision === 'PENDIENTE_REVISION_PIO' },
];
export function pestanaDe(clave: string | null) {
  return PESTANAS_VENCIMIENTOS.find((p) => p.clave === clave) ?? PESTANAS_VENCIMIENTOS[0];
}

// ---------------------------------------------------------------------------
// Filtros nuevos
// ---------------------------------------------------------------------------

type Nombres = Pick<FilaVencimientoPago, 'proveedor_comercial' | 'proveedor_razon_social' | 'proveedor' | 'proveedor_cif_comparable'>;
/** Clave de proveedor del filtro: el CIF comparable; sin CIF, el nombre (sin acentos ni mayúsculas). */
export function claveProveedor(f: Nombres): string {
  return f.proveedor_cif_comparable ?? `sin-cif:${textoPlano(f.proveedor_comercial ?? f.proveedor_razon_social ?? f.proveedor ?? '')}`;
}
export interface OpcionProveedorPago { clave: string; texto: string; vencimientos: number }
/** Opciones del filtro de proveedor: nombre comercial · razón social (si difiere); «(sin CIF)» si no tiene. */
export function opcionesProveedor(filas: readonly Nombres[]): OpcionProveedorPago[] {
  const m = new Map<string, OpcionProveedorPago>();
  for (const f of filas) {
    const clave = claveProveedor(f);
    const o = m.get(clave);
    if (o) { o.vencimientos++; continue; }
    const principal = f.proveedor_comercial ?? f.proveedor_razon_social ?? f.proveedor ?? 'Proveedor sin identificar';
    const sec = razonSocialSecundaria(f.proveedor_comercial, f.proveedor_razon_social);
    m.set(clave, { clave, texto: `${principal}${sec ? ` · ${sec}` : ''}${f.proveedor_cif_comparable === null ? ' (sin CIF)' : ''}`, vencimientos: 1 });
  }
  return [...m.values()].sort((a, b) => a.texto.localeCompare(b.texto, 'es') || a.clave.localeCompare(b.clave));
}

/** Rangos de importe de Facturas, por el valor absoluto (un abono de −45,30 € entra en «Hasta 200 €»). */
export const IMPORTES_LISTA = [
  { clave: 'hasta200', texto: 'Hasta 200 €' },
  { clave: '200a1000', texto: 'De 200 a 1.000 €' },
  { clave: 'mas1000', texto: 'Más de 1.000 €' },
  { clave: 'sin', texto: 'Importe pendiente' },
] as const;
export function cumpleImporte(importe: number | null, rango: string): boolean {
  if (rango === '') return true;
  if (rango === 'sin') return importe === null;
  if (importe === null) return false;
  const a = Math.abs(importe);
  if (rango === 'hasta200') return a <= 200;
  if (rango === '200a1000') return a > 200 && a <= 1000;
  if (rango === 'mas1000') return a > 1000;
  return true;
}

/** Estado de la factura: 'norm:X' o 'conc:X' (como el filtro «Estado» de Facturas, sin la diferencia del motor). */
export function cumpleEstadoFactura(f: EstadosFactura, valor: string): boolean {
  if (valor === '') return true;
  const [eje, v] = valor.split(':');
  if (eje === 'norm') return f.estado_normalizacion === v;
  if (eje === 'conc') return f.estado_conciliacion_cf === v;
  return true;
}

/**
 * Búsqueda de la lista: la de H6 (proveedor, CIF, nº de factura) y, como en Facturas, un importe ("152", "152,37",
 * "45,30 €") contra el importe del vencimiento y el total de su factura (por el valor absoluto).
 */
export function cumpleBusquedaLista(f: Parameters<typeof cumpleBusquedaPago>[0] & Pick<FilaVencimientoPago, 'importe' | 'importe_factura'>, q: string): boolean {
  if (q.trim() === '') return true;
  return coincideImporte(q, [f.importe, f.importe_factura]) || cumpleBusquedaPago(f, q);
}

// ---------------------------------------------------------------------------
// Orden por columna (los null siempre al final; empate: orden de llegada, que es fecha, nº y orden)
// ---------------------------------------------------------------------------

type Valor = string | number | null;
export const COLUMNAS_LISTA: readonly { clave: string; texto: string; num?: boolean; valor: (f: FilaVencimientoPago) => Valor }[] = [
  { clave: 'fecha', texto: 'Fecha', valor: (f) => f.fecha_vencimiento?.slice(0, 10) ?? null },
  { clave: 'proveedor', texto: 'Proveedor', valor: (f) => textoPlano(f.proveedor_comercial ?? f.proveedor_razon_social ?? f.proveedor ?? '') || null },
  { clave: 'numero', texto: 'Nº factura', valor: (f) => f.numero_factura },
  { clave: 'importe', texto: 'Importe', num: true, valor: (f) => f.importe },
  { clave: 'sentido', texto: 'Sentido', valor: (f) => f.sentido },
  { clave: 'forma', texto: 'Forma de pago', valor: (f) => TEXTO_FORMA[f.forma_pago] },
  // Estado: por gravedad (el peor primero en orden ascendente), no por orden alfabético.
  { clave: 'estado', texto: 'Estado', valor: (f) => ORDEN_PEOR.indexOf(f.estado_pago) },
];
export const COLUMNA_POR_DEFECTO = 'fecha';

export function columnaDe(clave: string | null) {
  return COLUMNAS_LISTA.find((c) => c.clave === clave) ?? COLUMNAS_LISTA[0];
}
export function direccionDe(dir: string | null): 1 | -1 {
  return dir === 'desc' ? -1 : 1;
}

function comparar(a: Valor, b: Valor, dir: 1 | -1): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return (typeof a === 'number' && typeof b === 'number' ? a - b : String(a).localeCompare(String(b), 'es')) * dir;
}

/** Ordena sin mutar; estable. */
export function ordenar<T extends FilaVencimientoPago>(filas: readonly T[], columna: string | null, dir: string | null): T[] {
  const c = columnaDe(columna);
  const d = direccionDe(dir);
  return filas.map((f, i) => ({ f, i }))
    .sort((a, b) => comparar(c.valor(a.f), c.valor(b.f), d) || a.i - b.i)
    .map((x) => x.f);
}
