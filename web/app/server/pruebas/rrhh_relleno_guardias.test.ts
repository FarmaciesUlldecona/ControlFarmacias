// TA4-2: relleno automático de las guardias del año por rotación (decisión de Pío, 26/11/2026). Continuidad de la
// rotación semanal y festiva al cambiar de año, persona propuesta por «más tiempo sin hacerlo» (empate alfabético),
// no pisa lo que ya existe, Pascua (2028: 16/4 → Divendres Sant 14/4, Dilluns Pasqua 17/4), festivos de otra fecha
// móvil «a revisar», sin persona disponible, y una ida y vuelta por la API en FIXTURES (deshacer deja todo como
// estaba). Uso: npm run test:unit
import assert from 'node:assert/strict';
import { describe, test } from 'node:test';
import Fastify from 'fastify';
import { crearAdaptadorRrhhFixtures } from '../rrhh/adaptador_fixtures.ts';
import type { Trabajadora } from '../rrhh/contrato.ts';
import type { FarmaciaGuardia, FestivoVista, GuardiasDTO, PersonaGuardia, SemanaGuardiaVista } from '../rrhh/guardias.ts';
import { peticionGuardia, type OpGuardia } from '../rrhh/herramientas_guardia.ts';
import {
  FESTIVOS_PASCUA, ROTACION_FARMACIAS, normalizarNombreFestivo, pascua, personaPropuesta, planRellenoGuardias, siguienteFarmacia,
} from '../rrhh/relleno_guardias.ts';
import { registrarRrhh } from '../rrhh/rutas.ts';

const ficha = (id: string, nombre: string, farmacia: 'PIO' | 'RITA', o: Partial<Trabajadora> = {}): Trabajadora => ({
  id, farmacia, nombre, categoria: 'TECNICA', tipo_jornada: 'COMPLETA', horas_diarias: 8, computa_convenio: true, fecha_alta: '2026-01-01',
  fecha_baja: null, anulada: false, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z', activa: true, ...o,
});
const MARI = ficha('p1', 'Mari Carmen', 'PIO');
const PATRI = ficha('p2', 'Patricia', 'PIO');
const ANA = ficha('p3', 'Ana', 'PIO');
const RAQUEL = ficha('r1', 'Raquel', 'RITA');
const SONIA = ficha('r2', 'Sònia', 'RITA');
const per = (t: Trabajadora): PersonaGuardia => ({ id: t.id, nombre: t.nombre, farmacia: t.farmacia, iniciales: t.nombre.slice(0, 2) });
const semana = (lunes: string, farmacia: FarmaciaGuardia | null, g: Trabajadora | null = null, a: Trabajadora | null = null): SemanaGuardiaVista => ({
  lunes, domingo: lunes, farmacia, guardia: g ? per(g) : null, apoyo: a ? per(a) : null, horas_guardia: 0, horas_apoyo: 0, festivos: [],
});
const festivo = (fecha: string, nombre: string, farmacia: FarmaciaGuardia | null = null, p: Trabajadora | null = null): FestivoVista => ({
  fecha, nombre, ambito: 'LOCAL', guardia: farmacia ? { farmacia, persona: p ? per(p) : null } : null, semana: null,
});
const dto = (anio: number, semanas: SemanaGuardiaVista[], festivos: FestivoVista[]): GuardiasDTO => ({ disponible: true, desde: `${anio}-01-01`, hasta: `${anio}-12-31`, semanas, festivos });
const FICHAS = [MARI, PATRI, ANA, RAQUEL, SONIA];

describe('TA4-2: constantes, Pascua y rotación cíclica', () => {
  test('ROTACION_FARMACIAS = OTRA, PIO, RITA (cíclica); sin anterior, la primera', () => {
    assert.deepEqual(ROTACION_FARMACIAS, ['OTRA', 'PIO', 'RITA']);
    assert.deepEqual([siguienteFarmacia('OTRA'), siguienteFarmacia('PIO'), siguienteFarmacia('RITA'), siguienteFarmacia(null)], ['PIO', 'RITA', 'OTRA', 'OTRA']);
  });
  test('Pascua por algoritmo: 2026 → 5/4, 2027 → 28/3, 2028 → 16/4; FESTIVOS_PASCUA −2 y +1', () => {
    assert.deepEqual([pascua(2026), pascua(2027), pascua(2028), pascua(2019), pascua(2038)], ['2026-04-05', '2027-03-28', '2028-04-16', '2019-04-21', '2038-04-25']);
    assert.deepEqual(FESTIVOS_PASCUA, { 'DIVENDRES SANT': -2, 'DILLUNS PASQUA': 1 });
    assert.equal(normalizarNombreFestivo('  Dilluns   de Pàsqua '), 'DILLUNS DE PASQUA');
    assert.equal(normalizarNombreFestivo('Divendres Sant'), 'DIVENDRES SANT');
  });
});

describe('TA4-2: continuidad de la rotación al cambiar de año (ejemplos de Pío)', () => {
  const previo = dto(2027, [semana('2027-12-20', 'OTRA'), semana('2027-12-27', 'PIO', MARI)], [festivo('2027-12-08', 'Immaculada', 'RITA', RAQUEL), festivo('2027-12-26', 'Sant Esteve', 'OTRA')]);
  const actual = dto(2028, [], [festivo('2028-01-01', 'Any Nou'), festivo('2028-01-06', 'Reis')]);
  const p = planRellenoGuardias({ anio: 2028, previo, actual, fichas: FICHAS });
  test('semanal: 27/12/2027 = PIO → 3/1/2028 = RITA, después OTRA, PIO…', () => {
    assert.deepEqual(p.semanas.slice(0, 4).map((s) => [s.lunes, s.farmacia]), [['2028-01-03', 'RITA'], ['2028-01-10', 'OTRA'], ['2028-01-17', 'PIO'], ['2028-01-24', 'RITA']]);
    assert.equal(p.semanas.at(-1)?.lunes, '2028-12-25'); // la semana es del año de su lunes
    assert.equal(p.semanas.length, 52);
  });
  test('festiva, independiente de la semanal: 26/12/2027 = OTRA → 1/1/2028 = PIO, 6/1 = RITA', () => {
    // Los de 2028 que ya existen y, después, los copiados de 2027 (Immaculada y Sant Esteve, mismo día y mes).
    assert.deepEqual(p.festivas.map((f) => [f.fecha, f.farmacia]), [['2028-01-01', 'PIO'], ['2028-01-06', 'RITA'], ['2028-12-08', 'OTRA'], ['2028-12-26', 'PIO']]);
  });
  test('PIO sin historial de guardia festiva en 12 meses: sin persona disponible (la BD exige persona): no se crea, con aviso', () => {
    assert.equal(p.festivas[0].crear, false);
    assert.ok(p.avisos.some((a) => a.tipo === 'SIN_PERSONA' && a.fecha === '2028-01-01'));
    assert.ok(!p.pasos.some((x) => x.op.k === 'guardia_festivo' && x.op.fecha === '2028-01-01'));
    // RITA: Raquel hizo la del 8/12/2027.
    assert.deepEqual([p.festivas[1].crear, p.festivas[1].persona?.nombre], [true, 'Raquel']);
  });
  test('sin el año anterior: empieza en OTRA, con aviso', () => {
    const q = planRellenoGuardias({ anio: 2028, previo: null, actual, fichas: FICHAS });
    assert.equal(q.semanas[0].farmacia, 'OTRA');
    assert.equal(q.festivas[0].farmacia, 'OTRA');
    assert.ok(q.avisos.some((a) => a.tipo === 'SIN_ANIO_ANTERIOR'));
  });
});

describe('TA4-2: persona propuesta = la que lleva más tiempo sin hacer ese papel (12 meses, de alta; empate alfabético)', () => {
  test('ejemplo de Pío: festivos PIO 2027, último Mari Carmen el 8/12 y Patricia el 18/10 → 1/1/2028 Patricia', () => {
    const previo = dto(2027, [], [festivo('2027-10-18', 'Festa local', 'PIO', PATRI), festivo('2027-12-08', 'Immaculada', 'PIO', MARI), festivo('2027-12-26', 'Sant Esteve', 'OTRA')]);
    const p = planRellenoGuardias({ anio: 2028, previo, actual: dto(2028, [], [festivo('2028-01-01', 'Any Nou')]), fichas: FICHAS });
    assert.deepEqual([p.festivas[0].farmacia, p.festivas[0].persona?.nombre], ['PIO', 'Patricia']);
  });
  test('empate (misma última fecha): orden alfabético; fuera de los 12 meses o de baja no cuenta', () => {
    const hechos = [
      { farmacia: 'PIO' as const, papel: 'G' as const, persona: 'p1', fecha: '2027-06-05' },
      { farmacia: 'PIO' as const, papel: 'G' as const, persona: 'p2', fecha: '2027-06-05' },
      { farmacia: 'PIO' as const, papel: 'G' as const, persona: 'p3', fecha: '2026-12-01' }, // hace más de 12 meses
    ];
    const fichas = new Map(FICHAS.map((t) => [t.id, t]));
    assert.equal(personaPropuesta(hechos, fichas, 'PIO', 'G', '2028-01-08', ['2028-01-08']).persona?.nombre, 'Mari Carmen');
    const baja = new Map(fichas); baja.set('p1', { ...MARI, fecha_baja: '2027-12-31', activa: false });
    assert.equal(personaPropuesta(hechos, baja, 'PIO', 'G', '2028-01-08', ['2028-01-08']).persona?.nombre, 'Patricia');
    assert.equal(personaPropuesta(hechos, fichas, 'PIO', 'G', '2028-01-08', ['2028-01-08'], 'p1').persona?.nombre, 'Patricia'); // excluida (apoyo ≠ guardia)
    assert.deepEqual(personaPropuesta(hechos, fichas, 'PIO', 'A', '2028-01-08', ['2028-01-08']), { persona: null, usado: false });
  });
  test('guardia y apoyo rotan por turnos (lo planificado cuenta); apoyo solo donde ya se usa', () => {
    const previo = dto(2027, [
      semana('2027-11-29', 'PIO', MARI, ANA), semana('2027-12-06', 'RITA', RAQUEL), semana('2027-12-13', 'OTRA'),
      semana('2027-12-20', 'PIO', PATRI, MARI), semana('2027-12-27', 'RITA', SONIA),
    ], []);
    const p = planRellenoGuardias({ anio: 2028, previo, actual: dto(2028, [], []), fichas: FICHAS });
    const pio = p.semanas.filter((s) => s.farmacia === 'PIO').slice(0, 3).map((s) => [s.guardia?.nombre, s.apoyo?.nombre ?? null]);
    // G: Mari (29/11) lleva más que Patricia (20/12) → Mari, Patricia, Mari… ; A: Ana (4/12) antes que Mari (25/12), nunca la guardia.
    assert.deepEqual(pio, [['Mari Carmen', 'Ana'], ['Patricia', 'Mari Carmen'], ['Mari Carmen', 'Ana']]);
    const rita = p.semanas.filter((s) => s.farmacia === 'RITA').slice(0, 2).map((s) => [s.guardia?.nombre, s.apoyo]);
    assert.deepEqual(rita, [['Raquel', null], ['Sònia', null]]); // RITA no usa apoyo
  });
});

describe('TA4-2: no pisa lo que ya existe (solo rellena huecos)', () => {
  test('semanas, festivos y guardias festivas existentes: ningún paso los toca; la rotación sigue desde ellos', () => {
    const previo = dto(2027, [semana('2027-12-27', 'PIO', MARI)], [festivo('2027-12-26', 'Sant Esteve', 'OTRA'), festivo('2027-01-06', 'Reis', 'PIO', MARI)]);
    const actual = dto(2028, [semana('2028-01-03', null), semana('2028-01-10', 'RITA', RAQUEL)], [festivo('2028-01-01', 'Any Nou', 'RITA', SONIA), festivo('2028-01-06', 'Reis')]);
    const p = planRellenoGuardias({ anio: 2028, previo, actual, fichas: FICHAS });
    assert.deepEqual(p.semanas.slice(0, 2).map((s) => [s.lunes, s.farmacia]), [['2028-01-03', 'RITA'], ['2028-01-17', 'OTRA']]);
    assert.ok(!p.pasos.some((x) => (x.op.k === 'semana' && x.op.lunes === '2028-01-10') || ('fecha' in x.op && x.op.fecha === '2028-01-01')));
    // Tras RITA (1/1, existente): Reis OTRA; Sant Esteve (copiado de 2027) PIO.
    assert.deepEqual(p.festivas.map((f) => [f.fecha, f.farmacia]), [['2028-01-06', 'OTRA'], ['2028-12-26', 'PIO']]);
    assert.deepEqual(p.festivos.map((f) => f.nombre), ['Sant Esteve']); // Reis ya existe en 2028 (por nombre): no se propone
    assert.ok(p.pasos.every((x) => ['semana', 'festivo', 'guardia_festivo'].includes(x.op.k))); // nunca anula ni borra
    assert.ok(p.pasos.every((x) => x.inversa.k.startsWith('anular_')));
  });
});

describe('TA4-2: festivos del año nuevo a partir del año anterior', () => {
  const previo = dto(2027, [], [
    festivo('2027-01-06', 'Reis', 'OTRA'), festivo('2027-03-26', 'Divendres Sant', 'PIO', MARI), festivo('2027-03-29', 'Dilluns Pasqua', 'RITA', RAQUEL),
    festivo('2027-05-17', 'Segona Pasqua', 'PIO', PATRI), festivo('2027-12-26', 'Sant Esteve', 'OTRA'),
  ]);
  const p = planRellenoGuardias({ anio: 2028, previo, actual: dto(2028, [], []), fichas: FICHAS });
  test('Pascua 2028 (16/4): Divendres Sant 14/4, Dilluns Pasqua 17/4; el resto, mismo día y mes', () => {
    assert.deepEqual(p.festivos.map((f) => [f.fecha, f.nombre, f.pascua]), [
      ['2028-01-06', 'Reis', false], ['2028-04-14', 'Divendres Sant', true], ['2028-04-17', 'Dilluns Pasqua', true], ['2028-12-26', 'Sant Esteve', false],
    ]);
  });
  test('otra fecha móvil (Segona Pasqua, Pascua +50): no se crea, «festivo a revisar»', () => {
    assert.ok(!p.festivos.some((f) => f.nombre === 'Segona Pasqua'));
    assert.ok(p.avisos.some((a) => a.tipo === 'FESTIVO_A_REVISAR' && a.texto.includes('Segona Pasqua')));
  });
  test('orden de los pasos: festivos, semanas y guardias festivas (que van sobre sus festivos nuevos)', () => {
    const ks = p.pasos.map((x) => x.op.k);
    assert.ok(ks.lastIndexOf('festivo') < ks.indexOf('semana') && ks.lastIndexOf('semana') < ks.indexOf('guardia_festivo'));
    // Rotación festiva desde Sant Esteve 2027 (OTRA): Reis PIO, Divendres Sant RITA, Dilluns Pasqua OTRA, Sant Esteve PIO.
    assert.deepEqual(p.festivas.map((f) => f.farmacia), ['PIO', 'RITA', 'OTRA', 'PIO']);
  });
});

describe('TA4-2: FIXTURES por la API: relleno de 2027 desde 2026, todo pasa las reglas; deshacer deja todo como estaba', () => {
  test('ida y vuelta', async () => {
    let n = 0;
    const a = crearAdaptadorRrhhFixtures({ nuevoId: () => `f5000000-0000-4000-8000-${String(++n).padStart(12, '0')}`, ahora: () => '2026-11-26T10:00:00.000Z' });
    const app = Fastify();
    registrarRrhh(app, { modo: 'FIXTURES', quien: 'Marc', adaptador: a, sesionValida: () => true });
    await app.ready();
    const W = { host: '127.0.0.1:4747', origin: 'http://127.0.0.1:4747', 'content-type': 'application/json' };
    const aplicar = async (op: OpGuardia) => {
      const q = peticionGuardia(op);
      const r = await app.inject({ method: q.metodo, url: q.ruta, headers: W, payload: JSON.stringify(q.cuerpo) });
      assert.ok(r.statusCode === 200 || r.statusCode === 201, `${q.ruta}: ${r.body}`);
    };
    const vista = () => JSON.stringify(a.guardiasTa3.vista('2026-01-01', '2027-12-31'));
    const inicio = vista();
    const p = planRellenoGuardias({ anio: 2027, previo: a.guardiasTa3.vista('2026-01-01', '2026-12-31'), actual: a.guardiasTa3.vista('2027-01-01', '2027-12-31'), fichas: a.trabajadoras('AMBAS', true).trabajadoras });
    // 28/12/2026 = RITA (semilla) → 4/1/2027 = OTRA; 26/12/2026 = OTRA → primer festivo de 2027 = PIO.
    assert.deepEqual([p.semanas[0].lunes, p.semanas[0].farmacia, p.semanas[1].farmacia], ['2027-01-04', 'OTRA', 'PIO']);
    assert.deepEqual([p.festivas[0].fecha, p.festivas[0].farmacia], ['2027-01-01', 'PIO']);
    // Viernes Santo, Lunes de Pascua y Segunda Pascua (fechas móviles con nombre no catalán): a revisar.
    assert.equal(p.avisos.filter((x) => x.tipo === 'FESTIVO_A_REVISAR').length, 3);
    assert.equal(p.festivos.length, 12);
    assert.equal(p.semanas.filter((s) => s.crear).length, 52);
    const hechas: OpGuardia[] = [];
    for (const x of p.pasos) { await aplicar(x.op); hechas.unshift(x.inversa); }
    const v = a.guardiasTa3.vista('2027-01-01', '2027-12-31');
    assert.equal(v.semanas.filter((s) => s.lunes >= '2027-01-04' && s.farmacia !== null).length, 52);
    assert.equal(v.festivos.filter((f) => f.guardia !== null).length, p.festivas.filter((f) => f.crear).length);
    for (const op of hechas) await aplicar(op);
    assert.equal(vista(), inicio);
    assert.ok(a.guardiasTa3.datos().semanas.some((s) => s.lunes === '2027-01-04' && s.anulada)); // anula, no borra
    await app.close();
  });
});
