// TA3 Trabajadores: guardias y festivos con los datos de ejemplo del servidor FIXTURES. Solo FIXTURES
// (playwright.config.ts lo exige). El modo REAL se simula interceptando la API.
// Las pruebas que escriben usan 2027 y personas de RITA, y deshacen o dan de baja lo que crean (el servidor es común).
import { expect, test, type Page } from '@playwright/test';
import { join } from 'node:path';
import { entrar } from './sesion.ts';

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'ta3');
const ID = (n: number) => `e0000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const AINA = ID(1); const CLARA = ID(2); const ELENA = ID(4); const LAURA = ID(11); const MARTA = ID(12);

test.beforeEach(async ({ page }) => entrar(page));

async function modoFixtures(page: Page) {
  const estado = await (await page.request.get('/api/estado')).json();
  expect(estado.modo).toBe('FIXTURES');
}
async function abrirCalendario(page: Page, consulta: string) {
  await modoFixtures(page);
  await page.goto(`/trabajadores/calendario${consulta}`);
  await expect(page.locator('[data-calendario]')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}
async function abrirGuardias(page: Page, consulta = '') {
  await modoFixtures(page);
  await page.goto(`/trabajadores/guardias${consulta}`);
  await expect(page.locator('[data-guardias]')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}
const aviso = (page: Page) => page.locator('[data-aviso-guardias]');

test.describe('Guardias y festivos PC 1440', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('vista año: banda por semana de guardia (color de farmacia + «G: XX · A: YY»; OTRA gris) y festivos con su farmacia de guardia', async ({ page }) => {
    await abrirCalendario(page, '?vista=anio&fecha=2026-11-09');
    const nov = page.locator('[data-banda-semana="2026-11-09"]').first();
    await expect(nov).toHaveAttribute('data-banda-farmacia', 'PIO');
    await expect(nov).toContainText('G: TE · A: AB'); // titular de PIO de guardia; Aina de apoyo
    await expect(nov).toHaveAttribute('title', /Guardia: Titular de ejemplo · Apoyo sábado: Aina Bosch Ferrer/);
    await expect(page.locator('[data-banda-semana="2026-01-05"]').first()).toContainText('G: LS · A: IG'); // RITA: Laura, apoyo Irene
    const otra = page.locator('[data-banda-semana="2026-01-12"]').first();
    await expect(otra).toHaveAttribute('data-banda-farmacia', 'OTRA');
    await expect(otra).toContainText('OTRA');
    // Colores propios: PIO y RITA distintos entre sí y de OTRA.
    const fondo = async (lunes: string) => page.locator(`[data-banda-semana="${lunes}"]`).first().evaluate((e) => getComputedStyle(e).backgroundColor);
    const [pio, rita, ajena] = [await fondo('2026-11-09'), await fondo('2026-01-05'), await fondo('2026-01-12')];
    expect(new Set([pio, rita, ajena]).size).toBe(3);
    // Festivos: marcados con la farmacia de guardia (el 31 ago, sin asignar).
    await expect(page.locator('[data-dia="2026-01-01"]')).toHaveAttribute('data-festivo', 'PIO');
    await expect(page.locator('[data-dia="2026-01-01"]')).toHaveAttribute('title', /Festivo: Año Nuevo \(guardia PIO: Aina Bosch Ferrer\)/);
    await expect(page.locator('[data-dia="2026-12-25"]')).toHaveAttribute('data-festivo', 'RITA');
    await expect(page.locator('[data-dia="2026-08-31"]')).toHaveAttribute('data-festivo', '');
    await expect(page.locator('[data-dia="2026-08-31"]')).toHaveAttribute('title', /guardia sin asignar/);
    await expect(page.locator('[data-dia="2026-11-02"]')).not.toHaveAttribute('data-festivo', /.*/);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_anio_guardias.png'), fullPage: true });
  });

  test('semana y mes: cabecera «Guardia: Nombre · Apoyo sábado: Nombre»; festivos con su nombre', async ({ page }) => {
    await abrirCalendario(page, '?fecha=2026-11-09');
    const cab = page.locator('[data-cabecera-guardias]');
    await expect(cab.locator('[data-cabecera-semana]')).toHaveCount(1);
    await expect(cab.locator('[data-texto-guardia]')).toHaveText('Guardia: Titular de ejemplo · Apoyo sábado: Aina Bosch Ferrer');
    await expect(cab.locator('[data-guardia-farmacia]')).toHaveText('PIO');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_semana_guardias.png'), fullPage: true });
    // Semana con festivo: la columna lleva el nombre; la cabecera, el festivo y su guardia.
    await page.goto('/trabajadores/calendario?fecha=2026-12-07');
    await expect(page.locator('[data-columna="2026-12-08"]')).toHaveAttribute('data-festivo-columna', 'La Inmaculada');
    await expect(page.locator('[data-columna="2026-12-08"]')).toContainText('La Inmaculada');
    await expect(page.locator('[data-cabecera-festivo="2026-12-08"]')).toContainText('La Inmaculada · guardia PIO · Clara Roig Pujol');
    await expect(page.locator('[data-cabecera-guardias] [data-texto-guardia]')).toHaveText('Guardia: Marta Vila Soler · Apoyo sábado: Rosa Camps Oliver');
    await expect(page.locator('[data-cabecera-guardias] [data-guardia-farmacia]')).toHaveText('RITA');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_semana_festivo.png'), fullPage: true });
    // Mes: una línea por semana y los festivos del mes.
    await page.goto('/trabajadores/calendario?vista=mes&fecha=2026-12-01');
    await expect(page.locator('[data-cabecera-semana]')).toHaveCount(5); // 30 nov, 7, 14 (OTRA), 21 y 28 dic
    await expect(page.locator('[data-cabecera-semana="2026-12-14"] [data-texto-guardia]')).toHaveText('Guardia: OTRA (farmacia ajena)');
    await expect(page.locator('[data-cabecera-festivo]')).toHaveCount(3);
    await expect(page.locator('[data-cabecera-semana="2026-12-21"] [data-texto-guardia]')).toHaveText('Guardia: Clara Roig Pujol · Apoyo sábado: Elena Mas Garriga');
    await expect(page.locator('[data-columna="2026-12-25"]')).toHaveAttribute('data-festivo-columna', 'Navidad');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_mes_guardias.png'), fullPage: true });
    // La paleta ya no habla de TA3.
    await expect(page.locator('[data-tipos-ta3]')).toContainText('se registran en Guardias y festivos');
    await expect(page.locator('[data-tipos-ta3]')).not.toContainText('TA3');
  });

  test('pestaña: lista anual por semana y festivos; sin etiqueta TA3', async ({ page }) => {
    await abrirGuardias(page, '?anio=2026');
    const pestana = page.locator('[data-seccion="guardias"]');
    await expect(pestana).toHaveAttribute('aria-current', 'page');
    await expect(pestana).toHaveText('Guardias y festivos');
    await expect(page.locator('.rrhh-secciones')).not.toContainText('TA3');
    await expect(page.locator('[data-semana]')).toHaveCount(53);
    const s = page.locator('[data-semana="2026-11-09"]');
    await expect(s.locator('[data-guardia-farmacia]')).toHaveText('PIO');
    await expect(s.locator('[data-col="guardia"]')).toHaveText('Titular de ejemplo');
    await expect(s.locator('[data-col="apoyo"]')).toHaveText('Aina Bosch Ferrer');
    await expect(s.locator('[data-col="horas"]')).toHaveText('14 h'); // 6,5 + 3 + 4,5
    await expect(page.locator('[data-semana="2026-10-26"] [data-col="horas"]')).toHaveText('11 h'); // domingo 1 nov festivo: 6,5 + 4,5
    await expect(page.locator('[data-semana="2026-01-12"] [data-col="guardia"]')).toHaveText('farmacia ajena');
    await expect(page.locator('[data-festivo]')).toHaveCount(15);
    await expect(page.locator('[data-festivo="2026-08-31"] [data-guardia-festivo]')).toHaveText('guardia sin asignar');
    await expect(page.locator('[data-festivo="2026-01-06"] [data-guardia-festivo]')).toContainText('OTRA');
    await expect(page.locator('[data-horario-guardia]')).toContainText('sábado 9:00–13:30 y 18:00–20:00 (6,5 h) · domingo 10:00–13:00 (3 h)');
    await expect(page.locator('[data-horario-guardia]')).toContainText('9:00–13:30 (4,5 h)');
    await expect(page.locator('[data-horario-guardia]')).toContainText('sin horas, solo constancia');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_pestana_guardias.png'), fullPage: true });
  });

  test('pestaña: editar farmacia, guardia y apoyo de una semana; alta, guardia por defecto y baja de un festivo; el calendario los usa', async ({ page }) => {
    await abrirGuardias(page, '?anio=2026');
    await page.locator('[data-selector-anio="2027"]').click();
    await expect(page.locator('[data-semana="2027-01-04"] [data-sin-asignar]')).toBeVisible();

    // Semana del 4 ene 2027: PIO, Clara de guardia, Elena de apoyo (la guardia no sale como apoyo).
    await page.locator('[data-editar-semana="2027-01-04"]').click();
    const ed = page.locator('[data-editor-semana="2027-01-04"]');
    await ed.locator('[data-campo="farmacia"]').selectOption('PIO');
    await ed.locator('[data-campo="guardia"]').selectOption(CLARA);
    await expect(ed.locator(`[data-campo="apoyo"] option[value="${CLARA}"]`)).toHaveCount(0);
    await expect(ed.locator(`[data-campo="guardia"] option[value="${MARTA}"]`)).toHaveCount(0); // solo personas de PIO
    await ed.locator('[data-campo="apoyo"]').selectOption(ELENA);
    await ed.locator('[data-guardar-semana]').click();
    await expect(aviso(page)).toHaveText('Guardia de la semana 4–10 ene 2027 guardada.');
    const fila = page.locator('[data-semana="2027-01-04"]');
    await expect(fila.locator('[data-col="guardia"]')).toHaveText('Clara Roig Pujol');
    await expect(fila.locator('[data-col="apoyo"]')).toHaveText('Elena Mas Garriga');
    await expect(fila.locator('[data-col="horas"]')).toHaveText('14 h');
    // RITA sin persona: falla cerrado con el motivo; OTRA: sin personas.
    await page.locator('[data-editar-semana="2027-01-04"]').click();
    await ed.locator('[data-campo="farmacia"]').selectOption('RITA');
    await ed.locator('[data-guardar-semana]').click();
    await expect(aviso(page)).toHaveText('Elige la persona de guardia');
    await ed.locator('[data-campo="farmacia"]').selectOption('OTRA');
    await expect(ed.locator('[data-campo="guardia"]')).toHaveCount(0);
    await ed.locator('[data-guardar-semana]').click();
    await expect(fila.locator('[data-col="guardia"]')).toHaveText('farmacia ajena');
    // Semana del 15 mar 2027: RITA, Laura (para la guardia por defecto del festivo).
    await page.locator('[data-editar-semana="2027-03-15"]').click();
    const ed2 = page.locator('[data-editor-semana="2027-03-15"]');
    await ed2.locator('[data-campo="farmacia"]').selectOption('RITA');
    await ed2.locator('[data-campo="guardia"]').selectOption(LAURA);
    await ed2.locator('[data-guardar-semana]').click();
    await expect(page.locator('[data-semana="2027-03-15"] [data-col="guardia"]')).toHaveText('Laura Serra Coll');

    // Alta de un festivo (fecha y nombre); duplicado rechazado.
    await page.locator('input[name="fecha_festivo"]').fill('2027-03-19');
    await page.locator('input[name="nombre_festivo"]').fill('Sant Josep');
    await page.locator('[data-anadir-festivo]').click();
    await expect(aviso(page)).toContainText('Festivo añadido');
    const fe = page.locator('[data-festivo="2027-03-19"]');
    await expect(fe.locator('[data-nombre-festivo]')).toHaveText('Sant Josep');
    await expect(fe.locator('[data-guardia-festivo]')).toHaveText('guardia sin asignar');
    await page.locator('input[name="fecha_festivo"]').fill('2027-03-19');
    await page.locator('input[name="nombre_festivo"]').fill('Otro');
    await page.locator('[data-anadir-festivo]').click();
    await expect(aviso(page)).toHaveText('Ese día ya es festivo.');
    // Guardia del festivo: por defecto, la de esa semana (RITA, Laura); editable.
    await page.locator('[data-editar-festivo="2027-03-19"]').click();
    const ef = page.locator('[data-editor-festivo="2027-03-19"]');
    await expect(ef.locator('[data-campo="farmacia"]')).toHaveValue('RITA');
    await expect(ef.locator('[data-campo="persona"]')).toHaveValue(LAURA);
    await expect(ef.locator('[data-pista-defecto]')).toBeVisible();
    await ef.locator('[data-campo="farmacia"]').selectOption('PIO');
    await expect(ef.locator('[data-campo="persona"]')).toHaveValue(''); // otra farmacia: sin persona por defecto
    await ef.locator('[data-campo="farmacia"]').selectOption('RITA');
    await ef.locator('[data-campo="persona"]').selectOption(MARTA);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_pestana_editar.png'), fullPage: true });
    await ef.locator('[data-guardar-festivo]').click();
    await expect(fe.locator('[data-guardia-festivo]')).toContainText('RITA');
    await expect(fe.locator('[data-guardia-festivo]')).toContainText('Marta Vila Soler');

    // Calendario: columna festiva; rellenar la salta; pintar sobre ella se permite con aviso.
    await abrirCalendario(page, `?farmacia=RITA&fecha=2027-03-15&persona=${MARTA}`);
    await expect(page.locator('[data-columna="2027-03-19"]')).toHaveAttribute('data-festivo-columna', 'Sant Josep');
    await expect(page.locator('[data-cabecera-guardias] [data-texto-guardia]')).toHaveText('Guardia: Laura Serra Coll · Apoyo sábado: —');
    await page.locator('[data-accion="rellenar"]').click();
    await expect(page.locator('[data-aviso-calendario]')).toHaveText('Rellenado 15–21 mar 2027: 4 días laborables × 1 persona.');
    await expect(page.locator(`[data-celda="${MARTA}|2027-03-19|MANANA"]`)).toHaveAttribute('data-tipo', '');
    await page.locator('[data-herramienta="VACACIONES"]').click();
    await page.locator(`[data-celda="${MARTA}|2027-03-19|MANANA"]`).click();
    await expect(page.locator('[data-aviso-calendario]')).toHaveText('Pintado Vacaciones 19 mar 2027: 1 día laborable × 1 persona · 1 franja. Ojo: 19 mar (Sant Josep) es festivo.');
    await expect(page.locator(`[data-celda="${MARTA}|2027-03-19|MANANA"]`)).toHaveAttribute('data-tipo', 'VACACIONES');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_semana_festivo_aviso.png'), fullPage: true });
    // Se deshace todo lo pintado (el servidor es común a todas las pruebas).
    await page.locator('[data-accion="deshacer"]').click();
    await expect(page.locator('[data-aviso-calendario]')).toContainText('Deshecho «Pintado Vacaciones');
    await page.locator('[data-accion="deshacer"]').click();
    await expect(page.locator('[data-aviso-calendario]')).toContainText('Deshecho «Rellenado');

    // Baja del festivo con confirmación (se anula con su guardia).
    await abrirGuardias(page, '?anio=2027');
    await page.locator('[data-baja-festivo="2027-03-19"]').click();
    await expect(page.locator('[data-confirmar-baja="2027-03-19"]')).toContainText('Se anula con su guardia');
    await page.locator('[data-baja-festivo-si]').click();
    await expect(aviso(page)).toContainText('Festivo dado de baja');
    await expect(page.locator('[data-festivo="2027-03-19"]')).toHaveCount(0);
    await expect(page.locator('[data-sin-festivos]')).toBeVisible();
  });

  test('ficha anual: bloque «Guardias del año» (horas fuera de cómputo)', async ({ page }) => {
    await modoFixtures(page);
    await page.goto(`/trabajadores/${AINA}?anio=2026`);
    const b = page.locator('[data-bloque="guardias"]');
    await expect(b).toBeVisible();
    await expect(b.locator('[data-cifra="semanas-guardia"]')).toHaveText('5semanas de guardia');
    await expect(b.locator('[data-cifra="sabados-apoyo"]')).toHaveText('4sábados de apoyo');
    await expect(b.locator('[data-cifra="festivos-guardia"]')).toHaveText('2festivos de guardia');
    await expect(b.locator('[data-horas-fuera-computo]')).toHaveText('71,5 h fuera de cómputo');
    await expect(b.locator('[data-desglose-guardias]')).toContainText('Guardia 47,5 h · apoyo 18 h · festivos 6 h');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_ficha_guardias.png'), fullPage: true });
  });
});

test.describe('Modo REAL simulado (intercepción): pestaña y edición deshabilitadas', () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  test('«Pendiente de tablas en Supabase»: pestaña sin enlace; la página no muestra ni edita nada; el calendario sigue sin guardias', async ({ page }) => {
    await page.route('**/api/rrhh/estado', (r) => r.fulfill({ json: {
      modo: 'REAL', conectado: true, datos_ejemplo: false, mensaje: 'Datos reales: cada cambio se guarda en la base de datos con autor Marc', guardias_disponibles: false } }));
    await page.route(/\/api\/rrhh\/guardias\?/, (r) => r.fulfill({ json: { disponible: false, mensaje: 'Pendiente de tablas en Supabase' } }));
    await page.goto('/trabajadores/guardias');
    const pestana = page.locator('[data-seccion="guardias"]');
    await expect(pestana).toHaveAttribute('aria-disabled', 'true');
    await expect(pestana).toContainText('Pendiente de tablas en Supabase');
    await expect(page.locator('a[data-seccion="guardias"]')).toHaveCount(0);
    await expect(page.locator('[data-ta3-pendiente]')).toContainText('Pendiente de tablas en Supabase');
    await expect(page.locator('[data-semana], [data-festivo], [data-alta-festivo]')).toHaveCount(0);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_real_pendiente.png'), fullPage: true });
    await page.goto('/trabajadores/calendario?fecha=2026-11-09');
    await expect(page.locator('[data-calendario]')).toBeVisible();
    await expect(page.locator('[data-cabecera-guardias]')).toHaveCount(0);
  });
});

test.describe('Móvil 390', () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test('pestaña sin desplazamiento horizontal de página', async ({ page }) => {
    await abrirGuardias(page, '?anio=2026');
    const ancho = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(ancho).toBeLessThanOrEqual(390);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_pestana_guardias.png'), fullPage: true });
  });
});
