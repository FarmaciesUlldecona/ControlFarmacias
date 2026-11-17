// H6-4: Vencimientos en calendario (Día / Semana / Mes / Año) sobre la lista; desplegable con los pagos del día (cursor,
// teclado o toque); clic en día, semana o mes filtra la lista; lista con pestañas, filtros y orden de Facturas.
// Solo FIXTURES (playwright.config.ts lo exige). Referencia de FIXTURES: lunes 16/11/2026.
import { expect, test, type Page } from '@playwright/test';
import { join } from 'node:path';
import { entrar } from './sesion.ts';

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'h6');
const filas = (page: Page) => page.locator('tr[data-vencimiento]');
const dia = (page: Page, f: string) => page.locator(`[data-dia="${f}"]`);

test.describe('Calendario PC 1440', () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  test.beforeEach(async ({ page }) => entrar(page, '/vencimientos'));

  test('Mes por defecto (noviembre de 2026): total y globo por día, color = peor estado; sin tarjetas por semana ni mes', async ({ page }) => {
    const cal = page.locator('[data-calendario-vencimientos]');
    await expect(cal).toHaveAttribute('data-vista-cal', 'mes');
    await expect(page.locator('[data-vista="mes"]')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('[data-periodo-cal]')).toHaveText('Noviembre de 2026');
    // 6 semanas de lunes a domingo (del 26/10 al 06/12).
    await expect(cal.locator('[data-semana]')).toHaveCount(6);
    await expect(dia(page, '2026-11-04').locator('[data-importe-dia]')).toHaveAttribute('data-importe-dia', '304,74 €');
    await expect(dia(page, '2026-11-04').locator('[data-globo]')).toHaveText('2');
    const colores: [string, string][] = [
      ['2026-11-04', 'rojo'], ['2026-11-15', 'domiciliado'], ['2026-10-29', 'azul'], ['2026-11-21', 'neutro'], ['2026-11-07', 'verde'], ['2026-11-05', 'ninguno'],
    ];
    for (const [f, c] of colores) await expect(dia(page, f)).toHaveAttribute('data-color-dia', c);
    // 21/11: abono aún no vencido (pendiente): −45,30 €; 07/11: pagado pero de sentido no documentado: no suma.
    await expect(dia(page, '2026-11-21').locator('[data-importe-dia]')).toHaveAttribute('data-importe-dia', '-45,30 €');
    // H6-5: sin total, la celda dice por qué (antes «—» y «1 fuera»).
    await expect(dia(page, '2026-11-07').locator('[data-importe-dia]')).toHaveAttribute('data-sin-total', 'sentido no documentado');
    await expect(dia(page, '2026-11-16')).toHaveClass(/hoy/);
    await expect(page.locator('.ve-periodo, [data-totales]')).toHaveCount(0);
    await expect(page.locator('[data-total-general]')).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_calendario_mes.png'), fullPage: false });
  });

  test('desplegable con varios pagos el mismo día (cursor): proveedor comercial, importe, estado y suma; accesible con teclado', async ({ page }) => {
    await dia(page, '2026-11-04').hover();
    const des = page.locator('[data-desplegable="2026-11-04"]');
    await expect(des).toBeVisible();
    await expect(des).toHaveAttribute('role', 'tooltip');
    await expect(dia(page, '2026-11-04')).toHaveAttribute('aria-describedby', 'vc-desplegable-2026-11-04');
    await expect(des.locator('[data-pago]')).toHaveCount(2);
    await expect(des.locator('.vc-pago-proveedor')).toHaveText(['ALLIANCE', 'ALLIANCE']);
    await expect(des.locator('.vc-pago-importe')).toHaveText(['152,37 €', '152,37 €']);
    await expect(des.locator('[data-estado-pago]')).toHaveText(['Vencido sin pagar', 'Vencido sin pagar']);
    await expect(des.locator('[data-suma-dia]')).toHaveText('Total304,74 €');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_calendario_desplegable.png'), fullPage: false });
    // Lo que no suma se cuenta aparte en el desplegable.
    await dia(page, '2026-11-14').hover();
    await expect(page.locator('[data-desplegable="2026-11-04"]')).toHaveCount(0);
    await expect(page.locator('[data-desplegable="2026-11-14"] [data-fuera-total]')).toHaveText('Fuera del total: 1 de sentido no documentado');
    await page.mouse.move(5, 5);
    await expect(page.locator('[data-desplegable]')).toHaveCount(0);
    // Teclado: una sola parada de tabulación en la rejilla (hoy); foco = desplegable; flechas mueven; Escape cierra.
    await expect(page.locator('.vc-mes [data-dia][tabindex="0"]')).toHaveCount(1);
    await expect(dia(page, '2026-11-16')).toHaveAttribute('tabindex', '0');
    await dia(page, '2026-11-11').focus();
    await expect(page.locator('[data-desplegable="2026-11-11"]')).toBeVisible();
    await page.keyboard.press('ArrowUp'); // 04/11
    await expect(dia(page, '2026-11-04')).toBeFocused();
    await expect(page.locator('[data-desplegable="2026-11-04"] [data-pago]')).toHaveCount(2);
    await expect(page.locator('[data-desplegable="2026-11-11"]')).toHaveCount(0);
    await page.keyboard.press('Escape');
    await expect(page.locator('[data-desplegable]')).toHaveCount(0);
    await expect(dia(page, '2026-11-04')).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/cal=dia%3A2026-11-04/);
    await expect(filas(page)).toHaveCount(2);
  });

  test('clic en día, semana y mes filtra la lista: filtro visible, en la URL y quitable; segundo clic lo quita', async ({ page }) => {
    await dia(page, '2026-11-04').click();
    const chip = page.locator('[data-filtro-calendario]');
    await expect(chip).toHaveText(/Calendario: Miércoles, 4 de noviembre de 2026/);
    await expect(page).toHaveURL(/cal=dia%3A2026-11-04/);
    await expect(filas(page)).toHaveCount(2);
    await expect(dia(page, '2026-11-04')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('[data-total-general] [data-total="por_pagar"] .ve-cifra-n')).toHaveText('304,74 €');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_calendario_filtro_dia.png'), fullPage: false });
    // Semana: del 2 al 8 de noviembre (04 ×2 y 07).
    await page.locator('[data-semana="2026-11-02"]').click();
    await expect(chip).toHaveText(/Semana 45 · 2–8 nov 2026/);
    await expect(filas(page)).toHaveCount(3);
    // Segundo clic sobre la misma semana: quita el filtro.
    await page.locator('[data-semana="2026-11-02"]').click();
    await expect(chip).toHaveCount(0);
    await expect(filas(page)).toHaveCount(12);
    // Mes: botón «Ver este mes en la lista».
    await page.locator('[data-mostrar-periodo]').click();
    await expect(chip).toHaveText(/Calendario: Noviembre de 2026/);
    await expect(filas(page)).toHaveCount(9);
    // El filtro se combina con los demás y «Quitar» lo borra (los demás siguen).
    await page.locator('select[name="estado"]').selectOption('VENCIDO_SIN_PAGAR');
    await expect(filas(page)).toHaveCount(3);
    await page.locator('[data-quitar-filtro-calendario]').click();
    await expect(chip).toHaveCount(0);
    await expect(page).not.toHaveURL(/cal=/);
    await expect(filas(page)).toHaveCount(3);
    // El calendario aplica los filtros que no son de fecha: con «Vencido sin pagar», el 15/11 queda vacío.
    await expect(dia(page, '2026-11-15')).toHaveAttribute('data-color-dia', 'ninguno');
    await expect(dia(page, '2026-11-04')).toHaveAttribute('data-color-dia', 'rojo');
    // Un filtro inválido en la URL no filtra (falla cerrado) y no muestra chip.
    await page.goto('/vencimientos?cal=semana:2026-11-04');
    await expect(filas(page)).toHaveCount(12);
    await expect(chip).toHaveCount(0);
  });

  test('vistas Día, Semana y Año; navegación; año: 12 meses con total e intensidad; clic en mes filtra; «Ver mes»', async ({ page }) => {
    await page.locator('[data-cal-anterior]').click();
    await expect(page.locator('[data-periodo-cal]')).toHaveText('Octubre de 2026');
    await expect(page).toHaveURL(/fecha=2026-10-01/);
    await page.locator('[data-cal-hoy]').click();
    await expect(page.locator('[data-periodo-cal]')).toHaveText('Noviembre de 2026');
    // Semana de hoy: 16–22 nov (19: Fedefarma sin importe; 21: abono).
    await page.locator('[data-vista="semana"]').click();
    await expect(page).toHaveURL(/vista=semana/);
    await expect(page.locator('[data-periodo-cal]')).toHaveText('16–22 nov 2026');
    await expect(page.locator('[data-vista-semana] [data-dia]')).toHaveCount(7);
    await expect(page.locator('[data-pago-semana]')).toHaveCount(2);
    await expect(dia(page, '2026-11-21').locator('[data-importe-dia]')).toHaveAttribute('data-importe-dia', '-45,30 €');
    await page.locator('[data-cal-anterior]').click();
    await expect(page.locator('[data-periodo-cal]')).toHaveText('9–15 nov 2026');
    await expect(page.locator('[data-pago-semana]')).toHaveCount(3);
    // Día: 04/11 con sus dos pagos y la suma.
    await page.goto('/vencimientos?vista=dia&fecha=2026-11-04');
    await expect(page.locator('[data-periodo-cal]')).toHaveText('Miércoles, 4 de noviembre de 2026');
    await expect(page.locator('[data-vista-dia] [data-pago]')).toHaveCount(2);
    await expect(page.locator('[data-vista-dia] [data-suma-dia]')).toHaveText('Total304,74 €');
    await expect(page.locator('[data-vista-dia]')).toHaveAttribute('data-color-dia', 'rojo');
    await page.locator('[data-cal-siguiente]').click();
    await expect(page.locator('[data-vista-dia]')).toContainText('Ningún vencimiento este día.');
    await page.locator('[data-cal-anterior]').click();
    await page.locator('[data-mostrar-periodo]').click();
    await expect(filas(page)).toHaveCount(2);
    // Año: 12 meses; octubre y noviembre con pagos; intensidad por importe.
    await page.locator('[data-vista="anio"]').click();
    await expect(page.locator('[data-periodo-cal]')).toHaveText('2026');
    await expect(page.locator('[data-mes]')).toHaveCount(12);
    await expect(page.locator('[data-mes="2026-11"] [data-importe-mes]')).toHaveText('881,66 €');
    await expect(page.locator('[data-mes="2026-11"]')).toContainText('9 pagos');
    await expect(page.locator('[data-mes="2026-11"]')).toHaveAttribute('data-intensidad', '4');
    await expect(page.locator('[data-mes="2026-10"] [data-importe-mes]')).toHaveText('380,00 €');
    await expect(page.locator('[data-mes="2026-10"]')).toHaveAttribute('data-intensidad', '2');
    await expect(page.locator('[data-mes="2026-03"]')).toHaveAttribute('data-intensidad', '0');
    await expect(page.locator('[data-mes="2026-03"]')).toContainText('sin pagos');
    await page.evaluate(() => document.fonts.ready);
    await page.locator('[data-mes="2026-10"] .vc-mes-boton').click();
    await expect(page.locator('[data-filtro-calendario]')).toHaveText(/Octubre de 2026/);
    await expect(filas(page)).toHaveCount(3);
    await page.locator('[data-calendario-vencimientos]').screenshot({ path: join(CAPTURAS, 'pc1440_calendario_anio.png') });
    await page.locator('[data-mes="2026-10"]').getByRole('button', { name: 'Ver octubre en el calendario' }).click();
    await expect(page.locator('[data-calendario-vencimientos]')).toHaveAttribute('data-vista-cal', 'mes');
    await expect(page.locator('[data-periodo-cal]')).toHaveText('Octubre de 2026');
  });

  test('lista: pestañas de Facturas con recuento, filtros nuevos (proveedor, sentido, importe, estado de la factura, revisión), búsqueda por importe y orden por columna, en la URL', async ({ page }) => {
    const pestana = (t: string) => page.getByRole('tab', { name: new RegExp(`^${t}`) });
    await expect(page.locator('[data-pestana] .pestana-n')).toHaveText(['12', '6', '5', '2', '3']);
    await pestana('Conciliadas').click();
    await expect(filas(page)).toHaveCount(6);
    await expect(page).toHaveURL(/pestana=conciliadas/);
    await pestana('No revisadas por Pío').click();
    await expect(filas(page)).toHaveCount(3);
    await pestana('Todas').click();
    await page.locator('select[name="proveedor"]').selectOption('A00000001');
    await expect(filas(page)).toHaveCount(7);
    await expect(page.locator('[data-pestana="conciliadas"] .pestana-n')).toHaveText('4'); // recuentos con el resto de filtros
    await page.locator('select[name="sentido"]').selectOption('ABONO');
    await expect(filas(page)).toHaveCount(2);
    await page.locator('select[name="sentido"]').selectOption('');
    await page.locator('select[name="importe"]').selectOption('sin');
    await expect(filas(page)).toHaveCount(1); // CF-2026-55811, 3.º vencimiento
    await page.getByRole('button', { name: 'Quitar filtros' }).click();
    await page.locator('select[name="factura"]').selectOption('norm:REQUIERE_REVISION');
    await expect(filas(page)).toHaveCount(1);
    await page.locator('select[name="factura"]').selectOption('');
    await page.locator('select[name="revision"]').selectOption('PENDIENTE_REVISION_PIO');
    await expect(filas(page)).toHaveCount(3);
    await page.locator('select[name="revision"]').selectOption('');
    await page.locator('input[name="q"]').fill('152,37');
    await expect(filas(page)).toHaveCount(2);
    await page.locator('input[name="q"]').fill('');
    // Orden por columna: importe ascendente y descendente (importe pendiente siempre al final).
    const importes = page.locator('tr[data-vencimiento] td.num');
    await page.locator('[data-ordenar="importe"]').click();
    await expect(page).toHaveURL(/orden=importe/);
    await expect(page.locator('th:has([data-ordenar="importe"])')).toHaveAttribute('aria-sort', 'ascending');
    await expect(importes.first()).toContainText('-45,30 €');
    await expect(importes.last()).toContainText('importe pendiente');
    await page.locator('[data-ordenar="importe"]').click();
    await expect(page).toHaveURL(/dir=desc/);
    await expect(page.locator('th:has([data-ordenar="importe"])')).toHaveAttribute('aria-sort', 'descending');
    await expect(importes.first()).toHaveText('472,22 €');
    await expect(importes.last()).toContainText('importe pendiente');
    await page.locator('[data-ordenar="estado"]').click();
    await expect(page.locator('tr[data-vencimiento] [data-estado-pago]').first()).toHaveText('Vencido sin pagar');
    await expect(page.locator('tr[data-vencimiento] [data-estado-pago]').last()).toHaveText('pagado (marcado a mano)');
    // Recargar conserva filtros y orden (URL).
    await page.reload();
    await expect(page.locator('th:has([data-ordenar="estado"])')).toHaveAttribute('aria-sort', 'ascending');
  });
});

test.describe('Calendario REAL simulado: igual que la lista, solo lectura', () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  test('sin marcas: calendario con los estados de REAL (domiciliados previstos en violeta); marcar sigue deshabilitado', async ({ page }) => {
    const { readFileSync } = await import('node:fs');
    const { DIR_DTO } = await import('../server/adaptador_fixtures.ts');
    const { construirPantalla } = await import('../server/pagos/pagos.ts');
    const real = construirPantalla(JSON.parse(readFileSync(join(DIR_DTO, 'vencimientos.json'), 'utf8')), null, { hoy: '2026-11-16', modo: 'REAL' });
    await page.route('**/api/pagos/vencimientos', (r) => r.fulfill({ json: real }));
    await entrar(page, '/vencimientos');
    await expect(page.locator('[data-banner-pagos="real"]')).toBeVisible();
    await expect(dia(page, '2026-11-04')).toHaveAttribute('data-color-dia', 'domiciliado');
    await expect(dia(page, '2026-11-07')).toHaveAttribute('data-color-dia', 'domiciliado'); // sin la marca de FIXTURES
    await dia(page, '2026-11-04').click();
    await page.locator('thead [data-seleccionar-todas]').check();
    await expect(page.locator('[data-marcar-pagado]')).toBeDisabled();
  });
});

test.describe('Calendario móvil 390', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test('toque en un día: detalle con los pagos y la suma; «Filtrar la lista a este día»; sin desbordamiento', async ({ page }) => {
    await entrar(page, '/vencimientos');
    await expect(page.locator('[data-calendario-vencimientos]')).toHaveAttribute('data-vista-cal', 'mes');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.evaluate(() => document.fonts.ready);
    await page.locator('[data-calendario-vencimientos]').screenshot({ path: join(CAPTURAS, 'movil390_calendario.png') });
    // Toque: abre el detalle (no filtra todavía).
    await dia(page, '2026-11-04').tap();
    const hoja = page.locator('[data-hoja-dia="2026-11-04"]');
    await expect(hoja).toBeVisible();
    await expect(hoja).toHaveAttribute('role', 'dialog');
    await expect(hoja.locator('[data-pago]')).toHaveCount(2);
    await expect(hoja.locator('[data-suma-dia]')).toHaveText('Total304,74 €');
    await expect(page).not.toHaveURL(/cal=/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_calendario_toque.png'), fullPage: false });
    // Otro toque en el mismo día lo cierra; tocar otro día cambia el detalle.
    await dia(page, '2026-11-04').tap();
    await expect(hoja).toHaveCount(0);
    await dia(page, '2026-11-14').tap();
    await expect(page.locator('[data-hoja-dia="2026-11-14"] [data-fuera-total]')).toContainText('1 de sentido no documentado');
    await page.getByRole('button', { name: 'Cerrar el detalle del día' }).tap();
    await expect(page.locator('[data-hoja-dia]')).toHaveCount(0);
    // Filtrar desde el detalle.
    await dia(page, '2026-11-04').tap();
    await page.locator('[data-filtrar-dia="2026-11-04"]').tap();
    await expect(page.locator('[data-hoja-dia]')).toHaveCount(0);
    await expect(page).toHaveURL(/cal=dia%3A2026-11-04/);
    await expect(page.locator('li[data-vencimiento]')).toHaveCount(2);
    await expect(page.locator('[data-filtro-calendario]')).toBeVisible();
    // Año en móvil: 2 columnas, sin desbordamiento.
    await page.locator('[data-vista="anio"]').tap();
    await expect(page.locator('[data-mes]')).toHaveCount(12);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.locator('[data-calendario-vencimientos]').screenshot({ path: join(CAPTURAS, 'movil390_calendario_anio.png') });
  });

  test('orden en móvil: selector «Ordenar por» y dirección', async ({ page }) => {
    await entrar(page, '/vencimientos');
    await page.locator('select[name="orden"]').selectOption('importe');
    await page.locator('[data-orden-dir]').tap();
    await expect(page).toHaveURL(/orden=importe.*dir=desc|dir=desc.*orden=importe/);
    await expect(page.locator('li[data-vencimiento]').first()).toContainText('472,22 €');
  });
});
