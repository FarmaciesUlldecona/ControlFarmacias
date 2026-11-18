// H6-5: vencidos sin importe en el calendario y resumen del periodo. Un día con pagos se marca siempre (color del peor
// estado y globo) aunque nada sume, con «importe pendiente» en la celda y en el desplegable; si el periodo visible está
// vacío, aviso con salto a las fechas con pagos. Resumen junto al título: Total = Pagado + Domiciliado previsto + Falta
// por pagar (− Abonos por compensar), sin desbordar a 1440, 1024 y 390.
// Solo FIXTURES (playwright.config.ts lo exige). Referencia de FIXTURES: lunes 16/11/2026.
import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { DIR_DTO } from '../server/adaptador_fixtures.ts';
import type { VencimientosDTO } from '../server/contrato.ts';
import { construirPantalla } from '../server/pagos/pagos.ts';
import { entrar } from './sesion.ts';

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'h6');
const dia = (page: Page, f: string) => page.locator(`[data-dia="${f}"]`);
const resumen = (page: Page) => page.locator('[data-resumen-periodo]');
const FEDEFARMA = '90000000-0000-4000-8000-000000000008';

/** Céntimos de cada término del resumen y del total (para comprobar que cuadra). */
async function centimos(page: Page): Promise<{ total: number; suma: number; terminos: string[] }> {
  return resumen(page).evaluate((el) => {
    const n = (x: Element) => Number(x.getAttribute('data-centimos'));
    const terminos = [...el.querySelectorAll('[data-resumen]:not([data-resumen="total"])')];
    return {
      total: n(el.querySelector('[data-resumen="total"]') as Element),
      suma: terminos.reduce((s, x) => s + n(x), 0),
      terminos: terminos.map((x) => x.getAttribute('data-resumen') as string),
    };
  });
}

async function sinDesbordar(page: Page, ancho: number) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(ancho);
  const cal = await page.locator('[data-calendario-vencimientos]').boundingBox();
  for (const t of await resumen(page).locator('.vc-r').all()) {
    const b = await t.boundingBox();
    expect(b && cal && b.x >= cal.x && b.x + b.width <= cal.x + cal.width + 0.5).toBe(true);
  }
}

/**
 * Pantalla REAL simulada (sin marcas) con el caso visto en REAL: la factura sin CIF y sin importe vence en octubre
 * (antes de hoy), así que es el único «Vencido sin pagar», con importe null.
 */
function pantallaRealConVencidoSinImporte() {
  const dto = JSON.parse(readFileSync(join(DIR_DTO, 'vencimientos.json'), 'utf8')) as VencimientosDTO;
  dto.vencimientos = dto.vencimientos.map((v) => (v.vencimiento_id === FEDEFARMA ? { ...v, fecha_vencimiento: '2026-10-20' } : v));
  return construirPantalla(dto, null, { hoy: '2026-11-16', modo: 'REAL' });
}

test.describe('Resumen del periodo PC 1440', () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  test.beforeEach(async ({ page }) => entrar(page, '/vencimientos'));

  test('mes: Total = Pagado + Domiciliado + Falta por pagar (+ abonos); fuera de totales con recuento; cuadra en día, semana y año', async ({ page }) => {
    const r = resumen(page);
    await expect(r).toHaveAttribute('data-resumen-cuadra', 'true');
    await expect(r).toHaveAttribute('data-resumen-pagos', '9');
    await expect(r.locator('[data-resumen="total"] dd')).toHaveText('881,66 €');
    await expect(r.locator('[data-resumen="total"] dt')).toHaveText('Total · 9 pagos');
    await expect(r.locator('[data-resumen] dt')).toHaveText([/^Total/, /^Pagado/, /^Domiciliado previsto/, /^Falta por pagar/]);
    await expect(r.locator('[data-resumen-fuera]')).toHaveText('Fuera de los totales: 2 sin importe · 2 de sentido no documentado');
    let c = await centimos(page);
    expect(c.suma).toBe(c.total);
    expect(c.total).toBe(88166);
    await sinDesbordar(page, 1440);
    await page.evaluate(() => document.fonts.ready);
    await page.locator('[data-calendario-vencimientos]').screenshot({ path: join(CAPTURAS, 'pc1440_resumen_mes.png') });
    // Octubre: con abono pendiente de compensar (aparte, en azul) y un cargo negativo fuera.
    await page.locator('[data-cal-anterior]').click();
    await expect(page.locator('[data-periodo-cal]')).toHaveText('Octubre de 2026');
    await expect(r.locator('[data-resumen="abonos"]')).toBeVisible();
    await expect(r.locator('[data-resumen="abonos"]')).toHaveAttribute('data-op', '−');
    await expect(r.locator('[data-resumen-fuera]')).toContainText('1 cargo negativo');
    c = await centimos(page);
    expect(c.terminos).toEqual(['pagado', 'domiciliado', 'falta', 'abonos']);
    expect(c.suma).toBe(c.total);
    await page.locator('[data-calendario-vencimientos]').screenshot({ path: join(CAPTURAS, 'pc1440_resumen_abonos.png') });
    // Día, semana y año: el resumen es del periodo visible y cuadra.
    for (const [url, pagos] of [['/vencimientos?vista=dia&fecha=2026-11-04', '2'], ['/vencimientos?vista=semana', '2'], ['/vencimientos?vista=anio', '13']] as const) { // H6-REAL: +V13 (diciembre)
      await page.goto(url);
      await expect(r).toHaveAttribute('data-resumen-pagos', pagos);
      await expect(r).toHaveAttribute('data-resumen-cuadra', 'true');
      c = await centimos(page);
      expect(c.suma).toBe(c.total);
    }
    await expect(r.locator('[data-resumen="total"] dd')).toHaveText('1.261,66 €'); // año 2026: octubre + noviembre
  });

  test('el resumen sigue los filtros: con «Vencido sin pagar» solo hay falta por pagar', async ({ page }) => {
    await page.locator('[data-filtro-estado="VENCIDO_SIN_PAGAR"]').click();
    const r = resumen(page);
    await expect(r).toHaveAttribute('data-resumen-pagos', '3');
    await expect(r.locator('[data-resumen="falta"] dd')).toHaveText(await r.locator('[data-resumen="total"] dd').innerText());
    await expect(r.locator('[data-resumen="pagado"] dd')).toHaveText('—');
    await expect(r.locator('[data-resumen="domiciliado"] dd')).toHaveText('—');
    const c = await centimos(page);
    expect(c.suma).toBe(c.total);
  });

  test('día que no suma: la celda dice por qué (07/11 pagado de sentido no documentado), nunca «—» ni 0', async ({ page }) => {
    await expect(dia(page, '2026-11-07')).toHaveAttribute('data-color-dia', 'verde');
    await expect(dia(page, '2026-11-07').locator('[data-globo]')).toHaveText('1');
    await expect(dia(page, '2026-11-07').locator('[data-sin-total]')).toHaveAttribute('data-sin-total', 'sentido no documentado');
    await expect(dia(page, '2026-11-07').locator('.vc-importe-largo')).toHaveText('sentido no documentado');
  });
});

test.describe('REAL simulado: vencido sin pagar sin importe (factura sin CIF)', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('filtro «Vencido sin pagar»: el mes actual avisa y salta a octubre; el 20/10 se marca en rojo con globo e «importe pendiente»', async ({ page }) => {
    const real = pantallaRealConVencidoSinImporte();
    await page.route('**/api/pagos/vencimientos', (r) => r.fulfill({ json: real }));
    await entrar(page, '/vencimientos');
    await page.locator('[data-filtro-estado="VENCIDO_SIN_PAGAR"]').click();
    await expect(page.locator('[data-filtro-estado="VENCIDO_SIN_PAGAR"] .ve-estado-n')).toHaveText('1');
    // Noviembre no tiene ninguno: aviso con salto a la fecha con pagos (antes no se veía nada).
    await expect(page.locator('.vc-mes [data-color-dia="rojo"]')).toHaveCount(0);
    const aviso = page.locator('[data-aviso-periodo-vacio]');
    await expect(aviso).toContainText('Ningún pago en este periodo con estos filtros; hay 1 pago en otras fechas.');
    await expect(page.locator('[data-ir-siguiente]')).toHaveCount(0);
    await page.evaluate(() => document.fonts.ready);
    await page.locator('[data-calendario-vencimientos]').screenshot({ path: join(CAPTURAS, 'pc1440_vencido_sin_importe_aviso.png') });
    await page.locator('[data-ir-anterior="2026-10-20"]').click();
    await expect(page.locator('[data-periodo-cal]')).toHaveText('Octubre de 2026');
    // El día se marca siempre: color del peor estado, globo y «importe pendiente» (ningún importe suma).
    const d = dia(page, '2026-10-20');
    await expect(d).toHaveAttribute('data-color-dia', 'rojo');
    await expect(d.locator('[data-globo]')).toHaveText('1');
    await expect(d.locator('[data-sin-total]')).toHaveAttribute('data-sin-total', 'importe pendiente');
    await expect(d.locator('.vc-importe-largo')).toHaveText('importe pendiente');
    await expect(d).toHaveAttribute('aria-label', /1 pago, total sin importe que sume \(importe pendiente\)/);
    // La semana también se marca.
    await expect(page.locator('[data-semana="2026-10-19"]')).not.toHaveClass(/sin-pagos/);
    // Desplegable: «importe pendiente» en el pago y en la suma.
    await d.hover();
    const des = page.locator('[data-desplegable="2026-10-20"]');
    await expect(des.locator('.vc-pago-importe')).toHaveText('importe pendiente');
    await expect(des.locator('[data-suma-sin-total]')).toHaveText('importe pendiente');
    await expect(des.locator('[data-estado-pago]')).toHaveText('Vencido sin pagar');
    // Resumen: un pago, falta por pagar sin importe, total «importe pendiente», 1 sin importe fuera de los totales.
    const r = resumen(page);
    await expect(r).toHaveAttribute('data-resumen-pagos', '1');
    await expect(r.locator('[data-resumen="total"] dd')).toHaveText('importe pendiente');
    await expect(r.locator('[data-resumen="falta"] dd')).toHaveText('sin importe');
    await expect(r.locator('[data-resumen-fuera]')).toHaveText('Fuera de los totales: 1 sin importe');
    await page.locator('[data-calendario-vencimientos]').screenshot({ path: join(CAPTURAS, 'pc1440_vencido_sin_importe_dia.png') });
    // Clic: filtra la lista a ese día.
    await page.mouse.move(5, 5);
    await d.click();
    await expect(page.locator('tr[data-vencimiento]')).toHaveCount(1);
    await expect(page.locator('tr[data-vencimiento] [data-importe-pendiente]')).toBeVisible();
  });
});

test.describe('H6-6: domiciliados no vencidos en «Falta por pagar» (por estado), igual en resumen y cabecera', () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  test('REAL simulado con referencia 1/11/2026: los domiciliados de noviembre aún no han vencido → rojo; domiciliado previsto «—»', async ({ page }) => {
    // Sin marcas (REAL) y con hoy = 1 nov: todo lo de noviembre está pendiente; los de CIF sin configurar son domiciliados.
    const dto = JSON.parse(readFileSync(join(DIR_DTO, 'vencimientos.json'), 'utf8')) as VencimientosDTO;
    const real = construirPantalla(dto, null, { hoy: '2026-11-01', modo: 'REAL' });
    expect(real.filas.filter((f) => f.fecha_vencimiento?.startsWith('2026-11') && f.forma_pago === 'DOMICILIACION' && f.estado_pago === 'PENDIENTE').length).toBeGreaterThan(0);
    await page.route('**/api/pagos/vencimientos', (r) => r.fulfill({ json: real }));
    await entrar(page, '/vencimientos');
    const r = resumen(page);
    await expect(page.locator('[data-periodo-cal]')).toHaveText('Noviembre de 2026');
    await expect(r.locator('[data-resumen="domiciliado"] dd')).toHaveText('—');
    await expect(r.locator('[data-resumen="falta"] dd')).toHaveText(await r.locator('[data-resumen="total"] dd').innerText());
    const c = await centimos(page);
    expect(c.suma).toBe(c.total);
    await page.evaluate(() => document.fonts.ready);
    await page.locator('[data-calendario-vencimientos]').screenshot({ path: join(CAPTURAS, 'pc1440_resumen_domiciliados_futuros.png') });
    // La cabecera de totales de ese mes coincide con el resumen (mismos bloques por estado).
    await page.locator('[data-mostrar-periodo]').click();
    const cab = page.locator('[data-total-general]');
    await expect(cab.locator('[data-total="por_pagar"] .ve-cifra-n')).toHaveText(await r.locator('[data-resumen="falta"] dd').innerText());
    await expect(cab.locator('[data-total="domiciliado"] .ve-cifra-n')).toHaveText('—');
    await expect(cab.locator('[data-total="abonos"]')).toHaveCount(0);
  });
});

test.describe('Resumen sin desbordar a 1024', () => {
  test.use({ viewport: { width: 1024, height: 800 } });
  test('mes y octubre (con abonos): dentro del calendario, sin scroll horizontal', async ({ page }) => {
    await entrar(page, '/vencimientos');
    await page.goto('/vencimientos?fecha=2026-10-01');
    await expect(resumen(page).locator('[data-resumen="abonos"]')).toBeVisible();
    await sinDesbordar(page, 1024);
    await page.evaluate(() => document.fonts.ready);
    await page.locator('[data-calendario-vencimientos]').screenshot({ path: join(CAPTURAS, 'pc1024_resumen_abonos.png') });
    await page.goto('/vencimientos');
    await sinDesbordar(page, 1024);
  });
});

test.describe('Resumen móvil 390', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  test('mes, octubre y vencido sin importe: sin desbordar; el toque muestra «importe pendiente»', async ({ page }) => {
    await entrar(page, '/vencimientos');
    await page.goto('/vencimientos?fecha=2026-10-01');
    await expect(resumen(page).locator('[data-resumen="abonos"]')).toBeVisible();
    await expect(resumen(page)).toHaveAttribute('data-resumen-cuadra', 'true');
    await sinDesbordar(page, 390);
    await page.evaluate(() => document.fonts.ready);
    await page.locator('[data-calendario-vencimientos]').screenshot({ path: join(CAPTURAS, 'movil390_resumen_abonos.png') });
    const real = pantallaRealConVencidoSinImporte();
    await page.route('**/api/pagos/vencimientos', (r) => r.fulfill({ json: real }));
    await page.goto('/vencimientos?estado=VENCIDO_SIN_PAGAR');
    await expect(page.locator('[data-aviso-periodo-vacio]')).toBeVisible();
    await sinDesbordar(page, 390);
    await page.locator('[data-ir-anterior]').tap();
    const d = dia(page, '2026-10-20');
    await expect(d).toHaveAttribute('data-color-dia', 'rojo');
    await expect(d.locator('[data-globo]')).toHaveText('1');
    await d.tap();
    await expect(page.locator('[data-hoja-dia="2026-10-20"] .vc-pago-importe')).toHaveText('importe pendiente');
    await sinDesbordar(page, 390);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_vencido_sin_importe.png'), fullPage: false });
  });
});
