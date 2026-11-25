// H7: genera web/fixtures/cashflow/cashflow.json (datos ficticios con la forma del contrato del circuito:
// cf_cashflow_importaciones, cf_cashflow_cuentas, cf_cashflow_importes, cf_cashflow_saldos). Sin datos reales.
//
// Uso: npm run fixtures:cashflow (en web/app). check_fixtures comprueba que el fichero está al día.
//
// Casos que cubre (fecha de referencia 16/11/2026; última decena con saldo de banco: 01–10/11/2026):
//   - PIO y RITA, decenas reales desde octubre de 2025 (el año anterior de los modelos trimestrales) y previstas hasta
//     diciembre de 2027.
//   H7-REAL-2 (previsión por cuenta y categoría: vencimientos > apunte manual > Excel > media por posición de decena):
//   - El Excel futuro está poco anotado (como el de Pío): personal, alquiler del local, el robot, la campaña de HEFAME de
//     RITA, un TPV de Navidad de PIO (12.500 en 21–31/12/2026) y los traspasos con contrapartida. El resto, media de la
//     misma posición de decena en los últimos 3 meses reales. Los cobros reales varían por mes (+300, −100, −200: suman 0
//     en 3 meses seguidos), así que la media de cada posición es la cifra base: TPV PIO 11.000 / 10.000 / 9.000.
//   - SOE en la 3.ª decena: su media cae en su decena (PIO 40.000, RITA 20.000).
//   - «RS Modelo 303» y «RS Modelo 111» (trimestrales, 2.ª decena de enero, abril, julio y octubre): el mismo mes del año
//     anterior (enero de 2027 = enero de 2026: 8.500 y 1.500 en PIO).
//   - H7-REAL-4: traspasos internos (conceptos de TRASPASOS_INTERNOS: «La Caixa Rita» ↔ «DEPÓSITO CONECTADO», neutros y
//     sin media; dos sin contrapartida en la 3.ª decena de agosto a octubre de 2026, sin aviso) y externos («TRASPASO A
//     FONDOS/VALORS» en PIO, «TRASPASO A LA SL (JUBILACIO ETC)» en RITA): cuentan en el saldo y llevan media por concepto.
//   - RITA con «RE Cobro efectivo / COBRO EFECTIU» en todas las decenas reales (como su hoja del Excel).
//   - Naranja: RITA queda en negativo en 11–20/12/2026 (campaña de HEFAME y paga extra) y PIO la cubre; RITA recupera en
//     21–31/12/2026, la decena de la SOE.
//   - Rojo: el consolidado queda en negativo en 11–20/01/2027 (modelos trimestrales y el robot dispensador de PIO).
//   - Vencimiento del sistema y Excel distintos: ALLIANCE en 11–20/11/2026 (Excel 520,00 €; sistema 472,22 €, F02).
//     H7-REAL-3: «RS Proveedores» tiene vencimientos, así que va por concepto: ALLIANCE por vencimientos y el resto por la
//     media de la 2.ª decena sin ALLIANCE (COFARES 4.500 + HEFAME 3.500 + LOGISTA 800 = 8.800), sin doble cómputo.
//     H7-REAL-5: los vencimientos son un mínimo: los de ALLIANCE (472,22) son menores que su media de la 2.ª decena
//     (6.000), así que cuenta la media («Vencimientos conocidos 472,22 € (inferiores a la media)»). El caso contrario
//     (ganan los vencimientos) va en las pruebas unitarias: los fixtures de H6 no tienen otro vencimiento futuro con
//     correspondencia. Robot de 27.700 € para que los avisos sigan siendo los mismos.
//     H7-REAL-8: previsión base = Excel antes que la media; los vencimientos (472,22) se comparan con el Excel (520):
//     gana el Excel. Media de 12 meses; robot de 32.000 € para mantener el rojo de 11–20/01/2027 (2.584,99 €).
//     H7-REAL-9: previsión por concepto, el mayor entre Excel y media (ALLIANCE: su media de 6.000 > Excel 520); los
//     demás conceptos de una categoría anotada llevan su media. Robot de 23.400 € y campaña HEFAME de RITA de 9.800 €
//     para mantener la naranja de RITA (11–20/12/2026, 5.008,33 €) y un solo rojo (11–20/01/2027, 2.598,36 €).
//   H7-REAL-7: dos alias de KENVUE en la misma decena real (una línea con la suma) y una obra en 12/2027, fuera del
//   horizonte de 12 meses previstos: el consolidado queda en negativo allí, pero sin aviso.
//   - Importación vigente de hace 6 días (10/11/2026).
//   - Cuenta SL: en cf_cashflow_cuentas, sin filas (como el Excel actual) y fuera de la pantalla (solo PIO y RITA).
//   H7-REAL (forma final de la migración 38): ids, importacion_id (todas de la vigente), farmacia de la cuenta y
//   saldo_inicial (saldo_inicial + ΣRE − ΣRS = saldo_formulas en todas las decenas: cuadra). E7: en PIO 21–31/10/2026 el
//   banco va 35,20 € por debajo de las fórmulas.
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export const RUTA_CASHFLOW = join(import.meta.dirname, '..', 'cashflow', 'cashflow.json');
export const HOY_CASHFLOW = '2026-11-16';
const INICIO = '2025-10-01';
const FIN = '2027-12-21';
export const ULTIMA_REAL = '2026-11-01';
/** Saldo de banco al cierre de la última decena real. */
export const PARTIDA = { PIO: 25000, RITA: 2000 };

const DIAS = ['01', '11', '21'];
const sumarMes = (ym, n) => { const [a, m] = ym.split('-').map(Number); return new Date(Date.UTC(a, m - 1 + n, 1)).toISOString().slice(0, 7); };
const siguiente = (d) => (d.endsWith('-21') ? `${sumarMes(d.slice(0, 7), 1)}-01` : `${d.slice(0, 8)}${DIAS[DIAS.indexOf(d.slice(8)) + 1]}`);
const fin = (d) => (d.endsWith('-01') ? `${d.slice(0, 8)}10` : d.endsWith('-11') ? `${d.slice(0, 8)}20`
  : new Date(Date.UTC(Number(d.slice(0, 4)), Number(d.slice(5, 7)), 0)).toISOString().slice(0, 10));
const ord = (d) => DIAS.indexOf(d.slice(8)) + 1;
const mm = (d) => d.slice(5, 7);
const ym = (d) => d.slice(0, 7);
const r2 = (x) => Math.round(x * 100) / 100;

const DECENAS = [];
for (let d = INICIO; d <= FIN; d = siguiente(d)) DECENAS.push(d);

/** Variación mensual de los cobros reales: suma 0 en 3 meses seguidos (la media por posición es la cifra base). */
const VAR = [300, -100, -200];
const variacion = (d) => VAR[(Number(d.slice(0, 4)) * 12 + Number(mm(d))) % 3];
const TRIMESTRE = ['01', '04', '07', '10'];
const SOE_REAL = {
  PIO: { '2025-10': 39800, '2025-11': 40200, '2025-12': 40300, '2026-01': 39600, '2026-02': 40200, '2026-03': 39900, '2026-04': 40400,
    '2026-05': 39700, '2026-06': 39500, '2026-07': 40200, '2026-08': 38900, '2026-09': 40600, '2026-10': 40500 },
  RITA: { '2025-10': 19900, '2025-11': 20200, '2025-12': 20400, '2026-01': 19700, '2026-02': 20100, '2026-03': 19800, '2026-04': 20300,
    '2026-05': 19600, '2026-06': 19600, '2026-07': 20300, '2026-08': 19800, '2026-09': 20500, '2026-10': 19700 },
};
const MODELO_303 = {
  PIO: { '2025-10': 8200, '2026-01': 8500, '2026-04': 7900, '2026-07': 9100, '2026-10': 8800 },
  RITA: { '2025-10': 2900, '2026-01': 3100, '2026-04': 2800, '2026-07': 3300, '2026-10': 3000 },
};
/** Retiradas del titular de agosto a octubre de 2026 (base de la media de la 3.ª decena); antes, las que cierran el mes. */
const RETIRADA = { PIO: { '2026-08': 3500, '2026-09': 2000, '2026-10': 3500 }, RITA: { '2026-08': 3500, '2026-09': 4500, '2026-10': 4000 } };
/** Desde este mes la retirada es la de RETIRADA; antes, la del mismo mes del ciclo (mes % 3: sep 0, oct 1, ago 2). */
const DESDE_RETIRADA_FIJA = '2026-08';
/** Conceptos de traspaso interno (TRASPASOS_INTERNOS) que cierran a 0 los meses reales hasta julio de 2026. */
const TRASPASO_AJUSTE = { PIO: 'La Caixa Rita', RITA: 'TRASPÀS A PIO DEPOSITO CON.' };
const RETIRADA_CICLO = {
  PIO: [RETIRADA.PIO['2026-09'], RETIRADA.PIO['2026-10'], RETIRADA.PIO['2026-08']],
  RITA: [RETIRADA.RITA['2026-09'], RETIRADA.RITA['2026-10'], RETIRADA.RITA['2026-08']],
};
/** Traspasos internos PIO → RITA (con contrapartida: neutros en el consolidado). Conceptos de TRASPASOS_INTERNOS. */
const TRASPASOS = { '2026-09-11': 3000, '2027-03-01': 2000 };
/**
 * Traspasos internos (conceptos de TRASPASOS_INTERNOS) sin contrapartida en la otra cuenta: 3.ª decena de agosto a
 * octubre de 2026. Neutros y sin media; salen en la línea plegada «traspasos no compensados».
 */
const SIN_CONTRAPARTIDA = { PIO: ['DEPOSITO CONECTADO', 6000], RITA: ['TRASPÀS A PIO DEPOSITO CON.', 10000] };
/**
 * H7-REAL-4: traspasos EXTERNOS (conceptos fuera de TRASPASOS_INTERNOS): entradas o salidas reales del consolidado, con
 * media por concepto. PIO «TRASPASO A FONDOS/VALORS» 1.000 € en la 1.ª decena (anotado 2.500 € en 1–10/02/2027: manda
 * el Excel); RITA «TRASPASO A LA SL (JUBILACIO ETC)» 500 € en la 2.ª decena.
 */
const EXTERNOS = { PIO: ['TRASPASO A FONDOS/VALORS', 1, 1000], RITA: ['TRASPASO A LA SL (JUBILACIO ETC)', 2, 500] };
const conSinContrapartida = (d) => ord(d) === 3 && ym(d) >= '2026-08' && ym(d) <= '2026-10';

// [categoría, concepto, real(d) → importe | null, futuro(d) → importe | null (lo anotado en el Excel)]
const nada = () => null;
const CONCEPTOS = {
  PIO: [
    ['RE Cobro TPV', 'TPV CaixaBank', (d) => [11000, 10000, 9000][ord(d) - 1] + variacion(d), (d) => (d === '2026-12-21' ? 12500 : null)],
    ['RE Cobro efectivo', 'Ingresos de caja', (d) => 3000 + variacion(d) / 4, nada],
    ['RE Cobro SOE', 'CatSalut receptes', (d) => (ord(d) === 3 ? SOE_REAL.PIO[ym(d)] : null), nada],
    ['RE No relacionadas con la farmacia', 'Alquiler apartamento', (d) => (ord(d) === 1 ? 650 : null), nada],
    ['RS Proveedores', 'ALLIANCE', () => 6000, (d) => (d === '2026-11-11' ? 520 : null)],
    ['RS Proveedores', 'COFARES', () => 4500, nada],
    ['RS Proveedores', 'HEFAME', () => 3500, nada],
    ['RS Proveedores', 'FEDERACIÓ', (d) => (ord(d) === 3 ? 1500 : null), nada],
    ['RS Proveedores', 'LOGISTA', (d) => (ord(d) === 2 ? 800 : null), nada],
    ['RS Personal', 'Nóminas', (d) => (ord(d) === 1 ? 12000 : null), (d) => (ord(d) === 1 ? 12000 : null)],
    ['RS Personal', 'Seguridad Social', (d) => (ord(d) === 3 ? 4500 : null), (d) => (ord(d) === 3 ? 4500 : null)],
    ['RS Personal', 'Paga extra', (d) => (ord(d) === 3 && ['06', '12'].includes(mm(d)) ? 12000 : null), (d) => (ord(d) === 3 && ['06', '12'].includes(mm(d)) ? 12000 : null)],
    ['RS Gastos generales', 'Alquiler local', (d) => (ord(d) === 1 ? 2500 : null), (d) => (ord(d) === 1 ? 2500 : null)],
    ['RS Gastos generales', 'Suministros', (d) => (ord(d) === 2 ? 900 : null), nada],
    ['RS Modelo 303', 'IVA trimestral', (d) => (ord(d) === 2 ? MODELO_303.PIO[ym(d)] ?? null : null), nada],
    ['RS Modelo 111', 'Retenciones IRPF', (d) => (ord(d) === 2 && TRIMESTRE.includes(mm(d)) ? 1500 : null), nada],
    ['RS Inversiones', 'Robot dispensador', nada, (d) => (d === '2027-01-11' ? 23400 : null)],
    ['RS No relacionadas con la farmacia', 'Préstamo vivienda', (d) => (ord(d) === 1 ? 1200 : null), nada],
    ['RS Traspasos', 'La Caixa Rita', (d) => TRASPASOS[d] ?? null, (d) => TRASPASOS[d] ?? null],
    ['RS Traspasos', SIN_CONTRAPARTIDA.PIO[0], (d) => (conSinContrapartida(d) ? SIN_CONTRAPARTIDA.PIO[1] : null), nada],
    ['RS Traspasos', EXTERNOS.PIO[0], (d) => (ord(d) === EXTERNOS.PIO[1] ? EXTERNOS.PIO[2] : null), (d) => (d === '2027-02-01' ? 2500 : null)],
  ],
  RITA: [
    ['RE Cobro TPV', 'TPV Sabadell', (d) => [5500, 5000, 4500][ord(d) - 1] + variacion(d) / 2, nada],
    // Como la hoja RITA del Excel: «RE Cobro efectivo / COBRO EFECTIU» en todas las decenas.
    ['RE Cobro efectivo', 'COBRO EFECTIU', (d) => 1200 + variacion(d) / 10, nada],
    ['RE Cobro SOE', 'CatSalut receptes', (d) => (ord(d) === 3 ? SOE_REAL.RITA[ym(d)] : null), nada],
    ['RE Traspasos', 'DEPÓSITO CONECTADO', (d) => TRASPASOS[d] ?? null, (d) => TRASPASOS[d] ?? null],
    ['RS Proveedores', 'COFARES', () => 3000, nada],
    ['RS Proveedores', 'HEFAME', () => 2000, (d) => (d === '2026-12-01' ? 9800 : null)],
    ['RS Personal', 'Nóminas', (d) => (ord(d) === 1 ? 6000 : null), (d) => (ord(d) === 1 ? 6000 : null)],
    ['RS Personal', 'Seguridad Social', (d) => (ord(d) === 3 ? 2200 : null), (d) => (ord(d) === 3 ? 2200 : null)],
    // Real: tras la SOE; previsto: en la 2.ª decena de junio y diciembre.
    ['RS Personal', 'Paga extra', (d) => (ord(d) === 3 && ['06', '12'].includes(mm(d)) ? 7000 : null), (d) => (ord(d) === 2 && ['06', '12'].includes(mm(d)) ? 7000 : null)],
    ['RS Gastos generales', 'Alquiler local', (d) => (ord(d) === 1 ? 1500 : null), (d) => (ord(d) === 1 ? 1500 : null)],
    ['RS Gastos generales', 'Suministros', (d) => (ord(d) === 2 ? 500 : null), nada],
    ['RS Modelo 303', 'IVA trimestral', (d) => (ord(d) === 2 ? MODELO_303.RITA[ym(d)] ?? null : null), nada],
    ['RS Traspasos', SIN_CONTRAPARTIDA.RITA[0], (d) => (conSinContrapartida(d) ? SIN_CONTRAPARTIDA.RITA[1] : null), nada],
    ['RS Traspasos', EXTERNOS.RITA[0], (d) => (ord(d) === EXTERNOS.RITA[1] ? EXTERNOS.RITA[2] : null), nada],
  ],
};
const CATEGORIA_RETIRADA = 'RS No relacionadas con la farmacia';
const CONCEPTO_RETIRADA = 'Retirada titular';

/**
 * H7-2: filas con importe negativo (el signo de la celda se respeta): un abono dentro de un proveedor (RS negativo:
 * reduce las salidas; decena real fuera de la base de la media) y una regularización de cobros (RE negativo: reduce las
 * entradas; anotada a futuro). Se suman a las de su concepto.
 */
export const FILAS_NEGATIVAS = [
  { cuenta: 'PIO', decena_inicio: '2026-07-11', categoria: 'RS Proveedores', concepto: 'COFARES', importe: -250 },
  { cuenta: 'RITA', decena_inicio: '2026-11-21', categoria: 'RE Otros cobros', concepto: 'Regularización mutua', importe: -120 },
];
/**
 * H7-REAL-7: equivalencias de concepto (CONCEPTOS_EQUIVALENTES, decisión de Pío 25/11/2026). Dos alias de KENVUE en la
 * misma decena real de PIO (11–20/03/2026, fuera de la base de la media y en un mes que la retirada deja a 0: no cambia
 * ningún saldo ni ninguna previsión a la vista): una sola línea «KENVUE» con la suma (300 + 200 = 500).
 */
export const FILAS_EQUIVALENTES = [
  { cuenta: 'PIO', decena_inicio: '2026-03-11', categoria: 'RS Proveedores', concepto: 'JNTL CONSUMER (ORALDINE) S.L.', importe: 300 },
  { cuenta: 'PIO', decena_inicio: '2026-03-11', categoria: 'RS Proveedores', concepto: 'JHONSON & JHONSON', importe: 200 },
];
/**
 * H7-REAL-8 (en meses reales que la retirada deja a 0: los saldos reales a la vista no cambian):
 *  - PAGO_HACE_8_MESES: «RS Gastos generales / Reparación cámara frigorífica» 6.000 € en PIO 21–31/03/2026: entra en la
 *    media de 12 meses de la 3.ª decena (500 €), no en la de 3;
 *  - FILAS_PREFIJO: par por prefijo en PIO («DERMOPHARMACIE I PERF…» → «DERMOFARMACIA PERFUM…», el nombre completo del
 *    Excel): una línea «DERMOFARMACIA PERFUMERIA SL» con 120 + 80; en RITA el prefijo del nombre que queda coincide con
 *    dos nombres distintos: ambiguo, no se fusiona (tres líneas).
 */
export const PAGO_HACE_8_MESES = { cuenta: 'PIO', decena_inicio: '2026-03-21', categoria: 'RS Gastos generales', concepto: 'Reparación cámara frigorífica', importe: 6000 };
export const FILAS_PREFIJO = [
  { cuenta: 'PIO', decena_inicio: '2026-03-11', categoria: 'RS Proveedores', concepto: 'DERMOPHARMACIE I PERFUMERIA', importe: 120 },
  { cuenta: 'PIO', decena_inicio: '2026-03-11', categoria: 'RS Proveedores', concepto: 'DERMOFARMACIA PERFUMERIA SL', importe: 80 },
  { cuenta: 'RITA', decena_inicio: '2026-03-11', categoria: 'RS Proveedores', concepto: 'DERMOPHARMACIE I PERFUMERIA', importe: 60 },
  { cuenta: 'RITA', decena_inicio: '2026-03-11', categoria: 'RS Proveedores', concepto: 'DERMOFARMACIA PERFUMERIA SL', importe: 40 },
  { cuenta: 'RITA', decena_inicio: '2026-03-11', categoria: 'RS Proveedores', concepto: 'DERMOFARMACIA PERFUMES BCN', importe: 30 },
];
/**
 * H7-REAL-7: aviso fuera del horizonte. Obra anotada en el Excel de PIO en 11–20/12/2027, más allá de los 12 meses
 * previstos (hasta 01–10/11/2027): el consolidado queda en negativo, pero no sale ningún aviso (como el indicador).
 */
export const FUERA_HORIZONTE = { cuenta: 'PIO', decena_inicio: '2027-12-11', categoria: 'RS Inversiones', concepto: 'Reforma local', importe: 400000 };

const signo = (categoria) => (categoria.startsWith('RE ') ? 1 : -1);

/** Importación vigente de la semilla (todas las filas son suyas). */
export const IMPORTACION_VIGENTE = 'c7000000-0000-4000-8000-000000000002';
/** E7: diferencia banco − fórmulas en PIO 21–31/10/2026. */
export const DIFERENCIA_E7 = { cuenta: 'PIO', decena_inicio: '2026-10-21', importe: -35.2 };

export function generarCashflow() {
  const importes = [];
  const saldos = [];
  for (const cuenta of ['PIO', 'RITA']) {
    const mov = new Map();
    const delMes = new Map();
    const fila = (d, categoria, concepto, importe) => {
      importes.push({
        id: `m${String(importes.length + 1).padStart(5, '0')}`, importacion_id: IMPORTACION_VIGENTE, cuenta, farmacia: cuenta,
        decena_inicio: d, decena_fin: fin(d), categoria, concepto, importe,
      });
      mov.set(d, r2((mov.get(d) ?? 0) + signo(categoria) * importe));
      delMes.set(ym(d), r2((delMes.get(ym(d)) ?? 0) + signo(categoria) * importe));
    };
    for (const d of DECENAS) {
      const real = d <= ULTIMA_REAL;
      for (const [categoria, concepto, fReal, fFuturo] of CONCEPTOS[cuenta]) {
        const v = (real ? fReal : fFuturo)(d);
        if (v === null || v === undefined) continue;
        fila(d, categoria, concepto, r2(v));
      }
      for (const f of [...FILAS_NEGATIVAS, ...FILAS_EQUIVALENTES, FUERA_HORIZONTE, PAGO_HACE_8_MESES, ...FILAS_PREFIJO].filter((x) => x.cuenta === cuenta && x.decena_inicio === d)) fila(d, f.categoria, f.concepto, f.importe);
      // Retirada del titular (real, 3.ª decena). H7-REAL-8 (media de 12 meses): en todos los meses reales, el ciclo de
      // agosto–octubre de 2026 (suma lo mismo en 3 y en 12 meses, como los cobros); antes de H7-REAL-8, la que dejaba
      // el mes a 0 hasta julio de 2026.
      if (real && ord(d) === 3) {
        const fija = ym(d) >= DESDE_RETIRADA_FIJA;
        const v = fija ? RETIRADA[cuenta][ym(d)] : RETIRADA_CICLO[cuenta][Number(mm(d)) % 3];
        if (v > 0) fila(d, CATEGORIA_RETIRADA, CONCEPTO_RETIRADA, v);
        // Hasta julio de 2026 el resto del mes sale por un traspaso interno (neutro, sin media): el mes cierra con el
        // mismo saldo, como antes, sin que entre en la media de las «no relacionadas».
        const resto = r2(delMes.get(ym(d)) ?? 0);
        if (!fija && resto > 0) fila(d, 'RS Traspasos', TRASPASO_AJUSTE[cuenta], resto);
      }
    }
    // Saldo inicial para que el cierre de la última decena real sea PARTIDA.
    const realesNeto = DECENAS.filter((d) => d <= ULTIMA_REAL).reduce((a, d) => a + (mov.get(d) ?? 0), 0);
    let s = r2(PARTIDA[cuenta] - realesNeto);
    for (const d of DECENAS) {
      const inicial = s;
      s = r2(s + (mov.get(d) ?? 0));
      const real = d <= ULTIMA_REAL;
      // Fórmulas = saldo_inicial + ΣRE − ΣRS (cuadra); banco = fórmulas, salvo la diferencia E7.
      const e7 = cuenta === DIFERENCIA_E7.cuenta && d === DIFERENCIA_E7.decena_inicio ? DIFERENCIA_E7.importe : 0;
      saldos.push({
        id: `s${String(saldos.length + 1).padStart(4, '0')}`, importacion_id: IMPORTACION_VIGENTE, cuenta, farmacia: cuenta, decena_inicio: d,
        saldo_inicial: inicial, saldo_formulas: s, saldo_bancos: real ? r2(s + e7) : null,
      });
    }
  }
  return {
    hoy: HOY_CASHFLOW,
    importaciones: [
      { importacion_id: IMPORTACION_VIGENTE, archivo_nombre: 'Cashflow 2026.xlsx', origen: 'NOCHE', estado: 'OK', detalle_error: null,
        filas: importes.length + saldos.length, importado_at: '2026-11-10T07:45:00.000Z', vigente: true },
    ],
    cuentas: [
      { codigo: 'PIO', farmacia: 'PIO' },
      { codigo: 'RITA', farmacia: 'RITA' },
      { codigo: 'SL', farmacia: null },
    ],
    importes,
    saldos,
    // SL: sin filas en el Excel actual (la lectura REAL solo devolvería recuentos).
    otras_cuentas: [],
  };
}

/** Una fila por línea (diff legible). */
export function serializarCashflow(c) {
  const lista = (xs) => (xs.length === 0 ? '[]' : `[\n${xs.map((x) => `    ${JSON.stringify(x)}`).join(',\n')}\n  ]`);
  return `{\n  "hoy": ${JSON.stringify(c.hoy)},\n  "importaciones": ${lista(c.importaciones)},\n  "cuentas": ${lista(c.cuentas)},\n`
    + `  "importes": ${lista(c.importes)},\n  "saldos": ${lista(c.saldos)},\n  "otras_cuentas": ${lista(c.otras_cuentas)}\n}\n`;
}

if (import.meta.main) {
  mkdirSync(join(import.meta.dirname, '..', 'cashflow'), { recursive: true });
  writeFileSync(RUTA_CASHFLOW, serializarCashflow(generarCashflow()), 'utf8');
  console.log('escrito cashflow/cashflow.json');
}
