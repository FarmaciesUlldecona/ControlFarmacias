// TA1 Trabajadores: fichas con datos de ejemplo en memoria del servidor FIXTURES. Solo FIXTURES (playwright.config.ts
// lo exige). El modo REAL se simula interceptando la API: nunca se arranca ni se lee el modo REAL.
import { expect, test, type Page } from '@playwright/test';
import { join } from 'node:path';
import { entrar } from './sesion.ts';

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'ta1');
const BANNER = 'Datos de ejemplo: los cambios no se guardan hasta conectar las tablas reales';
const ID_ELENA = 'e0000000-0000-4000-8000-000000000004';
const ID_TITULAR_PIO = 'e0000000-0000-4000-8000-000000000021';
const ID_IRENE = 'e0000000-0000-4000-8000-000000000017'; // TA1-3: media tarde en RITA

test.beforeEach(async ({ page }) => entrar(page));

async function abrirFichas(page: Page, consulta = '') {
  const estado = await (await page.request.get('/api/estado')).json();
  expect(estado.modo).toBe('FIXTURES');
  await page.goto(`/trabajadores${consulta}`);
  await expect(page.locator('[data-rrhh-fichas]')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}
const nombres = (page: Page) => page.locator('.rrhh-tabla tbody tr .rrhh-nombre').allTextContents();

test.describe('Fichas PC 1440', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('menú activo, banner fijo y selector PIO / RITA / Ambas', async ({ page }) => {
    await abrirFichas(page);
    const menu = page.getByRole('navigation', { name: 'Menú principal' });
    await expect(menu.getByRole('link', { name: 'Trabajadores', exact: true })).toHaveClass(/activo/);
    await expect(page.locator('[data-rita]')).toHaveText('RITA: solo en Trabajadores');
    await expect(page.locator('[data-banner-ejemplo]')).toContainText(BANNER);
    // Ambas: PIO 4 + titular, RITA 6 + titular (las altas de otras pruebas no cambian las de ejemplo).
    for (const n of ['Aina Bosch Ferrer', 'Elena Mas Garriga', 'Laura Serra Coll', 'Paula Riera Bover']) expect(await nombres(page)).toContain(n);
    await page.locator('[data-selector-farmacia="PIO"]').click();
    await expect(page).toHaveURL(/farmacia=PIO/);
    await expect.poll(async () => (await page.locator('.rrhh-tabla [data-farmacia]').allTextContents()).every((f) => f === 'PIO')).toBe(true);
    await expect(page.locator('[data-selector-farmacia="PIO"]')).toHaveAttribute('aria-checked', 'true');
    expect(await nombres(page)).not.toContain('Laura Serra Coll');
    await page.locator('[data-selector-farmacia="RITA"]').click();
    await expect.poll(() => nombres(page)).toContain('Laura Serra Coll');
    expect(await nombres(page)).not.toContain('Aina Bosch Ferrer');
    // Columnas, jornada, computa y titular fuera del cómputo.
    const cab = await page.locator('.rrhh-tabla thead th').allTextContents();
    expect(cab).toEqual(['Nombre', 'Farmacia', 'Categoría', 'Jornada', 'Computa']);
    const laura = page.locator('tr', { has: page.getByText('Laura Serra Coll') });
    await expect(laura).toContainText('Farmacéutica');
    const paula = page.locator('tr', { has: page.getByText('Paula Riera Bover') });
    // TA1-2: jornada en horas diarias; porcentaje derivado (calculado) sobre la referencia de 40 h/sem.
    await expect(paula.locator('[data-horas-diarias]')).toHaveText('Media mañana · 4,5 h/día');
    await expect(paula.locator('[data-porcentaje-derivado]')).toHaveText('56,25 % · 22,5 h/sem');
    // TA1-3: media tarde (3,5 h/día, 17:00–20:30): 17,5 h/sem = 43,75 %.
    const irene = page.locator('tr', { has: page.getByText('Irene Gual Torrent') });
    await expect(irene.locator('[data-horas-diarias]')).toHaveText('Media tarde · 3,5 h/día');
    await expect(irene.locator('[data-porcentaje-derivado]')).toHaveText('43,75 % · 17,5 h/sem');
    const marta = page.locator('tr', { has: page.getByText('Marta Vila Soler') });
    await expect(marta.locator('[data-horas-diarias]')).toHaveText('Completa · 8 h/día');
    await expect(marta.locator('[data-porcentaje-derivado]')).toHaveText('100 % · 40 h/sem');
    const titular = page.locator('tr', { has: page.getByText('Titular de ejemplo') });
    await expect(titular.locator('[data-computa]')).toHaveText('No · titular');
    await expect(page.locator('[data-resumen-fichas]')).toContainText('jornada máxima 2026: 1767 h');
    await expect(page.locator('[data-referencia-semanal]')).toHaveText('40 h/sem');
    await expect(page.locator('[data-resumen-fichas]')).toContainText('provisional');
    await page.locator('[data-selector-farmacia="AMBAS"]').click();
    await expect(page.locator('.rrhh-tabla [data-farmacia="RITA"]').first()).toBeVisible();
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_fichas.png'), fullPage: true });
  });

  test('alta con validación (nombre obligatorio, sin campos de DNI), edición y baja con historial', async ({ page }) => {
    await abrirFichas(page, '?farmacia=RITA');
    await page.getByRole('button', { name: 'Nueva ficha' }).click();
    const form = page.locator('[data-formulario-ficha="alta"]');
    await expect(form).toBeVisible();
    // Sin campos de DNI ni otros datos personales.
    await expect(form.locator('input, select')).toHaveCount(6);
    await expect(form.getByText(/DNI|NIF|teléfono|dirección/i)).toHaveCount(0);
    await expect(form.locator('select[name="farmacia"]')).toHaveValue('RITA');
    // TA1-2: el porcentaje no es un campo: es un dato calculado.
    await expect(form.locator('input[name="porcentaje"], input[name="porcentaje_jornada"]')).toHaveCount(0);
    await expect(form.locator('input[name="horas_diarias"]')).toHaveValue('8');
    await expect(form.locator('[data-porcentaje-formulario]')).toHaveText('100 % · 40 h de 40 h/sem');
    await form.getByRole('button', { name: 'Crear ficha' }).click();
    await expect(form.locator('[data-error-campo="nombre"]')).toHaveText('Escribe el nombre');
    await form.getByLabel('Nombre').fill('Prueba Alta Ejemplo');
    // TA-REAL: categorías del esquema; fecha de alta obligatoria (por defecto hoy, editable); sin casilla de titular.
    await expect(form.locator('select[name="categoria"] option')).toHaveText(['Farmacéutica titular', 'Farmacéutica adjunta', 'Técnica', 'Auxiliar', 'Otra']);
    await expect(form.locator('input[name="es_titular"]')).toHaveCount(0);
    await expect(form.locator('input[name="fecha_alta"]')).toHaveValue(/^\d{4}-\d{2}-\d{2}$/);
    await form.locator('select[name="categoria"]').selectOption('FARMACEUTICA_TITULAR');
    await expect(form.locator('[data-pista-titular]')).toHaveText('fuera del cómputo del convenio; se registran sus horas');
    await form.locator('select[name="categoria"]').selectOption('TECNICA');
    await form.locator('input[name="fecha_alta"]').fill('2026-11-02');
    // TA1-3: selector Completa / Media mañana / Media tarde; media tarde por defecto 3,5 h (17:00–20:30).
    await expect(form.locator('select[name="tipo_jornada"] option')).toHaveText(['Completa', 'Media mañana', 'Media tarde']);
    await form.locator('select[name="tipo_jornada"]').selectOption('MEDIA_TARDE');
    await expect(form.locator('input[name="horas_diarias"]')).toHaveValue('3,5');
    await expect(form.locator('[data-franja]')).toHaveText('de lunes a viernes, de tarde (17:00–20:30)');
    await expect(form.locator('[data-porcentaje-formulario]')).toHaveText('43,75 % · 17,5 h de 40 h/sem');
    await form.locator('input[name="horas_diarias"]').fill('8');
    await form.getByRole('button', { name: 'Crear ficha' }).click();
    await expect(form.locator('[data-error-campo="horas_diarias"]')).toHaveText('La media tarde es menos de 8 h al día');
    await form.locator('select[name="tipo_jornada"]').selectOption('MEDIA_MANANA');
    await expect(form.locator('input[name="horas_diarias"]')).toHaveValue('4,5');
    await expect(form.locator('[data-porcentaje-formulario]')).toHaveText('56,25 % · 22,5 h de 40 h/sem');
    await form.locator('input[name="horas_diarias"]').fill('8');
    await form.getByRole('button', { name: 'Crear ficha' }).click();
    await expect(form.locator('[data-error-campo="horas_diarias"]')).toHaveText('La media mañana es menos de 8 h al día'); // validación del servidor
    await form.locator('input[name="horas_diarias"]').fill('0');
    await form.getByRole('button', { name: 'Crear ficha' }).click();
    await expect(form.locator('[data-error-campo="horas_diarias"]')).toHaveText('Horas al día: más de 0 y como máximo 8');
    await form.locator('input[name="horas_diarias"]').fill('6');
    await expect(form.locator('[data-error-campo="horas_diarias"]')).toHaveCount(0); // corregido: el error desaparece
    await expect(form.locator('[data-porcentaje-formulario]')).toHaveText('75 % · 30 h de 40 h/sem');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_alta.png'), fullPage: true });
    await form.getByRole('button', { name: 'Crear ficha' }).click();
    await expect(page.locator('[data-aviso-rrhh]')).toHaveText('Ficha creada: Prueba Alta Ejemplo (RITA).');
    const fila = page.locator('tr', { has: page.getByText('Prueba Alta Ejemplo') });
    await expect(fila.locator('[data-horas-diarias]')).toHaveText('Media mañana · 6 h/día');

    // Detalle y edición.
    await fila.locator('.rrhh-nombre').click();
    await expect(page.locator('[data-nombre-ficha]')).toHaveText('Prueba Alta Ejemplo');
    await expect(page.locator('[data-objetivo="2026"] [data-objetivo-horas]')).toHaveText('1325,3 h'); // 1767 × 30 / 40
    await expect(page.locator('[data-historial="ALTA"]')).toContainText('Marc'); // TA1-2: autor del historial
    await expect(page.locator('[data-historial="ALTA"]')).toContainText('Horas al día: 6 h/día');
    await expect(page.locator('[data-historial="ALTA"]')).toContainText('Fecha de alta: 02/11/2026');
    await expect(page.locator('[data-fecha-alta]')).toHaveText('02/11/2026');
    await page.getByRole('button', { name: 'Editar ficha' }).click();
    const ed = page.locator('[data-formulario-ficha="edicion"]');
    await expect(ed.locator('select[name="farmacia"]')).toHaveCount(0); // no se cambia de farmacia
    await ed.getByLabel('Nombre').fill('Prueba Editada Ejemplo');
    await ed.locator('select[name="categoria"]').selectOption('AUXILIAR');
    await expect(ed.locator('input[name="horas_diarias"]')).toHaveValue('6');
    await ed.locator('input[name="horas_diarias"]').fill('4,5');
    await ed.getByRole('button', { name: 'Guardar cambios' }).click();
    await expect(page.locator('[data-aviso-rrhh]')).toHaveText('Cambios guardados en la ficha.');
    await expect(page.locator('[data-nombre-ficha]')).toHaveText('Prueba Editada Ejemplo');
    const edicion = page.locator('[data-historial="EDICION"]');
    await expect(edicion).toContainText('Nombre: Prueba Alta Ejemplo → Prueba Editada Ejemplo');
    await expect(edicion).toContainText('Categoría: Técnica → Auxiliar');
    await expect(edicion).toContainText('Horas al día: 6 h/día → 4,5 h/día');
    await expect(edicion).toContainText('Marc');
    await expect(page.locator('[data-objetivo="2026"] [data-objetivo-horas]')).toHaveText('993,9 h');

    // Baja: fecha obligatoria; luego queda en el historial y sale del listado.
    await page.getByRole('button', { name: 'Dar de baja' }).click();
    const baja = page.locator('[data-formulario-baja]');
    await baja.getByRole('button', { name: 'Confirmar baja' }).click();
    await expect(baja.locator('[data-error-campo="fecha_baja"]')).toHaveText('Indica la fecha de baja');
    // TA-REAL: la baja no puede ser anterior al alta (2/11); en el calendario sale hasta su fecha de baja.
    await baja.getByLabel('Fecha de baja').fill('2026-11-01');
    await baja.getByRole('button', { name: 'Confirmar baja' }).click();
    await expect(baja.getByRole('alert').or(baja.locator('[data-error-campo="fecha_baja"]'))).toHaveText('La fecha de baja no puede ser anterior a la de alta.');
    await baja.getByLabel('Fecha de baja').fill('2026-11-06');
    await baja.getByRole('button', { name: 'Confirmar baja' }).click();
    await expect(page.locator('[data-baja]')).toHaveText('Baja desde 06/11/2026');
    await expect(page.locator('[data-historial="BAJA"]')).toContainText('Fecha de baja: — → 06/11/2026');
    await expect(page.getByRole('button', { name: 'Dar de baja' })).toHaveCount(0);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_detalle_historial.png'), fullPage: true });
    await page.getByRole('link', { name: '← Fichas' }).click();
    await expect.poll(() => nombres(page)).not.toContain('Prueba Editada Ejemplo');
    // Casilla controlada por la URL (?bajas=1): se actualiza tras la navegación.
    await page.getByLabel('Incluir bajas').click();
    await expect(page).toHaveURL(/bajas=1/);
    await expect(page.getByLabel('Incluir bajas')).toBeChecked();
    await expect.poll(() => nombres(page)).toContain('Prueba Editada Ejemplo');
    await expect(page.locator('tr.de-baja', { has: page.getByText('Prueba Editada Ejemplo') })).toContainText('baja 06/11/2026');
  });

  test('detalle: objetivo anual provisional, titular fuera del cómputo y huecos de horas (T5)', async ({ page }) => {
    await page.goto(`/trabajadores/${ID_ELENA}`);
    await expect(page.locator('[data-nombre-ficha]')).toHaveText('Elena Mas Garriga');
    await expect(page.locator('[data-banner-ejemplo]')).toBeVisible();
    await expect(page.locator('[data-provisional]')).toHaveText('provisional: convenio pendiente de publicación');
    // TA1-2: 4,5 h/día × 5 = 22,5 h/sem; 2026: 1767 × 22,5 / 40 = 993,9 h (ejemplo de Pío).
    await expect(page.locator('[data-objetivo="2026"] [data-objetivo-horas]')).toHaveText('993,9 h');
    await expect(page.locator('[data-objetivo="2027"] [data-objetivo-horas]')).toHaveText('985,5 h');
    await expect(page.locator('[data-objetivo="2028"] [data-objetivo-horas]')).toHaveText('985,5 h');
    await expect(page.locator('[data-objetivo="2026"]')).toContainText('1767 h × 22,5 h / 40 h (56,25 %)');
    await expect(page.locator('[data-objetivo="2026"]')).toContainText('referencia 40 h/sem provisional');
    await expect(page.locator('.rrhh-ficha [data-porcentaje-derivado]')).toHaveText('56,25 % · 22,5 h/sem');
    for (const h of ['planificadas', 'confirmadas', 'pendientes']) {
      await expect(page.locator(`[data-hueco-horas="${h}"] dd`)).toHaveText('pendiente motor de horas (T5)');
    }
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_detalle.png'), fullPage: true });
    // TA1-3: detalle de una media tarde, misma fórmula.
    await page.goto(`/trabajadores/${ID_IRENE}`);
    await expect(page.locator('.rrhh-ficha [data-horas-diarias]')).toHaveText('Media tarde · 3,5 h/día');
    await expect(page.locator('[data-objetivo="2026"] [data-objetivo-horas]')).toHaveText('773,1 h'); // 1767 × 17,5 / 40
    await expect(page.locator('[data-objetivo="2027"] [data-objetivo-horas]')).toHaveText('766,5 h');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_detalle_media_tarde.png'), fullPage: true });
    // Edición: el formulario muestra la media tarde con sus horas.
    await page.getByRole('button', { name: 'Editar ficha' }).click();
    const ed = page.locator('[data-formulario-ficha="edicion"]');
    await expect(ed.locator('select[name="tipo_jornada"]')).toHaveValue('MEDIA_TARDE');
    await expect(ed.locator('input[name="horas_diarias"]')).toHaveValue('3,5');
    await ed.getByRole('button', { name: 'Cancelar' }).click();
    await page.goto(`/trabajadores/${ID_TITULAR_PIO}`);
    await expect(page.locator('[data-provisional]')).toHaveText('fuera del cómputo');
    await expect(page.locator('[data-objetivo-horas]')).toHaveText(['fuera del cómputo', 'fuera del cómputo', 'fuera del cómputo']);
    await expect(page.locator('[data-computa]')).toHaveText('No · titular');
  });

  test('escritura solo con sesión y mismo origen; el resto de la API sigue de solo lectura', async ({ page }) => {
    const cuerpo = { farmacia: 'PIO', nombre: 'X', categoria: 'TECNICA', tipo_jornada: 'COMPLETA', horas_diarias: 8, fecha_alta: '2026-11-02' };
    const ajeno = await page.request.post('/api/rrhh/trabajadoras', { data: cuerpo, headers: { origin: 'http://evil.example' } });
    expect(ajeno.status()).toBe(403);
    expect((await page.request.post('/api/inicio', { data: {} })).status()).toBe(405);
    expect((await page.request.put('/api/facturas', { data: {} })).status()).toBe(405);
    expect((await page.request.delete(`/api/rrhh/trabajadoras/${ID_ELENA}`)).status()).toBe(405);
  });

  test('TA-REAL: «Anular» (registro erróneo) con confirmación: no se borra, sale del listado y queda en el historial', async ({ page }) => {
    await abrirFichas(page, '?farmacia=PIO');
    await page.getByRole('button', { name: 'Nueva ficha' }).click();
    const form = page.locator('[data-formulario-ficha="alta"]');
    await form.getByLabel('Nombre').fill('Ficha Creada Por Error');
    await form.locator('input[name="fecha_alta"]').fill('2026-11-02');
    await form.getByRole('button', { name: 'Crear ficha' }).click();
    await page.locator('tr', { has: page.getByText('Ficha Creada Por Error') }).locator('.rrhh-nombre').click();
    await page.locator('[data-anular]').click();
    const dialogo = page.locator('[data-formulario-anular]');
    await expect(dialogo).toContainText('Anular es solo para fichas creadas por error');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_anular.png'), fullPage: true });
    await dialogo.getByRole('button', { name: 'Cancelar' }).click();
    await expect(page.locator('[data-anulada]')).toHaveCount(0); // cancelar no cambia nada
    await page.locator('[data-anular]').click();
    await page.locator('[data-anular-si]').click();
    await expect(page.locator('[data-aviso-rrhh]')).toHaveText('Ficha anulada.');
    await expect(page.locator('[data-anulada]')).toHaveText('anulada');
    await expect(page.getByRole('button', { name: 'Editar ficha' })).toHaveCount(0);
    await expect(page.locator('[data-historial="ANULACION"]')).toContainText('Anulada: No → Sí');
    await page.getByRole('link', { name: '← Fichas' }).click();
    await expect.poll(() => nombres(page)).not.toContain('Ficha Creada Por Error');
    await page.getByLabel('Incluir bajas y anuladas').click();
    await expect.poll(() => nombres(page)).toContain('Ficha Creada Por Error');
  });

  test('TA-REAL: si faltan años del convenio, «Crear convenio 2026–2028 con los valores firmados» con confirmación', async ({ page }) => {
    // Simula una base de datos recién conectada sin convenio (el resto de datos, los de ejemplo).
    await page.route('**/api/rrhh/trabajadoras?**', async (r) => {
      const resp = await r.fetch();
      r.fulfill({ response: resp, json: { ...(await resp.json()), convenio: [] } });
    });
    await abrirFichas(page);
    const caja = page.locator('[data-convenio-falta]');
    await expect(caja).toHaveAttribute('data-convenio-falta', '2026,2027,2028');
    await expect(page.locator('[data-referencia-semanal]')).toHaveCount(0);
    await page.locator('[data-crear-convenio]').click();
    await expect(page.locator('[data-confirmar-convenio]')).toContainText('2026: jornada máxima 1767 h · 1 día de asuntos propios · permiso médico 24 h · referencia 40 h/sem');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_convenio_falta.png'), fullPage: true });
    await page.unroute('**/api/rrhh/trabajadoras?**');
    const crear = page.waitForRequest((q) => q.url().endsWith('/api/rrhh/convenio') && q.method() === 'POST');
    await page.locator('[data-crear-convenio-si]').click();
    expect((await crear).postDataJSON()).toEqual({ anios: [2026, 2027, 2028] });
    await expect(page.locator('[data-aviso-rrhh]')).toHaveText('Convenio creado con los valores firmados.');
    await expect(page.locator('[data-convenio-falta]')).toHaveCount(0);
  });
});

test.describe('Modo REAL simulado (intercepción): sin datos de ejemplo', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('TA-REAL: conectado: banner de datos reales, nunca «Datos de ejemplo»', async ({ page }) => {
    await page.route('**/api/rrhh/estado', (r) => r.fulfill({ json: {
      modo: 'REAL', conectado: true, datos_ejemplo: false, mensaje: 'Datos reales: cada cambio se guarda en la base de datos con autor Marc', anular_eventos: false } }));
    await abrirFichas(page);
    await expect(page.locator('[data-banner-real]')).toHaveText('RealDatos reales: cada cambio se guarda en la base de datos con autor Marc');
    await expect(page.locator('[data-banner-ejemplo]')).toHaveCount(0);
    await expect(page.getByText(/datos de ejemplo/i)).toHaveCount(0);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_real_banner.png') });
  });

  test('TA-REAL: sin credencial: «Falta configurar la credencial de Trabajadores»; ni banner de ejemplo ni fichas', async ({ page }) => {
    const pedidas: string[] = [];
    const AVISO = 'Falta configurar la credencial de Trabajadores';
    await page.route('**/api/estado', (r) => r.fulfill({ json: { modo: 'REAL', farmacia: 'PIO', solo_lectura: true, usuario: 'Pío' } }));
    await page.route('**/api/rrhh/**', (r) => {
      pedidas.push(new URL(r.request().url()).pathname);
      return new URL(r.request().url()).pathname === '/api/rrhh/estado'
        ? r.fulfill({ json: { modo: 'REAL', conectado: false, datos_ejemplo: false, mensaje: AVISO, anular_eventos: false } })
        : r.fulfill({ status: 503, json: { error: 'CREDENCIAL_TRABAJADORES_AUSENTE', mensaje: AVISO } });
    });
    for (const ruta of ['/trabajadores', `/trabajadores/${ID_ELENA}`]) {
      await page.goto(ruta);
      await expect(page.locator('[data-rrhh-pendiente]')).toContainText(AVISO);
      await expect(page.locator('[data-banner-real]')).toHaveCount(0);
      await expect(page.locator('[data-banner-ejemplo]')).toHaveCount(0);
      await expect(page.locator('[data-rrhh-fichas], [data-detalle-ficha]')).toHaveCount(0);
      for (const n of ['Aina Bosch Ferrer', 'Elena Mas Garriga', 'Titular de ejemplo']) await expect(page.getByText(n)).toHaveCount(0);
    }
    await expect(page.locator('.pie')).toContainText('Datos reales');
    // En REAL la pantalla no pide fichas: solo el estado del módulo.
    expect(pedidas.every((p) => p === '/api/rrhh/estado')).toBe(true);
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_real_pendiente.png'), fullPage: true });
  });
});

test.describe('Móvil 390', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test('tarjetas, selector a todo el ancho, banner y detalle sin desbordamiento', async ({ page }) => {
    await abrirFichas(page, '?farmacia=PIO');
    await expect(page.locator('.rrhh-tabla')).toHaveCount(0);
    await expect(page.locator('.rrhh-tarjeta').first()).toBeVisible();
    await expect(page.locator('[data-banner-ejemplo]')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_fichas.png'), fullPage: true });
    await page.getByRole('button', { name: 'Nueva ficha' }).click();
    await expect(page.locator('[data-formulario-ficha="alta"]')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_alta.png'), fullPage: true });
    await page.goto(`/trabajadores/${ID_ELENA}`);
    await expect(page.locator('[data-nombre-ficha]')).toHaveText('Elena Mas Garriga');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_detalle.png'), fullPage: true });
  });
});
