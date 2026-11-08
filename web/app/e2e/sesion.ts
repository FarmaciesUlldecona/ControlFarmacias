// H4b: entrada con la contraseña ficticia del modo FIXTURES (nunca la real).
import { expect, type Page } from '@playwright/test';
import { CLAVE_FIXTURES } from '../server/acceso.ts';

export { CLAVE_FIXTURES };

/** Entra por la pantalla de acceso, como lo haría Pío. */
export async function entrar(page: Page, ruta = '/') {
  await page.goto(ruta);
  await expect(page.getByRole('heading', { name: 'Entrar' })).toBeVisible();
  await page.getByLabel('Contraseña').fill(CLAVE_FIXTURES);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(page.locator('.app')).toBeVisible();
}
