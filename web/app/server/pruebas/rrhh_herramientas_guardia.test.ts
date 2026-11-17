// TA3-4: herramientas de guardia del calendario de Trabajadores (Guardia, Apoyo sábado, Guardia otra farmacia, Festivo
// y Goma sobre sus marcas) y deshacer. Planes puros (reglas de TA3-REAL antes de escribir, confirmación al sustituir
// otra farmacia o dar de baja un festivo, pasos inversos por clave), marcas de la capa del calendario, rutas nuevas de
// la goma y una ida y vuelta completa por la API en FIXTURES (deshacer deja todo como estaba). Uso: npm run test:unit
import assert from 'node:assert/strict';
import { after, describe, test } from 'node:test';
import Fastify from 'fastify';
import { crearAdaptadorRrhhFixtures, type AdaptadorRrhhFixtures } from '../rrhh/adaptador_fixtures.ts';
import type { Trabajadora } from '../rrhh/contrato.ts';
import {
  candidatasSemana, contextoGuardias, esAviso, marcasGuardia, peticionGuardia, planApoyo, planFestivo, planGomaApoyo, planGomaFestivo,
  planGomaGuardiaFestivo, planGomaSemana, planGuardia, planOtra, planSemanaElegida, restaurarFestivo,
  type ContextoGuardias, type OpGuardia, type PlanGuardia, type ResultadoPlan,
} from '../rrhh/herramientas_guardia.ts';
import { esEscrituraRrhh, registrarRrhh } from '../rrhh/rutas.ts';

const ID = (n: number) => `e0000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const AINA = ID(1); const CLARA = ID(2); const ELENA = ID(4); const LAURA = ID(11); const MARTA = ID(12); const TITULAR_PIO = ID(21);

function nuevo(): AdaptadorRrhhFixtures {
  let n = 0;
  return crearAdaptadorRrhhFixtures({ nuevoId: () => `f4000000-0000-4000-8000-${String(++n).padStart(12, '0')}`, ahora: () => '2026-11-16T10:00:00.000Z' });
}
const fichasDe = (a: AdaptadorRrhhFixtures) => a.trabajadoras('AMBAS', false).trabajadoras;
const ctxDe = (a: AdaptadorRrhhFixtures, desde = '2026-10-01', hasta = '2027-03-31', fichas: Trabajadora[] = fichasDe(a)): ContextoGuardias =>
  contextoGuardias(a.guardiasTa3.vista(desde, hasta), fichas);
const plan = (r: ResultadoPlan): PlanGuardia => { assert.ok(!esAviso(r), JSON.stringify(r)); return r as PlanGuardia; };
const aviso = (r: ResultadoPlan): string => { assert.ok(esAviso(r), JSON.stringify(r)); return (r as { aviso: string }).aviso; };

describe('Guardia: clic en una persona → guardia de su farmacia toda la semana; en un festivo, guardia del festivo', () => {
  const a = nuevo();
  const ctx = ctxDe(a);
  test('semana sin asignar (4–10 ene 2027): guardia PIO de Aina, sin apoyo; deshacer = anular la semana', () => {
    const p = plan(planGuardia(ctx, AINA, '2027-01-06')); // miércoles: cuenta toda la semana
    assert.deepEqual(p.op, { k: 'semana', lunes: '2027-01-04', farmacia: 'PIO', guardia: AINA, apoyo: null });
    assert.deepEqual(p.inversa, [{ k: 'anular_semana', lunes: '2027-01-04' }]);
    assert.equal(p.confirmar, null);
    assert.equal(p.texto, 'Guardia PIO: Aina Bosch Ferrer, semana 4–10 ene 2027');
  });
  test('semana PIO (9 nov 2026: titular, apoyo Aina): sustituye la guardia y conserva el apoyo; si el apoyo pasa a guardia, sin apoyo', () => {
    const p = plan(planGuardia(ctx, CLARA, '2026-11-12'));
    assert.deepEqual(p.op, { k: 'semana', lunes: '2026-11-09', farmacia: 'PIO', guardia: CLARA, apoyo: AINA });
    assert.deepEqual(p.inversa, [{ k: 'semana', lunes: '2026-11-09', farmacia: 'PIO', guardia: TITULAR_PIO, apoyo: AINA }]);
    assert.equal(p.confirmar, null); // misma farmacia: sin pregunta
    const q = plan(planGuardia(ctx, AINA, '2026-11-09'));
    assert.deepEqual([q.op.k === 'semana' && q.op.guardia, q.op.k === 'semana' && q.op.apoyo], [AINA, null]);
    assert.match(aviso(planGuardia(ctx, TITULAR_PIO, '2026-11-15')), /ya es la guardia de la semana 9–15 nov 2026/);
  });
  test('semana de otra farmacia (RITA u OTRA): pide confirmación y la sustituye', () => {
    const p = plan(planGuardia(ctx, AINA, '2026-12-09')); // semana del 7 dic: RITA (Marta)
    assert.equal(p.confirmar, 'La semana 7–13 dic 2026 es de RITA (Marta Vila Soler). ¿Sustituirla por la guardia de PIO (Aina Bosch Ferrer)?');
    assert.deepEqual(p.op, { k: 'semana', lunes: '2026-12-07', farmacia: 'PIO', guardia: AINA, apoyo: null }); // el apoyo de RITA no sigue
    const o = plan(planGuardia(ctx, LAURA, '2026-12-16')); // 14 dic: OTRA
    assert.match(o.confirmar ?? '', /es de OTRA \(farmacia ajena\)\. ¿Sustituirla por la guardia de RITA \(Laura Serra Coll\)\?/);
    assert.deepEqual(o.inversa, [{ k: 'semana', lunes: '2026-12-14', farmacia: 'OTRA', guardia: null, apoyo: null }]);
  });
  test('persona no de alta el sábado y el domingo: aviso llano y nada que guardar', () => {
    const fichas = fichasDe(a).map((t) => (t.id === AINA ? { ...t, fecha_baja: '2027-01-08' } : t));
    const c = ctxDe(a, '2026-10-01', '2027-03-31', fichas);
    assert.equal(aviso(planGuardia(c, AINA, '2027-01-05')),
      'Aina Bosch Ferrer no está de alta el sábado y el domingo de la semana 4–10 ene 2027: no puede hacer la guardia. No se ha guardado nada.');
    assert.match(aviso(planGuardia(c, ID(999), '2027-01-05')), /ya no está activa/);
  });
  test('en un festivo (8 dic, guardia PIO de Clara): guardia del festivo; otra farmacia pide confirmación; deshacer = la de antes', () => {
    const p = plan(planGuardia(ctx, ELENA, '2026-12-08'));
    assert.deepEqual(p.op, { k: 'guardia_festivo', fecha: '2026-12-08', farmacia: 'PIO', persona: ELENA });
    assert.deepEqual(p.inversa, [{ k: 'guardia_festivo', fecha: '2026-12-08', farmacia: 'PIO', persona: CLARA }]);
    assert.equal(p.confirmar, null);
    const r = plan(planGuardia(ctx, MARTA, '2026-12-08'));
    assert.match(r.confirmar ?? '', /tiene guardia de PIO \(Clara Roig Pujol\)\. ¿Sustituirla por RITA \(Marta Vila Soler\)\?/);
    assert.match(aviso(planGuardia(ctx, CLARA, '2026-12-08')), /ya está de guardia en La Inmaculada/);
  });
  test('sin datos de guardia del periodo: pide recargar (falla cerrado)', () => {
    assert.match(aviso(planGuardia(contextoGuardias(null, fichasDe(a)), AINA, '2027-01-05')), /recarga la página/);
  });
});

describe('Apoyo sábado: en un sábado de una semana con guardia de su farmacia', () => {
  const a = nuevo();
  const ctx = ctxDe(a);
  test('apoyo de Clara el 14 nov (semana PIO): conserva la guardia; deshacer = el apoyo de antes', () => {
    const p = plan(planApoyo(ctx, CLARA, '2026-11-14'));
    assert.deepEqual(p.op, { k: 'semana', lunes: '2026-11-09', farmacia: 'PIO', guardia: TITULAR_PIO, apoyo: CLARA });
    assert.deepEqual(p.inversa, [{ k: 'semana', lunes: '2026-11-09', farmacia: 'PIO', guardia: TITULAR_PIO, apoyo: AINA }]);
    assert.equal(p.texto, 'Apoyo sábado PIO: Clara Roig Pujol, 14 nov 2026');
  });
  test('avisos y nada guardado: no es sábado; sin guardia de su farmacia; es la guardia; ya es el apoyo', () => {
    assert.match(aviso(planApoyo(ctx, CLARA, '2026-11-13')), /El apoyo se pinta en el sábado/);
    assert.equal(aviso(planApoyo(ctx, LAURA, '2026-11-14')), 'Ese fin de semana no hay guardia de RITA: pinta antes la guardia. No se ha guardado nada.');
    assert.match(aviso(planApoyo(ctx, AINA, '2027-01-09')), /no hay guardia de PIO/); // semana sin asignar
    assert.match(aviso(planApoyo(ctx, TITULAR_PIO, '2026-11-14')), /tiene que ser otra persona/);
    assert.match(aviso(planApoyo(ctx, AINA, '2026-11-14')), /ya es el apoyo/);
    assert.match(aviso(planApoyo(ctx, AINA, '2026-12-19')), /no hay guardia de PIO/); // semana del 14 dic: OTRA
  });
});

describe('Guardia otra farmacia y Festivo (cabecera del día)', () => {
  const a = nuevo();
  const ctx = ctxDe(a);
  test('OTRA: la semana pasa a farmacia ajena (con confirmación si tenía guardia); en un festivo, su guardia', () => {
    const p = plan(planOtra(ctx, '2026-11-11'));
    assert.deepEqual(p.op, { k: 'semana', lunes: '2026-11-09', farmacia: 'OTRA', guardia: null, apoyo: null });
    assert.match(p.confirmar ?? '', /tiene guardia de PIO \(Titular de ejemplo\)\. ¿Sustituirla por OTRA \(farmacia ajena\)\?/);
    const v = plan(planOtra(ctx, '2027-01-05'));
    assert.equal(v.confirmar, null); // sin asignar
    assert.match(aviso(planOtra(ctx, '2026-12-15')), /ya es de OTRA/);
    const f = plan(planOtra(ctx, '2026-12-08'));
    assert.deepEqual(f.op, { k: 'guardia_festivo', fecha: '2026-12-08', farmacia: 'OTRA', persona: null });
    assert.match(f.confirmar ?? '', /¿Sustituirla por OTRA/);
  });
  test('Festivo: nombre 1–60 y ámbito (por defecto local); uno por día; deshacer = darlo de baja', () => {
    const p = plan(planFestivo(ctx, '2027-03-19', '  Sant   Josep '));
    assert.deepEqual(p.op, { k: 'festivo', fecha: '2027-03-19', nombre: 'Sant Josep', ambito: 'LOCAL' });
    assert.deepEqual(p.inversa, [{ k: 'anular_festivo', fecha: '2027-03-19' }]);
    assert.equal(p.texto, 'Festivo: Sant Josep (19 mar 2027, local)');
    assert.equal(plan(planFestivo(ctx, '2027-03-19', 'Sant Josep', 'AUTONOMICO')).op.k === 'festivo' && 'AUTONOMICO', 'AUTONOMICO');
    assert.match(aviso(planFestivo(ctx, '2026-12-08', 'Otra')), /Ese día ya es festivo \(La Inmaculada\)/);
    assert.match(aviso(planFestivo(ctx, '2027-03-19', '')), /Escribe el nombre del festivo/);
    assert.match(aviso(planFestivo(ctx, '2027-03-19', 'x'.repeat(61))), /Máximo 60 caracteres/);
  });
});

describe('Goma sobre las marcas', () => {
  const a = nuevo();
  const ctx = ctxDe(a, '2026-08-01');
  test('G (semana), A (apoyo), OTRA, GF (guardia de festivo) y festivo (con confirmación: arrastra su guardia)', () => {
    const s = plan(planGomaSemana(ctx, '2026-11-09'));
    assert.deepEqual([s.op, s.inversa], [{ k: 'anular_semana', lunes: '2026-11-09' }, [{ k: 'semana', lunes: '2026-11-09', farmacia: 'PIO', guardia: TITULAR_PIO, apoyo: AINA }]]);
    const o = plan(planGomaSemana(ctx, '2026-12-14'));
    assert.deepEqual(o.inversa, [{ k: 'semana', lunes: '2026-12-14', farmacia: 'OTRA', guardia: null, apoyo: null }]);
    assert.match(aviso(planGomaSemana(ctx, '2027-01-04')), /no tiene guardia/);
    const ap = plan(planGomaApoyo(ctx, '2026-11-09'));
    assert.deepEqual(ap.op, { k: 'semana', lunes: '2026-11-09', farmacia: 'PIO', guardia: TITULAR_PIO, apoyo: null });
    assert.match(aviso(planGomaApoyo(ctx, '2026-12-14')), /no tiene apoyo/);
    const gf = plan(planGomaGuardiaFestivo(ctx, '2026-12-08'));
    assert.deepEqual([gf.op, gf.inversa], [{ k: 'anular_guardia_festivo', fecha: '2026-12-08' }, [{ k: 'guardia_festivo', fecha: '2026-12-08', farmacia: 'PIO', persona: CLARA }]]);
    assert.match(aviso(planGomaGuardiaFestivo(ctx, '2026-08-31')), /no tiene guardia/); // sin asignar en la semilla
    const fe = plan(planGomaFestivo(ctx, '2026-12-08'));
    assert.equal(fe.confirmar, '¿Dar de baja el festivo «La Inmaculada» (8 dic 2026)? También se anula su guardia (PIO (Clara Roig Pujol)). No se borra: queda en el historial.');
    // Restaurar tras la goma: alta del festivo y su guardia (por fecha; ids nuevos).
    assert.deepEqual(fe.inversa, [
      { k: 'festivo', fecha: '2026-12-08', nombre: 'La Inmaculada', ambito: 'LOCAL' },
      { k: 'guardia_festivo', fecha: '2026-12-08', farmacia: 'PIO', persona: CLARA },
    ]);
    assert.match(aviso(planGomaFestivo(ctx, '2026-12-09')), /no es festivo/);
    const sinGuardia = ctx.festivo('2026-08-31');
    assert.ok(sinGuardia);
    assert.equal(restaurarFestivo(sinGuardia).length, 1);
  });
});

describe('Año: selector de guardia y apoyo de la semana', () => {
  const a = nuevo();
  const ctx = ctxDe(a);
  test('personas de la farmacia de alta ese fin de semana; guardar con apoyo; mismas reglas', () => {
    const g = candidatasSemana(fichasDe(a), 'RITA', '2027-01-04', 'guardia');
    assert.ok(g.length > 0 && g.every((t) => t.farmacia === 'RITA'));
    assert.deepEqual(candidatasSemana(fichasDe(a), 'OTRA', '2027-01-04', 'guardia'), []);
    const p = plan(planSemanaElegida(ctx, '2027-01-04', LAURA, MARTA));
    assert.deepEqual(p.op, { k: 'semana', lunes: '2027-01-04', farmacia: 'RITA', guardia: LAURA, apoyo: MARTA });
    assert.equal(p.texto, 'Guardia RITA: Laura Serra Coll · apoyo Marta Vila Soler, semana 4–10 ene 2027');
    assert.match(aviso(planSemanaElegida(ctx, '2027-01-04', LAURA, LAURA)), /otra persona/);
    assert.match(aviso(planSemanaElegida(ctx, '2027-01-04', LAURA, AINA)), /tiene que ser de RITA/);
    assert.match(plan(planSemanaElegida(ctx, '2026-11-09', LAURA, null)).confirmar ?? '', /es de PIO/);
    assert.match(aviso(planSemanaElegida(ctx, '2026-11-09', TITULAR_PIO, AINA)), /ya está así/);
  });
});

describe('Marcas del calendario (capa superpuesta) y peticiones', () => {
  const a = nuevo();
  test('G toda la semana (lunes a domingo), A el sábado, GF en el festivo; días OTRA', () => {
    const m = marcasGuardia(a.guardiasTa3.vista('2026-11-01', '2026-12-31'));
    for (let d = 9; d <= 15; d++) {
      const f = `2026-11-${String(d).padStart(2, '0')}`;
      assert.deepEqual([m.de(TITULAR_PIO, f)?.guardia, m.de(TITULAR_PIO, f)?.lunes], ['PIO', '2026-11-09'], f);
    }
    assert.equal(m.de(TITULAR_PIO, '2026-11-16')?.guardia ?? null, null);
    assert.equal(m.de(AINA, '2026-11-14')?.apoyo, 'PIO');
    assert.equal(m.de(AINA, '2026-11-13'), undefined);
    assert.equal(m.de(CLARA, '2026-12-08')?.festivo, 'PIO');
    assert.ok(['2026-12-14', '2026-12-17', '2026-12-20'].every((f) => m.otra.has(f)));
    assert.ok(!m.otra.has('2026-12-21'));
    assert.deepEqual(marcasGuardia(null).otra.size, 0);
  });
  test('cada operación va a una ruta de escritura admitida (PUT/POST, nunca DELETE); anular exige confirmar', () => {
    const ops: OpGuardia[] = [
      { k: 'semana', lunes: '2027-01-04', farmacia: 'PIO', guardia: AINA, apoyo: null }, { k: 'semana', lunes: '2027-01-04', farmacia: 'OTRA', guardia: null, apoyo: null },
      { k: 'anular_semana', lunes: '2027-01-04' }, { k: 'festivo', fecha: '2027-03-19', nombre: 'Sant Josep', ambito: 'LOCAL' },
      { k: 'anular_festivo', fecha: '2027-03-19' }, { k: 'guardia_festivo', fecha: '2027-03-19', farmacia: 'OTRA', persona: null },
      { k: 'anular_guardia_festivo', fecha: '2027-03-19' },
    ];
    for (const op of ops) {
      const p = peticionGuardia(op);
      assert.ok(esEscrituraRrhh(p.metodo, p.ruta), `${p.metodo} ${p.ruta}`);
      if (op.k.startsWith('anular')) assert.deepEqual(p.cuerpo, { confirmar: true });
    }
    assert.deepEqual(peticionGuardia(ops[1]).cuerpo, { farmacia: 'OTRA' });
    assert.deepEqual(peticionGuardia(ops[0]).cuerpo, { farmacia: 'PIO', persona_guardia_id: AINA, persona_apoyo_sabado_id: null });
    for (const [m, u] of [['DELETE', '/api/rrhh/guardias/2027-01-04'], ['PUT', '/api/rrhh/guardias/2027-01-05x/anular'], ['PUT', '/api/rrhh/festivos/2027-01-01/guardia/borrar']]) {
      assert.equal(esEscrituraRrhh(m, u), false, `${m} ${u}`);
    }
  });
});

describe('Almacén FIXTURES: anular semana y guardia de festivo', () => {
  test('anula (no borra); la semana queda sin asignar y el festivo sigue', () => {
    const a = nuevo();
    const g = a.guardiasTa3;
    const s = g.anularSemana('2026-11-09');
    assert.equal(typeof s === 'object' && s.farmacia, null);
    assert.ok(g.datos().semanas.some((x) => x.lunes === '2026-11-09' && x.anulada));
    assert.equal(g.anularSemana('2026-11-09'), 'SIN_GUARDIA');
    const f = g.anularGuardiaFestivo('2026-12-08');
    assert.deepEqual(typeof f === 'object' && [f.nombre, f.guardia], ['La Inmaculada', null]);
    assert.equal(g.anularGuardiaFestivo('2026-12-08'), 'SIN_GUARDIA');
    assert.equal(g.anularGuardiaFestivo('2026-12-09'), 'SIN_FESTIVO');
  });
});

describe('Ida y vuelta por la API (FIXTURES): cada herramienta y deshacer en orden inverso deja todo como estaba', async () => {
  const a = nuevo();
  const app = Fastify();
  registrarRrhh(app, { modo: 'FIXTURES', quien: 'Marc', adaptador: a, sesionValida: () => true });
  await app.ready();
  after(() => app.close());
  const W = { host: '127.0.0.1:4747', origin: 'http://127.0.0.1:4747', 'content-type': 'application/json' };
  const aplicar = async (op: OpGuardia) => {
    const p = peticionGuardia(op);
    const r = await app.inject({ method: p.metodo, url: p.ruta, headers: W, payload: JSON.stringify(p.cuerpo) });
    assert.ok(r.statusCode === 200 || r.statusCode === 201, `${p.ruta}: ${r.body}`);
  };
  const pila: PlanGuardia[] = [];
  const hacer = async (r: ResultadoPlan) => { const p = plan(r); await aplicar(p.op); pila.push(p); };
  const vista = () => JSON.stringify(a.guardiasTa3.vista('2026-11-01', '2027-03-31'));

  test('guardia, apoyo, OTRA, festivo + guardia de festivo, goma de G, A, GF y festivo; deshacer todo', async () => {
    const inicio = vista();
    await hacer(planGuardia(ctxDe(a), LAURA, '2027-01-05'));
    await hacer(planApoyo(ctxDe(a), MARTA, '2027-01-09'));
    await hacer(planGuardia(ctxDe(a), CLARA, '2026-11-10')); // sustituye al titular, conserva a Aina de apoyo
    await hacer(planOtra(ctxDe(a), '2027-01-12'));
    await hacer(planFestivo(ctxDe(a), '2027-03-19', 'Sant Josep', 'AUTONOMICO'));
    await hacer(planGuardia(ctxDe(a), LAURA, '2027-03-19'));
    await hacer(planGomaApoyo(ctxDe(a), '2027-01-04'));
    await hacer(planGomaSemana(ctxDe(a), '2026-11-09'));
    await hacer(planGomaGuardiaFestivo(ctxDe(a), '2026-12-08'));
    await hacer(planGomaFestivo(ctxDe(a), '2027-03-19'));
    const c = ctxDe(a);
    assert.deepEqual([c.semana('2027-01-04')?.guardia?.id, c.semana('2027-01-04')?.apoyo, c.semana('2027-01-11')?.farmacia], [LAURA, null, 'OTRA']);
    assert.deepEqual([c.semana('2026-11-09')?.farmacia, c.festivo('2026-12-08')?.guardia, c.festivo('2027-03-19')], [null, null, undefined]);
    assert.notEqual(vista(), inicio);
    // Deshacer en orden inverso (como la pila del calendario).
    while (pila.length) { const p = pila.pop() as PlanGuardia; for (const op of p.inversa) await aplicar(op); }
    assert.equal(vista(), inicio);
    // El festivo restaurado y luego dado de baja: nada se borró (todas las filas siguen, anuladas).
    assert.ok(a.guardiasTa3.datos().festivos.filter((f) => f.fecha === '2027-03-19').every((f) => f.anulado));
  });
});
