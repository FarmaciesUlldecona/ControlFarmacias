// H3b: genera web/fixtures/dto/*.json desde el contrato (web/app/server/contrato.ts).
//
// Fuente: los casos ficticios de H3a (web/fixtures/v_web_*.json, sin cambios) + los casos nuevos
// de H3b definidos aquí (ver web/fixtures/CASOS.md). Las filas se dan con la forma de las
// consultas del contrato y se pasan por los MISMOS constructores que usa el modo REAL.
// No conecta a ninguna base de datos. Todo es ficticio.
//
// Uso: node web/fixtures/scripts/gen_fixtures.mjs   (o `npm run fixtures:gen` en web/app)
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { cifFactura, construir, idProveedorR9 } from '../../app/server/contrato.ts';

const RAIZ = join(import.meta.dirname, '..');
const DTO = join(RAIZ, 'dto');
/** Fecha fija de generación: los DTO son deterministas. */
export const GENERADO_AT = '2026-11-02T08:00:00+00:00';
const FICTICIO = { ficticio: true, fuente: 'FIXTURE_H3B' };

const h3a = (n) => JSON.parse(readFileSync(join(RAIZ, `v_web_${n}.json`), 'utf8'));
const sinFarmacia = ({ farmacia, ...resto }) => resto; // eslint-disable-line no-unused-vars

const P = (n) => `a0000000-0000-4000-8000-0000000000${String(n).padStart(2, '0')}`;
const D = (n) => `d0000000-0000-4000-8000-0000000000${String(n).padStart(2, '0')}`;

// ---------------------------------------------------------------------------
// Casos nuevos H3b
// ---------------------------------------------------------------------------

const PROVEEDOR_BEIERSDORF = {
  id: P(6), farmacia: 'PIO', codigo: 'BEIERSDORF', nombre: 'BEIERSDORF (FICTICIO)', farmatic_id_proveedor: null,
  extractor_codigo: null, nivel_confianza: 'NO_VERIFICADO', activo: true, alias: [],
};

/** Varios PDF PROVEEDOR_NO_SOPORTADO (además de D08 de H3a). */
const DOCUMENTOS_H3B = [
  { n: 11, proveedor: P(6), nombre: 'Beiersdorf_FV_2026_1029.pdf', hash: 'b3', fecha: '2026-10-29T21:00:00+00:00' },
  { n: 12, proveedor: null, nombre: 'Factura_sin_membrete_3010.pdf', hash: 'c4', fecha: '2026-10-30T21:00:00+00:00' },
  { n: 13, proveedor: P(5), nombre: 'Laboratorio_demo_factura_2.pdf', hash: 'd5', fecha: '2026-10-31T21:00:00+00:00' },
].map((x) => ({
  documento_id: D(x.n),
  archivo_nombre: x.nombre,
  archivo_hash: x.hash.repeat(32),
  fecha_importacion: x.fecha,
  estado_lectura: 'PROVEEDOR_NO_SOPORTADO',
  estado_persistencia: 'PENDIENTE',
  intentos_fallo_normalizacion: 1,
  ultima_clase_fallo: 'NO_SOPORTADO',
  ultimo_error_codigo: 'PROVEEDOR_NO_SOPORTADO',
  proximo_reintento_at: null,
  numero_paginas: 1,
  cantidad_documentos_detectados: null,
  facturas: 0,
  incidencias_documento_abiertas: 0,
  proveedor_id: x.proveedor,
}));

/** H3c (decisión 1A): PDF en REVISION → cuenta en "Documentos con defecto" junto a ERROR (D09). */
const DOCUMENTO_REVISION = {
  documento_id: D(14),
  archivo_nombre: 'Alliance_multifactura_incompleta_0111.pdf',
  archivo_hash: 'e6'.repeat(32),
  fecha_importacion: '2026-11-01T21:00:00+00:00',
  estado_lectura: 'REVISION',
  estado_persistencia: 'REQUIERE_REVISION',
  intentos_fallo_normalizacion: 0,
  ultima_clase_fallo: null,
  ultimo_error_codigo: 'FACTURA_INCOMPLETA',
  proximo_reintento_at: null,
  numero_paginas: 3,
  cantidad_documentos_detectados: 1,
  facturas: 0,
  incidencias_documento_abiertas: 0,
  proveedor_id: P(3),
};

const ALERTA_AUSENTE = [{
  cambio_id: 5001, id_contador: 900102, motivo: 'AUSENTE_EN_FARMATIC', detectado_at: '2026-10-30T03:00:00+00:00',
  origen: 'RESYNC_VENTANA', numero_albaran: '08X10002', id_proveedor: '0002', proveedor: 'ALLIANCE HEALTHCARE (FICTICIO)',
  fecha: '2026-10-02', importe_puc: 68.17, factura_id: 'f0000000-0000-4000-8000-000000000001',
  conciliacion_id: 'c0000000-0000-4000-8000-000000000101', numero_factura: 'AL-26-100231',
  proveedor_factura: 'ALLIANCEHEALTHCARECENCORA',
}];

/**
 * H3d, regla B (validada por Pío): candidatos que devuelve la consulta (mismo proveedor R9 + mismo número sin
 * letra final). El constructor exige además el mismo importe.
 *  - 08C66676 / 08C66676A, 57,40 € los dos → CUMPLE (alerta).
 *  - 08C70015 / 08C70015A, 61,20 € y 64,85 € → NO cumple (distinto importe; sin alerta).
 */
export const ALERTA_DUPLICADO = [
  {
    id_proveedor_comparable: '2', numero_base: '08C66676', albaranes: 2, fecha_max: '2026-10-21',
    detalle: [
      { id_contador: 900301, numero_albaran: '08C66676', id_proveedor: '0002', proveedor: 'ALLIANCE HEALTHCARE (FICTICIO)', fecha: '2026-10-20', importe_puc: 57.4 },
      { id_contador: 900302, numero_albaran: '08C66676A', id_proveedor: '2', proveedor: 'ALLIANCE HEALTHCARE (FICTICIO)', fecha: '2026-10-21', importe_puc: 57.4 },
    ],
  },
  {
    id_proveedor_comparable: '2', numero_base: '08C70015', albaranes: 2, fecha_max: '2026-10-18',
    detalle: [
      { id_contador: 900311, numero_albaran: '08C70015', id_proveedor: '0002', proveedor: 'ALLIANCE HEALTHCARE (FICTICIO)', fecha: '2026-10-18', importe_puc: 61.2 },
      { id_contador: 900312, numero_albaran: '08C70015A', id_proveedor: '0002', proveedor: 'ALLIANCE HEALTHCARE (FICTICIO)', fecha: '2026-10-18', importe_puc: 64.85 },
    ],
  },
];

const ALERTA_CORRECCIONES = [
  {
    aprobacion_id: 2, id_contador: 900160, motivo: 'CAMBIO_IDENTIDAD',
    cambio: [{ campo: 'id_proveedor', anterior: '0004', nuevo: '0001' }],
    aprobado_por: 'Pio', aprobado_at: '2026-10-31T09:00:00+00:00', referencia: 'H3B-FICTICIO-2',
    aplicada_at: null, valores_anteriores: null, valores_nuevos: null,
    numero_albaran: 'FD-ALB-55120', proveedor: 'FEDEFARMA (FICTICIO)', fecha: '2026-10-21',
  },
  {
    aprobacion_id: 1, id_contador: 900150, motivo: 'CAMBIO_IDENTIDAD',
    cambio: [{ campo: 'numero_albaran', anterior: '08X10050', nuevo: '08X10050A' }],
    aprobado_por: 'Pio', aprobado_at: '2026-10-29T10:00:00+00:00', referencia: 'H3B-FICTICIO-1',
    aplicada_at: '2026-10-29T10:05:00+00:00', valores_anteriores: { numero_albaran: '08X10050' },
    valores_nuevos: { numero_albaran: '08X10050A' },
    numero_albaran: '08X10050A', proveedor: 'ALLIANCE HEALTHCARE (FICTICIO)', fecha: '2026-10-15',
  },
];

const HISTORIAL_H3B = DOCUMENTOS_H3B.map((d, i) => ({
  evento_id: 101 + i, documento_id: d.documento_id, factura_id: null, evento: 'NORMALIZACION_ERROR', origen: 'RPC',
  actor: 'worker-manual', estado_anterior: { estado_lectura: 'NORMALIZANDO' },
  estado_nuevo: { estado_lectura: 'PROVEEDOR_NO_SOPORTADO' }, detalle: FICTICIO,
  created_at: d.fecha_importacion.replace('T21:00', 'T21:05'),
})).concat([{
  evento_id: 104, documento_id: DOCUMENTO_REVISION.documento_id, factura_id: null, evento: 'INVENTARIO_MULTIFACTURA',
  origen: 'RPC', actor: 'worker-manual', estado_anterior: { estado_lectura: 'NORMALIZANDO' },
  estado_nuevo: { estado_lectura: 'REVISION', estado_persistencia: 'REQUIERE_REVISION' }, detalle: FICTICIO,
  created_at: '2026-11-01T21:05:00+00:00',
}]);

/** Movimientos documentales (descripción literal de CASOS.md H3a). */
const MOVIMIENTOS = {
  'c0000000-0000-4000-8000-000000000001': { categoria: 'SERVICIO_OPERATIVO', descripcion_literal: 'SERVICIO INTEGRAL DE DISTRIBUCION', sentido: 'CARGO' },
  'c0000000-0000-4000-8000-000000000002': { categoria: 'DESCONOCIDA', descripcion_literal: 'REGULARIZACION', sentido: null },
};

// ---------------------------------------------------------------------------
// Filas con la forma de las consultas del contrato
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Casos H4b: proveedores agrupados por CIF (todo ficticio)
// ---------------------------------------------------------------------------

/** CIF ficticio por proveedor (H3a los tenía todos iguales). FEDEFARMA (P04) sin CIF → grupo "sin CIF". */
/**
 * H5-8: HEFAME (P02) con el CIF que su adaptador exige (src/facturas/grupos_funcionales.py:41; CIF de empresa que
 * consta en el código, no dato de Pío). El resto, ficticio.
 */
const CIF_H4B = { [P(1)]: 'A00000001', [P(2)]: 'F30004444', [P(3)]: 'B00000003', [P(4)]: null };
/** F02: mismo CIF que Alliance escrito con guion y minúscula, y otro literal → alias del grupo. */
const AJUSTES_FACTURA_H4B = {
  'f0000000-0000-4000-8000-000000000002': { proveedor_cif: 'b-00000003', proveedor_literal: 'Alliance Healthcare España' },
  // H5-8: razón social que escribe el adaptador Hefame (src/facturas/motor_local/adaptadores/hefame.py:92).
  'f0000000-0000-4000-8000-000000000005': { proveedor_literal: 'HDAD.FMCTCA.MEDIT.,S.C.L.' },
};
/** H5-8: Hefame no documenta los tipos de IVA (TIPOS_FISCALES_NO_DOCUMENTADOS, hefame.py:378): tramo sin tipo. */
export const F05_SIN_TIPOS_FISCALES = 'f0000000-0000-4000-8000-000000000005';
/** Incidencia INFO (solo en el detalle de factura; nunca en Inicio). */
export const INCIDENCIAS_H4B = [{
  incidencia_id: '20000000-0000-4000-8000-000000000041', farmacia: 'PIO', documento_id: null,
  factura_id: 'f0000000-0000-4000-8000-000000000002', numero_factura: 'AL-26-100577',
  archivo_nombre: 'Alliance_AL-26-100577.pdf', codigo: 'MONEDA_NO_DOCUMENTADA', categoria: 'DATOS_DOCUMENTALES', severidad: 'INFO',
  bloqueante: false, estado: 'ABIERTA', mensaje_usuario: 'La moneda no consta en el documento; se asume EUR.',
  detalle_tecnico: { ...FICTICIO, fuente: 'FIXTURE_H4B' }, created_at: '2026-10-25T21:06:00+00:00',
  resuelta_at: null, resuelta_por: null,
}];

// ---------------------------------------------------------------------------
// Casos H4c: ajustes con la forma real de producción (todo ficticio)
// ---------------------------------------------------------------------------

/**
 * H4c: como en producción, facturas.proveedor_cif vacía y el CIF en datos_extraidos (proveedor.nif.valor).
 * Las filas de la consulta lo traen en `proveedor_nif_documental`. FEDEFARMA (F06) sin CIF: grupo de respaldo por
 * id_proveedor_albaranes R9 ('0004' → id:4).
 */
const conCifDocumental = (r) => ({ ...r, proveedor_cif: null, proveedor_nif_documental: r.proveedor_cif });

/** H4c: F05 (HEFAME) sin tipo de documento en datos_extraidos (la columna quedó en FACTURA por defecto). */
export const F05_SIN_TIPO_DOCUMENTAL = 'f0000000-0000-4000-8000-000000000005';
/**
 * H4c/H4c-2: tipo en datos_extraidos.tipo_documento.valor distinto del de H3a (el resto: el de H3a).
 *  - F05 null → NO_DOCUMENTADO;  F08 FACTURA_DUPLICADO → CARGO (copia de F01);
 *  - F03 FACTURA_RECTIFICATIVA → NO_DOCUMENTADO;  F06 'OTRO' literal → NO_DOCUMENTADO;  F07 ABONO (H3a) → ABONO.
 */
export const TIPO_DOCUMENTAL_H4C = {
  [F05_SIN_TIPO_DOCUMENTAL]: null,
  'f0000000-0000-4000-8000-000000000008': 'FACTURA_DUPLICADO',
  'f0000000-0000-4000-8000-000000000003': 'FACTURA_RECTIFICATIVA',
  'f0000000-0000-4000-8000-000000000006': 'OTRO',
};
const tipoDocumental = (r) => (Object.hasOwn(TIPO_DOCUMENTAL_H4C, r.factura_id) ? TIPO_DOCUMENTAL_H4C[r.factura_id] : r.tipo_documento);
/** Columna tipo_documento como la persistencia (migración 28): null → FACTURA; fuera de la lista → OTRO. */
const columnaTipo = (t) => (t === null ? 'FACTURA' : ['FACTURA', 'ABONO', 'FACTURA_RECTIFICATIVA', 'OTRO'].includes(t) ? t : 'OTRO');

// ---------------------------------------------------------------------------
// Casos H4d: "Necesita tu atención" agrupado (todo ficticio)
// ---------------------------------------------------------------------------

const incidenciaH4d = (n, factura, numero, codigo, severidad, created_at, extra = {}) => ({
  incidencia_id: `20000000-0000-4000-8000-0000000000${n}`, farmacia: 'PIO', documento_id: null,
  factura_id: `f0000000-0000-4000-8000-0000000000${factura}`, numero_factura: numero, archivo_nombre: null,
  codigo, categoria: 'NORMALIZACION', severidad, bloqueante: false, estado: 'ABIERTA',
  // Como la persistencia (migración 28): mensaje_usuario = descripción técnica o el propio código.
  mensaje_usuario: codigo, detalle_tecnico: { ...FICTICIO, fuente: 'FIXTURE_H4D' }, created_at,
  resuelta_at: null, resuelta_por: null, ...extra,
});
/**
 * H4d: varios casos del mismo código (agrupación), un SENTIDO_NO_DOCUMENTADO con severidad ERROR (nunca rojo), un
 * MONEDA_NO_DOCUMENTADA AVISO (como lo guarda producción: fuera de Inicio), un código sin traducción y
 * CANDIDATO_ALBARAN_NO_PROMOVIDO con dos motivos (el texto se precisa con detalle_tecnico.motivo).
 */
export const INCIDENCIAS_H4D = [
  incidenciaH4d(51, '06', 'FD-26/04471', 'IMPORTE_VENCIMIENTO_NO_DOCUMENTADO', 'AVISO', '2026-10-28T21:06:00+00:00'),
  incidenciaH4d(52, '03', 'CF-2026-55810', 'SENTIDO_NO_DOCUMENTADO', 'AVISO', '2026-10-27T21:06:00+00:00'),
  incidenciaH4d(53, '02', 'AL-26-100577', 'SENTIDO_NO_DOCUMENTADO', 'ERROR', '2026-10-29T21:06:00+00:00'),
  incidenciaH4d(54, '04', 'CF-2026-55811', 'MONEDA_NO_DOCUMENTADA', 'AVISO', '2026-10-20T21:06:00+00:00'),
  incidenciaH4d(55, '05', 'HF-0563-889120', 'CODIGO_FICTICIO_SIN_TRADUCCION', 'AVISO', '2026-10-22T21:06:00+00:00'),
  incidenciaH4d(56, '01', 'AL-26-100231', 'CANDIDATO_ALBARAN_NO_PROMOVIDO', 'AVISO', '2026-10-24T21:07:00+00:00',
    { mensaje_usuario: 'TIPO_PEDIDO_NO_CERTIFICADO', detalle_tecnico: { ...FICTICIO, motivo: 'TIPO_PEDIDO_NO_CERTIFICADO', tipos_pedido: ['PEDIDO X'] } }),
  incidenciaH4d(57, '02', 'AL-26-100577', 'CANDIDATO_ALBARAN_NO_PROMOVIDO', 'AVISO', '2026-10-25T21:07:00+00:00',
    { mensaje_usuario: 'SENTIDO_O_SIGNO_NO_COHERENTE', detalle_tecnico: { ...FICTICIO, motivo: 'SENTIDO_O_SIGNO_NO_COHERENTE' } }),
  // H4d-3: incidencia de sentido de línea: su propio grupo en el nivel 7 (no en el grupo 4 de vencimientos).
  incidenciaH4d(62, '04', 'CF-2026-55811', 'SENTIDO_NO_ETIQUETADO_DOCUMENTALMENTE', 'AVISO', '2026-10-26T21:07:00+00:00'),
  // H4d-2: códigos informativos solo de detalle (guardados como AVISO, como en producción).
  incidenciaH4d(58, '03', 'CF-2026-55810', 'REPRESENTACIONES_CONSOLIDADAS', 'AVISO', '2026-10-30T21:06:00+00:00'),
  incidenciaH4d(59, '07', 'CF-AB-2026-0912', 'FILAS_DUPLICADAS_EVIDENCIA_IDENTICA', 'AVISO', '2026-10-30T21:07:00+00:00'),
  incidenciaH4d(60, '01', 'AL-26-100231', 'FILA_IMPORTE_CERO_INFORMATIVA', 'AVISO', '2026-10-30T21:08:00+00:00'),
  incidenciaH4d(61, '05', 'HF-0563-889120', 'ALBARANES_CONSUMIBLES_SOLO_REFERENCIA_DOCUMENTAL', 'AVISO', '2026-10-30T21:09:00+00:00'),
];

const detalle = h3a('factura_detalle').map((r) => conCifDocumental({
  ...r,
  tipo_documento: columnaTipo(tipoDocumental(r)),
  tipo_documento_documental: tipoDocumental(r),
  proveedor_cif: Object.hasOwn(CIF_H4B, r.proveedor_id) ? CIF_H4B[r.proveedor_id] : r.proveedor_cif,
  ...(AJUSTES_FACTURA_H4B[r.factura_id] ?? {}),
}));
const lineasH3a = h3a('conciliacion_lineas').filter((l) => l.es_actual);
const incidenciasH3a = [...h3a('incidencias'), ...INCIDENCIAS_H4B, ...INCIDENCIAS_H4D];
const historialH3a = h3a('historial');
const vencimientosH3a = h3a('vencimientos');
const proveedoresH3a = h3a('proveedores_estado');

const abiertasDe = (id) => incidenciasH3a.filter((i) => i.factura_id === id && i.estado === 'ABIERTA');
const filaFactura = (r) => ({
  ...sinFarmacia(r),
  incidencias_abiertas: abiertasDe(r.factura_id).length,
  incidencias_bloqueantes: abiertasDe(r.factura_id).filter((i) => i.bloqueante).length,
});

const proveedorDeDocumento = new Map(detalle.map((r) => [r.documento_id, [r.proveedor_id, r.proveedor]]));
proveedorDeDocumento.set(D(8), [P(5), 'LABORATORIO DEMO (FICTICIO)']);
const nombreProveedor = new Map([...proveedoresH3a, PROVEEDOR_BEIERSDORF].map((p) => [p.id, p.nombre]));

const documentos = [
  ...h3a('documentos_estado').map((d) => {
    const [proveedor_id, proveedor] = proveedorDeDocumento.get(d.documento_id) ?? [null, null];
    // CIF (columna o datos_extraidos), id R9 y literal de la primera factura del PDF que los tenga (como la consulta `documentos`).
    const fs = detalle.filter((f) => f.documento_id === d.documento_id).sort((a, b) => a.pagina_inicio - b.pagina_inicio);
    const proveedor_cif = fs.map((f) => cifFactura(f.proveedor_cif, f.proveedor_nif_documental)).find((c) => c !== null) ?? null;
    const id_proveedor_albaranes = fs.find((f) => idProveedorR9(f.id_proveedor_albaranes) !== null)?.id_proveedor_albaranes ?? null;
    const proveedor_literal = fs.find((f) => f.proveedor_literal)?.proveedor_literal ?? null;
    return { ...sinFarmacia(d), proveedor_id, proveedor, proveedor_cif, id_proveedor_albaranes, proveedor_literal };
  }),
  ...[...DOCUMENTOS_H3B, DOCUMENTO_REVISION].map((d) => ({
    ...d, proveedor: d.proveedor_id ? nombreProveedor.get(d.proveedor_id) : null, proveedor_cif: null,
    id_proveedor_albaranes: null, proveedor_literal: null,
  })),
].sort((a, b) => b.fecha_importacion.localeCompare(a.fecha_importacion) || a.documento_id.localeCompare(b.documento_id));

const facturas = detalle.map(filaFactura)
  .sort((a, b) => (b.fecha_factura ?? '').localeCompare(a.fecha_factura ?? '') || a.factura_id.localeCompare(b.factura_id));
const facturaDe = new Map(detalle.map((r) => [r.factura_id, r]));
const vencimientos = vencimientosH3a.map(({ farmacia, importe_conocido, estado_pago, provenance, ...r }) => ({ // eslint-disable-line no-unused-vars
  ...r,
  tipo_documento: facturaDe.get(r.factura_id).tipo_documento,
  tipo_documento_documental: facturaDe.get(r.factura_id).tipo_documento_documental,
}));
// ---------------------------------------------------------------------------
// Casos H5: tipos de casado del detalle (todo ficticio; mismos importes que H3a, la conciliación no cambia)
// ---------------------------------------------------------------------------

const FX = (n) => `f0000000-0000-4000-8000-0000000000${n}`;
/** Ajustes de líneas H3a (factura, orden) → campos. */
const AJUSTES_LINEAS_H5 = [
  // F02 (Alliance) línea 8: mismo número con letra final (08X20008A = 08X20008).
  [FX('02'), 8, { numero_albaran_farmatic: '08X20008A', clase_numero: 'LETRA_FINAL', coincidencia_numero: 'DIFERENTE', coincidencia_numero_literal: false }],
  // F02 línea 7: albarán de la plataforma ECO360 (id 154), que Farmatic registra como compra a Alliance (R19).
  [FX('02'), 7, { farmatic_id_proveedor: '154', farmatic_proveedor: '6PLATAFECO360AH' }],
  // F04 (Cofares) línea 3: el número de Farmatic (8 dígitos) es el final del número de la factura.
  [FX('04'), 3, { numero_albaran_documental: 'CF-26007012', numero_albaran_farmatic: '26007012', clase_numero: 'FINAL_DOCUMENTAL',
    coincidencia_numero: 'DIFERENTE', coincidencia_numero_literal: false }],
  // H5-3: F07 línea 1 sin número en el PDF → clase NO_DISPONIBLE (casa por PUC, ±3 días).
  [FX('07'), 1, { numero_albaran_documental: null, clase_numero: 'NO_DISPONIBLE', coincidencia_numero: 'NO_DISPONIBLE', coincidencia_numero_literal: false }],
  // H5-3: F04 línea 2 con una clase_numero que el código no escribe (sin descripción; diagnóstico no_previsto).
  [FX('04'), 2, { clase_numero: 'CLASE_FUTURA_PRUEBA' }],
  // H5-5: F01 (Alliance) con estados de la versión anterior del motor (2T/2V): sin clase_numero en provenance.
  [FX('01'), 1, { estado_matching: 'EXACTO', clase_numero: null }],
  [FX('01'), 2, { estado_matching: 'ECONOMICO_UNICO', clase_numero: null, numero_albaran_farmatic: '08X10002B',
    coincidencia_numero: 'DIFERENTE', coincidencia_numero_literal: false }],
];
/**
 * H5-3: líneas sin casar de F07 (abono) con estados de motor: uno no previsto con forma de código, uno que no es
 * código (en el diagnóstico solo suma en otros_no_codigo) y ALBARAN_YA_CONCILIADO. importe_aplicado 0: el explicado no cambia.
 */
const SIN_CASAR_H5_3 = [
  [3, '77091', 'ESTADO_FUTURO_PRUEBA'],
  [4, '77092', 'valor raro (no es código)'],
  [5, '77093', 'ALBARAN_YA_CONCILIADO'],
];
function sinCasarF07(plantilla) {
  return SIN_CASAR_H5_3.map(([orden, numero, estado]) => ({
    ...plantilla, detalle_id: `10000000-0000-4000-8000-0000000007${orden}0`, orden, tipo_relacion: 'SIN_COINCIDENCIA',
    estado_linea: 'DIFERENCIA', estado_matching: estado, coincidencia_numero: null, clase_numero: null, coincidencia_numero_literal: false,
    factura_albaran_extraido_id: `b0000000-0000-4000-8000-0000000007${orden}0`, factura_movimiento_id: null,
    numero_albaran_documental: numero, fecha_albaran_documental: '2026-10-20', sentido_documental: 'ABONO', importe_documental: -10 * orden,
    albaran_farmacia: null, albaran_id_contador: null, numero_albaran_farmatic: null, fecha_albaran_farmatic: null,
    farmatic_id_proveedor: null, importe_puc: null, importe_pvp: null, importe_farmatic: null, importe_aplicado: 0, diferencia: null,
  }));
}
/**
 * F03 línea 2 (98,70 €): R17, una línea = dos albaranes de la misma recepción: 77002 (60,00, su número) + Q039904/2026
 * (38,70, numeración interna). La línea sin coincidencia pasa al orden 4. R17 cuenta como una línea casada (R11).
 */
function r17F03(l) {
  const comun = { tipo_relacion: 'UNO_A_VARIOS', estado_matching: 'MATCH_R17', regla: 'R17', coincidencia_numero: null };
  return [
    { ...l, ...comun, papel_r17: 'NUMERO', clase_numero: 'EXACTA', importe_puc: 60, importe_pvp: 81, importe_farmatic: 60, importe_aplicado: 60, diferencia: 0 },
    { ...l, ...comun, detalle_id: '10000000-0000-4000-8000-000000000131', orden: 3, papel_r17: 'INTERNO', clase_numero: 'INTERNO',
      coincidencia_numero_literal: false, albaran_id_contador: 900131, numero_albaran_farmatic: 'Q039904/2026',
      importe_puc: 38.7, importe_pvp: 52.25, importe_farmatic: 38.7, importe_aplicado: 38.7, diferencia: 0 },
  ];
}
/**
 * H5-2: forma de producción de las líneas.
 *  - Aquí se dejan null importe_documental, importe_farmatic y diferencia; H5-7: valoresPorLinea los rellena después como
 *    la migración 30 (antes de la 30 la persistencia solo escribía importe_aplicado, 24_cf_r17_recepcion.sql:338-354).
 *  - Importes del albarán en el PDF (facturas_albaranes_extraidos): importe_total = el importe documental H3a (total
 *    con IVA y RE, lo que compara el motor) e importe_base = su base sin IVA (ficticia: IVA 10 % + RE 1,4 %).
 *    Hefame (F05): el total del albarán es la base neta (hefame.py:155-161) e importe_base no consta.
 *  - F05: número exacto, como lo clasifica el motor en Hefame (comparar_numeros_albaran, conciliacion.py:290).
 *  - Movimiento de F04: magnitud_usada IMPORTE (conciliacion.py:722).
 */
const HEFAME = FX('05');
const base114 = (v) => (v === null ? null : Math.round((v / 1.114) * 100) / 100);
function formaProduccion(l) {
  const conAlbaran = l.factura_albaran_extraido_id !== null;
  const hefame = l.factura_id === HEFAME;
  const total = conAlbaran ? (hefame ? base114(l.importe_documental) : l.importe_documental) : null;
  return {
    ...l,
    importe_movimiento_fixture: l.importe_documental, // solo para generar facturas_movimientos (no está en el contrato)
    albaran_importe_total: total,
    albaran_importe_base: conAlbaran && !hefame ? base114(l.importe_documental) : null,
    magnitud_usada: l.tipo_relacion === 'MOVIMIENTO_NO_FARMATIC' && l.sentido_documental !== null ? 'IMPORTE' : null,
    ...(hefame && l.tipo_relacion === 'UNO_A_UNO'
      ? { clase_numero: 'EXACTA', coincidencia_numero: 'EXACTA', coincidencia_numero_literal: true, numero_albaran_farmatic: l.numero_albaran_documental }
      : {}),
    importe_documental: null, importe_farmatic: null, diferencia: null,
  };
}

function lineasH5(ls) {
  const out = [];
  for (const l0 of ls) {
    const mov = l0.factura_movimiento_id ? MOVIMIENTOS[l0.factura_movimiento_id] : null;
    // sentido_documental como la consulta: coalesce(fae.tipo_movimiento, fm.sentido) (H3a lo dejaba null en F04).
    let l = { ...l0, sentido_documental: l0.sentido_documental ?? mov?.sentido ?? null, papel_r17: null, regla: null, farmatic_proveedor: null,
      concepto_movimiento: mov?.descripcion_literal ?? null, categoria_movimiento: mov?.categoria ?? null };
    for (const [factura, orden, campos] of AJUSTES_LINEAS_H5) if (l.factura_id === factura && l.orden === orden) l = { ...l, ...campos };
    if (l.factura_id === FX('03') && l.orden === 2) { out.push(...r17F03(l).map(formaProduccion)); continue; }
    if (l.factura_id === FX('03') && l.orden === 3) l = { ...l, orden: 4 };
    out.push(formaProduccion(l));
    if (l.factura_id === FX('07') && l.orden === 1) extrasF07.push(...sinCasarF07(l).map(formaProduccion));
  }
  // Las líneas sin casar de F07 van tras las suyas (mismo orden que la consulta: factura_id, orden).
  const ultimaF07 = out.findLastIndex((x) => x.factura_id === FX('07'));
  out.splice(ultimaF07 + 1, 0, ...extrasF07);
  return valoresPorLinea(out.map((l) => {
    const a = AJUSTES_PDF_H5_7.find(([f, o]) => l.factura_id === f && l.orden === o);
    return a ? { ...l, ...a[2] } : l;
  }));
}
/**
 * H5-7: importes del PDF (facturas_albaranes_extraidos) ajustados para cubrir los estados por línea (todo ficticio):
 *  - F03 línea 1: el PDF trae 0,10 € más que Farmatic → DIFERENCIA en una línea casada (no Hefame);
 *  - F02 línea 6: el PDF no trae importe → NO_EVALUABLE con importe de Farmatic ("Sin importe del PDF para comparar");
 *  - F07 línea 5 (sin casar): el PDF no trae importe → NO_EVALUABLE sin Farmatic ("Sin contraparte en Farmatic").
 */
const AJUSTES_PDF_H5_7 = [
  [FX('03'), 1, { albaran_importe_total: 234.65 }],
  [FX('02'), 6, { albaran_importe_total: null, albaran_importe_base: null }],
  [FX('07'), 5, { albaran_importe_total: null, albaran_importe_base: null }],
];

/**
 * H5-7: detalle por línea como lo deja la migración 30 en producción (cf_detalles_por_linea,
 * 30_cf_detalle_por_linea.sql:43-70; espejo en conciliacion.py:695-730). En FIXTURES este generador hace de BD:
 *  - PDF = facturas_albaranes_extraidos.importe_total con signo (ABONO en negativo); movimiento: el importe aplicado;
 *  - Farmatic = importe aplicado, salvo movimiento o sin coincidencia (null);
 *  - diferencia = PDF − suma de lo aplicado en esa línea del PDF (R17: los dos detalles); sin coincidencia: = PDF;
 *    null si es movimiento o el PDF no trae importe;
 *  - estado: NO_EVALUABLE (movimiento o sin importe del PDF), DIFERENCIA (sin coincidencia), COINCIDE si |dif| ≤ 0,05.
 * Hefame (F05): el importe_total del PDF es la base neta y Farmatic va con IVA: la diferencia mezcla bases, como en producción.
 */
const r4 = (v) => Math.round(v * 10000) / 10000;
const CASADOS = ['UNO_A_UNO', 'UNO_A_VARIOS', 'VARIOS_A_UNO'];
function valoresPorLinea(ls) {
  const suma = new Map();
  for (const l of ls) {
    if (!CASADOS.includes(l.tipo_relacion)) continue;
    const k = `${l.factura_id}|${l.factura_albaran_extraido_id}`;
    suma.set(k, r4((suma.get(k) ?? 0) + l.importe_aplicado));
  }
  return ls.map((l) => {
    const mov = l.tipo_relacion === 'MOVIMIENTO_NO_FARMATIC';
    const sin = l.tipo_relacion === 'SIN_COINCIDENCIA';
    const t = l.albaran_importe_total;
    const documental = mov || t === null ? null : l.sentido_documental === 'ABONO' ? -Math.abs(r4(t)) : r4(t);
    const dif = mov || documental === null ? null : sin ? documental
      : r4(documental - (suma.get(`${l.factura_id}|${l.factura_albaran_extraido_id}`) ?? 0));
    return {
      ...l,
      // null nunca se convierte en 0 (en la BD, round(null) = null).
      importe_documental: mov ? (l.importe_aplicado === null ? null : r4(l.importe_aplicado)) : documental,
      importe_farmatic: mov || sin || l.importe_aplicado === null ? null : r4(l.importe_aplicado),
      diferencia: dif,
      estado_linea: mov || documental === null ? 'NO_EVALUABLE' : sin ? 'DIFERENCIA' : Math.abs(dif) <= 0.05 ? 'COINCIDE' : 'DIFERENCIA',
    };
  });
}
const extrasF07 = [];
/** Impuestos: un tramo por factura con base e IVA conocidos (IVA 10 % y recargo 1,4 %, los de los totales H3a). */
function impuestosH5(r) {
  if (r.base_imponible_total === null || r.iva_total === null) return [];
  const re = r.recargo_equivalencia_total;
  if (r.factura_id === F05_SIN_TIPOS_FISCALES) {
    return [{
      id: `90000000-0000-4000-8000-0000000000${r.factura_id.slice(-2)}`, orden: 1, concepto: null,
      base_imponible: r.base_imponible_total, tipo_iva: null, cuota_iva: r.iva_total,
      tipo_recargo_equivalencia: null, cuota_recargo_equivalencia: re,
      total_tramo: Math.round((r.base_imponible_total + r.iva_total + (re ?? 0)) * 100) / 100, literal: null,
    }];
  }
  return [{
    id: `90000000-0000-4000-8000-0000000000${r.factura_id.slice(-2)}`, orden: 1, concepto: 'IVA 10 %',
    base_imponible: r.base_imponible_total, tipo_iva: 10, cuota_iva: r.iva_total,
    tipo_recargo_equivalencia: re === null ? null : 1.4, cuota_recargo_equivalencia: re,
    total_tramo: Math.round((r.base_imponible_total + r.iva_total + (re ?? 0)) * 100) / 100, literal: null,
  }];
}

const lineas = lineasH5(lineasH3a.map(({ farmacia, es_actual, ...r }) => r)); // eslint-disable-line no-unused-vars
const incidenciasAbiertas = incidenciasH3a.filter((i) => i.estado === 'ABIERTA').map(sinFarmacia);
const luna = detalle.filter((r) => r.uso_luna);

const comunes = {
  documentos,
  facturas,
  vencimientos,
  lineas,
  incidencias_abiertas: incidenciasAbiertas,
  luna_mes: [{ ejecuciones_luna: luna.length, coste_luna: luna.reduce((a, r) => a + (r.coste_luna ?? 0), 0) || null }],
  proveedores: [...proveedoresH3a.map((p) => ({
    id: p.id, codigo: p.codigo, nombre: p.nombre, farmatic_id_proveedor: p.farmatic_id_proveedor,
    extractor_codigo: p.extractor_codigo, nivel_confianza: p.nivel_confianza, activo: p.activo, alias: p.alias ?? [],
  })), sinFarmacia(PROVEEDOR_BEIERSDORF)].sort((a, b) => a.nombre.localeCompare(b.nombre)),
  configuracion: h3a('configuracion'),
  alertas_albaran_no_en_farmatic: ALERTA_AUSENTE,
  alertas_duplicado_farmatic: ALERTA_DUPLICADO,
  alertas_correcciones_aprobadas: ALERTA_CORRECCIONES,
};

function filasDetalle(r) {
  const id = r.factura_id;
  const ls = lineas.filter((l) => l.factura_id === id);
  const historial = [...historialH3a.map(sinFarmacia), ...HISTORIAL_H3B]
    .filter((h) => h.factura_id === id || (h.factura_id === null && h.documento_id === r.documento_id))
    .sort((a, b) => a.created_at.localeCompare(b.created_at) || a.evento_id - b.evento_id);
  return {
    factura_cabecera: [{
      ...filaFactura(r),
      // Forma del motor: cada campo documentado es { valor, ... } (H4c: CIF en proveedor.nif.valor).
      datos_extraidos: {
        ...FICTICIO,
        numero_factura: { valor: r.numero_factura }, fecha_factura: { valor: { iso: r.fecha_factura } },
        tipo_documento: r.tipo_documento_documental === null ? null : { valor: r.tipo_documento_documental },
        proveedor: { nombre: { valor: r.proveedor_literal }, nif: r.proveedor_nif_documental === null ? null : { valor: r.proveedor_nif_documental } },
        totales: { base_imponible: { valor: r.base_imponible_total }, iva: { valor: r.iva_total },
          recargo_equivalencia: { valor: r.recargo_equivalencia_total }, total: { valor: r.importe_total } },
      },
    }],
    factura_lineas: ls,
    factura_impuestos: impuestosH5(r),
    factura_vencimientos: vencimientos.filter((v) => v.factura_id === id),
    // Una fila por albarán documental (R17: dos detalles con el mismo origen).
    factura_albaranes_extraidos: ls.filter((l, i) => l.factura_albaran_extraido_id
      && ls.findIndex((x) => x.factura_albaran_extraido_id === l.factura_albaran_extraido_id) === i).map((l) => ({
      id: l.factura_albaran_extraido_id, orden: l.orden, numero_albaran: l.numero_albaran_documental,
      fecha_albaran: l.fecha_albaran_documental, tipo_movimiento: l.sentido_documental, importe_base: l.albaran_importe_base,
      importe_total: l.albaran_importe_total, descripcion: null, literal: null,
    })),
    factura_movimientos: ls.filter((l) => l.factura_movimiento_id).map((l) => ({
      id: l.factura_movimiento_id, orden: l.orden, ...MOVIMIENTOS[l.factura_movimiento_id],
      base: base114(l.importe_movimiento_fixture), iva: null, recargo_equivalencia: null, importe: l.importe_movimiento_fixture,
      independiente: true, conciliable_farmatic: false,
    })),
    factura_ajustes: [],
    factura_incidencias: incidenciasH3a.filter((i) => i.factura_id === id || i.documento_id === r.documento_id).map(sinFarmacia),
    factura_historial: historial,
    factura_otras_pdf: detalle.filter((x) => x.documento_id === r.documento_id && x.factura_id !== id)
      .sort((a, b) => a.pagina_inicio - b.pagina_inicio)
      .map((x) => ({ factura_id: x.factura_id, numero_factura: x.numero_factura, pagina_inicio: x.pagina_inicio, pagina_fin: x.pagina_fin })),
  };
}

// ---------------------------------------------------------------------------
// DTO
// ---------------------------------------------------------------------------

export function generar() {
  const detalles = {};
  for (const r of detalle) detalles[r.factura_id] = construir.facturaDetalle(filasDetalle(r), GENERADO_AT);
  return {
    'inicio.json': construir.inicio(comunes, GENERADO_AT),
    'facturas.json': construir.facturas(comunes, GENERADO_AT),
    'factura_detalle.json': detalles,
    'conciliacion_bandeja.json': construir.conciliacionBandeja(comunes, GENERADO_AT),
    'vencimientos.json': construir.vencimientos(comunes, GENERADO_AT),
    'cashflow_semanas.json': construir.cashflowSemanas(comunes, GENERADO_AT),
    'proveedores.json': construir.proveedores(comunes, GENERADO_AT),
    'configuracion.json': construir.configuracion(comunes, GENERADO_AT),
  };
}

if (import.meta.main) {
  mkdirSync(DTO, { recursive: true });
  for (const [fichero, dto] of Object.entries(generar())) {
    writeFileSync(join(DTO, fichero), JSON.stringify(dto, null, 2) + '\n', 'utf8');
    console.log(`escrito dto/${fichero}`);
  }
}
