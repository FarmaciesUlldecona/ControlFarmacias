// H4b: pruebas del acceso con contraseña, del servidor (inyección, modo FIXTURES) y de set-password con un
// fichero temporal que no se llama .env* (nunca se invoca el script npm). Uso: npm run test:unit
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { after, describe, test } from 'node:test';
import {
  BLOQUEO_MS, CLAVE_FIXTURES, MAX_FALLOS, USUARIO, cookieSesion, crearAcceso, crearHash, destinoSeguro, leerHash,
  tokenDeCookie, verificarClave,
} from '../acceso.ts';
import { VARIABLE, ejecutar, fijarHashEnTexto } from '../fijar_clave.ts';
import { crearServidor, leerPuerto } from '../index.ts';

describe('hash scrypt', () => {
  test('formato, verificación y rechazo', async () => {
    const h = await crearHash('una clave larga');
    assert.match(h, /^scrypt:32768:8:1:[A-Za-z0-9_-]{22}:[A-Za-z0-9_-]{86}$/);
    assert.ok(!h.includes('una clave larga'));
    assert.equal(await verificarClave('una clave larga', leerHash(h)), true);
    assert.equal(await verificarClave('una clave largA', leerHash(h)), false);
    assert.notEqual(await crearHash('una clave larga'), h); // sal aleatoria
  });
  test('hash no válido: falla cerrado', () => {
    for (const malo of [undefined, '', 'texto', 'scrypt:1024:8:1:AAAAAAAAAAAAAAAAAAAAAA:' + 'A'.repeat(86), 'bcrypt:1:2:3:4:5']) {
      assert.throws(() => leerHash(malo), /HASH_ACCESO_NO_VALIDO/);
    }
  });
});

describe('sesiones y bloqueo', () => {
  test('5 fallos → bloqueo 5 min, también con la clave correcta; luego vuelve a dejar entrar', async () => {
    let t = 1_000_000;
    const a = crearAcceso(leerHash(await crearHash('correcta-123')), () => t);
    for (let i = 1; i < MAX_FALLOS; i++) assert.deepEqual(await a.entrar(USUARIO, 'mala'), { tipo: 'error' });
    assert.deepEqual(await a.entrar(USUARIO, 'mala'), { tipo: 'bloqueado' });
    assert.deepEqual(await a.entrar(USUARIO, 'correcta-123'), { tipo: 'bloqueado' });
    t += BLOQUEO_MS - 1;
    assert.deepEqual(await a.entrar(USUARIO, 'correcta-123'), { tipo: 'bloqueado' });
    t += 1;
    const r = await a.entrar(USUARIO, 'correcta-123');
    assert.equal(r.tipo, 'ok');
    assert.equal(a.sesionValida(r.tipo === 'ok' ? r.token : null), true);
  });
  test('usuario distinto de Pío: error genérico', async () => {
    const a = crearAcceso(leerHash(await crearHash('correcta-123')));
    assert.deepEqual(await a.entrar('Otro', 'correcta-123'), { tipo: 'error' });
  });
  test('salir invalida la sesión; tokens ajenos no valen', async () => {
    const a = crearAcceso(leerHash(await crearHash('correcta-123')));
    const r = await a.entrar(USUARIO, 'correcta-123');
    assert.equal(r.tipo, 'ok');
    const token = r.tipo === 'ok' ? r.token : '';
    assert.equal(a.sesionValida('x'.repeat(43)), false);
    assert.equal(a.sesionValida(null), false);
    a.salir(token);
    assert.equal(a.sesionValida(token), false);
  });
  test('cookie: HttpOnly, SameSite=Strict, sin caducidad; lectura y destino seguro', () => {
    const c = cookieSesion('abc');
    assert.match(c, /HttpOnly/);
    assert.match(c, /SameSite=Strict/);
    assert.doesNotMatch(c, /Expires|Max-Age/i);
    assert.equal(tokenDeCookie('a=1; cf_sesion=tok; b=2'), 'tok');
    assert.equal(tokenDeCookie(undefined), null);
    for (const [v, e] of [['/facturas', '/facturas'], ['//evil.com', '/'], ['/api/inicio', '/'], ['http://x', '/'], ['/a/../b', '/'], [3, '/']] as const) {
      assert.equal(destinoSeguro(v), e);
    }
  });
});

describe('servidor FIXTURES (inyección)', async () => {
  const app = await crearServidor('FIXTURES');
  after(() => app.close());
  const H = { host: '127.0.0.1:4747' };
  const entrar = (clave: string, extra: Record<string, string> = {}) => app.inject({
    method: 'POST', url: '/api/login', headers: { ...H, 'content-type': 'application/x-www-form-urlencoded', ...extra },
    payload: new URLSearchParams({ usuario: USUARIO, clave, destino: '/facturas' }).toString(),
  });

  test('sin sesión ninguna ruta es accesible: pantalla de acceso o 401', async () => {
    for (const url of ['/', '/facturas', '/facturas/f0000000-0000-4000-8000-000000000001', '/conciliacion', '/index.html', '/no-existe']) {
      const r = await app.inject({ method: 'GET', url, headers: H });
      assert.equal(r.statusCode, 401, url);
      assert.match(r.body, /<form method="post" action="\/api\/login"/, url);
      assert.doesNotMatch(r.body, /id="root"/, url);
    }
    for (const url of ['/api/estado', '/api/inicio', '/api/facturas', '/api/proveedores', '/api/configuracion', '/api/x', '/assets/index.js']) {
      const r = await app.inject({ method: 'GET', url, headers: H });
      assert.equal(r.statusCode, 401, url);
      assert.deepEqual(r.json(), { error: 'NO_AUTENTICADO' }, url);
    }
  });
  test('POST solo en login/logout; otros métodos y rutas, 405', async () => {
    for (const [method, url] of [['POST', '/api/inicio'], ['PUT', '/api/login'], ['DELETE', '/api/logout'], ['PATCH', '/']] as const) {
      assert.equal((await app.inject({ method, url, headers: H })).statusCode, 405, `${method} ${url}`);
    }
  });
  test('origen ajeno en POST: 403', async () => {
    assert.equal((await entrar(CLAVE_FIXTURES, { origin: 'http://evil.example' })).statusCode, 403);
    assert.equal((await entrar(CLAVE_FIXTURES, { 'sec-fetch-site': 'cross-site' })).statusCode, 403);
  });
  test('entrar, usar la API y salir', async () => {
    const r = await entrar(CLAVE_FIXTURES);
    assert.equal(r.statusCode, 303);
    assert.equal(r.headers.location, '/facturas');
    const setCookie = String(r.headers['set-cookie']);
    assert.match(setCookie, /^cf_sesion=[A-Za-z0-9_-]{43}; Path=\/; HttpOnly; SameSite=Strict$/);
    const cookie = setCookie.split(';')[0];
    const est = await app.inject({ method: 'GET', url: '/api/estado', headers: { ...H, cookie } });
    assert.equal(est.statusCode, 200);
    assert.equal(est.json().modo, 'FIXTURES');
    const s = await app.inject({ method: 'POST', url: '/api/logout', headers: { ...H, cookie } });
    assert.equal(s.statusCode, 303);
    assert.match(String(s.headers['set-cookie']), /Max-Age=0/);
    assert.equal((await app.inject({ method: 'GET', url: '/api/estado', headers: { ...H, cookie } })).statusCode, 401);
  });
  test('contraseña errónea: 401 con mensaje genérico; 5 fallos bloquean (429) incluso con la correcta', async () => {
    const r = await entrar('mala');
    assert.equal(r.statusCode, 401);
    assert.match(r.body, /No se ha podido entrar\. Revisa la contraseña\./);
    for (let i = 2; i < MAX_FALLOS; i++) assert.equal((await entrar('mala')).statusCode, 401);
    assert.equal((await entrar('mala')).statusCode, 429);
    const b = await entrar(CLAVE_FIXTURES);
    assert.equal(b.statusCode, 429);
    assert.match(b.body, /Acceso bloqueado/);
    assert.equal(b.headers['set-cookie'], undefined);
  });
  test('puerto fijo 4747; CF_PUERTO solo en FIXTURES', () => {
    const previo = process.env.CF_PUERTO;
    try {
      delete process.env.CF_PUERTO;
      assert.equal(leerPuerto('REAL'), 4747);
      process.env.CF_PUERTO = '5181';
      assert.equal(leerPuerto('FIXTURES'), 5181);
      assert.throws(() => leerPuerto('REAL'), /CF_PUERTO_NO_PERMITIDO_EN_REAL/);
    } finally {
      if (previo === undefined) delete process.env.CF_PUERTO; else process.env.CF_PUERTO = previo;
    }
  });
});

describe('set-password (fichero temporal, sin el script npm)', () => {
  const dir = mkdtempSync(join(tmpdir(), 'cf-h4b-'));
  after(() => rmSync(dir, { recursive: true, force: true }));
  const preguntas = (...r: string[]) => async () => r.shift() as string;

  test('fijarHashEnTexto: sustituye sin tocar otras líneas, conserva CRLF y quita duplicadas', async () => {
    const h = await crearHash('clave-de-prueba');
    const previo = 'A=1\r\nCF_WEB_PASSWORD_HASH=viejo\r\n# comentario\r\nCF_WEB_PASSWORD_HASH=otro\r\nB=2\r\n';
    assert.equal(fijarHashEnTexto(previo, h), `A=1\r\n${VARIABLE}=${h}\r\n# comentario\r\nB=2\r\n`);
    assert.equal(fijarHashEnTexto('A=1', h), `A=1\n${VARIABLE}=${h}\n`);
    assert.equal(fijarHashEnTexto('', h), `${VARIABLE}=${h}\n`);
    assert.throws(() => fijarHashEnTexto('', 'no-es-hash'), /HASH_ACCESO_NO_VALIDO/);
  });
  test('ejecutar: crea, luego sustituye; nunca escribe la contraseña', async () => {
    const ruta = join(dir, 'config_prueba.txt');
    assert.equal(await ejecutar(ruta, preguntas('primera-clave-1', 'primera-clave-1')), 'creada');
    writeFileSync(ruta, `CF_LECTURA_USER=cf_lectura\n${readFileSync(ruta, 'utf8')}OTRA=x\n`);
    assert.equal(await ejecutar(ruta, preguntas('segunda-clave-2', 'segunda-clave-2')), 'sustituida');
    const t = readFileSync(ruta, 'utf8');
    const lineas = t.trimEnd().split('\n');
    assert.equal(lineas.length, 3);
    assert.equal(lineas[0], 'CF_LECTURA_USER=cf_lectura');
    assert.equal(lineas[2], 'OTRA=x');
    assert.ok(!t.includes('primera-clave-1') && !t.includes('segunda-clave-2'));
    const h = leerHash(lineas[1].slice(VARIABLE.length + 1));
    assert.equal(await verificarClave('segunda-clave-2', h), true);
  });
  test('ejecutar: claves distintas o cortas no cambian nada', async () => {
    const ruta = join(dir, 'config_prueba2.txt');
    writeFileSync(ruta, 'A=1\n');
    await assert.rejects(ejecutar(ruta, preguntas('clave-larga-1', 'clave-larga-2')), /CLAVES_DISTINTAS/);
    await assert.rejects(ejecutar(ruta, preguntas('corta', 'corta')), /CLAVE_CORTA/);
    assert.equal(readFileSync(ruta, 'utf8'), 'A=1\n');
  });
});
