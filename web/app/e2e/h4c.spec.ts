// H4c: vencimientos en el detalle de factura (importe pendiente, total factura como referencia aparte y sentido
// no documentado). Solo FIXTURES (playwright.config.ts lo exige).
import { expect, test, type Page } from '@playwright/test';
import { join } from 'node:path';
import { entrar } from './sesion.ts';

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'h4c');
const F = (n: number) => `f0000000-0000-4000-8000-0000000000${String(n).padStart(2, '0')}`;

test.beforeEach(async ({ page }) => entrar(page));

async function abrirDetalle(page: Page, id: string) {
  const estado = await (await page.request.get('/api/estado')).json();
  expect(estado.modo).toBe('FIXTURES');
  await page.goto(`/facturas/${id}`);
  await expect(page.locator('[data-contrato-ok="facturaDetalle"]')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

test.describe('Detalle de factura PC 1440', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('F04: vencimiento sin importe = "importe pendiente" y total factura como referencia separada', async ({ page }) => {
    await abrirDetalle(page, F(4));
    const filas = page.locator('[data-vencimiento]');
    await expect(filas).toHaveCount(3);
    await expect(filas.nth(0)).toContainText('400,00 €');
    await expect(filas.nth(0).locator('[data-total-factura]')).toHaveCount(0);
    const pendiente = filas.nth(2);
    await expect(pendiente.locator('[data-importe-pendiente]')).toHaveText('importe pendiente');
    await expect(pendiente.locator('[data-total-factura]')).toHaveText('total factura: 568,05 € (referencia)');
    // El total no ocupa el lugar del importe: el importe sigue siendo "importe pendiente".
    await expect(pendiente).not.toContainText('desconocido');
    await expect(pendiente).not.toContainText('0,00 €');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_detalle_vencimiento_pendiente.png'), fullPage: true });
  });

  test('F05: tipo de documento no documentado → "sentido no documentado"', async ({ page }) => {
    await abrirDetalle(page, F(5));
    const v = page.locator('[data-vencimiento]');
    await expect(v).toHaveCount(1);
    await expect(v.locator('[data-sentido="NO_DOCUMENTADO"]')).toHaveText('sentido no documentado');
    await expect(v).toContainText('288,00 €');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_detalle_sentido_no_documentado.png'), fullPage: true });
  });

  test('F07: abono documentado', async ({ page }) => {
    await abrirDetalle(page, F(7));
    await expect(page.locator('[data-vencimiento] [data-sentido="ABONO"]')).toHaveText('abono');
  });

  // H4c-2: regla de Pío (solo el tipo documental).
  test('F08 FACTURA_DUPLICADO → cargo; F03 rectificativa y F06 OTRO → sentido no documentado', async ({ page }) => {
    await abrirDetalle(page, F(8));
    await expect(page.locator('[data-vencimiento] [data-sentido="CARGO"]')).toHaveText('cargo');
    for (const n of [3, 6]) {
      await abrirDetalle(page, F(n));
      await expect(page.locator('[data-vencimiento] [data-sentido="NO_DOCUMENTADO"]')).toHaveText('sentido no documentado');
    }
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_detalle_tipo_otro.png'), fullPage: true });
  });
});

test.describe('Detalle de factura móvil 390', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test('F04 sin desbordamiento horizontal y captura', async ({ page }) => {
    await abrirDetalle(page, F(4));
    await expect(page.locator('[data-total-factura]')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_detalle_vencimiento_pendiente.png'), fullPage: true });
  });
});
