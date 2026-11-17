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
 * TA-FICHA: GET /api/rrhh/fichas (resumen de plantilla) y GET /api/rrhh/trabajadoras/:id/anual (ficha anual), solo
 * lectura, con los cálculos puros de ficha_anual.ts sobre las lecturas existentes (calendario del año y convenio).
 *
 * TA-REAL-2 (migración 33): POST /api/rrhh/convenio/vacaciones (completar solo vacaciones_dias_naturales y
 * vacaciones_fuente de los años que no los tienen); PUT /api/rrhh/trabajadoras/:id/ajustes/:anio (días extra de
 * vacaciones y nota) y PUT …/ajustes/:anio/anular (con confirmación). La ficha anual suma los días extra.
 *
 * TA3: GET /api/rrhh/guardias (semanas de guardia y festivos de un año o un rango); PUT /api/rrhh/guardias/:lunes
 * (farmacia, guardia y apoyo de la semana); POST /api/rrhh/festivos (alta); PUT /api/rrhh/festivos/:fecha/anular (baja,
 * con confirmación) y PUT /api/rrhh/festivos/:fecha/guardia (farmacia y persona de guardia del festivo). TA3-REAL:
 * también en REAL (migración 34: guardias_semana, guardias_festivo y festivos, rol cf_trabajadores_web; errores de la
 * BD con mensaje llano). La ficha anual añade «Guardias del año» (fuera de cómputo).
 *
 * Se registra sobre cualquier instancia de Fastify (pruebas con instancia propia, sin BD).
 */
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import {
  ERROR_FALTA_CREDENCIAL, MENSAJE_FALTA_CREDENCIAL, TEXTO_BANNER_REAL, filtroFarmacia, validarAjuste, validarAnulacion, validarCompletarVacaciones,
  validarCrearConvenio, validarFechaBaja, validarTrabajadora, type EstadoRrhhDTO,
} from './contrato.ts';
import { crearAdaptadorRrhhFixtures, type AdaptadorRrhh } from './adaptador_fixtures.ts';
import {
  FECHA_MAX, FECHA_MIN, MAX_DIAS_LECTURA, diasEntre, enAniosConvenio, esFecha, validarDeshacer, validarPeticionEventos,
} from './eventos.ts';
import { ErrorRrhhBd, MENSAJES_BD } from './errores_bd.ts';
import { anioFicha, calcularFichaAnual, diasEnAlta, reglasFicha, resumenPlantilla, type FichaAnualDTO, type ResumenPlantillaDTO } from './ficha_anual.ts';
import {
  enAniosGuardia, esLunesAdmitido, validarFestivo, validarGuardiaFestivo, validarGuardiaSemana, type GuardiasTa3,
} from './guardias.ts';

/** Hoy en el reloj del servidor (fecha local), si el navegador no manda el suyo. */
function hoyServidor(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** Código HTTP de cada error del módulo (y mensaje llano de los que lo necesitan). */
const HTTP_ERROR: Readonly<Record<string, number>> = {
  TRABAJADORA_NO_VALIDA: 400, FRANJA_NO_VALIDA: 400, EVENTO_NO_ENCONTRADO: 404, EVENTO_CONFIRMADO: 409, EVENTO_FUERA_DEL_ALTA: 409,
  NADA_QUE_DESHACER: 409, NO_ES_EL_ULTIMO: 409, ESTADO_CAMBIADO: 409,
  YA_DE_BAJA: 409, YA_ANULADA: 409, BAJA_ANTES_DEL_ALTA: 400, NOMBRE_DUPLICADO: 409,
  SIN_AJUSTE: 409, SIN_ALTA_EN_EL_ANIO: 409, TRABAJADORA_ANULADA: 409,
  PERSONA_NO_VALIDA: 409, APOYO_IGUAL_GUARDIA: 400, OTRA_SIN_PERSONAS: 400, PERSONA_OBLIGATORIA: 400, NO_ES_FESTIVO: 409,
  FESTIVO_DUPLICADO: 409, SIN_FESTIVO: 409, SIN_GUARDIA: 409,
};
const MENSAJE_ERROR: Readonly<Record<string, string>> = {
  PERSONA_NO_VALIDA: 'Esa persona no es de esa farmacia o no está de alta esos días.',
  APOYO_IGUAL_GUARDIA: 'El apoyo del sábado tiene que ser otra persona.',
  OTRA_SIN_PERSONAS: 'La farmacia ajena (OTRA) no lleva personas.',
  PERSONA_OBLIGATORIA: 'Elige la persona de guardia.',
  NO_ES_FESTIVO: 'Ese día no es festivo.',
  FESTIVO_DUPLICADO: 'Ese día ya es festivo.',
  SIN_FESTIVO: 'Ese día no es festivo.',
  SIN_GUARDIA: 'No hay ninguna guardia que quitar ahí: recarga y vuelve a intentarlo.',
  SIN_AJUSTE: 'Esa persona no tiene días extra ese año.',
  SIN_ALTA_EN_EL_ANIO: 'Esa persona no está de alta ningún día de ese año.',
  TRABAJADORA_ANULADA: 'Esa ficha está anulada.',
  EVENTO_FUERA_DEL_ALTA: MENSAJES_BD.EVENTO_FUERA_DEL_ALTA.mensaje,
  BAJA_ANTES_DEL_ALTA: 'La fecha de baja no puede ser anterior a la de alta.',
  NOMBRE_DUPLICADO: 'Ya hay otra ficha con ese nombre en esa farmacia.',
};

export const PREFIJO_RRHH = '/api/rrhh/';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Rutas de escritura del módulo (método + patrón): las únicas que el servidor admite fuera de login/logout.
 * TA1: fichas (POST alta; PUT edición y baja; TA-REAL: PUT anulación). TA-REAL: POST /api/rrhh/convenio (crear los
 * años firmados que falten). TA2: POST /api/rrhh/eventos y POST /api/rrhh/eventos/deshacer. TA-REAL-2: POST
 * /api/rrhh/convenio/vacaciones; PUT /api/rrhh/trabajadoras/:id/ajustes/:anio(/anular). TA3: PUT /api/rrhh/guardias/:lunes;
 * POST /api/rrhh/festivos; PUT /api/rrhh/festivos/:fecha/(anular|guardia). TA3-4 (goma del calendario): PUT
 * /api/rrhh/guardias/:lunes/anular y PUT /api/rrhh/festivos/:fecha/guardia/anular. Nunca DELETE ni PATCH.
 */
export function esEscrituraRrhh(metodo: string, ruta: string): boolean {
  if (metodo === 'POST') {
    return ruta === '/api/rrhh/trabajadoras' || ruta === '/api/rrhh/convenio' || ruta === '/api/rrhh/convenio/vacaciones'
      || ruta === '/api/rrhh/eventos' || ruta === '/api/rrhh/eventos/deshacer' || ruta === '/api/rrhh/festivos';
  }
  if (metodo === 'PUT') {
    return /^\/api\/rrhh\/trabajadoras\/[0-9a-fA-F-]{36}(\/baja|\/anular|\/ajustes\/\d{4}(\/anular)?)?$/.test(ruta)
      || /^\/api\/rrhh\/guardias\/\d{4}-\d{2}-\d{2}(\/anular)?$/.test(ruta)
      || /^\/api\/rrhh\/festivos\/\d{4}-\d{2}-\d{2}\/(anular|guardia|guardia\/anular)$/.test(ruta);
  }
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
    const guardias_disponibles = datos !== null;
    if (modo === 'FIXTURES') return { modo, conectado: false, datos_ejemplo: true, mensaje: 'Datos de ejemplo en memoria', guardias_disponibles };
    if (datos === null) return { modo, conectado: false, datos_ejemplo: false, mensaje: sin.mensaje, guardias_disponibles };
    return { modo, conectado: true, datos_ejemplo: false, mensaje: TEXTO_BANNER_REAL, guardias_disponibles };
  });

  const farmacia = (v: string | undefined) => filtroFarmacia(v ?? 'AMBAS');

  app.get<{ Querystring: { farmacia?: string; bajas?: string } }>('/api/rrhh/trabajadoras', async (req, reply) => {
    const f = farmacia(req.query.farmacia);
    if (f === null) return datos === null ? pendiente(reply) : reply.code(400).send({ error: 'FARMACIA_NO_VALIDA' });
    return con(reply, async (d) => d.trabajadoras(f, req.query.bajas === '1'));
  });
  // --- TA-FICHA: ficha anual y resumen de plantilla (solo lectura; mismas lecturas en FIXTURES y REAL) -----------
  /** Año (por defecto el de hoy, dentro de los del convenio) y hoy (el del navegador; por defecto, el del servidor). */
  const anioYHoy = (q: { anio?: string; hoy?: string }): { anio: number; hoy: string } | null => {
    const hoy = q.hoy === undefined ? hoyServidor() : q.hoy;
    if (!esFecha(hoy)) return null;
    const porDefecto = anioFicha(hoy.slice(0, 4)) ?? (hoy < FECHA_MIN ? anioFicha(FECHA_MIN.slice(0, 4)) : anioFicha(FECHA_MAX.slice(0, 4)));
    const anio = q.anio === undefined ? porDefecto : anioFicha(q.anio);
    return anio === null ? null : { anio, hoy };
  };
  app.get<{ Querystring: { farmacia?: string; anio?: string; hoy?: string } }>('/api/rrhh/fichas', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const f = farmacia(req.query.farmacia);
    if (f === null) return reply.code(400).send({ error: 'FARMACIA_NO_VALIDA' });
    const ah = anioYHoy(req.query);
    if (ah === null) return reply.code(400).send({ error: 'ANIO_NO_VALIDO' });
    return con(reply, async (d): Promise<ResumenPlantillaDTO> => {
      const cal = await d.calendario(f, `${ah.anio}-01-01`, `${ah.anio}-12-31`);
      const convenio = await d.convenio();
      const filas = resumenPlantilla(cal.trabajadoras, cal.eventos, convenio, ah.anio, ah.hoy, {
        ajustes: await d.ajustes(f, ah.anio), festivos: await d.guardiasTa3.fechasFestivo(ah.anio),
      });
      return { farmacia: f, anio: ah.anio, hoy: ah.hoy, filas, reglas: reglasFicha(convenio, ah.anio) };
    });
  });
  app.get<{ Params: { id: string }; Querystring: { anio?: string; hoy?: string } }>('/api/rrhh/trabajadoras/:id/anual', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    if (!UUID.test(req.params.id)) return reply.code(400).send({ error: 'ID_NO_VALIDO' });
    const ah = anioYHoy(req.query);
    if (ah === null) return reply.code(400).send({ error: 'ANIO_NO_VALIDO' });
    const id = req.params.id.toLowerCase();
    return con(reply, async (d) => {
      const det = await d.trabajadora(id);
      if (!det) return reply.code(404).send({ error: 'TRABAJADORA_NO_ENCONTRADA' });
      const convenio = await d.convenio();
      const base = { anio: ah.anio, hoy: ah.hoy, reglas: reglasFicha(convenio, ah.anio) };
      if (det.trabajadora.anulada) return { ...base, ficha: null, motivo: 'ANULADA' } satisfies FichaAnualDTO;
      const cal = await d.calendario(det.trabajadora.farmacia, `${ah.anio}-01-01`, `${ah.anio}-12-31`);
      const t = cal.trabajadoras.find((x) => x.id === id);
      if (!t) return { ...base, ficha: null, motivo: 'SIN_ALTA_EN_EL_ANIO' } satisfies FichaAnualDTO;
      const ajustes = await d.ajustes(t.farmacia, ah.anio);
      return {
        ...base, ficha: calcularFichaAnual(t, cal.eventos, convenio, ah.anio, ah.hoy, { ajustes, festivos: await d.guardiasTa3.fechasFestivo(ah.anio) }), motivo: null,
        guardias: await d.guardiasTa3.resumenPersona(t.id, ah.anio),
      } satisfies FichaAnualDTO;
    });
  });

  // --- TA3 / TA3-REAL: guardias y festivos (FIXTURES: memoria; REAL: migración 34) ------------------------------------
  /** Con guardias y festivos del adaptador; un error de regla sale con su código y mensaje; los de la BD, llanos. */
  const conTa3 = (reply: FastifyReply, trabajo: (g: GuardiasTa3) => unknown) => con(reply, async (d) => {
    const r = await trabajo(d.guardiasTa3);
    return typeof r === 'string' ? error(reply, r) : r;
  });
  app.get<{ Querystring: { anio?: string; desde?: string; hasta?: string } }>('/api/rrhh/guardias', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const q = req.query;
    let desde: string; let hasta: string;
    if (q.anio !== undefined) {
      const a = anioFicha(q.anio);
      if (a === null || q.desde !== undefined || q.hasta !== undefined) return reply.code(400).send({ error: 'RANGO_NO_VALIDO' });
      [desde, hasta] = [`${a}-01-01`, `${a}-12-31`];
    } else {
      if (!esFecha(q.desde) || !esFecha(q.hasta) || q.hasta < q.desde || !enAniosGuardia(q.desde) || !enAniosGuardia(q.hasta) || diasEntre(q.desde, q.hasta) + 1 > MAX_DIAS_LECTURA) {
        return reply.code(400).send({ error: 'RANGO_NO_VALIDO' });
      }
      [desde, hasta] = [q.desde, q.hasta];
    }
    return conTa3(reply, (g) => g.vista(desde, hasta));
  });
  app.put<{ Params: { lunes: string } }>('/api/rrhh/guardias/:lunes', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const v = validarGuardiaSemana(req.params.lunes, req.body);
    if (!v.ok) return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.errores });
    return conTa3(reply, (g) => g.guardarSemana(v.datos, quien));
  });
  app.post('/api/rrhh/festivos', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const v = validarFestivo(req.body);
    if (!v.ok) return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.errores });
    return conTa3(reply, async (g) => {
      const r = await g.crearFestivo(v.fecha, v.nombre, v.ambito, quien);
      return typeof r === 'string' ? r : reply.code(201).send(r);
    });
  });
  const fechaFestivo = (f: string) => esFecha(f) && enAniosGuardia(f);
  app.put<{ Params: { fecha: string } }>('/api/rrhh/festivos/:fecha/anular', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const v = validarAnulacion(req.body);
    if (!v.ok || !fechaFestivo(req.params.fecha)) {
      return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.ok ? { fecha: 'Fecha no válida' } : v.errores });
    }
    return conTa3(reply, (g) => g.anularFestivo(req.params.fecha, quien));
  });
  app.put<{ Params: { fecha: string } }>('/api/rrhh/festivos/:fecha/guardia', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const v = validarGuardiaFestivo(req.body);
    if (!v.ok || !fechaFestivo(req.params.fecha)) {
      return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.ok ? { fecha: 'Fecha no válida' } : v.errores });
    }
    return conTa3(reply, (g) => g.guardarGuardiaFestivo(req.params.fecha, v.farmacia, v.persona_id, quien));
  });
  // TA3-4: goma del calendario (anular con confirmación explícita en el cuerpo, como las demás anulaciones).
  app.put<{ Params: { lunes: string } }>('/api/rrhh/guardias/:lunes/anular', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const v = validarAnulacion(req.body);
    if (!v.ok || !esLunesAdmitido(req.params.lunes)) {
      return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.ok ? { lunes: 'La semana empieza en lunes, dentro de los años del convenio' } : v.errores });
    }
    return conTa3(reply, (g) => g.anularSemana(req.params.lunes, quien));
  });
  app.put<{ Params: { fecha: string } }>('/api/rrhh/festivos/:fecha/guardia/anular', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const v = validarAnulacion(req.body);
    if (!v.ok || !fechaFestivo(req.params.fecha)) {
      return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.ok ? { fecha: 'Fecha no válida' } : v.errores });
    }
    return conTa3(reply, (g) => g.anularGuardiaFestivo(req.params.fecha, quien));
  });

  // --- TA-REAL-2: días extra de vacaciones por persona y año (trabajadoras_ajustes_anuales) -------------------------
  /** Id, año y ficha (sin anular y con algún día de alta en el año); si no, la respuesta de error. */
  const fichaParaAjuste = async (d: AdaptadorRrhh, reply: FastifyReply, p: { id: string; anio: string }) => {
    const anio = anioFicha(p.anio);
    if (!UUID.test(p.id) || anio === null) return { r: reply.code(400).send({ error: !UUID.test(p.id) ? 'ID_NO_VALIDO' : 'ANIO_NO_VALIDO' }) };
    const det = await d.trabajadora(p.id.toLowerCase());
    if (!det) return { r: reply.code(404).send({ error: 'TRABAJADORA_NO_ENCONTRADA' }) };
    if (det.trabajadora.anulada) return { r: error(reply, 'TRABAJADORA_ANULADA') };
    if (diasEnAlta(det.trabajadora, anio) === 0) return { r: error(reply, 'SIN_ALTA_EN_EL_ANIO') };
    return { id: det.trabajadora.id, anio };
  };
  app.put<{ Params: { id: string; anio: string } }>('/api/rrhh/trabajadoras/:id/ajustes/:anio', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const v = validarAjuste(req.body);
    if (!v.ok) return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.errores });
    return con(reply, async (d) => {
      const f = await fichaParaAjuste(d, reply, req.params);
      if ('r' in f) return f.r;
      return d.guardarAjuste(f.id, f.anio, v.dias, v.nota, quien);
    });
  });
  app.put<{ Params: { id: string; anio: string } }>('/api/rrhh/trabajadoras/:id/ajustes/:anio/anular', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const v = validarAnulacion(req.body);
    if (!v.ok) return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.errores });
    return con(reply, async (d) => {
      const f = await fichaParaAjuste(d, reply, req.params);
      if ('r' in f) return f.r;
      const r = await d.anularAjuste(f.id, f.anio, quien);
      return typeof r === 'string' ? error(reply, r) : r;
    });
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
  /** TA-REAL-2: completa solo vacaciones_dias_naturales (30) y vacaciones_fuente de los años que no los tienen. */
  app.post('/api/rrhh/convenio/vacaciones', async (req, reply) => {
    if (datos === null) return pendiente(reply);
    const v = validarCompletarVacaciones(req.body);
    if (!v.ok) return reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores: v.errores });
    return con(reply, async (d) => ({ completados: await d.completarVacacionesConvenio(v.anios, quien), convenio: await d.convenio() }));
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
