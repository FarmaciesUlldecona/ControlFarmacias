/**
 * Acceso con contraseña (H4b). Usuario único: Pío. Solo 127.0.0.1.
 *
 *  - Hash scrypt en CF_WEB_PASSWORD_HASH (modo REAL: web/app/.env.web; lo escribe `npm run set-password`).
 *    Formato: scrypt:<N>:<r>:<p>:<sal base64url>:<hash base64url>. Nunca contraseña en claro.
 *  - Modo FIXTURES: contraseña ficticia fija (CLAVE_FIXTURES), hash generado al arrancar. No sirve en REAL.
 *  - Sesión en memoria del servidor (se pierde al reiniciarlo). Cookie HttpOnly, SameSite=Strict, Path=/,
 *    sin Expires ni Max-Age: muere al cerrar el navegador.
 *  - 5 intentos fallidos seguidos → bloqueo de 5 minutos (también para la contraseña correcta).
 *  - Mensajes de error genéricos.
 *
 * Solo sintaxis TypeScript borrable (Node la ejecuta sin compilar).
 */
import { createHash, randomBytes, scrypt, timingSafeEqual, type ScryptOptions } from 'node:crypto';

export const USUARIO = 'Pío';
export const COOKIE_SESION = 'cf_sesion';
/** Contraseña ficticia del modo FIXTURES (documentada en CONFIG.md). Nunca válida en modo REAL. */
export const CLAVE_FIXTURES = 'fixtures-ficticia';
export const MAX_FALLOS = 5;
export const BLOQUEO_MS = 5 * 60 * 1000;
/** Longitud mínima de la contraseña al fijarla (set-password). */
export const LONGITUD_MINIMA = 10;
const MAX_SESIONES = 20;

const PARAMS = { N: 2 ** 15, r: 8, p: 1, sal: 16, largo: 64 } as const;

function b64url(b: Buffer): string {
  return b.toString('base64url');
}

function derivar(clave: string, sal: Buffer, N: number, r: number, p: number, largo: number): Promise<Buffer> {
  const opciones: ScryptOptions = { N, r, p, maxmem: 256 * N * r };
  return new Promise((ok, mal) => scrypt(clave.normalize('NFC'), sal, largo, opciones, (e, k) => (e ? mal(e) : ok(k))));
}

/** Crea el hash scrypt de una contraseña (sal aleatoria). */
export async function crearHash(clave: string): Promise<string> {
  const sal = randomBytes(PARAMS.sal);
  const k = await derivar(clave, sal, PARAMS.N, PARAMS.r, PARAMS.p, PARAMS.largo);
  return ['scrypt', PARAMS.N, PARAMS.r, PARAMS.p, b64url(sal), b64url(k)].join(':');
}

export interface HashScrypt { N: number; r: number; p: number; sal: Buffer; hash: Buffer }

/** Interpreta el hash; falla cerrado ante cualquier formato o parámetro fuera de rango. */
export function leerHash(texto: string | undefined): HashScrypt {
  const partes = (texto ?? '').trim().split(':');
  if (partes.length !== 6 || partes[0] !== 'scrypt') throw new Error('HASH_ACCESO_NO_VALIDO');
  const [N, r, p] = partes.slice(1, 4).map((x) => (/^[0-9]{1,8}$/.test(x) ? Number(x) : NaN));
  const b64 = /^[A-Za-z0-9_-]+$/;
  if (!b64.test(partes[4]) || !b64.test(partes[5])) throw new Error('HASH_ACCESO_NO_VALIDO');
  const sal = Buffer.from(partes[4], 'base64url');
  const hash = Buffer.from(partes[5], 'base64url');
  const potencia = Number.isInteger(N) && N >= 2 ** 14 && N <= 2 ** 20 && (N & (N - 1)) === 0;
  if (!potencia || !(r >= 8 && r <= 32) || !(p >= 1 && p <= 4) || sal.length < 16 || hash.length < 32) {
    throw new Error('HASH_ACCESO_NO_VALIDO');
  }
  return { N, r, p, sal, hash };
}

/** Comprueba la contraseña contra el hash en tiempo constante. */
export async function verificarClave(clave: string, h: HashScrypt): Promise<boolean> {
  const k = await derivar(clave, h.sal, h.N, h.r, h.p, h.hash.length);
  return timingSafeEqual(k, h.hash);
}

export type ResultadoEntrada =
  | { tipo: 'ok'; token: string }
  | { tipo: 'error' }
  | { tipo: 'bloqueado' };

export interface Acceso {
  /** Intento de entrada. Cuenta los fallos y aplica el bloqueo. */
  entrar(usuario: string, clave: string): Promise<ResultadoEntrada>;
  /** true si la cookie corresponde a una sesión viva. */
  sesionValida(token: string | null): boolean;
  salir(token: string | null): void;
  bloqueado(): boolean;
}

function huella(token: string): string {
  return createHash('sha256').update(token).digest('hex');
}

/** Gestor de acceso: un hash, sesiones en memoria y bloqueo por intentos. `ahora` es inyectable para pruebas. */
export function crearAcceso(hash: HashScrypt, ahora: () => number = Date.now): Acceso {
  const sesiones = new Map<string, number>(); // huella(token) → creada
  let fallos = 0;
  let bloqueadoHasta = 0;
  const bloqueado = () => ahora() < bloqueadoHasta;
  return {
    async entrar(usuario, clave) {
      if (bloqueado()) return { tipo: 'bloqueado' };
      // Siempre se deriva (aunque el usuario no sea Pío) para no distinguir casos por tiempo.
      const okClave = await verificarClave(clave.slice(0, 1024), hash);
      if (bloqueado()) return { tipo: 'bloqueado' };
      if (!okClave || usuario.trim() !== USUARIO) {
        fallos += 1;
        if (fallos >= MAX_FALLOS) { fallos = 0; bloqueadoHasta = ahora() + BLOQUEO_MS; return { tipo: 'bloqueado' }; }
        return { tipo: 'error' };
      }
      fallos = 0;
      const token = randomBytes(32).toString('base64url');
      sesiones.set(huella(token), ahora());
      while (sesiones.size > MAX_SESIONES) sesiones.delete(sesiones.keys().next().value as string);
      return { tipo: 'ok', token };
    },
    sesionValida(token) {
      return token !== null && /^[A-Za-z0-9_-]{43}$/.test(token) && sesiones.has(huella(token));
    },
    salir(token) {
      if (token !== null) sesiones.delete(huella(token));
    },
    bloqueado,
  };
}

/** Valor de la cookie de sesión en la cabecera Cookie (o null). */
export function tokenDeCookie(cabecera: string | undefined): string | null {
  for (const parte of (cabecera ?? '').split(';')) {
    const i = parte.indexOf('=');
    if (i > 0 && parte.slice(0, i).trim() === COOKIE_SESION) return parte.slice(i + 1).trim();
  }
  return null;
}

/** Cookie de sesión: sin Expires ni Max-Age (cookie de sesión del navegador). */
export function cookieSesion(token: string): string {
  return `${COOKIE_SESION}=${token}; Path=/; HttpOnly; SameSite=Strict`;
}
export function cookieBorrada(): string {
  return `${COOKIE_SESION}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0`;
}

/** Destino tras entrar: solo rutas locales de la web (nunca /api ni otro origen). */
export function destinoSeguro(v: unknown): string {
  if (typeof v !== 'string' || v.length > 300) return '/';
  if (!/^\/(?!\/)[A-Za-z0-9/_\-.%]*$/.test(v) || v.startsWith('/api') || v.includes('..')) return '/';
  return v;
}

// ---------------------------------------------------------------------------
// Pantalla de acceso (HTML autónomo: no carga el front ni la API)
// ---------------------------------------------------------------------------

function escapar(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string);
}

export type AvisoAcceso = null | 'error' | 'bloqueado';

/** Fuentes Figtree empaquetadas: peso → ruta pública (/assets/…woff2). */
export type FuentesAcceso = Partial<Record<400 | 600 | 800, string>>;

export const CSP_ACCESO = "default-src 'none'; style-src 'unsafe-inline'; font-src 'self'; img-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'";

export function paginaAcceso(opciones: { aviso: AvisoAcceso; destino: string; modo: string; fuentes: FuentesAcceso }): string {
  const { aviso, destino, modo, fuentes } = opciones;
  const caras = Object.entries(fuentes)
    .map(([peso, ruta]) => `@font-face{font-family:'Figtree';font-style:normal;font-weight:${peso};font-display:swap;src:url('${escapar(ruta as string)}') format('woff2')}`)
    .join('');
  const mensaje = aviso === 'bloqueado'
    ? 'Acceso bloqueado durante unos minutos por demasiados intentos. Espera y vuelve a intentarlo.'
    : aviso === 'error' ? 'No se ha podido entrar. Revisa la contraseña.' : null;
  return `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="robots" content="noindex">
<title>Entrar · ControlFarmacias</title>
<style>
${caras}
:root{--texto:#18211e;--tenue:#56625d;--fondo:#f4f5f2;--superficie:#fff;--borde:#e2e5e0;--primario:#1d3b47;--primario-fondo:#e6edef;--rojo-fondo:#fbe4e2;--rojo-texto:#a8221a;--naranja-fondo:#fbebd9;--naranja-texto:#8f4500;--gris-fondo:#eceeeb;color-scheme:light}
*{box-sizing:border-box}
html,body{margin:0}
body{min-height:100vh;display:grid;place-items:center;padding:24px 16px;font-family:'Figtree',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:var(--texto);background:var(--fondo);-webkit-font-smoothing:antialiased}
main{width:100%;max-width:400px}
.marca{display:flex;align-items:center;gap:12px;margin:0 0 20px 4px;font-weight:800;font-size:19px;letter-spacing:-0.01em}
.logo{width:40px;height:40px;border-radius:10px;background:var(--primario);color:#fff;display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:800}
.tarjeta{background:var(--superficie);border:1px solid var(--borde);border-top:4px solid var(--primario);border-radius:12px;padding:26px 24px 24px;display:flex;flex-direction:column;gap:18px}
h1{margin:0;font-size:24px;font-weight:800;letter-spacing:-0.02em}
.placa{display:flex;justify-content:space-between;align-items:baseline;gap:12px;padding:10px 12px;border:1px solid var(--borde);border-radius:10px;font-size:14px}
.placa strong{font-size:15px}
.tenue{color:var(--tenue)}
form{display:flex;flex-direction:column;gap:14px}
label{display:flex;flex-direction:column;gap:6px;font-size:14px;font-weight:600}
input{font:inherit;font-size:16px;min-height:46px;padding:0 12px;border:1px solid #c9d0cb;border-radius:8px;background:var(--superficie);color:var(--texto)}
input[readonly]{background:var(--gris-fondo);color:var(--tenue)}
input:focus-visible,button:focus-visible{outline:2px solid #2f6fd0;outline-offset:2px}
button{font:inherit;font-size:16px;font-weight:700;min-height:46px;border:0;border-radius:8px;background:var(--primario);color:#fff;cursor:pointer}
button:hover{background:#163039}
.aviso{margin:0;padding:10px 12px;border-radius:8px;font-size:14px;font-weight:600}
.aviso.error{background:var(--rojo-fondo);color:var(--rojo-texto)}
.aviso.bloqueado{background:var(--naranja-fondo);color:var(--naranja-texto)}
.pie{margin:14px 4px 0;font-size:12px}
</style>
</head>
<body>
<main>
<div class="marca"><span class="logo" aria-hidden="true">CF</span>ControlFarmacias</div>
<section class="tarjeta" aria-labelledby="t-acceso">
<h1 id="t-acceso">Entrar</h1>
<div class="placa"><span class="tenue">Farmacia</span><strong>PIO</strong></div>
${mensaje ? `<p class="aviso ${aviso}" role="alert" data-aviso-acceso="${aviso}">${mensaje}</p>` : ''}
<form method="post" action="/api/login" autocomplete="on">
<input type="hidden" name="destino" value="${escapar(destino)}">
<label>Usuario<input name="usuario" value="${escapar(USUARIO)}" readonly autocomplete="username"></label>
<label>Contraseña<input name="clave" type="password" required autofocus autocomplete="current-password" maxlength="1024"></label>
<button type="submit">Entrar</button>
</form>
</section>
<p class="pie tenue">Solo lectura y solo en este equipo.${modo === 'FIXTURES' ? ' Datos ficticios.' : ''}</p>
</main>
</body>
</html>`;
}
