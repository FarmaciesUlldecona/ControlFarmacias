// TA2/TA2-2 Trabajadores: calendario con datos de ejemplo en memoria del servidor FIXTURES. Solo FIXTURES
// (playwright.config.ts lo exige). El modo REAL se simula interceptando la API.
// Las pruebas que escriben usan diciembre de 2026 y los años 2027–2028 (fuera de la semilla de noviembre).
// TA2-2: mañana y tarde por separado: en la semana, celda = persona|día|franja; en mes y por persona, persona|día.
import { expect, test, type Locator, type Page } from '@playwright/test';
import { join } from 'node:path';
import { entrar } from './sesion.ts';

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'ta2');
const ID = (n: number) => `e0000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const AINA = ID(1); const CLARA = ID(2); const NURIA = ID(3); const ELENA = ID(4);
const MARTA = ID(12); const JUDIT = ID(14); const ROSA = ID(15); const IRENE = ID(17); const TITULAR_PIO = ID(21);
const AVISO_NOTA = 'No anotes datos de salud ni diagnósticos';
const AVISO_NOTA_VACIA = 'Pinta primero un evento para poder anotarlo';

test.beforeEach(async ({ page }) => entrar(page));

async function abrir(page: Page, consulta: string) {
  const estado = await (await page.request.get('/api/estado')).json();
  expect(estado.modo).toBe('FIXTURES');
  await page.goto(`/trabajadores/calendario${consulta}`);
  await expect(page.locator('[data-calendario]')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}
/** Semana: una franja. */
const franja = (page: Page, id: string, fecha: string, f: 'MANANA' | 'TARDE') => page.locator(`[data-celda="${id}|${fecha}|${f}"]`);
/** Mes y por persona: el día completo. */
const diaCompleto = (page: Page, id: string, fecha: string) => page.locator(`[data-celda="${id}|${fecha}"]`);
const aviso = (page: Page) => page.locator('[data-aviso-calendario]');
async function arrastrar(page: Page, desde: Locator, hasta: Locator) {
  const a = await desde.boundingBox();
  const b = await hasta.boundingBox();
  if (!a || !b) throw new Error('sin caja');
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
  await page.mouse.down();
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 10 });
  await page.mouse.up();
}
async function abrirHistorial(page: Page) {
  const h = page.locator('[data-historial-calendario]');
  await expect(h).not.toHaveAttribute('open'); // plegado por defecto
  await h.locator('> summary').click();
  await expect(h).toHaveAttribute('open', '');
  return h;
}

test.describe('Calendario PC 1440', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('semana: mañana y tarde por separado, ausencias y notas de ejemplo, navegación y filtros', async ({ page }) => {
    await abrir(page, '?fecha=2026-11-09');
    await expect(page.locator('[data-banner-ejemplo]')).toBeVisible();
    await expect(page.locator('[data-seccion="calendario"]')).toHaveAttribute('aria-current', 'page');
    await expect(page.locator('[data-rita]')).toHaveText('RITA: solo en Trabajadores');
    await expect(page.locator('[data-periodo]')).toHaveText('9–15 nov 2026');
    // Ambas: un grupo por farmacia; dos subfilas (mañana y tarde) por persona.
    await expect(page.locator('.cal-grupo [data-farmacia]')).toHaveText(['PIO', 'RITA']);
    await expect(page.locator('tbody tr[data-fila]')).toHaveCount(26);
    // Completa (TA2-3): mañana 4,5 h + tarde 3,5 h; media mañana solo mañana; media tarde solo tarde (la otra franja, rayada).
    await expect(franja(page, AINA, '2026-11-09', 'MANANA')).toHaveAttribute('data-tipo', 'JORNADA');
    await expect(franja(page, AINA, '2026-11-09', 'MANANA')).toHaveAttribute('data-horas', '4.5');
    await expect(franja(page, AINA, '2026-11-09', 'TARDE')).toHaveAttribute('data-tipo', 'JORNADA');
    await expect(franja(page, AINA, '2026-11-09', 'TARDE')).toHaveAttribute('data-horas', '3.5');
    await expect(franja(page, ELENA, '2026-11-09', 'MANANA')).toHaveAttribute('data-horas', '4.5');
    await expect(franja(page, ELENA, '2026-11-09', 'TARDE')).toHaveCount(0);
    await expect(franja(page, IRENE, '2026-11-09', 'TARDE')).toHaveAttribute('data-horas', '3.5');
    await expect(franja(page, IRENE, '2026-11-09', 'MANANA')).toHaveCount(0);
    // Mañana y tarde distintas el mismo día.
    await expect(franja(page, NURIA, '2026-11-10', 'MANANA')).toHaveAttribute('data-tipo', 'JORNADA');
    await expect(franja(page, NURIA, '2026-11-10', 'TARDE')).toHaveAttribute('data-tipo', 'PERMISO_MEDICO');
    await expect(franja(page, CLARA, '2026-11-13', 'TARDE')).toHaveAttribute('data-tipo', 'ASUNTOS_PROPIOS');
    await expect(franja(page, MARTA, '2026-11-11', 'MANANA')).toHaveAttribute('data-tipo', 'BAJA');
    await expect(franja(page, AINA, '2026-11-14', 'MANANA')).toHaveAttribute('data-tipo', ''); // sábado libre
    await expect(franja(page, AINA, '2026-11-09', 'MANANA')).toHaveAttribute('aria-label', 'Aina Bosch Ferrer, lunes, 9 de noviembre de 2026, mañana: Jornada, 4,5 h, planificado');
    // Quién trabaja: 13 menos la baja de Marta (Núria trabaja por la mañana).
    await expect(page.locator('[data-pie="2026-11-10"]')).toHaveText('12');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_semana.png'), fullPage: true });

    // Selector: PIO y RITA por separado.
    await page.locator('[data-selector-farmacia="PIO"]').click();
    await expect(page).toHaveURL(/farmacia=PIO/);
    await expect(page.locator('tbody tr[data-fila]')).toHaveCount(10);
    await page.locator('[data-selector-farmacia="RITA"]').click();
    await expect(page.locator('tbody tr[data-fila]')).toHaveCount(16);
    await page.locator('[data-selector-farmacia="AMBAS"]').click();

    // Anterior: semana confirmada (sólido con ✓), con el descanso de Judit y su nota.
    await page.locator('[data-navegar="anterior"]').click();
    await expect(page.locator('[data-periodo]')).toHaveText('2–8 nov 2026');
    await expect(franja(page, JUDIT, '2026-11-06', 'TARDE')).toHaveAttribute('data-estado', 'CONFIRMADO');
    await expect(franja(page, JUDIT, '2026-11-06', 'TARDE')).toHaveAttribute('data-nota', 'Compensa el sábado 31 de octubre');
    await expect(franja(page, AINA, '2026-11-02', 'MANANA').locator('.cal-ev-ok')).toBeVisible();
    await page.locator('[data-navegar="siguiente"]').click();
    await page.locator('[data-navegar="siguiente"]').click();
    await expect(page.locator('[data-periodo]')).toHaveText('16–22 nov 2026');
    // Nota visible al pasar el ratón (title) y marcada con ✎.
    const rosa = franja(page, ROSA, '2026-11-18', 'MANANA');
    await expect(rosa).toHaveAttribute('data-tipo', 'ASUNTOS_PROPIOS');
    await expect(rosa).toHaveAttribute('title', /Nota: Gestión en el ayuntamiento/);
    await expect(rosa.locator('[data-con-nota]')).toBeVisible();
    await expect(franja(page, ROSA, '2026-11-18', 'TARDE')).toHaveAttribute('data-tipo', 'JORNADA');

    // Filtros: categoría, persona y tipo (los otros tipos se atenúan, nunca se ocultan).
    // TA-REAL: categorías del esquema (la titular es su propia categoría).
    await expect(page.locator('[data-filtro="categoria"] option')).toHaveText(['Todas las categorías', 'Farmacéutica titular', 'Farmacéutica adjunta', 'Técnica', 'Auxiliar', 'Otra']);
    await page.locator('[data-filtro="categoria"]').selectOption('FARMACEUTICA_ADJUNTA');
    await expect(page.locator('tbody tr[data-fila]')).toHaveCount(2); // Laura (mañana y tarde)
    await page.locator('[data-filtro="categoria"]').selectOption('FARMACEUTICA_TITULAR');
    await expect(page.locator('tbody tr[data-fila]')).toHaveCount(4); // titular de cada farmacia
    await page.locator('[data-filtro="categoria"]').selectOption('');
    await page.locator('[data-filtro="persona"]').selectOption(AINA);
    await expect(page.locator('tbody tr[data-fila]')).toHaveCount(2);
    await page.locator('[data-filtro="persona"]').selectOption('');
    await page.locator('[data-filtro="tipo"]').selectOption('VACACIONES');
    await expect(franja(page, AINA, '2026-11-17', 'MANANA').locator('.cal-ev')).not.toHaveClass(/atenuado/);
    await expect(franja(page, CLARA, '2026-11-17', 'MANANA').locator('.cal-ev')).toHaveClass(/atenuado/);
  });

  test('Hoy: vuelve a la semana actual del reloj', async ({ page }) => {
    await page.clock.setFixedTime(new Date('2026-11-12T10:00:00'));
    await abrir(page, '?fecha=2026-12-21');
    await expect(page.locator('[data-periodo]')).toHaveText('21–27 dic 2026');
    await page.locator('[data-navegar="hoy"]').click();
    await expect(page.locator('[data-periodo]')).toHaveText('9–15 nov 2026');
    await expect(page.locator('th.cal-col.hoy')).toHaveAttribute('data-columna', '2026-11-12');
  });

  test('vistas mes (día partido), año (resumen por día) y por persona', async ({ page }) => {
    await abrir(page, '?vista=mes&fecha=2026-11-09');
    await expect(page.locator('[data-periodo]')).toHaveText('Noviembre de 2026');
    await expect(page.locator('[data-rejilla="mes"] thead th.cal-col')).toHaveCount(30);
    await expect(diaCompleto(page, MARTA, '2026-11-12')).toHaveAttribute('data-tipo-manana', 'BAJA');
    await expect(diaCompleto(page, NURIA, '2026-11-10')).toHaveAttribute('data-tipo-manana', 'JORNADA');
    await expect(diaCompleto(page, NURIA, '2026-11-10')).toHaveAttribute('data-tipo-tarde', 'PERMISO_MEDICO');
    await expect(diaCompleto(page, ELENA, '2026-11-10')).toHaveAttribute('data-tipo-tarde', '');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_mes.png'), fullPage: true });

    await page.locator('[data-vista-boton="anio"]').click();
    await expect(page.locator('[data-periodo]')).toHaveText('2026');
    await expect(page.locator('[data-vista-anio] [data-mes]')).toHaveCount(12);
    await expect(page.locator('[data-anio-vacio]')).toHaveCount(0);
    await expect(page.locator('[data-dia="2026-11-17"]')).toHaveAttribute('data-ausencias', '1'); // vacaciones de Aina
    await expect(page.locator('[data-dia="2026-11-17"]')).toHaveAttribute('data-trabajan', '12');
    await expect(page.locator('[data-dia="2026-11-18"]')).toHaveAttribute('data-ausencias', '2'); // + mañana de Rosa
    await expect(page.locator('[data-dia="2026-11-18"]')).toHaveAttribute('data-trabajan', '12'); // Rosa trabaja por la tarde
    await expect(page.locator('[data-dia="2026-11-10"]')).toHaveAttribute('title', /Permiso médico: Núria Pons Valls; Baja: Marta Vila Soler/);
    await expect(page.locator('[data-mes="2026-11"] h3')).toContainText('23 ausencias');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_anio.png'), fullPage: true });
    await page.locator('[data-dia="2026-11-10"]').click();
    await expect(page.locator('[data-vista-boton="semana"]')).toHaveAttribute('aria-checked', 'true');
    await expect(page.locator('[data-periodo]')).toHaveText('9–15 nov 2026');

    await abrir(page, `?vista=persona&fecha=2026-11-09&persona=${AINA}`);
    await expect(page.locator('[data-rejilla="persona"] tbody tr[data-fila]')).toHaveCount(12);
    // TA-REAL: días y horas (horas_efectivas) por tipo.
    await expect(page.locator('[data-total-tipo="VACACIONES"] dd')).toHaveText('5 días · 40 h');
    await expect(page.locator('[data-total-tipo="JORNADA"] dd')).toHaveText('15 días · 120 h');
    await expect(page.locator('[data-total-tipo="TURNO_GUARDIA"]')).toHaveCount(0); // tipos de TA3: solo si hay alguno
    await expect(diaCompleto(page, AINA, '2026-11-18')).toHaveAttribute('data-tipo-tarde', 'VACACIONES');
    await expect(page.locator(`[data-celda="${AINA}|2026-02-30"]`)).toHaveCount(0);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_persona.png'), fullPage: true });
  });

  test('pintar por franja (clic y arrastre), día completo en el mes, goma, deshacer e historial plegado', async ({ page }) => {
    await abrir(page, '?farmacia=PIO&fecha=2026-12-07');
    await expect(page.locator('[data-herramienta="seleccion"]')).toHaveAttribute('aria-pressed', 'true'); // por defecto no pinta

    // Clic: una franja.
    await page.locator('[data-herramienta="VACACIONES"]').click();
    await franja(page, AINA, '2026-12-07', 'MANANA').click();
    await expect(aviso(page)).toHaveText('Pintado Vacaciones 7 dic 2026: 1 día laborable × 1 persona · 1 franja.');
    await expect(franja(page, AINA, '2026-12-07', 'MANANA')).toHaveAttribute('data-tipo', 'VACACIONES');
    await expect(franja(page, AINA, '2026-12-07', 'MANANA')).toHaveAttribute('data-horas', '4.5');
    await expect(franja(page, AINA, '2026-12-07', 'TARDE')).toHaveAttribute('data-tipo', '');

    // Arrastre: Clara (mañana y tarde) y Elena (solo mañana) del 7 al 9 = 9 franjas, 6 días.
    await page.locator('[data-herramienta="PERMISO_RETRIBUIDO"]').click();
    await arrastrar(page, franja(page, CLARA, '2026-12-07', 'MANANA'), franja(page, ELENA, '2026-12-09', 'MANANA'));
    await expect(aviso(page)).toHaveText('Pintado Permiso retribuido 7–9 dic 2026: 3 días laborables × 2 personas.');
    for (const [id, f, fr] of [[CLARA, '2026-12-07', 'MANANA'], [CLARA, '2026-12-09', 'TARDE'], [ELENA, '2026-12-08', 'MANANA']] as const) {
      await expect(franja(page, id, f, fr)).toHaveAttribute('data-tipo', 'PERMISO_RETRIBUIDO');
    }
    await expect(franja(page, NURIA, '2026-12-08', 'MANANA')).toHaveAttribute('data-tipo', '');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_pintar.png'), fullPage: true });

    // Goma en una franja: la otra se queda.
    await page.locator('[data-herramienta="goma"]').click();
    await franja(page, CLARA, '2026-12-08', 'TARDE').click();
    await expect(aviso(page)).toHaveText('Borrado 8 dic 2026: 1 día laborable × 1 persona · 1 franja.');
    await expect(franja(page, CLARA, '2026-12-08', 'TARDE')).toHaveAttribute('data-tipo', '');
    await expect(franja(page, CLARA, '2026-12-08', 'MANANA')).toHaveAttribute('data-tipo', 'PERMISO_RETRIBUIDO');

    // Deshacer: botón y luego Ctrl+Z.
    await expect(page.locator('[data-deshacer-que]')).toHaveText('Borrado 8 dic 2026: 1 día laborable × 1 persona · 1 franja');
    await page.locator('[data-accion="deshacer"]').click();
    await expect(aviso(page)).toHaveText('Deshecho «Borrado 8 dic 2026»: 1 día laborable × 1 persona · 1 franja.');
    await expect(franja(page, CLARA, '2026-12-08', 'TARDE')).toHaveAttribute('data-tipo', 'PERMISO_RETRIBUIDO');
    await page.keyboard.press('Control+z');
    await expect(aviso(page)).toHaveText('Deshecho «Pintado Permiso retribuido 7–9 dic 2026»: 3 días laborables × 2 personas.');
    await expect(franja(page, CLARA, '2026-12-07', 'MANANA')).toHaveAttribute('data-tipo', '');

    // Historial plegado por defecto; un clic lo despliega.
    const h = await abrirHistorial(page);
    const cambios = h.locator('[data-cambio]');
    await expect(cambios.locator('[data-cambio-texto]')).toHaveText([
      'Deshecho «Pintado Permiso retribuido 7–9 dic 2026»: 3 días laborables × 2 personas',
      'Deshecho «Borrado 8 dic 2026»: 1 día laborable × 1 persona · 1 franja',
      'Borrado 8 dic 2026: 1 día laborable × 1 persona · 1 franja',
      'Pintado Permiso retribuido 7–9 dic 2026: 3 días laborables × 2 personas',
      'Pintado Vacaciones 7 dic 2026: 1 día laborable × 1 persona · 1 franja',
    ]);
    await expect(cambios.nth(2)).toHaveAttribute('data-deshecho', 'si');
    await expect(cambios.first()).toContainText('Marc');
    await cambios.nth(4).locator('summary').click();
    await expect(cambios.nth(4).locator('.cal-trazas li')).toHaveText([/Aina Bosch Ferrer · .*7 dic · mañana: Vacaciones 4,5 h/]);

    // Mes: un clic en el día completo aplica a las franjas que tenga la persona.
    await abrir(page, '?farmacia=PIO&vista=mes&fecha=2026-12-01');
    await expect(page.locator('[data-ayuda-franjas]')).toContainText('un clic');
    await page.locator('[data-herramienta="BAJA"]').click();
    await diaCompleto(page, NURIA, '2026-12-10').click();
    await expect(aviso(page)).toHaveText('Pintado Baja 10 dic 2026: 1 día laborable × 1 persona.');
    await expect(diaCompleto(page, NURIA, '2026-12-10')).toHaveAttribute('data-tipo-manana', 'BAJA');
    await expect(diaCompleto(page, NURIA, '2026-12-10')).toHaveAttribute('data-tipo-tarde', 'BAJA');
    await diaCompleto(page, ELENA, '2026-12-10').click();
    await expect(diaCompleto(page, ELENA, '2026-12-10')).toHaveAttribute('data-tipo-manana', 'BAJA');
    await expect(diaCompleto(page, ELENA, '2026-12-10')).toHaveAttribute('data-tipo-tarde', ''); // media mañana: solo su franja
  });

  test('rellenar (semana y mes), confirmar, selección, detalle del día con horas y nota', async ({ page }) => {
    await abrir(page, '?farmacia=PIO&fecha=2026-12-14');
    await page.locator('[data-herramienta="VACACIONES"]').click();
    await franja(page, AINA, '2026-12-15', 'TARDE').click();

    // Rellenar: por franja según la ficha, sin pisar la tarde de vacaciones.
    await page.locator('[data-accion="rellenar"]').click();
    await expect(aviso(page)).toHaveText('Rellenado 14–20 dic 2026: 5 días laborables × 5 personas · 39 franjas.'); // Aina, solo la mañana del 15
    await expect(franja(page, AINA, '2026-12-15', 'MANANA')).toHaveAttribute('data-tipo', 'JORNADA');
    await expect(franja(page, AINA, '2026-12-15', 'TARDE')).toHaveAttribute('data-tipo', 'VACACIONES');
    await expect(franja(page, ELENA, '2026-12-14', 'MANANA')).toHaveAttribute('data-horas', '4.5');
    await expect(franja(page, CLARA, '2026-12-14', 'MANANA')).toHaveAttribute('data-horas', '4.5'); // TA2-3: completa 4,5 + 3,5
    await expect(franja(page, CLARA, '2026-12-14', 'TARDE')).toHaveAttribute('data-horas', '3.5');
    await expect(franja(page, AINA, '2026-12-19', 'MANANA')).toHaveAttribute('data-tipo', '');
    await page.locator('[data-accion="rellenar"]').click();
    await expect(aviso(page)).toHaveText('Sin cambios: esos días ya estaban así.');

    // Confirmar la semana; lo confirmado no se pinta.
    await page.locator('[data-accion="confirmar-periodo"]').click();
    await expect(aviso(page)).toHaveText('Confirmado 14–20 dic 2026: 5 días laborables × 5 personas.');
    await expect(page.locator('[data-rejilla="semana"] [data-estado="CONFIRMADO"]')).toHaveCount(40);
    await page.locator('[data-herramienta="BAJA"]').click();
    await franja(page, AINA, '2026-12-14', 'MANANA').click();
    await expect(aviso(page)).toHaveText('Sin cambios: esos días ya estaban así. 1 franja confirmada no se ha tocado (quita antes la confirmación).');

    // Detalle del día (una franja seleccionada): quitar la confirmación, horas realizadas y nota.
    await page.locator('[data-herramienta="seleccion"]').click();
    await franja(page, AINA, '2026-12-16', 'TARDE').click();
    await expect(page.locator('[data-seleccionados]')).toHaveText('1 seleccionado');
    await expect(page.locator('[data-detalle-dia]')).toContainText('Confirmado: quita la confirmación para cambiar las horas o la nota.');
    // TA2-4: el campo Nota se ve siempre (en lo confirmado, bloqueado) con su aviso.
    const editor = page.locator('[data-editor-evento="TARDE"]');
    await expect(editor.locator('input[name="nota_evento"]')).toBeDisabled();
    await expect(editor.locator('[data-aviso-nota]')).toHaveText(AVISO_NOTA);
    await page.locator('[data-sel="desconfirmar"]').click();
    await expect(aviso(page)).toHaveText('Quitada la confirmación 16 dic 2026: 1 día laborable × 1 persona · 1 franja.');
    await expect(editor.locator('input[name="nota_evento"]')).toBeEnabled();
    await expect(editor.locator('[data-aviso-nota]')).toHaveText(AVISO_NOTA);
    await expect(editor.locator('input[name="horas_evento"]')).toHaveValue('3,5'); // tarde de una completa
    await expect(editor.locator('input[name="nota_evento"]')).toHaveAttribute('maxlength', '200');
    await editor.locator('input[name="horas_evento"]').fill('2,5');
    await editor.locator('input[name="nota_evento"]').fill('Sale antes para cubrir a Clara');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_detalle_nota.png'), fullPage: true });
    await editor.locator('[data-sel="guardar"]').click();
    await expect(aviso(page)).toHaveText('Editado 16 dic 2026: 1 día laborable × 1 persona · 1 franja.');
    const tarde = franja(page, AINA, '2026-12-16', 'TARDE');
    await expect(tarde).toHaveAttribute('data-horas', '2.5');
    await expect(tarde).toHaveAttribute('data-nota', 'Sale antes para cubrir a Clara');
    await expect(tarde).toHaveAttribute('title', /Nota: Sale antes para cubrir a Clara/);
    await expect(page.locator('[data-nota-detalle]')).toHaveText('Nota: Sale antes para cubrir a Clara');
    await page.locator('[data-sel="confirmar"]').click();
    await expect(tarde).toHaveAttribute('data-estado', 'CONFIRMADO');
    // La nota queda en el historial.
    const h = await abrirHistorial(page);
    await h.locator('[data-cambio="EDITAR"] summary').first().click();
    await expect(h.locator('[data-cambio="EDITAR"] .cal-trazas li').first()).toContainText('Jornada 2,5 h · nota: «Sale antes para cubrir a Clara»');

    // Selección múltiple arrastrando (se suma) y pintar la selección. La rejilla, arriba: la barra flotante no la tapa.
    await page.locator('[data-rejilla="semana"]').evaluate((e) => e.scrollIntoView({ block: 'start' }));
    await arrastrar(page, franja(page, CLARA, '2026-12-19', 'MANANA'), franja(page, ELENA, '2026-12-20', 'MANANA'));
    await expect(page.locator('[data-seleccionados]')).toHaveText('7 seleccionados');
    await page.locator('[data-tipo-seleccion]').selectOption('DESCANSO_COMPENSATORIO');
    await page.locator('[data-sel="pintar"]').click();
    await expect(aviso(page)).toHaveText('Pintado Descanso compensatorio 19–20 dic 2026: 2 días × 2 personas. 1 franja confirmada no se ha tocado (quita antes la confirmación).');
    await expect(franja(page, ELENA, '2026-12-20', 'MANANA')).toHaveAttribute('data-tipo', 'DESCANSO_COMPENSATORIO');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_rellenar_confirmar.png'), fullPage: true });
    await page.locator('[data-sel="limpiar"]').click();
    await expect(page.locator('[data-barra-seleccion]')).toHaveCount(0);

    // Mes: rellenar diciembre de una persona de RITA (media tarde: solo tardes de 3,5 h).
    await abrir(page, `?farmacia=RITA&vista=mes&fecha=2026-12-01&persona=${IRENE}`);
    await page.locator('[data-accion="rellenar"]').click();
    await expect(aviso(page)).toHaveText('Rellenado diciembre de 2026: 23 días laborables × 1 persona.');
    await expect(diaCompleto(page, IRENE, '2026-12-31')).toHaveAttribute('data-tipo-tarde', 'JORNADA');
    await expect(diaCompleto(page, IRENE, '2026-12-31')).toHaveAttribute('data-tipo-manana', '');
  });

  test('año vacío: se ofrece rellenarlo con confirmación; rellenar año completo; se deshace de una vez', async ({ page }) => {
    await abrir(page, '?farmacia=PIO&vista=anio&fecha=2027-01-01');
    const oferta = page.locator('[data-anio-vacio]');
    await expect(oferta).toContainText('2027 está vacío para estas personas');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_anio_vacio.png'), fullPage: true });
    // Cancelar no crea nada.
    await page.locator('[data-ofrecer-anio]').click();
    await expect(page.locator('[data-confirmar-anio]')).toContainText('5 personas en todo 2027, sin tocar lo ya pintado ni lo confirmado');
    await page.getByRole('button', { name: 'Cancelar' }).click();
    await expect(page.locator('[data-confirmar-anio]')).toHaveCount(0);
    await expect(oferta).toBeVisible();
    // Confirmar: 5 personas × 261 laborables de 2027.
    await page.locator('[data-ofrecer-anio]').click();
    await page.locator('[data-confirmar-anio-si]').click();
    await expect(aviso(page)).toHaveText('Rellenado 2027: 261 días laborables × 5 personas.'); // TA2-4: no «1305 días»
    await expect(oferta).toHaveCount(0);
    await expect(page.locator('[data-dia="2027-03-03"]')).toHaveAttribute('data-trabajan', '5');
    await expect(page.locator('[data-dia="2027-03-06"]')).toHaveAttribute('data-trabajan', '0'); // sábado
    await page.locator('[data-accion="deshacer"]').click();
    await expect(aviso(page)).toHaveText('Deshecho «Rellenado 2027»: 261 días laborables × 5 personas.');
    await expect(oferta).toBeVisible();
    // Botón «Rellenar año completo» en la vista por persona (2028, bisiesto: 260 laborables).
    await abrir(page, `?farmacia=RITA&vista=persona&fecha=2028-01-01&persona=${IRENE}`);
    await page.locator('[data-accion="rellenar-anio"]').click();
    await expect(page.locator('[data-confirmar-anio]')).toContainText('1 persona en todo 2028');
    await page.locator('[data-confirmar-anio-si]').click();
    await expect(aviso(page)).toHaveText('Rellenado 2028: 260 días laborables × 1 persona.');
    await expect(page.locator('[data-total-tipo="JORNADA"] dd')).toHaveText('260 días · 910 h'); // 260 × 3,5 h
    await expect(diaCompleto(page, IRENE, '2028-02-29')).toHaveAttribute('data-tipo-tarde', 'JORNADA');
  });

  test('TA2-4: «Añadir nota»: franja vacía pide pintar antes; una, su editor; varias, la misma nota (vacías omitidas y contadas)', async ({ page }) => {
    await abrir(page, '?farmacia=PIO&fecha=2026-12-28');
    // Franja vacía: el detalle muestra la Nota con su aviso; anotar pide pintar antes.
    await franja(page, AINA, '2026-12-28', 'MANANA').click();
    const libre = page.locator('[data-detalle-libre="MANANA"]');
    await expect(libre.locator('input[name="nota_evento"]')).toBeVisible();
    await expect(libre.locator('[data-aviso-nota]')).toHaveText(AVISO_NOTA);
    await libre.locator('input[name="nota_evento"]').fill('Formación');
    await expect(libre.locator('[data-error-campo="nota"]')).toHaveText(AVISO_NOTA_VACIA);
    await page.locator('[data-sel="anotar"]').click();
    await expect(page.locator('[data-aviso-anotar]')).toHaveText(`${AVISO_NOTA_VACIA}.`);
    await expect(franja(page, AINA, '2026-12-28', 'MANANA')).toHaveAttribute('data-tipo', ''); // no se crea nada
    await page.locator('[data-sel="limpiar"]').click();

    // Pintar tres franjas; con una seleccionada, «Añadir nota» lleva a su campo Nota.
    await page.locator('[data-herramienta="VACACIONES"]').click();
    for (const [id, fr] of [[AINA, 'MANANA'], [AINA, 'TARDE'], [CLARA, 'MANANA']] as const) await franja(page, id, '2026-12-28', fr).click();
    await page.locator('[data-herramienta="seleccion"]').click();
    await franja(page, AINA, '2026-12-28', 'MANANA').click();
    await page.locator('[data-sel="anotar"]').click();
    await expect(page.locator('[data-editor-evento="MANANA"] input[name="nota_evento"]')).toBeFocused();
    await expect(page.locator('[data-anotar-seleccion]')).toHaveCount(0);

    // Varias: la misma nota a las que tienen evento; la tarde vacía de Clara se omite y se avisa.
    for (const [id, fr] of [[AINA, 'TARDE'], [CLARA, 'MANANA'], [CLARA, 'TARDE']] as const) await franja(page, id, '2026-12-28', fr).click();
    await expect(page.locator('[data-seleccionados]')).toHaveText('4 seleccionados');
    await page.locator('[data-sel="anotar"]').click();
    const form = page.locator('[data-anotar-seleccion]');
    await expect(form).toContainText('Misma nota para las 3 franjas con evento (se omite 1 vacía)');
    await expect(form.locator('[data-aviso-nota]')).toHaveText(AVISO_NOTA);
    await form.locator('input[name="nota_seleccion"]').fill('Formación en Reus');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_anotar_seleccion.png'), fullPage: true });
    await form.locator('[data-sel="aplicar-nota"]').click();
    await expect(aviso(page)).toHaveText('Anotado 28 dic 2026: 1 día laborable × 2 personas · 3 franjas. '
      + '1 franja vacía no se ha anotado: pinta primero un evento para poder anotarlo.');
    for (const [id, fr] of [[AINA, 'MANANA'], [AINA, 'TARDE'], [CLARA, 'MANANA']] as const) {
      await expect(franja(page, id, '2026-12-28', fr)).toHaveAttribute('data-nota', 'Formación en Reus');
    }
    await expect(franja(page, CLARA, '2026-12-28', 'TARDE')).toHaveAttribute('data-tipo', '');
    // Se deshace de una vez.
    await page.locator('[data-accion="deshacer"]').click();
    await expect(aviso(page)).toHaveText('Deshecho «Anotado 28 dic 2026»: 1 día laborable × 2 personas · 3 franjas.');
    await expect(franja(page, AINA, '2026-12-28', 'TARDE')).toHaveAttribute('data-nota', '');
  });

  test('TA-REAL: «Notas próximas»: de hoy en adelante, por fecha («Persona — fecha: nota»); las pasadas no salen', async ({ page }) => {
    await page.clock.setFixedTime(new Date('2026-11-13T10:00:00'));
    await abrir(page, '?fecha=2026-11-09');
    const caja = page.locator('[data-notas-proximas]');
    await expect(caja.locator('h2')).toHaveText('✎ Notas próximas');
    const lineas = caja.locator('[data-nota-proxima]');
    // Las de ejemplo desde el 13 nov (la de Judit, del 6, ya pasó). Otras pruebas pueden añadir notas de diciembre detrás.
    await expect(lineas.nth(0)).toHaveText(/^Rosa Camps Oliver RITA — mié, 18 nov: Gestión en el ayuntamiento$/);
    await expect(lineas.nth(1)).toHaveText(/^Elena Mas Garriga PIO — mié, 25 nov: Traslado de domicilio$/);
    await expect(lineas.nth(2)).toHaveText(/^Elena Mas Garriga PIO — jue, 26 nov: Traslado de domicilio$/);
    await expect(caja).not.toContainText('Compensa el sábado 31 de octubre');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_notas_proximas.png') });
    // Un clic lleva a la semana de esa persona.
    await lineas.nth(1).click();
    await expect(page.locator('[data-periodo]')).toHaveText('23–29 nov 2026');
    await expect(page.locator('tbody tr[data-fila]')).toHaveCount(2); // filtro: solo Elena (media mañana: dos subfilas)
    // Por farmacia: RITA solo ve las suyas.
    await abrir(page, '?farmacia=RITA&fecha=2026-11-09');
    await expect(page.locator('[data-notas-proximas] [data-nota-proxima]').first()).toContainText('Rosa Camps Oliver');
    await expect(page.locator('[data-notas-proximas]')).not.toContainText('Elena Mas Garriga');
  });

  test('colores configurables en la leyenda (solo en este navegador)', async ({ page }) => {
    await abrir(page, '?fecha=2026-11-16');
    const vac = page.locator('[data-herramienta="VACACIONES"]');
    await expect(vac).toHaveAttribute('style', /--c: #e3b505/);
    await page.locator('[data-editar-colores]').click();
    await page.locator('[data-color="VACACIONES"]').fill('#ff9ec4');
    await expect(vac).toHaveAttribute('style', /--c: #ff9ec4/);
    await page.reload();
    await expect(page.locator('[data-herramienta="VACACIONES"]')).toHaveAttribute('style', /--c: #ff9ec4/);
    await page.locator('[data-editar-colores]').click();
    await page.locator('[data-restablecer-colores]').click();
    await expect(page.locator('[data-herramienta="VACACIONES"]')).toHaveAttribute('style', /--c: #e3b505/);
  });

  test('escritura solo en /api/rrhh/eventos con sesión y mismo origen; DELETE y PUT siguen en 405', async ({ page }) => {
    const cuerpo = { accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ trabajadora_id: TITULAR_PIO, fecha: '2026-12-28' }] };
    expect((await page.request.post('/api/rrhh/eventos', { data: cuerpo, headers: { origin: 'http://evil.example' } })).status()).toBe(403);
    expect((await page.request.delete(`/api/rrhh/eventos/${AINA}`)).status()).toBe(405);
    expect((await page.request.put('/api/rrhh/eventos', { data: cuerpo })).status()).toBe(405);
    expect((await page.request.post('/api/inicio', { data: {} })).status()).toBe(405);
  });
});

test.describe('Modo REAL simulado (intercepción): sin datos de ejemplo', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('TA-REAL: conectado: banner real; goma y deshacer de pintados nuevos desactivados con aviso', async ({ page }) => {
    const AVISO = 'Pendiente de que la base de datos permita anular eventos';
    await page.route('**/api/rrhh/estado', (r) => r.fulfill({ json: {
      modo: 'REAL', conectado: true, datos_ejemplo: false, mensaje: 'Datos reales: cada cambio se guarda en la base de datos con autor Marc', anular_eventos: false } }));
    // Calendario de ejemplo como si viniera de REAL: sin anular eventos y con un último cambio que creó eventos.
    await page.route('**/api/rrhh/eventos?**', async (r) => {
      const resp = await r.fetch();
      const d = await resp.json();
      r.fulfill({ response: resp, json: { ...d, anular_eventos: false, ultimo_cambio: {
        id: 'f9999999-0000-4000-8000-000000000001', origen: 'PINTAR', tipo: 'VACACIONES', quien: 'Marc', cuando: '2026-11-13T09:00:00.000Z', farmacias: ['PIO'],
        n: 1, dias: 1, fechas: 1, laborables: true, parcial: true, creados: 1, personas: ['Aina Bosch Ferrer'], desde: '2026-12-07', hasta: '2026-12-07',
        periodo: { desde: '2026-12-07', hasta: '2026-12-07' }, omitidas_confirmadas: 0, deshecho: false, deshace: null } } });
    });
    await abrir(page, '?farmacia=PIO&fecha=2026-11-09');
    await expect(page.locator('[data-banner-real]')).toBeVisible();
    await expect(page.locator('[data-banner-ejemplo]')).toHaveCount(0);
    await expect(page.locator('[data-herramienta="goma"]')).toBeDisabled();
    await expect(page.locator('[data-aviso-goma]')).toHaveText(`Goma: ${AVISO.charAt(0).toLowerCase()}${AVISO.slice(1)}`);
    await expect(page.locator('[data-accion="deshacer"]')).toBeDisabled();
    await expect(page.locator('[data-aviso-anular-deshacer]')).toHaveText(AVISO);
    await franja(page, AINA, '2026-11-10', 'MANANA').click();
    await expect(page.locator('[data-sel="borrar"]')).toBeDisabled();
    await expect(page.locator('[data-sel="borrar"]')).toHaveAttribute('title', AVISO);
    // FESTIVO, TURNO_GUARDIA y LOCALIZADA no están en la paleta (TA3).
    for (const t of ['FESTIVO', 'TURNO_GUARDIA', 'LOCALIZADA']) await expect(page.locator(`[data-herramienta="${t}"]`)).toHaveCount(0);
    await expect(page.locator('[data-tipos-ta3]')).toContainText('Turno de guardia y Localizada no suman horas');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_real_goma_desactivada.png'), fullPage: true });
  });

  test('TA-REAL: sin credencial: «Falta configurar la credencial de Trabajadores»; no pide eventos', async ({ page }) => {
    const pedidas: string[] = [];
    const AVISO = 'Falta configurar la credencial de Trabajadores';
    await page.route('**/api/estado', (r) => r.fulfill({ json: { modo: 'REAL', farmacia: 'PIO', solo_lectura: true, usuario: 'Pío' } }));
    await page.route('**/api/rrhh/**', (r) => {
      pedidas.push(new URL(r.request().url()).pathname);
      return new URL(r.request().url()).pathname === '/api/rrhh/estado'
        ? r.fulfill({ json: { modo: 'REAL', conectado: false, datos_ejemplo: false, mensaje: AVISO, anular_eventos: false } })
        : r.fulfill({ status: 503, json: { error: 'CREDENCIAL_TRABAJADORES_AUSENTE', mensaje: AVISO } });
    });
    await page.goto('/trabajadores/calendario?fecha=2026-11-09');
    await expect(page.locator('[data-rrhh-pendiente]')).toContainText(AVISO);
    await expect(page.locator('[data-banner-ejemplo], [data-calendario]')).toHaveCount(0);
    for (const n of ['Aina Bosch Ferrer', 'Marta Vila Soler']) await expect(page.getByText(n)).toHaveCount(0);
    expect(pedidas.every((p) => p === '/api/rrhh/estado')).toBe(true);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_real_pendiente.png'), fullPage: true });
  });
});

test.describe('Móvil 390', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test('semana con scroll horizontal dentro de la rejilla y pintar con toque por franja', async ({ page }) => {
    await abrir(page, '?farmacia=PIO&fecha=2026-12-21');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    const marco = page.locator('[data-rejilla="semana"]');
    expect(await marco.evaluate((m) => m.scrollWidth > m.clientWidth)).toBe(true); // la semana se desplaza dentro
    await page.locator('[data-herramienta="JORNADA"]').tap();
    await franja(page, AINA, '2026-12-22', 'MANANA').tap();
    await expect(franja(page, AINA, '2026-12-22', 'MANANA')).toHaveAttribute('data-tipo', 'JORNADA');
    await expect(aviso(page)).toHaveText('Pintado Jornada 22 dic 2026: 1 día laborable × 1 persona · 1 franja.');
    await page.locator('[data-herramienta="ASUNTOS_PROPIOS"]').tap();
    await franja(page, CLARA, '2026-12-23', 'TARDE').tap();
    await expect(franja(page, CLARA, '2026-12-23', 'TARDE')).toHaveAttribute('data-tipo', 'ASUNTOS_PROPIOS');
    await expect(franja(page, CLARA, '2026-12-23', 'MANANA')).toHaveAttribute('data-tipo', '');
    await page.screenshot({ path: join(CAPTURAS, 'movil390_semana.png'), fullPage: true });
    await page.locator('[data-herramienta="goma"]').tap();
    await franja(page, AINA, '2026-12-22', 'MANANA').tap();
    await expect(franja(page, AINA, '2026-12-22', 'MANANA')).toHaveAttribute('data-tipo', '');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await abrir(page, '?vista=anio&fecha=2026-11-09');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_anio.png'), fullPage: true });
  });
});
