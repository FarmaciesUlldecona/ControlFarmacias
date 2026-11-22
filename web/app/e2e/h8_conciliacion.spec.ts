// H8: pantalla Conciliación (doble comprobación por factura). Cuatro pestañas en la URL, enlaces, grupo de la noche en
// Doble comprobación y Albaranes, acciones deshabilitadas y móvil 390 sin desbordar. Solo FIXTURES.
import { expect, test, type Page } from '@playwright/test';
import { join } from 'node:path';
import { entrar } from './sesion.ts';

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'h8');
const F = (n: number) => `f0000000-0000-4000-8000-0000000000${String(n).padStart(2, '0')}`;

test.beforeEach(async ({ page }) => entrar(page));

async function abrir(page: Page, consulta = '') {
  await page.goto(`/conciliacion${consulta}`);
  await expect(page.locator('[data-contrato-ok="conciliacionBandeja"]')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}
const fila = (page: Page, n: number) => page.locator(`tr[data-factura="${F(n)}"]`);

/**
 * H8-4: margen interior (px) del contenido del filtro respecto de su tarjeta y del nombre del proveedor (`sel`) respecto
 * de la suya: deben coincidir.
 */
async function margenes(page: Page, sel: string): Promise<{ filtro: number; tabla: number }> {
  return page.evaluate((s) => {
    const izq = (el: Element) => { const r = document.createRange(); r.selectNodeContents(el); return r.getBoundingClientRect().left; };
    const filtros = document.querySelector('.filtros')!;
    const nombre = document.querySelector(s)!;
    return {
      filtro: izq(filtros.querySelector('label, select')!) - filtros.getBoundingClientRect().left,
      tabla: izq(nombre) - nombre.closest('.tarjeta')!.getBoundingClientRect().left,
    };
  }, sel);
}

test.describe('PC 1440', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('Doble comprobación (por defecto): marcas, banco gris, resumen en €, grupo de la noche e indicador «revisar (noche)»', async ({ page }) => {
    await abrir(page);
    await expect(page.locator('[data-pestana="doble"]')).toHaveAttribute('aria-selected', 'true');
    // Acciones visibles y deshabilitadas.
    for (const b of ['Reintentar conciliación', 'Cerrar con justificación']) {
      await expect(page.getByRole('button', { name: b })).toBeDisabled();
      await expect(page.getByRole('button', { name: b })).toHaveAttribute('title', 'Disponible en una fase posterior');
    }
    await expect(page.getByText('En construcción')).toHaveCount(0);
    // Resumen: verificado doble 0 (sin banco); sin importe fuera de totales.
    await expect(page.locator('[data-tramo="verificado_doble"] [data-tramo-importe]')).toHaveText('0,00 €');
    await expect(page.locator('[data-tramo="verificado_doble"]')).toContainText('0 facturas');
    await expect(page.locator('[data-tramo="solo_albaranes"]')).toContainText('3 facturas');
    await expect(page.locator('[data-sin-importe-doble]')).toContainText('1 factura sin importe, fuera de los totales');
    // Grupo de la noche encima de la lista.
    await expect(page.locator('[data-revisar-noche]')).toBeVisible();
    // Una fila por factura con las cuatro marcas.
    await expect(page.locator('tr[data-factura]')).toHaveCount(8);
    await expect(fila(page, 2).locator('[data-marca-albaranes]')).toHaveText('✓conciliada');
    await expect(fila(page, 2).locator('[data-diferencia-motor]')).toHaveText('dif. 0,07 €');
    await expect(fila(page, 3).locator('[data-marca-albaranes]')).toHaveText('✗con diferencia');
    await expect(fila(page, 3).locator('[data-diferencia-motor]')).toHaveText('dif. 41,90 €');
    await expect(fila(page, 6).locator('[data-marca-albaranes]')).toHaveText('○pendiente');
    await expect(fila(page, 5).locator('[data-marca-albaranes]')).toHaveText('!en revisión');
    await expect(fila(page, 7).locator('[data-marca-albaranes]')).toHaveText('✗no se puede comprobar');
    await expect(page.locator('[data-marca-banco="SIN_DATOS_BANCARIOS"]')).toHaveCount(8);
    await expect(fila(page, 1).locator('[data-marca-banco]')).toHaveText('○sin datos bancarios');
    // «revisar (noche)» en las facturas de la lista de la última noche (F03, F06, F07, F08), en naranja.
    await expect(page.locator('[data-indicador-noche]')).toHaveCount(4);
    await expect(fila(page, 8).locator('[data-indicador-noche]')).toHaveClass(/\bo\b/);
    await expect(fila(page, 1).locator('[data-indicador-noche]')).toHaveCount(0);
    // Próximo vencimiento y enlace al detalle.
    await expect(fila(page, 3).locator('[data-vencimiento-proximo]')).toHaveText('14/11/2026');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_conciliacion_doble.png'), fullPage: true });
    await fila(page, 3).getByRole('link', { name: 'CF-2026-55810' }).click();
    await expect(page).toHaveURL(new RegExp(`/facturas/${F(3)}$`));
  });

  test('Doble comprobación: filtros en la URL (proveedor, estado, búsqueda) y «Quitar filtros»', async ({ page }) => {
    await abrir(page, '?estado=PENDIENTE');
    await expect(page.locator('tr[data-factura]')).toHaveCount(2);
    await page.getByRole('combobox', { name: 'Albaranes' }).selectOption('noche');
    await expect(page).toHaveURL(/estado=noche/);
    await expect(page.locator('tr[data-factura]')).toHaveCount(4);
    await page.getByRole('combobox', { name: 'Albaranes' }).selectOption('');
    await page.getByRole('searchbox', { name: 'Buscar' }).fill('375,15');
    await expect(page).toHaveURL(/q=375%2C15/);
    await expect(page.locator('tr[data-factura]')).toHaveCount(1);
    await page.getByRole('button', { name: 'Quitar filtros' }).click();
    await expect(page.locator('tr[data-factura]')).toHaveCount(8);
    const opcion = await page.getByRole('combobox', { name: 'Proveedor' }).locator('option').nth(1).getAttribute('value');
    await page.getByRole('combobox', { name: 'Proveedor' }).selectOption(opcion as string);
    await expect(page).toHaveURL(/proveedor=/);
    expect(await page.locator('tr[data-factura]').count()).toBeLessThan(8);
    // La pestaña también vive en la URL y se conserva al recargar.
    await page.locator('[data-pestana="albaranes"]').click();
    await expect(page).toHaveURL(/pestana=albaranes/);
    await page.reload();
    await expect(page.locator('[data-panel="albaranes"]')).toBeVisible();
  });

  test('Albaranes: cabecera, cobertura por proveedor con «sin lector», grupo de la noche, bandeja por riesgo con «se cobra el» y alertas', async ({ page }) => {
    await abrir(page, '?pestana=albaranes');
    await expect(page.locator('[data-cifra="conciliadas"]')).toContainText('3');
    await expect(page.locator('[data-cifra="pendientes"]')).toContainText('4');
    await expect(page.locator('[data-cifra="revision"]')).toContainText('1');
    await expect(page.locator('[data-cifra="cobertura"]')).toContainText('conciliados de');
    await expect(page.locator('[data-sin-lector]')).toHaveCount(3);
    // H8-5: una fila por nombre: COFARES con su cobertura y, en la misma fila, sus albaranes pendientes de Farmatic;
    // HPLUS CONSUMO (Farmatic) va en la fila HEFAME. Sin nombres repetidos.
    const nombresCob = await page.locator('[data-cobertura-proveedor] .cc-cob-nombre').allTextContents();
    expect(new Set(nombresCob).size, nombresCob.join(' | ')).toBe(nombresCob.length);
    const filaCof = page.locator('[data-cobertura-proveedor]').filter({ hasText: 'COFARES' });
    await expect(filaCof).toHaveCount(1);
    await expect(filaCof.locator('[data-cobertura-pendientes]')).toHaveText('Además, 6 albaranes en Farmatic sin factura, pendientes de automatizar · 742,10 €');
    await expect(filaCof.locator('[data-sin-lector]')).toHaveCount(0);
    await expect(page.locator('[data-cobertura-proveedor]').filter({ hasText: 'HEFAME' }).locator('[data-cobertura-pendientes]')).toHaveAttribute('data-cobertura-pendientes', '3');
    await expect(page.locator('[data-revisar-noche]')).toBeVisible();
    // Bandeja: facturas no conciliadas por dinero en riesgo (vencimiento más próximo primero).
    const orden = await page.locator('[data-bandeja-factura]').evaluateAll((xs) => xs.map((x) => x.getAttribute('data-bandeja-factura')?.slice(-2)));
    expect(orden).toEqual(['08', '05', '03', '07', '06']);
    await expect(page.locator(`[data-bandeja-factura="${F(3)}"]`).locator('xpath=ancestor::*[@data-motivo][1]')).toHaveAttribute('data-motivo', 'NO_LOCALIZADO');
    await expect(page.locator('[data-motivo="NO_LOCALIZADO"]').first()).toContainText('Albarán no localizado en Farmatic');
    const cobra = page.locator(`[data-bandeja-factura="${F(3)}"] [data-se-cobra]`);
    await expect(cobra).toHaveText('se cobra el 14/11');
    await expect(cobra).toHaveAttribute('href', '/vencimientos?vista=dia&fecha=2026-11-14');
    // Alertas con su detalle completo.
    await expect(page.locator('[data-alerta="POSIBLE_DUPLICADO_FARMATIC"]')).toHaveCount(1);
    await expect(page.locator('[data-alerta="ALBARAN_FACTURADO_NO_EN_FARMATIC"]')).toHaveCount(1);
    await expect(page.locator('[data-alerta="CORRECCION_APROBADA"]')).toHaveCount(2);
    const dup = page.locator('[data-alerta="POSIBLE_DUPLICADO_FARMATIC"]');
    await dup.locator('[data-alerta-detalle] summary').click();
    await expect(dup.locator('[data-alerta-detalle]')).toContainText('regla: B: mismo proveedor');
    await page.evaluate(() => window.scrollTo(0, 0)); // la captura de página completa, desde arriba (lateral fijo)
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_conciliacion_albaranes.png'), fullPage: true });
    await cobra.click();
    await expect(page).toHaveURL(/\/vencimientos\?vista=dia&fecha=2026-11-14$/);
  });

  test('H8-4: Doble comprobación: el nombre del proveedor con el mismo margen que el filtro', async ({ page }) => {
    await abrir(page);
    const m = await margenes(page, 'tr[data-factura] td.proveedor');
    expect(Math.abs(m.tabla - m.filtro), JSON.stringify(m)).toBeLessThanOrEqual(1);
  });

  test('Sin factura: alerta (con conciliación automática) → leído sin conciliación → pendiente de automatizar → traspasos; ausentes excluidos', async ({ page }) => {
    await abrir(page, '?pestana=sin-factura');
    await expect(page.locator('[data-pestana="sin-factura"] .pestana-n')).toHaveText('2');
    // H8-2/H8-4: orden de grupos: alerta, leído sin conciliación, pendiente de automatizar, traspasos entre farmacias.
    const orden = await page.locator('[data-sf-alertas], [data-sf-leido], [data-sf-sin-lector], [data-sf-traspasos]').evaluateAll((xs) =>
      xs.map((x) => (x.hasAttribute('data-sf-alertas') ? 'alerta' : x.hasAttribute('data-sf-leido') ? 'leido'
        : x.hasAttribute('data-sf-traspasos') ? 'traspasos' : 'pendiente')));
    expect(orden).toEqual(['alerta', 'leido', 'pendiente', 'traspasos']);
    await expect(page.locator('[data-sf-ausentes]')).toHaveText('2 excluidos por no estar ya en Farmatic (130,50 €).');
    const leido = page.locator('[data-sf-leido]');
    await expect(leido.locator('[data-sf-leido-proveedor="4"]')).toContainText('FEDEFARMA');
    await expect(leido.locator('[data-sf-leido-proveedor="4"]')).toContainText('3 albaranes');
    await expect(leido.locator('[data-sf-leido-proveedor="4"]')).toContainText('455,00 €');
    await expect(leido.locator('[data-antiguedad]')).toHaveCount(0); // nunca alerta
    const al = page.locator('[data-sf-alertas]');
    await expect(al.locator('[data-sf-total-alertas]')).toHaveText('2 albaranes · 84,30 € (1 sin importe)');
    await expect(al.locator('[data-sf-proveedor]')).toHaveCount(1);
    await expect(al).not.toContainText('FD-ALB-3301');
    // H8-5: plegado por defecto; se abre al pulsar la cabecera.
    await expect(al.locator('[data-sf-proveedor="1"] [data-sf-albaran="77501"]')).toBeHidden();
    await al.locator('[data-sf-proveedor="1"] summary').click();
    await expect(al.locator('[data-sf-proveedor="1"] [data-sf-albaran="77501"]')).toBeVisible();
    await expect(al.locator('[data-sf-albaran="77501"] [data-antiguedad]')).toHaveText('51 días');
    await expect(al.locator('[data-sf-albaran="77502"]')).toContainText('no consta');
    await expect(al.locator('[data-sf-albaran="77510"]')).toHaveCount(0); // 8 días: en plazo
    // H8-4: nombre comercial (1.- SAFA → ALLIANCE, 3.- HEFAME → HEFAME) y desde = primer albarán conciliado.
    await expect(al.locator('[data-sf-anteriores="2"]')).toHaveText('ALLIANCE: 412 albaranes anteriores a su primer albarán conciliado (06/10/2026), sin alerta');
    await expect(al.locator('[data-sf-anteriores="9"]')).toContainText('HEFAME: 134 albaranes anteriores');
    await expect(al).not.toContainText(/\d+\.- /);
    const gris = page.locator('[data-sf-sin-lector]');
    await expect(gris.locator('[data-sf-gris]')).toHaveCount(5);
    // H8-5: HPLUS CONSUMO se muestra como HEFAME, con el literal real debajo.
    await expect(gris.locator('[data-sf-gris="42"] [data-sf-nombre]')).toContainText('HEFAME');
    await expect(gris.locator('[data-sf-gris="42"] [data-sf-literal]')).toHaveText('HPLUS CONSUMO');
    await expect(gris.locator('[data-sf-gris="37"]')).toContainText('LABORATORIOS ISDIN (FICTICIO)');
    await expect(gris).not.toContainText(/\d+\.- |RITA/);
    await expect(gris.locator('[data-sf-gris="sin_identificar"]')).toContainText('proveedor no determinado con certeza');
    // H8-4: traspasos entre farmacias, gris aparte, nunca alerta.
    const tr = page.locator('[data-sf-traspasos]');
    await expect(tr.locator('h2')).toHaveText('Traspasos entre farmacias (sin factura)');
    await expect(tr.locator('[data-sf-traspaso="RITA"]')).toContainText('FFARMACIA RITA');
    await expect(tr.locator('[data-sf-traspaso="RITA"]')).toContainText('12 albaranes');
    await expect(tr.locator('[data-sf-traspaso="RITA"]')).toContainText('1.840,00 €');
    await expect(tr.locator('[data-antiguedad]')).toHaveCount(0);
    // H8-3: total (más de 50) y su reparto por grupo, que suma el total; sin poder comprobar (naranja) y anteriores de leído.
    await expect(page.locator('[data-sf-total]')).toHaveAttribute('data-sf-total', '608');
    await expect(page.locator('[data-sf-total]')).toHaveText('En total, 608 albaranes sin reservar (54.933,45 €): 2 en alerta, 2 en plazo, '
      + '546 anteriores al primer albarán conciliado, 1 sin poder comprobar, 9 leídos sin conciliación automática, 34 pendientes de automatizar, '
      + '12 traspasos entre farmacias, 2 excluidos.');
    const sd = al.locator('[data-sf-sin-desde="7"]');
    await expect(sd.locator('[data-sf-nombre]')).toHaveText('LOGISTAPHARMA');
    await expect(sd.locator('[data-sf-n]')).toHaveText('1 albarán');
    await expect(sd.locator('[data-sf-importe]')).toHaveText('23,40 €');
    await expect(sd.locator('[data-sf-estado]')).toHaveText('sin poder comprobar');
    await expect(sd.locator('[data-sf-sin-desde-nota]')).toContainText('Revísalo');
    await expect(leido.locator('[data-sf-leido-anteriores="6"]')).toContainText('6 albaranes anteriores (512,80 €)');
    await expect(page.locator('[data-sf-truncado]')).toHaveCount(0);
    await expect(gris.locator('[data-antiguedad]')).toHaveCount(0); // nunca alerta
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_conciliacion_sin_factura.png'), fullPage: true });
  });

  test('H8-4: sin alertas pero con albaranes sin poder comprobar: «Ninguno en alerta; N sin poder comprobar»', async ({ page }) => {
    // Respuesta FIXTURES con las alertas quitadas (solo en este test): queda LOGISTAPHARMA sin poder comprobar.
    await page.route('**/api/conciliacion', async (ruta) => {
      const r = await ruta.fetch();
      const d = await r.json();
      const sf = d.datos?.sin_factura ?? d.sin_factura;
      for (const p of sf.con_lector) { p.alertas = []; p.alertas_total = 0; p.importe_alertas = null; p.alertas_sin_importe = 0; }
      sf.grupos.AUTO_ALERTA = { albaranes: 0, importe: null, sin_importe: 0 };
      sf.totales.alertas = 0; sf.totales.importe_alertas = null; sf.totales.alertas_sin_importe = 0;
      await ruta.fulfill({ response: r, json: d });
    });
    await abrir(page, '?pestana=sin-factura');
    await expect(page.locator('[data-sf-vacio]')).toHaveText('Ninguno en alerta; 1 sin poder comprobar.');
    await expect(page.locator('[data-sf-alertas]')).not.toContainText('pasa de 30 días');
  });

  test('H8-5: Sin factura: cada proveedor es un desplegable plegado con nombre, nº, importe, antigüedad y estado; al abrir, su detalle', async ({ page }) => {
    await abrir(page, '?pestana=sin-factura');
    const ds = page.locator('details[data-sf-desplegable]');
    await expect(ds).toHaveCount(9); // alerta 1, sin poder comprobar 1, leído 1, pendiente 5, traspasos 1
    expect(await ds.evaluateAll((xs) => xs.filter((x) => (x as HTMLDetailsElement).open).length)).toBe(0);
    // Estado por grupo: naranja solo alerta y sin poder comprobar; el resto gris.
    const estados = await page.locator('[data-sf-estado]').evaluateAll((xs) => xs.map((x) => `${x.getAttribute('data-sf-estado')}:${x.classList.contains('o') ? 'o' : 'n'}`));
    expect(estados).toEqual(['alerta:o', 'sin-desde:o', 'leido:n', 'pendiente:n', 'pendiente:n', 'pendiente:n', 'pendiente:n', 'pendiente:n', 'traspaso:n']);
    // Cabecera de ISDIN: 18 albaranes, 2.430,55 €, el más antiguo de 37 días, «pendiente de automatizar».
    const isdin = page.locator('[data-sf-gris="37"]');
    await expect(isdin.locator('summary')).toBeVisible();
    await expect(isdin.locator('[data-sf-n]')).toHaveText('18 albaranes');
    await expect(isdin.locator('[data-sf-importe]')).toHaveText('2.430,55 €');
    await expect(isdin.locator('[data-sf-mas-antiguo]')).toHaveText('el más antiguo, de 37 días');
    await expect(isdin.locator('[data-sf-estado]')).toHaveText('pendiente de automatizar');
    await expect(isdin.locator('tr[data-sf-albaran]').first()).toBeHidden();
    await isdin.locator('summary').click();
    await expect(isdin.locator('tr[data-sf-albaran]')).toHaveCount(18);
    await expect(isdin.locator('tr[data-sf-albaran]').first()).toHaveAttribute('data-sf-albaran', 'IS-001');
    await expect(isdin.locator('[data-antiguedad]')).toHaveCount(0); // gris: la antigüedad, sin insignia de alerta
    await expect(isdin.locator('[data-dias="37"]')).toHaveText('37 días');
    // Leído, traspasos y sin poder comprobar también se despliegan con su detalle.
    const fed = page.locator('[data-sf-leido-proveedor="4"]');
    await fed.locator('summary').click();
    await expect(fed.locator('tr[data-sf-albaran]')).toHaveText([/FD-ALB-3301/, /FD-ALB-3302/, /FD-ALB-3303/]);
    const rita = page.locator('[data-sf-traspaso="RITA"]');
    await rita.locator('summary').click();
    await expect(rita.locator('tr[data-sf-albaran]')).toHaveCount(12);
    await page.locator('[data-sf-sin-desde="7"] summary').click();
    await expect(page.locator('[data-sf-sin-desde="7"] tr[data-sf-albaran="LG-26-0141"]')).toBeVisible();
    // Se vuelve a plegar.
    await isdin.locator('summary').click();
    await expect(isdin.locator('tr[data-sf-albaran]').first()).toBeHidden();
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_sin_factura_desplegables.png'), fullPage: true });
  });

  test('Banco: aviso «Pendiente: conciliación bancaria (Norma 43)» con lo que hará; sin datos', async ({ page }) => {
    await abrir(page, '?pestana=banco');
    const b = page.locator('[data-banco-pendiente]');
    await expect(b.getByRole('heading', { level: 2 })).toHaveText('Pendiente: conciliación bancaria (Norma 43)');
    await expect(b.locator('li')).toHaveCount(3);
    await expect(page.locator('[data-revisar-noche]')).toHaveCount(0);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_conciliacion_banco.png'), fullPage: true });
  });

  test('Inicio: alertas y grupo de la noche solo como recuento con enlace a Conciliación', async ({ page }) => {
    await page.goto('/');
    const a = page.locator('[data-alertas-inicio]');
    await expect(a).toHaveAttribute('data-alertas-inicio', '4');
    await expect(a).toContainText('1 duplicado en Farmatic · 1 albarán facturado que ya no está en Farmatic · 2 correcciones aprobadas');
    await expect(page.locator('[data-grupo="DUPLICADO_FARMATIC"], [data-grupo="ALBARAN_NO_EN_FARMATIC"], [data-grupo="CORRECCION_APROBADA"]')).toHaveCount(0);
    await a.getByRole('link', { name: 'Ver en Conciliación' }).click();
    await expect(page).toHaveURL(/\/conciliacion\?pestana=albaranes$/);
    await expect(page.locator('#alertas')).toBeVisible();
  });
});

test.describe('Móvil 390', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('H8-4: Doble comprobación: el nombre del proveedor de la tarjeta con el mismo margen que el filtro', async ({ page }) => {
    await abrir(page);
    const m = await margenes(page, '.cc-tarjeta .cc-tarjeta-cabecera > :first-child');
    expect(Math.abs(m.tabla - m.filtro), JSON.stringify(m)).toBeLessThanOrEqual(1);
  });

  test('H8-5: Sin factura: desplegables legibles en móvil, sin desbordar, abiertos y cerrados', async ({ page }) => {
    await abrir(page, '?pestana=sin-factura');
    const isdin = page.locator('[data-sf-gris="37"]');
    await isdin.scrollIntoViewIfNeeded();
    for (const sel of ['[data-sf-nombre]', '[data-sf-n]', '[data-sf-importe]', '[data-sf-mas-antiguo]', '[data-sf-estado]']) await expect(isdin.locator(sel)).toBeVisible();
    await isdin.locator('summary').click();
    await expect(isdin.locator('tr[data-sf-albaran]').first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_sin_factura_desplegable.png'), fullPage: true });
  });

  test('las cuatro pestañas sin desplazamiento horizontal; tarjetas con las dos marcas', async ({ page }) => {
    for (const p of ['doble', 'albaranes', 'sin-factura', 'banco']) {
      await abrir(page, p === 'doble' ? '' : `?pestana=${p}`);
      await expect(page.locator(`[data-panel="${p}"]`)).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), p).toBe(true);
      // Las cuatro pestañas a la vista (sin desplazamiento lateral escondido).
      for (const t of ['doble', 'albaranes', 'sin-factura', 'banco']) await expect(page.locator(`[data-pestana="${t}"]`)).toBeInViewport({ ratio: 1 });
      if (p === 'doble') {
        await expect(page.locator('.cc-tarjeta')).toHaveCount(8);
        await expect(page.locator('.cc-tarjeta [data-marca-banco]')).toHaveCount(8);
        await page.screenshot({ path: join(CAPTURAS, 'movil390_conciliacion_doble.png'), fullPage: true });
      }
      if (p === 'albaranes') await page.screenshot({ path: join(CAPTURAS, 'movil390_conciliacion_albaranes.png'), fullPage: true });
      if (p === 'sin-factura') await page.screenshot({ path: join(CAPTURAS, 'movil390_conciliacion_sin_factura.png'), fullPage: true });
    }
  });
});
