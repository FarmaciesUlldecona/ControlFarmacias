// TA-FICHA Trabajadores: ficha anual y resumen de plantilla. Cada regla de cálculo con casos límite (derecho
// proporcional y redondeo, días naturales por periodo, medias franjas, libre disposición, permiso médico, horas y
// exceso, aviso de octubre, próximas ausencias y días de baja), la semilla de ejemplo y la API (solo lectura).
// TA-REAL-2: vacaciones del convenio (sin el dato, «pendiente»), días extra por persona y año (base + extra; editar,
// anular; farmacia de la ficha y sin columna autor, TA-REAL-2b) y completar las vacaciones del convenio. Uso: npm run test:unit
import assert from 'node:assert/strict';
import { after, describe, test } from 'node:test';
import { CLAVE_FIXTURES, USUARIO } from '../acceso.ts';
import { crearServidor } from '../index.ts';
import {
  CONVENIO_ANUAL, FUENTE_VACACIONES, VACACIONES_DIAS_NATURALES, aniosSinVacaciones, validarAjuste,
  type AjusteAnual, type ConvenioAnual, type Trabajadora,
} from '../rrhh/contrato.ts';
import { crearAdaptadorRrhhFixtures, leerSemillaAjustes, leerSemillaFichaAnual } from '../rrhh/adaptador_fixtures.ts';
import { esEscrituraRrhh } from '../rrhh/rutas.ts';
import { rangoFechas, esLaborable, type EventoCalendario, type Franja, type TipoEvento } from '../rrhh/eventos.ts';
import {
  AVISO_VACACIONES_DESDE, MAX_PROXIMAS_AUSENCIAS, REDONDEO_PROPORCIONAL, TIPOS_HORAS_COMPUTAN, anioFicha,
  calcularFichaAnual, derechoVacaciones, diasDelAnio, diasEnAlta, partirEnHoy, periodos, redondear, resumenPlantilla, valoresPorDia,
  type FichaAnual,
} from '../rrhh/ficha_anual.ts';

const ID = (n: number) => `e0000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const AINA = ID(1); const CLARA = ID(2); const NURIA = ID(3);
const LAURA = ID(11); const MARTA = ID(12); const SILVIA = ID(13); const JUDIT = ID(14); const ROSA = ID(15); const PAULA = ID(16);
const TITULAR_RITA = ID(22);
const HOY = '2026-11-13';

function ficha(o: Partial<Trabajadora> = {}): Trabajadora {
  return {
    id: 'a0000000-0000-4000-8000-000000000001', farmacia: 'PIO', nombre: 'Prueba', categoria: 'TECNICA', tipo_jornada: 'COMPLETA', horas_diarias: 8,
    computa_convenio: true, fecha_alta: '2026-01-01', fecha_baja: null, anulada: false, created_at: '', updated_at: '', activa: true, ...o,
  };
}
let nId = 0;
function ev(t: Trabajadora, fecha: string, franja: Franja, tipo: TipoEvento, o: Partial<EventoCalendario> = {}): EventoCalendario {
  const h = t.tipo_jornada === 'COMPLETA' ? (franja === 'MANANA' ? 4.5 : 3.5) : t.horas_diarias;
  return {
    id: `b0000000-0000-4000-8000-${String(++nId).padStart(12, '0')}`, farmacia: t.farmacia, trabajadora_id: t.id, fecha, franja, tipo, horas: null,
    horas_efectivas: h, estado: 'PLANIFICADO', nota: null, created_at: '', updated_at: '', ...o,
  };
}
/** Días laborables de un rango, en todas las franjas de la ficha (o en una). */
function dias(t: Trabajadora, desde: string, hasta: string, tipo: TipoEvento, o: Partial<EventoCalendario> = {}, franja?: Franja): EventoCalendario[] {
  const fr: Franja[] = franja ? [franja] : t.tipo_jornada === 'COMPLETA' ? ['MANANA', 'TARDE'] : t.tipo_jornada === 'MEDIA_MANANA' ? ['MANANA'] : ['TARDE'];
  return rangoFechas(desde, hasta).filter(esLaborable).flatMap((f) => fr.map((x) => ev(t, f, x, tipo, o)));
}
const COMPLETA = ficha();
const MEDIA = ficha({ id: 'a0000000-0000-4000-8000-000000000002', tipo_jornada: 'MEDIA_MANANA', horas_diarias: 4.5 });

describe('constantes (un único punto por regla)', () => {
  test('30 días naturales, redondeo hacia arriba, aviso desde el 1 de octubre, tipos que computan horas', () => {
    assert.equal(VACACIONES_DIAS_NATURALES, 30);
    assert.equal(FUENTE_VACACIONES, 'decisión de Pío, pendiente de texto publicado');
    assert.ok(CONVENIO_ANUAL.every((c) => c.vacaciones_dias_naturales === 30 && c.vacaciones_fuente === FUENTE_VACACIONES));
    assert.equal(REDONDEO_PROPORCIONAL, 'ENTERO_ARRIBA');
    assert.equal(AVISO_VACACIONES_DESDE, '10-01');
    assert.deepEqual([...TIPOS_HORAS_COMPUTAN], ['JORNADA', 'ASUNTOS_PROPIOS', 'PERMISO_RETRIBUIDO', 'PERMISO_MEDICO', 'BAJA', 'DESCANSO_COMPENSATORIO']);
    assert.equal(MAX_PROXIMAS_AUSENCIAS, 3);
  });
  test('años admitidos: los del convenio firmado', () => {
    assert.deepEqual(['2026', '2028', 2027].map(anioFicha), [2026, 2028, 2027]);
    for (const v of ['2025', '2029', '26', 'x', undefined, null, 2026.5]) assert.equal(anioFicha(v), null, String(v));
  });
});

describe('derecho de vacaciones (proporcional a los días en alta, entero hacia arriba)', () => {
  test('año completo: 30 días, también media jornada', () => {
    assert.equal(derechoVacaciones(COMPLETA, 2026, 30).derecho, 30);
    assert.equal(derechoVacaciones(MEDIA, 2026, 30).derecho, 30);
    assert.equal(derechoVacaciones(COMPLETA, 2026, 30).proporcional, false);
  });
  test('alta a mitad de año: 1 jul 2026 → 184 de 365 días → 15,12 → 16', () => {
    const d = derechoVacaciones(ficha({ fecha_alta: '2026-07-01' }), 2026, 30);
    assert.deepEqual([d.dias_en_alta, d.dias_anio, d.proporcional, d.derecho], [184, 365, true, 16]);
  });
  test('baja dentro del año: hasta el 31 mar → 90 días → 7,4 → 8; alta y baja el mismo año', () => {
    assert.equal(derechoVacaciones(ficha({ fecha_baja: '2026-03-31' }), 2026, 30).derecho, 8);
    assert.equal(diasEnAlta(ficha({ fecha_alta: '2026-03-01', fecha_baja: '2026-03-31' }), 2026), 31);
  });
  test('límites: un solo día → 1; múltiplo exacto (73 días = 6,0) no sube; bisiesto 2028 (366 días)', () => {
    assert.equal(derechoVacaciones(ficha({ fecha_alta: '2026-12-31' }), 2026, 30).derecho, 1);
    assert.equal(derechoVacaciones(ficha({ fecha_alta: '2026-10-20' }), 2026, 30).derecho, 6);
    assert.equal(diasDelAnio(2028), 366);
    assert.equal(derechoVacaciones(ficha({ fecha_alta: '2028-07-01' }), 2028, 30).derecho, 16); // 184/366 × 30 = 15,08
    assert.equal(derechoVacaciones(ficha({ fecha_alta: '2025-03-01' }), 2026, 30).derecho, 30); // alta anterior al año
  });
  test('sin días de alta en el año: 0 (alta posterior, baja anterior o anulada)', () => {
    assert.equal(diasEnAlta(ficha({ fecha_alta: '2027-02-01' }), 2026), 0);
    assert.equal(diasEnAlta(ficha({ fecha_alta: '2025-01-01', fecha_baja: '2025-12-31' }), 2026), 0);
    assert.equal(diasEnAlta(ficha({ anulada: true }), 2026), 0);
    assert.equal(derechoVacaciones(ficha({ fecha_alta: '2027-02-01' }), 2026, 30).derecho, 0);
  });
  test('redondeo configurable: medio día hacia arriba; base del convenio; sin base, pendiente (null)', () => {
    assert.equal(redondear(15.12, 'MEDIO_DIA_ARRIBA'), 15.5);
    assert.equal(redondear(15.5, 'MEDIO_DIA_ARRIBA'), 15.5);
    assert.equal(redondear(6.0000000001, 'ENTERO_ARRIBA'), 6); // ruido de coma flotante
    assert.equal(derechoVacaciones(ficha({ fecha_alta: '2026-07-01' }), 2026, 30, { redondeo: 'MEDIO_DIA_ARRIBA' }).derecho, 15.5);
    assert.equal(derechoVacaciones(COMPLETA, 2026, 31).derecho, 31);
    assert.equal(derechoVacaciones(COMPLETA, 2026, null).derecho, null);
    assert.equal(derechoVacaciones(ficha({ fecha_alta: '2026-07-01' }), 2026, null).derecho, null);
  });
});

describe('días naturales por periodo y medias franjas', () => {
  test('lunes a viernes de dos semanas (fin de semana dentro) = 12 días naturales', () => {
    const p = periodos(dias(COMPLETA, '2026-08-03', '2026-08-14', 'VACACIONES'), COMPLETA, 'VACACIONES');
    assert.deepEqual(p.map((x) => [x.desde, x.hasta, x.dias, x.parcial]), [['2026-08-03', '2026-08-14', 12, false]]);
  });
  test('de lunes a viernes = 5 (el fin de semana siguiente no cuenta); viernes + lunes = 4', () => {
    assert.equal(periodos(dias(COMPLETA, '2026-11-16', '2026-11-20', 'VACACIONES'), COMPLETA, 'VACACIONES')[0].dias, 5);
    const vl = [...dias(COMPLETA, '2026-11-20', '2026-11-20', 'VACACIONES'), ...dias(COMPLETA, '2026-11-23', '2026-11-23', 'VACACIONES')];
    assert.deepEqual(periodos(vl, COMPLETA, 'VACACIONES').map((x) => x.dias), [4]);
  });
  test('un día laborable sin vacaciones corta el periodo', () => {
    const e = [...dias(COMPLETA, '2026-11-16', '2026-11-16', 'VACACIONES'), ...dias(COMPLETA, '2026-11-18', '2026-11-18', 'VACACIONES')];
    assert.deepEqual(periodos(e, COMPLETA, 'VACACIONES').map((x) => x.dias), [1, 1]);
  });
  test('festivo intermedio (evento FESTIVO de la persona) no corta: cuenta como día natural', () => {
    const e = [...dias(COMPLETA, '2026-12-07', '2026-12-07', 'VACACIONES'), ...dias(COMPLETA, '2026-12-09', '2026-12-09', 'VACACIONES')];
    const f = calcularFichaAnual(COMPLETA, [...e, ev(COMPLETA, '2026-12-08', 'MANANA', 'FESTIVO')], CONVENIO_ANUAL, 2026, HOY);
    assert.deepEqual(f.vacaciones.periodos.map((x) => x.dias), [3]);
    assert.deepEqual(calcularFichaAnual(COMPLETA, e, CONVENIO_ANUAL, 2026, HOY).vacaciones.periodos.map((x) => x.dias), [1, 1]);
  });
  test('una sola franja de jornada completa = 0,5 (suelta, no une periodos); la franja única de media jornada = 1', () => {
    assert.equal(valoresPorDia([ev(COMPLETA, '2026-10-09', 'TARDE', 'VACACIONES')], COMPLETA, 'VACACIONES').get('2026-10-09'), 0.5);
    assert.equal(valoresPorDia([ev(MEDIA, '2026-10-09', 'MANANA', 'VACACIONES')], MEDIA, 'VACACIONES').get('2026-10-09'), 1);
    const e = [...dias(COMPLETA, '2026-11-16', '2026-11-16', 'VACACIONES'), ev(COMPLETA, '2026-11-17', 'MANANA', 'VACACIONES'),
      ...dias(COMPLETA, '2026-11-18', '2026-11-18', 'VACACIONES')];
    assert.deepEqual(periodos(e, COMPLETA, 'VACACIONES').map((x) => [x.dias, x.parcial]), [[1, false], [0.5, true], [1, false]]);
    // Media jornada: 5 días de su franja única = periodo de 5.
    assert.deepEqual(periodos(dias(MEDIA, '2026-09-07', '2026-09-11', 'VACACIONES'), MEDIA, 'VACACIONES').map((x) => x.dias), [5]);
  });
  test('disfrutadas hasta hoy (incluido) y planificadas desde mañana; un periodo que cruza hoy se reparte', () => {
    const p = periodos(dias(COMPLETA, '2026-08-03', '2026-08-14', 'VACACIONES'), COMPLETA, 'VACACIONES');
    assert.deepEqual(partirEnHoy(p, '2026-08-07'), { hasta_hoy: 5, desde_manana: 7 });
    assert.deepEqual(partirEnHoy(p, '2026-08-02'), { hasta_hoy: 0, desde_manana: 12 });
    assert.deepEqual(partirEnHoy(p, '2026-08-14'), { hasta_hoy: 12, desde_manana: 0 });
    assert.deepEqual(partirEnHoy([{ tipo: 'VACACIONES', desde: '2026-08-07', hasta: '2026-08-07', dias: 0.5, parcial: true }], '2026-08-07'), { hasta_hoy: 0.5, desde_manana: 0 });
  });
});

describe('ficha anual: vacaciones, libre disposición, permiso médico, horas, ausencias, baja y avisos', () => {
  test('vacaciones: derecho − disfrutadas − planificadas; por encima del derecho, aviso', () => {
    const f = calcularFichaAnual(COMPLETA, dias(COMPLETA, '2026-08-03', '2026-08-14', 'VACACIONES'), CONVENIO_ANUAL, 2026, '2026-08-07');
    assert.deepEqual([f.vacaciones.derecho, f.vacaciones.disfrutadas, f.vacaciones.planificadas, f.vacaciones.pendientes, f.vacaciones.dias_extra], [30, 5, 7, 18, 0]);
    assert.deepEqual([f.vacaciones.base, f.vacaciones.fuente, f.vacaciones.ajuste], [30, FUENTE_VACACIONES, null]);
    const mucho = calcularFichaAnual(COMPLETA, dias(COMPLETA, '2026-06-01', '2026-07-10', 'VACACIONES'), CONVENIO_ANUAL, 2026, HOY);
    assert.equal(mucho.vacaciones.pendientes, -10); // 1 jun – 10 jul = 40 días naturales
    assert.deepEqual(mucho.avisos.map((a) => a.codigo), ['VACACIONES_DE_MAS']);
    assert.equal(mucho.avisos[0].texto, '10 días de vacaciones por encima del derecho');
  });
  test('libre disposición: días del convenio del año; franja de completa 0,5; franja única de media 1; por encima, aviso', () => {
    const f = calcularFichaAnual(COMPLETA, [ev(COMPLETA, '2026-11-18', 'MANANA', 'ASUNTOS_PROPIOS')], CONVENIO_ANUAL, 2026, HOY);
    assert.deepEqual(f.libre_disposicion, { derecho: 1, usadas: 0.5, restantes: 0.5 });
    const m = calcularFichaAnual(MEDIA, [ev(MEDIA, '2026-11-18', 'MANANA', 'ASUNTOS_PROPIOS')], CONVENIO_ANUAL, 2026, HOY);
    assert.deepEqual(m.libre_disposicion, { derecho: 1, usadas: 1, restantes: 0 });
    const e27 = calcularFichaAnual(COMPLETA, dias(COMPLETA, '2027-03-03', '2027-03-03', 'ASUNTOS_PROPIOS'), CONVENIO_ANUAL, 2027, HOY);
    assert.deepEqual(e27.libre_disposicion, { derecho: 0, usadas: 1, restantes: -1 }); // 2027: 0 días en el convenio
    assert.ok(e27.avisos.some((a) => a.codigo === 'LIBRE_DISPOSICION_DE_MAS'));
  });
  test('permiso médico: horas_efectivas frente a 24 h; por encima, aviso', () => {
    const e = [...dias(COMPLETA, '2026-03-02', '2026-03-04', 'PERMISO_MEDICO'), ev(COMPLETA, '2026-03-05', 'TARDE', 'PERMISO_MEDICO')];
    const f = calcularFichaAnual(COMPLETA, e, CONVENIO_ANUAL, 2026, HOY);
    assert.deepEqual(f.permiso_medico, { horas: 24, usadas: 27.5, restantes: -3.5 });
    assert.ok(f.avisos.some((a) => a.codigo === 'PERMISO_MEDICO_DE_MAS' && a.texto === '3,5 h de permiso médico por encima del convenio'));
    const horasMano = calcularFichaAnual(COMPLETA, [ev(COMPLETA, '2026-03-02', 'MANANA', 'PERMISO_MEDICO', { horas: 2, horas_efectivas: 2 })], CONVENIO_ANUAL, 2026, HOY);
    assert.equal(horasMano.permiso_medico.usadas, 2);
  });
  test('horas: confirmadas y planificadas de los tipos que computan; pendientes = objetivo − registradas', () => {
    const conv: ConvenioAnual[] = [{ ...CONVENIO_ANUAL[0], jornada_max_horas: 100 }];
    const e = [
      ...dias(COMPLETA, '2026-02-02', '2026-02-06', 'JORNADA', { estado: 'CONFIRMADO' }), // 40 h
      ...dias(COMPLETA, '2026-02-09', '2026-02-10', 'JORNADA'), // 16 h planificadas
      ...dias(COMPLETA, '2026-02-11', '2026-02-11', 'PERMISO_MEDICO'), // 8 h: computa
      ...dias(COMPLETA, '2026-02-12', '2026-02-13', 'VACACIONES'), // no computa
      ...dias(COMPLETA, '2026-02-16', '2026-02-16', 'DESCANSO_COMPENSATORIO'), // TA-FICHA-2: 8 h, computa (cuenta como trabajado)
      ...dias(COMPLETA, '2026-02-17', '2026-02-17', 'PERMISO_NO_RETRIBUIDO'), // no computa
      ev(COMPLETA, '2026-02-21', 'MANANA', 'TURNO_GUARDIA'), // no suma horas
    ];
    const h = calcularFichaAnual(COMPLETA, e, conv, 2026, HOY).horas;
    assert.deepEqual([h.objetivo, h.confirmadas, h.planificadas, h.registradas, h.pendientes, h.exceso], [100, 40, 32, 72, 28, null]);
  });
  test('TA-FICHA-2: descanso compensatorio suma con las horas de la jornada normal (completa 4,5 + 3,5; media 4,5; confirmado o planificado)', () => {
    const conv: ConvenioAnual[] = [{ ...CONVENIO_ANUAL[0], jornada_max_horas: 100 }];
    const c = calcularFichaAnual(COMPLETA, [
      ...dias(COMPLETA, '2026-03-02', '2026-03-02', 'DESCANSO_COMPENSATORIO', { estado: 'CONFIRMADO' }),
      ev(COMPLETA, '2026-03-03', 'TARDE', 'DESCANSO_COMPENSATORIO'),
    ], conv, 2026, HOY).horas;
    assert.deepEqual([c.confirmadas, c.planificadas, c.registradas], [8, 3.5, 11.5]);
    const m = calcularFichaAnual(MEDIA, dias(MEDIA, '2026-03-02', '2026-03-03', 'DESCANSO_COMPENSATORIO'), conv, 2026, HOY).horas;
    assert.equal(m.planificadas, 9);
    // Vacaciones y permiso no retribuido siguen sin computar.
    const no = calcularFichaAnual(COMPLETA, [...dias(COMPLETA, '2026-03-02', '2026-03-02', 'VACACIONES'), ...dias(COMPLETA, '2026-03-03', '2026-03-03', 'PERMISO_NO_RETRIBUIDO')], conv, 2026, HOY).horas;
    assert.equal(no.registradas, 0);
  });
  test('exceso: «Exceso de X h ≈ Y días que podrían ser vacaciones» con Y = X / horas diarias', () => {
    const conv: ConvenioAnual[] = [{ ...CONVENIO_ANUAL[0], jornada_max_horas: 100 }];
    const f = calcularFichaAnual(COMPLETA, dias(COMPLETA, '2026-02-02', '2026-02-18', 'JORNADA'), conv, 2026, HOY); // 13 días × 8 = 104
    assert.deepEqual([f.horas.exceso, f.horas.exceso_dias, f.horas.pendientes], [4, 0.5, 0]);
    assert.ok(f.avisos.some((a) => a.texto === 'Exceso de 4 h ≈ 0,5 días que podrían ser vacaciones (estimación)'));
    // Justo en el objetivo: sin exceso.
    const justo = calcularFichaAnual(COMPLETA, dias(COMPLETA, '2026-02-02', '2026-02-13', 'JORNADA'), [{ ...conv[0], jornada_max_horas: 80 }], 2026, HOY);
    assert.deepEqual([justo.horas.exceso, justo.horas.pendientes], [null, 0]);
    // Media jornada: Y = X / 4,5.
    const m = calcularFichaAnual(MEDIA, dias(MEDIA, '2026-02-02', '2026-02-27', 'JORNADA'), [{ ...conv[0], jornada_max_horas: 100 }], 2026, HOY);
    assert.deepEqual([m.horas.objetivo, m.horas.registradas, m.horas.exceso, m.horas.exceso_dias], [56.3, 90, 33.7, 7.5]);
  });
  test('alta a mitad de año: objetivo proporcional a los días en alta (993,9 × 184/365 = 501,0)', () => {
    const f = calcularFichaAnual(ficha({ tipo_jornada: 'MEDIA_MANANA', horas_diarias: 4.5, fecha_alta: '2026-07-01' }), [], CONVENIO_ANUAL, 2026, HOY);
    assert.deepEqual([f.horas.objetivo_anual, f.horas.objetivo, f.horas.proporcional], [993.9, 501, true]);
  });
  test('titular: horas registradas sin objetivo ni exceso', () => {
    const t = ficha({ categoria: 'FARMACEUTICA_TITULAR', computa_convenio: false, tipo_jornada: 'MEDIA_MANANA', horas_diarias: 4.5 });
    const h = calcularFichaAnual(t, dias(t, '2026-02-02', '2026-02-06', 'JORNADA'), CONVENIO_ANUAL, 2026, HOY).horas;
    assert.deepEqual([h.computa, h.objetivo, h.registradas, h.pendientes, h.exceso], [false, null, 22.5, null, null]);
  });
  test('sin convenio del año: libre disposición, permiso médico y objetivo sin valor; aviso', () => {
    const f = calcularFichaAnual(COMPLETA, [], [], 2026, HOY);
    assert.deepEqual([f.convenio_anio, f.libre_disposicion.derecho, f.permiso_medico.horas, f.horas.objetivo, f.vacaciones.derecho], [false, null, null, null, null]);
    assert.deepEqual(f.avisos.map((a) => a.codigo), ['SIN_CONVENIO']);
  });
  test('TA-REAL-2: vacaciones del convenio; año sin el dato → «pendiente» (derecho y pendientes null), aviso y sin aviso de octubre', () => {
    const sin: ConvenioAnual[] = [{ ...CONVENIO_ANUAL[0], vacaciones_dias_naturales: null, vacaciones_fuente: null }];
    const f = calcularFichaAnual(COMPLETA, dias(COMPLETA, '2026-08-03', '2026-08-07', 'VACACIONES'), sin, 2026, HOY);
    assert.deepEqual([f.vacaciones.base, f.vacaciones.derecho_base, f.vacaciones.derecho, f.vacaciones.pendientes, f.vacaciones.disfrutadas], [null, null, null, null, 5]);
    assert.deepEqual(f.avisos.map((a) => [a.codigo, a.texto]), [['VACACIONES_SIN_DATO', 'Vacaciones de 2026 pendientes: el convenio no tiene los días']]);
    // Otro valor del convenio: se usa tal cual.
    assert.equal(calcularFichaAnual(COMPLETA, [], [{ ...CONVENIO_ANUAL[0], vacaciones_dias_naturales: 31 }], 2026, HOY).vacaciones.derecho, 31);
    assert.deepEqual(aniosSinVacaciones([...sin, CONVENIO_ANUAL[1]]), [2026]);
  });
  test('TA-REAL-2: días extra (ajuste no anulado de la persona y el año): derecho = base (proporcional) + extra', () => {
    const aj = (o: Partial<AjusteAnual>): AjusteAnual => ({ id: 'c1', trabajadora_id: COMPLETA.id, farmacia: 'PIO', anio: 2026, vacaciones_dias_extra: 3, nota: 'x', anulada: false, ...o });
    const f = calcularFichaAnual(COMPLETA, dias(COMPLETA, '2026-08-03', '2026-08-14', 'VACACIONES'), CONVENIO_ANUAL, 2026, HOY, { ajustes: [aj({})] });
    assert.deepEqual([f.vacaciones.derecho_base, f.vacaciones.dias_extra, f.vacaciones.derecho, f.vacaciones.pendientes, f.vacaciones.ajuste?.nota], [30, 3, 33, 21, 'x']);
    // Alta a mitad de año: 16 proporcionales + 2 extra (el extra no se prorratea).
    const p = calcularFichaAnual(ficha({ fecha_alta: '2026-07-01' }), [], CONVENIO_ANUAL, 2026, HOY, { ajustes: [aj({ vacaciones_dias_extra: 2 })] });
    assert.deepEqual([p.vacaciones.derecho_base, p.vacaciones.derecho], [16, 18]);
    // Anulado, de otro año o de otra persona: no cuenta.
    for (const o of [{ anulada: true }, { anio: 2027 }, { trabajadora_id: 'otra' }]) {
      assert.equal(calcularFichaAnual(COMPLETA, [], CONVENIO_ANUAL, 2026, HOY, { ajustes: [aj(o)] }).vacaciones.derecho, 30, JSON.stringify(o));
    }
    // Sin el dato del convenio: el derecho sigue pendiente aunque haya extra.
    const sin = calcularFichaAnual(COMPLETA, [], [{ ...CONVENIO_ANUAL[0], vacaciones_dias_naturales: null, vacaciones_fuente: null }], 2026, HOY, { ajustes: [aj({})] });
    assert.deepEqual([sin.vacaciones.derecho, sin.vacaciones.dias_extra], [null, 3]);
  });
  test('TA-REAL-2: validación de los días extra (entero de 0 a 365, nota opcional ≤ 200; nada más)', () => {
    assert.deepEqual(validarAjuste({ vacaciones_dias_extra: 0 }), { ok: true, dias: 0, nota: null });
    assert.deepEqual(validarAjuste({ vacaciones_dias_extra: 2, nota: '  Acuerdo   x ' }), { ok: true, dias: 2, nota: 'Acuerdo x' });
    assert.deepEqual(validarAjuste({ vacaciones_dias_extra: 2, nota: '   ' }), { ok: true, dias: 2, nota: null });
    for (const b of [{ vacaciones_dias_extra: -1 }, { vacaciones_dias_extra: 1.5 }, { vacaciones_dias_extra: '2' }, { vacaciones_dias_extra: 366 }, {},
      { vacaciones_dias_extra: 1, nota: 'x'.repeat(201) }, { vacaciones_dias_extra: 1, nota: '<b>' }, { vacaciones_dias_extra: 1, autor: 'otro' }, null, []]) {
      assert.equal(validarAjuste(b).ok, false, JSON.stringify(b));
    }
  });
  test('aviso de octubre: desde el 1 de octubre del año (configurable), solo dentro del año y si quedan días', () => {
    const cod = (hoy: string, anio = 2026, o = {}) => calcularFichaAnual(COMPLETA, [], CONVENIO_ANUAL, anio, hoy, o).avisos.map((a) => a.codigo);
    assert.deepEqual(cod('2026-09-30'), []);
    assert.deepEqual(cod('2026-10-01'), ['VACACIONES_SIN_PLANIFICAR']);
    assert.deepEqual(cod('2026-12-31'), ['VACACIONES_SIN_PLANIFICAR']);
    assert.deepEqual(cod('2027-01-10'), []); // año pasado
    assert.deepEqual(cod(HOY, 2027), []); // año que viene
    assert.deepEqual(cod(HOY, 2026, { avisoDesde: '11-15' }), []);
    assert.equal(calcularFichaAnual(COMPLETA, [], CONVENIO_ANUAL, 2026, HOY).avisos[0].texto, 'Quedan 30 días de vacaciones sin planificar');
    const todo = calcularFichaAnual(COMPLETA, dias(COMPLETA, '2026-07-06', '2026-08-04', 'VACACIONES'), CONVENIO_ANUAL, 2026, HOY);
    assert.deepEqual([todo.vacaciones.pendientes, todo.avisos.length], [0, 0]);
  });
  test('próximas 3 ausencias desde hoy (incluida la que está en curso), ordenadas; jornada y guardia no son ausencia', () => {
    const e = [
      ...dias(COMPLETA, '2026-11-02', '2026-11-04', 'VACACIONES'), // pasada
      ...dias(COMPLETA, '2026-11-12', '2026-11-16', 'BAJA'), // en curso
      ev(COMPLETA, '2026-11-24', 'TARDE', 'PERMISO_MEDICO'),
      ...dias(COMPLETA, '2026-11-20', '2026-11-20', 'JORNADA'),
      ev(COMPLETA, '2026-11-21', 'MANANA', 'TURNO_GUARDIA'),
      ...dias(COMPLETA, '2026-12-01', '2026-12-01', 'ASUNTOS_PROPIOS'),
      ...dias(COMPLETA, '2026-12-21', '2026-12-24', 'VACACIONES'),
    ];
    const f = calcularFichaAnual(COMPLETA, e, CONVENIO_ANUAL, 2026, HOY);
    assert.deepEqual(f.proximas_ausencias.map((p) => [p.tipo, p.desde, p.hasta, p.dias]),
      [['BAJA', '2026-11-12', '2026-11-16', 5], ['PERMISO_MEDICO', '2026-11-24', '2026-11-24', 0.5], ['ASUNTOS_PROPIOS', '2026-12-01', '2026-12-01', 1]]);
    assert.equal(f.dias_baja, 5);
  });
  test('días de baja: días naturales del periodo (jueves a martes = 6); solo el número', () => {
    const f = calcularFichaAnual(COMPLETA, dias(COMPLETA, '2026-03-12', '2026-03-17', 'BAJA'), CONVENIO_ANUAL, 2026, HOY);
    assert.equal(f.dias_baja, 6);
    assert.ok(!JSON.stringify(f).includes('motivo'));
  });
  test('solo cuenta el año pedido y la persona de la ficha', () => {
    const otra = ficha({ id: 'a0000000-0000-4000-8000-000000000009' });
    const e = [...dias(COMPLETA, '2027-02-01', '2027-02-05', 'VACACIONES'), ...dias(otra, '2026-02-02', '2026-02-06', 'VACACIONES')];
    assert.equal(calcularFichaAnual(COMPLETA, e, CONVENIO_ANUAL, 2026, HOY).vacaciones.pendientes, 30);
  });
});

describe('semilla de ejemplo (fixtures/rrhh/ficha_anual.json) y resumen de plantilla', () => {
  const a = crearAdaptadorRrhhFixtures({ anioReferencia: 2026 });
  const cal = a.calendario('AMBAS', '2026-01-01', '2026-12-31');
  const filas = resumenPlantilla(cal.trabajadoras, cal.eventos, a.convenio(), 2026, HOY, { ajustes: a.ajustes('AMBAS', 2026) });
  const de = (id: string) => filas.find((f) => f.trabajadora.id === id) as FichaAnual;
  const cods = (id: string) => de(id).avisos.map((x) => x.codigo);

  test('semilla: solo RITA y fuera de noviembre (la semana de TA2 no cambia)', () => {
    const s = leerSemillaFichaAnual();
    assert.ok([...s.ausencias, ...s.jornada_extra].every((x) => x.trabajadora_id.startsWith('e0000000-0000-4000-8000-00000000001')
      && !x.desde.startsWith('2026-11') && !x.hasta.startsWith('2026-11')));
  });
  test('13 filas (todas las fichas de alta en 2026), en el orden de las fichas', () => {
    assert.equal(filas.length, 13);
    assert.equal(resumenPlantilla(cal.trabajadoras, cal.eventos, a.convenio(), 2026, HOY).filter((f) => f.trabajadora.farmacia === 'RITA').length, 8);
  });
  test('Laura: 30 días planificados (6 jul – 4 ago) → 0 pendientes, sin aviso; permiso médico 8 h de 24', () => {
    assert.deepEqual([de(LAURA).vacaciones.disfrutadas, de(LAURA).vacaciones.pendientes], [30, 0]);
    assert.deepEqual(cods(LAURA), []);
    assert.deepEqual(de(LAURA).permiso_medico, { horas: 24, usadas: 8, restantes: 16 });
  });
  test('Sílvia: 3–14 ago (fin de semana dentro, 12) + media franja 9 oct (0,5) + 23–27 nov (5) → 12,5 disfrutadas, 5 planificadas, 12,5 pendientes, aviso', () => {
    const v = de(SILVIA).vacaciones;
    assert.deepEqual([v.disfrutadas, v.planificadas, v.pendientes], [12.5, 5, 12.5]);
    assert.deepEqual(cods(SILVIA), ['VACACIONES_SIN_PLANIFICAR']);
  });
  test('Paula: alta 1 jul, media jornada → derecho 16; 7–11 sep de su franja única = 5 días; objetivo 501 h', () => {
    const f = de(PAULA);
    assert.deepEqual([f.vacaciones.derecho, f.vacaciones.proporcional, f.vacaciones.disfrutadas, f.vacaciones.pendientes, f.horas.objetivo], [16, true, 5, 11, 501]);
  });
  test('Judit: jornada confirmada ene–oct + descanso compensatorio del 6 nov (8 h, TA-FICHA-2) → 1776 h confirmadas + 120 planificadas = exceso de 129 h ≈ 16,1 días', () => {
    const h = de(JUDIT).horas;
    assert.deepEqual([h.objetivo, h.confirmadas, h.planificadas, h.exceso, h.exceso_dias], [1767, 1776, 120, 129, 16.1]);
    assert.deepEqual(cods(JUDIT), ['VACACIONES_SIN_PLANIFICAR', 'EXCESO_HORAS']);
  });
  test('Marta: bajas 12–17 mar (6) y 9–13 nov (5) = 11 días', () => assert.equal(de(MARTA).dias_baja, 11));
  test('libre disposición: Clara 1 de 1; Rosa media franja 0,5 de 1; permiso médico de Núria 3,5 h (tarde)', () => {
    assert.deepEqual(de(CLARA).libre_disposicion, { derecho: 1, usadas: 1, restantes: 0 });
    assert.deepEqual(de(ROSA).libre_disposicion, { derecho: 1, usadas: 0.5, restantes: 0.5 });
    assert.equal(de(NURIA).permiso_medico.usadas, 3.5);
  });
  test('TA-REAL-2: Rosa 2 días extra (30 + 2 = 32, sin vacaciones: 32 pendientes); Clara, ajuste anulado: 30; vacaciones anuladas de Rosa no cuentan', () => {
    assert.deepEqual([de(ROSA).vacaciones.dias_extra, de(ROSA).vacaciones.derecho, de(ROSA).vacaciones.pendientes, de(ROSA).vacaciones.disfrutadas], [2, 32, 32, 0]);
    assert.equal(de(ROSA).vacaciones.ajuste?.nota, 'Acuerdo de ejemplo por antigüedad');
    assert.deepEqual([de(CLARA).vacaciones.dias_extra, de(CLARA).vacaciones.derecho, de(CLARA).vacaciones.ajuste], [0, 30, null]);
    const s = leerSemillaAjustes();
    assert.deepEqual(s.map((x) => [x.trabajadora_id, x.anio, x.vacaciones_dias_extra, x.anulada]), [[ROSA, 2026, 2, false], [CLARA, 2026, 3, true]]);
    assert.deepEqual(a.ajustes('PIO', 2026), []); // el de Clara está anulado
  });
  test('Aina: 16–20 nov planificadas (5) → 25 pendientes; próxima ausencia sus vacaciones', () => {
    assert.deepEqual([de(AINA).vacaciones.planificadas, de(AINA).vacaciones.pendientes], [5, 25]);
    assert.deepEqual(de(AINA).proximas_ausencias.map((p) => [p.tipo, p.desde, p.hasta]), [['VACACIONES', '2026-11-16', '2026-11-20']]);
  });
  test('titular: sin objetivo; 2027 sin eventos: 30 pendientes y sin aviso de octubre (aún no es octubre de 2027)', () => {
    assert.equal(de(TITULAR_RITA).horas.objetivo, null);
    const f27 = resumenPlantilla(cal.trabajadoras, [], a.convenio(), 2027, HOY);
    assert.ok(f27.every((f) => f.vacaciones.pendientes === 30 && f.avisos.length === 0));
  });
});

describe('API /api/rrhh/fichas y /api/rrhh/trabajadoras/:id/anual (solo lectura)', async () => {
  const app = await crearServidor('FIXTURES');
  after(() => app.close());
  const H = { host: '127.0.0.1:4747' };
  const ORIGEN = { origin: 'http://127.0.0.1:4747', 'content-type': 'application/json' };
  const login = await app.inject({
    method: 'POST', url: '/api/login', headers: { ...H, 'content-type': 'application/x-www-form-urlencoded' },
    payload: new URLSearchParams({ usuario: USUARIO, clave: CLAVE_FIXTURES, destino: '/' }).toString(),
  });
  const cookie = String(login.headers['set-cookie']).split(';')[0];
  const get = (url: string, con = true) => app.inject({ method: 'GET', url, headers: con ? { ...H, cookie } : H });

  test('resumen: sesión obligatoria; farmacia, año (2026–2028) y hoy validados; nunca escritura', async () => {
    assert.equal((await get('/api/rrhh/fichas?anio=2026', false)).statusCode, 401);
    const r = await get('/api/rrhh/fichas?farmacia=RITA&anio=2026&hoy=2026-11-13');
    assert.equal(r.statusCode, 200);
    const d = r.json();
    assert.deepEqual([d.farmacia, d.anio, d.hoy, d.filas.length, d.reglas.vacaciones_dias, d.reglas.aviso_desde], ['RITA', 2026, '2026-11-13', 8, 30, '10-01']);
    for (const q of ['farmacia=X', 'anio=2025', 'anio=2029', 'anio=abc', 'hoy=13/11/2026', 'hoy=2026-02-30']) {
      assert.equal((await get(`/api/rrhh/fichas?${q}`)).statusCode, 400, q);
    }
    assert.equal((await get('/api/rrhh/fichas?hoy=2027-03-01')).json().anio, 2027); // por defecto, el año de hoy
    assert.equal((await get('/api/rrhh/fichas?hoy=2030-03-01')).json().anio, 2028); // fuera del convenio: el extremo
    const post = await app.inject({ method: 'POST', url: '/api/rrhh/fichas', headers: { ...H, cookie, ...ORIGEN }, payload: {} });
    assert.equal(post.statusCode, 405);
  });
  test('ficha anual: por id y año; 404 si no existe; sin alta en el año y anulada, sin ficha y con motivo', async () => {
    const r = await get(`/api/rrhh/trabajadoras/${JUDIT}/anual?anio=2026&hoy=2026-11-13`);
    assert.equal(r.statusCode, 200);
    assert.equal(r.json().ficha.horas.exceso, 129);
    assert.equal((await get(`/api/rrhh/trabajadoras/${PAULA}/anual?anio=2027&hoy=2026-11-13`)).json().ficha.vacaciones.derecho, 30);
    assert.equal((await get('/api/rrhh/trabajadoras/f0000000-0000-4000-8000-000000000999/anual')).statusCode, 404);
    assert.equal((await get('/api/rrhh/trabajadoras/no-es-un-id/anual')).statusCode, 400);
    assert.equal((await get(`/api/rrhh/trabajadoras/${JUDIT}/anual?anio=2025`)).statusCode, 400);
    const nueva = await app.inject({ method: 'POST', url: '/api/rrhh/trabajadoras', headers: { ...H, cookie, ...ORIGEN },
      payload: { farmacia: 'RITA', nombre: 'Alta en 2027', categoria: 'AUXILIAR', tipo_jornada: 'COMPLETA', horas_diarias: 8, fecha_alta: '2027-03-01' } });
    const id = nueva.json().id as string;
    assert.deepEqual((await get(`/api/rrhh/trabajadoras/${id}/anual?anio=2026`)).json().motivo, 'SIN_ALTA_EN_EL_ANIO');
    assert.equal((await get(`/api/rrhh/trabajadoras/${id}/anual?anio=2027&hoy=2026-11-13`)).json().ficha.vacaciones.derecho, 26); // 306/365 × 30 = 25,15 → 26
    await app.inject({ method: 'PUT', url: `/api/rrhh/trabajadoras/${id}/anular`, headers: { ...H, cookie, ...ORIGEN }, payload: { confirmar: true } });
    const an = (await get(`/api/rrhh/trabajadoras/${id}/anual?anio=2027`)).json();
    assert.deepEqual([an.ficha, an.motivo], [null, 'ANULADA']);
    // TA-REAL-2: días extra de una ficha anulada o sin alta en el año: 409.
    const put = (tid: string, anio: number | string, payload: unknown) =>
      app.inject({ method: 'PUT', url: `/api/rrhh/trabajadoras/${tid}/ajustes/${anio}`, headers: { ...H, cookie, ...ORIGEN }, payload: payload as object });
    assert.deepEqual([(await put(id, 2027, { vacaciones_dias_extra: 1 })).statusCode, (await put(id, 2027, { vacaciones_dias_extra: 1 })).json().error], [409, 'TRABAJADORA_ANULADA']);
    assert.equal((await put(PAULA, 2026, { vacaciones_dias_extra: 1 })).statusCode, 200);
  });
  test('TA-REAL-2: días extra por API: guardar (farmacia de la ficha, sin columna autor), editar, la ficha suma base + extra, anular con confirmación', async () => {
    const url = `/api/rrhh/trabajadoras/${LAURA}/ajustes/2026`;
    const put = (u: string, payload: unknown, h: Record<string, string> = { ...H, cookie, ...ORIGEN }) => app.inject({ method: 'PUT', url: u, headers: h, payload: payload as object });
    assert.equal(esEscrituraRrhh('PUT', url), true);
    assert.equal(esEscrituraRrhh('PUT', `${url}/anular`), true);
    assert.equal(esEscrituraRrhh('POST', url), false);
    assert.equal(esEscrituraRrhh('DELETE', url), false);
    assert.equal((await put(url, { vacaciones_dias_extra: 1 }, { ...H, cookie })).statusCode, 403); // sin Origin
    assert.equal((await put(url, { vacaciones_dias_extra: -1 })).statusCode, 400);
    assert.equal((await put(`/api/rrhh/trabajadoras/${LAURA}/ajustes/2025`, { vacaciones_dias_extra: 1 })).statusCode, 400);
    assert.equal((await put(`${url}/anular`, { confirmar: true })).json().error, 'SIN_AJUSTE');
    const g = await put(url, { vacaciones_dias_extra: 3, nota: 'Acuerdo' });
    assert.equal(g.statusCode, 200);
    assert.deepEqual([g.json().vacaciones_dias_extra, g.json().nota, g.json().farmacia, g.json().anulada], [3, 'Acuerdo', 'RITA', false]);
    assert.ok(!('autor' in g.json()));
    const e = await put(url, { vacaciones_dias_extra: 4, nota: null });
    assert.equal(e.json().id, g.json().id); // un único ajuste no anulado: se actualiza
    const f = (await get(`/api/rrhh/trabajadoras/${LAURA}/anual?anio=2026&hoy=2026-11-13`)).json().ficha.vacaciones;
    assert.deepEqual([f.derecho_base, f.dias_extra, f.derecho, f.pendientes], [30, 4, 34, 4]);
    const fila = (await get('/api/rrhh/fichas?farmacia=RITA&anio=2026&hoy=2026-11-13')).json().filas.find((x: FichaAnual) => x.trabajadora.id === LAURA);
    assert.equal(fila.vacaciones.derecho, 34);
    assert.equal((await put(`${url}/anular`, {})).statusCode, 400); // sin confirmación
    const an = await put(`${url}/anular`, { confirmar: true });
    assert.deepEqual([an.statusCode, an.json().anulada], [200, true]);
    assert.equal((await get(`/api/rrhh/trabajadoras/${LAURA}/anual?anio=2026&hoy=2026-11-13`)).json().ficha.vacaciones.derecho, 30);
  });
  test('TA-REAL-2: completar vacaciones del convenio: solo los años sin el dato y solo esos dos campos', async () => {
    const a = crearAdaptadorRrhhFixtures({ convenio: [{ ...CONVENIO_ANUAL[0], vacaciones_dias_naturales: null, vacaciones_fuente: null }, CONVENIO_ANUAL[1]] });
    const hechos = a.completarVacacionesConvenio([2026, 2027], 'Marc');
    assert.deepEqual(hechos.map((c) => [c.anio, c.vacaciones_dias_naturales, c.vacaciones_fuente]), [[2026, 30, FUENTE_VACACIONES]]);
    assert.deepEqual(a.convenio()[0], { ...CONVENIO_ANUAL[0] }); // el resto, igual
    assert.deepEqual(a.completarVacacionesConvenio([2026], 'Marc'), []); // ya completo
    const r = await app.inject({ method: 'POST', url: '/api/rrhh/convenio/vacaciones', headers: { ...H, cookie, ...ORIGEN }, payload: { anios: [2026] } });
    assert.deepEqual([r.statusCode, r.json().completados], [200, []]); // FIXTURES ya tiene los tres años completos
    assert.equal((await app.inject({ method: 'POST', url: '/api/rrhh/convenio/vacaciones', headers: { ...H, cookie, ...ORIGEN }, payload: { anios: [2030] } })).statusCode, 400);
    assert.equal(esEscrituraRrhh('POST', '/api/rrhh/convenio/vacaciones'), true);
  });
});
