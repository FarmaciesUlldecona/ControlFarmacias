#!/usr/bin/env node
// Hook PreToolUse "bloqueo_rutas" (sesión WEB). Sin dependencias.
//
// - Textos secretos (clave de sistema de Supabase): en TODOS los campos,
//   incluidos contenidos y nombres de clave.
// - Rutas prohibidas: solo en campos de ruta (file_path, path, pattern, glob,
//   notebook_path...) y en comandos de shell (command). Los campos de contenido
//   (content, old_string, new_string, edits) no se revisan por rutas.
// - Comandos de shell, además: órdenes reservadas a Pío, cualquier "..",
//   y rutas absolutas bajo C:/ControlFarmacias fuera de Programa_web/web.
// - JSON ilegible o error interno: bloquea (falla cerrado).
//
// Los textos prohibidos se construyen por partes para que este fichero pueda
// editarse con el propio hook activo.
import path from 'node:path';

const RAIZ = 'c:/controlfarmacias';
const PW = RAIZ + '/programa_web';
const BASE = PW + '/web';

const PROHIBIDAS = [
  [PW + '/' + 'logs', 'carpeta logs de Programa_web'],
  [PW + '/' + 'tmp', 'carpeta tmp de Programa_web'],
  [PW + '/pruebas/' + 'facturas', 'facturas de prueba'],
  [PW + '/' + '.' + 'venv', 'entorno virtual python'],
  [RAIZ + '/programa', 'repositorio Programa'],
];

const ENV = new RegExp('(^|[^a-z0-9_])\\.' + 'env' + '(\\.[a-z0-9_*-]+)*\\*?(?![a-z0-9_])');
const SEG_VENV = new RegExp('(^|/)\\.' + 'venv' + '(/|$|[^a-z0-9_])');
const SEG_PF = new RegExp('(^|/)pruebas/' + 'facturas' + '(/|$|[^a-z0-9_])');
const SECRETOS = ['service' + '_role', 'supabase' + '_service'];
const ORDENES = ['dev:real', 'check:real', 'set-password', '--modo=real', 'cf_modo=real', 'iniciar_web'];
const PUNTOS = new RegExp('(^|[^a-z0-9_.])' + '\\.\\.' + '(/|$|[^a-z0-9_.])');
const PUNTOS_SEG = new RegExp('(^|/)' + '\\.\\.' + '(/|$)');

const CLAVES_RUTA = new Set([
  'file_path', 'path', 'paths', 'pattern', 'glob', 'notebook_path', 'file_paths',
  'cwd', 'directory', 'dir', 'root', 'out_dir', 'filepath', 'filename',
]);
const CLAVES_CONTENIDO = new Set(['content', 'old_string', 'new_string', 'edits', 'new_source']);

function bloquear(motivo) {
  process.stderr.write(`BLOQUEADO por bloqueo_rutas: ${motivo}\n`);
  process.exit(2);
}

function normalizar(s) {
  let t = String(s).toLowerCase().replace(/\\/g, '/');
  // Formas POSIX de unidad en Windows: /c/x, //c/x, /mnt/c/x -> c:/x
  t = t.replace(/(^|[^a-z0-9_.:])\/{1,2}(?:mnt\/)?([a-z])\//g, '$1$2:/');
  // Barras repetidas (p. ej. barras invertidas escapadas)
  t = t.replace(/\/{2,}/g, '/');
  return t;
}

function esPrefijo(ruta, p) {
  return ruta === p || ruta.startsWith(p + '/');
}

function absoluta(t, desde) {
  const r = /^[a-z]:\//.test(t) ? path.win32.resolve(t) : path.win32.resolve(desde, t);
  return r.toLowerCase().replace(/\\/g, '/').replace(/\/+$/, '');
}

function prohibida(abs) {
  for (const [p, motivo] of PROHIBIDAS) if (esPrefijo(abs, p)) return motivo;
  return null;
}

function patronesComunes(t) {
  if (ENV.test(t)) return 'fichero de entorno (env)';
  if (SEG_VENV.test(t)) return 'entorno virtual python';
  if (SEG_PF.test(t)) return 'facturas de prueba';
  return null;
}

function revisarCampoRuta(clave, valor, desde) {
  const t = normalizar(valor);
  const m = patronesComunes(t);
  if (m) return m;
  const comodin = t.search(/[*?[{]/);
  let fijo = t;
  if (comodin >= 0) {
    if (PUNTOS_SEG.test(t.slice(comodin))) return 'ruta con dos puntos tras comodín';
    fijo = t.slice(0, comodin);
    fijo = fijo.slice(0, fijo.lastIndexOf('/') + 1);
  }
  const abs = absoluta(fijo || '.', desde);
  const p = prohibida(abs);
  if (p) return p;
  // Búsqueda (path o patrón con comodín) cuya raíz abarca una ruta prohibida.
  if (comodin >= 0 || clave === 'path') {
    for (const [pr, motivo] of PROHIBIDAS) {
      if (pr.startsWith(abs + '/')) return `búsqueda que abarca ${motivo}`;
    }
  }
  return null;
}

function revisarComando(valor) {
  const t = normalizar(valor);
  for (const o of ORDENES) if (t.includes(o)) return `orden reservada a Pío (${o})`;
  if (PUNTOS.test(t)) return 'ruta con dos puntos (..) en comando';
  const m = patronesComunes(t);
  if (m) return m;
  // Rutas absolutas bajo la raíz del proyecto: solo dentro de Programa_web/web.
  let i = t.indexOf(RAIZ);
  while (i >= 0) {
    const resto = t.slice(i);
    const dentro = resto.startsWith(BASE) && !/^[a-z0-9_.-]/.test(resto.slice(BASE.length));
    if (!dentro) return 'ruta absoluta fuera de Programa_web/web';
    i = t.indexOf(RAIZ, i + 1);
  }
  // Tokens con aspecto de ruta, resueltos contra BASE.
  const tokens = t.split(/[\s"'`,;|&<>(){}\[\]=]+/).filter(Boolean);
  for (const tok of tokens) {
    if (!(tok.includes('/') || tok.startsWith('.'))) continue;
    const limpio = tok.replace(/[*?].*$/, '') || '.';
    let abs;
    try {
      abs = absoluta(limpio, BASE);
    } catch {
      continue;
    }
    const p = prohibida(abs);
    if (p) return p;
  }
  return null;
}

function todosLosTextos(v, salida) {
  if (v == null) return;
  if (typeof v === 'string') salida.push(v);
  else if (Array.isArray(v)) v.forEach((x) => todosLosTextos(x, salida));
  else if (typeof v === 'object') {
    for (const [k, x] of Object.entries(v)) {
      salida.push(k);
      todosLosTextos(x, salida);
    }
  } else salida.push(String(v));
}

function revisarCampos(v, clave, raizBusqueda) {
  if (v == null) return null;
  if (clave && CLAVES_CONTENIDO.has(clave)) return null;
  if (typeof v === 'string') {
    if (clave === 'command') return revisarComando(v);
    if (clave && CLAVES_RUTA.has(clave)) {
      return revisarCampoRuta(clave, v, clave === 'path' ? BASE : raizBusqueda);
    }
    return null;
  }
  if (Array.isArray(v)) {
    for (const x of v) {
      const m = revisarCampos(x, clave, raizBusqueda);
      if (m) return m;
    }
    return null;
  }
  if (typeof v === 'object') {
    for (const [k, x] of Object.entries(v)) {
      const m = revisarCampos(x, k, raizBusqueda);
      if (m) return m;
    }
  }
  return null;
}

let datos = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (c) => (datos += c));
process.stdin.on('error', () => bloquear('error leyendo stdin'));
process.stdin.on('end', () => {
  try {
    let evento;
    try {
      evento = JSON.parse(datos);
    } catch {
      bloquear('JSON de entrada ilegible');
    }
    if (!evento || typeof evento !== 'object') bloquear('JSON de entrada no válido');
    const herramienta = evento.tool_name ?? 'herramienta';
    const entrada = evento.tool_input ?? {};

    // 1) Textos secretos en todos los campos.
    const textos = [];
    todosLosTextos(entrada, textos);
    for (const s of textos) {
      const l = String(s).toLowerCase();
      for (const sec of SECRETOS) if (l.includes(sec)) bloquear(`${herramienta} contiene texto secreto prohibido`);
    }

    // 2) Rutas y comandos.
    let raizBusqueda = BASE;
    if (entrada && typeof entrada.path === 'string' && entrada.path.trim()) {
      raizBusqueda = absoluta(normalizar(entrada.path).replace(/[*?].*$/, '') || '.', BASE);
    }
    const motivo = revisarCampos(entrada, null, raizBusqueda);
    if (motivo) bloquear(`${herramienta} referencia ${motivo}`);
    process.exit(0);
  } catch {
    bloquear('error interno del hook');
  }
});
