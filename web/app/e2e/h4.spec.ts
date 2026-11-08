// H4: pantalla Inicio sobre el contrato `inicio`. Solo FIXTURES (playwright.config.ts lo exige).
import { expect, test, type Page } from '@playwright/test';
import { join } from 'node:path';
import { entrar } from './sesion.ts';

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'h4');

// H4b: todas las rutas exigen sesión.
test.beforeEach(async ({ page }) => entrar(page));

async function abrirInicio(page: Page) {
  const estado = await (await page.request.get('/api/estado')).json();
  expect(estado.modo).toBe('FIXTURES');
  await page.goto('/');
  await expect(page.locator('[data-contrato-ok="inicio"]')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

test.describe('Inicio PC 1440', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('contadores sin importes', async ({ page }) => {
    await abrirInicio(page);
    const esperado: Record<string, string> = {
      conciliadas: '3', 'pendientes-conciliar': '4', 'requieren-revision': '2', 'pendientes-procesar': '1',
      'con-defecto': '2', 'sin-automatizar': '4', incidencias: '6',
    };
    for (const [clave, n] of Object.entries(esperado)) await expect(page.locator(`[data-contador="${clave}"]`)).toHaveText(n);
    await expect(page.locator('.contadores')).toContainText('2 bloqueantes');
    await expect(page.locator('.contadores')).not.toContainText('€');
    await expect(page.locator('.contador.c-rojo').filter({ hasText: 'Con defecto' })).toHaveCount(1);
    await expect(page.locator('.contador.c-gris').filter({ hasText: 'Sin automatizar' })).toHaveCount(1);
  });

  test('cobertura en euros con importes conocidos y facturas sin importe excluidas', async ({ page }) => {
    await abrirInicio(page);
    const c = page.locator('.cobertura');
    await expect(c.locator('[data-cobertura-pct]')).toHaveText('60,8 %');
    await expect(c).toContainText('1.192,64 €');
    await expect(c).toContainText('1.962,86 €');
    await expect(c).toContainText('1 factura sin importe conocido, excluida');
    await expect(c).toContainText('sin datos bancarios');
  });

  test('próximos vencimientos: 5, "x de N" e importe desconocido', async ({ page }) => {
    await abrirInicio(page);
    const filas = page.locator('[data-vencimiento]');
    await expect(filas).toHaveCount(5);
    await expect(filas.nth(3)).toContainText('2 de 3');
    await expect(filas.nth(4)).toContainText('3 de 3');
    await expect(filas.nth(4)).toContainText('desconocido');
    await expect(filas.nth(4)).not.toContainText('0,00 €');
    await expect(filas.first()).toContainText('04/11/2026');
  });

  test('necesita tu atención: alertas (duplicado regla B) e incidencias con enlace', async ({ page }) => {
    await abrirInicio(page);
    const at = page.locator('#atencion');
    // Rojos primero; los 8 primeros visibles y el resto tras "Mostrar N avisos más".
    await expect(at.locator('.aviso')).toHaveCount(8);
    await expect(at.locator('.aviso').first()).toHaveClass(/borde-rojo/);
    await at.getByRole('button', { name: /Mostrar \d+ avisos más/ }).click();
    const dup = at.locator('[data-aviso="Duplicado en Farmatic"]');
    await expect(dup).toHaveCount(1);
    await expect(dup).toContainText('08C66676');
    await expect(dup).toContainText('57,40 €');
    await expect(at).not.toContainText('08C70015');
    await expect(at.locator('[data-aviso="Incidencia bloqueante"]')).toHaveCount(2);
    await expect(at).toContainText('El total de la factura no tiene evidencia legible en el documento.');
    await expect(at).toContainText('Diferencia según el motor: 41,90 €');
    // Enlace a destino: el aviso de albarán fuera de Farmatic abre su factura.
    await at.locator('[data-aviso="Fuera de Farmatic"]').getByRole('link', { name: /^Abrir/ }).click();
    await expect(page).toHaveURL(/\/facturas\/f0000000-0000-4000-8000-000000000001$/);
  });

  test('botones: Sincronizar deshabilitado, Actualizar relee; sin bloque de sincronización', async ({ page }) => {
    await abrirInicio(page);
    await expect(page.getByRole('button', { name: 'Sincronizar ahora' })).toBeDisabled();
    await expect(page.getByText('Última sincronización')).toHaveCount(0);
    await expect(page.locator('[data-lectura]')).toHaveText(/^Última lectura \d{2}:\d{2}:\d{2}$/);
    const peticion = page.waitForRequest((r) => new URL(r.url()).pathname === '/api/inicio');
    await page.getByRole('button', { name: 'Actualizar' }).click();
    await peticion;
    await expect(page.locator('[data-lectura]')).toHaveText(/^Última lectura /);
    await expect(page.locator('[data-contador="conciliadas"]')).toHaveText('3');
  });

  test('captura PC', async ({ page }) => {
    await abrirInicio(page);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_inicio.png'), fullPage: true });
  });
});

test.describe('Inicio móvil 390', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test('sin desbordamiento horizontal y captura', async ({ page }) => {
    await abrirInicio(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_inicio.png'), fullPage: true });
  });
});
