// H3b: arranque, navegación del menú a las 8 rutas y capturas PC 1440 / móvil 390. Solo FIXTURES.
import { expect, test, type Page } from '@playwright/test';
import { join } from 'node:path';
import { entrar } from './sesion.ts';

// H4b: todas las rutas exigen sesión.
test.beforeEach(async ({ page }) => entrar(page));

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'h3b');
const MENU = [
  { texto: 'Inicio', ruta: '/', titulo: 'Resumen del día', bloque: 'inicio' },
  { texto: 'Facturas', ruta: '/facturas', titulo: 'Facturas', bloque: 'facturas' },
  { texto: 'Conciliación', ruta: '/conciliacion', titulo: 'Conciliación', bloque: 'conciliacionBandeja' },
  { texto: 'Vencimientos', ruta: '/vencimientos', titulo: 'Vencimientos', bloque: 'vencimientos' },
  { texto: 'Cashflow', ruta: '/cashflow', titulo: 'Cashflow', bloque: 'cashflowSemanas' },
  { texto: 'Proveedores', ruta: '/proveedores', titulo: 'Proveedores', bloque: 'proveedores' },
  { texto: 'Configuración', ruta: '/configuracion', titulo: 'Configuración', bloque: 'configuracion' },
];

async function comprobarFixtures(page: Page) {
  const estado = await (await page.request.get('/api/estado')).json();
  expect(estado.modo).toBe('FIXTURES');
  await expect(page.locator('.pie')).toContainText('Datos ficticios');
}

test.describe('PC 1440', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('el menú navega a las 8 rutas', async ({ page }) => {
    await page.goto('/');
    await comprobarFixtures(page);
    const menu = page.getByRole('navigation', { name: 'Menú principal' });
    for (const m of MENU) {
      await menu.getByRole('link', { name: m.texto, exact: true }).click();
      await expect(page).toHaveURL(m.ruta);
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(m.titulo);
      // Inicio está construida desde H4 (e2e/h4.spec.ts).
      if (m.ruta !== '/') await expect(page.getByText('En construcción')).toBeVisible();
      await expect(page.locator(`[data-contrato-ok="${m.bloque}"]`)).toBeVisible();
      await expect(menu.getByRole('link', { name: m.texto, exact: true })).toHaveClass(/activo/);
    }
    // 8.ª ruta: /facturas/:id desde Facturas.
    await menu.getByRole('link', { name: 'Facturas', exact: true }).click();
    await page.getByRole('navigation', { name: 'Acceso provisional al detalle' }).getByRole('link').first().click();
    await expect(page).toHaveURL(/\/facturas\/[0-9a-f-]{36}$/);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(/^Factura /);
    await expect(page.locator('[data-contrato-ok="facturaDetalle"]')).toBeVisible();
    // "Próximamente" en gris, no navegable.
    await expect(menu.getByText('Próximamente')).toHaveCount(5);
    await expect(menu.getByRole('link', { name: /Compras|Stock|Ventas|Clientes|Trabajadores/ })).toHaveCount(0);
  });

  test('cero recursos externos y Figtree local', async ({ page }) => {
    const externas: string[] = [];
    page.on('request', (r) => {
      const u = new URL(r.url());
      if (u.hostname !== '127.0.0.1') externas.push(r.url());
    });
    const fuentes: string[] = [];
    page.on('response', (r) => { if (/\.woff2?$/.test(new URL(r.url()).pathname)) fuentes.push(r.url()); });
    await page.goto('/');
    await expect(page.locator('[data-contrato-ok]')).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    expect(await page.evaluate(() => document.fonts.check('800 28px Figtree'))).toBe(true);
    expect(fuentes.length).toBeGreaterThan(0);
    expect(externas).toEqual([]);
  });

  test('capturas PC', async ({ page }) => {
    // Captura de Inicio: desde H4 en docs/capturas/h4 (e2e/h4.spec.ts).
    for (const [ruta, nombre] of [['/facturas', 'facturas']]) {
      await page.goto(ruta);
      await comprobarFixtures(page);
      await expect(page.locator('[data-contrato-ok]')).toBeVisible();
      await page.screenshot({ path: join(CAPTURAS, `pc1440_${nombre}.png`), fullPage: true });
    }
  });
});

test.describe('Móvil 390', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test('capturas móvil y menú plegable', async ({ page }) => {
    // Captura de Inicio: desde H4 en docs/capturas/h4 (e2e/h4.spec.ts).
    for (const [ruta, nombre] of [['/facturas', 'facturas']]) {
      await page.goto(ruta);
      await expect(page.locator('[data-contrato-ok]')).toBeVisible();
      const anchoPagina = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(anchoPagina).toBeLessThanOrEqual(390);
      await page.screenshot({ path: join(CAPTURAS, `movil390_${nombre}.png`), fullPage: true });
    }
    await page.getByRole('button', { name: 'Menú' }).click();
    await comprobarFixtures(page);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_menu_abierto.png'), fullPage: true });
    await page.getByRole('navigation', { name: 'Menú principal' }).getByRole('link', { name: 'Cashflow', exact: true }).click();
    await expect(page).toHaveURL('/cashflow');
    await expect(page.getByRole('button', { name: 'Menú' })).toHaveAttribute('aria-expanded', 'false');
  });
});
