// H4b: acceso con contraseña, Salir, cookie de sesión, rutas sin sesión, bloqueo, lateral en páginas largas
// e Inicio sin incidencias INFO. Solo FIXTURES (playwright.config.ts lo exige).
import { expect, test, type Page } from '@playwright/test';
import { join } from 'node:path';
import { CLAVE_FIXTURES, entrar } from './sesion.ts';

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'h4b');
/** Servidor FIXTURES aparte para el bloqueo (playwright.config.ts). */
const BASE_BLOQUEO = 'http://127.0.0.1:5182';

const RUTAS = ['/', '/facturas', '/conciliacion', '/vencimientos', '/cashflow', '/proveedores', '/configuracion',
  '/facturas/f0000000-0000-4000-8000-000000000001', '/index.html', '/no-existe'];
const API = ['/api/estado', '/api/inicio', '/api/facturas', '/api/facturas/f0000000-0000-4000-8000-000000000001',
  '/api/conciliacion', '/api/vencimientos', '/api/cashflow', '/api/proveedores', '/api/configuracion'];

async function intentar(page: Page, clave: string) {
  await page.getByLabel('Contraseña').fill(clave);
  await page.getByRole('button', { name: 'Entrar' }).click();
}

test.describe('Acceso PC 1440', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('ninguna ruta ni API accesible sin sesión', async ({ page }) => {
    for (const r of RUTAS) {
      const resp = await page.request.get(r);
      expect(resp.status(), r).toBe(401);
      const html = await resp.text();
      expect(html, r).toContain('action="/api/login"');
      expect(html, r).not.toContain('id="root"');
    }
    for (const r of API) {
      const resp = await page.request.get(r);
      expect(resp.status(), r).toBe(401);
      expect(await resp.json(), r).toEqual({ error: 'NO_AUTENTICADO' });
    }
    // Solo POST en login/logout.
    expect((await page.request.post('/api/inicio')).status()).toBe(405);
    // La pantalla de acceso no carga el front ni llama a la API.
    const llamadas: string[] = [];
    page.on('request', (q) => { const p = new URL(q.url()).pathname; if (p.startsWith('/api/') || p.endsWith('.js')) llamadas.push(p); });
    await page.goto('/facturas');
    await expect(page.getByRole('heading', { name: 'Entrar' })).toBeVisible();
    expect(llamadas).toEqual([]);
  });

  test('pantalla de acceso y acceso correcto al destino pedido', async ({ page }) => {
    await page.goto('/facturas');
    await expect(page.getByRole('heading', { name: 'Entrar' })).toBeVisible();
    await expect(page.getByLabel('Usuario')).toHaveValue('Pío');
    await page.evaluate(() => document.fonts.ready);
    expect(await page.evaluate(() => document.fonts.check('800 24px Figtree'))).toBe(true);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_acceso.png'), fullPage: true });
    await intentar(page, CLAVE_FIXTURES);
    await expect(page).toHaveURL('/facturas');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Facturas');
    await expect(page.locator('.pie')).toContainText('Sesión de Pío');
  });

  test('contraseña errónea: mensaje genérico, sin sesión', async ({ page, context }) => {
    await page.goto('/');
    await intentar(page, 'no-es-la-clave');
    const aviso = page.locator('[data-aviso-acceso="error"]');
    await expect(aviso).toHaveText('No se ha podido entrar. Revisa la contraseña.');
    await expect(page.getByRole('heading', { name: 'Entrar' })).toBeVisible();
    expect((await context.cookies()).filter((c) => c.name === 'cf_sesion')).toEqual([]);
    expect((await page.request.get('/api/estado')).status()).toBe(401);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_acceso_error.png'), fullPage: true });
  });

  test('cookie de sesión: HttpOnly, SameSite=Strict, sin caducidad', async ({ page, context }) => {
    await entrar(page);
    const c = (await context.cookies()).filter((x) => x.name === 'cf_sesion');
    expect(c).toHaveLength(1);
    expect(c[0].expires).toBe(-1); // cookie de sesión: muere al cerrar el navegador
    expect(c[0].httpOnly).toBe(true);
    expect(c[0].sameSite).toBe('Strict');
    expect(c[0].path).toBe('/');
    expect(await page.evaluate(() => document.cookie)).not.toContain('cf_sesion');
  });

  test('Salir cierra la sesión y vuelve a la pantalla de acceso', async ({ page, context }) => {
    await entrar(page, '/vencimientos');
    await page.getByRole('button', { name: 'Salir' }).click();
    await expect(page.getByRole('heading', { name: 'Entrar' })).toBeVisible();
    expect((await context.cookies()).filter((c) => c.name === 'cf_sesion')).toEqual([]);
    expect((await page.request.get('/api/inicio')).status()).toBe(401);
    await page.goto('/vencimientos');
    await expect(page.getByRole('heading', { name: 'Entrar' })).toBeVisible();
  });

  test('lateral: fondo y borde de altura completa en una página larga', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 640 });
    await entrar(page);
    await expect(page.locator('[data-contrato-ok="inicio"]')).toBeVisible();
    // H4d: todos los grupos desplegados para que la página sea larga.
    for (const s of await page.locator('#atencion summary').all()) await s.click();
    const medidas = await page.evaluate(() => ({
      documento: document.documentElement.scrollHeight,
      lateral: (document.querySelector('.lateral') as HTMLElement).getBoundingClientRect().height,
    }));
    expect(medidas.documento).toBeGreaterThan(640 * 2);
    expect(medidas.lateral).toBeGreaterThanOrEqual(medidas.documento - 1);
    // El menú sigue a la vista al desplazarse.
    await page.mouse.wheel(0, 5000);
    await expect(page.getByRole('navigation', { name: 'Menú principal' }).getByRole('link', { name: 'Inicio', exact: true })).toBeInViewport();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_inicio_largo.png'), fullPage: true });
  });

  test('Inicio: incidencias INFO fuera de "Necesita tu atención"; textos llanos por código', async ({ page }) => {
    await entrar(page);
    const at = page.locator('#atencion');
    for (const s of await at.locator('summary').all()) await s.click();
    await expect(at).not.toContainText('MONEDA_NO_DOCUMENTADA');
    await expect(at).not.toContainText('moneda');
    await expect(at).toContainText('Puede que esta factura esté repetida en otro PDF');
    await expect(at).toContainText('Un vencimiento de la factura no indica su importe');
    await expect(page.locator('[data-contador="incidencias"]')).toHaveText('13');
    // La INFO sigue en el detalle (contrato) de su factura.
    const det = await (await page.request.get('/api/facturas/f0000000-0000-4000-8000-000000000002')).json();
    expect(det.incidencias.map((i: { codigo: string }) => i.codigo)).toContain('MONEDA_NO_DOCUMENTADA');
  });
});

test.describe('Acceso móvil 390', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test('pantalla de acceso sin desbordamiento y Salir en el menú', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Entrar' })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_acceso.png'), fullPage: true });
    await intentar(page, CLAVE_FIXTURES);
    await page.getByRole('button', { name: 'Menú' }).click();
    await expect(page.getByRole('button', { name: 'Salir' })).toBeVisible();
    await page.screenshot({ path: join(CAPTURAS, 'movil390_menu_salir.png'), fullPage: true });
    await page.getByRole('button', { name: 'Salir' }).click();
    await expect(page.getByRole('heading', { name: 'Entrar' })).toBeVisible();
  });
});

test.describe('Bloqueo (servidor FIXTURES aparte)', () => {
  test.use({ viewport: { width: 1440, height: 900 }, baseURL: BASE_BLOQUEO });

  test('5 intentos fallidos bloquean 5 minutos, también con la contraseña correcta', async ({ page, context }) => {
    await page.goto('/');
    for (let i = 1; i <= 4; i++) {
      await intentar(page, `mala-${i}`);
      await expect(page.locator('[data-aviso-acceso="error"]')).toBeVisible();
    }
    await intentar(page, 'mala-5');
    const aviso = page.locator('[data-aviso-acceso="bloqueado"]');
    await expect(aviso).toContainText('Acceso bloqueado durante unos minutos');
    await intentar(page, CLAVE_FIXTURES);
    await expect(aviso).toBeVisible();
    expect((await context.cookies()).filter((c) => c.name === 'cf_sesion')).toEqual([]);
    expect((await page.request.get('/api/estado')).status()).toBe(401);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_acceso_bloqueado.png'), fullPage: true });
  });
});
