// H8 (migración 36): R20 (albarán partido en Farmatic) y «para revisar» de la noche automática. Puro: sin BD.
import assert from 'node:assert/strict';
import { describe, test } from 'node:test';
import {
  CONSULTAS, CONSULTAS_CHECK, CONSULTAS_POR_BLOQUE, ETIQUETAS_ESTADO_MATCHING, OBJETOS_PERMITIDOS, construirRevisarNoche,
  formatoDiferenciaNoche, resumenCasado, type DocumentoPdf, type FacturaResumen, type LineaConciliacion,
} from '../contrato.ts';
import { claveCasado, codigoReglaDesconocido, esR20, importeFarmaticLinea, lineasConDiferencia, numerosR20, tipoCasado, textoEstadoMatching } from '../detalle.ts';
import { COLUMNAS_NOCHE, NOMBRES_DIAGNOSTICO, resumenNoche } from '../adaptador_real.ts';

const FA = 'f0000000-0000-4000-8000-0000000000a1';
const DOC = 'd0000000-0000-4000-8000-0000000000d1';

function linea(extra: Partial<LineaConciliacion>): LineaConciliacion {
  return {
    factura_id: FA, conciliacion_id: 'c1', intento: 1, detalle_id: 'x', orden: 1, tipo_relacion: 'UNO_A_VARIOS', estado_linea: 'COINCIDE',
    estado_matching: 'MATCH_R20', coincidencia_numero: null, clase_numero: 'EXACTA', coincidencia_numero_literal: true,
    factura_albaran_extraido_id: 'alb-1', factura_movimiento_id: null, numero_albaran_documental: '08013495', fecha_albaran_documental: '2026-11-18',
    sentido_documental: 'CARGO', importe_documental: 100, albaran_farmacia: 'PIO', albaran_id_contador: 1, numero_albaran_farmatic: '08013495',
    fecha_albaran_farmatic: '2026-11-18', farmatic_id_proveedor: '2', importe_puc: 60, importe_pvp: 80, importe_farmatic: 60, importe_aplicado: 60,
    diferencia: 0, papel_r17: null, regla: 'R20', papel_r20: 'NUMERO', farmatic_proveedor: null, concepto_movimiento: null, categoria_movimiento: null,
    albaran_importe_total: 100, albaran_importe_base: null, magnitud_usada: null, ...extra,
  };
}
const exacto = linea({ detalle_id: 'a', orden: 1 });
const variante = linea({ detalle_id: 'b', orden: 2, papel_r20: 'LETRA_FINAL', clase_numero: 'LETRA_FINAL', coincidencia_numero_literal: false,
  numero_albaran_farmatic: '08D79747', albaran_id_contador: 2, importe_puc: 40, importe_farmatic: 40, importe_aplicado: 40 });

describe('H8-5: etiquetas de R21 y R22; código de regla desconocido', () => {
  test('R21 «Albarán con complementarios de la misma recepción» (verde) y R22 «Cargo anulado por su abono (neto 0)» (gris)', () => {
    const r21 = linea({ regla: 'R21', estado_matching: 'MATCH_UNICO', papel_r20: null });
    const r22 = linea({ regla: 'R22', tipo_relacion: 'MOVIMIENTO_NO_FARMATIC', estado_matching: null, papel_r20: null });
    assert.deepEqual([tipoCasado(r21).texto, tipoCasado(r21).color], ['Albarán con complementarios de la misma recepción', 'verde']);
    assert.deepEqual([tipoCasado(r22).texto, tipoCasado(r22).color], ['Cargo anulado por su abono (neto 0)', 'gris']);
    // Mandan sobre un estado del motor que la web no conoce (no «sin descripción»).
    assert.equal(claveCasado(linea({ regla: 'R21', estado_matching: 'MATCH_R21' })), 'R21:COMPLEMENTARIOS');
    assert.equal(claveCasado(linea({ regla: 'R22', estado_matching: 'MATCH_R22', tipo_relacion: 'UNO_A_UNO' })), 'R22:ANULADO');
    assert.deepEqual([codigoReglaDesconocido({ regla: 'R21' }), codigoReglaDesconocido({ regla: 'R22' })], [null, null]);
  });
  test('H7-REAL-8: MATCH_R21 es estado conocido (casado, texto llano y etiqueta fija del diagnóstico); otros estados nuevos, no_previsto', () => {
    assert.ok((ETIQUETAS_ESTADO_MATCHING as readonly string[]).includes('MATCH_R21'));
    assert.match(textoEstadoMatching('MATCH_R21') ?? '', /R21/);
    assert.equal(claveCasado(linea({ regla: null, estado_matching: 'MATCH_R21', papel_r20: null })), 'NUMERO:EXACTA'); // casado, no «sin descripción»
    assert.equal(claveCasado(linea({ regla: 'R21', estado_matching: 'MATCH_R21', papel_r20: null })), 'R21:COMPLEMENTARIOS');
    assert.equal(resumenCasado([{ eje: 'estado_matching', etiqueta: 'match_r21', n: '3' }])['estado_matching.match_r21'], 3);
    assert.throws(() => resumenCasado([{ eje: 'estado_matching', etiqueta: 'no_previsto:MATCH_R21', n: '1' }]));
    assert.equal(resumenCasado([{ eje: 'estado_matching', etiqueta: 'no_previsto:MATCH_R22', n: '1' }])['estado_matching.no_previsto.MATCH_R22'], 1);
    assert.equal(claveCasado(linea({ regla: null, estado_matching: 'MATCH_R23', papel_r20: null })), 'ESTADO:SIN_DESCRIPCION');
  });
  test('código de regla desconocido: se muestra tal cual y no cambia el «cómo casó» (nunca falla)', () => {
    const r23 = linea({ regla: 'R23', estado_matching: 'MATCH_UNICO', papel_r20: null });
    assert.equal(codigoReglaDesconocido(r23), 'R23');
    assert.equal(claveCasado(r23), 'NUMERO:EXACTA');
    assert.doesNotThrow(() => tipoCasado(linea({ regla: '  ', estado_matching: 'MATCH_UNICO' })));
    assert.deepEqual([codigoReglaDesconocido({ regla: null }), codigoReglaDesconocido({}), codigoReglaDesconocido({ regla: 'R17' }), codigoReglaDesconocido({ regla: 'R20' })], [null, null, null, null]);
  });
});

describe('H8: R20 en el detalle', () => {
  test('«Cómo casó»: «Albarán partido en Farmatic»; secundario, los dos números (el exacto primero); fuente migración 36', () => {
    assert.equal(claveCasado(exacto), 'R20:PARTIDO');
    assert.equal(claveCasado(variante), 'R20:PARTIDO');
    const c = tipoCasado(variante, [variante, exacto]);
    assert.equal(c.texto, 'Albarán partido en Farmatic');
    assert.equal(c.color, 'verde');
    assert.equal(c.fuente, 'migración 36');
    assert.equal(c.relacion_texto, '08013495 / 08D79747');
    assert.match(textoEstadoMatching('MATCH_R20') ?? '', /R20/);
  });
  test('la regla distingue R20 de R17 (mismo tipo_relacion UNO_A_VARIOS)', () => {
    const r17 = linea({ estado_matching: 'MATCH_R17', regla: 'R17', papel_r20: null, papel_r17: 'NUMERO' });
    assert.equal(esR20(r17), false);
    assert.equal(claveCasado(r17), 'NUMERO:EXACTA');
    assert.match(tipoCasado(r17).relacion_texto, /R17/);
    assert.equal(esR20(linea({ estado_matching: 'MATCH_R20', regla: null })), true);
    assert.equal(esR20(linea({ estado_matching: 'MATCH_UNICO', regla: 'R20' })), true);
  });
  test('sin papel_r20, el exacto es el de coincidencia literal; sin número, «sin número»', () => {
    const a = { ...exacto, papel_r20: null };
    const b = { ...variante, papel_r20: null, numero_albaran_farmatic: null };
    assert.equal(numerosR20([b, a]), '08013495 / sin número');
  });
  test('importe de Farmatic de la línea = suma de las dos filas; si falta una, null (nunca 0)', () => {
    assert.equal(importeFarmaticLinea([exacto, variante]), 100);
    assert.equal(importeFarmaticLinea([exacto, { ...variante, importe_farmatic: null }]), null);
    assert.equal(importeFarmaticLinea([]), null);
  });
  test('«N albaranes con diferencia» cuenta la línea R20 una vez', () => {
    const dif = { estado_linea: 'DIFERENCIA', diferencia: 1.21 };
    assert.deepEqual(lineasConDiferencia([{ ...exacto, ...dif }, { ...variante, ...dif }]), { total: 1, sinCasar: 0 });
  });
  test('consulta de líneas: papel_r20 de provenance; MATCH_R20 es etiqueta fija del diagnóstico de casado', () => {
    assert.match(CONSULTAS.factura_lineas.sql, /cd\.provenance ->> 'papel_r20' as papel_r20/);
    assert.ok((ETIQUETAS_ESTADO_MATCHING as readonly string[]).includes('MATCH_R20'));
    const d = resumenCasado([{ eje: 'estado_matching', etiqueta: 'match_r20', n: '2' }]);
    assert.equal(d['estado_matching.match_r20'], 2);
    assert.throws(() => resumenCasado([{ eje: 'estado_matching', etiqueta: 'no_previsto:MATCH_R20', n: '1' }]));
  });
  test('configuración: conciliacion_r20 leída de cf_configuracion', () => {
    assert.match(CONSULTAS.configuracion.sql, /c\.conciliacion_r20/);
  });
});

describe('H8: diferencia simulada de la noche (valor del motor, sin recalcular)', () => {
  const casos: [unknown, string | null][] = [
    ['118.1600', '118,16'], ['0.0349', '0,0349'], ['2.0350', '2,0350'], ['-1234.5000', '-1.234,50'], ['5', '5,00'], ['12.3', '12,30'],
    ['1234567.0100', '1.234.567,01'], ['0.0000', '0,00'], [7.25, '7,25'], ['118.16001', null], ['118.160000', '118,16'],
    ['abc', null], ['1,5', null], [null, null], [undefined, null], ['', null],
  ];
  for (const [v, esperado] of casos) test(`${JSON.stringify(v)} → ${esperado}`, () => assert.equal(formatoDiferenciaNoche(v), esperado));
});

const factura = (id: string, numero: string): FacturaResumen => ({ factura_id: id, documento_id: DOC, numero_factura: numero, proveedor_cif: null,
  proveedor_nif_documental: null, proveedor_literal: 'ALLIANCE', proveedor: 'ALLIANCE' }) as unknown as FacturaResumen;
const documento = (id: string): DocumentoPdf => ({ documento_id: id, archivo_nombre: 'defecto.pdf' }) as unknown as DocumentoPdf;

describe('H8: «para revisar» de la noche', () => {
  const facts = [factura(FA, 'AL-1')];
  const docs = [documento(DOC)];
  test('sin noches: fecha null (la pantalla dice que todavía no hay ninguna)', () => {
    assert.deepEqual(construirRevisarNoche([], facts, docs).fecha, null);
  });
  test('noche sin elementos: lista vacía y válida («Nada para revisar en la noche del dd/mm»)', () => {
    const r = construirRevisarNoche([{ fecha: '2026-11-19', para_revisar: [] }], facts, docs);
    assert.equal(r.fecha, '2026-11-19');
    assert.equal(r.lista_valida, true);
    assert.equal(r.elementos.length, 0);
  });
  test('para_revisar null o que no es lista: lista_valida false (falla cerrado: nunca «nada para revisar»)', () => {
    for (const p of [null, { tipo: 'DIFERENCIA' }, 'texto']) {
      const r = construirRevisarNoche([{ fecha: '2026-11-19', para_revisar: p }], facts, docs);
      assert.equal(r.lista_valida, false);
      assert.equal(r.elementos.length, 0);
    }
    // jsonb como texto (otro cliente pg): se interpreta.
    assert.equal(construirRevisarNoche([{ fecha: '2026-11-19', para_revisar: '[]' }], facts, docs).lista_valida, true);
  });
  test('solo PIO: factura o documento de PIO; el resto (u sin id) no sale', () => {
    const r = construirRevisarNoche([{ fecha: '2026-11-19', para_revisar: [
      { tipo: 'DIFERENCIA', factura_id: FA.toUpperCase(), numero_factura: 'AL-1', diferencia: '118.1600', resultado_simulado: 'DIFERENCIA', fallo: null, r18: null },
      { tipo: 'DIFERENCIA', factura_id: 'f0000000-0000-4000-8000-0000000000ff', diferencia: '1.0000' },
      { tipo: 'DEFECTO', documento_id: DOC, estado: 'ERROR', intentos: 1, ejecucion: 'e1' },
      { tipo: 'DEFECTO', documento_id: 'd0000000-0000-4000-8000-0000000000ff', intentos: 2 },
      { tipo: 'NO_ALLIANCE' },
      'no es objeto',
    ] }], facts, docs);
    assert.deepEqual(r.elementos.map((e) => e.texto), ['Diferencia simulada de 118,16 €', 'Documento con defecto tras 1 intento']);
    assert.equal(r.elementos[0].enlace, `/facturas/${FA}`);
    assert.equal(r.elementos[1].enlace, '/facturas');
    assert.equal(r.elementos[1].archivo_nombre, 'defecto.pdf');
    assert.deepEqual(r.elementos[0].evidencia, { diferencia: '118.1600', resultado_simulado: 'DIFERENCIA', fallo: null, r18: null });
    assert.deepEqual(r.por_tipo, { DIFERENCIA: 1, NO_ALLIANCE: 0, R18_PENDIENTE: 0, DEFECTO: 1, OTRO: 0 });
  });
  test('textos llanos por tipo; R18 con fallo y r18 en la evidencia; tipo no previsto sin significado inventado', () => {
    const r = construirRevisarNoche([{ fecha: '2026-11-19', para_revisar: [
      { tipo: 'R18_PENDIENTE', factura_id: FA, fallo: 'F', r18: { estado: 'X' } },
      { tipo: 'NO_ALLIANCE', factura_id: FA },
      { tipo: 'DIFERENCIA', factura_id: FA, diferencia: 'ilegible' },
      { tipo: 'DEFECTO', documento_id: DOC, intentos: null },
      { tipo: 'NUEVO_TIPO', factura_id: FA },
      { tipo: 'valor raro', factura_id: FA },
    ] }], facts, docs);
    const t = Object.fromEntries(r.elementos.map((e) => [e.tipo_literal ?? e.tipo, e.texto]));
    assert.equal(t.R18_PENDIENTE, 'Pendiente de la regla R18');
    assert.equal(t.NO_ALLIANCE, 'Proveedor aún sin conciliación automática');
    assert.equal(t.DIFERENCIA, 'Diferencia simulada (valor en la evidencia técnica)');
    assert.equal(t.DEFECTO, 'Documento con defecto');
    assert.equal(t.NUEVO_TIPO, 'Elemento de la noche sin descripción (ver evidencia técnica)');
    assert.equal(r.elementos.find((e) => e.tipo === 'R18_PENDIENTE')?.evidencia.r18 && true, true);
    assert.equal(r.elementos.filter((e) => e.tipo === 'OTRO').length, 2);
    assert.ok(r.elementos.some((e) => e.tipo === 'OTRO' && e.tipo_literal === null)); // «valor raro» no es código: no se muestra
  });
  test('consulta: la noche más reciente; Inicio y Conciliación la cargan; objeto permitido', () => {
    assert.match(CONSULTAS.noche_revisar.sql, /order by n\.fecha desc\s+limit 1/);
    assert.ok(CONSULTAS_POR_BLOQUE.inicio.includes('noche_revisar'));
    assert.ok(CONSULTAS_POR_BLOQUE.conciliacionBandeja.includes('noche_revisar'));
    assert.ok(CONSULTAS_POR_BLOQUE.conciliacionBandeja.includes('documentos'));
    assert.ok((OBJETOS_PERMITIDOS as readonly string[]).includes('cf_noches_automaticas'));
  });
});

describe('H8: check:real, DIAGNOSTICO noche (solo números)', () => {
  const fila = { noches: '1', lista_no_valida: '0', elementos: '7', diferencia: '2', no_alliance: '1', r18_pendiente: '1', defecto: '1', otros_tipos: '1', fuera_de_pio: '1' };
  test('recuento por tipo de la última noche', () => {
    assert.ok(NOMBRES_DIAGNOSTICO.includes('noche'));
    assert.deepEqual(Object.keys(resumenNoche(fila)), COLUMNAS_NOCHE);
    assert.equal(resumenNoche(fila).diferencia, 2);
  });
  test('falla cerrado: valores que no son recuentos o que no cuadran', () => {
    assert.throws(() => resumenNoche({ ...fila, diferencia: 'dos' }), /DIAGNOSTICO_NO_ES_RECUENTO/);
    assert.throws(() => resumenNoche({ ...fila, elementos: '8' }), /INCOHERENTES/);
    assert.throws(() => resumenNoche({ ...fila, noches: '2' }), /INCOHERENTES/);
  });
  test('SQL: solo PIO por factura o documento; sin fechas ni ids en la salida', () => {
    const sql = CONSULTAS_CHECK.diagnostico_noche.sql;
    assert.match(sql, /f\.farmacia = \$1/);
    assert.match(sql, /d\.farmacia = \$1/);
    assert.match(sql, /jsonb_typeof\(ult\.para_revisar\) = 'array'/);
    assert.doesNotMatch(sql.split(/\bfrom p\b/)[0].split('select (select count(*) from ult)')[1] ?? '', /fecha|factura_id|documento_id/);
  });
});
