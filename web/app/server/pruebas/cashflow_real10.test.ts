// H7-REAL-10 (decisión de Pío, 26/11/2026): sin media para lo ajeno a la farmacia, conceptos esporádicos (año anterior)
// y terminados (aviso), comparación Excel / vencimientos / apuntes frente a la estimación por concepto y MES (sin doble
// cómputo entre decenas), pagas anuales, indicador «Operativo (solo farmacia)» y diagnóstico de check:real.
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  CATEGORIAS_SIN_MEDIA, CONFIG_CASHFLOW, MESES_TERMINADO, UMBRAL_ESPORADICO_MESES, VENTANA_FRECUENCIA_MESES, calcularCashflow, finDecena, ordinalDecena,
  siguienteDecena, variacionMensual, variacionOperativa,
  type ImporteCashflow, type ResultadoCashflow, type SaldoCashflow, type VencimientoCashflow,
} from '../cashflow/cashflow.ts';
import { diagnosticoReglasPrevision } from '../cashflow/lectura_real.ts';
import { validarDiagnostico } from '../adaptador_real.ts';
import { construirPantalla, crearAlmacenPagos } from '../pagos/pagos.ts';
import { leerSemillaPagos } from '../pagos/rutas.ts';
import { crearAdaptadorFixtures } from '../adaptador_fixtures.ts';
import { leerSemillaCashflow, vencimientoCashflow } from '../cashflow/rutas.ts';

let n = 0;
const fila = (cuenta: string, d: string, categoria: string, concepto: string, importe: number | null): ImporteCashflow =>
  ({ id: `x${++n}`, importacion_id: 'i1', cuenta, farmacia: cuenta, decena_inicio: d, decena_fin: finDecena(d), categoria, concepto, importe });
const banco = (cuenta: string, d: string, s: number | null, o: Partial<SaldoCashflow> = {}): SaldoCashflow =>
  ({ id: `b${++n}`, importacion_id: 'i1', cuenta, farmacia: cuenta, decena_inicio: d, saldo_inicial: null, saldo_formulas: s, saldo_bancos: s, ...o });
const IMP = [{ importacion_id: 'i1', archivo_nombre: 'Cashflow.xlsx', origen: 'NOCHE', estado: 'OK', detalle_error: null, filas: 1, importado_at: '2026-11-25T08:00:00.000Z', vigente: true }];
const CUENTAS = [{ codigo: 'PIO', farmacia: 'PIO' }, { codigo: 'RITA', farmacia: 'RITA' }];
// Un año real (de 1–10/11/2025 a 11–20/11/2026); hoy 25/11/2026.
const SALDOS = [banco('PIO', '2025-11-01', 0, { saldo_bancos: null }), banco('PIO', '2026-11-11', 50000), banco('RITA', '2026-11-11', 0)];
const BASE = { hoy: '2026-11-25', importaciones: IMP, cuentas: CUENTAS, saldos: SALDOS, config: CONFIG_CASHFLOW };
/** Una fila en cada decena real de la posición indicada (1, 2 o 3) y de los meses que pasen el filtro. */
const reales = (categoria: string, concepto: string, importe: number, posicion: 1 | 2 | 3, mes: (ym: string) => boolean = () => true, cuenta = 'PIO') => {
  const out: ImporteCashflow[] = [];
  for (let d = '2025-11-01'; d <= '2026-11-11'; d = siguienteDecena(d)) if (ordinalDecena(d) === posicion && mes(d.slice(0, 7))) out.push(fila(cuenta, d, categoria, concepto, importe));
  return out;
};
const calcular = (importes: ImporteCashflow[], o: { vencimientos?: VencimientoCashflow[]; apuntes_manuales?: Parameters<typeof calcularCashflow>[0]['apuntes_manuales'] } = {}) =>
  calcularCashflow({ ...BASE, importes, vencimientos: o.vencimientos ?? [], apuntes_manuales: o.apuntes_manuales });
const celdas = (r: ResultadoCashflow, concepto: string, cuenta: 'PIO' | 'RITA' = 'PIO') => {
  const l = r.vistas[cuenta].lineas.find((x) => x.concepto === concepto);
  assert.ok(l, `falta ${concepto}`);
  return l.celdas;
};
const venc = (o: Partial<VencimientoCashflow>): VencimientoCashflow => ({
  vencimiento_id: 'v1', factura_id: 'f1', numero_factura: 'N1', proveedor_comercial: 'ALLIANCE', proveedor_nombre: 'ALLIANCE',
  fecha_vencimiento: '2026-12-15', importe: 100, sentido: 'CARGO', estado_pago: 'PENDIENTE', fecha_pago: null, cargo_negativo: false, ...o,
});
/** Σ de lo previsto de un concepto en un mes (lo que entra en el saldo). */
const mes = (r: ResultadoCashflow, concepto: string, ym: string, cuenta: 'PIO' | 'RITA' = 'PIO') =>
  Math.round(Object.values(celdas(r, concepto, cuenta)).filter((c) => !c.real && c.decena.startsWith(ym) && c.en_saldo).reduce((a, c) => a + (c.importe ?? 0) * 100, 0)) / 100;

describe('H7-REAL-10: constantes (único punto)', () => {
  test('CATEGORIAS_SIN_MEDIA, umbral de esporádico, ventana y meses de terminado', () => {
    assert.deepEqual([...CATEGORIAS_SIN_MEDIA], ['NO_RELACIONADA', 'TRASPASO_EXTERNO']);
    assert.deepEqual([UMBRAL_ESPORADICO_MESES, VENTANA_FRECUENCIA_MESES, MESES_TERMINADO], [3, 12, 3]);
  });
});

describe('H7-REAL-10: regla 1, categorías ajenas a la farmacia sin media', () => {
  test('«no relacionadas» y traspasos externos sin apunte ni Excel → 0 previsto; con Excel o apunte → cuenta, sin comparar con media', () => {
    const importes = [
      ...reales('RS No relacionadas con la farmacia', 'Otras salidas (no relacionadas)', 2000, 1), ...reales('RS Traspasos', 'TRASPASO A MARC', 5000, 2),
      ...reales('RE No relacionadas con la farmacia', 'Alquiler', 650, 1), ...reales('RS Gastos generales', 'Luz', 100, 1),
    ];
    const r = calcular(importes);
    for (const c of ['Otras salidas (no relacionadas)', 'TRASPASO A MARC', 'Alquiler']) assert.ok(Object.values(celdas(r, c)).every((x) => x.real), c);
    assert.equal(celdas(r, 'Luz')['2026-12-01'].importe, -100); // la farmacia, sí
    assert.deepEqual([r.vistas.PIO.decenas['2026-12-01'].no_relacionadas, r.vistas.PIO.decenas['2026-12-11'].traspasos_externos], [null, null]);
    // Con Excel (y menor que lo que daría la media): cuenta el Excel, sin «mes» ni media.
    const conExcel = calcular([...importes, fila('PIO', '2027-01-11', 'RS Traspasos', 'TRASPASO A MARC', 1200)]);
    const t = celdas(conExcel, 'TRASPASO A MARC')['2027-01-11'];
    assert.deepEqual([t.fuente, t.importe, t.media, t.mes], ['EXCEL', -1200, null, null]);
    // Con apunte manual: cuenta.
    const conApunte = calcular(importes, { apuntes_manuales: [{ cuenta: 'PIO', decena_inicio: '2027-02-01', categoria: 'RS No relacionadas con la farmacia', concepto: 'Otras salidas (no relacionadas)', importe: 300 }] });
    assert.deepEqual([celdas(conApunte, 'Otras salidas (no relacionadas)')['2027-02-01'].fuente, celdas(conApunte, 'Otras salidas (no relacionadas)')['2027-02-01'].importe], ['MANUAL', -300]);
    // Un pago único grande de hace meses ya no se reparte en la previsión (antes: 1/12 cada mes).
    const unico = calcular([fila('PIO', '2026-08-01', 'RS No relacionadas con la farmacia', 'Pago único', 66190)]);
    assert.equal(celdas(unico, 'Pago único')['2026-12-01'], undefined);
  });
});

describe('H7-REAL-10: regla 2, conceptos esporádicos (≤ 3 meses con movimiento en 12): el año anterior', () => {
  test('mismo mes y decena del año anterior; marca «año anterior»; apunte manda; con Excel o vencimientos, el mayor', () => {
    const importes = [fila('PIO', '2025-12-11', 'RS Gastos generales', 'Reparación', 900), fila('PIO', '2026-03-21', 'RS Gastos generales', 'Reparación', 6000)];
    const r = calcular(importes);
    const c = celdas(r, 'Reparación');
    assert.deepEqual([c['2026-12-11'].fuente, c['2026-12-11'].importe, c['2026-12-11'].media?.regla, c['2026-12-11'].media?.motivo, c['2026-12-11'].media?.meses_con_movimiento],
      ['MEDIA', -900, 'ANIO_ANTERIOR', 'ESPORADICO', 2]);
    assert.deepEqual(c['2026-12-11'].media?.base.map((b) => [b.clave, b.importe]), [['2025-12-11', -900]]);
    // Ningún otro mes (antes: (900 + 6.000) ÷ 12 en cada 2.ª y 3.ª decena).
    assert.deepEqual([c['2026-12-01'], c['2027-01-11'], c['2027-02-21']], [undefined, undefined, undefined]);
    assert.equal(c['2027-03-21'].importe, -6000);
    assert.deepEqual(r.prevision.PIO.esporadicos, [{ categoria: 'RS Gastos generales', concepto: 'Reparación' }]);
    // 4 meses con movimiento: frecuente (media).
    const frecuente = calcular(['2025-12-11', '2026-02-11', '2026-05-11', '2026-09-11'].map((d) => fila('PIO', d, 'RS Gastos generales', 'Reparación', 1200)));
    assert.deepEqual([celdas(frecuente, 'Reparación')['2026-12-11'].media?.regla, celdas(frecuente, 'Reparación')['2026-12-11'].importe], ['POSICION', -400]);
    // Con Excel en el mismo mes: el mayor (por mes).
    const mayor = calcular([...importes, fila('PIO', '2026-12-01', 'RS Gastos generales', 'Reparación', 1500)]);
    assert.deepEqual([mes(mayor, 'Reparación', '2026-12'), celdas(mayor, 'Reparación')['2026-12-11']], [-1500, undefined]);
    const menor = calcular([...importes, fila('PIO', '2026-12-01', 'RS Gastos generales', 'Reparación', 400)]);
    assert.deepEqual([mes(menor, 'Reparación', '2026-12'), celdas(menor, 'Reparación')['2026-12-11'].importe, celdas(menor, 'Reparación')['2026-12-01'].mes?.regla], [-900, -500, 'ANIO_ANTERIOR']);
    // Apunte manual: manda (sin año anterior ese mes).
    const ap = calcular(importes, { apuntes_manuales: [{ cuenta: 'PIO', decena_inicio: '2026-12-21', categoria: 'RS Gastos generales', concepto: 'Reparación', importe: 200 }] });
    assert.deepEqual([mes(ap, 'Reparación', '2026-12'), celdas(ap, 'Reparación')['2026-12-11'], celdas(ap, 'Reparación')['2026-12-21'].mes?.apunte], [-200, undefined, true]);
    // Vencimientos (proveedor con correspondencia, esporádico): el mayor del mes.
    const pv = [fila('PIO', '2025-12-11', 'RS Proveedores', 'ALLIANCE', 900)];
    const v = calcular(pv, { vencimientos: [venc({ fecha_vencimiento: '2026-12-25', importe: 2000 })] });
    assert.deepEqual([mes(v, 'ALLIANCE', '2026-12'), celdas(v, 'ALLIANCE')['2026-12-21'].fuente, celdas(v, 'ALLIANCE')['2026-12-11']], [-2000, 'VENCIMIENTOS', undefined]);
    const v2 = calcular(pv, { vencimientos: [venc({ fecha_vencimiento: '2026-12-25', importe: 300 })] });
    assert.deepEqual([mes(v2, 'ALLIANCE', '2026-12'), celdas(v2, 'ALLIANCE')['2026-12-11'].importe], [-900, -600]);
  });
});

describe('H7-REAL-10: regla 3, conceptos terminados', () => {
  test('frecuente (≥ 4 meses) sin movimiento en los últimos 3: sin media y aviso gris con el último movimiento; Excel, apunte o vencimiento cuentan', () => {
    const importes = [...reales('RS Gastos generales', 'Alarma antigua', 80, 2, (ym) => ym <= '2026-07'), ...reales('RS Gastos generales', 'Luz', 100, 2)];
    const r = calcular(importes);
    assert.ok(Object.values(celdas(r, 'Alarma antigua')).every((c) => c.real));
    assert.equal(celdas(r, 'Luz')['2026-12-11'].importe, -100);
    const g = r.avisos.filter((a) => a.codigo === 'CONCEPTO_TERMINADO');
    assert.deepEqual(g.map((a) => [a.tipo, a.cuenta, a.texto]), [['gris', 'PIO', 'Posible concepto terminado: Alarma antigua (último movimiento 20/07/2026)']]);
    assert.deepEqual(r.prevision.PIO.terminados, [{ categoria: 'RS Gastos generales', concepto: 'Alarma antigua', ultimo: '2026-07-20' }]);
    // Movimiento dentro de los últimos 3 meses (agosto–noviembre): no está terminado.
    const vivo = calcular(reales('RS Gastos generales', 'Alarma antigua', 80, 2, (ym) => ym <= '2026-07' || ym === '2026-09'));
    assert.deepEqual([vivo.avisos.filter((a) => a.codigo === 'CONCEPTO_TERMINADO').length, celdas(vivo, 'Alarma antigua')['2026-12-11'].fuente], [0, 'MEDIA']);
    // Con Excel: cuenta (el aviso sigue).
    const ex = calcular([...importes, fila('PIO', '2027-01-11', 'RS Gastos generales', 'Alarma antigua', 95)]);
    assert.deepEqual([celdas(ex, 'Alarma antigua')['2027-01-11'].fuente, celdas(ex, 'Alarma antigua')['2027-01-11'].importe, ex.avisos.filter((a) => a.codigo === 'CONCEPTO_TERMINADO').length], ['EXCEL', -95, 1]);
  });
});

describe('H7-REAL-10: regla 4, Excel frente a media por concepto y MES (sin doble cómputo entre decenas)', () => {
  // Concepto en la 3.ª decena (media 1.000); el Excel lo anota en la 1.ª.
  const base = reales('RS Gastos generales', 'Seguro', 1000, 3);
  test('Excel en otra decena y mayor: gana el Excel; nada de media ese mes (antes: Excel + media)', () => {
    const r = calcular([...base, fila('PIO', '2027-01-01', 'RS Gastos generales', 'Seguro', 1100)]);
    const c = celdas(r, 'Seguro');
    assert.deepEqual([c['2027-01-01'].fuente, c['2027-01-01'].importe, c['2027-01-21'], mes(r, 'Seguro', '2027-01')], ['EXCEL', -1100, undefined, -1100]);
    assert.deepEqual([c['2027-01-01'].mes?.gana, c['2027-01-01'].mes?.conocido, c['2027-01-01'].mes?.media], ['CONOCIDO', -1100, -1000]);
    // Los demás meses, su media en su decena.
    assert.deepEqual([c['2027-02-21'].importe, c['2027-02-21'].mes], [-1000, null]);
    assert.deepEqual(r.prevision.PIO.doble_computo, { casos: 1, evitado: 1000 });
  });
  test('Excel en otra decena y menor: gana la media; el Excel en su decena y la diferencia en la decena habitual de la media', () => {
    const r = calcular([...base, fila('PIO', '2027-01-01', 'RS Gastos generales', 'Seguro', 300)]);
    const c = celdas(r, 'Seguro');
    assert.deepEqual([c['2027-01-01'].fuente, c['2027-01-01'].importe, c['2027-01-21'].fuente, c['2027-01-21'].importe, c['2027-01-21'].suma_media, mes(r, 'Seguro', '2027-01')],
      ['EXCEL', -300, 'MEDIA', -700, -700, -1000]);
    assert.deepEqual([c['2027-01-21'].mes?.gana, c['2027-01-21'].mes?.diferencia, c['2027-01-21'].mes?.decena_diferencia], ['MEDIA', -700, '2027-01-21']);
    assert.deepEqual(r.prevision.PIO.doble_computo, { casos: 1, evitado: 300 });
    // El saldo previsto es la suma de las cifras (una por concepto y decena).
    const s = r.vistas.PIO.decenas;
    assert.equal(s['2027-01-21'].saldo, Math.round(((s['2027-01-11'].saldo as number) - 700) * 100) / 100);
  });
  test('Excel en la misma decena: la misma regla (gana el mayor del mes); mes sin nada conocido: la media en cada decena', () => {
    const r = calcular([...base, fila('PIO', '2027-01-21', 'RS Gastos generales', 'Seguro', 400)]);
    assert.deepEqual([celdas(r, 'Seguro')['2027-01-21'].fuente, celdas(r, 'Seguro')['2027-01-21'].importe, celdas(r, 'Seguro')['2027-01-21'].suma_media], ['EXCEL', -1000, -600]);
    assert.deepEqual(r.prevision.PIO.doble_computo, { casos: 0, evitado: 0 });
    const t = calcular(reales('RE Cobro TPV', 'TPV', 3000, 1).concat(reales('RE Cobro TPV', 'TPV', 2000, 2), reales('RE Cobro TPV', 'TPV', 1000, 3)));
    assert.deepEqual(['2027-02-01', '2027-02-11', '2027-02-21'].map((d) => celdas(t, 'TPV')[d].importe), [3000, 2000, 1000]);
  });
});

describe('H7-REAL-10: regla 5, pagas anuales sin doble cómputo', () => {
  test('paga extra (junio y diciembre) con su Excel: el mes de la paga, la paga; los demás meses, nada (antes, 1/12 cada mes además del Excel)', () => {
    const importes = [
      ...reales('RS Personal', 'Paga extra', 12000, 3, (ym) => ['2025-12', '2026-06'].includes(ym)), ...reales('RS Personal', 'Nóminas', 12000, 1),
      fila('PIO', '2026-12-11', 'RS Personal', 'Paga extra', 12000), fila('PIO', '2027-06-11', 'RS Personal', 'Paga extra', 12000),
    ];
    const r = calcular(importes);
    const meses = ['2026-12', '2027-01', '2027-02', '2027-03', '2027-04', '2027-05', '2027-06', '2027-07', '2027-08', '2027-09', '2027-10', '2027-11'];
    assert.deepEqual(meses.map((m) => mes(r, 'Paga extra', m)), [-12000, 0, 0, 0, 0, 0, -12000, 0, 0, 0, 0, 0]);
    // Excel en la 2.ª decena y el año anterior en la 3.ª: solo el Excel.
    assert.deepEqual([celdas(r, 'Paga extra')['2026-12-11'].fuente, celdas(r, 'Paga extra')['2026-12-21'], celdas(r, 'Paga extra')['2026-12-11'].mes?.regla], ['EXCEL', undefined, 'ANIO_ANTERIOR']);
    // Año previsto: 24.000 (antes: 24.000 + 10 × 2.000 de media).
    assert.equal(meses.reduce((a, m) => a + mes(r, 'Paga extra', m), 0), -24000);
    assert.deepEqual(r.prevision.PIO.esporadicos.map((x) => x.concepto), ['Paga extra']);
    assert.deepEqual(r.prevision.PIO.doble_computo, { casos: 2, evitado: 24000 });
  });
});

describe('H7-REAL-10: indicador «Operativo (solo farmacia)» y check:real', () => {
  test('Σ del cash flow generado farmacia ÷ meses, real y previsto, en los mismos tramos que la variación del saldo', () => {
    const importes = [...reales('RE Cobro TPV', 'TPV', 3000, 1), ...reales('RS No relacionadas con la farmacia', 'Retirada', 2500, 3)];
    const saldos: SaldoCashflow[] = [banco('RITA', '2026-11-11', 0)];
    for (let d = '2025-11-11', k = 0; d <= '2026-11-11'; d = siguienteDecena(d), k++) saldos.push(banco('PIO', d, Math.round(10000 + (k / 3) * 500)));
    const r = calcularCashflow({ ...BASE, saldos, importes, vencimientos: [] });
    const op = variacionOperativa(r.vistas.PIO, r.decenas);
    const v = variacionMensual(r.vistas.PIO, r.decenas);
    // Previsto: hasta el final del horizonte (8,33 meses; 8 primeras decenas con TPV).
    assert.deepEqual([op.real?.desde, op.real?.hasta, op.real?.por_mes, op.prevista?.meses, op.prevista?.por_mes], [v.real?.desde, v.real?.hasta, 3000, 8.33, 2880]);
    // El saldo real crece menos (500 €/mes) por lo ajeno; en lo previsto, sin media de lo ajeno, lo que da la farmacia.
    assert.deepEqual([v.real?.por_mes, v.prevista?.por_mes], [500, 2880]);
  });
  test('diagnóstico: operativo por cuenta, esporádicos y terminados (recuento), doble cómputo evitado y las 5 mayores cifras de cada mes previsto (sin conceptos)', async () => {
    const semilla = leerSemillaCashflow();
    const almacen = crearAlmacenPagos(leerSemillaPagos());
    const p = construirPantalla(await crearAdaptadorFixtures().vencimientos(), almacen.fuente(), { hoy: almacen.hoy, modo: 'FIXTURES' });
    const r = calcularCashflow({ ...semilla, vencimientos: p.filas.map(vencimientoCashflow) });
    const d = validarDiagnostico(diagnosticoReglasPrevision(r));
    assert.deepEqual([d.conceptos_esporadicos_pio, d.conceptos_terminados_pio, d.conceptos_esporadicos_rita, d.conceptos_terminados_rita], [4, 1, 4, 0]);
    // PIO: TPV de diciembre (3.500); RITA: paga extra de diciembre y de junio (7.000 cada una) y HEFAME de diciembre (4.000).
    assert.deepEqual([d.doble_computo_pio_casos, d.doble_computo_pio_evitado_eur_mes, d.doble_computo_pio_evitado_negativa], [1, 3500, false]);
    assert.deepEqual([d.doble_computo_rita_casos, d.doble_computo_rita_evitado_eur_mes], [3, 18000]);
    assert.deepEqual([d.operativo_pio_real_disponible, d.operativo_pio_prevista_disponible, typeof d.operativo_pio_real_eur_mes, typeof d.operativo_rita_prevista_negativa], [true, true, 'number', 'boolean']);
    // Enero de 2027 en PIO: el robot (40.000, Excel) entre las dos mayores cifras previstas, con la SOE (media).
    const cats = d.top_pio_2027_01_categorias as string[];
    const i = cats.indexOf('rs_inversiones');
    assert.ok(i >= 0 && i <= 1 && cats.slice(0, 2).includes('re_cobro_soe'), cats.join());
    assert.deepEqual([(d.top_pio_2027_01_fuentes as string[])[i], (d.top_pio_2027_01_eur as number[])[i], (d.top_pio_2027_01_sentido as string[])[i]], ['excel', 40000, 'salida']);
    // De mayor a menor en valor absoluto.
    const eur = d.top_pio_2027_01_eur as number[];
    assert.ok(eur.every((x, k) => k === 0 || x <= eur[k - 1]));
    // Meses con decenas previstas en los 12 meses tras la última real (1–10/11/2026): de noviembre de 2026 (2.ª y 3.ª
    // decena) a noviembre de 2027 (1.ª decena).
    const meses = Object.keys(d).filter((k) => /^top_pio_\d{4}_\d{2}_categorias$/.test(k)).map((k) => k.slice(8, 15));
    assert.deepEqual([meses.length, meses[0], meses[12]], [13, '2026_11', '2027_11']);
    assert.ok(Object.entries(d).filter(([k]) => k.startsWith('top_')).every(([, v]) => Array.isArray(v) && v.length <= 5));
    const texto = JSON.stringify(d);
    for (const x of ['Mantenimiento', 'Paga', 'Robot', 'KENVUE', 'TPV CaixaBank']) assert.ok(!texto.includes(x), x);
  });
});
