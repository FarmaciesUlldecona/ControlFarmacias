// TA2/TA2-2/TA2-4 Trabajadores: calendario. Fechas, semilla de ejemplo, validación, eventos por franja (mañana / tarde),
// pintar, goma, rellenar jornada habitual (semana, mes y año), confirmar, editar horas y nota, deshacer e historial
// (autor "Marc"); API con el servidor FIXTURES (inyección). Uso: npm run test:unit
import assert from 'node:assert/strict';
import { after, describe, test } from 'node:test';
import { CLAVE_FIXTURES, USUARIO } from '../acceso.ts';
import { crearServidor } from '../index.ts';
import { AUTOR_HISTORIAL, FRANJA_JORNADA, HORARIO_COMPLETA, HORAS_COMPLETA } from '../rrhh/contrato.ts';
import { crearAdaptadorRrhhFixtures, leerSemillaEventos, type AdaptadorRrhh } from '../rrhh/adaptador_fixtures.ts';
import {
  AVISO_NOTA, AVISO_NOTA_VACIA, describirCambio, diaSemana, esFecha, esLaborable, horasFranja, leerNota, lunesDe, rangoFechas, sumarMeses, textoPeriodoCambio, ultimoDeMes,
  validarDeshacer, validarPeticionEventos,
  type EventoCalendario, type Franja, type PeticionEventos, type ResultadoCambioDTO,
} from '../rrhh/eventos.ts';

const ID = (n: number) => `e0000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const AINA = ID(1); const CLARA = ID(2); const NURIA = ID(3); const ELENA = ID(4);
const MARTA = ID(12); const JUDIT = ID(14); const ROSA = ID(15); const IRENE = ID(17); const TITULAR_PIO = ID(21);
/** Orden del calendario: por nombre, titular al final. */
const PIO = [AINA, CLARA, ELENA, NURIA, TITULAR_PIO];

function nuevo(): AdaptadorRrhh {
  let n = 0; let t = 0;
  return crearAdaptadorRrhhFixtures({
    nuevoId: () => `f2000000-0000-4000-8000-${String(++n).padStart(12, '0')}`,
    ahora: () => new Date(Date.UTC(2026, 10, 12, 10, 0, 0, t++)).toISOString(),
  });
}
/** Aplica una petición ya validada (como la API). */
function aplicar(a: AdaptadorRrhh, cuerpo: unknown): ResultadoCambioDTO | string {
  const v = validarPeticionEventos(cuerpo);
  assert.ok(v.ok, JSON.stringify(v));
  return a.cambiarEventos((v as { peticion: PeticionEventos }).peticion, AUTOR_HISTORIAL);
}
const ok = (r: ResultadoCambioDTO | string): ResultadoCambioDTO => { assert.equal(typeof r, 'object', String(r)); return r as ResultadoCambioDTO; };
const en = (a: AdaptadorRrhh, tid: string, fecha: string, franja: Franja): EventoCalendario | undefined =>
  a.eventos().find((e) => e.trabajadora_id === tid && e.fecha === fecha && e.franja === franja);
const delDia = (a: AdaptadorRrhh, tid: string, fecha: string) => a.eventos().filter((e) => e.trabajadora_id === tid && e.fecha === fecha)
  .sort((x, y) => x.franja.localeCompare(y.franja)).map((e) => [e.franja, e.tipo]);
const celdas = (tid: string, desde: string, hasta: string, franja?: Franja) => rangoFechas(desde, hasta).map((fecha) => ({ trabajadora_id: tid, fecha, ...(franja ? { franja } : {}) }));
const foto = (a: AdaptadorRrhh) => JSON.stringify(a.eventos().sort((x, y) => x.id.localeCompare(y.id)));

describe('fechas (UTC, lunes = 0)', () => {
  test('semana, mes y validez', () => {
    assert.equal(lunesDe('2026-11-12'), '2026-11-09');
    assert.equal(lunesDe('2026-11-15'), '2026-11-09');
    assert.deepEqual(['2026-11-09', '2026-11-13', '2026-11-14', '2026-11-15'].map(diaSemana), [0, 4, 5, 6]);
    assert.deepEqual(['2026-11-13', '2026-11-14'].map(esLaborable), [true, false]);
    assert.equal(sumarMeses('2026-12-01', 1), '2027-01-01');
    assert.equal(sumarMeses('2026-01-01', -1), '2025-12-01');
    assert.equal(ultimoDeMes('2028-02-10'), '2028-02-29');
    assert.equal(rangoFechas('2026-10-24', '2026-10-26').length, 3); // cambio de hora: sin huecos ni duplicados
    for (const f of ['2026-02-30', '2026-1-01', '', null, 20261101]) assert.equal(esFecha(f), false, String(f));
  });
  test('TA2-3: horas por franja: completa = mañana 4,5 h (9:00–13:30) + tarde 3,5 h (17:00–20:30); media jornada, todas en su franja', () => {
    assert.equal(horasFranja({ jornada: 'COMPLETA', horas_diarias: 8 }, 'MANANA'), 4.5);
    assert.equal(horasFranja({ jornada: 'COMPLETA', horas_diarias: 8 }, 'TARDE'), 3.5);
    assert.equal(horasFranja({ jornada: 'MEDIA_MANANA', horas_diarias: 4.5 }, 'MANANA'), 4.5);
    assert.equal(horasFranja({ jornada: 'MEDIA_TARDE', horas_diarias: 3.5 }, 'TARDE'), 3.5);
    assert.equal(horasFranja({ jornada: 'MEDIA_MANANA', horas_diarias: 5 }, 'MANANA'), 5); // media editada: sus horas
    // Único punto de configuración, con la suma comprobada.
    assert.deepEqual(HORARIO_COMPLETA, { MANANA: { horas: 4.5, desde: '9:00', hasta: '13:30' }, TARDE: { horas: 3.5, desde: '17:00', hasta: '20:30' } });
    assert.equal(HORARIO_COMPLETA.MANANA.horas + HORARIO_COMPLETA.TARDE.horas, HORAS_COMPLETA);
    assert.equal(FRANJA_JORNADA.COMPLETA, 'de lunes a viernes, 9:00–13:30 y 17:00–20:30');
  });
});

describe('semilla de ejemplo (fixtures/rrhh/eventos.json)', () => {
  const a = nuevo();
  const evs = a.eventos();
  test('noviembre 2026: 21 franjas por día (8 completas × 2 + 5 medias) × 20 laborables = 420; nada en fin de semana', () => {
    assert.equal(evs.length, 420);
    assert.equal(evs.filter((e) => e.tipo !== 'JORNADA').length, 41);
    assert.equal(new Set(evs.filter((e) => e.tipo !== 'JORNADA').map((e) => `${e.trabajadora_id}|${e.fecha}`)).size, 23); // días de persona con ausencia
    assert.ok(evs.every((e) => esLaborable(e.fecha) && e.fecha >= '2026-11-02' && e.fecha <= '2026-11-27'));
    assert.equal(new Set(evs.map((e) => `${e.trabajadora_id}|${e.fecha}|${e.franja}`)).size, evs.length); // uno por persona, día y franja
    const tipos = new Set(evs.map((e) => e.tipo));
    for (const t of ['JORNADA', 'VACACIONES', 'ASUNTOS_PROPIOS', 'PERMISO_RETRIBUIDO', 'PERMISO_NO_RETRIBUIDO', 'PERMISO_MEDICO', 'DESCANSO_COMPENSATORIO', 'BAJA']) {
      assert.ok(tipos.has(t as EventoCalendario['tipo']), t);
    }
  });
  test('franjas de la ficha: completa mañana 4,5 h y tarde 3,5 h (TA2-3); media mañana solo mañana; media tarde solo tarde', () => {
    assert.deepEqual(delDia(a, AINA, '2026-11-09'), [['MANANA', 'JORNADA'], ['TARDE', 'JORNADA']]);
    assert.equal(en(a, AINA, '2026-11-09', 'MANANA')?.horas, 4.5);
    assert.equal(en(a, AINA, '2026-11-09', 'TARDE')?.horas, 3.5);
    // Cada ficha completa suma 8 h al día; cada media, sus horas diarias.
    const porDia = new Map<string, number>();
    for (const e of evs) porDia.set(`${e.trabajadora_id}|${e.fecha}`, (porDia.get(`${e.trabajadora_id}|${e.fecha}`) ?? 0) + e.horas);
    assert.equal(porDia.get(`${AINA}|2026-11-09`), 8);
    assert.equal(porDia.get(`${ELENA}|2026-11-09`), 4.5);
    assert.deepEqual(delDia(a, ELENA, '2026-11-09'), [['MANANA', 'JORNADA']]);
    assert.equal(en(a, ELENA, '2026-11-09', 'MANANA')?.horas, 4.5);
    assert.deepEqual(delDia(a, IRENE, '2026-11-09'), [['TARDE', 'JORNADA']]);
    assert.equal(en(a, IRENE, '2026-11-09', 'TARDE')?.horas, 3.5);
    assert.equal(en(a, IRENE, '2026-11-09', 'TARDE')?.farmacia, 'RITA');
  });
  test('TA2-2: mañana y tarde distintas el mismo día', () => {
    assert.deepEqual(delDia(a, NURIA, '2026-11-10'), [['MANANA', 'JORNADA'], ['TARDE', 'PERMISO_MEDICO']]);
    assert.deepEqual(delDia(a, ROSA, '2026-11-18'), [['MANANA', 'ASUNTOS_PROPIOS'], ['TARDE', 'JORNADA']]);
    assert.deepEqual(delDia(a, MARTA, '2026-11-10'), [['MANANA', 'BAJA'], ['TARDE', 'BAJA']]);
  });
  test('TA2-2: notas de ejemplo (sin datos de salud); el resto sin nota', () => {
    const conNota = evs.filter((e) => e.nota !== null);
    assert.equal(conNota.length, 5);
    assert.equal(en(a, ELENA, '2026-11-25', 'MANANA')?.nota, 'Traslado de domicilio');
    assert.equal(en(a, ROSA, '2026-11-18', 'MANANA')?.nota, 'Gestión en el ayuntamiento');
    assert.ok(conNota.every((e) => e.tipo !== 'PERMISO_MEDICO' && e.tipo !== 'BAJA'));
  });
  test('semana del 2 al 8 confirmada (105, también el descanso de Judit); el resto planificado', () => {
    assert.equal(evs.filter((e) => e.estado === 'CONFIRMADO').length, 105);
    assert.ok(evs.filter((e) => e.estado === 'CONFIRMADO').every((e) => e.fecha <= '2026-11-08'));
    assert.equal(en(a, JUDIT, '2026-11-06', 'TARDE')?.estado, 'CONFIRMADO');
  });
  test('calendario por farmacia: personas de cada farmacia por separado; sin historial de la carga', () => {
    const c = a.calendario('PIO', '2026-11-09', '2026-11-15');
    assert.deepEqual(c.trabajadoras.map((t) => t.id), PIO);
    assert.equal(c.eventos.length, 40); // (3 × 2 + 2) franjas × 5 días
    assert.ok(c.eventos.every((e) => e.farmacia === 'PIO'));
    assert.equal(a.calendario('RITA', '2026-11-09', '2026-11-15').trabajadoras.length, 8);
    assert.equal(a.calendario('AMBAS', '2026-11-09', '2026-11-15').eventos.length, 105);
    assert.equal(c.ultimo_cambio, null);
    assert.deepEqual(a.historialEventos('AMBAS'), []);
  });
  test('la semilla solo usa fichas de ejemplo, tipos de TA2 y franjas propias', () => {
    const s = leerSemillaEventos();
    assert.ok(s.ausencias.every((x) => /^e0000000-/.test(x.trabajadora_id) && x.tipo !== 'JORNADA'));
  });
});

describe('validación de peticiones (falla cerrado)', () => {
  const c = [{ trabajadora_id: AINA, fecha: '2026-12-07' }];
  const errores = (b: unknown) => { const r = validarPeticionEventos(b); return r.ok ? {} : r.errores; };
  test('válidas', () => {
    for (const b of [
      { accion: 'PINTAR', tipo: 'VACACIONES', celdas: c }, { accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ ...c[0], franja: 'TARDE' }] },
      { accion: 'BORRAR', celdas: c },
      { accion: 'RELLENAR', trabajadora_ids: [AINA], desde: '2026-12-01', hasta: '2026-12-31' },
      { accion: 'RELLENAR', trabajadora_ids: [AINA], desde: '2028-01-01', hasta: '2028-12-31' }, // TA2-2: año entero (bisiesto: 366)
      { accion: 'CONFIRMAR', celdas: c }, { accion: 'CONFIRMAR', trabajadora_ids: [AINA], desde: '2026-12-07', hasta: '2026-12-13' },
      { accion: 'DESCONFIRMAR', celdas: c }, { accion: 'EDITAR', evento_id: AINA, horas: 3.25 },
      { accion: 'EDITAR', evento_id: AINA, nota: 'Cubre a Clara' }, { accion: 'EDITAR', evento_id: AINA, nota: null }, { accion: 'EDITAR', evento_id: AINA, horas: 2, nota: '' },
      { accion: 'ANOTAR', celdas: c, nota: 'Cubre a Clara' }, { accion: 'ANOTAR', celdas: [{ ...c[0], franja: 'TARDE' }], nota: null }, // TA2-4
    ]) assert.ok(validarPeticionEventos(b).ok, JSON.stringify(b));
  });
  test('rechazos', () => {
    assert.ok(errores({ accion: 'BORRAR_TODO', celdas: c }).accion);
    assert.ok(errores({ accion: 'PINTAR', tipo: 'GUARDIA', celdas: c }).tipo); // guardias: TA3
    assert.ok(errores({ accion: 'PINTAR', tipo: 'VACACIONES', celdas: [] }).celdas);
    assert.ok(errores({ accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ ...c[0], franja: 'NOCHE' }] }).celdas);
    assert.ok(errores({ accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ ...c[0], franja: 'COMPLETA' }] }).celdas);
    assert.equal(errores({ accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ trabajadora_id: AINA, fecha: '2025-12-31' }] }).celdas, 'Fecha fuera de los años del convenio');
    assert.ok(errores({ accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ ...c[0], farmacia: 'RITA' }] }).celdas); // la farmacia nunca viene del cliente
    assert.equal(errores({ accion: 'PINTAR', tipo: 'VACACIONES', celdas: c, nota: 'x' }).nota, 'Campo no admitido'); // la nota se pone en el detalle del día
    assert.equal(errores({ accion: 'PINTAR', tipo: 'VACACIONES', celdas: c, estado: 'CONFIRMADO' }).estado, 'Campo no admitido');
    assert.ok(errores({ accion: 'RELLENAR', trabajadora_ids: [AINA], desde: '2026-01-01', hasta: '2027-01-02' }).hasta); // 367 días: > 366
    assert.ok(errores({ accion: 'RELLENAR', trabajadora_ids: [AINA], desde: '2026-12-10', hasta: '2026-12-01' }).hasta);
    assert.ok(errores({ accion: 'RELLENAR', trabajadora_ids: [AINA, AINA], desde: '2026-12-01', hasta: '2026-12-07' }).trabajadora_ids);
    for (const h of [0, -1, 12.5, '8', 7.333, Number.NaN]) assert.ok(errores({ accion: 'EDITAR', evento_id: AINA, horas: h }).horas, String(h));
    assert.ok(errores({ accion: 'EDITAR', evento_id: AINA })._); // ni horas ni nota
    assert.equal(errores({ accion: 'EDITAR', evento_id: AINA, nota: 'x'.repeat(201) }).nota, 'La nota tiene como máximo 200 caracteres');
    assert.ok(errores({ accion: 'EDITAR', evento_id: AINA, nota: '<b>x</b>' }).nota);
    assert.ok(errores({ accion: 'EDITAR', evento_id: AINA, nota: 3 }).nota);
    // TA2-4: ANOTAR exige celdas y nota; sin tipo, horas ni evento_id.
    assert.ok(errores({ accion: 'ANOTAR', celdas: c }).nota);
    assert.ok(errores({ accion: 'ANOTAR', celdas: [], nota: 'x' }).celdas);
    assert.equal(errores({ accion: 'ANOTAR', celdas: c, nota: 'x'.repeat(201) }).nota, 'La nota tiene como máximo 200 caracteres');
    assert.equal(errores({ accion: 'ANOTAR', celdas: c, nota: 'x', horas: 2 }).horas, 'Campo no admitido');
    assert.equal(errores({ accion: 'ANOTAR', celdas: c, nota: 'x', evento_id: AINA }).evento_id, 'Campo no admitido');
    for (const malo of [null, [], 'x', 3]) assert.equal(validarPeticionEventos(malo).ok, false);
    assert.equal(validarDeshacer({ cambio_id: AINA }).ok, true);
    for (const malo of [{}, { cambio_id: 'x' }, { cambio_id: AINA, otro: 1 }, null]) assert.equal(validarDeshacer(malo).ok, false);
  });
  test('nota: espacios normalizados, vacía = null; el aviso de la pantalla', () => {
    assert.deepEqual(leerNota('  Cubre   a Clara  '), { ok: true, nota: 'Cubre a Clara' });
    assert.deepEqual(leerNota('   '), { ok: true, nota: null });
    assert.deepEqual(leerNota('x'.repeat(200)), { ok: true, nota: 'x'.repeat(200) });
    assert.equal(AVISO_NOTA, 'No anotes datos de salud ni diagnósticos');
  });
  test('celdas repetidas cuentan una vez', () => {
    const r = validarPeticionEventos({ accion: 'BORRAR', celdas: [...c, ...c] });
    assert.ok(r.ok && 'celdas' in r.peticion && r.peticion.celdas.length === 1);
  });
});

describe('pintar y goma por franja', () => {
  test('el día completo (sin franja) pinta las dos franjas de una completa; una franja solo esa', () => {
    const a = nuevo();
    const r = ok(aplicar(a, { accion: 'PINTAR', tipo: 'VACACIONES', celdas: celdas(AINA, '2026-12-07', '2026-12-11') }));
    assert.deepEqual([r.cambio?.n, r.cambio?.dias], [10, 5]);
    assert.equal(describirCambio(r.cambio!), 'Pintado Vacaciones 7–11 dic 2026: 5 días laborables × 1 persona');
    assert.deepEqual(delDia(a, AINA, '2026-12-09'), [['MANANA', 'VACACIONES'], ['TARDE', 'VACACIONES']]);
    const e = en(a, AINA, '2026-12-09', 'TARDE');
    assert.deepEqual([e?.horas, e?.estado, e?.farmacia, e?.nota], [3.5, 'PLANIFICADO', 'PIO', null]);
    assert.equal(en(a, AINA, '2026-12-09', 'MANANA')?.horas, 4.5);
    const t = ok(aplicar(a, { accion: 'PINTAR', tipo: 'PERMISO_MEDICO', celdas: [{ trabajadora_id: CLARA, fecha: '2026-12-07', franja: 'TARDE' }] }));
    assert.deepEqual([t.cambio?.n, t.cambio?.dias], [1, 1]);
    assert.deepEqual(delDia(a, CLARA, '2026-12-07'), [['TARDE', 'PERMISO_MEDICO']]);
    ok(aplicar(a, { accion: 'PINTAR', tipo: 'JORNADA', celdas: [{ trabajadora_id: CLARA, fecha: '2026-12-07', franja: 'MANANA' }] }));
    assert.deepEqual(delDia(a, CLARA, '2026-12-07'), [['MANANA', 'JORNADA'], ['TARDE', 'PERMISO_MEDICO']]); // mañana y tarde distintas
    const h = a.historialEventos('PIO');
    assert.ok(h[2].trazas.every((x) => x.accion === 'CREAR' && x.antes === null && x.nombre === 'Aina Bosch Ferrer'));
    assert.deepEqual(h[2].trazas.slice(0, 2).map((x) => x.franja), ['MANANA', 'TARDE']);
  });
  test('media jornada: el día completo es su única franja; la otra franja falla cerrado', () => {
    const a = nuevo();
    ok(aplicar(a, { accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ trabajadora_id: ELENA, fecha: '2026-12-07' }, { trabajadora_id: IRENE, fecha: '2026-12-07' }] }));
    assert.deepEqual(delDia(a, ELENA, '2026-12-07'), [['MANANA', 'VACACIONES']]);
    assert.deepEqual(delDia(a, IRENE, '2026-12-07'), [['TARDE', 'VACACIONES']]);
    assert.equal(en(a, ELENA, '2026-12-07', 'MANANA')?.horas, 4.5);
    const antes = foto(a);
    const cuerpo = { accion: 'PINTAR', tipo: 'BAJA', celdas: [{ trabajadora_id: AINA, fecha: '2026-12-08' }, { trabajadora_id: ELENA, fecha: '2026-12-08', franja: 'TARDE' }] };
    assert.equal(aplicar(a, cuerpo), 'FRANJA_NO_VALIDA');
    assert.equal(foto(a), antes); // todo o nada
  });
  test('pintar sobre una jornada la sustituye (EDITAR, sin la nota anterior); el mismo tipo no cambia nada', () => {
    const a = nuevo();
    const antes = en(a, ELENA, '2026-11-25', 'MANANA');
    assert.equal(antes?.nota, 'Traslado de domicilio');
    ok(aplicar(a, { accion: 'PINTAR', tipo: 'ASUNTOS_PROPIOS', celdas: [{ trabajadora_id: ELENA, fecha: '2026-11-25' }] }));
    const t = a.historialEventos('AMBAS')[0].trazas[0];
    assert.deepEqual([t.accion, t.antes?.tipo, t.antes?.nota, t.despues?.tipo, t.despues?.nota, t.evento_id], ['EDITAR', 'PERMISO_RETRIBUIDO', 'Traslado de domicilio', 'ASUNTOS_PROPIOS', null, antes?.id]);
    assert.equal(ok(aplicar(a, { accion: 'PINTAR', tipo: 'ASUNTOS_PROPIOS', celdas: [{ trabajadora_id: ELENA, fecha: '2026-11-25' }] })).cambio, null);
  });
  test('lo confirmado no se pinta ni se borra (se informa cuántas franjas se omiten)', () => {
    const a = nuevo();
    const r = ok(aplicar(a, { accion: 'PINTAR', tipo: 'BAJA', celdas: celdas(AINA, '2026-11-05', '2026-11-10') }));
    assert.equal(r.omitidas_confirmadas, 4); // 5 y 6 confirmados (2 franjas cada uno)
    assert.deepEqual([r.cambio?.n, r.cambio?.dias], [8, 4]); // 7 y 8 libres (a mano sí se pinta el fin de semana); 9 y 10 planificados
    assert.equal(en(a, AINA, '2026-11-05', 'MANANA')?.tipo, 'JORNADA');
    const g = ok(aplicar(a, { accion: 'BORRAR', celdas: celdas(AINA, '2026-11-05', '2026-11-10', 'TARDE') }));
    assert.deepEqual([g.omitidas_confirmadas, g.cambio?.n, g.cambio?.origen], [2, 4, 'BORRAR']);
    assert.deepEqual(delDia(a, AINA, '2026-11-09'), [['MANANA', 'BAJA']]); // la goma de la tarde deja la mañana
    assert.equal(describirCambio(g.cambio!), 'Borrado 7–10 nov 2026: 4 días × 1 persona · 4 franjas'); // con fin de semana: «días»; solo tardes: franjas
  });
  test('persona de baja o inexistente: no se aplica nada (todo o nada)', () => {
    const a = nuevo();
    a.darDeBaja(CLARA, '2026-11-30', AUTOR_HISTORIAL);
    const antes = foto(a);
    const cuerpo = { accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ trabajadora_id: AINA, fecha: '2026-12-07' }, { trabajadora_id: CLARA, fecha: '2026-12-07' }] };
    assert.equal(aplicar(a, cuerpo), 'TRABAJADORA_NO_VALIDA');
    assert.equal(aplicar(a, { ...cuerpo, celdas: [{ trabajadora_id: 'f9999999-0000-4000-8000-000000000000', fecha: '2026-12-07' }] }), 'TRABAJADORA_NO_VALIDA');
    assert.equal(foto(a), antes);
    assert.ok(!a.calendario('PIO', '2026-11-30', '2026-12-06').trabajadoras.some((t) => t.id === CLARA));
  });
});

describe('rellenar jornada habitual (semana, mes y año)', () => {
  test('lunes a viernes por franja según la ficha, sin sobrescribir ausencias; repetirlo no crea nada', () => {
    const a = nuevo();
    ok(aplicar(a, { accion: 'PINTAR', tipo: 'VACACIONES', celdas: celdas(AINA, '2026-12-09', '2026-12-09', 'TARDE') }));
    const r = ok(aplicar(a, { accion: 'RELLENAR', trabajadora_ids: PIO, desde: '2026-12-07', hasta: '2026-12-13' }));
    assert.deepEqual([r.cambio?.n, r.cambio?.dias], [39, 25]); // 8 franjas × 5 días − la tarde de vacaciones
    assert.equal(describirCambio(r.cambio!), 'Rellenado 7–13 dic 2026: 5 días laborables × 5 personas · 39 franjas'); // Aina, solo la mañana del 9
    assert.deepEqual(delDia(a, AINA, '2026-12-09'), [['MANANA', 'JORNADA'], ['TARDE', 'VACACIONES']]);
    assert.deepEqual(delDia(a, AINA, '2026-12-12'), []); // sábado
    assert.deepEqual(delDia(a, ELENA, '2026-12-07'), [['MANANA', 'JORNADA']]);
    assert.deepEqual([en(a, CLARA, '2026-12-07', 'MANANA')?.horas, en(a, CLARA, '2026-12-07', 'TARDE')?.horas], [4.5, 3.5]); // TA2-3
    assert.equal(ok(aplicar(a, { accion: 'RELLENAR', trabajadora_ids: PIO, desde: '2026-12-07', hasta: '2026-12-13' })).cambio, null);
  });
  test('un mes (RITA, media tarde a 3,5 h de tarde)', () => {
    const a = nuevo();
    const r = ok(aplicar(a, { accion: 'RELLENAR', trabajadora_ids: [IRENE], desde: '2026-12-01', hasta: '2026-12-31' }));
    assert.equal(r.cambio?.dias, 23);
    assert.equal(describirCambio(r.cambio!), 'Rellenado diciembre de 2026: 23 días laborables × 1 persona');
    assert.ok(a.eventos().filter((e) => e.trabajadora_id === IRENE && e.fecha >= '2026-12-01').every((e) => e.franja === 'TARDE' && e.horas === 3.5));
  });
  test('TA2-2: año completo sin tocar lo pintado ni lo confirmado; se deshace de una vez', () => {
    const a = nuevo();
    const antes = foto(a);
    const r = ok(aplicar(a, { accion: 'RELLENAR', trabajadora_ids: [AINA, ELENA], desde: '2026-01-01', hasta: '2026-12-31' }));
    // 261 laborables en 2026; Aina y Elena ya tienen 20 días de noviembre cada una.
    assert.deepEqual([r.cambio?.dias, r.cambio?.n], [(261 - 20) * 2, (261 - 20) * 3]);
    assert.equal(en(a, AINA, '2026-11-17', 'MANANA')?.tipo, 'VACACIONES'); // ausencia intacta
    assert.equal(en(a, AINA, '2026-11-03', 'MANANA')?.estado, 'CONFIRMADO'); // confirmado intacto
    assert.equal(en(a, AINA, '2026-01-01', 'MANANA')?.tipo, 'JORNADA'); // los festivos llegan en TA3
    ok(a.deshacerEventos(r.cambio!.id, AUTOR_HISTORIAL) as ResultadoCambioDTO);
    assert.equal(foto(a), antes);
  });
  test('TA2-4: mensajes en días laborables × personas, no en días de persona (año, confirmar y deshacer)', () => {
    const a = nuevo();
    const r = ok(aplicar(a, { accion: 'RELLENAR', trabajadora_ids: PIO, desde: '2027-01-01', hasta: '2027-12-31' }));
    assert.deepEqual([r.cambio?.fechas, r.cambio?.personas.length, r.cambio?.dias, r.cambio?.laborables, r.cambio?.parcial], [261, 5, 1305, true, false]);
    assert.equal(describirCambio(r.cambio!), 'Rellenado 2027: 261 días laborables × 5 personas');
    const c = ok(aplicar(a, { accion: 'CONFIRMAR', trabajadora_ids: PIO, desde: '2027-01-01', hasta: '2027-12-31' }));
    assert.equal(describirCambio(c.cambio!), 'Confirmado 2027: 261 días laborables × 5 personas');
    const d = ok(a.deshacerEventos(c.cambio!.id, AUTOR_HISTORIAL) as ResultadoCambioDTO);
    assert.equal(describirCambio(d.cambio!), 'Deshecho «Confirmado 2027»: 261 días laborables × 5 personas');
    // 2028 empieza en sábado: el periodo es el pedido (el año), no el primer día tocado.
    const r28 = ok(aplicar(a, { accion: 'RELLENAR', trabajadora_ids: [AINA], desde: '2028-01-01', hasta: '2028-12-31' }));
    assert.equal(describirCambio(r28.cambio!), 'Rellenado 2028: 260 días laborables × 1 persona');
    const d28 = ok(a.deshacerEventos(r28.cambio!.id, AUTOR_HISTORIAL) as ResultadoCambioDTO);
    assert.equal(describirCambio(d28.cambio!), 'Deshecho «Rellenado 2028»: 260 días laborables × 1 persona');
  });
  test('TA2-4: periodo legible', () => {
    assert.equal(textoPeriodoCambio('2027-01-01', '2027-12-31'), '2027');
    assert.equal(textoPeriodoCambio('2026-12-01', '2026-12-31'), 'diciembre de 2026');
    assert.equal(textoPeriodoCambio('2028-02-01', '2028-02-29'), 'febrero de 2028');
    assert.equal(textoPeriodoCambio('2026-11-10', '2026-11-10'), '10 nov 2026');
    assert.equal(textoPeriodoCambio('2026-11-02', '2026-11-08'), '2–8 nov 2026');
    assert.equal(textoPeriodoCambio('2026-11-30', '2026-12-06'), '30 nov – 6 dic 2026');
    assert.equal(textoPeriodoCambio('2026-12-28', '2027-01-03'), '28 dic 2026 – 3 ene 2027');
  });
  test('la jornada usa la ficha vigente (tras editarla)', () => {
    const a = nuevo();
    a.editar(AINA, { nombre: 'Aina Bosch Ferrer', categoria: 'TECNICO', jornada: 'MEDIA_TARDE', horas_diarias: 3.5, es_titular: false }, AUTOR_HISTORIAL);
    ok(aplicar(a, { accion: 'RELLENAR', trabajadora_ids: [AINA], desde: '2026-12-07', hasta: '2026-12-07' }));
    assert.deepEqual(delDia(a, AINA, '2026-12-07'), [['TARDE', 'JORNADA']]);
  });
});

describe('confirmar, editar horas y nota', () => {
  test('confirmar una semana (rango) o franjas sueltas; quitar la confirmación', () => {
    const a = nuevo();
    const r = ok(aplicar(a, { accion: 'CONFIRMAR', trabajadora_ids: PIO, desde: '2026-11-09', hasta: '2026-11-15' }));
    assert.deepEqual([r.cambio?.n, r.cambio?.dias], [40, 25]);
    assert.ok(a.calendario('PIO', '2026-11-09', '2026-11-15').eventos.every((e) => e.estado === 'CONFIRMADO'));
    const d = ok(aplicar(a, { accion: 'DESCONFIRMAR', celdas: [{ trabajadora_id: NURIA, fecha: '2026-11-10', franja: 'TARDE' }] }));
    assert.equal(describirCambio(d.cambio!), 'Quitada la confirmación 10 nov 2026: 1 día laborable × 1 persona · 1 franja');
    assert.equal(describirCambio(r.cambio!), 'Confirmado 9–15 nov 2026: 5 días laborables × 5 personas');
    assert.deepEqual([en(a, NURIA, '2026-11-10', 'MANANA')?.estado, en(a, NURIA, '2026-11-10', 'TARDE')?.estado], ['CONFIRMADO', 'PLANIFICADO']);
  });
  test('horas y nota a mano: solo en planificado; queda en la traza; confirmado y desconocido fallan', () => {
    const a = nuevo();
    const e = en(a, AINA, '2026-11-11', 'TARDE') as EventoCalendario;
    const r = ok(aplicar(a, { accion: 'EDITAR', evento_id: e.id, horas: 2.5, nota: 'Sale antes para cubrir a Clara' }));
    assert.equal(describirCambio(r.cambio!), 'Editado 11 nov 2026: 1 día laborable × 1 persona · 1 franja');
    assert.deepEqual([en(a, AINA, '2026-11-11', 'TARDE')?.horas, en(a, AINA, '2026-11-11', 'TARDE')?.nota], [2.5, 'Sale antes para cubrir a Clara']);
    const t = a.historialEventos('PIO')[0].trazas[0];
    assert.deepEqual([t.antes?.horas, t.antes?.nota, t.despues?.horas, t.despues?.nota], [3.5, null, 2.5, 'Sale antes para cubrir a Clara']);
    ok(aplicar(a, { accion: 'EDITAR', evento_id: e.id, nota: '' }));
    assert.equal(en(a, AINA, '2026-11-11', 'TARDE')?.nota, null); // vaciar la nota la quita
    assert.equal(ok(aplicar(a, { accion: 'EDITAR', evento_id: e.id, horas: 2.5 })).cambio, null);
    assert.equal(aplicar(a, { accion: 'EDITAR', evento_id: (en(a, AINA, '2026-11-03', 'MANANA') as EventoCalendario).id, nota: 'x' }), 'EVENTO_CONFIRMADO');
    assert.equal(aplicar(a, { accion: 'EDITAR', evento_id: 'f9999999-0000-4000-8000-000000000000', horas: 2 }), 'EVENTO_NO_ENCONTRADO');
  });
  test('TA2-4: ANOTAR pone la misma nota en las franjas con evento; vacías y confirmadas se omiten y se cuentan; se deshace', () => {
    const a = nuevo();
    const inicio = foto(a);
    // Aina: 6 y 9-10 nov (6 confirmado, 2 franjas); 7-8 fin de semana (vacíos, 2 franjas cada uno). Elena 9 nov: su mañana.
    const sel = [...celdas(AINA, '2026-11-06', '2026-11-10'), { trabajadora_id: ELENA, fecha: '2026-11-09' }];
    const r = ok(aplicar(a, { accion: 'ANOTAR', celdas: sel, nota: '  Formación   en Reus ' }));
    assert.deepEqual([r.omitidas_vacias, r.omitidas_confirmadas, r.cambio?.n, r.cambio?.origen], [4, 2, 5, 'ANOTAR']);
    assert.equal(describirCambio(r.cambio!), 'Anotado 9–10 nov 2026: 2 días laborables × 2 personas');
    assert.deepEqual([en(a, AINA, '2026-11-09', 'TARDE')?.nota, en(a, ELENA, '2026-11-09', 'MANANA')?.nota], ['Formación en Reus', 'Formación en Reus']);
    assert.equal(en(a, AINA, '2026-11-06', 'MANANA')?.nota, null); // confirmado: intacto
    assert.equal(en(a, AINA, '2026-11-07', 'MANANA'), undefined); // vacío: no se crea nada
    assert.ok(a.historialEventos('PIO')[0].trazas.every((t) => t.antes?.nota === null && t.despues?.nota === 'Formación en Reus'));
    assert.equal(ok(aplicar(a, { accion: 'ANOTAR', celdas: sel, nota: 'Formación en Reus' })).cambio, null); // misma nota: sin cambios
    ok(a.deshacerEventos(r.cambio!.id, AUTOR_HISTORIAL) as ResultadoCambioDTO);
    assert.equal(foto(a), inicio);
  });
  test('TA2-4: ANOTAR solo franjas vacías: nada cambia y se cuenta cuántas; franja ajena falla cerrado', () => {
    const a = nuevo();
    const antes = foto(a);
    const r = ok(aplicar(a, { accion: 'ANOTAR', celdas: celdas(AINA, '2026-12-14', '2026-12-15'), nota: 'x' }));
    assert.deepEqual([r.cambio, r.omitidas_vacias, r.omitidas_confirmadas], [null, 4, 0]);
    assert.equal(AVISO_NOTA_VACIA, 'Pinta primero un evento para poder anotarlo');
    assert.equal(aplicar(a, { accion: 'ANOTAR', celdas: [{ trabajadora_id: IRENE, fecha: '2026-11-09', franja: 'MANANA' }], nota: 'x' }), 'FRANJA_NO_VALIDA');
    assert.equal(foto(a), antes);
  });
});

describe('deshacer e historial', () => {
  test('deshace el último cambio, luego el anterior; restaura exactamente (franjas y notas); queda en la traza', () => {
    const a = nuevo();
    const inicio = foto(a);
    const c1 = ok(aplicar(a, { accion: 'RELLENAR', trabajadora_ids: PIO, desde: '2026-12-07', hasta: '2026-12-13' })).cambio!;
    const tras1 = foto(a);
    const c2 = ok(aplicar(a, { accion: 'PINTAR', tipo: 'VACACIONES', celdas: celdas(AINA, '2026-12-07', '2026-12-13', 'TARDE') })).cambio!;
    const ev = en(a, CLARA, '2026-12-07', 'MANANA') as EventoCalendario;
    const c3 = ok(aplicar(a, { accion: 'EDITAR', evento_id: ev.id, nota: 'Abre la farmacia' })).cambio!;
    const c4 = ok(aplicar(a, { accion: 'BORRAR', celdas: celdas(CLARA, '2026-12-07', '2026-12-08') })).cambio!;
    assert.equal(a.calendario('PIO', '2026-12-07', '2026-12-13').ultimo_cambio?.id, c4.id);
    assert.equal(a.deshacerEventos(c2.id, AUTOR_HISTORIAL), 'NO_ES_EL_ULTIMO'); // solo el último
    const d4 = a.deshacerEventos(c4.id, AUTOR_HISTORIAL) as ResultadoCambioDTO;
    assert.equal(describirCambio(d4.cambio!), 'Deshecho «Borrado 7–8 dic 2026»: 2 días laborables × 1 persona');
    assert.equal(en(a, CLARA, '2026-12-07', 'MANANA')?.nota, 'Abre la farmacia'); // vuelve con su nota
    ok(a.deshacerEventos(c3.id, AUTOR_HISTORIAL) as ResultadoCambioDTO);
    const d2 = a.deshacerEventos(c2.id, AUTOR_HISTORIAL) as ResultadoCambioDTO;
    assert.equal(describirCambio(d2.cambio!), 'Deshecho «Pintado Vacaciones 7–13 dic 2026»: 7 días × 1 persona · 7 franjas');
    assert.equal(foto(a), tras1);
    ok(a.deshacerEventos(c1.id, AUTOR_HISTORIAL) as ResultadoCambioDTO);
    assert.equal(foto(a), inicio);
    assert.equal(a.deshacerEventos(c1.id, AUTOR_HISTORIAL), 'NADA_QUE_DESHACER');
    const h = a.historialEventos('AMBAS');
    assert.deepEqual(h.map((c) => [c.origen, c.deshecho]), [
      ['DESHACER', false], ['DESHACER', false], ['DESHACER', false], ['DESHACER', false], ['BORRAR', true], ['EDITAR', true], ['PINTAR', true], ['RELLENAR', true],
    ]);
    assert.ok(h.every((c) => c.quien === 'Marc' && /^2026-11-12T10:00:00\.\d{3}Z$/.test(c.cuando)));
  });
  test('un cambio nuevo tras deshacer pasa a ser el último; deshacer queda fuera de la pila', () => {
    const a = nuevo();
    const c1 = ok(aplicar(a, { accion: 'PINTAR', tipo: 'BAJA', celdas: celdas(NURIA, '2026-12-14', '2026-12-15') })).cambio!;
    a.deshacerEventos(c1.id, AUTOR_HISTORIAL);
    assert.equal(a.calendario('PIO', '2026-12-14', '2026-12-20').ultimo_cambio, null);
    const c2 = ok(aplicar(a, { accion: 'PINTAR', tipo: 'PERMISO_MEDICO', celdas: celdas(NURIA, '2026-12-14', '2026-12-14', 'MANANA') })).cambio!;
    assert.equal(a.calendario('PIO', '2026-12-14', '2026-12-20').ultimo_cambio?.id, c2.id);
  });
  test('historial por farmacia: solo sus trazas', () => {
    const a = nuevo();
    ok(aplicar(a, { accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ trabajadora_id: AINA, fecha: '2026-12-21' }, { trabajadora_id: IRENE, fecha: '2026-12-21' }] }));
    ok(aplicar(a, { accion: 'PINTAR', tipo: 'BAJA', celdas: [{ trabajadora_id: MARTA, fecha: '2026-12-22' }] }));
    const pio = a.historialEventos('PIO');
    assert.equal(pio.length, 1);
    assert.deepEqual([pio[0].n, pio[0].dias, pio[0].farmacias, pio[0].personas], [2, 1, ['PIO'], ['Aina Bosch Ferrer']]);
    assert.equal(a.historialEventos('RITA').length, 2);
    assert.deepEqual(a.historialEventos('AMBAS')[1].farmacias, ['PIO', 'RITA']);
  });
});

describe('API /api/rrhh/eventos en el servidor FIXTURES (inyección)', async () => {
  const app = await crearServidor('FIXTURES');
  after(() => app.close());
  const H = { host: '127.0.0.1:4747' };
  const ORIGEN = { origin: 'http://127.0.0.1:4747', 'content-type': 'application/json' };
  const login = await app.inject({
    method: 'POST', url: '/api/login', headers: { ...H, 'content-type': 'application/x-www-form-urlencoded' },
    payload: new URLSearchParams({ usuario: USUARIO, clave: CLAVE_FIXTURES, destino: '/' }).toString(),
  });
  const cookie = String(login.headers['set-cookie']).split(';')[0];
  const pintar = { accion: 'PINTAR', tipo: 'VACACIONES', celdas: celdas(AINA, '2026-12-07', '2026-12-08') };

  test('lectura: sesión obligatoria; rango válido dentro de los años del convenio', async () => {
    const url = '/api/rrhh/eventos?farmacia=PIO&desde=2026-11-09&hasta=2026-11-15';
    assert.equal((await app.inject({ method: 'GET', url, headers: H })).statusCode, 401);
    const r = await app.inject({ method: 'GET', url, headers: { ...H, cookie } });
    assert.equal(r.statusCode, 200);
    assert.equal(r.json().eventos.length, 40);
    for (const q of ['farmacia=X&desde=2026-11-09&hasta=2026-11-15', 'desde=2026-11-15&hasta=2026-11-09', 'desde=2025-12-01&hasta=2025-12-07',
      'desde=2026-01-01&hasta=2027-12-31', 'desde=2026-11-9&hasta=2026-11-15', 'farmacia=PIO']) {
      assert.equal((await app.inject({ method: 'GET', url: `/api/rrhh/eventos?${q}`, headers: { ...H, cookie } })).statusCode, 400, q);
    }
  });
  test('escritura: sesión, Origin del mismo sitio y JSON; validación 400; franja ajena 400; cambio y deshacer con autor Marc', async () => {
    const post = (url: string, headers: Record<string, string>, payload: unknown) => app.inject({ method: 'POST', url, headers: { ...H, ...headers }, payload: payload as object });
    assert.equal((await post('/api/rrhh/eventos', ORIGEN, pintar)).statusCode, 401);
    assert.equal((await post('/api/rrhh/eventos', { cookie, 'content-type': 'application/json' }, pintar)).statusCode, 403);
    assert.equal((await post('/api/rrhh/eventos', { cookie, ...ORIGEN, origin: 'http://evil.example' }, pintar)).statusCode, 403);
    assert.equal((await post('/api/rrhh/eventos', { cookie, ...ORIGEN, 'sec-fetch-site': 'cross-site' }, pintar)).statusCode, 403);
    const form = await app.inject({ method: 'POST', url: '/api/rrhh/eventos', headers: { ...H, cookie, origin: ORIGEN.origin, 'content-type': 'application/x-www-form-urlencoded' }, payload: 'accion=BORRAR' });
    assert.equal(form.statusCode, 415);
    const malo = await post('/api/rrhh/eventos', { cookie, ...ORIGEN }, { ...pintar, nota: 'x' });
    assert.equal(malo.statusCode, 400);
    assert.deepEqual(malo.json().errores, { nota: 'Campo no admitido' });
    const ajena = await post('/api/rrhh/eventos', { cookie, ...ORIGEN }, { ...pintar, celdas: [{ trabajadora_id: IRENE, fecha: '2026-12-07', franja: 'MANANA' }] });
    assert.deepEqual([ajena.statusCode, ajena.json().error], [400, 'FRANJA_NO_VALIDA']);
    const r = await post('/api/rrhh/eventos', { cookie, ...ORIGEN }, pintar);
    assert.equal(r.statusCode, 200);
    const cambio = r.json().cambio;
    assert.deepEqual([cambio.n, cambio.dias, cambio.quien, cambio.origen], [4, 2, 'Marc', 'PINTAR']);
    const otro = await post('/api/rrhh/eventos/deshacer', { cookie, ...ORIGEN }, { cambio_id: 'f9999999-0000-4000-8000-000000000000' });
    assert.deepEqual([otro.statusCode, otro.json().error], [409, 'NO_ES_EL_ULTIMO']);
    const d = await post('/api/rrhh/eventos/deshacer', { cookie, ...ORIGEN }, { cambio_id: cambio.id });
    assert.equal(d.statusCode, 200);
    assert.equal(d.json().cambio.deshace.id, cambio.id);
    const nada = await post('/api/rrhh/eventos/deshacer', { cookie, ...ORIGEN }, { cambio_id: cambio.id });
    assert.deepEqual([nada.statusCode, nada.json().error], [409, 'NADA_QUE_DESHACER']);
    const h = await app.inject({ method: 'GET', url: '/api/rrhh/eventos/historial?farmacia=PIO', headers: { ...H, cookie } });
    assert.deepEqual(h.json().map((c: { origen: string; quien: string }) => [c.origen, c.quien]), [['DESHACER', 'Marc'], ['PINTAR', 'Marc']]);
    const conf = await post('/api/rrhh/eventos', { cookie, ...ORIGEN }, { accion: 'EDITAR', evento_id: (await app.inject({
      method: 'GET', url: '/api/rrhh/eventos?farmacia=PIO&desde=2026-11-03&hasta=2026-11-03', headers: { ...H, cookie } })).json().eventos[0].id, nota: 'x' });
    assert.deepEqual([conf.statusCode, conf.json().error], [409, 'EVENTO_CONFIRMADO']);
    // TA2-4: ANOTAR sobre franjas vacías: 200 sin cambio y con las vacías contadas.
    const vacia = await post('/api/rrhh/eventos', { cookie, ...ORIGEN }, { accion: 'ANOTAR', celdas: celdas(AINA, '2026-12-14', '2026-12-14'), nota: 'x' });
    assert.deepEqual([vacia.statusCode, vacia.json().cambio, vacia.json().omitidas_vacias], [200, null, 2]);
  });
  test('sin DELETE ni PATCH ni PUT en eventos: 405', async () => {
    for (const [method, url] of [['DELETE', `/api/rrhh/eventos/${AINA}`], ['PUT', '/api/rrhh/eventos'], ['PATCH', '/api/rrhh/eventos'], ['DELETE', '/api/rrhh/eventos']] as const) {
      assert.equal((await app.inject({ method, url, headers: { ...H, cookie, ...ORIGEN }, payload: {} })).statusCode, 405, `${method} ${url}`);
    }
  });
});
