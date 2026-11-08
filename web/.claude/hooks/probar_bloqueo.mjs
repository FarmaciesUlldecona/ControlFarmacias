#!/usr/bin/env node
// Pruebas de bloqueo_rutas.mjs: le pasa casos por stdin y comprueba el exit code.
// Los textos prohibidos se construyen en tiempo de ejecución ({U}, {E}, ...) para
// que este fichero pueda editarse con el hook activo.
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const HOOK = path.join(path.dirname(fileURLToPath(import.meta.url)), 'bloqueo_rutas.mjs');

const R = {
  U: '.' + '.',
  E: '.' + 'env',
  V: '.' + 'venv',
  PF: 'pruebas' + '/' + 'facturas',
  CF: 'C:' + '\\' + 'ControlFarmacias',
  CFB: '/' + 'c' + '/' + 'ControlFarmacias',
  SR: 'service' + '_role',
  SS: 'SUPABASE' + '_SERVICE',
};
const P = (v) => {
  if (typeof v === 'string') return v.replace(/\{(\w+)\}/g, (_, k) => R[k]);
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, P(x)]));
  return v;
};

// [nombre, herramienta, tool_input, debe bloquear]
const casos = [
  // --- 20 casos de Blindaje 2 (19 + JSON ilegible al final) ---
  ['Glob {U}\\logs', 'Glob', { pattern: '*', path: '{U}\\logs' }, true],
  ['Glob patrón {U}/logs/**', 'Glob', { pattern: '{U}/logs/**' }, true],
  ['Read {U}/tmp/x', 'Read', { file_path: '{U}/tmp/x' }, true],
  ['Grep en Programa_web\\{PF}', 'Grep', { pattern: 'CIF', path: '{CF}\\Programa_web\\{PF}' }, true],
  ['Grep en {U}/{PF}', 'Grep', { pattern: 'CIF', path: '{U}/{PF}' }, true],
  ['Read {U}/{V}/x', 'Read', { file_path: '{U}/{V}/Lib/x.py' }, true],
  ['PowerShell {CF}\\Programa\\x', 'PowerShell', { command: 'Get-Content {CF}\\Programa\\x' }, true],
  ['Bash {CFB}/Programa/x', 'Bash', { command: 'cat {CFB}/Programa/x' }, true],
  ['Read {U}/{U}/Programa/docs (relativa)', 'Read', { file_path: '{U}/{U}/Programa/docs/a.md' }, true],
  ['Read app/{E}.web', 'Read', { file_path: 'app/{E}.web' }, true],
  ['Bash cat {E}', 'Bash', { command: 'cat {E}' }, true],
  ['Glob **/{E}*', 'Glob', { pattern: '**/{E}*' }, true],
  ['Texto {SR}', 'Bash', { command: 'echo {SR}' }, true],
  ['Texto {SS}_KEY', 'Write', { file_path: 'a.txt', content: '{SS}_KEY=1' }, true],
  ['Permitida web/app/src/main.tsx', 'Read', { file_path: '{CF}\\Programa_web\\web\\app\\src\\main.tsx' }, false],
  ['Permitida app/src/main.tsx (relativa)', 'Read', { file_path: 'app/src/main.tsx' }, false],
  ['Permitida Programa_web/web/x', 'Read', { file_path: '{CF}/Programa_web/web/x' }, false],
  ['Permitida process.env.X en código', 'Write', { file_path: 'app/src/a.ts', content: 'const p = process.env.PORT;' }, false],
  ['Permitida npx tsc', 'Bash', { command: 'cd app && npx tsc --noEmit' }, false],
  // --- Blindaje 3 ---
  ['Write config.ts menciona {E}.web', 'Write', { file_path: 'app/server/config.ts', content: "const F = '{E}.web';" }, false],
  ['Edit CLAUDE.md new_string {CF}\\Programa', 'Edit', { file_path: 'CLAUDE.md', old_string: 'x', new_string: 'Ruta {CF}\\Programa prohibida' }, false],
  ['Write contenido {SR}', 'Write', { file_path: 'app/a.ts', content: 'clave {SR}' }, true],
  ['PowerShell cd {U}; dir logs', 'PowerShell', { command: 'cd {U}; dir logs' }, true],
  ['PowerShell npm run dev:real', 'PowerShell', { command: 'npm run dev:real' }, true],
  ['PowerShell npm run check:real', 'PowerShell', { command: 'npm run check:real' }, true],
  ['PowerShell npm run set-password', 'PowerShell', { command: 'npm run set-password' }, true],
  ['PowerShell npx playwright test', 'PowerShell', { command: 'npx playwright test' }, false],
  ['PowerShell dir {CF}\\Programa_web\\web\\app', 'PowerShell', { command: 'dir {CF}\\Programa_web\\web\\app' }, false],
  // --- extra ---
  ['Extra: Set-Location {U}', 'PowerShell', { command: 'Set-Location {U}' }, true],
  ['Extra: pushd {U}\\x', 'Bash', { command: 'pushd {U}\\x' }, true],
  ['Extra: --modo=REAL', 'PowerShell', { command: 'node server.js --modo=REAL' }, true],
  ['Extra: CF_MODO=REAL', 'Bash', { command: 'CF_MODO=REAL node server.js' }, true],
  ['Extra: iniciar_web.cmd', 'PowerShell', { command: '.\\app\\iniciar_web.cmd' }, true],
  ['Extra: dir {CF}\\Programa_web', 'PowerShell', { command: 'dir {CF}\\Programa_web' }, true],
  ['Extra: Glob raíz Programa_web **/*.log', 'Glob', { path: '{CF}\\Programa_web', pattern: '**/*.log' }, true],
  ['Extra: Read {U}/pruebas/auditoria_2bn/DISENO.md', 'Read', { file_path: '{U}/pruebas/auditoria_2bn/DISENO.md' }, false],
  ['Extra: git status', 'PowerShell', { command: 'git status --short' }, false],
];

let fallos = 0;
const fila = (a, b, c, d) => console.log(`${a.padEnd(48)} | ${b.padEnd(9)} | ${c.padEnd(9)} | ${d}`);
fila('caso', 'esperado', 'obtenido', 'ok');
for (const [nombre, tool, input, debeBloquear] of casos) {
  const r = spawnSync(process.execPath, [HOOK], {
    input: JSON.stringify({ hook_event_name: 'PreToolUse', tool_name: tool, tool_input: P(input) }),
    encoding: 'utf8',
  });
  const bloqueado = r.status === 2;
  const ok = bloqueado === debeBloquear && (r.status === 0 || r.status === 2);
  if (!ok) fallos++;
  fila(P(nombre), debeBloquear ? 'bloqueado' : 'permitido', bloqueado ? 'bloqueado' : `perm(${r.status})`, ok ? 'OK' : 'FALLO');
}
{
  const r = spawnSync(process.execPath, [HOOK], { input: '{no json', encoding: 'utf8' });
  const ok = r.status === 2;
  if (!ok) fallos++;
  fila('JSON ilegible', 'bloqueado', r.status === 2 ? 'bloqueado' : `perm(${r.status})`, ok ? 'OK' : 'FALLO');
}
console.log(`\n${casos.length + 1} casos. ` + (fallos === 0 ? 'TODOS OK' : `FALLOS: ${fallos}`));
process.exit(fallos === 0 ? 0 : 1);
