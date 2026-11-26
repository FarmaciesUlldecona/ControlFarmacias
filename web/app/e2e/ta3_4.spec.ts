// TA3-4: guardias y festivos pintados en el calendario de Trabajadores (decisión de Marc). Herramientas Guardia, Apoyo
// sábado, Guardia otra farmacia y Festivo; Goma sobre sus marcas; deshacer en la pila (también restaurar tras la goma);
// vista año con selector de guardia y apoyo; capa de marcas que no tapa jornada ni ausencias. Solo FIXTURES
// (playwright.config.ts lo exige); el servidor es común: cada prueba deshace todo lo que crea (semanas de 2027).
import { expect, test, type Page } from '@playwright/test';
import { join } from 'node:path';
import { entrar } from './sesion.ts';

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'ta3');
const ID = (n: number) => `e0000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const AINA = ID(1); const CLARA = ID(2); const ELENA = ID(4); const LAURA = ID(11); const MARTA = ID(12);

test.beforeEach(async ({ page }) => entrar(page));

async function abrir(page: Page, consulta: string) {
  const estado = await (await page.request.get('/api/estado')).json();
  expect(estado.modo).toBe('FIXTURES');
  await page.goto(`/trabajadores/calendario${consulta}`);
  await expect(page.locator('[data-calendario]')).toBeVisible();
  await expect(page.locator('[data-cabecera-guardias], [data-vista-anio]').first()).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}
const aviso = (page: Page) => page.locator('[data-aviso-calendario]');
const herramienta = (page: Page, h: string) => page.locator(`[data-herramienta="${h}"]`).click();
const celda = (page: Page, tid: string, fecha: string, franja = 'MANANA') => page.locator(`[data-celda="${tid}|${fecha}|${franja}"]`);
const cabecera = (page: Page, fecha: string) => page.locator(`[data-columna="${fecha}"] .cal-col-boton`);
async function deshacer(page: Page, texto: string | RegExp) {
  await page.locator('[data-accion="deshacer"]').click();
  await expect(aviso(page)).toHaveText(typeof texto === 'string' ? `Deshecho «${texto}».` : texto);
}

test.describe('Herramientas de guardia PC 1440', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('Guardia (toda la semana, «G»), Apoyo sábado («A»), confirmación al sustituir otra farmacia, OTRA; deshacer todo', async ({ page }) => {
    await abrir(page, '?fecha=2027-01-04');
    await expect(page.locator('[data-cabecera-guardias] [data-texto-guardia]')).toHaveText('Guardia: sin asignar');
    // TA4: + Guardia festiva.
    await expect(page.locator('[data-paleta-guardias] [data-herramienta]')).toHaveText(['GGuardia', 'AApoyo sábado', 'OTRAGuardia otra farmacia', 'FFestivo', 'GFGuardia festiva']);
    const jornadaAntes = await celda(page, AINA, '2027-01-05').getAttribute('data-tipo');

    // Guardia: clic en Aina el miércoles → guardia PIO toda la semana (lunes a domingo).
    await herramienta(page, 'guardia');
    await expect(page.locator('[data-ayuda-guardia="guardia"]')).toContainText('toda la semana');
    await celda(page, AINA, '2027-01-06').click();
    await expect(aviso(page)).toHaveText('Guardia PIO: Aina Bosch Ferrer, semana 4–10 ene 2027.');
    await expect(page.locator(`[data-capa-guardia^="${AINA}|2027-01-"] [data-franja-guardia="PIO"]`)).toHaveCount(7);
    await expect(page.locator(`[data-marca-g="${AINA}|2027-01-04"]`)).toHaveText('G');
    await expect(page.locator('[data-cabecera-guardias] [data-texto-guardia]')).toHaveText('Guardia: Aina Bosch Ferrer · Apoyo sábado: —');
    // La capa no cambia la celda ni sus eventos.
    expect(await celda(page, AINA, '2027-01-05').getAttribute('data-tipo')).toBe(jornadaAntes);
    await expect(celda(page, AINA, '2027-01-09')).toHaveAttribute('aria-label', /semana de guardia PIO/);

    // Apoyo sábado: en viernes, aviso y nada guardado; en sábado, Elena (media jornada de mañana: la marca va en su franja vacía).
    await herramienta(page, 'apoyo');
    await celda(page, ELENA, '2027-01-08').click();
    await expect(aviso(page)).toHaveText('El apoyo se pinta en el sábado: haz clic en el sábado de esa persona. No se ha guardado nada.');
    await celda(page, AINA, '2027-01-09').click();
    await expect(aviso(page)).toContainText('tiene que ser otra persona');
    await celda(page, ELENA, '2027-01-09').click();
    await expect(aviso(page)).toHaveText('Apoyo sábado PIO: Elena Mas Garriga, 9 ene 2027.');
    await expect(page.locator(`[data-marca-a="${ELENA}|2027-01-09"]`)).toHaveText('A');
    await expect(page.locator('[data-cabecera-guardias] [data-texto-guardia]')).toHaveText('Guardia: Aina Bosch Ferrer · Apoyo sábado: Elena Mas Garriga');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_ta3_4_semana_guardia_apoyo.png'), fullPage: true });
    // Apoyo en una semana sin guardia de su farmacia (RITA): aviso.
    await celda(page, LAURA, '2027-01-09').click();
    await expect(aviso(page)).toHaveText('Ese fin de semana no hay guardia de RITA: pinta antes la guardia. No se ha guardado nada.');

    // Guardia de otra farmacia en una semana PIO: pide confirmación; Cancelar no cambia nada.
    await herramienta(page, 'guardia');
    await celda(page, LAURA, '2027-01-05').click();
    await expect(page.locator('[data-confirmar-guardia="semana"]')).toContainText('La semana 4–10 ene 2027 es de PIO (Aina Bosch Ferrer). ¿Sustituirla por la guardia de RITA (Laura Serra Coll)?');
    await page.locator('[data-confirmar-guardia-no]').click();
    await expect(page.locator(`[data-marca-g="${AINA}|2027-01-04"]`)).toBeVisible();

    // Mes: marcas en la fila de cada persona.
    await page.goto('/trabajadores/calendario?vista=mes&fecha=2027-01-01');
    await expect(page.locator(`[data-marca-g="${AINA}|2027-01-04"]`)).toBeVisible();
    await expect(page.locator(`[data-marca-a="${ELENA}|2027-01-09"]`)).toBeVisible();
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_ta3_4_mes.png'), fullPage: true });

    // OTRA: clic en la cabecera de un día de la semana siguiente → semana de farmacia ajena (gris en la cabecera).
    await herramienta(page, 'otra');
    await cabecera(page, '2027-01-13').click();
    await expect(aviso(page)).toHaveText('Guardia OTRA (farmacia ajena): semana 11–17 ene 2027.');
    await expect(page.locator('[data-otra-columna]')).toHaveCount(7);
    await expect(page.locator('[data-marca-otra="2027-01-11"]')).toHaveText('OTRA');
    // Guardia o Apoyo en la cabecera: indica que es en la fila de la persona.
    await herramienta(page, 'guardia');
    await cabecera(page, '2027-01-20').click();
    await expect(aviso(page)).toHaveText('Con Guardia, haz clic en la fila de la persona, en el día que toca.');

    // Deshacer (pila de la sesión): OTRA, apoyo y guardia.
    await expect(page.locator('[data-deshacer-que]')).toHaveText('Guardia OTRA (farmacia ajena): semana 11–17 ene 2027');
    await deshacer(page, 'Guardia OTRA (farmacia ajena): semana 11–17 ene 2027');
    await expect(page.locator('[data-otra-columna]')).toHaveCount(0);
    await deshacer(page, 'Apoyo sábado PIO: Elena Mas Garriga, 9 ene 2027');
    await expect(page.locator(`[data-marca-a="${ELENA}|2027-01-09"]`)).toHaveCount(0);
    await deshacer(page, 'Guardia PIO: Aina Bosch Ferrer, semana 4–10 ene 2027');
    await expect(page.locator(`[data-capa-guardia^="${AINA}|2027-01-0"]`)).toHaveCount(0);
  });

  test('Festivo (cabecera: nombre y ámbito) + guardia de festivo («GF»); goma de GF y del festivo (confirmación); deshacer restaura', async ({ page }) => {
    await abrir(page, '?fecha=2027-03-15');
    await herramienta(page, 'festivo');
    await cabecera(page, '2027-03-19').click();
    const dlg = page.locator('[data-dialogo-festivo="2027-03-19"]');
    await expect(dlg).toContainText('Nuevo festivo: Viernes, 19 de marzo de 2027');
    await expect(dlg.locator('select[name="ambito_festivo"]')).toHaveValue('LOCAL');
    await dlg.locator('[data-crear-festivo]').click();
    await expect(aviso(page)).toHaveText('Escribe el nombre del festivo. No se ha guardado nada.');
    await cabecera(page, '2027-03-19').click();
    await dlg.locator('input[name="nombre_festivo"]').fill('Sant Josep');
    await dlg.locator('select[name="ambito_festivo"]').selectOption('AUTONOMICO');
    await dlg.locator('[data-crear-festivo]').click();
    await expect(aviso(page)).toHaveText('Festivo: Sant Josep (19 mar 2027, autonómico).');
    await expect(page.locator('[data-columna="2027-03-19"]')).toHaveAttribute('data-festivo-columna', 'Sant Josep');
    await cabecera(page, '2027-03-19').click();
    await expect(aviso(page)).toHaveText('Ese día ya es festivo (Sant Josep). No se ha guardado nada.');

    // Guardia de festivo: herramienta Guardia y clic en Clara el día festivo.
    await herramienta(page, 'guardia');
    await celda(page, CLARA, '2027-03-19').click();
    await expect(aviso(page)).toHaveText('Guardia de festivo PIO: Clara Roig Pujol, Sant Josep (19 mar 2027).');
    await expect(page.locator(`[data-marca-gf="${CLARA}|2027-03-19"]`)).toHaveText('GF');
    await expect(page.locator('[data-cabecera-festivo="2027-03-19"]')).toContainText('Sant Josep · guardia PIO · Clara Roig Pujol');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_ta3_4_festivo.png'), fullPage: true });

    // Rellenar salta el festivo; pintar sobre él avisa (como en TA3).
    await page.goto(`/trabajadores/calendario?farmacia=RITA&fecha=2027-03-15&persona=${MARTA}`);
    await page.locator('[data-accion="rellenar"]').click();
    await expect(aviso(page)).toHaveText('Rellenado 15–21 mar 2027: 4 días laborables × 1 persona.');
    await herramienta(page, 'VACACIONES');
    await celda(page, MARTA, '2027-03-19').click();
    await expect(aviso(page)).toHaveText('Pintado Vacaciones 19 mar 2027: 1 día laborable × 1 persona · 1 franja. Ojo: 19 mar (Sant Josep) es festivo.');
    await deshacer(page, /^Deshecho «Pintado Vacaciones/);
    await deshacer(page, /^Deshecho «Rellenado/);

    // Goma: sobre la GF la quita; sobre el nombre del festivo pide confirmación (arrastra su guardia).
    await page.goto('/trabajadores/calendario?fecha=2027-03-15');
    await herramienta(page, 'goma');
    await expect(page.locator('[data-ayuda-guardia="goma"]')).toContainText('sobre una marca G, A, GF, OTRA');
    await page.locator(`[data-marca-gf="${CLARA}|2027-03-19"]`).click();
    await expect(aviso(page)).toHaveText('Quitada la guardia de Sant Josep (PIO (Clara Roig Pujol)).');
    await expect(page.locator(`[data-marca-gf="${CLARA}|2027-03-19"]`)).toHaveCount(0);
    await page.locator('[data-goma-festivo="2027-03-19"]').click();
    const conf = page.locator('[data-confirmar-guardia="anular_festivo"]');
    await expect(conf).toContainText('¿Dar de baja el festivo «Sant Josep» (19 mar 2027)? No se borra: queda en el historial.');
    await conf.locator('[data-confirmar-guardia-si]').click();
    await expect(aviso(page)).toHaveText('Festivo dado de baja: Sant Josep (19 mar 2027).');
    await expect(page.locator('[data-columna="2027-03-19"]')).not.toHaveAttribute('data-festivo-columna', /.*/);

    // Deshacer: el festivo vuelve (fila nueva), después su guardia; luego se deshacen guardia y alta.
    await deshacer(page, 'Festivo dado de baja: Sant Josep (19 mar 2027)');
    await expect(page.locator('[data-columna="2027-03-19"]')).toHaveAttribute('data-festivo-columna', 'Sant Josep');
    await deshacer(page, 'Quitada la guardia de Sant Josep (PIO (Clara Roig Pujol))');
    await expect(page.locator(`[data-marca-gf="${CLARA}|2027-03-19"]`)).toBeVisible();
    await deshacer(page, 'Guardia de festivo PIO: Clara Roig Pujol, Sant Josep (19 mar 2027)');
    await deshacer(page, 'Festivo: Sant Josep (19 mar 2027, autonómico)');
    await expect(page.locator('[data-columna="2027-03-19"]')).not.toHaveAttribute('data-festivo-columna', /.*/);
  });

  test('vista mes: Goma sobre G, A y OTRA; deshacer restaura cada una', async ({ page }) => {
    await abrir(page, '?vista=mes&fecha=2027-02-01');
    const dia = (tid: string, f: string) => page.locator(`[data-celda="${tid}|${f}"]`); // en el mes, un clic es el día completo
    await herramienta(page, 'guardia');
    await dia(AINA, '2027-02-02').click();
    await herramienta(page, 'apoyo');
    await dia(CLARA, '2027-02-06').click();
    await herramienta(page, 'otra');
    await cabecera(page, '2027-02-10').click();
    await expect(page.locator('[data-marca-otra="2027-02-08"]')).toBeVisible();
    await herramienta(page, 'goma');
    await page.locator(`[data-marca-a="${CLARA}|2027-02-06"]`).click();
    await expect(aviso(page)).toHaveText('Quitado el apoyo del sábado (Clara Roig Pujol), 6 feb 2027.');
    await page.locator(`[data-marca-g="${AINA}|2027-02-01"]`).click();
    await expect(aviso(page)).toHaveText('Quitada la guardia PIO (Aina Bosch Ferrer) de la semana 1–7 feb 2027.');
    await page.locator('[data-goma-otra="2027-02-08"]').click();
    await expect(aviso(page)).toHaveText('Quitada la guardia OTRA (farmacia ajena) de la semana 8–14 feb 2027.');
    await expect(page.locator('[data-capa-guardia], [data-otra-columna]')).toHaveCount(0);
    await deshacer(page, 'Quitada la guardia OTRA (farmacia ajena) de la semana 8–14 feb 2027');
    await expect(page.locator('[data-marca-otra="2027-02-08"]')).toBeVisible();
    await deshacer(page, 'Quitada la guardia PIO (Aina Bosch Ferrer) de la semana 1–7 feb 2027');
    await expect(page.locator(`[data-marca-g="${AINA}|2027-02-01"]`)).toBeVisible();
    await deshacer(page, 'Quitado el apoyo del sábado (Clara Roig Pujol), 6 feb 2027');
    await expect(page.locator(`[data-marca-a="${CLARA}|2027-02-06"]`)).toBeVisible();
    await deshacer(page, 'Guardia OTRA (farmacia ajena): semana 8–14 feb 2027');
    await deshacer(page, 'Apoyo sábado PIO: Clara Roig Pujol, 6 feb 2027');
    await deshacer(page, 'Guardia PIO: Aina Bosch Ferrer, semana 1–7 feb 2027');
    await expect(page.locator('[data-capa-guardia], [data-otra-columna]')).toHaveCount(0);
  });

  test('vista año: paleta sin tipos de evento; clic en la banda con Guardia abre el selector (farmacia, guardia y apoyo)', async ({ page }) => {
    await abrir(page, '?vista=anio&fecha=2027-01-01');
    await expect(page.locator('[data-herramienta="VACACIONES"]')).toHaveCount(0);
    await expect(page.locator('[data-paleta-guardias] [data-herramienta]')).toHaveCount(5); // TA4: + Guardia festiva
    const banda = page.locator('[data-banda-semana="2027-02-15"]').first();
    await expect(banda).toHaveAttribute('data-banda-farmacia', '');
    await herramienta(page, 'guardia');
    await banda.click();
    const sel = page.locator('[data-selector-semana="2027-02-15"]');
    await expect(sel).toContainText('Semana 15–21 feb 2027');
    await sel.locator('[data-selector-campo="farmacia"]').selectOption('RITA');
    await expect(sel.locator(`[data-selector-campo="guardia"] option[value="${AINA}"]`)).toHaveCount(0); // solo RITA
    await sel.locator('[data-selector-campo="guardia"]').selectOption(LAURA);
    await expect(sel.locator(`[data-selector-campo="apoyo"] option[value="${LAURA}"]`)).toHaveCount(0); // el apoyo, otra persona
    await sel.locator('[data-selector-campo="apoyo"]').selectOption(MARTA);
    await sel.locator('[data-selector-guardar]').click();
    await expect(aviso(page)).toHaveText('Guardia RITA: Laura Serra Coll · apoyo Marta Vila Soler, semana 15–21 feb 2027.');
    await expect(banda).toHaveAttribute('data-banda-farmacia', 'RITA');
    await expect(banda).toContainText('G: LS · A: MV');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_ta3_4_anio.png'), fullPage: true });
    // OTRA en la banda; goma en la banda; deshacer todo.
    await herramienta(page, 'otra');
    await page.locator('[data-banda-semana="2027-02-22"]').first().click();
    await expect(page.locator('[data-banda-semana="2027-02-22"]').first()).toHaveAttribute('data-banda-farmacia', 'OTRA');
    await herramienta(page, 'goma');
    await banda.click();
    await expect(banda).toHaveAttribute('data-banda-farmacia', '');
    await deshacer(page, /^Deshecho «Quitada la guardia RITA \(Laura Serra Coll\)/);
    await expect(banda).toHaveAttribute('data-banda-farmacia', 'RITA');
    await deshacer(page, /^Deshecho «Guardia OTRA/);
    await deshacer(page, /^Deshecho «Guardia RITA: Laura Serra Coll/);
    await expect(banda).toHaveAttribute('data-banda-farmacia', '');
    // Sin herramienta (Abrir semana), clic en un día abre su semana, como antes.
    await herramienta(page, 'seleccion');
    await page.locator('[data-dia="2027-02-17"]').click();
    await expect(page.locator('[data-calendario]')).toHaveAttribute('data-vista', 'semana');
  });
});

test.describe('REAL simulado (intercepción del estado): las herramientas también están', () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  test('paleta con las 4 herramientas; pintar y deshacer una guardia', async ({ page }) => {
    await page.route('**/api/rrhh/estado', (r) => r.fulfill({ json: {
      modo: 'REAL', conectado: true, datos_ejemplo: false, mensaje: 'Datos reales: cada cambio se guarda en la base de datos con autor Marc', guardias_disponibles: true } }));
    await page.goto('/trabajadores/calendario?fecha=2027-03-01');
    await expect(page.locator('[data-paleta-guardias] [data-herramienta]')).toHaveCount(5); // TA4: + Guardia festiva
    await herramienta(page, 'guardia');
    await celda(page, LAURA, '2027-03-03').click();
    await expect(page.locator(`[data-marca-g="${LAURA}|2027-03-01"]`)).toBeVisible();
    await deshacer(page, 'Guardia RITA: Laura Serra Coll, semana 1–7 mar 2027');
  });
});

test.describe('Móvil 390', () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test('semana con guardia: sin desplazamiento horizontal de página; marcas visibles', async ({ page }) => {
    await abrir(page, '?fecha=2027-04-05&farmacia=PIO');
    await herramienta(page, 'guardia');
    await celda(page, AINA, '2027-04-07').click();
    await expect(page.locator(`[data-marca-g="${AINA}|2027-04-05"]`)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_ta3_4_semana.png'), fullPage: false });
    await deshacer(page, 'Guardia PIO: Aina Bosch Ferrer, semana 5–11 abr 2027');
  });
});
