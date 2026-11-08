/**
 * Servidor local de la web ControlFarmacias fase 1. Solo lectura y solo 127.0.0.1.
 *
 *   CF_MODO=FIXTURES (por defecto) | REAL, o --modo=...   — REAL solo lo ejecuta Pío (npm run dev:real
 *   o iniciar_web.cmd).
 *   Puerto fijo 4747. CF_PUERTO solo se admite en FIXTURES (Playwright); en REAL, si no es 4747, no arranca.
 *
 * Acceso con contraseña (H4b, server/acceso.ts): sin sesión, cualquier ruta devuelve la pantalla de acceso
 * (HTML autónomo) y cualquier /api/* devuelve 401. Solo POST /api/login y /api/logout admiten POST.
 *
 * Sirve la API /api/* y, si existe, el front compilado (dist/).
 */
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { parseEnv } from 'node:util';
import Fastify, { type FastifyReply, type FastifyRequest } from 'fastify';
import fastifyStatic from '@fastify/static';
import { FARMACIA, UUID_RE, type Contrato } from './contrato.ts';
import { crearAdaptadorFixtures } from './adaptador_fixtures.ts';
import {
  CLAVE_FIXTURES, CSP_ACCESO, USUARIO, cookieBorrada, cookieSesion, crearAcceso, crearHash, destinoSeguro,
  leerHash, paginaAcceso, tokenDeCookie, verificarClave, type Acceso, type AvisoAcceso, type FuentesAcceso,
} from './acceso.ts';

const HOST = '127.0.0.1';
export const PUERTO_FIJO = 4747;
const MODOS = ['FIXTURES', 'REAL'] as const;
type Modo = (typeof MODOS)[number];
const POST_PERMITIDOS = new Set(['/api/login', '/api/logout']);

/**
 * Modo: argumento --modo=REAL|FIXTURES (lo usa `npm run dev:real`, portable a cmd de Windows) o CF_MODO.
 * Si ambos están y no coinciden, no arranca (falla cerrado).
 */
function leerModo(): Modo {
  const arg = process.argv.find((a) => a.startsWith('--modo='))?.slice('--modo='.length);
  const env = process.env.CF_MODO;
  if (arg !== undefined && env !== undefined && arg !== env) throw new Error(`CF_MODO_CONTRADICTORIO: --modo=${arg} y CF_MODO=${env}`);
  const m = arg ?? env ?? 'FIXTURES';
  if (!(MODOS as readonly string[]).includes(m)) throw new Error(`CF_MODO_NO_VALIDO: ${m}`);
  return m as Modo;
}

export function leerPuerto(modo: Modo): number {
  const v = process.env.CF_PUERTO;
  if (v === undefined || v === '') return PUERTO_FIJO;
  if (modo === 'REAL' && v !== String(PUERTO_FIJO)) throw new Error(`CF_PUERTO_NO_PERMITIDO_EN_REAL: el puerto es fijo (${PUERTO_FIJO})`);
  const n = Number(v);
  if (!Number.isInteger(n) || n <= 0 || n > 65535) throw new Error('CF_PUERTO_NO_VALIDO');
  return n;
}

async function crearContrato(modo: Modo): Promise<{ contrato: Contrato; cerrar: () => Promise<void> }> {
  if (modo === 'FIXTURES') return { contrato: crearAdaptadorFixtures(), cerrar: async () => {} };
  const { crearAdaptadorReal } = await import('./adaptador_real.ts');
  const real = crearAdaptadorReal();
  return { contrato: real.contrato, cerrar: real.cerrar };
}

/**
 * Hash de acceso. FIXTURES: contraseña ficticia fija. REAL: CF_WEB_PASSWORD_HASH leído del propio .env.web
 * (no del entorno del proceso); sin hash válido no arranca, y tampoco si el hash admite la contraseña ficticia.
 */
async function crearGestorAcceso(modo: Modo): Promise<Acceso> {
  if (modo === 'FIXTURES') return crearAcceso(leerHash(await crearHash(CLAVE_FIXTURES)));
  const { RUTA_ENV_WEB } = await import('./adaptador_real.ts');
  if (!existsSync(RUTA_ENV_WEB)) throw new Error('ENV_WEB_AUSENTE');
  const hash = leerHash(parseEnv(readFileSync(RUTA_ENV_WEB, 'utf8')).CF_WEB_PASSWORD_HASH);
  if (await verificarClave(CLAVE_FIXTURES, hash)) throw new Error('HASH_ACCESO_ES_EL_DE_FIXTURES');
  return crearAcceso(hash);
}

/** Figtree empaquetada por Vite (dist/assets): única cosa pública además del formulario. */
function fuentesAcceso(dist: string): { fuentes: FuentesAcceso; publicas: Set<string> } {
  const fuentes: FuentesAcceso = {};
  const publicas = new Set<string>();
  const dir = join(dist, 'assets');
  if (!existsSync(dir)) return { fuentes, publicas };
  for (const f of readdirSync(dir)) {
    const m = /^figtree-latin-(400|600|800)-normal-[A-Za-z0-9_-]+\.woff2$/.exec(f);
    if (!m) continue;
    const ruta = `/assets/${f}`;
    fuentes[Number(m[1]) as 400 | 600 | 800] = ruta;
    publicas.add(ruta);
  }
  return { fuentes, publicas };
}

function ruta(req: FastifyRequest): string {
  return req.url.split('?')[0];
}

export async function crearServidor(modo: Modo) {
  const { contrato, cerrar } = await crearContrato(modo);
  const acceso = await crearGestorAcceso(modo);
  const dist = join(import.meta.dirname, '..', 'dist');
  const { fuentes, publicas } = fuentesAcceso(dist);

  const app = Fastify({ logger: { level: 'warn' }, bodyLimit: 4096 });
  app.addHook('onClose', async () => cerrar());

  const enviarAcceso = (reply: FastifyReply, codigo: number, aviso: AvisoAcceso, destino: string) =>
    reply.code(codigo)
      .header('content-security-policy', CSP_ACCESO)
      .header('cache-control', 'no-store')
      .type('text/html; charset=utf-8')
      .send(paginaAcceso({ aviso, destino, modo, fuentes }));

  // Solo peticiones dirigidas a la máquina local (defensa frente a DNS rebinding).
  app.addHook('onRequest', async (req, reply) => {
    const host = (req.headers.host ?? '').replace(/:\d+$/, '');
    if (host !== '127.0.0.1' && host !== 'localhost') return reply.code(403).send({ error: 'HOST_NO_LOCAL' });
  });
  // Solo lectura: GET/HEAD; POST únicamente en /api/login y /api/logout, y solo desde el mismo origen.
  app.addHook('onRequest', async (req, reply) => {
    if (req.method === 'GET' || req.method === 'HEAD') return;
    if (req.method !== 'POST' || !POST_PERMITIDOS.has(ruta(req))) return reply.code(405).send({ error: 'SOLO_LECTURA' });
    const origen = req.headers.origin;
    if (origen !== undefined && origen !== `http://${req.headers.host}`) return reply.code(403).send({ error: 'ORIGEN_NO_PERMITIDO' });
    const sitio = req.headers['sec-fetch-site'];
    if (sitio !== undefined && sitio !== 'same-origin' && sitio !== 'none') return reply.code(403).send({ error: 'ORIGEN_NO_PERMITIDO' });
  });
  // Cabeceras comunes. Referrer-Policy same-origin (no no-referrer: con él Chrome envía Origin: null en los
  // POST de formulario y la comprobación de origen los rechazaría).
  app.addHook('onRequest', async (_req, reply) => {
    reply.header('x-frame-options', 'DENY').header('referrer-policy', 'same-origin').header('x-content-type-options', 'nosniff');
  });
  // Sesión obligatoria salvo login, logout y las fuentes de la pantalla de acceso.
  app.addHook('onRequest', async (req, reply) => {
    const r = ruta(req);
    if (req.method === 'POST') return; // login/logout (el hook anterior ya filtró)
    if (publicas.has(r)) return;
    if (acceso.sesionValida(tokenDeCookie(req.headers.cookie))) return;
    if (r.startsWith('/api/') || r.startsWith('/assets/')) {
      return reply.code(401).header('cache-control', 'no-store').send({ error: 'NO_AUTENTICADO' });
    }
    return enviarAcceso(reply, 401, null, destinoSeguro(r));
  });

  app.addContentTypeParser('application/x-www-form-urlencoded', { parseAs: 'string' }, (_req, cuerpo, hecho) => {
    hecho(null, Object.fromEntries(new URLSearchParams(cuerpo as string)));
  });

  app.post<{ Body: Record<string, string> | undefined }>('/api/login', async (req, reply) => {
    const b = req.body && typeof req.body === 'object' ? req.body : {};
    const destino = destinoSeguro(b.destino);
    const r = await acceso.entrar(typeof b.usuario === 'string' ? b.usuario : '', typeof b.clave === 'string' ? b.clave : '');
    if (r.tipo === 'ok') return reply.code(303).header('set-cookie', cookieSesion(r.token)).header('cache-control', 'no-store').redirect(destino, 303);
    return enviarAcceso(reply, r.tipo === 'bloqueado' ? 429 : 401, r.tipo, destino);
  });
  app.post('/api/logout', async (req, reply) => {
    acceso.salir(tokenDeCookie(req.headers.cookie));
    return reply.header('set-cookie', cookieBorrada()).header('cache-control', 'no-store').redirect('/', 303);
  });

  app.get('/api/estado', async () => ({ modo, farmacia: FARMACIA, solo_lectura: true, usuario: USUARIO }));
  app.get('/api/inicio', () => contrato.inicio());
  app.get('/api/facturas', () => contrato.facturas());
  app.get<{ Params: { id: string } }>('/api/facturas/:id', async (req, reply) => {
    if (!UUID_RE.test(req.params.id)) return reply.code(400).send({ error: 'ID_NO_VALIDO' });
    const dto = await contrato.facturaDetalle(req.params.id.toLowerCase());
    if (dto === null) return reply.code(404).send({ error: 'FACTURA_NO_ENCONTRADA' });
    return dto;
  });
  app.get('/api/conciliacion', () => contrato.conciliacionBandeja());
  app.get('/api/vencimientos', () => contrato.vencimientos());
  app.get('/api/cashflow', () => contrato.cashflowSemanas());
  app.get('/api/proveedores', () => contrato.proveedores());
  app.get('/api/configuracion', () => contrato.configuracion());

  // Errores: mensaje genérico al cliente; nunca filas ni datos de conexión.
  app.setErrorHandler((err, _req, reply) => {
    app.log.error({ msg: (err instanceof Error ? err.message : String(err)).split('\n')[0] });
    const codigo = (err as { statusCode?: number }).statusCode;
    if (codigo !== undefined && codigo >= 400 && codigo < 500) return reply.code(codigo).send({ error: 'PETICION_NO_VALIDA' });
    reply.code(500).send({ error: 'ERROR_INTERNO' });
  });

  if (existsSync(dist)) {
    await app.register(fastifyStatic, { root: dist, wildcard: false });
    app.setNotFoundHandler((req, reply) => {
      if (req.url.startsWith('/api/')) return reply.code(404).send({ error: 'NO_ENCONTRADO' });
      return reply.sendFile('index.html');
    });
  }
  return app;
}

if (import.meta.main) {
  const modo = leerModo();
  const puerto = leerPuerto(modo);
  const app = await crearServidor(modo);
  await app.listen({ host: HOST, port: puerto });
  console.log(`ControlFarmacias web · modo ${modo} · http://${HOST}:${puerto}`);
}
