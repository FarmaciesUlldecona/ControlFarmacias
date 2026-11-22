// H8: pantalla Conciliación (doble comprobación). Marcas, orden por dinero en riesgo, con/sin lector y antigüedad. Puro.
import assert from 'node:assert/strict';
import { describe, test } from 'node:test';
import {
  BANCO_SIN_DATOS, CLASE_DETALLE_SIN_FACTURA, COLUMNA_DIAGNOSTICO_GRUPO, CONSULTAS, CONSULTAS_CHECK, CONSULTAS_POR_BLOQUE, DIAS_ALERTA_SIN_FACTURA, GRUPOS_SIN_FACTURA,
  LIMITE_DETALLE_ALERTA, TRASPASOS_ENTRE_FARMACIAS, claveLiteralFarmatic, construirSinFactura, diasEntre, idProveedorLector,
  literalFarmaticSinPrefijo, nombreProveedorFarmatic,
  type FacturaBandeja, type FacturaResumen, type Fila, type GrupoSinFactura,
} from '../contrato.ts';
import {
  bandejaAlbaranes, coberturaProveedores, compararRiesgo, cumpleFiltrosDoble, enlaceVencimiento, marcaAlbaranes, marcaBanco, motivoBandeja, resumenDoble,
} from '../conciliacion.ts';
import { COLUMNAS_SIN_FACTURA, ErrorRecuentosIncoherentes, NOMBRES_DIAGNOSTICO, resumenSinFactura } from '../adaptador_real.ts';

// ---------------------------------------------------------------------------
// H8-3: base simulada de «Sin factura». Réplica en TS del `case` de g (mismo orden de ramas) y de la agregación de la
// consulta albaranes_sin_factura; el test de SQL comprueba que el orden de ramas del SQL es ORDEN_CASE.
// ---------------------------------------------------------------------------
const HOY_SIM = '2026-11-02';
/** Proveedores con facturas leídas y su `desde` (por sus facturas). */
const LECT_SIM = new Map([['1', '2026-08-01'], ['4', '2026-09-20']]);
/**
 * H8-4: proveedores con conciliación automática y su `desde` = albarán reservado más antiguo (5: ninguno con fecha; 6: sin
 * facturas leídas con su id, como SAFA en REAL, pero con reservas: ya no es «sin fecha de inicio»).
 */
const AUTO_SIM = new Map<string, string | null>([['1', '2026-08-01'], ['5', null], ['6', '2026-09-01']]);
const ORDEN_CASE: GrupoSinFactura[] = ['AUSENTE', 'TRASPASO', 'SIN_PROVEEDOR', 'AUTO_SIN_DESDE', 'AUTO_ANTERIOR', 'AUTO_ALERTA', 'AUTO_RECIENTE',
  'LEIDO_ANTERIOR', 'LEIDO', 'SIN_LECTOR'];
interface AlbSim { id: number; idp: string | null; fecha: string | null; importe: number | null; ausente: boolean; literal?: string }
function grupoSim(a: AlbSim): GrupoSinFactura {
  const desde = a.idp === null ? undefined : LECT_SIM.get(a.idp);
  const auto = a.idp !== null && AUTO_SIM.has(a.idp);
  const desdeAuto = a.idp === null ? null : AUTO_SIM.get(a.idp) ?? null;
  if (a.ausente) return 'AUSENTE';
  if (claveLiteralFarmatic(a.literal ?? null) === 'FFARMACIARITA') return 'TRASPASO';
  if (a.idp === null) return 'SIN_PROVEEDOR';
  if (auto && desdeAuto === null) return 'AUTO_SIN_DESDE';
  if (auto && (a.fecha === null || a.fecha < desdeAuto!)) return 'AUTO_ANTERIOR';
  if (auto && diasEntre(a.fecha!, HOY_SIM) > DIAS_ALERTA_SIN_FACTURA) return 'AUTO_ALERTA'; // = fecha < current_date - 30
  if (auto) return 'AUTO_RECIENTE';
  if (desde !== undefined && (a.fecha === null || a.fecha < desde)) return 'LEIDO_ANTERIOR';
  if (desde !== undefined) return 'LEIDO';
  return 'SIN_LECTOR';
}
const fechaMas = (base: string, d: number) => new Date(Date.parse(`${base}T00:00:00Z`) + d * 86_400_000).toISOString().slice(0, 10);
/** 140 albaranes: 110 de Cofares en alerta (10 € cada uno), y de todos los demás grupos. */
const BASE_SIMULADA: AlbSim[] = (() => {
  const xs: AlbSim[] = [];
  let id = 1;
  const add = (k: number, idp: string | null, fecha: string | null, importe: number | null, ausente = false, literal?: string) => {
    for (let i = 0; i < k; i += 1) xs.push({ id: id++, idp, fecha: typeof fecha === 'string' ? fechaMas(fecha, i % 60) : null, importe, ausente, literal });
  };
  add(110, '1', '2026-08-02', 10);             // alerta (02/08 a 30/09)
  add(3, '1', '2026-10-25', 5);                // en plazo
  add(1, '1', '2026-07-15', 7);                // anterior a lo leído
  add(1, '1', null, null);                     // sin fecha: anterior
  add(4, '5', '2026-08-10', 3);                // conciliación automática sin facturas leídas: sin desde
  add(2, '4', '2026-10-10', 20);               // leído sin conciliación
  add(1, '4', '2026-09-01', 9);                // leído, anterior
  add(3, '37', '2026-09-01', null);            // sin lector
  add(2, null, '2026-09-01', 4);               // sin proveedor
  add(3, '1', '2026-08-15', 11, true);         // ausentes (también de Cofares, con edad de alerta)
  add(5, '6', '2026-08-20', 2, false, '1.- SAFA'); // H8-4: con reservas, sin facturas leídas con su id: anteriores a su desde
  add(4, '40', '2026-09-01', 50, false, '4.- FFARMACIA RITA'); // H8-4: traspaso entre farmacias
  add(1, null, '2026-09-01', 50, false, '4.- FFARMACIA RITA'); // traspaso aunque falte el id
  return xs;
})();
function simularConsulta(base: AlbSim[]): Fila[] {
  const grupos = new Map<string, AlbSim[]>();
  for (const a of base) {
    const k = `${grupoSim(a)}|${a.idp ?? ''}`;
    grupos.set(k, [...(grupos.get(k) ?? []), a]);
  }
  const resumen = (xs: AlbSim[]) => {
    const imps = xs.map((x) => x.importe).filter((x): x is number => x !== null);
    return { albaranes: String(xs.length), importe: imps.length ? String(imps.reduce((s, x) => s + x, 0)) : null,
      sin_importe: String(xs.filter((x) => x.importe === null).length) };
  };
  const out: Fila[] = [];
  for (const [k, xs] of grupos) {
    const [g, idp] = k.split('|');
    const fechas = xs.map((x) => x.fecha).filter((x): x is string => x !== null).sort();
    const desde = g.startsWith('AUTO_') ? AUTO_SIM.get(idp) ?? null : LECT_SIM.get(idp) ?? null;
    out.push(fila(g, idp || null, { ...resumen(xs), proveedor: xs[0].literal ?? null, fecha: fechas.at(-1) ?? null, desde }));
    // H8-5: detalle de todos los grupos con desplegable (orden: fecha, los sin fecha al final; luego id).
    const claseDetalle = (CLASE_DETALLE_SIN_FACTURA as Partial<Record<string, string>>)[g];
    if (claseDetalle !== undefined) {
      const det = [...xs].sort((a, b) => (a.fecha === null ? 1 : 0) - (b.fecha === null ? 1 : 0) || (a.fecha ?? '').localeCompare(b.fecha ?? '') || a.id - b.id)
        .slice(0, LIMITE_DETALLE_ALERTA);
      for (const d of det) out.push(fila(claseDetalle, idp || null, { id_contador: String(d.id), numero_albaran: `S${d.id}`, fecha: d.fecha,
        importe: d.importe === null ? null : String(d.importe), sin_importe: d.importe === null ? '1' : '0' }));
    }
  }
  out.push(fila('TOTAL', null, resumen(base)));
  return out;
}

let n = 0;
function fb(extra: Partial<FacturaBandeja> & { resultado?: string | null; diferencia?: number | null; venc?: string | null }): FacturaBandeja {
  n += 1;
  const { resultado = null, diferencia = null, venc = null, ...resto } = extra;
  return {
    factura_id: `f-${n}`, numero_factura: `N-${n}`, importe_total: 100, estado_conciliacion_cf: 'PENDIENTE_CONCILIAR',
    conciliacion: resultado === null && diferencia === null ? null : { resultado, diferencia } as FacturaBandeja['conciliacion'],
    lineas: [], proveedor_grupo: 'cif:A1', proveedor_etiqueta: 'ALFA', proveedor_comercial: 'Alfa', proveedor_razon_social: null, proveedor: 'ALFA',
    vencimiento_proximo: venc === null ? null : { fecha_vencimiento: venc } as FacturaBandeja['vencimiento_proximo'], vencimiento_vencido: false,
    banco: BANCO_SIN_DATOS, ...resto,
  } as FacturaBandeja;
}

describe('H8: marca 1 (albaranes ↔ factura)', () => {
  test('✓ conciliada con la diferencia del motor tal cual | ✗ con diferencia | ○ pendiente | ! en revisión', () => {
    const c = marcaAlbaranes(fb({ estado_conciliacion_cf: 'CONCILIADA', resultado: 'CONCILIADA', diferencia: 0.07 }));
    assert.deepEqual([c.clave, c.simbolo, c.color, c.diferencia_motor], ['CONCILIADA', '✓', 'verde', 0.07]);
    const d = marcaAlbaranes(fb({ resultado: 'DIFERENCIA', diferencia: 41.9 }));
    assert.deepEqual([d.clave, d.simbolo, d.texto, d.color, d.diferencia_motor], ['DIFERENCIA', '✗', 'con diferencia', 'rojo', 41.9]);
    const p = marcaAlbaranes(fb({}));
    assert.deepEqual([p.clave, p.simbolo, p.color], ['PENDIENTE', '○', 'azul']);
    const r = marcaAlbaranes(fb({ estado_conciliacion_cf: 'REVISION_CONCILIACION', resultado: 'DIFERENCIA', diferencia: 3 }));
    assert.deepEqual([r.clave, r.simbolo, r.color], ['REVISION', '!', 'naranja']);
  });
  test('NO_EVALUABLE: ✗ «no se puede comprobar», sin cifra de diferencia; estado desconocido: gris con el literal', () => {
    const x = marcaAlbaranes(fb({ resultado: 'NO_EVALUABLE', diferencia: 5 }));
    assert.equal(x.clave, 'DIFERENCIA');
    assert.equal(x.texto, 'no se puede comprobar');
    assert.equal(x.diferencia_motor, null);
    const o = marcaAlbaranes(fb({ estado_conciliacion_cf: 'ESTADO_RARO' }));
    assert.deepEqual([o.clave, o.color, o.texto], ['OTRO', 'gris', 'ESTADO_RARO']);
  });
  test('una diferencia null nunca se convierte en 0', () => {
    assert.equal(marcaAlbaranes(fb({ estado_conciliacion_cf: 'CONCILIADA', resultado: 'CONCILIADA', diferencia: null })).diferencia_motor, null);
  });
});

describe('H8: marca 2 (banco ↔ pago) y resumen en euros', () => {
  test('hoy siempre «○ sin datos bancarios» (gris); el contrato reserva «✓ pagado (banco)»', () => {
    assert.deepEqual(marcaBanco(BANCO_SIN_DATOS), { clave: 'SIN_DATOS_BANCARIOS', simbolo: '○', texto: 'sin datos bancarios', color: 'gris' });
    assert.equal(marcaBanco({ estado: 'PAGADO_BANCO', texto: '', color: 'verde', fecha_pago: '2026-11-10' }).texto, 'pagado (banco)');
  });
  test('verificado doble (hoy 0) / solo albaranes / ninguna; sin importe fuera con recuento', () => {
    const r = resumenDoble([
      fb({ estado_conciliacion_cf: 'CONCILIADA', resultado: 'CONCILIADA', importe_total: 100.1 }),
      fb({ estado_conciliacion_cf: 'CONCILIADA', resultado: 'CONCILIADA', importe_total: null }),
      fb({ importe_total: 50 }),
      fb({ estado_conciliacion_cf: 'CONCILIADA', resultado: 'CONCILIADA', importe_total: 20, banco: { estado: 'PAGADO_BANCO', texto: '', color: 'verde', fecha_pago: null } }),
    ]);
    assert.deepEqual(r.verificado_doble, { facturas: 1, importe: 20 });
    assert.deepEqual(r.solo_albaranes, { facturas: 1, importe: 100.1 });
    assert.deepEqual(r.ninguna, { facturas: 1, importe: 50 });
    assert.equal(r.sin_importe, 1);
    assert.deepEqual(resumenDoble([]).verificado_doble, { facturas: 0, importe: null });
  });
});

describe('H8: orden por dinero en riesgo y bandeja por proveedor → motivo', () => {
  test('vencimiento más próximo primero (sin fecha al final), luego importe mayor (sin importe al final)', () => {
    const a = fb({ venc: '2026-11-20', importe_total: 10 });
    const b = fb({ venc: '2026-11-05', importe_total: 5 });
    const c = fb({ venc: '2026-11-20', importe_total: 900 });
    const d = fb({ venc: null, importe_total: 5000 });
    const e = fb({ venc: '2026-11-20', importe_total: null });
    assert.deepEqual([a, b, c, d, e].sort(compararRiesgo).map((x) => x.factura_id), [b.factura_id, c.factura_id, a.factura_id, e.factura_id, d.factura_id]);
  });
  test('motivo con el texto del diccionario: revisión > albarán no localizado > diferencia > no evaluable > pendiente', () => {
    const sin = { tipo_relacion: 'SIN_COINCIDENCIA', estado_matching: 'SIN_COINCIDENCIA', clase_numero: null, coincidencia_numero: null, sentido_documental: 'CARGO' };
    assert.equal(motivoBandeja(fb({ estado_conciliacion_cf: 'REVISION_CONCILIACION', lineas: [sin] as FacturaBandeja['lineas'] })), 'REVISION');
    assert.equal(motivoBandeja(fb({ resultado: 'DIFERENCIA', lineas: [sin] as FacturaBandeja['lineas'] })), 'NO_LOCALIZADO');
    assert.equal(motivoBandeja(fb({ resultado: 'DIFERENCIA' })), 'DIFERENCIA');
    assert.equal(motivoBandeja(fb({ resultado: 'NO_EVALUABLE' })), 'NO_EVALUABLE');
    assert.equal(motivoBandeja(fb({})), 'PENDIENTE');
  });
  test('sin las conciliadas; proveedores en el orden de su factura de más riesgo', () => {
    const x1 = fb({ proveedor_grupo: 'cif:B', venc: '2026-11-30' });
    const x2 = fb({ proveedor_grupo: 'cif:A', venc: '2026-11-10' });
    const x3 = fb({ proveedor_grupo: 'cif:B', venc: '2026-11-03', resultado: 'DIFERENCIA' });
    const ok = fb({ proveedor_grupo: 'cif:C', estado_conciliacion_cf: 'CONCILIADA', venc: '2026-11-01' });
    const g = bandejaAlbaranes([x1, x2, x3, ok]);
    assert.deepEqual(g.map((y) => y.proveedor_grupo), ['cif:B', 'cif:A']);
    assert.deepEqual(g[0].motivos.map((m) => m.clave), ['DIFERENCIA', 'PENDIENTE']);
    assert.equal(g[0].importe, 200);
    assert.equal(enlaceVencimiento('2026-11-03'), '/vencimientos?vista=dia&fecha=2026-11-03');
  });
  test('filtros de «Doble comprobación»: proveedor, estado (marca o «noche») y búsqueda por nº, nombre o importe', () => {
    const a = fb({ numero_factura: 'AL-26-1', proveedor_comercial: 'Alliance', importe_total: 472.22, estado_conciliacion_cf: 'CONCILIADA', resultado: 'CONCILIADA' });
    const vacio = { proveedor: '', estado: '', q: '' };
    assert.ok(cumpleFiltrosDoble(a, { ...vacio, q: 'allian' }, new Set()));
    assert.ok(cumpleFiltrosDoble(a, { ...vacio, q: '472,22' }, new Set()));
    assert.ok(!cumpleFiltrosDoble(a, { ...vacio, estado: 'PENDIENTE' }, new Set()));
    assert.ok(cumpleFiltrosDoble(a, { ...vacio, estado: 'noche' }, new Set([a.factura_id])));
    assert.ok(!cumpleFiltrosDoble(a, { ...vacio, proveedor: 'cif:OTRO' }, new Set()));
  });
});

const fact = (id_proveedor_albaranes: string, comercial: string) => ({ factura_id: 'x', id_proveedor_albaranes, proveedor_cif: null,
  proveedor_nif_documental: null, proveedor_literal: comercial, proveedor: comercial }) as unknown as FacturaResumen;
const fila = (clase: string, idp: string | null, extra: Fila = {}): Fila => ({ clase, idp, id_contador: null, numero_albaran: null, proveedor: null,
  fecha: null, importe: null, albaranes: '1', sin_importe: '0', desde: null, ...extra });
/** H8-5: n filas de detalle (fechas de `fechas`, en ese orden; null = sin fecha). */
let idDetalle = 9000;
const detalles = (clase: string, idp: string | null, fechas: (string | null)[]): Fila[] =>
  fechas.map((f) => fila(clase, idp, { id_contador: String(idDetalle += 1), numero_albaran: `D${idDetalle}`, fecha: f, importe: '1' }));

describe('H8: Sin factura (con / sin lector y antigüedad)', () => {
  test('lector: id R9 y ECO360 (154) = Alliance (2), igual en SQL', () => {
    assert.equal(idProveedorLector('0002'), '2');
    assert.equal(idProveedorLector('154'), '2');
    assert.equal(idProveedorLector(' 0563 '), '563');
    assert.equal(idProveedorLector(null), null);
    assert.match(CONSULTAS.albaranes_sin_factura.sql, /= '154' then '2'/);
  });
  test('antigüedad en días (UTC) y plazo de 30 días en un único punto', () => {
    assert.equal(diasEntre('2026-10-03', '2026-11-02'), 30);
    assert.equal(diasEntre('2026-03-28', '2026-03-30'), 2); // cambio de hora: sigue siendo 2
    assert.equal(DIAS_ALERTA_SIN_FACTURA, 30);
    assert.match(CONSULTAS_CHECK.diagnostico_sin_factura.sql, /current_date - 30\b/);
  });
  test('con conciliación automática: alerta con detalle; recientes, anteriores y sin fecha de inicio sin alerta; importe null nunca 0', () => {
    const sf = construirSinFactura([
      fila('AUTO_ALERTA', '2', { albaranes: '2', importe: '10.5', sin_importe: '1', desde: '2026-09-01' }),
      fila('DETALLE_ALERTA', '2', { id_contador: '1', numero_albaran: 'A', fecha: '2026-10-02', importe: '10.5', desde: '2026-09-01' }),
      fila('DETALLE_ALERTA', '2', { id_contador: '3', numero_albaran: 'C', fecha: '2026-09-02', importe: null, sin_importe: '1', desde: '2026-09-01' }),
      fila('AUTO_RECIENTE', '2', { importe: '7', desde: '2026-09-01' }),
      fila('AUTO_ANTERIOR', '2', { albaranes: '40', importe: '999', sin_importe: '2', desde: '2026-09-01' }),
      fila('AUTO_SIN_DESDE', '9', { proveedor: 'HEFAME', albaranes: '3', importe: '12' }),
      ...detalles('DETALLE_SIN_DESDE', '9', [null, '2026-10-20', '2026-09-01']),
      fila('TOTAL', null, { albaranes: '46', importe: '1028.5', sin_importe: '3' }),
    ], [fact('0002', 'ALLIANCE')], '2026-11-02');
    // H8-5: detalle de los «sin poder comprobar», del más antiguo al más reciente y los sin fecha al final.
    assert.deepEqual(sf.con_lector.find((x) => x.clave === '9')!.detalle_sin_desde.map((a) => a.dias), [62, 13, null]);
    const p = sf.con_lector.find((x) => x.clave === '2')!;
    assert.deepEqual(p.alertas.map((a) => [a.numero_albaran, a.dias, a.importe]), [['C', 61, null], ['A', 31, 10.5]]);
    assert.equal(p.alertas_total, 2);
    assert.equal(p.importe_alertas, 10.5);
    assert.equal(p.alertas_sin_importe, 1);
    assert.deepEqual(p.recientes, { albaranes: 1, importe: 7, sin_importe: 0 });
    assert.deepEqual(p.anteriores, { albaranes: 40, importe: 999, sin_importe: 2 });
    assert.deepEqual(sf.con_lector.find((x) => x.clave === '9')!.sin_desde, { albaranes: 3, importe: 12, sin_importe: 0 });
    assert.equal(sf.totales.alertas, 2);
    assert.deepEqual(sf.total, { albaranes: 46, importe: 1028.5, sin_importe: 3 });
  });
  test('sin lector: gris, por importe; sin proveedor comparable: «Proveedor sin identificar», nunca alerta', () => {
    const sf = construirSinFactura([
      fila('SIN_LECTOR', '37', { proveedor: 'ISDIN', importe: '50', albaranes: '3' }),
      fila('SIN_PROVEEDOR', null, { proveedor: 'X', importe: '900', albaranes: '2' }),
      fila('SIN_LECTOR', '88', { proveedor: 'BETA', importe: null, albaranes: '1', sin_importe: '1' }),
      ...detalles('DETALLE_SIN_LECTOR', '37', ['2026-10-01', '2026-09-01', '2026-10-30']),
      ...detalles('DETALLE_SIN_PROVEEDOR', null, ['2026-10-01', '2026-10-02']),
      ...detalles('DETALLE_SIN_LECTOR', '88', ['2026-10-01']),
      fila('TOTAL', null, { albaranes: '6', importe: '950', sin_importe: '1' }),
    ], [], '2026-11-02');
    assert.deepEqual(sf.sin_lector.map((s) => s.detalle.map((a) => a.dias)), [[32, 31], [62, 32, 3], [32]]);
    assert.deepEqual(sf.sin_lector.map((s) => [s.proveedor, s.identificado]), [['Proveedor sin identificar', false], ['ISDIN', true], ['BETA', true]]);
    assert.equal(sf.con_lector.length, 0);
    assert.deepEqual(sf.totales.sin_lector, { albaranes: 6, importe: 950, sin_importe: 1 });
  });
  test('H8-2: leído sin conciliación automática: gris propio por proveedor (y sus anteriores), nunca alerta; ausentes: solo recuento', () => {
    const sf = construirSinFactura([
      fila('LEIDO', '4', { proveedor: 'FEDEFARMA', albaranes: '3', importe: '455', desde: '2026-09-20', fecha: '2026-10-29' }),
      fila('LEIDO_ANTERIOR', '4', { proveedor: 'FEDEFARMA', albaranes: '6', importe: '512.8', desde: '2026-09-20', fecha: '2026-09-18' }),
      fila('LEIDO', '9', { proveedor: 'OTRO', albaranes: '1', importe: null, sin_importe: '1' }),
      ...detalles('DETALLE_LEIDO', '4', ['2026-10-29', '2026-09-25', '2026-10-12']),
      ...detalles('DETALLE_LEIDO', '9', ['2026-10-01']),
      fila('AUSENTE', null, { albaranes: '1', importe: '100' }),
      fila('AUSENTE', '37', { albaranes: '1', importe: '30.5' }),
      fila('TOTAL', null, { albaranes: '12', importe: '1098.3', sin_importe: '1' }),
    ], [fact('0004', 'FEDEFARMA')], '2026-11-02');
    assert.equal(sf.con_lector.length, 0);
    assert.equal(sf.totales.alertas, 0);
    assert.deepEqual(sf.leido_sin_conciliacion.map((p) => [p.clave, p.proveedor, p.albaranes, p.importe, p.desde, p.anteriores.albaranes]),
      [['4', 'FEDEFARMA', 3, 455, '2026-09-20', 6], ['9', 'OTRO', 1, null, null, 0]]);
    assert.deepEqual(sf.totales.leido_sin_conciliacion, { albaranes: 4, importe: 455, sin_importe: 1 });
    assert.deepEqual(sf.excluidos_ausentes, { albaranes: 2, importe: 130.5, sin_importe: 0 });
  });
  test('H8-3 SQL: un único case exhaustivo (con else) que asigna los grupos; agregado por proveedor, sin depender de un límite', () => {
    const sql = CONSULTAS.albaranes_sin_factura.sql;
    // El case de grupos de g (hasta su else); el case de las clases de detalle (H8-5) va después, en el select.
    const hastaElse = sql.slice(0, sql.indexOf("else 'SIN_LECTOR'"));
    const enCase = [...hastaElse.matchAll(/then '([A-Z_]+)'/g)].map((m) => m[1]).filter((c) => !c.startsWith('DETALLE_'));
    assert.deepEqual(enCase, ORDEN_CASE.slice(0, -1));
    assert.match(sql, /else 'SIN_LECTOR'\s+end::text as grupo/);
    assert.deepEqual([...ORDEN_CASE].sort(), [...GRUPOS_SIN_FACTURA].sort());
    assert.match(sql, /group by g\.grupo, g\.idp/);
    assert.match(sql, /'TOTAL'[\s\S]*from a0/);
    assert.match(sql, new RegExp(`orden_detalle <= ${LIMITE_DETALLE_ALERTA}\\b`));
    // H8-5: detalle por (grupo, proveedor) en todos los grupos con desplegable, los más antiguos primero y los sin fecha al final.
    assert.match(sql, /partition by g\.grupo, g\.idp order by g\.fecha nulls last, g\.id_contador/);
    assert.match(sql, /g\.grupo in \('AUTO_ALERTA', 'AUTO_SIN_DESDE', 'LEIDO', 'SIN_LECTOR', 'SIN_PROVEEDOR', 'TRASPASO'\)/);
    for (const [g, c] of Object.entries(CLASE_DETALLE_SIN_FACTURA)) assert.match(sql, new RegExp(`when '${g}' then '${c}'`));
    // Ningún límite de filas fuera del detalle de alertas.
    assert.doesNotMatch(sql, /\blimit\b/i);
    // lect y auto, una fila por idp: los left join no duplican albaranes.
    assert.match(sql, /group by 1\n\)/);
    // H8-4: auto, una fila por idp con su desde = albarán reservado más antiguo.
    assert.match(sql, /auto as \(\s+select \(case[\s\S]*?as idp, min\(ar\.fecha\)::date as desde[\s\S]*?group by 1\n\)/);
    assert.match(sql, /when u\.idp is not null and u\.desde is null then 'AUTO_SIN_DESDE'/);
    assert.match(sql, /a0\.fecha < u\.desde\) then 'AUTO_ANTERIOR'/);
    assert.match(sql, /in \('FFARMACIARITA'\) then 'TRASPASO'/);
    assert.match(sql, /c\.campo = 'presencia'/);
    assert.match(sql, /order by c\.id_contador, c\.id desc/);
    assert.match(sql, /u\.valor_nuevo = 'AUSENTE'/);
    assert.ok(CONSULTAS.albaranes_sin_factura.objetos.includes('albaranes_cambios'));
    // El diagnóstico usa el mismo case (mismo CTE) y cuenta el total aparte, sobre a0.
    const diag = CONSULTAS_CHECK.diagnostico_sin_factura.sql;
    assert.match(diag, /\(select count\(\*\) from a0\) as total/);
    for (const g of GRUPOS_SIN_FACTURA) assert.match(diag, new RegExp(`g\\.grupo = '${g}'\\) as ${COLUMNA_DIAGNOSTICO_GRUPO[g]}\\b`));
  });
  test('H8-3/H8-4: base simulada de 140 albaranes (más de 50): los grupos son excluyentes, suman el total y el detalle se limita sin tocar los recuentos', () => {
    const sf = construirSinFactura(simularConsulta(BASE_SIMULADA), [fact('0001', 'COFARES')], HOY_SIM);
    assert.ok(BASE_SIMULADA.length > 50);
    const suma = GRUPOS_SIN_FACTURA.reduce((a, g) => a + sf.grupos[g].albaranes, 0);
    assert.equal(sf.total.albaranes, BASE_SIMULADA.length);
    assert.equal(suma, sf.total.albaranes);
    const cof = sf.con_lector.find((p) => p.clave === '1')!;
    assert.equal(cof.alertas_total, 110);
    assert.equal(cof.alertas.length, LIMITE_DETALLE_ALERTA);
    assert.equal(sf.totales.alertas, 110);
    assert.equal(sf.totales.importe_alertas, 110 * 10);
    // H8-4: sin fecha de inicio solo si ningún albarán reservado tiene fecha (5); SAFA (6) sin facturas leídas con su id
    // ya tiene fecha de inicio por sus reservas: sus albaranes anteriores no son «sin poder comprobar».
    assert.deepEqual(sf.con_lector.find((p) => p.clave === '5')!.sin_desde.albaranes, 4);
    const safa = sf.con_lector.find((p) => p.clave === '6')!;
    assert.deepEqual([safa.proveedor, safa.desde, safa.anteriores.albaranes, safa.sin_desde.albaranes], ['ALLIANCE', '2026-09-01', 5, 0]);
    assert.equal(sf.grupos.AUTO_SIN_DESDE.albaranes, 4);
    assert.equal(sf.grupos.AUTO_RECIENTE.albaranes, 3);
    assert.equal(sf.grupos.AUTO_ANTERIOR.albaranes, 7);
    assert.equal(sf.grupos.LEIDO.albaranes, 2);
    assert.equal(sf.grupos.LEIDO_ANTERIOR.albaranes, 1);
    assert.equal(sf.grupos.SIN_LECTOR.albaranes, 3);
    assert.equal(sf.grupos.SIN_PROVEEDOR.albaranes, 2);
    assert.equal(sf.grupos.TRASPASO.albaranes, 5);
    assert.equal(sf.grupos.AUSENTE.albaranes, 3);
    // Traspasos: aparte, nunca en «pendiente de automatizar» (también el que no trae id).
    assert.deepEqual(sf.traspasos.map((t) => [t.clave, t.farmacia_origen, t.proveedor, t.albaranes]), [['40', 'RITA', 'FFARMACIA RITA', 4], [null, 'RITA', 'FFARMACIA RITA', 1]]);
    assert.ok(!sf.sin_lector.some((s) => s.clave === '40' || /RITA/.test(s.proveedor)));
  });
  test('H8-4: nombres de Farmatic: comercial por las equivalencias, si no el literal sin el prefijo numérico', () => {
    assert.equal(literalFarmaticSinPrefijo('1.- SAFA'), 'SAFA');
    assert.equal(literalFarmaticSinPrefijo(' 7.- LOGISTAPHARMA '), 'LOGISTAPHARMA');
    assert.equal(literalFarmaticSinPrefijo('LABORATORIOS 3M'), 'LABORATORIOS 3M');
    assert.equal(nombreProveedorFarmatic('1.- SAFA'), 'ALLIANCE');
    assert.equal(nombreProveedorFarmatic('3.- HEFAME'), 'HEFAME');
    assert.equal(nombreProveedorFarmatic('7.- LOGISTAPHARMA'), 'LOGISTAPHARMA');
    assert.equal(nombreProveedorFarmatic(null), null);
    assert.equal(claveLiteralFarmatic('4.- FFARMACIA RITA'), 'FFARMACIARITA');
    assert.equal(claveLiteralFarmatic('  4 .- ffarmacia  rita'), 'FFARMACIARITA');
    assert.deepEqual(TRASPASOS_ENTRE_FARMACIAS.map((t) => t.farmacia), ['RITA']);
  });
  test('H8-4: traspaso con un literal que no está en la configuración: falla cerrado', () => {
    assert.throws(() => construirSinFactura([fila('TRASPASO', '41', { proveedor: 'OTRA FARMACIA' }), fila('TRASPASO', null), fila('TOTAL', null, { albaranes: '2' })], [], HOY_SIM),
      /SIN_FACTURA_TRASPASO_NO_CONFIGURADO/);
  });
  test('H8-3: falla cerrado si los grupos no suman el total, si falta el total o si el detalle no cuadra', () => {
    const filas = simularConsulta(BASE_SIMULADA);
    const sinTotal = filas.filter((f) => f.clase !== 'TOTAL');
    assert.throws(() => construirSinFactura(sinTotal, [], HOY_SIM), /SIN_FACTURA_SIN_TOTAL/);
    const totalMal = filas.map((f) => (f.clase === 'TOTAL' ? { ...f, albaranes: String(BASE_SIMULADA.length + 1) } : f));
    assert.throws(() => construirSinFactura(totalMal, [], HOY_SIM), /SIN_FACTURA_GRUPOS_NO_CUADRAN: total=141 suma_grupos=140/);
    const sinUnDetalle = filas.filter((f, i) => !(f.clase === 'DETALLE_ALERTA' && i === filas.findIndex((x) => x.clase === 'DETALLE_ALERTA')));
    assert.throws(() => construirSinFactura(sinUnDetalle, [], HOY_SIM), /SIN_FACTURA_DETALLE_NO_CUADRA/);
    assert.throws(() => construirSinFactura([fila('LEIDO', null), fila('TOTAL', null)], [], HOY_SIM), /sin proveedor/);
  });
  test('fila desconocida: falla cerrado', () => {
    assert.throws(() => construirSinFactura([fila('RARA', '1')], [], '2026-11-02'), /SIN_FACTURA_FILA_NO_RECONOCIDA/);
    // Las clases de H8/H8-2 ya no existen.
    assert.throws(() => construirSinFactura([fila('CON_LECTOR', '1')], [], '2026-11-02'), /SIN_FACTURA_FILA_NO_RECONOCIDA/);
  });
  test('consulta: solo albaranes de PIO no reservados por una conciliación vigente; la carga Conciliación', () => {
    const sql = CONSULTAS.albaranes_sin_factura.sql;
    assert.match(sql, /c\.es_actual/);
    assert.match(sql, /a\.farmacia = \$1/);
    assert.match(sql, /not exists \(select 1 from res where res\.id_contador = a\.id_contador\)/);
    assert.ok(CONSULTAS_POR_BLOQUE.conciliacionBandeja.includes('albaranes_sin_factura'));
    assert.ok(CONSULTAS_POR_BLOQUE.conciliacionBandeja.includes('vencimientos'));
  });
  test('check:real: diagnóstico sin_factura, solo recuentos; los grupos suman el total; si no, el error lleva los recuentos', () => {
    assert.ok(NOMBRES_DIAGNOSTICO.includes('sin_factura'));
    const ok = { total: '32', con_conciliacion_alerta: '2', con_conciliacion_recientes: '1', con_conciliacion_anteriores: '2',
      con_conciliacion_sin_desde: '4', leido_sin_conciliacion: '3', leido_sin_conciliacion_anteriores: '7', sin_lector: '9',
      sin_proveedor: '1', traspasos_entre_farmacias: '0', excluidos_ausentes: '3', proveedores_con_conciliacion: '2',
      proveedores_leido_sin_conciliacion: '1', proveedores_sin_lector: '3', proveedores_con_conciliacion_sin_desde: '1', proveedores_traspaso: '0' };
    assert.deepEqual(Object.keys(resumenSinFactura(ok)), COLUMNAS_SIN_FACTURA);
    assert.deepEqual(COLUMNAS_SIN_FACTURA.slice(1, 1 + GRUPOS_SIN_FACTURA.length), GRUPOS_SIN_FACTURA.map((g) => COLUMNA_DIAGNOSTICO_GRUPO[g]));
    let err: unknown = null;
    try { resumenSinFactura({ ...ok, total: '35' }); } catch (e) { err = e; }
    assert.ok(err instanceof ErrorRecuentosIncoherentes);
    assert.match((err as Error).message, /DIAGNOSTICO_RECUENTOS_INCOHERENTES: sin_factura/);
    const r = (err as ErrorRecuentosIncoherentes).recuentos;
    assert.equal(r.total, 35);
    assert.equal(r.suma_grupos, 32);
    assert.equal(r.diferencia, 3);
    assert.equal(r.con_conciliacion_sin_desde, 4);
    assert.ok(Object.values(r).every((v) => Number.isSafeInteger(v)));
    assert.throws(() => resumenSinFactura({ ...ok, sin_lector: 'x' }), /NO_ES_RECUENTO/);
  });
  test('H8-4: check:real cuenta los traspasos y los proveedores de traspaso y sin fecha de inicio', () => {
    const diag = CONSULTAS_CHECK.diagnostico_sin_factura.sql;
    assert.match(diag, /g\.grupo = 'TRASPASO'\) as traspasos_entre_farmacias/);
    assert.match(diag, /as proveedores_traspaso/);
    assert.match(diag, /as proveedores_con_conciliacion_sin_desde/);
    assert.ok(COLUMNAS_SIN_FACTURA.includes('traspasos_entre_farmacias') && COLUMNAS_SIN_FACTURA.includes('proveedores_traspaso'));
  });
});

describe('H8-4: cobertura por proveedor con el nombre comercial de la lista', () => {
  const sfVacio = () => construirSinFactura([fila('TOTAL', null, { albaranes: '0' })], [], HOY_SIM);
  test('una factura HEFAME sin CIF ni id cae en HEFAME (con las de su CIF), no en «Proveedor sin identificar»', () => {
    const conCif = fb({ proveedor_grupo: 'cif:F30004444', proveedor_comercial: 'HEFAME', importe_total: 200 });
    const sinCif = fb({ proveedor_grupo: 'sin_identificar', proveedor_comercial: 'HEFAME', importe_total: 313.29 });
    const otra = fb({ proveedor_grupo: 'sin_identificar', proveedor_comercial: null, importe_total: 10 });
    const cob = coberturaProveedores([conCif, sinCif, otra], sfVacio());
    const hef = cob.find((f) => f.tipo === 'LECTOR' && f.nombre === 'HEFAME');
    assert.ok(hef && hef.tipo === 'LECTOR');
    assert.equal(hef.facturas, 2);
    assert.equal(hef.cobertura.facturado, 513.29);
    assert.equal(hef.proveedor_grupo, 'cif:F30004444');
    const resto = cob.filter((f) => f.tipo === 'LECTOR' && f.nombre === null);
    assert.deepEqual(resto.map((f) => f.clave), ['sin_identificar']);
  });
  test('una factura sin comercial va con el comercial de su grupo (CIF o id)', () => {
    const a = fb({ proveedor_grupo: 'cif:A50004324', proveedor_comercial: 'ALLIANCE' });
    const b = fb({ proveedor_grupo: 'cif:A50004324', proveedor_comercial: null });
    const cob = coberturaProveedores([a, b], sfVacio());
    assert.equal(cob.length, 1);
    assert.deepEqual(cob[0].tipo === 'LECTOR' && [cob[0].nombre, cob[0].facturas], ['ALLIANCE', 2]);
  });
});

describe('H8-5: desplegables de Sin factura, HPLUS = HEFAME y cobertura sin duplicados', () => {
  const sfCon = (filas: Fila[]) => {
    const n = filas.filter((f) => !String(f.clase).startsWith('DETALLE_')).reduce((a, f) => a + Number(f.albaranes), 0);
    return construirSinFactura([...filas, fila('TOTAL', null, { albaranes: String(n) })], [], HOY_SIM);
  };
  test('detalle de cada bloque limitado a los 100 más antiguos; recuento e importe de todos', () => {
    const base: AlbSim[] = Array.from({ length: 150 }, (_, i) => ({ id: i + 1, idp: '37', fecha: fechaMas('2026-06-01', i), importe: 2, ausente: false }));
    const sf = construirSinFactura(simularConsulta(base), [], HOY_SIM);
    const s = sf.sin_lector[0];
    assert.deepEqual([s.albaranes, s.importe, s.detalle.length], [150, 300, LIMITE_DETALLE_ALERTA]);
    assert.equal(s.detalle[0].fecha, '2026-06-01');
    assert.equal(s.detalle.at(-1)!.fecha, fechaMas('2026-06-01', 99));
  });
  test('falla cerrado: detalle sin su grupo, detalle de menos y detalle sin proveedor con proveedor', () => {
    assert.throws(() => sfCon([...detalles('DETALLE_LEIDO', '4', ['2026-10-01'])]), /SIN_FACTURA_DETALLE_NO_CUADRA/);
    assert.throws(() => sfCon([fila('TRASPASO', '40', { proveedor: '4.- FFARMACIA RITA', albaranes: '2' }),
      ...detalles('DETALLE_TRASPASO', '40', ['2026-10-01'])]), /SIN_FACTURA_DETALLE_NO_CUADRA/);
    assert.throws(() => sfCon([fila('SIN_PROVEEDOR', null), ...detalles('DETALLE_SIN_PROVEEDOR', '37', ['2026-10-01'])]), /con proveedor/);
    assert.throws(() => sfCon([fila('LEIDO', '4'), ...detalles('DETALLE_LEIDO', null, ['2026-10-01'])]), /sin proveedor/);
  });
  test('HPLUS CONSUMO se muestra como HEFAME (por CIF y por literal, también el de Farmatic), con su razón social debajo', () => {
    assert.equal(nombreProveedorFarmatic('12.- HPLUS CONSUMO'), 'HEFAME');
    const sf = sfCon([fila('SIN_LECTOR', '42', { proveedor: '12.- HPLUS CONSUMO' }), ...detalles('DETALLE_SIN_LECTOR', '42', ['2026-10-01']),
      fila('AUTO_RECIENTE', '2', { proveedor: '1.- SAFA', desde: '2026-10-01' })]);
    assert.deepEqual([sf.sin_lector[0].proveedor, sf.sin_lector[0].literal_farmatic], ['HEFAME', 'HPLUS CONSUMO']);
    assert.deepEqual([sf.con_lector[0].proveedor, sf.con_lector[0].literal_farmatic], ['ALLIANCE', 'SAFA']);
  });
  test('cobertura: una fila por nombre; los pendientes de Farmatic van en la fila de sus facturas; «sin lector» solo sin facturas', () => {
    const cof = fb({ proveedor_grupo: 'cif:A00000001', proveedor_etiqueta: 'COFARES', proveedor_comercial: null, importe_total: 177.74 });
    const hef = fb({ proveedor_grupo: 'cif:F30004444', proveedor_comercial: 'HEFAME', importe_total: 50 });
    const hplus = fb({ proveedor_grupo: 'cif:B30462451', proveedor_comercial: 'HEFAME', importe_total: 20 });
    const sf = sfCon([
      fila('SIN_LECTOR', '41', { proveedor: '2.- COFARES', albaranes: '396', importe: '1000' }),
      fila('SIN_LECTOR', '42', { proveedor: '12.- HPLUS CONSUMO', albaranes: '3', importe: '87.6' }),
      fila('SIN_LECTOR', '37', { proveedor: '37.- ISDIN', albaranes: '2', importe: '10' }),
      fila('SIN_LECTOR', '38', { proveedor: 'ISDIN', albaranes: '1', importe: null, sin_importe: '1' }),
      fila('SIN_PROVEEDOR', null, { proveedor: 'COFARES', albaranes: '1', importe: '5' }),
      ...detalles('DETALLE_SIN_LECTOR', '41', Array(100).fill('2026-10-01')),
      ...detalles('DETALLE_SIN_LECTOR', '42', ['2026-10-01', '2026-10-02', '2026-10-03']),
      ...detalles('DETALLE_SIN_LECTOR', '37', ['2026-10-01', '2026-10-02']),
      ...detalles('DETALLE_SIN_LECTOR', '38', ['2026-10-01']),
      ...detalles('DETALLE_SIN_PROVEEDOR', null, ['2026-10-01']),
    ]);
    const cob = coberturaProveedores([cof, hef, hplus], sf);
    const lector = cob.filter((f) => f.tipo === 'LECTOR');
    assert.deepEqual(lector.map((f) => f.tipo === 'LECTOR' && [f.nombre_mostrado, f.facturas, f.pendientes]), [
      ['COFARES', 1, { albaranes: 396, importe: 1000, sin_importe: 0 }],
      ['HEFAME', 2, { albaranes: 3, importe: 87.6, sin_importe: 0 }],
    ]);
    // ISDIN (dos ids de Farmatic) en una sola fila; los sin proveedor comparable nunca se juntan con COFARES.
    assert.deepEqual(cob.filter((f) => f.tipo === 'SIN_LECTOR').map((f) => f.tipo === 'SIN_LECTOR' && [f.proveedor, f.albaranes, f.importe, f.sin_importe]),
      [['ISDIN', 3, 10, 1], ['Proveedor sin identificar', 1, 5, 0]]);
  });
});
