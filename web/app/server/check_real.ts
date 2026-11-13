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
 * Solo recuentos, sí/no o nombres de columna; nunca valores.
 * Código de salida: 0 si todas OK; 1 si alguna falla (también sin conexión); 2 si falta .env.web o está incompleto.
 */
import { CONSULTAS, type NombreConsulta } from './contrato.ts';
import { NOMBRES_DIAGNOSTICO, crearAdaptadorReal, type AdaptadorReal } from './adaptador_real.ts';
import { configuracionRrhh, crearAdaptadorRrhhReal, crearPoolRrhh, leerEnvWeb } from './rrhh/adaptador_real.ts';

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
  }
}

await real.cerrar();

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

console.log(`TOTAL ${Object.keys(CONSULTAS).length} consultas + ${2 + NOMBRES_DIAGNOSTICO.length} diagnósticos, ${fallos} con error`);
process.exit(fallos ? 1 : 0);
