// H8 (migración 36): R20 en el detalle (albarán partido en Farmatic) y «Revisar: detectado por la noche» en Conciliación
// e Inicio. Solo FIXTURES (playwright.config.ts lo exige); el caso «nada para revisar» se simula interceptando la API.
import { expect, test, type Page } from '@playwright/test';
import { join } from 'node:path';
import { entrar } from './sesion.ts';

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'h8');
const F = (n: number) => `f0000000-0000-4000-8000-0000000000${String(n).padStart(2, '0')}`;

test.beforeEach(async ({ page }) => entrar(page));

async function abrirDetalle(page: Page, n: number) {
  await page.goto(`/facturas/${F(n)}`);
  await expect(page.locator('[data-contrato-ok="facturaDetalle"]')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

test.describe('PC 1440', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('R20 (F02): «Albarán partido en Farmatic» con los dos números; una diferencia por línea; suma de Farmatic', async ({ page }) => {
    await abrirDetalle(page, 2);
    const alb = page.locator('[data-seccion="albaranes"]');
    const r20 = alb.locator('[data-casado="R20:PARTIDO"]');
    // Un «cómo casó» por línea del PDF (no por albarán).
    await expect(r20).toHaveCount(2);
    await expect(r20.first()).toHaveText('Albarán partido en Farmatic');
    await expect(alb.locator('[data-relacion="UNO_A_VARIOS"]')).toHaveText(['08X20002 / 08D20002', '08X20004 / 08D20004']);
    await expect(alb.locator('[data-estado-matching="MATCH_R20"]')).toHaveCount(2);
    await expect(alb.locator('[data-suma-farmatic-r20]')).toHaveText(['Farmatic, suma de los 2: 43,09 €', 'Farmatic, suma de los 2: 156,73 €']);
    // Cada fila conserva su importe de Farmatic.
    for (const v of ['30,00 €', '13,09 €', '100,00 €', '56,73 €']) await expect(alb.locator('[data-importe-linea="farmatic"]', { hasText: v })).toHaveCount(1);
    // Una sola cifra de diferencia y un estado por línea (8 líneas del PDF, 10 detalles; la línea 6 sin importe del PDF:
    // diferencia «no consta»).
    await expect(alb.locator('[data-diferencia-linea]')).toHaveCount(7);
    await expect(alb.locator('[data-no-consta="diferencia"]')).toHaveCount(1);
    await expect(alb.locator('[data-estado-linea]')).toHaveCount(8);
    await expect(alb.locator('[data-linea]')).toHaveCount(10);
    const fila2 = alb.locator('tr', { has: page.locator('.linea-pdf', { hasText: '08X20002' }) });
    await expect(fila2.locator('[data-diferencia-linea]')).toHaveText('1,21 €');
    await expect(fila2.locator('[data-estado-linea]')).toHaveText('Diferencia');
    const fila4 = alb.locator('tr', { has: page.locator('.linea-pdf', { hasText: '08X20004' }) });
    await expect(fila4.locator('[data-diferencia-linea]')).toHaveText('0,01 €');
    await expect(fila4.locator('[data-estado-linea]')).toHaveText('Coincide');
    // El aviso cuenta la línea R20 una vez.
    await expect(page.locator('[data-aviso-detalle="lineas-con-diferencia"]')).toHaveText(/^1 albarán con diferencia/);
    await expect(alb.locator('[data-insignia-seccion]')).toHaveText('1 con diferencia');
    await fila2.scrollIntoViewIfNeeded();
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_r20_detalle.png'), fullPage: true });
  });

  test('Conciliación: grupo naranja «Revisar: detectado por la noche (01/11/2026)» con los cuatro tipos, enlaces y evidencia', async ({ page }) => {
    await page.goto('/conciliacion');
    const g = page.locator('[data-revisar-noche]');
    await expect(g).toBeVisible();
    await expect(g.getByRole('heading', { level: 2 })).toHaveText('Revisar: detectado por la noche (01/11/2026)');
    await expect(g).toHaveAttribute('data-color', 'naranja');
    await expect(g.locator('[data-noche-casos]')).toHaveText('6 casos');
    await expect(g.locator('[data-noche-casos]')).toHaveClass(/\bo\b/);
    await expect(g.locator('.insignia.r, .pr')).toHaveCount(0); // nunca rojo
    await expect(g.locator('[data-noche-texto]')).toHaveText([
      'Diferencia simulada de 118,16 €', 'Diferencia simulada de 2,0350 €', 'Proveedor aún sin conciliación automática',
      'Pendiente de la regla R18', 'Documento con defecto tras 3 intentos', 'Elemento de la noche sin descripción (ver evidencia técnica)',
    ]);
    await expect(g).not.toContainText('OTRA-FARMACIA');
    // Enlaces: la factura (detalle) o, para un documento, Facturas.
    const r18 = g.locator('[data-noche-elemento="R18_PENDIENTE"]');
    await expect(r18.getByRole('link', { name: /Abrir/ })).toHaveAttribute('href', `/facturas/${F(6)}`);
    await expect(g.locator('[data-noche-elemento="DEFECTO"]').getByRole('link', { name: /Abrir/ })).toHaveAttribute('href', '/facturas');
    await expect(g.locator('[data-noche-elemento="DEFECTO"]')).toContainText('PDF');
    // R18: fallo y r18 en la evidencia técnica (desplegable).
    await r18.locator('[data-noche-evidencia] summary').click();
    await expect(r18.locator('[data-noche-evidencia]')).toContainText('fallo: R18_SIN_EVIDENCIA_FICTICIO');
    await expect(r18.locator('[data-noche-evidencia]')).toContainText('"estado":"PENDIENTE"');
    // H8 (pantalla): el grupo está en «Doble comprobación» (por defecto); ya no hay tarjeta «En construcción».
    await expect(page.locator('[data-panel="doble"]')).toBeVisible();
    await expect(page.getByText('En construcción')).toHaveCount(0);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_conciliacion_noche.png'), fullPage: true });
    await r18.getByRole('link', { name: /Abrir/ }).click();
    await expect(page).toHaveURL(new RegExp(`/facturas/${F(6)}$`));
  });

  test('H8-5: R21 (F05) y R22 (F04) con su etiqueta legible en el detalle; las dos facturas están en Conciliación', async ({ page }) => {
    await page.goto('/conciliacion');
    await expect(page.locator('[data-revisar-noche]')).toBeVisible();
    for (const [n, clave, texto] of [[5, 'R21:COMPLEMENTARIOS', 'Albarán con complementarios de la misma recepción'], [4, 'R22:ANULADO', 'Cargo anulado por su abono (neto 0)']] as const) {
      await abrirDetalle(page, n);
      const alb = page.locator('[data-seccion="albaranes"]');
      await expect(alb.locator(`[data-casado="${clave}"]`)).toHaveCount(1);
      await expect(alb.locator(`[data-casado="${clave}"]`)).toHaveText(texto);
      await expect(alb.locator('[data-regla-desconocida]')).toHaveCount(0);
      await alb.locator(`[data-casado="${clave}"]`).scrollIntoViewIfNeeded();
      await page.screenshot({ path: join(CAPTURAS, `pc1440_${clave.slice(0, 3).toLowerCase()}_detalle.png`) });
    }
    // Código de regla desconocido: el código tal cual, sin fallar (respuesta de FIXTURES modificada en el navegador).
    await page.route('**/api/facturas/*', async (r) => {
      const res = await r.fetch();
      const j = (await res.json()) as { lineas?: Record<string, unknown>[] };
      if (Array.isArray(j.lineas)) j.lineas = j.lineas.map((l) => (l.regla === 'R21' ? { ...l, regla: 'R99' } : l));
      await r.fulfill({ response: res, json: j });
    });
    await abrirDetalle(page, 5);
    const alb = page.locator('[data-seccion="albaranes"]');
    await expect(alb.locator('[data-regla-desconocida="R99"]')).toHaveText('R99');
    await expect(alb.locator('[data-casado="R21:COMPLEMENTARIOS"]')).toHaveCount(0);
  });

  test('Inicio: solo recuento y enlace (naranja); no suma en «Necesita tu atención»', async ({ page }) => {
    await page.goto('/');
    const r = page.locator('[data-revisar-noche-inicio]');
    await expect(r).toHaveText(/Revisar: detectado por la noche \(01\/11\/2026\): 6 casos\s*Ver en Conciliación/);
    await expect(r).toHaveClass(/borde-naranja/);
    await expect(r.locator('[data-noche-elemento]')).toHaveCount(0);
    // H8 (pantalla): las alertas de albaranes también salen de «Necesita tu atención» (15/27 → 12/23).
    await expect(page.locator('[data-atencion-resumen]')).toHaveText('— 12 tipos, 23 casos');
    await r.getByRole('link', { name: 'Ver en Conciliación' }).click();
    await expect(page).toHaveURL(/\/conciliacion$/);
    await expect(page.locator('[data-revisar-noche]')).toBeVisible();
  });

  test('noche sin elementos: «Nada para revisar en la noche del 18/11» (Conciliación e Inicio, sin enlace)', async ({ page }) => {
    const vacia = { fecha: '2026-11-18', lista_valida: true, elementos: [], por_tipo: { DIFERENCIA: 0, NO_ALLIANCE: 0, R18_PENDIENTE: 0, DEFECTO: 0, OTRO: 0 } };
    for (const api of ['conciliacion', 'inicio']) {
      await page.route(`**/api/${api}`, async (ruta) => {
        const res = await ruta.fetch();
        await ruta.fulfill({ response: res, json: { ...(await res.json()), revisar_noche: vacia } });
      });
    }
    await page.goto('/conciliacion');
    await expect(page.locator('[data-noche-vacio]')).toHaveText('Nada para revisar en la noche del 18/11');
    await expect(page.locator('[data-noche-elemento]')).toHaveCount(0);
    await page.goto('/');
    const r = page.locator('[data-revisar-noche-inicio]');
    await expect(r).toHaveText('Nada para revisar en la noche del 18/11');
    await expect(r.getByRole('link')).toHaveCount(0);
  });
});

test.describe('Móvil 390', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('R20 en la lista móvil: un «cómo casó» y la suma de Farmatic por línea; Conciliación sin desbordar', async ({ page }) => {
    await abrirDetalle(page, 2);
    const pestana = page.getByRole('tab', { name: 'Detalle' });
    if (await pestana.count()) await pestana.click();
    const alb = page.locator('[data-seccion="albaranes"]');
    await expect(alb.locator('[data-casado="R20:PARTIDO"]')).toHaveCount(2);
    await expect(alb.locator('[data-suma-farmatic-r20]')).toHaveCount(2);
    await page.goto('/conciliacion');
    await expect(page.locator('[data-revisar-noche]')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_conciliacion_noche.png'), fullPage: true });
  });
});
