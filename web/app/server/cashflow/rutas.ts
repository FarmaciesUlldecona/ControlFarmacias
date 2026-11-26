/**
 * H7: GET /api/cashflow. H7-AP1: más los apuntes manuales de la migración 40 (lectura y escritura).
 *
 * FIXTURES: datos ficticios con la forma del contrato (web/fixtures/cashflow/cashflow.json, generado por
 *   fixtures/scripts/gen_cashflow.mjs) y los vencimientos de PIO de la pantalla Vencimientos (contrato H6, con sus marcas).
 *   Apuntes: almacén en memoria con la semilla web/fixtures/cashflow/apuntes.json.
 * REAL (H7-REAL): tablas cf_cashflow_* de la migración 38 con cf_lectura (server/cashflow/lectura_real.ts, una foto READ
 *   ONLY): importación vigente y sus filas; fecha de referencia = hoy en Europe/Madrid. Sin vigente, la pantalla muestra
 *   «Todavía no hay datos importados». H7-AP1: en la misma foto, conceptos nuevos, recurrentes, apuntes y ocurrencias
 *   (cf_cashflow_ocurrencias); escritura con cf_cashflow_web (server/cashflow/adaptador_real.ts). Sin su credencial,
 *   la lectura sigue y la escritura responde 503 «Falta configurar la credencial de Cashflow».
 *
 * H7-AP1, escritura (sesión, Origin del mismo sitio obligatorio, Sec-Fetch-Site same-origin si viene y JSON; nunca
 * DELETE ni PATCH):
 *   POST /api/cashflow/apuntes                          alta de un apunte suelto o un recurrente (con concepto nuevo)
 *   POST /api/cashflow/apuntes/editar                   { anterior: {tabla, id}, motivo, alta }: anular + crear
 *   PUT  /api/cashflow/apuntes/:id/anular               { motivo }
 *   PUT  /api/cashflow/recurrentes/:id/anular           { motivo } (anula todas sus ocurrencias)
 *   POST /api/cashflow/recurrentes/:id/anular-ocurrencia { fecha_ocurrencia, motivo }
 *   POST /api/cashflow/sustituciones                    { apunte_id | recurrente_id + fecha_ocurrencia, factura_id, vencimiento_orden }
 * Antes de escribir, las reglas de la web (apuntes.ts) sobre lo recién leído, con los códigos de la BD; la BD las vuelve
 * a comprobar. La sustitución solo se guarda si la factura sigue siendo candidata (±5 %); nunca es automática.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import { PAGO_SIN_DATOS } from '../contrato.ts';
import { esPagado, hoyMadrid, type FilaVencimientoPago, type PantallaVencimientosDTO } from '../pagos/pagos.ts';
import { origenEscrituraValido } from '../rrhh/rutas.ts';
import { CONFIG_CASHFLOW, type CashflowDTO, type DatosCashflow, type VencimientoCashflow } from './cashflow.ts';
import {
  candidatoDe, candidatosSustitucion, comprobarAlta, comprobarAnular, comprobarAnularOcurrencia, esUuid, motivoSustitucion, validarAlta,
  validarMotivo, validarSustitucion, type ContextoCashflow, type PrevisionesCashflow, type TablaAnulable,
} from './apuntes.ts';
import { almacenSinEscritura, crearAlmacenCashflowFixtures, type AlmacenCashflowAsync, type SemillaApuntes } from './almacen.ts';
import { errorCashflow, traducirErrorCashflow, type CodigoErrorCashflow } from './errores_bd.ts';

export const RUTA_SEMILLA_CASHFLOW = join(import.meta.dirname, '..', '..', '..', 'fixtures', 'cashflow', 'cashflow.json');
export const RUTA_SEMILLA_APUNTES = join(import.meta.dirname, '..', '..', '..', 'fixtures', 'cashflow', 'apuntes.json');
export const PREFIJO_CASHFLOW = '/api/cashflow/';

export function leerSemillaCashflow(): DatosCashflow & { hoy: string } {
  const { hoy, importaciones, cuentas, importes, saldos, otras_cuentas } = JSON.parse(readFileSync(RUTA_SEMILLA_CASHFLOW, 'utf8')) as DatosCashflow & { hoy: string };
  return { hoy, importaciones, cuentas, importes, saldos, otras_cuentas };
}
export function leerSemillaApuntes(): SemillaApuntes {
  const { hoy, conceptos, recurrentes, apuntes } = JSON.parse(readFileSync(RUTA_SEMILLA_APUNTES, 'utf8')) as SemillaApuntes;
  return { hoy, conceptos, recurrentes, apuntes };
}

/** Vencimiento de la pantalla H6 → lo que usa el cashflow. */
export function vencimientoCashflow(f: FilaVencimientoPago): VencimientoCashflow {
  return {
    vencimiento_id: f.vencimiento_id, factura_id: f.factura_id, numero_factura: f.numero_factura,
    // H7-AP1: orden y CIF, para sugerir la sustitución de un apunte por su factura.
    vencimiento_orden: f.orden, proveedor_cif: f.proveedor_cif_comparable,
    proveedor_comercial: f.proveedor_comercial,
    proveedor_nombre: f.proveedor_comercial ?? f.proveedor_razon_social ?? f.proveedor ?? 'Proveedor sin identificar',
    fecha_vencimiento: f.fecha_vencimiento, importe: f.importe, sentido: f.sentido, estado_pago: f.estado_pago,
    // H6-REAL: una marca «a revisar» (ya no coincide con el vencimiento) no cuenta como pagada.
    fecha_pago: f.marca !== null && esPagado(f.estado_pago) ? f.marca.fecha_pago : null, cargo_negativo: f.cargo_negativo,
  };
}

/** Rutas de escritura de H7-AP1 (método + patrón). */
const ID = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
const PUT_CASHFLOW = [new RegExp(`^/api/cashflow/apuntes/${ID}/anular$`, 'i'), new RegExp(`^/api/cashflow/recurrentes/${ID}/anular$`, 'i')];
const POST_CASHFLOW = [/^\/api\/cashflow\/apuntes$/, /^\/api\/cashflow\/apuntes\/editar$/, /^\/api\/cashflow\/sustituciones$/,
  new RegExp(`^/api/cashflow/recurrentes/${ID}/anular-ocurrencia$`, 'i')];
export function esEscrituraCashflow(metodo: string, ruta: string): boolean {
  if (metodo === 'POST') return POST_CASHFLOW.some((r) => r.test(ruta));
  if (metodo === 'PUT') return PUT_CASHFLOW.some((r) => r.test(ruta));
  return false;
}

export interface OpcionesCashflow {
  modo: 'FIXTURES' | 'REAL';
  /** Pantalla Vencimientos (H6): vencimientos de PIO con estado y marca. */
  pantallaPagos: () => Promise<PantallaVencimientosDTO>;
  /** FIXTURES: por defecto, la semilla. */
  semilla?: DatosCashflow & { hoy: string };
  /** REAL: lectura de las tablas cf_cashflow_* (obligatoria en REAL), con las previsiones de la migración 40. */
  leerReal?: () => Promise<DatosCashflow & { previsiones?: PrevisionesCashflow }>;
  /** REAL: fecha de referencia (por defecto, hoy en Europe/Madrid). */
  hoy?: () => string;
  /** H7-AP1: sesión (sin ella, las rutas /api/cashflow/… responden 401). */
  sesionValida?: (req: FastifyRequest) => boolean;
  /** H7-AP1: autor de los apuntes (cf.autor de cada transacción). */
  quien?: string;
  /** H7-AP1: FIXTURES: por defecto, en memoria con la semilla. REAL: sin él, solo lectura (sin credencial). */
  almacen?: AlmacenCashflowAsync;
  /** FIXTURES: semilla de los apuntes (por defecto, web/fixtures/cashflow/apuntes.json). */
  semillaApuntes?: SemillaApuntes;
}

export function registrarCashflow(app: FastifyInstance, opciones: OpcionesCashflow): void {
  const semilla = opciones.modo === 'FIXTURES' ? opciones.semilla ?? leerSemillaCashflow() : null;
  if (opciones.modo === 'REAL' && !opciones.leerReal) throw new Error('CASHFLOW_REAL_SIN_LECTURA');
  const hoy = opciones.hoy ?? (() => hoyMadrid());
  const sesionValida = opciones.sesionValida ?? (() => false);
  const quien = opciones.quien ?? 'Marc';
  const almacen: AlmacenCashflowAsync = opciones.almacen
    ?? (semilla !== null ? crearAlmacenCashflowFixtures(opciones.semillaApuntes ?? leerSemillaApuntes(), () => semilla) : almacenSinEscritura());

  /** Lo importado y las previsiones (FIXTURES: semilla + memoria; REAL: una sola foto con cf_lectura). */
  const leer = async (): Promise<DatosCashflow & { hoy: string; previsiones: PrevisionesCashflow }> => {
    if (semilla !== null) {
      if (!almacen.previsiones) throw new Error('CASHFLOW_FIXTURES_SIN_PREVISIONES');
      return { ...semilla, previsiones: await almacen.previsiones(semilla.hoy) };
    }
    const d = await (opciones.leerReal as NonNullable<OpcionesCashflow['leerReal']>)();
    // Falla cerrado: REAL siempre lee las previsiones en la misma foto que lo importado.
    if (!d.previsiones) throw new Error('CASHFLOW_REAL_SIN_PREVISIONES');
    return { ...d, previsiones: d.previsiones, hoy: hoy() };
  };
  const contexto = async (): Promise<ContextoCashflow & { hoy: string }> => {
    const d = await leer();
    return { datos: d, previsiones: d.previsiones, hoy: d.hoy };
  };

  app.get('/api/cashflow', async (_req, reply): Promise<CashflowDTO> => {
    reply.header('cache-control', 'no-store');
    const datos = await leer();
    const p = await opciones.pantallaPagos();
    return {
      farmacia: p.farmacia, generado_at: p.generado_at, hoy: datos.hoy, modo: opciones.modo, config: CONFIG_CASHFLOW,
      importaciones: datos.importaciones, cuentas: datos.cuentas, importes: datos.importes, saldos: datos.saldos,
      otras_cuentas: datos.otras_cuentas,
      // Solo PIO (la pantalla H6 es de PIO). RITA: solo datos bancarios.
      vencimientos: p.filas.map(vencimientoCashflow),
      pago: PAGO_SIN_DATOS,
      previsiones: datos.previsiones,
      escritura_cashflow: { habilitada: almacen.sinEscritura === null, codigo: almacen.sinEscritura?.codigo ?? null, mensaje: almacen.sinEscritura?.mensaje ?? null, autor: quien },
    };
  });

  // --- H7-AP1: escritura ----------------------------------------------------------------------------------------------
  app.addHook('onRequest', async (req, reply) => {
    const ruta = req.url.split('?')[0];
    if (!ruta.startsWith(PREFIJO_CASHFLOW)) return;
    if (!sesionValida(req)) return reply.code(401).header('cache-control', 'no-store').send({ error: 'NO_AUTENTICADO' });
    reply.header('cache-control', 'no-store');
    if (!esEscrituraCashflow(req.method, ruta)) return reply.code(405).send({ error: 'SOLO_LECTURA' });
    if (!origenEscrituraValido(req)) return reply.code(403).send({ error: 'ORIGEN_NO_PERMITIDO' });
    if (!/^application\/json\b/i.test(req.headers['content-type'] ?? '')) return reply.code(415).send({ error: 'SOLO_JSON' });
  });

  /** Error de la web o de la BD → { error, mensaje, campo } llano (nunca el texto técnico). */
  const fallo = (reply: FastifyReply, e: unknown, campo: string | null = null) => {
    const t = traducirErrorCashflow(e);
    if (t.codigo === 'ERROR_BD') app.log.error({ msg: `cashflow: ${(e instanceof Error ? e.message : String(e)).split('\n')[0].slice(0, 200)}` });
    return reply.code(t.http).send({ error: t.codigo, mensaje: t.mensaje, campo });
  };
  const regla = (reply: FastifyReply, codigo: CodigoErrorCashflow, campo: string | null) => fallo(reply, errorCashflow(codigo), campo);
  const noValida = (reply: FastifyReply, errores: Record<string, string>) => reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores });
  /** Sin credencial de Cashflow: 503 antes de leer nada. */
  const escritura = async (reply: FastifyReply, trabajo: () => Promise<unknown>) => {
    if (almacen.sinEscritura) return regla(reply, almacen.sinEscritura.codigo, null);
    try { return await trabajo(); } catch (e) { return fallo(reply, e); }
  };
  const motivo = (reply: FastifyReply, body: unknown) => {
    const m = validarMotivo(body);
    if (!m.ok) { regla(reply, m.codigo, 'motivo'); return null; }
    return m.motivo;
  };

  app.post('/api/cashflow/apuntes', (req, reply) => escritura(reply, async () => {
    const v = validarAlta(req.body);
    if (!v.ok) return noValida(reply, v.errores);
    const f = comprobarAlta(v.datos, await contexto());
    if (f) return regla(reply, f.codigo, f.campo);
    return reply.code(201).send(await almacen.alta(v.datos, quien));
  }));

  app.post('/api/cashflow/apuntes/editar', (req, reply) => escritura(reply, async () => {
    const b = (req.body && typeof req.body === 'object' ? req.body : {}) as { anterior?: { tabla?: unknown; id?: unknown }; alta?: unknown };
    const tabla = b.anterior?.tabla === 'APUNTE' || b.anterior?.tabla === 'RECURRENTE' ? b.anterior.tabla as TablaAnulable : null;
    if (tabla === null || !esUuid(b.anterior?.id)) return noValida(reply, { anterior: 'Apunte que se edita no válido' });
    const m = motivo(reply, req.body);
    if (m === null) return reply;
    const v = validarAlta(b.alta);
    if (!v.ok) return noValida(reply, v.errores);
    const ctx = await contexto();
    const id = (b.anterior?.id as string).toLowerCase();
    const fa = comprobarAnular(tabla, id, ctx.previsiones);
    if (fa) return regla(reply, fa.codigo, null);
    // El alta se comprueba como si lo anterior ya estuviera anulado (misma transacción).
    const sin = { ...ctx, previsiones: { ...ctx.previsiones, apuntes: ctx.previsiones.apuntes.filter((x) => x.id !== id), recurrentes: ctx.previsiones.recurrentes.filter((x) => x.id !== id) } };
    const f = comprobarAlta(v.datos, sin);
    if (f) return regla(reply, f.codigo, f.campo);
    return reply.code(201).send(await almacen.editar({ tabla, id }, m, v.datos, quien));
  }));

  const anular = (tabla: TablaAnulable) => (req: FastifyRequest<{ Params: { id: string } }>, reply: FastifyReply) => escritura(reply, async () => {
    const m = motivo(reply, req.body);
    if (m === null) return reply;
    const id = req.params.id.toLowerCase();
    const f = comprobarAnular(tabla, id, (await contexto()).previsiones);
    if (f) return regla(reply, f.codigo, null);
    return { anulado: await almacen.anular(tabla, id, m, quien) };
  });
  app.put<{ Params: { id: string } }>('/api/cashflow/apuntes/:id/anular', anular('APUNTE'));
  app.put<{ Params: { id: string } }>('/api/cashflow/recurrentes/:id/anular', anular('RECURRENTE'));

  app.post<{ Params: { id: string } }>('/api/cashflow/recurrentes/:id/anular-ocurrencia', (req, reply) => escritura(reply, async () => {
    const m = motivo(reply, req.body);
    if (m === null) return reply;
    const fecha = (req.body as { fecha_ocurrencia?: unknown } | null)?.fecha_ocurrencia;
    if (typeof fecha !== 'string') return noValida(reply, { fecha_ocurrencia: 'Fecha de la ocurrencia no válida' });
    const id = req.params.id.toLowerCase();
    const f = comprobarAnularOcurrencia(id, fecha, await contexto());
    if (f) return regla(reply, f.codigo, f.campo);
    return reply.code(201).send({ apunte: await almacen.anularOcurrencia(id, fecha, m, quien, null) });
  }));

  app.post('/api/cashflow/sustituciones', (req, reply) => escritura(reply, async () => {
    const v = validarSustitucion(req.body);
    if (!v.ok) return noValida(reply, v.errores);
    const ctx = await contexto();
    const s = v.datos;
    if (ctx.previsiones.apuntes.some((a) => a.sustituido_factura_id === s.factura_id && a.sustituido_vencimiento_orden === s.vencimiento_orden)) {
      return regla(reply, 'VENCIMIENTO_YA_SUSTITUYE', null);
    }
    // La web elige el candidato (mismo concepto, misma decena o la siguiente, ±5 %): se vuelve a comprobar ahora.
    const vencimientos = (await opciones.pantallaPagos()).filas.map(vencimientoCashflow);
    const c = candidatoDe(candidatosSustitucion(ctx, vencimientos), s);
    if (c === null) return regla(reply, 'SUSTITUCION_NO_CANDIDATA', null);
    const sustitucion = { factura_id: c.vencimiento.factura_id, vencimiento_orden: c.vencimiento.vencimiento_orden };
    const apunte = c.tipo === 'SUELTO'
      ? await almacen.sustituirApunte(c.apunte_id as string, motivoSustitucion(c), sustitucion, quien)
      : await almacen.anularOcurrencia(c.recurrente_id as string, c.fecha, motivoSustitucion(c), quien, sustitucion);
    return reply.code(201).send({ apunte });
  }));
}
