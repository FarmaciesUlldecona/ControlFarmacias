// H6-4 Vencimientos en calendario: agregación por día / semana / mes / año con la regla de totales de H6 (cargos −
// abonos; importe pendiente, sentido no documentado y cargos negativos fuera, contados aparte), peor estado del periodo,
// rejilla, vistas, filtro de la lista por un periodo del calendario y lista (pestañas, filtros y orden de Facturas).
// npm run test:unit
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, test } from 'node:test';
import { DIR_DTO } from '../adaptador_fixtures.ts';
import type { VencimientosDTO } from '../contrato.ts';
import {
  COLOR_DIA, GRUPOS_RESUMEN, ORDEN_PEOR, grupoResumen, agregar, claveDe, cumpleCalendario, leerFiltroCalendario, moverVista,
  periodoVista, peorEstado, rangoDe, rejillaMes, resumenAnio, resumenPeriodo, resumir, semanaIso, sinFecha, textoSinTotal,
  valorFiltroCalendario, vecinosConPagos, type FilaCalendario,
} from '../pagos/calendario.ts';
import {
  PESTANAS_VENCIMIENTOS, claveProveedor, cumpleBusquedaLista, cumpleEstadoFactura, cumpleImporte, opcionesProveedor, ordenar,
} from '../pagos/lista.ts';
import { construirPantalla, crearAlmacenPagos, totalGeneral, type FilaVencimientoPago } from '../pagos/pagos.ts';
import { leerSemillaPagos } from '../pagos/rutas.ts';

const V = (n: number) => `90000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const fila = (o: Partial<FilaCalendario>): FilaCalendario => ({ fecha_vencimiento: '2026-11-18', importe: 100, sentido: 'CARGO', estado_pago: 'PENDIENTE', forma_pago: 'TRANSFERENCIA', ...o });
/** Pantalla FIXTURES (semilla de pagos; referencia lunes 16/11/2026). */
function pantalla() {
  const dto = JSON.parse(readFileSync(join(DIR_DTO, 'vencimientos.json'), 'utf8')) as VencimientosDTO;
  return construirPantalla(dto, crearAlmacenPagos(leerSemillaPagos()).fuente(), { hoy: '2026-11-16', modo: 'FIXTURES' });
}

describe('peor estado y color del día', () => {
  test('prioridad de Marc: vencido sin pagar > domiciliado previsto > abono pendiente > pendiente > pagado', () => {
    assert.deepEqual(ORDEN_PEOR.slice(0, 4), ['VENCIDO_SIN_PAGAR', 'DOMICILIADO_PREVISTO', 'ABONO_PENDIENTE_COMPENSAR', 'PENDIENTE']);
    assert.equal(peorEstado(['PAGADO_MANUAL', 'PENDIENTE', 'DOMICILIADO_PREVISTO']), 'DOMICILIADO_PREVISTO');
    assert.equal(peorEstado(['PENDIENTE', 'VENCIDO_SIN_PAGAR', 'ABONO_PENDIENTE_COMPENSAR']), 'VENCIDO_SIN_PAGAR');
    assert.equal(peorEstado(['PAGADO_MANUAL', 'ABONO_PENDIENTE_COMPENSAR']), 'ABONO_PENDIENTE_COMPENSAR');
    assert.equal(peorEstado(['PAGADO_MANUAL', 'PENDIENTE']), 'PENDIENTE');
    assert.equal(peorEstado(['PAGADO_MANUAL', 'PAGADO_BANCO']), 'PAGADO_MANUAL');
    assert.equal(peorEstado([]), null);
    assert.deepEqual([COLOR_DIA.VENCIDO_SIN_PAGAR, COLOR_DIA.DOMICILIADO_PREVISTO, COLOR_DIA.ABONO_PENDIENTE_COMPENSAR, COLOR_DIA.PENDIENTE, COLOR_DIA.PAGADO_MANUAL, COLOR_DIA.PAGADO_BANCO],
      ['rojo', 'domiciliado', 'azul', 'neutro', 'verde', 'verde']);
  });
});

describe('agregación: misma regla de totales de H6', () => {
  test('total del día = cargos − |abonos| (también lo pagado); importe pendiente, no documentado y cargo negativo fuera, con recuento', () => {
    const r = resumir([
      fila({ importe: 300, estado_pago: 'VENCIDO_SIN_PAGAR' }),
      fila({ importe: 50, estado_pago: 'PAGADO_MANUAL' }),
      fila({ importe: -45.3, sentido: 'ABONO' }),
      fila({ importe: null }),
      fila({ importe: 288, sentido: 'NO_DOCUMENTADO' }),
      fila({ importe: -25, sentido: 'CARGO' }),
    ], '2026-11-18', 'dia');
    assert.equal(r.pagos, 6);
    assert.equal(r.total.neto, 304.7);
    assert.equal(r.total.cargos, 350);
    assert.equal(r.total.abonos, -45.3);
    assert.deepEqual([r.sin_importe, r.sentido_no_documentado, r.cargo_negativo], [1, 1, 1]);
    assert.equal(r.peor, 'VENCIDO_SIN_PAGAR');
    assert.equal(r.color, 'rojo');
    assert.deepEqual([r.desde, r.hasta], ['2026-11-18', '2026-11-18']);
  });
  test('nada suma: total null (nunca 0 inventado), pero el globo cuenta los pagos', () => {
    const r = resumir([fila({ importe: null }), fila({ importe: 10, sentido: 'NO_DOCUMENTADO' })], '2026-11-18', 'dia');
    assert.equal(r.total.neto, null);
    assert.equal(r.pagos, 2);
  });
  test('por día, semana (lunes a domingo), mes y año; sin fecha fuera del calendario y contados aparte', () => {
    const fs = [
      fila({ fecha_vencimiento: '2026-11-01', importe: 10 }), // domingo: semana del 26/10
      fila({ fecha_vencimiento: '2026-11-02', importe: 20, estado_pago: 'DOMICILIADO_PREVISTO' }),
      fila({ fecha_vencimiento: '2026-11-02', importe: -5, sentido: 'ABONO' }),
      fila({ fecha_vencimiento: '2026-12-31', importe: 7 }),
      fila({ fecha_vencimiento: null, importe: 1000 }),
    ];
    const dia = agregar(fs, 'dia');
    assert.deepEqual([...dia.keys()], ['2026-11-01', '2026-11-02', '2026-12-31']);
    assert.equal(dia.get('2026-11-02')?.total.neto, 15);
    assert.equal(dia.get('2026-11-02')?.pagos, 2);
    assert.equal(dia.get('2026-11-02')?.color, 'domiciliado');
    const sem = agregar(fs, 'semana');
    assert.deepEqual([...sem.keys()], ['2026-10-26', '2026-11-02', '2026-12-28']);
    assert.deepEqual([sem.get('2026-10-26')?.desde, sem.get('2026-10-26')?.hasta], ['2026-10-26', '2026-11-01']);
    const mes = agregar(fs, 'mes');
    assert.equal(mes.get('2026-11')?.total.neto, 25);
    assert.equal(mes.get('2026-11')?.pagos, 3);
    assert.deepEqual([mes.get('2026-11')?.desde, mes.get('2026-11')?.hasta], ['2026-11-01', '2026-11-30']);
    assert.equal(agregar(fs, 'anio').get('2026')?.total.neto, 32);
    assert.equal(sinFecha(fs), 1);
  });
  test('año: 12 meses (también vacíos) con intensidad 0–4 por |total| frente al mayor mes', () => {
    const meses = resumenAnio([
      fila({ fecha_vencimiento: '2026-03-10', importe: 1000 }),
      fila({ fecha_vencimiento: '2026-04-10', importe: 240 }),
      fila({ fecha_vencimiento: '2026-05-10', importe: -600, sentido: 'ABONO' }),
      fila({ fecha_vencimiento: '2026-06-10', importe: null }),
      fila({ fecha_vencimiento: '2025-03-10', importe: 99999 }), // otro año: no cuenta
    ], '2026');
    assert.equal(meses.length, 12);
    assert.deepEqual(meses.map((m) => m.clave).slice(0, 3), ['2026-01', '2026-02', '2026-03']);
    assert.deepEqual(meses.map((m) => m.intensidad), [0, 0, 4, 1, 3, 0, 0, 0, 0, 0, 0, 0]);
    assert.equal(meses[5].pagos, 1);
    assert.equal(meses[5].total.neto, null);
    assert.equal(meses[0].pagos, 0);
    assert.equal(meses[0].color, null);
    assert.ok(resumenAnio([], '2026').every((m) => m.intensidad === 0));
  });
});

describe('fechas, rejilla y vistas', () => {
  test('claves y rangos', () => {
    assert.equal(claveDe('2026-11-04', 'semana'), '2026-11-02');
    assert.equal(claveDe('2026-11-04', 'mes'), '2026-11');
    assert.deepEqual(rangoDe('2026-02', 'mes'), { desde: '2026-02-01', hasta: '2026-02-28' });
    assert.deepEqual(rangoDe('2028-02', 'mes'), { desde: '2028-02-01', hasta: '2028-02-29' });
    assert.deepEqual(rangoDe('2026', 'anio'), { desde: '2026-01-01', hasta: '2026-12-31' });
    assert.equal(semanaIso('2026-11-04'), 45);
    assert.equal(semanaIso('2026-01-01'), 1);
    assert.equal(semanaIso('2027-01-01'), 53);
  });
  test('rejilla del mes: semanas completas de lunes a domingo', () => {
    const nov = rejillaMes('2026-11-16');
    assert.equal(nov.length, 6); // 1/11/2026 es domingo
    assert.deepEqual([nov[0][0], nov[0][6], nov[5][0], nov[5][6]], ['2026-10-26', '2026-11-01', '2026-11-30', '2026-12-06']);
    assert.ok(nov.every((s) => s.length === 7));
    assert.equal(rejillaMes('2027-02-10').length, 4); // febrero de 2027 empieza en lunes y tiene 28 días
  });
  test('periodo de cada vista y navegación', () => {
    assert.deepEqual(periodoVista('mes', '2026-11-16'), { desde: '2026-11-01', hasta: '2026-11-30' });
    assert.deepEqual(periodoVista('semana', '2026-11-16'), { desde: '2026-11-16', hasta: '2026-11-22' });
    assert.deepEqual(periodoVista('dia', '2026-11-16'), { desde: '2026-11-16', hasta: '2026-11-16' });
    assert.equal(moverVista('mes', '2026-12-31', 1), '2027-01-01');
    assert.equal(moverVista('mes', '2026-01-31', -1), '2025-12-01');
    assert.equal(moverVista('semana', '2026-11-18', -1), '2026-11-09');
    assert.equal(moverVista('dia', '2026-11-30', 1), '2026-12-01');
    assert.equal(moverVista('anio', '2026-11-16', -1), '2025-01-01');
  });
});

describe('filtro de la lista por el calendario (?cal=)', () => {
  test('día, semana (debe ser lunes) y mes; cualquier otro valor no filtra (falla cerrado)', () => {
    assert.deepEqual(leerFiltroCalendario('dia:2026-11-04'), { escala: 'dia', clave: '2026-11-04', desde: '2026-11-04', hasta: '2026-11-04' });
    assert.deepEqual(leerFiltroCalendario('semana:2026-11-02'), { escala: 'semana', clave: '2026-11-02', desde: '2026-11-02', hasta: '2026-11-08' });
    assert.deepEqual(leerFiltroCalendario('mes:2026-11'), { escala: 'mes', clave: '2026-11', desde: '2026-11-01', hasta: '2026-11-30' });
    for (const malo of [null, '', 'dia:2026-02-30', 'semana:2026-11-04', 'mes:2026-13', 'anio:2026', 'dia:2026-11-04:x', 'dia']) {
      assert.equal(leerFiltroCalendario(malo), null, String(malo));
    }
    assert.equal(valorFiltroCalendario('semana', '2026-11-02'), 'semana:2026-11-02');
    const sem = leerFiltroCalendario('semana:2026-11-02');
    assert.equal(cumpleCalendario({ fecha_vencimiento: '2026-11-08' }, sem), true);
    assert.equal(cumpleCalendario({ fecha_vencimiento: '2026-11-09' }, sem), false);
    assert.equal(cumpleCalendario({ fecha_vencimiento: null }, sem), false);
    assert.equal(cumpleCalendario({ fecha_vencimiento: null }, null), true);
  });
});

describe('fixtures: calendario de noviembre y octubre de 2026', () => {
  const p = pantalla();
  test('04/11: dos pagos de Alliance, 304,74 €, rojo; 07/11 pagado (no documentado): verde y sin total', () => {
    const dia = agregar(p.filas, 'dia');
    const d4 = dia.get('2026-11-04');
    assert.equal(d4?.pagos, 2);
    assert.equal(d4?.total.neto, 304.74);
    assert.equal(d4?.color, 'rojo');
    assert.equal(dia.get('2026-11-07')?.color, 'verde');
    assert.equal(dia.get('2026-11-07')?.total.neto, null);
    assert.equal(dia.get('2026-11-07')?.sentido_no_documentado, 1);
    assert.equal(dia.get('2026-11-21')?.color, 'neutro'); // abono aún no vencido: pendiente
    assert.equal(dia.get('2026-11-21')?.total.neto, -45.3);
    assert.equal(dia.get('2026-10-29')?.color, 'azul'); // abono pendiente de compensar
    assert.equal(dia.get('2026-10-31')?.cargo_negativo, 1);
    assert.equal(dia.get('2026-10-31')?.total.neto, null);
  });
  test('meses y año', () => {
    const anio = resumenAnio(p.filas, '2026');
    const [oct, nov] = [anio[9], anio[10]];
    assert.deepEqual([oct.pagos, oct.total.neto, oct.cargo_negativo, oct.color], [3, 380, 1, 'domiciliado']);
    assert.deepEqual([nov.pagos, nov.total.neto, nov.sin_importe, nov.sentido_no_documentado, nov.color], [9, 881.66, 2, 2, 'rojo']);
    assert.deepEqual(anio.map((m) => m.intensidad), [0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 4, 0]);
    assert.equal(agregar(p.filas, 'semana').get('2026-11-02')?.total.neto, 304.74);
  });
});

describe('H6-5: días con pagos que no suman y resumen del periodo', () => {
  test('día con solo importes pendientes (vencido sin pagar, sin CIF): marcado igual (color y globo), total null y «importe pendiente»', () => {
    const fs = [
      fila({ fecha_vencimiento: '2026-10-20', importe: null, estado_pago: 'VENCIDO_SIN_PAGAR', forma_pago: 'SIN_DETERMINAR' }),
      fila({ fecha_vencimiento: '2026-10-20', importe: null, estado_pago: 'PENDIENTE' }),
    ];
    const r = agregar(fs, 'dia').get('2026-10-20');
    assert.ok(r);
    assert.equal(r.pagos, 2);
    assert.equal(r.color, 'rojo');
    assert.equal(r.total.neto, null);
    assert.equal(r.sin_importe, 2);
    assert.deepEqual(textoSinTotal(r), { largo: 'importe pendiente', corto: 'pend.' });
    // También la semana y el mes que lo contienen.
    assert.equal(agregar(fs, 'semana').get('2026-10-19')?.color, 'rojo');
    assert.equal(agregar(fs, 'mes').get('2026-10')?.pagos, 2);
  });
  test('solo cargos negativos o solo sentido no documentado: marcado, sin total, y dice por qué', () => {
    const neg = resumir([fila({ importe: -25, estado_pago: 'VENCIDO_SIN_PAGAR' })], '2026-11-18', 'dia');
    assert.deepEqual([neg.pagos, neg.color, neg.total.neto], [1, 'rojo', null]);
    assert.equal(textoSinTotal(neg)?.largo, 'importe negativo');
    const nd = resumir([fila({ importe: 288, sentido: 'NO_DOCUMENTADO', estado_pago: 'PAGADO_MANUAL' })], '2026-11-18', 'dia');
    assert.deepEqual([nd.pagos, nd.color, nd.total.neto], [1, 'verde', null]);
    assert.equal(textoSinTotal(nd)?.largo, 'sentido no documentado');
    // Prioridad: importe pendiente antes que el resto; con algo que suma, no hay texto.
    assert.equal(textoSinTotal(resumir([fila({ importe: null }), fila({ importe: -5 })], '2026-11-18', 'dia'))?.largo, 'importe pendiente');
    assert.equal(textoSinTotal(resumir([fila({ importe: null }), fila({ importe: 5 })], '2026-11-18', 'dia')), null);
  });
  test('resumen: Pagado + Domiciliado + Falta por pagar + Abonos = Total; fuera de totales con recuento; solo el periodo', () => {
    const fs = [
      fila({ fecha_vencimiento: '2026-11-02', importe: 100.1, estado_pago: 'PAGADO_MANUAL' }),
      fila({ fecha_vencimiento: '2026-11-03', importe: 20.2, estado_pago: 'PAGADO_BANCO' }),
      fila({ fecha_vencimiento: '2026-11-04', importe: 300.3, estado_pago: 'DOMICILIADO_PREVISTO', forma_pago: 'DOMICILIACION' }),
      fila({ fecha_vencimiento: '2026-11-05', importe: 50.05, estado_pago: 'VENCIDO_SIN_PAGAR' }),
      fila({ fecha_vencimiento: '2026-11-20', importe: 70, estado_pago: 'PENDIENTE' }),
      fila({ fecha_vencimiento: '2026-11-21', importe: -10, sentido: 'ABONO', estado_pago: 'PENDIENTE' }),
      fila({ fecha_vencimiento: '2026-11-06', importe: 45.3, sentido: 'ABONO', estado_pago: 'ABONO_PENDIENTE_COMPENSAR' }),
      fila({ fecha_vencimiento: '2026-11-07', importe: null, estado_pago: 'VENCIDO_SIN_PAGAR' }),
      fila({ fecha_vencimiento: '2026-11-08', importe: -25, estado_pago: 'VENCIDO_SIN_PAGAR' }),
      fila({ fecha_vencimiento: '2026-11-09', importe: 288, sentido: 'NO_DOCUMENTADO', estado_pago: 'PAGADO_MANUAL' }),
      fila({ fecha_vencimiento: '2026-12-01', importe: 9999 }), // otro mes
      fila({ fecha_vencimiento: null, importe: 9999 }), // sin fecha
    ];
    const r = resumenPeriodo(fs, '2026-11-01', '2026-11-30');
    assert.equal(r.pagos, 10);
    assert.equal(r.grupos.pagado.neto, 120.3);
    assert.equal(r.grupos.pagado.pagos, 3); // también el no documentado (no suma)
    assert.equal(r.grupos.domiciliado.neto, 300.3);
    assert.equal(r.grupos.falta.neto, 110.05); // 50,05 + 70 − 10
    assert.equal(r.grupos.falta.pagos, 5);
    assert.equal(r.grupos.abonos.neto, -45.3);
    assert.equal(r.total.neto, 485.35);
    assert.equal(r.cuadra, true);
    const suma = GRUPOS_RESUMEN.reduce((s, g) => s + Math.round((r.grupos[g].neto ?? 0) * 100), 0);
    assert.equal(suma, Math.round((r.total.neto ?? 0) * 100));
    assert.deepEqual([r.sin_importe, r.cargo_negativo, r.sentido_no_documentado], [1, 1, 1]);
    assert.deepEqual(GRUPOS_RESUMEN.map((g) => r.grupos[g].pagos).reduce((a, b) => a + b), r.pagos); // cada pago en un solo grupo
  });
  test('H6-6: grupos por ESTADO: un domiciliado no vencido (PENDIENTE) es «Falta por pagar»; «Domiciliado previsto», solo el ya vencido', () => {
    assert.equal(grupoResumen({ estado_pago: 'PENDIENTE' }), 'falta');
    assert.equal(grupoResumen({ estado_pago: 'VENCIDO_SIN_PAGAR' }), 'falta');
    assert.equal(grupoResumen({ estado_pago: 'DOMICILIADO_PREVISTO' }), 'domiciliado');
    assert.equal(grupoResumen({ estado_pago: 'PAGADO_MANUAL' }), 'pagado');
    assert.equal(grupoResumen({ estado_pago: 'PAGADO_BANCO' }), 'pagado');
    assert.equal(grupoResumen({ estado_pago: 'ABONO_PENDIENTE_COMPENSAR' }), 'abonos');
    const r = resumenPeriodo([
      fila({ importe: 200, estado_pago: 'PENDIENTE', forma_pago: 'DOMICILIACION' }), // domiciliado futuro: rojo
      fila({ importe: 30, estado_pago: 'PENDIENTE', forma_pago: 'TRANSFERENCIA' }),
      fila({ importe: 80, estado_pago: 'DOMICILIADO_PREVISTO', forma_pago: 'DOMICILIACION' }),
    ], '2026-11-01', '2026-11-30');
    assert.deepEqual([r.grupos.domiciliado.neto, r.grupos.falta.neto, r.total.neto, r.cuadra], [80, 230, 310, true]);
  });
  test('fixtures: el resumen del periodo y la cabecera de totales coinciden (mismos cuatro bloques, por estado)', () => {
    const p = pantalla();
    for (const mes of ['2026-10', '2026-11']) {
      const fs = p.filas.filter((f) => f.fecha_vencimiento?.startsWith(mes));
      const r = resumenPeriodo(fs, `${mes}-01`, `${mes}-31`);
      const cab = totalGeneral(fs);
      assert.deepEqual([r.grupos.pagado.neto, r.grupos.domiciliado.neto, r.grupos.falta.neto, r.grupos.abonos.neto],
        [cab.pagado.neto, cab.domiciliado.neto, cab.por_pagar.neto, cab.abonos.neto], mes);
    }
    // Noviembre: el abono domiciliado del 21 (aún no vencido) cuenta en falta por pagar; domiciliado previsto, solo el vencido.
    const nov = resumenPeriodo(p.filas, '2026-11-01', '2026-11-30');
    assert.deepEqual([nov.grupos.falta.neto, nov.grupos.domiciliado.neto, nov.total.neto, nov.cuadra], [731.66, 150, 881.66, true]);
  });
  test('resumen vacío o con solo importes pendientes: total null, nunca 0; cuadra', () => {
    const vacio = resumenPeriodo([], '2026-11-01', '2026-11-30');
    assert.deepEqual([vacio.pagos, vacio.total.neto, vacio.cuadra], [0, null, true]);
    const pend = resumenPeriodo([fila({ importe: null, estado_pago: 'VENCIDO_SIN_PAGAR' })], '2026-11-01', '2026-11-30');
    assert.deepEqual([pend.pagos, pend.total.neto, pend.grupos.falta.pagos, pend.grupos.falta.neto, pend.sin_importe, pend.cuadra], [1, null, 1, null, 1, true]);
  });
  test('periodo vacío: fechas con pagos más cercanas antes y después (sin fecha: no cuentan)', () => {
    const fs = [fila({ fecha_vencimiento: '2026-09-01' }), fila({ fecha_vencimiento: '2026-10-20' }), fila({ fecha_vencimiento: '2027-01-05' }), fila({ fecha_vencimiento: null })];
    assert.deepEqual(vecinosConPagos(fs, '2026-11-01', '2026-11-30'), { antes: '2026-10-20', despues: '2027-01-05', fuera: 3 });
    assert.deepEqual(vecinosConPagos(fs.slice(0, 2), '2026-11-01', '2026-11-30'), { antes: '2026-10-20', despues: null, fuera: 2 });
    assert.deepEqual(vecinosConPagos(fs, '2026-10-01', '2026-10-31'), { antes: '2026-09-01', despues: '2027-01-05', fuera: 2 });
  });
  test('fixtures: el resumen cuadra en cada día, semana, mes y año con pagos', () => {
    const p = pantalla();
    for (const escala of ['dia', 'semana', 'mes', 'anio'] as const) {
      for (const r of agregar(p.filas, escala).values()) {
        const res = resumenPeriodo(p.filas, r.desde, r.hasta);
        assert.equal(res.cuadra, true, `${escala} ${r.clave}`);
        assert.equal(res.total.neto, r.total.neto, `${escala} ${r.clave}`);
        assert.equal(res.pagos, r.pagos);
      }
    }
    const nov = resumenPeriodo(p.filas, '2026-11-01', '2026-11-30');
    assert.equal(nov.total.neto, 881.66);
    assert.deepEqual([nov.sin_importe, nov.sentido_no_documentado], [2, 2]);
  });
});

describe('lista: pestañas, filtros y orden de Facturas', () => {
  const p = pantalla();
  test('pestañas por el estado de la factura, como Facturas', () => {
    const n = Object.fromEntries(PESTANAS_VENCIMIENTOS.map((t) => [t.clave, p.filas.filter(t.cumple).length]));
    assert.deepEqual(n, { todas: 12, conciliadas: 6, pendientes: 5, revision: 2, 'no-revisadas': 3 });
  });
  test('proveedor por CIF (sin CIF: por nombre), sentido, importe (valor absoluto) y estado de la factura', () => {
    const ops = opcionesProveedor(p.filas);
    assert.deepEqual(ops.map((o) => [o.clave, o.vencimientos]), [['B00000003', 3], ['A00000001', 7], ['sin-cif:fedefarma', 1], ['F30004444', 1]]);
    assert.match(ops.find((o) => o.clave === 'sin-cif:fedefarma')?.texto ?? '', /\(sin CIF\)$/);
    assert.equal(p.filas.filter((f) => claveProveedor(f) === 'A00000001').length, 7);
    assert.equal(cumpleImporte(-45.3, 'hasta200'), true);
    assert.equal(cumpleImporte(null, 'hasta200'), false);
    assert.equal(cumpleImporte(null, 'sin'), true);
    assert.equal(cumpleImporte(472.22, '200a1000'), true);
    assert.equal(cumpleImporte(1000.01, 'mas1000'), true);
    assert.equal(p.filas.filter((f) => cumpleEstadoFactura(f, 'norm:REQUIERE_REVISION')).length, 1);
    assert.equal(p.filas.filter((f) => cumpleEstadoFactura(f, 'conc:CONCILIADA')).length, 6);
  });
  test('búsqueda: importe del vencimiento o total de su factura (también con «,» y «€»), además de proveedor, CIF y nº', () => {
    const q = (s: string) => p.filas.filter((f) => cumpleBusquedaLista(f, s)).map((f) => f.vencimiento_id.slice(-2)).sort();
    assert.deepEqual(q('152,37'), ['01', '10']);
    assert.deepEqual(q('45,30 €'), ['09', '12']);
    assert.deepEqual(q('568'), ['04', '05', '06', '11']); // total de la factura CF-2026-55811
    assert.deepEqual(q('fedefarma'), ['08']);
  });
  test('orden por columna: nulos al final, estable; estado por gravedad', () => {
    const ids = (fs: FilaVencimientoPago[]) => fs.map((f) => f.vencimiento_id.slice(-2));
    assert.deepEqual(ids(ordenar(p.filas, 'fecha', 'asc')), ids(p.filas));
    assert.deepEqual(ids(ordenar(p.filas, 'importe', 'desc')).slice(0, 3), ['02', '04', '03']);
    assert.deepEqual(ids(ordenar(p.filas, 'importe', 'desc')).slice(-2), ['08', '06']); // importe pendiente al final
    assert.deepEqual(ids(ordenar(p.filas, 'importe', 'asc')).slice(-2), ['08', '06']);
    assert.deepEqual(ids(ordenar(p.filas, 'estado', 'asc')).slice(0, 3), ['01', '10', '02']);
    assert.equal(ordenar(p.filas, 'estado', 'asc').at(-1)?.estado_pago, 'PAGADO_MANUAL');
    assert.equal(ordenar(p.filas, 'proveedor', 'asc')[0].proveedor_comercial, 'ALLIANCE');
    assert.equal(ordenar(p.filas, 'desconocida', null).length, 12); // columna no válida: fecha
    assert.equal(p.filas.find((f) => f.vencimiento_id === V(7))?.estado_pago, 'PAGADO_MANUAL');
  });
});
