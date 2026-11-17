/**
 * H7: GET /api/cashflow (solo lectura; sin escrituras ni excepción nueva).
 *
 * FIXTURES: datos ficticios con la forma del contrato (web/fixtures/cashflow/cashflow.json, generado por
 *   fixtures/scripts/gen_cashflow.mjs) y los vencimientos de PIO de la pantalla Vencimientos (contrato H6, con sus marcas).
 * REAL: las tablas cf_cashflow_* no existen todavía: 503 H7_PENDIENTE «Pendiente de tablas en Supabase». Las lecturas
 *   están escritas contra el contrato (server/cashflow/lectura_real.ts) pero no se conectan hasta que el circuito cree las
 *   tablas y Pío amplíe la lista cerrada de objetos legibles.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { FastifyInstance } from 'fastify';
import { PAGO_SIN_DATOS } from '../contrato.ts';
import type { FilaVencimientoPago, PantallaVencimientosDTO } from '../pagos/pagos.ts';
import {
  CONFIG_CASHFLOW, ERROR_H7_PENDIENTE, TEXTO_H7_PENDIENTE, type CashflowDTO, type DatosCashflow, type VencimientoCashflow,
} from './cashflow.ts';

export const RUTA_SEMILLA_CASHFLOW = join(import.meta.dirname, '..', '..', '..', 'fixtures', 'cashflow', 'cashflow.json');

export function leerSemillaCashflow(): DatosCashflow & { hoy: string } {
  const { hoy, importaciones, cuentas, importes, saldos } = JSON.parse(readFileSync(RUTA_SEMILLA_CASHFLOW, 'utf8')) as DatosCashflow & { hoy: string };
  return { hoy, importaciones, cuentas, importes, saldos };
}

/** Vencimiento de la pantalla H6 → lo que usa el cashflow. */
export function vencimientoCashflow(f: FilaVencimientoPago): VencimientoCashflow {
  return {
    vencimiento_id: f.vencimiento_id, factura_id: f.factura_id, numero_factura: f.numero_factura,
    proveedor_comercial: f.proveedor_comercial,
    proveedor_nombre: f.proveedor_comercial ?? f.proveedor_razon_social ?? f.proveedor ?? 'Proveedor sin identificar',
    fecha_vencimiento: f.fecha_vencimiento, importe: f.importe, sentido: f.sentido, estado_pago: f.estado_pago,
    fecha_pago: f.marca?.fecha_pago ?? null, cargo_negativo: f.cargo_negativo,
  };
}

export interface OpcionesCashflow {
  modo: 'FIXTURES' | 'REAL';
  /** Pantalla Vencimientos (H6): vencimientos de PIO con estado y marca. */
  pantallaPagos: () => Promise<PantallaVencimientosDTO>;
  /** FIXTURES: por defecto, la semilla. */
  semilla?: DatosCashflow & { hoy: string };
}

export function registrarCashflow(app: FastifyInstance, opciones: OpcionesCashflow): void {
  const semilla = opciones.modo === 'FIXTURES' ? opciones.semilla ?? leerSemillaCashflow() : null;
  app.get('/api/cashflow', async (_req, reply): Promise<CashflowDTO | undefined> => {
    reply.header('cache-control', 'no-store');
    if (semilla === null) {
      reply.code(503).send({ error: ERROR_H7_PENDIENTE, mensaje: TEXTO_H7_PENDIENTE });
      return undefined;
    }
    const p = await opciones.pantallaPagos();
    return {
      farmacia: p.farmacia, generado_at: p.generado_at, hoy: semilla.hoy, modo: opciones.modo, config: CONFIG_CASHFLOW,
      importaciones: semilla.importaciones, cuentas: semilla.cuentas, importes: semilla.importes, saldos: semilla.saldos,
      // Solo PIO (la pantalla H6 es de PIO). RITA: solo datos bancarios.
      vencimientos: p.filas.map(vencimientoCashflow),
      pago: PAGO_SIN_DATOS,
    };
  });
}
