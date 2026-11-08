/**
 * npm run check:real — SOLO LO EJECUTA PÍO.
 *
 * Ejecuta en modo REAL (rol cf_lectura, transacción READ ONLY) cada consulta del contrato e
 * imprime solo: nombre, OK/ERROR (+ mensaje), nº de columnas y nº de filas. Nunca filas ni valores.
 * Las consultas por factura (factura_*) usan la factura PIO más reciente, elegida dentro del
 * adaptador; su id no se imprime (solo "factura=reciente" o "factura=ninguna" si PIO no tiene facturas).
 * Al final, diagnósticos (H4b): proveedores (CIF distintos, facturas sin CIF), vencimientos (total, null,
 * incidencia IMPORTE_VENCIMIENTO_NO_DOCUMENTADO, nulls por grupo de CIF sin CIF ni nombres), duplicados
 * (candidatos y tras filtro de importe) y par 08C66676/08C66676A (sí/no y nombres de columna).
 * Solo recuentos, sí/no o nombres de columna; nunca valores.
 * Código de salida: 0 si todas OK; 1 si alguna falla (también sin conexión); 2 si falta .env.web o está incompleto.
 */
import { CONSULTAS, type NombreConsulta } from './contrato.ts';
import { crearAdaptadorReal, type AdaptadorReal } from './adaptador_real.ts';

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
try {
  const ds = await real.diagnosticos();
  for (const [seccion, d] of Object.entries(ds)) {
    console.log(`DIAGNOSTICO ${seccion} ${Object.entries(d).map(([k, v]) => `${k}=${formato(v)}`).join(' ')}`);
  }
} catch (e) {
  fallos += 1;
  console.log(`DIAGNOSTICO vencimientos/duplicados/par_08C66676 ${error(e)}`);
}

await real.cerrar();
console.log(`TOTAL ${Object.keys(CONSULTAS).length} consultas + 4 diagnósticos, ${fallos} con error`);
process.exit(fallos ? 1 : 0);
