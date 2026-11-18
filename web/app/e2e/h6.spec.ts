// H6: pantalla Vencimientos. Lista con estado de pago, filtros, totales, marcar varios, confirmar domiciliados, anular,
// forma de pago por proveedor y modo REAL sin credencial de pagos (simulado interceptando la API). Solo FIXTURES
// (playwright.config.ts lo exige). Fecha de referencia de FIXTURES: lunes 16/11/2026.
// H6-REAL: el vencimiento viaja como (factura_id, orden); sin importe no se marca (mensaje llano); «a revisar» y huérfanas.
// El servidor es común: después de cada prueba se deja todo como en la semilla (afterEach).
import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { entrar } from './sesion.ts';
import {
  MENSAJE_FALTA_CREDENCIAL_PAGOS, claveVencimiento, construirPantalla, crearAlmacenPagos, type MarcaPago, type PantallaVencimientosDTO,
} from '../server/pagos/pagos.ts';
import { leerSemillaPagos } from '../server/pagos/rutas.ts';
import { DIR_DTO } from '../server/adaptador_fixtures.ts';

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'h6');
const ORIGEN = 'http://127.0.0.1:5181';
const V = (n: number) => `90000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const filas = (page: Page) => page.locator('tr[data-vencimiento]');
const contador = (page: Page, e: string) => page.locator(`[data-filtro-estado="${e}"] .ve-estado-n`);

async function api(page: Page, method: 'POST' | 'PUT', url: string, data: unknown) {
  const r = await page.request.fetch(url, { method, data, headers: { origin: ORIGEN, 'content-type': 'application/json' } });
  expect(r.ok(), `${method} ${url}: ${r.status()} ${await r.text()}`).toBe(true);
  return r;
}

/** Vuelve a la semilla: anula las marcas nuevas, repone la de Hefame (V7) y las formas configuradas. */
async function restaurar(page: Page) {
  const d = (await (await page.request.get('/api/pagos/vencimientos')).json()) as PantallaVencimientosDTO;
  for (const f of d.filas) {
    if (f.marca && f.vencimiento_id !== V(7)) await api(page, 'PUT', `/api/pagos/marcas/${f.marca.marca_id}/anular`, { confirmar: true });
  }
  if (!d.filas.find((f) => f.vencimiento_id === V(7))?.marca) {
    await api(page, 'POST', '/api/pagos/marcas', { vencimientos: [{ factura_id: 'f0000000-0000-4000-8000-000000000005', orden: 1 }], fecha_pago: '2026-11-09', forma: 'TRANSFERENCIA' });
  }
  const forma = (cif: string) => d.proveedores.find((p) => p.cif === cif);
  if (!forma('A00000001')?.por_defecto) await api(page, 'PUT', '/api/pagos/formas/A00000001', { forma: null });
  for (const cif of ['B00000003', 'F30004444']) if (forma(cif)?.forma !== 'TRANSFERENCIA') await api(page, 'PUT', `/api/pagos/formas/${cif}`, { forma: 'TRANSFERENCIA' });
}

test.describe('PC 1440', () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  test.beforeEach(async ({ page }) => entrar(page, '/vencimientos'));
  test.afterEach(async ({ page }) => restaurar(page));

  test('lista: una fila por vencimiento con estado, forma y sentido; importe pendiente fuera de totales con recuento; enlace al detalle', async ({ page }) => {
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Vencimientos');
    await expect(page.locator('[data-contrato-ok="vencimientos"]')).toBeVisible();
    await expect(page.locator('.subtitulo')).toContainText('13 vencimientos de PIO · referencia: lunes 16/11/2026');
    await expect(page.locator('[data-banner-pagos="fixtures"]')).toContainText('Datos ficticios');
    await expect(filas(page)).toHaveCount(13);
    for (const [e, n] of [['PENDIENTE', '4'], ['VENCIDO_SIN_PAGAR', '3'], ['DOMICILIADO_PREVISTO', '4'], ['ABONO_PENDIENTE_COMPENSAR', '1'], ['PAGADO_MANUAL', '1']]) {
      await expect(contador(page, e)).toHaveText(n);
    }
    // H6-REAL: sin marcas a revisar, su botón no aparece.
    await expect(page.locator('[data-filtro-estado="A_REVISAR"]')).toHaveCount(0);
    await expect(page.locator('[data-aviso-revisar], [data-marcas-huerfanas]')).toHaveCount(0);
    await expect(page.locator('[data-estado-reservado="PAGADO_BANCO"]')).toContainText('sin datos bancarios');
    // Menú: Vencimientos es un enlace activo, sin «Próximamente».
    const menu = page.getByRole('navigation', { name: 'Menú principal' });
    await expect(menu.getByRole('link', { name: 'Vencimientos', exact: true })).toHaveClass(/activo/);
    await expect(menu.locator('.menu-proximamente', { hasText: 'Vencimientos' })).toHaveCount(0);
    // Hefame pagado a mano: fecha y forma; Fedefarma sin CIF: forma sin determinar con aviso.
    const hef = page.locator(`tr[data-vencimiento="${V(7)}"]`);
    await expect(hef.locator('[data-estado-pago]')).toHaveText('pagado (marcado a mano)');
    await expect(hef).toContainText('09/11/2026 · Transferencia');
    await expect(hef.locator('[data-proveedor-principal]')).toHaveAttribute('data-proveedor-principal', 'HEFAME');
    const fed = page.locator(`tr[data-vencimiento="${V(8)}"]`);
    await expect(fed.locator('[data-forma]')).toContainText('Sin determinar');
    await expect(fed.locator('[data-sin-cif]')).toContainText('sin CIF');
    await expect(fed.locator('[data-importe-pendiente]')).toHaveText('importe pendiente');
    await expect(page.locator(`tr[data-vencimiento="${V(4)}"] [data-estado-pago]`)).toHaveText('Domiciliado previsto');
    await expect(page.locator(`tr[data-vencimiento="${V(1)}"] [data-estado-pago]`)).toHaveText('Vencido sin pagar');
    await expect(page.locator(`tr[data-vencimiento="${V(9)}"] [data-sentido]`)).toHaveText('Abono');
    await expect(page.locator(`tr[data-vencimiento="${V(3)}"] [data-sentido]`)).toHaveText('no documentado');
    // Importe pendiente: recuento visible; totales sin inventar ceros.
    await expect(page.locator('[data-recuento-sin-importe]')).toContainText('2 con importe pendiente (fuera de los totales)');
    const general = page.locator('[data-total-general]');
    // H6-6: por estado. Falta por pagar 731,66 (incluye el abono domiciliado no vencido); domiciliado previsto, solo lo
    // vencido (400 + 150); abonos por compensar aparte (−20). 731,66 + 550 − 20 = 1.261,66, el total del año.
    await expect(general.locator('[data-total="por_pagar"] .ve-cifra-etiqueta')).toHaveText('Falta por pagar');
    await expect(general.locator('[data-total="por_pagar"] .ve-cifra-n')).toHaveText('731,66 €');
    await expect(general.locator('[data-total="domiciliado"] .ve-cifra-n')).toHaveText('550,00 €');
    await expect(general.locator('[data-total="abonos"] .ve-cifra-n')).toHaveText('-20,00 €');
    await expect(general.locator('[data-notas-total]')).toContainText('2 importes pendientes · 3 de sentido no documentado · 1 cargo con importe negativo');
    // H6-4: sin tarjetas de totales por semana ni por mes.
    await expect(page.locator('.ve-periodo, [data-totales]')).toHaveCount(0);
    await expect(page.locator('[data-nota-banco]')).toContainText('sin datos bancarios');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_lista.png'), fullPage: true });
    // Nº de factura: enlace al detalle.
    await page.locator(`tr[data-vencimiento="${V(7)}"] .enlace-factura`).click();
    await expect(page).toHaveURL('/facturas/f0000000-0000-4000-8000-000000000005');
  });

  test('filtros de H6: atrasados, esta semana, este mes, próximos 30, rango, estado, forma y búsqueda (en la URL)', async ({ page }) => {
    // H6-4: el periodo pasa de pestañas a un selector («Vencimiento»); las pestañas son las de Facturas.
    const periodo = page.locator('select[name="periodo"]');
    await periodo.selectOption('atrasados');
    await expect(filas(page)).toHaveCount(8); // 3 rojos + 4 domiciliados previstos + 1 abono pendiente; el pagado no
    await expect(page.locator('tr[data-vencimiento] [data-estado-pago="PAGADO_MANUAL"]')).toHaveCount(0);
    await expect(page).toHaveURL(/periodo=atrasados/);
    await periodo.selectOption('semana');
    await expect(filas(page)).toHaveCount(2); // 19 y 21 nov
    await periodo.selectOption('mes');
    await expect(filas(page)).toHaveCount(9);
    await periodo.selectOption('p30');
    await expect(filas(page)).toHaveCount(3);
    await periodo.selectOption('rango');
    await page.locator('input[name="desde"]').fill('2026-11-01');
    await page.locator('input[name="hasta"]').fill('2026-11-07');
    await expect(filas(page)).toHaveCount(3);
    await periodo.selectOption('');
    await expect(filas(page)).toHaveCount(13);
    await page.locator('select[name="estado"]').selectOption('VENCIDO_SIN_PAGAR');
    await expect(filas(page)).toHaveCount(3);
    await page.locator('select[name="estado"]').selectOption('');
    await page.locator('[data-filtro-estado="DOMICILIADO_PREVISTO"]').click();
    await expect(filas(page)).toHaveCount(4);
    await expect(page.locator('select[name="estado"]')).toHaveValue('DOMICILIADO_PREVISTO');
    await page.locator('[data-filtro-estado="DOMICILIADO_PREVISTO"]').click();
    await page.locator('select[name="forma"]').selectOption('SIN_DETERMINAR');
    await expect(filas(page)).toHaveCount(2);
    await page.locator('select[name="forma"]').selectOption('');
    await page.locator('input[name="q"]').fill('F-30004444');
    await expect(filas(page)).toHaveCount(1);
    await page.locator('input[name="q"]').fill('cf-2026-55811');
    await expect(filas(page)).toHaveCount(4);
    await page.locator('input[name="q"]').fill('fedefarma');
    await expect(filas(page)).toHaveCount(2);
    await page.getByRole('button', { name: 'Quitar filtros' }).click();
    await expect(filas(page)).toHaveCount(13);
  });

  test('marcar varios como pagados: fecha (hoy por defecto) y forma de cada proveedor; quedan «pagado (marcado a mano)»', async ({ page }) => {
    await page.locator('[data-filtro-estado="VENCIDO_SIN_PAGAR"]').click();
    await expect(filas(page)).toHaveCount(3);
    await page.locator('thead [data-seleccionar-todas]').check();
    await expect(page.locator('[data-seleccionados]')).toHaveText('3 seleccionados');
    await page.locator('[data-marcar-pagado]').click();
    const form = page.locator('[data-formulario-marcar]');
    await expect(form.locator('input[name="fecha_pago"]')).toHaveValue('2026-11-16');
    await expect(form.locator('select[name="forma_pago"]')).toHaveValue('');
    await expect(form.locator('select[name="forma_pago"] option').first()).toHaveText('La de cada proveedor (transferencia)');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_marcado_multiple.png'), fullPage: false });
    await form.locator('input[name="fecha_pago"]').fill('2026-11-13');
    await form.locator('[data-marcar-si]').click();
    await expect(page.locator('[data-aviso-pagos="ok"]')).toHaveText('3 vencimientos marcados como pagados el 13/11/2026.');
    await expect(contador(page, 'PAGADO_MANUAL')).toHaveText('4');
    await expect(contador(page, 'VENCIDO_SIN_PAGAR')).toHaveText('0');
    await page.locator('[data-filtro-estado="VENCIDO_SIN_PAGAR"]').click(); // quitar el filtro
    for (const n of [1, 2, 10]) await expect(page.locator(`tr[data-vencimiento="${V(n)}"]`)).toContainText('pagado (marcado a mano)13/11/2026 · Transferencia');
    // H6-6: queda en falta por pagar el abono domiciliado del 21/11, aún no vencido.
    await expect(page.locator('[data-total-general] [data-total="por_pagar"] .ve-cifra-n')).toHaveText('-45,30 €');
    await page.locator('[data-historial-pagos] summary').click();
    await expect(page.locator('[data-historial-pagos] li').first()).toContainText('Marc marcó pagado');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_marcado_hecho.png'), fullPage: true });
  });

  test('sin CIF (con importe): hay que elegir la forma de pago antes de marcar', async ({ page }) => {
    // H6-REAL: FEDEFARMA, vencimiento 2 de 2 (96,80 €), sin CIF.
    const fed = page.locator(`tr[data-vencimiento="${V(13)}"]`);
    await expect(fed.locator('[data-sin-cif]')).toContainText('sin CIF');
    await expect(fed).toContainText('96,80 €');
    await fed.locator('[data-seleccionar]').check();
    await page.locator('[data-marcar-pagado]').click();
    await expect(page.locator('[data-aviso-sin-cif]')).toContainText('elige la forma de pago');
    await expect(page.locator('[data-marcar-si]')).toBeDisabled();
    await page.locator('select[name="forma_pago"]').selectOption('EFECTIVO');
    await page.locator('[data-marcar-si]').click();
    await expect(page.locator('[data-aviso-pagos="ok"]')).toHaveText('1 vencimiento marcado como pagado el 16/11/2026.');
    await expect(fed).toContainText('16/11/2026 · Efectivo');
    await expect(fed.locator('[data-estado-pago]')).toHaveText('pagado (marcado a mano)');
  });

  test('H6-REAL: sin importe no se puede marcar: mensaje llano en la fila y en la barra; la API tampoco lo admite', async ({ page }) => {
    const fed = page.locator(`tr[data-vencimiento="${V(8)}"]`);
    await expect(fed.locator('[data-no-marcable="SIN_IMPORTE"]')).toHaveText('no tiene importe (importe pendiente): no se puede marcar hasta que se complete');
    await fed.locator('[data-seleccionar]').check();
    await expect(page.locator('[data-aviso-no-marcable="SIN_IMPORTE"]')).toHaveText(
      'Un vencimiento seleccionado no tiene importe (importe pendiente): no se puede marcar hasta que se complete.');
    await expect(page.locator('[data-marcar-pagado]')).toBeDisabled();
    await expect(page.locator('[data-marcar-pagado]')).toHaveText('Marcar pagado (0)');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_sin_importe_no_marcable.png'), fullPage: false });
    // Con otro marcable en la selección, se marca solo ese.
    await page.locator(`tr[data-vencimiento="${V(2)}"] [data-seleccionar]`).check();
    await expect(page.locator('[data-marcar-pagado]')).toHaveText('Marcar pagado (1)');
    // La API: 409 con el mensaje llano y sin marcar nada.
    const r = await page.request.fetch('/api/pagos/marcas', {
      method: 'POST', headers: { origin: ORIGEN, 'content-type': 'application/json' },
      data: { vencimientos: [{ factura_id: 'f0000000-0000-4000-8000-000000000006', orden: 1 }], fecha_pago: '2026-11-16', forma: 'EFECTIVO' },
    });
    expect(r.status()).toBe(409);
    expect(await r.json()).toEqual({ error: 'VENCIMIENTO_SIN_IMPORTE', mensaje: 'Algún vencimiento no tiene importe (importe pendiente): no se puede marcar hasta que se complete. No se ha marcado ninguno.' });
    await expect(fed.locator('[data-marca]')).toHaveCount(0);
  });

  test('confirmar domiciliados: en bloque, con la fecha de vencimiento y forma domiciliación', async ({ page }) => {
    await page.locator('[data-filtro-estado="DOMICILIADO_PREVISTO"]').click();
    await page.locator('thead [data-seleccionar-todas]').check();
    await expect(page.locator('[data-confirmar-domiciliados]')).toHaveText('Confirmar domiciliados (4)');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_domiciliados.png'), fullPage: true });
    await page.locator('[data-confirmar-domiciliados]').click();
    await expect(page.locator('[data-aviso-pagos="ok"]')).toHaveText('4 domiciliados confirmados con su fecha de vencimiento.');
    await expect(contador(page, 'DOMICILIADO_PREVISTO')).toHaveText('0');
    await page.locator('[data-filtro-estado="DOMICILIADO_PREVISTO"]').click();
    await expect(page.locator(`tr[data-vencimiento="${V(4)}"]`)).toContainText('30/10/2026 · Domiciliación · domiciliado confirmado');
    await expect(page.locator(`tr[data-vencimiento="${V(5)}"]`)).toContainText('15/11/2026 · Domiciliación · domiciliado confirmado');
  });

  test('anular marca con confirmación: no se borra (historial con autor) y el vencimiento vuelve a su estado', async ({ page }) => {
    const hef = page.locator(`tr[data-vencimiento="${V(7)}"]`);
    await hef.locator('[data-anular-marca]').click();
    await expect(hef.locator('[data-confirmar-anular]')).toContainText('Queda en el historial (no se borra)');
    await hef.getByRole('button', { name: 'Cancelar' }).click();
    await expect(hef.locator('[data-estado-pago]')).toHaveText('pagado (marcado a mano)');
    await hef.locator('[data-anular-marca]').click();
    await hef.locator('[data-anular-si]').click();
    await expect(page.locator('[data-aviso-pagos="ok"]')).toContainText('Marca de pago anulada: HF-0563-889120');
    await expect(hef.locator('[data-estado-pago]')).toHaveText('Vencido sin pagar');
    await page.locator('[data-historial-pagos] summary').click();
    await expect(page.locator('[data-historial-pagos] li').first()).toContainText('Marc anuló la marca de pago de HF-0563-889120');
  });

  test('H6-3: abono vencido = «Abono pendiente de compensar» (azul); marcarlo = «compensado / cobrado», compensación por defecto', async ({ page }) => {
    const ab = page.locator(`tr[data-vencimiento="${V(12)}"]`);
    await expect(ab.locator('[data-estado-pago]')).toHaveText('Abono pendiente de compensar');
    await expect(ab.locator('[data-estado-pago]')).toHaveClass(/insignia b/);
    await expect(ab.locator('[data-sentido]')).toHaveText('Abono');
    await ab.locator('[data-seleccionar]').check();
    await expect(page.locator('[data-confirmar-domiciliados]')).toHaveText('Confirmar domiciliados (0)');
    await expect(page.locator('[data-confirmar-domiciliados]')).toBeDisabled();
    await page.locator('[data-marcar-pagado]').click();
    await expect(page.locator('select[name="forma_pago"] option').first()).toHaveText('La de cada proveedor (compensación con abono)');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_abono_compensar.png'), fullPage: false });
    await page.locator('[data-marcar-si]').click();
    await expect(page.locator('[data-aviso-pagos="ok"]')).toHaveText('1 abono marcado como compensado / cobrado el 16/11/2026.');
    await expect(ab.locator('[data-estado-pago]')).toHaveText('compensado / cobrado (marcado a mano)');
    await expect(ab).toContainText('16/11/2026 · Compensación con abono');
    await expect(contador(page, 'ABONO_PENDIENTE_COMPENSAR')).toHaveText('0');
    await page.locator('[data-historial-pagos] summary').click();
    await expect(page.locator('[data-historial-pagos] li').first()).toContainText('Marc marcó compensado / cobrado CF-AB-2026-0912');
  });

  test('H6-3: cargo con importe negativo: sentido «Cargo», aviso «importe negativo: revisar» y fuera de los totales (recuento visible)', async ({ page }) => {
    const neg = page.locator(`tr[data-vencimiento="${V(11)}"]`);
    await expect(neg.locator('[data-sentido]')).toHaveText('Cargo');
    await expect(neg).toContainText('-25,00 €');
    await expect(neg.locator('[data-cargo-negativo]')).toHaveText('importe negativo: revisar');
    await expect(page.locator('[data-recuento-cargo-negativo]')).toContainText('1 cargo con importe negativo: revisar (fuera de los totales)');
    // H6-4: en el calendario el 31/10 no suma (H6-5: la celda dice «importe negativo», ya no «—»); filtrada la semana
    // del 26/10, la cabecera de totales da domiciliado previsto 400 y, aparte (H6-6), abonos por compensar −20; los −25
    // no restan.
    await expect(page.locator('[data-dia="2026-10-31"] [data-importe-dia]')).toHaveAttribute('data-sin-total', 'importe negativo');
    await expect(page.locator('[data-dia="2026-10-31"]')).toHaveAttribute('data-color-dia', 'domiciliado');
    await expect(page.locator('[data-semana="2026-10-26"]')).toHaveAttribute('aria-label', /total 380,00\s€.*1 cargo con importe negativo/);
    await page.locator('[data-semana="2026-10-26"]').click();
    const cab = page.locator('[data-total-general]');
    await expect(cab.locator('[data-total="domiciliado"] .ve-cifra-n')).toHaveText('400,00 €');
    await expect(cab.locator('[data-total="abonos"] .ve-cifra-n')).toHaveText('-20,00 €');
    await expect(cab.locator('[data-notas-total]')).toContainText('1 cargo con importe negativo');
    await page.locator('[data-quitar-filtro-calendario]').click();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_cargo_negativo.png'), fullPage: true });
  });

  test('forma de pago por proveedor: Cofares a transferencia pone en rojo sus vencidos; volver a por defecto', async ({ page }) => {
    const cof = page.locator('[data-forma-proveedor="A00000001"]');
    await expect(cof).toContainText('por defecto');
    await cof.locator('select').selectOption('TRANSFERENCIA');
    await cof.locator('[data-guardar-forma]').click();
    await expect(page.locator('[data-aviso-pagos="ok"]')).toContainText('forma de pago transferencia');
    await expect(contador(page, 'VENCIDO_SIN_PAGAR')).toHaveText('7');
    await expect(contador(page, 'DOMICILIADO_PREVISTO')).toHaveText('0');
    await expect(contador(page, 'ABONO_PENDIENTE_COMPENSAR')).toHaveText('1'); // el abono no pasa a rojo
    await expect(cof).toContainText('configurada');
    await cof.locator('[data-forma-defecto]').click();
    await expect(contador(page, 'DOMICILIADO_PREVISTO')).toHaveText('4');
    await expect(cof).toContainText('por defecto');
  });
});

test.describe('Modo REAL simulado (intercepción)', () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  const dto = () => JSON.parse(readFileSync(join(DIR_DTO, 'vencimientos.json'), 'utf8'));
  test('H6-REAL: sin credencial de pagos: se ven las marcas guardadas; marcar, confirmar, anular y forma deshabilitados con «Falta configurar la credencial de pagos»', async ({ page }) => {
    const fuente = crearAlmacenPagos(leerSemillaPagos()).fuente();
    const real = construirPantalla(dto(), { ...fuente, formas: new Map() }, { modo: 'REAL', mensajeEscritura: MENSAJE_FALTA_CREDENCIAL_PAGOS });
    await page.route('**/api/pagos/vencimientos', (r) => r.fulfill({ json: real }));
    await entrar(page, '/vencimientos');
    await expect(page.locator('[data-banner-pagos="real"]')).toContainText('Falta configurar la credencial de pagos');
    await expect(page.locator('[data-banner-pagos="fixtures"]')).toHaveCount(0);
    await expect(contador(page, 'DOMICILIADO_PREVISTO')).toHaveText('7');
    await expect(contador(page, 'ABONO_PENDIENTE_COMPENSAR')).toHaveText('1');
    await expect(contador(page, 'PAGADO_MANUAL')).toHaveText('1'); // la marca guardada se ve
    await expect(contador(page, 'VENCIDO_SIN_PAGAR')).toHaveText('0');
    await page.locator('thead [data-seleccionar-todas]').check();
    await expect(page.locator('[data-marcar-pagado]')).toBeDisabled();
    await expect(page.locator('[data-confirmar-domiciliados]')).toBeDisabled();
    await expect(page.locator('[data-marcar-pagado]')).toHaveAttribute('title', 'Falta configurar la credencial de pagos');
    await expect(page.locator('[data-pendiente-tablas]')).toContainText('Falta configurar la credencial de pagos');
    await expect(page.locator(`tr[data-vencimiento="${V(7)}"] [data-anular-marca]`)).toBeDisabled();
    for (const s of await page.locator('[data-forma-select]').all()) await expect(s).toBeDisabled();
    await expect(page.locator('[data-formas-pendiente]')).toContainText('Falta configurar la credencial de pagos');
    await expect(page.locator('body')).not.toContainText('Pendiente de tablas');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_real_solo_lectura.png'), fullPage: true });
  });
  test('H6-REAL: «a revisar» (naranja, nunca pagado): importe o fecha cambiados y marca huérfana; total aparte; se puede anular', async ({ page }) => {
    const d = dto();
    const v = (n: number) => d.vencimientos.find((x: { vencimiento_id: string }) => x.vencimiento_id === V(n));
    const marca = (n: number, o: Partial<MarcaPago>): MarcaPago => ({
      marca_id: `73000000-0000-4000-8000-${String(n).padStart(12, '0')}`, farmacia: 'PIO', factura_id: v(n).factura_id, vencimiento_orden: v(n).orden,
      fecha_vencimiento: v(n).fecha_vencimiento, importe: v(n).importe, fecha_pago: '2026-11-12', forma: 'TRANSFERENCIA', origen: 'MANUAL', anulada: false,
      creada_at: '2026-11-12T10:00:00.000Z', creada_por: 'Marc', anulada_at: null, anulada_por: null, ...o,
    });
    const marcas = [marca(2, { importe: 427.22 }), marca(10, { fecha_vencimiento: '2026-11-03' }), marca(4, { vencimiento_orden: 9, importe: 120, fecha_vencimiento: '2026-10-15' })];
    const fuente = crearAlmacenPagos(leerSemillaPagos()).fuente();
    const real = construirPantalla(d, { ...fuente, marcas: new Map([...fuente.marcas, ...marcas.map((m) => [claveVencimiento(m.factura_id, m.vencimiento_orden), m] as const)]) }, { modo: 'REAL' });
    await page.route('**/api/pagos/vencimientos', (r) => r.fulfill({ json: real }));
    await entrar(page, '/vencimientos');
    await expect(page.locator('[data-aviso-revisar]')).toContainText('3 marcas de pago a revisar');
    await expect(contador(page, 'A_REVISAR')).toHaveText('3'); // 2 vencimientos + 1 huérfana
    await expect(contador(page, 'PAGADO_MANUAL')).toHaveText('1');
    const v2 = page.locator(`tr[data-vencimiento="${V(2)}"]`);
    await expect(v2.locator('[data-estado-pago]')).toHaveText('a revisar');
    await expect(v2.locator('[data-estado-pago]')).toHaveClass(/insignia o/);
    await expect(v2.locator('[data-revisar="IMPORTE"]')).toContainText('Ha cambiado el importe desde que se marcó (entonces: vto. 11/11/2026, 427,22 €). No cuenta como pagado.');
    await expect(page.locator(`tr[data-vencimiento="${V(10)}"] [data-revisar="FECHA"]`)).toContainText('Ha cambiado la fecha');
    await expect(v2.locator('[data-anular-marca]')).toBeEnabled();
    // Totales: «A revisar» aparte (472,22 + 152,37), nunca en pagado.
    await expect(page.locator('[data-total-general] [data-total="revisar"] .ve-cifra-n')).toHaveText('624,59 €');
    await expect(page.locator('[data-total-general] [data-notas-total]')).not.toContainText('pagado');
    // Calendario: el 11/11 en naranja no gana al rojo; el resumen del mes tiene «A revisar».
    await expect(page.locator('[data-resumen="revisar"] dd')).toHaveText('624,59 €');
    // Huérfana: su vencimiento ya no existe.
    const h = page.locator('[data-marcas-huerfanas]');
    await expect(h).toContainText('Marcas a revisar sin vencimiento');
    await expect(h.locator('[data-marca-huerfana]')).toContainText('CF-2026-55811 · vencimiento 9 · COFARES');
    await expect(h.locator('[data-marca-huerfana]')).toContainText('Marcada: vto. 15/10/2026, 120,00 €');
    await page.locator('[data-filtro-estado="A_REVISAR"]').click();
    await expect(filas(page)).toHaveCount(2);
    await page.locator('[data-filtro-estado="A_REVISAR"]').click();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_a_revisar.png'), fullPage: true });
  });
});

/**
 * H6-2: importes largos (6 cifras por vencimiento; los totales de noviembre llegan a 7) inyectados por intercepción.
 * Cada importe y cada nota quedan dentro de su tarjeta y no se desbordan de su caja (sin recorte ni puntos suspensivos).
 */
function pantallaImportesLargos(): PantallaVencimientosDTO {
  const dto = JSON.parse(readFileSync(join(DIR_DTO, 'vencimientos.json'), 'utf8'));
  for (const v of dto.vencimientos) {
    if (v.importe !== null) v.importe = v.sentido === 'ABONO' ? -999999.99 : 999999.99;
  }
  return construirPantalla(dto, crearAlmacenPagos(leerSemillaPagos()).fuente(), { hoy: '2026-11-16', modo: 'FIXTURES' });
}
async function comprobarDentro(page: Page, donde: string) {
  const fuera = await page.evaluate(() => {
    const malos: string[] = [];
    for (const tarjeta of document.querySelectorAll<HTMLElement>('.ve-total-general')) {
      const t = tarjeta.getBoundingClientRect();
      for (const el of tarjeta.querySelectorAll<HTMLElement>('.ve-cifra-n, .ve-cifra-nota, .ve-cifra-etiqueta')) {
        const r = el.getBoundingClientRect();
        const rango = document.createRange();
        rango.selectNodeContents(el);
        const texto = rango.getBoundingClientRect(); // caja real del texto (aunque desborde su elemento)
        const dentro = (b: DOMRect) => b.left >= t.left - 0.5 && b.right <= t.right + 0.5 && b.top >= t.top - 0.5 && b.bottom <= t.bottom + 0.5;
        if (!dentro(r) || !dentro(texto) || el.scrollWidth > el.clientWidth + 1 || getComputedStyle(el).textOverflow === 'ellipsis') {
          malos.push(`${tarjeta.dataset.periodo ?? 'cabecera'}: «${el.textContent}» texto ${Math.round(texto.left)}–${Math.round(texto.right)} tarjeta ${Math.round(t.left)}–${Math.round(t.right)}`);
        }
      }
    }
    return malos;
  });
  expect(fuera, donde).toEqual([]);
}

/** H6-4: importe de cada día, semana y mes del calendario dentro de su celda (el visible: completo o corto). */
async function comprobarCalendarioDentro(page: Page, donde: string) {
  const fuera = await page.evaluate(() => {
    const malos: string[] = [];
    for (const celda of document.querySelectorAll<HTMLElement>('.vc-dia, .vc-sem, .vc-mes-boton')) {
      const c = celda.getBoundingClientRect();
      for (const el of celda.querySelectorAll<HTMLElement>('.vc-importe-largo, .vc-importe-corto, .vc-mes-total, .vc-globo, .vc-dia-num')) {
        if (getComputedStyle(el).display === 'none' || el.offsetParent === null) continue;
        const rango = document.createRange();
        rango.selectNodeContents(el);
        const t = rango.getBoundingClientRect();
        if (t.width === 0) continue;
        if (t.left < c.left - 0.5 || t.right > c.right + 0.5 || t.top < c.top - 0.5 || t.bottom > c.bottom + 0.5) {
          malos.push(`${celda.dataset.dia ?? celda.dataset.semana ?? celda.closest<HTMLElement>('[data-mes]')?.dataset.mes}: «${el.textContent}» ${Math.round(t.left)}–${Math.round(t.right)} en ${Math.round(c.left)}–${Math.round(c.right)}`);
        }
      }
    }
    return malos;
  });
  expect(fuera, donde).toEqual([]);
}

test.describe('H6-2 / H6-4: importes largos dentro de la cabecera de totales y de las celdas del calendario', () => {
  for (const ancho of [1440, 1024, 390]) {
    test(`${ancho} px: cabecera, calendario Mes, Semana y Año con importes de 6 y 7 cifras`, async ({ page }) => {
      await page.setViewportSize({ width: ancho, height: 900 });
      const dto = pantallaImportesLargos();
      await page.route('**/api/pagos/vencimientos', (r) => r.fulfill({ json: dto }));
      await entrar(page, '/vencimientos');
      const cab = page.locator('[data-total-general]');
      // H6-6: por estado (el domiciliado aún no vencido cuenta en falta por pagar).
      await expect(cab.locator('[data-total="por_pagar"] .ve-cifra-n')).toHaveText('1.999.999,98 €');
      await expect(page.locator('[data-dia="2026-11-04"] [data-importe-dia]')).toHaveAttribute('data-importe-dia', '1.999.999,98 €');
      await page.evaluate(() => document.fonts.ready);
      await comprobarDentro(page, `${ancho} cabecera`);
      await comprobarCalendarioDentro(page, `${ancho} mes`);
      if (ancho !== 1024) {
        await page.locator('.ve-totales').screenshot({ path: join(CAPTURAS, `${ancho === 390 ? 'movil390' : 'pc1440'}_importes_largos_cabecera.png`) });
        await page.locator('[data-calendario-vencimientos]').screenshot({ path: join(CAPTURAS, `${ancho === 390 ? 'movil390' : 'pc1440'}_importes_largos_calendario.png`) });
      }
      await page.locator('[data-vista="semana"]').click();
      await comprobarCalendarioDentro(page, `${ancho} semana`);
      await page.locator('[data-vista="anio"]').click();
      await expect(page.locator('[data-mes="2026-11"] [data-importe-mes]')).toHaveAttribute('data-importe-mes', /^\d\.\d{3}\.\d{3},\d{2}\s€$/);
      await comprobarCalendarioDentro(page, `${ancho} año`);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(ancho);
    });
  }
});

test.describe('Móvil 390', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  test.afterEach(async ({ page }) => restaurar(page));
  test('tarjetas sin desbordamiento; seleccionar y barra de acciones', async ({ page }) => {
    await entrar(page, '/vencimientos');
    await expect(page.locator('li[data-vencimiento]')).toHaveCount(13);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_lista.png'), fullPage: true });
    await page.locator(`li[data-vencimiento="${V(4)}"] [data-seleccionar]`).check();
    await page.locator(`li[data-vencimiento="${V(5)}"] [data-seleccionar]`).check();
    await expect(page.locator('[data-seleccionados]')).toHaveText('2 seleccionados');
    await expect(page.locator('[data-confirmar-domiciliados]')).toHaveText('Confirmar domiciliados (2)');
    await page.locator('[data-marcar-pagado]').click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_seleccion.png'), fullPage: false });
  });
});
