/**
 * TA1/TA2/TA-REAL: API /api/rrhh/*. GET y, solo aquí, POST/PUT (fichas: alta, edición, baja y anulación; convenio;
 * eventos del calendario y deshacer). Toda ruta exige sesión; la escritura exige además Origin del mismo sitio
 * (obligatorio), Sec-Fetch-Site same-origin si viene y Content-Type application/json.
 *
 * Modo FIXTURES: adaptador RRHH_FIXTURES en memoria (datos de ejemplo).
 * Modo REAL (TA-REAL): adaptador RRHH_REAL (tablas reales, rol cf_trabajadores_web). Si falta la credencial en
 * .env.web, todas las rutas responden 503 «Falta configurar la credencial de Trabajadores» sin ningún dato (nunca datos
 * de ejemplo como reales); solo /api/rrhh/estado responde 200 con el aviso, para que la pantalla lo muestre.
 * Errores de la base de datos: código, HTTP y mensaje llano (errores_bd.ts); nunca filas, SQL ni datos de conexión.
 *
 * Se registra sobre cualquier instancia de Fastify (pruebas con instancia propia, sin BD).
 */
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import {
  ERROR_FALTA_CREDENCIAL, MENSAJE_FALTA_CREDENCIAL, TEXTO_BANNER_REAL, filtroFarmacia, validarAnulacion, validarCrearConvenio,
  validarFechaBaja, validarTrabajadora, type EstadoRrhhDTO,
} from './contrato.ts';
import { crearAdaptadorRrhhFixtures, type AdaptadorRrhh } from './adaptador_fixtures.ts';
import {
  AVISO_ANULAR_PENDIENTE, FECHA_MAX, FECHA_MIN, MAX_DIAS_LECTURA, diasEntre, enAniosConvenio, esFecha, validarDeshacer, validarPeticionEventos,
} from './eventos.ts';
import { ErrorRrhhBd, MENSAJES_BD } from './errores_bd.ts';

/** Código HTTP de cada error del módulo (y mensaje llano de los que lo necesitan). */
const HTTP_ERROR: Readonly<Record<string, number>> = {
  TRABAJADORA_NO_VALIDA: 400, FRANJA_NO_VALIDA: 400, EVENTO_NO_ENCONTRADO: 404, EVENTO_CONFIRMADO: 409, EVENTO_FUERA_DEL_ALTA: 409,
  ANULAR_EVENTOS_PENDIENTE: 409, NADA_QUE_DESHACER: 409, NO_ES_EL_ULTIMO: 409, ESTADO_CAMBIADO: 409,
  YA_DE_BAJA: 409, YA_ANULADA: 409, BAJA_ANTES_DEL_ALTA: 400, NOMBRE_DUPLICADO: 409,
};
const MENSAJE_ERROR: Readonly<Record<string, string>> = {
  ANULAR_EVENTOS_PENDIENTE: AVISO_ANULAR_PENDIENTE,
  EVENTO_FUERA_DEL_ALTA: MENSAJES_BD.EVENTO_FUERA_DEL_ALTA.mensaje,
  BAJA_ANTES_DEL_ALTA: 'La fecha de baja no puede ser anterior a la de alta.',
  NOMBRE_DUPLICADO: 'Ya hay otra ficha con ese nombre en esa farmacia.',
};

export const PREFIJO_RRHH = '/api/rrhh/';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Rutas de escritura del módulo (método + patrón): las únicas que el servidor admite fuera de login/logout.
 * TA1: fichas (POST alta; PUT edición y baja; TA-REAL: PUT anulación). TA-REAL: POST /api/rrhh/convenio (crear los
 * años firmados que falten). TA2: POST /api/rrhh/eventos y POST /api/rrhh/eventos/deshacer. Nunca DELETE ni PATCH.
 */
export function esEscrituraRrhh(metodo: string, ruta: string): boolean {
  if (metodo === 'POST') return ruta === '/api/rrhh/trabajadoras' || ruta === '/api/rrhh/convenio' || ruta === '/api/rrhh/eventos' || ruta === '/api/rrhh/eventos/deshacer';
  if (metodo === 'PUT') return /^\/api\/rrhh\/trabajadoras\/[0-9a-fA-F-]{36}(\/baja|\/anular)?$/.test(ruta);
  return false;
}

export interface OpcionesRrhh {
  modo: 'FIXTURES' | 'REAL';
  /** Sesión válida (cookie). */
  sesionValida: (req: FastifyRequest) => boolean;
  /** Quién figura en el historial (en REAL, cf.autor de cada transacción). */
  quien: string;
  /** FIXTURES: por defecto, uno nuevo con la semilla de ejemplo. REAL: el adaptador RRHH_REAL (sin él, falta la credencial). */
  adaptador?: AdaptadorRrhh;
  /** REAL sin adaptador: por qué no conecta (por defecto, falta la credencial). */
  sinConexion?: { codigo: string; mensaje: string };
}

/** Origen de la escritura: Origin obligatorio e igual al host; Sec-Fetch-Site same-origin si viene. */
export function origenEscrituraValido(req: Pick<FastifyRequest, 'headers'>): boolean {
  const origen = req.headers.origin;
  if (origen === undefined || origen !== `http://${req.headers.host}`) return false;
  const sitio = req.headers['sec-fetch-site'];
  return sitio === undefined || sitio === 'same-origin';
}

export function registrarRrhh(app: FastifyInstance, opciones: OpcionesRrhh): void {
  const { modo, sesionValida, quien } = opciones;
  const datos: AdaptadorRrhh | null = modo === 'FIXTURES' ? opciones.adaptador ?? crearAdaptadorRrhhFixtures() : opciones.adaptador ?? null;
  const sin = opciones.sinConexion ?? { codigo: ERROR_FALTA_CREDENCIAL, mensaje: MENSAJE_FALTA_CREDENCIAL };

  const pendiente = (reply: FastifyReply) => reply.code(503).header('cache-control', 'no-store').send({ error: sin.codigo, mensaje: sin.mensaje });
  const error = (reply: FastifyReply, codigo: string, defecto = 400) =>
    reply.code(HTTP_ERROR[codigo] ?? defecto).send({ error: codigo, ...(MENSAJE_ERROR[codigo] ? { mensaje: MENSAJE_ERROR[codigo] } : {}) });
  /** Ejecuta con el adaptador; los errores de la BD salen con su mensaje llano (la transacción ya está deshecha). */
  async function con<T>(reply: FastifyReply, trabajo: (d: AdaptadorRrhh) => Promise<T>): Promise<T | FastifyReply> {
    if (datos === null) return pendiente(reply);
    try {
      return await trabajo(datos);
    } catch (e) {
      if (e instanceof ErrorRrhhBd) {
        app.log.warn({ msg: `Trabajadores: ${e.codigo}` });
        return reply.code(e.http).send({ error: e.codigo, mensaje: e.mensaje });
      }
      throw e;
    }
  }

  // Sesión en todas las rutas del módulo; en escritura, además origen y JSON (defensa en profundidad).
  app.addHook('onRequest', async (req, reply) => {
    const ruta = req.url.split('?')[0];
    if (!ruta.startsWith(PREFIJO_RRHH)) return;
    if (!sesionValida(req)) return reply.code(401).header('cache-control', 'no-store').send({ error: 'NO_AUTENTICADO' });
    reply.header('cache-control', 'no-store');
    if (req.method === 'GET' || req.method === 'HEAD') return;
    if (!esEscrituraRrhh(req.method, ruta)) return reply.code(405).send({ error: 'SOLO_LECTURA' });
    if (!origenEscrituraValido(req)) return reply.code(403).send({ error: 'ORIGEN_NO_PERMITIDO' });
    if (!/^application\/json\b/i.test(req.headers['content-type'] ?? '')) return reply.code(415).send({ error: 'SOLO_JSON' });
  });

  app.get('/api/rrhh/estado', async (): Promise<EstadoRrhhDTO> => {
    if (modo === 'FIXTURES') return { modo, conectado: false, datos_ejemplo: true, mensaje: 'Datos de ejemplo en memoria', anular_eventos: datos?.anularEventos ?? true };
    if (datos === null) return { modo, conectado: false, datos_ejemplo: false, mensaje: sin.mensaje, anular_eventos: false };
    return { modo, conectado: true, datos_ejemplo: false, mensaje: TEXTO_BANNER_REAL, anular_eventos: datos.anularEventos };
  });

  const farmacia = (v: string | undefined) => filtroFarmacia(v ?? 'AMBAS');

  app.get<{ Querystring: { farmacia?: string; bajas?: string } }>('/api/rrhh/trabajadoras', async (req, reply) => {
    const f = farmacia(req.query.farmacia);
    if (f === null) return datos === null ? pendiente(reply) : reply.code(400).send({ error: 'FARMACIA_NO_VALIDA' });
    return con(reply, async (d) => d.trabajadoras(f, req.query.bajas === '1'));
  });
  app.get<{ Params: { id: string } }>('/api/rrhh/trabajadoras/:id', async (req, reply) => {
    if (datos !== null && !UUID.test(req.params.id)) return reply.code(400).send({ error: 'ID_NO_VALIDO' });
    return con(reply, async (d) => (await d.trabajadora(req.params.id.toLowerCase())) ?? reply.code(404).send({ error: 'TRABAJADORA_NO_ENCONTRADA' }));
  });
  app.get('/api/rrhh/convenio', async (_req, reply) => con(reply, async (d) => d.convenio()));
  app.post('/api/rrhh/convenio', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const v = validarCrearConvenio(req.body);
    if (!v.ok) return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.errores });
    return con(reply, async (d) => ({ creados: await d.crearConvenio(v.anios, quien), convenio: await d.convenio() }));
  });
  app.get<{ Querystring: { farmacia?: string } }>('/api/rrhh/historial', async (req, reply) => {
    const f = farmacia(req.query.farmacia);
    if (f === null) return datos === null ? pendiente(reply) : reply.code(400).send({ error: 'FARMACIA_NO_VALIDA' });
    return con(reply, async (d) => d.historial(f));
  });

  app.post('/api/rrhh/trabajadoras', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const v = validarTrabajadora(req.body, 'alta');
    if (!v.ok) return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.errores });
    return con(reply, async (d) => {
      const t = await d.crear(v.datos, quien);
      return typeof t === 'string' ? error(reply, t) : reply.code(201).send(t);
    });
  });
  app.put<{ Params: { id: string } }>('/api/rrhh/trabajadoras/:id', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    if (!UUID.test(req.params.id)) return reply.code(400).send({ error: 'ID_NO_VALIDO' });
    const v = validarTrabajadora(req.body, 'edicion');
    if (!v.ok) return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.errores });
    return con(reply, async (d) => {
      const t = await d.editar(req.params.id.toLowerCase(), v.datos, quien);
      if (typeof t === 'string') return error(reply, t);
      return t ?? reply.code(404).send({ error: 'TRABAJADORA_NO_ENCONTRADA' });
    });
  });
  app.put<{ Params: { id: string } }>('/api/rrhh/trabajadoras/:id/baja', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    if (!UUID.test(req.params.id)) return reply.code(400).send({ error: 'ID_NO_VALIDO' });
    const v = validarFechaBaja(req.body);
    if (!v.ok) return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.errores });
    return con(reply, async (d) => {
      const t = await d.darDeBaja(req.params.id.toLowerCase(), v.fecha, quien);
      if (typeof t === 'string') return error(reply, t);
      return t ?? reply.code(404).send({ error: 'TRABAJADORA_NO_ENCONTRADA' });
    });
  });
  app.put<{ Params: { id: string } }>('/api/rrhh/trabajadoras/:id/anular', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    if (!UUID.test(req.params.id)) return reply.code(400).send({ error: 'ID_NO_VALIDO' });
    const v = validarAnulacion(req.body);
    if (!v.ok) return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.errores });
    return con(reply, async (d) => {
      const t = await d.anular(req.params.id.toLowerCase(), quien);
      if (typeof t === 'string') return error(reply, t);
      return t ?? reply.code(404).send({ error: 'TRABAJADORA_NO_ENCONTRADA' });
    });
  });

  // --- TA2: calendario ---------------------------------------------------------
  app.get<{ Querystring: { farmacia?: string; desde?: string; hasta?: string } }>('/api/rrhh/eventos', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const f = farmacia(req.query.farmacia);
    if (f === null) return reply.code(400).send({ error: 'FARMACIA_NO_VALIDA' });
    const { desde, hasta } = req.query;
    if (!esFecha(desde) || !esFecha(hasta) || hasta < desde || !enAniosConvenio(desde) || !enAniosConvenio(hasta) || diasEntre(desde, hasta) + 1 > MAX_DIAS_LECTURA) {
      return reply.code(400).send({ error: 'RANGO_NO_VALIDO' });
    }
    return con(reply, async (d) => d.calendario(f, desde, hasta));
  });
  /** TA-REAL «Notas próximas»: notas desde `desde` (hoy en el navegador). */
  app.get<{ Querystring: { farmacia?: string; desde?: string } }>('/api/rrhh/eventos/notas', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const f = farmacia(req.query.farmacia);
    if (f === null) return reply.code(400).send({ error: 'FARMACIA_NO_VALIDA' });
    const desde = req.query.desde;
    if (!esFecha(desde)) return reply.code(400).send({ error: 'FECHA_NO_VALIDA' });
    return con(reply, async (d) => d.notasProximas(f, desde < FECHA_MIN ? FECHA_MIN : desde > FECHA_MAX ? FECHA_MAX : desde));
  });
  app.get<{ Querystring: { farmacia?: string } }>('/api/rrhh/eventos/historial', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const f = farmacia(req.query.farmacia);
    if (f === null) return reply.code(400).send({ error: 'FARMACIA_NO_VALIDA' });
    return con(reply, async (d) => d.historialEventos(f));
  });
  app.post('/api/rrhh/eventos', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const v = validarPeticionEventos(req.body);
    if (!v.ok) return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.errores });
    return con(reply, async (d) => {
      const r = await d.cambiarEventos(v.peticion, quien);
      return typeof r === 'string' ? error(reply, r) : r;
    });
  });
  app.post('/api/rrhh/eventos/deshacer', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const v = validarDeshacer(req.body);
    if (!v.ok) return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.errores });
    return con(reply, async (d) => {
      const r = await d.deshacerEventos(v.cambio_id, quien);
      return typeof r === 'string' ? error(reply, r, 409) : r;
    });
  });
}
