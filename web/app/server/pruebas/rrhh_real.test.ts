// TA-REAL: adaptador RRHH_REAL simulado SIN CONEXIÓN (pool inyectado con una base de datos en memoria). Comprueba:
// mapeo de errores de la BD a mensajes llanos, autor por transacción (set_config local, nunca de sesión), ROLLBACK ante
// error y sin reintentos, lotes al rellenar, contrato real (filas de la migración 31 → contrato), historial desde
// trabajadores_historial y la API en modo REAL. Nunca abre una conexión real ni lee .env.
// TA-REAL-2 (esquema de la migración 33, simulado en memoria): eventos_calendario.anulado (goma y deshacer anulan;
// inserción ON CONFLICT … WHERE NOT anulado; lecturas sin anulados), convenio_anual con vacaciones y
// trabajadoras_ajustes_anuales (TA-REAL-2b: columnas de producción, sin autor; autor solo por cf.autor). Uso: npm run test:unit
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { after, describe, test } from 'node:test';
import Fastify from 'fastify';
import { FUENTE_VACACIONES, MENSAJE_FALTA_CREDENCIAL, TEXTO_BANNER_REAL } from '../rrhh/contrato.ts';
import { ErrorRrhhBd, MENSAJES_BD, traducirErrorBd } from '../rrhh/errores_bd.ts';
import {
  MAX_CONEXIONES, SQL, TAM_LOTE, VARIABLES_TRAB, cambiosDesdeHistorial, configuracionRrhh, crearAdaptadorRrhhReal, filaAAjuste, filaAConvenio, filaAEvento,
  filaATrabajadora, historialFichas, instante, lotes, type ClienteBd, type Fila, type PoolBd,
} from '../rrhh/adaptador_real.ts';
import { registrarRrhh } from '../rrhh/rutas.ts';
import { describirCambio, type CambioCalendario, type PeticionEventos } from '../rrhh/eventos.ts';

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
/** Convenio como lo devuelve pg (numeric en texto); TA-REAL-2: con o sin las columnas de vacaciones. */
const filaConvenio = (anio: number, vac: number | null): Fila => ({
  anio, jornada_max_horas: '1767.00', asuntos_propios_dias: '1.00', permiso_medico_horas: '24.00', horas_semanales_referencia: '40.00',
  estado: 'FIRMADO_PENDIENTE_PUBLICACION', fuente: 'x', vacaciones_dias_naturales: vac, vacaciones_fuente: vac === null ? null : FUENTE_VACACIONES,
});
/** TA-REAL-2b: columnas de producción de trabajadoras_ajustes_anuales (sin autor). */
const COLUMNAS_AJUSTES = ['id', 'trabajadora_id', 'farmacia', 'anio', 'vacaciones_dias_extra', 'nota', 'anulada', 'created_at', 'updated_at'];
/** Ajuste como lo devuelve pg (columnas de producción). */
const filaAjuste = (x: Partial<Fila>): Fila => ({
  id: randomUUID(), trabajadora_id: AINA, farmacia: 'PIO', anio: 2026, vacaciones_dias_extra: 2, nota: null, anulada: false, created_at: T0, updated_at: T0, ...x,
});
/**
 * Base de datos simulada con el esquema de la migración 33: eventos con anulado (unicidad de persona, día y franja solo
 * entre los no anulados; la vista excluye los anulados), convenio con vacaciones y ajustes anuales.
 * TA-REAL-2b, como producción en trabajadoras_ajustes_anuales: una sentencia que nombra la columna autor (inexistente)
 * falla con 42703; escribir sin cf.autor en la transacción falla con P0001 AUTOR_AUSENTE (el trigger del historial);
 * farmacia obligatoria y del módulo (PIO o RITA). `sinAutor`: set_config no llega (simula que falta cf.autor).
 */
function bdSimulada(o: { eventos?: Fila[]; convenio?: Fila[]; ajustes?: Fila[]; fallo?: (sql: string, params?: unknown[]) => unknown; falloConexion?: unknown;
  sinAutor?: boolean } = {}) {
  const eventos = new Map<string, Fila>((o.eventos ?? []).map((e) => [String(e.id), { anulado: false, ...e }]));
  const convenio = (o.convenio ?? []).map((c) => ({ ...c }));
  const ajustes = (o.ajustes ?? []).map((a) => ({ ...a }));
  const log: Consulta[] = [];
  let conexiones = 0;
  let liberadas = 0;
  const en = (lista: unknown, v: unknown) => (lista as unknown[]).includes(v);
  const vivos = () => [...eventos.values()].filter((e) => e.anulado !== true);
  /** cf.autor local de la transacción de cada conexión (se pierde en commit / rollback). */
  const autorDe = new Map<number, string | null>();
  const responder = (cliente: number, sql: string, p: unknown[] = []): Fila[] => {
    const err = o.fallo?.(sql, p);
    if (err) throw err;
    if (sql === 'begin' || sql === 'commit' || sql === 'rollback') { autorDe.set(cliente, null); return []; }
    if (sql === SQL.autor) { if (!o.sinAutor) autorDe.set(cliente, String(p[0])); return []; }
    if (/^(insert into|update) public\.trabajadoras_ajustes_anuales\b/.test(sql)) {
      if (/\bautor\b/.test(sql)) throw errorPg('42703', 'column "autor" of relation "trabajadoras_ajustes_anuales" does not exist');
      if (!autorDe.get(cliente)) throw errorPg('P0001', 'AUTOR_AUSENTE');
    }
    if (sql === SQL.ahora) return [{ ahora: AHORA }];
    if (sql === SQL.fichasPorId) return FICHAS.filter((f) => en(p[0], f.id));
    if (sql === SQL.fichasTodas || sql === SQL.fichasPeriodo) return FICHAS;
    if (sql === SQL.ficha) return FICHAS.filter((f) => f.id === p[0]);
    if (sql === SQL.historialFicha) return [];
    if (sql === SQL.convenio) return convenio.map((c) => ({ ...c }));
    if (sql === SQL.completarVacaciones) {
      return convenio.filter((c) => en(p[0], c.anio) && c.vacaciones_dias_naturales === null).map((c) => Object.assign(c, { vacaciones_dias_naturales: p[1], vacaciones_fuente: p[2] }));
    }
    if (sql === SQL.ajustes) return ajustes.filter((a) => a.anio === p[1] && a.anulada !== true && FICHAS.some((f) => f.id === a.trabajadora_id && en(p[0], f.farmacia)));
    if (sql === SQL.ajusteBloqueo) return ajustes.filter((a) => a.trabajadora_id === p[0] && a.anio === p[1] && a.anulada !== true);
    if (sql === SQL.insertarAjuste) {
      const [tid, farmacia, anio, dias, nota] = p;
      if (farmacia !== 'PIO' && farmacia !== 'RITA') throw errorPg('P0001', `FARMACIA_NO_HABILITADA_EN_MODULO:${String(farmacia)}`);
      if (ajustes.some((a) => a.trabajadora_id === tid && a.anio === anio && a.anulada !== true)) throw errorPg('23505'); // única entre no anuladas
      const f = filaAjuste({ trabajadora_id: tid, farmacia, anio, vacaciones_dias_extra: dias, nota, created_at: AHORA, updated_at: AHORA });
      ajustes.push(f);
      return [{ ...f }];
    }
    if (sql === SQL.actualizarAjuste) {
      return ajustes.filter((a) => a.id === p[0] && a.anulada !== true).map((a) => ({ ...Object.assign(a, { vacaciones_dias_extra: p[1], nota: p[2], updated_at: AHORA }) }));
    }
    if (sql === SQL.anularAjuste) return ajustes.filter((a) => a.id === p[0] && a.anulada !== true).map((a) => ({ ...Object.assign(a, { anulada: true, updated_at: AHORA }) }));
    if (sql === SQL.eventosRangoBloqueo) return vivos().filter((e) => en(p[0], e.trabajadora_id) && String(e.fecha) >= String(p[1]) && String(e.fecha) <= String(p[2]));
    if (sql === SQL.eventosCeldasBloqueo) return vivos().filter((e) => en(p[0], e.trabajadora_id) && en(p[1], e.fecha));
    if (sql === SQL.eventosPorIdBloqueo) return vivos().filter((e) => en(p[0], e.id));
    if (sql === SQL.eventoBloqueo) return vivos().filter((e) => e.id === p[0]);
    // La vista v_eventos_calendario_horas ya excluye los anulados.
    if (sql === SQL.eventosPeriodo) return vivos().map((e) => ({ ...e, horas_efectivas: e.horas ?? (e.franja === 'MANANA' ? '4.50' : '3.50') }));
    if (sql === SQL.insertarEventos) {
      const [t, fa, fe, fr, ti, es, ho, no] = p as unknown[][];
      const r: Fila[] = [];
      t.forEach((_, i) => {
        if (vivos().some((e) => e.trabajadora_id === t[i] && e.fecha === fe[i] && e.franja === fr[i])) return; // ON CONFLICT … WHERE NOT anulado DO NOTHING
        const f: Fila = { id: randomUUID(), trabajadora_id: t[i], farmacia: fa[i], fecha: fe[i], franja: fr[i], tipo: ti[i], estado: es[i],
          horas: ho[i] === null ? null : String(ho[i]), nota: no[i], anulado: false, created_at: AHORA, updated_at: AHORA };
        eventos.set(String(f.id), f);
        r.push(f);
      });
      return r;
    }
    if (sql === SQL.actualizarEventos) {
      const [ids, ti, es, ho, no] = p as unknown[][];
      return ids.filter((id) => eventos.get(String(id))?.anulado === false).map((id) => {
        const i = ids.indexOf(id);
        const f = { ...eventos.get(String(id)), tipo: ti[i], estado: es[i], horas: ho[i] === null ? null : String(ho[i]), nota: no[i], updated_at: AHORA } as Fila;
        eventos.set(String(id), f);
        return f;
      });
    }
    if (sql === SQL.anularEventos) {
      return vivos().filter((e) => en(p[0], e.id) && e.estado !== 'CONFIRMADO').map((e) => {
        const f = { ...e, anulado: true, updated_at: AHORA };
        eventos.set(String(e.id), f);
        return f;
      });
    }
    return [];
  };
  const pool: PoolBd = {
    connect: async (): Promise<ClienteBd> => {
      if (o.falloConexion) throw o.falloConexion;
      const n = ++conexiones;
      return { query: async (sql, params) => { log.push({ cliente: n, sql, params }); return { rows: responder(n, sql, params) }; }, release: () => { liberadas++; } };
    },
    end: async () => {},
  };
  return { pool, log, eventos, convenio, ajustes, cuenta: () => ({ conexiones, liberadas }) };
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

describe('TA-REAL-2: esquema de la migración 33 (convenio con vacaciones, eventos anulados, ajustes anuales)', () => {
  test('toda consulta a eventos_calendario excluye los anulados; nunca DELETE; la vista no se filtra (ya los excluye)', () => {
    const tabla = Object.entries(SQL).filter(([, s]) => /from public\.eventos_calendario|update public\.eventos_calendario/.test(s));
    assert.deepEqual(tabla.map(([k]) => k).sort(), ['actualizarEventos', 'anularEventos', 'diagnostico', 'eventoBloqueo', 'eventosCeldasBloqueo', 'eventosPorIdBloqueo', 'eventosRangoBloqueo']);
    for (const [k, s] of tabla) assert.match(s, /not (e\.)?anulado/, k);
    assert.match(SQL.diagnostico, /count\(\*\) from public\.eventos_calendario where not anulado/);
    assert.ok(Object.values(SQL).every((s) => !/\bdelete\b/i.test(s)));
    assert.match(SQL.anularEventos, /set anulado = true where id = any\(\$1::uuid\[\]\) and not anulado and estado <> 'CONFIRMADO'/);
  });
  test('convenio: columnas nuevas (sin dato → null, nunca 0); crear con 30 días y la fuente; completar solo esos dos campos y solo si faltan', async () => {
    assert.deepEqual([filaAConvenio(filaConvenio(2026, null)).vacaciones_dias_naturales, filaAConvenio(filaConvenio(2026, null)).vacaciones_fuente], [null, null]);
    assert.equal(filaAConvenio({ ...filaConvenio(2026, null), vacaciones_dias_naturales: undefined }).vacaciones_dias_naturales, null);
    assert.deepEqual([filaAConvenio(filaConvenio(2027, 30)).vacaciones_dias_naturales, filaAConvenio(filaConvenio(2027, 30)).vacaciones_fuente], [30, FUENTE_VACACIONES]);
    const bd = bdSimulada({ convenio: [filaConvenio(2026, null), filaConvenio(2027, 30)] });
    const a = crearAdaptadorRrhhReal({ pool: bd.pool });
    await Promise.resolve(a.crearConvenio([2028], 'Marc')).catch(() => null); // la simulación no inserta; se miran los parámetros
    const crear = bd.log.find((c) => c.sql === SQL.crearConvenio);
    assert.deepEqual([crear?.params?.[7], crear?.params?.[8]], [[30], [FUENTE_VACACIONES]]);
    assert.match(SQL.crearConvenio, /vacaciones_dias_naturales, vacaciones_fuente\) select \* from unnest/);
    const hechos = await a.completarVacacionesConvenio([2026, 2027], 'Marc');
    assert.deepEqual(hechos.map((c) => [c.anio, c.vacaciones_dias_naturales, c.vacaciones_fuente]), [[2026, 30, FUENTE_VACACIONES]]);
    assert.match(SQL.completarVacaciones, /^update public\.convenio_anual set vacaciones_dias_naturales = \$2, vacaciones_fuente = \$3 where anio = any\(\$1::int\[\]\) and vacaciones_dias_naturales is null returning \*$/);
    const c = bd.log.filter((x) => x.sql === SQL.completarVacaciones);
    assert.deepEqual(c.map((x) => x.params), [[[2026, 2027], 30, FUENTE_VACACIONES]]);
    const i = bd.log.indexOf(c[0]);
    assert.deepEqual([bd.log[i - 2].sql, bd.log[i - 1].sql, bd.log[i - 1].params, bd.log[i + 1].sql], ['begin', SQL.autor, ['Marc'], 'commit']);
  });
  test('TA-REAL-2b: ajustes: guardar (INSERT con la farmacia de la ficha, sin columna autor), editar, sin cambios no escribe, anular; autor solo por cf.autor', async () => {
    const bd = bdSimulada();
    const a = crearAdaptadorRrhhReal({ pool: bd.pool });
    assert.equal(await a.anularAjuste(AINA, 2026, 'Marc'), 'SIN_AJUSTE');
    const g = await a.guardarAjuste(AINA, 2026, 2, 'Acuerdo', 'Marc');
    assert.deepEqual([g.vacaciones_dias_extra, g.nota, g.farmacia, g.anulada], [2, 'Acuerdo', 'PIO', false]);
    assert.ok(!('autor' in g));
    const ins = bd.log.find((c) => c.sql === SQL.insertarAjuste);
    assert.deepEqual(ins?.params, [AINA, 'PIO', 2026, 2, 'Acuerdo']); // farmacia de la ficha; nunca el autor
    assert.deepEqual(Object.keys(bd.ajustes[0]).sort(), [...COLUMNAS_AJUSTES].sort()); // columnas de producción
    for (const s of [SQL.insertarAjuste, SQL.actualizarAjuste, SQL.anularAjuste]) assert.ok(!/\bautor\b/.test(s), s);
    const e = await a.guardarAjuste(AINA, 2026, 3, null, 'Marc');
    assert.deepEqual([e.id, e.vacaciones_dias_extra, e.nota], [g.id, 3, null]);
    const n = bd.log.length;
    await a.guardarAjuste(AINA, 2026, 3, null, 'Marc');
    assert.ok(!bd.log.slice(n).some((c) => c.sql === SQL.actualizarAjuste || c.sql === SQL.insertarAjuste)); // sin cambios
    assert.deepEqual((await a.ajustes('PIO', 2026)).map((x) => x.vacaciones_dias_extra), [3]);
    assert.deepEqual(await a.ajustes('RITA', 2026), []);
    const an = await a.anularAjuste(AINA, 2026, 'Marc');
    assert.equal(typeof an === 'object' && an.anulada, true);
    assert.deepEqual(await a.ajustes('PIO', 2026), []);
    // Tras anular, se puede crear otro (único entre no anulados).
    assert.notEqual((await a.guardarAjuste(AINA, 2026, 1, null, 'Marc')).id, g.id);
    // Toda escritura, con set_config(cf.autor) dentro de su transacción.
    assert.equal(bd.log.filter((c) => c.sql === SQL.autor).length, bd.log.filter((c) => c.sql === 'begin').length);
    for (const i of bd.log.map((c, k) => (c.sql === SQL.insertarAjuste || c.sql === SQL.actualizarAjuste || c.sql === SQL.anularAjuste ? k : -1)).filter((k) => k >= 0)) {
      const desde = bd.log.slice(0, i).map((c) => c.sql).lastIndexOf('begin');
      assert.ok(bd.log.slice(desde, i).some((c) => c.sql === SQL.autor && (c.params as unknown[])[0] === 'Marc'), bd.log[i].sql);
    }
    assert.throws(() => filaAAjuste(filaAjuste({ vacaciones_dias_extra: -1 })), /VALOR_NO_PREVISTO/);
    assert.throws(() => filaAAjuste(filaAjuste({ farmacia: 'OTRA' })), /VALOR_NO_PREVISTO: farmacia/);
    assert.equal(filaAAjuste(filaAjuste({ vacaciones_dias_extra: '2' })).vacaciones_dias_extra, 2);
  });
  test('TA-REAL-2b: la base simulada rechaza la columna autor (42703) y la escritura sin cf.autor (AUTOR_AUSENTE), como producción', async () => {
    const bd = bdSimulada();
    const c = await bd.pool.connect();
    await c.query('begin');
    await c.query(SQL.autor, ['Marc']);
    await assert.rejects(c.query('insert into public.trabajadoras_ajustes_anuales (trabajadora_id, farmacia, anio, vacaciones_dias_extra, nota, autor) values ($1, $2, $3, $4, $5, $6) returning *',
      [AINA, 'PIO', 2026, 1, null, 'Marc']), (e: { code?: string }) => e.code === '42703');
    await c.query('rollback');
    await c.query('begin');
    await assert.rejects(c.query(SQL.insertarAjuste, [AINA, 'PIO', 2026, 1, null]), (e: Error & { code?: string }) => e.code === 'P0001' && e.message === 'AUTOR_AUSENTE');
    await c.query('rollback');
    c.release();
    assert.equal(bd.ajustes.length, 0);
  });
  test('TA-REAL-2b: guardar y anular un ajuste sin cf.autor: error controlado (AUTOR_AUSENTE, mensaje llano), ROLLBACK y nada guardado', async () => {
    const previo = filaAjuste({ id: 'aj-previo', trabajadora_id: ELENA, vacaciones_dias_extra: 4, nota: 'antes' });
    const bd = bdSimulada({ sinAutor: true, ajustes: [previo] });
    const a = crearAdaptadorRrhhReal({ pool: bd.pool });
    // Guardar uno nuevo (INSERT).
    const e1 = await Promise.resolve(a.guardarAjuste(AINA, 2026, 2, 'x', 'Marc')).catch((x: unknown) => x);
    assert.ok(e1 instanceof ErrorRrhhBd && e1.codigo === 'AUTOR_AUSENTE' && e1.http === 500, String(e1));
    assert.equal(e1.mensaje, MENSAJES_BD.AUTOR_AUSENTE.mensaje);
    // Editar el existente (UPDATE) y anularlo.
    const e2 = await Promise.resolve(a.guardarAjuste(ELENA, 2026, 9, null, 'Marc')).catch((x: unknown) => x);
    const e3 = await Promise.resolve(a.anularAjuste(ELENA, 2026, 'Marc')).catch((x: unknown) => x);
    assert.ok([e2, e3].every((e) => e instanceof ErrorRrhhBd && e.codigo === 'AUTOR_AUSENTE'));
    // Nada guardado: sin filas nuevas y el existente intacto; cada intento termina en ROLLBACK, sin COMMIT ni reintento.
    assert.equal(bd.ajustes.length, 1);
    assert.deepEqual([bd.ajustes[0].vacaciones_dias_extra, bd.ajustes[0].nota, bd.ajustes[0].anulada], [4, 'antes', false]);
    assert.equal(sqls(bd.log).filter((s) => s === 'rollback').length, 3);
    assert.ok(!sqls(bd.log).includes('commit'));
    assert.equal(sqls(bd.log).filter((s) => s === SQL.insertarAjuste || s === SQL.actualizarAjuste || s === SQL.anularAjuste).length, 3);
    assert.deepEqual(bd.cuenta(), { conexiones: 3, liberadas: 3 });
  });
  test('TA-REAL-2b: eventos, convenio y fichas no escriben ninguna columna autor (solo set_config local)', () => {
    const escrituras = Object.entries(SQL).filter(([, s]) => /^(insert|update)\b/i.test(s));
    assert.ok(escrituras.length >= 12);
    const conAutor = escrituras.filter(([, s]) => /\bautor\b/i.test(s)).map(([k]) => k);
    assert.deepEqual(conAutor, []);
    assert.equal(SQL.autor, "select set_config('cf.autor', $1, true)");
  });
  test('historial: un UPDATE que pone anulado = true es un borrado («Borrado …»)', () => {
    const fichas = FICHAS.map(filaATrabajadora);
    const ev = (x: Partial<Fila>) => ({ ...evento({ id: 'a' }), anulado: false, created_at: '2026-11-13T10:00:00+00:00', updated_at: '2026-11-13T10:00:00+00:00', ...x });
    const filas: Fila[] = [{ id: '9', grupo: 'G3', operacion: 'UPDATE', antes: ev({}), despues: ev({ anulado: true }), autor: 'Marc', created_at: AHORA }];
    const c = cambiosDesdeHistorial(filas, fichas, new Map());
    assert.deepEqual([c[0].origen, c[0].trazas[0].accion, c[0].trazas[0].despues], ['BORRAR', 'BORRAR', null]);
    assert.equal(describirCambio(c[0]), 'Borrado 9 nov 2026: 1 día laborable × 1 persona · 1 franja');
  });
  test('ficha anual en REAL con convenio de vacaciones y un ajuste: base + extra; solo lectura', async () => {
    const bd = bdSimulada({ convenio: [filaConvenio(2026, 30)], ajustes: [filaAjuste({ id: 'aj1' })] });
    const appF = Fastify();
    registrarRrhh(appF, { modo: 'REAL', quien: 'Marc', adaptador: crearAdaptadorRrhhReal({ pool: bd.pool }), sesionValida: () => true });
    await appF.ready();
    try {
      const r = await appF.inject({ method: 'GET', url: `/api/rrhh/trabajadoras/${AINA}/anual?anio=2026&hoy=2026-11-13`, headers: { host: '127.0.0.1:4747' } });
      assert.equal(r.statusCode, 200, r.body);
      const v = r.json().ficha.vacaciones;
      assert.deepEqual([v.base, v.dias_extra, v.derecho, v.fuente], [30, 2, 32, FUENTE_VACACIONES]);
      assert.ok(sqls(bd.log).every((q) => q === 'begin transaction read only' || q === 'rollback' || /^select /i.test(q)));
    } finally {
      await appF.close();
    }
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
    assert.match(SQL.insertarEventos, /on conflict \(trabajadora_id, fecha, franja\) where not anulado do nothing returning \*$/);
    assert.deepEqual(sqls(bd.log).filter((s) => s === 'begin' || s === SQL.autor || s === 'commit'), ['begin', SQL.autor, 'commit']);
    assert.ok(inserts.every((c) => (c.params?.[6] as unknown[]).every((h) => h === null))); // horas vacías: las de la ficha
  });
  test('TA-REAL-2: goma = UPDATE anulado = true (nunca DELETE), con autor; la franja queda libre y no se lee; lo confirmado no se toca', async () => {
    const e9 = evento({ fecha: '2026-11-09' });
    const e9t = evento({ fecha: '2026-11-09', franja: 'TARDE' });
    const conf = evento({ fecha: '2026-11-10', estado: 'CONFIRMADO' });
    const bd = bdSimulada({ eventos: [e9, e9t, conf] });
    const a = crearAdaptadorRrhhReal({ pool: bd.pool });
    const r = await a.cambiarEventos({ accion: 'BORRAR', celdas: [{ trabajadora_id: AINA, fecha: '2026-11-09' }, { trabajadora_id: AINA, fecha: '2026-11-10' }] }, 'Marc');
    const res = r as Exclude<typeof r, string>;
    assert.deepEqual([res.cambio?.n, res.cambio?.origen, res.omitidas_confirmadas], [2, 'BORRAR', 1]); // el 10 tiene solo la mañana, confirmada
    assert.deepEqual(sqls(bd.log).filter((s) => s !== SQL.fichasPorId), ['begin', SQL.autor, SQL.ahora, SQL.eventosCeldasBloqueo, SQL.anularEventos, 'commit']);
    assert.ok(!bd.log.some((c) => /\bdelete\b/i.test(c.sql)), 'nunca DELETE');
    assert.deepEqual([bd.eventos.get(String(e9.id))?.anulado, bd.eventos.get(String(e9t.id))?.anulado, bd.eventos.get(String(conf.id))?.anulado], [true, true, false]);
    const cal = await a.calendario('PIO', '2026-11-09', '2026-11-15');
    assert.deepEqual(cal.eventos.map((e) => e.fecha), ['2026-11-10']); // los anulados no se leen
    // La franja anulada se vuelve a pintar (la unicidad solo cuenta los no anulados).
    const p = await a.cambiarEventos({ accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ trabajadora_id: AINA, fecha: '2026-11-09', franja: 'MANANA' }] }, 'Marc');
    assert.equal((p as { cambio: { creados: number } }).cambio.creados, 1);
    assert.equal(bd.eventos.size, 4);
  });
  test('TA-REAL-2: deshacer un pintado anula lo creado; deshacer la goma recrea las franjas (fila nueva); si se ocupan entre medias, ESTADO_CAMBIADO y ROLLBACK', async () => {
    const e9 = evento({ fecha: '2026-11-09' });
    const bd = bdSimulada({ eventos: [e9] });
    const a = crearAdaptadorRrhhReal({ pool: bd.pool });
    const pintado = (await a.cambiarEventos({ accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ trabajadora_id: AINA, fecha: '2026-12-07' }] }, 'Marc')) as { cambio: { id: string; creados: number } };
    assert.equal(pintado.cambio.creados, 2);
    const d = await a.deshacerEventos(pintado.cambio.id, 'Marc');
    assert.equal(typeof d, 'object');
    assert.ok([...bd.eventos.values()].filter((e) => e.fecha === '2026-12-07').every((e) => e.anulado === true));
    // Goma y deshacer de la goma.
    const goma = (await a.cambiarEventos({ accion: 'BORRAR', celdas: [{ trabajadora_id: AINA, fecha: '2026-11-09', franja: 'MANANA' }] }, 'Marc')) as { cambio: { id: string } };
    const dg = await a.deshacerEventos(goma.cambio.id, 'Marc');
    assert.equal(describirCambio((dg as { cambio: Omit<CambioCalendario, 'trazas'> }).cambio), 'Deshecho «Borrado 9 nov 2026»: 1 día laborable × 1 persona · 1 franja');
    const vivos9 = [...bd.eventos.values()].filter((e) => e.fecha === '2026-11-09' && e.anulado === false);
    assert.equal(vivos9.length, 1);
    assert.notEqual(vivos9[0].id, e9.id); // fila nueva igual a la anulada
    assert.deepEqual([vivos9[0].tipo, vivos9[0].estado], ['JORNADA', 'PLANIFICADO']);
    // Ocupada entre medias: no se deshace nada.
    const goma2 = (await a.cambiarEventos({ accion: 'BORRAR', celdas: [{ trabajadora_id: AINA, fecha: '2026-11-09', franja: 'MANANA' }] }, 'Marc')) as { cambio: { id: string } };
    bd.eventos.set('ajena', { ...evento({ id: 'ajena', fecha: '2026-11-09', tipo: 'BAJA' }), anulado: false });
    assert.equal(await a.deshacerEventos(goma2.cambio.id, 'Marc'), 'ESTADO_CAMBIADO');
  });
  test('TA-REAL-2c: pintar → goma → deshacer → deshacer: queda vacío (antes: ESTADO_CAMBIADO por buscar el id original, ya anulado)', async () => {
    const bd = bdSimulada();
    const a = crearAdaptadorRrhhReal({ pool: bd.pool });
    const M = [{ trabajadora_id: AINA, fecha: '2027-10-04', franja: 'MANANA' as const }];
    const p = (await a.cambiarEventos({ accion: 'PINTAR', tipo: 'VACACIONES', celdas: M }, 'Marc')) as { cambio: { id: string } };
    const g = (await a.cambiarEventos({ accion: 'BORRAR', celdas: M }, 'Marc')) as { cambio: { id: string } };
    assert.equal(typeof await a.deshacerEventos(g.cambio.id, 'Marc'), 'object');
    const vivos = () => [...bd.eventos.values()].filter((e) => e.anulado === false && e.fecha === '2027-10-04');
    assert.equal(vivos().length, 1);
    const d = await a.deshacerEventos(p.cambio.id, 'Marc');
    assert.equal(typeof d, 'object', String(d));
    assert.equal(vivos().length, 0); // queda vacío
    assert.equal([...bd.eventos.values()].filter((e) => e.fecha === '2027-10-04').length, 2); // dos filas, las dos anuladas; nunca DELETE
    assert.equal(await a.deshacerEventos(p.cambio.id, 'Marc'), 'NADA_QUE_DESHACER');
  });
  test('TA-REAL-2c: 3 niveles (pintar → goma → pintar otro tipo → goma), deshechos en orden, vuelven al día vacío', async () => {
    const bd = bdSimulada();
    const a = crearAdaptadorRrhhReal({ pool: bd.pool });
    const id = async (b: PeticionEventos) => ((await a.cambiarEventos(b, 'Marc')) as { cambio: { id: string } }).cambio.id;
    const dias = [{ trabajadora_id: AINA, fecha: '2027-10-05' }, { trabajadora_id: AINA, fecha: '2027-10-06' }];
    const c1 = await id({ accion: 'PINTAR', tipo: 'VACACIONES', celdas: dias });
    const c2 = await id({ accion: 'BORRAR', celdas: [{ trabajadora_id: AINA, fecha: '2027-10-05', franja: 'TARDE' }] });
    const c3 = await id({ accion: 'PINTAR', tipo: 'BAJA', celdas: [{ trabajadora_id: AINA, fecha: '2027-10-06' }] });
    const c4 = await id({ accion: 'BORRAR', celdas: [{ trabajadora_id: AINA, fecha: '2027-10-06', franja: 'MANANA' }] });
    const vivos = (f: string) => [...bd.eventos.values()].filter((e) => e.anulado === false && e.fecha === f).map((e) => `${String(e.franja)}:${String(e.tipo)}`).sort();
    for (const c of [c4, c3, c2]) assert.equal(typeof await a.deshacerEventos(c, 'Marc'), 'object', c);
    assert.deepEqual([vivos('2027-10-05'), vivos('2027-10-06')], [['MANANA:VACACIONES', 'TARDE:VACACIONES'], ['MANANA:VACACIONES', 'TARDE:VACACIONES']]);
    assert.equal(typeof await a.deshacerEventos(c1, 'Marc'), 'object');
    assert.deepEqual([vivos('2027-10-05'), vivos('2027-10-06')], [[], []]);
  });
  test('TA-REAL-2c: ESTADO_CAMBIADO solo si el día cambió de verdad (otro tipo, confirmado o vacío, por otra sesión); si no, se deshace', async () => {
    const cambios: [string, ((e: Fila) => Fila) | null][] = [
      ['sin cambios', null],
      ['otro tipo', (e) => ({ ...e, tipo: 'BAJA' })],
      ['confirmado', (e) => ({ ...e, estado: 'CONFIRMADO' })],
      ['vacío', (e) => ({ ...e, anulado: true })],
    ];
    for (const [nombre, cambiar] of cambios) {
      const bd = bdSimulada();
      const a = crearAdaptadorRrhhReal({ pool: bd.pool });
      const M = [{ trabajadora_id: AINA, fecha: '2027-10-04', franja: 'MANANA' as const }];
      const p = (await a.cambiarEventos({ accion: 'PINTAR', tipo: 'VACACIONES', celdas: M }, 'Marc')) as { cambio: { id: string } };
      const g = (await a.cambiarEventos({ accion: 'BORRAR', celdas: M }, 'Marc')) as { cambio: { id: string } };
      await a.deshacerEventos(g.cambio.id, 'Marc');
      const fila = [...bd.eventos.values()].find((e) => e.anulado === false && e.fecha === '2027-10-04') as Fila;
      if (cambiar) bd.eventos.set(String(fila.id), cambiar(fila)); // cambio hecho fuera de esta sesión
      const d = await a.deshacerEventos(p.cambio.id, 'Marc');
      if (cambiar) assert.equal(d, 'ESTADO_CAMBIADO', nombre);
      else assert.equal(typeof d, 'object', nombre);
    }
  });
  test('deshacer de estado/tipo/nota (UPDATE al valor anterior); si alguien lo cambió entre medias, no se deshace nada', async () => {
    const e9 = evento({ fecha: '2026-11-09' });
    const bd = bdSimulada({ eventos: [e9] });
    const a = crearAdaptadorRrhhReal({ pool: bd.pool });
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
    assert.equal(cal.eventos[0].horas_efectivas, 3.5);
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

  test('estado: conectado, sin «datos de ejemplo»', async () => {
    const e = await app.inject({ method: 'GET', url: '/api/rrhh/estado', headers: H });
    assert.deepEqual(e.json(), { modo: 'REAL', conectado: true, datos_ejemplo: false, mensaje: TEXTO_BANNER_REAL, guardias_disponibles: false });
    assert.ok(!/ejemplo/i.test(TEXTO_BANNER_REAL));
  });
  test('errores de la BD con su mensaje llano: duplicado 409, tiempo agotado 504; TA-REAL-2: la goma ya funciona', async () => {
    const dup = await app.inject({ method: 'POST', url: '/api/rrhh/trabajadoras', headers: W,
      payload: { farmacia: 'PIO', nombre: 'Aina Bosch Ferrer', categoria: 'TECNICA', tipo_jornada: 'COMPLETA', horas_diarias: 8, fecha_alta: '2026-01-01' } });
    assert.deepEqual([dup.statusCode, dup.json()], [409, { error: 'DUPLICADO', mensaje: MENSAJES_BD.DUPLICADO.mensaje }]);
    const lento = await app.inject({ method: 'GET', url: '/api/rrhh/eventos/historial?farmacia=PIO', headers: H });
    assert.deepEqual([lento.statusCode, lento.json().error], [504, 'TIEMPO_AGOTADO']);
    const goma = await app.inject({ method: 'POST', url: '/api/rrhh/eventos', headers: W, payload: { accion: 'BORRAR', celdas: [{ trabajadora_id: AINA, fecha: '2026-11-09' }] } });
    assert.deepEqual([goma.statusCode, goma.json().cambio], [200, null]); // sin eventos ese día: nada que anular
  });
  test('TA-FICHA: el resumen de plantilla en REAL solo lee (READ ONLY + ROLLBACK, sin autor) y usa los mismos cálculos', async () => {
    const bdF = bdSimulada({ eventos: [evento({ fecha: '2026-11-16', tipo: 'VACACIONES' }), evento({ fecha: '2026-11-16', franja: 'TARDE', tipo: 'VACACIONES' })] });
    const appF = Fastify();
    registrarRrhh(appF, { modo: 'REAL', quien: 'Marc', adaptador: crearAdaptadorRrhhReal({ pool: bdF.pool }), sesionValida: () => true });
    await appF.ready();
    try {
      const r = await appF.inject({ method: 'GET', url: '/api/rrhh/fichas?farmacia=PIO&anio=2026&hoy=2026-11-13', headers: { host: '127.0.0.1:4747' } });
      assert.equal(r.statusCode, 200);
      const aina = r.json().filas.find((f: { trabajadora: { id: string } }) => f.trabajadora.id === AINA);
      // TA-REAL-2: sin convenio en la BD simulada (como hoy en REAL): vacaciones «pendiente» (null, nunca 30 inventados),
      // libre disposición y objetivo sin valor, aviso.
      assert.deepEqual([aina.vacaciones.planificadas, aina.vacaciones.derecho, aina.vacaciones.pendientes, aina.libre_disposicion.derecho, aina.horas.objetivo, aina.avisos[0].codigo],
        [1, null, null, null, null, 'SIN_CONVENIO']);
      assert.equal(r.json().reglas.vacaciones_dias, null);
      const s = sqls(bdF.log);
      assert.ok(s.every((q) => q === 'begin transaction read only' || q === 'rollback' || /^select /i.test(q)), JSON.stringify(s));
      assert.ok(!s.includes(SQL.autor) && !s.includes('begin') && !s.includes('commit'));
    } finally {
      await appF.close();
    }
  });
  test('la franja contraria a la media jornada se sigue rechazando', async () => {
    const r = await app.inject({ method: 'POST', url: '/api/rrhh/eventos', headers: W,
      payload: { accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ trabajadora_id: ELENA, fecha: '2026-12-07', franja: 'TARDE' }] } });
    assert.deepEqual([r.statusCode, r.json().error], [400, 'FRANJA_NO_VALIDA']);
  });
});
