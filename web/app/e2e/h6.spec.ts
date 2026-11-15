// H6: pantalla Vencimientos. Lista con estado de pago, filtros, totales, marcar varios, confirmar domiciliados, anular,
// forma de pago por proveedor y modo REAL deshabilitado (simulado interceptando la API). Solo FIXTURES
// (playwright.config.ts lo exige). Fecha de referencia de FIXTURES: lunes 16/11/2026.
// El servidor es común: después de cada prueba se deja todo como en la semilla (afterEach).
import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { entrar } from './sesion.ts';
import { construirPantalla, crearAlmacenPagos, type PantallaVencimientosDTO } from '../server/pagos/pagos.ts';
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
    await api(page, 'POST', '/api/pagos/marcas', { vencimientos: [V(7)], fecha_pago: '2026-11-09', forma: 'TRANSFERENCIA' });
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
    await expect(page.locator('.subtitulo')).toContainText('12 vencimientos de PIO · referencia: lunes 16/11/2026');
    await expect(page.locator('[data-banner-pagos="fixtures"]')).toContainText('Datos ficticios');
    await expect(filas(page)).toHaveCount(12);
    for (const [e, n] of [['PENDIENTE', '3'], ['VENCIDO_SIN_PAGAR', '3'], ['DOMICILIADO_PREVISTO', '4'], ['ABONO_PENDIENTE_COMPENSAR', '1'], ['PAGADO_MANUAL', '1']]) {
      await expect(contador(page, e)).toHaveText(n);
    }
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
    await expect(general.locator('[data-total="por_pagar"] .ve-cifra-n')).toHaveText('776,96 €');
    await expect(general.locator('[data-total="domiciliado"] .ve-cifra-n')).toHaveText('484,70 €');
    await expect(general.locator('[data-notas-total]')).toContainText('2 importes pendientes · 2 de sentido no documentado · 1 cargo con importe negativo');
    await expect(page.locator('[data-periodo="2026-11-16"] [data-total="domiciliado"] .ve-cifra-n')).toHaveText('-45,30 €');
    await expect(page.locator('[data-periodo="2026-11-30"] [data-total="por_pagar"] .ve-cifra-n')).toHaveText('—');
    await expect(page.locator('[data-nota-banco]')).toContainText('sin datos bancarios');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_lista.png'), fullPage: true });
    // Nº de factura: enlace al detalle.
    await page.locator(`tr[data-vencimiento="${V(7)}"] .enlace-factura`).click();
    await expect(page).toHaveURL('/facturas/f0000000-0000-4000-8000-000000000005');
  });

  test('filtros: atrasados, esta semana, este mes, próximos 30, rango, estado, forma y búsqueda (en la URL); totales por mes', async ({ page }) => {
    const pestana = (t: string) => page.getByRole('tab', { name: t, exact: true });
    await pestana('Atrasados').click();
    await expect(filas(page)).toHaveCount(8); // 3 rojos + 4 domiciliados previstos + 1 abono pendiente; el pagado no
    await expect(page.locator('tr[data-vencimiento] [data-estado-pago="PAGADO_MANUAL"]')).toHaveCount(0);
    await expect(page).toHaveURL(/periodo=atrasados/);
    await pestana('Esta semana').click();
    await expect(filas(page)).toHaveCount(2); // 19 y 21 nov
    await pestana('Este mes').click();
    await expect(filas(page)).toHaveCount(9);
    await pestana('Próximos 30 días').click();
    await expect(filas(page)).toHaveCount(3);
    await pestana('Rango').click();
    await page.locator('input[name="desde"]').fill('2026-11-01');
    await page.locator('input[name="hasta"]').fill('2026-11-07');
    await expect(filas(page)).toHaveCount(3);
    await pestana('Todos').click();
    await expect(filas(page)).toHaveCount(12);
    await page.locator('select[name="estado"]').selectOption('VENCIDO_SIN_PAGAR');
    await expect(filas(page)).toHaveCount(3);
    await page.locator('select[name="estado"]').selectOption('');
    await page.locator('[data-filtro-estado="DOMICILIADO_PREVISTO"]').click();
    await expect(filas(page)).toHaveCount(4);
    await expect(page.locator('select[name="estado"]')).toHaveValue('DOMICILIADO_PREVISTO');
    await page.locator('[data-filtro-estado="DOMICILIADO_PREVISTO"]').click();
    await page.locator('select[name="forma"]').selectOption('SIN_DETERMINAR');
    await expect(filas(page)).toHaveCount(1);
    await page.locator('select[name="forma"]').selectOption('');
    await page.locator('input[name="q"]').fill('F-30004444');
    await expect(filas(page)).toHaveCount(1);
    await page.locator('input[name="q"]').fill('cf-2026-55811');
    await expect(filas(page)).toHaveCount(4);
    await page.locator('input[name="q"]').fill('fedefarma');
    await expect(filas(page)).toHaveCount(1);
    await page.getByRole('button', { name: 'Quitar filtros' }).click();
    await expect(filas(page)).toHaveCount(12);
    await page.locator('[data-totales="mes"]').click();
    await expect(page.locator('.ve-periodo')).toHaveCount(2);
    await expect(page.locator('[data-periodo="2026-11"] [data-total="por_pagar"] .ve-cifra-n')).toHaveText('776,96 €');
    await expect(page.locator('[data-periodo="2026-11"] [data-total="domiciliado"] .ve-cifra-n')).toHaveText('104,70 €');
    await expect(page.locator('[data-periodo="2026-11"] [data-total="domiciliado"] .ve-cifra-nota')).toHaveText('150,00 € cargos − 45,30 € abonos');
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
    await expect(page.locator('[data-total-general] [data-total="por_pagar"] .ve-cifra-n')).toHaveText('—');
    await page.locator('[data-historial-pagos] summary').click();
    await expect(page.locator('[data-historial-pagos] li').first()).toContainText('Marc marcó pagado');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_marcado_hecho.png'), fullPage: true });
  });

  test('sin CIF: hay que elegir la forma de pago antes de marcar', async ({ page }) => {
    await page.locator(`tr[data-vencimiento="${V(8)}"] [data-seleccionar]`).check();
    await page.locator('[data-marcar-pagado]').click();
    await expect(page.locator('[data-aviso-sin-cif]')).toContainText('elige la forma de pago');
    await expect(page.locator('[data-marcar-si]')).toBeDisabled();
    await page.locator('select[name="forma_pago"]').selectOption('EFECTIVO');
    await page.locator('[data-marcar-si]').click();
    await expect(page.locator(`tr[data-vencimiento="${V(8)}"]`)).toContainText('16/11/2026 · Efectivo');
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
    // Semana del 26/10: domiciliado 400 − 20 (abono) = 380; los −25 no restan.
    const sem = page.locator('[data-periodo="2026-10-26"]');
    await expect(sem.locator('[data-total="domiciliado"] .ve-cifra-n')).toHaveText('380,00 €');
    await expect(sem.locator('[data-total="domiciliado"] .ve-cifra-nota')).toHaveText('400,00 € cargos − 20,00 € abonos');
    await expect(sem.locator('[data-notas-total]')).toContainText('1 cargo con importe negativo');
    await page.locator('[data-totales="mes"]').click();
    await expect(page.locator('[data-periodo="2026-10"] [data-total="domiciliado"] .ve-cifra-n')).toHaveText('380,00 €');
    await page.locator('[data-totales="semana"]').click();
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

test.describe('Modo REAL simulado (intercepción): solo lectura', () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  test('sin marcas: lo vencido domiciliado figura como previsto; marcar, confirmar, anular y forma deshabilitados con «Pendiente de tablas en Supabase»', async ({ page }) => {
    const dto = JSON.parse(readFileSync(join(DIR_DTO, 'vencimientos.json'), 'utf8'));
    const real = construirPantalla(dto, null, { hoy: '2026-11-16', modo: 'REAL' });
    await page.route('**/api/pagos/vencimientos', (r) => r.fulfill({ json: real }));
    await entrar(page, '/vencimientos');
    await expect(page.locator('[data-banner-pagos="real"]')).toContainText('Pendiente de tablas en Supabase');
    await expect(contador(page, 'DOMICILIADO_PREVISTO')).toHaveText('8');
    await expect(contador(page, 'ABONO_PENDIENTE_COMPENSAR')).toHaveText('1');
    await expect(contador(page, 'PAGADO_MANUAL')).toHaveText('0');
    await expect(contador(page, 'VENCIDO_SIN_PAGAR')).toHaveText('0');
    await page.locator('thead [data-seleccionar-todas]').check();
    await expect(page.locator('[data-marcar-pagado]')).toBeDisabled();
    await expect(page.locator('[data-confirmar-domiciliados]')).toBeDisabled();
    await expect(page.locator('[data-marcar-pagado]')).toHaveAttribute('title', 'Pendiente de tablas en Supabase');
    await expect(page.locator('[data-pendiente-tablas]')).toContainText('Pendiente de tablas en Supabase');
    await expect(page.locator('[data-anular-marca]')).toHaveCount(0);
    for (const s of await page.locator('[data-forma-select]').all()) await expect(s).toBeDisabled();
    await expect(page.locator('[data-formas-pendiente]')).toContainText('Pendiente de tablas en Supabase');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_real_solo_lectura.png'), fullPage: true });
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
    for (const tarjeta of document.querySelectorAll<HTMLElement>('.ve-periodo, .ve-total-general')) {
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

test.describe('H6-2: importes largos dentro de las tarjetas de totales', () => {
  for (const ancho of [1440, 1024, 390]) {
    test(`${ancho} px: semana, mes y cabecera con importes de 6 y 7 cifras`, async ({ page }) => {
      await page.setViewportSize({ width: ancho, height: 900 });
      const dto = pantallaImportesLargos();
      await page.route('**/api/pagos/vencimientos', (r) => r.fulfill({ json: dto }));
      await entrar(page, '/vencimientos');
      const cab = page.locator('[data-total-general]');
      await expect(cab.locator('[data-total="por_pagar"] .ve-cifra-n')).toHaveText('2.999.999,97 €');
      await expect(page.locator('[data-periodo="2026-10-26"] [data-total="domiciliado"] .ve-cifra-n')).toHaveText('999.999,99 €');
      await page.evaluate(() => document.fonts.ready);
      await comprobarDentro(page, `${ancho} semana`);
      if (ancho !== 1024) await page.locator('.ve-totales').screenshot({ path: join(CAPTURAS, `${ancho === 390 ? 'movil390' : 'pc1440'}_importes_largos_semana.png`) });
      await page.locator('[data-totales="mes"]').click();
      await expect(page.locator('[data-periodo="2026-11"] [data-total="por_pagar"] .ve-cifra-n')).toHaveText('2.999.999,97 €');
      await expect(page.locator('[data-periodo="2026-11"] [data-total="domiciliado"] .ve-cifra-nota')).toHaveText('999.999,99 € cargos − 999.999,99 € abonos');
      await comprobarDentro(page, `${ancho} mes`);
      if (ancho !== 1024) await page.locator('.ve-totales').screenshot({ path: join(CAPTURAS, `${ancho === 390 ? 'movil390' : 'pc1440'}_importes_largos_mes.png`) });
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(ancho);
    });
  }
});

test.describe('Móvil 390', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  test.afterEach(async ({ page }) => restaurar(page));
  test('tarjetas sin desbordamiento; seleccionar y barra de acciones', async ({ page }) => {
    await entrar(page, '/vencimientos');
    await expect(page.locator('li[data-vencimiento]')).toHaveCount(12);
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
