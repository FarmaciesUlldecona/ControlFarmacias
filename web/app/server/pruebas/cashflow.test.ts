// H7: pantalla Cashflow. Previsión por fuente, sin doble cómputo, medias, traspasos neutros, avisos naranja y rojo con
// devolución, antigüedad de la importación, ruta (FIXTURES y REAL 503) y lecturas REAL contra el contrato.
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import Fastify from 'fastify';
import { crearAdaptadorFixtures } from '../adaptador_fixtures.ts';
import { construirPantalla, crearAlmacenPagos } from '../pagos/pagos.ts';
import { leerSemillaPagos } from '../pagos/rutas.ts';
import {
  CONCEPTO_MEDIA, CONFIG_CASHFLOW, CORRESPONDENCIAS_PROVEEDOR, TEXTO_H7_PENDIENTE, calcularCashflow, celdaColumna, clasificarCategoria,
  columnasVista, comercialDeConcepto, decenaDe, estadoImportacion, finDecena, moverDecena, ordinalDecena, saldoColumna, siguienteDecena,
  totalCategoria, type CashflowDTO, type ImporteCashflow, type Linea, type ResultadoCashflow, type SaldoCashflow, type VencimientoCashflow,
} from '../cashflow/cashflow.ts';
import { leerSemillaCashflow, registrarCashflow, vencimientoCashflow } from '../cashflow/rutas.ts';
import { SQL_CASHFLOW, leerCashflowReal } from '../cashflow/lectura_real.ts';

async function datosFixtures(): Promise<CashflowDTO> {
  const semilla = leerSemillaCashflow();
  const almacen = crearAlmacenPagos(leerSemillaPagos());
  const p = construirPantalla(await crearAdaptadorFixtures().vencimientos(), almacen.fuente(), { hoy: almacen.hoy, modo: 'FIXTURES' });
  return {
    ...semilla, farmacia: 'PIO', generado_at: p.generado_at, modo: 'FIXTURES', config: CONFIG_CASHFLOW,
    vencimientos: p.filas.map(vencimientoCashflow), pago: p.pago,
  };
}
const linea = (r: ResultadoCashflow, vista: 'PIO' | 'RITA' | 'CONSOLIDADO', categoria: string, concepto: string): Linea => {
  const l = r.vistas[vista].lineas.find((x) => x.categoria === categoria && x.concepto === concepto);
  assert.ok(l, `${vista}: falta ${categoria} / ${concepto}`);
  return l;
};
const saldo = (r: ResultadoCashflow, vista: 'PIO' | 'RITA' | 'CONSOLIDADO', d: string) => r.vistas[vista].decenas[d].saldo;

// Datos mínimos para casos sintéticos.
const fila = (cuenta: string, d: string, categoria: string, concepto: string, importe: number | null): ImporteCashflow =>
  ({ cuenta, decena_inicio: d, decena_fin: finDecena(d), categoria, concepto, importe });
const banco = (cuenta: string, d: string, s: number | null): SaldoCashflow => ({ cuenta, decena_inicio: d, saldo_formulas: s, saldo_bancos: s });
const IMP_OK = [{ importacion_id: 'i1', vigente: true, importado_at: '2026-11-15T08:00:00.000Z', origen: 'x.xlsx', estado: 'OK' }];
const CUENTAS = [{ codigo: 'PIO', farmacia: 'PIO' }, { codigo: 'RITA', farmacia: 'RITA' }];
const venc = (o: Partial<VencimientoCashflow>): VencimientoCashflow => ({
  vencimiento_id: 'v1', factura_id: 'f1', numero_factura: 'N1', proveedor_comercial: 'ALLIANCE', proveedor_nombre: 'ALLIANCE',
  fecha_vencimiento: '2026-11-25', importe: 100, sentido: 'CARGO', estado_pago: 'PENDIENTE', fecha_pago: null, cargo_negativo: false, ...o,
});

describe('H7: decenas y configuración', () => {
  test('decenas 1–10, 11–20 y 21–fin de mes', () => {
    assert.equal(decenaDe('2026-11-16'), '2026-11-11');
    assert.equal(decenaDe('2026-11-30'), '2026-11-21');
    assert.equal(finDecena('2026-02-21'), '2026-02-28');
    assert.equal(finDecena('2026-11-01'), '2026-11-10');
    assert.equal(siguienteDecena('2026-12-21'), '2027-01-01');
    assert.equal(moverDecena('2026-11-11', -3), '2026-10-11');
    assert.equal(ordinalDecena('2026-11-21'), 3);
  });
  test('categorías RE/RS, traspasos y «no relacionadas»; correspondencias en un único punto', () => {
    assert.deepEqual(clasificarCategoria('RE Cobro TPV'), { sentido: 'ENTRADA', clase: 'FARMACIA' });
    assert.deepEqual(clasificarCategoria('RS Traspasos'), { sentido: 'SALIDA', clase: 'TRASPASO' });
    assert.deepEqual(clasificarCategoria('RS No relacionadas con la farmacia'), { sentido: 'SALIDA', clase: 'NO_RELACIONADA' });
    assert.equal(clasificarCategoria('Varios'), null);
    assert.equal(comercialDeConcepto('Federació'), 'FEDEFARMA');
    assert.equal(comercialDeConcepto(' logista '), 'LOGISTA PHARMA');
    assert.equal(comercialDeConcepto('Nóminas'), null);
    assert.ok(CORRESPONDENCIAS_PROVEEDOR.some((c) => c.comercial === 'ALLIANCE'));
    assert.deepEqual([CONFIG_CASHFLOW.decenas_media, CONFIG_CASHFLOW.meses_media_soe, CONFIG_CASHFLOW.dias_importacion_antigua, CONFIG_CASHFLOW.saldo_minimo], [6, 3, 5, 0]);
  });
  test('vistas: 3 decenas pasadas y 9 próximas; 3 meses pasados y 9 próximos', () => {
    const d = columnasVista('2026-11-16', 'decenas');
    assert.equal(d.length, 12);
    assert.deepEqual([d[0].clave, d[3].clave, d[11].clave], ['2026-10-11', '2026-11-11', '2027-02-01']);
    assert.ok(d[3].actual);
    const m = columnasVista('2026-11-16', 'mes');
    assert.deepEqual([m.length, m[0].clave, m[3].clave, m[11].clave], [12, '2026-08', '2026-11', '2027-07']);
  });
});

describe('H7: fixtures (16/11/2026; última decena real 01–10/11)', () => {
  test('real hasta la última decena con saldo de banco; partida = ese saldo', async () => {
    const r = calcularCashflow(await datosFixtures());
    assert.equal(r.vistas.PIO.ultima_real, '2026-11-01');
    assert.equal(r.vistas.RITA.ultima_real, '2026-11-01');
    assert.equal(r.vistas.PIO.saldo_partida, 9000);
    assert.equal(r.vistas.RITA.saldo_partida, 2000);
    assert.equal(r.vistas.CONSOLIDADO.saldo_partida, 11000);
    assert.equal(r.vistas.PIO.decenas['2026-11-01'].real, true);
    assert.equal(r.vistas.PIO.decenas['2026-11-11'].real, false);
    // Todas las decenas reales con saldo positivo (fixtures coherentes).
    for (const v of ['PIO', 'RITA'] as const) {
      for (const d of r.decenas.filter((x) => x >= '2026-06-01' && x <= '2026-11-01')) assert.ok((saldo(r, v, d) as number) > 0, `${v} ${d}`);
    }
  });

  test('previsión por fuente: ALLIANCE 11–20/11 sale de los vencimientos (472,22) y sustituye al Excel (520): posible duplicado o diferencia', async () => {
    const r = calcularCashflow(await datosFixtures());
    const c = linea(r, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-11-11'];
    assert.equal(c.fuente, 'VENCIMIENTOS');
    assert.equal(c.importe, -472.22);
    assert.equal(c.excel, -520);
    assert.equal(c.diferencia, true);
    assert.deepEqual(c.vencimientos?.incluidos.map((v) => v.vencimiento_id), ['90000000-0000-4000-8000-000000000002']);
    // Decenas sin vencimientos: lo anotado en el Excel.
    assert.equal(linea(r, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-11-21'].fuente, 'EXCEL');
    assert.equal(linea(r, 'PIO', 'RS Proveedores', 'COFARES').celdas['2026-11-11'].fuente, 'EXCEL');
    // Real: del Excel, aunque haya vencimientos (04/11).
    assert.equal(linea(r, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-11-01'].fuente, 'REAL');
    // RITA: nunca vencimientos del sistema.
    assert.ok(r.vistas.RITA.lineas.every((l) => Object.values(l.celdas).every((x) => x.fuente !== 'VENCIMIENTOS')));
    // Lo que no entra, contado: COFARES/FEDEFARMA sin nombre comercial, y los sin pagar de decenas reales.
    assert.ok(r.fuera.venc_sin_concepto.length >= 1);
    assert.ok(r.fuera.venc_en_decenas_reales.length >= 1);
    assert.equal(r.fuera.filas_otras_cuentas, 2); // SL
  });

  test('sin doble cómputo: el saldo de 11–20/11 suma los vencimientos y no el Excel de ALLIANCE', async () => {
    const r = calcularCashflow(await datosFixtures(), { 'RE Cobro TPV': 'excel', 'RE Cobro efectivo': 'excel', 'RE Cobro SOE': 'excel' });
    // 9.000 + 9.900 + 3.000 − 472,22 − 4.500 − 3.500 − 800 − 900 = 11.727,78
    assert.equal(saldo(r, 'PIO', '2026-11-11'), 11727.78);
    const usadas = r.vistas.PIO.lineas.flatMap((l) => (l.celdas['2026-11-11']?.en_saldo ? [l.concepto] : []));
    assert.equal(usadas.filter((c) => c === 'ALLIANCE').length, 1);
  });

  test('medias: TPV y efectivo de las últimas 6 decenas; SOE de los últimos 3 meses en su decena habitual; «Media / Excel» por categoría', async () => {
    const dto = await datosFixtures();
    const r = calcularCashflow(dto);
    const tpv = linea(r, 'PIO', 'RE Cobro TPV', CONCEPTO_MEDIA).celdas['2026-11-11'];
    assert.equal(tpv.fuente, 'MEDIA');
    assert.equal(tpv.media?.base.length, 6);
    assert.equal(tpv.importe, 10000);
    assert.equal(tpv.en_saldo, true);
    assert.equal(linea(r, 'PIO', 'RE Cobro TPV', 'TPV CaixaBank').celdas['2026-11-11'].en_saldo, false);
    const soe = linea(r, 'RITA', 'RE Cobro SOE', CONCEPTO_MEDIA);
    assert.equal(soe.celdas['2026-11-21'].importe, 20100);
    assert.deepEqual(soe.celdas['2026-11-21'].media?.base.map((x) => x.clave), ['2026-08', '2026-09', '2026-10']);
    assert.equal(soe.celdas['2026-11-21'].media?.decena_habitual, 3);
    assert.equal(soe.celdas['2026-11-11'], undefined);
    // Con «Excel»: cuenta lo anotado y la media queda a la vista sin sumar.
    const e = calcularCashflow(dto, { 'RE Cobro TPV': 'excel' });
    assert.equal(linea(e, 'PIO', 'RE Cobro TPV', CONCEPTO_MEDIA).celdas['2026-11-11'].en_saldo, false);
    assert.equal(linea(e, 'PIO', 'RE Cobro TPV', 'TPV CaixaBank').celdas['2026-11-11'].en_saldo, true);
    assert.equal((saldo(r, 'PIO', '2026-11-11') as number) - (saldo(e, 'PIO', '2026-11-11') as number), 100);
    // Columna: la cifra que no suma también se ve.
    const col = columnasVista('2026-11-16', 'decenas')[3];
    const t = totalCategoria(r.vistas.PIO.lineas.filter((l) => l.categoria === 'RE Cobro TPV'), col, r.vistas.PIO);
    assert.deepEqual([t?.importe, t?.sin_usar], [10000, 9900]);
    // Consolidado: el mismo concepto en las dos cuentas (Ingresos de caja) suma las dos partes, también lo que no se usa.
    const ef = totalCategoria(r.vistas.CONSOLIDADO.lineas.filter((l) => l.categoria === 'RE Cobro efectivo'), col, r.vistas.CONSOLIDADO);
    assert.deepEqual([ef?.importe, ef?.sin_usar], [4200, 4100]);
  });

  test('traspasos entre cuentas propias: neutros en el consolidado', async () => {
    const r = calcularCashflow(await datosFixtures());
    assert.equal(linea(r, 'PIO', 'RS Traspasos', 'Traspaso a RITA').celdas['2026-09-11'].importe, -3000);
    assert.equal(linea(r, 'RITA', 'RE Traspasos', 'Traspaso desde PIO').celdas['2026-09-11'].importe, 3000);
    assert.ok(r.vistas.CONSOLIDADO.lineas.every((l) => l.clase !== 'TRASPASO'));
    assert.equal(r.vistas.CONSOLIDADO.decenas['2026-09-11'].traspasos, 0);
    assert.ok(!r.avisos.some((a) => a.codigo === 'TRASPASO_SIN_CONTRAPARTIDA'));
    for (const d of ['2026-11-11', '2027-03-01', '2027-06-21']) {
      assert.equal(saldo(r, 'CONSOLIDADO', d), Math.round(((saldo(r, 'PIO', d) as number) + (saldo(r, 'RITA', d) as number)) * 100) / 100);
    }
  });

  test('H7-2: fixtures con un RS negativo (abono de COFARES en PIO) y un RE negativo (regularización en RITA)', async () => {
    const r = calcularCashflow(await datosFixtures());
    assert.equal(linea(r, 'PIO', 'RS Proveedores', 'COFARES').celdas['2026-12-01'].importe, -4250);
    assert.equal(linea(r, 'PIO', 'RS Proveedores', 'COFARES').celdas['2026-12-01'].excel_filas, 2);
    assert.equal(linea(r, 'RITA', 'RE Otros cobros', 'Regularización mutua').celdas['2026-11-21'].importe, -120);
    const p = r.vistas.PIO.decenas;
    assert.equal(p['2026-12-01'].saldo, Math.round(((p['2026-11-21'].saldo as number) + (p['2026-12-01'].neto as number)) * 100) / 100);
  });

  test('«no relacionadas con la farmacia»: cuentan en el saldo, no en el cash flow generado farmacia', async () => {
    const r = calcularCashflow(await datosFixtures());
    const d = r.vistas.PIO.decenas['2026-12-01'];
    assert.equal(d.no_relacionadas, 650 - 1200);
    assert.equal(d.neto, Math.round(((d.farmacia as number) + (d.no_relacionadas as number)) * 100) / 100);
  });

  for (const eleccion of ['media', 'excel'] as const) {
    test(`avisos (${eleccion}): naranja RITA cubierta por PIO en 11–20/12 hasta la SOE (21–31/12); rojo del consolidado en 11–20/01/2027`, async () => {
      const r = calcularCashflow(await datosFixtures(), { 'RE Cobro TPV': eleccion, 'RE Cobro efectivo': eleccion, 'RE Cobro SOE': eleccion });
      const naranjas = r.avisos.filter((a) => a.tipo === 'naranja');
      const rojos = r.avisos.filter((a) => a.tipo === 'rojo');
      assert.equal(naranjas.length, 1, JSON.stringify(naranjas));
      assert.deepEqual([naranjas[0].cuenta, naranjas[0].cubre, naranjas[0].decena, naranjas[0].hasta, naranjas[0].devolucion],
        ['RITA', 'PIO', '2026-12-11', '2026-12-11', '2026-12-21']);
      assert.equal(naranjas[0].importe, -(saldo(r, 'RITA', '2026-12-11') as number));
      assert.ok((saldo(r, 'CONSOLIDADO', '2026-12-11') as number) >= 0);
      assert.equal(rojos.length, 1, JSON.stringify(rojos));
      assert.deepEqual([rojos[0].decena, rojos[0].hasta], ['2027-01-11', '2027-01-11']);
      assert.equal(rojos[0].importe, -(saldo(r, 'CONSOLIDADO', '2027-01-11') as number));
      // Gris: importación de hace 6 días.
      assert.deepEqual(r.avisos.filter((a) => a.tipo === 'gris').map((a) => a.codigo), ['IMPORTACION_ANTIGUA']);
      assert.equal(r.importacion.dias, 6);
    });
  }

  test('vista por meses: el saldo del mes es el de su última decena; noviembre mezcla real y previsto', async () => {
    const r = calcularCashflow(await datosFixtures());
    const cols = columnasVista(r.hoy, 'mes');
    const nov = cols.find((c) => c.clave === '2026-11')!;
    assert.equal(saldoColumna(r.vistas.PIO, nov).saldo, saldo(r, 'PIO', '2026-11-21'));
    const c = celdaColumna(linea(r, 'PIO', 'RS Proveedores', 'ALLIANCE'), nov, r.vistas.PIO);
    assert.equal(c?.tipo, 'mixto');
    assert.equal(c?.diferencia, true);
    assert.equal(c?.importe, -12472.22);
  });
});

describe('H7: casos sintéticos', () => {
  const base = { hoy: '2026-11-16', importaciones: IMP_OK, cuentas: CUENTAS };
  test('vencimientos y Excel iguales: sin aviso; vencimiento sin importe: saldo incompleto, nunca 0', () => {
    const importes = [fila('PIO', '2026-11-21', 'RS Proveedores', 'ALLIANCE', 100)];
    const saldos = [banco('PIO', '2026-11-11', 1000), banco('RITA', '2026-11-11', 0)];
    const igual = calcularCashflow({ ...base, importes, saldos, vencimientos: [venc({})] });
    const c = linea(igual, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-11-21'];
    assert.deepEqual([c.fuente, c.importe, c.diferencia], ['VENCIMIENTOS', -100, false]);
    assert.equal(saldo(igual, 'PIO', '2026-11-21'), 900);
    const nulo = calcularCashflow({ ...base, importes, saldos, vencimientos: [venc({ importe: null })] });
    const n = linea(nulo, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-11-21'];
    assert.deepEqual([n.importe, n.desconocidos, n.diferencia], [null, 1, true]);
    assert.equal(saldo(nulo, 'PIO', '2026-11-21'), 1000);
    assert.equal(nulo.vistas.PIO.decenas['2026-11-21'].incompleto, true);
    // Abono del mismo proveedor: resta de lo que se paga. Pagado antes del último saldo de banco: ya está en el saldo.
    const ab = calcularCashflow({ ...base, importes, saldos, vencimientos: [venc({}), venc({ vencimiento_id: 'v2', importe: -30, sentido: 'ABONO' }),
      venc({ vencimiento_id: 'v3', importe: 50, estado_pago: 'PAGADO_MANUAL', fecha_pago: '2026-11-15' })] });
    assert.equal(linea(ab, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-11-21'].importe, -70);
    // Proveedor sin línea en el Excel: se crea en RS Proveedores con su concepto.
    const nuevo = calcularCashflow({ ...base, importes: [], saldos, vencimientos: [venc({ proveedor_comercial: 'FEDEFARMA' })] });
    assert.equal(linea(nuevo, 'PIO', 'RS Proveedores', 'FEDERACIÓ').celdas['2026-11-21'].importe, -100);
  });
  test('H7-2: signo de la celda, nunca valor absoluto: RS negativo reduce las salidas; RE negativo reduce las entradas', () => {
    const saldos = [banco('PIO', '2026-11-11', 1000), banco('RITA', '2026-11-11', 0)];
    const r = calcularCashflow({ ...base, vencimientos: [], saldos, importes: [
      fila('PIO', '2026-11-21', 'RS Proveedores', 'COFARES', 300), fila('PIO', '2026-11-21', 'RS Proveedores', 'COFARES', -100),
      fila('PIO', '2026-11-21', 'RE Otros cobros', 'Regularización', -50), fila('PIO', '2026-12-01', 'RS Gastos generales', 'Comisión devuelta', -20),
    ] });
    // Dos filas del mismo concepto y decena: −300 + 100 = −200.
    assert.equal(linea(r, 'PIO', 'RS Proveedores', 'COFARES').celdas['2026-11-21'].importe, -200);
    assert.equal(linea(r, 'PIO', 'RE Otros cobros', 'Regularización').celdas['2026-11-21'].importe, -50);
    const d = r.vistas.PIO.decenas['2026-11-21'];
    assert.deepEqual([d.entradas, d.salidas, d.neto, d.saldo], [-50, -200, -250, 750]);
    // Un RS negativo solo: las salidas quedan en positivo (+20) y el saldo sube.
    assert.deepEqual([r.vistas.PIO.decenas['2026-12-01'].salidas, r.vistas.PIO.decenas['2026-12-01'].saldo], [20, 770]);
  });
  test('importe del Excel ausente: no suma y se cuenta; cuenta fuera de cf_cashflow_cuentas: fuera', () => {
    const r = calcularCashflow({ ...base, cuentas: [{ codigo: 'PIO', farmacia: 'PIO' }], vencimientos: [],
      importes: [fila('PIO', '2026-11-21', 'RS Personal', 'Nóminas', null), fila('RITA', '2026-11-21', 'RS Personal', 'Nóminas', 5), fila('PIO', '2026-11-21', 'Varios', 'x', 5)],
      saldos: [banco('PIO', '2026-11-11', 1000)] });
    assert.equal(r.vistas.PIO.decenas['2026-11-21'].saldo, 1000);
    assert.equal(r.vistas.PIO.decenas['2026-11-21'].desconocidos, 1);
    assert.equal(r.vistas.PIO.decenas['2026-11-21'].incompleto, true);
    assert.equal(r.vistas.RITA, undefined);
    assert.equal(r.fuera.filas_otras_cuentas, 1);
    assert.deepEqual(r.fuera.categorias_no_reconocidas, ['Varios']);
  });
  test('traspaso sin contrapartida: aviso gris', () => {
    const r = calcularCashflow({ ...base, vencimientos: [], importes: [fila('PIO', '2026-11-21', 'RS Traspasos', 'A RITA', 500)],
      saldos: [banco('PIO', '2026-11-11', 1000), banco('RITA', '2026-11-11', 1000)] });
    assert.ok(r.avisos.some((a) => a.codigo === 'TRASPASO_SIN_CONTRAPARTIDA' && a.decena === '2026-11-21'));
  });
  test('naranja sin devolución dentro del horizonte; rojo con lo que falta', () => {
    const r = calcularCashflow({ ...base, vencimientos: [], importes: [fila('RITA', '2026-11-21', 'RS Personal', 'Nóminas', 300), fila('PIO', '2026-12-01', 'RS Personal', 'Nóminas', 2000)],
      saldos: [banco('PIO', '2026-11-11', 1000), banco('RITA', '2026-11-11', 100)] });
    const n = r.avisos.find((a) => a.tipo === 'naranja')!;
    assert.deepEqual([n.cuenta, n.cubre, n.decena, n.hasta, n.importe, n.devolucion], ['RITA', 'PIO', '2026-11-21', '2026-11-21', 200, null]);
    const rojo = r.avisos.find((a) => a.tipo === 'rojo')!;
    assert.deepEqual([rojo.decena, rojo.importe], ['2026-12-01', 1200]);
    assert.ok(rojo.hasta! >= '2027-07-21');
  });
  test('media SOE: si no hay meses reales completos, sin media (cuenta el Excel)', () => {
    const r = calcularCashflow({ ...base, vencimientos: [], importes: [fila('PIO', '2026-12-21', 'RE Cobro SOE', 'CatSalut', 900)],
      saldos: [banco('PIO', '2026-11-11', 1000), banco('RITA', '2026-11-11', 0)] });
    assert.equal(linea(r, 'PIO', 'RE Cobro SOE', 'CatSalut').celdas['2026-12-21'].en_saldo, true);
    assert.equal(saldo(r, 'PIO', '2026-12-21'), 1900);
  });
});

describe('H7: antigüedad de la importación', () => {
  const imp = (vigente: boolean, at: string, estado = 'OK') => ({ importacion_id: at, vigente, importado_at: at, origen: 'x', estado });
  test('más de 5 días: gris; 5 días: nada; la última falló: gris; ninguna vigente: gris', () => {
    assert.deepEqual(estadoImportacion([imp(true, '2026-11-10T08:00:00Z')], '2026-11-16').avisos.map((a) => a.codigo), ['IMPORTACION_ANTIGUA']);
    assert.deepEqual(estadoImportacion([imp(true, '2026-11-11T08:00:00Z')], '2026-11-16').avisos, []);
    assert.deepEqual(estadoImportacion([imp(true, '2026-11-15T08:00:00Z'), imp(false, '2026-11-16T07:00:00Z', 'ERROR')], '2026-11-16').avisos.map((a) => a.codigo), ['IMPORTACION_FALLIDA']);
    assert.deepEqual(estadoImportacion([], '2026-11-16').avisos.map((a) => a.codigo), ['SIN_IMPORTACION_VIGENTE']);
    assert.deepEqual(estadoImportacion([imp(true, '2026-11-15T08:00:00Z'), imp(true, '2026-11-14T08:00:00Z')], '2026-11-16').avisos.map((a) => a.codigo), ['SIN_IMPORTACION_VIGENTE']);
    // Fecha de Madrid: las 23:30 UTC del 10/11 ya son el 11/11.
    assert.equal(estadoImportacion([imp(true, '2026-11-10T23:30:00Z')], '2026-11-16').estado.dias, 5);
  });
});

describe('H7: ruta /api/cashflow', () => {
  test('FIXTURES: datos de partida + vencimientos de PIO; REAL: 503 «Pendiente de tablas en Supabase»', async () => {
    const dto = await datosFixtures();
    const app = Fastify();
    const almacen = crearAlmacenPagos(leerSemillaPagos());
    const vencs = await crearAdaptadorFixtures().vencimientos();
    registrarCashflow(app, { modo: 'FIXTURES', pantallaPagos: async () => construirPantalla(vencs, almacen.fuente(), { hoy: almacen.hoy, modo: 'FIXTURES' }) });
    const r = await app.inject({ method: 'GET', url: '/api/cashflow' });
    assert.equal(r.statusCode, 200);
    const j = r.json() as CashflowDTO;
    assert.deepEqual([j.hoy, j.importes.length, j.vencimientos.length], [dto.hoy, dto.importes.length, dto.vencimientos.length]);
    const real = Fastify();
    registrarCashflow(real, { modo: 'REAL', pantallaPagos: async () => { throw new Error('no se lee'); } });
    const r2 = await real.inject({ method: 'GET', url: '/api/cashflow' });
    assert.equal(r2.statusCode, 503);
    assert.deepEqual(r2.json(), { error: 'H7_PENDIENTE', mensaje: TEXTO_H7_PENDIENTE });
    assert.equal((await real.inject({ method: 'POST', url: '/api/cashflow' })).statusCode, 404);
  });
});

describe('H7: lecturas REAL contra el contrato (sin conectar)', () => {
  test('solo SELECT, solo PIO y RITA; conversión de numeric y fail cerrado', async () => {
    for (const sql of Object.values(SQL_CASHFLOW)) {
      assert.match(sql, /^select /);
      assert.doesNotMatch(sql, /\b(insert|update|delete|truncate|grant|alter|create|drop)\b/i);
    }
    const llamadas: unknown[][] = [];
    const filas: Record<string, Record<string, unknown>[]> = {
      [SQL_CASHFLOW.importaciones]: [{ vigente: true, importado_at: new Date('2026-11-10T07:45:00Z'), origen: 'Cashflow.xlsx', estado: 'OK' }],
      [SQL_CASHFLOW.cuentas]: [{ codigo: 'PIO', farmacia: 'PIO' }],
      [SQL_CASHFLOW.importes]: [{ cuenta: 'PIO', decena_inicio: '2026-11-21', decena_fin: '2026-11-30', categoria: 'RS Proveedores', concepto: 'ALLIANCE', importe: '520.00' },
        { cuenta: 'PIO', decena_inicio: '2026-12-01', decena_fin: '2026-12-10', categoria: 'RS Personal', concepto: 'Nóminas', importe: null }],
      [SQL_CASHFLOW.saldos]: [{ cuenta: 'PIO', decena_inicio: '2026-11-11', saldo_formulas: '100.5', saldo_bancos: null }],
    };
    const d = await leerCashflowReal(async (sql, params) => { llamadas.push(params); return filas[sql]; });
    assert.deepEqual(llamadas.slice(1), [[['PIO', 'RITA']], [['PIO', 'RITA']], [['PIO', 'RITA']]]);
    assert.deepEqual(d.importes.map((x) => x.importe), [520, null]);
    assert.deepEqual([d.saldos[0].saldo_formulas, d.saldos[0].saldo_bancos], [100.5, null]);
    assert.equal(d.importaciones[0].importado_at, '2026-11-10T07:45:00.000Z');
    filas[SQL_CASHFLOW.importes] = [{ cuenta: 'SL', decena_inicio: '2026-11-21', decena_fin: '2026-11-30', categoria: 'RS x', concepto: 'x', importe: '1' }];
    await assert.rejects(leerCashflowReal(async (sql) => filas[sql]), /CASHFLOW_CUENTA_NO_PEDIDA/);
    filas[SQL_CASHFLOW.importes] = [{ cuenta: 'PIO', decena_inicio: '2026-11-21', decena_fin: '2026-11-30', categoria: 'RS x', concepto: 'x', importe: 'mil' }];
    await assert.rejects(leerCashflowReal(async (sql) => filas[sql]), /CASHFLOW_IMPORTE_NO_VALIDO/);
  });
});
