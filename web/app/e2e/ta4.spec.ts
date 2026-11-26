// TA4: guardia festiva de un día (herramienta del calendario), colores de guardia editables y vista de impresión del
// año en una hoja A4. Solo FIXTURES (playwright.config.ts lo exige); el servidor es común: la prueba de la guardia
// festiva deshace todo lo que crea (2027, sin guardias en los fixtures).
import { expect, test, type Page } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { entrar } from './sesion.ts';

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'ta4');
mkdirSync(CAPTURAS, { recursive: true });
const ID = (n: number) => `e0000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const AINA = ID(1);

test.beforeEach(async ({ page }) => {
  await entrar(page);
  // Colores por defecto al empezar (el almacenamiento es del navegador de la prueba).
  await page.evaluate(() => { try { localStorage.removeItem('cf.rrhh.calendario.colores.v1'); sessionStorage.clear(); } catch { /* nada */ } });
});

async function abrir(page: Page, consulta: string) {
  const estado = await (await page.request.get('/api/estado')).json();
  expect(estado.modo).toBe('FIXTURES');
  await page.goto(`/trabajadores/calendario${consulta}`);
  await expect(page.locator('[data-calendario]')).toBeVisible();
  await expect(page.locator('[data-cabecera-guardias], [data-vista-anio]').first()).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}
const aviso = (page: Page) => page.locator('[data-aviso-calendario]');
const cabecera = (page: Page, fecha: string) => page.locator(`[data-columna="${fecha}"] .cal-col-boton`);
const panel = (page: Page) => page.locator('[data-dialogo-festiva]');
async function deshacer(page: Page, texto: string) {
  await page.locator('[data-accion="deshacer"]').click();
  await expect(aviso(page)).toHaveText(`Deshecho «${texto}».`);
}
const rgb = (hex: string) => `rgb(${[1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).join(', ')})`;
const colorDe = (page: Page, sel: string) => page.locator(sel).first().evaluate((el) => {
  const s = getComputedStyle(el);
  return { fondo: s.backgroundColor, texto: s.color };
});

test.describe('TA4 PC 1440', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('Guardia festiva: crear (PIO con persona, festivo nuevo «Reis»), verla en Semana, Mes, Año y Por persona; editar a OTRA; anular; deshacer todo', async ({ page }) => {
    await abrir(page, '?fecha=2027-01-04');
    await expect(page.locator('[data-paleta-guardias] [data-herramienta="festiva"]')).toHaveText('GFGuardia festiva');
    await expect(page.locator('[data-columna="2027-01-06"][data-festivo-columna]')).toHaveCount(0);

    // Crear: panel con farmacia, persona (de esa farmacia) y nombre opcional.
    await page.locator('[data-herramienta="festiva"]').click();
    await cabecera(page, '2027-01-06').click();
    await expect(panel(page)).toContainText('aún no es festivo');
    await panel(page).locator('[data-festiva-campo="farmacia"]').selectOption('PIO');
    const personas = await panel(page).locator('[data-festiva-campo="persona"] option').allTextContents();
    expect(personas).toContain('Aina Bosch Ferrer');
    expect(personas).not.toContain('Marta Vila Soler'); // de RITA
    await panel(page).locator('[data-festiva-campo="persona"]').selectOption(AINA);
    await panel(page).locator('[data-festiva-campo="nombre"]').fill('Reis');
    await panel(page).locator('[data-guardar-festiva]').click();
    await expect(aviso(page)).toHaveText('Guardia festiva PIO (Aina Bosch Ferrer): Reis (6 ene 2027).');
    const popup = '6/1 Reis · Guardia festiva: PIO · Aina Bosch Ferrer';
    // Semana: marca diaria en la cabecera (color festivo + iniciales) y «GF» en la fila de la persona, con su popup.
    const marca = page.locator('[data-columna="2027-01-06"] [data-marca-festiva="2027-01-06"]');
    await expect(marca).toHaveText('PIO AB');
    await expect(marca).toHaveAttribute('title', popup);
    await expect(page.locator(`[data-marca-gf="${AINA}|2027-01-06"]`)).toHaveAttribute('title', popup);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_semana_guardia_festiva.png'), fullPage: true });
    // Mes, Año y Por persona.
    await page.goto('/trabajadores/calendario?vista=mes&fecha=2027-01-01');
    await expect(page.locator('[data-marca-festiva="2027-01-06"]')).toHaveText('AB');
    await expect(page.locator(`[data-marca-gf="${AINA}|2027-01-06"]`)).toBeVisible();
    await page.goto('/trabajadores/calendario?vista=anio&fecha=2027-01-01');
    await expect(page.locator('[data-dia="2027-01-06"] [data-marca-festiva]')).toHaveText('AB');
    await expect(page.locator('[data-dia="2027-01-06"]')).toHaveAttribute('title', new RegExp(`^${popup} · `));
    await page.goto(`/trabajadores/calendario?vista=persona&fecha=2027-01-01&persona=${AINA}`);
    await expect(page.locator(`[data-marca-gf="${AINA}|2027-01-06"]`)).toHaveAttribute('title', popup);

    // Editar: el panel propone lo guardado (nombre del festivo); pasa a OTRA (sin persona).
    await page.goto('/trabajadores/calendario?fecha=2027-01-04');
    await page.locator('[data-herramienta="festiva"]').click();
    await cabecera(page, '2027-01-06').click();
    await expect(panel(page).locator('[data-festiva-campo="nombre"]')).toHaveValue('Reis');
    await expect(panel(page).locator('[data-festiva-campo="farmacia"]')).toHaveValue('PIO');
    await panel(page).locator('[data-festiva-campo="farmacia"]').selectOption('OTRA');
    await expect(panel(page).locator('[data-festiva-campo="persona"]')).toHaveCount(0);
    await panel(page).locator('[data-guardar-festiva]').click();
    await expect(aviso(page)).toHaveText('Guardia festiva OTRA (farmacia ajena): Reis (6 ene 2027).');
    await expect(page.locator('[data-marca-festiva="2027-01-06"]')).toHaveText('OTRA');
    await expect(page.locator('[data-marca-festiva="2027-01-06"]')).toHaveAttribute('title', '6/1 Reis · Guardia festiva: Otra farmacia');
    await expect(page.locator(`[data-marca-gf="${AINA}|2027-01-06"]`)).toHaveCount(0);

    // Anular (no borrar): desde el panel.
    await cabecera(page, '2027-01-06').click();
    await panel(page).locator('[data-anular-festiva]').click();
    await expect(aviso(page)).toHaveText('Quitada la guardia de Reis (OTRA (farmacia ajena)).');
    await expect(page.locator('[data-marca-festiva="2027-01-06"]')).toHaveCount(0);
    await expect(page.locator('[data-columna="2027-01-06"][data-festivo-columna="Reis"]')).toHaveCount(1); // el festivo sigue

    // Deshacer en orden inverso: todo como estaba (sin festivo el 6 ene).
    await deshacer(page, 'Quitada la guardia de Reis (OTRA (farmacia ajena))');
    await expect(page.locator('[data-marca-festiva="2027-01-06"]')).toHaveText('OTRA');
    await deshacer(page, 'Guardia festiva OTRA (farmacia ajena): Reis (6 ene 2027)');
    await expect(page.locator('[data-marca-festiva="2027-01-06"]')).toHaveText('PIO AB');
    await deshacer(page, 'Guardia festiva PIO (Aina Bosch Ferrer): Reis (6 ene 2027)');
    await expect(page.locator('[data-columna="2027-01-06"][data-festivo-columna]')).toHaveCount(0);
  });

  test('Colores de guardia: semanal (claro → texto oscuro) y festiva (oscuro → texto blanco) en Año e impresión; restaurar por defecto', async ({ page }) => {
    await abrir(page, '?vista=anio&fecha=2026-01-01');
    await page.locator('[data-editar-colores]').click();
    await expect(page.locator('[data-colores-guardia] [data-color-guardia]')).toHaveCount(6);
    await page.locator('[data-color-guardia="semanal|PIO"]').fill('#ffe066');
    await page.locator('[data-color-guardia="festiva|PIO"]').fill('#102a43');
    // Año: barra semanal PIO y marca del festivo con guardia PIO (8 dic: Clara Roig Pujol).
    const banda = await colorDe(page, '[data-banda-farmacia="PIO"]');
    expect(banda).toEqual({ fondo: rgb('#ffe066'), texto: rgb('#18211e') });
    const fe = await colorDe(page, '[data-dia="2026-12-08"] [data-marca-festiva]');
    expect(fe).toEqual({ fondo: rgb('#102a43'), texto: rgb('#ffffff') });
    await expect(page.locator('[data-dia="2026-12-08"] [data-marca-festiva]')).toHaveText('CR');
    await expect(page.locator('[data-muestra-guardia="semanal|PIO"]')).toHaveCSS('color', rgb('#18211e'));
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_colores_guardia.png'), fullPage: true });
    // Impresión: los mismos colores (mismo almacenamiento).
    await page.goto('/trabajadores/guardias/imprimir?anio=2026');
    await expect(page.locator('[data-hoja-a4]')).toBeVisible();
    expect(await colorDe(page, '[data-imp-farmacia="PIO"]')).toEqual({ fondo: rgb('#ffe066'), texto: rgb('#18211e') });
    expect(await colorDe(page, '[data-imp-festivo="2026-12-08"]')).toEqual({ fondo: rgb('#102a43'), texto: rgb('#ffffff') });
    // TA4-3: la línea del festivo en la lista, resaltada con el color personalizado (texto blanco por contraste).
    expect(await colorDe(page, '[data-imp-festivo-linea="2026-12-08"] [data-imp-resalte]')).toEqual({ fondo: rgb('#102a43'), texto: rgb('#ffffff') });
    // Restaurar colores por defecto.
    await page.goto('/trabajadores/calendario?vista=anio&fecha=2026-01-01');
    await page.locator('[data-editar-colores]').click();
    await page.locator('[data-restablecer-colores]').click();
    await expect(page.locator('[data-restablecer-colores]')).toHaveText('Restaurar colores por defecto');
    expect(await colorDe(page, '[data-banda-farmacia="PIO"]')).toEqual({ fondo: rgb('#6d2e6b'), texto: rgb('#ffffff') });
    expect((await colorDe(page, '[data-dia="2026-12-08"] [data-marca-festiva]')).fondo).toBe(rgb('#a86aa6'));
    await page.goto('/trabajadores/guardias/imprimir?anio=2026');
    expect((await colorDe(page, '[data-imp-farmacia="PIO"]')).fondo).toBe(rgb('#6d2e6b'));
  });

  test('Imprimir / PDF: botón en la vista Año; hoja A4 vertical en una sola página (emulación print); festivos con los tres casos; leyenda; PDF de ejemplo', async ({ page }) => {
    await abrir(page, '?vista=anio&fecha=2026-01-01&farmacia=PIO');
    await expect(page.locator('[data-accion="imprimir-anio"]')).toHaveAttribute('href', '/trabajadores/guardias/imprimir?anio=2026&farmacia=PIO');
    await expect(page.locator('[data-accion="imprimir-anio"]')).toHaveAttribute('target', '_blank');
    // Ambas farmacias.
    await page.goto('/trabajadores/guardias/imprimir?anio=2026');
    const hoja = page.locator('[data-hoja-a4]');
    await expect(hoja).toBeVisible();
    await expect(page.locator('[data-imp-titulo]')).toHaveText('Guardias 2026 · PIO y RITA');
    await expect(page.locator('[data-imp-fecha]')).toHaveText(/^Impreso el \d{2}\/\d{2}\/\d{4}$/);
    await expect(page.locator('[data-imp-mes]')).toHaveCount(12);
    await expect(page.locator('[data-imp-farmacia="PIO"]').first()).toHaveText(/^PIO · G: [A-Z]{1,2}/);
    await expect(page.locator('[data-imp-farmacia="OTRA"]').first()).toHaveText('OTRA');
    const lineas = page.locator('[data-imp-festivos] li');
    await expect(lineas).toHaveCount(15);
    await expect(page.locator('[data-imp-festivo-linea="2026-12-08"]')).toHaveText('8/12 La Inmaculada → Farmacia PIO (Clara Roig Pujol)');
    await expect(page.locator('[data-imp-festivo-linea="2026-01-06"]')).toHaveText('6/1 Reyes → Otra farmacia');
    await expect(page.locator('[data-imp-festivo-linea="2026-08-31"]')).toHaveText('31/8 Fiesta mayor (ejemplo) → sin asignar');
    // TA4-3: subrayador con el color de la guardia festiva (por defecto): PIO y OTRA con fondo y el mismo texto
    // (blanco/negro) que la marca del día; sin asignar, sin fondo. Fondos forzados al imprimir.
    const resalte = (f: string) => `[data-imp-festivo-linea="${f}"] [data-imp-resalte]`;
    expect(await colorDe(page, resalte('2026-12-08'))).toEqual(await colorDe(page, '[data-imp-festivo="2026-12-08"]'));
    expect((await colorDe(page, resalte('2026-12-08'))).fondo).toBe(rgb('#a86aa6'));
    expect(await colorDe(page, resalte('2026-01-06'))).toEqual(await colorDe(page, '[data-imp-festivo="2026-01-06"]'));
    expect((await colorDe(page, resalte('2026-01-06'))).fondo).toBe(rgb('#8e978f'));
    await expect(page.locator(resalte('2026-08-31'))).toHaveAttribute('data-imp-resalte', '');
    expect((await colorDe(page, resalte('2026-08-31'))).fondo).toBe('rgba(0, 0, 0, 0)');
    for (const sel of [resalte('2026-12-08'), '[data-imp-festivo="2026-12-08"]', '[data-imp-farmacia="PIO"]']) {
      expect(await page.locator(sel).first().evaluate((el) => getComputedStyle(el).getPropertyValue('print-color-adjust'))).toBe('exact');
    }
    await expect(page.locator('[data-imp-leyenda="semanal"] [data-imp-muestra]')).toHaveText(['PIO', 'RITA', 'OTRA']);
    await expect(page.locator('[data-imp-leyenda="festiva"] [data-imp-muestra]')).toHaveText(['PIO', 'RITA', 'OTRA']);
    await expect(page.locator('[data-imp-personas]')).toContainText('Clara Roig Pujol (PIO)');

    // Emulación de impresión: la barra de botones desaparece y la hoja cabe en el A4 (279 mm de alto ≤ 281 mm útiles).
    await page.emulateMedia({ media: 'print' });
    await expect(page.locator('[data-imprimir]')).toBeHidden();
    const alto = await hoja.evaluate((el) => el.getBoundingClientRect().height);
    const UTIL = (281 / 25.4) * 96; // alto útil del A4 con márgenes de 8 mm, en px CSS
    expect(alto).toBeLessThanOrEqual(UTIL + 0.5);
    // TA4-2: la rejilla de 12 meses ocupa al menos el 70 % del alto útil; letra: días ≥ 9 pt, barra ≥ 7,5 pt, mes ≥ 10 pt.
    const rejilla = await page.locator('[data-imp-rejilla]').evaluate((el) => el.getBoundingClientRect().height);
    expect(rejilla / UTIL).toBeGreaterThanOrEqual(0.7);
    const pt = async (sel: string) => Math.round(Number((await page.locator(sel).first().evaluate((el) => getComputedStyle(el).fontSize)).replace('px', '')) * 0.75 * 100) / 100;
    expect(await pt('.imp-dia')).toBeGreaterThanOrEqual(9);
    expect(await pt('.imp-barra-semana')).toBeGreaterThanOrEqual(7.5);
    expect(await pt('.imp-mes h2')).toBeGreaterThanOrEqual(10);
    // Ningún mes se corta (seis semanas incluidas) y la barra no recorta su texto.
    expect(await page.locator('.imp-mes').evaluateAll((els) => els.every((el) => el.scrollHeight <= el.clientHeight + 1))).toBe(true);
    expect(await page.locator('.imp-barra-semana').evaluateAll((els) => els.every((el) => el.scrollWidth <= el.clientWidth + 1))).toBe(true);
    // Festivos en 3 columnas debajo de la rejilla; leyenda al pie.
    await expect(page.locator('[data-imp-festivos]')).toHaveCSS('column-count', '3');
    const [yRejilla, yFestivos, yLeyenda] = await Promise.all(['[data-imp-rejilla]', '[data-imp-festivos]', '.imp-leyenda']
      .map((s) => page.locator(s).evaluate((el) => el.getBoundingClientRect().top)));
    expect(yRejilla < yFestivos && yFestivos < yLeyenda).toBe(true);
    // Nada se sale de la hoja (sin cortes ni desbordes).
    expect(await hoja.evaluate((el) => el.scrollHeight <= el.clientHeight + 1 && el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    await page.evaluate(() => document.fonts.ready);
    await hoja.screenshot({ path: join(CAPTURAS, 'impresion_guardias_2026_A4.png') });
    // PDF del navegador (Chromium): A4 con @page; una sola página.
    const pdf = await page.pdf({ preferCSSPageSize: true, printBackground: true });
    writeFileSync(join(CAPTURAS, 'guardias_2026_A4.pdf'), pdf);
    const paginas = (pdf.toString('latin1').match(/\/Type\s*\/Page(?!s)/g) ?? []).length;
    expect(paginas).toBe(1);
    const caja = pdf.toString('latin1').match(/\/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]/);
    expect(caja && [Math.round(Number(caja[1])), Math.round(Number(caja[2]))]).toEqual([595, 842]); // A4 vertical en puntos

    // Filtro PIO: título y la otra farmacia en gris neutro (con su nombre como texto).
    await page.emulateMedia({ media: 'screen' });
    await page.goto('/trabajadores/guardias/imprimir?anio=2026&farmacia=PIO');
    await expect(page.locator('[data-imp-titulo]')).toHaveText('Guardias 2026 · PIO');
    await expect(page.locator('[data-imp-farmacia="RITA"]').first()).toHaveClass(/neutra/);
    await expect(page.locator('[data-imp-farmacia="RITA"]').first()).toHaveText(/^RITA · G: /);
    await expect(page.locator('[data-imp-leyenda="semanal"] [data-imp-muestra]')).toHaveText(['PIO', 'OTRA']);
  });

  test('TA4-2: «Rellenar año completo» (Año 2027): vista previa de guardias por rotación desde 2026, Confirmar crea solo huecos, un solo Deshacer', async ({ page }) => {
    await abrir(page, '?vista=anio&fecha=2027-01-01');
    await expect(page.locator('[data-banda-semana="2027-01-04"]')).toHaveAttribute('data-banda-farmacia', '');
    await page.locator('[data-accion="rellenar-anio"]').click();
    const previa = page.locator('[data-relleno-previa="2027"]');
    await expect(previa).toBeVisible();
    await expect(page.locator('[data-relleno-incluir="jornada"]')).toBeChecked();
    await expect(page.locator('[data-relleno-incluir="guardias"]')).toBeChecked();
    // Semanal: 28/12/2026 = RITA (semilla) → 4/1/2027 = OTRA, 11/1 = PIO, 18/1 = RITA.
    await expect(page.locator('[data-relleno-semana="2027-01-04"]')).toHaveAttribute('data-relleno-farmacia', 'OTRA');
    await expect(page.locator('[data-relleno-semana="2027-01-11"]')).toHaveAttribute('data-relleno-farmacia', 'PIO');
    await expect(page.locator('[data-relleno-semana="2027-01-18"]')).toHaveAttribute('data-relleno-farmacia', 'RITA');
    await expect(page.locator('[data-relleno-semana]')).toHaveCount(52);
    // Festiva (rotación propia): Sant Esteve 2026 = OTRA → 1/1/2027 = PIO.
    await expect(page.locator('[data-relleno-festiva="2027-01-01"]')).toHaveAttribute('data-relleno-farmacia', 'PIO');
    await expect(page.locator('[data-relleno-festivo]')).toHaveCount(12);
    // Festivos de fecha móvil con nombre no previsto (Viernes Santo, Lunes de Pascua, Segunda Pascua): a revisar.
    await expect(page.locator('[data-relleno-aviso="FESTIVO_A_REVISAR"]')).toHaveCount(3);
    await expect(page.locator('[data-relleno-resumen]')).toHaveText(/^Guardias 2027 por rotación: 52 semanas, 12 festivos y \d+ guardias festivas\. Se crean como planificado/);
    await page.locator('[data-confirmar-anio]').screenshot({ path: join(CAPTURAS, 'pc1440_relleno_vista_previa.png') });

    // Confirmar: guardias + jornada, un solo paso de deshacer. La jornada va después y salta los festivos recién creados
    // (261 laborables − 7 festivos de lunes a viernes = 254).
    await page.locator('[data-confirmar-anio-si]').click();
    await expect(aviso(page)).toHaveText(/^Guardias 2027 por rotación: 52 semanas, 12 festivos y 12 guardias festivas\. Rellenado 2027: 254 días laborables × \d+ personas\.$/);
    await expect(page.locator('[data-banda-semana="2027-01-04"]')).toHaveAttribute('data-banda-farmacia', 'OTRA');
    await expect(page.locator('[data-banda-semana="2027-01-11"]')).toHaveAttribute('data-banda-farmacia', 'PIO');
    await expect(page.locator('[data-dia="2027-01-01"] [data-marca-festiva]')).toHaveAttribute('data-festiva-farmacia', 'PIO');
    // No pisa: un segundo relleno ya no propone semanas.
    await page.locator('[data-accion="rellenar-anio"]').click();
    await expect(page.locator('[data-relleno-resumen]')).toHaveText(/^Guardias 2027 por rotación: 0 semanas, 0 festivos y 0 guardias festivas/);
    await page.getByRole('button', { name: 'Cancelar' }).click();
    // Deshacer: todo de una vez (jornada y guardias).
    await page.locator('[data-accion="deshacer"]').click();
    await expect(aviso(page)).toHaveText(/^Deshecho «Guardias 2027 por rotación: 52 semanas/);
    await expect(page.locator('[data-banda-semana="2027-01-04"]')).toHaveAttribute('data-banda-farmacia', '');
    await expect(page.locator('[data-dia="2027-01-01"] [data-marca-festiva]')).toHaveCount(0);
    await expect(page.locator('[data-anio-vacio]')).toBeVisible();
  });
});
