// TA1 Trabajadores: contrato, objetivo anual, historial, validaciones y API (FIXTURES con el servidor completo;
// REAL con una instancia propia de Fastify, sin BD ni .env). TA-REAL: contrato alineado con la migración 31
// (categorías, tipo_jornada, fecha_alta, anulada, jornada_max_horas), anulación y convenio. Uso: npm run test:unit
import assert from 'node:assert/strict';
import { after, describe, test } from 'node:test';
import Fastify from 'fastify';
import { CLAVE_FIXTURES, USUARIO } from '../acceso.ts';
import { crearServidor } from '../index.ts';
import {
  AUTOR_HISTORIAL, CATEGORIAS, CONVENIO_ANUAL, ERROR_FALTA_CREDENCIAL, JORNADAS, MENSAJE_FALTA_CREDENCIAL, accionActualizacion, aniosConvenioQueFaltan,
  computaConvenio, diferencias, esTitular, filtroFarmacia, horasSemanales, objetivoAnual, objetivosAnuales, porcentajeDerivado, validarAnulacion,
  validarCrearConvenio, validarFechaBaja, validarTrabajadora, type Trabajadora,
} from '../rrhh/contrato.ts';
import { crearAdaptadorRrhhFixtures, leerSemilla } from '../rrhh/adaptador_fixtures.ts';
import { esEscrituraRrhh, registrarRrhh } from '../rrhh/rutas.ts';

const valido = { farmacia: 'PIO', nombre: '  Ana   Prueba ', categoria: 'TECNICA', tipo_jornada: 'COMPLETA', horas_diarias: 8, fecha_alta: '2026-11-02' };
const edicion = (x: Record<string, unknown>) => { const { farmacia: _f, ...r } = { ...valido, ...x }; return r; };
/** Ficha creada (falla la prueba si el adaptador devuelve un código). */
const ficha = (t: Trabajadora | string | null): Trabajadora => { assert.equal(typeof t, 'object', String(t)); return t as Trabajadora; };

describe('TA-REAL: contrato = esquema real (migración 31)', () => {
  test('categorías, jornadas y titular del esquema', () => {
    assert.deepEqual([...CATEGORIAS], ['FARMACEUTICA_TITULAR', 'FARMACEUTICA_ADJUNTA', 'TECNICA', 'AUXILIAR', 'OTRA']);
    assert.deepEqual([...JORNADAS], ['COMPLETA', 'MEDIA_MANANA', 'MEDIA_TARDE']);
    assert.equal(esTitular({ categoria: 'FARMACEUTICA_TITULAR' }), true);
    assert.equal(esTitular({ categoria: 'FARMACEUTICA_ADJUNTA' }), false);
    assert.deepEqual(CATEGORIAS.map(computaConvenio), [false, true, true, true, true]);
  });
  test('convenio_anual: columnas del esquema (jornada_max_horas, horas_semanales_referencia, estado, fuente); años que faltan', () => {
    assert.deepEqual(Object.keys(CONVENIO_ANUAL[0]).sort(),
      ['anio', 'asuntos_propios_dias', 'estado', 'fuente', 'horas_semanales_referencia', 'jornada_max_horas', 'permiso_medico_horas']);
    assert.ok(CONVENIO_ANUAL.every((c) => c.fuente.length >= 1 && c.fuente.length <= 200));
    assert.deepEqual(aniosConvenioQueFaltan([]), [2026, 2027, 2028]);
    assert.deepEqual(aniosConvenioQueFaltan([{ anio: 2027 }]), [2026, 2028]);
  });
  test('anulación con confirmación expresa; crear convenio solo con años firmados', () => {
    assert.deepEqual(validarAnulacion({ confirmar: true }), { ok: true });
    for (const malo of [{}, { confirmar: 'si' }, { confirmar: true, motivo: 'x' }, null, []]) assert.equal(validarAnulacion(malo).ok, false);
    assert.deepEqual(validarCrearConvenio({ anios: [2028, 2026] }), { ok: true, anios: [2026, 2028] });
    for (const malo of [{}, { anios: [] }, { anios: [2025] }, { anios: [2026, 2026] }, { anios: [2026], otro: 1 }]) assert.equal(validarCrearConvenio(malo).ok, false);
  });
  test('acción del historial: anulación, baja o edición', () => {
    const t = ficha(crearAdaptadorRrhhFixtures({ semillaEventos: null }).trabajadoras('PIO', false).trabajadoras[0]);
    assert.equal(accionActualizacion(t, { ...t, anulada: true }), 'ANULACION');
    assert.equal(accionActualizacion(t, { ...t, fecha_baja: '2026-12-31' }), 'BAJA');
    assert.equal(accionActualizacion(t, { ...t, nombre: 'Otra' }), 'EDICION');
  });
});

describe('convenio y objetivo anual (decisiones T0)', () => {
  test('convenio por año: 2026 1.767 h y 1 día; 2027–2028 1.752 h y 0 días; permiso médico 24 h; referencia 40 h/sem; pendiente de publicación', () => {
    assert.deepEqual(CONVENIO_ANUAL.map((c) => [c.anio, c.jornada_max_horas, c.horas_semanales_referencia, c.asuntos_propios_dias, c.permiso_medico_horas, c.estado]), [
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
    assert.deepEqual(objetivosAnuales({ horas_diarias: 8, computa_convenio: true }, []), []); // sin convenio en la BD: sin objetivos
    const o = objetivoAnual({ horas_diarias: 4.5, computa_convenio: true }, c26);
    assert.deepEqual([o.horas_semanales, o.horas_semanales_referencia, o.porcentaje_derivado, o.jornada_max_horas], [22.5, 40, 56.25, 1767]);
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
    assert.equal(r.ok && r.datos.fecha_alta, '2026-11-02');
    const s = validarTrabajadora({ ...valido, horas_diarias: undefined }, 'alta');
    assert.equal(s.ok && s.datos.horas_diarias, 8);
    const m = validarTrabajadora({ ...valido, tipo_jornada: 'MEDIA_MANANA', horas_diarias: undefined }, 'alta');
    assert.equal(m.ok && m.datos.horas_diarias, 4.5);
    for (const h of [4.5, 0.25, 7.75, 4.15]) assert.ok(validarTrabajadora({ ...valido, tipo_jornada: 'MEDIA_MANANA', horas_diarias: h }, 'alta').ok, String(h));
  });
  test('TA-REAL: fecha de alta obligatoria y real', () => {
    const errores = (cuerpo: unknown) => { const r = validarTrabajadora(cuerpo, 'alta'); return r.ok ? {} : r.errores; };
    for (const f of [undefined, '', '2026-02-30', '02/11/2026', 20261102, '1900-01-01']) assert.ok(errores({ ...valido, fecha_alta: f }).fecha_alta, String(f));
    assert.ok(validarTrabajadora(edicion({ fecha_alta: '2025-03-01' }), 'edicion').ok);
  });
  test('TA1-3: MEDIA_TARDE: por defecto 3,5 h (17:00–20:30), editable; > 0 y < 8 con hasta 2 decimales', () => {
    const t = validarTrabajadora({ ...valido, tipo_jornada: 'MEDIA_TARDE', horas_diarias: undefined }, 'alta');
    assert.equal(t.ok && t.datos.horas_diarias, 3.5);
    for (const h of [3.5, 3, 4.25, 7.99]) assert.ok(validarTrabajadora({ ...valido, tipo_jornada: 'MEDIA_TARDE', horas_diarias: h }, 'alta').ok, String(h));
    const errores = (h: unknown) => { const r = validarTrabajadora({ ...valido, tipo_jornada: 'MEDIA_TARDE', horas_diarias: h }, 'alta'); return r.ok ? {} : r.errores; };
    for (const h of [0, -0.5, 8.5, '3,5', 3.333]) assert.equal(errores(h).horas_diarias, 'Horas al día: más de 0 y como máximo 8', String(h));
    assert.equal(errores(8).horas_diarias, 'La media tarde es menos de 8 h al día');
    assert.equal(porcentajeDerivado({ horas_diarias: 3.5 }, CONVENIO_ANUAL[0]), 43.75);
    assert.deepEqual(objetivosAnuales({ horas_diarias: 3.5, computa_convenio: true }).map((o) => o.objetivo_horas), [773.1, 766.5, 766.5]);
  });
  test('TA1-2: horas > 0 y ≤ 8; COMPLETA = 8; MEDIA_MANANA < 8; hasta 2 decimales; el porcentaje no se admite (es derivado)', () => {
    const errores = (cuerpo: unknown) => { const r = validarTrabajadora(cuerpo, 'alta'); return r.ok ? {} : r.errores; };
    for (const h of [0, -1, 8.5, 9, '4,5', '4.5', Number.NaN, Number.POSITIVE_INFINITY, 4.333]) {
      assert.ok(errores({ ...valido, tipo_jornada: 'MEDIA_MANANA', horas_diarias: h }).horas_diarias, String(h));
    }
    assert.equal(errores({ ...valido, tipo_jornada: 'MEDIA_MANANA', horas_diarias: 8 }).horas_diarias, 'La media mañana es menos de 8 h al día');
    assert.equal(errores({ ...valido, tipo_jornada: 'COMPLETA', horas_diarias: 6 }).horas_diarias, 'La jornada completa son 8 h al día');
    assert.equal(errores({ ...valido, porcentaje_jornada: 100 }).porcentaje_jornada, 'Campo no admitido');
  });
  test('nombre obligatorio; sin campos de DNI ni otros; listas cerradas (las del esquema)', () => {
    const errores = (cuerpo: unknown, modo: 'alta' | 'edicion' = 'alta') => { const r = validarTrabajadora(cuerpo, modo); return r.ok ? {} : r.errores; };
    assert.ok(errores({ ...valido, nombre: '   ' }).nombre);
    assert.ok(errores({ ...valido, nombre: undefined }).nombre);
    assert.ok(errores({ ...valido, nombre: 'x'.repeat(81) }).nombre);
    assert.ok(errores({ ...valido, nombre: '<script>' }).nombre);
    assert.equal(errores({ ...valido, dni: '00000000T' }).dni, 'Campo no admitido');
    assert.equal(errores({ ...valido, telefono: '600' }).telefono, 'Campo no admitido');
    assert.ok(errores({ ...valido, farmacia: 'OTRA' }).farmacia);
    for (const c of ['GERENTE', 'TECNICO', 'FARMACEUTICO']) assert.ok(errores({ ...valido, categoria: c }).categoria, c); // las de TA1 ya no valen
    assert.ok(errores({ ...valido, tipo_jornada: 'TARDE' }).tipo_jornada);
    assert.equal(errores({ ...valido, jornada: 'COMPLETA' }).jornada, 'Campo no admitido');
    assert.equal(errores({ ...valido, es_titular: true }).es_titular, 'Campo no admitido'); // titular = categoría
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
  const datos = (x: Record<string, unknown>, modo: 'alta' | 'edicion' = 'edicion') => {
    const v = validarTrabajadora(modo === 'alta' ? { ...valido, ...x } : edicion(x), modo);
    assert.ok(v.ok, JSON.stringify(v));
    return v.datos;
  };

  test('semilla: PIO 4 + titular, RITA 7 (con una media tarde, TA1-3) + titular; separadas por farmacia', () => {
    assert.equal(a.trabajadoras('PIO', false).trabajadoras.length, 5);
    assert.equal(a.trabajadoras('RITA', false).trabajadoras.length, 8);
    assert.equal(a.trabajadoras('AMBAS', false).trabajadoras.length, 13);
    const tarde = a.trabajadoras('RITA', false).trabajadoras.filter((x) => x.tipo_jornada === 'MEDIA_TARDE');
    assert.deepEqual(tarde.map((x) => [x.nombre, x.horas_diarias]), [['Irene Gual Torrent', 3.5]]);
    assert.deepEqual(a.trabajadora(tarde[0].id)?.objetivos.map((o) => o.objetivo_horas), [773.1, 766.5, 766.5]);
    assert.ok(a.trabajadoras('PIO', false).trabajadoras.every((x) => x.farmacia === 'PIO' && x.fecha_alta === '2026-01-01' && !x.anulada));
    assert.equal(a.trabajadoras('AMBAS', false).anio_referencia, 2026);
  });
  test('alta, edición y baja quedan en el historial con quién, cuándo y antes/después', () => {
    const nueva = ficha(a.crear(datos({}, 'alta'), AUTOR_HISTORIAL));
    assert.deepEqual([nueva.computa_convenio, nueva.fecha_alta, nueva.anulada, nueva.activa], [true, '2026-11-02', false, true]);
    const e = datos({ nombre: 'Ana Prueba', categoria: 'AUXILIAR', tipo_jornada: 'MEDIA_MANANA', horas_diarias: 4.5 });
    assert.equal(ficha(a.editar(nueva.id, e, AUTOR_HISTORIAL)).horas_diarias, 4.5);
    a.editar(nueva.id, e, AUTOR_HISTORIAL); // sin cambios: no registra nada
    assert.equal(a.darDeBaja(nueva.id, '2026-11-01', AUTOR_HISTORIAL), 'BAJA_ANTES_DEL_ALTA'); // como el check de la tabla
    const baja = ficha(a.darDeBaja(nueva.id, '2026-12-31', AUTOR_HISTORIAL));
    assert.ok(!baja.activa && baja.fecha_baja === '2026-12-31');
    assert.equal(a.darDeBaja(nueva.id, '2026-12-31', AUTOR_HISTORIAL), 'YA_DE_BAJA');
    assert.equal(a.editar(nueva.id, datos({ fecha_alta: '2027-01-15' }), AUTOR_HISTORIAL), 'BAJA_ANTES_DEL_ALTA');
    const h = a.trabajadora(nueva.id)?.historial ?? [];
    assert.deepEqual(h.map((x) => x.accion), ['BAJA', 'EDICION', 'ALTA']); // más reciente primero
    assert.ok(h.every((x) => x.quien === 'Marc' && /^2026-11-11T09:00:\d{2}\.000Z$/.test(x.cuando) && x.farmacia === 'PIO'));
    assert.deepEqual(h[1].antes, { categoria: 'TECNICA', tipo_jornada: 'COMPLETA', horas_diarias: 8 });
    assert.deepEqual(h[1].despues, { categoria: 'AUXILIAR', tipo_jornada: 'MEDIA_MANANA', horas_diarias: 4.5 });
    assert.deepEqual(h[0].despues, { fecha_baja: '2026-12-31' });
    assert.equal(h[2].antes, null);
    assert.deepEqual(h[2].despues, { farmacia: 'PIO', nombre: 'Ana Prueba', categoria: 'TECNICA', tipo_jornada: 'COMPLETA', horas_diarias: 8, computa_convenio: true, fecha_alta: '2026-11-02' });
    assert.ok(!a.trabajadoras('PIO', false).trabajadoras.some((x) => x.id === nueva.id));
    assert.ok(a.trabajadoras('PIO', true).trabajadoras.some((x) => x.id === nueva.id));
    assert.equal(a.historial('RITA').length, 0);
  });
  test('TA-REAL: titular = categoría FARMACEUTICA_TITULAR (computa_convenio false); al cambiar de categoría se recalcula', () => {
    const x = ficha(a.crear(datos({ nombre: 'Titular Prueba', categoria: 'FARMACEUTICA_TITULAR', tipo_jornada: 'MEDIA_MANANA', horas_diarias: 4.5 }, 'alta'), 'Marc'));
    assert.equal(x.computa_convenio, false);
    assert.ok(a.trabajadora(x.id)?.objetivos.every((o) => o.objetivo_horas === null));
    const y = ficha(a.editar(x.id, datos({ nombre: 'Titular Prueba', categoria: 'FARMACEUTICA_ADJUNTA', tipo_jornada: 'MEDIA_MANANA', horas_diarias: 4.5 }), 'Marc'));
    assert.equal(y.computa_convenio, true);
    assert.deepEqual(a.trabajadora(x.id)?.historial[0].despues, { categoria: 'FARMACEUTICA_ADJUNTA', computa_convenio: true });
  });
  test('TA-REAL: anular = registro erróneo (no se borra): sale del listado y del calendario; queda en el historial', () => {
    const x = ficha(a.crear(datos({ nombre: 'Ficha Errónea', fecha_alta: '2026-01-01' }, 'alta'), 'Marc'));
    const an = ficha(a.anular(x.id, 'Marc'));
    assert.deepEqual([an.anulada, an.activa], [true, false]);
    assert.equal(a.anular(x.id, 'Marc'), 'YA_ANULADA');
    assert.equal(a.anular('f9999999-0000-4000-8000-000000000000', 'Marc'), null);
    assert.ok(!a.trabajadoras('PIO', false).trabajadoras.some((t2) => t2.id === x.id));
    assert.ok(a.trabajadoras('PIO', true).trabajadoras.some((t2) => t2.id === x.id && t2.anulada));
    assert.ok(!a.calendario('PIO', '2026-11-09', '2026-11-15').trabajadoras.some((t2) => t2.id === x.id));
    assert.deepEqual(a.trabajadora(x.id)?.historial.map((h) => [h.accion, JSON.stringify(h.despues)]), [['ANULACION', '{"anulada":true}'], ['ALTA', JSON.stringify(a.trabajadora(x.id)?.historial[1].despues)]]);
    assert.equal(a.editar(x.id, datos({ nombre: 'Otra' }), 'Marc'), null); // anulada: no se edita
    // Una anulada libera el nombre (índice único entre las no anuladas).
    assert.equal(typeof a.crear(datos({ nombre: 'Ficha Errónea' }, 'alta'), 'Marc'), 'object');
    assert.equal(a.crear(datos({ nombre: 'ficha errónea' }, 'alta'), 'Marc'), 'NOMBRE_DUPLICADO');
  });
  test('TA-REAL: convenio que falta → se crean los años firmados (los existentes no se tocan)', () => {
    const b = crearAdaptadorRrhhFixtures({ semillaEventos: null, convenio: [CONVENIO_ANUAL[1]] });
    assert.deepEqual(b.convenio().map((c) => c.anio), [2027]);
    assert.deepEqual(b.trabajadora('e0000000-0000-4000-8000-000000000001')?.objetivos.map((o) => o.anio), [2027]);
    assert.deepEqual(b.crearConvenio([2026, 2027, 2028], 'Marc').map((c) => c.anio), [2026, 2028]);
    assert.deepEqual(b.convenio(), CONVENIO_ANUAL.map((c) => ({ ...c })));
    assert.deepEqual(b.crearConvenio([2026], 'Marc'), []);
  });
  test('fichas de ejemplo: medias jornadas a 4,5 h/día (993,9 h en 2026); completas a 8 h/día', () => {
    const ts = a.trabajadoras('AMBAS', false).trabajadoras.filter((x) => !esTitular(x));
    assert.ok(ts.filter((x) => x.tipo_jornada === 'MEDIA_MANANA').every((x) => x.horas_diarias === 4.5));
    assert.ok(ts.filter((x) => x.tipo_jornada === 'COMPLETA').every((x) => x.horas_diarias === 8));
    assert.deepEqual(a.trabajadora('e0000000-0000-4000-8000-000000000004')?.objetivos.map((o) => o.objetivo_horas), [993.9, 985.5, 985.5]);
  });
  test('titular: dos fichas (una por farmacia), fuera del cómputo; objetivo null en todos los años', () => {
    const tit = crearAdaptadorRrhhFixtures({ semillaEventos: null }).trabajadoras('AMBAS', false).trabajadoras.filter(esTitular);
    assert.equal(tit.length, 2);
    assert.deepEqual(tit.map((x) => x.farmacia).sort(), ['PIO', 'RITA']);
    for (const x of tit) {
      assert.equal(x.computa_convenio, false);
      assert.ok(a.trabajadora(x.id)?.objetivos.every((o) => o.objetivo_horas === null));
    }
  });
  test('la semilla trae solo columnas de trabajadoras y ningún dato personal más allá del nombre', () => {
    const permitidos = ['id', 'farmacia', 'nombre', 'categoria', 'tipo_jornada', 'horas_diarias', 'fecha_alta'];
    for (const s of leerSemilla()) {
      assert.deepEqual(Object.keys(s).filter((k) => !permitidos.includes(k)), [], s.nombre);
      assert.ok(CATEGORIAS.includes(s.categoria) && JORNADAS.includes(s.tipo_jornada), s.nombre);
    }
  });
  test('diferencias: solo lo que cambia', () => {
    const x = a.trabajadoras('PIO', false).trabajadoras[0];
    assert.deepEqual(diferencias(x, { ...x }), { antes: {}, despues: {} });
    assert.deepEqual(diferencias(x, { ...x, nombre: 'Otro' }).despues, { nombre: 'Otro' });
  });
  test('historial con el mismo instante (mismo milisegundo): sigue el orden real, más reciente primero', () => {
    const b = crearAdaptadorRrhhFixtures({ ahora: () => '2026-11-11T09:00:00.000Z' });
    const x = ficha(b.crear(datos({}, 'alta'), 'Pío'));
    b.editar(x.id, datos({ nombre: 'Otra' }), 'Pío');
    b.darDeBaja(x.id, '2026-12-31', 'Pío');
    assert.deepEqual(b.trabajadora(x.id)?.historial.map((h) => h.accion), ['BAJA', 'EDICION', 'ALTA']);
    assert.deepEqual(b.historial('PIO').map((h) => h.accion), ['BAJA', 'EDICION', 'ALTA']);
  });
  test('interfaz TA3 preparada y vacía (guardias y festivos); TA2 con eventos de ejemplo', () => {
    assert.deepEqual([a.guardias('PIO'), a.festivos('RITA')], [[], []]);
    assert.ok(a.eventos().length > 0);
  });
});

describe('rutas de escritura admitidas', () => {
  test('solo POST alta, PUT edición/baja/anulación, POST convenio y (TA2) POST /api/rrhh/eventos(/deshacer)', () => {
    const id = 'e0000000-0000-4000-8000-000000000001';
    assert.equal(esEscrituraRrhh('POST', '/api/rrhh/trabajadoras'), true);
    assert.equal(esEscrituraRrhh('PUT', `/api/rrhh/trabajadoras/${id}`), true);
    assert.equal(esEscrituraRrhh('PUT', `/api/rrhh/trabajadoras/${id}/baja`), true);
    assert.equal(esEscrituraRrhh('PUT', `/api/rrhh/trabajadoras/${id}/anular`), true);
    assert.equal(esEscrituraRrhh('POST', '/api/rrhh/convenio'), true);
    assert.equal(esEscrituraRrhh('POST', '/api/rrhh/eventos'), true);
    assert.equal(esEscrituraRrhh('POST', '/api/rrhh/eventos/deshacer'), true);
    for (const [m, r] of [['DELETE', `/api/rrhh/trabajadoras/${id}`], ['POST', `/api/rrhh/trabajadoras/${id}`], ['PUT', '/api/rrhh/trabajadoras'],
      ['PUT', '/api/rrhh/convenio'], ['DELETE', '/api/rrhh/convenio'], ['POST', `/api/rrhh/trabajadoras/${id}/anular`],
      ['PATCH', `/api/rrhh/trabajadoras/${id}`], ['POST', '/api/inicio'], ['PUT', '/api/facturas'],
      ['DELETE', `/api/rrhh/eventos/${id}`], ['PUT', '/api/rrhh/eventos'], ['PATCH', '/api/rrhh/eventos'], ['POST', '/api/rrhh/eventos/historial'],
      ['POST', '/api/rrhh/eventos/notas'], ['POST', `/api/rrhh/eventos/${id}`], ['DELETE', '/api/rrhh/eventos']] as const) {
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
    assert.deepEqual(e.json(), { modo: 'FIXTURES', conectado: false, datos_ejemplo: true, mensaje: 'Datos de ejemplo en memoria', anular_eventos: true });
  });
  test('escritura: Origin obligatorio y del mismo sitio; solo JSON; validación 400; anular con confirmación', async () => {
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
    const dup = await post(ORIGEN);
    assert.deepEqual([dup.statusCode, dup.json().error], [409, 'NOMBRE_DUPLICADO']);
    const ed = await app.inject({ method: 'PUT', url: `/api/rrhh/trabajadoras/${id}`, headers: { ...H, cookie, ...ORIGEN }, payload: edicion({ nombre: 'Ana Editada', categoria: 'OTRA' }) });
    assert.equal(ed.statusCode, 200);
    assert.equal(ed.json().nombre, 'Ana Editada');
    const antes = await app.inject({ method: 'PUT', url: `/api/rrhh/trabajadoras/${id}/baja`, headers: { ...H, cookie, ...ORIGEN }, payload: { fecha_baja: '2026-10-01' } });
    assert.deepEqual([antes.statusCode, antes.json().error], [400, 'BAJA_ANTES_DEL_ALTA']);
    const baja = await app.inject({ method: 'PUT', url: `/api/rrhh/trabajadoras/${id}/baja`, headers: { ...H, cookie, ...ORIGEN }, payload: { fecha_baja: '2026-11-30' } });
    assert.equal(baja.statusCode, 200);
    assert.equal((await app.inject({ method: 'PUT', url: `/api/rrhh/trabajadoras/${id}/baja`, headers: { ...H, cookie, ...ORIGEN }, payload: { fecha_baja: '2026-11-30' } })).statusCode, 409);
    const sinConfirmar = await app.inject({ method: 'PUT', url: `/api/rrhh/trabajadoras/${id}/anular`, headers: { ...H, cookie, ...ORIGEN }, payload: {} });
    assert.equal(sinConfirmar.statusCode, 400);
    const anulada = await app.inject({ method: 'PUT', url: `/api/rrhh/trabajadoras/${id}/anular`, headers: { ...H, cookie, ...ORIGEN }, payload: { confirmar: true } });
    assert.deepEqual([anulada.statusCode, anulada.json().anulada], [200, true]);
    assert.equal((await app.inject({ method: 'PUT', url: `/api/rrhh/trabajadoras/${id}/anular`, headers: { ...H, cookie, ...ORIGEN }, payload: { confirmar: true } })).statusCode, 409);
    const det = await app.inject({ method: 'GET', url: `/api/rrhh/trabajadoras/${id}`, headers: { ...H, cookie } });
    assert.deepEqual(det.json().historial.map((h: { accion: string; quien: string }) => [h.accion, h.quien]),
      [['ANULACION', 'Marc'], ['BAJA', 'Marc'], ['EDICION', 'Marc'], ['ALTA', 'Marc']]); // TA1-2: autor "Marc"
  });
  test('convenio: POST con años firmados (ya existen: no crea nada); otros años 400', async () => {
    const r = await app.inject({ method: 'POST', url: '/api/rrhh/convenio', headers: { ...H, cookie, ...ORIGEN }, payload: { anios: [2026, 2027, 2028] } });
    assert.equal(r.statusCode, 200);
    assert.deepEqual([r.json().creados, r.json().convenio.length], [[], 3]);
    assert.equal((await app.inject({ method: 'POST', url: '/api/rrhh/convenio', headers: { ...H, cookie, ...ORIGEN }, payload: { anios: [2030] } })).statusCode, 400);
  });
  test('el resto sigue de solo lectura: 405 fuera de las rutas de escritura RRHH', async () => {
    for (const [method, url] of [['POST', '/api/inicio'], ['PUT', '/api/facturas'], ['DELETE', '/api/rrhh/trabajadoras/e0000000-0000-4000-8000-000000000001'],
      ['PUT', '/api/rrhh/convenio'], ['PATCH', '/api/rrhh/trabajadoras'], ['DELETE', '/api/rrhh/eventos/e0000000-0000-4000-8000-000000000001'],
      ['PUT', '/api/rrhh/eventos'], ['POST', '/api/rrhh/eventos/historial'], ['POST', '/api/rrhh/eventos/notas']] as const) {
      assert.equal((await app.inject({ method, url, headers: { ...H, cookie, ...ORIGEN }, payload: {} })).statusCode, 405, `${method} ${url}`);
    }
  });
});

describe('modo REAL sin credencial (instancia propia de Fastify, sin BD): «Falta configurar la credencial de Trabajadores», nunca datos de ejemplo', async () => {
  const app = Fastify();
  registrarRrhh(app, { modo: 'REAL', quien: 'Marc', sesionValida: (req) => req.headers.cookie === 'cf_sesion=ok' });
  await app.ready();
  after(() => app.close());
  const H = { host: '127.0.0.1:4747', cookie: 'cf_sesion=ok' };
  const nombresEjemplo = leerSemilla().map((s) => s.nombre);
  const AVISO = { error: ERROR_FALTA_CREDENCIAL, mensaje: MENSAJE_FALTA_CREDENCIAL };

  test('todas las rutas de datos: 503 con el aviso y sin ningún nombre de ejemplo', async () => {
    for (const url of ['/api/rrhh/trabajadoras', '/api/rrhh/trabajadoras?farmacia=PIO', '/api/rrhh/trabajadoras/e0000000-0000-4000-8000-000000000001',
      '/api/rrhh/convenio', '/api/rrhh/historial', '/api/rrhh/eventos?farmacia=PIO&desde=2026-11-09&hasta=2026-11-15', '/api/rrhh/eventos/historial',
      '/api/rrhh/eventos/notas?desde=2026-11-13']) {
      const r = await app.inject({ method: 'GET', url, headers: H });
      assert.equal(r.statusCode, 503, url);
      assert.deepEqual(r.json(), AVISO, url);
      for (const n of nombresEjemplo) assert.ok(!r.body.includes(n), `${url}: ${n}`);
    }
    const e = await app.inject({ method: 'GET', url: '/api/rrhh/estado', headers: H });
    assert.deepEqual(e.json(), { modo: 'REAL', conectado: false, datos_ejemplo: false, mensaje: MENSAJE_FALTA_CREDENCIAL, anular_eventos: false });
  });
  test('escritura en REAL: sesión y origen primero; luego 503, sin crear nada', async () => {
    const W = { ...H, origin: 'http://127.0.0.1:4747', 'content-type': 'application/json' };
    assert.equal((await app.inject({ method: 'POST', url: '/api/rrhh/trabajadoras', headers: { ...W, cookie: '' }, payload: valido })).statusCode, 401);
    assert.equal((await app.inject({ method: 'POST', url: '/api/rrhh/trabajadoras', headers: { ...W, origin: 'http://x' }, payload: valido })).statusCode, 403);
    const pintar = { accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ trabajadora_id: 'e0000000-0000-4000-8000-000000000001', fecha: '2026-12-07' }] };
    for (const [method, url, payload] of [['POST', '/api/rrhh/trabajadoras', valido], ['POST', '/api/rrhh/eventos', pintar],
      ['POST', '/api/rrhh/eventos/deshacer', { cambio_id: 'f1000000-0000-4000-8000-000000000001' }], ['POST', '/api/rrhh/convenio', { anios: [2026] }],
      ['PUT', '/api/rrhh/trabajadoras/e0000000-0000-4000-8000-000000000001/anular', { confirmar: true }]] as const) {
      const e = await app.inject({ method, url, headers: W, payload });
      assert.equal(e.statusCode, 503, url);
      assert.deepEqual(e.json(), AVISO, url);
    }
  });
});
