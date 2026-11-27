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
  CATEGORIAS_SIN_MEDIA, CONCEPTO_VACIO, CONCEPTOS_EQUIVALENTES, CONFIG_CASHFLOW, CORRESPONDENCIAS_PROVEEDOR, ORDEN_PRIORIDAD, TRASPASOS_INTERNOS, calcularCashflow, celdaColumna,
  conceptoEquivalente, resolverEquivalencias,
  claseMovimiento, clasificarCategoria, esTraspasoInterno, variacionMensual,
  columnasVista, comercialDeConcepto, decenaDe, estadoImportacion, finDecena, moverDecena, ordinalDecena, reglaEstimacion, saldoColumna, siguienteDecena,
  totalCategoria, traspasosNoCompensados, type CashflowDTO, type ImportacionCashflow, type ImporteCashflow, type Linea, type ResultadoCashflow,
  type SaldoCashflow, type VencimientoCashflow, type Celda,
} from '../cashflow/cashflow.ts';
import { leerSemillaCashflow, registrarCashflow, vencimientoCashflow } from '../cashflow/rutas.ts';
import { SQL_CASHFLOW, claveCategoria, diagnosticoCashflow, leerCashflowReal } from '../cashflow/lectura_real.ts';
import { validarDiagnostico } from '../adaptador_real.ts';
import { previsionesVacias } from '../cashflow/apuntes.ts';

async function datosFixtures(): Promise<CashflowDTO> {
  const semilla = leerSemillaCashflow();
  const almacen = crearAlmacenPagos(leerSemillaPagos());
  const p = construirPantalla(await crearAdaptadorFixtures().vencimientos(), almacen.fuente(), { hoy: almacen.hoy, modo: 'FIXTURES' });
  return {
    ...semilla, farmacia: 'PIO', generado_at: p.generado_at, modo: 'FIXTURES', config: CONFIG_CASHFLOW,
    vencimientos: p.filas.map(vencimientoCashflow), pago: p.pago,
    // H7-AP1: sin apuntes manuales (sus casos, en cashflow_apuntes.test.ts).
    previsiones: previsionesVacias(semilla.hoy), escritura_cashflow: { habilitada: true, codigo: null, mensaje: null, autor: 'Marc' },
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
    // H7-REAL-8 (decisión de Pío, 25/11/2026): media de 12 meses.
    assert.deepEqual([CONFIG_CASHFLOW.meses_media, CONFIG_CASHFLOW.dias_importacion_antigua, CONFIG_CASHFLOW.saldo_minimo], [12, 5, 0]);
    assert.deepEqual([...ORDEN_PRIORIDAD], ['VENCIMIENTOS', 'MANUAL', 'EXCEL', 'MEDIA']);
    assert.equal(reglaEstimacion('RS Modelo 303'), 'ANIO_ANTERIOR');
    assert.equal(reglaEstimacion('RS  modelo 111 retenciones'), 'ANIO_ANTERIOR');
    assert.equal(reglaEstimacion('RS Impuestos'), 'POSICION');
    // H7-REAL-10: las de CATEGORIAS_SIN_MEDIA (no relacionadas, traspasos externos) no se estiman.
    assert.equal(reglaEstimacion('RE No relacionadas con la farmacia'), null);
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

  test('previsión por fuente: ALLIANCE 11–20/11: Excel (520) > vencimientos (472,22) en su decena; noviembre: media del mes (12.000) > lo conocido → la diferencia (11.480) en 21–30/11', async () => {
    const r = calcularCashflow(await datosFixtures());
    const c = linea(r, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-11-11'];
    // H7-REAL-10: lo conocido de la decena = el mayor entre el Excel (520) y los vencimientos (472,22): el Excel. Por mes,
    // lo conocido (520) frente a la media de las dos decenas futuras (6.000 + 6.000): gana la media; la diferencia va a la
    // decena habitual sin nada conocido (21–30/11).
    assert.deepEqual([c.fuente, c.importe, c.vencimientos?.neto, c.comparada], ['EXCEL', -520, 472.22, { fuente: 'VENCIMIENTOS', importe: -472.22 }]);
    assert.deepEqual(c.mes, { mes: '2026-11', regla: 'POSICION', conocido: -520, media: -12000, gana: 'MEDIA', diferencia: -11480, decena_diferencia: '2026-11-21', decenas_conocidas: ['2026-11-11'], apunte: false });
    assert.equal(c.excel, -520);
    assert.equal(c.diferencia, true);
    assert.deepEqual(c.vencimientos?.incluidos.map((v) => v.vencimiento_id), ['90000000-0000-4000-8000-000000000002']);
    // Sin la regla «vencimientos como mínimo» (como antes): los vencimientos.
    const antes = calcularCashflow({ ...(await datosFixtures()), config: { ...CONFIG_CASHFLOW, vencimientos_como_minimo: false } });
    assert.deepEqual([linea(antes, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-11-11'].fuente, linea(antes, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-11-11'].importe], ['VENCIMIENTOS', -472.22]);
    // H7-REAL-9: cada concepto con su media en su línea: COFARES 4.500 − abono de julio (250 ÷ 12) = 4.479,17.
    assert.deepEqual([linea(r, 'PIO', 'RS Proveedores', 'COFARES').celdas['2026-11-11'].fuente, linea(r, 'PIO', 'RS Proveedores', 'COFARES').celdas['2026-11-11'].importe], ['MEDIA', -4479.17]);
    const all21 = linea(r, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-11-21'];
    assert.deepEqual([all21.fuente, all21.importe, all21.suma_media, all21.media?.base[0].clave, all21.media?.base[11].clave], ['MEDIA', -11480, -11480, '2025-11-21', '2026-10-21']);
    // Sin línea de «Media calculada» de categoría.
    assert.ok(r.vistas.PIO.lineas.every((l) => !l.media && l.concepto !== 'Media calculada'));
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

  test('sin doble cómputo (H7-REAL-9/10): 11–20/11, una cifra por concepto; esporádicos y terminados sin media; el saldo es la suma', async () => {
    const dto = await datosFixtures();
    // 25.000 + TPV 10.000 + efectivo 3.000 − ALLIANCE 520 (Excel; la diferencia del mes, en 21–30/11) − COFARES 4.479,17
    // − HEFAME 3.500 − LOGISTA 800 − suministros 900 = 27.800,83. H7-REAL-10: KENVUE y DERMOFARMACIA (esporádicos: solo
    // marzo) sin media; «Mantenimiento antiguo» (terminado) tampoco.
    const r = calcularCashflow(dto);
    assert.equal(saldo(r, 'PIO', '2026-11-11'), 27800.83);
    const usadas = r.vistas.PIO.lineas.flatMap((l) => (l.celdas['2026-11-11']?.en_saldo ? [`${l.categoria}|${l.concepto}`] : []));
    assert.deepEqual(usadas.sort(), ['RE Cobro TPV|TPV CaixaBank', 'RE Cobro efectivo|Ingresos de caja', 'RS Gastos generales|Suministros',
      'RS Proveedores|ALLIANCE', 'RS Proveedores|COFARES', 'RS Proveedores|HEFAME', 'RS Proveedores|LOGISTA'].sort());
    assert.equal(r.vistas.PIO.decenas['2026-11-11'].salidas, -10199.17);
    // Una cifra por concepto y decena: el saldo previsto es el anterior más la suma de las cifras de todas las líneas.
    for (const v of ['PIO', 'RITA'] as const) {
      let s = r.vistas[v].saldo_partida as number;
      for (const d of r.decenas.filter((x) => x > (r.vistas[v].ultima_real as string))) {
        s = Math.round(s * 100 + r.vistas[v].lineas.reduce((a, l) => a + Math.round((l.celdas[d]?.importe ?? 0) * 100), 0)) / 100;
        assert.equal(saldo(r, v, d), s, `${v} ${d}`);
      }
    }
  });

  test('H7-REAL-10: Excel frente a la media del concepto POR MES: gana la media → la diferencia en su decena habitual; gana el Excel → nada de media ese mes', async () => {
    const r = calcularCashflow(await datosFixtures());
    // TPV de Navidad: Excel 12.500 (21–31/12) frente a la media del mes (11.000 + 10.000 + 9.000): gana la media; la
    // diferencia (17.500) en la decena de mayor media sin nada conocido (1–10/12); 11–20/12 sin cifra (antes 33.500).
    const tpv = linea(r, 'PIO', 'RE Cobro TPV', 'TPV CaixaBank').celdas;
    assert.deepEqual([tpv['2026-12-21'].fuente, tpv['2026-12-21'].importe, tpv['2026-12-21'].mes?.gana, tpv['2026-12-21'].mes?.media, tpv['2026-12-21'].mes?.diferencia],
      ['EXCEL', 12500, 'MEDIA', 30000, 17500]);
    assert.deepEqual([tpv['2026-12-01'].fuente, tpv['2026-12-01'].importe, tpv['2026-12-01'].suma_media, tpv['2026-12-11']], ['MEDIA', 17500, 17500, undefined]);
    assert.equal(tpv['2026-12-01'].mes, tpv['2026-12-21'].mes);
    // RITA HEFAME: Excel 9.800 (1–10/12) frente a la media del mes (6.000): gana el Excel; nada de media en diciembre.
    const hef = linea(r, 'RITA', 'RS Proveedores', 'HEFAME').celdas;
    assert.deepEqual([hef['2026-12-01'].fuente, hef['2026-12-01'].importe, hef['2026-12-01'].mes?.gana, hef['2026-12-01'].mes?.media, hef['2026-12-11'], hef['2026-12-21']],
      ['EXCEL', -9800, 'CONOCIDO', -6000, undefined, undefined]);
    // RITA COFARES en 1–10/12 (HEFAME anotado en esa decena): su propia media.
    assert.deepEqual([linea(r, 'RITA', 'RS Proveedores', 'COFARES').celdas['2026-12-01'].fuente, linea(r, 'RITA', 'RS Proveedores', 'COFARES').celdas['2026-12-01'].importe], ['MEDIA', -3000]);
    // Paga extra (esporádica: 2 meses en 12): el año anterior, no 1/12 cada mes. Diciembre: Excel 12.000 frente al año
    // anterior 12.000 → el Excel; enero (sin paga el año anterior): nada.
    const paga = linea(r, 'PIO', 'RS Personal', 'Paga extra').celdas;
    assert.deepEqual([paga['2026-12-21'].fuente, paga['2026-12-21'].importe, paga['2026-12-21'].mes?.gana, paga['2026-12-21'].media?.motivo, paga['2027-01-21']],
      ['EXCEL', -12000, 'CONOCIDO', 'ESPORADICO', undefined]);
    // RITA: paga en el Excel en la 2.ª decena (7.000) y el año anterior en la 3.ª (7.000): solo el Excel (antes 8.166,67).
    const pr = linea(r, 'RITA', 'RS Personal', 'Paga extra').celdas;
    assert.deepEqual([pr['2026-12-11'].importe, pr['2026-12-21'], pr['2026-12-11'].mes?.regla, pr['2026-12-11'].mes?.media], [-7000, undefined, 'ANIO_ANTERIOR', -7000]);
  });

  test('media por posición de decena (últimos 12 meses reales): TPV, efectivo y SOE en su decena, en la línea de su concepto', async () => {
    const dto = await datosFixtures();
    const r = calcularCashflow(dto);
    const tpv = linea(r, 'PIO', 'RE Cobro TPV', 'TPV CaixaBank');
    // 2.ª decena: 11–20 de noviembre de 2025 a octubre de 2026 (los cobros varían +300/−100/−200 y suman 0 cada 3 meses).
    assert.deepEqual([tpv.celdas['2026-11-11'].fuente, tpv.celdas['2026-11-11'].importe, tpv.celdas['2026-11-11'].en_saldo], ['MEDIA', 10000, true]);
    const base = tpv.celdas['2026-11-11'].media?.base.map((b) => b.clave) ?? [];
    assert.deepEqual([base.length, base[0], base[11]], [12, '2025-11-11', '2026-10-11']);
    assert.deepEqual([tpv.celdas['2026-11-11'].media?.posicion, tpv.celdas['2026-11-11'].media?.regla], [2, 'POSICION']);
    // 1.ª y 3.ª decena con su propia base (1.ª: de diciembre de 2025 a noviembre de 2026; enero de 2027, sin Excel).
    assert.equal(tpv.celdas['2027-01-01'].importe, 11000);
    const base1 = tpv.celdas['2027-01-01'].media?.base.map((b) => b.clave) ?? [];
    assert.deepEqual([base1.length, base1[0], base1[11]], [12, '2025-12-01', '2026-11-01']);
    assert.equal(tpv.celdas['2026-11-21'].importe, 9000);
    // SOE: solo en la 3.ª decena (la media de las otras posiciones es 0: no hay cifra).
    const soe = linea(r, 'RITA', 'RE Cobro SOE', 'CatSalut receptes');
    assert.equal(soe.celdas['2026-11-21'].importe, 20000);
    assert.equal(soe.celdas['2026-11-21'].media?.base.length, 12);
    assert.equal(soe.celdas['2026-11-11'], undefined);
    assert.equal(soe.celdas['2026-12-01'], undefined);
    // Columna: total de la categoría (sin cifras «a la vista sin sumar»: ya no hay selector «Media / Excel»).
    const col = columnasVista('2026-11-16', 'decenas')[3];
    const t = totalCategoria(r.vistas.PIO.lineas.filter((l) => l.categoria === 'RE Cobro TPV'), col, r.vistas.PIO);
    assert.deepEqual([t?.importe, t?.sin_usar], [10000, null]);
    // Consolidado: la media de efectivo de las dos cuentas (PIO 3.000 + RITA 1.200).
    const ef = totalCategoria(r.vistas.CONSOLIDADO.lineas.filter((l) => l.categoria === 'RE Cobro efectivo'), col, r.vistas.CONSOLIDADO);
    assert.equal(ef?.importe, 4200);
    // Las categorías de la farmacia con historia llevan media; H7-REAL-10: «no relacionadas» y traspasos (internos y
    // externos), nunca (CATEGORIAS_SIN_MEDIA).
    assert.ok(['RS Proveedores', 'RS Gastos generales', 'RE Cobro TPV', 'RE Cobro SOE'].every((c) => r.categorias_media.includes(c)));
    assert.ok(['RS No relacionadas con la farmacia', 'RE No relacionadas con la farmacia', 'RS Traspasos', 'RE Traspasos'].every((c) => !r.categorias_media.includes(c)));
  });

  test('RITA: «RE Cobro efectivo / COBRO EFECTIU» real en todas las decenas y previsto por media', async () => {
    const r = calcularCashflow(await datosFixtures());
    const ef = linea(r, 'RITA', 'RE Cobro efectivo', 'COBRO EFECTIU');
    const reales = r.decenas.filter((d) => d <= '2026-11-01');
    assert.ok(reales.every((d) => ef.celdas[d]?.fuente === 'REAL' && (ef.celdas[d].importe as number) > 0));
    assert.ok(r.decenas.filter((d) => d > '2026-11-01').every((d) => ef.celdas[d]?.fuente === 'MEDIA' && ef.celdas[d]?.importe === 1200));
    assert.equal(r.vistas.RITA.decenas['2026-11-01'].entradas! > 0, true);
  });

  test('«RS Modelo …» (trimestrales): el mismo mes del año anterior, no la media', async () => {
    const r = calcularCashflow(await datosFixtures());
    const m303 = linea(r, 'PIO', 'RS Modelo 303', 'IVA trimestral');
    assert.deepEqual([m303.celdas['2027-01-11'].importe, m303.celdas['2027-01-11'].media?.regla, m303.celdas['2027-01-11'].media?.base.map((b) => b.clave)],
      [-8500, 'ANIO_ANTERIOR', ['2026-01-11']]);
    assert.equal(m303.celdas['2027-04-11'].importe, -7900);
    assert.equal(m303.celdas['2027-10-11'].importe, -8800);
    // Sin modelo el año anterior (noviembre y diciembre de 2025): nada; la media por posición daría −2.933,33.
    assert.equal(m303.celdas['2026-11-11'], undefined);
    assert.equal(m303.celdas['2026-12-11'], undefined);
    // Más de 12 meses por delante (el año anterior aún no es real): nada.
    assert.equal(m303.celdas['2027-12-11'], undefined);
    assert.equal(linea(r, 'PIO', 'RS Modelo 111', 'Retenciones IRPF').celdas['2027-01-11'].importe, -1500);
    assert.equal(linea(r, 'RITA', 'RS Modelo 303', 'IVA trimestral').celdas['2027-01-11'].importe, -3100);
  });

  test('traspasos internos: neutros en el consolidado y sin media; los no compensados no son aviso (línea plegada de las decenas visibles)', async () => {
    const r = calcularCashflow(await datosFixtures());
    assert.equal(linea(r, 'PIO', 'RS Traspasos', 'La Caixa Rita').celdas['2026-09-11'].importe, -3000);
    assert.equal(linea(r, 'RITA', 'RE Traspasos', 'DEPÓSITO CONECTADO').celdas['2026-09-11'].importe, 3000);
    assert.ok(r.vistas.CONSOLIDADO.lineas.every((l) => l.clase !== 'TRASPASO'));
    assert.equal(r.vistas.CONSOLIDADO.decenas['2026-09-11'].traspasos, 0);
    // Sin media: la 3.ª decena futura no lleva los internos sin contrapartida de agosto a octubre.
    for (const v of ['PIO', 'RITA'] as const) assert.ok(r.vistas[v].lineas.filter((l) => l.clase === 'TRASPASO').every((l) => !l.media && Object.values(l.celdas).every((c) => c.fuente !== 'MEDIA')));
    // H7-REAL-10: externos SIN media (CATEGORIAS_SIN_MEDIA): solo el Excel (o un apunte); cuentan en el consolidado.
    const fondos = linea(r, 'PIO', 'RS Traspasos', 'TRASPASO A FONDOS/VALORS');
    assert.deepEqual([fondos.clase, fondos.celdas['2026-12-01'], fondos.celdas['2027-02-01'].fuente, fondos.celdas['2027-02-01'].importe, fondos.celdas['2027-02-01'].media],
      ['TRASPASO_EXTERNO', undefined, 'EXCEL', -2500, null]);
    assert.equal(linea(r, 'RITA', 'RS Traspasos', 'TRASPASO A LA SL (JUBILACIO ETC)').celdas['2026-11-11'], undefined);
    assert.equal(r.vistas.CONSOLIDADO.decenas['2026-11-11'].traspasos_externos, null);
    assert.equal(r.vistas.CONSOLIDADO.decenas['2027-02-01'].traspasos_externos, -2500);
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

  test('«no relacionadas con la farmacia»: cuentan en el saldo (real), no en el cash flow generado farmacia; H7-REAL-10: sin media a futuro', async () => {
    const r = calcularCashflow(await datosFixtures());
    const real = r.vistas.PIO.decenas['2026-11-01'];
    assert.equal(real.no_relacionadas, 650 - 1200);
    // Previsto: sin Excel ni apunte, nada (antes, su media); el fondo de PIO, por su Excel (−2.500 en 1–10/02/2027).
    assert.equal(r.vistas.PIO.decenas['2026-12-01'].no_relacionadas, null);
    const d = r.vistas.PIO.decenas['2027-02-01'];
    assert.deepEqual([d.no_relacionadas, d.traspasos_externos], [null, -2500]);
    assert.equal(d.neto, Math.round(((d.farmacia as number) + (d.traspasos_externos as number)) * 100) / 100);
    assert.equal(real.neto, Math.round(((real.farmacia as number) + (real.no_relacionadas as number) + (real.traspasos_externos as number)) * 100) / 100);
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
      // H7-REAL-10 (sin media de lo ajeno a la farmacia): robot de 40.000 € y reforma del escaparate de RITA (8.180 €)
      // para mantener la naranja de RITA en 11–20/12 y un solo rojo en 11–20/01/2027.
      assert.deepEqual([saldo(r, 'PIO', '2027-01-11'), saldo(r, 'RITA', '2027-01-11'), rojos[0].importe], [-10037.51, 7300, 2737.51]);
      assert.equal(saldo(r, 'RITA', '2026-12-11'), -5000);
      // Gris: importación de hace 6 días y el concepto terminado (ninguno por traspasos).
      assert.deepEqual(r.avisos.filter((a) => a.tipo === 'gris').map((a) => a.codigo), ['IMPORTACION_ANTIGUA', 'CONCEPTO_TERMINADO']);
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
    assert.equal(c?.importe, -18000); // 6.000 real (1–10/11) + Excel 520 (11–20/11) + la diferencia de la media del mes, 11.480 (21–30/11)
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
    // Neto 70; H7-REAL-8: el Excel (100) es mayor y gana; los vencimientos quedan como «la otra».
    const abc = linea(ab, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-11-21'];
    assert.deepEqual([abc.fuente, abc.importe, abc.vencimientos?.neto, abc.comparada], ['EXCEL', -100, 70, { fuente: 'VENCIMIENTOS', importe: -70 }]);
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
  // H7-REAL-8: estos casos prueban el mecanismo con una ventana de 3 meses (N en un único punto, CONFIG_CASHFLOW.meses_media);
  // la de 12 (la vigente, decisión de Pío) va en «H7-REAL-8: media de 12 meses».
  const base = { hoy, importaciones: IMP_OK, cuentas: CUENTAS, config: { ...CONFIG_CASHFLOW, meses_media: 3 } };
  const reales = (cuenta: string, categoria: string, concepto: string, porPosicion: [number, number, number], desde = '2026-06-01', hasta = '2026-11-11') => {
    const out: ImporteCashflow[] = [];
    for (let d = desde; d <= hasta; d = siguienteDecena(d)) out.push(fila(cuenta, d, categoria, concepto, porPosicion[ordinalDecena(d) - 1]));
    return out.filter((f) => f.importe !== 0);
  };
  const saldos = [banco('PIO', '2026-06-01', 0, { saldo_bancos: null }), banco('PIO', '2026-11-11', 10000), banco('RITA', '2026-11-11', 0)];
  // H7-REAL-9: ya no hay línea de media de categoría: suma, por decena futura, las cifras de media de los conceptos de la
  // categoría (cada uno en su línea), con la media del primero que la lleve.
  const media = (r: ResultadoCashflow, cuenta: 'PIO' | 'RITA', categoria: string) => {
    const out: Record<string, { importe: number; media: Celda['media']; conceptos: string[] }> = {};
    for (const l of r.vistas[cuenta].lineas.filter((x) => x.categoria === categoria)) {
      for (const [d, c] of Object.entries(l.celdas)) {
        if (c.real || c.fuente !== 'MEDIA' || c.importe === null) continue;
        const x = out[d] ?? { importe: 0, media: c.media, conceptos: [] };
        x.importe = Math.round((x.importe + c.importe) * 100) / 100;
        x.conceptos.push(l.concepto);
        out[d] = x;
      }
    }
    return out;
  };

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

  test('H7-REAL-10: por concepto y MES: Excel inferior a la media del mes → el Excel y la diferencia en la decena habitual; superior → solo el Excel; los demás conceptos, su media', () => {
    const importes = [
      ...reales('PIO', 'RS Gastos generales', 'Luz', [1000, 1000, 1000]), ...reales('PIO', 'RS Gastos generales', 'Agua', [500, 500, 500]),
      fila('PIO', '2026-12-11', 'RS Gastos generales', 'Agua', 450), // Excel inferior a la media del mes (1.500)
      fila('PIO', '2027-01-11', 'RS Gastos generales', 'Agua', 1700), // Excel superior a la media del mes (1.500)
    ];
    const r = calcularCashflow({ ...base, vencimientos: [], importes, saldos });
    const agua = linea(r, 'PIO', 'RS Gastos generales', 'Agua').celdas;
    // Diciembre: 450 frente a 1.500 → gana la media: el Excel en 11–20/12 y 1.050 en 1–10/12 (primera de las de mayor
    // media sin nada conocido); 21–31/12, nada. Total del mes = 1.500 (antes, por decena: 500 + 500 + 500 = 1.500 también).
    assert.deepEqual([agua['2026-12-11'].fuente, agua['2026-12-11'].importe, agua['2026-12-11'].excel, agua['2026-12-01'].fuente, agua['2026-12-01'].importe, agua['2026-12-21']],
      ['EXCEL', -450, -450, 'MEDIA', -1050, undefined]);
    assert.deepEqual(agua['2026-12-11'].mes, { mes: '2026-12', regla: 'POSICION', conocido: -450, media: -1500, gana: 'MEDIA', diferencia: -1050, decena_diferencia: '2026-12-01', decenas_conocidas: ['2026-12-11'], apunte: false });
    // Enero: 1.700 frente a 1.500 → solo el Excel (antes: 500 + 1.700 + 500 = 2.700, doble cómputo).
    assert.deepEqual([agua['2027-01-11'].fuente, agua['2027-01-11'].importe, agua['2027-01-11'].mes?.gana, agua['2027-01-01'], agua['2027-01-21']], ['EXCEL', -1700, 'CONOCIDO', undefined, undefined]);
    // Sin nada conocido (febrero): la media en cada decena.
    assert.deepEqual([agua['2027-02-01'].importe, agua['2027-02-11'].importe, agua['2027-02-21'].importe, agua['2027-02-01'].mes], [-500, -500, -500, null]);
    // Luz (sin Excel): su media, aunque Agua esté anotada.
    const luz = linea(r, 'PIO', 'RS Gastos generales', 'Luz').celdas;
    assert.deepEqual([luz['2026-12-11'].fuente, luz['2026-12-11'].importe, luz['2027-01-11'].importe], ['MEDIA', -1000, -1000]);
    const s = r.vistas.PIO.decenas;
    assert.deepEqual([s['2026-12-01'].salidas, s['2026-12-11'].salidas, s['2026-12-21'].salidas, s['2027-01-11'].salidas, s['2027-01-21'].salidas], [-2050, -1450, -1000, -2700, -1000]);
    // Doble cómputo evitado (regla 4): enero (2.700 → 1.700): un caso, 1.000 €.
    assert.deepEqual(r.prevision.PIO.doble_computo, { casos: 1, evitado: 1000 });
    assert.ok(r.vistas.PIO.lineas.every((l) => !l.media));
    // Excel con importe desconocido: no se compara y el mes queda sin media de ese concepto (cuenta como desconocido, nunca 0).
    const nulo = calcularCashflow({ ...base, vencimientos: [], saldos, importes: [...importes, fila('PIO', '2027-02-11', 'RS Gastos generales', 'Agua', null)] });
    const an = linea(nulo, 'PIO', 'RS Gastos generales', 'Agua').celdas;
    assert.deepEqual([an['2027-02-11'].fuente, an['2027-02-11'].importe, an['2027-02-11'].mes, an['2027-02-11'].desconocidos, an['2027-02-01'], an['2027-02-21']], ['EXCEL', null, null, 1, undefined, undefined]);
  });

  test('H7-REAL-3/9: categoría CON vencimientos: cada concepto con su previsión (vencimientos, Excel o media); sin doble cómputo', () => {
    const importes = [
      ...reales('PIO', 'RS Proveedores', 'ALLIANCE', [1000, 1000, 1000]), ...reales('PIO', 'RS Proveedores', 'COFARES', [500, 500, 500]),
      ...reales('PIO', 'RS Proveedores', 'Varios', [200, 200, 200]),
      fila('PIO', '2026-12-11', 'RS Proveedores', 'COFARES', 450), // anotado en el Excel (inferior a su media)
    ];
    // Vencimiento de ALLIANCE (1.200 en 1–10/12), lo conocido de diciembre, frente a su media del mes (3.000).
    const vencimientos = [venc({ fecha_vencimiento: '2026-12-05', importe: 1200 })];
    const r = calcularCashflow({ ...base, vencimientos, importes, saldos });
    const a = linea(r, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas;
    const cof = linea(r, 'PIO', 'RS Proveedores', 'COFARES').celdas;
    // H7-REAL-10: ALLIANCE: los vencimientos en su decena y la diferencia del mes (1.800) en 11–20/12; COFARES: Excel 450
    // en 11–20/12 y la diferencia (1.050) en 1–10/12; Varios, su media en cada decena.
    assert.deepEqual([a['2026-12-01'].fuente, a['2026-12-01'].importe, a['2026-12-11'].fuente, a['2026-12-11'].importe, a['2026-12-21']], ['VENCIMIENTOS', -1200, 'MEDIA', -1800, undefined]);
    assert.deepEqual([cof['2026-12-01'].fuente, cof['2026-12-01'].importe, cof['2026-12-11'].fuente, cof['2026-12-11'].importe, cof['2026-12-21']], ['MEDIA', -1050, 'EXCEL', -450, undefined]);
    const d = r.vistas.PIO.decenas;
    // Total del mes por concepto: ALLIANCE 3.000, COFARES 1.500, Varios 600 (sin doble cómputo).
    assert.deepEqual([d['2026-12-01'].salidas, d['2026-12-11'].salidas, d['2026-12-21'].salidas], [-2450, -2450, -200]);
    // Correspondencia por nombre comercial: un vencimiento de FEDEFARMA va a «FEDERACIO» (400; la media del mes, 900).
    const fed = calcularCashflow({ ...base, saldos, vencimientos: [venc({ proveedor_comercial: 'FEDEFARMA', fecha_vencimiento: '2026-12-05', importe: 400 })],
      importes: [...reales('PIO', 'RS Proveedores', 'FEDERACIO', [300, 300, 300]), ...reales('PIO', 'RS Proveedores', 'HEFAME', [100, 100, 100])] });
    const f = linea(fed, 'PIO', 'RS Proveedores', 'FEDERACIO').celdas;
    assert.deepEqual([f['2026-12-01'].fuente, f['2026-12-01'].importe, f['2026-12-01'].comparada, f['2026-12-11'].importe, fed.vistas.PIO.decenas['2026-12-01'].salidas],
      ['VENCIMIENTOS', -400, null, -500, -500]);
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
    // H7-REAL-10: los vencimientos de cada decena son lo conocido del mes (400 + 3.500 − 50 = 3.850), frente a la media del
    // mes (1.000 + 3.000 = 4.000): gana la media; todas las decenas con media tienen algo conocido, así que la diferencia
    // (150) va a la de mayor media (11–20/12).
    assert.deepEqual([a['2026-12-01'].fuente, a['2026-12-01'].importe, a['2026-12-01'].vencimientos?.neto, a['2026-12-01'].comparada], ['VENCIMIENTOS', -400, 400, null]);
    assert.deepEqual(a['2026-12-01'].media?.base.map((b) => b.clave), ['2026-09-01', '2026-10-01', '2026-11-01']);
    assert.deepEqual([a['2026-12-11'].fuente, a['2026-12-11'].importe, a['2026-12-11'].suma_media, a['2026-12-11'].media?.media], ['VENCIMIENTOS', -3650, -150, -3000]);
    assert.deepEqual([a['2026-12-21'].fuente, a['2026-12-21'].importe], ['VENCIMIENTOS', 50]);
    assert.deepEqual([a['2026-12-11'].mes?.conocido, a['2026-12-11'].mes?.media, a['2026-12-11'].mes?.gana], [-3850, -4000, 'MEDIA']);
    // Sin vencimientos (enero): la media del concepto en cada decena.
    assert.deepEqual([a['2027-01-01'].fuente, a['2027-01-01'].importe, a['2027-01-11'].importe], ['MEDIA', -1000, -3000]);
    assert.deepEqual([r.vistas.PIO.decenas['2026-12-01'].salidas, r.vistas.PIO.decenas['2026-12-11'].salidas], [-900, -4150]);
    // Vencimientos del mes mayores que la media del mes: solo los vencimientos.
    const mayores = linea(calcularCashflow({ ...base, importes, saldos, vencimientos: [vencimientos[0], { ...vencimientos[1], importe: 5000 }] }), 'PIO', 'RS Proveedores', 'ALLIANCE').celdas;
    assert.deepEqual([mayores['2026-12-01'].importe, mayores['2026-12-11'].importe, mayores['2026-12-11'].mes?.gana, mayores['2026-12-21']], [-400, -5000, 'CONOCIDO', undefined]);
    // En su decena, el Excel frente a los vencimientos (3.500): gana el mayor; a igualdad, los vencimientos.
    const conExcel = (x: number) => linea(calcularCashflow({ ...base, vencimientos, importes: [...importes, fila('PIO', '2026-12-11', 'RS Proveedores', 'ALLIANCE', x)], saldos }), 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-12-11'];
    const gx = conExcel(4000);
    assert.deepEqual([gx.fuente, gx.importe, gx.comparada, gx.mes?.gana], ['EXCEL', -4000, { fuente: 'VENCIMIENTOS', importe: -3500 }, 'CONOCIDO']);
    // (Con 3.500 o 2.000 lo conocido del mes, 3.850, sigue por debajo de la media del mes: la diferencia, 150, suma aquí.)
    const sinMedia = (c: Celda) => Math.round(((c.importe as number) - (c.suma_media ?? 0)) * 100) / 100;
    const gv = conExcel(3500);
    assert.deepEqual([gv.fuente, sinMedia(gv), gv.suma_media, gv.comparada, gv.diferencia], ['VENCIMIENTOS', -3500, -150, { fuente: 'EXCEL', importe: -3500 }, false]);
    const em = conExcel(2000);
    assert.deepEqual([em.fuente, sinMedia(em), em.comparada, em.diferencia], ['VENCIMIENTOS', -3500, { fuente: 'EXCEL', importe: -2000 }, true]);
    // Vencimiento sin importe conocido: no se compara (los vencimientos, saldo incompleto) y ese mes no lleva media.
    const n = linea(calcularCashflow({ ...base, vencimientos: [venc({ fecha_vencimiento: '2026-12-05', importe: null })], importes, saldos }), 'PIO', 'RS Proveedores', 'ALLIANCE').celdas;
    assert.deepEqual([n['2026-12-01'].fuente, n['2026-12-01'].importe, n['2026-12-11'], n['2027-01-11'].importe], ['VENCIMIENTOS', null, undefined, -3000]);
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

  test('traspasos internos: neutros, sin media; H7-REAL-10: «no relacionadas» sin media (CATEGORIAS_SIN_MEDIA): solo el Excel o un apunte', () => {
    assert.deepEqual([...CATEGORIAS_SIN_MEDIA], ['NO_RELACIONADA', 'TRASPASO_EXTERNO']);
    const importes = [...reales('PIO', 'RS Traspasos', 'La Caixa Rita', [0, 0, 5000]), ...reales('PIO', 'RS No relacionadas con la farmacia', 'Préstamo', [300, 0, 0]),
      ...reales('PIO', 'RE No relacionadas con la farmacia', 'Alquiler', [650, 0, 0])];
    const r = calcularCashflow({ ...base, vencimientos: [], importes, saldos });
    assert.equal(r.vistas.PIO.lineas.find((l) => l.categoria === 'RS Traspasos' && l.media), undefined);
    assert.ok(Object.values(r.vistas.PIO.lineas.find((l) => l.concepto === 'La Caixa Rita')!.celdas).every((c) => c.fuente === 'REAL'));
    // Sin apunte ni Excel: 0 previsto (ninguna cifra; el saldo previsto no cambia).
    assert.equal(linea(r, 'PIO', 'RS No relacionadas con la farmacia', 'Préstamo').celdas['2026-12-01'], undefined);
    assert.deepEqual([r.vistas.PIO.decenas['2026-12-01'].no_relacionadas, saldo(r, 'PIO', '2026-12-01')], [null, 10000]);
    assert.deepEqual(r.categorias_media, []);
    // Con apunte manual o Excel: cuenta (sin comparar con ninguna media).
    const con = calcularCashflow({ ...base, vencimientos: [], saldos, importes: [...importes, fila('PIO', '2027-01-01', 'RS No relacionadas con la farmacia', 'Préstamo', 120)],
      apuntes_manuales: [{ cuenta: 'PIO', decena_inicio: '2026-12-01', categoria: 'RE No relacionadas con la farmacia', concepto: 'Alquiler', importe: 700 }] });
    const pr = linea(con, 'PIO', 'RS No relacionadas con la farmacia', 'Préstamo').celdas;
    const al = linea(con, 'PIO', 'RE No relacionadas con la farmacia', 'Alquiler').celdas;
    assert.deepEqual([pr['2027-01-01'].fuente, pr['2027-01-01'].importe, pr['2027-01-01'].mes, pr['2027-01-01'].media], ['EXCEL', -120, null, null]);
    assert.deepEqual([al['2026-12-01'].fuente, al['2026-12-01'].importe, al['2026-12-01'].media, al['2027-01-01']], ['MANUAL', 700, null, undefined]);
    assert.deepEqual([saldo(con, 'PIO', '2026-12-01'), saldo(con, 'PIO', '2027-01-01')], [10700, 10580]);
  });

  test('H7-REAL-4: traspasos externos: media por concepto (en su línea), en el saldo de la cuenta y del consolidado; el Excel manda (sin doble cómputo)', () => {
    const importes = [
      ...reales('RITA', 'RS Traspasos', 'TRASPASO A LA SL (JUBILACIO ETC)', [0, 6000, 0]), ...reales('RITA', 'RS Traspasos', 'Otro fondo', [0, 1000, 0]),
      ...reales('RITA', 'RS Traspasos', 'DEPÓSITO CONECTADO', [0, 9000, 0]), // interno: sin media
      fila('RITA', '2026-12-11', 'RS Traspasos', 'TRASPASO A LA SL (JUBILACIO ETC)', 8000), // anotado, mayor que su media (6.000): manda
    ];
    const conSaldos = { ...base, vencimientos: [], importes, saldos: [...saldos.filter((s) => s.cuenta !== 'RITA'), banco('RITA', '2026-11-11', 50000)] };
    const r = calcularCashflow(conSaldos);
    const sl = linea(r, 'RITA', 'RS Traspasos', 'TRASPASO A LA SL (JUBILACIO ETC)');
    assert.equal(sl.clase, 'TRASPASO_EXTERNO');
    // H7-REAL-10: sin media (CATEGORIAS_SIN_MEDIA): solo lo anotado en el Excel.
    assert.deepEqual([sl.celdas['2026-11-21'], sl.celdas['2027-01-11']], [undefined, undefined]);
    assert.deepEqual([sl.celdas['2026-12-11'].fuente, sl.celdas['2026-12-11'].importe, sl.celdas['2026-12-11'].mes, sl.celdas['2026-12-11'].media], ['EXCEL', -8000, null, null]);
    assert.equal(linea(r, 'RITA', 'RS Traspasos', 'Otro fondo').celdas['2026-12-11'], undefined);
    assert.ok(Object.values(linea(r, 'RITA', 'RS Traspasos', 'DEPÓSITO CONECTADO').celdas).every((c) => c.fuente === 'REAL'));
    const d = r.vistas.RITA.decenas;
    assert.deepEqual([d['2026-12-11'].traspasos_externos, d['2026-12-11'].traspasos, d['2026-12-11'].saldo], [-8000, null, 42000]);
    // Consolidado: el externo cuenta (línea y saldo); el interno no compensado, solo en la línea plegada.
    assert.ok(r.vistas.CONSOLIDADO.lineas.some((l) => l.concepto === 'TRASPASO A LA SL (JUBILACIO ETC)'));
    assert.ok(!r.vistas.CONSOLIDADO.lineas.some((l) => l.concepto === 'DEPÓSITO CONECTADO'));
    assert.equal(r.vistas.CONSOLIDADO.decenas['2026-12-11'].traspasos_externos, -8000);
    assert.equal(r.vistas.CONSOLIDADO.decenas['2026-12-11'].traspasos, null);
    assert.equal(r.vistas.CONSOLIDADO.decenas['2026-11-11'].traspasos, -9000);
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

  test('apunte manual (hueco preparado): antes que el Excel y comparado con los vencimientos; sin apuntes, nada cambia', () => {
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
    // H7-REAL-9: el apunte de otro concepto (enero: Finiquito) no deja a Nóminas sin su media.
    assert.deepEqual([media(r, 'PIO', 'RS Personal')['2027-01-01'].importe, media(r, 'PIO', 'RS Personal')['2027-01-01'].conceptos], [-1000, ['Nóminas']]);
    assert.equal(linea(r, 'PIO', 'RS Personal', 'Finiquito').celdas['2027-01-01'].importe, -400);
    assert.equal(media(r, 'PIO', 'RS Personal')['2027-02-01'].importe, -1000);
    // H7-REAL-8: el apunte es la previsión base y se compara con los vencimientos: 999 > 800 → el apunte.
    const al = linea(r, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-12-01'];
    assert.deepEqual([al.fuente, al.importe, al.comparada], ['MANUAL', -999, { fuente: 'VENCIMIENTOS', importe: -800 }]);
    // Apunte menor que los vencimientos: los vencimientos.
    const menor = calcularCashflow({ ...base, vencimientos: [venc({ fecha_vencimiento: '2026-12-05', importe: 800 })], importes, saldos,
      apuntes_manuales: [{ cuenta: 'PIO', decena_inicio: '2026-12-01', categoria: 'RS Proveedores', concepto: 'ALLIANCE', importe: 300 }] });
    assert.deepEqual([linea(menor, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-12-01'].fuente, linea(menor, 'PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-12-01'].comparada],
      ['VENCIMIENTOS', { fuente: 'MANUAL', importe: -300 }]);
  });

  test('H7-REAL-8: media de 12 meses (decisión de Pío): un pago grande de hace 8 meses entra en la de 12, no en la de 3', () => {
    // Un año de reales (desde 11/2025): «Reparación» 6.000 en 21–31/03/2026 y nada más en la categoría.
    const saldos12 = [banco('PIO', '2025-11-01', 0, { saldo_bancos: null }), banco('PIO', '2026-11-11', 10000), banco('RITA', '2026-11-11', 0)];
    // H7-REAL-10: en el mismo concepto (un concepto con un solo pago sería esporádico: el año anterior, no la media).
    const importes = [...reales('PIO', 'RS Gastos generales', 'Luz', [100, 100, 100], '2025-11-01'), fila('PIO', '2026-03-21', 'RS Gastos generales', 'Luz', 6000)];
    const r12 = calcularCashflow({ ...base, config: CONFIG_CASHFLOW, vencimientos: [], importes, saldos: saldos12 });
    const m12 = media(r12, 'PIO', 'RS Gastos generales')['2026-11-21'];
    assert.deepEqual([m12.importe, m12.media?.base.length, m12.media?.base[0].clave], [-600, 12, '2025-11-21']); // 100 + 6.000 ÷ 12
    const r3 = calcularCashflow({ ...base, vencimientos: [], importes, saldos: saldos12 });
    assert.equal(media(r3, 'PIO', 'RS Gastos generales')['2026-11-21'].importe, -100);
    // Menos de 12 meses de historia: los que haya (desde la primera decena de la cuenta).
    const corto = calcularCashflow({ ...base, config: CONFIG_CASHFLOW, vencimientos: [], importes: reales('PIO', 'RS Gastos generales', 'Luz', [100, 100, 100]), saldos });
    assert.equal(media(corto, 'PIO', 'RS Gastos generales')['2026-11-21'].media?.base.length, 5); // junio a octubre
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

describe('H7-REAL-7: equivalencias de concepto y horizonte de los avisos', () => {
  test('CONCEPTOS_EQUIVALENTES: JNTL CONSUMER (ORALDI…) y JHONSON & JHONSON → KENVUE (sin mayúsculas ni acentos); el resto, igual', () => {
    assert.equal(conceptoEquivalente('JNTL CONSUMER (ORALDINE) S.L.'), 'KENVUE');
    assert.equal(conceptoEquivalente('jntl consumer (oraldi'), 'KENVUE');
    assert.equal(conceptoEquivalente(' Jhonson  &  Jhonson '), 'KENVUE');
    assert.equal(conceptoEquivalente('JNTL CONSUMER'), 'JNTL CONSUMER'); // sin «(ORALDI», no
    assert.equal(conceptoEquivalente('ALLIANCE'), 'ALLIANCE');
    assert.equal(CONCEPTOS_EQUIVALENTES.filter((e) => e.queda === 'KENVUE').length, 2);
    assert.equal(comercialDeConcepto('KENVUE'), 'KENVUE');
  });

  test('H7-REAL-8: las 9 fusiones de Pío; truncados («…») por prefijo en el alias y en el que queda (texto del Excel); ambiguo o sin coincidencia: sin fusionar', () => {
    assert.equal(CONCEPTOS_EQUIVALENTES.length, 11);
    const exactos: [string, string][] = [['PROTECTFARMA', 'PROTECFARMA'], ['SM NATURAL (SOLARAY)', 'SOLARAY'], ['LAB. VILARDELL (NO USAR)', 'LAB. VILARDELL'],
      ['BIODERMA (NAOS)', 'BIODERMA'], ['DERMOFARM (CUMLAUDE)', 'CUMLAUDE'], ['AREAFAR (ENNA CYCLE)', 'AREAFAR'], ['EXPOFARM CREU, CASH', 'EXPOFARM'], ['PEROXIDOS', 'PEROXFARMA']];
    for (const [a, q] of exactos) assert.equal(conceptoEquivalente(a), q, a);
    // El que queda con otra grafía en el Excel: la del Excel (misma línea).
    assert.equal(resolverEquivalencias(['Peroxidos', 'Peroxfarma']).mapa.get('Peroxidos'), 'Peroxfarma');
    // Truncados: alias y nombre que queda por prefijo; queda el texto completo del Excel.
    const ok = resolverEquivalencias(['DERMOPHARMACIE I PERFUMERIA', 'Dermofarmacia Perfumeria SL']);
    assert.deepEqual([...ok.mapa], [['DERMOPHARMACIE I PERFUMERIA', 'Dermofarmacia Perfumeria SL']]);
    assert.deepEqual([ok.ambiguas, ok.sin_coincidencia], [0, 1]); // JNTL… no está
    // Prefijo del que queda con dos nombres distintos: ambiguo, no se fusiona.
    const amb = resolverEquivalencias(['DERMOPHARMACIE I PERFUMERIA', 'DERMOFARMACIA PERFUMERIA SL', 'DERMOFARMACIA PERFUMES BCN']);
    assert.deepEqual([amb.mapa.size, amb.ambiguas], [0, 1]);
    // Prefijo del que queda sin coincidencia (el alias sí está): no se fusiona.
    const sin = resolverEquivalencias(['DERMOPHARMACIE I PERFUMERIA']);
    assert.deepEqual([sin.mapa.size, sin.sin_coincidencia], [0, 2]);
    // Mismo nombre con distinta grafía: no es ambiguo (es el mismo nombre).
    assert.equal(resolverEquivalencias(['JNTL CONSUMER (ORALDINE)', 'jntl consumer (oraldine)']).mapa.size, 2);
  });

  test('H7-REAL-8: fusiones en el cálculo por cuenta (cada hoja); saldo final por decena idéntico con y sin fusiones', () => {
    const importes = [
      ...['2026-08-11', '2026-09-11', '2026-10-11'].flatMap((d) => [fila('PIO', d, 'RS Proveedores', 'PROTECTFARMA', 100), fila('PIO', d, 'RS Proveedores', 'PROTECFARMA', 20)]),
      fila('PIO', '2026-11-11', 'RS Proveedores', 'PEROXIDOS', 50), fila('PIO', '2026-11-01', 'RE Cobro TPV', 'TPV', 1000),
      // RITA: prefijo ambiguo en su hoja (en PIO no lo sería): sin fusionar.
      fila('RITA', '2026-10-11', 'RS Proveedores', 'DERMOPHARMACIE I PERFUMERIA', 10), fila('RITA', '2026-10-11', 'RS Proveedores', 'DERMOFARMACIA PERFUMERIA SL', 10),
      fila('RITA', '2026-10-11', 'RS Proveedores', 'DERMOFARMACIA PERFUMES', 10),
    ];
    const b = { hoy: '2026-11-16', importaciones: IMP_OK, cuentas: CUENTAS, saldos: [banco('PIO', '2026-11-01', 5000), banco('RITA', '2026-11-01', 1000)], vencimientos: [] };
    const r = calcularCashflow({ ...b, importes });
    assert.deepEqual(linea(r, 'PIO', 'RS Proveedores', 'PROTECFARMA').celdas['2026-10-11'].importe, -120);
    assert.deepEqual(linea(r, 'PIO', 'RS Proveedores', 'PEROXFARMA').celdas['2026-11-11'].importe, -50);
    assert.equal(r.vistas.RITA.lineas.filter((l) => /^DERMO/.test(l.concepto)).length, 3);
    assert.deepEqual([r.equivalencias.filas, r.equivalencias.ambiguas], [{ PIO: 4, RITA: 0 }, 1]);
    const sin = calcularCashflow({ ...b, importes: importes.map((f) => ({ ...f, concepto: `ZZ ${f.concepto}` })) });
    for (const v of ['PIO', 'RITA', 'CONSOLIDADO'] as const) for (const d of r.decenas) assert.equal(saldo(r, v, d), saldo(sin, v, d), `${v} ${d}`);
  });

  test('real, Excel y media sumados bajo KENVUE por cuenta y decena; «incluye»; saldo final por decena idéntico sin la equivalencia', () => {
    const importes = [
      // Real (base de la media de la 2.ª decena: de julio a octubre; H7-REAL-10: 4 meses, frecuente, no esporádico) y
      // Excel a futuro, repartidos entre los dos alias.
      ...['2026-07-11', '2026-08-11', '2026-09-11', '2026-10-11'].flatMap((d) => [fila('PIO', d, 'RS Proveedores', 'JNTL CONSUMER (ORALDINE)', 100), fila('PIO', d, 'RS Proveedores', 'JHONSON & JHONSON', 50)]),
      fila('PIO', '2026-11-11', 'RS Proveedores', 'JNTL CONSUMER (ORALDINE)', 70), fila('PIO', '2026-11-11', 'RS Proveedores', 'JHONSON & JHONSON', 30),
      fila('PIO', '2026-11-01', 'RE Cobro TPV', 'TPV', 1000), fila('RITA', '2026-11-01', 'RS Proveedores', 'JHONSON & JHONSON', 40),
    ];
    const saldos = [banco('PIO', '2026-11-01', 5000), banco('RITA', '2026-11-01', 1000)];
    const base = { hoy: '2026-11-16', importaciones: IMP_OK, cuentas: CUENTAS, saldos, vencimientos: [] };
    const r = calcularCashflow({ ...base, importes });
    const k = linea(r, 'PIO', 'RS Proveedores', 'KENVUE');
    assert.deepEqual(k.incluye, ['JHONSON & JHONSON', 'JNTL CONSUMER (ORALDINE)']);
    assert.equal(r.vistas.PIO.lineas.filter((l) => l.categoria === 'RS Proveedores' && !l.media).length, 1);
    // H7-REAL-10: Excel sumado (100) frente a la media sumada del mes (150, solo en la 2.ª decena): gana la media; la
    // diferencia (50) va a la misma decena (la única con media).
    assert.deepEqual([k.celdas['2026-10-11'].importe, k.celdas['2026-10-11'].excel_filas, k.celdas['2026-11-11'].importe, k.celdas['2026-11-11'].fuente, k.celdas['2026-11-11'].suma_media, k.celdas['2026-11-11'].mes?.conocido],
      [-150, 2, -150, 'EXCEL', -50, -100]);
    // La media del concepto usa los reales sumados (−150 en cada 2.ª decena).
    assert.equal(k.celdas['2026-12-11'].importe, -150);
    // Consolidado: una línea con los alias de las dos cuentas.
    assert.deepEqual(linea(r, 'CONSOLIDADO', 'RS Proveedores', 'KENVUE').incluye, ['JHONSON & JHONSON', 'JNTL CONSUMER (ORALDINE)']);
    // Sin la equivalencia (otros nombres, mismos importes): los saldos de todas las decenas, idénticos.
    const sin = calcularCashflow({ ...base, importes: importes.map((f) => ({ ...f, concepto: `ZZ ${f.concepto}` })) });
    for (const v of ['PIO', 'RITA', 'CONSOLIDADO'] as const) for (const d of r.decenas) assert.equal(saldo(r, v, d), saldo(sin, v, d), `${v} ${d}`);
    assert.equal(sin.vistas.PIO.lineas.filter((l) => l.categoria === 'RS Proveedores' && !l.media).length, 2);
  });

  test('vencimientos del sistema con nombre comercial KENVUE van a la línea KENVUE', () => {
    const importes = [fila('PIO', '2026-10-11', 'RS Proveedores', 'JHONSON & JHONSON', 50), fila('PIO', '2026-11-01', 'RE Cobro TPV', 'TPV', 1000)];
    const r = calcularCashflow({ hoy: '2026-11-16', importaciones: IMP_OK, cuentas: CUENTAS, importes, saldos: [banco('PIO', '2026-11-01', 5000)],
      vencimientos: [venc({ proveedor_comercial: 'KENVUE', proveedor_nombre: 'KENVUE', fecha_vencimiento: '2026-11-25', importe: 900 })] });
    const c = linea(r, 'PIO', 'RS Proveedores', 'KENVUE').celdas['2026-11-21'];
    assert.deepEqual([c.fuente, c.importe, c.vencimientos?.comercial], ['VENCIMIENTOS', -900, 'KENVUE']);
    assert.equal(r.fuera.venc_sin_concepto.length, 0);
  });

  test('avisos de saldo solo en los 12 meses previstos tras la última decena real (como el indicador)', () => {
    // Solo lo anotado (sin reales: ninguna media).
    const importes = [fila('PIO', '2027-12-11', 'RS Inversiones', 'Obra', 9000), fila('PIO', '2027-10-21', 'RS Inversiones', 'Obra', 2000)];
    const r = calcularCashflow({ hoy: '2026-11-16', importaciones: IMP_OK, cuentas: CUENTAS, importes, saldos: [banco('PIO', '2026-11-01', 5000), banco('RITA', '2026-11-01', 0)], vencimientos: [] });
    assert.ok((saldo(r, 'CONSOLIDADO', '2027-12-11') as number) < 0);
    // Horizonte: hasta 01–10/11/2027 (36 decenas tras 01–10/11/2026). La obra de 12/2027 no da aviso.
    assert.deepEqual(r.avisos.filter((a) => a.tipo !== 'gris').map((a) => a.decena), []);
    const dentro = calcularCashflow({ hoy: '2026-11-16', importaciones: IMP_OK, cuentas: CUENTAS, saldos: [banco('PIO', '2026-11-01', 5000), banco('RITA', '2026-11-01', 0)], vencimientos: [],
      importes: [...importes, fila('PIO', '2027-11-01', 'RS Inversiones', 'Obra', 4000)] });
    assert.deepEqual(dentro.avisos.filter((a) => a.tipo === 'rojo').map((a) => [a.decena, a.hasta]), [['2027-11-01', '2027-11-01']]);
  });
});

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
    // H7-REAL-7: el diagnóstico de la previsión (prev_*, equivalencias_*, kenvue_*) se prueba aparte.
    // H7-REAL-10: el de las reglas de la previsión (operativo_*, conceptos_*, doble_computo_*, top_*), también.
    const nuevas = /^(prev_|equivalencias_|kenvue_|indicador_media|excel_gana_media_|media_gana_excel_|operativo_|conceptos_|doble_computo_|top_)/;
    assert.deepEqual(Object.fromEntries(Object.entries(diag).filter(([k]) => !nuevas.test(k))), {
      vigente: true, dias_desde_vigente: 6, ultima_error: true,
      importes_pio: 4, saldos_pio: 2, importes_rita: 1, saldos_rita: 2, importes_sl: 1, saldos_sl: 0, importes_otras: 0, saldos_otras: 0,
      decenas_diferencia_banco_formulas: 1, decenas_no_cuadran: 1,
      // H7-REAL-2: por cuenta y categoría (reales = decena con saldo de banco; futuros = anotados) y efectivo.
      efectivo_pio_reales: 0, efectivo_pio_futuros: 0, efectivo_pio_en_otra_categoria: 0,
      efectivo_rita_reales: 0, efectivo_rita_futuros: 0, efectivo_rita_en_otra_categoria: 0,
      cat_pio_re_cobro_tpv_reales: 1, cat_pio_rs_gastos_generales_reales: 1, cat_pio_rs_personal_futuros: 1, cat_pio_rs_proveedores_reales: 1,
      cat_rita_re_cobro_tpv_reales: 1,
      // H7-REAL-5: sin vencimientos; indicador real no disponible (una sola decena real), previsto disponible. H7-REAL-10:
      // con una sola decena real todos los conceptos son esporádicos (el año anterior, que no hay): solo lo anotado.
      vencimientos_leidos: 0,
      indicador_antes_real_disponible: false, indicador_antes_prevista_disponible: true, indicador_antes_prevista_eur_mes: 12, indicador_antes_prevista_negativa: true,
      indicador_despues_real_disponible: false, indicador_despues_prevista_disponible: true, indicador_despues_prevista_eur_mes: 12, indicador_despues_prevista_negativa: true,
    });
    const vacia = diagnosticoCashflow(await leerCashflowReal(consultarSimulada(baseSimulada({ importaciones: [] }))), '2026-11-16');
    assert.deepEqual([vacia.vigente, 'dias_desde_vigente' in vacia, vacia.ultima_error, vacia.importes_pio], [false, false, false, 0]);
    // Ningún valor es un concepto ni un texto (H7-REAL-7: las listas, solo etiquetas de categoría o de fuente; H7-REAL-10:
    // las cifras mayores de cada mes, top_*_eur, en euros enteros sin signo).
    assert.ok(Object.entries(diag).every(([k, v]) => typeof v === 'boolean' || Number.isSafeInteger(v)
      || (Array.isArray(v) && v.every((x) => (typeof x === 'string' && /^[a-z_][a-z0-9_]*$/.test(x)) || (/^top_.*_eur$/.test(k) && Number.isSafeInteger(x) && (x as number) >= 0)))));
    assert.deepEqual([diag.prev_pio_disponible, diag.equivalencias_filas_pio, diag.kenvue_venc_con_comercial, diag.kenvue_venc_sin_comercial], [true, 0, 0, 0]);
  });

  test('H7-REAL-5 check:real: decenas en que gana la media frente a los vencimientos, por concepto (nombre comercial), e indicador antes/después', async () => {
    const dto = await datosFixtures();
    const d = { importaciones: dto.importaciones, cuentas: dto.cuentas, importes: dto.importes, saldos: dto.saldos, otras_cuentas: dto.otras_cuentas };
    const diag = validarDiagnostico(diagnosticoCashflow(d, dto.hoy, dto.vencimientos));
    assert.equal(diag.vencimientos_leidos, dto.vencimientos.length);
    // H7-REAL-10: ALLIANCE 11–20/11: en su decena, el Excel (520) frente a sus vencimientos (472,22): el Excel.
    assert.deepEqual([diag.venc_gana_media_alliance_pio, diag.venc_gana_excel_alliance_pio, diag.venc_gana_manual_alliance_pio, diag.venc_ganan_vencimientos_alliance_pio], [0, 1, 0, 0]);
    // Excel frente a media por mayorista y cuenta, por mes: ALLIANCE PIO (noviembre: la media), HEFAME RITA (diciembre: el Excel).
    assert.deepEqual([diag.media_gana_excel_alliance_pio, diag.excel_gana_media_alliance_pio, diag.excel_gana_media_hefame_rita, diag.media_gana_excel_hefame_rita], [1, 0, 1, 0]);
    assert.ok(!('excel_gana_media_kenvue_pio' in diag)); // KENVUE no es mayorista
    // H7-REAL-10: con la comparación por mes, los vencimientos como total o como mínimo dan el mismo mes (la media del mes
    // de ALLIANCE es mayor que los dos): el indicador previsto no cambia.
    const antes = (diag.indicador_antes_prevista_negativa ? -1 : 1) * (diag.indicador_antes_prevista_eur_mes as number);
    const despues = (diag.indicador_despues_prevista_negativa ? -1 : 1) * (diag.indicador_despues_prevista_eur_mes as number);
    assert.equal(antes, despues);
    assert.equal(diag.indicador_antes_real_eur_mes, diag.indicador_despues_real_eur_mes);
    assert.ok(Object.values(diag).every((v) => typeof v === 'boolean' || (Number.isSafeInteger(v) && (v as number) >= 0) || Array.isArray(v)));
  });

  test('H7-REAL-7 check:real: diagnóstico de la previsión por cuenta y categoría (media mensual real y prevista, fuente dominante, top diferencias, solo previsión / solo real)', async () => {
    const dto = await datosFixtures();
    const d = { importaciones: dto.importaciones, cuentas: dto.cuentas, importes: dto.importes, saldos: dto.saldos, otras_cuentas: dto.otras_cuentas };
    const diag = validarDiagnostico(diagnosticoCashflow(d, dto.hoy, dto.vencimientos));
    // TPV de PIO: real 30.000 €/mes (11.000 + 10.000 + 9.000; las variaciones suman 0 por trimestre); previsto por media.
    assert.deepEqual([diag.prev_pio_re_cobro_tpv_real_eur_mes, diag.prev_pio_re_cobro_tpv_real_negativa, diag.prev_pio_re_cobro_tpv_fuente], [30000, false, ['media']]);
    assert.equal(diag.prev_pio_re_cobro_tpv_prevista_negativa, false);
    // Personal de PIO: el Excel manda (Nóminas y Seguridad Social anotadas); salidas → negativa.
    assert.deepEqual([diag.prev_pio_rs_personal_fuente, diag.prev_pio_rs_personal_real_negativa], [['excel'], true]);
    // Modelos: año anterior; robot y obra: solo previsión (ningún real en 12 meses).
    assert.deepEqual(diag.prev_pio_rs_modelo_303_fuente, ['anio_anterior']);
    assert.ok((diag.prev_pio_solo_prevision as string[]).includes('rs_inversiones'));
    // H7-REAL-10: las «no relacionadas» (sin media, sin Excel ni apunte a futuro): solo real.
    assert.deepEqual(diag.prev_pio_solo_real, ['re_no_relacionadas_con_la_farmacia', 'rs_no_relacionadas_con_la_farmacia']);
    // Top 10 por cuenta, sin repetidos y con etiquetas de categoría (nunca conceptos).
    const top = diag.prev_pio_top_diferencia as string[];
    assert.ok(top.length > 0 && top.length <= 10 && new Set(top).size === top.length && top.every((x) => `prev_pio_${x}_fuente` in diag));
    // Variación mensual por cuenta (como el indicador) y equivalencias: las 2 filas de KENVUE de PIO.
    assert.deepEqual([diag.prev_pio_variacion_real_disponible, diag.prev_rita_variacion_prevista_disponible], [true, true]);
    // H7-REAL-8: + DERMOPHARMACIE (prefijo); RITA, ambiguo (sin fusionar) y JNTL… sin coincidencia en su hoja.
    assert.deepEqual([diag.equivalencias_filas_pio, diag.equivalencias_filas_rita, diag.equivalencias_ambiguas, diag.equivalencias_sin_coincidencia], [3, 0, 1, 1]);
    // Media de 3 y de 12 meses: indicador consolidado y variación prevista por cuenta.
    for (const m of ['media3', 'media12']) {
      assert.equal(diag[`indicador_${m}_prevista_disponible`], true);
      assert.equal(typeof diag[`indicador_${m}_prevista_eur_mes`], 'number');
      for (const c of ['pio', 'rita']) assert.equal(typeof diag[`prev_${c}_variacion_prevista_${m}_negativa`], 'boolean');
    }
    assert.notEqual(diag.prev_pio_variacion_prevista_media3_eur_mes, diag.prev_pio_variacion_prevista_media12_eur_mes);
    assert.ok(!JSON.stringify(diag).includes('KENVUE') && !JSON.stringify(diag).includes('JNTL'));
    // KENVUE en los vencimientos: con y sin nombre comercial, por el nombre del proveedor.
    const v = dto.vencimientos[0];
    const k = diagnosticoCashflow(d, dto.hoy, [{ ...v, proveedor_comercial: 'KENVUE', proveedor_nombre: 'KENVUE' }, { ...v, proveedor_comercial: null, proveedor_nombre: 'Johnson & Johnson SA' }]);
    assert.deepEqual([k.kenvue_venc_con_comercial, k.kenvue_venc_sin_comercial], [1, 1]);
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
      leerReal: async () => { lecturas += 1; return { ...await leerCashflowReal(consultarSimulada(baseSimulada())), previsiones: previsionesVacias('2026-11-16') }; },
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
    registrarCashflow(vacia, { modo: 'REAL', hoy: () => '2026-11-16',
      leerReal: async () => ({ ...await leerCashflowReal(consultarSimulada(baseSimulada({ importaciones: [] }))), previsiones: previsionesVacias('2026-11-16') }),
      pantallaPagos: async () => construirPantalla(vencs, almacen.fuente(), { hoy: almacen.hoy, modo: 'REAL' }) });
    const v = (await vacia.inject({ method: 'GET', url: '/api/cashflow' })).json() as CashflowDTO;
    assert.deepEqual([v.importaciones, v.importes], [[], []]);
    assert.equal((await real.inject({ method: 'POST', url: '/api/cashflow' })).statusCode, 404);
    // REAL sin lectura: no arranca (falla cerrado).
    assert.throws(() => registrarCashflow(Fastify(), { modo: 'REAL', pantallaPagos: async () => { throw new Error('no'); } }), /CASHFLOW_REAL_SIN_LECTURA/);
  });
});
