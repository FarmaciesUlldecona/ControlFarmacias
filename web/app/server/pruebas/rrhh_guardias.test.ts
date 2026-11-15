// TA3 Trabajadores: guardias y festivos. Horario (único punto) y horas fuera de cómputo, validación, reglas de
// personas (OTRA sin personas, persona de esa farmacia y de alta, titular permitido, apoyo distinto), persona por
// defecto de la guardia de un festivo, semilla de ejemplo, «Guardias del año», calendario (rellenar salta festivos,
// pintar sobre festivo avisa) y API (FIXTURES; REAL: «Pendiente de tablas en Supabase»). Uso: npm run test:unit
import assert from 'node:assert/strict';
import { after, describe, test } from 'node:test';
import Fastify from 'fastify';
import { CLAVE_FIXTURES, USUARIO } from '../acceso.ts';
import { crearServidor } from '../index.ts';
import { AUTOR_HISTORIAL } from '../rrhh/contrato.ts';
import { crearAdaptadorRrhhFixtures, leerSemillaGuardias, type AdaptadorRrhhFixtures } from '../rrhh/adaptador_fixtures.ts';
import { validarPeticionEventos, type PeticionEventos, type ResultadoCambioDTO } from '../rrhh/eventos.ts';
import {
  ERROR_TA3_PENDIENTE, HORARIO_GUARDIA, HORAS_SERVICIO, TEXTO_TA3_PENDIENTE, horasSemana, horasTramos, iniciales, reglasSemana,
  resumenGuardiasPersona, semanasDeRotacion, validarFestivo, validarGuardiaFestivo, validarGuardiaSemana,
  type DatosGuardiaSemana,
} from '../rrhh/guardias.ts';
import { esEscrituraRrhh, registrarRrhh } from '../rrhh/rutas.ts';

const ID = (n: number) => `e0000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const AINA = ID(1); const CLARA = ID(2); const ELENA = ID(4); const LAURA = ID(11); const MARTA = ID(12); const SILVIA = ID(13);
const JUDIT = ID(14); const ROSA = ID(15); const PAULA = ID(16); const TITULAR_PIO = ID(21);

function nuevo(): AdaptadorRrhhFixtures {
  let n = 0;
  return crearAdaptadorRrhhFixtures({ nuevoId: () => `f3000000-0000-4000-8000-${String(++n).padStart(12, '0')}`, ahora: () => '2026-11-12T10:00:00.000Z' });
}
const semana = (o: Partial<DatosGuardiaSemana>): DatosGuardiaSemana => ({
  lunes: '2027-01-04', farmacia: 'PIO', persona_guardia_id: CLARA, persona_apoyo_sabado_id: ELENA, ...o,
});

describe('horario de guardia (único punto) y horas fuera de cómputo', () => {
  test('guardia sábado 9:00–13:30 y 18:00–20:00 (6,5 h), domingo 10:00–13:00 (3 h); apoyo 4,5 h; festivo 3 h; localizada sin horas', () => {
    assert.deepEqual(HORARIO_GUARDIA, {
      GUARDIA_SABADO: [{ desde: '9:00', hasta: '13:30' }, { desde: '18:00', hasta: '20:00' }],
      GUARDIA_DOMINGO: [{ desde: '10:00', hasta: '13:00' }],
      APOYO_SABADO: [{ desde: '9:00', hasta: '13:30' }],
      FESTIVO: [{ desde: '10:00', hasta: '13:00' }],
      LOCALIZADA: [],
    });
    assert.deepEqual(HORAS_SERVICIO, { GUARDIA_SABADO: 6.5, GUARDIA_DOMINGO: 3, APOYO_SABADO: 4.5, FESTIVO: 3, LOCALIZADA: 0 });
    assert.equal(horasTramos([{ desde: '9:15', hasta: '10:00' }]), 0.75);
  });
  test('una semana: 9,5 h de guardia y 4,5 h de apoyo; un festivo en sábado o domingo sustituye ese día', () => {
    assert.deepEqual(horasSemana('2027-01-04', () => false), { guardia: 9.5, apoyo: 4.5 });
    assert.deepEqual(horasSemana('2026-10-26', (f) => f === '2026-11-01'), { guardia: 6.5, apoyo: 4.5 }); // domingo festivo
    assert.deepEqual(horasSemana('2026-12-21', (f) => f === '2026-12-26'), { guardia: 3, apoyo: 0 }); // sábado festivo
  });
  test('iniciales para la banda', () => {
    assert.deepEqual(['Aina Bosch Ferrer', 'Titular de ejemplo', 'Sílvia Font Rius'].map(iniciales), ['AB', 'TE', 'SF']);
  });
});

describe('validación (falla cerrado)', () => {
  test('guardia semanal: lunes de los años del convenio, farmacia, OTRA sin personas, guardia obligatoria en PIO/RITA, apoyo distinto', () => {
    assert.ok(validarGuardiaSemana('2027-01-04', { farmacia: 'PIO', persona_guardia_id: CLARA }).ok);
    assert.ok(validarGuardiaSemana('2025-12-29', { farmacia: 'OTRA' }).ok); // la semana del 1 ene 2026
    const e = (lunes: string, b: unknown) => { const v = validarGuardiaSemana(lunes, b); assert.equal(v.ok, false); return (v as { errores: Record<string, string> }).errores; };
    assert.ok(e('2027-01-05', { farmacia: 'PIO', persona_guardia_id: CLARA }).lunes); // martes
    assert.ok(e('2025-12-22', { farmacia: 'OTRA' }).lunes); // fuera de los años del convenio
    assert.ok(e('2027-01-04', { farmacia: 'CERCANA' }).farmacia);
    assert.equal(e('2027-01-04', { farmacia: 'OTRA', persona_guardia_id: CLARA }).farmacia, 'La farmacia ajena (OTRA) no lleva personas');
    assert.equal(e('2027-01-04', { farmacia: 'OTRA', persona_apoyo_sabado_id: ELENA }).farmacia, 'La farmacia ajena (OTRA) no lleva personas');
    assert.equal(e('2027-01-04', { farmacia: 'RITA' }).persona_guardia_id, 'Elige la persona de guardia');
    assert.equal(e('2027-01-04', { farmacia: 'PIO', persona_guardia_id: CLARA, persona_apoyo_sabado_id: CLARA }).persona_apoyo_sabado_id, 'El apoyo del sábado tiene que ser otra persona');
    assert.ok(e('2027-01-04', { farmacia: 'PIO', persona_guardia_id: 'x' }).persona_guardia_id);
    assert.equal(e('2027-01-04', { farmacia: 'OTRA', nota: 'x' }).nota, 'Campo no admitido');
  });
  test('festivo: fecha de los años del convenio y nombre de 1 a 60 caracteres; guardia de festivo: farmacia y persona', () => {
    assert.deepEqual(validarFestivo({ fecha: '2027-01-01', nombre: '  Año   Nuevo ' }), { ok: true, fecha: '2027-01-01', nombre: 'Año Nuevo' });
    for (const b of [{ fecha: '2027-01-01', nombre: '' }, { fecha: '2027-01-01', nombre: 'x'.repeat(61) }, { fecha: '2025-12-25', nombre: 'Navidad' },
      { fecha: '2027-02-30', nombre: 'x' }, { fecha: '2027-01-01', nombre: '<b>' }, { fecha: '2027-01-01', nombre: 'x', ambito: 'LOCAL' }, null]) {
      assert.equal(validarFestivo(b).ok, false, JSON.stringify(b));
    }
    assert.ok(validarFestivo({ fecha: '2027-01-01', nombre: 'x'.repeat(60) }).ok);
    assert.deepEqual(validarGuardiaFestivo({ farmacia: 'RITA' }), { ok: true, farmacia: 'RITA', persona_id: null }); // persona por defecto
    assert.equal(validarGuardiaFestivo({ farmacia: 'OTRA', persona_id: AINA }).ok, false);
    assert.equal(validarGuardiaFestivo({ farmacia: 'PIO', persona_id: AINA, fecha: '2027-01-01' }).ok, false);
  });
});

describe('reglas de personas (fichas vigentes)', () => {
  const a = nuevo();
  const g = a.guardiasTa3;
  const ficha = (id: string) => a.trabajadoras('AMBAS', true).trabajadoras.find((t) => t.id === id);
  test('persona de esa farmacia y de alta; titular permitido; apoyo distinto; OTRA sin personas', () => {
    assert.equal(reglasSemana(semana({}), ficha), null);
    assert.equal(reglasSemana(semana({ persona_guardia_id: TITULAR_PIO }), ficha), null); // el titular puede hacer guardia
    assert.equal(reglasSemana(semana({ farmacia: 'RITA', persona_guardia_id: AINA, persona_apoyo_sabado_id: null }), ficha), 'PERSONA_NO_VALIDA');
    assert.equal(reglasSemana(semana({ persona_apoyo_sabado_id: MARTA }), ficha), 'PERSONA_NO_VALIDA'); // apoyo de otra farmacia
    assert.equal(reglasSemana(semana({ persona_apoyo_sabado_id: CLARA }), ficha), 'APOYO_IGUAL_GUARDIA');
    assert.equal(reglasSemana(semana({ farmacia: 'OTRA' }), ficha), 'OTRA_SIN_PERSONAS');
    assert.equal(reglasSemana(semana({ farmacia: 'OTRA', persona_guardia_id: null, persona_apoyo_sabado_id: null }), ficha), null);
    // Paula entra el 1 jul 2026: no puede hacer guardia ni apoyo antes.
    assert.equal(reglasSemana(semana({ lunes: '2026-06-22', farmacia: 'RITA', persona_guardia_id: PAULA, persona_apoyo_sabado_id: null }), ficha), 'PERSONA_NO_VALIDA');
    assert.equal(reglasSemana(semana({ lunes: '2026-07-06', farmacia: 'RITA', persona_guardia_id: PAULA, persona_apoyo_sabado_id: null }), ficha), null);
  });
  test('de baja o anulada: ya no puede; el almacén aplica las mismas reglas', () => {
    a.darDeBaja(CLARA, '2027-01-09', AUTOR_HISTORIAL); // sábado: el domingo ya no está de alta
    assert.equal(g.guardarSemana(semana({})), 'PERSONA_NO_VALIDA');
    assert.equal(typeof g.guardarSemana(semana({ persona_guardia_id: ELENA, persona_apoyo_sabado_id: CLARA })), 'object'); // apoyo: solo el sábado
    a.anular(ELENA, AUTOR_HISTORIAL);
    assert.equal(g.guardarSemana(semana({ persona_guardia_id: AINA, persona_apoyo_sabado_id: ELENA })), 'PERSONA_NO_VALIDA');
  });
});

describe('semilla de ejemplo (fixtures/rrhh/guardias.json)', () => {
  const a = nuevo();
  const g = a.guardiasTa3;
  const d = g.datos();
  test('53 semanas de 2026 (29 dic 2025 – 3 ene 2027) rotando PIO, RITA y OTRA; OTRA sin personas; una por semana', () => {
    assert.equal(d.semanas.length, 53);
    assert.deepEqual(d.semanas.slice(0, 4).map((s) => s.farmacia), ['PIO', 'RITA', 'OTRA', 'PIO']);
    assert.ok(d.semanas.filter((s) => s.farmacia === 'OTRA').every((s) => s.persona_guardia_id === null && s.persona_apoyo_sabado_id === null));
    assert.equal(new Set(d.semanas.map((s) => s.lunes)).size, 53);
    assert.deepEqual(semanasDeRotacion(leerSemillaGuardias().rotacion).map((s) => s.lunes), d.semanas.map((s) => s.lunes));
  });
  test('15 festivos de ejemplo de 2026 con su rotación propia; uno sin guardia; Año Nuevo con la persona por defecto', () => {
    assert.equal(d.festivos.length, 15);
    assert.equal(d.guardiasFestivo.length, 14);
    const v = g.vista('2026-01-01', '2026-12-31');
    assert.equal(v.festivos.find((f) => f.fecha === '2026-08-31')?.guardia, null);
    const anio = v.festivos.find((f) => f.fecha === '2026-01-01');
    assert.deepEqual([anio?.guardia?.farmacia, anio?.guardia?.persona?.id, anio?.semana?.guardia?.id], ['PIO', AINA, AINA]);
  });
  test('vista de una semana: guardia, apoyo, iniciales y horas', () => {
    const v = g.vista('2026-11-09', '2026-11-15');
    assert.equal(v.semanas.length, 1);
    const s = v.semanas[0];
    assert.deepEqual([s.farmacia, s.guardia?.id, s.guardia?.iniciales, s.apoyo?.id, s.apoyo?.iniciales, s.horas_guardia, s.horas_apoyo],
      ['PIO', TITULAR_PIO, 'TE', AINA, 'AB', 9.5, 4.5]);
    // Semana del 26 oct: guardia de Rosa; el domingo 1 nov es festivo (guardia de Laura): solo cuenta su sábado.
    const t = g.vista('2026-10-26', '2026-11-01');
    assert.deepEqual([t.semanas[0].guardia?.id, t.semanas[0].horas_guardia, t.semanas[0].festivos], [ROSA, 6.5, ['2026-11-01']]);
    assert.equal(t.festivos[0].guardia?.persona?.id, LAURA);
  });
});

describe('«Guardias del año» (fuera de cómputo)', () => {
  const a = nuevo();
  const g = a.guardiasTa3;
  test('Aina 2026: 5 semanas (47,5 h), 4 sábados de apoyo (18 h), 2 festivos (6 h) = 71,5 h', () => {
    assert.deepEqual(g.resumenPersona(AINA, 2026), {
      anio: 2026, semanas_guardia: 5, sabados_apoyo: 4, festivos_guardia: 2, horas_guardia: 47.5, horas_apoyo: 18, horas_festivo: 6, horas_total: 71.5,
    });
  });
  test('la semana del 28 dic 2026 cuenta en 2027 (año del sábado); festivo en sábado: el apoyo no suma horas', () => {
    assert.equal(g.resumenPersona(SILVIA, 2027).semanas_guardia, 1);
    assert.equal(g.resumenPersona(SILVIA, 2027).horas_guardia, 9.5);
    // Semana del 21 dic 2026 (Clara, apoyo Elena): el sábado 26 es festivo (guardia OTRA).
    const e = g.resumenPersona(ELENA, 2026);
    assert.deepEqual([e.sabados_apoyo, e.horas_apoyo], [10, 9 * 4.5]); // 10 sábados; el 26 dic (festivo) no suma
    const c = g.resumenPersona(CLARA, 2026);
    assert.deepEqual([c.semanas_guardia, c.horas_guardia, c.festivos_guardia], [5, 4 * 9.5 + 3, 2]); // el sábado 26 dic, no
    assert.equal(resumenGuardiasPersona(ROSA, 2026, g.datos()).horas_guardia, 9.5 + 9.5 + 6.5); // semana del 1 nov: 6,5 h
    assert.deepEqual(g.resumenPersona(JUDIT, 2028), { anio: 2028, semanas_guardia: 0, sabados_apoyo: 0, festivos_guardia: 0, horas_guardia: 0, horas_apoyo: 0, horas_festivo: 0, horas_total: 0 });
  });
  test('festivo dado de baja: deja de contar (y su guardia queda anulada)', () => {
    const b = nuevo();
    assert.equal(typeof b.guardiasTa3.anularFestivo('2026-10-12'), 'object');
    assert.equal(b.guardiasTa3.resumenPersona(AINA, 2026).festivos_guardia, 1);
    assert.ok(b.guardiasTa3.datos().guardiasFestivo.find((x) => x.fecha === '2026-10-12')?.anulada);
    assert.equal(b.guardiasTa3.anularFestivo('2026-10-12'), 'SIN_FESTIVO');
  });
});

describe('guardia de festivo: persona por defecto = la de guardia de esa semana si es la misma farmacia', () => {
  test('misma farmacia: la de la semana; otra farmacia: obligatoria; editable; OTRA sin persona; solo en festivos', () => {
    const g = nuevo().guardiasTa3;
    assert.equal(typeof g.crearFestivo('2026-12-31', 'Fin de año (ejemplo)'), 'object');
    assert.equal(g.crearFestivo('2026-12-31', 'Otro'), 'FESTIVO_DUPLICADO');
    // Semana del 28 dic 2026: RITA, Sílvia.
    const r = g.guardarGuardiaFestivo('2026-12-31', 'RITA', null);
    assert.equal(typeof r === 'object' && r.guardia?.persona?.id, SILVIA);
    assert.equal(g.guardarGuardiaFestivo('2026-12-31', 'PIO', null), 'PERSONA_OBLIGATORIA');
    const e = g.guardarGuardiaFestivo('2026-12-31', 'RITA', JUDIT); // editable
    assert.equal(typeof e === 'object' && e.guardia?.persona?.id, JUDIT);
    assert.equal(g.guardarGuardiaFestivo('2026-12-31', 'RITA', AINA), 'PERSONA_NO_VALIDA');
    assert.equal(g.guardarGuardiaFestivo('2026-12-31', 'OTRA', JUDIT), 'OTRA_SIN_PERSONAS');
    const o = g.guardarGuardiaFestivo('2026-12-31', 'OTRA', null);
    assert.equal(typeof o === 'object' && o.guardia?.persona, null);
    assert.equal(g.guardarGuardiaFestivo('2026-12-30', 'RITA', JUDIT), 'NO_ES_FESTIVO');
    assert.equal(g.datos().guardiasFestivo.filter((x) => x.fecha === '2026-12-31' && !x.anulada).length, 1); // una por festivo
  });
});

describe('calendario: rellenar salta festivos; pintar sobre festivo se permite con aviso', () => {
  const aplicar = (a: AdaptadorRrhhFixtures, cuerpo: unknown) => {
    const v = validarPeticionEventos(cuerpo);
    assert.ok(v.ok);
    return a.cambiarEventos((v as { peticion: PeticionEventos }).peticion, AUTOR_HISTORIAL) as ResultadoCambioDTO;
  };
  test('rellenar la semana del 7 dic 2026 no crea nada el 8 (La Inmaculada); un festivo nuevo también se salta', () => {
    const a = nuevo();
    aplicar(a, { accion: 'RELLENAR', trabajadora_ids: [AINA], desde: '2026-12-07', hasta: '2026-12-13' });
    assert.deepEqual(a.eventos().filter((e) => e.trabajadora_id === AINA && e.fecha >= '2026-12-07' && e.fecha <= '2026-12-13').map((e) => e.fecha).sort(),
      ['2026-12-07', '2026-12-07', '2026-12-09', '2026-12-09', '2026-12-10', '2026-12-10', '2026-12-11', '2026-12-11']);
    a.guardiasTa3.crearFestivo('2027-03-19', 'Sant Josep (ejemplo)');
    const r = aplicar(a, { accion: 'RELLENAR', trabajadora_ids: [AINA], desde: '2027-03-15', hasta: '2027-03-21' });
    assert.equal(r.cambio?.fechas, 4);
    // Sin festivos (otra semilla): el 8 sí se rellena.
    const b = crearAdaptadorRrhhFixtures({ guardias: null });
    aplicar(b, { accion: 'RELLENAR', trabajadora_ids: [AINA], desde: '2026-12-07', hasta: '2026-12-13' });
    assert.ok(b.eventos().some((e) => e.trabajadora_id === AINA && e.fecha === '2026-12-08'));
  });
  test('pintar el 8 dic: se pinta y avisa (festivos_pintados); fuera de festivos, sin aviso; confirmar por rango no salta festivos', () => {
    const a = nuevo();
    const r = aplicar(a, { accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ trabajadora_id: AINA, fecha: '2026-12-08' }, { trabajadora_id: AINA, fecha: '2026-12-09' }] });
    assert.deepEqual(r.festivos_pintados, ['2026-12-08']);
    assert.ok(a.eventos().some((e) => e.trabajadora_id === AINA && e.fecha === '2026-12-08' && e.tipo === 'VACACIONES'));
    const s = aplicar(a, { accion: 'PINTAR', tipo: 'BAJA', celdas: [{ trabajadora_id: AINA, fecha: '2026-12-10' }] });
    assert.equal(s.festivos_pintados, undefined);
    const c = aplicar(a, { accion: 'CONFIRMAR', trabajadora_ids: [AINA], desde: '2026-12-07', hasta: '2026-12-13' });
    assert.ok(c.cambio !== null && c.cambio.n >= 2 && c.festivos_pintados === undefined);
  });
});

describe('API /api/rrhh/guardias y /api/rrhh/festivos (FIXTURES)', async () => {
  const app = await crearServidor('FIXTURES');
  after(() => app.close());
  const H = { host: '127.0.0.1:4747' };
  const login = await app.inject({
    method: 'POST', url: '/api/login', headers: { ...H, 'content-type': 'application/x-www-form-urlencoded' },
    payload: new URLSearchParams({ usuario: USUARIO, clave: CLAVE_FIXTURES, destino: '/' }).toString(),
  });
  const cookie = String(login.headers['set-cookie']).split(';')[0];
  const W = { ...H, cookie, origin: 'http://127.0.0.1:4747', 'content-type': 'application/json' };
  const get = (url: string, con = true) => app.inject({ method: 'GET', url, headers: con ? { ...H, cookie } : H });
  const put = (url: string, body: unknown) => app.inject({ method: 'PUT', url, headers: W, payload: JSON.stringify(body) });
  const post = (url: string, body: unknown) => app.inject({ method: 'POST', url, headers: W, payload: JSON.stringify(body) });

  test('lectura: sesión obligatoria; año o rango validados; estado con guardias disponibles', async () => {
    assert.equal((await get('/api/rrhh/guardias?anio=2026', false)).statusCode, 401);
    const r = await get('/api/rrhh/guardias?anio=2026');
    assert.equal(r.statusCode, 200);
    assert.deepEqual([r.json().disponible, r.json().semanas.length, r.json().festivos.length], [true, 53, 15]);
    const s = await get('/api/rrhh/guardias?desde=2026-11-09&hasta=2026-11-15');
    assert.equal(s.json().semanas[0].apoyo.nombre, 'Aina Bosch Ferrer');
    for (const q of ['anio=2025', 'anio=2026&desde=2026-01-01', 'desde=2026-11-15&hasta=2026-11-09', 'desde=2026-01-01', 'desde=2025-01-01&hasta=2025-01-07', 'desde=2026-01-01&hasta=2027-03-01']) {
      assert.equal((await get(`/api/rrhh/guardias?${q}`)).statusCode, 400, q);
    }
    assert.equal((await get('/api/rrhh/estado')).json().guardias_disponibles, true);
  });
  test('guardia semanal: guarda, edita y aplica las reglas (400 / 409); sin origen, 403', async () => {
    const ok = await put('/api/rrhh/guardias/2027-01-04', { farmacia: 'PIO', persona_guardia_id: CLARA, persona_apoyo_sabado_id: ELENA });
    assert.equal(ok.statusCode, 200, ok.body);
    assert.deepEqual([ok.json().guardia.id, ok.json().apoyo.id, ok.json().horas_guardia], [CLARA, ELENA, 9.5]);
    const ed = await put('/api/rrhh/guardias/2027-01-04', { farmacia: 'OTRA' });
    assert.deepEqual([ed.statusCode, ed.json().farmacia, ed.json().guardia, ed.json().horas_guardia], [200, 'OTRA', null, 0]);
    assert.equal((await put('/api/rrhh/guardias/2027-01-04', { farmacia: 'OTRA', persona_guardia_id: CLARA })).statusCode, 400);
    assert.equal((await put('/api/rrhh/guardias/2027-01-05', { farmacia: 'OTRA' })).statusCode, 400);
    const ajena = await put('/api/rrhh/guardias/2027-01-04', { farmacia: 'RITA', persona_guardia_id: AINA });
    assert.deepEqual([ajena.statusCode, ajena.json().error], [409, 'PERSONA_NO_VALIDA']);
    assert.equal((await put('/api/rrhh/guardias/2027-01-04', { farmacia: 'PIO', persona_guardia_id: TITULAR_PIO })).statusCode, 200); // titular
    const sinOrigen = await app.inject({ method: 'PUT', url: '/api/rrhh/guardias/2027-01-04', headers: { ...H, cookie, 'content-type': 'application/json' }, payload: '{"farmacia":"OTRA"}' });
    assert.equal(sinOrigen.statusCode, 403);
    const sem = (await get('/api/rrhh/guardias?desde=2027-01-04&hasta=2027-01-10')).json().semanas[0];
    assert.deepEqual([sem.farmacia, sem.guardia.id, sem.apoyo], ['PIO', TITULAR_PIO, null]);
  });
  test('festivos: alta (201), duplicado (409), guardia por defecto y editable, baja con confirmación', async () => {
    const a = await post('/api/rrhh/festivos', { fecha: '2027-01-01', nombre: 'Año Nuevo' });
    assert.equal(a.statusCode, 201, a.body);
    assert.equal((await post('/api/rrhh/festivos', { fecha: '2027-01-01', nombre: 'Otro' })).json().error, 'FESTIVO_DUPLICADO');
    assert.equal((await post('/api/rrhh/festivos', { fecha: '2027-01-02', nombre: 'x'.repeat(61) })).statusCode, 400);
    // 1 ene 2027 cae en la semana del 28 dic 2026 (RITA, Sílvia): por defecto, Sílvia.
    const g = await put('/api/rrhh/festivos/2027-01-01/guardia', { farmacia: 'RITA' });
    assert.deepEqual([g.statusCode, g.json().guardia.persona.id], [200, SILVIA]);
    assert.equal((await put('/api/rrhh/festivos/2027-01-01/guardia', { farmacia: 'PIO' })).json().error, 'PERSONA_OBLIGATORIA');
    assert.equal((await put('/api/rrhh/festivos/2027-01-01/guardia', { farmacia: 'RITA', persona_id: MARTA })).json().guardia.persona.id, MARTA);
    assert.equal((await put('/api/rrhh/festivos/2027-01-05/guardia', { farmacia: 'OTRA' })).json().error, 'NO_ES_FESTIVO');
    assert.equal((await put('/api/rrhh/festivos/2027-01-01/anular', {})).statusCode, 400); // sin confirmar
    assert.equal((await put('/api/rrhh/festivos/2027-01-01/anular', { confirmar: true })).statusCode, 200);
    assert.equal((await put('/api/rrhh/festivos/2027-01-01/anular', { confirmar: true })).json().error, 'SIN_FESTIVO');
    assert.equal((await get('/api/rrhh/guardias?anio=2027')).json().festivos.length, 0);
  });
  test('ficha anual: «Guardias del año» (no cambia ninguna cifra de horas)', async () => {
    const r = (await get(`/api/rrhh/trabajadoras/${AINA}/anual?anio=2026&hoy=2026-11-13`)).json();
    assert.deepEqual([r.guardias.semanas_guardia, r.guardias.horas_total], [5, 71.5]);
  });
  test('TA3-2: ficha anual: el festivo dado de alta hace de puente en las vacaciones; dado de baja, ya no', async () => {
    const p = await post('/api/rrhh/eventos', { accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ trabajadora_id: AINA, fecha: '2026-12-24' }, { trabajadora_id: AINA, fecha: '2026-12-28' }] });
    assert.equal(p.statusCode, 200, p.body);
    const periodo = async () => (await get(`/api/rrhh/trabajadoras/${AINA}/anual?anio=2026&hoy=2026-11-13`)).json().ficha.vacaciones.periodos
      .filter((x: { desde: string }) => x.desde >= '2026-12-24').map((x: { desde: string; dias: number }) => [x.desde, x.dias]);
    assert.deepEqual(await periodo(), [['2026-12-24', 5]]);
    const r = (await get('/api/rrhh/fichas?farmacia=PIO&anio=2026&hoy=2026-11-13')).json().filas.find((f: { trabajadora: { id: string } }) => f.trabajadora.id === AINA);
    assert.ok(r.vacaciones.periodos.some((x: { desde: string; dias: number }) => x.desde === '2026-12-24' && x.dias === 5)); // también en el resumen
    assert.equal((await put('/api/rrhh/festivos/2026-12-25/anular', { confirmar: true })).statusCode, 200);
    assert.deepEqual(await periodo(), [['2026-12-24', 1], ['2026-12-28', 1]]);
  });
  test('escritura: solo las rutas previstas; nunca DELETE', () => {
    for (const [m, u] of [['PUT', '/api/rrhh/guardias/2027-01-04'], ['POST', '/api/rrhh/festivos'], ['PUT', '/api/rrhh/festivos/2027-01-01/anular'], ['PUT', '/api/rrhh/festivos/2027-01-01/guardia']]) {
      assert.equal(esEscrituraRrhh(m, u), true, `${m} ${u}`);
    }
    for (const [m, u] of [['DELETE', '/api/rrhh/festivos/2027-01-01'], ['POST', '/api/rrhh/guardias/2027-01-04'], ['PUT', '/api/rrhh/festivos/2027-01-01'], ['PATCH', '/api/rrhh/guardias/2027-01-04']]) {
      assert.equal(esEscrituraRrhh(m, u), false, `${m} ${u}`);
    }
  });
});

describe('modo REAL: «Pendiente de tablas en Supabase» (lectura sin datos, escritura 503)', async () => {
  // Adaptador sin almacén de TA3 (como RRHH_REAL hoy).
  const { guardiasTa3: _g, ...sinTa3 } = crearAdaptadorRrhhFixtures();
  const app = Fastify();
  registrarRrhh(app, { modo: 'REAL', quien: 'Marc', adaptador: sinTa3, sesionValida: () => true });
  await app.ready();
  after(() => app.close());
  const H = { host: '127.0.0.1:4747' };
  const W = { ...H, origin: 'http://127.0.0.1:4747', 'content-type': 'application/json' };

  test('estado sin guardias; lectura { disponible: false, mensaje }; cada escritura 503 TA3_PENDIENTE; ficha anual sin guardias', async () => {
    assert.equal((await app.inject({ method: 'GET', url: '/api/rrhh/estado', headers: H })).json().guardias_disponibles, false);
    const r = await app.inject({ method: 'GET', url: '/api/rrhh/guardias?anio=2026', headers: H });
    assert.deepEqual(r.json(), { disponible: false, mensaje: TEXTO_TA3_PENDIENTE });
    for (const [method, url, body] of [
      ['PUT', '/api/rrhh/guardias/2027-01-04', { farmacia: 'OTRA' }], ['POST', '/api/rrhh/festivos', { fecha: '2027-01-01', nombre: 'Año Nuevo' }],
      ['PUT', '/api/rrhh/festivos/2027-01-01/anular', { confirmar: true }], ['PUT', '/api/rrhh/festivos/2027-01-01/guardia', { farmacia: 'OTRA' }],
    ] as const) {
      const e = await app.inject({ method, url, headers: W, payload: JSON.stringify(body) });
      assert.deepEqual([e.statusCode, e.json()], [503, { error: ERROR_TA3_PENDIENTE, mensaje: TEXTO_TA3_PENDIENTE }], url);
    }
    const f = await app.inject({ method: 'GET', url: `/api/rrhh/trabajadoras/${AINA}/anual?anio=2026&hoy=2026-11-13`, headers: H });
    assert.equal(f.json().guardias, null);
  });
});
