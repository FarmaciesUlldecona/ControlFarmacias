/**
 * npm run set-password — SOLO LO EJECUTA PÍO.
 *
 * Pide la contraseña de acceso a la web dos veces sin mostrarla, calcula su hash scrypt y crea o sustituye la
 * línea CF_WEB_PASSWORD_HASH de web/app/.env.web sin tocar las demás líneas. Nunca escribe la contraseña.
 *
 * La lógica (`fijarHashEnTexto`, `ejecutar`) está separada de la consola para probarla con un fichero
 * temporal sin invocar el script npm.
 */
import { existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { crearHash, leerHash, LONGITUD_MINIMA } from './acceso.ts';

export const VARIABLE = 'CF_WEB_PASSWORD_HASH';
const LINEA = new RegExp(`^\\s*(export\\s+)?${VARIABLE}\\s*=`);

/** Sustituye (o añade) la línea de la variable. Conserva el resto de líneas y el fin de línea del fichero. */
export function fijarHashEnTexto(texto: string, hash: string): string {
  leerHash(hash); // solo hashes válidos
  const eol = texto.includes('\r\n') ? '\r\n' : '\n';
  const lineas = texto === '' ? [] : texto.split(/\r?\n/);
  const finalVacio = lineas.length > 0 && lineas[lineas.length - 1] === '';
  if (finalVacio) lineas.pop();
  const nueva = `${VARIABLE}=${hash}`;
  let puesta = false;
  const out: string[] = [];
  for (const l of lineas) {
    if (!LINEA.test(l)) { out.push(l); continue; }
    if (!puesta) { out.push(nueva); puesta = true; } // duplicadas: se eliminan
  }
  if (!puesta) out.push(nueva);
  return out.join(eol) + eol;
}

export type Preguntar = (texto: string) => Promise<string>;

/** Flujo completo sobre `ruta`: dos preguntas, validación, escritura atómica. Devuelve 'creada' o 'sustituida'. */
export async function ejecutar(ruta: string, preguntar: Preguntar): Promise<'creada' | 'sustituida'> {
  const a = await preguntar('Nueva contraseña de acceso a la web: ');
  if (a.length < LONGITUD_MINIMA) throw new Error(`CLAVE_CORTA: mínimo ${LONGITUD_MINIMA} caracteres`);
  if (a.trim() !== a) throw new Error('CLAVE_CON_ESPACIOS_EN_LOS_EXTREMOS');
  const b = await preguntar('Repítela: ');
  if (a !== b) throw new Error('CLAVES_DISTINTAS: no se ha cambiado nada');
  const hash = await crearHash(a);
  const previo = existsSync(ruta) ? readFileSync(ruta, 'utf8') : '';
  const sustituida = previo.split(/\r?\n/).some((l) => LINEA.test(l));
  const temporal = `${ruta}.${process.pid}.nuevo`;
  writeFileSync(temporal, fijarHashEnTexto(previo, hash), { encoding: 'utf8', flag: 'wx' });
  renameSync(temporal, ruta);
  return sustituida ? 'sustituida' : 'creada';
}

/** Lee una línea de la consola sin mostrarla. Solo en una consola interactiva. */
export function leerOculto(texto: string): Promise<string> {
  const entrada = process.stdin;
  if (!entrada.isTTY) return Promise.reject(new Error('SIN_CONSOLA: ejecútalo en una ventana de consola'));
  process.stdout.write(texto);
  return new Promise((ok, mal) => {
    let valor = '';
    const terminar = (e: Error | null) => {
      entrada.setRawMode(false);
      entrada.pause();
      entrada.off('data', alLeer);
      process.stdout.write('\n');
      if (e) mal(e); else ok(valor);
    };
    const alLeer = (trozo: string) => {
      for (const c of trozo) {
        if (c === '\r' || c === '\n') return terminar(null);
        if (c === '\u0003') return terminar(new Error('CANCELADO'));
        if (c === '\u007f' || c === '\b') { valor = [...valor].slice(0, -1).join(''); continue; }
        if (c >= ' ') valor += c;
      }
    };
    entrada.setEncoding('utf8');
    entrada.setRawMode(true);
    entrada.resume();
    entrada.on('data', alLeer);
  });
}

if (import.meta.main) {
  const { RUTA_ENV_WEB } = await import('./adaptador_real.ts');
  try {
    const r = await ejecutar(RUTA_ENV_WEB, leerOculto);
    console.log(`${VARIABLE} ${r} en web\\app\\.env.web. Reinicia la web para aplicarla.`);
  } catch (e) {
    console.log(`ERROR ${e instanceof Error ? e.message : String(e)}`);
    process.exitCode = 1;
  }
}
