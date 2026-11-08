/**
 * Adaptador FIXTURES: sirve los DTO ficticios de web/fixtures/dto/ (generados por
 * web/fixtures/scripts/gen_fixtures.mjs con los constructores del contrato).
 * No conecta a ninguna base de datos.
 */
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import type {
  CashflowSemanasDTO, ConciliacionBandejaDTO, ConfiguracionDTO, Contrato, FacturaDetalleDTO,
  FacturasDTO, InicioDTO, ProveedoresDTO, VencimientosDTO,
} from './contrato.ts';

export const DIR_DTO = join(import.meta.dirname, '..', '..', 'fixtures', 'dto');

/** Fichero de cada bloque. */
export const FICHEROS_DTO = {
  inicio: 'inicio.json',
  facturas: 'facturas.json',
  facturaDetalle: 'factura_detalle.json',
  conciliacionBandeja: 'conciliacion_bandeja.json',
  vencimientos: 'vencimientos.json',
  cashflowSemanas: 'cashflow_semanas.json',
  proveedores: 'proveedores.json',
  configuracion: 'configuracion.json',
} as const;

async function leer<T>(fichero: string): Promise<T> {
  return JSON.parse(await readFile(join(DIR_DTO, fichero), 'utf8')) as T;
}

export function crearAdaptadorFixtures(): Contrato {
  return {
    inicio: () => leer<InicioDTO>(FICHEROS_DTO.inicio),
    facturas: () => leer<FacturasDTO>(FICHEROS_DTO.facturas),
    facturaDetalle: async (id) => {
      const todos = await leer<Record<string, FacturaDetalleDTO>>(FICHEROS_DTO.facturaDetalle);
      return Object.hasOwn(todos, id) ? todos[id] : null;
    },
    conciliacionBandeja: () => leer<ConciliacionBandejaDTO>(FICHEROS_DTO.conciliacionBandeja),
    vencimientos: () => leer<VencimientosDTO>(FICHEROS_DTO.vencimientos),
    cashflowSemanas: () => leer<CashflowSemanasDTO>(FICHEROS_DTO.cashflowSemanas),
    proveedores: () => leer<ProveedoresDTO>(FICHEROS_DTO.proveedores),
    configuracion: () => leer<ConfiguracionDTO>(FICHEROS_DTO.configuracion),
  };
}
