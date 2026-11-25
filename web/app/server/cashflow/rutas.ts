/**
 * H7: GET /api/cashflow (solo lectura; sin escrituras ni excepción nueva).
 *
 * FIXTURES: datos ficticios con la forma del contrato (web/fixtures/cashflow/cashflow.json, generado por
 *   fixtures/scripts/gen_cashflow.mjs) y los vencimientos de PIO de la pantalla Vencimientos (contrato H6, con sus marcas).
 * REAL (H7-REAL): tablas cf_cashflow_* de la migración 38 con cf_lectura (server/cashflow/lectura_real.ts, una foto READ
 *   ONLY): importación vigente y sus filas; fecha de referencia = hoy en Europe/Madrid. Sin vigente, la pantalla muestra
 *   «Todavía no hay datos importados».
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { FastifyInstance } from 'fastify';
import { PAGO_SIN_DATOS } from '../contrato.ts';
import { esPagado, hoyMadrid, type FilaVencimientoPago, type PantallaVencimientosDTO } from '../pagos/pagos.ts';
import { CONFIG_CASHFLOW, type CashflowDTO, type DatosCashflow, type VencimientoCashflow } from './cashflow.ts';

export const RUTA_SEMILLA_CASHFLOW = join(import.meta.dirname, '..', '..', '..', 'fixtures', 'cashflow', 'cashflow.json');

export function leerSemillaCashflow(): DatosCashflow & { hoy: string } {
  const { hoy, importaciones, cuentas, importes, saldos, otras_cuentas } = JSON.parse(readFileSync(RUTA_SEMILLA_CASHFLOW, 'utf8')) as DatosCashflow & { hoy: string };
  return { hoy, importaciones, cuentas, importes, saldos, otras_cuentas };
}

/** Vencimiento de la pantalla H6 → lo que usa el cashflow. */
export function vencimientoCashflow(f: FilaVencimientoPago): VencimientoCashflow {
  return {
    vencimiento_id: f.vencimiento_id, factura_id: f.factura_id, numero_factura: f.numero_factura,
    proveedor_comercial: f.proveedor_comercial,
    proveedor_nombre: f.proveedor_comercial ?? f.proveedor_razon_social ?? f.proveedor ?? 'Proveedor sin identificar',
    fecha_vencimiento: f.fecha_vencimiento, importe: f.importe, sentido: f.sentido, estado_pago: f.estado_pago,
    // H6-REAL: una marca «a revisar» (ya no coincide con el vencimiento) no cuenta como pagada.
    fecha_pago: f.marca !== null && esPagado(f.estado_pago) ? f.marca.fecha_pago : null, cargo_negativo: f.cargo_negativo,
  };
}

export interface OpcionesCashflow {
  modo: 'FIXTURES' | 'REAL';
  /** Pantalla Vencimientos (H6): vencimientos de PIO con estado y marca. */
  pantallaPagos: () => Promise<PantallaVencimientosDTO>;
  /** FIXTURES: por defecto, la semilla. */
  semilla?: DatosCashflow & { hoy: string };
  /** REAL: lectura de las tablas cf_cashflow_* (obligatoria en REAL). */
  leerReal?: () => Promise<DatosCashflow>;
  /** REAL: fecha de referencia (por defecto, hoy en Europe/Madrid). */
  hoy?: () => string;
}

export function registrarCashflow(app: FastifyInstance, opciones: OpcionesCashflow): void {
  const semilla = opciones.modo === 'FIXTURES' ? opciones.semilla ?? leerSemillaCashflow() : null;
  if (opciones.modo === 'REAL' && !opciones.leerReal) throw new Error('CASHFLOW_REAL_SIN_LECTURA');
  const hoy = opciones.hoy ?? (() => hoyMadrid());
  app.get('/api/cashflow', async (_req, reply): Promise<CashflowDTO> => {
    reply.header('cache-control', 'no-store');
    const datos: DatosCashflow & { hoy: string } = semilla ?? { ...(await (opciones.leerReal as () => Promise<DatosCashflow>)()), hoy: hoy() };
    const p = await opciones.pantallaPagos();
    return {
      farmacia: p.farmacia, generado_at: p.generado_at, hoy: datos.hoy, modo: opciones.modo, config: CONFIG_CASHFLOW,
      importaciones: datos.importaciones, cuentas: datos.cuentas, importes: datos.importes, saldos: datos.saldos,
      otras_cuentas: datos.otras_cuentas,
      // Solo PIO (la pantalla H6 es de PIO). RITA: solo datos bancarios.
      vencimientos: p.filas.map(vencimientoCashflow),
      pago: PAGO_SIN_DATOS,
    };
  });
}
