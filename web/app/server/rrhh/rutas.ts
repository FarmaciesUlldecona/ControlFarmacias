/**
 * TA1/TA2: API /api/rrhh/*. GET y, solo aquí, POST/PUT (fichas: alta, edición, baja; TA2: eventos del calendario
 * y deshacer, solo POST). Toda ruta exige sesión; la escritura exige
 * además Origin del mismo sitio (obligatorio), Sec-Fetch-Site same-origin si viene y Content-Type application/json.
 *
 * Modo FIXTURES: adaptador RRHH_FIXTURES en memoria (datos de ejemplo). Modo REAL: todas las rutas responden 503
 * "Módulo pendiente de conexión (T1)" sin ningún dato (nunca datos de ejemplo como reales). Solo /api/rrhh/estado
 * responde 200 con el aviso, para que la pantalla lo muestre.
 *
 * Se registra sobre cualquier instancia de Fastify (pruebas con instancia propia, sin BD).
 */
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import {
  ERROR_PENDIENTE_T1, MENSAJE_PENDIENTE_T1, filtroFarmacia, validarFechaBaja, validarTrabajadora, type EstadoRrhhDTO,
} from './contrato.ts';
import { crearAdaptadorRrhhFixtures, type AdaptadorRrhh } from './adaptador_fixtures.ts';
import { MAX_DIAS_LECTURA, diasEntre, enAniosConvenio, esFecha, validarDeshacer, validarPeticionEventos } from './eventos.ts';

/** Código HTTP de cada error del calendario. */
const HTTP_ERROR_EVENTOS: Readonly<Record<string, number>> = {
  TRABAJADORA_NO_VALIDA: 400, FRANJA_NO_VALIDA: 400, EVENTO_NO_ENCONTRADO: 404, EVENTO_CONFIRMADO: 409,
  NADA_QUE_DESHACER: 409, NO_ES_EL_ULTIMO: 409, ESTADO_CAMBIADO: 409,
};

export const PREFIJO_RRHH = '/api/rrhh/';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Rutas de escritura del módulo (método + patrón): las únicas que el servidor admite fuera de login/logout.
 * TA1: fichas (POST alta; PUT edición y baja). TA2: calendario, solo POST /api/rrhh/eventos (pintar, goma, rellenar,
 * confirmar, quitar confirmación, editar horas) y POST /api/rrhh/eventos/deshacer. Nunca DELETE ni PATCH.
 */
export function esEscrituraRrhh(metodo: string, ruta: string): boolean {
  if (metodo === 'POST') return ruta === '/api/rrhh/trabajadoras' || ruta === '/api/rrhh/eventos' || ruta === '/api/rrhh/eventos/deshacer';
  if (metodo === 'PUT') return /^\/api\/rrhh\/trabajadoras\/[0-9a-fA-F-]{36}(\/baja)?$/.test(ruta);
  return false;
}

export interface OpcionesRrhh {
  modo: 'FIXTURES' | 'REAL';
  /** Sesión válida (cookie). */
  sesionValida: (req: FastifyRequest) => boolean;
  /** Quién figura en el historial. */
  quien: string;
  /** Solo FIXTURES; por defecto, uno nuevo con la semilla de ejemplo. */
  adaptador?: AdaptadorRrhh;
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
  const datos: AdaptadorRrhh | null = modo === 'FIXTURES' ? opciones.adaptador ?? crearAdaptadorRrhhFixtures() : null;

  const pendiente = (reply: FastifyReply) => reply.code(503).header('cache-control', 'no-store').send({ error: ERROR_PENDIENTE_T1, mensaje: MENSAJE_PENDIENTE_T1 });

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

  app.get('/api/rrhh/estado', async (): Promise<EstadoRrhhDTO> => (modo === 'FIXTURES'
    ? { modo, conectado: false, datos_ejemplo: true, mensaje: 'Datos de ejemplo en memoria' }
    : { modo, conectado: false, datos_ejemplo: false, mensaje: MENSAJE_PENDIENTE_T1 }));

  app.get<{ Querystring: { farmacia?: string; bajas?: string } }>('/api/rrhh/trabajadoras', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const f = filtroFarmacia(req.query.farmacia ?? 'AMBAS');
    if (f === null) return reply.code(400).send({ error: 'FARMACIA_NO_VALIDA' });
    return datos.trabajadoras(f, req.query.bajas === '1');
  });
  app.get<{ Params: { id: string } }>('/api/rrhh/trabajadoras/:id', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    if (!UUID.test(req.params.id)) return reply.code(400).send({ error: 'ID_NO_VALIDO' });
    const d = datos.trabajadora(req.params.id.toLowerCase());
    return d ?? reply.code(404).send({ error: 'TRABAJADORA_NO_ENCONTRADA' });
  });
  app.get('/api/rrhh/convenio', async (_req, reply) => (datos === null ? pendiente(reply) : datos.convenio()));
  app.get<{ Querystring: { farmacia?: string } }>('/api/rrhh/historial', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const f = filtroFarmacia(req.query.farmacia ?? 'AMBAS');
    if (f === null) return reply.code(400).send({ error: 'FARMACIA_NO_VALIDA' });
    return datos.historial(f);
  });

  app.post('/api/rrhh/trabajadoras', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const v = validarTrabajadora(req.body, 'alta');
    if (!v.ok) return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.errores });
    return reply.code(201).send(datos.crear(v.datos, quien));
  });
  app.put<{ Params: { id: string } }>('/api/rrhh/trabajadoras/:id', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    if (!UUID.test(req.params.id)) return reply.code(400).send({ error: 'ID_NO_VALIDO' });
    const v = validarTrabajadora(req.body, 'edicion');
    if (!v.ok) return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.errores });
    const t = datos.editar(req.params.id.toLowerCase(), v.datos, quien);
    return t ?? reply.code(404).send({ error: 'TRABAJADORA_NO_ENCONTRADA' });
  });
  app.put<{ Params: { id: string } }>('/api/rrhh/trabajadoras/:id/baja', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    if (!UUID.test(req.params.id)) return reply.code(400).send({ error: 'ID_NO_VALIDO' });
    const v = validarFechaBaja(req.body);
    if (!v.ok) return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.errores });
    const t = datos.darDeBaja(req.params.id.toLowerCase(), v.fecha, quien);
    if (t === 'YA_DE_BAJA') return reply.code(409).send({ error: 'YA_DE_BAJA' });
    return t ?? reply.code(404).send({ error: 'TRABAJADORA_NO_ENCONTRADA' });
  });

  // --- TA2: calendario ---------------------------------------------------------
  app.get<{ Querystring: { farmacia?: string; desde?: string; hasta?: string } }>('/api/rrhh/eventos', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const f = filtroFarmacia(req.query.farmacia ?? 'AMBAS');
    if (f === null) return reply.code(400).send({ error: 'FARMACIA_NO_VALIDA' });
    const { desde, hasta } = req.query;
    if (!esFecha(desde) || !esFecha(hasta) || hasta < desde || !enAniosConvenio(desde) || !enAniosConvenio(hasta) || diasEntre(desde, hasta) + 1 > MAX_DIAS_LECTURA) {
      return reply.code(400).send({ error: 'RANGO_NO_VALIDO' });
    }
    return datos.calendario(f, desde, hasta);
  });
  app.get<{ Querystring: { farmacia?: string } }>('/api/rrhh/eventos/historial', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const f = filtroFarmacia(req.query.farmacia ?? 'AMBAS');
    if (f === null) return reply.code(400).send({ error: 'FARMACIA_NO_VALIDA' });
    return datos.historialEventos(f);
  });
  app.post('/api/rrhh/eventos', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const v = validarPeticionEventos(req.body);
    if (!v.ok) return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.errores });
    const r = datos.cambiarEventos(v.peticion, quien);
    if (typeof r === 'string') return reply.code(HTTP_ERROR_EVENTOS[r] ?? 400).send({ error: r });
    return r;
  });
  app.post('/api/rrhh/eventos/deshacer', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const v = validarDeshacer(req.body);
    if (!v.ok) return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.errores });
    const r = datos.deshacerEventos(v.cambio_id, quien);
    if (typeof r === 'string') return reply.code(HTTP_ERROR_EVENTOS[r] ?? 409).send({ error: r });
    return r;
  });
}
