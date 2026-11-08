import { defineConfig } from '@playwright/test';

// Playwright SOLO en modo FIXTURES: nunca abre, captura ni lee datos reales.
if ((process.env.CF_MODO ?? 'FIXTURES') !== 'FIXTURES') {
  throw new Error('PLAYWRIGHT_SOLO_FIXTURES: CF_MODO debe ser FIXTURES');
}

const PUERTO = 5181;
/** Servidor FIXTURES aparte para la prueba de bloqueo (5 min), para no bloquear el resto de pruebas. */
export const PUERTO_BLOQUEO = 5182;

const servidor = (puerto: number, compilar: boolean) => ({
  command: compilar ? 'npm run build && node server/index.ts' : 'node server/index.ts',
  // Sin sesión /api/estado responde 401: Playwright lo da por listo (2xx, 3xx, 400–403).
  url: `http://127.0.0.1:${puerto}/api/estado`,
  reuseExistingServer: false,
  timeout: 120_000,
  env: { CF_MODO: 'FIXTURES', CF_PUERTO: String(puerto) },
});

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: `http://127.0.0.1:${PUERTO}`,
    browserName: 'chromium',
    locale: 'es-ES',
    colorScheme: 'light',
  },
  webServer: [servidor(PUERTO, true), servidor(PUERTO_BLOQUEO, false)],
});
