// H6-REAL-2: rótulo de modo en el pie del lateral. Solo FIXTURES (playwright.config.ts lo exige); el modo REAL se
// simula interceptando /api/estado: nunca se arranca ni se lee el modo REAL.
import { expect, test, type Page } from '@playwright/test';
import { join } from 'node:path';
import { entrar } from './sesion.ts';

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'h6_real_2');

test.beforeEach(async ({ page }) => entrar(page));
test.use({ viewport: { width: 1440, height: 900 } });

async function simularReal(page: Page, escritura: string[] | undefined) {
  const json: Record<string, unknown> = { modo: 'REAL', farmacia: 'PIO', solo_lectura: true, usuario: 'Pío' };
  if (escritura !== undefined) json.escritura = escritura;
  await page.route('**/api/estado', (r) => r.fulfill({ json }));
  await page.goto('/configuracion');
  await expect(page.locator('[data-rotulo-real]')).toBeVisible();
}

/** Sin usuarios completos ni datos de conexión; tampoco el rótulo antiguo «solo lectura». */
async function sinDatosSensibles(page: Page) {
  const pie = page.locator('.pie');
  await expect(pie).not.toContainText('solo lectura');
  await expect(pie).not.toContainText('cf_lectura.');
  for (const t of ['cf_trabajadores_web', 'cf_pagos_web', 'supabase', 'pooler', '5432', '6543', 'postgres']) {
    await expect(pie).not.toContainText(t, { ignoreCase: true });
  }
}

test('FIXTURES sin cambios: «Fase 1 · solo lectura» y «Datos ficticios»; sin rótulo de REAL', async ({ page }) => {
  const estado = await (await page.request.get('/api/estado')).json();
  expect(estado.modo).toBe('FIXTURES');
  expect(estado.escritura).toEqual([]);
  await page.goto('/configuracion');
  const pie = page.locator('.pie');
  await expect(pie).toContainText('Fase 1 · solo lectura');
  await expect(pie).toContainText('Datos ficticios');
  await expect(page.locator('[data-rotulo-real]')).toHaveCount(0);
});

test.describe('REAL simulado (intercepción de /api/estado)', () => {
  test('con credencial de pagos: «escritura: Trabajadores, Pagos»', async ({ page }) => {
    await simularReal(page, ['Trabajadores', 'Pagos']);
    await expect(page.locator('[data-rotulo-real]')).toHaveText('Datos reales · lectura cf_lectura' + 'escritura: Trabajadores, Pagos');
    await expect(page.locator('[data-rotulo-escritura]')).toHaveText('escritura: Trabajadores, Pagos');
    await sinDatosSensibles(page);
    await page.evaluate(() => document.fonts.ready);
    await page.locator('.lateral').screenshot({ path: join(CAPTURAS, 'pc1440_lateral_real_con_pagos.png') });
  });

  test('sin credencial de pagos: Pagos no aparece («escritura: Trabajadores»)', async ({ page }) => {
    await simularReal(page, ['Trabajadores']);
    await expect(page.locator('[data-rotulo-escritura]')).toHaveText('escritura: Trabajadores');
    await expect(page.locator('.pie')).not.toContainText('Pagos');
    await sinDatosSensibles(page);
    await page.evaluate(() => document.fonts.ready);
    await page.locator('.lateral').screenshot({ path: join(CAPTURAS, 'pc1440_lateral_real_sin_pagos.png') });
  });

  test('1440×900: la línea «escritura: …» se ve sin desplazar; el pie no tapa el menú', async ({ page }) => {
    await simularReal(page, ['Trabajadores', 'Pagos']);
    await page.evaluate(() => document.fonts.ready);
    await expect(page.locator('[data-rotulo-escritura]')).toBeInViewport({ ratio: 1 });
    await expect(page.locator('.pie .boton-salir')).toBeInViewport({ ratio: 1 });
    const menu = await page.locator('#menu-principal').boundingBox();
    const pie = await page.locator('.pie').boundingBox();
    expect(menu && pie && menu.y + menu.height <= pie.y + 0.5).toBe(true);
    // A 900 px cabe el menú entero: la última opción se ve sin desplazar el menú.
    const ultima = page.getByRole('navigation', { name: 'Menú principal' }).getByRole('link', { name: 'Configuración', exact: true });
    await expect(ultima).toBeInViewport({ ratio: 1 });
    expect(await page.locator('#menu-principal').evaluate((m) => m.scrollTop)).toBe(0);
    expect(await page.locator('#menu-principal').evaluate((m) => m.scrollHeight <= m.clientHeight)).toBe(true);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440x900_pie_visible.png') });
  });

  test('pantalla baja (1440×700): el menú se desplaza por dentro; el pie sigue visible y la última opción se alcanza', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 700 });
    await simularReal(page, ['Trabajadores', 'Pagos']);
    await expect(page.locator('[data-rotulo-escritura]')).toBeInViewport({ ratio: 1 });
    const desborda = await page.locator('#menu-principal').evaluate((m) => m.scrollHeight > m.clientHeight);
    expect(desborda).toBe(true);
    const ultima = page.getByRole('navigation', { name: 'Menú principal' }).getByRole('link', { name: 'Configuración', exact: true });
    await ultima.scrollIntoViewIfNeeded();
    await expect(ultima).toBeInViewport({ ratio: 1 });
    await expect(page.locator('[data-rotulo-escritura]')).toBeInViewport({ ratio: 1 });
  });

  test('sin ninguna credencial de escritura (o estado sin el campo): «escritura: ninguna»', async ({ page }) => {
    await simularReal(page, []);
    await expect(page.locator('[data-rotulo-escritura]')).toHaveText('escritura: ninguna');
    await page.unrouteAll();
    await simularReal(page, undefined);
    await expect(page.locator('[data-rotulo-escritura]')).toHaveText('escritura: ninguna');
    await sinDatosSensibles(page);
  });
});
