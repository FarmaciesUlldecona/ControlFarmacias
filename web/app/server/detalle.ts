/**
 * H5: textos llanos de la pantalla Facturas (listado y detalle). Puro: no conecta a nada, no recalcula importes,
 * diferencias ni tolerancias (siempre las del motor). Lo usan el front y check_fixtures.
 *
 * Fuentes del diccionario de tipos de casado (leídas, nunca ejecutadas):
 *   C = src/facturas/runtime_supabase/conciliacion.py
 *   M = src/facturas/runtime_supabase/modelos.py
 *   S = sql/migrations/11_cf_conciliacion.sql (CHECK de conciliacion_detalles.tipo_relacion y estado)
 *   R17 = sql/migrations/24_cf_r17_recepcion.sql (cf_linea_r17_valida revalida la pareja)
 *
 * Solo sintaxis TypeScript borrable (Node la ejecuta sin compilar).
 */
import {
  CODIGOS_SENTIDO, TEXTO_INCIDENCIA, TEXTO_VENCIMIENTO_SIN_SENTIDO, idProveedorR9, textoIncidencia,
  type Color, type FacturaDetalleDTO, type FacturaResumen, type Importe, type LineaConciliacion,
} from './contrato.ts';
import { canonicalizarProveedor } from './proveedor_comercial.ts';

// ---------------------------------------------------------------------------
// Estados (tres ejes separados) y etiquetas
// ---------------------------------------------------------------------------

export interface Etiqueta { texto: string; color: Color }

const ESTADO_NORMALIZACION: Record<string, Etiqueta> = {
  PENDIENTE: { texto: 'Pendiente de leer', color: 'azul' },
  NORMALIZANDO: { texto: 'Leyendo', color: 'azul' },
  NORMALIZADA: { texto: 'Normalizada', color: 'verde' },
  REQUIERE_REVISION: { texto: 'Requiere revisión', color: 'naranja' },
};
const ESTADO_CONCILIACION: Record<string, Etiqueta> = {
  PENDIENTE_CONCILIAR: { texto: 'Pendiente de conciliar', color: 'azul' },
  CONCILIADA: { texto: 'Conciliada', color: 'verde' },
  REVISION_CONCILIACION: { texto: 'Revisión conciliación', color: 'naranja' },
};
const ESTADO_REVISION: Record<string, Etiqueta> = {
  NO_REQUERIDA: { texto: 'No requerida', color: 'gris' },
  PENDIENTE_REVISION_PIO: { texto: 'Pendiente Pío', color: 'naranja' },
  VALIDADA_PIO: { texto: 'Validada Pío', color: 'verde' },
};

/** Estado desconocido: gris con el literal (nunca se inventa un significado). */
function etiqueta(mapa: Record<string, Etiqueta>, v: string | null): Etiqueta {
  if (v !== null && Object.hasOwn(mapa, v)) return mapa[v];
  return { texto: v ?? 'Sin estado', color: 'gris' };
}
export const etiquetaNormalizacion = (v: string | null) => etiqueta(ESTADO_NORMALIZACION, v);
export const etiquetaConciliacion = (v: string | null) => etiqueta(ESTADO_CONCILIACION, v);
export const etiquetaRevision = (v: string | null) => etiqueta(ESTADO_REVISION, v);
export const OPCIONES_NORMALIZACION = Object.keys(ESTADO_NORMALIZACION);
export const OPCIONES_CONCILIACION = Object.keys(ESTADO_CONCILIACION);
export const OPCIONES_REVISION = Object.keys(ESTADO_REVISION);

/** Resultado del motor (conciliaciones.resultado) en texto llano. */
const RESULTADO_MOTOR: Record<string, Etiqueta> = {
  CONCILIADA: { texto: 'Cuadra con sus albaranes', color: 'verde' },
  DIFERENCIA: { texto: 'No cuadra con sus albaranes', color: 'rojo' },
  NO_EVALUABLE: { texto: 'No se puede comprobar', color: 'rojo' },
  PENDIENTE_REVISION_PIO: { texto: 'Pendiente de revisión de Pío', color: 'naranja' },
};
export const etiquetaResultadoMotor = (v: string | null) => etiqueta(RESULTADO_MOTOR, v);

// ---------------------------------------------------------------------------
// Tipos de casado (línea del PDF ↔ albarán de Farmatic)
// ---------------------------------------------------------------------------

export interface EntradaCasado {
  texto: string;
  color: Color;
  /** fichero:línea del motor donde se define (para el informe y el title). */
  fuente: string;
}

/**
 * H5-2: "cómo casó", dato principal. La forma de casar el número (provenance.clase_numero; si falta,
 * coincidencia_numero; Hefame: estado_matching EXACTO_ECONOMICO) o, si no casó, el motivo (estado_matching).
 * El tipo de relación (1 a 1, R17, varios a 1) es secundario: RELACION_CASADO.
 */
/**
 * H5-5: fuentes de EXACTO y ECONOMICO_UNICO (commit:fichero:línea; los ficheros ya no están en HEAD). Los scripts 2T y
 * 2V clasificaban el resultado de buscar_candidato_albaran: EXACTO = MATCH_UNICO con coincidencia_numero EXACTA;
 * ECONOMICO_UNICO = MATCH_UNICO sin número exacto; y lo guardaban en provenance.estado_matching.
 */
const FUENTE_EXACTO = 'e18acf0:pruebas/auditoria_2t/flujo_controlado.py:210,370; e18acf0:pruebas/auditoria_2v/conciliar_08009277.py:72,197';
const FUENTE_ECONOMICO_UNICO = 'e18acf0:pruebas/auditoria_2t/flujo_controlado.py:211,370; e18acf0:pruebas/auditoria_2v/conciliar_08009277.py:73,197; '
  + 'e18acf0:pruebas/auditoria_2t/resultado.md:36-40';
/** H5-5: estados de una versión anterior del motor (no los escribe el código actual). */
export const ESTADOS_VERSION_ANTERIOR = ['EXACTO', 'ECONOMICO_UNICO'] as const;

export const DICCIONARIO_CASADO = {
  // Forma de casar el número (clase_numero, R15b, C:117,180-207)
  'NUMERO:EXACTA': { texto: 'Mismo número de albarán', color: 'verde', fuente: 'C:176,183' },
  'NUMERO:LETRA_FINAL': { texto: 'Mismo número con una letra final (Alliance: 08C52171A = 08C52171)', color: 'verde', fuente: 'C:29-30,184,198-200' },
  'NUMERO:FINAL_DOCUMENTAL': { texto: 'El número de Farmatic es el final del número de la factura', color: 'verde', fuente: 'C:31,185,201-202' },
  'NUMERO:INTERNO': { texto: 'Numeración interna de Farmatic (Q/R…): casa por importe', color: 'verde', fuente: 'C:27-28,186,205-206' },
  'NUMERO:SIN_PATRON': { texto: 'Proveedor sin numeración comparable: casa por importe y fecha (±3 días)', color: 'verde', fuente: 'C:23-24,189,207' },
  'NUMERO:PROVEEDOR': { texto: 'Número de Alliance con otro formato', color: 'verde', fuente: 'C:187-188,207' },
  'NUMERO:DIFERENTE': { texto: 'Número distinto: casa solo por importe', color: 'verde', fuente: 'C:170-177,317-324' },
  // H5-3: sin número en el PDF o en Farmatic (C:173-174,203-204): no cuenta como coincidencia de número, así que solo
  // casa por PUC (C:317-324) y dentro de ±3 días (C:23-24,267-271).
  'NUMERO:NO_DISPONIBLE': { texto: 'Sin número para comparar: casa por importe (PUC) y fecha (±3 días)', color: 'verde', fuente: 'C:173-174,203-204,267-271,317-324' },
  'NUMERO:OTRO': { texto: 'Casado (forma del número no registrada)', color: 'verde', fuente: 'M:46; S:60' },
  // Hefame: número exacto e importe (estado_matching EXACTO_ECONOMICO, C:370)
  'HEFAME:EXACTO_ECONOMICO': { texto: 'Mismo número e importe (Hefame)', color: 'verde', fuente: 'C:327-349,370' },
  // H5-5: estados escritos por una versión anterior del motor (scripts de los hitos 2T/2V; ya no están en el código).
  'ANTERIOR:EXACTO': { texto: 'Un único albarán; el motor anterior lo dio por número coincidente (versión anterior del motor)', color: 'verde', fuente: FUENTE_EXACTO },
  'ANTERIOR:ECONOMICO_UNICO': { texto: 'Un único albarán por importe; el número no es idéntico (versión anterior del motor)', color: 'verde', fuente: FUENTE_ECONOMICO_UNICO },
  // Cargos y abonos sin albarán (C:694-738)
  'MOVIMIENTO': { texto: 'Cargo o servicio sin albarán: no se busca en Farmatic', color: 'gris', fuente: 'C:694-724; M:49; S:63' },
  'MOVIMIENTO:ABONO': { texto: 'Abono sin albarán: no se busca en Farmatic', color: 'gris', fuente: 'C:665-667,713-714; M:49' },
  'MOVIMIENTO:SIN_SENTIDO': { texto: 'Cargo o abono sin sentido documentado: no se puede sumar ni restar', color: 'naranja', fuente: 'C:702-706' },
  // Sin coincidencia (tipo_relacion SIN_COINCIDENCIA; provenance.estado_matching, C:615-633)
  'SIN:SIN_COINCIDENCIA': { texto: 'Albarán no localizado en Farmatic', color: 'rojo', fuente: 'C:375,624-629; M:50; S:64' },
  'SIN:AMBIGUO': { texto: 'Varios albaranes posibles: no se elige ninguno', color: 'naranja', fuente: 'C:361-363,375' },
  'SIN:AMBIGUO_R17': { texto: 'Varias parejas posibles de la misma recepción: no se elige ninguna', color: 'naranja', fuente: 'C:539-558' },
  'SIN:CONFLICTO_R17': { texto: 'El albarán encaja en dos líneas: no se casa ninguna', color: 'naranja', fuente: 'C:539-540,561-562' },
  'SIN:ALBARAN_YA_CONCILIADO': { texto: 'El albarán ya justifica otra factura o línea', color: 'naranja', fuente: 'C:400-405,421-425' },
  'SIN:NUMERO_PROVEEDOR_DISTINTO': { texto: 'Solo hay un albarán de Alliance con otro número: no casa por importe', color: 'naranja', fuente: 'C:187-188,405,426-430' },
  'SIN:NUMERO_AUSENTE': { texto: 'El número del albarán no está en Farmatic', color: 'rojo', fuente: 'C:327-336' },
  'SIN:NO_DEMOSTRABLE': { texto: 'El número está en Farmatic, pero fuera de fecha o sin importe para comprobarlo', color: 'naranja', fuente: 'C:337-342' },
  'SIN:NUMERO_EXACTO_ECONOMIA_INCOMPATIBLE': { texto: 'Mismo número, pero el importe no cuadra', color: 'rojo', fuente: 'C:343-349' },
  'SIN:OTRO': { texto: 'Albarán no localizado en Farmatic', color: 'rojo', fuente: 'M:50; S:64' },
  // H5-3: estado_matching o clase_numero que no aparece en el código del motor: no se inventa significado.
  'ESTADO:SIN_DESCRIPCION': { texto: 'Estado del motor sin descripción (ver evidencia técnica)', color: 'gris', fuente: '—' },
} as const satisfies Record<string, EntradaCasado>;
export type ClaveCasado = keyof typeof DICCIONARIO_CASADO;

/** H5-2: tipo de relación (secundario). conciliacion_detalles.tipo_relacion: M:45-50; S:58-65. */
export const RELACION_CASADO = {
  UNO_A_UNO: { texto: '1 línea = 1 albarán', fuente: 'M:46; C:636' },
  UNO_A_VARIOS: { texto: '1 línea = 2 albaranes de la misma recepción (R17)', fuente: 'M:47; C:497-502,575-612; 24_cf_r17_recepcion.sql:22' },
  VARIOS_A_UNO: { texto: 'Varias líneas = 1 albarán', fuente: 'M:48; S:62' },
  MOVIMIENTO_NO_FARMATIC: { texto: 'Sin albarán', fuente: 'M:49; C:713,728' },
  SIN_COINCIDENCIA: { texto: 'Sin casar', fuente: 'M:50; C:624' },
  OTRO: { texto: 'Relación no reconocida', fuente: 'S:58-65' },
} as const;
export type ClaveRelacion = keyof typeof RELACION_CASADO;

/** ECO360 (R19, C:41-46, 164-167): la plataforma ECO360 de Farmatic (id 154) es siempre compra a Alliance (id 2). */
export const NOTA_ECO360 = { texto: 'Albarán de la plataforma ECO360: Farmatic lo registra como compra a Alliance', fuente: 'C:41-46,164-167' };

/** true si el albarán de Farmatic es de la plataforma ECO360 (id R9 154 o literal 6PLATAFECO360AH). */
export function esEco360(l: Pick<LineaConciliacion, 'farmatic_id_proveedor' | 'farmatic_proveedor'>): boolean {
  if (idProveedorR9(l.farmatic_id_proveedor) === '154') return true;
  return (l.farmatic_proveedor ?? '').toUpperCase().replace(/[^A-Z0-9]/g, '').includes('ECO360');
}

/** Clave principal ("cómo casó") de una línea de conciliación, tal como la dejó el motor. */
/**
 * H5-3: todos los valores de provenance.estado_matching que puede escribir el motor. Solo
 * src/facturas/runtime_supabase/conciliacion.py escribe esa clave (C:588 R17, C:629 sin coincidencia, C:648 1 a 1),
 * siempre con ResultadoBusquedaAlbaran.estado. Movimientos, cargos y ajustes no la llevan (C:716-734).
 */
export const ESTADOS_MATCHING = {
  MATCH_UNICO: { texto: 'Un único albarán de Farmatic cumple los criterios del motor', fuente: 'C:367-373' },
  EXACTO_ECONOMICO: { texto: 'Hefame: mismo número e importe compatible', fuente: 'C:327-349,370' },
  MATCH_R17: { texto: 'Pareja de la misma recepción que suma el importe (R17)', fuente: 'C:497-525,564-568,588' },
  SIN_COINCIDENCIA: { texto: DICCIONARIO_CASADO['SIN:SIN_COINCIDENCIA'].texto, fuente: 'C:374-375' },
  AMBIGUO: { texto: DICCIONARIO_CASADO['SIN:AMBIGUO'].texto, fuente: 'C:361-363,375' },
  AMBIGUO_R17: { texto: DICCIONARIO_CASADO['SIN:AMBIGUO_R17'].texto, fuente: 'C:557-558' },
  CONFLICTO_R17: { texto: DICCIONARIO_CASADO['SIN:CONFLICTO_R17'].texto, fuente: 'C:561-562' },
  ALBARAN_YA_CONCILIADO: { texto: DICCIONARIO_CASADO['SIN:ALBARAN_YA_CONCILIADO'].texto, fuente: 'C:421-425' },
  NUMERO_PROVEEDOR_DISTINTO: { texto: DICCIONARIO_CASADO['SIN:NUMERO_PROVEEDOR_DISTINTO'].texto, fuente: 'C:426-430' },
  NUMERO_AUSENTE: { texto: DICCIONARIO_CASADO['SIN:NUMERO_AUSENTE'].texto, fuente: 'C:332-336' },
  NO_DEMOSTRABLE: { texto: DICCIONARIO_CASADO['SIN:NO_DEMOSTRABLE'].texto, fuente: 'C:337-342' },
  NUMERO_EXACTO_ECONOMIA_INCOMPATIBLE: { texto: DICCIONARIO_CASADO['SIN:NUMERO_EXACTO_ECONOMIA_INCOMPATIBLE'].texto, fuente: 'C:343-349' },
  // H5-5: versión anterior del motor (fuente commit:fichero:línea).
  EXACTO: { texto: 'Versión anterior del motor: un único albarán de Farmatic, dado por número coincidente', fuente: FUENTE_EXACTO, version_anterior: true },
  ECONOMICO_UNICO: { texto: 'Versión anterior del motor: un único albarán de Farmatic por importe, sin número idéntico', fuente: FUENTE_ECONOMICO_UNICO, version_anterior: true },
} as const;
/** Estados con los que la línea queda casada (el resto, sin casar). EXACTO/ECONOMICO_UNICO: MATCH_UNICO antiguo. */
const ESTADOS_CASADOS = ['MATCH_UNICO', 'EXACTO_ECONOMICO', 'MATCH_R17', ...ESTADOS_VERSION_ANTERIOR];
/** clase_numero que puede escribir el motor (C:117,170-207). */
const CLASES_NUMERO = ['EXACTA', 'LETRA_FINAL', 'FINAL_DOCUMENTAL', 'INTERNO', 'PROVEEDOR', 'SIN_PATRON', 'NO_DISPONIBLE', 'DIFERENTE'];

/** true si el valor de estado_matching / clase_numero no aparece en el código del motor. */
export function estadoSinDescripcion(l: Pick<LineaConciliacion, 'estado_matching' | 'clase_numero'>): boolean {
  return (l.estado_matching !== null && !Object.hasOwn(ESTADOS_MATCHING, l.estado_matching))
    || (l.clase_numero !== null && !CLASES_NUMERO.includes(l.clase_numero));
}

export function claveCasado(l: Pick<LineaConciliacion, 'tipo_relacion' | 'estado_matching' | 'clase_numero' | 'coincidencia_numero' | 'sentido_documental'>): ClaveCasado {
  if (l.tipo_relacion === 'MOVIMIENTO_NO_FARMATIC') {
    if (l.sentido_documental === null) return 'MOVIMIENTO:SIN_SENTIDO';
    return l.sentido_documental === 'ABONO' ? 'MOVIMIENTO:ABONO' : 'MOVIMIENTO';
  }
  // H5-3: un valor que el código no escribe nunca recibe un texto inventado.
  if (estadoSinDescripcion(l)) return 'ESTADO:SIN_DESCRIPCION';
  if (l.tipo_relacion === 'SIN_COINCIDENCIA' || !Object.hasOwn(RELACION_CASADO, l.tipo_relacion)
    || (l.estado_matching !== null && !ESTADOS_CASADOS.includes(l.estado_matching))) {
    const k = `SIN:${l.estado_matching ?? ''}`;
    return (Object.hasOwn(DICCIONARIO_CASADO, k) ? k : 'SIN:OTRO') as ClaveCasado;
  }
  // H5-5: estado de la versión anterior del motor (no guardaba clase_numero): su propio texto.
  if (l.estado_matching === 'EXACTO' || l.estado_matching === 'ECONOMICO_UNICO') return `ANTERIOR:${l.estado_matching}`;
  // Casado (1 a 1, R17 o varios a 1): la forma del número es el dato principal.
  const clase = l.clase_numero ?? (l.coincidencia_numero === 'EXACTA' ? 'EXACTA' : null);
  if (l.estado_matching === 'EXACTO_ECONOMICO' && (clase === null || clase === 'EXACTA')) return 'HEFAME:EXACTO_ECONOMICO';
  const k = `NUMERO:${clase ?? ''}`;
  return (Object.hasOwn(DICCIONARIO_CASADO, k) ? k : 'NUMERO:OTRO') as ClaveCasado;
}

/** Texto llano del estado del motor (secundario en las líneas casadas); null si no hay o no está en el código. */
export function textoEstadoMatching(v: string | null): string | null {
  return v !== null && Object.hasOwn(ESTADOS_MATCHING, v) ? ESTADOS_MATCHING[v as keyof typeof ESTADOS_MATCHING].texto : null;
}

export function claveRelacion(l: Pick<LineaConciliacion, 'tipo_relacion'>): ClaveRelacion {
  return (Object.hasOwn(RELACION_CASADO, l.tipo_relacion) ? l.tipo_relacion : 'OTRO') as ClaveRelacion;
}

export interface Casado extends EntradaCasado { clave: ClaveCasado; relacion: ClaveRelacion; relacion_texto: string; notas: string[] }

export function tipoCasado(l: LineaConciliacion): Casado {
  const clave = claveCasado(l);
  const relacion = claveRelacion(l);
  const e: EntradaCasado = DICCIONARIO_CASADO[clave];
  return { clave, ...e, relacion, relacion_texto: RELACION_CASADO[relacion].texto, notas: esEco360(l) ? [NOTA_ECO360.texto] : [] };
}

// ---------------------------------------------------------------------------
// H5-2: bases de los importes de la línea (nunca se recalcula IVA ni diferencia)
// ---------------------------------------------------------------------------

/** Identidad del proveedor como el motor (conciliacion.py:124-141); vive en proveedor_comercial.ts desde H5-8. */
export { canonicalizarProveedor };

/**
 * Base de facturas_albaranes_extraidos.importe_total, que es lo que compara el motor (repositorios.py:405,453):
 *  - CON_IVA: total del albarán con IVA y recargo (multifactura.py:242; alliance.py:811), la misma base que el PUC/PVP
 *    de Farmatic con que se compara (conciliacion.py:218-228) y que importe_aplicado;
 *  - BASE_NETA: Hefame (mismo criterio de proveedor que el motor, conciliacion.py:287): el total del albarán es la
 *    base neta sin IVA (hefame.py:155-161) y el motor la convierte a bruto solo en memoria (hefame_economia.py:27-29,
 *    conciliacion.py:312); ese bruto no se guarda, así que la web no tiene importe del PDF en la base de Farmatic.
 */
export type BaseAlbaran = 'CON_IVA' | 'BASE_NETA';
export function baseAlbaran(proveedorFactura: string | null): BaseAlbaran {
  return canonicalizarProveedor(proveedorFactura) === 'HEFAMEMERCANCIA' ? 'BASE_NETA' : 'CON_IVA';
}

/** Qué valor de Farmatic aplicó el motor (importe_aplicado = PUC o PVP, conciliacion.py:220-228; R17 siempre PUC). Solo compara. */
export function origenAplicado(l: Pick<LineaConciliacion, 'importe_aplicado' | 'importe_puc' | 'importe_pvp'>): 'PUC' | 'PVP' | null {
  const a = l.importe_aplicado;
  if (a === null) return null;
  const igual = (x: Importe) => x !== null && Math.abs(Math.abs(a) - Math.abs(x)) < 0.00005;
  if (igual(l.importe_puc)) return 'PUC';
  if (igual(l.importe_pvp)) return 'PVP';
  return null;
}

/** Línea del PDF con sus albaranes de Farmatic (R17 agrupa dos detalles bajo la misma línea documental). */
export interface GrupoLinea {
  clave: string;
  documental: {
    numero: string | null; fecha: string | null; sentido: string | null; concepto: string | null;
    /** facturas_albaranes_extraidos.importe_total (lo que compara el motor; base según baseAlbaran). */
    importe_total: Importe;
    /** facturas_albaranes_extraidos.importe_base (base sin IVA; no se compara). */
    importe_base: Importe;
  };
  detalles: LineaConciliacion[];
}

export function agruparLineas(lineas: LineaConciliacion[]): GrupoLinea[] {
  const out: GrupoLinea[] = [];
  const porOrigen = new Map<string, GrupoLinea>();
  for (const l of [...lineas].sort((a, b) => (a.orden ?? 0) - (b.orden ?? 0))) {
    const origen = l.tipo_relacion === 'UNO_A_VARIOS' && l.factura_albaran_extraido_id ? `alb:${l.factura_albaran_extraido_id}` : null;
    const previo = origen ? porOrigen.get(origen) : undefined;
    if (previo) { previo.detalles.push(l); continue; }
    const g: GrupoLinea = {
      clave: origen ?? l.detalle_id,
      documental: { numero: l.numero_albaran_documental, fecha: l.fecha_albaran_documental, sentido: l.sentido_documental,
        concepto: l.concepto_movimiento, importe_total: l.albaran_importe_total, importe_base: l.albaran_importe_base },
      detalles: [l],
    };
    if (origen) porOrigen.set(origen, g);
    out.push(g);
  }
  return out;
}

// ---------------------------------------------------------------------------
// Avisos principales del detalle (arriba, en lenguaje llano)
// ---------------------------------------------------------------------------

export interface AvisoDetalle { clave: string; texto: string; detalle: string | null; color: Color; codigo: string | null }

const EUR = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', useGrouping: 'always', minimumFractionDigits: 2, maximumFractionDigits: 4 });
const eur = (v: Importe) => (v === null ? null : EUR.format(v));
const plural = (n: number, uno: string, varios: string) => `${n} ${n === 1 ? uno : varios}`;

/**
 * Avisos de arriba del detalle: conciliación (diferencia, revisión, no evaluable), albaranes sin casar agrupados por
 * motivo, datos que faltan y las incidencias abiertas ERROR o de posible duplicado. Los avisos AVISO restantes y las
 * INFO quedan en el desplegable Incidencias. Diferencia y tolerancia: las del motor, tal cual.
 */
// ---------------------------------------------------------------------------
// H5-7: estado por línea de la conciliación (migración 30, cf_detalles_por_linea; espejo en
// conciliacion.py:695-730). La web no recalcula: muestra importe_documental, importe_farmatic, diferencia y estado.
// ---------------------------------------------------------------------------

export interface EntradaEstadoLinea { texto: string; color: Color }
/** NO_EVALUABLE con importe de Farmatic: el PDF no trae importe para esa línea (30_cf_detalle_por_linea.sql:25,63,66). */
export const ESTADO_LINEA = {
  COINCIDE: { texto: 'Coincide', color: 'verde' },
  DIFERENCIA: { texto: 'Diferencia', color: 'rojo' },
  NO_EVALUABLE: { texto: 'Sin contraparte en Farmatic', color: 'gris' },
  NO_EVALUABLE_SIN_PDF: { texto: 'Sin importe del PDF para comparar', color: 'gris' },
  OTRO: { texto: 'Estado de línea no reconocido', color: 'gris' },
} as const satisfies Record<string, EntradaEstadoLinea>;
export type ClaveEstadoLinea = keyof typeof ESTADO_LINEA;

export function claveEstadoLinea(l: Pick<LineaConciliacion, 'estado_linea' | 'importe_farmatic'>): ClaveEstadoLinea {
  if (l.estado_linea === 'COINCIDE' || l.estado_linea === 'DIFERENCIA') return l.estado_linea;
  if (l.estado_linea === 'NO_EVALUABLE') return l.importe_farmatic === null ? 'NO_EVALUABLE' : 'NO_EVALUABLE_SIN_PDF';
  return 'OTRO';
}

/**
 * H5-7 (decisión de Pío): Hefame. La diferencia por línea resta la base neta del PDF (hefame.py:155-161) al importe de
 * Farmatic con IVA (conciliacion.py:639-648; 30_cf_detalle_por_linea.sql:51-53,63-65). Se muestra tal cual, con este aviso.
 */
export const TEXTO_HEFAME_BASES = 'El motor compara la base neta del PDF (sin IVA) con el importe de Farmatic (con IVA): la diferencia incluye el IVA y el recargo';

/** Líneas del PDF (no movimientos) en DIFERENCIA; una línea R17 (dos detalles) cuenta una vez. */
export function lineasConDiferencia(ls: readonly LineaConciliacion[]): { total: number; sinCasar: number } {
  const vistas = new Map<string, boolean>();
  for (const l of ls) {
    if (l.tipo_relacion === 'MOVIMIENTO_NO_FARMATIC' || l.estado_linea !== 'DIFERENCIA') continue;
    vistas.set(l.factura_albaran_extraido_id ?? l.detalle_id, l.tipo_relacion === 'SIN_COINCIDENCIA');
  }
  return { total: vistas.size, sinCasar: [...vistas.values()].filter(Boolean).length };
}

export function avisosFactura(d: FacturaDetalleDTO): AvisoDetalle[] {
  const out: AvisoDetalle[] = [];
  const f = d.factura;
  const c = f.conciliacion;
  if (f.estado_conciliacion_cf === 'REVISION_CONCILIACION') {
    out.push({ clave: 'revision-conciliacion', color: 'naranja', codigo: c?.resultado ?? null,
      texto: 'Se han agotado los intentos de conciliar la factura con sus albaranes',
      detalle: c && c.diferencia !== null ? `Diferencia según el motor: ${eur(c.diferencia)} · tolerancia ${eur(c.tolerancia) ?? 'sin dato'}` : null });
  } else if (c?.resultado === 'DIFERENCIA') {
    out.push({ clave: 'diferencia', color: 'rojo', codigo: 'DIFERENCIA',
      texto: `La factura no cuadra con sus albaranes: diferencia de ${eur(c.diferencia) ?? 'importe desconocido'}`,
      detalle: `Tolerancia del motor (R11): ${eur(c.tolerancia) ?? 'sin dato'}` });
  } else if (c?.resultado === 'NO_EVALUABLE') {
    out.push({ clave: 'no-evaluable', color: 'rojo', codigo: 'NO_EVALUABLE',
      texto: 'No se puede comprobar la factura contra sus albaranes', detalle: 'Diferencia no evaluable' });
  }
  // H5-7: líneas del PDF que el motor deja en DIFERENCIA (estado por línea, migración 30), contadas por línea del PDF.
  const conDif = lineasConDiferencia(d.lineas);
  if (conDif.total > 0) {
    const partes = [
      conDif.sinCasar > 0 ? `De ${conDif.total === 1 ? 'él' : 'ellos'}, ${conDif.sinCasar} sin casar en Farmatic` : null,
      // Hefame: misma advertencia que en Albaranes (la diferencia por línea del motor mezcla bases).
      baseAlbaran(f.proveedor_literal ?? f.proveedor) === 'BASE_NETA' ? TEXTO_HEFAME_BASES : null,
    ].filter((x) => x !== null);
    out.push({ clave: 'lineas-con-diferencia', color: 'rojo', codigo: null,
      texto: `${plural(conDif.total, 'albarán', 'albaranes')} con diferencia`, detalle: partes.length ? partes.join(' · ') : null });
  }
  // Albaranes sin casar, uno por motivo.
  const sin = new Map<ClaveCasado, number>();
  for (const l of d.lineas) {
    const k = claveCasado(l);
    if (k.startsWith('SIN:') || k === 'MOVIMIENTO:SIN_SENTIDO' || k === 'ESTADO:SIN_DESCRIPCION') sin.set(k, (sin.get(k) ?? 0) + 1);
  }
  for (const [k, n] of sin) {
    const e = DICCIONARIO_CASADO[k];
    const texto = k === 'SIN:SIN_COINCIDENCIA' || k === 'SIN:OTRO'
      ? `Falta localizar ${plural(n, 'albarán', 'albaranes')} en Farmatic`
      : n > 1 ? `${e.texto} (${n} líneas)` : e.texto;
    out.push({ clave: `lineas-${k}`, color: e.color, codigo: null, texto, detalle: null });
  }
  if (f.importe_total === null) {
    out.push({ clave: 'sin-total', color: 'naranja', codigo: null, texto: 'El total de la factura no consta en el documento', detalle: null });
  }
  if (f.estado_normalizacion === 'REQUIERE_REVISION') {
    out.push({ clave: 'normalizacion', color: 'naranja', codigo: 'REQUIERE_REVISION', texto: 'Faltan datos de la factura por revisar', detalle: null });
  }
  if (f.sentido === 'NO_DOCUMENTADO') {
    out.push({ clave: 'sentido', color: 'naranja', codigo: null, texto: TEXTO_VENCIMIENTO_SIN_SENTIDO, detalle: null });
  }
  const pendientes = d.vencimientos.filter((v) => v.importe === null).length;
  if (pendientes > 0) {
    out.push({ clave: 'vencimiento-pendiente', color: 'naranja', codigo: null,
      texto: pendientes === 1 ? 'Un vencimiento tiene el importe pendiente' : `${pendientes} vencimientos tienen el importe pendiente`, detalle: null });
  }
  const vistas = new Set<string>();
  for (const i of d.incidencias) {
    if (i.estado !== 'ABIERTA' || vistas.has(i.codigo)) continue;
    if (i.codigo === 'POSIBLE_DUPLICADO') {
      out.push({ clave: `inc-${i.codigo}`, color: 'naranja', codigo: i.codigo, texto: TEXTO_INCIDENCIA.POSIBLE_DUPLICADO, detalle: null });
      vistas.add(i.codigo);
    } else if (i.severidad === 'ERROR' || i.bloqueante) {
      // H4d-3: las incidencias de sentido nunca van en rojo, aunque sean ERROR.
      out.push({ clave: `inc-${i.codigo}`, color: CODIGOS_SENTIDO.includes(i.codigo) ? 'naranja' : 'rojo', codigo: i.codigo,
        texto: textoIncidencia(i), detalle: i.bloqueante ? 'Bloqueante' : null });
      vistas.add(i.codigo);
    }
  }
  const orden: Record<Color, number> = { rojo: 0, naranja: 1, azul: 2, gris: 3, verde: 4 };
  return out.map((a, n) => ({ a, n })).sort((x, y) => orden[x.a.color] - orden[y.a.color] || x.n - y.n).map((x) => x.a);
}

// ---------------------------------------------------------------------------
// Historial (historial_facturas.evento) en texto llano
// ---------------------------------------------------------------------------

/** Evento → texto. Fuente: el INSERT de cada evento en sql/migrations. Sin entrada: se muestra el código. */
export const TEXTO_EVENTO: Readonly<Record<string, string>> = {
  NORMALIZACION_CLAIM: 'Empieza la lectura del PDF', // 16_cf_worker_manual_one_shot.sql:74
  INVENTARIO_MULTIFACTURA: 'PDF con varias facturas: inventario de facturas', // 15_cf_multifactura.sql:176
  DOCUMENTO_NORMALIZADO_PERSISTIDO: 'Factura leída y guardada', // 12_cf_views_rls_rpc.sql:558
  NORMALIZACION_ERROR: 'La lectura del PDF ha fallado', // 12_cf_views_rls_rpc.sql:615
  NORMALIZACION_REPLAY_IDEMPOTENTE: 'Lectura repetida sin cambios', // 17_cf_replay_y_fallos_no_bloqueantes.sql:112
  CONCILIACION_CLAIM: 'Empieza la conciliación con Farmatic', // 18_cf_conciliacion_manual_atomica.sql:125
  CONCILIACION_PERSISTIDA: 'Conciliación guardada', // 18_cf_conciliacion_manual_atomica.sql:349
  CONCILIACION_REPLAY_IDEMPOTENTE: 'Conciliación repetida sin cambios', // 18_cf_conciliacion_manual_atomica.sql:263
  CONCILIACION_ERROR: 'La conciliación ha fallado', // 18_cf_conciliacion_manual_atomica.sql:431
  FACTURA_ENRIQUECIDA: 'Datos de la factura completados', // 20_cf_alliance_tolerancia_enriquecimiento.sql:317
  FACTURA_VALIDADA_PIO: 'Validada por Pío', // 12_cf_views_rls_rpc.sql:668
  FACTURA_DESVALIDADA: 'Se deshizo la validación de Pío', // 12_cf_views_rls_rpc.sql:727
};

export function textoEvento(evento: string): string {
  return Object.hasOwn(TEXTO_EVENTO, evento) ? TEXTO_EVENTO[evento] : evento;
}

// ---------------------------------------------------------------------------
// Listado: insignias
// ---------------------------------------------------------------------------

export interface Insignia { clave: 'posible-duplicado' | 'abono' | 'sentido-no-documentado'; texto: string; color: Color }

/**
 * Insignias del listado. "abono" y "sentido no documentado": sentido de la regla de Pío (H4c-2, solo
 * datos_extraidos.tipo_documento.valor). "posible duplicado": incidencia POSIBLE_DUPLICADO abierta.
 */
export function insigniasFactura(f: Pick<FacturaResumen, 'sentido'> & { posible_duplicado: boolean }): Insignia[] {
  const out: Insignia[] = [];
  if (f.posible_duplicado) out.push({ clave: 'posible-duplicado', texto: 'posible duplicado', color: 'naranja' });
  if (f.sentido === 'ABONO') out.push({ clave: 'abono', texto: 'abono', color: 'azul' });
  if (f.sentido === 'NO_DOCUMENTADO') out.push({ clave: 'sentido-no-documentado', texto: 'sentido no documentado', color: 'naranja' });
  return out;
}

// ---------------------------------------------------------------------------
// H5-2: búsqueda por importe del listado
// ---------------------------------------------------------------------------

/**
 * Consulta de importe: se ignoran puntos, espacios y "€"; la coma es el separador decimal.
 *  - sin coma ("5000", "5.000") → de 5.000,00 a 5.000,99;
 *  - con coma ("5000,1") → exacto 5.000,10 (máximo 2 decimales).
 * Devuelve el rango en céntimos (por valor absoluto: un abono de −45,30 € responde a "45,30") o null si no es un importe.
 */
export function rangoImporteBuscado(q: string): { desde: number; hasta: number } | null {
  const t = q.replace(/[.\s €]/g, '');
  const m = /^-?(\d+)(?:,(\d{1,2}))?$/.exec(t);
  if (!m) return null;
  const enteros = Number(m[1]);
  if (!Number.isSafeInteger(enteros * 100)) return null;
  if (m[2] === undefined) return { desde: enteros * 100, hasta: enteros * 100 + 99 };
  const c = enteros * 100 + Number(m[2].padEnd(2, '0'));
  return { desde: c, hasta: c };
}

/** true si algún importe (total de factura o de un vencimiento) cae en el rango buscado. Los null no coinciden nunca. */
export function coincideImporte(q: string, importes: Importe[]): boolean {
  const r = rangoImporteBuscado(q);
  if (r === null) return false;
  return importes.some((v) => {
    if (v === null) return false;
    const c = Math.round(Math.abs(v) * 100);
    return c >= r.desde && c <= r.hasta;
  });
}
