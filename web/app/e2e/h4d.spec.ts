// H4d: "Necesita tu atención" agrupado y ordenado, MONEDA_NO_DOCUMENTADA solo en el detalle, posible duplicado en
// próximos vencimientos y nombres largos truncados. Solo FIXTURES (playwright.config.ts lo exige).
import { expect, test, type Page } from '@playwright/test';
import { join } from 'node:path';
import { entrar } from './sesion.ts';

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'h4d');
const F = (n: number) => `f0000000-0000-4000-8000-0000000000${String(n).padStart(2, '0')}`;

/** Orden fijo de grupos (decisión de Pío): 1–5 una fila; 6 y 7 una por código; 8 correcciones (H4d-2: sin grupo 9). */
const ORDEN_ESPERADO = [
  'DIFERENCIA_ALBARANES', 'DOCUMENTOS_DEFECTO', 'DUPLICADO_FARMATIC', 'VENCIMIENTO_SIN_SENTIDO', 'ALBARAN_NO_EN_FARMATIC',
  'INCIDENCIA_ERROR:REQUIERE_REVISION', 'INCIDENCIA_ERROR:SEGUNDA_LECTURA_FALLIDA', 'INCIDENCIA_ERROR:VALOR_SIN_EVIDENCIA',
  // H4d-3: las incidencias de sentido del motor, cada código en su grupo del nivel 7.
  'INCIDENCIA_AVISO:SENTIDO_NO_DOCUMENTADO', 'INCIDENCIA_AVISO:IMPORTE_VENCIMIENTO_NO_DOCUMENTADO',
  'INCIDENCIA_AVISO:SENTIDO_NO_ETIQUETADO_DOCUMENTALMENTE', 'INCIDENCIA_AVISO:CANDIDATO_ALBARAN_NO_PROMOVIDO',
  'INCIDENCIA_AVISO:POSIBLE_DUPLICADO', 'INCIDENCIA_AVISO:CODIGO_FICTICIO_SIN_TRADUCCION',
  'CORRECCION_APROBADA',
];
/** H4d-2: informativos que solo salen en el detalle de su factura. */
const SOLO_DETALLE: [string, number][] = [
  ['MONEDA_NO_DOCUMENTADA', 4], ['REPRESENTACIONES_CONSOLIDADAS', 3], ['FILAS_DUPLICADAS_EVIDENCIA_IDENTICA', 7],
  ['FILA_IMPORTE_CERO_INFORMATIVA', 1], ['ALBARANES_CONSUMIBLES_SOLO_REFERENCIA_DOCUMENTAL', 5],
];

test.beforeEach(async ({ page }) => entrar(page));

async function abrirInicio(page: Page) {
  const estado = await (await page.request.get('/api/estado')).json();
  expect(estado.modo).toBe('FIXTURES');
  await page.goto('/');
  await expect(page.locator('[data-contrato-ok="inicio"]')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

test.describe('Necesita tu atención PC 1440', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('cabecera "N tipos, M casos" y orden fijo de grupos', async ({ page }) => {
    await abrirInicio(page);
    const at = page.locator('#atencion');
    await expect(at.locator('[data-atencion-resumen]')).toHaveText('— 15 tipos, 26 casos');
    const claves = await at.locator('[data-grupo]').evaluateAll((els) => els.map((e) => e.getAttribute('data-grupo')));
    expect(claves).toEqual(ORDEN_ESPERADO);
    // Una fila por tipo con su número de casos; todo plegado al entrar.
    await expect(at.locator('[data-grupo="INCIDENCIA_AVISO:SENTIDO_NO_DOCUMENTADO"] [data-casos]')).toHaveText('3 casos');
    await expect(at.locator('[data-grupo="INCIDENCIA_AVISO:IMPORTE_VENCIMIENTO_NO_DOCUMENTADO"] [data-casos]')).toHaveText('2 casos');
    await expect(at.locator('details[open]')).toHaveCount(0);
    await expect(at.locator('[data-caso]').first()).toBeHidden();
  });

  test('colores: 1–2 y ERROR rojo; revisión, 3–5 y AVISO naranja; correcciones gris; duplicado y sentido nunca rojo', async ({ page }) => {
    await abrirInicio(page);
    const colores = await page.locator('#atencion [data-grupo]').evaluateAll((els) =>
      els.map((e) => [e.getAttribute('data-grupo'), e.getAttribute('data-color')]));
    // H4d-2: "Facturas con datos por revisar" (grupo 6) en naranja.
    const esperado = (clave: string) => clave === 'INCIDENCIA_ERROR:REQUIERE_REVISION' ? 'naranja'
      : clave === 'DIFERENCIA_ALBARANES' || clave === 'DOCUMENTOS_DEFECTO' || clave.startsWith('INCIDENCIA_ERROR')
        ? 'rojo' : clave === 'CORRECCION_APROBADA' ? 'gris' : 'naranja';
    for (const [clave, color] of colores) expect(color, clave as string).toBe(esperado(clave as string));
    for (const [clave, color] of colores) if (/DUPLICADO|SENTIDO/.test(clave as string)) expect(color).not.toBe('rojo');
    await expect(page.locator('#atencion [data-grupo="DIFERENCIA_ALBARANES"]')).toHaveClass(/borde-rojo/);
    await expect(page.locator('#atencion [data-grupo="CORRECCION_APROBADA"]')).toHaveClass(/borde-gris/);
    const rev = page.locator('#atencion [data-grupo="INCIDENCIA_ERROR:REQUIERE_REVISION"]');
    await expect(rev.locator('.grupo-titulo')).toHaveText('Facturas con datos por revisar');
    await expect(rev).toHaveClass(/borde-naranja/);
  });

  test('H4d-2: los PDF sin automatizar no salen en "Necesita tu atención"; siguen en su contador gris', async ({ page }) => {
    await abrirInicio(page);
    const at = page.locator('#atencion');
    for (const s of await at.locator('summary').all()) await s.click();
    await expect(at.locator('[data-grupo="SIN_AUTOMATIZAR"]')).toHaveCount(0);
    await expect(at).not.toContainText('PROVEEDOR_NO_SOPORTADO');
    await expect(at).not.toContainText('todavía no sabe leer');
    await expect(page.locator('[data-contador="sin-automatizar"]')).toHaveText('4');
  });

  test('H4d-2: informativos solo de detalle fuera de Inicio y visibles en el detalle de su factura', async ({ page }) => {
    await abrirInicio(page);
    const at = page.locator('#atencion');
    for (const s of await at.locator('summary').all()) await s.click();
    for (const [codigo] of SOLO_DETALLE) await expect(at).not.toContainText(codigo);
    await expect(page.locator('[data-contador="incidencias"]')).toHaveText('13');
    for (const [codigo, n] of SOLO_DETALLE) {
      await page.goto(`/facturas/${F(n)}`);
      await expect(page.locator(`[data-incidencia="${codigo}"]`), codigo).toBeVisible();
      await expect(page.locator(`[data-incidencia="${codigo}"] .caso-texto`)).not.toHaveText(/^[A-Z_]+$/);
    }
  });

  test('desplegable: casos del más reciente al más antiguo, texto llano, código pequeño y enlace', async ({ page }) => {
    await abrirInicio(page);
    const g = page.locator('#atencion [data-grupo="INCIDENCIA_AVISO:SENTIDO_NO_DOCUMENTADO"]');
    await g.locator('summary').click();
    await expect(g.locator('details')).toHaveAttribute('open', '');
    const casos = g.locator('[data-caso]');
    await expect(casos).toHaveCount(3);
    await expect(casos.nth(0)).toContainText('29/10/2026');
    await expect(casos.nth(1)).toContainText('27/10/2026');
    await expect(casos.nth(2)).toContainText('23/10/2026');
    await expect(casos.nth(0).locator('.caso-texto')).toHaveText('La factura no indica si un movimiento es un cargo o un abono');
    await expect(casos.nth(0).locator('code.codigo')).toHaveText('SENTIDO_NO_DOCUMENTADO');
    await casos.nth(0).getByRole('link', { name: /^Abrir/ }).click();
    await expect(page).toHaveURL(new RegExp(`/facturas/${F(2)}$`));
  });

  test('H4d-3: grupo 4 solo con vencimientos de sentido no documentado; incidencias de sentido en el nivel 7', async ({ page }) => {
    await abrirInicio(page);
    const at = page.locator('#atencion');
    const g4 = at.locator('[data-grupo="VENCIMIENTO_SIN_SENTIDO"]');
    await expect(g4.locator('.grupo-titulo')).toHaveText('Vencimiento sin cargo/abono documentado');
    await expect(g4).toHaveAttribute('data-color', 'naranja');
    await expect(g4).toHaveAttribute('data-orden', '4');
    await g4.locator('summary').click();
    const casos = g4.locator('[data-caso]');
    await expect(casos).toHaveCount(3);
    for (const t of await casos.locator('.caso-texto').allTextContents()) {
      expect(t).toBe('No se sabe si esta factura es un pago o un abono; no se suma en el cashflow');
    }
    await expect(g4.locator('code.codigo')).toHaveCount(0);
    // Más reciente primero (fecha de vencimiento): F06 19/11, F03 14/11, F05 07/11.
    await expect(casos.nth(0)).toContainText('19/11/2026');
    await expect(casos.nth(2)).toContainText('07/11/2026');
    await casos.nth(1).getByRole('link', { name: /^Abrir/ }).click();
    await expect(page).toHaveURL(new RegExp(`/facturas/${F(3)}$`));
    await page.goBack();
    const ne = page.locator('#atencion [data-grupo="INCIDENCIA_AVISO:SENTIDO_NO_ETIQUETADO_DOCUMENTALMENTE"]');
    await expect(ne).toHaveAttribute('data-orden', '7');
    await expect(ne).toHaveAttribute('data-color', 'naranja');
    await expect(ne.locator('.grupo-titulo')).toHaveText('El documento no indica si una línea es un cargo o un abono');
  });

  test('textos llanos: motivo de CANDIDATO_ALBARAN_NO_PROMOVIDO y código sin traducción', async ({ page }) => {
    await abrirInicio(page);
    const at = page.locator('#atencion');
    const ca = at.locator('[data-grupo="INCIDENCIA_AVISO:CANDIDATO_ALBARAN_NO_PROMOVIDO"]');
    await ca.locator('summary').click();
    await expect(ca).toContainText('tipo de pedido que el sistema no reconoce');
    await expect(ca).toContainText('cuyo cargo, abono o signo no cuadra');
    const sin = at.locator('[data-grupo="INCIDENCIA_AVISO:CODIGO_FICTICIO_SIN_TRADUCCION"]');
    await expect(sin.locator('.grupo-titulo')).toHaveText('Aviso técnico del motor (ver detalle)');
    await sin.locator('summary').click();
    await expect(sin.locator('.caso-texto')).toHaveText('Aviso técnico del motor (ver detalle)');
    await expect(sin.locator('code.codigo')).toHaveText('CODIGO_FICTICIO_SIN_TRADUCCION');
    // Ningún texto principal es un código técnico.
    for (const s of await at.locator('summary').all()) if (!(await s.locator('..').getAttribute('open'))) await s.click();
    const textos = await at.locator('.caso-texto, .grupo-titulo').allTextContents();
    expect(textos.filter((t) => /^[A-Z_]+$/.test(t.trim()))).toEqual([]);
  });

  test('MONEDA_NO_DOCUMENTADA: fuera de Inicio y del contador; visible en el detalle de factura', async ({ page }) => {
    await abrirInicio(page);
    const at = page.locator('#atencion');
    for (const s of await at.locator('summary').all()) await s.click();
    await expect(at).not.toContainText('MONEDA_NO_DOCUMENTADA');
    await expect(at).not.toContainText('moneda');
    await expect(page.locator('[data-contador="incidencias"]')).toHaveText('13');
    await page.goto(`/facturas/${F(4)}`);
    const inc = page.locator('[data-incidencia="MONEDA_NO_DOCUMENTADA"]');
    await expect(inc).toBeVisible();
    await expect(inc.locator('.caso-texto')).toHaveText('La factura no indica la moneda');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_detalle_moneda.png'), fullPage: true });
  });

  test('próximos vencimientos: "posible duplicado" en la factura con esa incidencia', async ({ page }) => {
    await abrirInicio(page);
    const filas = page.locator('[data-vencimiento]');
    await expect(filas.locator('[data-posible-duplicado]')).toHaveCount(1);
    await expect(filas.first().locator('[data-posible-duplicado]')).toHaveText('posible duplicado');
  });

  test('captura PC con grupos desplegados', async ({ page }) => {
    await abrirInicio(page);
    for (const clave of ['VENCIMIENTO_SIN_SENTIDO', 'INCIDENCIA_AVISO:CANDIDATO_ALBARAN_NO_PROMOVIDO']) {
      await page.locator(`#atencion [data-grupo="${clave}"] summary`).click();
    }
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_inicio_atencion.png'), fullPage: true });
  });
});

test.describe('Necesita tu atención móvil 390', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test('nombres largos truncados con "…" y completos en title; sin desbordamiento', async ({ page }) => {
    await abrirInicio(page);
    const nombre = page.locator('[data-vencimiento] .nombre-truncado').first();
    await expect(nombre).toHaveAttribute('title', 'ALLIANCEHEALTHCARECENCORA');
    const m = await nombre.evaluate((e) => ({ scroll: e.scrollWidth, client: e.clientWidth, ws: getComputedStyle(e).whiteSpace, to: getComputedStyle(e).textOverflow }));
    expect(m.ws).toBe('nowrap');
    expect(m.to).toBe('ellipsis');
    expect(m.scroll).toBeGreaterThan(m.client); // no cabe: se ve con "…", en una sola línea
    expect((await nombre.boundingBox())!.height).toBeLessThan(30);
    for (const s of await page.locator('#atencion summary').all()) await s.click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_inicio_atencion.png'), fullPage: true });
  });
});
