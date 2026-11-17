// H7: genera web/fixtures/cashflow/cashflow.json (datos ficticios con la forma del contrato del circuito:
// cf_cashflow_importaciones, cf_cashflow_cuentas, cf_cashflow_importes, cf_cashflow_saldos). Sin datos reales.
//
// Uso: npm run fixtures:cashflow (en web/app). check_fixtures comprueba que el fichero está al día.
//
// Casos que cubre (fecha de referencia 16/11/2026; última decena con saldo de banco: 01–10/11/2026):
//   - PIO y RITA, decenas de 2026 (reales desde junio) y 2027 (previstas, hasta diciembre).
//   - Naranja: RITA queda en negativo en 11–20/12/2026 (campaña de HEFAME y paga extra) y PIO la cubre; RITA recupera
//     en 21–31/12/2026, la decena de la SOE.
//   - Rojo: el consolidado queda en negativo en 11–20/01/2027 (IVA y el robot dispensador de PIO).
//   - Vencimiento del sistema y Excel distintos: ALLIANCE en 11–20/11/2026 (Excel 520,00 €; sistema 472,22 €, F02).
//   - Importación vigente de hace 6 días (10/11/2026).
//   - Traspasos PIO → RITA con contrapartida (neutros en el consolidado) y «no relacionadas con la farmacia».
//   - Cuenta SL: en cf_cashflow_cuentas y con filas, pero fuera de la pantalla (solo PIO y RITA).
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export const RUTA_CASHFLOW = join(import.meta.dirname, '..', 'cashflow', 'cashflow.json');
export const HOY_CASHFLOW = '2026-11-16';
const INICIO = '2026-06-01';
const FIN = '2027-12-21';
export const ULTIMA_REAL = '2026-11-01';
/** Saldo de banco al cierre de la última decena real. */
export const PARTIDA = { PIO: 9000, RITA: 2000 };

const DIAS = ['01', '11', '21'];
const sumarMes = (ym, n) => { const [a, m] = ym.split('-').map(Number); return new Date(Date.UTC(a, m - 1 + n, 1)).toISOString().slice(0, 7); };
const siguiente = (d) => (d.endsWith('-21') ? `${sumarMes(d.slice(0, 7), 1)}-01` : `${d.slice(0, 8)}${DIAS[DIAS.indexOf(d.slice(8)) + 1]}`);
const fin = (d) => (d.endsWith('-01') ? `${d.slice(0, 8)}10` : d.endsWith('-11') ? `${d.slice(0, 8)}20`
  : new Date(Date.UTC(Number(d.slice(0, 4)), Number(d.slice(5, 7)), 0)).toISOString().slice(0, 10));
const ord = (d) => DIAS.indexOf(d.slice(8)) + 1;
const mm = (d) => d.slice(5, 7);
const r2 = (x) => Math.round(x * 100) / 100;

const DECENAS = [];
for (let d = INICIO; d <= FIN; d = siguiente(d)) DECENAS.push(d);

/** Variación de los cobros reales: suma 0 cada 6 decenas (la media de las últimas 6 es la cifra base). */
const CICLO = [300, -200, 100, -300, 200, -100];
const TRIMESTRE = ['01', '04', '07', '10'];
const SOE_REAL = {
  PIO: { '2026-06': 39500, '2026-07': 40200, '2026-08': 38900, '2026-09': 40600, '2026-10': 41000 },
  RITA: { '2026-06': 19600, '2026-07': 20300, '2026-08': 19800, '2026-09': 20500, '2026-10': 20000 },
};
/** Retiradas del titular de los meses reales (los meses reales cierran con un saldo parecido). */
const RETIRADA = {
  PIO: { '06': 1750, '07': 5950, '08': 13150, '09': 11850, '10': 11200 },
  RITA: { '06': 6600, '07': 11300, '08': 13800, '09': 17500, '10': 12400 },
};
const TRASPASOS = { '2026-09-11': 3000, '2027-03-01': 2000 };

// [categoría, concepto, (decena, k, real) => importe | null (sin fila)]
const CONCEPTOS = {
  PIO: [
    ['RE Cobro TPV', 'TPV CaixaBank', (d, k, real) => (real ? 10000 + CICLO[k % 6] : 9900)],
    ['RE Cobro efectivo', 'Ingresos de caja', (d, k, real) => (real ? 3000 + CICLO[k % 6] / 4 : 3000)],
    ['RE Cobro SOE', 'CatSalut receptes', (d, k, real) => (ord(d) !== 3 ? null : real ? SOE_REAL.PIO[d.slice(0, 7)] : 40000)],
    ['RE No relacionadas con la farmacia', 'Alquiler apartamento', (d) => (ord(d) === 1 ? 650 : null)],
    ['RS Proveedores', 'ALLIANCE', (d) => (d === '2026-11-11' ? 520 : 6000)],
    ['RS Proveedores', 'COFARES', () => 4500],
    ['RS Proveedores', 'HEFAME', () => 3500],
    ['RS Proveedores', 'FEDERACIÓ', (d) => (ord(d) === 1 ? 1500 : null)],
    ['RS Proveedores', 'LOGISTA', (d) => (ord(d) === 2 ? 800 : null)],
    ['RS Personal', 'Nóminas', (d) => (ord(d) === 1 ? 12000 : null)],
    ['RS Personal', 'Seguridad Social', (d) => (ord(d) === 3 ? 4500 : null)],
    ['RS Personal', 'Paga extra', (d) => (ord(d) === 3 && (mm(d) === '06' || mm(d) === '12') ? 12000 : null)],
    ['RS Gastos generales', 'Alquiler local', (d) => (ord(d) === 1 ? 2500 : null)],
    ['RS Gastos generales', 'Suministros', (d) => (ord(d) === 2 ? 900 : null)],
    ['RS Impuestos', 'IVA y retenciones', (d) => (ord(d) === 2 && TRIMESTRE.includes(mm(d)) ? 8500 : null)],
    ['RS Inversiones', 'Robot dispensador', (d) => (d === '2027-01-11' ? 32000 : null)],
    ['RS No relacionadas con la farmacia', 'Préstamo vivienda', (d) => (ord(d) === 1 ? 1200 : null)],
    ['RS No relacionadas con la farmacia', 'Retirada titular', (d, k, real) => (real && ord(d) === 3 ? RETIRADA.PIO[mm(d)] : null)],
    ['RS Traspasos', 'Traspaso a RITA', (d) => TRASPASOS[d] ?? null],
  ],
  RITA: [
    ['RE Cobro TPV', 'TPV Sabadell', (d, k, real) => (real ? 5200 + CICLO[k % 6] / 2 : 5000)],
    ['RE Cobro efectivo', 'Ingresos de caja', (d, k, real) => (real ? 1200 + CICLO[k % 6] / 10 : 1100)],
    ['RE Cobro SOE', 'CatSalut receptes', (d, k, real) => (ord(d) !== 3 ? null : real ? SOE_REAL.RITA[d.slice(0, 7)] : 20000)],
    ['RE Traspasos', 'Traspaso desde PIO', (d) => TRASPASOS[d] ?? null],
    ['RS Proveedores', 'COFARES', () => 3000],
    ['RS Proveedores', 'HEFAME', (d) => (d === '2026-12-01' ? 14000 : 2000)],
    ['RS Personal', 'Nóminas', (d) => (ord(d) === 1 ? 6000 : null)],
    ['RS Personal', 'Seguridad Social', (d) => (ord(d) === 3 ? 2200 : null)],
    // Real: la paga de junio, tras la SOE; previsto: en la 2.ª decena de junio y diciembre.
    ['RS Personal', 'Paga extra', (d, k, real) => (real ? (d === '2026-06-21' ? 7000 : null) : (ord(d) === 2 && (mm(d) === '06' || mm(d) === '12') ? 7000 : null))],
    ['RS Gastos generales', 'Alquiler local', (d) => (ord(d) === 1 ? 1500 : null)],
    ['RS Gastos generales', 'Suministros', (d) => (ord(d) === 2 ? 500 : null)],
    ['RS Impuestos', 'IVA y retenciones', (d) => (ord(d) === 2 && TRIMESTRE.includes(mm(d)) ? 3000 : null)],
    ['RS No relacionadas con la farmacia', 'Retirada titular', (d, k, real) => (real && ord(d) === 3 ? RETIRADA.RITA[mm(d)] : null)],
  ],
};

/**
 * H7-2: filas con importe negativo (el signo de la celda se respeta): un abono dentro de un proveedor (RS negativo:
 * reduce las salidas) y una regularización de cobros (RE negativo: reduce las entradas). Se suman a las de su concepto.
 */
export const FILAS_NEGATIVAS = [
  { cuenta: 'PIO', decena_inicio: '2026-12-01', categoria: 'RS Proveedores', concepto: 'COFARES', importe: -250 },
  { cuenta: 'RITA', decena_inicio: '2026-11-21', categoria: 'RE Otros cobros', concepto: 'Regularización mutua', importe: -120 },
];

const signo = (categoria) => (categoria.startsWith('RE ') ? 1 : -1);

export function generarCashflow() {
  const importes = [];
  const saldos = [];
  for (const cuenta of ['PIO', 'RITA']) {
    const mov = new Map();
    DECENAS.forEach((d, k) => {
      const real = d <= ULTIMA_REAL;
      for (const [categoria, concepto, f] of CONCEPTOS[cuenta]) {
        const v = f(d, k, real);
        if (v === null || v === undefined) continue;
        importes.push({ cuenta, decena_inicio: d, decena_fin: fin(d), categoria, concepto, importe: r2(v) });
        mov.set(d, r2((mov.get(d) ?? 0) + signo(categoria) * v));
      }
      for (const f of FILAS_NEGATIVAS.filter((x) => x.cuenta === cuenta && x.decena_inicio === d)) {
        importes.push({ cuenta, decena_inicio: d, decena_fin: fin(d), categoria: f.categoria, concepto: f.concepto, importe: f.importe });
        mov.set(d, r2((mov.get(d) ?? 0) + signo(f.categoria) * f.importe));
      }
    });
    // Saldo inicial para que el cierre de la última decena real sea PARTIDA.
    const realesNeto = DECENAS.filter((d) => d <= ULTIMA_REAL).reduce((a, d) => a + (mov.get(d) ?? 0), 0);
    let s = r2(PARTIDA[cuenta] - realesNeto);
    for (const d of DECENAS) {
      s = r2(s + (mov.get(d) ?? 0));
      const real = d <= ULTIMA_REAL;
      // Fórmulas del Excel = banco, salvo una diferencia de 35,20 € en PIO (21–31/10/2026).
      const formulas = cuenta === 'PIO' && d === '2026-10-21' ? r2(s + 35.2) : s;
      saldos.push({ cuenta, decena_inicio: d, saldo_formulas: formulas, saldo_bancos: real ? s : null });
    }
  }
  // Cuenta SL: fuera de la pantalla.
  for (const d of ['2026-10-01', '2026-11-01']) importes.push({ cuenta: 'SL', decena_inicio: d, decena_fin: fin(d), categoria: 'RS Gastos generales', concepto: 'Gestoría', importe: 300 });
  return {
    hoy: HOY_CASHFLOW,
    importaciones: [
      { importacion_id: 'c7000000-0000-4000-8000-000000000001', vigente: false, importado_at: '2026-11-03T07:40:00.000Z', origen: 'Cashflow 2026.xlsx', estado: 'OK' },
      { importacion_id: 'c7000000-0000-4000-8000-000000000002', vigente: true, importado_at: '2026-11-10T07:45:00.000Z', origen: 'Cashflow 2026.xlsx', estado: 'OK' },
    ],
    cuentas: [
      { codigo: 'PIO', farmacia: 'PIO' },
      { codigo: 'RITA', farmacia: 'RITA' },
      { codigo: 'SL', farmacia: null },
    ],
    importes,
    saldos,
  };
}

/** Una fila por línea (diff legible). */
export function serializarCashflow(c) {
  const lista = (xs) => `[\n${xs.map((x) => `    ${JSON.stringify(x)}`).join(',\n')}\n  ]`;
  return `{\n  "hoy": ${JSON.stringify(c.hoy)},\n  "importaciones": ${lista(c.importaciones)},\n  "cuentas": ${lista(c.cuentas)},\n`
    + `  "importes": ${lista(c.importes)},\n  "saldos": ${lista(c.saldos)}\n}\n`;
}

if (import.meta.main) {
  mkdirSync(join(import.meta.dirname, '..', 'cashflow'), { recursive: true });
  writeFileSync(RUTA_CASHFLOW, serializarCashflow(generarCashflow()), 'utf8');
  console.log('escrito cashflow/cashflow.json');
}
