// H5: pantalla Facturas (listado + detalle) e Inicio "IA no utilizada". Solo FIXTURES (playwright.config.ts lo exige).
import { expect, test, type Page } from '@playwright/test';
import { join } from 'node:path';
import { entrar } from './sesion.ts';

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'h5');
const F = (n: number) => `f0000000-0000-4000-8000-0000000000${String(n).padStart(2, '0')}`;
const fila = (page: Page, n: number) => page.locator(`[data-factura="${F(n)}"]`);

test.beforeEach(async ({ page }) => entrar(page));

async function abrirListado(page: Page, consulta = '') {
  const estado = await (await page.request.get('/api/estado')).json();
  expect(estado.modo).toBe('FIXTURES');
  await page.goto(`/facturas${consulta}`);
  await expect(page.locator('[data-contrato-ok="facturas"]')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}
async function abrirDetalle(page: Page, n: number) {
  await page.goto(`/facturas/${F(n)}`);
  await expect(page.locator('[data-contrato-ok="facturaDetalle"]')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}
const filas = (page: Page) => page.locator('.tabla-facturas tbody tr');
async function numeros(page: Page): Promise<string[]> {
  return page.locator('.tabla-facturas tbody tr .enlace-factura').allTextContents();
}

test.describe('Listado PC 1440', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('columnas, vencimiento próximo con "+N", importe pendiente, diferencia del motor, pago gris e insignias', async ({ page }) => {
    await abrirListado(page);
    await expect(filas(page)).toHaveCount(8);
    const cab = await page.locator('.tabla-facturas thead th').allTextContents();
    expect(cab.map((t) => t.replace(/[↑↓↕]/g, '').trim())).toEqual(['Proveedor', 'Nº factura', 'Fecha', 'Total', 'Vencimiento', 'Normalización', 'Conciliación', 'Revisión Pío', 'Pago']);
    // Orden por defecto: fecha descendente.
    await expect.poll(async () => (await numeros(page))[0]).toBe('CF-AB-2026-0912');
    // F04: 30/10 ya pasó (hoy 02/11) → próximo 15/11, "+2".
    await expect(fila(page, 4).locator('[data-vencimiento-listado]')).toContainText('15/11/2026');
    await expect(fila(page, 4).locator('[data-mas]')).toHaveText('+2');
    // F06: vencimiento sin importe → "importe pendiente"; total desconocido.
    await expect(fila(page, 6).locator('[data-importe-pendiente]')).toHaveText('importe pendiente');
    await expect(fila(page, 6).locator('[data-importe-desconocido]')).toHaveText('desconocido');
    await expect(fila(page, 6)).not.toContainText('0,00 €');
    // Diferencia del motor tal cual; no evaluable si el motor no pudo.
    await expect(fila(page, 3).locator('[data-diferencia-motor]')).toHaveText('dif. 41,90 €');
    await expect(fila(page, 2).locator('[data-diferencia-motor]')).toHaveText('dif. 0,07 €');
    await expect(fila(page, 7).locator('[data-diferencia-motor]')).toHaveText('no evaluable');
    await expect(fila(page, 1).locator('[data-diferencia-motor]')).toHaveCount(0);
    // Pago: gris, "sin datos bancarios", en todas.
    await expect(page.locator('.tabla-facturas .pago-gris')).toHaveCount(8);
    await expect(page.locator('.tabla-facturas .pago-gris').first()).toHaveText('sin datos bancarios');
    // Insignias.
    for (const n of [1, 8]) await expect(fila(page, n).locator('[data-insignia="posible-duplicado"]')).toHaveText('posible duplicado');
    await expect(fila(page, 7).locator('[data-insignia="abono"]')).toHaveText('abono');
    for (const n of [3, 5, 6]) await expect(fila(page, n).locator('[data-insignia="sentido-no-documentado"]')).toHaveText('sentido no documentado');
    await expect(page.locator('[data-insignia]')).toHaveCount(6);
    // Proveedor: nombre comercial + razón social del PDF (H5-8); F06 sin CIF.
    await expect(fila(page, 2).locator('[data-proveedor-principal]')).toHaveAttribute('data-proveedor-principal', 'ALLIANCE');
    await expect(fila(page, 2).locator('[data-razon-social]')).toHaveText('Alliance Healthcare España');
    await expect(fila(page, 6).locator('.celda-proveedor')).toContainText('sin CIF');
    // A 1440 px la tabla cabe entera (sin desplazamiento horizontal).
    const ancho = await page.locator('.tabla-desplazable').evaluate((e) => ({ s: e.scrollWidth, c: e.clientWidth }));
    expect(ancho.s).toBeLessThanOrEqual(ancho.c);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_facturas.png'), fullPage: true });
  });

  test('pestañas con recuento', async ({ page }) => {
    await abrirListado(page);
    const esperado: Record<string, string> = { todas: '8', conciliadas: '3', pendientes: '4', revision: '2', 'no-revisadas': '3' };
    for (const [k, n] of Object.entries(esperado)) await expect(page.locator(`[data-pestana="${k}"] .pestana-n`)).toHaveText(n);
    await page.locator('[data-pestana="conciliadas"]').click();
    await expect(filas(page)).toHaveCount(3);
    await expect.poll(async () => (await numeros(page)).sort()).toEqual(['AL-26-100231', 'AL-26-100577', 'CF-2026-55811']);
    await page.locator('[data-pestana="revision"]').click();
    await expect.poll(async () => (await numeros(page)).sort()).toEqual(['FD-26/04471', 'HF-0563-889120']);
    await page.locator('[data-pestana="no-revisadas"]').click();
    await expect(filas(page)).toHaveCount(3);
    await expect(page).toHaveURL(/pestana=no-revisadas/);
  });

  test('filtros: proveedor, importe (sin importe conocido), vencimiento, estado, revisión y fecha', async ({ page }) => {
    await abrirListado(page);
    const sel = (n: string) => page.locator(`select[name="${n}"]`);
    await sel('proveedor').selectOption('cif:B00000003');
    await expect.poll(async () => (await numeros(page)).sort()).toEqual(['AL-26-100231', 'AL-26-100231', 'AL-26-100577']);
    // Las pestañas cuentan sobre lo filtrado.
    await expect(page.locator('[data-pestana="todas"] .pestana-n')).toHaveText('3');
    await page.getByRole('button', { name: 'Quitar filtros' }).click();
    await expect(filas(page)).toHaveCount(8);
    await sel('importe').selectOption('sin');
    await expect.poll(() => numeros(page)).toEqual(['FD-26/04471']);
    await sel('importe').selectOption('hasta200');
    await expect.poll(async () => (await numeros(page)).sort()).toEqual(['AL-26-100231', 'AL-26-100231', 'CF-AB-2026-0912']); // abono por su valor absoluto
    await sel('importe').selectOption('');
    // H5-2: cualquier vencimiento con importe null (F04: el 3.º; F06), no solo el próximo.
    await sel('venc').selectOption('pendiente');
    await expect.poll(async () => (await numeros(page)).sort()).toEqual(['CF-2026-55811', 'FD-26/04471']);
    await sel('venc').selectOption('semana'); // semana del 02/11: F01 y F08 (04/11) y F05 (07/11)
    await expect.poll(async () => (await numeros(page)).sort()).toEqual(['AL-26-100231', 'AL-26-100231', 'HF-0563-889120']);
    await sel('venc').selectOption('');
    await sel('estado').selectOption('conc:REVISION_CONCILIACION');
    await expect.poll(() => numeros(page)).toEqual(['HF-0563-889120']);
    await sel('estado').selectOption('dif:motor');
    await expect.poll(async () => (await numeros(page)).sort()).toEqual(['AL-26-100577', 'CF-2026-55810', 'HF-0563-889120']);
    await sel('estado').selectOption('');
    await sel('revision').selectOption('VALIDADA_PIO');
    await expect.poll(async () => (await numeros(page)).sort()).toEqual(['AL-26-100231', 'CF-2026-55811']);
    await sel('revision').selectOption('');
    await sel('fecha').selectOption('mes:2026-10');
    await expect(filas(page)).toHaveCount(8);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_facturas_filtros.png'), fullPage: true });
  });

  test('búsqueda global: proveedor, nº de factura e importe', async ({ page }) => {
    await abrirListado(page);
    const q = page.getByRole('searchbox');
    await q.fill('cofares');
    await expect.poll(async () => (await numeros(page)).sort()).toEqual(['CF-2026-55810', 'CF-2026-55811', 'CF-AB-2026-0912']);
    await q.fill('55811');
    await expect.poll(() => numeros(page)).toEqual(['CF-2026-55811']);
    await q.fill('472,22');
    await expect.poll(() => numeros(page)).toEqual(['AL-26-100577']);
    await q.fill('45,30 €');
    await expect.poll(() => numeros(page)).toEqual(['CF-AB-2026-0912']);
    await q.fill('españa');
    await expect.poll(() => numeros(page)).toEqual(['AL-26-100577']);
    await q.fill('no-existe-zzz');
    await expect(page.locator('[data-resumen-listado]')).toHaveText('Ninguna factura cumple estos filtros.');
  });

  // H5-2: importes ficticios inyectados por intercepción (F02 total 5.000,10; F04 2.º vencimiento 5.000,95).
  test('búsqueda por importe: "5000" y "5.000" = de 5.000,00 a 5.000,99; "5000,1" exacto; total y vencimientos', async ({ page }) => {
    await page.route('**/api/facturas', async (ruta) => {
      const r = await ruta.fetch();
      const d = await r.json();
      for (const f of d.facturas) {
        if (f.factura_id === F(2)) f.importe_total = 5000.1;
        if (f.factura_id === F(4)) f.vencimientos_importes = [400, 5000.95, null];
      }
      await ruta.fulfill({ response: r, json: d });
    });
    await abrirListado(page);
    const q = page.getByRole('searchbox');
    for (const consulta of ['5000', '5.000', '5 000 €']) {
      await q.fill(consulta);
      await expect.poll(async () => (await numeros(page)).sort(), consulta).toEqual(['AL-26-100577', 'CF-2026-55811']);
    }
    await q.fill('5000,1');
    await expect.poll(() => numeros(page)).toEqual(['AL-26-100577']);
    await q.fill('5.000,10 €');
    await expect.poll(() => numeros(page)).toEqual(['AL-26-100577']);
    await q.fill('5000,95');
    await expect.poll(() => numeros(page)).toEqual(['CF-2026-55811']); // importe de un vencimiento
    await q.fill('5000,11');
    await expect(page.locator('[data-resumen-listado]')).toHaveText('Ninguna factura cumple estos filtros.');
    await q.fill('5001');
    await expect(page.locator('[data-resumen-listado]')).toHaveText('Ninguna factura cumple estos filtros.');
  });

  test('ordenable por columna; importes desconocidos siempre al final', async ({ page }) => {
    await abrirListado(page);
    await page.locator('[data-ordenar="total"]').click();
    await expect(page.locator('th[aria-sort="ascending"] [data-ordenar="total"]')).toBeVisible();
    const extremos = async () => { const ns = await numeros(page); return [ns[0], ns[ns.length - 1]]; };
    await expect.poll(extremos).toEqual(['CF-AB-2026-0912', 'FD-26/04471']);
    await page.locator('[data-ordenar="total"]').click();
    await expect(page.locator('th[aria-sort="descending"] [data-ordenar="total"]')).toBeVisible();
    await expect.poll(extremos).toEqual(['CF-2026-55811', 'FD-26/04471']);
    await page.locator('[data-ordenar="numero"]').click();
    await expect.poll(async () => (await numeros(page))[0]).toBe('AL-26-100231');
    await page.locator('[data-ordenar="vencimiento"]').click();
    await expect.poll(async () => (await numeros(page)).slice(0, 2)).toEqual(['AL-26-100231', 'AL-26-100231']);
    await page.locator('[data-ordenar="proveedor"]').click();
    await expect(filas(page).first().locator('[data-proveedor-principal]')).toHaveAttribute('data-proveedor-principal', 'ALLIANCE');
  });

  // H5-8: búsqueda por nombre comercial, razón social o CIF, sin mayúsculas ni acentos.
  test('búsqueda H5-8: hefame / Hefame / HDAD / F30004444 / F-30004444; nombre comercial + razón social', async ({ page }) => {
    await abrirListado(page);
    const q = page.getByRole('searchbox');
    for (const consulta of ['hefame', 'Hefame', 'HEFAME', 'HDAD', 'hdad.fmctca', 'F30004444', 'f30004444', 'F-30004444']) {
      await q.fill(consulta);
      await expect.poll(() => numeros(page), consulta).toEqual(['HF-0563-889120']);
    }
    const p = fila(page, 5).locator('.celda-proveedor');
    await expect(p.locator('[data-proveedor-principal]')).toHaveAttribute('data-proveedor-principal', 'HEFAME');
    await expect(p.locator('[data-razon-social]')).toHaveText('HDAD.FMCTCA.MEDIT.,S.C.L.');
    const tam = await p.locator('[data-razon-social]').evaluate((e) => parseFloat(getComputedStyle(e).fontSize));
    expect(tam).toBeLessThan(13); // secundaria, pequeña
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_facturas_busqueda_hefame.png'), fullPage: true });
    // Alliance por nombre comercial y por razón social con acento; Cofares sin equivalencia: literal, sin secundaria.
    await q.fill('alliance');
    await expect.poll(async () => (await numeros(page)).sort()).toEqual(['AL-26-100231', 'AL-26-100231', 'AL-26-100577']);
    await q.fill('ESPANA');
    await expect.poll(() => numeros(page)).toEqual(['AL-26-100577']);
    await q.fill('');
    await expect(fila(page, 7).locator('[data-proveedor-principal]')).toHaveAttribute('data-proveedor-principal', 'COFARES');
    await expect(fila(page, 7).locator('[data-razon-social]')).toHaveCount(0);
    // Filtro: mismo criterio (nombre comercial · razón social).
    await expect(page.locator('select[name="proveedor"] option[value="cif:F30004444"]')).toHaveText('HEFAME · HDAD.FMCTCA.MEDIT.,S.C.L.');
    await expect(page.locator('select[name="proveedor"] option[value="cif:A00000001"]')).toHaveText('COFARES');
  });

  test('paginación si hay más de 50 facturas (120 ficticias por intercepción)', async ({ page }) => {
    await page.route('**/api/facturas', async (ruta) => {
      const r = await ruta.fetch();
      const d = await r.json();
      const base = d.facturas;
      d.facturas = Array.from({ length: 120 }, (_, i) => ({
        ...base[i % base.length],
        factura_id: `f1000000-0000-4000-8000-${String(i).padStart(12, '0')}`,
        numero_factura: `FICT-${String(i + 1).padStart(3, '0')}`,
      }));
      await ruta.fulfill({ response: r, json: d });
    });
    await abrirListado(page);
    await expect(filas(page)).toHaveCount(50);
    await expect(page.locator('[data-pagina]')).toHaveText('Página 1 de 3');
    await page.getByRole('button', { name: 'Siguiente' }).click();
    await expect(page.locator('[data-pagina]')).toHaveText('Página 2 de 3');
    await page.getByRole('button', { name: 'Siguiente' }).click();
    await expect(filas(page)).toHaveCount(20);
    await expect(page.getByRole('button', { name: 'Siguiente' })).toBeDisabled();
  });

  test('el listado conserva filtros al volver del detalle', async ({ page }) => {
    await abrirListado(page);
    await page.locator('select[name="proveedor"]').selectOption('cif:A00000001');
    await fila(page, 3).locator('.enlace-factura').click();
    await expect(page.locator('[data-contrato-ok="facturaDetalle"]')).toBeVisible();
    await page.goBack();
    await expect(page.locator('select[name="proveedor"]')).toHaveValue('cif:A00000001');
    await expect(filas(page)).toHaveCount(3);
  });
});

test.describe('Detalle PC 1440', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('F03: cabecera, avisos, albaranes con R17 y sin coincidencia, conciliación del motor y PDF', async ({ page }) => {
    await abrirDetalle(page, 3);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('CF-2026-55810');
    for (const b of ['Validar factura', 'Deshacer validación', 'Reintentar conciliación', 'Reprocesar factura']) {
      await expect(page.getByRole('button', { name: b })).toBeDisabled();
    }
    await expect(page.locator('[data-total]')).toHaveText('375,15 €');
    await expect(page.locator('[data-estado="normalizacion"]')).toHaveText('Normalizada');
    await expect(page.locator('[data-estado="conciliacion"]')).toHaveText('Pendiente de conciliar');
    await expect(page.locator('[data-estado="revision"]')).toHaveText('No requerida');
    await expect(page.locator('.cabecera-factura .pago-gris')).toHaveText('sin datos bancarios');
    // Avisos en lenguaje llano: diferencia (motor) y albarán no localizado.
    await expect(page.locator('[data-aviso-detalle="diferencia"]')).toContainText('diferencia de 41,90 €');
    await expect(page.locator('[data-aviso-detalle="diferencia"]')).toContainText('Tolerancia del motor (R11): 0,05 €');
    await expect(page.locator('[data-aviso-detalle="lineas-SIN:SIN_COINCIDENCIA"]')).toHaveText('Falta localizar 1 albarán en Farmatic');
    await expect(page.locator('[data-aviso-detalle="sentido"]')).toBeVisible();
    // Albaranes: R17 (una línea = dos albaranes de la misma recepción) y no localizado.
    const alb = page.locator('[data-seccion="albaranes"]');
    // H5-2: cómo casó = forma del número (principal); la misma recepción R17, como relación (secundario).
    const r17 = alb.locator('[data-relacion="UNO_A_VARIOS"]');
    await expect(r17).toHaveCount(2);
    await expect(r17.first()).toHaveText('1 línea = 2 albaranes de la misma recepción (R17)');
    await expect(alb.locator('[data-casado="NUMERO:INTERNO"]')).toHaveText('Numeración interna de Farmatic (Q/R…): casa por importe');
    await expect(alb.locator('[data-relacion="UNO_A_UNO"]')).toHaveCount(1);
    await expect(alb).toContainText('Q039904/2026');
    await expect(alb.locator('[data-casado="SIN:SIN_COINCIDENCIA"]')).toHaveText('Albarán no localizado en Farmatic');
    // H5-7: bases rotuladas y detalle por línea del motor (migración 30), tal cual.
    await expect(alb.locator('[data-encabezado="pdf"]')).toHaveText(/Importe PDF\s*con IVA y RE/);
    await expect(alb.locator('[data-encabezado="farmatic"]')).toHaveText(/Importe Farmatic\s*con IVA y RE · PUC o PVP/);
    await expect(alb.locator('[data-encabezado="diferencia"]')).toHaveText(/la del motor/);
    await expect(alb.locator('[data-encabezado="base"]')).toHaveText(/sin IVA · no se compara/);
    await expect(alb.locator('[data-importe-linea="pdf"]').first()).toHaveText('234,65 €');
    await expect(alb.locator('[data-base-pdf]').first()).toHaveText('210,55 €');
    await expect(alb.locator('[data-explicado]')).toHaveText('333,25 €');
    await expect(alb.locator('[data-nota-bases]')).not.toContainText('No guarda');
    await expect(alb.locator('[data-nota-bases]')).toContainText('La diferencia total de la factura, con su tolerancia, está en Conciliación');
    await expect(alb.locator('[data-insignia-seccion]')).toHaveText('2 con diferencia');
    // Línea 1 casada con 0,10 € de diferencia; R17 (dos albaranes, una línea) coincide; sin casar: diferencia = PDF.
    await expect(alb.locator('[data-diferencia-linea]')).toHaveText(['0,10 €', '0,00 €', '41,90 €']);
    await expect(alb.locator('[data-estado-linea]')).toHaveText(['Diferencia', 'Coincide', 'Diferencia']);
    await expect(alb.locator('[data-estado-linea="DIFERENCIA"]').first()).toHaveClass(/\br\b/); // rojo
    await expect(alb.locator('[data-estado-linea="COINCIDE"]')).toHaveClass(/\bg\b/); // verde
    await expect(alb.locator('[data-no-consta="farmatic"]')).toHaveCount(1); // sin casar: Farmatic no consta, nunca 0
    await expect(page.locator('[data-aviso-detalle="lineas-con-diferencia"]')).toContainText('2 albaranes con diferencia');
    await expect(page.locator('[data-aviso-detalle="lineas-con-diferencia"]')).toContainText('De ellos, 1 sin casar en Farmatic');
    // Conciliación: resultado, diferencia exacta, tolerancia R11 y último intento, tal cual.
    const con = page.locator('[data-seccion="conciliacion"]');
    await expect(con.locator('[data-resultado-motor]')).toHaveText('No cuadra con sus albaranes');
    await expect(con.locator('[data-diferencia-exacta]')).toHaveText('41,90 €');
    await expect(con.locator('[data-tolerancia]')).toHaveText('0,05 €');
    await expect(con.locator('[data-regla-r11]')).toContainText('2 albaranes casados');
    await expect(con.locator('[data-ultimo-intento]')).toContainText('Intento');
    // PDF: no legible por cf_lectura; otras facturas del PDF.
    const pdf = page.locator('[data-pdf-original="no-disponible"]');
    await expect(pdf).toContainText('PDF original: disponible en una fase posterior');
    await expect(pdf.getByRole('link', { name: 'CF-2026-55811' })).toBeVisible();
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_detalle_F03.png'), fullPage: true });
  });

  test('tipos de casado en texto llano: exacto, letra final, ECO360, final documental, Hefame, ambiguo, cargos y abonos', async ({ page }) => {
    await abrirDetalle(page, 2);
    const alb = page.locator('[data-seccion="albaranes"]');
    await expect(alb.locator('[data-casado="NUMERO:EXACTA"]')).toHaveCount(7);
    await expect(alb.locator('[data-casado="NUMERO:LETRA_FINAL"]')).toHaveText('Mismo número con una letra final (Alliance: 08C52171A = 08C52171)');
    await expect(alb.locator('[data-nota-casado]')).toHaveText('Albarán de la plataforma ECO360: Farmatic lo registra como compra a Alliance');
    await expect(alb.locator('[data-origen-aplicado="PUC"]')).toHaveCount(8);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_detalle_F02.png'), fullPage: true });

    await abrirDetalle(page, 4);
    await expect(page.locator('[data-casado="NUMERO:FINAL_DOCUMENTAL"]')).toHaveText('El número de Farmatic es el final del número de la factura');
    const mov = page.locator('[data-seccion="movimientos"]');
    await expect(mov.locator('[data-movimiento]')).toContainText('SERVICIO INTEGRAL DE DISTRIBUCION');
    await expect(mov.locator('[data-casado="MOVIMIENTO"]')).toHaveText('Cargo o servicio sin albarán: no se busca en Farmatic');
    await expect(mov.locator('[data-magnitud="IMPORTE"]')).toHaveText('con IVA y RE');
    await expect(mov.locator('[data-encabezado="mov-base"]')).toContainText('sin IVA');

    await abrirDetalle(page, 5);
    await expect(page.locator('[data-casado="HEFAME:EXACTO_ECONOMICO"]')).toHaveCount(3);
    // H5-7 Hefame: importe del PDF = base neta (rotulado); estado y diferencia del motor tal cual, con advertencia visible.
    const HEFAME = 'El motor compara la base neta del PDF (sin IVA) con el importe de Farmatic (con IVA): la diferencia incluye el IVA y el recargo';
    await expect(page.locator('[data-encabezado="pdf"]')).toHaveText(/base neta sin IVA \(Hefame\)/);
    await expect(page.locator('[data-seccion="albaranes"] [data-diferencia-linea]')).toHaveText(['-14,86 €', '-9,07 €', '-3,15 €', '21,05 €']);
    await expect(page.locator('[data-seccion="albaranes"] [data-estado-linea="DIFERENCIA"]')).toHaveCount(4);
    await expect(page.locator('[data-aviso-hefame]')).toContainText(HEFAME);
    await expect(page.locator('[data-aviso-detalle="lineas-con-diferencia"]')).toContainText('4 albaranes con diferencia');
    await expect(page.locator('[data-aviso-detalle="lineas-con-diferencia"]')).toContainText(HEFAME);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_detalle_F05_hefame_por_linea.png'), fullPage: true });
    await expect(page.locator('[data-casado="SIN:AMBIGUO"]')).toHaveText('Varios albaranes posibles: no se elige ninguno');
    await expect(page.locator('[data-aviso-detalle="revision-conciliacion"]')).toContainText('Se han agotado los intentos');

    await abrirDetalle(page, 7);
    await expect(page.locator('[data-casado="MOVIMIENTO:SIN_SENTIDO"]')).toHaveText('Cargo o abono sin sentido documentado: no se puede sumar ni restar');
    await expect(page.locator('[data-aviso-detalle="no-evaluable"]')).toBeVisible();

    await abrirDetalle(page, 2); // H5-5: F01 lleva ahora estados de la versión anterior del motor
    await expect(page.locator('[data-seccion="albaranes"] [data-casado="NUMERO:EXACTA"]').first()).toHaveText('Mismo número de albarán');
  });

  test('H5-5: EXACTO y ECONOMICO_UNICO (versión anterior del motor) con texto llano, marcados y casados', async ({ page }) => {
    await abrirDetalle(page, 1);
    const alb = page.locator('[data-seccion="albaranes"]');
    await expect(alb.locator('[data-casado="ANTERIOR:EXACTO"]')).toHaveText('Un único albarán; el motor anterior lo dio por número coincidente (versión anterior del motor)');
    await expect(alb.locator('[data-casado="ANTERIOR:ECONOMICO_UNICO"]')).toHaveText('Un único albarán por importe; el número no es idéntico (versión anterior del motor)');
    await expect(alb.locator('[data-estado-matching="EXACTO"]')).toHaveText('Versión anterior del motor: un único albarán de Farmatic, dado por número coincidente');
    // H5-6: el número coincidente del motor anterior admite prefijo o letra final (57517 ↔ 08C57517A): nunca "mismo número".
    await expect(alb).not.toContainText('mismo número'); // F01 no tiene líneas NUMERO:EXACTA
    await expect(alb.locator('[data-estado-matching="ECONOMICO_UNICO"]')).toHaveText('Versión anterior del motor: un único albarán de Farmatic por importe, sin número idéntico');
    await expect(alb.locator('[data-casado="ESTADO:SIN_DESCRIPCION"]')).toHaveCount(0);
    await expect(page.locator('[data-aviso-detalle="lineas-ESTADO:SIN_DESCRIPCION"]')).toHaveCount(0);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_detalle_F01_version_anterior.png'), fullPage: true });
  });

  test('H5-7: NO_EVALUABLE gris (sin contraparte / sin importe del PDF) y null = «no consta», nunca 0', async ({ page }) => {
    // F02 línea 6: casada, el PDF sin importe → «Sin importe del PDF para comparar»; diferencia no consta.
    await abrirDetalle(page, 2);
    const alb = page.locator('[data-seccion="albaranes"]');
    const sinPdf = alb.locator('[data-estado-linea="NO_EVALUABLE_SIN_PDF"]');
    await expect(sinPdf).toHaveText('Sin importe del PDF para comparar');
    await expect(sinPdf).toHaveClass(/\bn\b/); // gris
    await expect(alb.locator('[data-no-consta="pdf"]')).toHaveCount(1);
    await expect(alb.locator('[data-no-consta="diferencia"]')).toHaveCount(1);
    await expect(alb.locator('[data-estado-linea="COINCIDE"]')).toHaveCount(7);
    await expect(page.locator('[data-aviso-detalle="lineas-con-diferencia"]')).toHaveCount(0);
    // F07 línea 5: sin casar y el PDF sin importe → «Sin contraparte en Farmatic»; tres importes no consta.
    await abrirDetalle(page, 7);
    const sinFar = alb.locator('[data-estado-linea="NO_EVALUABLE"]');
    await expect(sinFar).toHaveText('Sin contraparte en Farmatic');
    await expect(sinFar).toHaveClass(/\bn\b/);
    const fila = alb.locator('tr:has([data-estado-linea="NO_EVALUABLE"])');
    await expect(fila).toHaveCount(1);
    await expect(fila.locator('[data-no-consta]')).toHaveCount(3);
    await expect(fila).not.toContainText('0,00');
    await expect(alb.locator('[data-estado-linea="DIFERENCIA"]')).toHaveCount(2);
    await expect(page.locator('[data-aviso-detalle="lineas-con-diferencia"]')).toContainText('2 albaranes con diferencia');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_detalle_F07_por_linea.png'), fullPage: true });
  });

  test('H5-3: estados del motor: sin número, ya conciliado, y valores no previstos → "sin descripción" con el código en evidencia', async ({ page }) => {
    await abrirDetalle(page, 7);
    const alb = page.locator('[data-seccion="albaranes"]');
    await expect(alb.locator('[data-casado="NUMERO:NO_DISPONIBLE"]')).toHaveText('Sin número para comparar: casa por importe (PUC) y fecha (±3 días)');
    await expect(alb.locator('[data-casado="SIN:ALBARAN_YA_CONCILIADO"]')).toHaveText('El albarán ya justifica otra factura o línea');
    const sinDesc = alb.locator('[data-casado="ESTADO:SIN_DESCRIPCION"]');
    await expect(sinDesc).toHaveCount(2);
    await expect(sinDesc.first()).toHaveText('Estado del motor sin descripción (ver evidencia técnica)');
    await expect(alb).not.toContainText('ESTADO_FUTURO_PRUEBA'); // el literal solo en Evidencia técnica
    await expect(page.locator('[data-aviso-detalle="lineas-ESTADO:SIN_DESCRIPCION"]')).toContainText('Estado del motor sin descripción');
    const ev = page.locator('[data-seccion="evidencia"]');
    await ev.locator('summary').click();
    await expect(ev).toContainText('ESTADO_FUTURO_PRUEBA');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_detalle_F07_estados.png'), fullPage: true });

    await abrirDetalle(page, 4);
    await expect(page.locator('[data-seccion="albaranes"] [data-casado="ESTADO:SIN_DESCRIPCION"]')).toHaveCount(1);
    // En las casadas, el estado del motor en texto llano como dato secundario.
    await abrirDetalle(page, 2);
    await expect(page.locator('[data-estado-matching="MATCH_UNICO"]').first()).toHaveText('Un único albarán de Farmatic cumple los criterios del motor');
    await abrirDetalle(page, 3);
    await expect(page.locator('[data-estado-matching="MATCH_R17"]')).toHaveCount(2);
  });

  test('desplegables: fiscalidad por tipo, historial y evidencia técnica', async ({ page }) => {
    await abrirDetalle(page, 1);
    const fis = page.locator('[data-seccion="fiscalidad"]');
    await expect(fis.locator('[data-impuesto]')).toContainText('136,78 €');
    await expect(fis.locator('[data-impuesto]')).toContainText('10 %');
    await expect(fis.locator('.fila-total')).toContainText('152,37 €');
    await expect(fis.locator('[data-cuadre]')).not.toBeEmpty();
    for (const id of ['fiscalidad', 'albaranes', 'vencimientos', 'conciliacion', 'incidencias']) {
      await expect(page.locator(`[data-seccion="${id}"]`)).toHaveAttribute('open', '');
    }
    const his = page.locator('[data-seccion="historial"]');
    await expect(his).not.toHaveAttribute('open', '');
    await his.locator('summary').click();
    await expect(his).toContainText('Empieza la conciliación con Farmatic');
    const ev = page.locator('[data-seccion="evidencia"]');
    await ev.locator('summary').click();
    await expect(ev).toContainText('IA (Luna)');
    await expect(ev).toContainText('POSIBLE_DUPLICADO');
    await abrirDetalle(page, 6);
    await expect(page.locator('[data-seccion="fiscalidad"]')).toContainText('La factura no trae desglose de impuestos.');
    await page.locator('[data-seccion="evidencia"] summary').click();
    await expect(page.locator('[data-seccion="evidencia"]')).toContainText('sí · ');
  });

  test('H5-8: F05 Hefame: cabecera con nombre comercial + razón social y CIF; fiscalidad sin tipo («tipo no indicado», sin guion)', async ({ page }) => {
    await abrirDetalle(page, 5);
    const cab = page.locator('.cf-proveedor');
    await expect(cab.locator('[data-proveedor-principal]')).toHaveAttribute('data-proveedor-principal', 'HEFAME');
    await expect(cab.locator('[data-razon-social]')).toHaveText('HDAD.FMCTCA.MEDIT.,S.C.L.');
    await expect(cab.locator('[data-cif]')).toHaveText('· CIF F30004444');
    const fis = page.locator('[data-seccion="fiscalidad"]');
    const t = fis.locator('[data-impuesto]');
    await expect(t.locator('[data-tipo-impuesto]')).toHaveText('tipo no indicado');
    await expect(t).not.toContainText('IVA —');
    // Importes sin nada delante: el "—" era el tipo ausente (tipoPorcentaje(null)), no un signo; los importes son positivos.
    await expect(t.locator('[data-cuota="iva"]')).toHaveText('25,85 €');
    await expect(t.locator('[data-cuota="re"]')).toHaveText('3,62 €');
    expect(await t.textContent()).not.toMatch(/[—–−-]/);
    await fis.scrollIntoViewIfNeeded();
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_detalle_F05_fiscalidad_sin_tipo.png'), fullPage: true });
    // F01 con tipo: sigue "10 %" delante de la cuota.
    await abrirDetalle(page, 1);
    await expect(page.locator('[data-seccion="fiscalidad"] [data-cuota="iva"]')).toHaveText('10 % 13,68 €');
  });
});

test.describe('Inicio: IA del mes', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('con lecturas: "IA usada este mes"; con 0: "IA no utilizada este mes"', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('[data-ia-mes="utilizada"]')).toContainText('IA usada este mes: Luna');
    await page.route('**/api/inicio', async (ruta) => {
      const r = await ruta.fetch();
      const d = await r.json();
      d.luna_mes = { ejecuciones: 0, coste: null };
      await ruta.fulfill({ response: r, json: d });
    });
    await page.reload();
    await expect(page.locator('[data-ia-mes="no-utilizada"]')).toHaveText('IA no utilizada este mes');
    await expect(page.locator('.pie-inicio')).not.toContainText('lecturas');
  });
});

test.describe('Móvil 390', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test('listado en tarjetas, sin tabla ni desbordamiento', async ({ page }) => {
    await abrirListado(page);
    await expect(page.locator('.tarjeta-factura')).toHaveCount(8);
    await expect(page.locator('.tabla-facturas')).toHaveCount(0);
    await expect(page.locator(`.tarjeta-factura[data-factura="${F(4)}"] [data-mas]`)).toHaveText('+2');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_facturas.png'), fullPage: true });
  });

  test('detalle con pestañas Resumen / Detalle / PDF', async ({ page }) => {
    await abrirDetalle(page, 3);
    await expect(page.getByRole('tab', { name: 'Resumen' })).toHaveAttribute('aria-selected', 'true');
    await expect(page.locator('[data-aviso-detalle="diferencia"]')).toBeVisible();
    await expect(page.locator('[data-seccion="albaranes"]')).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_detalle_resumen.png'), fullPage: true });
    await page.getByRole('tab', { name: 'Detalle' }).click();
    await expect(page.locator('[data-seccion="albaranes"] [data-casado="NUMERO:INTERNO"]')).toBeVisible();
    // H5-7: en móvil, diferencia y estado del motor por línea (R17: una vez por línea del PDF).
    await expect(page.locator('[data-seccion="albaranes"] [data-diferencia-linea]')).toHaveText(['0,10 €', '0,00 €', '41,90 €']);
    await expect(page.locator('[data-seccion="albaranes"] [data-estado-linea]')).toHaveText(['Diferencia', 'Coincide', 'Diferencia']);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_detalle_detalle.png'), fullPage: true });
    await page.getByRole('tab', { name: 'PDF' }).click();
    await expect(page.locator('[data-pdf-original]')).toContainText('disponible en una fase posterior');
    await page.screenshot({ path: join(CAPTURAS, 'movil390_detalle_pdf.png'), fullPage: true });
  });
});
