// TA-REAL: adaptador RRHH_REAL simulado SIN CONEXIÓN (pool inyectado con una base de datos en memoria). Comprueba:
// mapeo de errores de la BD a mensajes llanos, autor por transacción (set_config local, nunca de sesión), ROLLBACK ante
// error y sin reintentos, lotes al rellenar, contrato real (filas de la migración 31 → contrato), goma y deshacer
// desactivados, historial desde trabajadores_historial y la API en modo REAL. Nunca abre una conexión real ni lee .env.
// Uso: npm run test:unit
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { after, describe, test } from 'node:test';
import Fastify from 'fastify';
import { MENSAJE_FALTA_CREDENCIAL, TEXTO_BANNER_REAL } from '../rrhh/contrato.ts';
import { ErrorRrhhBd, MENSAJES_BD, traducirErrorBd } from '../rrhh/errores_bd.ts';
import {
  MAX_CONEXIONES, SQL, TAM_LOTE, VARIABLES_TRAB, cambiosDesdeHistorial, configuracionRrhh, crearAdaptadorRrhhReal, filaAEvento, filaATrabajadora,
  historialFichas, instante, lotes, type ClienteBd, type Fila, type PoolBd,
} from '../rrhh/adaptador_real.ts';
import { registrarRrhh } from '../rrhh/rutas.ts';
import { AVISO_ANULAR_PENDIENTE, describirCambio, type CambioCalendario, type PeticionEventos } from '../rrhh/eventos.ts';

const AINA = 'e0000000-0000-4000-8000-000000000001';
const ELENA = 'e0000000-0000-4000-8000-000000000004';
const T0 = '2026-11-01 08:00:00+00';
const AHORA = '2026-11-13 10:00:00.123456+00';
/** Filas como las devuelve pg con los tipos en texto (numeric, date, timestamptz). */
const FICHAS: Fila[] = [
  { id: AINA, farmacia: 'PIO', nombre: 'Aina Bosch Ferrer', categoria: 'TECNICA', tipo_jornada: 'COMPLETA', horas_diarias: '8.00', computa_convenio: true,
    fecha_alta: '2026-01-01', fecha_baja: null, anulada: false, created_at: T0, updated_at: T0 },
  { id: ELENA, farmacia: 'PIO', nombre: 'Elena Mas Garriga', categoria: 'TECNICA', tipo_jornada: 'MEDIA_MANANA', horas_diarias: '4.50', computa_convenio: true,
    fecha_alta: '2026-01-01', fecha_baja: null, anulada: false, created_at: T0, updated_at: T0 },
];

interface Consulta { cliente: number; sql: string; params?: unknown[] }
/** Base de datos simulada: responde a las consultas del adaptador sobre eventos en memoria. */
function bdSimulada(o: { eventos?: Fila[]; fallo?: (sql: string, params?: unknown[]) => unknown; falloConexion?: unknown } = {}) {
  const eventos = new Map<string, Fila>((o.eventos ?? []).map((e) => [String(e.id), { ...e }]));
  const log: Consulta[] = [];
  let conexiones = 0;
  let liberadas = 0;
  const en = (lista: unknown, v: unknown) => (lista as unknown[]).includes(v);
  const responder = (sql: string, p: unknown[] = []): Fila[] => {
    const err = o.fallo?.(sql, p);
    if (err) throw err;
    if (sql === SQL.ahora) return [{ ahora: AHORA }];
    if (sql === SQL.fichasPorId) return FICHAS.filter((f) => en(p[0], f.id));
    if (sql === SQL.fichasTodas || sql === SQL.fichasPeriodo) return FICHAS;
    if (sql === SQL.convenio) return [];
    if (sql === SQL.eventosRangoBloqueo) return [...eventos.values()].filter((e) => en(p[0], e.trabajadora_id) && String(e.fecha) >= String(p[1]) && String(e.fecha) <= String(p[2]));
    if (sql === SQL.eventosCeldasBloqueo) return [...eventos.values()].filter((e) => en(p[0], e.trabajadora_id) && en(p[1], e.fecha));
    if (sql === SQL.eventosPorIdBloqueo) return [...eventos.values()].filter((e) => en(p[0], e.id));
    if (sql === SQL.eventosPeriodo) return [...eventos.values()].map((e) => ({ ...e, horas_efectivas: e.horas ?? (e.franja === 'MANANA' ? '4.50' : '3.50') }));
    if (sql === SQL.insertarEventos) {
      const [t, fa, fe, fr, ti, es, ho, no] = p as unknown[][];
      const r: Fila[] = [];
      t.forEach((_, i) => {
        if ([...eventos.values()].some((e) => e.trabajadora_id === t[i] && e.fecha === fe[i] && e.franja === fr[i])) return; // ON CONFLICT DO NOTHING
        const f: Fila = { id: randomUUID(), trabajadora_id: t[i], farmacia: fa[i], fecha: fe[i], franja: fr[i], tipo: ti[i], estado: es[i],
          horas: ho[i] === null ? null : String(ho[i]), nota: no[i], created_at: AHORA, updated_at: AHORA };
        eventos.set(String(f.id), f);
        r.push(f);
      });
      return r;
    }
    if (sql === SQL.actualizarEventos) {
      const [ids, ti, es, ho, no] = p as unknown[][];
      return ids.map((id, i) => {
        const f = { ...eventos.get(String(id)), tipo: ti[i], estado: es[i], horas: ho[i] === null ? null : String(ho[i]), nota: no[i], updated_at: AHORA } as Fila;
        eventos.set(String(id), f);
        return f;
      });
    }
    return [];
  };
  const pool: PoolBd = {
    connect: async (): Promise<ClienteBd> => {
      if (o.falloConexion) throw o.falloConexion;
      const n = ++conexiones;
      return { query: async (sql, params) => { log.push({ cliente: n, sql, params }); return { rows: responder(sql, params) }; }, release: () => { liberadas++; } };
    },
    end: async () => {},
  };
  return { pool, log, eventos, cuenta: () => ({ conexiones, liberadas }) };
}
const errorPg = (code: string, message = 'x') => Object.assign(new Error(message), { code });
const sqls = (log: Consulta[]) => log.map((c) => c.sql);
const evento = (x: Partial<Fila>): Fila => ({
  id: randomUUID(), trabajadora_id: AINA, farmacia: 'PIO', fecha: '2026-11-09', franja: 'MANANA', tipo: 'JORNADA', estado: 'PLANIFICADO', horas: null, nota: null,
  created_at: T0, updated_at: T0, ...x,
});

describe('TA-REAL: errores de la base de datos → mensaje llano', () => {
  test('códigos del módulo y de PostgreSQL', () => {
    const casos: [unknown, string, number][] = [
      [errorPg('P0001', 'AUTOR_AUSENTE'), 'AUTOR_AUSENTE', 500],
      [errorPg('P0001', 'FARMACIA_NO_HABILITADA_EN_MODULO:FOO'), 'FARMACIA_NO_HABILITADA_EN_MODULO', 403],
      [errorPg('P0001', `EVENTO_FUERA_DEL_ALTA:${AINA}:2025-01-01`), 'EVENTO_FUERA_DEL_ALTA', 409],
      [errorPg('P0001', 'otro'), 'ERROR_BD', 500],
      [errorPg('42501'), 'PERMISO_DENEGADO', 403], [errorPg('23505'), 'DUPLICADO', 409], [errorPg('23514'), 'REGLA_TABLA', 400],
      [errorPg('23503'), 'REGISTRO_RELACIONADO', 409], [errorPg('57014'), 'TIEMPO_AGOTADO', 504], [errorPg('25P03'), 'TIEMPO_AGOTADO', 504],
      [errorPg('53300'), 'SIN_CONEXIONES', 503], [errorPg('ECONNREFUSED'), 'SIN_CONEXION', 503], [new Error('cualquier cosa'), 'ERROR_BD', 500],
    ];
    for (const [e, codigo, http] of casos) {
      const r = traducirErrorBd(e);
      assert.deepEqual([r.codigo, r.http, r.mensaje], [codigo, http, MENSAJES_BD[codigo as keyof typeof MENSAJES_BD].mensaje], codigo);
      assert.ok(!r.mensaje.includes('select') && !r.mensaje.includes(AINA), 'sin SQL ni datos');
    }
    assert.match(MENSAJES_BD.TIEMPO_AGOTADO.mensaje, /60 s/);
    assert.match(MENSAJES_BD.DUPLICADO.mensaje, /No se ha guardado nada/);
  });
});

describe('TA-REAL: configuración (credencial propia; Code nunca lee .env.web)', () => {
  const [VAR_USUARIO, VAR_CLAVE] = VARIABLES_TRAB;
  const VALOR_PRUEBA = 'valor-inventado-de-prueba';
  const env: Record<string, string | undefined> = {
    CF_LECTURA_HOST: 'aws-0-eu-west-1.pooler.supabase.com', CF_LECTURA_PORT: '5432', CF_LECTURA_DB: 'postgres',
    [VAR_USUARIO]: 'cf_trabajadores_web.ref', [VAR_CLAVE]: VALOR_PRUEBA,
  };
  const ca = () => '-----BEGIN CERTIFICATE-----ficticio';
  test('sin usuario o sin contraseña de Trabajadores: «Falta configurar la credencial de Trabajadores»', () => {
    for (const falta of VARIABLES_TRAB) {
      const c = configuracionRrhh({ ...env, [falta]: undefined }, ca);
      assert.deepEqual(c, { ok: false, codigo: 'CREDENCIAL_TRABAJADORES_AUSENTE', mensaje: MENSAJE_FALTA_CREDENCIAL });
    }
  });
  test('solo el rol cf_trabajadores_web (directo o del pooler); cualquier otro usuario no conecta', () => {
    for (const u of ['postgres', 'cf_lectura', 'cf_lectura.ref', 'usuario_inventado', 'cf_trabajadores_webx']) {
      assert.equal(configuracionRrhh({ ...env, [VAR_USUARIO]: u }, ca).ok, false, u);
    }
    assert.equal(configuracionRrhh({ ...env, [VAR_USUARIO]: 'cf_trabajadores_web' }, ca).ok, true);
  });
  test('pool de 2 conexiones, TLS con verificación de la CA; sin CA válida no conecta', () => {
    const c = configuracionRrhh(env, ca);
    assert.ok(c.ok);
    const cfg = c.ok ? c.config : null;
    assert.deepEqual([cfg?.max, MAX_CONEXIONES, cfg?.host, cfg?.port, cfg?.database, cfg?.user], [2, 2, env.CF_LECTURA_HOST, 5432, 'postgres', env[VAR_USUARIO]]);
    assert.deepEqual(cfg?.ssl, { rejectUnauthorized: true, ca: ca() });
    const sinCa = configuracionRrhh(env, () => { throw new Error('FALTA_CERTIFICADO_CA: falta certificado CA (x)'); });
    assert.deepEqual(sinCa.ok ? null : [sinCa.codigo, sinCa.mensaje], ['CERTIFICADO_CA', 'Certificado CA no válido: FALTA_CERTIFICADO_CA']);
    assert.equal(configuracionRrhh({ ...env, CF_LECTURA_HOST: undefined }, ca).ok, false);
    assert.equal(configuracionRrhh({ ...env, CF_LECTURA_PORT: 'x' }, ca).ok, false);
  });
});

describe('TA-REAL: contrato real (filas de la migración 31 → contrato)', () => {
  test('trabajadoras: numeric y fechas en texto; activa derivada', () => {
    const t = filaATrabajadora(FICHAS[1]);
    assert.deepEqual([t.horas_diarias, t.fecha_alta, t.fecha_baja, t.activa, t.created_at], [4.5, '2026-01-01', null, true, '2026-11-01T08:00:00.000Z']);
    assert.equal(filaATrabajadora({ ...FICHAS[0], fecha_baja: '2026-12-31' }).activa, false);
    assert.equal(filaATrabajadora({ ...FICHAS[0], anulada: true }).activa, false);
    assert.throws(() => filaATrabajadora({ ...FICHAS[0], categoria: 'TECNICO' }), /VALOR_NO_PREVISTO: categoria/); // falla cerrado
    assert.throws(() => filaATrabajadora({ ...FICHAS[0], farmacia: 'OTRA' }), /VALOR_NO_PREVISTO: farmacia/);
  });
  test('eventos: horas_efectivas de la vista; sin ella (tabla o jsonb), como la vista con la ficha', () => {
    const t = filaATrabajadora(FICHAS[0]);
    assert.equal(filaAEvento({ ...evento({}), horas_efectivas: '4.50' }, t).horas_efectivas, 4.5);
    assert.deepEqual([filaAEvento(evento({ franja: 'TARDE' }), t).horas, filaAEvento(evento({ franja: 'TARDE' }), t).horas_efectivas], [null, 3.5]);
    assert.equal(filaAEvento(evento({ horas: '2.25' }), t).horas_efectivas, 2.25);
    assert.equal(filaAEvento(evento({ tipo: 'TURNO_GUARDIA' }), t).tipo, 'TURNO_GUARDIA'); // los 11 tipos
    assert.throws(() => filaAEvento(evento({ tipo: 'GUARDIA' }), t), /VALOR_NO_PREVISTO: tipo/);
    assert.equal(instante('2026-11-13 10:00:00.123456+00'), '2026-11-13T10:00:00.123Z');
    assert.equal(instante('2026-11-13T10:00:00.5+01:00'), '2026-11-13T09:00:00.500Z');
  });
  test('historial de fichas desde trabajadores_historial (jsonb): alta, edición, baja y anulación', () => {
    const j = (x: Partial<Fila>) => ({ ...FICHAS[0], horas_diarias: 8, created_at: '2026-11-01T08:00:00+00:00', updated_at: '2026-11-01T08:00:00+00:00', ...x });
    const filas: Fila[] = [
      { id: '4', operacion: 'UPDATE', antes: j({ fecha_baja: '2026-12-31' }), despues: j({ fecha_baja: '2026-12-31', anulada: true }), autor: 'Marc', created_at: AHORA },
      { id: '3', operacion: 'UPDATE', antes: j({}), despues: j({ fecha_baja: '2026-12-31' }), autor: 'Marc', created_at: AHORA },
      { id: '2', operacion: 'UPDATE', antes: j({}), despues: j({ nombre: 'Aina B.' }), autor: 'Marc', created_at: AHORA },
      { id: '1', operacion: 'INSERT', antes: null, despues: j({}), autor: 'Marc', created_at: T0 },
    ];
    const h = historialFichas(filas);
    assert.deepEqual(h.map((x) => x.accion), ['ANULACION', 'BAJA', 'EDICION', 'ALTA']);
    assert.deepEqual([h[0].despues, h[1].despues, h[2].antes, h[2].despues], [{ anulada: true }, { fecha_baja: '2026-12-31' }, { nombre: 'Aina Bosch Ferrer' }, { nombre: 'Aina B.' }]);
    assert.ok(h.every((x) => x.quien === 'Marc' && x.entidad_id === AINA));
  });
  test('cambios del calendario: uno por transacción (mismo created_at); origen de la sesión o deducido', () => {
    const fichas = FICHAS.map(filaATrabajadora);
    const ev = (x: Partial<Fila>) => ({ ...evento({ id: 'a' }), created_at: '2026-11-13T10:00:00+00:00', updated_at: '2026-11-13T10:00:00+00:00', ...x });
    const filas: Fila[] = [
      { id: '9', grupo: 'G2', operacion: 'UPDATE', antes: ev({}), despues: ev({ estado: 'CONFIRMADO' }), autor: 'Marc', created_at: AHORA },
      { id: '7', grupo: 'G1', operacion: 'INSERT', antes: null, despues: ev({ id: 'b', fecha: '2026-11-10' }), autor: 'Marc', created_at: T0 },
      { id: '8', grupo: 'G1', operacion: 'INSERT', antes: null, despues: ev({ id: 'c', fecha: '2026-11-11' }), autor: 'Marc', created_at: T0 },
    ];
    const sinMarca = cambiosDesdeHistorial(filas, fichas, new Map());
    assert.deepEqual(sinMarca.map((c) => [c.origen, c.n, c.creados]), [['CONFIRMAR', 1, 0], ['RELLENAR', 2, 2]]);
    assert.equal(describirCambio(sinMarca[0]), 'Confirmado 9 nov 2026: 1 día laborable × 1 persona · 1 franja');
    const marca = { ...sinMarca[1], id: randomUUID(), origen: 'PINTAR', tipo: 'JORNADA', deshecho: true, periodo: { desde: '2026-11-09', hasta: '2026-11-15' } } as CambioCalendario;
    const conMarca = cambiosDesdeHistorial(filas, fichas, new Map([['G1', marca]]));
    assert.deepEqual([conMarca[1].id, conMarca[1].origen, conMarca[1].tipo, conMarca[1].deshecho], [marca.id, 'PINTAR', 'JORNADA', true]);
  });
  test('lotes', () => {
    assert.deepEqual(lotes([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]]);
    assert.equal(TAM_LOTE, 500);
  });
});

describe('TA-REAL: transacciones (simulado, sin conexión)', () => {
  test('cada escritura en su transacción con set_config(cf.autor, Marc, true) DENTRO; error de mapeo → ROLLBACK; conexión liberada', async () => {
    const bd = bdSimulada();
    const a = crearAdaptadorRrhhReal({ pool: bd.pool });
    const t = await Promise.resolve(a.crear({ farmacia: 'PIO', nombre: 'Ana Prueba', categoria: 'FARMACEUTICA_TITULAR', tipo_jornada: 'MEDIA_MANANA', horas_diarias: 4.5, fecha_alta: '2026-11-02' }, 'Marc'))
      .catch((e: unknown) => e);
    // La simulación no devuelve fila al insertar la ficha: el mapeo falla cerrado y se hace ROLLBACK.
    assert.ok(t instanceof ErrorRrhhBd);
    assert.deepEqual(sqls(bd.log).slice(0, 3), ['begin', SQL.autor, SQL.insertarFicha]);
    assert.deepEqual(bd.log[1].params, ['Marc']);
    assert.equal(bd.log[2].params?.[5], false); // titular: computa_convenio false
    assert.equal(sqls(bd.log).at(-1), 'rollback');
    assert.deepEqual(bd.cuenta(), { conexiones: 1, liberadas: 1 });
    // Nunca a nivel de sesión.
    assert.ok(!bd.log.some((c) => /set\s+(session\s+)?cf\.autor|set_config\('cf\.autor',\s*\$1,\s*false\)/i.test(c.sql)));
    assert.match(SQL.autor, /set_config\('cf\.autor', \$1, true\)/);
  });
  test('error de la BD: ROLLBACK, mensaje llano y sin reintento', async () => {
    const bd = bdSimulada({ fallo: (sql) => (sql === SQL.insertarEventos ? errorPg('23514') : null) });
    const a = crearAdaptadorRrhhReal({ pool: bd.pool });
    const p: PeticionEventos = { accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ trabajadora_id: AINA, fecha: '2026-12-07' }] };
    const e = await Promise.resolve(a.cambiarEventos(p, 'Marc')).catch((x: unknown) => x);
    assert.ok(e instanceof ErrorRrhhBd && e.codigo === 'REGLA_TABLA' && e.http === 400);
    assert.equal(sqls(bd.log).filter((s) => s === SQL.insertarEventos).length, 1); // nunca reintenta
    assert.ok(sqls(bd.log).includes('rollback') && !sqls(bd.log).includes('commit'));
    assert.equal(bd.eventos.size, 0);
    // El cambio fallido no queda en la sesión: no hay nada que deshacer.
    assert.equal((await a.calendario('PIO', '2026-12-07', '2026-12-13')).ultimo_cambio, null);
  });
  test('EVENTO_FUERA_DEL_ALTA del trigger y 53300 al conectar', async () => {
    const bd = bdSimulada({ fallo: (sql) => (sql === SQL.insertarEventos ? errorPg('P0001', `EVENTO_FUERA_DEL_ALTA:${AINA}:2026-12-07`) : null) });
    const e = await Promise.resolve(crearAdaptadorRrhhReal({ pool: bd.pool }).cambiarEventos({ accion: 'PINTAR', tipo: 'BAJA', celdas: [{ trabajadora_id: AINA, fecha: '2026-12-07' }] }, 'Marc'))
      .catch((x: unknown) => x);
    assert.ok(e instanceof ErrorRrhhBd && e.codigo === 'EVENTO_FUERA_DEL_ALTA');
    const sin = bdSimulada({ falloConexion: errorPg('53300') });
    const e2 = await Promise.resolve(crearAdaptadorRrhhReal({ pool: sin.pool }).calendario('PIO', '2026-12-07', '2026-12-13')).catch((x: unknown) => x);
    assert.ok(e2 instanceof ErrorRrhhBd && e2.codigo === 'SIN_CONEXIONES' && e2.http === 503);
  });
  test('rellenar el año: INSERT … ON CONFLICT DO NOTHING por lotes, en una sola transacción con autor', async () => {
    const bd = bdSimulada({ eventos: [evento({ fecha: '2026-11-09', franja: 'MANANA', tipo: 'VACACIONES' })] });
    const a = crearAdaptadorRrhhReal({ pool: bd.pool, tamLote: 200 });
    const r = await a.cambiarEventos({ accion: 'RELLENAR', trabajadora_ids: [AINA, ELENA], desde: '2026-01-01', hasta: '2026-12-31' }, 'Marc');
    assert.equal(typeof r, 'object');
    const res = r as Exclude<typeof r, string>;
    // 261 laborables: Aina 2 franjas (menos la mañana del 9 nov, ya pintada) + Elena 1 = 782 altas → 4 lotes de 200.
    assert.equal(res.cambio?.n, 261 * 3 - 1);
    assert.equal(describirCambio(res.cambio!), 'Rellenado 2026: 261 días laborables × 2 personas · 782 franjas');
    const inserts = bd.log.filter((c) => c.sql === SQL.insertarEventos);
    assert.equal(inserts.length, 4);
    assert.ok(inserts.every((c) => (c.params?.[0] as unknown[]).length <= 200));
    assert.match(SQL.insertarEventos, /on conflict \(trabajadora_id, fecha, franja\) do nothing/);
    assert.deepEqual(sqls(bd.log).filter((s) => s === 'begin' || s === SQL.autor || s === 'commit'), ['begin', SQL.autor, 'commit']);
    assert.ok(inserts.every((c) => (c.params?.[6] as unknown[]).every((h) => h === null))); // horas vacías: las de la ficha
  });
  test('goma y deshacer de pintados nuevos desactivados; deshacer de estado/tipo/nota sí (UPDATE al valor anterior)', async () => {
    const e9 = evento({ fecha: '2026-11-09' });
    const bd = bdSimulada({ eventos: [e9] });
    const a = crearAdaptadorRrhhReal({ pool: bd.pool });
    assert.equal(a.anularEventos, false);
    assert.equal(await a.cambiarEventos({ accion: 'BORRAR', celdas: [{ trabajadora_id: AINA, fecha: '2026-11-09' }] }, 'Marc'), 'ANULAR_EVENTOS_PENDIENTE');
    assert.equal(bd.cuenta().conexiones, 0); // ni siquiera conecta
    const pintado = await a.cambiarEventos({ accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ trabajadora_id: AINA, fecha: '2026-12-07' }] }, 'Marc');
    const idP = (pintado as { cambio: { id: string; creados: number } }).cambio;
    assert.equal(idP.creados, 2);
    assert.equal(await a.deshacerEventos(idP.id, 'Marc'), 'ANULAR_EVENTOS_PENDIENTE');
    const conf = await a.cambiarEventos({ accion: 'CONFIRMAR', celdas: [{ trabajadora_id: AINA, fecha: '2026-11-09', franja: 'MANANA' }] }, 'Marc');
    const c = (conf as { cambio: { id: string } }).cambio;
    assert.equal(bd.eventos.get(String(e9.id))?.estado, 'CONFIRMADO');
    assert.equal((await a.calendario('PIO', '2026-11-09', '2026-11-15')).ultimo_cambio?.id, c.id);
    const d = await a.deshacerEventos(c.id, 'Marc');
    assert.equal(typeof d, 'object');
    assert.equal(bd.eventos.get(String(e9.id))?.estado, 'PLANIFICADO');
    assert.equal(describirCambio((d as { cambio: Omit<CambioCalendario, 'trazas'> }).cambio),'Deshecho «Confirmado 9 nov 2026»: 1 día laborable × 1 persona · 1 franja');
    // Si alguien lo cambió entre medias, no se deshace nada.
    const conf2 = (await a.cambiarEventos({ accion: 'CONFIRMAR', celdas: [{ trabajadora_id: AINA, fecha: '2026-11-09', franja: 'MANANA' }] }, 'Marc')) as { cambio: { id: string } };
    bd.eventos.set(String(e9.id), { ...bd.eventos.get(String(e9.id)), nota: 'cambiada fuera' } as Fila);
    assert.equal(await a.deshacerEventos(conf2.cambio.id, 'Marc'), 'ESTADO_CAMBIADO');
  });
  test('lectura: transacción READ ONLY con ROLLBACK, sin autor; horas de la vista v_eventos_calendario_horas', async () => {
    const bd = bdSimulada({ eventos: [evento({ franja: 'TARDE' })] });
    const cal = await crearAdaptadorRrhhReal({ pool: bd.pool }).calendario('PIO', '2026-11-09', '2026-11-15');
    assert.deepEqual(sqls(bd.log), ['begin transaction read only', SQL.fichasPeriodo, SQL.eventosPeriodo, 'rollback']);
    assert.match(SQL.eventosPeriodo, /from public\.v_eventos_calendario_horas/);
    assert.deepEqual([cal.eventos[0].horas_efectivas, cal.anular_eventos], [3.5, false]);
  });
  test('diagnóstico (check:real): recuentos, módulo PIO/RITA y años del convenio; solo lectura', async () => {
    const log: string[] = [];
    const pool: PoolBd = {
      connect: async () => ({
        query: async (sql) => {
          log.push(sql);
          return { rows: sql === SQL.diagnostico ? [{ trabajadoras: '13', convenio_anual: '2', eventos_calendario: '0', guardias_farmacia: '0', festivos: '0',
            trabajadores_historial: '15', modulo: ['RITA', 'PIO'], anios: [2026, 2027] }] : [] };
        },
        release: () => {},
      }),
      end: async () => {},
    };
    const d = await crearAdaptadorRrhhReal({ pool }).diagnostico();
    assert.deepEqual(d, { trabajadoras: 13, convenio_anual: 2, eventos_calendario: 0, guardias_farmacia: 0, festivos: 0, trabajadores_historial: 15,
      modulo_pio_rita: true, anios_convenio: [2026, 2027], anios_convenio_faltan: [2028] });
    assert.deepEqual(log, ['begin transaction read only', SQL.diagnostico, 'rollback']);
    assert.ok(!/insert|update|delete/i.test(SQL.diagnostico));
  });
});

describe('TA-REAL: API en modo REAL con el adaptador simulado', async () => {
  const bd = bdSimulada({ fallo: (sql) => (sql === SQL.insertarFicha ? errorPg('23505') : sql === SQL.historialEventos ? errorPg('57014') : null) });
  const app = Fastify();
  registrarRrhh(app, { modo: 'REAL', quien: 'Marc', adaptador: crearAdaptadorRrhhReal({ pool: bd.pool }), sesionValida: (req) => req.headers.cookie === 'cf_sesion=ok' });
  await app.ready();
  after(() => app.close());
  const H = { host: '127.0.0.1:4747', cookie: 'cf_sesion=ok' };
  const W = { ...H, origin: 'http://127.0.0.1:4747', 'content-type': 'application/json' };

  test('estado: conectado, sin «datos de ejemplo», goma desactivada', async () => {
    const e = await app.inject({ method: 'GET', url: '/api/rrhh/estado', headers: H });
    assert.deepEqual(e.json(), { modo: 'REAL', conectado: true, datos_ejemplo: false, mensaje: TEXTO_BANNER_REAL, anular_eventos: false });
    assert.ok(!/ejemplo/i.test(TEXTO_BANNER_REAL));
  });
  test('errores de la BD con su mensaje llano: duplicado 409, tiempo agotado 504; anular eventos 409', async () => {
    const dup = await app.inject({ method: 'POST', url: '/api/rrhh/trabajadoras', headers: W,
      payload: { farmacia: 'PIO', nombre: 'Aina Bosch Ferrer', categoria: 'TECNICA', tipo_jornada: 'COMPLETA', horas_diarias: 8, fecha_alta: '2026-01-01' } });
    assert.deepEqual([dup.statusCode, dup.json()], [409, { error: 'DUPLICADO', mensaje: MENSAJES_BD.DUPLICADO.mensaje }]);
    const lento = await app.inject({ method: 'GET', url: '/api/rrhh/eventos/historial?farmacia=PIO', headers: H });
    assert.deepEqual([lento.statusCode, lento.json().error], [504, 'TIEMPO_AGOTADO']);
    const goma = await app.inject({ method: 'POST', url: '/api/rrhh/eventos', headers: W, payload: { accion: 'BORRAR', celdas: [{ trabajadora_id: AINA, fecha: '2026-11-09' }] } });
    assert.deepEqual([goma.statusCode, goma.json()], [409, { error: 'ANULAR_EVENTOS_PENDIENTE', mensaje: AVISO_ANULAR_PENDIENTE }]);
  });
  test('la franja contraria a la media jornada se sigue rechazando', async () => {
    const r = await app.inject({ method: 'POST', url: '/api/rrhh/eventos', headers: W,
      payload: { accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ trabajadora_id: ELENA, fecha: '2026-12-07', franja: 'TARDE' }] } });
    assert.deepEqual([r.statusCode, r.json().error], [400, 'FRANJA_NO_VALIDA']);
  });
});
