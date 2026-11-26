// H7-AP1: Cashflow, apuntes manuales (migración 40). Solo FIXTURES (almacén en memoria con la semilla
// web/fixtures/cashflow/apuntes.json); REAL sin la credencial de Cashflow, simulado interceptando /api/cashflow. Crear
// desde la celda, anular con motivo, recurrente (el 31 en meses cortos), anular una ocurrencia, concepto nuevo,
// vencimiento mayor que el apunte y sustitución confirmada, credencial ausente, rótulo REAL y móvil 390.
// Cada prueba crea sus propios apuntes (notas «(e2e)»): el almacén es el mismo en todo el servidor de Playwright.
import { expect, test, type Page } from '@playwright/test';
import { join } from 'node:path';
import { MENSAJE_FALTA_CREDENCIAL_CASHFLOW } from '../server/cashflow/errores_bd.ts';
import { entrar } from './sesion.ts';

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'h7');
const celda = (page: Page, clave: string) => page.locator(`[data-cf-celda="${clave}"]`);
const seccion = (page: Page) => page.locator('[data-ap-seccion]');
async function sinDesbordar(page: Page, ancho: number) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(ancho);
}
async function abrirCashflow(page: Page, cuenta?: 'PIO' | 'RITA') {
  await entrar(page, '/cashflow');
  await expect(page.locator('[data-contrato-ok="cashflow"]')).toBeVisible();
  if (cuenta) await page.locator(`[data-cf-cuenta="${cuenta}"]`).click();
}
async function desplegar(page: Page, categoria: string) {
  const b = page.locator(`[data-cf-plegar="${categoria}"]`);
  if ((await b.getAttribute('aria-expanded')) === 'false') await b.click();
}
async function pulsarCelda(page: Page, clave: string) {
  const b = celda(page, clave).locator('button');
  await b.evaluate((el) => el.scrollIntoView({ block: 'center', inline: 'center' }));
  await b.click();
  await expect(page.locator('[data-cf-desglose]')).toBeVisible();
}
/** «Añadir apunte»: abre el formulario y rellena cuenta, categoría y concepto (o uno nuevo). */
async function anadir(page: Page, o: { cuenta: 'PIO' | 'RITA'; categoria: string; concepto?: string; nuevo?: string }) {
  await seccion(page).scrollIntoViewIfNeeded();
  await page.locator('[data-ap-anadir]').click();
  const f = page.locator('[data-ap-form="nuevo"]');
  await expect(f).toBeVisible();
  await f.locator('[data-ap-campo="cuenta"]').selectOption(o.cuenta);
  await f.locator('[data-ap-campo="categoria"]').selectOption(o.categoria);
  if (o.nuevo !== undefined) {
    await f.locator('[data-ap-campo="concepto"]').selectOption('__nuevo__');
    await f.locator('[data-ap-campo="concepto_nuevo"]').fill(o.nuevo);
  } else {
    await f.locator('[data-ap-campo="concepto"]').selectOption(o.concepto as string);
  }
  return f;
}

test.describe('PC 1440', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('semilla: apunte que gana al Excel y a la media (marca «a», popup y desglose), leyenda y sección «Apuntes manuales» con filtro por cuenta', async ({ page }) => {
    await abrirCashflow(page, 'PIO');
    await expect(page.locator('[data-cf-leyenda-apunte]')).toHaveText('a');
    await desplegar(page, 'RS Traspasos (externo)');
    const c = celda(page, 'RS Traspasos (externo)|TRASPASO A FONDOS/VALORS|2027-02-01');
    await expect(c).toHaveAttribute('data-cf-fuente', 'manual');
    await expect(c).toContainText('−2.000');
    const a = c.locator('[data-cf-marca-apunte]');
    await expect(a).toHaveText('a');
    await expect(a).toHaveAttribute('title', 'Apunte manual: Aportación acordada con el banco · Marc · 03/02/2027');
    // La marca «a» (azul) no es la «m» (morada).
    const fondo = (sel: string) => page.locator(sel).first().evaluate((el) => getComputedStyle(el).backgroundColor);
    await expect(c.locator('[data-cf-marca-media]')).toHaveCount(0);
    expect(await fondo('[data-cf-marca-apunte]')).not.toBe(await fondo('[data-cf-leyenda-apunte] ~ .cf-marca-media'));
    await pulsarCelda(page, 'RS Traspasos (externo)|TRASPASO A FONDOS/VALORS|2027-02-01');
    const d = page.locator('[data-cf-desglose]');
    await expect(d.locator('[data-cf-desglose-fuente="MANUAL"]')).toBeVisible();
    await expect(d.locator('[data-cf-apunte-manda="si"]')).toHaveText('El apunte manual manda en esta decena sobre lo anotado en el Excel (−2.500,00 €) y la media del concepto (−1.000,00 €): no suman.');
    await expect(d.locator('[data-cf-apunte]')).toContainText('Apunte manual: Aportación acordada con el banco · Marc · 03/02/2027');
    await expect(d.locator('[data-cf-media]')).toHaveCount(0);
    await expect(d.locator('[data-ap-panel]')).toBeVisible(); // la celda futura también deja anotar otro
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_apunte_gana_excel_media.png') });
    await page.keyboard.press('Escape');
    // Sección: sueltos y recurrentes vigentes; anulados contados; filtro por cuenta.
    const s = seccion(page);
    await expect(s.locator('[data-ap-suelto="e7a00000-0000-4000-8000-000000000101"]')).toContainText('Mantenimiento ascensor');
    await expect(s.locator('[data-ap-suelto="e7a00000-0000-4000-8000-000000000102"]')).toContainText('−2.000,00 €');
    await expect(s.locator('[data-ap-suelto="e7a00000-0000-4000-8000-000000000103"]')).toHaveCount(0); // anulado
    const r = s.locator('[data-ap-recurrente="b7a00000-0000-4000-8000-000000000201"]');
    await expect(r.locator('[data-ap-regla]')).toHaveText('mensual, día 31, desde 31/01/2027 hasta 31/12/2027');
    await expect(r.locator('[data-ap-ocurrencia="b7a00000-0000-4000-8000-000000000201|2027-02-28"]')).toBeVisible(); // el 31 en febrero
    await expect(r.locator('[data-ap-ocurrencia="b7a00000-0000-4000-8000-000000000201|2027-03-31"]')).toHaveCount(0); // anulada
    await expect(r.locator('[data-ap-anuladas]')).toContainText('31/03/2027 (Marzo sin cuota: promoción del proveedor)');
    await s.locator('[data-ap-filtro="RITA"]').click();
    await expect(s.locator('[data-ap-suelto]')).toHaveCount(0);
    await expect(s.locator('[data-ap-recurrente]')).toHaveCount(1);
    await s.locator('[data-ap-filtro="TODAS"]').click();
    await s.scrollIntoViewIfNeeded();
    await page.evaluate(() => document.fonts.ready);
    await s.screenshot({ path: join(CAPTURAS, 'pc1440_apuntes_manuales.png') });
  });

  test('crear desde la celda de una decena futura (fecha dentro de la decena) y anular con motivo obligatorio', async ({ page }) => {
    await abrirCashflow(page, 'PIO');
    await desplegar(page, 'RS Gastos generales');
    const clave = 'RS Gastos generales|Alquiler local|2027-01-21';
    await expect(celda(page, clave)).toHaveAttribute('data-cf-tipo', 'vacia');
    await pulsarCelda(page, clave);
    const f = page.locator('[data-ap-panel] [data-ap-form="celda"]');
    await expect(f.locator('[data-ap-fijo]')).toContainText('PIO · RS Gastos generales · Alquiler local');
    await expect(f.locator('[data-ap-fijo]')).toContainText('salida: resta del saldo');
    await expect(f.locator('[data-ap-campo="fecha"]')).toHaveAttribute('min', '2027-01-21');
    await expect(f.locator('[data-ap-campo="fecha"]')).toHaveAttribute('max', '2027-01-31');
    await f.locator('[data-ap-campo="importe"]').fill('450');
    await f.locator('[data-ap-campo="fecha"]').fill('2027-02-05');
    await f.locator('[data-ap-campo="nota"]').fill('Pintura del local (e2e)');
    await f.locator('[data-ap-guardar]').click();
    await expect(f.locator('[data-ap-error-campo="fecha"]')).toHaveText('La fecha tiene que estar dentro de la decena 21–31 ene 2027.');
    await f.locator('[data-ap-campo="fecha"]').fill('2027-01-25');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_apunte_panel_celda.png') });
    await f.locator('[data-ap-guardar]').click();
    await expect(page.locator('[data-cf-desglose]')).toHaveCount(0);
    await expect(page.locator('[data-ap-aviso-ok]')).toHaveText('Apunte manual guardado.');
    await expect(celda(page, clave)).toHaveAttribute('data-cf-fuente', 'manual');
    await expect(celda(page, clave)).toContainText('−450');
    await expect(celda(page, clave).locator('[data-cf-marca-apunte]')).toHaveAttribute('title', 'Apunte manual: Pintura del local (e2e) · Marc · 25/01/2027');
    // Anular: sin motivo no se anula; con motivo, desaparece y la celda vuelve a estar vacía.
    const fila = seccion(page).locator('[data-ap-suelto]', { hasText: 'Pintura del local (e2e)' });
    await fila.locator('[data-ap-anular]').click();
    await fila.locator('[data-ap-confirmar-anular]').click();
    await expect(fila.locator('[data-ap-error]')).toHaveText('Escribe el motivo de la anulación.');
    await fila.locator('[data-ap-motivo]').fill('Se pinta en primavera');
    await fila.scrollIntoViewIfNeeded();
    await page.evaluate(() => document.fonts.ready);
    await fila.screenshot({ path: join(CAPTURAS, 'pc1440_anular_con_motivo.png') });
    await fila.locator('[data-ap-confirmar-anular]').click();
    await expect(page.locator('[data-ap-aviso-ok]')).toHaveText('Apunte anulado.');
    await expect(seccion(page).locator('[data-ap-suelto]', { hasText: 'Pintura del local (e2e)' })).toHaveCount(0);
    await expect(celda(page, clave)).toHaveAttribute('data-cf-tipo', 'vacia');
  });

  test('recurrente mensual el día 31 (30/04, 31/05, 30/06…), en la vista por meses; anular una sola ocurrencia', async ({ page }) => {
    await abrirCashflow(page);
    const f = await anadir(page, { cuenta: 'PIO', categoria: 'RS Gastos generales', concepto: 'Suministros' });
    await f.locator('[data-ap-tipo="RECURRENTE"]').click();
    await f.locator('[data-ap-campo="importe"]').fill('75');
    await f.locator('[data-ap-campo="frecuencia"]').selectOption('MENSUAL');
    await f.locator('[data-ap-campo="dia"]').fill('31');
    await f.locator('[data-ap-campo="inicio"]').fill('2027-04-29');
    await f.locator('[data-ap-campo="fin"]').fill('2027-08-31');
    await f.locator('[data-ap-campo="nota"]').fill('Mantenimiento de la alarma (e2e)');
    await f.locator('[data-ap-guardar]').click();
    await expect(f.locator('[data-ap-error-campo="inicio"]')).toContainText('tiene que ser la primera ocurrencia');
    await f.locator('[data-ap-campo="inicio"]').fill('2027-04-30');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_recurrente_formulario.png') });
    await f.locator('[data-ap-guardar]').click();
    await expect(page.locator('[data-ap-aviso-ok]')).toHaveText('Recurrente guardado.');
    const r = seccion(page).locator('[data-ap-recurrente]', { hasText: 'Mantenimiento de la alarma (e2e)' });
    await expect(r.locator('[data-ap-regla]')).toHaveText('mensual, día 31, desde 30/04/2027 hasta 31/08/2027');
    await expect(r.locator('[data-ap-ocurrencia] .cf-num')).toHaveText(['30/04/2027', '31/05/2027', '30/06/2027', '31/07/2027', '31/08/2027']);
    // Mes: la cifra de mayo lleva la marca «a» (media de la 2.ª decena + 75 en la 3.ª).
    await page.locator('[data-cf-escala="mes"]').click();
    await page.locator('[data-cf-cuenta="PIO"]').click();
    await desplegar(page, 'RS Gastos generales');
    await expect(celda(page, 'RS Gastos generales|Suministros|2027-05').locator('[data-cf-marca-apunte]')).toHaveAttribute('title', 'Apunte manual: Mantenimiento de la alarma (e2e) · Marc · 31/05/2027');
    await expect(celda(page, 'RS Gastos generales|Suministros|2027-05')).toContainText('−975');
    await celda(page, 'RS Gastos generales|Suministros|2027-05').scrollIntoViewIfNeeded();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_recurrente_mes.png') });
    // Anular solo la de junio.
    const o = r.locator('[data-ap-ocurrencia$="|2027-06-30"]');
    await o.locator('[data-ap-anular]').click();
    await o.locator('[data-ap-motivo]').fill('Junio sin cuota (e2e)');
    await o.locator('[data-ap-confirmar-anular]').click();
    await expect(page.locator('[data-ap-aviso-ok]')).toHaveText('Ocurrencia del 30/06/2027 anulada.');
    await expect(r.locator('[data-ap-ocurrencia] .cf-num')).toHaveText(['30/04/2027', '31/05/2027', '31/07/2027', '31/08/2027']);
    await expect(r.locator('[data-ap-anuladas]')).toContainText('30/06/2027 (Junio sin cuota (e2e))');
    await expect(celda(page, 'RS Gastos generales|Suministros|2027-06').locator('[data-cf-marca-apunte]')).toHaveCount(0);
    await r.scrollIntoViewIfNeeded();
    await page.evaluate(() => document.fonts.ready);
    await r.screenshot({ path: join(CAPTURAS, 'pc1440_recurrente_ocurrencia_anulada.png') });
    // Anular el recurrente entero (con motivo): ninguna ocurrencia cuenta.
    await r.locator('.ap-acciones [data-ap-anular]').click();
    await r.locator('[data-ap-motivo]').first().fill('Fin de la prueba');
    await r.locator('[data-ap-confirmar-anular]').first().click();
    await expect(page.locator('[data-ap-aviso-ok]')).toHaveText('Recurrente anulado: todas sus ocurrencias dejan de contar.');
    await expect(seccion(page).locator('[data-ap-recurrente]', { hasText: 'Mantenimiento de la alarma (e2e)' })).toHaveCount(0);
  });

  test('concepto nuevo en RITA (asociado a una categoría): su línea en la tabla, «(nuevo)» en la lista y sin repetir nombre; editar = anular + crear', async ({ page }) => {
    await abrirCashflow(page);
    const f = await anadir(page, { cuenta: 'RITA', categoria: 'RS Gastos generales', nuevo: 'Desinfección (e2e)' });
    await expect(f.locator('[data-ap-campo="proveedor_cif"]')).toBeVisible();
    await f.locator('[data-ap-campo="importe"]').fill('210');
    await f.locator('[data-ap-campo="fecha"]').fill('2027-02-05');
    await f.locator('[data-ap-campo="nota"]').fill('Desinfección anual');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_concepto_nuevo.png') });
    await f.locator('[data-ap-guardar]').click();
    await expect(page.locator('[data-ap-aviso-ok]')).toHaveText('Apunte manual guardado.');
    const fila = seccion(page).locator('[data-ap-suelto]', { hasText: 'Desinfección (e2e)' });
    await expect(fila).toContainText('RITA');
    await expect(fila).toContainText('−210,00 €');
    // El mismo nombre (sin distinguir mayúsculas) ya no se puede crear: está en la lista como «(nuevo)».
    const g = await anadir(page, { cuenta: 'RITA', categoria: 'RS Gastos generales', nuevo: 'DESINFECCIÓN (E2E)' });
    await g.locator('[data-ap-campo="importe"]').fill('10');
    await g.locator('[data-ap-campo="fecha"]').fill('2027-02-13');
    await g.locator('[data-ap-guardar]').click();
    await expect(g.locator('[data-ap-error-campo="concepto_nuevo"]')).toContainText('Ya hay un concepto con ese nombre en esa categoría');
    await expect(g.locator('[data-ap-campo="concepto"] option', { hasText: 'Desinfección (e2e) (nuevo)' })).toHaveCount(1);
    await page.keyboard.press('Escape');
    // Tabla de RITA: línea propia con la marca «a».
    await page.locator('[data-cf-cuenta="RITA"]').click();
    await desplegar(page, 'RS Gastos generales');
    await expect(celda(page, 'RS Gastos generales|Desinfección (e2e)|2027-02-01')).toContainText('−210');
    await expect(celda(page, 'RS Gastos generales|Desinfección (e2e)|2027-02-01').locator('[data-cf-marca-apunte]')).toBeVisible();
    // Editar: anular + crear (con motivo obligatorio).
    await fila.locator('[data-ap-editar]').click();
    const e = page.locator('[data-ap-form="editar"]');
    await expect(e.locator('[data-ap-campo="concepto"]')).toHaveValue('Desinfección (e2e)');
    await e.locator('[data-ap-campo="importe"]').fill('230');
    await e.locator('[data-ap-guardar]').click();
    await expect(e.locator('[data-ap-error-campo="motivo"]')).toHaveText('Escribe el motivo de la anulación.');
    await e.locator('[data-ap-campo="motivo"]').fill('Presupuesto actualizado');
    await e.locator('[data-ap-guardar]').click();
    await expect(page.locator('[data-ap-aviso-ok]')).toHaveText('Cambio guardado: el anterior queda anulado con su motivo.');
    await expect(seccion(page).locator('[data-ap-suelto]', { hasText: 'Desinfección (e2e)' })).toContainText('−230,00 €');
    await expect(celda(page, 'RS Gastos generales|Desinfección (e2e)|2027-02-01')).toContainText('−230');
  });

  test('vencimiento mayor que el apunte (ganan los vencimientos) y sustitución confirmada por la factura (±5 %, misma decena)', async ({ page }) => {
    await abrirCashflow(page);
    const f = await anadir(page, { cuenta: 'PIO', categoria: 'RS Proveedores', concepto: 'ALLIANCE' });
    await f.locator('[data-ap-campo="importe"]').fill('460');
    await f.locator('[data-ap-campo="fecha"]').fill('2026-11-15');
    await f.locator('[data-ap-campo="nota"]').fill('Pedido Alliance (e2e)');
    await f.locator('[data-ap-guardar]').click();
    await expect(page.locator('[data-ap-aviso-ok]')).toHaveText('Apunte manual guardado.');
    // El apunte (460) manda sobre el Excel (520) y la media (6.000); los vencimientos (472,22) son mayores: cuentan ellos.
    await page.locator('[data-cf-cuenta="PIO"]').click();
    await desplegar(page, 'RS Proveedores');
    const c = celda(page, 'RS Proveedores|ALLIANCE|2026-11-11');
    await expect(c).toHaveAttribute('data-cf-fuente', 'vencimientos');
    await expect(c).toContainText('−472');
    await expect(c.locator('[data-cf-marca-apunte]')).toHaveAttribute('title', 'Apunte manual: Pedido Alliance (e2e) · Marc · 15/11/2026\n(ganan los vencimientos, mayores que el apunte)');
    await pulsarCelda(page, 'RS Proveedores|ALLIANCE|2026-11-11');
    const d = page.locator('[data-cf-desglose]');
    await expect(d.locator('[data-cf-venc-ganan="manual"]')).toHaveText('Ganan los vencimientos: apunte manual 460,00 € (inferior a los vencimientos).');
    await expect(d.locator('[data-cf-apunte-manda="no"]')).toBeVisible();
    await expect(d.locator('[data-ap-sugerencia]')).toContainText('Sustituir apunte por factura AL-26-100577');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_venc_mayor_que_apunte.png') });
    await page.keyboard.press('Escape');
    // Sugerencia en «Apuntes manuales»: nunca automática; Confirmar anula el apunte y guarda la factura.
    const s = seccion(page).locator('[data-ap-sugerencia]', { hasText: 'AL-26-100577' });
    await expect(s).toContainText('apunte del 15/11/2026 −460,00 €');
    await expect(s).toContainText('vencimiento del 11/11/2026 −472,22 €');
    await s.scrollIntoViewIfNeeded();
    await page.evaluate(() => document.fonts.ready);
    await seccion(page).screenshot({ path: join(CAPTURAS, 'pc1440_sugerencia_sustitucion.png') });
    await s.locator('[data-ap-confirmar-sustitucion]').click();
    await expect(page.locator('[data-ap-aviso-ok]')).toHaveText('Apunte sustituido por la factura AL-26-100577: queda anulado y cuenta el vencimiento.');
    await expect(seccion(page).locator('[data-ap-sugerencia]')).toHaveCount(0);
    await expect(seccion(page).locator('[data-ap-suelto]', { hasText: 'Pedido Alliance (e2e)' })).toHaveCount(0);
    await expect(seccion(page).locator('[data-ap-anulados]')).toContainText('sustituido por una factura');
    // La celda vuelve a su previsión (media 6.000 > vencimientos), sin apunte.
    await expect(c).toHaveAttribute('data-cf-fuente', 'media');
    await expect(c.locator('[data-cf-marca-apunte]')).toHaveCount(0);
  });

  test('REAL sin la credencial de Cashflow (simulado): se ven los apuntes; crear, editar, anular y sustituir desactivados con el aviso', async ({ page }) => {
    await page.route('**/api/cashflow', async (r) => {
      const res = await r.fetch();
      const j = await res.json();
      j.modo = 'REAL';
      j.escritura_cashflow = { habilitada: false, codigo: 'CREDENCIAL_CASHFLOW_AUSENTE', mensaje: MENSAJE_FALTA_CREDENCIAL_CASHFLOW, autor: 'Marc' };
      await r.fulfill({ response: res, json: j });
    });
    await abrirCashflow(page, 'PIO');
    const s = seccion(page);
    await expect(s.locator('[data-ap-sin-escritura]')).toHaveText(MENSAJE_FALTA_CREDENCIAL_CASHFLOW);
    await expect(s.locator('[data-ap-anadir]')).toBeDisabled();
    await expect(s.locator('[data-ap-anadir]')).toHaveAttribute('title', MENSAJE_FALTA_CREDENCIAL_CASHFLOW);
    await expect(s.locator('[data-ap-suelto="e7a00000-0000-4000-8000-000000000102"]')).toBeVisible();
    for (const b of await s.locator('[data-ap-editar], [data-ap-anular]').all()) await expect(b).toBeDisabled();
    await s.scrollIntoViewIfNeeded();
    await page.evaluate(() => document.fonts.ready);
    await s.screenshot({ path: join(CAPTURAS, 'pc1440_sin_credencial_cashflow.png') });
    // Desde la celda: el formulario se ve, pero Guardar está desactivado con el mismo aviso.
    await desplegar(page, 'RS Gastos generales');
    await pulsarCelda(page, 'RS Gastos generales|Alquiler local|2027-01-21');
    await expect(page.locator('[data-ap-panel] [data-ap-guardar]')).toBeDisabled();
    await expect(page.locator('[data-ap-panel] [data-ap-sin-escritura]')).toHaveText(MENSAJE_FALTA_CREDENCIAL_CASHFLOW);
  });

  test('rótulo REAL (simulado): «escritura: Trabajadores, Pagos, Cashflow»', async ({ page }) => {
    await entrar(page);
    await page.route('**/api/estado', (r) => r.fulfill({ json: { modo: 'REAL', farmacia: 'PIO', solo_lectura: true, usuario: 'Pío', escritura: ['Trabajadores', 'Pagos', 'Cashflow'] } }));
    await page.goto('/configuracion');
    await expect(page.locator('[data-rotulo-escritura]')).toHaveText('escritura: Trabajadores, Pagos, Cashflow');
    await expect(page.locator('[data-rotulo-escritura]')).toBeInViewport({ ratio: 1 });
    await page.evaluate(() => document.fonts.ready);
    await page.locator('.lateral').screenshot({ path: join(CAPTURAS, 'pc1440_lateral_real_con_cashflow.png') });
  });
});

test.describe('Móvil 390', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test('sección «Apuntes manuales» y formulario «Añadir apunte» sin desbordar la página', async ({ page }) => {
    await abrirCashflow(page);
    await seccion(page).scrollIntoViewIfNeeded();
    await sinDesbordar(page, 390);
    await page.evaluate(() => document.fonts.ready);
    await seccion(page).screenshot({ path: join(CAPTURAS, 'movil390_apuntes_manuales.png') });
    await page.locator('[data-ap-anadir]').click();
    await expect(page.locator('[data-ap-form="nuevo"]')).toBeVisible();
    await sinDesbordar(page, 390);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_anadir_apunte.png') });
  });
});
