// H7: pantalla Cashflow (solo FIXTURES; REAL simulado con 503). Vistas decenas / mes y PIO / RITA / consolidado,
// desglose de la fuente, avisos, «Media / Excel» guardado solo en el navegador y móvil 390 sin desbordar.
import { expect, test, type Page } from '@playwright/test';
import { join } from 'node:path';
import { entrar } from './sesion.ts';

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'h7');

async function sinDesbordar(page: Page, ancho: number) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(ancho);
}
const celda = (page: Page, clave: string) => page.locator(`[data-cf-celda="${clave}"]`);
const saldo = (page: Page, columna: string) => page.locator(`[data-cf-saldo="${columna}"] .cf-num`);

test.describe('PC 1440', () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  test.beforeEach(async ({ page }) => {
    await entrar(page, '/cashflow');
    await page.evaluate(() => { try { localStorage.removeItem('cf.cashflow.eleccion.v1'); } catch { /* nada */ } });
    await page.reload();
    await expect(page.locator('[data-contrato-ok="cashflow"]')).toBeVisible();
  });

  test('decenas, consolidado: cabecera, 3 pasadas + 9 próximas, avisos naranja, rojo y gris, gráfico con la línea en 0', async ({ page }) => {
    await expect(page.locator('[data-cf-cuenta="CONSOLIDADO"]')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('[data-cf-escala="decenas"]')).toHaveAttribute('aria-pressed', 'true');
    const cols = page.locator('[data-cf-columna]');
    await expect(cols).toHaveCount(12);
    await expect(cols.first()).toHaveAttribute('data-cf-columna', '2026-10-11');
    await expect(cols.last()).toHaveAttribute('data-cf-columna', '2027-02-01');
    await expect(page.locator('[data-cf-columna="2026-11-01"]')).toHaveAttribute('data-cf-tipo', 'real');
    await expect(page.locator('[data-cf-columna="2026-11-11"]')).toHaveAttribute('data-cf-tipo', 'previsto');
    // Cabecera: saldo actual por cuenta, próximo aviso y última importación.
    await expect(page.locator('[data-cf-saldo-actual="PIO"] .cf-ficha-cifra')).toHaveText('9.000,00 €');
    await expect(page.locator('[data-cf-saldo-actual="RITA"] .cf-ficha-cifra')).toHaveText('2.000,00 €');
    await expect(page.locator('[data-cf-saldo-actual="CONSOLIDADO"] .cf-ficha-cifra')).toHaveText('11.000,00 €');
    await expect(page.locator('[data-cf-proximo-aviso]')).toHaveAttribute('data-cf-proximo-aviso', 'naranja');
    await expect(page.locator('[data-cf-proximo-aviso]')).toContainText('11–20 dic 2026');
    await expect(page.locator('[data-cf-importacion]')).toContainText('hace 6 días');
    // Avisos.
    await expect(page.locator('[data-cf-aviso="gris"]')).toHaveText('La importación vigente del Excel tiene 6 días.');
    const naranja = page.locator('[data-cf-aviso="naranja"]');
    await expect(naranja).toHaveCount(1);
    await expect(naranja).toContainText('RITA en negativo');
    await expect(naranja).toContainText('PIO la cubre');
    await expect(naranja).toContainText('Devolución prevista: 21–31 dic 2026');
    const rojo = page.locator('[data-cf-aviso="rojo"]');
    await expect(rojo).toHaveCount(1);
    await expect(rojo).toContainText('Consolidado en negativo (11–20 ene 2027)');
    // Gráfico: tres series, marcas de los avisos y línea en 0.
    const g = page.locator('[data-cf-grafico]');
    await expect(g.locator('[data-cf-serie]')).toHaveCount(3);
    await expect(g.locator('[data-cf-marca="naranja"][data-columna="2026-12-11"]')).toHaveCount(1);
    await expect(g.locator('[data-cf-marca="rojo"][data-columna="2027-01-11"]')).toHaveCount(1);
    await expect(g.locator('.cf-cero')).toHaveCount(1);
    // Consolidado: traspasos neutros; saldo negativo en rojo.
    await expect(page.locator('[data-cf-traspasos-neutros]')).toBeVisible();
    await expect(page.locator('[data-cf-saldo="2027-01-11"]')).toHaveClass(/negativo/);
    // Pasar el ratón por una decena: tooltip con los tres saldos.
    await g.locator('.cf-zona-foco').nth(9).hover();
    await expect(page.locator('[data-cf-tooltip]')).toContainText('11–20 ene 2027');
    await expect(page.locator('[data-cf-tooltip]')).toContainText('Consolidado en negativo');
    await page.mouse.move(0, 0);
    await sinDesbordar(page, 1440);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_decenas_consolidado.png'), fullPage: true });
  });

  test('mes: 3 pasados + 9 próximos; RITA con su paga de diciembre; tabla plegable a concepto', async ({ page }) => {
    await page.locator('[data-cf-escala="mes"]').click();
    await page.locator('[data-cf-cuenta="RITA"]').click();
    await expect(page).toHaveURL(/escala=mes/);
    await expect(page).toHaveURL(/cuenta=RITA/);
    const cols = page.locator('[data-cf-columna]');
    await expect(cols).toHaveCount(12);
    await expect(cols.first()).toHaveAttribute('data-cf-columna', '2026-08');
    await expect(page.locator('[data-cf-columna="2026-11"]')).toHaveAttribute('data-cf-tipo', 'mixto');
    await expect(page.locator('[data-cf-columna="2026-12"]')).toHaveAttribute('data-cf-tipo', 'previsto');
    // RITA nunca tiene vencimientos del sistema.
    await expect(page.locator('[data-cf-fuente="vencimientos"]')).toHaveCount(0);
    await expect(page.locator('[data-cf-concepto]')).toHaveCount(0);
    await page.locator('[data-cf-plegar="RS Personal"]').click();
    await expect(page.locator('[data-cf-plegar="RS Personal"]')).toHaveAttribute('aria-expanded', 'true');
    await expect(celda(page, 'RS Personal|Paga extra|2026-12')).toContainText('−7.000');
    await expect(page.locator('[data-cf-tabla="RITA"] [data-cf-seccion="traspasos"]')).toBeVisible();
    await sinDesbordar(page, 1440);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_mes_rita.png'), fullPage: true });
    // Consolidado por meses (captura del informe).
    await page.locator('[data-cf-cuenta="CONSOLIDADO"]').click();
    await expect(page.locator('[data-cf-tabla="CONSOLIDADO"]')).toBeVisible();
    // En «Mes» las marcas van al saldo de la peor decena (enero cierra en positivo, pero el 11–20 falta saldo).
    await expect(page.locator('[data-cf-marca="rojo"][data-columna="2027-01"]')).toHaveAttribute('data-decena', '2027-01-11');
    await expect(page.locator('[data-cf-marca="naranja"][data-columna="2026-12"]')).toHaveAttribute('data-decena', '2026-12-11');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_mes_consolidado.png'), fullPage: true });
  });

  test('desglose: vencimientos con enlace a la factura y «posible duplicado o diferencia»; media con su cálculo', async ({ page }) => {
    await page.locator('[data-cf-cuenta="PIO"]').click();
    await page.locator('[data-cf-plegar="RS Proveedores"]').click();
    const alliance = celda(page, 'RS Proveedores|ALLIANCE|2026-11-11');
    await expect(alliance).toHaveAttribute('data-cf-fuente', 'vencimientos');
    await expect(alliance.locator('[data-cf-diferencia]')).toBeVisible();
    await expect(alliance).toContainText('−472');
    await alliance.locator('button').click();
    const d = page.locator('[data-cf-desglose]');
    await expect(d).toBeVisible();
    await expect(d.locator('[data-cf-desglose-fuente="VENCIMIENTOS"]')).toBeVisible();
    await expect(d.locator('[data-cf-comparacion="diferencia"]')).toContainText('Posible duplicado o diferencia');
    await expect(d.locator('[data-cf-comparacion="diferencia"]')).toContainText('Excel: −520,00 €');
    await expect(d.locator('[data-cf-venc="90000000-0000-4000-8000-000000000002"]')).toContainText('472,22');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_desglose_vencimientos.png') });
    // Enlace a la factura.
    await d.locator('[data-cf-venc="90000000-0000-4000-8000-000000000002"] a').click();
    await expect(page).toHaveURL('/facturas/f0000000-0000-4000-8000-000000000002');
    await page.goBack();
    await expect(page).toHaveURL(/\/cashflow/);
    await expect(page.locator('[data-contrato-ok="cashflow"]')).toBeVisible();
    await expect(d).toHaveCount(0); // seguir el enlace cierra el desglose
    // Media de TPV: las 6 decenas y la media.
    const tpv = celda(page, 'RE Cobro TPV|*|2026-11-11');
    await expect(tpv).toHaveAttribute('data-cf-fuente', 'media');
    await expect(tpv.locator('[data-cf-alt]')).toHaveText('Excel 9.900');
    await tpv.locator('button').click();
    await expect(d.locator('[data-cf-media] li')).toHaveCount(7);
    await expect(d.locator('.cf-media-total')).toContainText('10.000,00 €');
    await expect(d.locator('[data-cf-no-suma]')).toBeVisible(); // la línea del Excel, a la vista sin sumar
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_desglose_media.png') });
    await page.keyboard.press('Escape');
    await expect(d).toHaveCount(0);
  });

  test('«Media / Excel»: cambia el saldo y se guarda solo en el navegador', async ({ page }) => {
    await page.locator('[data-cf-cuenta="PIO"]').click();
    await expect(saldo(page, '2026-11-11')).toHaveText('11.828');
    const sel = page.locator('[data-cf-eleccion="RE Cobro TPV"]');
    await sel.locator('[data-opcion="excel"]').click();
    await expect(sel.locator('[data-opcion="excel"]')).toHaveAttribute('aria-pressed', 'true');
    await expect(saldo(page, '2026-11-11')).toHaveText('11.728');
    await expect(celda(page, 'RE Cobro TPV|*|2026-11-11').locator('[data-cf-alt]')).toHaveText('Media 10.000');
    await page.reload();
    await expect(page.locator('[data-cf-eleccion="RE Cobro TPV"] [data-opcion="excel"]')).toHaveAttribute('aria-pressed', 'true');
    await expect(saldo(page, '2026-11-11')).toHaveText('11.728');
    // Sin almacenamiento disponible: la pantalla funciona con «Media».
    await page.addInitScript(() => { Object.defineProperty(window, 'localStorage', { get() { throw new Error('bloqueado'); } }); });
    await page.reload();
    await expect(saldo(page, '2026-11-11')).toHaveText('11.828');
  });

  test('avisos y gráfico (captura)', async ({ page }) => {
    await page.evaluate(() => document.fonts.ready);
    await page.locator('#cf-avisos').screenshot({ path: join(CAPTURAS, 'pc1440_avisos.png') });
    await page.locator('[data-cf-grafico]').screenshot({ path: join(CAPTURAS, 'pc1440_grafico.png') });
  });
});

test.describe('Móvil 390', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test('sin desbordar la página: la tabla se desplaza dentro de su marco', async ({ page }) => {
    await entrar(page, '/cashflow');
    await expect(page.locator('[data-contrato-ok="cashflow"]')).toBeVisible();
    await sinDesbordar(page, 390);
    const marco = await page.locator('.cf-tabla-marco').boundingBox();
    expect(marco && marco.x >= 0 && marco.x + marco.width <= 390).toBe(true);
    const g = await page.locator('[data-cf-grafico] svg').boundingBox();
    expect(g && g.x >= 0 && g.x + g.width <= 390).toBe(true);
    await page.locator('[data-cf-escala="mes"]').click();
    await sinDesbordar(page, 390);
    await page.locator('[data-cf-escala="decenas"]').click();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_cashflow.png'), fullPage: true });
    // Desglose en móvil: ocupa el ancho sin desbordar.
    await page.locator('[data-cf-saldo-actual]').first().scrollIntoViewIfNeeded();
    await page.locator('[data-cf-celda^="RS Proveedores|*|2026-11-11"] button').click();
    await expect(page.locator('[data-cf-desglose]')).toBeVisible();
    await sinDesbordar(page, 390);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_desglose.png') });
  });
});

test.describe('REAL simulado', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('tablas pendientes: pantalla visible con «Pendiente de tablas en Supabase» (503) y sin cifras', async ({ page }) => {
    await page.route('**/api/cashflow', (r) => r.fulfill({ status: 503, json: { error: 'H7_PENDIENTE', mensaje: 'Pendiente de tablas en Supabase' } }));
    await entrar(page, '/cashflow');
    const p = page.locator('[data-cf-pendiente]');
    await expect(p).toBeVisible();
    await expect(p.getByRole('heading')).toHaveText('Pendiente de tablas en Supabase');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Cashflow');
    await expect(page.locator('[data-cf-tabla]')).toHaveCount(0);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_real_pendiente.png') });
  });
});
