// H6 Vencimientos: estados de pago, forma de pago por proveedor (CIF; por defecto domiciliación; sin CIF = sin
// determinar, tratado como transferencia), marcas (una vigente por vencimiento, anular en vez de borrar, historial con
// autor), totales por semana y mes (cargos menos abonos; importe pendiente y sentido no documentado fuera), filtros,
// validación y API en FIXTURES. H6-REAL: vencimiento identificado por (factura_id, orden), estado A_REVISAR (marca que ya
// no coincide; huérfanas), reglas previas (sin fecha / sin importe no se marca). El adaptador REAL, en pagos_real.test.ts.
// npm run test:unit
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { after, describe, test } from 'node:test';
import { CLAVE_FIXTURES, USUARIO } from '../acceso.ts';
import { DIR_DTO } from '../adaptador_fixtures.ts';
import type { VencimientosDTO } from '../contrato.ts';
import { crearServidor } from '../index.ts';
import { vencimientoCashflow } from '../cashflow/rutas.ts';
import {
  BLOQUE_DE_ESTADO, DICCIONARIO_ESTADOS, ESTADOS_IMPLEMENTADOS, ESTADOS_PAGO, MAX_VENCIMIENTOS_PETICION,
  claveVencimiento, construirPantalla, crearAlmacenPagos, cumpleBusquedaPago, cumplePeriodo, diferenciasMarca, esCargoNegativo, estadoPago,
  filasPagos, formaEfectiva, formaPorDefectoMarca, hoyMadrid, motivoNoMarcable, prepararDomiciliados, prepararMarcas, textoEstadoPago,
  totalGeneral, totalesPorPeriodo, validarConfirmacion, validarDomiciliados, validarFormaProveedor, validarMarcar,
  type FilaTotal, type FilaVencimientoPago, type FormaPago, type MarcaPago, type SemillaPagos,
} from '../pagos/pagos.ts';
import { esEscrituraPagos, leerSemillaPagos } from '../pagos/rutas.ts';

const V = (n: number) => `90000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const HOY = '2026-11-16';
const dto = (): VencimientosDTO => JSON.parse(readFileSync(join(DIR_DTO, 'vencimientos.json'), 'utf8')) as VencimientosDTO;
/** (factura_id, orden) de un vencimiento de los fixtures: lo que viaja en las peticiones (nunca el id). */
const id = (n: number) => { const v = dto().vencimientos.find((x) => x.vencimiento_id === V(n))!; return { factura_id: v.factura_id, orden: v.orden as number }; };
const clave = (n: number) => { const x = id(n); return claveVencimiento(x.factura_id, x.orden); };
function almacen(semilla: SemillaPagos = leerSemillaPagos()) {
  let n = 0;
  return crearAlmacenPagos(semilla, { ahora: () => '2026-11-16T10:00:00.000Z', nuevoId: () => `71000000-0000-4000-8000-${String(++n).padStart(12, '0')}` });
}
const filasFixtures = (marcas?: Map<string, MarcaPago>) => { const f = almacen().fuente(); return filasPagos(dto().vencimientos, f.formas, marcas ?? f.marcas, f.hoy); };
const copiaDe = (fs: FilaVencimientoPago[]) => (k: string) => fs.find((f) => f.clave === k);
const fila = (o: Partial<FilaTotal>): FilaTotal => ({ fecha_vencimiento: '2026-11-18', importe: 100, sentido: 'CARGO', estado_pago: 'PENDIENTE', forma_pago: 'TRANSFERENCIA', ...o });
const marca = (n: number, o: Partial<MarcaPago> = {}): MarcaPago => {
  const v = dto().vencimientos.find((x) => x.vencimiento_id === V(n))!;
  return {
    marca_id: `72000000-0000-4000-8000-${String(n).padStart(12, '0')}`, farmacia: 'PIO', factura_id: v.factura_id, vencimiento_orden: v.orden as number,
    fecha_vencimiento: (v.fecha_vencimiento ?? '2026-01-01').slice(0, 10), importe: v.importe ?? 1, fecha_pago: '2026-11-10', forma: 'TRANSFERENCIA',
    origen: 'MANUAL', anulada: false, creada_at: '2026-11-10T10:00:00.000Z', creada_por: 'Marc', anulada_at: null, anulada_por: null, ...o,
  };
};

describe('estados de pago', () => {
  test('pendiente, vencido sin pagar, domiciliado previsto y pagado a mano; el día de vencimiento aún no ha vencido', () => {
    assert.equal(estadoPago('2026-11-17', 'TRANSFERENCIA', false, HOY), 'PENDIENTE');
    assert.equal(estadoPago(HOY, 'TRANSFERENCIA', false, HOY), 'PENDIENTE');
    assert.equal(estadoPago('2026-11-15', 'TRANSFERENCIA', false, HOY), 'VENCIDO_SIN_PAGAR');
    for (const f of ['EFECTIVO', 'COMPENSACION_ABONO', 'SIN_DETERMINAR'] as const) assert.equal(estadoPago('2026-11-15', f, false, HOY), 'VENCIDO_SIN_PAGAR', f);
    assert.equal(estadoPago('2026-11-15', 'DOMICILIACION', false, HOY), 'DOMICILIADO_PREVISTO');
    assert.equal(estadoPago('2026-11-15', 'DOMICILIACION', true, HOY), 'PAGADO_MANUAL');
    assert.equal(estadoPago('2026-12-15', 'TRANSFERENCIA', true, HOY), 'PAGADO_MANUAL'); // pagado por adelantado
    assert.equal(estadoPago(null, 'TRANSFERENCIA', false, HOY), 'PENDIENTE'); // sin fecha: no se afirma que haya vencido
  });
  test('H6-3: abono vencido sin marca = ABONO_PENDIENTE_COMPENSAR (nunca rojo ni domiciliado); marcado = «compensado / cobrado»', () => {
    for (const f of ['TRANSFERENCIA', 'DOMICILIACION', 'SIN_DETERMINAR', 'COMPENSACION_ABONO'] as const) {
      assert.equal(estadoPago('2026-11-10', f, false, HOY, 'ABONO'), 'ABONO_PENDIENTE_COMPENSAR', f);
    }
    assert.equal(estadoPago('2026-11-20', 'DOMICILIACION', false, HOY, 'ABONO'), 'PENDIENTE');
    assert.equal(estadoPago('2026-11-10', 'DOMICILIACION', true, HOY, 'ABONO'), 'PAGADO_MANUAL');
    assert.equal(estadoPago('2026-11-10', 'DOMICILIACION', false, HOY, 'NO_DOCUMENTADO'), 'DOMICILIADO_PREVISTO');
    assert.equal(textoEstadoPago('PAGADO_MANUAL', 'ABONO'), 'compensado / cobrado (marcado a mano)');
    assert.equal(textoEstadoPago('PAGADO_MANUAL', 'CARGO'), 'pagado (marcado a mano)');
    assert.equal(textoEstadoPago('ABONO_PENDIENTE_COMPENSAR', 'ABONO'), 'Abono pendiente de compensar');
    assert.equal(formaPorDefectoMarca({ sentido: 'ABONO', forma_pago: 'DOMICILIACION' }), 'COMPENSACION_ABONO');
    assert.equal(formaPorDefectoMarca({ sentido: 'ABONO', forma_pago: 'SIN_DETERMINAR' }), 'COMPENSACION_ABONO');
    assert.equal(formaPorDefectoMarca({ sentido: 'CARGO', forma_pago: 'TRANSFERENCIA' }), 'TRANSFERENCIA');
  });
  test('H6-3: cargo con importe negativo: sigue siendo cargo, con aviso; un abono negativo no lo es', () => {
    assert.equal(esCargoNegativo({ sentido: 'CARGO', importe: -25 }), true);
    assert.equal(esCargoNegativo({ sentido: 'CARGO', importe: 0 }), false);
    assert.equal(esCargoNegativo({ sentido: 'CARGO', importe: null }), false);
    assert.equal(esCargoNegativo({ sentido: 'ABONO', importe: -25 }), false);
    assert.equal(esCargoNegativo({ sentido: 'NO_DOCUMENTADO', importe: -25 }), false);
  });
  test('forma por CIF: configurada, por defecto domiciliación, sin CIF sin determinar', () => {
    const formas = new Map<string, FormaPago>([['B00000003', 'TRANSFERENCIA']]);
    assert.deepEqual(formaEfectiva('B00000003', formas), { forma: 'TRANSFERENCIA', por_defecto: false, sin_cif: false });
    assert.deepEqual(formaEfectiva('A00000001', formas), { forma: 'DOMICILIACION', por_defecto: true, sin_cif: false });
    assert.deepEqual(formaEfectiva(null, formas), { forma: 'SIN_DETERMINAR', por_defecto: false, sin_cif: true });
  });
  test('diccionario: A_REVISAR naranja («a revisar», nunca pagado); PAGADO_BANCO reservado; domiciliado con color propio', () => {
    assert.deepEqual([...ESTADOS_PAGO], ['PENDIENTE', 'VENCIDO_SIN_PAGAR', 'DOMICILIADO_PREVISTO', 'ABONO_PENDIENTE_COMPENSAR', 'A_REVISAR', 'PAGADO_MANUAL', 'PAGADO_BANCO']);
    assert.equal(DICCIONARIO_ESTADOS.PAGADO_BANCO.implementado, false);
    assert.deepEqual([...ESTADOS_IMPLEMENTADOS], ['PENDIENTE', 'VENCIDO_SIN_PAGAR', 'DOMICILIADO_PREVISTO', 'ABONO_PENDIENTE_COMPENSAR', 'A_REVISAR', 'PAGADO_MANUAL']);
    assert.deepEqual([DICCIONARIO_ESTADOS.A_REVISAR.texto, DICCIONARIO_ESTADOS.A_REVISAR.color], ['a revisar', 'naranja']);
    assert.ok(!/pagado \(/.test(DICCIONARIO_ESTADOS.A_REVISAR.texto));
    assert.equal(textoEstadoPago('A_REVISAR', 'ABONO'), 'a revisar');
    assert.equal(DICCIONARIO_ESTADOS.ABONO_PENDIENTE_COMPENSAR.color, 'azul');
    assert.equal(DICCIONARIO_ESTADOS.VENCIDO_SIN_PAGAR.color, 'rojo');
    assert.equal(DICCIONARIO_ESTADOS.DOMICILIADO_PREVISTO.color, 'domiciliado');
    assert.equal(DICCIONARIO_ESTADOS.PAGADO_MANUAL.texto, 'pagado (marcado a mano)');
  });
  test('fixtures (hoy 16/11/2026): estado, forma, clave (factura, orden) y marca de cada vencimiento', () => {
    const filas = filasFixtures();
    const por = Object.fromEntries(filas.map((x) => [Number(x.vencimiento_id.slice(-2)), [x.estado_pago, x.forma_pago]]));
    assert.deepEqual(por, {
      1: ['VENCIDO_SIN_PAGAR', 'TRANSFERENCIA'], // su marca de la semilla está anulada
      2: ['VENCIDO_SIN_PAGAR', 'TRANSFERENCIA'],
      3: ['DOMICILIADO_PREVISTO', 'DOMICILIACION'],
      4: ['DOMICILIADO_PREVISTO', 'DOMICILIACION'],
      5: ['DOMICILIADO_PREVISTO', 'DOMICILIACION'],
      6: ['PENDIENTE', 'DOMICILIACION'],
      7: ['PAGADO_MANUAL', 'TRANSFERENCIA'],
      8: ['PENDIENTE', 'SIN_DETERMINAR'],
      9: ['PENDIENTE', 'DOMICILIACION'],
      10: ['VENCIDO_SIN_PAGAR', 'TRANSFERENCIA'],
      11: ['DOMICILIADO_PREVISTO', 'DOMICILIACION'], // H6-3: cargo negativo (estado normal; aviso y fuera de totales)
      12: ['ABONO_PENDIENTE_COMPENSAR', 'DOMICILIACION'], // H6-3: abono vencido
      13: ['PENDIENTE', 'SIN_DETERMINAR'], // H6-REAL: sin CIF y con importe (sí se puede marcar)
    });
    assert.deepEqual(filas.filter((x) => x.cargo_negativo).map((x) => x.vencimiento_id), [V(11)]);
    const v7 = filas.find((x) => x.vencimiento_id === V(7))!;
    assert.equal(v7.clave, 'f0000000-0000-4000-8000-000000000005#1');
    assert.deepEqual(v7.marca && [v7.marca.fecha_pago, v7.marca.forma, v7.marca.creada_por, v7.marca.diferencias], ['2026-11-09', 'TRANSFERENCIA', 'Marc', []]);
    assert.equal(filas.find((x) => x.vencimiento_id === V(8))?.sin_cif, true);
    assert.equal(filas.find((x) => x.vencimiento_id === V(6))?.forma_por_defecto, true);
    // No marcables: los dos sin importe (V6, V8). Los importes no cambian: el null sigue null.
    assert.deepEqual(filas.filter((x) => x.no_marcable).map((x) => [x.vencimiento_id.slice(-2), x.no_marcable]), [['06', 'SIN_IMPORTE'], ['08', 'SIN_IMPORTE']]);
    assert.equal(filas.find((x) => x.vencimiento_id === V(6))?.importe, null);
  });
  test('un vencido sin CIF sale rojo (tratado como transferencia)', () => {
    const [x] = filasPagos([{ ...dto().vencimientos.find((v) => v.vencimiento_id === V(13))!, fecha_vencimiento: '2026-11-10' }], new Map(), new Map(), HOY);
    assert.deepEqual([x.estado_pago, x.forma_pago, x.sin_cif], ['VENCIDO_SIN_PAGAR', 'SIN_DETERMINAR', true]);
  });
});

describe('H6-REAL: A_REVISAR y marcas huérfanas', () => {
  test('diferencias: fecha (día) e importe (al céntimo); sin fecha o sin importe actuales también difieren', () => {
    const m = { fecha_vencimiento: '2026-11-11', importe: 472.22 };
    assert.deepEqual(diferenciasMarca(m, { fecha_vencimiento: '2026-11-11', importe: 472.22 }), []);
    assert.deepEqual(diferenciasMarca(m, { fecha_vencimiento: '2026-11-11T00:00:00', importe: 472.224 }), []);
    assert.deepEqual(diferenciasMarca(m, { fecha_vencimiento: '2026-11-12', importe: 472.22 }), ['FECHA']);
    assert.deepEqual(diferenciasMarca(m, { fecha_vencimiento: '2026-11-11', importe: 427.22 }), ['IMPORTE']);
    assert.deepEqual(diferenciasMarca(m, { fecha_vencimiento: null, importe: null }), ['FECHA', 'IMPORTE']);
    assert.equal(estadoPago('2026-11-11', 'TRANSFERENCIA', true, HOY, 'CARGO', true), 'A_REVISAR');
    assert.equal(estadoPago('2026-11-11', 'TRANSFERENCIA', true, HOY, 'ABONO', true), 'A_REVISAR');
  });
  test('marca vigente cuyo importe o fecha copiados ya no coinciden: A_REVISAR, nunca pagado; ni totales, ni cabecera, ni cashflow', () => {
    const marcas = new Map([
      [clave(2), marca(2, { importe: 427.22 })], // importe cambiado
      [clave(10), marca(10, { fecha_vencimiento: '2026-11-03' })], // fecha cambiada
      [clave(7), marca(7)], // coincide
    ]);
    const filas = filasFixtures(marcas);
    const v2 = filas.find((f) => f.vencimiento_id === V(2))!;
    assert.deepEqual([v2.estado_pago, v2.marca?.diferencias, v2.marca?.importe], ['A_REVISAR', ['IMPORTE'], 427.22]);
    assert.deepEqual(filas.find((f) => f.vencimiento_id === V(10))!.marca?.diferencias, ['FECHA']);
    assert.equal(filas.find((f) => f.vencimiento_id === V(7))!.estado_pago, 'PAGADO_MANUAL');
    const t = totalGeneral(filas);
    assert.deepEqual(t.revisar, { neto: 624.59, cargos: 624.59, abonos: null, vencimientos: 2 });
    assert.equal(t.pagado.vencimientos, 0); // V7 pagado, pero de sentido no documentado: no suma
    assert.equal(filas.filter((f) => f.estado_pago === 'PAGADO_MANUAL').length, 1);
    // Cashflow (H7): la marca a revisar no da fecha de pago (no cuenta como pagado).
    assert.equal(vencimientoCashflow(v2).fecha_pago, null);
    assert.equal(vencimientoCashflow(filas.find((f) => f.vencimiento_id === V(7))!).fecha_pago, '2026-11-10');
    // Atrasados: sigue atrasado (no está pagado).
    assert.equal(cumplePeriodo(v2, 'atrasados', HOY), true);
    // Pantalla: cuenta a revisar y no es pagado del proveedor.
    const p = construirPantalla(dto(), { hoy: HOY, formas: almacen().fuente().formas, marcas, historial: [] }, { modo: 'REAL' });
    assert.equal(p.a_revisar, 2);
    assert.equal(p.proveedores.find((x) => x.cif === 'B00000003')?.sin_pagar, 3);
  });
  test('marca huérfana (su vencimiento ya no existe): fuera de las filas, en marcas_huerfanas y cuenta como «a revisar»', () => {
    const huerfana = marca(4, { vencimiento_orden: 9, marca_id: '72000000-0000-4000-8000-000000000099' });
    const marcas = new Map([[claveVencimiento(huerfana.factura_id, 9), huerfana], [clave(7), marca(7)]]);
    const p = construirPantalla(dto(), { hoy: HOY, formas: new Map(), marcas, historial: [] }, { modo: 'REAL' });
    assert.equal(p.filas.filter((f) => f.marca !== null).length, 1);
    assert.equal(p.marcas_huerfanas.length, 1);
    assert.deepEqual([p.marcas_huerfanas[0].vencimiento_orden, p.marcas_huerfanas[0].numero_factura, p.marcas_huerfanas[0].diferencias],
      [9, 'CF-2026-55811', ['FECHA', 'IMPORTE']]);
    assert.equal(p.a_revisar, 1);
  });
  test('reglas previas: sin orden, sin fecha o sin importe no se marca', () => {
    const base = dto().vencimientos.find((v) => v.vencimiento_id === V(2))!;
    assert.equal(motivoNoMarcable(base), null);
    assert.equal(motivoNoMarcable({ ...base, orden: null }), 'SIN_ORDEN');
    assert.equal(motivoNoMarcable({ ...base, fecha_vencimiento: null }), 'SIN_FECHA');
    assert.equal(motivoNoMarcable({ ...base, importe: null }), 'SIN_IMPORTE');
    const [sinOrden] = filasPagos([{ ...base, orden: null }], new Map(), new Map([[claveVencimiento(base.factura_id, 1), marca(2)]]), HOY);
    assert.deepEqual([sinOrden.clave, sinOrden.marca], [null, null]); // sin orden no se le asocia ninguna marca
  });
  test('prepararMarcas / prepararDomiciliados: todo o nada, con el código de la regla', () => {
    const filas = new Map(filasFixtures().flatMap((f): [string, FilaVencimientoPago][] => (f.clave ? [[f.clave, f]] : [])));
    const m = (ns: number[], forma: FormaPago | null = null) => prepararMarcas(filas, { vencimientos: ns.map(id), fecha_pago: HOY, forma });
    assert.deepEqual(m([2, 10]), { ok: true, items: [2, 10].map((n) => ({ factura_id: id(n).factura_id, vencimiento_orden: 1, fecha_pago: HOY, forma: 'TRANSFERENCIA', origen: 'MANUAL' })) });
    assert.deepEqual(m([2, 8], 'EFECTIVO'), { ok: false, codigo: 'VENCIMIENTO_SIN_IMPORTE' });
    assert.deepEqual(m([7]), { ok: false, codigo: 'YA_PAGADO' });
    assert.deepEqual(m([13]), { ok: false, codigo: 'FORMA_SIN_CIF' });
    assert.ok(m([13], 'EFECTIVO').ok);
    assert.deepEqual(prepararMarcas(filas, { vencimientos: [{ factura_id: id(2).factura_id, orden: 7 }], fecha_pago: HOY, forma: null }), { ok: false, codigo: 'VENCIMIENTO_NO_ENCONTRADO' });
    const d = prepararDomiciliados(filas, [id(4), id(5)], HOY);
    assert.deepEqual(d.ok && d.items.map((i) => [i.fecha_pago, i.forma, i.origen]), [['2026-10-30', 'DOMICILIACION', 'DOMICILIADOS'], ['2026-11-15', 'DOMICILIACION', 'DOMICILIADOS']]);
    assert.deepEqual(prepararDomiciliados(filas, [id(4), id(9)], HOY), { ok: false, codigo: 'NO_DOMICILIADO_PREVISTO' }); // V9 aún no vence
    assert.deepEqual(prepararDomiciliados(filas, [id(6)], HOY), { ok: false, codigo: 'VENCIMIENTO_SIN_IMPORTE' });
    // Con la fecha de referencia el mismo día del vencimiento, aún no ha vencido: no se confirma.
    assert.deepEqual(prepararDomiciliados(filas, [id(5)], '2026-11-15'), { ok: false, codigo: 'NO_DOMICILIADO_PREVISTO' });
  });
  test('hoy en Madrid (no en UTC)', () => {
    assert.equal(hoyMadrid(new Date('2026-11-16T23:30:00Z')), '2026-11-17');
    assert.equal(hoyMadrid(new Date('2026-07-16T22:30:00Z')), '2026-07-17');
    assert.equal(hoyMadrid(new Date('2026-11-16T22:59:00Z')), '2026-11-16');
  });
});

describe('totales por semana y mes', () => {
  test('H6-6: por estado: falta por pagar (pendiente, también domiciliado no vencido, + vencido), domiciliado previsto (solo vencido), pagado, abonos y a revisar aparte', () => {
    const fs = [
      fila({ importe: 100 }),
      fila({ importe: -30, sentido: 'ABONO' }),
      fila({ importe: 30, sentido: 'ABONO' }), // un abono con importe positivo resta igual
      fila({ importe: 200, forma_pago: 'DOMICILIACION' }), // domiciliado aún no vencido: PENDIENTE → falta por pagar
      fila({ importe: 150, forma_pago: 'DOMICILIACION', estado_pago: 'DOMICILIADO_PREVISTO' }),
      fila({ importe: 45, sentido: 'ABONO', estado_pago: 'ABONO_PENDIENTE_COMPENSAR' }),
      fila({ importe: 50, estado_pago: 'PAGADO_MANUAL' }),
      fila({ importe: 60, estado_pago: 'A_REVISAR' }),
      fila({ importe: null }),
      fila({ importe: 80, sentido: 'NO_DOCUMENTADO' }),
      fila({ importe: 70, forma_pago: 'SIN_DETERMINAR', estado_pago: 'VENCIDO_SIN_PAGAR', fecha_vencimiento: '2026-11-10' }),
    ];
    const [s1, s2] = totalesPorPeriodo(fs, 'semana');
    assert.deepEqual([s1.clave, s1.desde, s1.hasta], ['2026-11-09', '2026-11-09', '2026-11-15']);
    assert.deepEqual(s1.por_pagar, { neto: 70, cargos: 70, abonos: null, vencimientos: 1 });
    assert.deepEqual([s2.clave, s2.hasta, s2.vencimientos], ['2026-11-16', '2026-11-22', 10]);
    assert.deepEqual(s2.por_pagar, { neto: 240, cargos: 300, abonos: -60, vencimientos: 4 });
    assert.deepEqual(s2.domiciliado, { neto: 150, cargos: 150, abonos: null, vencimientos: 1 });
    assert.deepEqual(s2.pagado, { neto: 50, cargos: 50, abonos: null, vencimientos: 1 });
    assert.deepEqual(s2.abonos, { neto: -45, cargos: null, abonos: -45, vencimientos: 1 });
    assert.deepEqual(s2.revisar, { neto: 60, cargos: 60, abonos: null, vencimientos: 1 });
    assert.deepEqual([s2.sin_importe, s2.sentido_no_documentado], [1, 1]);
    // Cada estado, en un solo bloque; A_REVISAR nunca en pagado.
    assert.deepEqual(BLOQUE_DE_ESTADO, {
      PAGADO_MANUAL: 'pagado', PAGADO_BANCO: 'pagado', DOMICILIADO_PREVISTO: 'domiciliado',
      PENDIENTE: 'por_pagar', VENCIDO_SIN_PAGAR: 'por_pagar', ABONO_PENDIENTE_COMPENSAR: 'abonos', A_REVISAR: 'revisar',
    });
  });
  test('H6-3: el cargo con importe negativo queda fuera de los totales y se cuenta aparte (en cualquier bloque)', () => {
    const [t] = totalesPorPeriodo([
      fila({ importe: 100 }), fila({ importe: -25 }), fila({ importe: -10, forma_pago: 'DOMICILIACION' }),
      fila({ importe: -15, estado_pago: 'PAGADO_MANUAL' }), fila({ importe: -20, sentido: 'ABONO' }),
    ], 'semana');
    assert.deepEqual(t.por_pagar, { neto: 80, cargos: 100, abonos: -20, vencimientos: 2 });
    assert.deepEqual(t.domiciliado.neto, null);
    assert.deepEqual(t.pagado.neto, null);
    assert.equal(t.cargo_negativo, 3);
    assert.equal(totalGeneral([fila({ importe: -5 })]).por_pagar.neto, null);
  });
  test('sin ningún importe conocido el total es null (nunca 0); los sin fecha, al final; meses de 1 a fin de mes', () => {
    const ts = totalesPorPeriodo([fila({ importe: null }), fila({ fecha_vencimiento: null }), fila({ fecha_vencimiento: '2026-02-03' })], 'mes');
    assert.deepEqual(ts.map((t) => [t.clave, t.desde, t.hasta]), [['2026-02', '2026-02-01', '2026-02-28'], ['2026-11', '2026-11-01', '2026-11-30'], [null, null, null]]);
    assert.deepEqual(ts[1].por_pagar, { neto: null, cargos: null, abonos: null, vencimientos: 0 });
    assert.equal(ts[1].sin_importe, 1);
    assert.deepEqual(totalGeneral([]).por_pagar.neto, null);
  });
  test('fixtures (hoy 16/11/2026): semanas y meses', () => {
    const filas = filasFixtures();
    const sem = totalesPorPeriodo(filas, 'semana').map((t) => [t.clave, t.por_pagar.neto, t.domiciliado.neto, t.pagado.vencimientos, t.sin_importe, t.sentido_no_documentado, t.cargo_negativo]);
    assert.deepEqual(sem, [
      ['2026-10-26', null, 400, 0, 0, 0, 1], // domiciliado vencido 400; el abono vencido (−20) va aparte; el cargo negativo de −25 no suma
      ['2026-11-02', 304.74, null, 0, 0, 1, 0], // HEFAME pagado, pero de sentido no documentado: no suma
      ['2026-11-09', 472.22, 150, 0, 0, 1, 0],
      ['2026-11-16', -45.3, null, 0, 1, 0, 0], // H6-6: abono domiciliado aún no vencido (pendiente): falta por pagar
      ['2026-11-30', null, null, 0, 1, 0, 0],
      ['2026-12-14', null, null, 0, 0, 1, 0], // H6-REAL: FEDEFARMA 96,80, sentido no documentado: no suma
    ]);
    const mes = totalesPorPeriodo(filas, 'mes').map((t) => [t.clave, t.por_pagar.neto, t.domiciliado.neto, t.abonos.neto, t.sin_importe, t.sentido_no_documentado, t.cargo_negativo]);
    assert.deepEqual(mes, [['2026-10', null, 400, -20, 0, 0, 1], ['2026-11', 731.66, 150, null, 2, 2, 0], ['2026-12', null, null, null, 0, 1, 0]]);
  });
});

describe('filtros', () => {
  const x = (fecha: string | null, estado: FilaTotal['estado_pago'] = 'PENDIENTE') => ({ fecha_vencimiento: fecha, estado_pago: estado });
  test('atrasados (vencido sin pagar; a revisar también), esta semana, este mes, próximos 30/60/90 y rango; sin fecha fuera', () => {
    assert.equal(cumplePeriodo(x('2026-11-15', 'VENCIDO_SIN_PAGAR'), 'atrasados', HOY), true);
    assert.equal(cumplePeriodo(x('2026-11-15', 'DOMICILIADO_PREVISTO'), 'atrasados', HOY), true);
    assert.equal(cumplePeriodo(x('2026-11-15', 'A_REVISAR'), 'atrasados', HOY), true);
    assert.equal(cumplePeriodo(x('2026-11-07', 'PAGADO_MANUAL'), 'atrasados', HOY), false);
    assert.equal(cumplePeriodo(x(HOY), 'atrasados', HOY), false);
    assert.deepEqual(['2026-11-15', '2026-11-16', '2026-11-22', '2026-11-23'].map((f) => cumplePeriodo(x(f), 'semana', HOY)), [false, true, true, false]);
    assert.deepEqual(['2026-10-31', '2026-11-01', '2026-11-30', '2026-12-01'].map((f) => cumplePeriodo(x(f), 'mes', HOY)), [false, true, true, false]);
    assert.deepEqual(['2026-11-15', HOY, '2026-12-16', '2026-12-17'].map((f) => cumplePeriodo(x(f), 'p30', HOY)), [false, true, true, false]);
    assert.equal(cumplePeriodo(x('2027-01-15'), 'p60', HOY), true);
    assert.equal(cumplePeriodo(x('2027-02-14'), 'p90', HOY), true);
    assert.equal(cumplePeriodo(x('2027-02-15'), 'p90', HOY), false);
    assert.equal(cumplePeriodo(x('2026-11-05'), 'rango', HOY, { desde: '2026-11-01', hasta: '2026-11-05' }), true);
    assert.equal(cumplePeriodo(x('2026-11-06'), 'rango', HOY, { desde: '2026-11-01', hasta: '2026-11-05' }), false);
    assert.equal(cumplePeriodo(x('2020-01-01'), 'rango', HOY, { hasta: '2026-11-05' }), true);
    assert.equal(cumplePeriodo(x(null), 'semana', HOY), false);
    assert.equal(cumplePeriodo(x(null), '', HOY), true);
  });
  test('búsqueda por nombre comercial, razón social, CIF (con guiones) y nº de factura; sin acentos', () => {
    const v = { proveedor_comercial: 'HEFAME', proveedor_razon_social: 'HDAD.FMCTCA.MEDIT.,S.C.L.', proveedor: 'HEFAME', proveedor_cif_comparable: 'F30004444', numero_factura: 'HF-0563-889120' };
    for (const q of ['hefame', 'hdad', 'F-30004444', 'f30004444', 'hf-0563', '889120', 'Héfame']) assert.equal(cumpleBusquedaPago(v, q), true, q);
    assert.equal(cumpleBusquedaPago(v, 'cofares'), false);
  });
});

describe('validación (falla cerrado)', () => {
  const ids = [id(1), id(2)];
  test('marcar: [{factura_id, orden}] sin repetir (máx. 60), fecha ≤ hoy, forma de la lista o null; nunca el id del vencimiento', () => {
    assert.deepEqual(validarMarcar({ vencimientos: ids, fecha_pago: HOY, forma: null }, HOY), { ok: true, datos: { vencimientos: ids, fecha_pago: HOY, forma: null } });
    assert.ok(validarMarcar({ vencimientos: ids, fecha_pago: '2026-11-01', forma: 'EFECTIVO' }, HOY).ok);
    const e = (b: unknown) => { const r = validarMarcar(b, HOY); assert.equal(r.ok, false); return Object.keys((r as { errores: object }).errores); };
    assert.deepEqual(e({ vencimientos: ids, fecha_pago: '2026-11-17', forma: null }), ['fecha_pago']);
    assert.deepEqual(e({ vencimientos: ids, fecha_pago: '2026-02-30', forma: null }), ['fecha_pago']);
    assert.deepEqual(e({ vencimientos: ids, fecha_pago: HOY, forma: 'CHEQUE' }), ['forma']);
    assert.deepEqual(e({ vencimientos: ids, fecha_pago: HOY }), ['forma']);
    assert.deepEqual(e({ vencimientos: [id(1), id(1)], fecha_pago: HOY, forma: null }), ['vencimientos']);
    assert.deepEqual(e({ vencimientos: [], fecha_pago: HOY, forma: null }), ['vencimientos']);
    assert.deepEqual(e({ vencimientos: [V(1)], fecha_pago: HOY, forma: null }), ['vencimientos']); // el id del vencimiento no vale
    assert.deepEqual(e({ vencimientos: [{ ...id(1), orden: 0 }], fecha_pago: HOY, forma: null }), ['vencimientos']);
    assert.deepEqual(e({ vencimientos: [{ ...id(1), orden: 1.5 }], fecha_pago: HOY, forma: null }), ['vencimientos']);
    assert.deepEqual(e({ vencimientos: [{ ...id(1), vencimiento_id: V(1) }], fecha_pago: HOY, forma: null }), ['vencimientos']);
    assert.deepEqual(e({ vencimientos: Array.from({ length: MAX_VENCIMIENTOS_PETICION + 1 }, (_, i) => ({ ...id(1), orden: i + 1 })), fecha_pago: HOY, forma: null }), ['vencimientos']);
    assert.deepEqual(e({ vencimientos: ids, fecha_pago: HOY, forma: null, importe: 0 }), ['cuerpo']);
    // 60 vencimientos caben en el límite de 4 KB del cuerpo.
    assert.ok(JSON.stringify({ vencimientos: Array.from({ length: MAX_VENCIMIENTOS_PETICION }, (_, i) => ({ ...id(1), orden: 9000 + i })), fecha_pago: HOY, forma: 'COMPENSACION_ABONO' }).length < 4096);
  });
  test('domiciliados, forma del proveedor y confirmación', () => {
    assert.deepEqual(validarDomiciliados({ vencimientos: ids }), { ok: true, vencimientos: ids });
    assert.equal(validarDomiciliados({ vencimientos: ids, fecha_pago: HOY }).ok, false);
    assert.deepEqual(validarFormaProveedor({ forma: 'TRANSFERENCIA' }), { ok: true, forma: 'TRANSFERENCIA' });
    assert.deepEqual(validarFormaProveedor({ forma: null }), { ok: true, forma: null });
    assert.equal(validarFormaProveedor({ forma: 'SIN_DETERMINAR' }).ok, false);
    assert.equal(validarFormaProveedor({}).ok, false);
    assert.equal(validarConfirmacion({ confirmar: true }), true);
    assert.equal(validarConfirmacion({ confirmar: 'si' }), false);
  });
});

describe('almacén de marcas y formas (FIXTURES)', () => {
  const item = (n: number, forma: FormaPago = 'TRANSFERENCIA') => ({ factura_id: id(n).factura_id, vencimiento_orden: id(n).orden, fecha_pago: HOY, forma, origen: 'MANUAL' as const });
  test('semilla: historial en orden, con el cambio de forma de Hefame como un solo evento', () => {
    const h = almacen().fuente().historial.map((e) => [e.accion, e.cif ?? `${e.factura_id?.slice(-2)}#${e.vencimiento_orden}`, e.forma, e.forma_anterior]);
    assert.deepEqual(h, [
      ['FORMA', 'B00000003', 'TRANSFERENCIA', null],
      ['FORMA', 'F30004444', 'EFECTIVO', null],
      ['FORMA', 'F30004444', 'TRANSFERENCIA', 'EFECTIVO'],
      ['MARCA', '01#1', 'TRANSFERENCIA', null],
      ['ANULA_MARCA', '01#1', 'TRANSFERENCIA', null],
      ['MARCA', '05#1', 'TRANSFERENCIA', null],
    ]);
  });
  test('una marca vigente por (factura, orden) (todo o nada); copia fecha e importe (trigger simulado); anular nunca borra', () => {
    const a = almacen();
    const copia = copiaDe(filasFixtures());
    const r = a.marcar([item(2)], 'Marc', copia);
    assert.ok(Array.isArray(r));
    const m = (r as MarcaPago[])[0];
    assert.deepEqual([m.fecha_vencimiento, m.importe, m.farmacia, m.creada_por], ['2026-11-11', 472.22, 'PIO', 'Marc']);
    assert.equal(a.marcar([item(10), item(2, 'EFECTIVO')], 'Marc', copia), 'YA_PAGADO');
    assert.equal(a.fuente().marcas.has(clave(10)), false); // todo o nada
    assert.equal(a.marcar([item(8, 'EFECTIVO')], 'Marc', copia), 'VENCIMIENTO_SIN_IMPORTE');
    assert.equal(a.marcar([{ ...item(2), vencimiento_orden: 5 }], 'Marc', copia), 'VENCIMIENTO_NO_ENCONTRADO');
    assert.equal(a.marcar([{ ...item(10), fecha_pago: '2026-11-17' }], 'Marc', copia), 'FECHA_PAGO_FUTURA');
    const anulada = a.anular(m.marca_id, 'Marc');
    assert.ok(typeof anulada !== 'string' && anulada.anulada && anulada.anulada_por === 'Marc');
    assert.equal(a.anular(m.marca_id, 'Marc'), 'MARCA_YA_ANULADA');
    assert.equal(a.anular('71000000-0000-4000-8000-999999999999', 'Marc'), 'MARCA_NO_ENCONTRADA');
    assert.equal(a.datos().marcas.filter((x) => x.factura_id === id(2).factura_id).length, 1); // sigue ahí, anulada
    assert.ok(Array.isArray(a.marcar([item(2, 'EFECTIVO')], 'Marc', copia))); // se puede volver a marcar
    const ult = a.fuente().historial.slice(-3).map((e) => [e.accion, e.autor, e.factura_id, e.vencimiento_orden]);
    assert.deepEqual(ult, [['MARCA', 'Marc', id(2).factura_id, 1], ['ANULA_MARCA', 'Marc', id(2).factura_id, 1], ['MARCA', 'Marc', id(2).factura_id, 1]]);
  });
  test('forma por CIF: una vigente (la anterior se anula), sin cambios = SIN_CAMBIOS, null vuelve a domiciliación', () => {
    const a = almacen();
    assert.deepEqual(a.fijarForma('A00000001', 'TRANSFERENCIA', 'Marc'), { cif: 'A00000001', forma: 'TRANSFERENCIA', por_defecto: false });
    assert.equal(a.fijarForma('A00000001', 'TRANSFERENCIA', 'Marc'), 'SIN_CAMBIOS');
    assert.deepEqual(a.fijarForma('A00000001', null, 'Marc'), { cif: 'A00000001', forma: 'DOMICILIACION', por_defecto: true });
    assert.equal(a.fijarForma('A00000001', null, 'Marc'), 'SIN_CAMBIOS');
    assert.equal(a.datos().formas.filter((f) => f.cif === 'A00000001' && !f.anulada).length, 0);
    assert.equal(a.datos().formas.filter((f) => f.cif === 'A00000001').length, 1); // anulada, no borrada
    assert.equal(a.fuente().formas.get('A00000001'), undefined);
  });
  test('semilla con dos marcas vigentes del mismo vencimiento, o sin (factura, orden): no arranca', () => {
    const s = leerSemillaPagos();
    const m = { ...s.marcas[1], marca_id: '70000000-0000-4000-8000-000000000099' };
    assert.throws(() => crearAlmacenPagos({ ...s, marcas: [...s.marcas, m] }), /SEMILLA_PAGOS_MARCA_DUPLICADA/);
    const sinOrden = { ...s.marcas[1], vencimiento_orden: undefined } as unknown as MarcaPago;
    assert.throws(() => crearAlmacenPagos({ ...s, marcas: [sinOrden] }), /SEMILLA_PAGOS_MARCA_NO_VALIDA/);
  });
});

describe('API /api/pagos (FIXTURES)', async () => {
  const app = await crearServidor('FIXTURES');
  after(() => app.close());
  const H = { host: '127.0.0.1:4747' };
  const login = await app.inject({
    method: 'POST', url: '/api/login', headers: { ...H, 'content-type': 'application/x-www-form-urlencoded' },
    payload: new URLSearchParams({ usuario: USUARIO, clave: CLAVE_FIXTURES, destino: '/' }).toString(),
  });
  const cookie = String(login.headers['set-cookie']).split(';')[0];
  const W = { ...H, cookie, origin: 'http://127.0.0.1:4747', 'content-type': 'application/json' };
  const get = async () => (await app.inject({ method: 'GET', url: '/api/pagos/vencimientos', headers: { ...H, cookie } })).json();
  const post = (url: string, body: unknown) => app.inject({ method: 'POST', url, headers: W, payload: JSON.stringify(body) });
  const put = (url: string, body: unknown) => app.inject({ method: 'PUT', url, headers: W, payload: JSON.stringify(body) });
  const estado = async (n: number) => (await get()).filas.find((f: { vencimiento_id: string }) => f.vencimiento_id === V(n));

  test('lectura: sin sesión 401; con sesión, 13 filas, escritura disponible, proveedores por CIF, sin CIF contado, historial y banco sin datos', async () => {
    assert.equal((await app.inject({ method: 'GET', url: '/api/pagos/vencimientos', headers: H })).statusCode, 401);
    const d = await get();
    assert.deepEqual([d.modo, d.hoy, d.marcas_disponibles, d.mensaje_escritura, d.filas.length, d.a_revisar, d.marcas_huerfanas], ['FIXTURES', HOY, true, null, 13, 0, []]);
    assert.deepEqual(d.proveedores.map((p: { cif: string; forma: string; por_defecto: boolean }) => [p.cif, p.forma, p.por_defecto]),
      [['B00000003', 'TRANSFERENCIA', false], ['A00000001', 'DOMICILIACION', true], ['F30004444', 'TRANSFERENCIA', false]]);
    assert.deepEqual(d.sin_cif, { vencimientos: 2 });
    assert.deepEqual(d.pago, { estado: 'SIN_DATOS_BANCARIOS', texto: 'sin datos bancarios', color: 'gris' });
    assert.equal(d.historial[0].accion, 'MARCA'); // lo más reciente primero
    assert.equal(d.historial[0].numero_factura, 'HF-0563-889120');
  });
  test('marcar varios por (factura, orden) (forma de cada proveedor), ya pagado = 409 sin marcar ninguno, anular con confirmación', async () => {
    const r = await post('/api/pagos/marcas', { vencimientos: [id(2), id(10)], fecha_pago: '2026-11-12', forma: null });
    assert.equal(r.statusCode, 201);
    const [m2, m10] = r.json().marcas;
    assert.deepEqual([m2.forma, m2.fecha_pago, m2.creada_por, m2.origen, m2.importe, m2.fecha_vencimiento], ['TRANSFERENCIA', '2026-11-12', 'Marc', 'MANUAL', 472.22, '2026-11-11']);
    assert.equal((await estado(2)).estado_pago, 'PAGADO_MANUAL');
    const doble = await post('/api/pagos/marcas', { vencimientos: [id(1), id(2)], fecha_pago: HOY, forma: null });
    assert.deepEqual([doble.statusCode, doble.json().error], [409, 'YA_PAGADO']);
    assert.match(doble.json().mensaje, /No se ha marcado ninguno/);
    assert.equal((await estado(1)).estado_pago, 'VENCIDO_SIN_PAGAR');
    assert.equal((await put(`/api/pagos/marcas/${m2.marca_id}/anular`, {})).statusCode, 400);
    assert.equal((await put(`/api/pagos/marcas/${m2.marca_id}/anular`, { confirmar: true })).statusCode, 200);
    const otra = await put(`/api/pagos/marcas/${m2.marca_id}/anular`, { confirmar: true });
    assert.deepEqual([otra.statusCode, otra.json().error, otra.json().mensaje], [409, 'MARCA_YA_ANULADA', 'Esa marca de pago ya está anulada.']);
    assert.equal((await put(`/api/pagos/marcas/${m10.marca_id}/anular`, { confirmar: true })).statusCode, 200);
    assert.equal((await estado(2)).estado_pago, 'VENCIDO_SIN_PAGAR');
  });
  test('reglas previas: el id del vencimiento no vale (400); sin importe no se marca (409, mensaje llano), tampoco con forma elegida', async () => {
    const porId = await post('/api/pagos/marcas', { vencimientos: [V(2)], fecha_pago: HOY, forma: null });
    assert.deepEqual([porId.statusCode, porId.json().error], [400, 'DATOS_NO_VALIDOS']);
    const r = await post('/api/pagos/marcas', { vencimientos: [id(8)], fecha_pago: HOY, forma: 'EFECTIVO' });
    assert.deepEqual([r.statusCode, r.json().error], [409, 'VENCIMIENTO_SIN_IMPORTE']);
    assert.equal(r.json().mensaje, 'Algún vencimiento no tiene importe (importe pendiente): no se puede marcar hasta que se complete. No se ha marcado ninguno.');
    assert.equal((await estado(8)).marca, null);
    const futura = await post('/api/pagos/marcas', { vencimientos: [id(2)], fecha_pago: '2026-11-17', forma: null });
    assert.deepEqual([futura.statusCode, Object.keys(futura.json().errores)], [400, ['fecha_pago']]);
  });
  test('sin CIF (con importe): «la de cada proveedor» no vale (400 FORMA_SIN_CIF); con forma elegida, sí', async () => {
    const r = await post('/api/pagos/marcas', { vencimientos: [id(13)], fecha_pago: HOY, forma: null });
    assert.deepEqual([r.statusCode, r.json().error], [400, 'FORMA_SIN_CIF']);
    const ok = await post('/api/pagos/marcas', { vencimientos: [id(13)], fecha_pago: HOY, forma: 'TRANSFERENCIA' });
    assert.equal(ok.statusCode, 201);
    assert.equal((await put(`/api/pagos/marcas/${ok.json().marcas[0].marca_id}/anular`, { confirmar: true })).statusCode, 200);
  });
  test('confirmar domiciliados: solo DOMICILIADO_PREVISTO ya vencido; fecha = vencimiento y forma domiciliación', async () => {
    const no = await post('/api/pagos/marcas/domiciliados', { vencimientos: [id(4), id(9)] }); // V9 aún no ha vencido
    assert.deepEqual([no.statusCode, no.json().error], [409, 'NO_DOMICILIADO_PREVISTO']);
    assert.equal((await estado(4)).estado_pago, 'DOMICILIADO_PREVISTO');
    const r = await post('/api/pagos/marcas/domiciliados', { vencimientos: [id(4), id(5)] });
    assert.equal(r.statusCode, 201);
    assert.deepEqual(r.json().marcas.map((m: { fecha_pago: string; forma: string; origen: string }) => [m.fecha_pago, m.forma, m.origen]),
      [['2026-10-30', 'DOMICILIACION', 'DOMICILIADOS'], ['2026-11-15', 'DOMICILIACION', 'DOMICILIADOS']]);
    for (const m of r.json().marcas) assert.equal((await put(`/api/pagos/marcas/${m.marca_id}/anular`, { confirmar: true })).statusCode, 200);
  });
  test('H6-3: marcar un abono vencido: «la de cada proveedor» = compensación con abono; confirmar domiciliados no lo admite', async () => {
    assert.equal((await estado(12)).estado_pago, 'ABONO_PENDIENTE_COMPENSAR');
    const no = await post('/api/pagos/marcas/domiciliados', { vencimientos: [id(12)] });
    assert.deepEqual([no.statusCode, no.json().error], [409, 'NO_DOMICILIADO_PREVISTO']);
    const r = await post('/api/pagos/marcas', { vencimientos: [id(12)], fecha_pago: HOY, forma: null });
    assert.equal(r.statusCode, 201);
    assert.deepEqual([r.json().marcas[0].forma, (await estado(12)).estado_pago], ['COMPENSACION_ABONO', 'PAGADO_MANUAL']);
    const h = (await get()).historial[0];
    assert.deepEqual([h.accion, h.sentido, h.factura_id, h.vencimiento_orden], ['MARCA', 'ABONO', id(12).factura_id, 2]);
    assert.equal((await put(`/api/pagos/marcas/${r.json().marcas[0].marca_id}/anular`, { confirmar: true })).statusCode, 200);
    assert.equal((await estado(12)).estado_pago, 'ABONO_PENDIENTE_COMPENSAR');
  });
  test('forma de pago del proveedor: cambia el estado de sus vencidos; CIF ajeno 404; null vuelve a domiciliación', async () => {
    assert.equal((await put('/api/pagos/formas/A00000001', { forma: 'TRANSFERENCIA' })).statusCode, 200);
    assert.equal((await estado(4)).estado_pago, 'VENCIDO_SIN_PAGAR');
    assert.equal((await put('/api/pagos/formas/A00000001', { forma: 'TRANSFERENCIA' })).json().error, 'SIN_CAMBIOS');
    assert.equal((await put('/api/pagos/formas/Z99999999', { forma: 'EFECTIVO' })).statusCode, 404);
    assert.equal((await put('/api/pagos/formas/A00000001', { forma: null })).statusCode, 200);
    assert.equal((await estado(4)).estado_pago, 'DOMICILIADO_PREVISTO');
    const h = (await get()).historial.slice(0, 2).map((e: { accion: string; autor: string }) => [e.accion, e.autor]);
    assert.deepEqual(h, [['FORMA_POR_DEFECTO', 'Marc'], ['FORMA', 'Marc']]);
  });
  test('solo las rutas de escritura previstas; sin Origin 403; nada de DELETE; otras rutas siguen en solo lectura', async () => {
    assert.equal((await app.inject({ method: 'POST', url: '/api/pagos/marcas', headers: { ...H, cookie, 'content-type': 'application/json' }, payload: '{}' })).statusCode, 403);
    assert.equal((await app.inject({ method: 'DELETE', url: `/api/pagos/marcas/${V(1)}`, headers: W })).statusCode, 405);
    assert.equal((await app.inject({ method: 'POST', url: '/api/vencimientos', headers: W, payload: '{}' })).statusCode, 405);
    assert.equal((await app.inject({ method: 'PUT', url: '/api/facturas/f0000000-0000-4000-8000-000000000001', headers: W, payload: '{}' })).statusCode, 405);
    for (const [m, u, si] of [
      ['POST', '/api/pagos/marcas', true], ['POST', '/api/pagos/marcas/domiciliados', true],
      ['PUT', '/api/pagos/marcas/70000000-0000-4000-8000-000000000002/anular', true], ['PUT', '/api/pagos/marcas/42/anular', true],
      ['PUT', '/api/pagos/formas/B00000003', true],
      ['PUT', '/api/pagos/marcas', false], ['POST', '/api/pagos/formas/B00000003', false], ['PUT', '/api/pagos/formas/b-00000003', false],
      ['PUT', '/api/pagos/marcas/x;drop/anular', false], ['PUT', '/api/pagos/marcas/0/anular', false],
      ['DELETE', '/api/pagos/marcas/70000000-0000-4000-8000-000000000002', false], ['POST', '/api/pagos/vencimientos', false],
    ] as const) assert.equal(esEscrituraPagos(m, u), si, `${m} ${u}`);
  });
});
