// H7: pantalla Cashflow (solo FIXTURES; REAL simulado con 503). Vistas decenas / mes y PIO / RITA / consolidado,
// desglose de la fuente, avisos y móvil 390 sin desbordar. H7-REAL-9: sin selector «Media / Excel».
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
    await expect(page.locator('[data-cf-saldo-actual="PIO"] .cf-ficha-cifra')).toHaveText('25.000,00 €');
    await expect(page.locator('[data-cf-saldo-actual="RITA"] .cf-ficha-cifra')).toHaveText('2.000,00 €');
    await expect(page.locator('[data-cf-saldo-actual="CONSOLIDADO"] .cf-ficha-cifra')).toHaveText('27.000,00 €');
    await expect(page.locator('[data-cf-proximo-aviso]')).toHaveAttribute('data-cf-proximo-aviso', 'naranja');
    await expect(page.locator('[data-cf-proximo-aviso]')).toContainText('11–20 dic 2026');
    await expect(page.locator('[data-cf-importacion]')).toContainText('hace 6 días');
    // Avisos: un solo gris (ninguno por traspasos no compensados: H7-REAL-2).
    await expect(page.locator('[data-cf-aviso="gris"]')).toHaveCount(1);
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
    // Consolidado: traspasos neutros; los no compensados, una sola línea plegada de las decenas visibles; saldo negativo en rojo.
    await expect(page.locator('[data-cf-traspasos-neutros]')).toBeVisible();
    const nc = page.locator('[data-cf-traspasos-no-compensados]');
    await expect(nc).toHaveCount(1);
    await expect(nc.locator('summary')).toHaveText('1 decena con traspasos no compensados');
    await expect(nc.locator('li')).toBeHidden();
    await nc.locator('summary').click();
    await expect(nc.locator('li')).toHaveCount(1);
    await expect(nc.locator('li')).toContainText('21–31 oct 2026');
    await expect(nc.locator('li')).toContainText('−16.000,00 €');
    await nc.locator('summary').click();
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
    // H7-REAL-9: Excel de diciembre (7.000, 2.ª decena) + su media en la 3.ª (1.166,67: dos pagas en 12 meses).
    await expect(celda(page, 'RS Personal|Paga extra|2026-12')).toContainText('−8.167');
    await expect(page.locator('[data-cf-tabla="RITA"] [data-cf-seccion="traspasos"]')).toBeVisible();
    await sinDesbordar(page, 1440);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_mes_rita.png'), fullPage: true });
    // Consolidado por meses (captura del informe).
    await page.locator('[data-cf-cuenta="CONSOLIDADO"]').click();
    await expect(page.locator('[data-cf-tabla="CONSOLIDADO"]')).toBeVisible();
    // Traspasos no compensados de las columnas visibles (agosto, septiembre y octubre).
    await expect(page.locator('[data-cf-traspasos-no-compensados] summary')).toHaveText('3 decenas con traspasos no compensados');
    // En «Mes» las marcas van al saldo de la peor decena (enero cierra en positivo, pero el 11–20 falta saldo).
    await expect(page.locator('[data-cf-marca="rojo"][data-columna="2027-01"]')).toHaveAttribute('data-decena', '2027-01-11');
    await expect(page.locator('[data-cf-marca="naranja"][data-columna="2026-12"]')).toHaveAttribute('data-decena', '2026-12-11');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_mes_consolidado.png'), fullPage: true });
  });

  test('desglose: vencimientos con enlace a la factura y «posible duplicado o diferencia»; media con su cálculo', async ({ page }) => {
    await page.locator('[data-cf-cuenta="PIO"]').click();
    await page.locator('[data-cf-plegar="RS Proveedores"]').click();
    // H7-REAL-9: previsión base de ALLIANCE = el mayor entre su Excel (520) y su media (6.000): la media; los vencimientos
    // (472,22) son menores: cuenta la media, con el Excel a la vista.
    const alliance = celda(page, 'RS Proveedores|ALLIANCE|2026-11-11');
    await expect(alliance).toHaveAttribute('data-cf-fuente', 'media');
    await expect(alliance.locator('[data-cf-marca-media]')).toBeVisible();
    await expect(alliance.locator('[data-cf-diferencia]')).toBeVisible();
    await expect(alliance).toContainText('−6.000');
    await expect(alliance.locator('[data-cf-alt]')).toHaveText('Excel −520');
    await alliance.locator('button').click();
    const d = page.locator('[data-cf-desglose]');
    await expect(d).toBeVisible();
    await expect(d.locator('[data-cf-desglose-fuente="MEDIA"]')).toBeVisible();
    await expect(d.locator('[data-cf-frente="media"]')).toHaveText('Excel 520,00 € (inferior a la media) → media 6.000,00 €.');
    await expect(d.locator('[data-cf-venc-minimo="media"]')).toContainText('Vencimientos conocidos 472,22 € (inferiores a la media)');
    await expect(d.locator('[data-cf-media-ventana]')).toHaveText('Media de 12 meses (misma decena)');
    await expect(d.locator('[data-cf-comparacion="diferencia"]')).toContainText('Posible duplicado o diferencia');
    await expect(d.locator('[data-cf-comparacion="diferencia"]')).toContainText('Excel: −520,00 €');
    await expect(d.locator('[data-cf-comparacion="diferencia"]')).toContainText('47,78 € entre los dos');
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
    // H7-REAL-9: por concepto, cada uno con su cifra (sin «media del resto»): 11–20/11 = ALLIANCE 6.000 + COFARES 4.479,17
    // + DERMOFARMACIA 16,67 + HEFAME 3.500 + KENVUE 41,67 + LOGISTA 800.
    await page.keyboard.press('Escape');
    const prov = celda(page, 'RS Proveedores|*|2026-11-11');
    await expect(prov).toContainText('−14.838');
    await prov.locator('button').click();
    await expect(d.locator('[data-cf-parte="vencimientos"]')).toHaveText('Vencimientos (ALLIANCE)');
    await expect(d.locator('[data-cf-parte="media-resto"]')).toHaveCount(0);
    await expect(d.locator('[data-cf-desglose-fuente="MEDIA"] .cf-desglose-cifra')).toHaveText(['−6.000,00 €', '−4.479,17 €', '−16,67 €', '−3.500,00 €', '−41,67 €', '−800,00 €']);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_desglose_vencimientos_resto.png') });
    await page.keyboard.press('Escape');
    await expect(celda(page, 'RS Proveedores|*|2026-11-21').locator('[data-cf-marca-media]')).toBeVisible();
    // Media de TPV por posición de decena (H7-REAL-8: 12 meses, de 11–20/11/2025 a 11–20/10/2026), con su marca «m».
    const tpv = celda(page, 'RE Cobro TPV|*|2026-11-11');
    await expect(tpv).toHaveAttribute('data-cf-fuente', 'media');
    await expect(tpv.locator('[data-cf-marca-media]')).toHaveText('m');
    await expect(tpv.locator('[data-cf-alt]')).toHaveCount(0); // nada anotado en el Excel
    await tpv.locator('button').click();
    await expect(d.locator('[data-cf-media-ventana]')).toHaveText('Media de 12 meses (misma decena)');
    await expect(d.locator('[data-cf-regla="posicion"]')).toContainText('Media del concepto en la 2.ª decena del mes en los últimos 12 meses reales');
    await expect(d.locator('[data-cf-media] li')).toHaveCount(13);
    await expect(d.locator('[data-cf-media] li').first()).toContainText('11–20 nov 2025');
    await expect(d.locator('.cf-media-total')).toContainText('10.000,00 €');
    await expect(d.locator('[data-cf-no-suma]')).toHaveCount(0);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_desglose_media.png') });
    await page.keyboard.press('Escape');
    await expect(d).toHaveCount(0);
    // Excel superior a la media: TPV de Navidad (21–31/12, 12.500 frente a 9.000) sin marca «m»; la media, a la vista.
    await expect(celda(page, 'RE Cobro TPV|*|2026-12-21')).toHaveAttribute('data-cf-fuente', 'excel');
    await expect(celda(page, 'RE Cobro TPV|*|2026-12-21').locator('[data-cf-marca-media]')).toHaveCount(0);
    await page.locator('[data-cf-plegar="RE Cobro TPV"]').click();
    await expect(celda(page, 'RE Cobro TPV|TPV CaixaBank|2026-12-21').locator('[data-cf-alt]')).toHaveText('Media 9.000');
    await celda(page, 'RE Cobro TPV|TPV CaixaBank|2026-12-21').locator('button').evaluate((el) => el.scrollIntoView({ block: 'center', inline: 'center' }));
    await celda(page, 'RE Cobro TPV|TPV CaixaBank|2026-12-21').locator('button').click();
    await expect(d.locator('[data-cf-frente="excel"]')).toHaveText('Excel 12.500,00 € (superior a la media 9.000,00 €).');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_excel_superior_media.png') });
    await page.keyboard.press('Escape');
    // «RS Modelo 303» de enero de 2027: el mismo mes del año anterior.
    await celda(page, 'RS Modelo 303|*|2027-01-11').locator('button').click();
    await expect(d.locator('[data-cf-regla="anio_anterior"]')).toBeVisible();
    await expect(d.locator('[data-cf-media] li').first()).toContainText('11–20 ene 2026');
    await expect(d.locator('.cf-media-total')).toContainText('−8.500,00 €');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_desglose_modelo.png') });
    await page.keyboard.press('Escape');
  });

  test('H7-REAL-2: vista RITA con su efectivo (COBRO EFECTIU): real y previsto por media (captura)', async ({ page }) => {
    await page.locator('[data-cf-cuenta="RITA"]').click();
    await expect(page.locator('[data-cf-tabla="RITA"]')).toBeVisible();
    await expect(page.locator('[data-cf-categoria="RE Cobro efectivo"]')).toBeVisible();
    await page.locator('[data-cf-plegar="RE Cobro efectivo"]').click();
    await expect(page.locator('[data-cf-concepto="COBRO EFECTIU"]')).toBeVisible();
    await expect(celda(page, 'RE Cobro efectivo|COBRO EFECTIU|2026-11-01')).toHaveAttribute('data-cf-tipo', 'real');
    await expect(celda(page, 'RE Cobro efectivo|COBRO EFECTIU|2026-11-11')).toContainText('1.200');
    await expect(celda(page, 'RE Cobro efectivo|*|2026-11-11').locator('[data-cf-marca-media]')).toBeVisible();
    await expect(page.locator('[data-cf-tabla="RITA"] [data-cf-traspasos-no-compensados]')).toHaveCount(0);
    await sinDesbordar(page, 1440);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_decenas_rita.png'), fullPage: true });
  });

  test('H7-REAL-9: sin selector «Media / Excel» (la regla aplica siempre); RITA: HEFAME anotado (Excel > media) y COFARES con su media en la misma decena', async ({ page }) => {
    await page.locator('[data-cf-cuenta="PIO"]').click();
    await expect(saldo(page, '2026-11-11')).toHaveText('22.262');
    await expect(page.locator('[data-cf-eleccion]')).toHaveCount(0);
    // Una elección antigua guardada en el navegador ya no cambia nada.
    await page.evaluate(() => { try { localStorage.setItem('cf.cashflow.eleccion.v1', JSON.stringify({ 'RE Cobro TPV': 'excel' })); } catch { /* nada */ } });
    await page.reload();
    await expect(saldo(page, '2026-11-11')).toHaveText('22.262');
    await page.locator('[data-cf-cuenta="RITA"]').click();
    await page.locator('[data-cf-plegar="RS Proveedores"]').click();
    const hef = celda(page, 'RS Proveedores|HEFAME|2026-12-01');
    await expect(hef).toHaveAttribute('data-cf-fuente', 'excel');
    await expect(hef).toContainText('−9.800');
    await expect(hef.locator('[data-cf-alt]')).toHaveText('Media −2.000');
    const cof = celda(page, 'RS Proveedores|COFARES|2026-12-01');
    await expect(cof).toHaveAttribute('data-cf-fuente', 'media');
    await expect(cof).toContainText('−3.000');
    await expect(celda(page, 'RS Proveedores|*|2026-12-01')).toContainText('−12.800');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_rita_excel_y_media.png') });
  });

  test('H7-REAL: saldo final con su desglose: E7 (banco − fórmulas, informativa) en PIO 21–31/10 y cuadre de control', async ({ page }) => {
    await page.locator('[data-cf-cuenta="PIO"]').click();
    const oct = page.locator('[data-cf-saldo="2026-10-21"]');
    await expect(oct.locator('[data-cf-dif-banco]')).toContainText('dif. banco');
    await expect(oct.locator('[data-cf-dif-banco]')).toContainText('35,20');
    await expect(page.locator('[data-cf-dif-banco]')).toHaveCount(1);
    await expect(page.locator('[data-cf-no-cuadra]')).toHaveCount(0);
    await page.locator('button:has([data-cf-saldo="2026-10-21"])').click();
    const d = page.locator('[data-cf-desglose="saldo"]');
    await expect(d).toBeVisible();
    await expect(d.locator('[data-cf-e7]')).toContainText('Diferencia banco − fórmulas');
    await expect(d.locator('[data-cf-e7]')).toContainText('35,20');
    await expect(d.locator('[data-cf-cuadre="cuadra"]')).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_desglose_saldo_e7.png') });
    await page.keyboard.press('Escape');
    await expect(d).toHaveCount(0);
    // Consolidado: el desglose del saldo trae las dos cuentas.
    await page.locator('[data-cf-cuenta="CONSOLIDADO"]').click();
    await page.locator('button:has([data-cf-saldo="2026-11-01"])').click();
    await expect(page.locator('[data-cf-desglose-saldo]')).toHaveCount(2);
    await expect(page.locator('[data-cf-desglose-saldo="RITA|2026-11-01"]')).toBeVisible();
  });

  test('H7-REAL-4: traspasos externos en el consolidado con media y marca en el desglose; indicador de variación mensual junto al gráfico', async ({ page }) => {
    // Indicador de control (consolidado): real de los últimos 12 meses frente a la prevista.
    const ind = page.locator('[data-cf-indicador]');
    await expect(ind).toContainText('Variación media mensual del consolidado');
    await expect(ind.locator('[data-cf-variacion="real"] strong')).toHaveText(/€\/mes$/);
    await expect(ind.locator('[data-cf-variacion="prevista"] strong')).toHaveText(/€\/mes$/);
    // Consolidado: sección de traspasos externos (los internos siguen neutros).
    const t = page.locator('[data-cf-tabla="CONSOLIDADO"]');
    await expect(t.locator('[data-cf-seccion="traspasos_externos"]')).toBeVisible();
    await expect(t.locator('[data-cf-total="traspasos_externos"]')).toBeVisible();
    await expect(t.locator('[data-cf-traspasos-neutros]')).toBeVisible();
    await t.locator('[data-cf-plegar="RS Traspasos (externo)"]').click();
    await expect(t.locator('[data-cf-concepto="TRASPASO A FONDOS/VALORS"]')).toBeVisible();
    await expect(t.locator('[data-cf-concepto="La Caixa Rita"]')).toHaveCount(0);
    const c = celda(page, 'RS Traspasos (externo)|TRASPASO A FONDOS/VALORS|2026-12-01');
    await expect(c).toContainText('−1.000');
    await expect(c.locator('[data-cf-marca-media]')).toBeVisible();
    await c.locator('button').click();
    const d = page.locator('[data-cf-desglose]');
    await expect(d.locator('[data-cf-traspaso-externo]')).toContainText('Traspaso externo');
    await page.keyboard.press('Escape');
    // PIO: los internos en su sección (sin media); los externos, aparte.
    await page.locator('[data-cf-cuenta="PIO"]').click();
    await expect(page.locator('[data-cf-tabla="PIO"] [data-cf-seccion="traspasos"]')).toBeVisible();
    await expect(page.locator('[data-cf-tabla="PIO"] [data-cf-seccion="traspasos_externos"]')).toBeVisible();
    await expect(page.locator('[data-cf-eleccion]')).toHaveCount(0); // H7-REAL-9: sin selector «Media / Excel»
  });

  test('«Fuera de la previsión»: SL contada como cuenta fuera de la pantalla', async ({ page }) => {
    const f = page.locator('[data-cf-fuera]');
    await f.locator('summary').click();
    await expect(f.locator('[data-cf-fuera-item="cuentas-fuera"]')).toContainText('SL');
    await expect(f.locator('[data-cf-fuera-item="cuentas-fuera"]')).toContainText('sin filas en la importación vigente');
  });

  test('avisos y gráfico (captura)', async ({ page }) => {
    await page.evaluate(() => document.fonts.ready);
    await page.locator('#cf-avisos').screenshot({ path: join(CAPTURAS, 'pc1440_avisos.png') });
    await page.locator('[data-cf-grafico]').screenshot({ path: join(CAPTURAS, 'pc1440_grafico.png') });
  });
});

// H7-REAL-5: la tabla se desplaza dentro de su marco: cabecera fija arriba y primera columna fija a la izquierda.
test.describe('Cabecera y primera columna fijas (1440 × 900)', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  for (const escala of ['decenas', 'mes'] as const) {
    test(`${escala}: tras desplazar la tabla en vertical la cabecera sigue a la vista; en horizontal, la primera columna (PIO, RITA y Consolidado)`, async ({ page }) => {
      await entrar(page, '/cashflow');
      await expect(page.locator('[data-contrato-ok="cashflow"]')).toBeVisible();
      await page.locator(`[data-cf-escala="${escala}"]`).click();
      await expect(page.locator(`[data-cf-escala="${escala}"]`)).toHaveAttribute('aria-pressed', 'true');
      await expect(page.locator('[data-cf-columna]').first()).toHaveAttribute('data-cf-columna', escala === 'mes' ? '2026-08' : '2026-10-11');
      for (const vista of ['PIO', 'RITA', 'CONSOLIDADO'] as const) {
        await page.locator(`[data-cf-cuenta="${vista}"]`).click();
        const marco = page.locator('.cf-tabla-marco');
        await expect(page.locator(`[data-cf-tabla="${vista}"]`)).toBeVisible();
        // Desplegar todas las categorías: la tabla pasa de la altura del marco.
        const plegadas = page.locator('[data-cf-plegar][aria-expanded="false"]');
        for (let n = await plegadas.count(); n > 0; n = await plegadas.count()) await plegadas.first().click();
        // La página lleva el marco arriba de la ventana: cabe entero (altura ligada a la ventana).
        await marco.evaluate((el) => el.scrollIntoView({ block: 'start' }));
        const m = (await marco.boundingBox())!;
        expect(m.y).toBeGreaterThanOrEqual(-1);
        expect(m.y + m.height).toBeLessThanOrEqual(901);
        // Vertical.
        await marco.evaluate((el) => { el.scrollTop = 600; });
        expect(await marco.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
        const cab = (await page.locator('[data-cf-columna]').first().boundingBox())!;
        expect(cab.y).toBeGreaterThanOrEqual(m.y - 1);
        expect(cab.y + cab.height).toBeLessThanOrEqual(m.y + m.height);
        expect(cab.y - m.y).toBeLessThan(4); // pegada arriba del marco
        const esquina = (await page.locator('.cf-esquina').boundingBox())!;
        expect(Math.abs(esquina.y - m.y)).toBeLessThan(4);
        // La cabecera queda por encima de las filas (la esquina recibe el punto de su centro).
        expect(await page.evaluate(([x, y]) => !!document.elementFromPoint(x, y)?.closest('thead'), [cab.x + cab.width / 2, cab.y + cab.height / 2])).toBe(true);
        if (vista === 'CONSOLIDADO') {
          await page.evaluate(() => document.fonts.ready);
          await page.screenshot({ path: join(CAPTURAS, `pc1440x900_tabla_fija_${escala}.png`) });
        }
        // Horizontal (H7-REAL-6: con la letra mayor ya se desplaza también a 1440 px; aquí, a 1000 px).
        await page.setViewportSize({ width: 1000, height: 900 });
        await marco.evaluate((el) => el.scrollIntoView({ block: 'start' }));
        const m2 = (await marco.boundingBox())!;
        await marco.evaluate((el) => { el.scrollLeft = 400; el.scrollTop = 300; });
        expect(await marco.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0);
        // En el borde izquierdo del marco, a media altura, sigue la primera columna (nombre de categoría o concepto).
        const izq = await page.evaluate(([x, y]) => {
          const th = document.elementFromPoint(x, y)?.closest('tbody th');
          const b = th?.getBoundingClientRect();
          return b ? { x: b.x, ancho: b.width } : null;
        }, [m2.x + 20, m2.y + m2.height / 2]);
        expect(izq).not.toBeNull();
        expect(Math.abs((izq as { x: number }).x - m2.x)).toBeLessThan(4);
        // Y la cabecera también (la esquina, encima de las dos).
        expect(await page.evaluate(([x, y]) => !!document.elementFromPoint(x, y)?.closest('.cf-esquina'), [m2.x + 20, m2.y + 10])).toBe(true);
        if (vista === 'CONSOLIDADO') {
          await page.evaluate(() => document.fonts.ready);
          await page.screenshot({ path: join(CAPTURAS, `pc1000x900_tabla_fija_horizontal_${escala}.png`) });
        }
        await page.setViewportSize({ width: 1440, height: 900 });
        // El desglose de una cifra sigue abriéndose con la tabla desplazada.
        await marco.evaluate((el) => { el.scrollTop = 0; el.scrollLeft = 0; });
        const cifraBtn = page.locator('[data-cf-celda$="|*|' + (escala === 'mes' ? '2026-12' : '2026-12-01') + '"] button').first();
        await cifraBtn.evaluate((el) => el.scrollIntoView({ block: 'center', inline: 'center' }));
        await cifraBtn.click();
        await expect(page.locator('[data-cf-desglose]')).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(page.locator('[data-cf-desglose]')).toHaveCount(0);
      }
    });
  }
});

// H7-REAL-6: números más grandes. Tamaños calculados por el navegador (no reglas CSS): las variables de estilos_cashflow.css.
test.describe('Letra de Cashflow (1440 × 900)', () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  type Estilo = { tam: number; peso: number; tabular: boolean; alin: string };
  const estilo = (page: Page, sel: string) => page.locator(sel).first().evaluate((el): Estilo => {
    const s = getComputedStyle(el);
    return { tam: parseFloat(s.fontSize), peso: Number(s.fontWeight), tabular: s.fontVariantNumeric.includes('tabular-nums'), alin: s.textAlign };
  });

  for (const escala of ['decenas', 'mes'] as const) {
    test(`${escala}: tamaños de tabla, gráfico, indicador y avisos en PIO, RITA y Consolidado; a 1440 px, scroll horizontal con la primera columna fija`, async ({ page }) => {
      await entrar(page, '/cashflow');
      await expect(page.locator('[data-contrato-ok="cashflow"]')).toBeVisible();
      await page.locator(`[data-cf-escala="${escala}"]`).click();
      await expect(page.locator(`[data-cf-escala="${escala}"]`)).toHaveAttribute('aria-pressed', 'true');
      for (const vista of ['PIO', 'RITA', 'CONSOLIDADO'] as const) {
        await page.locator(`[data-cf-cuenta="${vista}"]`).click();
        const t = page.locator(`[data-cf-tabla="${vista}"]`);
        await expect(t).toBeVisible();
        const plegadas = page.locator('[data-cf-plegar][aria-expanded="false"]');
        for (let n = await plegadas.count(); n > 0; n = await plegadas.count()) await plegadas.first().click();
        // Cifras y nombres de concepto: 15 px; cifras tabulares, a la derecha.
        const cifra = await estilo(page, `[data-cf-tabla="${vista}"] .cf-concepto .cf-c .cf-num`);
        expect(cifra.tam).toBe(15);
        expect(cifra.tabular).toBe(true);
        expect(await estilo(page, `[data-cf-tabla="${vista}"] .cf-concepto .cf-c`).then((e) => e.alin)).toBe('right');
        expect((await estilo(page, `[data-cf-tabla="${vista}"] .cf-concepto-nombre`)).tam).toBe(15);
        expect((await estilo(page, `[data-cf-tabla="${vista}"] .cf-categoria .cf-num`)).tam).toBe(15);
        // Totales 16 px en negrita; saldo final 18 px en negrita.
        for (const tot of ['entradas', 'salidas', 'farmacia']) {
          const e = await estilo(page, `[data-cf-tabla="${vista}"] [data-cf-total="${tot}"] td .cf-num`);
          expect(e.tam).toBe(16);
          expect(e.peso).toBeGreaterThanOrEqual(700);
          expect(e.alin).toBe('right');
          expect((await estilo(page, `[data-cf-tabla="${vista}"] [data-cf-total="${tot}"] th`)).tam).toBe(16);
        }
        if (await t.locator('[data-cf-total="no_relacionadas"]').count()) expect((await estilo(page, `[data-cf-tabla="${vista}"] [data-cf-total="no_relacionadas"] td .cf-num`)).tam).toBe(16);
        if (await t.locator('[data-cf-total="traspasos_externos"]').count()) expect((await estilo(page, `[data-cf-tabla="${vista}"] [data-cf-total="traspasos_externos"] td .cf-num`)).tam).toBe(16);
        const s = await estilo(page, `[data-cf-tabla="${vista}"] [data-cf-saldo] .cf-num`);
        expect(s.tam).toBe(18);
        expect(s.peso).toBeGreaterThanOrEqual(700);
        expect(s.tabular).toBe(true);
        // Cabecera: decena o mes 15 px; año y Real/Previsto 13 px.
        expect((await estilo(page, `[data-cf-tabla="${vista}"] .cf-col-texto`)).tam).toBe(15);
        expect((await estilo(page, `[data-cf-tabla="${vista}"] .cf-col-anio`)).tam).toBe(13);
        expect((await estilo(page, `[data-cf-tabla="${vista}"] .cf-col-tipo`)).tam).toBe(13);
        // Secundarios: nunca por debajo de 12 px.
        for (const sel of ['.cf-sub', '.cf-marca-media', '.cf-dif', '.cf-eleccion button', '.cf-esquina', '.cf-seccion th']) {
          const n = await t.locator(sel).count();
          for (let i = 0; i < n; i++) expect(await t.locator(sel).nth(i).evaluate((el) => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(12);
        }
        // Gráfico: 14 px en pantalla (el dibujo va a 1 unidad = 1 px), leyenda 14 px.
        const g = page.locator('[data-cf-grafico]');
        const escalaSvg = await g.locator('svg').evaluate((el) => (el as SVGSVGElement).getBoundingClientRect().width / (el as SVGSVGElement).viewBox.baseVal.width);
        expect(Math.abs(escalaSvg - 1)).toBeLessThan(0.02);
        expect((await estilo(page, '[data-cf-grafico] .cf-eje')).tam).toBe(14);
        expect((await estilo(page, '[data-cf-grafico] .cf-leyenda')).tam).toBe(14);
        if (await g.locator('.cf-etiqueta').count()) expect((await estilo(page, '[data-cf-grafico] .cf-etiqueta')).tam).toBe(14);
        // Indicador 16 px, cifras en negrita; avisos de saldo 15 px.
        expect((await estilo(page, '[data-cf-indicador]')).tam).toBe(16);
        expect((await estilo(page, '[data-cf-indicador] strong')).peso).toBeGreaterThanOrEqual(700);
        expect((await estilo(page, '#cf-avisos .cf-aviso')).tam).toBe(15);
        // A 1440 px la tabla ya no cabe a lo ancho: se desplaza dentro de su marco, nunca la página.
        await sinDesbordar(page, 1440);
        const marco = page.locator('.cf-tabla-marco');
        const anchos = await marco.evaluate((el) => ({ total: el.scrollWidth, visible: el.clientWidth }));
        expect(anchos.total).toBeGreaterThan(anchos.visible);
        await marco.evaluate((el) => el.scrollIntoView({ block: 'start' }));
        await marco.evaluate((el) => { el.scrollLeft = el.scrollWidth; el.scrollTop = 0; });
        const m = (await marco.boundingBox())!;
        // A la altura de una fila de categoría (no de una de sección, que ocupa todo el ancho).
        const fila = (await page.locator(`[data-cf-tabla="${vista}"] .cf-categoria th`).nth(1).boundingBox())!;
        const izq = await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.closest('tbody th')?.getBoundingClientRect().x ?? null, [m.x + 20, fila.y + fila.height / 2]);
        expect(izq).not.toBeNull();
        expect(Math.abs((izq as number) - m.x)).toBeLessThan(4);
        // El desglose sigue abriéndose.
        const btn = page.locator(`[data-cf-tabla="${vista}"] [data-cf-celda$="|*|${escala === 'mes' ? '2026-12' : '2026-12-01'}"] button`).first();
        await btn.evaluate((el) => el.scrollIntoView({ block: 'center', inline: 'center' }));
        await btn.click();
        await expect(page.locator('[data-cf-desglose]')).toBeVisible();
        await page.keyboard.press('Escape');
        await marco.evaluate((el) => { el.scrollLeft = 0; el.scrollTop = 0; });
      }
      // Capturas (consolidado): tabla a 1440 × 900 y, en decenas, gráfico con indicador y tabla a 1000 × 900 desplazada.
      const marco = page.locator('.cf-tabla-marco');
      await marco.evaluate((el) => el.scrollIntoView({ block: 'start' }));
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: join(CAPTURAS, `pc1440x900_letra_tabla_${escala}.png`) });
      if (escala === 'decenas') {
        await page.mouse.move(0, 0);
        await page.locator('section[aria-labelledby="t-cf-grafico"]').scrollIntoViewIfNeeded();
        await page.mouse.move(0, 0);
        await page.locator('section[aria-labelledby="t-cf-grafico"]').screenshot({ path: join(CAPTURAS, 'pc1440x900_letra_grafico_indicador.png') });
        await page.setViewportSize({ width: 1000, height: 900 });
        await marco.evaluate((el) => el.scrollIntoView({ block: 'start' }));
        await marco.evaluate((el) => { el.scrollLeft = 500; el.scrollTop = 200; });
        expect(await marco.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0);
        await page.evaluate(() => document.fonts.ready);
        await page.screenshot({ path: join(CAPTURAS, 'pc1000x900_letra_tabla_horizontal.png') });
      }
    });
  }
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

// H7-REAL: la respuesta de FIXTURES (forma del contrato final) modificada en el navegador como la daría REAL. Nunca datos reales.
type Dto = { modo: string; importaciones: Record<string, unknown>[]; importes: unknown[]; saldos: Record<string, unknown>[] };
const ERROR_POSTERIOR = {
  importacion_id: 'c7000000-0000-4000-8000-000000000003', archivo_nombre: 'Cashflow 2026.xlsx', origen: 'NOCHE', estado: 'ERROR',
  detalle_error: 'HOJA_NO_ENCONTRADA:RITA', filas: null, importado_at: '2026-11-16T02:00:00.000Z', vigente: false,
};
async function simularReal(page: Page, cambiar: (j: Dto) => void) {
  await page.route('**/api/cashflow', async (r) => {
    const res = await r.fetch();
    const j = (await res.json()) as Dto;
    j.modo = 'REAL';
    cambiar(j);
    await r.fulfill({ response: res, json: j });
  });
}

// H7-REAL-7: equivalencias de concepto. Los alias de los fixtures están en 03/2026 (fuera de las columnas): aquí la
// respuesta de FIXTURES se modifica en el navegador para ponerlos en una decena visible (11–20/10/2026), con un cobro
// que compensa el cuadre. Nunca datos reales.
test.describe('Equivalencias de concepto (1440 × 900)', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('JNTL CONSUMER… + JHONSON & JHONSON en la misma decena: una fila KENVUE con la suma; el popup dice qué incluye', async ({ page }) => {
    await page.route('**/api/cashflow', async (r) => {
      const res = await r.fetch();
      const j = (await res.json()) as { importes: Record<string, unknown>[] };
      const base = j.importes.find((f) => f.cuenta === 'PIO' && f.decena_inicio === '2026-10-11') as Record<string, unknown>;
      const mas = (id: string, categoria: string, concepto: string, importe: number) => ({ ...base, id, categoria, concepto, importe });
      j.importes.push(mas('e2e-1', 'RS Proveedores', 'JNTL CONSUMER (ORALDINE) S.L.', 300), mas('e2e-2', 'RS Proveedores', 'JHONSON & JHONSON', 200),
        mas('e2e-3', 'RE Otros cobros', 'Compensación de la prueba', 500));
      await r.fulfill({ response: res, json: j });
    });
    await entrar(page, '/cashflow');
    await expect(page.locator('[data-contrato-ok="cashflow"]')).toBeVisible();
    await page.locator('[data-cf-cuenta="PIO"]').click();
    const t = page.locator('[data-cf-tabla="PIO"]');
    await t.locator('[data-cf-plegar="RS Proveedores"]').click();
    await expect(t.locator('[data-cf-concepto="KENVUE"]')).toHaveCount(1);
    await expect(t.locator('[data-cf-concepto^="JNTL"], [data-cf-concepto^="JHONSON"]')).toHaveCount(0);
    const c = celda(page, 'RS Proveedores|KENVUE|2026-10-11');
    await expect(c).toContainText('−500');
    await c.locator('button').evaluate((el) => el.scrollIntoView({ block: 'center', inline: 'center' }));
    await c.locator('button').click();
    const inc = page.locator('[data-cf-desglose] [data-cf-incluye]');
    await expect(inc).toHaveText('Incluye: JHONSON & JHONSON, JNTL CONSUMER (ORALDINE) S.L. (mismo proveedor en el Excel con otro nombre).');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_kenvue_incluye.png') });
  });
});

// H7-REAL-8/9: vencimientos mayores que la previsión base. Los fixtures de H6 solo tienen un vencimiento futuro con
// correspondencia (ALLIANCE 472,22, menor que su media de 6.000): aquí ese vencimiento sube a 7.000 € en la respuesta de
// FIXTURES, modificada en el navegador. Nunca datos reales.
test.describe('Vencimientos frente a la previsión base (1440 × 900)', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('vencimientos (7.000) mayores que la previsión base (media 6.000 > Excel 520): ganan los vencimientos y el popup da la otra cifra', async ({ page }) => {
    await page.route('**/api/cashflow', async (r) => {
      const res = await r.fetch();
      const j = (await res.json()) as { vencimientos: Record<string, unknown>[] };
      for (const v of j.vencimientos) if (v.vencimiento_id === '90000000-0000-4000-8000-000000000002') v.importe = 7000;
      await r.fulfill({ response: res, json: j });
    });
    await entrar(page, '/cashflow');
    await expect(page.locator('[data-contrato-ok="cashflow"]')).toBeVisible();
    await page.locator('[data-cf-cuenta="PIO"]').click();
    await page.locator('[data-cf-plegar="RS Proveedores"]').click();
    const c = celda(page, 'RS Proveedores|ALLIANCE|2026-11-11');
    await expect(c).toHaveAttribute('data-cf-fuente', 'vencimientos');
    await expect(c).toContainText('−7.000');
    await c.locator('button').evaluate((el) => el.scrollIntoView({ block: 'center', inline: 'center' }));
    await c.locator('button').click();
    const d = page.locator('[data-cf-desglose]');
    await expect(d.locator('[data-cf-venc-ganan="media"]')).toHaveText('Ganan los vencimientos: media del concepto 6.000,00 € (inferior a los vencimientos).');
    await expect(d.locator('[data-cf-frente="media"]')).toHaveText('Excel 520,00 € (inferior a la media) → media 6.000,00 €.');
    await expect(d.locator('[data-cf-venc-minimo]')).toHaveCount(0);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_venc_ganan_excel.png') });
  });
});

test.describe('REAL simulado', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('sin importación vigente (solo una ERROR): «Todavía no hay datos importados», aviso gris con su fecha y detalle, sin cifras ni 503', async ({ page }) => {
    await simularReal(page, (j) => { j.importaciones = [ERROR_POSTERIOR]; j.importes = []; j.saldos = []; });
    await entrar(page, '/cashflow');
    const p = page.locator('[data-cf-sin-datos]');
    await expect(p).toBeVisible();
    await expect(p.getByRole('heading')).toHaveText('Todavía no hay datos importados');
    const g = page.locator('[data-cf-aviso="gris"][data-codigo="IMPORTACION_FALLIDA"]');
    await expect(g).toContainText('La última importación del Excel falló');
    await expect(g).toContainText('16/11/2026');
    await expect(g.locator('[data-cf-detalle-error]')).toHaveText('HOJA_NO_ENCONTRADA:RITA');
    await expect(g).toContainText('No hay ninguna importación vigente');
    await expect(page.locator('[data-cf-aviso="gris"]')).toHaveCount(1);
    await expect(page.locator('[data-cf-tabla]')).toHaveCount(0);
    await expect(page.locator('[data-cf-resumen]')).toHaveCount(0);
    await expect(page.locator('[data-banner-cashflow]')).toHaveCount(0);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_real_sin_datos.png') });
  });

  test('ERROR posterior a la vigente y decena que no cuadra: avisos grises; se sigue mostrando la vigente; «no cuadra» en el saldo y su desglose', async ({ page }) => {
    await simularReal(page, (j) => {
      j.importaciones = [ERROR_POSTERIOR, ...j.importaciones];
      const s = j.saldos.find((x) => x.cuenta === 'PIO' && x.decena_inicio === '2026-11-11')!;
      s.saldo_formulas = Math.round(((s.saldo_formulas as number) + 10) * 100) / 100;
    });
    await entrar(page, '/cashflow');
    await expect(page.locator('[data-contrato-ok="cashflow"]')).toBeVisible();
    const fallida = page.locator('[data-cf-aviso="gris"][data-codigo="IMPORTACION_FALLIDA"]');
    await expect(fallida).toContainText('Se siguen mostrando los datos de la vigente');
    await expect(fallida.locator('[data-cf-detalle-error]')).toHaveText('HOJA_NO_ENCONTRADA:RITA');
    const cuadre = page.locator('[data-cf-aviso="gris"][data-codigo="IMPORTACION_NO_CUADRA"]');
    await expect(cuadre).toHaveCount(1);
    await expect(cuadre).toContainText('Datos de la importación no cuadran en PIO, 11–20 nov 2026');
    // La vigente se sigue usando: mismos saldos que en FIXTURES (no se recalcula nada).
    await expect(page.locator('[data-cf-saldo-actual="PIO"] .cf-ficha-cifra')).toHaveText('25.000,00 €');
    await page.locator('[data-cf-cuenta="PIO"]').click();
    await expect(saldo(page, '2026-11-11')).toHaveText('22.262');
    await expect(page.locator('[data-cf-saldo="2026-11-11"] [data-cf-no-cuadra]')).toHaveText('no cuadra');
    await page.locator('button:has([data-cf-saldo="2026-11-11"])').click();
    const d = page.locator('[data-cf-desglose="saldo"]');
    await expect(d.locator('[data-cf-cuadre="no-cuadra"]')).toBeVisible();
    await expect(d.locator('[data-cf-no-cuadra-detalle]')).toContainText('10,00');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_real_no_cuadra.png') });
    await page.keyboard.press('Escape');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_real_avisos_grises.png') });
  });
});
