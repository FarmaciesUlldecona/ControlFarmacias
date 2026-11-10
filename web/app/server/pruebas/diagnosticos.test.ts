// H5-4: resumen del diagnóstico de casado con valores límite, y salvaguardas del SQL de diagnósticos (el error 22P02
// de H5-3: concatenar texto con una expresión jsonb). No conecta a nada. Uso: npm run test:unit
import assert from 'node:assert/strict';
import { describe, test } from 'node:test';
import {
  CONSULTAS, CONSULTAS_CHECK, ETIQUETAS_CLASE_NUMERO, ETIQUETAS_ESTADO_MATCHING, etiquetaDiagnostico, resumenCasado,
} from '../contrato.ts';
import { NOMBRES_DIAGNOSTICO, validarDiagnostico } from '../adaptador_real.ts';

const E = ETIQUETAS_ESTADO_MATCHING;

describe('etiquetaDiagnostico (mismo criterio que el CASE del SQL)', () => {
  const casos: [string | null, string][] = [
    [null, 'sin_valor'],
    ['', 'sin_valor'],
    ['MATCH_UNICO', 'match_unico'],
    ['match_unico', 'otros_no_codigo'], // minúsculas: no es código
    ['Match_Unico', 'otros_no_codigo'],
    ['ESTADO_NUEVO_1', 'no_previsto:ESTADO_NUEVO_1'],
    ['A'.repeat(40), `no_previsto:${'A'.repeat(40)}`],
    ['A'.repeat(41), 'otros_no_codigo'], // más de 40
    [' MATCH_UNICO', 'otros_no_codigo'], // espacio
    ['MATCH UNICO', 'otros_no_codigo'],
    ["O'REILLY", 'otros_no_codigo'], // comilla simple
    ['"MATCH"', 'otros_no_codigo'], // comillas dobles
    ['{"a":1}', 'otros_no_codigo'], // aspecto de JSON
    ['ÑANDU', 'otros_no_codigo'], // no ASCII
    ['X-1', 'otros_no_codigo'],
    ['X\nY', 'otros_no_codigo'],
    ['ESTADO\u0000', 'otros_no_codigo'],
    // H5-5: estados de la versión anterior del motor, ahora etiquetas fijas.
    ['EXACTO', 'exacto'],
    ['ECONOMICO_UNICO', 'economico_unico'],
    ['exacto', 'otros_no_codigo'],
    ['EXACTO ', 'otros_no_codigo'],
  ];
  for (const [v, esperado] of casos) {
    test(`${JSON.stringify(v)} → ${esperado}`, () => assert.equal(etiquetaDiagnostico(v, E), esperado));
  }
});

describe('resumenCasado', () => {
  const filas = (eje: string, valores: (string | null)[], etiquetas: readonly string[]) => {
    const m = new Map<string, number>();
    for (const v of valores) { const e = etiquetaDiagnostico(v, etiquetas); m.set(e, (m.get(e) ?? 0) + 1); }
    return [...m].map(([etiqueta, n]) => ({ eje, etiqueta, n: String(n) }));
  };

  test('cuenta etiquetas fijas, no previstos con forma de código y el resto sin mostrarlo', () => {
    const d = resumenCasado([
      ...filas('estado_matching', [null, '', 'MATCH_UNICO', 'MATCH_UNICO', 'match_unico', "O'X", 'NUEVO_1', 'NUEVO_1', '{"x":1}'], E),
      ...filas('clase_numero', ['EXACTA', 'CLASE_NUEVA', 'exacta', null], ETIQUETAS_CLASE_NUMERO),
    ]);
    assert.equal(d['estado_matching.sin_valor'], 2);
    assert.equal(d['estado_matching.match_unico'], 2);
    assert.equal(d['estado_matching.no_previsto.NUEVO_1'], 2);
    assert.equal(d['estado_matching.otros_no_codigo'], 3);
    assert.equal(d['clase_numero.exacta'], 1);
    assert.equal(d['clase_numero.no_previsto.CLASE_NUEVA'], 1);
    assert.equal(d['clase_numero.otros_no_codigo'], 1);
    assert.equal(d['clase_numero.sin_valor'], 1);
    // Todas las etiquetas fijas presentes con 0; ningún literal que no sea código en las claves.
    assert.equal(d['estado_matching.ambiguo_r17'], 0);
    for (const k of Object.keys(d)) assert.match(k, /^(clase_numero|estado_matching)\.(no_previsto\.[A-Z0-9_]{1,40}|[a-z0-9_]+)$/);
    assert.doesNotThrow(() => validarDiagnostico(d));
  });

  test('sin filas: todo a 0', () => {
    const d = resumenCasado([]);
    assert.ok(Object.values(d).every((n) => n === 0));
    assert.equal(d['estado_matching.otros_no_codigo'], 0);
  });

  test('falla cerrado ante etiquetas o recuentos que no encajan', () => {
    const malas = [
      { eje: 'estado_matching', etiqueta: 'MATCH_UNICO', n: '1' }, // literal sin pasar por la etiqueta
      { eje: 'estado_matching', etiqueta: 'no_previsto:valor raro', n: '1' },
      { eje: 'estado_matching', etiqueta: "no_previsto:O'X", n: '1' },
      { eje: 'estado_matching', etiqueta: `no_previsto:${'A'.repeat(41)}`, n: '1' },
      { eje: 'estado_matching', etiqueta: 'no_previsto:', n: '1' },
      { eje: 'estado_matching', etiqueta: 'no_previsto:MATCH_UNICO', n: '1' }, // etiqueta fija disfrazada
      { eje: 'otro_eje', etiqueta: 'sin_valor', n: '1' },
      { eje: 'estado_matching', etiqueta: null, n: '1' },
      { eje: 'estado_matching', etiqueta: 'sin_valor', n: '-1' },
      { eje: 'estado_matching', etiqueta: 'sin_valor', n: '1.5' },
      { eje: 'estado_matching', etiqueta: 'sin_valor', n: null },
    ];
    for (const f of malas) assert.throws(() => resumenCasado([f]), Error, JSON.stringify(f));
  });
});

describe('SQL de diagnósticos (salvaguardas del 22P02 de H5-3)', () => {
  const todas = { ...CONSULTAS, ...CONSULTAS_CHECK };

  test('ninguna consulta concatena (||) en la misma línea que un operador jsonb (-> ->> #> #>>)', () => {
    for (const [n, c] of Object.entries(todas)) {
      for (const l of c.sql.split('\n')) assert.ok(!(l.includes('||') && /->|#>/.test(l)), `${n}: ${l.trim()}`);
    }
  });

  test('casado: el valor se extrae como text en un CTE y la etiqueta se construye solo con texto', () => {
    const sql = CONSULTAS_CHECK.diagnostico_casado.sql;
    assert.match(sql, /\(cd\.provenance ->> 'clase_numero'\)::text as clase_raw/);
    assert.match(sql, /\(cd\.provenance ->> 'estado_matching'\)::text as estado_raw/);
    assert.match(sql, /'no_previsto:'::text \|\| v\.clase_raw/);
    assert.match(sql, /v\.estado_raw ~ '\^\[A-Z0-9_\]\{1,40\}\$'/);
    assert.ok(!/::jsonb?\b/.test(sql), 'sin conversiones a json');
    // El patrón se aplica antes de agregar: el CASE vive en el CTE l, el group by después.
    assert.ok(sql.indexOf("~ '^[A-Z0-9_]{1,40}$'") < sql.indexOf('group by'));
  });

  test('solo conversiones a json de literales JSON válidos', () => {
    for (const [n, c] of Object.entries(todas)) {
      for (const m of c.sql.matchAll(/'([^']*)'::jsonb?/g)) assert.doesNotThrow(() => JSON.parse(m[1]), `${n}: '${m[1]}'`);
    }
  });

  test('cada diagnóstico tiene nombre propio (una línea y una transacción por diagnóstico)', () => {
    assert.deepEqual([...NOMBRES_DIAGNOSTICO], ['vencimientos', 'documentos', 'tipo_documento', 'sentido', 'casado', 'duplicados', 'par_08C66676']);
  });
});
