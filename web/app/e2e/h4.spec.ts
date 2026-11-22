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
      'con-defecto': '2', 'sin-automatizar': '4', incidencias: '13',
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

  test('próximos vencimientos: 5, "x de N" e importe pendiente (H4c)', async ({ page }) => {
    await abrirInicio(page);
    const filas = page.locator('[data-vencimiento]');
    await expect(filas).toHaveCount(5);
    // H6-3: CF-2026-55811 tiene 4 vencimientos (el 4.º, negativo «a cuenta» del 31/10, ya pasado: no sale aquí).
    await expect(filas.nth(3)).toContainText('2 de 4');
    await expect(filas.nth(4)).toContainText('3 de 4');
    await expect(filas.nth(4)).toContainText('importe pendiente');
    await expect(filas.nth(4)).not.toContainText('desconocido');
    await expect(filas.nth(4)).not.toContainText('0,00 €');
    await expect(filas.first()).toContainText('04/11/2026');
  });

  test('necesita tu atención: incidencias con enlace; alertas (duplicado regla B) solo como recuento → Conciliación', async ({ page }) => {
    await abrirInicio(page);
    const at = page.locator('#atencion');
    // H4d: agrupado; primero "Diferencia con albaranes" (rojo).
    await expect(at.locator('[data-grupo]').first()).toHaveAttribute('data-grupo', 'DIFERENCIA_ALBARANES');
    await expect(at.locator('[data-grupo]').first()).toHaveClass(/borde-rojo/);
    const dif = at.locator('[data-grupo="DIFERENCIA_ALBARANES"]');
    await dif.locator('summary').click();
    await expect(dif).toContainText('Diferencia según el motor: 41,90 €');
    // H8: las alertas de albaranes ya no están en «Necesita tu atención»; su detalle completo, en Conciliación → Albaranes.
    await expect(at.locator('[data-grupo="DUPLICADO_FARMATIC"], [data-grupo="ALBARAN_NO_EN_FARMATIC"]')).toHaveCount(0);
    await page.locator('[data-alertas-inicio]').getByRole('link', { name: 'Ver en Conciliación' }).click();
    await expect(page).toHaveURL(/\/conciliacion\?pestana=albaranes$/);
    const dup = page.locator('[data-alerta="POSIBLE_DUPLICADO_FARMATIC"]');
    await expect(dup).toHaveCount(1);
    await expect(dup).toContainText('08C66676');
    await dup.locator('[data-alerta-detalle] summary').click();
    await expect(dup.locator('[data-alerta-detalle]')).toContainText('importe_puc: 57.4');
    await expect(page.locator('#alertas')).not.toContainText('08C70015');
    // Enlace a destino: el albarán fuera de Farmatic abre su factura.
    await page.locator('[data-alerta="ALBARAN_FACTURADO_NO_EN_FARMATIC"]').getByRole('link', { name: /^Abrir/ }).click();
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
