/**
 * Contrato de datos de la web ControlFarmacias, fase 1 (H3b). Solo lectura.
 *
 * Una función y un DTO por bloque de pantalla:
 *   inicio, facturas, facturaDetalle, conciliacionBandeja, vencimientos,
 *   cashflowSemanas, proveedores (+ mapa documentos proveedor×estado), configuracion.
 * Alertas (en inicio y en la bandeja de conciliación): albarán facturado no en Farmatic,
 * posible duplicado en Farmatic y correcciones aprobadas de albaranes.
 *
 * Reglas (web/CLAUDE.md):
 *   - Solo objetos de la lista cerrada de pruebas/auditoria_2bn/DISENO.md (rol cf_lectura).
 *     Nunca v_dashboard_diario (convierte null en 0). Ninguna función de BD.
 *   - Solo PIO: todas las consultas filtran farmacia = $1 = 'PIO' y exigen que PIO esté en
 *     cf_configuracion.farmacias_habilitadas (si no, no devuelven filas: falla cerrado).
 *   - Importe ausente = null, nunca 0. Las sumas solo suman importes conocidos y cuentan aparte
 *     los desconocidos. Diferencias y tolerancia: las del motor (conciliaciones, R11); no se
 *     recalcula ningún umbral.
 *   - Tres estados separados: normalización / conciliación / revisión Pío.
 *   - Estado de pago: sin datos bancarios (fase 1).
 *   - Datos extraídos: facturas.datos_extraidos; nunca normalizacion_ejecuciones.resultado_json.
 *
 * Este módulo no conecta a nada: define consultas y construye DTO a partir de filas. El
 * adaptador REAL ejecuta las consultas; el generador de fixtures pasa filas ficticias por los
 * mismos constructores.
 *
 * Solo sintaxis TypeScript borrable (Node la ejecuta sin compilar).
 */

export const FARMACIA = 'PIO';

// ---------------------------------------------------------------------------
// Tipos comunes
// ---------------------------------------------------------------------------

/** Importe en euros. null = desconocido (nunca 0). */
export type Importe = number | null;
export type Color = 'verde' | 'azul' | 'naranja' | 'rojo' | 'gris';
export type Fila = Record<string, unknown>;

export interface EstadoPago {
  estado: 'SIN_DATOS_BANCARIOS';
  texto: 'sin datos bancarios';
  color: 'gris';
}
export const PAGO_SIN_DATOS: EstadoPago = { estado: 'SIN_DATOS_BANCARIOS', texto: 'sin datos bancarios', color: 'gris' };

interface Cabecera {
  farmacia: string;
  generado_at: string;
}

/** Conciliación vigente (es_actual) tal como la dejó el motor. */
export interface ConciliacionVigente {
  conciliacion_id: string;
  intento: number | null;
  disparador: string | null;
  estado: string | null;
  resultado: string | null;
  importe_factura: Importe;
  importe_explicado: Importe;
  diferencia: Importe;
  tolerancia: Importe;
  /** provenance.tolerancia_regla (R11) literal del motor. */
  tolerancia_regla: unknown;
  finalizado_at: string | null;
}

export interface FacturaResumen {
  factura_id: string;
  documento_id: string;
  archivo_nombre: string | null;
  pagina_inicio: number | null;
  pagina_fin: number | null;
  tipo_documento: string | null;
  categoria: string | null;
  numero_factura: string | null;
  fecha_factura: string | null;
  moneda: string | null;
  proveedor_id: string | null;
  proveedor_codigo: string | null;
  proveedor: string | null;
  proveedor_literal: string | null;
  /** facturas.proveedor_cif literal (agrupación de proveedores: ver grupoProveedor). */
  proveedor_cif: string | null;
  base_imponible_total: Importe;
  iva_total: Importe;
  recargo_equivalencia_total: Importe;
  importe_total: Importe;
  cuadre_fiscal_correcto: boolean | null;
  diferencia_cuadre: Importe;
  estado_normalizacion: string;
  estado_conciliacion_cf: string;
  estado_revision: string;
  /** Literal de BD; la UI muestra siempre `pago` (sin datos bancarios). */
  estado_pago_bd: string | null;
  requiere_conciliacion_albaranes: boolean | null;
  conciliacion_intentos: number | null;
  conciliacion_intentos_fallo: number | null;
  conciliacion_ultima_clase_fallo: string | null;
  conciliacion_proximo_at: string | null;
  conciliacion: ConciliacionVigente | null;
  uso_luna: boolean | null;
  coste_luna: Importe;
  incidencias_abiertas: number;
  incidencias_bloqueantes: number;
  updated_at: string | null;
}

export interface DocumentoPdf {
  documento_id: string;
  archivo_nombre: string | null;
  archivo_hash: string | null;
  fecha_importacion: string | null;
  estado_lectura: string;
  estado_persistencia: string | null;
  intentos_fallo_normalizacion: number | null;
  ultima_clase_fallo: string | null;
  ultimo_error_codigo: string | null;
  proximo_reintento_at: string | null;
  numero_paginas: number | null;
  cantidad_documentos_detectados: number | null;
  facturas: number;
  incidencias_documento_abiertas: number;
  /** Proveedor por sus facturas o, si no tiene, por su última ejecución de normalización. */
  proveedor_id: string | null;
  proveedor: string | null;
  /** CIF y literal de la primera factura del PDF que los tenga (agrupación por CIF). */
  proveedor_cif: string | null;
  proveedor_literal: string | null;
}

export interface LineaConciliacion {
  factura_id: string;
  conciliacion_id: string;
  intento: number | null;
  detalle_id: string;
  orden: number | null;
  tipo_relacion: string;
  estado_linea: string;
  estado_matching: string | null;
  coincidencia_numero: string | null;
  clase_numero: string | null;
  coincidencia_numero_literal: boolean | null;
  factura_albaran_extraido_id: string | null;
  factura_movimiento_id: string | null;
  numero_albaran_documental: string | null;
  fecha_albaran_documental: string | null;
  sentido_documental: string | null;
  importe_documental: Importe;
  albaran_farmacia: string | null;
  albaran_id_contador: number | null;
  numero_albaran_farmatic: string | null;
  fecha_albaran_farmatic: string | null;
  farmatic_id_proveedor: string | null;
  importe_puc: Importe;
  importe_pvp: Importe;
  importe_farmatic: Importe;
  importe_aplicado: Importe;
  diferencia: Importe;
}

export interface Incidencia {
  incidencia_id: string;
  documento_id: string | null;
  factura_id: string | null;
  numero_factura: string | null;
  archivo_nombre: string | null;
  codigo: string;
  categoria: string | null;
  severidad: string | null;
  bloqueante: boolean;
  estado: string;
  mensaje_usuario: string | null;
  detalle_tecnico: unknown;
  created_at: string | null;
  resuelta_at: string | null;
  resuelta_por: string | null;
}

export interface EventoHistorial {
  evento_id: number;
  documento_id: string | null;
  factura_id: string | null;
  evento: string;
  origen: string | null;
  actor: string | null;
  estado_anterior: unknown;
  estado_nuevo: unknown;
  detalle: unknown;
  created_at: string | null;
}

export interface Vencimiento {
  vencimiento_id: string;
  factura_id: string;
  numero_factura: string | null;
  tipo_documento: string | null;
  proveedor: string | null;
  orden: number | null;
  fecha_vencimiento: string | null;
  importe: Importe;
  importe_conocido: boolean;
  literal: string | null;
  importe_factura: Importe;
  vencimientos_factura: number;
  estado_normalizacion: string;
  estado_conciliacion_cf: string;
  estado_revision: string;
  pago: EstadoPago;
}

export type TipoAlerta = 'ALBARAN_FACTURADO_NO_EN_FARMATIC' | 'POSIBLE_DUPLICADO_FARMATIC' | 'CORRECCION_APROBADA';

/**
 * VALIDADA: regla validada por Pío; se muestra en Inicio y en la bandeja.
 * PENDIENTE_VALIDAR: reservado para reglas futuras aún no validadas (solo bandeja). Hoy ninguna alerta lo usa:
 * el posible duplicado en Farmatic quedó validado por Pío (regla B, H3d).
 */
export type ValidacionAlerta = 'VALIDADA' | 'PENDIENTE_VALIDAR';

export interface Alerta {
  tipo: TipoAlerta;
  validacion: ValidacionAlerta;
  color: Color;
  titulo: string;
  id_contadores: number[];
  numero_albaran: string | null;
  proveedor: string | null;
  factura_id: string | null;
  numero_factura: string | null;
  fecha: string | null;
  /** Datos literales de la fila (sin recalcular nada). */
  detalle: Record<string, unknown>;
}

export interface ItemAtencion {
  tipo: string;
  color: Color;
  /** Texto en lenguaje llano. */
  texto: string;
  referencia: string;
  /** Código técnico de origen (estado, resultado o código de incidencia), para mostrar en pequeño. */
  codigo: string | null;
  /** Solo en avisos de conciliación: diferencia tal como la dejó el motor (null = no evaluable). */
  diferencia_motor?: Importe;
  factura_id: string | null;
  documento_id: string | null;
}

// ---------------------------------------------------------------------------
// DTO por bloque
// ---------------------------------------------------------------------------

export interface InicioDTO extends Cabecera {
  documentos: {
    total: number;
    pendientes_procesar: number;
    /** Contador rojo "Documentos con defecto" (decisión 1A): estado_lectura ERROR + REVISION. */
    con_defecto: number;
    /** Contador gris "Sin automatizar" (decisión 1A): estado_lectura PROVEEDOR_NO_SOPORTADO. */
    sin_automatizar: number;
    por_estado: Record<string, number>;
  };
  facturas: { total: number; sin_importe: number; importe_total_conocido: Importe };
  requieren_revision: number;
  normalizacion: Record<string, number>;
  conciliacion: Record<string, number>;
  revision: Record<string, number>;
  cobertura: { importe_facturado_conocido: Importe; importe_conciliado_conocido: Importe; facturas_sin_importe: number };
  incidencias: { abiertas: number; bloqueantes: number };
  proximos_vencimientos: Vencimiento[];
  atencion: ItemAtencion[];
  alertas: Alerta[];
  luna_mes: { ejecuciones: number; coste: Importe };
  pago: EstadoPago;
}

export interface FacturaListado extends FacturaResumen {
  /** Clave del grupo de proveedor (OpcionFiltroProveedor.clave). */
  proveedor_grupo: string;
}

export interface FacturasDTO extends Cabecera {
  facturas: FacturaListado[];
  /** Filtro de proveedor: grupos por CIF (y "sin CIF" por nombre canónico R9). */
  proveedores_filtro: OpcionFiltroProveedor[];
  /** PDF que no han generado ninguna factura (pendientes, error, proveedor no soportado...). */
  documentos_sin_factura: DocumentoPdf[];
  pago: EstadoPago;
}

export interface FacturaDetalleDTO extends Cabecera {
  factura: FacturaResumen;
  documento: {
    documento_id: string;
    archivo_nombre: string | null;
    archivo_ruta: string | null;
    archivo_hash: string | null;
    numero_paginas: number | null;
    estado_lectura: string | null;
    estado_persistencia: string | null;
    fecha_importacion: string | null;
  };
  proveedor: {
    proveedor_cif: string | null;
    id_proveedor_albaranes: string | null;
    extractor_codigo: string | null;
    nivel_confianza: string | null;
  };
  normalizacion: {
    ejecucion_id: string | null;
    disparador: string | null;
    estado: string | null;
    extractor_usado: string | null;
    normalizador_version: string | null;
    uso_ocr: boolean | null;
    uso_luna: boolean | null;
    luna_modelo: string | null;
    luna_campos: string[];
    tokens_total: number | null;
    coste_luna: Importe;
    finalizado_at: string | null;
  };
  /** facturas.datos_extraidos (jsonb literal). */
  datos_extraidos: unknown;
  provenance: unknown;
  lineas: LineaConciliacion[];
  impuestos: Fila[];
  vencimientos: Vencimiento[];
  albaranes_extraidos: Fila[];
  movimientos: Fila[];
  ajustes: Fila[];
  incidencias: Incidencia[];
  historial: EventoHistorial[];
  pago: EstadoPago;
}

export interface FacturaBandeja extends FacturaResumen {
  prioridad: number;
  color: Color;
  lineas: LineaConciliacion[];
  lineas_por_estado: Record<string, number>;
}

export interface ConciliacionBandejaDTO extends Cabecera {
  resumen: Record<string, number>;
  facturas: FacturaBandeja[];
  alertas: Alerta[];
}

export interface VencimientosDTO extends Cabecera {
  vencimientos: Vencimiento[];
  totales: {
    vencimientos: number;
    sin_importe: number;
    sin_fecha: number;
    importe_cargos_conocido: Importe;
    importe_abonos_conocido: Importe;
  };
  pago: EstadoPago;
}

export interface SemanaCashflow {
  /** Lunes de la semana (ISO). null = vencimientos sin fecha. */
  semana: string | null;
  semana_fin: string | null;
  vencimientos: number;
  vencimientos_sin_importe: number;
  importe_cargos_conocido: Importe;
  importe_abonos_conocido: Importe;
  vencimientos_sin_validar: number;
}

export interface CashflowSemanasDTO extends Cabecera {
  semanas: SemanaCashflow[];
  pago: EstadoPago;
}

/**
 * Grupo de proveedor (H4b; el catálogo `proveedores` está vacío en producción y no se usa para agrupar):
 *  - con CIF: facturas.proveedor_cif normalizado (mayúsculas, sin espacios, puntos ni guiones);
 *  - sin CIF: nombre canónico R9 del literal (mayúsculas, sin acentos ni signos), marcado sin_cif;
 *  - sin CIF ni literal: un único grupo "Proveedor sin identificar" (sin_cif).
 * Nunca proveedor_id.
 */
export interface GrupoProveedor {
  /** 'cif:<CIF>' | 'nombre:<CANONICO>' | 'sin_identificar'. */
  clave: string;
  cif: string | null;
  sin_cif: boolean;
}

export interface Proveedor extends GrupoProveedor {
  /** Literal más frecuente del grupo (empate: el primero en orden alfabético). */
  etiqueta: string;
  /** Resto de literales del grupo. */
  alias: string[];
  facturas: number;
  norm_revision: number;
  conc_pendiente: number;
  conc_ok: number;
  conc_revision: number;
  rev_pendiente: number;
  facturas_sin_importe: number;
  importe_total_conocido: Importe;
  ultima_fecha_factura: string | null;
}

export interface ProveedoresDTO extends Cabecera {
  proveedores: Proveedor[];
  mapa_documentos: {
    estados: string[];
    filas: { clave: string; proveedor: string; sin_cif: boolean; por_estado: Record<string, number>; total: number }[];
  };
}

/** Opción del filtro de proveedor de Facturas: mismo criterio que la pantalla Proveedores. */
export interface OpcionFiltroProveedor {
  clave: string;
  etiqueta: string;
  sin_cif: boolean;
  facturas: number;
}

export interface ConfiguracionDTO extends Cabecera {
  farmacia_activa: string;
  farmacias_habilitadas: string[];
  normalizacion_automatica: boolean | null;
  conciliacion_automatica: boolean | null;
  luna_habilitada: boolean | null;
  tolerancia_conciliacion: Importe;
  conciliacion_tolerancia_suelo: Importe;
  conciliacion_tolerancia_por_albaran: Importe;
  conciliacion_tolerancia_tope: Importe;
  normalizacion_max_intentos: number | null;
  normalizacion_backoff: string[];
  conciliacion_max_intentos: number | null;
  conciliacion_backoff: string[];
  updated_at: string | null;
}

/** Interfaz que implementan los adaptadores FIXTURES y REAL. */
export interface Contrato {
  inicio(): Promise<InicioDTO>;
  facturas(): Promise<FacturasDTO>;
  /** null si la factura no existe o no es de PIO. */
  facturaDetalle(id: string): Promise<FacturaDetalleDTO | null>;
  conciliacionBandeja(): Promise<ConciliacionBandejaDTO>;
  vencimientos(): Promise<VencimientosDTO>;
  cashflowSemanas(): Promise<CashflowSemanasDTO>;
  proveedores(): Promise<ProveedoresDTO>;
  configuracion(): Promise<ConfiguracionDTO>;
}

export type Bloque = keyof Contrato;
export const BLOQUES: Bloque[] = [
  'inicio', 'facturas', 'facturaDetalle', 'conciliacionBandeja',
  'vencimientos', 'cashflowSemanas', 'proveedores', 'configuracion',
];

// ---------------------------------------------------------------------------
// Consultas (parámetros: $1 = farmacia; $2 = id de factura uuid donde aplica)
// ---------------------------------------------------------------------------

/** Lista cerrada de objetos legibles por cf_lectura (DISENO 2BN). */
export const OBJETOS_PERMITIDOS = [
  'documentos_facturas', 'facturas', 'facturas_vencimientos', 'facturas_impuestos',
  'facturas_albaranes_extraidos', 'facturas_ajustes', 'facturas_movimientos', 'facturas_incidencias',
  'historial_facturas', 'normalizacion_ejecuciones', 'conciliaciones', 'conciliacion_detalles',
  'conciliacion_albaranes_reservados', 'albaranes', 'albaranes_cambios', 'albaranes_aprobaciones',
  'albaranes_aprobaciones_aplicadas', 'proveedores', 'proveedores_alias', 'cf_configuracion',
  'v_facturas_listado', 'v_dashboard_diario', 'v_vencimientos_calendario', 'v_proveedores_estado',
] as const;
/** Permitidos por el rol pero vetados por la web. */
export const OBJETOS_VETADOS = ['v_dashboard_diario'] as const;

export interface Consulta {
  objetos: string[];
  /** true si usa $2 (id de factura). */
  porFactura: boolean;
  sql: string;
}

/** PIO habilitada en cf_configuracion; si no, cross join vacío: ninguna fila. */
const HAB = `hab as (
    select 1 from public.cf_configuracion cfg
     where cfg.id and $1::text = any(cfg.farmacias_habilitadas)
)`;

const SQL_FACTURA_COLUMNAS = `
    f.id as factura_id, f.documento_id, d.archivo_nombre, f.pagina_inicio, f.pagina_fin,
    f.tipo_documento, f.categoria, f.numero_factura, f.fecha_factura, f.moneda, f.proveedor_id,
    p.codigo as proveedor_codigo,
    coalesce(p.nombre, f.proveedor_literal, f.proveedor_nombre) as proveedor,
    f.proveedor_literal, f.proveedor_cif,
    f.base_imponible_total, f.iva_total, f.recargo_equivalencia_total, f.importe_total,
    f.cuadre_fiscal_correcto, f.diferencia_cuadre,
    f.estado_normalizacion, f.estado_conciliacion_cf, f.estado_revision, f.estado_pago,
    f.requiere_conciliacion_albaranes, f.conciliacion_intentos, f.conciliacion_intentos_fallo,
    f.conciliacion_ultima_clase_fallo, f.conciliacion_proximo_at,
    ne.uso_luna, ne.coste_luna,
    c.id as conciliacion_id, c.intento as conciliacion_intento, c.disparador as conciliacion_disparador,
    c.estado as conciliacion_estado, c.resultado as conciliacion_resultado,
    c.importe_factura as conciliacion_importe_factura, c.importe_explicado as conciliacion_importe_explicado,
    c.diferencia as conciliacion_diferencia, c.tolerancia as conciliacion_tolerancia,
    c.provenance -> 'tolerancia_regla' as conciliacion_tolerancia_regla,
    c.finalizado_at as conciliacion_finalizada_at,
    (select count(*) from public.facturas_incidencias fi
      where fi.factura_id = f.id and fi.estado = 'ABIERTA') as incidencias_abiertas,
    (select count(*) from public.facturas_incidencias fi
      where fi.factura_id = f.id and fi.estado = 'ABIERTA' and fi.bloqueante) as incidencias_bloqueantes,
    f.updated_at`;

const SQL_FACTURA_JOINS = `
from public.facturas f
cross join hab
join public.documentos_facturas d on d.id = f.documento_id
left join public.proveedores p on p.id = f.proveedor_id
left join public.normalizacion_ejecuciones ne on ne.id = f.normalizacion_ejecucion_id
left join public.conciliaciones c on c.factura_id = f.id and c.es_actual`;

const OBJ_FACTURA = ['facturas', 'documentos_facturas', 'proveedores', 'normalizacion_ejecuciones',
  'conciliaciones', 'facturas_incidencias', 'cf_configuracion'];

function sqlLineas(porFactura: boolean): string {
  return `with ${HAB}
select
    c.factura_id, c.id as conciliacion_id, c.intento,
    cd.id as detalle_id, cd.orden, cd.tipo_relacion, cd.estado as estado_linea,
    cd.provenance ->> 'estado_matching' as estado_matching,
    cd.provenance ->> 'coincidencia_numero' as coincidencia_numero,
    cd.provenance ->> 'clase_numero' as clase_numero,
    cd.coincidencia_numero_literal,
    cd.factura_albaran_extraido_id, cd.factura_movimiento_id,
    coalesce(cd.numero_albaran_documental, fae.numero_albaran) as numero_albaran_documental,
    fae.fecha_albaran as fecha_albaran_documental,
    coalesce(fae.tipo_movimiento, fm.sentido) as sentido_documental,
    cd.importe_documental,
    cd.albaran_farmacia, cd.albaran_id_contador,
    coalesce(cd.numero_albaran_farmatic, a.numero_albaran) as numero_albaran_farmatic,
    a.fecha as fecha_albaran_farmatic, a.id_proveedor as farmatic_id_proveedor,
    a.importe_puc, a.importe_pvp,
    cd.importe_farmatic, cd.importe_aplicado, cd.diferencia
from public.conciliacion_detalles cd
join public.conciliaciones c on c.id = cd.conciliacion_id and c.es_actual
join public.facturas f on f.id = c.factura_id
cross join hab
left join public.facturas_albaranes_extraidos fae on fae.id = cd.factura_albaran_extraido_id
left join public.facturas_movimientos fm on fm.id = cd.factura_movimiento_id
left join public.albaranes a on a.farmacia = cd.albaran_farmacia and a.id_contador = cd.albaran_id_contador
where f.farmacia = $1${porFactura ? ' and f.id = $2::uuid' : ''}
order by c.factura_id, cd.orden`;
}
const OBJ_LINEAS = ['conciliacion_detalles', 'conciliaciones', 'facturas', 'facturas_albaranes_extraidos',
  'facturas_movimientos', 'albaranes', 'cf_configuracion'];

function sqlVencimientos(porFactura: boolean): string {
  return `with ${HAB}
select
    v.id as vencimiento_id, v.factura_id, f.numero_factura, f.tipo_documento,
    coalesce(p.nombre, f.proveedor_literal, f.proveedor_nombre) as proveedor,
    v.orden, v.fecha_vencimiento, v.importe, v.literal,
    f.importe_total as importe_factura,
    count(*) over (partition by v.factura_id) as vencimientos_factura,
    f.estado_normalizacion, f.estado_conciliacion_cf, f.estado_revision
from public.facturas_vencimientos v
join public.facturas f on f.id = v.factura_id
cross join hab
left join public.proveedores p on p.id = f.proveedor_id
where f.farmacia = $1${porFactura ? ' and f.id = $2::uuid' : ''}
order by v.fecha_vencimiento nulls last, v.factura_id, v.orden`;
}
const OBJ_VENCIMIENTOS = ['facturas_vencimientos', 'facturas', 'proveedores', 'cf_configuracion'];

function sqlIncidencias(porFactura: boolean): string {
  return `with ${HAB}
select
    fi.id as incidencia_id, fi.documento_id, fi.factura_id, f.numero_factura,
    coalesce(d.archivo_nombre, df.archivo_nombre) as archivo_nombre,
    fi.codigo, fi.categoria, fi.severidad, fi.bloqueante, fi.estado,
    fi.mensaje_usuario, fi.detalle_tecnico, fi.created_at, fi.resuelta_at, fi.resuelta_por
from public.facturas_incidencias fi
cross join hab
left join public.facturas f on f.id = fi.factura_id
left join public.documentos_facturas df on df.id = f.documento_id
left join public.documentos_facturas d on d.id = fi.documento_id
where coalesce(f.farmacia, d.farmacia) = $1
${porFactura
    ? `  and (fi.factura_id = $2::uuid
       or fi.documento_id = (select f2.documento_id from public.facturas f2 where f2.id = $2::uuid))`
    : `  and fi.estado = 'ABIERTA'`}
order by fi.created_at desc, fi.id`;
}
const OBJ_INCIDENCIAS = ['facturas_incidencias', 'facturas', 'documentos_facturas', 'cf_configuracion'];

/** Literal del id de proveedor comparable (R9), en SQL plano: la función de BD no es ejecutable por cf_lectura. */
const SQL_ID_PROVEEDOR_R9 = `case
        when btrim(a.id_proveedor) ~ '^[0-9]+$' then coalesce(nullif(ltrim(btrim(a.id_proveedor), '0'), ''), '0')
        else nullif(btrim(a.id_proveedor), '')
    end`;

/** CIF comparable en SQL, igual que normalizarCif (mayúsculas, sin espacios, puntos ni guiones; vacío = null). */
function SQL_CIF_NORMALIZADO(col: string): string {
  return `nullif(upper(regexp_replace(coalesce(${col}, ''), '[[:space:].-]', '', 'g')), '')`;
}

export const CONSULTAS = {
  documentos: {
    objetos: ['documentos_facturas', 'facturas', 'facturas_incidencias', 'normalizacion_ejecuciones', 'proveedores', 'cf_configuracion'],
    porFactura: false,
    sql: `with ${HAB}
select
    d.id as documento_id, d.archivo_nombre, d.archivo_hash, d.fecha_importacion,
    d.estado_lectura, d.estado_persistencia, d.intentos_fallo_normalizacion, d.ultima_clase_fallo,
    d.ultimo_error_codigo, d.proximo_reintento_at, d.numero_paginas, d.cantidad_documentos_detectados,
    (select count(*) from public.facturas f where f.documento_id = d.id) as facturas,
    (select count(*) from public.facturas_incidencias fi
      where fi.documento_id = d.id and fi.estado = 'ABIERTA') as incidencias_documento_abiertas,
    prov.proveedor_id, p.nombre as proveedor,
    (select f.proveedor_cif from public.facturas f
      where f.documento_id = d.id and nullif(btrim(f.proveedor_cif), '') is not null
      order by f.pagina_inicio nulls last, f.id limit 1) as proveedor_cif,
    (select coalesce(f.proveedor_literal, f.proveedor_nombre) from public.facturas f
      where f.documento_id = d.id and nullif(btrim(coalesce(f.proveedor_literal, f.proveedor_nombre)), '') is not null
      order by f.pagina_inicio nulls last, f.id limit 1) as proveedor_literal
from public.documentos_facturas d
cross join hab
left join lateral (
    select coalesce(
        (select f.proveedor_id from public.facturas f
          where f.documento_id = d.id and f.proveedor_id is not null
          order by f.pagina_inicio nulls last, f.id limit 1),
        (select ne.proveedor_id from public.normalizacion_ejecuciones ne
          where ne.documento_id = d.id and ne.proveedor_id is not null
          order by ne.created_at desc, ne.id limit 1)
    ) as proveedor_id
) prov on true
left join public.proveedores p on p.id = prov.proveedor_id
where d.farmacia = $1
order by d.fecha_importacion desc nulls last, d.id`,
  },

  facturas: {
    objetos: OBJ_FACTURA,
    porFactura: false,
    sql: `with ${HAB}
select ${SQL_FACTURA_COLUMNAS}
${SQL_FACTURA_JOINS}
where f.farmacia = $1
order by f.fecha_factura desc nulls last, f.id`,
  },

  factura_cabecera: {
    objetos: OBJ_FACTURA,
    porFactura: true,
    sql: `with ${HAB}
select ${SQL_FACTURA_COLUMNAS},
    d.archivo_ruta, d.archivo_hash, d.numero_paginas, d.estado_lectura, d.estado_persistencia,
    d.fecha_importacion,
    f.id_proveedor_albaranes,
    p.extractor_codigo as proveedor_extractor_codigo, p.nivel_confianza as proveedor_nivel_confianza,
    ne.id as normalizacion_ejecucion_id, ne.disparador as normalizacion_disparador,
    ne.estado as normalizacion_ejecucion_estado, ne.extractor_usado, ne.normalizador_version,
    ne.uso_ocr, ne.luna_modelo, ne.luna_campos, ne.tokens_total,
    ne.finalizado_at as normalizacion_finalizada_at,
    f.provenance as factura_provenance,
    f.datos_extraidos
${SQL_FACTURA_JOINS}
where f.farmacia = $1 and f.id = $2::uuid`,
  },

  factura_lineas: { objetos: OBJ_LINEAS, porFactura: true, sql: sqlLineas(true) },

  factura_impuestos: {
    objetos: ['facturas_impuestos', 'facturas', 'cf_configuracion'],
    porFactura: true,
    sql: `with ${HAB}
select x.id, x.orden, x.concepto, x.base_imponible, x.tipo_iva, x.cuota_iva,
       x.tipo_recargo_equivalencia, x.cuota_recargo_equivalencia, x.total_tramo, x.literal
from public.facturas_impuestos x
join public.facturas f on f.id = x.factura_id
cross join hab
where f.farmacia = $1 and f.id = $2::uuid
order by x.orden, x.id`,
  },

  factura_vencimientos: { objetos: OBJ_VENCIMIENTOS, porFactura: true, sql: sqlVencimientos(true) },

  factura_albaranes_extraidos: {
    objetos: ['facturas_albaranes_extraidos', 'facturas', 'cf_configuracion'],
    porFactura: true,
    sql: `with ${HAB}
select x.id, x.orden, x.numero_albaran, x.fecha_albaran, x.tipo_movimiento,
       x.importe_base, x.importe_total, x.descripcion, x.literal
from public.facturas_albaranes_extraidos x
join public.facturas f on f.id = x.factura_id
cross join hab
where f.farmacia = $1 and f.id = $2::uuid
order by x.orden, x.id`,
  },

  factura_movimientos: {
    objetos: ['facturas_movimientos', 'facturas', 'cf_configuracion'],
    porFactura: true,
    sql: `with ${HAB}
select x.id, x.orden, x.categoria, x.descripcion_literal, x.sentido, x.base, x.iva,
       x.recargo_equivalencia, x.importe, x.independiente, x.conciliable_farmatic
from public.facturas_movimientos x
join public.facturas f on f.id = x.factura_id
cross join hab
where f.farmacia = $1 and f.id = $2::uuid
order by x.orden, x.id`,
  },

  factura_ajustes: {
    objetos: ['facturas_ajustes', 'facturas', 'cf_configuracion'],
    porFactura: true,
    sql: `with ${HAB}
select x.id, x.orden, x.tipo_ajuste, x.descripcion, x.importe, x.incluido_en_base,
       x.incluido_en_total, x.literal
from public.facturas_ajustes x
join public.facturas f on f.id = x.factura_id
cross join hab
where f.farmacia = $1 and f.id = $2::uuid
order by x.orden, x.id`,
  },

  factura_incidencias: { objetos: OBJ_INCIDENCIAS, porFactura: true, sql: sqlIncidencias(true) },

  factura_historial: {
    objetos: ['historial_facturas', 'facturas', 'cf_configuracion'],
    porFactura: true,
    sql: `with ${HAB},
fx as (select f.id, f.documento_id from public.facturas f cross join hab where f.farmacia = $1 and f.id = $2::uuid)
select h.id as evento_id, h.documento_id, h.factura_id, h.evento, h.origen, h.actor,
       h.estado_anterior, h.estado_nuevo, h.detalle, h.created_at
from public.historial_facturas h
join fx on h.factura_id = fx.id or (h.factura_id is null and h.documento_id = fx.documento_id)
order by h.created_at, h.id`,
  },

  lineas: { objetos: OBJ_LINEAS, porFactura: false, sql: sqlLineas(false) },

  incidencias_abiertas: { objetos: OBJ_INCIDENCIAS, porFactura: false, sql: sqlIncidencias(false) },

  vencimientos: { objetos: OBJ_VENCIMIENTOS, porFactura: false, sql: sqlVencimientos(false) },

  proveedores: {
    objetos: ['proveedores', 'proveedores_alias', 'cf_configuracion'],
    porFactura: false,
    sql: `with ${HAB}
select p.id, p.codigo, p.nombre, p.farmatic_id_proveedor, p.extractor_codigo, p.nivel_confianza, p.activo,
       coalesce((select array_agg(pa.alias order by pa.alias)
                   from public.proveedores_alias pa where pa.proveedor_id = p.id), '{}'::text[]) as alias
from public.proveedores p
cross join hab
order by p.nombre, p.id`,
  },

  configuracion: {
    objetos: ['cf_configuracion'],
    porFactura: false,
    sql: `with ${HAB}
select c.farmacias_habilitadas, c.normalizacion_automatica, c.conciliacion_automatica, c.luna_habilitada,
       c.tolerancia_conciliacion, c.conciliacion_tolerancia_suelo, c.conciliacion_tolerancia_por_albaran,
       c.conciliacion_tolerancia_tope, c.normalizacion_max_intentos,
       c.normalizacion_backoff::text[] as normalizacion_backoff,
       c.conciliacion_max_intentos,
       c.conciliacion_backoff::text[] as conciliacion_backoff,
       c.updated_at
from public.cf_configuracion c
cross join hab
where c.id`,
  },

  luna_mes: {
    objetos: ['normalizacion_ejecuciones', 'documentos_facturas', 'cf_configuracion'],
    porFactura: false,
    sql: `with ${HAB}
select count(*) filter (where ne.uso_luna) as ejecuciones_luna,
       sum(ne.coste_luna) filter (where ne.uso_luna) as coste_luna
from public.normalizacion_ejecuciones ne
join public.documentos_facturas d on d.id = ne.documento_id
cross join hab
where d.farmacia = $1 and ne.created_at >= date_trunc('month', now())`,
  },

  alertas_albaran_no_en_farmatic: {
    objetos: ['albaranes_cambios', 'conciliacion_albaranes_reservados', 'facturas', 'proveedores', 'albaranes', 'cf_configuracion'],
    porFactura: false,
    sql: `with ${HAB},
ult as (
    select distinct on (c.id_contador)
           c.id, c.farmacia, c.id_contador, c.valor_nuevo, c.motivo, c.detectado_at, c.origen
      from public.albaranes_cambios c
      cross join hab
     where c.farmacia = $1 and c.campo = 'presencia'
     order by c.id_contador, c.id desc
)
select ult.id as cambio_id, ult.id_contador, ult.motivo, ult.detectado_at, ult.origen,
       a.numero_albaran, a.id_proveedor, a.proveedor, a.fecha, a.importe_puc,
       r.factura_id, r.conciliacion_id, f.numero_factura,
       coalesce(p.nombre, f.proveedor_literal, f.proveedor_nombre) as proveedor_factura
from ult
join public.conciliacion_albaranes_reservados r
  on r.albaran_farmacia = ult.farmacia and r.albaran_id_contador = ult.id_contador
join public.facturas f on f.id = r.factura_id and f.farmacia = $1
left join public.proveedores p on p.id = f.proveedor_id
left join public.albaranes a on a.farmacia = ult.farmacia and a.id_contador = ult.id_contador
where ult.valor_nuevo = 'AUSENTE'
order by ult.detectado_at desc, ult.id_contador`,
  },

  /**
   * Candidatos a duplicado en Farmatic (regla B validada por Pío): mismo proveedor (R9) y mismo número
   * ignorando la letra final (08C66676 = 08C66676A). La tercera condición, mismo importe, la aplica
   * construirAlertas sobre `detalle` (gruposDuplicadoFarmatic), que además revalida las otras dos.
   * Sin proveedor comparable no hay "mismo proveedor": esos albaranes no son candidatos.
   */
  alertas_duplicado_farmatic: {
    objetos: ['albaranes', 'cf_configuracion'],
    porFactura: false,
    sql: `with ${HAB},
a as (
    select a.id_contador, a.numero_albaran, a.id_proveedor, a.proveedor, a.fecha, a.importe_puc,
           ${SQL_ID_PROVEEDOR_R9} as id_proveedor_comparable,
           regexp_replace(upper(btrim(a.numero_albaran)), '[A-Z]$', '') as numero_base
      from public.albaranes a
      cross join hab
     where a.farmacia = $1 and nullif(btrim(a.numero_albaran), '') is not null
)
select a.id_proveedor_comparable, a.numero_base,
       count(*) as albaranes,
       max(a.fecha) as fecha_max,
       json_agg(json_build_object(
           'id_contador', a.id_contador, 'numero_albaran', a.numero_albaran,
           'id_proveedor', a.id_proveedor, 'proveedor', a.proveedor,
           'fecha', a.fecha, 'importe_puc', a.importe_puc
       ) order by a.id_contador) as detalle
from a
where a.id_proveedor_comparable is not null
group by a.id_proveedor_comparable, a.numero_base
having count(*) > 1
order by max(a.fecha) desc nulls last, a.numero_base
limit 200`,
  },

  alertas_correcciones_aprobadas: {
    objetos: ['albaranes_aprobaciones', 'albaranes_aprobaciones_aplicadas', 'albaranes', 'cf_configuracion'],
    porFactura: false,
    sql: `with ${HAB}
select ap.id as aprobacion_id, ap.id_contador, ap.motivo, ap.cambio, ap.aprobado_por, ap.aprobado_at,
       ap.referencia, apl.aplicada_at, apl.valores_anteriores, apl.valores_nuevos,
       a.numero_albaran, a.proveedor, a.fecha
from public.albaranes_aprobaciones ap
cross join hab
left join public.albaranes_aprobaciones_aplicadas apl on apl.aprobacion_id = ap.id
left join public.albaranes a on a.farmacia = ap.farmacia and a.id_contador = ap.id_contador
where ap.farmacia = $1
order by ap.aprobado_at desc, ap.id desc
limit 100`,
  },
} satisfies Record<string, Consulta>;

export type NombreConsulta = keyof typeof CONSULTAS;
export type Filas = Partial<Record<NombreConsulta, Fila[]>>;

/**
 * Consultas exclusivas de check:real (no forman parte de ningún bloque). Solo devuelven recuentos o,
 * en `factura_reciente`, el id que el adaptador usa internamente para probar las consultas por factura
 * (nunca se imprime).
 */
export const CONSULTAS_CHECK = {
  /** Factura PIO más reciente (mismo orden que el listado de facturas). */
  factura_reciente: {
    objetos: ['facturas', 'cf_configuracion'],
    porFactura: false,
    sql: `with ${HAB}
select f.id as factura_id
from public.facturas f
cross join hab
where f.farmacia = $1
order by f.fecha_factura desc nulls last, f.id
limit 1`,
  },
  /** Diagnóstico del bloque proveedores: solo recuentos. */
  diagnostico_proveedores: {
    objetos: ['facturas', 'proveedores', 'cf_configuracion'],
    porFactura: false,
    sql: `with ${HAB}
select count(*) as facturas,
       count(*) filter (where f.proveedor_id is null) as facturas_sin_proveedor_id,
       count(distinct f.proveedor_id) as grupos_proveedor_id,
       count(distinct lower(btrim(coalesce(f.proveedor_literal, f.proveedor_nombre))))
           filter (where f.proveedor_id is null) as literales_distintos_sin_proveedor_id,
       (select count(*) from public.proveedores) as proveedores_catalogo,
       count(distinct ${SQL_CIF_NORMALIZADO('f.proveedor_cif')}) as cif_distintos,
       count(*) filter (where ${SQL_CIF_NORMALIZADO('f.proveedor_cif')} is null) as facturas_sin_cif
from public.facturas f
cross join hab
where f.farmacia = $1`,
  },
  /**
   * H4b, diagnóstico de vencimientos: solo recuentos. `nulls_por_grupo_cif` es la lista de recuentos de
   * vencimientos con importe null por grupo de CIF (de mayor a menor), sin CIF ni nombres.
   */
  diagnostico_vencimientos: {
    objetos: ['facturas_vencimientos', 'facturas', 'facturas_incidencias', 'cf_configuracion'],
    porFactura: false,
    sql: `with ${HAB},
v as (
    select v.importe, f.id as factura_id, ${SQL_CIF_NORMALIZADO('f.proveedor_cif')} as cif,
           exists (select 1 from public.facturas_incidencias fi
                    where fi.factura_id = f.id and fi.codigo = 'IMPORTE_VENCIMIENTO_NO_DOCUMENTADO') as con_incidencia
      from public.facturas_vencimientos v
      join public.facturas f on f.id = v.factura_id
      cross join hab
     where f.farmacia = $1
)
select count(*) as vencimientos,
       count(*) filter (where v.importe is null) as vencimientos_importe_null,
       count(*) filter (where v.importe is null and v.con_incidencia) as vencimientos_null_con_incidencia,
       count(*) filter (where v.importe is null and not v.con_incidencia) as vencimientos_null_sin_incidencia,
       count(distinct v.factura_id) filter (where v.con_incidencia) as facturas_con_incidencia,
       (select count(*) from public.facturas_incidencias fi
          join public.facturas f2 on f2.id = fi.factura_id
         where f2.farmacia = $1 and fi.codigo = 'IMPORTE_VENCIMIENTO_NO_DOCUMENTADO') as incidencias_importe_vencimiento,
       count(*) filter (where v.importe is null and v.cif is null) as vencimientos_null_sin_cif,
       (select coalesce(json_agg(g.n order by g.n desc), '[]'::json)
          from (select count(*) as n from v v2 where v2.importe is null and v2.cif is not null group by v2.cif) g) as nulls_por_grupo_cif
from v`,
  },
  /**
   * H4b, par 08C66676 / 08C66676A (regla B). Las filas no salen del adaptador: resumenPar08C66676 solo
   * devuelve sí/no, recuentos y nombres de columna.
   */
  diagnostico_par_08c66676: {
    objetos: ['albaranes', 'cf_configuracion'],
    porFactura: false,
    sql: `with ${HAB}
select a.*, upper(btrim(a.numero_albaran)) as numero_par_diagnostico
from public.albaranes a
cross join hab
where a.farmacia = $1 and upper(btrim(a.numero_albaran)) in ('08C66676', '08C66676A')
order by a.id_contador`,
  },
} satisfies Record<string, Consulta>;

export type ValorDiagnostico = number | boolean | number[] | string[];

/** Duplicados en Farmatic: candidatos (mismo proveedor R9 + número sin letra final) y tras el filtro de importe. */
export function resumenDuplicados(filasCandidatos: Fila[]): Record<string, ValorDiagnostico> {
  let albaranes = 0;
  let grupos = 0;
  for (const r of filasCandidatos) {
    const det = (Array.isArray(r.detalle) ? (r.detalle as Fila[]) : []).map((d) => ({
      id_contador: entero(d.id_contador), numero_albaran: texto(d.numero_albaran), id_proveedor: texto(d.id_proveedor),
      proveedor: null, fecha: null, importe_puc: importe(d.importe_puc),
    }));
    albaranes += det.length;
    grupos += gruposDuplicadoFarmatic(det).length;
  }
  return {
    candidatos: filasCandidatos.length,
    albaranes_candidatos: albaranes,
    tras_filtro_importe: grupos,
    limite_200_alcanzado: filasCandidatos.length >= 200,
  };
}

/**
 * Par 08C66676 / 08C66676A. `columnasImporte`: columnas numéricas de albaranes (las da el adaptador por el tipo).
 * Solo sí/no, recuentos y nombres de columna.
 */
export function resumenPar08C66676(filasPar: Fila[], columnasImporte: string[]): Record<string, ValorDiagnostico> {
  const a = filasPar.filter((r) => r.numero_par_diagnostico === '08C66676');
  const b = filasPar.filter((r) => r.numero_par_diagnostico === '08C66676A');
  const out: Record<string, ValorDiagnostico> = {
    filas_08C66676: a.length,
    filas_08C66676A: b.length,
    existen_ambos: a.length > 0 && b.length > 0,
  };
  if (a.length !== 1 || b.length !== 1) return { ...out, comparable_uno_a_uno: false };
  const [x, y] = [a[0], b[0]];
  const prov = (v: unknown) => idProveedorR9(texto(v));
  const igual = (c: string) => {
    const [p, q] = [importe(x[c]), importe(y[c])];
    return p !== null && q !== null && p === q;
  };
  return {
    ...out,
    comparable_uno_a_uno: true,
    mismo_proveedor_r9: prov(x.id_proveedor) !== null && prov(x.id_proveedor) === prov(y.id_proveedor),
    mismo_importe_puc: igual('importe_puc'),
    otras_columnas_importe_coinciden: columnasImporte.filter((c) => c !== 'importe_puc' && igual(c)).sort(),
  };
}
export type NombreConsultaCheck = keyof typeof CONSULTAS_CHECK;

const ALERTAS: NombreConsulta[] = ['alertas_albaran_no_en_farmatic', 'alertas_duplicado_farmatic', 'alertas_correcciones_aprobadas'];

/** Consultas que necesita cada bloque. */
export const CONSULTAS_POR_BLOQUE: Record<Bloque, NombreConsulta[]> = {
  inicio: ['documentos', 'facturas', 'vencimientos', 'incidencias_abiertas', 'luna_mes', ...ALERTAS],
  facturas: ['facturas', 'documentos'],
  facturaDetalle: ['factura_cabecera', 'factura_lineas', 'factura_impuestos', 'factura_vencimientos',
    'factura_albaranes_extraidos', 'factura_movimientos', 'factura_ajustes', 'factura_incidencias', 'factura_historial'],
  conciliacionBandeja: ['facturas', 'lineas', ...ALERTAS],
  vencimientos: ['vencimientos'],
  cashflowSemanas: ['vencimientos'],
  // H4b: agrupación por CIF; el catálogo `proveedores` no interviene (vacío en producción).
  proveedores: ['facturas', 'documentos'],
  configuracion: ['configuracion'],
};

/** Objetos de BD que usa cada bloque (para el informe y para check_fixtures). */
export function objetosPorBloque(bloque: Bloque): string[] {
  const s = new Set<string>();
  for (const n of CONSULTAS_POR_BLOQUE[bloque]) for (const o of CONSULTAS[n].objetos) s.add(o);
  return [...s].sort();
}

// ---------------------------------------------------------------------------
// Conversión de valores (pg devuelve numeric/int8/fechas como texto en el adaptador REAL)
// ---------------------------------------------------------------------------

export function importe(v: unknown): Importe {
  if (v === null || v === undefined) return null;
  const n = typeof v === 'number' ? v : Number(v);
  if (!Number.isFinite(n)) throw new Error(`IMPORTE_NO_NUMERICO: ${String(v)}`);
  return n;
}
function entero(v: unknown): number | null {
  if (v === null || v === undefined) return null;
  const n = typeof v === 'number' ? v : Number(v);
  if (!Number.isSafeInteger(n)) throw new Error(`ENTERO_NO_VALIDO: ${String(v)}`);
  return n;
}
/** Contadores (count(*)): nunca null. */
function cuenta(v: unknown): number {
  return entero(v) ?? 0;
}
function texto(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  if (v instanceof Date) return v.toISOString();
  return String(v);
}
function textoReq(v: unknown, campo: string): string {
  const t = texto(v);
  if (t === null) throw new Error(`CAMPO_OBLIGATORIO_NULO: ${campo}`);
  return t;
}
function booleano(v: unknown): boolean | null {
  if (v === null || v === undefined) return null;
  return v === true || v === 't' || v === 'true';
}
function listaTexto(v: unknown): string[] {
  if (v === null || v === undefined) return [];
  if (Array.isArray(v)) return v.map((x) => String(x));
  throw new Error(`LISTA_NO_VALIDA: ${String(v)}`);
}

/** Suma solo importes conocidos. null si no hay ninguno; cuenta aparte los desconocidos. */
export function sumaConocida(valores: Importe[]): { suma: Importe; desconocidos: number } {
  let suma: number | null = null;
  let desconocidos = 0;
  for (const v of valores) {
    if (v === null) desconocidos += 1;
    else suma = (suma ?? 0) + v;
  }
  return { suma: suma === null ? null : Math.round(suma * 10000) / 10000, desconocidos };
}

function contar(valores: string[], claves: readonly string[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const c of claves) out[c] = 0;
  for (const v of valores) out[v] = (out[v] ?? 0) + 1;
  return out;
}

// ---------------------------------------------------------------------------
// Estados conocidos (CHECK de las migraciones 08, 15, 17 y 18)
// ---------------------------------------------------------------------------

export const ESTADOS_LECTURA = ['PENDIENTE', 'PROCESANDO', 'EXTRAIDA', 'NORMALIZANDO', 'NORMALIZADA', 'REVISION', 'ERROR', 'PROVEEDOR_NO_SOPORTADO'] as const;
export const ESTADOS_NORMALIZACION = ['PENDIENTE', 'NORMALIZANDO', 'NORMALIZADA', 'REQUIERE_REVISION'] as const;
export const ESTADOS_CONCILIACION = ['PENDIENTE_CONCILIAR', 'CONCILIADA', 'REVISION_CONCILIACION'] as const;
export const ESTADOS_REVISION = ['NO_REQUERIDA', 'PENDIENTE_REVISION_PIO', 'VALIDADA_PIO'] as const;
export const ESTADOS_LINEA = ['COINCIDE', 'DIFERENCIA', 'NO_EVALUABLE'] as const;
const LECTURA_PENDIENTE = ['PENDIENTE', 'PROCESANDO'];
const LECTURA_CON_DEFECTO = ['ERROR', 'REVISION'];
const LECTURA_SIN_AUTOMATIZAR = ['PROVEEDOR_NO_SOPORTADO'];

// ---------------------------------------------------------------------------
// Constructores fila -> DTO
// ---------------------------------------------------------------------------

function filas(f: Filas, n: NombreConsulta): Fila[] {
  const r = f[n];
  if (!r) throw new Error(`CONSULTA_SIN_FILAS_ENTREGADAS: ${n}`);
  return r;
}

export function aFactura(r: Fila): FacturaResumen {
  const conciliacionId = texto(r.conciliacion_id);
  return {
    factura_id: textoReq(r.factura_id, 'factura_id'),
    documento_id: textoReq(r.documento_id, 'documento_id'),
    archivo_nombre: texto(r.archivo_nombre),
    pagina_inicio: entero(r.pagina_inicio),
    pagina_fin: entero(r.pagina_fin),
    tipo_documento: texto(r.tipo_documento),
    categoria: texto(r.categoria),
    numero_factura: texto(r.numero_factura),
    fecha_factura: texto(r.fecha_factura),
    moneda: texto(r.moneda),
    proveedor_id: texto(r.proveedor_id),
    proveedor_codigo: texto(r.proveedor_codigo),
    proveedor: texto(r.proveedor),
    proveedor_literal: texto(r.proveedor_literal),
    proveedor_cif: texto(r.proveedor_cif),
    base_imponible_total: importe(r.base_imponible_total),
    iva_total: importe(r.iva_total),
    recargo_equivalencia_total: importe(r.recargo_equivalencia_total),
    importe_total: importe(r.importe_total),
    cuadre_fiscal_correcto: booleano(r.cuadre_fiscal_correcto),
    diferencia_cuadre: importe(r.diferencia_cuadre),
    estado_normalizacion: textoReq(r.estado_normalizacion, 'estado_normalizacion'),
    estado_conciliacion_cf: textoReq(r.estado_conciliacion_cf, 'estado_conciliacion_cf'),
    estado_revision: textoReq(r.estado_revision, 'estado_revision'),
    estado_pago_bd: texto(r.estado_pago),
    requiere_conciliacion_albaranes: booleano(r.requiere_conciliacion_albaranes),
    conciliacion_intentos: entero(r.conciliacion_intentos),
    conciliacion_intentos_fallo: entero(r.conciliacion_intentos_fallo),
    conciliacion_ultima_clase_fallo: texto(r.conciliacion_ultima_clase_fallo),
    conciliacion_proximo_at: texto(r.conciliacion_proximo_at),
    conciliacion: conciliacionId === null ? null : {
      conciliacion_id: conciliacionId,
      intento: entero(r.conciliacion_intento),
      disparador: texto(r.conciliacion_disparador),
      estado: texto(r.conciliacion_estado),
      resultado: texto(r.conciliacion_resultado),
      importe_factura: importe(r.conciliacion_importe_factura),
      importe_explicado: importe(r.conciliacion_importe_explicado),
      diferencia: importe(r.conciliacion_diferencia),
      tolerancia: importe(r.conciliacion_tolerancia),
      tolerancia_regla: r.conciliacion_tolerancia_regla ?? null,
      finalizado_at: texto(r.conciliacion_finalizada_at),
    },
    uso_luna: booleano(r.uso_luna),
    coste_luna: importe(r.coste_luna),
    incidencias_abiertas: cuenta(r.incidencias_abiertas),
    incidencias_bloqueantes: cuenta(r.incidencias_bloqueantes),
    updated_at: texto(r.updated_at),
  };
}

export function aDocumento(r: Fila): DocumentoPdf {
  return {
    documento_id: textoReq(r.documento_id, 'documento_id'),
    archivo_nombre: texto(r.archivo_nombre),
    archivo_hash: texto(r.archivo_hash),
    fecha_importacion: texto(r.fecha_importacion),
    estado_lectura: textoReq(r.estado_lectura, 'estado_lectura'),
    estado_persistencia: texto(r.estado_persistencia),
    intentos_fallo_normalizacion: entero(r.intentos_fallo_normalizacion),
    ultima_clase_fallo: texto(r.ultima_clase_fallo),
    ultimo_error_codigo: texto(r.ultimo_error_codigo),
    proximo_reintento_at: texto(r.proximo_reintento_at),
    numero_paginas: entero(r.numero_paginas),
    cantidad_documentos_detectados: entero(r.cantidad_documentos_detectados),
    facturas: cuenta(r.facturas),
    incidencias_documento_abiertas: cuenta(r.incidencias_documento_abiertas),
    proveedor_id: texto(r.proveedor_id),
    proveedor: texto(r.proveedor),
    proveedor_cif: texto(r.proveedor_cif),
    proveedor_literal: texto(r.proveedor_literal),
  };
}

export function aLinea(r: Fila): LineaConciliacion {
  return {
    factura_id: textoReq(r.factura_id, 'factura_id'),
    conciliacion_id: textoReq(r.conciliacion_id, 'conciliacion_id'),
    intento: entero(r.intento),
    detalle_id: textoReq(r.detalle_id, 'detalle_id'),
    orden: entero(r.orden),
    tipo_relacion: textoReq(r.tipo_relacion, 'tipo_relacion'),
    estado_linea: textoReq(r.estado_linea, 'estado_linea'),
    estado_matching: texto(r.estado_matching),
    coincidencia_numero: texto(r.coincidencia_numero),
    clase_numero: texto(r.clase_numero),
    coincidencia_numero_literal: booleano(r.coincidencia_numero_literal),
    factura_albaran_extraido_id: texto(r.factura_albaran_extraido_id),
    factura_movimiento_id: texto(r.factura_movimiento_id),
    numero_albaran_documental: texto(r.numero_albaran_documental),
    fecha_albaran_documental: texto(r.fecha_albaran_documental),
    sentido_documental: texto(r.sentido_documental),
    importe_documental: importe(r.importe_documental),
    albaran_farmacia: texto(r.albaran_farmacia),
    albaran_id_contador: entero(r.albaran_id_contador),
    numero_albaran_farmatic: texto(r.numero_albaran_farmatic),
    fecha_albaran_farmatic: texto(r.fecha_albaran_farmatic),
    farmatic_id_proveedor: texto(r.farmatic_id_proveedor),
    importe_puc: importe(r.importe_puc),
    importe_pvp: importe(r.importe_pvp),
    importe_farmatic: importe(r.importe_farmatic),
    importe_aplicado: importe(r.importe_aplicado),
    diferencia: importe(r.diferencia),
  };
}

export function aIncidencia(r: Fila): Incidencia {
  return {
    incidencia_id: textoReq(r.incidencia_id, 'incidencia_id'),
    documento_id: texto(r.documento_id),
    factura_id: texto(r.factura_id),
    numero_factura: texto(r.numero_factura),
    archivo_nombre: texto(r.archivo_nombre),
    codigo: textoReq(r.codigo, 'codigo'),
    categoria: texto(r.categoria),
    severidad: texto(r.severidad),
    bloqueante: booleano(r.bloqueante) ?? false,
    estado: textoReq(r.estado, 'estado'),
    mensaje_usuario: texto(r.mensaje_usuario),
    detalle_tecnico: r.detalle_tecnico ?? null,
    created_at: texto(r.created_at),
    resuelta_at: texto(r.resuelta_at),
    resuelta_por: texto(r.resuelta_por),
  };
}

export function aEvento(r: Fila): EventoHistorial {
  return {
    evento_id: entero(r.evento_id) ?? 0,
    documento_id: texto(r.documento_id),
    factura_id: texto(r.factura_id),
    evento: textoReq(r.evento, 'evento'),
    origen: texto(r.origen),
    actor: texto(r.actor),
    estado_anterior: r.estado_anterior ?? null,
    estado_nuevo: r.estado_nuevo ?? null,
    detalle: r.detalle ?? null,
    created_at: texto(r.created_at),
  };
}

export function aVencimiento(r: Fila): Vencimiento {
  const imp = importe(r.importe);
  return {
    vencimiento_id: textoReq(r.vencimiento_id, 'vencimiento_id'),
    factura_id: textoReq(r.factura_id, 'factura_id'),
    numero_factura: texto(r.numero_factura),
    tipo_documento: texto(r.tipo_documento),
    proveedor: texto(r.proveedor),
    orden: entero(r.orden),
    fecha_vencimiento: texto(r.fecha_vencimiento),
    importe: imp,
    importe_conocido: imp !== null,
    literal: texto(r.literal),
    importe_factura: importe(r.importe_factura),
    vencimientos_factura: cuenta(r.vencimientos_factura),
    estado_normalizacion: textoReq(r.estado_normalizacion, 'estado_normalizacion'),
    estado_conciliacion_cf: textoReq(r.estado_conciliacion_cf, 'estado_conciliacion_cf'),
    estado_revision: textoReq(r.estado_revision, 'estado_revision'),
    pago: PAGO_SIN_DATOS,
  };
}

/** Filas genéricas (impuestos, albaranes extraídos, movimientos, ajustes): importes como Importe. */
function aFilaImportes(r: Fila, camposImporte: string[]): Fila {
  const out: Fila = {};
  for (const [k, v] of Object.entries(r)) out[k] = camposImporte.includes(k) ? importe(v) : (v instanceof Date ? v.toISOString() : v);
  return out;
}

/** Número de albarán sin la letra final (regla B): 08C66676A → 08C66676. Igual que el SQL del contrato. */
export function numeroAlbaranBase(n: string): string {
  return n.trim().toUpperCase().replace(/[A-Z]$/, '');
}

/** Id de proveedor comparable (R9), igual que SQL_ID_PROVEEDOR_R9. */
export function idProveedorR9(v: string | null): string | null {
  if (v === null) return null;
  const t = v.trim();
  if (/^[0-9]+$/.test(t)) return t.replace(/^0+/, '') || '0';
  return t === '' ? null : t;
}

export interface AlbaranFarmatic {
  id_contador: number | null;
  numero_albaran: string | null;
  id_proveedor: string | null;
  proveedor: string | null;
  fecha: string | null;
  importe_puc: Importe;
}

/**
 * Regla B (validada por Pío): duplicado en Farmatic = mismo proveedor (R9) + mismo número ignorando la letra
 * final + mismo importe (importe_puc). Importe desconocido (null) no cumple "mismo importe". Devuelve los
 * grupos de 2 o más albaranes que cumplen las tres condiciones.
 */
export function gruposDuplicadoFarmatic(albaranes: AlbaranFarmatic[]): AlbaranFarmatic[][] {
  const grupos = new Map<string, AlbaranFarmatic[]>();
  for (const a of albaranes) {
    const prov = idProveedorR9(a.id_proveedor);
    if (prov === null || a.numero_albaran === null || a.importe_puc === null) continue;
    const base = numeroAlbaranBase(a.numero_albaran);
    if (base === '') continue;
    const k = JSON.stringify([prov, base, a.importe_puc]);
    grupos.set(k, [...(grupos.get(k) ?? []), a]);
  }
  return [...grupos.values()].filter((g) => g.length > 1);
}

// ---------------------------------------------------------------------------
// Proveedores agrupados por CIF (H4b)
// ---------------------------------------------------------------------------

/** CIF comparable: mayúsculas, sin espacios, puntos ni guiones. null si vacío. Igual que SQL_CIF_NORMALIZADO. */
export function normalizarCif(v: string | null): string | null {
  if (v === null) return null;
  const t = v.toUpperCase().replace(/[\s.-]/g, '');
  return t === '' ? null : t;
}

/** Nombre canónico R9 de un literal de proveedor: mayúsculas, sin acentos ni signos ni espacios. null si vacío. */
export function nombreCanonico(v: string | null): string | null {
  if (v === null) return null;
  // NFD + quitar marcas diacríticas (\p{M}): "España" → "ESPANA".
  const t = v.normalize('NFD').replace(/\p{M}/gu, '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  return t === '' ? null : t;
}

/** Grupo de un proveedor a partir de su CIF y su literal. Nunca proveedor_id. */
export function grupoProveedor(cif: string | null, literal: string | null): GrupoProveedor {
  const c = normalizarCif(cif);
  if (c !== null) return { clave: `cif:${c}`, cif: c, sin_cif: false };
  const n = nombreCanonico(literal);
  if (n !== null) return { clave: `nombre:${n}`, cif: null, sin_cif: true };
  return { clave: 'sin_identificar', cif: null, sin_cif: true };
}

const SIN_IDENTIFICAR = 'Proveedor sin identificar';

/** Literal mostrado de una factura: el impreso; si falta, el nombre resuelto. */
function literalFactura(fa: FacturaResumen): string | null {
  const t = (fa.proveedor_literal ?? fa.proveedor)?.trim();
  return t ? t : null;
}

/** Etiqueta = literal más frecuente (empate: alfabético); resto = alias. */
export function etiquetaYAlias(literales: (string | null)[]): { etiqueta: string; alias: string[] } {
  const n = new Map<string, number>();
  for (const l of literales) if (l !== null) n.set(l, (n.get(l) ?? 0) + 1);
  const orden = [...n.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  if (orden.length === 0) return { etiqueta: SIN_IDENTIFICAR, alias: [] };
  return { etiqueta: orden[0][0], alias: orden.slice(1).map(([l]) => l).sort((a, b) => a.localeCompare(b)) };
}

interface GrupoFacturas { grupo: GrupoProveedor; etiqueta: string; alias: string[]; facturas: FacturaResumen[] }

/** Agrupa facturas por CIF (o nombre canónico si no tienen). Orden: con CIF primero, luego por etiqueta. */
export function agruparFacturasPorProveedor(facturas: FacturaResumen[]): GrupoFacturas[] {
  const m = new Map<string, { grupo: GrupoProveedor; facturas: FacturaResumen[] }>();
  for (const fa of facturas) {
    const g = grupoProveedor(fa.proveedor_cif, literalFactura(fa));
    const e = m.get(g.clave) ?? { grupo: g, facturas: [] };
    e.facturas.push(fa);
    m.set(g.clave, e);
  }
  return [...m.values()]
    .map((e) => ({ ...e, ...etiquetaYAlias(e.facturas.map(literalFactura)) }))
    .sort((a, b) => Number(a.grupo.sin_cif) - Number(b.grupo.sin_cif) || a.etiqueta.localeCompare(b.etiqueta) || a.grupo.clave.localeCompare(b.grupo.clave));
}

// ---------------------------------------------------------------------------
// Incidencias en lenguaje llano (H4b)
// ---------------------------------------------------------------------------

/** Código de incidencia → texto llano. Sin entrada: se usa mensaje_usuario. */
export const TEXTO_INCIDENCIA: Readonly<Record<string, string>> = {
  MONEDA_NO_DOCUMENTADA: 'La factura no indica la moneda',
  IMPORTE_VENCIMIENTO_NO_DOCUMENTADO: 'Un vencimiento de la factura no indica su importe',
  SENTIDO_NO_DOCUMENTADO: 'La factura no indica si un movimiento es un cargo o un abono',
  POSIBLE_DUPLICADO: 'Puede que esta factura esté repetida en otro PDF',
  SEGUNDA_LECTURA_FALLIDA: 'No se ha podido leer el PDF; se volverá a intentar automáticamente',
};

export function textoIncidencia(i: Pick<Incidencia, 'codigo' | 'mensaje_usuario'>): string {
  return (Object.hasOwn(TEXTO_INCIDENCIA, i.codigo) ? TEXTO_INCIDENCIA[i.codigo] : null) ?? i.mensaje_usuario ?? `Incidencia ${i.codigo}`;
}

/** "Necesita tu atención" e Inicio: las INFO no salen (solo en el detalle de factura). Severidad desconocida: sí sale. */
export function incidenciaEnInicio(i: Pick<Incidencia, 'severidad'>): boolean {
  return i.severidad !== 'INFO';
}

/** Alertas (todas con regla validada por Pío): las mismas en Inicio y en la bandeja. */
export function construirAlertas(f: Filas): Alerta[] {
  const out: Alerta[] = [];
  for (const r of filas(f, 'alertas_albaran_no_en_farmatic')) {
    out.push({
      tipo: 'ALBARAN_FACTURADO_NO_EN_FARMATIC',
      validacion: 'VALIDADA',
      color: 'rojo',
      titulo: 'Albarán facturado que ya no está en Farmatic',
      id_contadores: [entero(r.id_contador) ?? 0],
      numero_albaran: texto(r.numero_albaran),
      proveedor: texto(r.proveedor_factura) ?? texto(r.proveedor),
      factura_id: texto(r.factura_id),
      numero_factura: texto(r.numero_factura),
      fecha: texto(r.detectado_at),
      detalle: {
        cambio_id: entero(r.cambio_id), motivo: texto(r.motivo), origen: texto(r.origen),
        conciliacion_id: texto(r.conciliacion_id), id_proveedor: texto(r.id_proveedor),
        fecha_albaran: texto(r.fecha), importe_puc: importe(r.importe_puc),
      },
    });
  }
  for (const r of filas(f, 'alertas_duplicado_farmatic')) {
    const det: AlbaranFarmatic[] = (Array.isArray(r.detalle) ? (r.detalle as Fila[]) : []).map((d) => ({
      id_contador: entero(d.id_contador), numero_albaran: texto(d.numero_albaran),
      id_proveedor: texto(d.id_proveedor), proveedor: texto(d.proveedor),
      fecha: texto(d.fecha), importe_puc: importe(d.importe_puc),
    }));
    for (const g of gruposDuplicadoFarmatic(det)) {
      const fechas = g.map((x) => x.fecha).filter((x): x is string => x !== null).sort();
      out.push({
        tipo: 'POSIBLE_DUPLICADO_FARMATIC',
        validacion: 'VALIDADA',
        color: 'naranja',
        titulo: 'Albarán duplicado en Farmatic',
        id_contadores: g.map((x) => x.id_contador ?? 0),
        numero_albaran: numeroAlbaranBase(g[0].numero_albaran as string),
        proveedor: g[0].proveedor,
        factura_id: null,
        numero_factura: null,
        fecha: fechas.length ? fechas[fechas.length - 1] : null,
        detalle: {
          regla: 'B: mismo proveedor + mismo número sin letra final + mismo importe',
          id_proveedor_comparable: idProveedorR9(g[0].id_proveedor),
          importe_puc: g[0].importe_puc,
          albaranes: g.length,
          filas: g,
        },
      });
    }
  }
  for (const r of filas(f, 'alertas_correcciones_aprobadas')) {
    const aplicada = texto(r.aplicada_at) !== null;
    out.push({
      tipo: 'CORRECCION_APROBADA',
      validacion: 'VALIDADA',
      color: aplicada ? 'verde' : 'azul',
      titulo: aplicada ? 'Corrección de albarán aprobada y aplicada' : 'Corrección de albarán aprobada, pendiente de aplicar',
      id_contadores: [entero(r.id_contador) ?? 0],
      numero_albaran: texto(r.numero_albaran),
      proveedor: texto(r.proveedor),
      factura_id: null,
      numero_factura: null,
      fecha: texto(r.aplicada_at) ?? texto(r.aprobado_at),
      detalle: {
        aprobacion_id: entero(r.aprobacion_id), motivo: texto(r.motivo), cambio: r.cambio ?? null,
        aprobado_por: texto(r.aprobado_por), aprobado_at: texto(r.aprobado_at), referencia: texto(r.referencia),
        aplicada_at: texto(r.aplicada_at), valores_anteriores: r.valores_anteriores ?? null,
        valores_nuevos: r.valores_nuevos ?? null,
      },
    });
  }
  return out;
}

function referenciaFactura(fa: FacturaResumen): string {
  return [fa.proveedor ?? 'Proveedor sin identificar', fa.numero_factura ?? '(sin número)'].join(' ');
}

function construirAtencion(facturas: FacturaResumen[], documentos: DocumentoPdf[], incidencias: Incidencia[]): ItemAtencion[] {
  const out: ItemAtencion[] = [];
  for (const fa of facturas) {
    const c = fa.conciliacion;
    if (fa.estado_conciliacion_cf === 'REVISION_CONCILIACION') {
      out.push({ tipo: 'Revisión conciliación', color: 'naranja', factura_id: fa.factura_id, documento_id: fa.documento_id,
        referencia: referenciaFactura(fa), codigo: c?.resultado ?? null, diferencia_motor: c?.diferencia ?? null,
        texto: 'Se han agotado los intentos de conciliar la factura con sus albaranes' });
    } else if (c && c.resultado && c.resultado !== 'CONCILIADA') {
      out.push({ tipo: 'Diferencia', color: 'rojo', factura_id: fa.factura_id, documento_id: fa.documento_id,
        referencia: referenciaFactura(fa), codigo: c.resultado, diferencia_motor: c.diferencia,
        texto: c.resultado === 'NO_EVALUABLE'
          ? 'No se puede comprobar la factura contra sus albaranes'
          : 'La factura no cuadra con sus albaranes' });
    }
    if (fa.estado_normalizacion === 'REQUIERE_REVISION') {
      out.push({ tipo: 'Revisión normalización', color: 'naranja', factura_id: fa.factura_id, documento_id: fa.documento_id,
        referencia: referenciaFactura(fa), codigo: fa.estado_normalizacion,
        texto: fa.importe_total === null ? 'Faltan datos de la factura: el total no consta en el documento' : 'Faltan datos de la factura' });
    }
  }
  // Incidencias abiertas AVISO/ERROR (las INFO solo en el detalle de factura), en lenguaje llano:
  // diccionario de códigos (TEXTO_INCIDENCIA) o, si no hay entrada, mensaje_usuario.
  for (const i of incidencias.filter(incidenciaEnInicio)) {
    const referencia = i.numero_factura ?? i.archivo_nombre ?? '';
    if (i.codigo === 'POSIBLE_DUPLICADO') {
      out.push({ tipo: 'Posible duplicado', color: 'naranja', factura_id: i.factura_id, documento_id: i.documento_id,
        referencia, codigo: i.codigo, texto: textoIncidencia(i) });
    } else {
      out.push({ tipo: i.bloqueante ? 'Incidencia bloqueante' : 'Incidencia', color: 'rojo', factura_id: i.factura_id,
        documento_id: i.documento_id, referencia, codigo: i.codigo, texto: textoIncidencia(i) });
    }
  }
  for (const d of documentos) {
    const referencia = [d.proveedor ?? 'Proveedor sin identificar', d.archivo_nombre ?? ''].join(' · ');
    if (LECTURA_CON_DEFECTO.includes(d.estado_lectura)) {
      out.push({ tipo: 'Con defecto', color: 'rojo', factura_id: null, documento_id: d.documento_id, referencia,
        codigo: d.ultimo_error_codigo,
        texto: d.estado_lectura === 'REVISION' ? 'El PDF necesita revisión manual' : 'No se ha podido leer el PDF' });
    } else if (LECTURA_SIN_AUTOMATIZAR.includes(d.estado_lectura)) {
      out.push({ tipo: 'Sin automatizar', color: 'gris', factura_id: null, documento_id: d.documento_id, referencia,
        codigo: d.estado_lectura, texto: 'El sistema todavía no sabe leer las facturas de este proveedor' });
    }
  }
  return out;
}

function ahora(): string {
  return new Date().toISOString();
}

export const construir = {
  inicio(f: Filas, generado_at: string = ahora()): InicioDTO {
    const docs = filas(f, 'documentos').map(aDocumento);
    const facts = filas(f, 'facturas').map(aFactura);
    const venc = filas(f, 'vencimientos').map(aVencimiento);
    // Inicio no muestra incidencias INFO (ni en el contador ni en "Necesita tu atención").
    const inc = filas(f, 'incidencias_abiertas').map(aIncidencia).filter(incidenciaEnInicio);
    const luna = filas(f, 'luna_mes')[0] ?? {};
    const total = sumaConocida(facts.map((x) => x.importe_total));
    const conciliado = sumaConocida(facts.filter((x) => x.estado_conciliacion_cf === 'CONCILIADA').map((x) => x.importe_total));
    const conciliacion = contar(facts.map((x) => x.estado_conciliacion_cf), ESTADOS_CONCILIACION);
    conciliacion.NO_APLICA = facts.filter((x) => x.requiere_conciliacion_albaranes === false).length;
    const hoy = generado_at.slice(0, 10);
    return {
      farmacia: FARMACIA,
      generado_at,
      documentos: {
        total: docs.length,
        pendientes_procesar: docs.filter((d) => LECTURA_PENDIENTE.includes(d.estado_lectura)).length,
        con_defecto: docs.filter((d) => LECTURA_CON_DEFECTO.includes(d.estado_lectura)).length,
        sin_automatizar: docs.filter((d) => LECTURA_SIN_AUTOMATIZAR.includes(d.estado_lectura)).length,
        por_estado: contar(docs.map((d) => d.estado_lectura), ESTADOS_LECTURA),
      },
      facturas: { total: facts.length, sin_importe: total.desconocidos, importe_total_conocido: total.suma },
      requieren_revision: facts.filter((x) => x.estado_normalizacion === 'REQUIERE_REVISION' || x.estado_conciliacion_cf === 'REVISION_CONCILIACION').length,
      normalizacion: contar(facts.map((x) => x.estado_normalizacion), ESTADOS_NORMALIZACION),
      conciliacion,
      revision: contar(facts.map((x) => x.estado_revision), ESTADOS_REVISION),
      cobertura: {
        importe_facturado_conocido: total.suma,
        importe_conciliado_conocido: conciliado.suma,
        facturas_sin_importe: total.desconocidos,
      },
      incidencias: {
        abiertas: inc.length,
        bloqueantes: inc.filter((i) => i.bloqueante).length,
      },
      proximos_vencimientos: venc.filter((v) => v.fecha_vencimiento !== null && v.fecha_vencimiento >= hoy).slice(0, 5),
      atencion: construirAtencion(facts, docs, inc),
      alertas: construirAlertas(f),
      luna_mes: { ejecuciones: cuenta(luna.ejecuciones_luna), coste: importe(luna.coste_luna) },
      pago: PAGO_SIN_DATOS,
    };
  },

  facturas(f: Filas, generado_at: string = ahora()): FacturasDTO {
    const facts = filas(f, 'facturas').map(aFactura);
    const grupos = agruparFacturasPorProveedor(facts);
    const claveDe = new Map<string, string>();
    for (const g of grupos) for (const fa of g.facturas) claveDe.set(fa.factura_id, g.grupo.clave);
    return {
      farmacia: FARMACIA,
      generado_at,
      facturas: facts.map((fa) => ({ ...fa, proveedor_grupo: claveDe.get(fa.factura_id) as string })),
      proveedores_filtro: grupos.map((g) => ({ clave: g.grupo.clave, etiqueta: g.etiqueta, sin_cif: g.grupo.sin_cif, facturas: g.facturas.length })),
      documentos_sin_factura: filas(f, 'documentos').map(aDocumento).filter((d) => d.facturas === 0),
      pago: PAGO_SIN_DATOS,
    };
  },

  facturaDetalle(f: Filas, generado_at: string = ahora()): FacturaDetalleDTO | null {
    const cab = filas(f, 'factura_cabecera');
    if (cab.length === 0) return null;
    if (cab.length > 1) throw new Error('FACTURA_CABECERA_DUPLICADA');
    const r = cab[0];
    return {
      farmacia: FARMACIA,
      generado_at,
      factura: aFactura(r),
      documento: {
        documento_id: textoReq(r.documento_id, 'documento_id'),
        archivo_nombre: texto(r.archivo_nombre),
        archivo_ruta: texto(r.archivo_ruta),
        archivo_hash: texto(r.archivo_hash),
        numero_paginas: entero(r.numero_paginas),
        estado_lectura: texto(r.estado_lectura),
        estado_persistencia: texto(r.estado_persistencia),
        fecha_importacion: texto(r.fecha_importacion),
      },
      proveedor: {
        proveedor_cif: texto(r.proveedor_cif),
        id_proveedor_albaranes: texto(r.id_proveedor_albaranes),
        extractor_codigo: texto(r.proveedor_extractor_codigo),
        nivel_confianza: texto(r.proveedor_nivel_confianza),
      },
      normalizacion: {
        ejecucion_id: texto(r.normalizacion_ejecucion_id),
        disparador: texto(r.normalizacion_disparador),
        estado: texto(r.normalizacion_ejecucion_estado),
        extractor_usado: texto(r.extractor_usado),
        normalizador_version: texto(r.normalizador_version),
        uso_ocr: booleano(r.uso_ocr),
        uso_luna: booleano(r.uso_luna),
        luna_modelo: texto(r.luna_modelo),
        luna_campos: listaTexto(r.luna_campos),
        tokens_total: entero(r.tokens_total),
        coste_luna: importe(r.coste_luna),
        finalizado_at: texto(r.normalizacion_finalizada_at),
      },
      datos_extraidos: r.datos_extraidos ?? null,
      provenance: r.factura_provenance ?? null,
      lineas: filas(f, 'factura_lineas').map(aLinea),
      impuestos: filas(f, 'factura_impuestos').map((x) => aFilaImportes(x, ['base_imponible', 'cuota_iva', 'cuota_recargo_equivalencia', 'total_tramo', 'tipo_iva', 'tipo_recargo_equivalencia'])),
      vencimientos: filas(f, 'factura_vencimientos').map(aVencimiento),
      albaranes_extraidos: filas(f, 'factura_albaranes_extraidos').map((x) => aFilaImportes(x, ['importe_base', 'importe_total'])),
      movimientos: filas(f, 'factura_movimientos').map((x) => aFilaImportes(x, ['base', 'iva', 'recargo_equivalencia', 'importe'])),
      ajustes: filas(f, 'factura_ajustes').map((x) => aFilaImportes(x, ['importe'])),
      incidencias: filas(f, 'factura_incidencias').map(aIncidencia),
      historial: filas(f, 'factura_historial').map(aEvento),
      pago: PAGO_SIN_DATOS,
    };
  },

  conciliacionBandeja(f: Filas, generado_at: string = ahora()): ConciliacionBandejaDTO {
    const facts = filas(f, 'facturas').map(aFactura);
    const lineas = filas(f, 'lineas').map(aLinea);
    const porFactura = new Map<string, LineaConciliacion[]>();
    for (const l of lineas) {
      const lista = porFactura.get(l.factura_id) ?? [];
      lista.push(l);
      porFactura.set(l.factura_id, lista);
    }
    const bandeja: FacturaBandeja[] = facts.map((fa) => {
      const ls = porFactura.get(fa.factura_id) ?? [];
      const res = fa.conciliacion?.resultado ?? null;
      // Prioridad de presentación (no recalcula nada): revisión > resultado no conciliado > pendiente > conciliada.
      let prioridad = 4;
      let color: Color = 'gris';
      if (fa.estado_conciliacion_cf === 'REVISION_CONCILIACION') { prioridad = 1; color = 'naranja'; }
      else if (fa.estado_conciliacion_cf === 'PENDIENTE_CONCILIAR' && res !== null && res !== 'CONCILIADA') { prioridad = 2; color = 'rojo'; }
      else if (fa.estado_conciliacion_cf === 'PENDIENTE_CONCILIAR') { prioridad = 3; color = 'azul'; }
      else if (fa.estado_conciliacion_cf === 'CONCILIADA') { prioridad = 5; color = 'verde'; }
      return { ...fa, prioridad, color, lineas: ls, lineas_por_estado: contar(ls.map((l) => l.estado_linea), ESTADOS_LINEA) };
    });
    bandeja.sort((a, b) => a.prioridad - b.prioridad || (b.fecha_factura ?? '').localeCompare(a.fecha_factura ?? '') || a.factura_id.localeCompare(b.factura_id));
    const resumen = contar(facts.map((x) => x.estado_conciliacion_cf), ESTADOS_CONCILIACION);
    resumen.NO_APLICA = facts.filter((x) => x.requiere_conciliacion_albaranes === false).length;
    return { farmacia: FARMACIA, generado_at, resumen, facturas: bandeja, alertas: construirAlertas(f) };
  },

  vencimientos(f: Filas, generado_at: string = ahora()): VencimientosDTO {
    const v = filas(f, 'vencimientos').map(aVencimiento);
    const cargos = sumaConocida(v.filter((x) => x.tipo_documento !== 'ABONO' && x.importe !== null).map((x) => x.importe));
    const abonos = sumaConocida(v.filter((x) => x.tipo_documento === 'ABONO' && x.importe !== null).map((x) => x.importe));
    return {
      farmacia: FARMACIA,
      generado_at,
      vencimientos: v,
      totales: {
        vencimientos: v.length,
        sin_importe: v.filter((x) => x.importe === null).length,
        sin_fecha: v.filter((x) => x.fecha_vencimiento === null).length,
        importe_cargos_conocido: cargos.suma,
        importe_abonos_conocido: abonos.suma,
      },
      pago: PAGO_SIN_DATOS,
    };
  },

  cashflowSemanas(f: Filas, generado_at: string = ahora()): CashflowSemanasDTO {
    const v = filas(f, 'vencimientos').map(aVencimiento);
    const grupos = new Map<string, Vencimiento[]>();
    for (const x of v) {
      const k = x.fecha_vencimiento === null ? '' : lunesISO(x.fecha_vencimiento);
      const g = grupos.get(k) ?? [];
      g.push(x);
      grupos.set(k, g);
    }
    const semanas: SemanaCashflow[] = [...grupos.entries()]
      .sort(([a], [b]) => (a === '' ? 1 : b === '' ? -1 : a.localeCompare(b)))
      .map(([k, g]) => ({
        semana: k === '' ? null : k,
        semana_fin: k === '' ? null : sumarDias(k, 6),
        vencimientos: g.length,
        vencimientos_sin_importe: g.filter((x) => x.importe === null).length,
        importe_cargos_conocido: sumaConocida(g.filter((x) => x.tipo_documento !== 'ABONO' && x.importe !== null).map((x) => x.importe)).suma,
        importe_abonos_conocido: sumaConocida(g.filter((x) => x.tipo_documento === 'ABONO' && x.importe !== null).map((x) => x.importe)).suma,
        vencimientos_sin_validar: g.filter((x) => x.estado_revision !== 'VALIDADA_PIO').length,
      }));
    return { farmacia: FARMACIA, generado_at, semanas, pago: PAGO_SIN_DATOS };
  },

  proveedores(f: Filas, generado_at: string = ahora()): ProveedoresDTO {
    const facts = filas(f, 'facturas').map(aFactura);
    const docs = filas(f, 'documentos').map(aDocumento);
    const grupos = agruparFacturasPorProveedor(facts);
    const proveedores: Proveedor[] = grupos.map(({ grupo, etiqueta, alias, facturas: fp }) => {
      const tot = sumaConocida(fp.map((x) => x.importe_total));
      const fechas = fp.map((x) => x.fecha_factura).filter((x): x is string => x !== null).sort();
      return {
        ...grupo,
        etiqueta,
        alias,
        facturas: fp.length,
        norm_revision: fp.filter((x) => x.estado_normalizacion === 'REQUIERE_REVISION').length,
        conc_pendiente: fp.filter((x) => x.estado_conciliacion_cf === 'PENDIENTE_CONCILIAR').length,
        conc_ok: fp.filter((x) => x.estado_conciliacion_cf === 'CONCILIADA').length,
        conc_revision: fp.filter((x) => x.estado_conciliacion_cf === 'REVISION_CONCILIACION').length,
        rev_pendiente: fp.filter((x) => x.estado_revision === 'PENDIENTE_REVISION_PIO').length,
        facturas_sin_importe: tot.desconocidos,
        importe_total_conocido: tot.suma,
        ultima_fecha_factura: fechas.length ? fechas[fechas.length - 1] : null,
      };
    });
    // Mapa PDF × estado con el mismo criterio: CIF de sus facturas; si no, nombre canónico del literal.
    const etiquetas = new Map(proveedores.map((p) => [p.clave, p.etiqueta]));
    const mapa = new Map<string, { clave: string; proveedor: string; sin_cif: boolean; por_estado: Record<string, number>; total: number }>();
    for (const d of docs) {
      const literal = d.proveedor_literal ?? d.proveedor;
      const g = grupoProveedor(d.proveedor_cif, literal);
      const fila = mapa.get(g.clave) ?? {
        clave: g.clave,
        proveedor: etiquetas.get(g.clave) ?? (g.clave === 'sin_identificar' ? SIN_IDENTIFICAR : (literal as string).trim()),
        sin_cif: g.sin_cif,
        por_estado: contar([], ESTADOS_LECTURA),
        total: 0,
      };
      fila.por_estado[d.estado_lectura] = (fila.por_estado[d.estado_lectura] ?? 0) + 1;
      fila.total += 1;
      mapa.set(g.clave, fila);
    }
    const estados = [...new Set([...ESTADOS_LECTURA, ...docs.map((d) => d.estado_lectura)])];
    const filasMapa = [...mapa.values()].sort((a, b) =>
      Number(a.clave === 'sin_identificar') - Number(b.clave === 'sin_identificar')
      || Number(a.sin_cif) - Number(b.sin_cif) || a.proveedor.localeCompare(b.proveedor));
    return { farmacia: FARMACIA, generado_at, proveedores, mapa_documentos: { estados, filas: filasMapa } };
  },

  configuracion(f: Filas, generado_at: string = ahora()): ConfiguracionDTO {
    const rs = filas(f, 'configuracion');
    if (rs.length !== 1) throw new Error(`CONFIGURACION_NO_UNICA_O_PIO_NO_HABILITADA: ${rs.length}`);
    const r = rs[0];
    return {
      farmacia: FARMACIA,
      generado_at,
      farmacia_activa: FARMACIA,
      farmacias_habilitadas: listaTexto(r.farmacias_habilitadas),
      normalizacion_automatica: booleano(r.normalizacion_automatica),
      conciliacion_automatica: booleano(r.conciliacion_automatica),
      luna_habilitada: booleano(r.luna_habilitada),
      tolerancia_conciliacion: importe(r.tolerancia_conciliacion),
      conciliacion_tolerancia_suelo: importe(r.conciliacion_tolerancia_suelo),
      conciliacion_tolerancia_por_albaran: importe(r.conciliacion_tolerancia_por_albaran),
      conciliacion_tolerancia_tope: importe(r.conciliacion_tolerancia_tope),
      normalizacion_max_intentos: entero(r.normalizacion_max_intentos),
      normalizacion_backoff: listaTexto(r.normalizacion_backoff),
      conciliacion_max_intentos: entero(r.conciliacion_max_intentos),
      conciliacion_backoff: listaTexto(r.conciliacion_backoff),
      updated_at: texto(r.updated_at),
    };
  },
};

// Fechas ISO (YYYY-MM-DD) sin zona horaria.
function lunesISO(fecha: string): string {
  const d = new Date(fecha.slice(0, 10) + 'T00:00:00Z');
  const dia = (d.getUTCDay() + 6) % 7; // lunes = 0
  d.setUTCDate(d.getUTCDate() - dia);
  return d.toISOString().slice(0, 10);
}
function sumarDias(fecha: string, n: number): string {
  const d = new Date(fecha + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** Ejecutor de consultas que provee el adaptador REAL (una transacción READ ONLY por bloque). */
export type EjecutorBloque = <T>(trabajo: (consultar: (n: NombreConsulta, idFactura?: string) => Promise<Fila[]>) => Promise<T>) => Promise<T>;

/** Implementación del contrato sobre un ejecutor de consultas. */
export function contratoDesdeConsultas(enTransaccion: EjecutorBloque): Contrato {
  const cargar = (bloque: Bloque, idFactura?: string): Promise<Filas> =>
    enTransaccion(async (consultar) => {
      const out: Filas = {};
      for (const n of CONSULTAS_POR_BLOQUE[bloque]) out[n] = await consultar(n, idFactura);
      return out;
    });
  return {
    inicio: async () => construir.inicio(await cargar('inicio')),
    facturas: async () => construir.facturas(await cargar('facturas')),
    facturaDetalle: async (id) => construir.facturaDetalle(await cargar('facturaDetalle', id)),
    conciliacionBandeja: async () => construir.conciliacionBandeja(await cargar('conciliacionBandeja')),
    vencimientos: async () => construir.vencimientos(await cargar('vencimientos')),
    cashflowSemanas: async () => construir.cashflowSemanas(await cargar('cashflowSemanas')),
    proveedores: async () => construir.proveedores(await cargar('proveedores')),
    configuracion: async () => construir.configuracion(await cargar('configuracion')),
  };
}

export const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
