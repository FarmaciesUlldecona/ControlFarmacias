// H6-REAL: adaptador REAL de pagos contra una base simulada con las reglas de la migración 35 (sin conexión real):
// copia de fecha e importe por trigger, autor obligatorio por transacción, único UPDATE = anular (SOLO_ANULAR), nunca
// DELETE, índices parciales (una vigente por (farmacia, factura_id, vencimiento_orden) y por (farmacia, cif)), origen
// DOMICILIADOS, farmacia de la factura, RLS e historial por trigger. Cada error de la BD → mensaje llano, ROLLBACK y sin
// reintento. A_REVISAR y huérfanas desde la BD. npm run test:unit
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { after, describe, test } from 'node:test';
import Fastify from 'fastify';
import { crearAdaptadorFixtures, DIR_DTO } from '../adaptador_fixtures.ts';
import type { VencimientosDTO } from '../contrato.ts';
import type { ClienteBd, Fila, PoolBd } from '../rrhh/adaptador_real.ts';
import { configuracionPagos, crearAlmacenPagosReal, fuenteDesdeFilas, historialPagos, type FilasPagos } from '../pagos/adaptador_real.ts';
import { CODIGOS_TRIGGER, MENSAJES_PAGOS, traducirErrorPagos, type CodigoErrorPagos } from '../pagos/errores_bd.ts';
import { MENSAJE_FALTA_CREDENCIAL_PAGOS, claveVencimiento, type FilaVencimientoPago } from '../pagos/pagos.ts';
import { registrarPagos } from '../pagos/rutas.ts';
import { SQL_PAGOS } from '../pagos/sql.ts';

const HOY = '2026-11-16';
const AHORA = '2026-11-16 10:00:00.000+00';
const V = (n: number) => `90000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const DTO = JSON.parse(readFileSync(join(DIR_DTO, 'vencimientos.json'), 'utf8')) as VencimientosDTO;
const venc = (n: number) => DTO.vencimientos.find((v) => v.vencimiento_id === V(n))!;
const id = (n: number) => ({ factura_id: venc(n).factura_id, orden: venc(n).orden as number });
const FACTURA_RITA = 'f0000000-0000-4000-8000-0000000000aa';
const errorPg = (code: string, message = 'x', extra: Record<string, unknown> = {}) => Object.assign(new Error(message), { code, ...extra });

interface Consulta { cliente: number; sql: string; params: unknown[] }

/**
 * Base simulada con las reglas de la migración 35. Responde SOLO a las sentencias de SQL_PAGOS (más begin/commit/
 * rollback): cualquier otra cosa falla (la web no puede leer facturas ni vencimientos con cf_pagos_web).
 */
function crearBd(o: { marcas?: Fila[]; formas?: Fila[]; sinAutor?: boolean; fallo?: (sql: string) => Error | undefined; falloConexion?: Error } = {}) {
  const log: Consulta[] = [];
  const marcas: Fila[] = (o.marcas ?? []).map((m) => ({ ...m }));
  const formas: Fila[] = (o.formas ?? []).map((f) => ({ ...f }));
  const historial: Fila[] = [];
  let hid = 0;
  const autorDe = new Map<number, string | null>();
  // now() de cada transacción: las filas de historial de una misma transacción comparten created_at.
  let tx = 0;
  const instanteDe = new Map<number, string>();
  // Vencimientos y facturas de la BD (los que el trigger consulta; la web no los lee con este rol).
  const vencimientos = new Map(DTO.vencimientos.map((v) => [claveVencimiento(v.factura_id, v.orden as number), v]));
  const facturas = new Map<string, string>([...DTO.vencimientos.map((v) => [v.factura_id, 'PIO'] as [string, string]), [FACTURA_RITA, 'RITA']]);
  vencimientos.set(claveVencimiento(FACTURA_RITA, 1), { ...venc(2), factura_id: FACTURA_RITA, orden: 1 });
  let conexiones = 0;
  let liberadas = 0;
  const hist = (cliente: number, tabla: string, op: string, antes: Fila | null, despues: Fila) => {
    historial.push({ id: String(++hid), tabla, registro_id: String(despues.id), farmacia: despues.farmacia, operacion: op, antes, despues, autor: autorDe.get(cliente), created_at: instanteDe.get(cliente) ?? AHORA });
  };
  const exigirAutor = (cliente: number) => { if (!autorDe.get(cliente)) throw errorPg('P0001', 'AUTOR_AUSENTE'); };

  function responder(cliente: number, sql: string, p: unknown[] = []): Fila[] {
    const err = o.fallo?.(sql);
    if (err) throw err;
    if (sql === 'begin' || sql === 'commit' || sql === 'rollback' || sql === 'begin transaction read only') {
      autorDe.set(cliente, null);
      if (sql === 'begin') instanteDe.set(cliente, `2026-11-16 10:${String(++tx).padStart(2, '0')}:00.000+00`);
      return [];
    }
    if (/\bdelete\b/i.test(sql)) throw errorPg('42501', 'permission denied for table');
    if (/facturas_vencimientos|public\.facturas\b/.test(sql)) throw errorPg('42501', 'permission denied for table facturas'); // cf_pagos_web no lee facturas
    if (sql === SQL_PAGOS.autor) { if (!o.sinAutor) autorDe.set(cliente, String(p[0])); return []; }
    // Único UPDATE permitido: anulada = true sobre una vigente.
    if (/^update /.test(sql) && !/ set anulada = true where /.test(sql)) throw errorPg('P0001', 'SOLO_ANULAR');
    if (sql === SQL_PAGOS.insertarMarcas) {
      exigirAutor(cliente);
      const [farmacia, fs, os, fps, formasP, origenes] = p as [string, string[], number[], string[], string[], string[]];
      const r: Fila[] = [];
      fs.forEach((factura_id, i) => {
        if (farmacia !== 'PIO') throw errorPg('P0001', `FARMACIA_NO_HABILITADA: ${farmacia}`);
        if (!facturas.has(factura_id)) throw errorPg('P0001', 'FACTURA_NO_ENCONTRADA');
        if (facturas.get(factura_id) !== farmacia) throw errorPg('P0001', 'FARMACIA_DISTINTA_DE_LA_FACTURA');
        const v = vencimientos.get(claveVencimiento(factura_id, os[i]));
        if (!v) throw errorPg('P0001', 'VENCIMIENTO_NO_ENCONTRADO');
        if (v.fecha_vencimiento === null) throw errorPg('P0001', 'VENCIMIENTO_SIN_FECHA');
        if (v.importe === null) throw errorPg('P0001', 'VENCIMIENTO_SIN_IMPORTE');
        if (fps[i] > HOY) throw errorPg('P0001', 'FECHA_PAGO_FUTURA');
        if (!['DOMICILIACION', 'TRANSFERENCIA', 'EFECTIVO', 'COMPENSACION_ABONO'].includes(formasP[i])) throw errorPg('23514', 'check', { constraint: 'vencimientos_marcas_pago_forma_check' });
        const fv = v.fecha_vencimiento.slice(0, 10);
        if (origenes[i] === 'DOMICILIADOS' && (formasP[i] !== 'DOMICILIACION' || fps[i] !== fv || !(fv < HOY))) throw errorPg('P0001', 'DOMICILIADO_NO_VALIDO');
        // Índice parcial (farmacia, factura_id, vencimiento_orden) where not anulada: ON CONFLICT … DO NOTHING.
        if (marcas.some((m) => !m.anulada && m.farmacia === farmacia && m.factura_id === factura_id && m.vencimiento_orden === os[i])) return;
        // Trigger: copia fecha e importe del vencimiento (la web no los envía).
        const m: Fila = { id: randomUUID(), farmacia, factura_id, vencimiento_orden: os[i], fecha_vencimiento: fv, importe: String(v.importe),
          fecha_pago: fps[i], forma: formasP[i], origen: origenes[i], anulada: false, created_at: AHORA, updated_at: AHORA };
        marcas.push(m);
        hist(cliente, 'vencimientos_marcas_pago', 'INSERT', null, m);
        r.push({ ...m });
      });
      return r;
    }
    if (sql === SQL_PAGOS.anularMarca) {
      exigirAutor(cliente);
      return marcas.filter((m) => String(m.id) === p[0] && m.farmacia === p[1] && !m.anulada).map((m) => {
        const antes = { ...m };
        Object.assign(m, { anulada: true, updated_at: AHORA });
        hist(cliente, 'vencimientos_marcas_pago', 'UPDATE', antes, { ...m });
        return { ...m };
      });
    }
    if (sql === SQL_PAGOS.marcaPorId) return marcas.filter((m) => String(m.id) === p[0] && m.farmacia === p[1]).map((m) => ({ id: m.id, anulada: m.anulada }));
    if (sql === SQL_PAGOS.formaBloqueo) return formas.filter((f) => f.farmacia === p[0] && f.cif === p[1] && !f.anulada).map((f) => ({ ...f }));
    if (sql === SQL_PAGOS.anularForma) {
      exigirAutor(cliente);
      return formas.filter((f) => String(f.id) === p[0] && !f.anulada).map((f) => {
        const antes = { ...f };
        Object.assign(f, { anulada: true, updated_at: AHORA });
        hist(cliente, 'proveedores_forma_pago', 'UPDATE', antes, { ...f });
        return { ...f };
      });
    }
    if (sql === SQL_PAGOS.insertarForma) {
      exigirAutor(cliente);
      const [farmacia, cif, forma] = p as string[];
      if (farmacia !== 'PIO') throw errorPg('42501', 'new row violates row-level security policy for table "proveedores_forma_pago"');
      if (!/^[A-Z0-9]{5,20}$/.test(cif)) throw errorPg('23514', 'check', { constraint: 'proveedores_forma_pago_cif_check' });
      if (formas.some((f) => !f.anulada && f.farmacia === farmacia && f.cif === cif)) return []; // ON CONFLICT … DO NOTHING
      const f: Fila = { id: randomUUID(), farmacia, cif, forma, anulada: false, created_at: AHORA, updated_at: AHORA };
      formas.push(f);
      hist(cliente, 'proveedores_forma_pago', 'INSERT', null, f);
      return [{ ...f }];
    }
    if (sql === SQL_PAGOS.prueba) return [{ formas: String(formas.length) }];
    throw errorPg('42601', `sentencia no prevista en la base simulada: ${sql.slice(0, 40)}`);
  }
  const pool: PoolBd = {
    connect: async (): Promise<ClienteBd> => {
      if (o.falloConexion) throw o.falloConexion;
      const n = ++conexiones;
      return { query: async (sql, params) => { log.push({ cliente: n, sql, params: params ?? [] }); return { rows: responder(n, sql, params) }; }, release: () => { liberadas++; } };
    },
    end: async () => {},
  };
  /** Lo que lee cf_lectura (READ ONLY): vigentes de PIO e historial de PIO. */
  const lector = async (): Promise<FilasPagos> => ({
    marcas: marcas.filter((m) => m.farmacia === 'PIO' && !m.anulada).map((m) => ({ ...m })),
    formas: formas.filter((f) => f.farmacia === 'PIO' && !f.anulada).map((f) => ({ ...f })),
    historial: historial.filter((h) => h.farmacia === 'PIO').map((h) => ({ ...h })),
  });
  return { pool, lector, log, marcas, formas, historial, cuenta: () => ({ conexiones, liberadas }) };
}
const sqls = (log: Consulta[]) => log.map((c) => c.sql);
const filaMarca = (n: number, o: Partial<Fila> = {}): Fila => ({
  id: randomUUID(), farmacia: 'PIO', factura_id: venc(n).factura_id, vencimiento_orden: venc(n).orden, fecha_vencimiento: venc(n).fecha_vencimiento,
  importe: String(venc(n).importe), fecha_pago: '2026-11-09', forma: 'TRANSFERENCIA', origen: 'MANUAL', anulada: false, created_at: AHORA, updated_at: AHORA, ...o,
});

describe('H6-REAL: errores de la BD → mensaje llano (nunca el texto técnico)', () => {
  test('cada código de trigger, 23505, 23514, 42501, RLS, tiempo, conexiones y red', () => {
    const casos: [unknown, CodigoErrorPagos][] = [
      ...CODIGOS_TRIGGER.map((k): [unknown, CodigoErrorPagos] => [errorPg('P0001', k), k]),
      [errorPg('P0001', 'VENCIMIENTO_SIN_IMPORTE: factura f0000000-… orden 3'), 'VENCIMIENTO_SIN_IMPORTE'],
      [errorPg('P0001', 'FARMACIA_NO_HABILITADA: RITA'), 'FARMACIA_NO_HABILITADA'],
      [errorPg('P0001', 'otro'), 'ERROR_BD'],
      [errorPg('23505', 'duplicate key value violates unique constraint "vencimientos_marcas_pago_vigente"'), 'DUPLICADO'],
      [errorPg('23514', 'new row for relation "proveedores_forma_pago" violates check constraint'), 'REGLA_TABLA'],
      [errorPg('42501', 'permission denied for table facturas'), 'PERMISO_DENEGADO'],
      [errorPg('42501', 'new row violates row-level security policy for table "vencimientos_marcas_pago"'), 'RLS_DENEGADO'],
      [errorPg('57014'), 'TIEMPO_AGOTADO'], [errorPg('53300'), 'SIN_CONEXIONES'], [errorPg('ECONNREFUSED'), 'SIN_CONEXION'],
      [new Error('cualquier cosa'), 'ERROR_BD'],
    ];
    for (const [e, codigo] of casos) {
      const r = traducirErrorPagos(e);
      assert.deepEqual([r.codigo, r.http, r.mensaje], [codigo, MENSAJES_PAGOS[codigo].http, MENSAJES_PAGOS[codigo].mensaje], codigo);
      assert.ok(!/constraint|relation|permission|select|insert|f0000000|P0001|23505/i.test(r.mensaje), `sin texto técnico: ${codigo}`);
    }
    assert.deepEqual(CODIGOS_TRIGGER.length, 10);
  });
});

describe('H6-REAL: configuración de la credencial de pagos (sin leer .env.web)', () => {
  const base = { CF_LECTURA_HOST: 'h', CF_LECTURA_PORT: '5432', CF_LECTURA_DB: 'd' };
  const ca = () => '-----BEGIN CERTIFICATE-----';
  test('sin credencial: «Falta configurar la credencial de pagos»; rol distinto: no conecta; correcta: pool de 2 con TLS', () => {
    assert.deepEqual(configuracionPagos(base, ca), { ok: false, codigo: 'CREDENCIAL_PAGOS_AUSENTE', mensaje: MENSAJE_FALTA_CREDENCIAL_PAGOS });
    assert.equal(MENSAJE_FALTA_CREDENCIAL_PAGOS, 'Falta configurar la credencial de pagos');
    const otro = configuracionPagos({ ...base, CF_PAGOS_USER: 'cf_lectura', CF_PAGOS_PASSWORD: 'x' }, ca);
    assert.deepEqual(otro.ok ? null : otro.codigo, 'USUARIO_NO_CF_PAGOS_WEB');
    const ok = configuracionPagos({ ...base, CF_PAGOS_USER: 'cf_pagos_web.abc', CF_PAGOS_PASSWORD: 'x' }, ca);
    assert.ok(ok.ok);
    assert.deepEqual(ok.ok && [ok.config.max, ok.config.user, (ok.config.ssl as { rejectUnauthorized: boolean }).rejectUnauthorized], [2, 'cf_pagos_web.abc', true]);
    const sinCa = configuracionPagos({ ...base, CF_PAGOS_USER: 'cf_pagos_web', CF_PAGOS_PASSWORD: 'x' }, () => { throw new Error('FALTA_CERTIFICADO_CA: x'); });
    assert.deepEqual(sinCa.ok ? null : sinCa.codigo, 'CERTIFICADO_CA');
  });
});

describe('H6-REAL: historial y fuente desde las filas', () => {
  test('alta, anulación, cambio de forma (un solo evento con la anterior) y vuelta a por defecto; autor de cada marca', () => {
    const m = filaMarca(7);
    const fA = { id: 'a', farmacia: 'PIO', cif: 'A00000001', forma: 'TRANSFERENCIA', anulada: false };
    const fB = { ...fA, id: 'b', forma: 'EFECTIVO' };
    const h: Fila[] = [
      { id: '1', tabla: 'vencimientos_marcas_pago', registro_id: m.id, farmacia: 'PIO', operacion: 'INSERT', antes: null, despues: m, autor: 'Marc', created_at: '2026-11-09 10:00:00+00' },
      { id: '2', tabla: 'public.vencimientos_marcas_pago', registro_id: m.id, farmacia: 'PIO', operacion: 'UPDATE', antes: m, despues: { ...m, anulada: true }, autor: 'Marc', created_at: '2026-11-10 10:00:00+00' },
      { id: '3', tabla: 'proveedores_forma_pago', registro_id: 'a', farmacia: 'PIO', operacion: 'INSERT', antes: null, despues: fA, autor: 'Marc', created_at: '2026-11-11 10:00:00+00' },
      { id: '4', tabla: 'proveedores_forma_pago', registro_id: 'a', farmacia: 'PIO', operacion: 'UPDATE', antes: fA, despues: { ...fA, anulada: true }, autor: 'Marc', created_at: '2026-11-12 10:00:00+00' },
      { id: '5', tabla: 'proveedores_forma_pago', registro_id: 'b', farmacia: 'PIO', operacion: 'INSERT', antes: null, despues: fB, autor: 'Marc', created_at: '2026-11-12 10:00:00+00' },
      { id: '6', tabla: 'proveedores_forma_pago', registro_id: 'b', farmacia: 'PIO', operacion: 'UPDATE', antes: fB, despues: JSON.stringify({ ...fB, anulada: true }), autor: 'Pío', created_at: '2026-11-13 10:00:00+00' },
    ];
    const { eventos, autorAlta } = historialPagos(h);
    assert.deepEqual(eventos.map((e) => [e.evento_id, e.accion, e.autor, e.forma, e.forma_anterior]), [
      [1, 'MARCA', 'Marc', 'TRANSFERENCIA', null], [2, 'ANULA_MARCA', 'Marc', 'TRANSFERENCIA', null],
      [3, 'FORMA', 'Marc', 'TRANSFERENCIA', null], [5, 'FORMA', 'Marc', 'EFECTIVO', 'TRANSFERENCIA'], [6, 'FORMA_POR_DEFECTO', 'Pío', null, 'EFECTIVO'],
    ]);
    assert.deepEqual([eventos[0].factura_id, eventos[0].vencimiento_orden], [venc(7).factura_id, 1]);
    assert.equal(autorAlta.get(String(m.id)), 'Marc');
  });
  test('falla cerrado: forma u origen no previstos, o dos vigentes del mismo vencimiento', () => {
    assert.throws(() => fuenteDesdeFilas(HOY, { marcas: [filaMarca(7, { forma: 'CHEQUE' })], formas: [], historial: [] }), /VALOR_NO_PREVISTO: forma/);
    assert.throws(() => fuenteDesdeFilas(HOY, { marcas: [filaMarca(7, { origen: 'BANCO' })], formas: [], historial: [] }), /VALOR_NO_PREVISTO: origen/);
    assert.throws(() => fuenteDesdeFilas(HOY, { marcas: [filaMarca(7), filaMarca(7)], formas: [], historial: [] }), /MARCAS_VIGENTES_DUPLICADAS/);
    const f = fuenteDesdeFilas(HOY, { marcas: [filaMarca(7)], formas: [{ id: 'x', farmacia: 'PIO', cif: 'B00000003', forma: 'EFECTIVO', anulada: false }], historial: [] });
    assert.deepEqual([f.marcas.get(claveVencimiento(venc(7).factura_id, 1))?.importe, f.formas.get('B00000003')], [288, 'EFECTIVO']);
  });
});

describe('H6-REAL: API con la base simulada (cf_lectura lee; cf_pagos_web escribe)', async () => {
  const H = { host: '127.0.0.1:4747' };
  const W = { ...H, origin: 'http://127.0.0.1:4747', 'content-type': 'application/json' };
  async function servidor(bd: ReturnType<typeof crearBd>, conCredencial = true) {
    const app = Fastify();
    registrarPagos(app, { modo: 'REAL', contrato: crearAdaptadorFixtures(), quien: 'Marc', sesionValida: () => true,
      almacen: crearAlmacenPagosReal({ lector: bd.lector, pool: conCredencial ? bd.pool : null, hoy: () => HOY }) });
    await app.ready();
    return {
      app,
      get: async () => (await app.inject({ method: 'GET', url: '/api/pagos/vencimientos', headers: H })).json(),
      post: (url: string, body: unknown) => app.inject({ method: 'POST', url, headers: W, payload: JSON.stringify(body) }),
      put: (url: string, body: unknown) => app.inject({ method: 'PUT', url, headers: W, payload: JSON.stringify(body) }),
    };
  }
  const apps: { close: () => Promise<unknown> }[] = [];
  after(async () => { for (const a of apps) await a.close(); });
  const fila = (d: { filas: FilaVencimientoPago[] }, n: number) => d.filas.find((f) => f.vencimiento_id === V(n)) as FilaVencimientoPago;

  test('lectura: marcas, A_REVISAR (importe o fecha distintos) y huérfana desde la BD; sin el 503 de antes', async () => {
    const bd = crearBd({ marcas: [
      filaMarca(7), // coincide
      filaMarca(2, { importe: '400.00' }), // el vencimiento vale 472,22: a revisar
      filaMarca(4, { vencimiento_orden: 9 }), // huérfana
      filaMarca(1, { anulada: true }),
    ] });
    const s = await servidor(bd);
    apps.push(s.app);
    const d = await s.get();
    assert.deepEqual([d.modo, d.hoy, d.marcas_disponibles, d.mensaje_escritura, d.a_revisar, d.marcas_huerfanas.length], ['REAL', HOY, true, null, 2, 1]);
    assert.equal(fila(d, 7).estado_pago, 'PAGADO_MANUAL');
    assert.deepEqual([fila(d, 2).estado_pago, fila(d, 2).marca?.diferencias], ['A_REVISAR', ['IMPORTE']]);
    assert.deepEqual([fila(d, 1).estado_pago, fila(d, 1).marca], ['DOMICILIADO_PREVISTO', null]); // la anulada no cuenta (sin formas en la BD: domiciliación)
    assert.ok(!JSON.stringify(d).includes('Pendiente de tablas'));
    assert.equal(bd.log.length, 0); // leer no usa la credencial de pagos
  });

  test('marcar: una transacción con autor; la web no envía fecha ni importe (los copia el trigger); conflicto = ROLLBACK de todas', async () => {
    const bd = crearBd({ marcas: [filaMarca(7)] });
    const s = await servidor(bd);
    apps.push(s.app);
    const r = await s.post('/api/pagos/marcas', { vencimientos: [id(2), id(10)], fecha_pago: '2026-11-12', forma: null });
    assert.equal(r.statusCode, 201);
    assert.deepEqual(r.json().marcas.map((m: { importe: number; fecha_vencimiento: string; creada_por: string }) => [m.importe, m.fecha_vencimiento, m.creada_por]),
      [[472.22, '2026-11-11', 'Marc'], [152.37, '2026-11-04', 'Marc']]);
    assert.deepEqual(sqls(bd.log), ['begin', SQL_PAGOS.autor, SQL_PAGOS.insertarMarcas, 'commit']);
    assert.deepEqual(bd.log[1].params, ['Marc']);
    assert.ok(!/\b(fecha_vencimiento|importe)\b/.test(SQL_PAGOS.insertarMarcas.split('returning')[0]));
    assert.ok(/on conflict \(farmacia, factura_id, vencimiento_orden\) where not anulada do nothing/.test(SQL_PAGOS.insertarMarcas));
    assert.equal(bd.historial.filter((h) => h.operacion === 'INSERT').every((h) => h.autor === 'Marc'), true);
    const d = await s.get();
    assert.equal(fila(d, 2).estado_pago, 'PAGADO_MANUAL');
    assert.equal(d.historial[0].autor, 'Marc');
    // Conflicto en BD (otro cambio entre la lectura y la escritura): ninguna, ROLLBACK.
    bd.log.length = 0;
    const almacen = crearAlmacenPagosReal({ lector: bd.lector, pool: bd.pool, hoy: () => HOY });
    const it = (n: number) => ({ factura_id: id(n).factura_id, vencimiento_orden: id(n).orden, fecha_pago: HOY, forma: 'TRANSFERENCIA' as const, origen: 'MANUAL' as const });
    await assert.rejects(almacen.marcar([it(1), it(2)], 'Marc', () => undefined), (e: { codigo: string }) => e.codigo === 'YA_PAGADO');
    assert.deepEqual(sqls(bd.log), ['begin', SQL_PAGOS.autor, SQL_PAGOS.insertarMarcas, 'rollback']);
  });

  test('confirmar domiciliados: origen DOMICILIADOS, forma domiciliación y fecha = vencimiento; la BD rechaza uno no válido', async () => {
    const bd = crearBd();
    const s = await servidor(bd);
    apps.push(s.app);
    const r = await s.post('/api/pagos/marcas/domiciliados', { vencimientos: [id(4), id(5)] });
    assert.equal(r.statusCode, 201);
    const ins = bd.log.find((c) => c.sql === SQL_PAGOS.insertarMarcas)!;
    assert.deepEqual(ins.params.slice(3), [['2026-10-30', '2026-11-15'], ['DOMICILIACION', 'DOMICILIACION'], ['DOMICILIADOS', 'DOMICILIADOS']]);
    // Directo a la BD con fecha distinta de la de vencimiento: DOMICILIADO_NO_VALIDO, mensaje llano.
    const almacen = crearAlmacenPagosReal({ lector: bd.lector, pool: bd.pool, hoy: () => HOY });
    await assert.rejects(almacen.marcar([{ factura_id: id(3).factura_id, vencimiento_orden: 1, fecha_pago: '2026-11-15', forma: 'DOMICILIACION', origen: 'DOMICILIADOS' }], 'Marc', () => undefined),
      (e: { codigo: string; mensaje: string }) => e.codigo === 'DOMICILIADO_NO_VALIDO' && e.mensaje === MENSAJES_PAGOS.DOMICILIADO_NO_VALIDO.mensaje);
  });

  test('anular: UPDATE anulada = true (nunca DELETE); ya anulada / no encontrada con mensaje llano', async () => {
    const m = filaMarca(7);
    const bd = crearBd({ marcas: [m] });
    const s = await servidor(bd);
    apps.push(s.app);
    assert.equal((await s.put(`/api/pagos/marcas/${m.id}/anular`, { confirmar: true })).statusCode, 200);
    assert.deepEqual(sqls(bd.log), ['begin', SQL_PAGOS.autor, SQL_PAGOS.anularMarca, 'commit']);
    assert.equal(bd.marcas.length, 1); // sigue ahí, anulada
    const otra = await s.put(`/api/pagos/marcas/${m.id}/anular`, { confirmar: true });
    assert.deepEqual([otra.statusCode, otra.json()], [409, { error: 'MARCA_YA_ANULADA', mensaje: MENSAJES_PAGOS.MARCA_YA_ANULADA.mensaje }]);
    const nada = await s.put(`/api/pagos/marcas/${randomUUID()}/anular`, { confirmar: true });
    assert.equal(nada.json().error, 'MARCA_NO_ENCONTRADA');
    assert.ok(!sqls(bd.log).some((q) => /delete/i.test(q)));
    const d = await s.get();
    assert.deepEqual(d.historial.map((e: { accion: string; autor: string }) => [e.accion, e.autor]), [['ANULA_MARCA', 'Marc']]); // la marca sembrada no tiene fila de alta
    assert.equal(fila(d, 7).estado_pago, 'DOMICILIADO_PREVISTO'); // vuelve a su estado (sin formas en la BD: domiciliación)
  });

  test('forma por CIF: cambiar = anular + insertar en la misma transacción (un evento FORMA); null = solo anular', async () => {
    const bd = crearBd({ formas: [{ id: randomUUID(), farmacia: 'PIO', cif: 'B00000003', forma: 'TRANSFERENCIA', anulada: false, created_at: AHORA, updated_at: AHORA }] });
    const s = await servidor(bd);
    apps.push(s.app);
    assert.equal((await s.put('/api/pagos/formas/B00000003', { forma: 'EFECTIVO' })).statusCode, 200);
    assert.deepEqual(sqls(bd.log), ['begin', SQL_PAGOS.autor, SQL_PAGOS.formaBloqueo, SQL_PAGOS.anularForma, SQL_PAGOS.insertarForma, 'commit']);
    assert.equal(new Set(bd.log.map((c) => c.cliente)).size, 1);
    let d = await s.get();
    assert.deepEqual([d.historial[0].accion, d.historial[0].forma, d.historial[0].forma_anterior], ['FORMA', 'EFECTIVO', 'TRANSFERENCIA']);
    assert.equal(d.proveedores.find((p: { cif: string }) => p.cif === 'B00000003').forma, 'EFECTIVO');
    assert.equal((await s.put('/api/pagos/formas/B00000003', { forma: 'EFECTIVO' })).json().error, 'SIN_CAMBIOS');
    assert.equal((await s.put('/api/pagos/formas/B00000003', { forma: null })).statusCode, 200);
    d = await s.get();
    assert.deepEqual([d.historial[0].accion, d.proveedores.find((p: { cif: string }) => p.cif === 'B00000003').por_defecto], ['FORMA_POR_DEFECTO', true]);
    assert.equal(bd.formas.length, 2); // nada se borra
  });

  test('reglas previas en la web: sin importe 409 sin tocar la BD; fecha futura 400; el trigger también lo impediría', async () => {
    const bd = crearBd();
    const s = await servidor(bd);
    apps.push(s.app);
    const r = await s.post('/api/pagos/marcas', { vencimientos: [id(8)], fecha_pago: HOY, forma: 'EFECTIVO' });
    assert.deepEqual([r.statusCode, r.json()], [409, { error: 'VENCIMIENTO_SIN_IMPORTE', mensaje: MENSAJES_PAGOS.VENCIMIENTO_SIN_IMPORTE.mensaje }]);
    assert.equal((await s.post('/api/pagos/marcas', { vencimientos: [id(2)], fecha_pago: '2026-11-17', forma: null })).statusCode, 400);
    assert.equal(bd.log.length, 0);
    const almacen = crearAlmacenPagosReal({ lector: bd.lector, pool: bd.pool, hoy: () => HOY });
    const it = (n: number, o: Partial<{ fecha_pago: string; factura_id: string; vencimiento_orden: number }> = {}) =>
      ({ factura_id: id(n).factura_id, vencimiento_orden: id(n).orden, fecha_pago: HOY, forma: 'EFECTIVO' as const, origen: 'MANUAL' as const, ...o });
    for (const [item, codigo] of [
      [it(8), 'VENCIMIENTO_SIN_IMPORTE'], [it(2, { fecha_pago: '2026-11-17' }), 'FECHA_PAGO_FUTURA'],
      [it(2, { vencimiento_orden: 9 }), 'VENCIMIENTO_NO_ENCONTRADO'], [it(2, { factura_id: randomUUID() }), 'FACTURA_NO_ENCONTRADA'],
      [it(2, { factura_id: FACTURA_RITA, vencimiento_orden: 1 }), 'FARMACIA_DISTINTA_DE_LA_FACTURA'],
    ] as const) {
      bd.log.length = 0;
      await assert.rejects(almacen.marcar([item], 'Marc', () => undefined), (e: { codigo: string }) => e.codigo === codigo, codigo);
      assert.equal(sqls(bd.log).at(-1), 'rollback', codigo);
      assert.equal(sqls(bd.log).filter((q) => q === SQL_PAGOS.insertarMarcas).length, 1, `${codigo}: sin reintento`);
    }
    assert.equal(bd.marcas.length, 0);
  });

  test('cada error de la BD → mensaje llano, ROLLBACK y sin reintento (AUTOR_AUSENTE, SOLO_ANULAR, 23505, 23514, 42501, RLS, FARMACIA_NO_HABILITADA)', async () => {
    const casos: [Error, CodigoErrorPagos][] = [
      [errorPg('P0001', 'SOLO_ANULAR'), 'SOLO_ANULAR'],
      [errorPg('P0001', 'FARMACIA_NO_HABILITADA'), 'FARMACIA_NO_HABILITADA'],
      [errorPg('23505', 'duplicate key value violates unique constraint "vencimientos_marcas_pago_vigente"'), 'DUPLICADO'],
      [errorPg('23514', 'violates check constraint "vencimientos_marcas_pago_forma_check"'), 'REGLA_TABLA'],
      [errorPg('42501', 'permission denied for table vencimientos_marcas_pago'), 'PERMISO_DENEGADO'],
      [errorPg('42501', 'new row violates row-level security policy'), 'RLS_DENEGADO'],
    ];
    for (const [err, codigo] of casos) {
      const bd = crearBd({ fallo: (sql) => (sql === SQL_PAGOS.insertarMarcas ? err : undefined) });
      const s = await servidor(bd);
      apps.push(s.app);
      const r = await s.post('/api/pagos/marcas', { vencimientos: [id(2)], fecha_pago: HOY, forma: null });
      assert.deepEqual([r.statusCode, r.json()], [MENSAJES_PAGOS[codigo].http, { error: codigo, mensaje: MENSAJES_PAGOS[codigo].mensaje }], codigo);
      assert.deepEqual(sqls(bd.log), ['begin', SQL_PAGOS.autor, SQL_PAGOS.insertarMarcas, 'rollback'], codigo);
      assert.deepEqual(bd.cuenta(), { conexiones: 1, liberadas: 1 });
    }
    // AUTOR_AUSENTE: la BD no recibe el autor (simulado) y rechaza la escritura.
    const sin = crearBd({ sinAutor: true });
    const s = await servidor(sin);
    apps.push(s.app);
    const r = await s.post('/api/pagos/marcas', { vencimientos: [id(2)], fecha_pago: HOY, forma: null });
    assert.deepEqual([r.statusCode, r.json().error], [500, 'AUTOR_AUSENTE']);
    assert.equal(sqls(sin.log).at(-1), 'rollback');
    // SOLO_ANULAR desde la propia base simulada: cualquier UPDATE que no sea anular.
    const c = await crearBd().pool.connect();
    await assert.rejects(c.query('update public.vencimientos_marcas_pago set forma = $1 where id::text = $2', ['EFECTIVO', 'x']), (e: { message: string }) => traducirErrorPagos(e).codigo === 'SOLO_ANULAR');
    // Sin conexión: mensaje llano.
    const caida = crearBd({ falloConexion: errorPg('ECONNREFUSED', 'connect ECONNREFUSED 10.0.0.1:5432') });
    const sc = await servidor(caida);
    apps.push(sc.app);
    const rc = await sc.post('/api/pagos/marcas', { vencimientos: [id(2)], fecha_pago: HOY, forma: null });
    assert.deepEqual([rc.statusCode, rc.json().error], [503, 'SIN_CONEXION']);
    assert.ok(!rc.body.includes('10.0.0.1'));
  });

  test('sin credencial de pagos: la pantalla se lee (con sus marcas) en solo lectura; toda escritura 503 con el aviso', async () => {
    const bd = crearBd({ marcas: [filaMarca(7)] });
    const s = await servidor(bd, false);
    apps.push(s.app);
    const d = await s.get();
    assert.deepEqual([d.marcas_disponibles, d.mensaje_escritura, fila(d, 7).estado_pago], [false, MENSAJE_FALTA_CREDENCIAL_PAGOS, 'PAGADO_MANUAL']);
    for (const [method, url, body] of [
      ['POST', '/api/pagos/marcas', { vencimientos: [id(2)], fecha_pago: HOY, forma: null }],
      ['POST', '/api/pagos/marcas/domiciliados', { vencimientos: [id(4)] }],
      ['PUT', `/api/pagos/marcas/${String(bd.marcas[0].id)}/anular`, { confirmar: true }],
      ['PUT', '/api/pagos/formas/B00000003', { forma: 'TRANSFERENCIA' }],
    ] as const) {
      const r = await s.app.inject({ method, url, headers: W, payload: JSON.stringify(body) });
      assert.deepEqual([r.statusCode, r.json()], [503, { error: 'CREDENCIAL_PAGOS_AUSENTE', mensaje: MENSAJES_PAGOS.CREDENCIAL_PAGOS_AUSENTE.mensaje }], `${method} ${url}`);
    }
    assert.equal(bd.log.length, 0);
  });

  test('REAL sin almacén no arranca (falla cerrado)', () => {
    assert.throws(() => registrarPagos(Fastify(), { modo: 'REAL', contrato: crearAdaptadorFixtures(), quien: 'Marc', sesionValida: () => true }), /PAGOS_REAL_SIN_ALMACEN/);
  });
});
