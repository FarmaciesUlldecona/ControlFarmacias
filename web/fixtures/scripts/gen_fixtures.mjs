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
import { construir } from '../../app/server/contrato.ts';

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
const CIF_H4B = { [P(1)]: 'A00000001', [P(2)]: 'B00000002', [P(3)]: 'B00000003', [P(4)]: null };
/** F02: mismo CIF que Alliance escrito con guion y minúscula, y otro literal → alias del grupo. */
const AJUSTES_FACTURA_H4B = {
  'f0000000-0000-4000-8000-000000000002': { proveedor_cif: 'b-00000003', proveedor_literal: 'Alliance Healthcare España' },
};
/** Incidencia INFO (solo en el detalle de factura; nunca en Inicio). */
export const INCIDENCIAS_H4B = [{
  incidencia_id: '20000000-0000-4000-8000-000000000041', farmacia: 'PIO', documento_id: null,
  factura_id: 'f0000000-0000-4000-8000-000000000002', numero_factura: 'AL-26-100577',
  archivo_nombre: 'Alliance_AL-26-100577.pdf', codigo: 'MONEDA_NO_DOCUMENTADA', categoria: 'DATOS_DOCUMENTALES', severidad: 'INFO',
  bloqueante: false, estado: 'ABIERTA', mensaje_usuario: 'La moneda no consta en el documento; se asume EUR.',
  detalle_tecnico: { ...FICTICIO, fuente: 'FIXTURE_H4B' }, created_at: '2026-10-25T21:06:00+00:00',
  resuelta_at: null, resuelta_por: null,
}];

const detalle = h3a('factura_detalle').map((r) => ({
  ...r,
  proveedor_cif: Object.hasOwn(CIF_H4B, r.proveedor_id) ? CIF_H4B[r.proveedor_id] : r.proveedor_cif,
  ...(AJUSTES_FACTURA_H4B[r.factura_id] ?? {}),
}));
const lineasH3a = h3a('conciliacion_lineas').filter((l) => l.es_actual);
const incidenciasH3a = [...h3a('incidencias'), ...INCIDENCIAS_H4B];
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
    // CIF y literal de la primera factura del PDF que los tenga (como la consulta `documentos`).
    const fs = detalle.filter((f) => f.documento_id === d.documento_id).sort((a, b) => a.pagina_inicio - b.pagina_inicio);
    const proveedor_cif = fs.find((f) => f.proveedor_cif)?.proveedor_cif ?? null;
    const proveedor_literal = fs.find((f) => f.proveedor_literal)?.proveedor_literal ?? null;
    return { ...sinFarmacia(d), proveedor_id, proveedor, proveedor_cif, proveedor_literal };
  }),
  ...[...DOCUMENTOS_H3B, DOCUMENTO_REVISION].map((d) => ({
    ...d, proveedor: d.proveedor_id ? nombreProveedor.get(d.proveedor_id) : null, proveedor_cif: null, proveedor_literal: null,
  })),
].sort((a, b) => b.fecha_importacion.localeCompare(a.fecha_importacion) || a.documento_id.localeCompare(b.documento_id));

const facturas = detalle.map(filaFactura)
  .sort((a, b) => (b.fecha_factura ?? '').localeCompare(a.fecha_factura ?? '') || a.factura_id.localeCompare(b.factura_id));
const vencimientos = vencimientosH3a.map(({ farmacia, importe_conocido, estado_pago, provenance, ...r }) => r); // eslint-disable-line no-unused-vars
const lineas = lineasH3a.map(({ farmacia, es_actual, ...r }) => r); // eslint-disable-line no-unused-vars
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
      datos_extraidos: {
        ...FICTICIO,
        numero_factura: r.numero_factura, fecha_factura: r.fecha_factura, tipo_documento: r.tipo_documento,
        proveedor: { nombre: r.proveedor_literal, nif: r.proveedor_cif },
        totales: { base: r.base_imponible_total, iva: r.iva_total, recargo: r.recargo_equivalencia_total, total: r.importe_total },
      },
    }],
    factura_lineas: ls,
    factura_impuestos: [],
    factura_vencimientos: vencimientos.filter((v) => v.factura_id === id),
    factura_albaranes_extraidos: ls.filter((l) => l.factura_albaran_extraido_id).map((l) => ({
      id: l.factura_albaran_extraido_id, orden: l.orden, numero_albaran: l.numero_albaran_documental,
      fecha_albaran: l.fecha_albaran_documental, tipo_movimiento: l.sentido_documental, importe_base: null,
      importe_total: l.importe_documental, descripcion: null, literal: null,
    })),
    factura_movimientos: ls.filter((l) => l.factura_movimiento_id).map((l) => ({
      id: l.factura_movimiento_id, orden: l.orden, ...MOVIMIENTOS[l.factura_movimiento_id],
      base: null, iva: null, recargo_equivalencia: null, importe: l.importe_documental,
      independiente: true, conciliable_farmatic: false,
    })),
    factura_ajustes: [],
    factura_incidencias: incidenciasH3a.filter((i) => i.factura_id === id || i.documento_id === r.documento_id).map(sinFarmacia),
    factura_historial: historial,
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
