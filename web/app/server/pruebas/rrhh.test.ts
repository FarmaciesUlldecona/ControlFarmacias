// TA1 Trabajadores: contrato, objetivo anual, historial, validaciones y API (FIXTURES con el servidor completo;
// REAL con una instancia propia de Fastify, sin BD ni .env). Uso: npm run test:unit
import assert from 'node:assert/strict';
import { after, describe, test } from 'node:test';
import Fastify from 'fastify';
import { CLAVE_FIXTURES, USUARIO } from '../acceso.ts';
import { crearServidor } from '../index.ts';
import {
  AUTOR_HISTORIAL, CONVENIO_ANUAL, MENSAJE_PENDIENTE_T1, diferencias, filtroFarmacia, horasSemanales, objetivoAnual, objetivosAnuales,
  porcentajeDerivado, validarFechaBaja,
  validarTrabajadora, type Trabajadora,
} from '../rrhh/contrato.ts';
import { crearAdaptadorRrhhFixtures, leerSemilla } from '../rrhh/adaptador_fixtures.ts';
import { esEscrituraRrhh, registrarRrhh } from '../rrhh/rutas.ts';

const valido = { farmacia: 'PIO', nombre: '  Ana   Prueba ', categoria: 'TECNICO', jornada: 'COMPLETA', horas_diarias: 8, es_titular: false };

describe('convenio y objetivo anual (decisiones T0)', () => {
  test('convenio por año: 2026 1.767 h y 1 día; 2027–2028 1.752 h y 0 días; permiso médico 24 h; referencia 40 h/sem; pendiente de publicación', () => {
    assert.deepEqual(CONVENIO_ANUAL.map((c) => [c.anio, c.jornada_maxima_horas, c.horas_semanales_referencia, c.asuntos_propios_dias, c.permiso_medico_horas, c.estado]), [
      [2026, 1767, 40, 1, 24, 'FIRMADO_PENDIENTE_PUBLICACION'],
      [2027, 1752, 40, 0, 24, 'FIRMADO_PENDIENTE_PUBLICACION'],
      [2028, 1752, 40, 0, 24, 'FIRMADO_PENDIENTE_PUBLICACION'],
    ]);
  });
  test('TA1-2: horas semanales = horas/día × 5; porcentaje DERIVADO = semanales / referencia', () => {
    assert.equal(horasSemanales({ horas_diarias: 8 }), 40);
    assert.equal(horasSemanales({ horas_diarias: 4.5 }), 22.5);
    assert.equal(porcentajeDerivado({ horas_diarias: 8 }, { horas_semanales_referencia: 40 }), 100);
    assert.equal(porcentajeDerivado({ horas_diarias: 4.5 }, { horas_semanales_referencia: 40 }), 56.25);
    // La referencia es configurable por año: con 37,5 h/sem, 7,5 h/día = 100 %.
    assert.equal(porcentajeDerivado({ horas_diarias: 7.5 }, { horas_semanales_referencia: 37.5 }), 100);
  });
  test('objetivo = jornada máxima × semanales / referencia (0,1 h al final); 2026, 4,5 h/día → 993,9 h; titular null', () => {
    const c26 = CONVENIO_ANUAL[0];
    assert.equal(objetivoAnual({ horas_diarias: 8, computa_convenio: true }, c26).objetivo_horas, 1767);
    assert.equal(objetivoAnual({ horas_diarias: 4.5, computa_convenio: true }, c26).objetivo_horas, 993.9); // ejemplo de Pío
    assert.equal(objetivoAnual({ horas_diarias: 4.5, computa_convenio: true }, CONVENIO_ANUAL[1]).objetivo_horas, 985.5);
    assert.equal(objetivoAnual({ horas_diarias: 6, computa_convenio: true }, c26).objetivo_horas, 1325.3);
    assert.equal(objetivoAnual({ horas_diarias: 4.5, computa_convenio: true }, { ...c26, horas_semanales_referencia: 37.5 }).objetivo_horas, 1060.2);
    assert.equal(objetivoAnual({ horas_diarias: 4.5, computa_convenio: false }, c26).objetivo_horas, null);
    assert.deepEqual(objetivosAnuales({ horas_diarias: 8, computa_convenio: true }).map((o) => o.objetivo_horas), [1767, 1752, 1752]);
    const o = objetivoAnual({ horas_diarias: 4.5, computa_convenio: true }, c26);
    assert.deepEqual([o.horas_semanales, o.horas_semanales_referencia, o.porcentaje_derivado], [22.5, 40, 56.25]);
  });
  test('filtro de farmacia: PIO, RITA o AMBAS; nada más', () => {
    for (const v of ['PIO', 'RITA', 'AMBAS']) assert.equal(filtroFarmacia(v), v);
    for (const v of ['pio', 'TODAS', '', null, 1]) assert.equal(filtroFarmacia(v), null);
  });
});

describe('validaciones', () => {
  test('alta válida: nombre normalizado; sin horas: COMPLETA = 8 y MEDIA_MANANA = 4,5', () => {
    const r = validarTrabajadora(valido, 'alta');
    assert.ok(r.ok);
    assert.equal(r.ok && r.datos.nombre, 'Ana Prueba');
    const s = validarTrabajadora({ ...valido, horas_diarias: undefined }, 'alta');
    assert.equal(s.ok && s.datos.horas_diarias, 8);
    const m = validarTrabajadora({ ...valido, jornada: 'MEDIA_MANANA', horas_diarias: undefined }, 'alta');
    assert.equal(m.ok && m.datos.horas_diarias, 4.5);
    for (const h of [4.5, 0.25, 7.75, 4.15]) assert.ok(validarTrabajadora({ ...valido, jornada: 'MEDIA_MANANA', horas_diarias: h }, 'alta').ok, String(h));
  });
  test('TA1-3: MEDIA_TARDE: por defecto 3,5 h (17:00–20:30), editable; > 0 y < 8 con hasta 2 decimales', () => {
    const t = validarTrabajadora({ ...valido, jornada: 'MEDIA_TARDE', horas_diarias: undefined }, 'alta');
    assert.equal(t.ok && t.datos.horas_diarias, 3.5);
    for (const h of [3.5, 3, 4.25, 7.99]) assert.ok(validarTrabajadora({ ...valido, jornada: 'MEDIA_TARDE', horas_diarias: h }, 'alta').ok, String(h));
    const errores = (h: unknown) => { const r = validarTrabajadora({ ...valido, jornada: 'MEDIA_TARDE', horas_diarias: h }, 'alta'); return r.ok ? {} : r.errores; };
    for (const h of [0, -0.5, 8.5, '3,5', 3.333]) assert.equal(errores(h).horas_diarias, 'Horas al día: más de 0 y como máximo 8', String(h));
    assert.equal(errores(8).horas_diarias, 'La media tarde es menos de 8 h al día');
    // Misma fórmula: 3,5 h × 5 = 17,5 h/sem = 43,75 %; 2026: 1767 × 17,5 / 40 = 773,1 h; 2027–2028: 766,5 h.
    assert.equal(porcentajeDerivado({ horas_diarias: 3.5 }, CONVENIO_ANUAL[0]), 43.75);
    assert.deepEqual(objetivosAnuales({ horas_diarias: 3.5, computa_convenio: true }).map((o) => o.objetivo_horas), [773.1, 766.5, 766.5]);
  });
  test('TA1-2: horas > 0 y ≤ 8; COMPLETA = 8; MEDIA_MANANA < 8; hasta 2 decimales; el porcentaje no se admite (es derivado)', () => {
    const errores = (cuerpo: unknown) => { const r = validarTrabajadora(cuerpo, 'alta'); return r.ok ? {} : r.errores; };
    for (const h of [0, -1, 8.5, 9, '4,5', '4.5', Number.NaN, Number.POSITIVE_INFINITY, 4.333]) {
      assert.ok(errores({ ...valido, jornada: 'MEDIA_MANANA', horas_diarias: h }).horas_diarias, String(h));
    }
    assert.equal(errores({ ...valido, jornada: 'MEDIA_MANANA', horas_diarias: 8 }).horas_diarias, 'La media mañana es menos de 8 h al día');
    assert.equal(errores({ ...valido, jornada: 'COMPLETA', horas_diarias: 6 }).horas_diarias, 'La jornada completa son 8 h al día');
    assert.equal(errores({ ...valido, porcentaje_jornada: 100 }).porcentaje_jornada, 'Campo no admitido');
  });
  test('nombre obligatorio; sin campos de DNI ni otros; listas cerradas', () => {
    const errores = (cuerpo: unknown, modo: 'alta' | 'edicion' = 'alta') => { const r = validarTrabajadora(cuerpo, modo); return r.ok ? {} : r.errores; };
    assert.ok(errores({ ...valido, nombre: '   ' }).nombre);
    assert.ok(errores({ ...valido, nombre: undefined }).nombre);
    assert.ok(errores({ ...valido, nombre: 'x'.repeat(81) }).nombre);
    assert.ok(errores({ ...valido, nombre: '<script>' }).nombre);
    assert.equal(errores({ ...valido, dni: '00000000T' }).dni, 'Campo no admitido');
    assert.equal(errores({ ...valido, telefono: '600' }).telefono, 'Campo no admitido');
    assert.ok(errores({ ...valido, farmacia: 'OTRA' }).farmacia);
    assert.ok(errores({ ...valido, categoria: 'GERENTE' }).categoria);
    assert.ok(errores({ ...valido, jornada: 'TARDE' }).jornada);
    assert.ok(errores({ ...valido, es_titular: 'no' }).es_titular);
    assert.equal(errores({ ...valido }, 'edicion').farmacia, 'Campo no admitido'); // no se cambia de farmacia
    for (const malo of [null, [], 'x', 3]) assert.equal(validarTrabajadora(malo, 'alta').ok, false);
  });
  test('fecha de baja: YYYY-MM-DD real; nada más en el cuerpo', () => {
    assert.deepEqual(validarFechaBaja({ fecha_baja: '2026-11-30' }), { ok: true, fecha: '2026-11-30' });
    for (const malo of [{}, { fecha_baja: '2026-02-30' }, { fecha_baja: '30/11/2026' }, { fecha_baja: '2026-11-30', motivo: 'x' }, null]) {
      assert.equal(validarFechaBaja(malo).ok, false, JSON.stringify(malo));
    }
  });
});

describe('adaptador RRHH_FIXTURES e historial', () => {
  let n = 0;
  let t = 0;
  const a = crearAdaptadorRrhhFixtures({
    nuevoId: () => `f1000000-0000-4000-8000-${String(++n).padStart(12, '0')}`,
    ahora: () => new Date(Date.UTC(2026, 10, 11, 9, 0, t++)).toISOString(),
  });

  test('semilla: PIO 4 + titular, RITA 7 (con una media tarde, TA1-3) + titular; separadas por farmacia', () => {
    assert.equal(a.trabajadoras('PIO', false).trabajadoras.length, 5);
    assert.equal(a.trabajadoras('RITA', false).trabajadoras.length, 8);
    assert.equal(a.trabajadoras('AMBAS', false).trabajadoras.length, 13);
    const tarde = a.trabajadoras('RITA', false).trabajadoras.filter((x) => x.jornada === 'MEDIA_TARDE');
    assert.deepEqual(tarde.map((x) => [x.nombre, x.horas_diarias]), [['Irene Gual Torrent', 3.5]]);
    assert.deepEqual(a.trabajadora(tarde[0].id)?.objetivos.map((o) => o.objetivo_horas), [773.1, 766.5, 766.5]);
    assert.ok(a.trabajadoras('PIO', false).trabajadoras.every((x) => x.farmacia === 'PIO'));
    assert.equal(a.trabajadoras('AMBAS', false).anio_referencia, 2026);
  });
  test('alta, edición y baja quedan en el historial con quién, cuándo y antes/después', () => {
    const v = validarTrabajadora(valido, 'alta');
    assert.ok(v.ok);
    const nueva = a.crear(v.ok ? v.datos : (null as never), AUTOR_HISTORIAL);
    assert.equal(nueva.computa_convenio, true);
    const e = validarTrabajadora({ nombre: 'Ana Prueba', categoria: 'AUXILIAR', jornada: 'MEDIA_MANANA', horas_diarias: 4.5, es_titular: false }, 'edicion');
    const editada = a.editar(nueva.id, e.ok ? e.datos : (null as never), AUTOR_HISTORIAL);
    assert.equal(editada?.horas_diarias, 4.5);
    // Editar sin cambios no registra nada.
    a.editar(nueva.id, e.ok ? e.datos : (null as never), AUTOR_HISTORIAL);
    const baja = a.darDeBaja(nueva.id, '2026-12-31', AUTOR_HISTORIAL);
    assert.ok(baja && baja !== 'YA_DE_BAJA' && !baja.activa && baja.fecha_baja === '2026-12-31');
    assert.equal(a.darDeBaja(nueva.id, '2026-12-31', AUTOR_HISTORIAL), 'YA_DE_BAJA');
    const h = a.trabajadora(nueva.id)?.historial ?? [];
    assert.deepEqual(h.map((x) => x.accion), ['BAJA', 'EDICION', 'ALTA']); // más reciente primero
    assert.ok(h.every((x) => x.quien === 'Marc' && /^2026-11-11T09:00:\d{2}\.000Z$/.test(x.cuando) && x.farmacia === 'PIO'));
    assert.deepEqual(h[1].antes, { categoria: 'TECNICO', jornada: 'COMPLETA', horas_diarias: 8 });
    assert.deepEqual(h[1].despues, { categoria: 'AUXILIAR', jornada: 'MEDIA_MANANA', horas_diarias: 4.5 });
    assert.deepEqual(h[0].despues, { activa: false, fecha_baja: '2026-12-31' });
    assert.equal(h[2].antes, null);
    // Las bajas salen del listado salvo que se pidan.
    assert.ok(!a.trabajadoras('PIO', false).trabajadoras.some((x) => x.id === nueva.id));
    assert.ok(a.trabajadoras('PIO', true).trabajadoras.some((x) => x.id === nueva.id));
    assert.equal(a.historial('RITA').length, 0);
  });
  test('fichas de ejemplo: medias jornadas a 4,5 h/día (993,9 h en 2026); completas a 8 h/día', () => {
    const ts = a.trabajadoras('AMBAS', false).trabajadoras.filter((x) => !x.es_titular);
    assert.ok(ts.filter((x) => x.jornada === 'MEDIA_MANANA').every((x) => x.horas_diarias === 4.5));
    assert.ok(ts.filter((x) => x.jornada === 'COMPLETA').every((x) => x.horas_diarias === 8));
    assert.deepEqual(a.trabajadora('e0000000-0000-4000-8000-000000000004')?.objetivos.map((o) => o.objetivo_horas), [993.9, 985.5, 985.5]);
  });
  test('titular: dos fichas (una por farmacia), fuera del cómputo; objetivo null en todos los años', () => {
    const tit = a.trabajadoras('AMBAS', false).trabajadoras.filter((x) => x.es_titular);
    assert.equal(tit.length, 2);
    assert.deepEqual(tit.map((x) => x.farmacia).sort(), ['PIO', 'RITA']);
    for (const x of tit) {
      assert.equal(x.computa_convenio, false);
      assert.ok(a.trabajadora(x.id)?.objetivos.every((o) => o.objetivo_horas === null));
    }
  });
  test('la semilla no trae campos personales más allá del nombre', () => {
    const permitidos = ['id', 'farmacia', 'nombre', 'categoria', 'jornada', 'horas_diarias', 'es_titular'];
    for (const s of leerSemilla()) assert.deepEqual(Object.keys(s).filter((k) => !permitidos.includes(k)), [], s.nombre);
  });
  test('diferencias: solo lo que cambia', () => {
    const x = a.trabajadoras('PIO', false).trabajadoras[0];
    assert.deepEqual(diferencias(x, { ...x }), { antes: {}, despues: {} });
    assert.deepEqual(diferencias(x, { ...x, nombre: 'Otro' } as Trabajadora).despues, { nombre: 'Otro' });
  });
  test('historial con el mismo instante (mismo milisegundo): sigue el orden real, más reciente primero', () => {
    const b = crearAdaptadorRrhhFixtures({ ahora: () => '2026-11-11T09:00:00.000Z' });
    const v = validarTrabajadora(valido, 'alta');
    const x = b.crear(v.ok ? v.datos : (null as never), 'Pío');
    const e = validarTrabajadora({ nombre: 'Otra', categoria: 'TECNICO', jornada: 'COMPLETA', horas_diarias: 8, es_titular: false }, 'edicion');
    b.editar(x.id, e.ok ? e.datos : (null as never), 'Pío');
    b.darDeBaja(x.id, '2026-12-31', 'Pío');
    assert.deepEqual(b.trabajadora(x.id)?.historial.map((h) => h.accion), ['BAJA', 'EDICION', 'ALTA']);
    assert.deepEqual(b.historial('PIO').map((h) => h.accion), ['BAJA', 'EDICION', 'ALTA']);
  });
  test('interfaz TA2–TA3 preparada y vacía', () => {
    assert.deepEqual([a.eventos('AMBAS'), a.guardias('PIO'), a.festivos('RITA')], [[], [], []]);
  });
});

describe('rutas de escritura admitidas', () => {
  test('solo POST /api/rrhh/trabajadoras y PUT /api/rrhh/trabajadoras/:id(/baja)', () => {
    const id = 'e0000000-0000-4000-8000-000000000001';
    assert.equal(esEscrituraRrhh('POST', '/api/rrhh/trabajadoras'), true);
    assert.equal(esEscrituraRrhh('PUT', `/api/rrhh/trabajadoras/${id}`), true);
    assert.equal(esEscrituraRrhh('PUT', `/api/rrhh/trabajadoras/${id}/baja`), true);
    for (const [m, r] of [['DELETE', `/api/rrhh/trabajadoras/${id}`], ['POST', `/api/rrhh/trabajadoras/${id}`], ['PUT', '/api/rrhh/trabajadoras'],
      ['POST', '/api/rrhh/convenio'], ['PATCH', `/api/rrhh/trabajadoras/${id}`], ['POST', '/api/inicio'], ['PUT', '/api/facturas']] as const) {
      assert.equal(esEscrituraRrhh(m, r), false, `${m} ${r}`);
    }
  });
});

describe('API /api/rrhh en el servidor FIXTURES (inyección)', async () => {
  const app = await crearServidor('FIXTURES');
  after(() => app.close());
  const H = { host: '127.0.0.1:4747' };
  const ORIGEN = { origin: 'http://127.0.0.1:4747', 'content-type': 'application/json' };
  const login = await app.inject({
    method: 'POST', url: '/api/login', headers: { ...H, 'content-type': 'application/x-www-form-urlencoded' },
    payload: new URLSearchParams({ usuario: USUARIO, clave: CLAVE_FIXTURES, destino: '/' }).toString(),
  });
  const cookie = String(login.headers['set-cookie']).split(';')[0];

  test('sin sesión: 401 en lectura y en escritura (también con Origin correcto)', async () => {
    assert.equal((await app.inject({ method: 'GET', url: '/api/rrhh/trabajadoras', headers: H })).statusCode, 401);
    assert.equal((await app.inject({ method: 'POST', url: '/api/rrhh/trabajadoras', headers: { ...H, ...ORIGEN }, payload: valido })).statusCode, 401);
  });
  test('con sesión: listado por farmacia y estado de ejemplo', async () => {
    const r = await app.inject({ method: 'GET', url: '/api/rrhh/trabajadoras?farmacia=RITA', headers: { ...H, cookie } });
    assert.equal(r.statusCode, 200);
    assert.equal(r.json().trabajadoras.length, 8); // RITA: 7 + titular (TA1-3: media tarde)
    assert.equal((await app.inject({ method: 'GET', url: '/api/rrhh/trabajadoras?farmacia=X', headers: { ...H, cookie } })).statusCode, 400);
    const e = await app.inject({ method: 'GET', url: '/api/rrhh/estado', headers: { ...H, cookie } });
    assert.deepEqual(e.json(), { modo: 'FIXTURES', conectado: false, datos_ejemplo: true, mensaje: 'Datos de ejemplo en memoria' });
  });
  test('escritura: Origin obligatorio y del mismo sitio; solo JSON; validación 400', async () => {
    const post = (headers: Record<string, string>, payload: unknown = valido) =>
      app.inject({ method: 'POST', url: '/api/rrhh/trabajadoras', headers: { ...H, cookie, ...headers }, payload: payload as object });
    assert.equal((await post({ 'content-type': 'application/json' })).statusCode, 403); // sin Origin
    assert.equal((await post({ ...ORIGEN, origin: 'http://evil.example' })).statusCode, 403);
    assert.equal((await post({ ...ORIGEN, 'sec-fetch-site': 'cross-site' })).statusCode, 403);
    const form = await app.inject({ method: 'POST', url: '/api/rrhh/trabajadoras', headers: { ...H, cookie, origin: ORIGEN.origin, 'content-type': 'application/x-www-form-urlencoded' }, payload: 'nombre=x' });
    assert.equal(form.statusCode, 415);
    const malo = await post(ORIGEN, { ...valido, nombre: '', dni: '1' });
    assert.equal(malo.statusCode, 400);
    assert.deepEqual(Object.keys(malo.json().errores).sort(), ['dni', 'nombre']);
    const ok = await post(ORIGEN);
    assert.equal(ok.statusCode, 201);
    const id = ok.json().id;
    const ed = await app.inject({ method: 'PUT', url: `/api/rrhh/trabajadoras/${id}`, headers: { ...H, cookie, ...ORIGEN },
      payload: { nombre: 'Ana Editada', categoria: 'OTRA', jornada: 'COMPLETA', horas_diarias: 8, es_titular: false } });
    assert.equal(ed.statusCode, 200);
    assert.equal(ed.json().nombre, 'Ana Editada');
    const baja = await app.inject({ method: 'PUT', url: `/api/rrhh/trabajadoras/${id}/baja`, headers: { ...H, cookie, ...ORIGEN }, payload: { fecha_baja: '2026-11-30' } });
    assert.equal(baja.statusCode, 200);
    const det = await app.inject({ method: 'GET', url: `/api/rrhh/trabajadoras/${id}`, headers: { ...H, cookie } });
    assert.deepEqual(det.json().historial.map((h: { accion: string; quien: string }) => [h.accion, h.quien]), [['BAJA', 'Marc'], ['EDICION', 'Marc'], ['ALTA', 'Marc']]); // TA1-2: autor "Marc"
    assert.equal((await app.inject({ method: 'PUT', url: `/api/rrhh/trabajadoras/${id}/baja`, headers: { ...H, cookie, ...ORIGEN }, payload: { fecha_baja: '2026-11-30' } })).statusCode, 409);
  });
  test('el resto sigue de solo lectura: 405 fuera de las rutas de escritura RRHH', async () => {
    for (const [method, url] of [['POST', '/api/inicio'], ['PUT', '/api/facturas'], ['DELETE', '/api/rrhh/trabajadoras/e0000000-0000-4000-8000-000000000001'],
      ['POST', '/api/rrhh/convenio'], ['PATCH', '/api/rrhh/trabajadoras']] as const) {
      assert.equal((await app.inject({ method, url, headers: { ...H, cookie, ...ORIGEN }, payload: {} })).statusCode, 405, `${method} ${url}`);
    }
  });
});

describe('modo REAL (instancia propia de Fastify, sin BD): «Módulo pendiente de conexión (T1)», nunca datos de ejemplo', async () => {
  const app = Fastify();
  registrarRrhh(app, { modo: 'REAL', quien: 'Pío', sesionValida: (req) => req.headers.cookie === 'cf_sesion=ok' });
  await app.ready();
  after(() => app.close());
  const H = { host: '127.0.0.1:4747', cookie: 'cf_sesion=ok' };
  const nombresEjemplo = leerSemilla().map((s) => s.nombre);

  test('todas las rutas de datos: 503 con el aviso y sin ningún nombre de ejemplo', async () => {
    for (const url of ['/api/rrhh/trabajadoras', '/api/rrhh/trabajadoras?farmacia=PIO', '/api/rrhh/trabajadoras/e0000000-0000-4000-8000-000000000001',
      '/api/rrhh/convenio', '/api/rrhh/historial']) {
      const r = await app.inject({ method: 'GET', url, headers: H });
      assert.equal(r.statusCode, 503, url);
      assert.deepEqual(r.json(), { error: 'MODULO_PENDIENTE_T1', mensaje: MENSAJE_PENDIENTE_T1 }, url);
      for (const n of nombresEjemplo) assert.ok(!r.body.includes(n), `${url}: ${n}`);
    }
    const e = await app.inject({ method: 'GET', url: '/api/rrhh/estado', headers: H });
    assert.deepEqual(e.json(), { modo: 'REAL', conectado: false, datos_ejemplo: false, mensaje: MENSAJE_PENDIENTE_T1 });
  });
  test('escritura en REAL: sesión y origen primero; luego 503, sin crear nada', async () => {
    const W = { ...H, origin: 'http://127.0.0.1:4747', 'content-type': 'application/json' };
    assert.equal((await app.inject({ method: 'POST', url: '/api/rrhh/trabajadoras', headers: { ...W, cookie: '' }, payload: valido })).statusCode, 401);
    assert.equal((await app.inject({ method: 'POST', url: '/api/rrhh/trabajadoras', headers: { ...W, origin: 'http://x' }, payload: valido })).statusCode, 403);
    const r = await app.inject({ method: 'POST', url: '/api/rrhh/trabajadoras', headers: W, payload: valido });
    assert.equal(r.statusCode, 503);
    assert.equal(r.json().mensaje, MENSAJE_PENDIENTE_T1);
  });
});
