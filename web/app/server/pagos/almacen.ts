/**
 * H6-REAL: almacén de marcas y formas que usan las rutas, igual en los dos modos.
 *
 *  - FIXTURES: envoltorio asíncrono del almacén en memoria (pagos.ts), con la semilla web/fixtures/pagos/pagos.json.
 *  - REAL: server/pagos/adaptador_real.ts (lectura con cf_lectura; escritura con cf_pagos_web).
 *
 * Toda operación de escritura que no se puede hacer LANZA ErrorPagosBd (código y mensaje llano); la ruta lo devuelve
 * tal cual. Nunca se reintenta.
 *
 * Solo sintaxis TypeScript borrable.
 */
import { errorPagos } from './errores_bd.ts';
import type { AlmacenPagos, CopiaVencimiento, FormaPago, FuentePagos, ItemMarca, MarcaPago } from './pagos.ts';

export interface AlmacenPagosAsync {
  /** Fecha de referencia (FIXTURES: la de la semilla; REAL: hoy en Madrid). */
  hoy(): string;
  /** null si se puede escribir; si no, por qué (REAL sin credencial de pagos). */
  sinEscritura: { codigo: 'CREDENCIAL_PAGOS_AUSENTE'; mensaje: string } | null;
  fuente(): Promise<FuentePagos>;
  /**
   * Todo o nada. `copia`: fecha e importe actuales de cada vencimiento (solo FIXTURES, donde simula el trigger; en REAL
   * los copia la BD y la web no los envía).
   */
  marcar(items: readonly ItemMarca[], autor: string, copia: (clave: string) => CopiaVencimiento | undefined): Promise<MarcaPago[]>;
  anular(marcaId: string, autor: string): Promise<MarcaPago>;
  fijarForma(cif: string, forma: FormaPago | null, autor: string): Promise<{ cif: string; forma: FormaPago; por_defecto: boolean }>;
  cerrar?(): Promise<void>;
}

/** FIXTURES: el almacén en memoria con la misma interfaz que REAL (los códigos de error, como excepción). */
export function almacenFixtures(a: AlmacenPagos): AlmacenPagosAsync {
  const o = <T>(r: T | string): T => { if (typeof r === 'string') throw errorPagos(r as Parameters<typeof errorPagos>[0]); return r; };
  return {
    hoy: () => a.hoy,
    sinEscritura: null,
    fuente: async () => a.fuente(),
    marcar: async (items, autor, copia) => o(a.marcar(items, autor, copia)),
    anular: async (id, autor) => o(a.anular(id, autor)),
    fijarForma: async (cif, forma, autor) => o(a.fijarForma(cif, forma, autor)),
  };
}
