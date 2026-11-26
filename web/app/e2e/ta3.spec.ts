// TA3 Trabajadores: guardias y festivos con los datos de ejemplo del servidor FIXTURES. Solo FIXTURES
// (playwright.config.ts lo exige). El modo REAL se simula interceptando la API.
// TA3-4: la pestaña es de consulta; pintar guardias y festivos en el calendario se prueba en ta3_4.spec.ts.
import { expect, test, type Page } from '@playwright/test';
import { join } from 'node:path';
import { entrar } from './sesion.ts';

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'ta3');
const ID = (n: number) => `e0000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const AINA = ID(1);

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
    // TA4: popup «1/1 Año Nuevo · Guardia festiva: PIO · Aina Bosch Ferrer» al principio del título del día.
    await expect(page.locator('[data-dia="2026-01-01"]')).toHaveAttribute('title', /^1\/1 Año Nuevo · Guardia festiva: PIO · Aina Bosch Ferrer · /);
    await expect(page.locator('[data-dia="2026-12-25"]')).toHaveAttribute('data-festivo', 'RITA');
    await expect(page.locator('[data-dia="2026-08-31"]')).toHaveAttribute('data-festivo', '');
    await expect(page.locator('[data-dia="2026-08-31"]')).toHaveAttribute('title', /^31\/8 Fiesta mayor \(ejemplo\) · Guardia festiva: sin asignar · /);
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
    // La paleta ya no habla de TA3; TA3-4: guardias y festivos se pintan con sus herramientas.
    await expect(page.locator('[data-tipos-ta3]')).toContainText('guardias, apoyos y festivos se pintan con sus herramientas');
    await expect(page.locator('[data-tipos-ta3]')).not.toContainText('TA3');
    await expect(page.locator('[data-paleta-guardias] [data-herramienta]')).toHaveCount(5); // TA4: + Guardia festiva
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

  test('TA3-4: la pestaña es de consulta (sin formularios); «Editar en el calendario» abre la semana', async ({ page }) => {
    await abrirGuardias(page, '?anio=2026');
    await expect(page.locator('[data-solo-consulta]')).toContainText('se pintan en el calendario');
    await expect(page.locator('.gu form, .gu select, .gu input, [data-alta-festivo], [data-baja-festivo]')).toHaveCount(0);
    await expect(page.locator('[data-editar-festivo="2026-12-08"]')).toHaveText('Editar en el calendario');
    await page.locator('[data-editar-semana="2026-11-09"]').click();
    await expect(page).toHaveURL(/\/trabajadores\/calendario\?fecha=2026-11-09$/);
    await expect(page.locator('[data-calendario]')).toHaveAttribute('data-vista', 'semana');
    await expect(page.locator('[data-periodo]')).toHaveText('9–15 nov 2026');
    await abrirGuardias(page, '?anio=2027');
    await expect(page.locator('[data-sin-festivos]')).toContainText('con la herramienta Festivo');
    await page.locator('[data-editar-calendario-anio]').click();
    await expect(page.locator('[data-calendario]')).toHaveAttribute('data-vista', 'anio');
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

test.describe('TA3-REAL: modo REAL simulado (intercepción del estado): pestaña y edición disponibles', () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  test('sin «Pendiente de tablas en Supabase»: pestaña de consulta; el calendario muestra las guardias y sus herramientas', async ({ page }) => {
    await page.route('**/api/rrhh/estado', (r) => r.fulfill({ json: {
      modo: 'REAL', conectado: true, datos_ejemplo: false, mensaje: 'Datos reales: cada cambio se guarda en la base de datos con autor Marc', guardias_disponibles: true } }));
    await page.goto('/trabajadores/guardias?anio=2026');
    await expect(page.locator('a[data-seccion="guardias"]')).toHaveCount(1);
    await expect(page.locator('[data-semana]').first()).toBeVisible();
    await expect(page.locator('[data-solo-consulta]')).toBeVisible();
    await expect(page.getByText('Pendiente de tablas en Supabase')).toHaveCount(0);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_real_guardias.png'), fullPage: true });
    await page.goto('/trabajadores/calendario?fecha=2026-11-09');
    await expect(page.locator('[data-calendario]')).toBeVisible();
    await expect(page.locator('[data-cabecera-guardias]')).toBeVisible();
    await expect(page.locator('[data-paleta-guardias] [data-herramienta]')).toHaveCount(5); // TA4: + Guardia festiva
    await expect(page.locator(`[data-marca-g="${ID(21)}|2026-11-09"]`)).toBeVisible(); // titular de PIO de guardia
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
