// TA-FICHA Trabajadores: ficha anual de cada persona y resumen de plantilla con los datos de ejemplo del servidor
// FIXTURES (fixtures/rrhh/ficha_anual.json: solo fichas de RITA, que las pruebas de TA1/TA2 no tocan). Solo FIXTURES.
// Reloj del navegador fijo (hoy = 13 nov 2026, salvo en la prueba del aviso de octubre).
// TA-REAL-2: vacaciones del convenio, días extra (Rosa 2 de ejemplo; Irene se edita y se anula al final) y «pendiente».
import { expect, test, type Page } from '@playwright/test';
import { join } from 'node:path';
import { entrar } from './sesion.ts';

const CAPTURAS = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'ta_ficha');
const CAPTURAS_TA_REAL_2 = join(import.meta.dirname, '..', '..', 'docs', 'capturas', 'ta_real_2');
const ID = (n: number) => `e0000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const AINA = ID(1); const LAURA = ID(11); const MARTA = ID(12); const SILVIA = ID(13); const JUDIT = ID(14); const ROSA = ID(15); const PAULA = ID(16);
const IRENE = ID(17);
const TITULAR_RITA = ID(22);

async function preparar(page: Page, hoy = '2026-11-13T10:00:00') {
  await page.clock.setFixedTime(new Date(hoy));
  await entrar(page);
  expect((await (await page.request.get('/api/estado')).json()).modo).toBe('FIXTURES');
}
async function abrirFichas(page: Page, consulta = '') {
  await page.goto(`/trabajadores${consulta}`);
  await expect(page.locator('[data-resumen-pie]')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}
async function abrirFicha(page: Page, id: string, consulta = '') {
  await page.goto(`/trabajadores/${id}${consulta}`);
  await expect(page.locator('[data-bloque="vacaciones"], [data-ficha-sin-datos]').first()).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}
const fila = (page: Page, id: string) => page.locator(`.fa-tabla [data-fila-resumen="${id}"]`);
const cifra = (page: Page, c: string) => page.locator(`[data-cifra="${c}"] .fa-cifra-valor`);

test.describe('TA-FICHA PC 1440', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('resumen de plantilla: encima del listado; farmacia, año, orden y avisos', async ({ page }) => {
    await preparar(page);
    await abrirFichas(page, '?farmacia=RITA');
    const resumen = page.locator('[data-resumen-plantilla]');
    await expect(resumen).toHaveAttribute('data-resumen-plantilla', '2026');
    await expect(resumen.locator('h2')).toHaveText('Resumen de plantilla 2026');
    // Encima del listado de fichas.
    expect(await page.evaluate(() => {
      const r = document.querySelector('[data-resumen-plantilla]');
      const l = document.querySelector('.rrhh-tabla');
      return !!r && !!l && !!(r.compareDocumentPosition(l) & Node.DOCUMENT_POSITION_FOLLOWING);
    })).toBe(true);
    await expect(page.locator('[data-resumen-pie]')).toContainText('calculado a 13/11/2026');
    await expect(page.locator('[data-resumen-pie]')).not.toContainText('festivos'); // TA3-2: el objetivo ya descuenta los festivos
    await expect(page.locator('[data-resumen-pie]')).toContainText('vacaciones: 30 días naturales del convenio');
    await expect(fila(page, ROSA).locator('[data-col="vacaciones"]')).toHaveText('32 de 32 (2 extra)'); // TA-REAL-2: 30 + 2 días extra
    // Una fila por persona de RITA, con sus cifras.
    await expect(fila(page, LAURA).locator('[data-col="vacaciones"]')).toHaveText('0 de 30');
    await expect(fila(page, LAURA).locator('[data-col="avisos"]')).toHaveText('—');
    await expect(fila(page, SILVIA).locator('[data-col="vacaciones"]')).toHaveText('12,5 de 30');
    await expect(fila(page, SILVIA).locator('[data-aviso="VACACIONES_SIN_PLANIFICAR"]')).toHaveText('Quedan 12,5 días de vacaciones sin planificar');
    await expect(fila(page, PAULA).locator('[data-col="vacaciones"]')).toHaveText('11 de 16'); // alta 1 jul: proporcional
    await expect(fila(page, JUDIT).locator('[data-col="horas"]')).toHaveText('exceso 129 h ≈ 16,1 días'); // TA-FICHA-2: con su descanso compensatorio
    await expect(fila(page, JUDIT).locator('[data-aviso="EXCESO_HORAS"]')).toBeVisible();
    await expect(fila(page, MARTA).locator('[data-col="baja"]')).toHaveText('11');
    await expect(fila(page, LAURA).locator('[data-col="libre"]')).toHaveText('1 de 1');
    await expect(fila(page, TITULAR_RITA).locator('[data-col="horas"]')).toContainText('sin objetivo');
    await expect(fila(page, AINA)).toHaveCount(0); // PIO
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_resumen.png'), fullPage: true });

    // Ordenable: las cifras empiezan de más a menos (exceso arriba); un segundo clic invierte.
    const ordenHoras = page.locator('[data-ordenar="horas"]');
    await ordenHoras.click();
    await expect(page.locator('th', { has: ordenHoras })).toHaveAttribute('aria-sort', 'descending');
    await expect(page.locator('.fa-tabla tbody tr').first()).toHaveAttribute('data-fila-resumen', JUDIT);
    await ordenHoras.click();
    await expect(page.locator('th', { has: ordenHoras })).toHaveAttribute('aria-sort', 'ascending');
    await expect(page.locator('.fa-tabla tbody tr').last()).toHaveAttribute('data-fila-resumen', JUDIT);
    await page.locator('[data-ordenar="baja"]').click();
    await expect(page.locator('.fa-tabla tbody tr').first()).toHaveAttribute('data-fila-resumen', MARTA);
    await page.locator('[data-ordenar="vacaciones"]').click();
    await page.locator('[data-ordenar="vacaciones"]').click();
    await expect(page.locator('.fa-tabla tbody tr').first()).toHaveAttribute('data-fila-resumen', LAURA); // 0 sin planificar

    // Selector de farmacia (el mismo del listado): PIO y Ambas.
    await page.locator('[data-selector-farmacia="PIO"]').click();
    await expect(fila(page, AINA)).toBeVisible();
    await expect(fila(page, LAURA)).toHaveCount(0);
    await page.locator('[data-selector-farmacia="AMBAS"]').click();
    await expect(fila(page, AINA)).toBeVisible();
    await expect(fila(page, LAURA)).toBeVisible();

    // Selector de año: 2027 (sin eventos de ejemplo en RITA: 30 de 30; aún no toca el aviso de octubre).
    await page.locator('[data-selector-anio="2027"]').click();
    await expect(page).toHaveURL(/anio=2027/);
    await expect(resumen.locator('h2')).toHaveText('Resumen de plantilla 2027');
    await expect(fila(page, LAURA).locator('[data-col="vacaciones"]')).toHaveText('30 de 30');
    await expect(fila(page, LAURA).locator('[data-col="libre"]')).toHaveText('0 de 0'); // 2027: 0 días en el convenio
    await expect(fila(page, SILVIA).locator('[data-aviso="VACACIONES_SIN_PLANIFICAR"]')).toHaveCount(0);
    await expect(fila(page, PAULA).locator('[data-col="vacaciones"]')).toHaveText('30 de 30');
  });

  test('ficha de Sílvia: regla de vacaciones (fin de semana dentro y media franja), bloques y aviso de octubre', async ({ page }) => {
    await preparar(page);
    await abrirFicha(page, SILVIA);
    await expect(page.locator('[data-ficha-anual]')).toHaveAttribute('data-ficha-anual', '2026');
    await expect(page.locator('#t-fa')).toHaveText('Año 2026');
    await expect(page.locator('[data-selector-anio="2026"]')).toHaveAttribute('aria-checked', 'true');
    // Vacaciones: 30 naturales; 12,5 disfrutados (3–14 ago = 12, 9 oct media franja = 0,5), 5 planificados, 12,5 sin planificar.
    await expect(page.locator('[data-derecho-vacaciones]')).toContainText('30 días naturales');
    await expect(cifra(page, 'disfrutadas')).toHaveText('12,5');
    await expect(cifra(page, 'planificadas')).toHaveText('5');
    await expect(cifra(page, 'pendientes')).toHaveText('12,5');
    await expect(page.locator('[data-cifra="pendientes"]')).toHaveClass(/naranja/);
    const regla = page.locator('[data-regla-vacaciones]');
    await expect(regla.locator('.fa-dia')).toHaveCount(30);
    await expect(regla.locator('.fa-dia[data-a="disfrutada"]')).toHaveCount(13);
    await expect(regla.locator('.fa-dia[data-b="disfrutada"]')).toHaveCount(12); // la casilla 13 es media: disfrutada + planificada
    await expect(regla).toHaveClass(/avisar/);
    await expect(page.locator('[data-periodo-vacaciones]')).toHaveText(['3–14 ago 2026 · 12 días', '9 oct 2026 · media franja, 0,5 días', '23–27 nov 2026 · 5 días']);
    // TA-REAL-2: días extra editables (ya no «pendiente de habilitar»); fuente de las vacaciones del convenio.
    await expect(page.locator('[data-dias-extra]')).toBeEnabled();
    await expect(page.locator('[data-dias-extra-actual]')).toHaveText('sin días extra');
    await expect(page.getByText('pendiente de habilitar')).toHaveCount(0);
    await expect(page.locator('[data-desglose-vacaciones]')).toHaveText(' · 30 del convenio');
    await expect(page.locator('[data-fuente-vacaciones]')).toHaveText(' · fuente: decisión de Pío, pendiente de texto publicado');
    await expect(page.locator('[data-aviso="VACACIONES_SIN_PLANIFICAR"]')).toHaveText('Quedan 12,5 días de vacaciones sin planificar');
    // Libre disposición, permiso médico, baja, horas y próximas ausencias.
    await expect(page.locator('[data-libre-restantes]')).toHaveText('1 de 1 día restantes');
    await expect(page.locator('[data-medico-usadas]')).toHaveText('0 de 24 h usadas');
    await expect(page.locator('[data-dias-baja]')).toHaveText('0 días en 2026');
    await expect(page.locator('[data-objetivo-anual]')).toContainText('objetivo 1767 h');
    await expect(page.locator('[data-bloque="horas"]')).not.toContainText('aún no descontados'); // TA3-2: texto retirado
    await expect(page.locator('[data-ausencia]').first()).toHaveAttribute('data-ausencia', 'VACACIONES');
    await expect(page.locator('[data-ausencia]').first()).toContainText('23–27 nov 2026');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_ficha.png'), fullPage: true });
    // La ausencia lleva a su semana en el calendario.
    await page.locator('[data-ausencia] a').first().click();
    await expect(page).toHaveURL(/\/trabajadores\/calendario\?farmacia=RITA&fecha=2026-11-23&persona=/);
  });

  test('alta a mitad de año (Paula), exceso de horas (Judit), baja (Marta), sin avisos (Laura), titular y selector de año', async ({ page }) => {
    await preparar(page);
    await abrirFicha(page, PAULA);
    await expect(page.locator('[data-derecho-vacaciones]')).toContainText('16 días naturales');
    await expect(page.locator('[data-proporcional]')).toContainText('184 de 365 días en alta (30 × 184/365, redondeo hacia arriba)');
    await expect(page.locator('[data-desglose-vacaciones]')).toHaveText(' · 16 proporcionales');
    await expect(page.locator('[data-regla-vacaciones] .fa-dia')).toHaveCount(16);
    await expect(cifra(page, 'disfrutadas')).toHaveText('5'); // 7–11 sep, su franja única = 1 día
    await expect(page.locator('[data-objetivo-anual]')).toContainText('objetivo 501 h');
    await expect(page.locator('[data-objetivo-anual]')).toContainText('proporcional a 184 de 365 días en alta (año completo: 993,9 h)');
    await page.locator('[data-selector-anio="2027"]').click();
    await expect(page).toHaveURL(/anio=2027/);
    await expect(page.locator('#t-fa')).toHaveText('Año 2027');
    await expect(page.locator('[data-derecho-vacaciones]')).toContainText('30 días naturales');
    await expect(page.locator('[data-proporcional]')).toHaveCount(0);

    await abrirFicha(page, JUDIT);
    // TA-FICHA-2: el descanso compensatorio del 6 nov (8 h, confirmado) suma como trabajado.
    await expect(page.locator('[data-exceso-horas]')).toContainText('Exceso de 129 h ≈ 16,1 días que podrían ser vacaciones');
    await expect(page.locator('[data-aviso="EXCESO_HORAS"]')).toBeVisible();
    await expect(cifra(page, 'confirmadas')).toHaveText('1776');
    await expect(cifra(page, 'planificadas-h')).toHaveText('120');
    await expect(cifra(page, 'exceso')).toHaveText('129');
    await expect(page.locator('[data-horas-suman]')).toContainText('baja y descanso compensatorio');
    await page.screenshot({ path: join(CAPTURAS, 'pc1440_ficha_exceso.png'), fullPage: true });

    await abrirFicha(page, MARTA);
    await expect(page.locator('[data-dias-baja]')).toHaveText('11 días en 2026'); // 12–17 mar (6) + 9–13 nov (5)
    await expect(page.locator('[data-bloque="baja"]')).not.toContainText(/motivo|médic|enferm/i);

    await abrirFicha(page, LAURA);
    await expect(page.locator('[data-avisos-ficha]')).toHaveCount(0);
    await expect(page.locator('[data-regla-vacaciones] .fa-dia[data-a="disfrutada"]')).toHaveCount(30);
    await expect(page.locator('[data-medico-usadas]')).toHaveText('8 de 24 h usadas');

    await abrirFicha(page, TITULAR_RITA);
    await expect(page.locator('[data-horas-titular]')).toContainText('sin objetivo');
  });

  test('aviso de octubre según el día: 30 sep no, 1 oct sí', async ({ page }) => {
    await preparar(page, '2026-09-30T10:00:00');
    await abrirFicha(page, SILVIA);
    await expect(cifra(page, 'disfrutadas')).toHaveText('12'); // el 9 oct aún es planificado
    await expect(cifra(page, 'planificadas')).toHaveText('5,5');
    await expect(page.locator('[data-aviso="VACACIONES_SIN_PLANIFICAR"]')).toHaveCount(0);
    await page.clock.setFixedTime(new Date('2026-10-01T10:00:00'));
    await page.reload();
    await expect(page.locator('[data-aviso="VACACIONES_SIN_PLANIFICAR"]')).toHaveText('Quedan 12,5 días de vacaciones sin planificar');
  });

  test('TA-REAL-2: días extra: Rosa (2 de ejemplo); Irene: guardar, editar, validar y anular (base + extra)', async ({ page }) => {
    await preparar(page);
    await abrirFicha(page, ROSA);
    await expect(page.locator('[data-derecho-vacaciones] strong')).toHaveText('32 días');
    await expect(page.locator('[data-desglose-vacaciones]')).toHaveText(' · 30 del convenio + 2 extra');
    await expect(page.locator('[data-dias-extra-actual]')).toHaveText('2 días · «Acuerdo de ejemplo por antigüedad»');
    await expect(page.locator('[data-dias-extra]')).toHaveValue('2');
    await expect(page.locator('[data-regla-vacaciones] .fa-dia')).toHaveCount(32);
    await expect(cifra(page, 'pendientes')).toHaveText('32');
    await expect(page.locator('[data-guardar-extra]')).toBeDisabled(); // sin cambios
    await page.screenshot({ path: join(CAPTURAS_TA_REAL_2, 'pc1440_ficha_dias_extra.png'), fullPage: true });

    await abrirFicha(page, IRENE);
    await expect(page.locator('[data-dias-extra-actual]')).toHaveText('sin días extra');
    await expect(page.locator('[data-anular-extra]')).toHaveCount(0);
    // Validación: entero ≥ 0.
    await page.locator('[data-dias-extra]').fill('-1');
    await page.locator('[data-guardar-extra]').click();
    await expect(page.locator('[data-aviso-extra]')).toHaveText('Días extra: un número entero de 0 a 365');
    // Guardar 3 con nota.
    await page.locator('[data-dias-extra]').fill('3');
    await page.locator('[data-nota-extra]').fill('Acuerdo de ejemplo');
    const guardar = page.waitForRequest((q) => q.url().endsWith(`/api/rrhh/trabajadoras/${IRENE}/ajustes/2026`) && q.method() === 'PUT');
    await page.locator('[data-guardar-extra]').click();
    expect((await guardar).postDataJSON()).toEqual({ vacaciones_dias_extra: 3, nota: 'Acuerdo de ejemplo' });
    await expect(page.locator('[data-aviso-extra]')).toHaveText('Días extra de 2026 guardados: 3 días.');
    await expect(page.locator('[data-derecho-vacaciones] strong')).toHaveText('33 días');
    await expect(page.locator('[data-desglose-vacaciones]')).toHaveText(' · 30 del convenio + 3 extra');
    await expect(page.locator('[data-dias-extra-actual]')).toHaveText('3 días · «Acuerdo de ejemplo»');
    await expect(cifra(page, 'pendientes')).toHaveText('33');
    // Editar a 1 sin nota.
    await page.locator('[data-dias-extra]').fill('1');
    await page.locator('[data-nota-extra]').fill('');
    await page.locator('[data-guardar-extra]').click();
    await expect(page.locator('[data-dias-extra-actual]')).toHaveText('1 día');
    await expect(page.locator('[data-derecho-vacaciones] strong')).toHaveText('31 días');
    // Anular con confirmación (no se borra).
    await page.locator('[data-anular-extra]').click();
    await expect(page.locator('[data-confirmar-anular-extra]')).toContainText('Se anularán los días extra de 2026 (1 día; quedan registrados, no se borran). El derecho vuelve a 30 días.');
    await page.screenshot({ path: join(CAPTURAS_TA_REAL_2, 'pc1440_ficha_dias_extra_anular.png'), fullPage: true });
    await page.locator('[data-anular-extra-si]').click();
    await expect(page.locator('[data-aviso-extra]')).toHaveText('Días extra de 2026 anulados.');
    await expect(page.locator('[data-dias-extra-actual]')).toHaveText('sin días extra');
    await expect(page.locator('[data-derecho-vacaciones] strong')).toHaveText('30 días');
    await expect(page.locator('[data-dias-extra]')).toHaveValue('');
  });

  test('TA3-2: un festivo dado de alta entre días de vacaciones hace de puente (Irene 18 y 22 mar 2027, 19 festivo = 5 días); dado de baja, 1 + 1', async ({ page }) => {
    await preparar(page);
    await abrirFicha(page, IRENE, '?anio=2027');
    // Preparación por la API (2027, Irene; se deshace al final: el servidor es común a todas las pruebas).
    const W = { headers: { origin: new URL(page.url()).origin } };
    expect((await page.request.post('/api/rrhh/festivos', { ...W, data: { fecha: '2027-03-19', nombre: 'Puente de ejemplo' } })).status()).toBe(201);
    const p = await page.request.post('/api/rrhh/eventos', { ...W, data: { accion: 'PINTAR', tipo: 'VACACIONES', celdas: [
      { trabajadora_id: IRENE, fecha: '2027-03-18' }, { trabajadora_id: IRENE, fecha: '2027-03-22' }] } });
    expect(p.status()).toBe(200);
    const cambio = (await p.json()).cambio.id as string;
    try {
      await abrirFicha(page, IRENE, '?anio=2027');
      const periodos = page.locator('[data-periodos-vacaciones] [data-periodo-vacaciones]');
      await expect(periodos).toHaveText(['18–22 mar 2027 · 5 días']);
      await expect(cifra(page, 'planificadas')).toHaveText('5');
      await expect(page.locator('[data-bloque="horas"]')).not.toContainText('aún no descontados');
      await page.locator('[data-bloque="vacaciones"]').screenshot({ path: join(CAPTURAS, 'pc1440_vacaciones_puente_festivo.png') });
      // Sin el festivo: la regla de siempre (el viernes laborable corta).
      expect((await page.request.put('/api/rrhh/festivos/2027-03-19/anular', { ...W, data: { confirmar: true } })).status()).toBe(200);
      await abrirFicha(page, IRENE, '?anio=2027');
      await expect(periodos).toHaveText(['18 mar 2027 · 1 día', '22 mar 2027 · 1 día']);
      await expect(cifra(page, 'planificadas')).toHaveText('2');
    } finally {
      await page.request.post('/api/rrhh/eventos/deshacer', { ...W, data: { cambio_id: cambio } });
      await page.request.put('/api/rrhh/festivos/2027-03-19/anular', { ...W, data: { confirmar: true } });
    }
  });

  test('TA-REAL-2: convenio sin días de vacaciones (como hoy en REAL): la ficha muestra «pendiente», sin regla ni cifra inventada', async ({ page }) => {
    await preparar(page);
    // La ficha de Laura como la calcularía el servidor con convenio_anual sin vacaciones_dias_naturales.
    await page.route('**/api/rrhh/trabajadoras/*/anual?**', async (r) => {
      const resp = await r.fetch();
      const d = await resp.json();
      const v = { ...d.ficha.vacaciones, base: null, fuente: null, derecho_base: null, derecho: null, pendientes: null };
      const avisos = [{ codigo: 'VACACIONES_SIN_DATO', texto: 'Vacaciones de 2026 pendientes: el convenio no tiene los días' }];
      r.fulfill({ response: resp, json: { ...d, reglas: { ...d.reglas, vacaciones_dias: null, vacaciones_fuente: null }, ficha: { ...d.ficha, vacaciones: v, avisos } } });
    });
    await abrirFicha(page, LAURA);
    await expect(page.locator('[data-vacaciones-pendiente]')).toHaveText('pendiente');
    await expect(page.locator('[data-derecho-vacaciones]')).toContainText('el convenio de 2026 no tiene los días');
    await expect(page.locator('[data-regla-vacaciones]')).toHaveCount(0);
    await expect(cifra(page, 'pendientes')).toHaveText('pendiente');
    await expect(cifra(page, 'disfrutadas')).toHaveText('30'); // lo disfrutado sí se cuenta
    await expect(page.locator('[data-aviso="VACACIONES_SIN_DATO"]')).toHaveText('Vacaciones de 2026 pendientes: el convenio no tiene los días');
    await expect(page.locator('[data-aviso="VACACIONES_SIN_DATO"]')).toHaveClass(/gris/);
    await page.screenshot({ path: join(CAPTURAS_TA_REAL_2, 'pc1440_ficha_vacaciones_pendiente.png'), fullPage: true });
  });
});

test.describe('TA-FICHA Móvil 390', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test('resumen en tarjetas y ficha sin desbordamiento', async ({ page }) => {
    await preparar(page);
    await abrirFichas(page, '?farmacia=RITA');
    await expect(page.locator('.fa-tabla')).toHaveCount(0);
    await expect(page.locator(`.fa-tarjeta[data-fila-resumen="${JUDIT}"] [data-col="horas"]`)).toHaveText('exceso 129 h ≈ 16,1 días');
    await page.locator('[data-ordenar-movil]').selectOption('horas:desc');
    await expect(page.locator('.fa-tarjeta').first()).toHaveAttribute('data-fila-resumen', JUDIT);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_resumen.png'), fullPage: true });
    await abrirFicha(page, SILVIA);
    await expect(page.locator('[data-regla-vacaciones] .fa-dia')).toHaveCount(30);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: join(CAPTURAS, 'movil390_ficha.png'), fullPage: true });
  });
});
