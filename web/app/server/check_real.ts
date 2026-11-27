/**
 * npm run check:real — SOLO LO EJECUTA PÍO.
 *
 * Ejecuta en modo REAL (rol cf_lectura, transacción READ ONLY) cada consulta del contrato e
 * imprime solo: nombre, OK/ERROR (+ mensaje), nº de columnas y nº de filas. Nunca filas ni valores.
 * Las consultas por factura (factura_*) usan la factura PIO más reciente, elegida dentro del
 * adaptador; su id no se imprime (solo "factura=reciente" o "factura=ninguna" si PIO no tiene facturas).
 * Al final, diagnósticos (H4b/H4c): proveedores (facturas con CIF en la columna y en datos_extraidos, CIF
 * distintos, facturas sin CIF, sin CIF con id R9), vencimientos (total, null, incidencia
 * IMPORTE_VENCIMIENTO_NO_DOCUMENTADO, nulls por grupo de CIF sin CIF ni nombres, tipo_documento null en la
 * columna y en datos_extraidos, OTRO, sentido no documentado), documentos (PDF sin factura con y sin campo de
 * proveedor), tipo_documento (H4c-2: facturas por datos_extraidos.tipo_documento.valor en etiquetas fijas;
 * un valor no previsto solo suma en otros_valores, nunca se muestra), sentido (H4d-3: casos por origen:
 * vencimiento_regla, incidencia_sentido_no_documentado, incidencia_sentido_no_etiquetado), casado (H5-2/H5-3: líneas
 * vigentes por clase_numero y estado_matching; un valor no previsto se lista solo si cumple ^[A-Z0-9_]{1,40}$, el resto
 * suma en otros_no_codigo sin mostrarse), estado_linea (H5-7: líneas vigentes por estado de línea de la migración 30:
 * COINCIDE, DIFERENCIA, NO_EVALUABLE, sin_valor y otros_valores, y líneas con diferencia null), duplicados (candidatos y tras filtro de importe) y par 08C66676/08C66676A (sí/no y nombres de columna).
 * TA-REAL: DIAGNOSTICO trabajadores con cf_trabajadores_web (solo lectura): recuentos por tabla del módulo, módulo
 * TRABAJADORES = PIO/RITA (sí/no) y años de convenio_anual (y los que faltan de 2026–2028).
 * H6-REAL: DIAGNOSTICO pagos con cf_lectura (marcas vigentes, anuladas, a revisar —huérfanas incluidas— y huérfanas;
 * formas por CIF vigentes; filas de historial) y DIAGNOSTICO credencial_pagos con cf_pagos_web (conecta sí/no, en READ ONLY).
 * H8 (migración 36): MATCH_R20 es etiqueta fija del diagnóstico casado; DIAGNOSTICO noche: «para revisar» de la última
 * noche automática por tipo (diferencia, no_alliance, r18_pendiente, defecto, otros_tipos; fuera_de_pio aparte);
 * DIAGNOSTICO sin_factura: albaranes no reservados por ninguna conciliación vigente: total y un recuento por grupo
 * exhaustivo y excluyente (H8-3): con conciliación automática (alerta, recientes, anteriores, sin fecha de inicio), leído sin
 * conciliación automática (y anteriores), sin lector, sin proveedor y excluidos por no estar ya en Farmatic (AUSENTE);
 * proveedores por bloque. Si los grupos no suman el total, ERROR y una línea RECUENTOS con los mismos números.
 * H8-4: fecha de inicio de los proveedores con conciliación = su albarán reservado más antiguo (anteriores por esa fecha);
 * grupo traspasos_entre_farmacias; proveedores_con_conciliacion_sin_desde y proveedores_traspaso (debería ser 1).
 * H8-6: grupo devoluciones_abono_bloque (devoluciones Alliance en bloque, PROVEEDORES_ABONO_EN_BLOQUE) con sus tipos
 * devoluciones_bloque_safa, _safa_recientes, _eco360 y _safa_caducitats (deben sumar el grupo) y
 * devoluciones_bloque_discrepancia (id y literal que no casan: no clasificadas, siguen en su grupo).
 * H7-REAL: DIAGNOSTICO cashflow (migración 38): vigente sí/no, días desde la vigente, última ERROR sí/no, filas de
 * importes y saldos por cuenta, decenas reales con diferencia banco/fórmulas (E7) y decenas que no cuadran.
 * H7-REAL-2: recuentos de importes por cuenta y categoría (reales / anotados a futuro) y del efectivo de cada cuenta.
 * H7-AP1 (migración 40): DIAGNOSTICO cashflow_apuntes con cf_lectura (apuntes vigentes, anulados y sustituidos,
 * ocurrencias anuladas, recurrentes vigentes y anulados, ocurrencias en los próximos 12 meses, conceptos nuevos y anulados)
 * y DIAGNOSTICO credencial_cashflow con cf_cashflow_web (conecta sí/no, en READ ONLY y sin escribir).
 * H7-REAL-10 (en DIAGNOSTICO cashflow, lectura_real.ts → diagnosticoReglasPrevision): por cuenta, operativo (solo
 * farmacia) real y previsto, nº de conceptos esporádicos y terminados (sin nombres), doble cómputo evitado por la regla
 * del mes (casos e importe: entero + _negativa) y, por mes previsto, las 5 mayores cifras con categoría, fuente y sentido.
 * Solo recuentos, sí/no o nombres de columna; nunca valores.
 * Código de salida: 0 si todas OK; 1 si alguna falla (también sin conexión); 2 si falta .env.web o está incompleto.
 */
import { CONSULTAS, type NombreConsulta } from './contrato.ts';
import { ErrorRecuentosIncoherentes, NOMBRES_DIAGNOSTICO, crearAdaptadorReal, type AdaptadorReal } from './adaptador_real.ts';
import { configuracionRrhh, crearAdaptadorRrhhReal, crearPoolRrhh, leerEnvWeb } from './rrhh/adaptador_real.ts';
import { configuracionPagos, crearAlmacenPagosReal, crearPoolPagos, fuenteDesdeFilas } from './pagos/adaptador_real.ts';
import { construirPantalla, hoyMadrid } from './pagos/pagos.ts';
import { vencimientoCashflow } from './cashflow/rutas.ts';
import type { VencimientoCashflow } from './cashflow/cashflow.ts';
import { configuracionCashflow, crearAlmacenCashflowReal, crearPoolCashflow } from './cashflow/adaptador_real.ts';

function primeraLinea(e: unknown): string {
  const m = e instanceof Error ? e.message : String(e);
  return (m.split('\n')[0] ?? '').slice(0, 300);
}
function error(e: unknown): string {
  const codigo = (e as { code?: string }).code;
  return `ERROR ${codigo ? '[' + codigo + '] ' : ''}${primeraLinea(e)}`;
}

let real: AdaptadorReal;
try {
  real = crearAdaptadorReal();
} catch (e) {
  console.log(`SIN_CONFIGURACION ERROR ${primeraLinea(e)}`);
  process.exit(2);
}

let fallos = 0;
for (const n of Object.keys(CONSULTAS) as NombreConsulta[]) {
  try {
    const { columnas, filas, factura } = await real.probar(n);
    console.log(`${n} OK columnas=${columnas} filas=${filas}${factura ? ' factura=' + factura : ''}`);
  } catch (e) {
    fallos += 1;
    console.log(`${n} ${error(e)}`);
  }
}

// Diagnóstico proveedores (solo recuentos).
try {
  const d = await real.diagnosticoProveedores();
  console.log(`DIAGNOSTICO proveedores ${Object.entries(d).map(([k, v]) => `${k}=${v}`).join(' ')}`);
} catch (e) {
  fallos += 1;
  console.log(`DIAGNOSTICO proveedores ${error(e)}`);
}

// H4b: diagnósticos de vencimientos, duplicados y par 08C66676 (recuentos, sí/no o nombres de columna).
const formato = (v: unknown) => (typeof v === 'boolean' ? (v ? 'sí' : 'no') : Array.isArray(v) ? `[${v.join(',')}]` : String(v));
// H5-4: cada diagnóstico por separado (su propia transacción): un error solo afecta a su línea.
for (const nombre of NOMBRES_DIAGNOSTICO) {
  try {
    const d = await real.diagnostico(nombre);
    console.log(`DIAGNOSTICO ${nombre} ${Object.entries(d).map(([k, v]) => `${k}=${formato(v)}`).join(' ')}`);
  } catch (e) {
    fallos += 1;
    console.log(`DIAGNOSTICO ${nombre} ${error(e)}`);
    // H8-3: si los recuentos no cuadran, se imprimen igualmente (solo números) para ver la diferencia.
    const r = e instanceof ErrorRecuentosIncoherentes ? e.recuentos : null;
    if (r) console.log(`DIAGNOSTICO ${nombre} RECUENTOS ${Object.entries(r).map(([k, v]) => `${k}=${Number.isSafeInteger(v) ? v : 'no_numero'}`).join(' ')}`);
  }
}

// H6-REAL: pagos con cf_lectura (READ ONLY): marcas vigentes, anuladas, a revisar (huérfanas incluidas) y huérfanas,
// formas por CIF vigentes y filas de historial. Solo recuentos.
try {
  const d = await real.diagnosticoPagos();
  console.log(`DIAGNOSTICO pagos ${Object.entries(d).map(([k, v]) => `${k}=${v}`).join(' ')}`);
} catch (e) {
  fallos += 1;
  console.log(`DIAGNOSTICO pagos ${error(e)}`);
}

// H7-REAL: cashflow con cf_lectura (una foto READ ONLY): vigente sí/no, días desde la vigente, última ERROR sí/no, filas de
// importes y saldos por cuenta (PIO, RITA, SL, otras), decenas reales con diferencia banco/fórmulas y decenas que no
// cuadran. Solo números y sí/no. H7-REAL-2: recuentos por cuenta y categoría (reales y anotados a futuro,
// cat_<cuenta>_<categoría>_reales|_futuros) y del efectivo (efectivo_<cuenta>_reales|_futuros|_en_otra_categoria).
// H7-REAL-5: con los vencimientos de PIO (contrato H6 y marcas de pago, solo lectura) para ver cuántas decenas gana la
// media frente a los vencimientos y el indicador consolidado antes/después. Si no se pueden leer, sin vencimientos
// (vencimientos_leidos=0) y una línea con el error.
let vencimientosCashflow: VencimientoCashflow[] = [];
try {
  const hoy = hoyMadrid();
  const pantalla = construirPantalla(await real.contrato.vencimientos(), fuenteDesdeFilas(hoy, await real.leerPagos()), { modo: 'REAL' });
  vencimientosCashflow = pantalla.filas.map(vencimientoCashflow);
} catch (e) {
  fallos += 1;
  console.log(`DIAGNOSTICO cashflow_vencimientos ${error(e)}`);
}
try {
  const d = await real.diagnosticoCashflow(vencimientosCashflow);
  console.log(`DIAGNOSTICO cashflow ${Object.entries(d).map(([k, v]) => `${k}=${formato(v)}`).join(' ')}`);
} catch (e) {
  fallos += 1;
  console.log(`DIAGNOSTICO cashflow ${error(e)}`);
}

// H7-AP1: apuntes manuales de Cashflow (migración 40) con cf_lectura (READ ONLY): apuntes vigentes, anulados y
// sustituidos, ocurrencias anuladas una a una, recurrentes vigentes y anulados, ocurrencias en los próximos 12 meses
// (cf_cashflow_ocurrencias) y conceptos nuevos. Solo recuentos.
try {
  const d = await real.diagnosticoApuntesCashflow();
  console.log(`DIAGNOSTICO cashflow_apuntes ${Object.entries(d).map(([k, v]) => `${k}=${v}`).join(' ')}`);
} catch (e) {
  fallos += 1;
  console.log(`DIAGNOSTICO cashflow_apuntes ${error(e)}`);
}

await real.cerrar();

// H7-AP1: credencial de Cashflow (cf_cashflow_web), transacción READ ONLY y ROLLBACK. Sin escrituras. Solo sí/no y un recuento.
const cfgCashflow = configuracionCashflow(leerEnvWeb());
if (!cfgCashflow.ok) {
  fallos += 1;
  console.log(`DIAGNOSTICO credencial_cashflow SIN_CONFIGURACION ${cfgCashflow.codigo}: ${cfgCashflow.mensaje}`);
} else {
  const cf = crearAlmacenCashflowReal({ pool: crearPoolCashflow(cfgCashflow.config) });
  try {
    const d = await cf.probarCredencial();
    console.log(`DIAGNOSTICO credencial_cashflow conecta=sí filas_visibles=${d.filas}`);
  } catch (e) {
    fallos += 1;
    console.log(`DIAGNOSTICO credencial_cashflow ${error(e)}`);
  }
  await cf.cerrar?.();
}

// H6-REAL: credencial de pagos (cf_pagos_web), transacción READ ONLY y ROLLBACK. Sin escrituras. Solo sí/no y un recuento.
const cfgPagos = configuracionPagos(leerEnvWeb());
if (!cfgPagos.ok) {
  fallos += 1;
  console.log(`DIAGNOSTICO credencial_pagos SIN_CONFIGURACION ${cfgPagos.codigo}: ${cfgPagos.mensaje}`);
} else {
  const pagos = crearAlmacenPagosReal({ lector: async () => ({ marcas: [], formas: [], historial: [] }), pool: crearPoolPagos(cfgPagos.config) });
  try {
    const d = await pagos.probarCredencial();
    console.log(`DIAGNOSTICO credencial_pagos conecta=sí formas_vigentes_y_anuladas=${d.formas}`);
  } catch (e) {
    fallos += 1;
    console.log(`DIAGNOSTICO credencial_pagos ${error(e)}`);
  }
  await pagos.cerrar?.();
}

// TA-REAL: Trabajadores con su propia credencial (cf_trabajadores_web), transacción READ ONLY y ROLLBACK. Sin escrituras.
// Solo recuentos por tabla, sí/no del módulo TRABAJADORES = PIO/RITA y años del convenio (y los que faltan de 2026–2028).
const cfgTrab = configuracionRrhh(leerEnvWeb());
if (!cfgTrab.ok) {
  fallos += 1;
  console.log(`DIAGNOSTICO trabajadores SIN_CONFIGURACION ${cfgTrab.codigo}: ${cfgTrab.mensaje}`);
} else {
  const trab = crearAdaptadorRrhhReal({ pool: crearPoolRrhh(cfgTrab.config) });
  try {
    const d = await trab.diagnostico();
    console.log(`DIAGNOSTICO trabajadores ${Object.entries(d).map(([k, v]) => `${k}=${formato(v)}`).join(' ')}`);
  } catch (e) {
    fallos += 1;
    console.log(`DIAGNOSTICO trabajadores ${error(e)}`);
  }
  await trab.cerrar?.();
}

console.log(`TOTAL ${Object.keys(CONSULTAS).length} consultas + ${7 + NOMBRES_DIAGNOSTICO.length} diagnósticos, ${fallos} con error`);
process.exit(fallos ? 1 : 0);
