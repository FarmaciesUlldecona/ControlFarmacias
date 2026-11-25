// H7: pantalla Cashflow. Previsión por fuente, sin doble cómputo, medias, traspasos neutros, avisos naranja y rojo con
// devolución, antigüedad de la importación, ruta y lecturas REAL. H7-REAL: base simulada de las tablas cf_cashflow_*
// (vigente, ERROR posterior, sin importación, E7, signos, cuadre) y diagnóstico de check:real.
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import Fastify from 'fastify';
import { crearAdaptadorFixtures } from '../adaptador_fixtures.ts';
import { construirPantalla, crearAlmacenPagos } from '../pagos/pagos.ts';
import { leerSemillaPagos } from '../pagos/rutas.ts';
import {
  CONCEPTO_MEDIA, CONCEPTO_VACIO, CONFIG_CASHFLOW, CORRESPONDENCIAS_PROVEEDOR, ORDEN_PRIORIDAD, TRASPASOS_INTERNOS, calcularCashflow, celdaColumna,
  claseMovimiento, clasificarCategoria, esTraspasoInterno, variacionMensual,
  columnasVista, comercialDeConcepto, decenaDe, estadoImportacion, finDecena, moverDecena, ordinalDecena, reglaEstimacion, saldoColumna, siguienteDecena,
  totalCategoria, traspasosNoCompensados, type CashflowDTO, type ImportacionCashflow, type ImporteCashflow, type Linea, type ResultadoCashflow,
  type SaldoCashflow, type VencimientoCashflow,
} from '../cashflow/cashflow.ts';
import { leerSemillaCashflow, registrarCashflow, vencimientoCashflow } from '../cashflow/rutas.ts';
import { SQL_CASHFLOW, claveCategoria, diagnosticoCashflow, leerCashflowReal } from '../cashflow/lectura_real.ts';
import { validarDiagnostico } from '../adaptador_real.ts';

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

// Datos mínimos para casos sintéticos (todos de la importación vigente i1).
let n = 0;
const fila = (cuenta: string, d: string, categoria: string, concepto: string | null, importe: number | null, importacion_id = 'i1'): ImporteCashflow =>
  ({ id: `m${++n}`, importacion_id, cuenta, farmacia: cuenta, decena_inicio: d, decena_fin: finDecena(d), categoria, concepto, importe });
const banco = (cuenta: string, d: string, s: number | null, o: Partial<SaldoCashflow> = {}): SaldoCashflow =>
  ({ id: `s${++n}`, importacion_id: 'i1', cuenta, farmacia: cuenta, decena_inicio: d, saldo_inicial: null, saldo_formulas: s, saldo_bancos: s, ...o });
const importacion = (o: Partial<ImportacionCashflow> = {}): ImportacionCashflow => ({
  importacion_id: 'i1', archivo_nombre: 'Cashflow.xlsx', origen: 'NOCHE', estado: 'OK', detalle_error: null, filas: 10,
  importado_at: '2026-11-15T08:00:00.000Z', vigente: true, ...o,
});
const IMP_OK = [importacion()];
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
    assert.deepEqual([CONFIG_CASHFLOW.meses_media, CONFIG_CASHFLOW.dias_importacion_antigua, CONFIG_CASHFLOW.saldo_minimo], [3, 5, 0]);
    assert.deepEqual([...ORDEN_PRIORIDAD], ['VENCIMIENTOS', 'MANUAL', 'EXCEL', 'MEDIA']);
    assert.equal(reglaEstimacion('RS Modelo 303'), 'ANIO_ANTERIOR');
    assert.equal(reglaEstimacion('RS  modelo 111 retenciones'), 'ANIO_ANTERIOR');
    assert.equal(reglaEstimacion('RS Impuestos'), 'POSICION');
    assert.equal(reglaEstimacion('RE No relacionadas con la farmacia'), 'POSICION');
    assert.equal(reglaEstimacion('RS Traspasos'), null);
    // H7-REAL-4: traspaso interno (lista de Pío, sin mayúsculas, acentos ni espacios) o externo.
    assert.deepEqual(TRASPASOS_INTERNOS, { PIO: ['TRANSFERENCIA DE RITA A PIO', 'La Caixa Rita', 'DEPOSITO CONECTADO'], RITA: ['TRASPÀS A PIO DEPOSITO CON.', 'DEPÓSITO CONECTADO'] });
    assert.equal(esTraspasoInterno('PIO', 'la caixa  RITA'), true);
    assert.equal(esTraspasoInterno('PIO', 'Depósito conectado'), true);
    assert.equal(esTraspasoInterno('RITA', 'traspas a pio deposito con.'), true);
    assert.equal(esTraspasoInterno('RITA', 'Depositoconectado'), true);
    assert.equal(esTraspasoInterno('RITA', 'La Caixa Rita'), false); // de la lista de PIO, no de RITA
    assert.equal(esTraspasoInterno('RITA', 'TRASPASO A LA SL (JUBILACIO ETC)'), false);
    assert.equal(claseMovimiento('PIO', 'RS Traspasos', 'TRASPASO A FONDOS/VALORS')?.clase, 'TRASPASO_EXTERNO');
    assert.equal(claseMovimiento('PIO', 'RE Traspasos', 'TRANSFERENCIA DE RITA A PIO')?.clase, 'TRASPASO');
    assert.equal(claseMovimiento('PIO', 'RS Personal', 'La Caixa Rita')?.clase, 'FARMACIA');
    assert.equal(reglaEstimacion('Varios'), null);
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
    assert.equal(r.vistas.PIO.saldo_partida, 25000);
    assert.equal(r.vistas.RITA.saldo_partida, 2000);
    assert.equal(r.vistas.CONSOLIDADO.saldo_partida, 27000);
    assert.equal(r.vistas.PIO.decenas['2026-11-01'].real, true);
    assert.equal(r.vistas.PIO.decenas['2026-11-11'].real, false);
    // Todas las decenas reales (desde octubre de 2025) con saldo positivo (fixtures coherentes).
    assert.equal(r.decenas[0], '2025-10-01');
    for (const v of ['PIO', 'RITA'] as const) {
      for (const d of r.decenas.filter((x) => x <= '2026-11-01')) assert.ok((saldo(r, v, d) as number) > 0, `${v} ${d}`);
    }
  });

  test('previsión por fuente: ALLIANCE 11–20/11: vencimientos (472,22) como mínimo; gana su media (6.000); el Excel (520) no cuenta: posible duplicado o diferencia', async () => {
    const r = calcularCashflow(await datosFixtures());
    const c = linea(r, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-11-11'];
    // H7-REAL-5: vencimientos conocidos 472,22 inferiores a la media del concepto en la 2.ª decena: cuenta la media.
    assert.deepEqual([c.fuente, c.importe, c.vencimientos?.neto, c.media?.base.map((b) => b.clave)], ['MEDIA', -6000, 472.22, ['2026-08-11', '2026-09-11', '2026-10-11']]);
    assert.equal(c.excel, -520);
    assert.equal(c.diferencia, true);
    assert.deepEqual(c.vencimientos?.incluidos.map((v) => v.vencimiento_id), ['90000000-0000-4000-8000-000000000002']);
    // Sin la regla (como antes): los vencimientos.
    const antes = calcularCashflow({ ...(await datosFixtures()), config: { ...CONFIG_CASHFLOW, vencimientos_como_minimo: false } });
    assert.deepEqual([linea(antes, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-11-11'].fuente, linea(antes, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-11-11'].importe], ['VENCIMIENTOS', -472.22]);
    // H7-REAL-3: «RS Proveedores» tiene vencimientos → por concepto. 11–20/11: ALLIANCE por vencimientos y el resto por la
    // media de la 2.ª decena sin ALLIANCE (4.500 + 3.500 + 800); en 21–30/11 (nada previsto), la media de toda la categoría.
    const resto = linea(r, 'PIO', 'RS Proveedores', CONCEPTO_MEDIA).celdas['2026-11-11'];
    assert.deepEqual([resto.importe, resto.media?.excluidos, resto.en_saldo], [-8800, ['ALLIANCE'], true]);
    assert.deepEqual(resto.media?.base.map((b) => b.importe), [-8800, -8800, -8800]);
    assert.equal(linea(r, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-11-21'], undefined);
    const prov = linea(r, 'PIO', 'RS Proveedores', CONCEPTO_MEDIA).celdas['2026-11-21'];
    assert.deepEqual([prov.fuente, prov.importe, prov.media?.base.map((b) => b.clave)], ['MEDIA', -15500, ['2026-08-21', '2026-09-21', '2026-10-21']]);
    // Real: del Excel, aunque haya vencimientos (04/11).
    assert.equal(linea(r, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-11-01'].fuente, 'REAL');
    // RITA: nunca vencimientos del sistema.
    assert.ok(r.vistas.RITA.lineas.every((l) => Object.values(l.celdas).every((x) => x.fuente !== 'VENCIMIENTOS')));
    // Lo que no entra, contado: COFARES/FEDEFARMA sin nombre comercial, y los sin pagar de decenas reales.
    assert.ok(r.fuera.venc_sin_concepto.length >= 1);
    assert.ok(r.fuera.venc_en_decenas_reales.length >= 1);
    // SL: declarada y fuera de la pantalla, sin filas en la importación vigente.
    assert.deepEqual([r.fuera.cuentas_fuera, r.fuera.filas_otras_cuentas, r.fuera.filas_otra_importacion], [['SL'], 0, 0]);
  });

  test('H7-REAL: fixtures cuadran en todas las decenas; E7 solo en PIO 21–31/10/2026 (banco 35,20 por debajo de las fórmulas)', async () => {
    const r = calcularCashflow(await datosFixtures());
    for (const v of ['PIO', 'RITA'] as const) {
      for (const [d, x] of Object.entries(r.vistas[v].decenas)) if (x.cuadre) assert.equal(x.cuadra, true, `${v} ${d}`);
    }
    assert.ok(!r.avisos.some((a) => a.codigo === 'IMPORTACION_NO_CUADRA'));
    const conDif = (['PIO', 'RITA'] as const).flatMap((v) => Object.values(r.vistas[v].decenas).filter((x) => x.diferencia_banco !== null).map((x) => `${v} ${x.decena}`));
    assert.deepEqual(conDif, ['PIO 2026-10-21']);
    const oct = r.vistas.PIO.decenas['2026-10-21'];
    assert.equal(oct.diferencia_banco, -35.2);
    assert.equal(oct.saldo, oct.saldo_bancos); // real: el del banco
    assert.equal(r.vistas.CONSOLIDADO.decenas['2026-10-21'].diferencia_banco, -35.2);
    assert.equal(saldoColumna(r.vistas.PIO, columnasVista(r.hoy, 'decenas')[1]).diferencia_banco, -35.2);
  });

  test('sin doble cómputo (H7-REAL-3/5): 11–20/11 suma ALLIANCE (el mayor entre vencimientos y su media) + la media del resto de proveedores, nunca el Excel', async () => {
    const dto = await datosFixtures();
    // 25.000 + TPV 10.000 + efectivo 3.000 − ALLIANCE 6.000 (media > vencimientos) − resto de proveedores 8.800 − suministros 900 = 22.300
    const r = calcularCashflow(dto);
    assert.equal(saldo(r, 'PIO', '2026-11-11'), 22300);
    const usadas = r.vistas.PIO.lineas.flatMap((l) => (l.celdas['2026-11-11']?.en_saldo ? [`${l.categoria}|${l.concepto}`] : []));
    assert.deepEqual(usadas.sort(), ['RE Cobro TPV|Media calculada', 'RE Cobro efectivo|Media calculada', 'RS Gastos generales|Media calculada',
      'RS Proveedores|ALLIANCE', 'RS Proveedores|Media calculada'].sort());
    assert.equal(r.vistas.PIO.decenas['2026-11-11'].salidas, -15700);
    // La media del resto sigue sin ALLIANCE (el concepto con vencimientos).
    assert.deepEqual(linea(r, 'PIO', 'RS Proveedores', CONCEPTO_MEDIA).celdas['2026-11-11'].media?.excluidos, ['ALLIANCE']);
    // «Excel» en todas: solo lo anotado (y los vencimientos): 25.000 − 472,22.
    const e = calcularCashflow(dto, Object.fromEntries(r.categorias_media.map((c) => [c, 'excel' as const])));
    assert.equal(saldo(e, 'PIO', '2026-11-11'), 24527.78);
  });

  test('media por posición de decena (últimos 3 meses reales): TPV, efectivo y SOE en su decena; Excel antes que la media; «Media / Excel»', async () => {
    const dto = await datosFixtures();
    const r = calcularCashflow(dto);
    const tpv = linea(r, 'PIO', 'RE Cobro TPV', CONCEPTO_MEDIA);
    // 2.ª decena: 11–20 de agosto, septiembre y octubre (los cobros varían +300/−100/−200 y suman 0).
    assert.deepEqual([tpv.celdas['2026-11-11'].fuente, tpv.celdas['2026-11-11'].importe, tpv.celdas['2026-11-11'].en_saldo], ['MEDIA', 10000, true]);
    assert.deepEqual(tpv.celdas['2026-11-11'].media?.base.map((b) => b.clave), ['2026-08-11', '2026-09-11', '2026-10-11']);
    assert.deepEqual([tpv.celdas['2026-11-11'].media?.posicion, tpv.celdas['2026-11-11'].media?.regla], [2, 'POSICION']);
    // 1.ª y 3.ª decena con su propia base (1.ª: septiembre, octubre y noviembre).
    assert.equal(tpv.celdas['2026-12-01'].importe, 11000);
    assert.deepEqual(tpv.celdas['2026-12-01'].media?.base.map((b) => b.clave), ['2026-09-01', '2026-10-01', '2026-11-01']);
    assert.equal(tpv.celdas['2026-11-21'].importe, 9000);
    // Anotado en el Excel (TPV de Navidad): manda el Excel y no se añade media.
    assert.equal(tpv.celdas['2026-12-21'], undefined);
    assert.deepEqual([linea(r, 'PIO', 'RE Cobro TPV', 'TPV CaixaBank').celdas['2026-12-21'].fuente, linea(r, 'PIO', 'RE Cobro TPV', 'TPV CaixaBank').celdas['2026-12-21'].importe], ['EXCEL', 12500]);
    // SOE: solo en la 3.ª decena (la media de las otras posiciones es 0: no hay cifra).
    const soe = linea(r, 'RITA', 'RE Cobro SOE', CONCEPTO_MEDIA);
    assert.equal(soe.celdas['2026-11-21'].importe, 20000);
    assert.deepEqual(soe.celdas['2026-11-21'].media?.base.map((x) => x.clave), ['2026-08-21', '2026-09-21', '2026-10-21']);
    assert.equal(soe.celdas['2026-11-11'], undefined);
    assert.equal(soe.celdas['2026-12-01'], undefined);
    // Con «Excel»: solo lo anotado; la media queda a la vista sin sumar.
    const e = calcularCashflow(dto, { 'RE Cobro TPV': 'excel' });
    assert.equal(linea(e, 'PIO', 'RE Cobro TPV', CONCEPTO_MEDIA).celdas['2026-11-11'].en_saldo, false);
    assert.equal((saldo(r, 'PIO', '2026-11-11') as number) - (saldo(e, 'PIO', '2026-11-11') as number), 10000);
    // Columna: la cifra que no suma también se ve.
    const col = columnasVista('2026-11-16', 'decenas')[3];
    const t = totalCategoria(r.vistas.PIO.lineas.filter((l) => l.categoria === 'RE Cobro TPV'), col, r.vistas.PIO);
    assert.deepEqual([t?.importe, t?.sin_usar], [10000, null]);
    const te = totalCategoria(e.vistas.PIO.lineas.filter((l) => l.categoria === 'RE Cobro TPV'), col, e.vistas.PIO);
    assert.deepEqual([te?.importe, te?.sin_usar], [null, 10000]);
    // Consolidado: la media de efectivo de las dos cuentas (PIO 3.000 + RITA 1.200).
    const ef = totalCategoria(r.vistas.CONSOLIDADO.lineas.filter((l) => l.categoria === 'RE Cobro efectivo'), col, r.vistas.CONSOLIDADO);
    assert.equal(ef?.importe, 4200);
    // Todas las categorías RE y RS con historia llevan media (también «no relacionadas»); de los traspasos, solo los externos.
    assert.ok(['RS Proveedores', 'RS Gastos generales', 'RS No relacionadas con la farmacia', 'RE No relacionadas con la farmacia', 'RS Traspasos'].every((c) => r.categorias_media.includes(c)));
    assert.ok(!r.categorias_media.includes('RE Traspasos'));
    // RS Personal: anotada en el Excel en todas sus decenas (la 2.ª no tiene historia): sin media.
    assert.ok(!r.categorias_media.includes('RS Personal'));
  });

  test('RITA: «RE Cobro efectivo / COBRO EFECTIU» real en todas las decenas y previsto por media', async () => {
    const r = calcularCashflow(await datosFixtures());
    const ef = linea(r, 'RITA', 'RE Cobro efectivo', 'COBRO EFECTIU');
    const reales = r.decenas.filter((d) => d <= '2026-11-01');
    assert.ok(reales.every((d) => ef.celdas[d]?.fuente === 'REAL' && (ef.celdas[d].importe as number) > 0));
    const m = linea(r, 'RITA', 'RE Cobro efectivo', CONCEPTO_MEDIA);
    assert.ok(r.decenas.filter((d) => d > '2026-11-01').every((d) => m.celdas[d]?.importe === 1200));
    assert.equal(r.vistas.RITA.decenas['2026-11-01'].entradas! > 0, true);
  });

  test('«RS Modelo …» (trimestrales): el mismo mes del año anterior, no la media', async () => {
    const r = calcularCashflow(await datosFixtures());
    const m303 = linea(r, 'PIO', 'RS Modelo 303', CONCEPTO_MEDIA);
    assert.deepEqual([m303.celdas['2027-01-11'].importe, m303.celdas['2027-01-11'].media?.regla, m303.celdas['2027-01-11'].media?.base.map((b) => b.clave)],
      [-8500, 'ANIO_ANTERIOR', ['2026-01-11']]);
    assert.equal(m303.celdas['2027-04-11'].importe, -7900);
    assert.equal(m303.celdas['2027-10-11'].importe, -8800);
    // Sin modelo el año anterior (noviembre y diciembre de 2025): nada; la media por posición daría −2.933,33.
    assert.equal(m303.celdas['2026-11-11'], undefined);
    assert.equal(m303.celdas['2026-12-11'], undefined);
    // Más de 12 meses por delante (el año anterior aún no es real): nada.
    assert.equal(m303.celdas['2027-12-11'], undefined);
    assert.equal(linea(r, 'PIO', 'RS Modelo 111', CONCEPTO_MEDIA).celdas['2027-01-11'].importe, -1500);
    assert.equal(linea(r, 'RITA', 'RS Modelo 303', CONCEPTO_MEDIA).celdas['2027-01-11'].importe, -3100);
  });

  test('traspasos internos: neutros en el consolidado y sin media; los no compensados no son aviso (línea plegada de las decenas visibles)', async () => {
    const r = calcularCashflow(await datosFixtures());
    assert.equal(linea(r, 'PIO', 'RS Traspasos', 'La Caixa Rita').celdas['2026-09-11'].importe, -3000);
    assert.equal(linea(r, 'RITA', 'RE Traspasos', 'DEPÓSITO CONECTADO').celdas['2026-09-11'].importe, 3000);
    assert.ok(r.vistas.CONSOLIDADO.lineas.every((l) => l.clase !== 'TRASPASO'));
    assert.equal(r.vistas.CONSOLIDADO.decenas['2026-09-11'].traspasos, 0);
    // Sin media: la 3.ª decena futura no lleva los internos sin contrapartida de agosto a octubre.
    for (const v of ['PIO', 'RITA'] as const) assert.ok(r.vistas[v].lineas.filter((l) => l.clase === 'TRASPASO').every((l) => !l.media && Object.values(l.celdas).every((c) => c.fuente !== 'MEDIA')));
    // H7-REAL-4: externos con media por concepto (y el Excel manda); cuentan en el consolidado.
    const fondos = linea(r, 'PIO', 'RS Traspasos', 'TRASPASO A FONDOS/VALORS');
    assert.deepEqual([fondos.clase, fondos.celdas['2026-12-01'].fuente, fondos.celdas['2026-12-01'].importe, fondos.celdas['2027-02-01'].fuente, fondos.celdas['2027-02-01'].importe],
      ['TRASPASO_EXTERNO', 'MEDIA', -1000, 'EXCEL', -2500]);
    assert.equal(linea(r, 'RITA', 'RS Traspasos', 'TRASPASO A LA SL (JUBILACIO ETC)').celdas['2026-11-11'].importe, -500);
    assert.equal(r.vistas.CONSOLIDADO.decenas['2026-11-11'].traspasos_externos, -500);
    // Internos sin contrapartida (DEPOSITO CONECTADO, TRASPÀS A PIO…): ningún aviso; en la vista de decenas solo 21–31/10 es visible.
    assert.equal(r.vistas.CONSOLIDADO.decenas['2026-10-21'].traspasos, -16000);
    assert.ok(r.avisos.every((a) => !/TRASPASO/.test(a.codigo)));
    assert.deepEqual(traspasosNoCompensados(r.vistas.CONSOLIDADO, columnasVista(r.hoy, 'decenas')), [{ decena: '2026-10-21', importe: -16000 }]);
    assert.deepEqual(traspasosNoCompensados(r.vistas.CONSOLIDADO, columnasVista(r.hoy, 'mes')).map((x) => x.decena), ['2026-08-21', '2026-09-21', '2026-10-21']);
    for (const d of ['2026-11-11', '2027-03-01', '2027-06-21']) {
      assert.equal(saldo(r, 'CONSOLIDADO', d), Math.round(((saldo(r, 'PIO', d) as number) + (saldo(r, 'RITA', d) as number)) * 100) / 100);
    }
  });

  test('H7-2: fixtures con un RS negativo (abono de COFARES en PIO) y un RE negativo (regularización en RITA)', async () => {
    const r = calcularCashflow(await datosFixtures());
    assert.equal(linea(r, 'PIO', 'RS Proveedores', 'COFARES').celdas['2026-07-11'].importe, -4250);
    assert.equal(linea(r, 'PIO', 'RS Proveedores', 'COFARES').celdas['2026-07-11'].excel_filas, 2);
    assert.equal(linea(r, 'RITA', 'RE Otros cobros', 'Regularización mutua').celdas['2026-11-21'].importe, -120);
    const p = r.vistas.PIO.decenas;
    assert.equal(p['2026-12-01'].saldo, Math.round(((p['2026-11-21'].saldo as number) + (p['2026-12-01'].neto as number)) * 100) / 100);
  });

  test('«no relacionadas con la farmacia»: cuentan en el saldo, no en el cash flow generado farmacia', async () => {
    const r = calcularCashflow(await datosFixtures());
    const d = r.vistas.PIO.decenas['2026-12-01'];
    assert.equal(d.no_relacionadas, 650 - 1200);
    // Neto = farmacia + no relacionadas + traspasos externos (H7-REAL-4: el fondo de PIO, −1.000 en la 1.ª decena).
    assert.equal(d.traspasos_externos, -1000);
    assert.equal(d.neto, Math.round(((d.farmacia as number) + (d.no_relacionadas as number) + (d.traspasos_externos as number)) * 100) / 100);
  });

  {
    test('avisos (media): naranja RITA cubierta por PIO en 11–20/12 hasta la SOE (21–31/12); rojo del consolidado en 11–20/01/2027', async () => {
      const r = calcularCashflow(await datosFixtures());
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
      assert.deepEqual([saldo(r, 'PIO', '2027-01-11'), saldo(r, 'RITA', '2027-01-11'), rojos[0].importe], [-3400, 780, 2620]);
      assert.equal(saldo(r, 'RITA', '2026-12-11'), -5020);
      // Gris: importación de hace 6 días (y ninguno por traspasos).
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
    assert.equal(c?.importe, -12000); // 6.000 real (1–10/11) + 6.000 media de ALLIANCE (11–20/11, mayor que sus vencimientos)
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
  test('H7-REAL-2: traspaso sin contrapartida: ningún aviso; cuenta en la línea plegada solo si su decena es visible', () => {
    const r = calcularCashflow({ ...base, vencimientos: [], importes: [fila('PIO', '2026-11-21', 'RS Traspasos', 'La Caixa Rita', 500), fila('PIO', '2027-06-21', 'RS Traspasos', 'La Caixa Rita', 700)],
      saldos: [banco('PIO', '2026-11-11', 1000), banco('RITA', '2026-11-11', 1000)] });
    assert.deepEqual(r.avisos.filter((a) => a.tipo === 'gris'), []);
    assert.equal(r.vistas.PIO.decenas['2026-11-21'].saldo, 500); // cuenta en el saldo de su cuenta
    assert.deepEqual(traspasosNoCompensados(r.vistas.CONSOLIDADO, columnasVista(base.hoy, 'decenas')), [{ decena: '2026-11-21', importe: -500 }]);
    assert.equal(traspasosNoCompensados(r.vistas.CONSOLIDADO, columnasVista(base.hoy, 'mes')).length, 2);
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
  test('sin historia real de la categoría: sin media (cuenta el Excel)', () => {
    const r = calcularCashflow({ ...base, vencimientos: [], importes: [fila('PIO', '2026-12-21', 'RE Cobro SOE', 'CatSalut', 900)],
      saldos: [banco('PIO', '2026-11-11', 1000), banco('RITA', '2026-11-11', 0)] });
    assert.equal(linea(r, 'PIO', 'RE Cobro SOE', 'CatSalut').celdas['2026-12-21'].en_saldo, true);
    assert.equal(saldo(r, 'PIO', '2026-12-21'), 1900);
    assert.ok(r.vistas.PIO.lineas.every((l) => !l.media));
  });
});

describe('H7-REAL-2: previsión por cuenta y categoría (vencimientos > apunte manual > Excel > media)', () => {
  // Real hasta 11–20/11/2026 (hoy 16/11 → la decena actual también es real aquí): meses reales completos.
  const hoy = '2026-11-25';
  const base = { hoy, importaciones: IMP_OK, cuentas: CUENTAS };
  const reales = (cuenta: string, categoria: string, concepto: string, porPosicion: [number, number, number], desde = '2026-06-01', hasta = '2026-11-11') => {
    const out: ImporteCashflow[] = [];
    for (let d = desde; d <= hasta; d = siguienteDecena(d)) out.push(fila(cuenta, d, categoria, concepto, porPosicion[ordinalDecena(d) - 1]));
    return out.filter((f) => f.importe !== 0);
  };
  const saldos = [banco('PIO', '2026-06-01', 0, { saldo_bancos: null }), banco('PIO', '2026-11-11', 10000), banco('RITA', '2026-11-11', 0)];
  const media = (r: ResultadoCashflow, cuenta: 'PIO' | 'RITA', categoria: string) => r.vistas[cuenta].lineas.find((l) => l.categoria === categoria && l.media)?.celdas ?? {};

  test('posición de decena: últimos 3 meses reales de la misma decena del mes (1.ª, 2.ª o 3.ª)', () => {
    // 1.ª: 100; 2.ª: 200; 3.ª: 300, salvo septiembre (600): 3.ª = (600 + 300 + 300) / 3 = 400.
    const importes = [...reales('PIO', 'RS Gastos generales', 'Varios', [100, 200, 300]).filter((f) => f.decena_inicio !== '2026-09-21'),
      fila('PIO', '2026-09-21', 'RS Gastos generales', 'Varios', 600)];
    const r = calcularCashflow({ ...base, vencimientos: [], importes, saldos });
    const m = media(r, 'PIO', 'RS Gastos generales');
    assert.deepEqual([m['2026-11-21'].importe, m['2026-12-01'].importe, m['2026-12-11'].importe, m['2026-12-21'].importe], [-400, -100, -200, -400]);
    assert.deepEqual(m['2026-11-21'].media?.base.map((b) => [b.clave, b.importe]), [['2026-08-21', -300], ['2026-09-21', -600], ['2026-10-21', -300]]);
    assert.deepEqual(m['2026-12-01'].media?.base.map((b) => b.clave), ['2026-09-01', '2026-10-01', '2026-11-01']);
    // Una decena real sin filas cuenta como 0; N en un único punto (CONFIG_CASHFLOW.meses_media).
    const cfg = { ...CONFIG_CASHFLOW, meses_media: 2 };
    const r2 = calcularCashflow({ ...base, config: cfg, vencimientos: [], saldos, importes: importes.filter((f) => f.decena_inicio !== '2026-10-21') });
    assert.equal(media(r2, 'PIO', 'RS Gastos generales')['2026-11-21'].importe, -300); // (600 + 0) / 2: 21–30/09 y 21–31/10
    assert.deepEqual(media(r2, 'PIO', 'RS Gastos generales')['2026-11-21'].media?.base.map((b) => b.importe), [-600, 0]);
  });

  test('sin doble cómputo, categoría SIN vencimientos: con Excel en la categoría y decena no se añade media (aunque sea de otro concepto)', () => {
    const importes = [
      ...reales('PIO', 'RS Gastos generales', 'Luz', [1000, 1000, 1000]), ...reales('PIO', 'RS Gastos generales', 'Agua', [500, 500, 500]),
      fila('PIO', '2026-12-11', 'RS Gastos generales', 'Agua', 450), // anotado en el Excel
    ];
    const r = calcularCashflow({ ...base, vencimientos: [], importes, saldos });
    const m = media(r, 'PIO', 'RS Gastos generales');
    assert.equal(m['2026-12-11'], undefined);
    assert.equal(m['2026-12-21'].importe, -1500);
    assert.deepEqual([r.vistas.PIO.decenas['2026-12-11'].salidas, r.vistas.PIO.decenas['2026-12-21'].salidas], [-450, -1500]);
  });

  test('H7-REAL-3: categoría CON vencimientos: por concepto; el resto lleva la media de la categoría sin los conceptos ya previstos', () => {
    const importes = [
      ...reales('PIO', 'RS Proveedores', 'ALLIANCE', [1000, 1000, 1000]), ...reales('PIO', 'RS Proveedores', 'COFARES', [500, 500, 500]),
      ...reales('PIO', 'RS Proveedores', 'Varios', [200, 200, 200]),
      fila('PIO', '2026-12-11', 'RS Proveedores', 'COFARES', 450), // anotado en el Excel
    ];
    // Vencimiento de ALLIANCE (1.200) mayor que su media (1.000): ganan los vencimientos (H7-REAL-5).
    const vencimientos = [venc({ fecha_vencimiento: '2026-12-05', importe: 1200 })];
    const r = calcularCashflow({ ...base, vencimientos, importes, saldos });
    const m = media(r, 'PIO', 'RS Proveedores');
    // 1–10/12: vencimiento de ALLIANCE (1.200) + media del resto sin ALLIANCE (500 + 200).
    assert.deepEqual([m['2026-12-01'].importe, m['2026-12-01'].media?.excluidos], [-700, ['ALLIANCE']]);
    // 11–20/12: Excel de COFARES (450) + media del resto sin COFARES (1.000 + 200).
    assert.deepEqual([m['2026-12-11'].importe, m['2026-12-11'].media?.excluidos], [-1200, ['COFARES']]);
    // 21–31/12: nada previsto: media de toda la categoría.
    assert.deepEqual([m['2026-12-21'].importe, m['2026-12-21'].media?.excluidos], [-1700, []]);
    const d = r.vistas.PIO.decenas;
    assert.deepEqual([d['2026-12-01'].salidas, d['2026-12-11'].salidas, d['2026-12-21'].salidas], [-1900, -1650, -1700]);
    // Correspondencia por nombre comercial: un vencimiento de FEDEFARMA excluye «FEDERACIO» de la media.
    const fed = calcularCashflow({ ...base, saldos, vencimientos: [venc({ proveedor_comercial: 'FEDEFARMA', fecha_vencimiento: '2026-12-05', importe: 400 })],
      importes: [...reales('PIO', 'RS Proveedores', 'FEDERACIO', [300, 300, 300]), ...reales('PIO', 'RS Proveedores', 'HEFAME', [100, 100, 100])] });
    assert.deepEqual([media(fed, 'PIO', 'RS Proveedores')['2026-12-01'].importe, fed.vistas.PIO.decenas['2026-12-01'].salidas], [-100, -500]);
    // Con «Excel»: solo lo anotado y los vencimientos; la media, a la vista sin sumar.
    const e = calcularCashflow({ ...base, vencimientos, importes, saldos }, { 'RS Proveedores': 'excel' });
    assert.equal(media(e, 'PIO', 'RS Proveedores')['2026-12-21'].en_saldo, false);
    assert.deepEqual([e.vistas.PIO.decenas['2026-12-01'].salidas, e.vistas.PIO.decenas['2026-12-21'].salidas], [-1200, null]);
  });

  test('H7-REAL-5: vencimientos como mínimo, por concepto y decena: menores que la media → media; mayores → vencimientos; sin vencimientos → media', () => {
    // ALLIANCE: 1.000 en la 1.ª decena, 3.000 en la 2.ª; COFARES 500 en todas (media del resto).
    const importes = [...reales('PIO', 'RS Proveedores', 'ALLIANCE', [1000, 3000, 0]), ...reales('PIO', 'RS Proveedores', 'COFARES', [500, 500, 500])];
    const vencimientos = [
      venc({ vencimiento_id: 'v1', fecha_vencimiento: '2026-12-05', importe: 400 }), // 1.ª decena: 400 < 1.000 → media
      venc({ vencimiento_id: 'v2', fecha_vencimiento: '2026-12-15', importe: 3500 }), // 2.ª decena: 3.500 > 3.000 → vencimientos
      venc({ vencimiento_id: 'v3', fecha_vencimiento: '2026-12-25', importe: -50, sentido: 'ABONO' }), // 3.ª: media 0 → vencimientos
    ];
    const r = calcularCashflow({ ...base, vencimientos, importes, saldos });
    const a = linea(r, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas;
    assert.deepEqual([a['2026-12-01'].fuente, a['2026-12-01'].importe, a['2026-12-01'].vencimientos?.neto], ['MEDIA', -1000, 400]);
    assert.deepEqual(a['2026-12-01'].media?.base.map((b) => b.clave), ['2026-09-01', '2026-10-01', '2026-11-01']);
    assert.deepEqual([a['2026-12-11'].fuente, a['2026-12-11'].importe, a['2026-12-11'].media], ['VENCIMIENTOS', -3500, null]);
    assert.deepEqual([a['2026-12-21'].fuente, a['2026-12-21'].importe], ['VENCIMIENTOS', 50]);
    // Sin vencimientos (enero): media del concepto dentro de la media de la categoría (ALLIANCE + COFARES).
    assert.equal(a['2027-01-01'], undefined);
    assert.equal(media(r, 'PIO', 'RS Proveedores')['2027-01-01'].importe, -1500);
    // La media del resto excluye ALLIANCE también cuando ganó su media (sin doble cómputo).
    assert.deepEqual([media(r, 'PIO', 'RS Proveedores')['2026-12-01'].importe, media(r, 'PIO', 'RS Proveedores')['2026-12-01'].media?.excluidos], [-500, ['ALLIANCE']]);
    assert.deepEqual([r.vistas.PIO.decenas['2026-12-01'].salidas, r.vistas.PIO.decenas['2026-12-11'].salidas], [-1500, -4000]);
    // Con «Excel» en la categoría: los vencimientos, como antes (la media no entra).
    const e = calcularCashflow({ ...base, vencimientos, importes, saldos }, { 'RS Proveedores': 'excel' });
    assert.deepEqual([linea(e, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-12-01'].fuente, e.vistas.PIO.decenas['2026-12-01'].salidas], ['VENCIMIENTOS', -400]);
    // Vencimiento sin importe conocido: no se compara (los vencimientos, saldo incompleto).
    const n = calcularCashflow({ ...base, vencimientos: [venc({ fecha_vencimiento: '2026-12-05', importe: null })], importes, saldos });
    assert.equal(linea(n, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-12-01'].fuente, 'VENCIMIENTOS');
  });

  test('«RS Modelo …»: la misma decena del mismo mes del año anterior; sin año anterior real, nada', () => {
    const importes = [
      fila('PIO', '2026-01-11', 'RS Modelo 303', 'IVA', 900), fila('PIO', '2026-04-11', 'RS Modelo 303', 'IVA', 700),
      fila('PIO', '2026-07-11', 'RS Modelo 303', 'IVA', 800), fila('PIO', '2026-10-11', 'RS Modelo 303', 'IVA', 1000),
    ];
    const r = calcularCashflow({ ...base, vencimientos: [], importes, saldos: [banco('PIO', '2025-12-01', 0, { saldo_bancos: null }), ...saldos] });
    const m = media(r, 'PIO', 'RS Modelo 303');
    assert.deepEqual([m['2027-01-11'].importe, m['2027-04-11'].importe, m['2027-07-11'].importe], [-900, -700, -800]);
    assert.equal(m['2027-01-11'].media?.regla, 'ANIO_ANTERIOR');
    // Fuera de los meses del modelo, nada (la media por posición daría −833,33 en cada 2.ª decena).
    assert.deepEqual([m['2026-12-11'], m['2027-02-11'], m['2027-03-11']], [undefined, undefined, undefined]);
    // Año anterior antes de los datos de la cuenta: nada.
    const sin = calcularCashflow({ ...base, vencimientos: [], importes: importes.slice(1), saldos });
    assert.equal(media(sin, 'PIO', 'RS Modelo 303')['2027-01-11'], undefined);
  });

  test('traspasos internos: neutros, sin media; «no relacionadas»: con media', () => {
    const importes = [...reales('PIO', 'RS Traspasos', 'La Caixa Rita', [0, 0, 5000]), ...reales('PIO', 'RS No relacionadas con la farmacia', 'Préstamo', [300, 0, 0])];
    const r = calcularCashflow({ ...base, vencimientos: [], importes, saldos });
    assert.equal(r.vistas.PIO.lineas.find((l) => l.categoria === 'RS Traspasos' && l.media), undefined);
    assert.ok(Object.values(r.vistas.PIO.lineas.find((l) => l.concepto === 'La Caixa Rita')!.celdas).every((c) => c.fuente === 'REAL'));
    assert.equal(media(r, 'PIO', 'RS No relacionadas con la farmacia')['2026-12-01'].importe, -300);
    assert.deepEqual(r.categorias_media, ['RS No relacionadas con la farmacia']);
  });

  test('H7-REAL-4: traspasos externos: media por concepto (en su línea), en el saldo de la cuenta y del consolidado; el Excel manda (sin doble cómputo)', () => {
    const importes = [
      ...reales('RITA', 'RS Traspasos', 'TRASPASO A LA SL (JUBILACIO ETC)', [0, 6000, 0]), ...reales('RITA', 'RS Traspasos', 'Otro fondo', [0, 1000, 0]),
      ...reales('RITA', 'RS Traspasos', 'DEPÓSITO CONECTADO', [0, 9000, 0]), // interno: sin media
      fila('RITA', '2026-12-11', 'RS Traspasos', 'TRASPASO A LA SL (JUBILACIO ETC)', 2000), // anotado: manda
    ];
    const conSaldos = { ...base, vencimientos: [], importes, saldos: [...saldos.filter((s) => s.cuenta !== 'RITA'), banco('RITA', '2026-11-11', 50000)] };
    const r = calcularCashflow(conSaldos);
    const sl = linea(r, 'RITA', 'RS Traspasos', 'TRASPASO A LA SL (JUBILACIO ETC)');
    assert.equal(sl.clase, 'TRASPASO_EXTERNO');
    assert.deepEqual([sl.celdas['2026-11-21'], sl.celdas['2027-01-11'].fuente, sl.celdas['2027-01-11'].importe], [undefined, 'MEDIA', -6000]);
    assert.deepEqual([sl.celdas['2026-12-11'].fuente, sl.celdas['2026-12-11'].importe], ['EXCEL', -2000]);
    // Por concepto: «Otro fondo» lleva su media aunque la SL esté anotada en 11–20/12.
    assert.equal(linea(r, 'RITA', 'RS Traspasos', 'Otro fondo').celdas['2026-12-11'].importe, -1000);
    assert.ok(Object.values(linea(r, 'RITA', 'RS Traspasos', 'DEPÓSITO CONECTADO').celdas).every((c) => c.fuente === 'REAL'));
    const d = r.vistas.RITA.decenas;
    assert.deepEqual([d['2026-12-11'].traspasos_externos, d['2026-12-11'].traspasos, d['2026-12-11'].saldo], [-3000, null, 47000]);
    // Consolidado: el externo cuenta (línea y saldo); el interno no compensado, solo en la línea plegada.
    assert.ok(r.vistas.CONSOLIDADO.lineas.some((l) => l.concepto === 'TRASPASO A LA SL (JUBILACIO ETC)'));
    assert.ok(!r.vistas.CONSOLIDADO.lineas.some((l) => l.concepto === 'DEPÓSITO CONECTADO'));
    assert.equal(r.vistas.CONSOLIDADO.decenas['2026-12-11'].traspasos_externos, -3000);
    assert.equal(r.vistas.CONSOLIDADO.decenas['2026-12-11'].traspasos, null);
    assert.equal(r.vistas.CONSOLIDADO.decenas['2026-11-11'].traspasos, -9000);
    // «Media / Excel» de la categoría: con «Excel», solo lo anotado.
    const e = calcularCashflow(conSaldos, { 'RS Traspasos': 'excel' });
    assert.equal(e.vistas.RITA.decenas['2027-01-11'].traspasos_externos, null);
  });

  test('H7-REAL-4: indicador de control: variación media mensual real (12 meses) frente a prevista', () => {
    // Real: 1.000 € más por mes (de 0 a 12.000 en 12 meses); previsto: −100 € en cada 1.ª decena.
    const saldosR = [banco('RITA', '2026-11-11', 0)];
    for (let d = '2025-11-11', k = 0; d <= '2026-11-11'; d = siguienteDecena(d), k++) saldosR.push(banco('PIO', d, Math.round((k / 3) * 1000 * 100) / 100));
    const r = calcularCashflow({ ...base, vencimientos: [], importes: reales('PIO', 'RS Gastos generales', 'Luz', [100, 0, 0]), saldos: saldosR });
    const x = variacionMensual(r.vistas.PIO, r.decenas);
    assert.deepEqual([x.real?.desde, x.real?.hasta, x.real?.meses, x.real?.por_mes], ['2025-11-11', '2026-11-11', 12, 1000]);
    assert.deepEqual([x.prevista?.desde, x.prevista?.hasta, x.prevista?.meses, x.prevista?.por_mes], ['2026-11-11', '2027-07-21', 8.33, -96]);
  });

  test('apunte manual (hueco preparado): entre vencimientos y Excel; sin apuntes, nada cambia', () => {
    const importes = [...reales('PIO', 'RS Personal', 'Nóminas', [1000, 0, 0]), fila('PIO', '2026-12-01', 'RS Personal', 'Nóminas', 1100)];
    const sin = calcularCashflow({ ...base, vencimientos: [], importes, saldos });
    assert.equal(sin.vistas.PIO.lineas.find((l) => l.concepto === 'Nóminas')!.celdas['2026-12-01'].fuente, 'EXCEL');
    const apuntes = [
      { cuenta: 'PIO', decena_inicio: '2026-12-01', categoria: 'RS Personal', concepto: 'Nóminas', importe: 1250 },
      { cuenta: 'PIO', decena_inicio: '2027-01-01', categoria: 'RS Personal', concepto: 'Finiquito', importe: 400 },
      { cuenta: 'PIO', decena_inicio: '2026-12-01', categoria: 'RS Proveedores', concepto: 'ALLIANCE', importe: 999 },
    ];
    const r = calcularCashflow({ ...base, vencimientos: [venc({ fecha_vencimiento: '2026-12-05', importe: 800 })], importes, saldos, apuntes_manuales: apuntes });
    const nom = linea(r, 'PIO', 'RS Personal', 'Nóminas').celdas['2026-12-01'];
    assert.deepEqual([nom.fuente, nom.importe, nom.excel], ['MANUAL', -1250, -1100]);
    // Con un apunte en la categoría y decena, no hay media (enero: Finiquito, sin media de Nóminas).
    assert.equal(media(r, 'PIO', 'RS Personal')['2027-01-01'], undefined);
    assert.equal(media(r, 'PIO', 'RS Personal')['2027-02-01'].importe, -1000);
    // Los vencimientos mandan sobre el apunte.
    assert.deepEqual([linea(r, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-12-01'].fuente, linea(r, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-12-01'].importe], ['VENCIMIENTOS', -800]);
  });

  test('H7-REAL-2 (RITA sin efectivo): la categoría y el concepto del Excel llegan a la vista RITA, con cualquier mayúscula', () => {
    for (const categoria of ['RE Cobro efectivo', 'RE Cobro Efectivo', 'RE  cobro efectivo']) {
      const importes = reales('RITA', categoria, 'COBRO EFECTIU', [700, 700, 700]);
      const r = calcularCashflow({ ...base, vencimientos: [], importes, saldos });
      const l = r.vistas.RITA.lineas.find((x) => x.categoria === categoria && x.concepto === 'COBRO EFECTIU');
      assert.ok(l, categoria);
      assert.equal(l.celdas['2026-11-11'].fuente, 'REAL');
      assert.equal(media(r, 'RITA', categoria)['2026-12-01'].importe, 700);
      assert.equal(r.vistas.RITA.decenas['2026-11-11'].entradas, 700);
      assert.equal(r.fuera.filas_no_reconocidas, 0);
    }
  });
});

describe('H7: antigüedad de la importación', () => {
  const imp = (vigente: boolean, at: string, estado = 'OK') => importacion({ importacion_id: at, vigente, importado_at: at, estado });
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

describe('H7-REAL: importación vigente, cuadre de control y E7 (cálculo)', () => {
  const base = { hoy: '2026-11-16', importaciones: IMP_OK, cuentas: CUENTAS, vencimientos: [] };
  test('solo filas de la vigente (nunca se mezclan importaciones); sin vigente, ninguna fila; una ERROR nunca es vigente', () => {
    const importes = [fila('PIO', '2026-11-21', 'RS Personal', 'Nóminas', 100), fila('PIO', '2026-11-21', 'RS Personal', 'Nóminas', 999, 'i0')];
    const saldos = [banco('PIO', '2026-11-11', 1000), banco('RITA', '2026-11-11', 0), { ...banco('PIO', '2026-11-11', 5), importacion_id: 'i0' }];
    const r = calcularCashflow({ ...base, importes, saldos });
    assert.equal(saldo(r, 'PIO', '2026-11-21'), 900);
    assert.equal(r.fuera.filas_otra_importacion, 2);
    const sin = calcularCashflow({ ...base, importaciones: [], importes, saldos });
    assert.equal(sin.importacion.vigente, null);
    assert.equal(sin.vistas.PIO.ultima_real, null);
    assert.equal(sin.fuera.filas_otra_importacion, 5);
    const err = calcularCashflow({ ...base, importaciones: [importacion({ estado: 'ERROR', detalle_error: 'E_CELDA C12' })], importes, saldos });
    assert.equal(err.importacion.vigente, null);
  });
  test('ERROR posterior a la vigente: aviso gris con su fecha y detalle (códigos), y se sigue usando la vigente', () => {
    const imps = [importacion({ importado_at: '2026-11-14T22:00:00.000Z' }),
      importacion({ importacion_id: 'i2', vigente: false, estado: 'ERROR', detalle_error: 'HOJA_NO_ENCONTRADA RITA', importado_at: '2026-11-16T02:00:00.000Z' })];
    const r = calcularCashflow({ ...base, importaciones: imps, importes: [], saldos: [banco('PIO', '2026-11-11', 700), banco('RITA', '2026-11-11', 0)] });
    assert.equal(r.importacion.vigente?.importacion_id, 'i1');
    assert.equal(r.importacion.ultima?.importacion_id, 'i2');
    const a = r.avisos.find((x) => x.codigo === 'IMPORTACION_FALLIDA');
    assert.equal(a?.tipo, 'gris');
    assert.match(a!.texto, /16\/11|2026-11-16/);
    assert.match(a!.texto, /HOJA_NO_ENCONTRADA RITA/);
    assert.match(a!.texto, /se muestran los datos de la vigente/);
    assert.equal(r.vistas.PIO.saldo_partida, 700);
  });
  test('cuadre: saldo_inicial + ΣRE − ΣRS = saldo_formulas (RS negativo suma); tolerancia 0,005 € por importe; si no, aviso gris por cuenta', () => {
    const importes = [
      fila('PIO', '2026-11-01', 'RE Cobro TPV', 'TPV', 500), fila('PIO', '2026-11-01', 'RS Proveedores', 'COFARES', 300),
      fila('PIO', '2026-11-01', 'RS Proveedores', 'COFARES', -50), fila('PIO', '2026-11-01', 'RS Traspasos', 'A RITA', 100),
      fila('RITA', '2026-11-01', 'RE Traspasos', 'De PIO', 100), fila('PIO', '2026-11-11', 'RE Otros', 'x', 10),
    ];
    // PIO 01: 1000 + 500 − (300 − 50 + 100) = 1150 → cuadra. PIO 11: 1150 + 10 = 1160, fórmulas 1160,01 con 1 importe → no cuadra.
    // RITA 01: 0 + 100 = 100,01 con 1 importe (tolerancia 0,005): no cuadra; RITA 11: 0 importes, 100 = 100 → cuadra.
    const saldos = [
      banco('PIO', '2026-11-01', 1150, { saldo_inicial: 1000 }), banco('PIO', '2026-11-11', 1160.01, { saldo_inicial: 1150, saldo_bancos: null }),
      banco('RITA', '2026-11-01', 100.01, { saldo_inicial: 0 }), banco('RITA', '2026-11-11', 100, { saldo_inicial: 100, saldo_bancos: null }),
    ];
    const r = calcularCashflow({ ...base, importes, saldos });
    const p1 = r.vistas.PIO.decenas['2026-11-01'];
    assert.deepEqual(p1.cuadre, { saldo_inicial: 1000, entradas: 500, salidas: 350, esperado: 1150, saldo_formulas: 1150, diferencia: 0, filas: 4, cuadra: true });
    assert.equal(r.vistas.PIO.decenas['2026-11-11'].cuadra, false);
    assert.equal(r.vistas.PIO.decenas['2026-11-11'].cuadre?.diferencia, 0.01);
    assert.equal(r.vistas.RITA.decenas['2026-11-01'].cuadra, false);
    assert.equal(r.vistas.RITA.decenas['2026-11-11'].cuadra, true);
    assert.equal(r.vistas.CONSOLIDADO.decenas['2026-11-01'].cuadra, false);
    const avisos = r.avisos.filter((a) => a.codigo === 'IMPORTACION_NO_CUADRA');
    assert.deepEqual(avisos.map((a) => [a.tipo, a.cuenta, a.decenas.map((x) => x.decena)]), [['gris', 'PIO', ['2026-11-11']], ['gris', 'RITA', ['2026-11-01']]]);
    // No se recalcula: el saldo real sigue siendo el del banco; el previsto parte de él.
    assert.equal(saldo(r, 'RITA', '2026-11-01'), 100.01);
    // Tolerancia por importe: con 2 importes, 0,01 € de diferencia cuadra.
    const t = calcularCashflow({ ...base, importes: [fila('PIO', '2026-11-01', 'RE a', 'a', 1), fila('PIO', '2026-11-01', 'RE a', 'b', 1)],
      saldos: [banco('PIO', '2026-11-01', 102.01, { saldo_inicial: 100 }), banco('RITA', '2026-11-01', 0)] });
    assert.equal(t.vistas.PIO.decenas['2026-11-01'].cuadra, true);
    // Sin saldo inicial o con un importe desconocido: no se puede comprobar (null), sin aviso.
    const nulo = calcularCashflow({ ...base, importes: [fila('PIO', '2026-11-01', 'RE a', 'a', null)],
      saldos: [banco('PIO', '2026-11-01', 100, { saldo_inicial: 100 }), banco('RITA', '2026-11-01', 0)] });
    assert.deepEqual([nulo.vistas.PIO.decenas['2026-11-01'].cuadre, nulo.vistas.RITA.decenas['2026-11-01'].cuadre], [null, null]);
    assert.ok(!nulo.avisos.some((a) => a.codigo === 'IMPORTACION_NO_CUADRA'));
  });
  test('E7: banco ≠ fórmulas en una decena real: diferencia informativa (no aviso); en una prevista, nada', () => {
    const saldos = [banco('PIO', '2026-11-01', 1000, { saldo_formulas: 1012.5 }), banco('PIO', '2026-11-11', 990, { saldo_formulas: 990 }),
      banco('PIO', '2026-11-21', null, { saldo_formulas: 50 }), banco('RITA', '2026-11-11', 0)];
    const r = calcularCashflow({ ...base, importes: [], saldos });
    assert.equal(r.vistas.PIO.decenas['2026-11-01'].diferencia_banco, -12.5);
    assert.equal(r.vistas.PIO.decenas['2026-11-11'].diferencia_banco, null);
    assert.equal(r.vistas.PIO.decenas['2026-11-21'].diferencia_banco, null);
    assert.equal(r.vistas.PIO.decenas['2026-11-01'].saldo, 1000);
    assert.deepEqual(r.avisos.filter((a) => a.tipo !== 'gris' || a.codigo === 'IMPORTACION_NO_CUADRA'), []);
  });
  test('concepto null: línea «Sin concepto»; SL declarada: en «Fuera de la previsión» con sus recuentos', () => {
    const r = calcularCashflow({ ...base, cuentas: [...CUENTAS, { codigo: 'SL', farmacia: null }], otras_cuentas: [{ cuenta: 'SL', importes: 3, saldos: 2 }],
      importes: [fila('PIO', '2026-11-21', 'RS Gastos generales', null, 40)], saldos: [banco('PIO', '2026-11-11', 100), banco('RITA', '2026-11-11', 0)] });
    assert.equal(linea(r, 'PIO', 'RS Gastos generales', CONCEPTO_VACIO).celdas['2026-11-21'].importe, -40);
    assert.deepEqual([r.fuera.cuentas_fuera, r.fuera.filas_otras_cuentas], [['SL'], 5]);
    assert.equal((r.vistas as Record<string, unknown>).SL, undefined);
  });
});

// ---------------------------------------------------------------------------
// Base simulada de las tablas cf_cashflow_* (migración 38): ejecuta las consultas de SQL_CASHFLOW como lo haría
// Postgres para cf_lectura (filtros por importacion_id y cuentas; numeric, date y timestamptz como texto).
// ---------------------------------------------------------------------------

interface BaseSimulada {
  importaciones: Record<string, unknown>[];
  cuentas: Record<string, unknown>[];
  importes: Record<string, unknown>[];
  saldos: Record<string, unknown>[];
}
const U = (k: number) => `c7000000-0000-4000-8000-${String(k).padStart(12, '0')}`;
function baseSimulada(o: Partial<BaseSimulada> = {}): BaseSimulada {
  const imp = (k: number, at: string, vigente: boolean, estado = 'OK', detalle: string | null = null) => ({
    id: U(k), archivo_nombre: 'Cashflow 2026.xlsx', archivo_hash: 'h', origen: 'NOCHE', estado, detalle_error: detalle, filas: estado === 'OK' ? 9 : null,
    importado_at: at, vigente,
  });
  const m = (k: number, imp: number, cuenta: string, d: string, categoria: string, concepto: string | null, importe: string) => ({
    id: String(k), importacion_id: U(imp), cuenta, farmacia: cuenta === 'SL' ? null : cuenta, decena_inicio: d, decena_fin: finDecena(d),
    categoria, concepto, importe, fila_excel: k + 10,
  });
  const s = (k: number, imp: number, cuenta: string, d: string, ini: string, form: string, banc: string | null) => ({
    id: String(k), importacion_id: U(imp), cuenta, farmacia: cuenta === 'SL' ? null : cuenta, decena_inicio: d, saldo_inicial: ini, saldo_formulas: form, saldo_bancos: banc,
  });
  return {
    // 1: antigua (no vigente); 2: vigente (OK); 3: ERROR posterior (solo cabecera).
    importaciones: [imp(1, '2026-11-03 07:40:00+00', false), imp(2, '2026-11-10 07:45:00.25+00', true),
      imp(3, '2026-11-16 02:00:00+00', false, 'ERROR', 'HOJA_NO_ENCONTRADA:RITA; CELDA_NO_NUMERICA:PIO!F14')],
    cuentas: [{ codigo: 'PIO', farmacia: 'PIO', hoja: 'PIO' }, { codigo: 'RITA', farmacia: 'RITA', hoja: 'RITA' }, { codigo: 'SL', farmacia: null, hoja: 'SL' }],
    importes: [
      // Importación antigua: nunca se lee.
      m(1, 1, 'PIO', '2026-11-01', 'RE Cobro TPV', 'TPV', '99999.00'),
      // Vigente. PIO 01–10/11: 1.000 + 800 − (300 − 20) = 1.520 (RS negativo suma). E7: banco 1.500.
      m(2, 2, 'PIO', '2026-11-01', 'RE Cobro TPV', 'TPV', '800.00'),
      m(3, 2, 'PIO', '2026-11-01', 'RS Proveedores', 'COFARES', '300.00'),
      m(4, 2, 'PIO', '2026-11-01', 'RS Gastos generales', null, '-20.00'),
      // PIO 11–20/11 (prevista): 1.520 − 100 = 1.420, pero fórmulas 1.400: no cuadra.
      m(5, 2, 'PIO', '2026-11-11', 'RS Personal', 'Nóminas', '100.00'),
      // RITA 01–10/11: 500 − 50 (RE negativo) = 450.
      m(6, 2, 'RITA', '2026-11-01', 'RE Cobro TPV', 'TPV', '-50.00'),
      // SL: solo se cuenta.
      m(7, 2, 'SL', '2026-11-01', 'RS Gastos generales', 'Gestoría', '300.00'),
    ],
    saldos: [
      s(1, 1, 'PIO', '2026-11-01', '0', '99999.00', '99999.00'),
      s(2, 2, 'PIO', '2026-11-01', '1000.00', '1520.00', '1500.00'),
      s(3, 2, 'PIO', '2026-11-11', '1520.00', '1400.00', null),
      s(4, 2, 'RITA', '2026-11-01', '500.00', '450.00', '450.00'),
      s(5, 2, 'RITA', '2026-11-11', '450.00', '450.00', null),
    ],
    ...o,
  };
}
/** Ejecuta las consultas de SQL_CASHFLOW sobre la base simulada; registra cada consulta y sus parámetros. */
function consultarSimulada(b: BaseSimulada, log: { sql: string; params: unknown[] }[] = []) {
  return async (sql: string, params: unknown[]) => {
    log.push({ sql, params });
    const [id, cuentas] = params as [string, string[]];
    const deVigente = (xs: Record<string, unknown>[]) => xs.filter((x) => x.importacion_id === id);
    switch (sql) {
      case SQL_CASHFLOW.importaciones: {
        const orden = [...b.importaciones].sort((x, y) => String(y.importado_at).localeCompare(String(x.importado_at)));
        return orden.filter((x, i) => x.vigente === true || i === 0).map(({ archivo_hash: _h, ...x }) => x);
      }
      case SQL_CASHFLOW.cuentas: return b.cuentas.map(({ hoja: _h, ...x }) => x);
      case SQL_CASHFLOW.importes: return deVigente(b.importes).filter((x) => cuentas.includes(String(x.cuenta))).map(({ fila_excel: _f, ...x }) => x);
      case SQL_CASHFLOW.saldos: return deVigente(b.saldos).filter((x) => cuentas.includes(String(x.cuenta)));
      case SQL_CASHFLOW.otras_cuentas: {
        const otras = new Map<string, { cuenta: string; importes: number; saldos: number }>();
        const sumar = (xs: Record<string, unknown>[], k: 'importes' | 'saldos') => {
          for (const x of deVigente(xs).filter((y) => !cuentas.includes(String(y.cuenta)))) {
            const o = otras.get(String(x.cuenta)) ?? { cuenta: String(x.cuenta), importes: 0, saldos: 0 };
            o[k] += 1;
            otras.set(o.cuenta, o);
          }
        };
        sumar(b.importes, 'importes');
        sumar(b.saldos, 'saldos');
        return [...otras.values()].sort((x, y) => x.cuenta.localeCompare(y.cuenta));
      }
      default: throw new Error(`consulta no prevista: ${sql.slice(0, 40)}`);
    }
  };
}

describe('H7-REAL: lectura de las tablas cf_cashflow_* (base simulada)', () => {
  test('solo SELECT de los cuatro objetos; importes y saldos filtrados por la importación vigente', () => {
    for (const sql of Object.values(SQL_CASHFLOW)) {
      assert.match(sql, /^select /);
      assert.doesNotMatch(sql, /\b(insert|update|delete|truncate|grant|alter|create|drop|merge|copy)\b/i);
      for (const t of sql.match(/public\.\w+/g) ?? []) assert.ok(['public.cf_cashflow_importaciones', 'public.cf_cashflow_cuentas', 'public.cf_cashflow_importes', 'public.cf_cashflow_saldos'].includes(t), t);
    }
    assert.match(SQL_CASHFLOW.importaciones, /where i\.vigente\s+or i\.id = \(select u\.id .* order by u\.importado_at desc, u\.id desc limit 1\)/s);
    for (const k of ['importes', 'saldos'] as const) assert.match(SQL_CASHFLOW[k], /where \w\.importacion_id = \$1::uuid and \w\.cuenta = any\(\$2::text\[\]\)/);
    assert.equal((SQL_CASHFLOW.otras_cuentas.match(/importacion_id = \$1::uuid and not \(\w\.cuenta = any\(\$2::text\[\]\)\)/g) ?? []).length, 2);
  });

  test('vigente con ERROR posterior: filas solo de la vigente, signos de la celda, SL solo contada; cálculo con E7 y cuadre', async () => {
    const log: { sql: string; params: unknown[] }[] = [];
    const d = await leerCashflowReal(consultarSimulada(baseSimulada(), log));
    assert.deepEqual(log.map((x) => x.sql), [SQL_CASHFLOW.importaciones, SQL_CASHFLOW.cuentas, SQL_CASHFLOW.importes, SQL_CASHFLOW.saldos, SQL_CASHFLOW.otras_cuentas]);
    assert.deepEqual(log.slice(2).map((x) => x.params), [[U(2), ['PIO', 'RITA']], [U(2), ['PIO', 'RITA']], [U(2), ['PIO', 'RITA']]]);
    assert.deepEqual(d.importaciones.map((i) => [i.importacion_id, i.estado, i.vigente, i.importado_at]),
      [[U(3), 'ERROR', false, '2026-11-16T02:00:00.000Z'], [U(2), 'OK', true, '2026-11-10T07:45:00.250Z']]);
    assert.equal(d.importaciones[0].detalle_error, 'HOJA_NO_ENCONTRADA:RITA; CELDA_NO_NUMERICA:PIO!F14');
    assert.equal(d.importaciones[1].detalle_error, null);
    assert.ok(d.importes.every((x) => x.importacion_id === U(2)) && d.saldos.every((x) => x.importacion_id === U(2)));
    assert.deepEqual(d.importes.map((x) => x.importe), [800, 300, -20, 100, -50]);
    assert.equal(d.importes[2].concepto, null);
    assert.deepEqual(d.saldos.map((x) => [x.cuenta, x.decena_inicio, x.saldo_inicial, x.saldo_formulas, x.saldo_bancos]), [
      ['PIO', '2026-11-01', 1000, 1520, 1500], ['PIO', '2026-11-11', 1520, 1400, null], ['RITA', '2026-11-01', 500, 450, 450], ['RITA', '2026-11-11', 450, 450, null]]);
    assert.deepEqual(d.otras_cuentas, [{ cuenta: 'SL', importes: 1, saldos: 0 }]);

    const r = calcularCashflow({ ...d, hoy: '2026-11-16', vencimientos: [] });
    // Real hasta la última decena con banco; partida = ese saldo_bancos.
    assert.deepEqual([r.vistas.PIO.ultima_real, r.vistas.PIO.saldo_partida, r.vistas.RITA.saldo_partida], ['2026-11-01', 1500, 450]);
    // Signos: RS negativo reduce las salidas; RE negativo, las entradas.
    assert.equal(r.vistas.PIO.decenas['2026-11-01'].salidas, -280);
    assert.equal(r.vistas.RITA.decenas['2026-11-01'].entradas, -50);
    // E7 (informativa) y cuadre.
    assert.equal(r.vistas.PIO.decenas['2026-11-01'].diferencia_banco, -20);
    assert.equal(r.vistas.PIO.decenas['2026-11-01'].cuadra, true);
    assert.equal(r.vistas.PIO.decenas['2026-11-11'].cuadra, false);
    assert.equal(r.vistas.PIO.decenas['2026-11-11'].cuadre?.diferencia, -20);
    assert.deepEqual(r.avisos.filter((a) => a.tipo === 'gris').map((a) => [a.codigo, a.cuenta]),
      [['IMPORTACION_ANTIGUA', null], ['IMPORTACION_FALLIDA', null], ['IMPORTACION_NO_CUADRA', 'PIO']]);
    assert.deepEqual([r.fuera.cuentas_fuera, r.fuera.filas_otras_cuentas, r.fuera.filas_otra_importacion], [['SL'], 1, 0]);
  });

  test('sin importación: no se leen importes ni saldos («Todavía no hay datos importados»); solo una ERROR: tampoco', async () => {
    const log: { sql: string; params: unknown[] }[] = [];
    const vacia = await leerCashflowReal(consultarSimulada(baseSimulada({ importaciones: [], importes: [], saldos: [] }), log));
    assert.deepEqual(log.map((x) => x.sql), [SQL_CASHFLOW.importaciones, SQL_CASHFLOW.cuentas]);
    assert.deepEqual([vacia.importaciones, vacia.importes, vacia.saldos, vacia.otras_cuentas], [[], [], [], []]);
    assert.equal(calcularCashflow({ ...vacia, hoy: '2026-11-16', vencimientos: [] }).importacion.vigente, null);
    const b = baseSimulada();
    const soloError = await leerCashflowReal(consultarSimulada({ ...b, importaciones: b.importaciones.filter((i) => i.estado === 'ERROR') }));
    assert.deepEqual([soloError.importaciones.length, soloError.importes.length], [1, 0]);
    const r = calcularCashflow({ ...soloError, hoy: '2026-11-16', vencimientos: [] });
    assert.equal(r.importacion.vigente, null);
    assert.ok(r.avisos.some((a) => a.codigo === 'IMPORTACION_FALLIDA' && /no hay ninguna vigente/.test(a.texto)));
  });

  test('falla cerrado: varias vigentes, vigente ERROR, fila de otra importación, farmacia ajena, saldo repetido, valores raros', async () => {
    const b = baseSimulada();
    const con = (o: Partial<BaseSimulada>) => leerCashflowReal(consultarSimulada({ ...b, ...o }));
    await assert.rejects(con({ importaciones: b.importaciones.map((i) => ({ ...i, vigente: i.estado === 'OK' })) }), /CASHFLOW_VARIAS_VIGENTES/);
    await assert.rejects(con({ importaciones: b.importaciones.map((i) => ({ ...i, vigente: i.estado === 'ERROR' })) }), /CASHFLOW_VIGENTE_NO_OK/);
    // Una fila de otra importación que se colara en la respuesta: error (nunca se mezclan).
    const mezcla = async (sql: string, p: unknown[]) => {
      const filas = await consultarSimulada(b)(sql, p);
      if (sql !== SQL_CASHFLOW.importes) return filas;
      const { fila_excel: _f, ...colada } = b.importes[0];
      return [...filas, colada];
    };
    await assert.rejects(leerCashflowReal(mezcla), /CASHFLOW_OTRA_IMPORTACION/);
    await assert.rejects(con({ importes: b.importes.map((x) => (x.id === '2' ? { ...x, farmacia: 'RITA' } : x)) }), /CASHFLOW_FARMACIA_NO_CUADRA/);
    await assert.rejects(con({ cuentas: [{ codigo: 'PIO', farmacia: 'RITA' }] }), /CASHFLOW_FARMACIA_NO_CUADRA/);
    await assert.rejects(con({ saldos: [...b.saldos, { ...b.saldos[1], id: '99' }] }), /CASHFLOW_SALDO_REPETIDO/);
    await assert.rejects(con({ importes: b.importes.map((x) => (x.id === '2' ? { ...x, importe: 'mil' } : x)) }), /CASHFLOW_IMPORTE_NO_VALIDO/);
    await assert.rejects(con({ importes: b.importes.map((x) => (x.id === '2' ? { ...x, decena_inicio: '2026-11-05' } : x)) }), /CASHFLOW_DECENA_NO_VALIDA/);
    await assert.rejects(con({ importaciones: b.importaciones.map((i) => ({ ...i, origen: 'OTRO' })) }), /CASHFLOW_VALOR_NO_VALIDO: origen/);
    await assert.rejects(con({ importaciones: b.importaciones.map((i) => ({ ...i, importado_at: 'ayer' })) }), /CASHFLOW_FECHA_NO_VALIDA/);
  });

  test('detalle_error: solo en ERROR y recortado; en OK no se muestra', async () => {
    const b = baseSimulada();
    const largo = 'X'.repeat(1000);
    const d = await leerCashflowReal(consultarSimulada({ ...b, importaciones: b.importaciones.map((i) => ({ ...i, detalle_error: i.estado === 'ERROR' ? largo : 'no debe salir' })) }));
    assert.equal(d.importaciones.find((i) => i.estado === 'ERROR')?.detalle_error?.length, 300);
    assert.equal(d.importaciones.find((i) => i.estado === 'OK')?.detalle_error, null);
  });

  test('check:real: diagnóstico cashflow solo con números y sí/no', async () => {
    const d = await leerCashflowReal(consultarSimulada(baseSimulada()));
    const diag = validarDiagnostico(diagnosticoCashflow(d, '2026-11-16'));
    assert.deepEqual(diag, {
      vigente: true, dias_desde_vigente: 6, ultima_error: true,
      importes_pio: 4, saldos_pio: 2, importes_rita: 1, saldos_rita: 2, importes_sl: 1, saldos_sl: 0, importes_otras: 0, saldos_otras: 0,
      decenas_diferencia_banco_formulas: 1, decenas_no_cuadran: 1,
      // H7-REAL-2: por cuenta y categoría (reales = decena con saldo de banco; futuros = anotados) y efectivo.
      efectivo_pio_reales: 0, efectivo_pio_futuros: 0, efectivo_pio_en_otra_categoria: 0,
      efectivo_rita_reales: 0, efectivo_rita_futuros: 0, efectivo_rita_en_otra_categoria: 0,
      cat_pio_re_cobro_tpv_reales: 1, cat_pio_rs_gastos_generales_reales: 1, cat_pio_rs_personal_futuros: 1, cat_pio_rs_proveedores_reales: 1,
      cat_rita_re_cobro_tpv_reales: 1,
      // H7-REAL-5: sin vencimientos; indicador real no disponible (una sola decena real), previsto disponible.
      vencimientos_leidos: 0,
      indicador_antes_real_disponible: false, indicador_antes_prevista_disponible: true, indicador_antes_prevista_eur_mes: 422, indicador_antes_prevista_negativa: false,
      indicador_despues_real_disponible: false, indicador_despues_prevista_disponible: true, indicador_despues_prevista_eur_mes: 422, indicador_despues_prevista_negativa: false,
    });
    const vacia = diagnosticoCashflow(await leerCashflowReal(consultarSimulada(baseSimulada({ importaciones: [] }))), '2026-11-16');
    assert.deepEqual([vacia.vigente, 'dias_desde_vigente' in vacia, vacia.ultima_error, vacia.importes_pio], [false, false, false, 0]);
    // Ningún valor es un importe, un concepto ni un texto.
    assert.ok(Object.values(diag).every((v) => typeof v === 'boolean' || Number.isSafeInteger(v)));
  });

  test('H7-REAL-5 check:real: decenas en que gana la media frente a los vencimientos, por concepto (nombre comercial), e indicador antes/después', async () => {
    const dto = await datosFixtures();
    const d = { importaciones: dto.importaciones, cuentas: dto.cuentas, importes: dto.importes, saldos: dto.saldos, otras_cuentas: dto.otras_cuentas };
    const diag = validarDiagnostico(diagnosticoCashflow(d, dto.hoy, dto.vencimientos));
    assert.equal(diag.vencimientos_leidos, dto.vencimientos.length);
    assert.deepEqual([diag.venc_gana_media_alliance_pio, diag.venc_ganan_vencimientos_alliance_pio], [1, 0]);
    // Antes (vencimientos como total) la previsión sube más que después (vencimientos como mínimo).
    const antes = (diag.indicador_antes_prevista_negativa ? -1 : 1) * (diag.indicador_antes_prevista_eur_mes as number);
    const despues = (diag.indicador_despues_prevista_negativa ? -1 : 1) * (diag.indicador_despues_prevista_eur_mes as number);
    assert.ok(antes > despues, `${antes} > ${despues}`);
    assert.equal(diag.indicador_antes_real_eur_mes, diag.indicador_despues_real_eur_mes);
    assert.ok(Object.values(diag).every((v) => typeof v === 'boolean' || (Number.isSafeInteger(v) && (v as number) >= 0)));
  });

  test('H7-REAL-2 check:real: efectivo de RITA (reales, futuros y en otra categoría) y claves de categoría sin conceptos ni importes', () => {
    const importes = [
      fila('RITA', '2026-11-01', 'RE Cobro efectivo', 'COBRO EFECTIU', 1200), fila('RITA', '2026-10-21', 'RE Cobro efectivo', 'COBRO EFECTIU', 1100),
      fila('RITA', '2026-11-21', 'RE Cobro efectivo', 'COBRO EFECTIU', 1150), fila('RITA', '2026-11-01', 'RE Cobro TPV', 'COBRO EFECTIU', 90),
      fila('PIO', '2026-11-01', 'RE Altres cobraments', 'Ingrés en metàl·lic', 50), fila('PIO', '2026-11-01', 'RS Gestoría «Ñ» 2026', 'Secreto SL', 10),
    ];
    const d = { importaciones: IMP_OK, cuentas: CUENTAS, importes, saldos: [banco('PIO', '2026-11-01', 100), banco('RITA', '2026-11-01', 100)], otras_cuentas: [] };
    const diag = validarDiagnostico(diagnosticoCashflow(d, '2026-11-16'));
    assert.deepEqual([diag.efectivo_rita_reales, diag.efectivo_rita_futuros, diag.efectivo_rita_en_otra_categoria, diag.efectivo_pio_en_otra_categoria], [2, 1, 1, 1]);
    assert.deepEqual([diag.cat_rita_re_cobro_efectivo_reales, diag.cat_rita_re_cobro_efectivo_futuros, diag.cat_pio_rs_gestoria_n_2026_reales], [2, 1, 1]);
    assert.equal(claveCategoria('RE Cobro efectivo'), 're_cobro_efectivo');
    assert.ok(Object.keys(diag).every((k) => /^[a-z0-9_]+$/.test(k)));
    assert.ok(!JSON.stringify(diag).includes('Secreto') && !JSON.stringify(diag).includes('EFECTIU'));
  });
});

describe('H7: ruta /api/cashflow', () => {
  test('FIXTURES: datos de partida + vencimientos de PIO', async () => {
    const dto = await datosFixtures();
    const app = Fastify();
    const almacen = crearAlmacenPagos(leerSemillaPagos());
    const vencs = await crearAdaptadorFixtures().vencimientos();
    registrarCashflow(app, { modo: 'FIXTURES', pantallaPagos: async () => construirPantalla(vencs, almacen.fuente(), { hoy: almacen.hoy, modo: 'FIXTURES' }) });
    const r = await app.inject({ method: 'GET', url: '/api/cashflow' });
    assert.equal(r.statusCode, 200);
    const j = r.json() as CashflowDTO;
    assert.deepEqual([j.hoy, j.importes.length, j.vencimientos.length, j.otras_cuentas], [dto.hoy, dto.importes.length, dto.vencimientos.length, []]);
  });
  test('H7-REAL: sin 503; lee la base (simulada), fecha de hoy del servidor y vencimientos de PIO', async () => {
    const almacen = crearAlmacenPagos(leerSemillaPagos());
    const vencs = await crearAdaptadorFixtures().vencimientos();
    const real = Fastify();
    let lecturas = 0;
    registrarCashflow(real, {
      modo: 'REAL', hoy: () => '2026-11-16',
      leerReal: async () => { lecturas += 1; return leerCashflowReal(consultarSimulada(baseSimulada())); },
      pantallaPagos: async () => construirPantalla(vencs, almacen.fuente(), { hoy: almacen.hoy, modo: 'REAL' }),
    });
    const r = await real.inject({ method: 'GET', url: '/api/cashflow' });
    assert.equal(r.statusCode, 200);
    assert.equal(r.headers['cache-control'], 'no-store');
    const j = r.json() as CashflowDTO;
    assert.deepEqual([j.modo, j.hoy, j.importes.length, j.saldos.length, j.otras_cuentas.length, lecturas], ['REAL', '2026-11-16', 5, 4, 1, 1]);
    assert.ok(!JSON.stringify(j).includes('Gestoría')); // SL: solo recuentos
    // Sin importación: 200 con la lista vacía (la pantalla dice «Todavía no hay datos importados»).
    const vacia = Fastify();
    registrarCashflow(vacia, { modo: 'REAL', hoy: () => '2026-11-16', leerReal: () => leerCashflowReal(consultarSimulada(baseSimulada({ importaciones: [] }))),
      pantallaPagos: async () => construirPantalla(vencs, almacen.fuente(), { hoy: almacen.hoy, modo: 'REAL' }) });
    const v = (await vacia.inject({ method: 'GET', url: '/api/cashflow' })).json() as CashflowDTO;
    assert.deepEqual([v.importaciones, v.importes], [[], []]);
    assert.equal((await real.inject({ method: 'POST', url: '/api/cashflow' })).statusCode, 404);
    // REAL sin lectura: no arranca (falla cerrado).
    assert.throws(() => registrarCashflow(Fastify(), { modo: 'REAL', pantallaPagos: async () => { throw new Error('no'); } }), /CASHFLOW_REAL_SIN_LECTURA/);
  });
});
