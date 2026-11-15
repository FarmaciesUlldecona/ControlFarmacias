/**
 * H6: API /api/pagos/* de la pantalla Vencimientos.
 *
 *   GET  /api/pagos/vencimientos                lista con estado, forma de pago y marca vigente (+ proveedores e historial)
 *   POST /api/pagos/marcas                      «Marcar pagado»: { vencimientos, fecha_pago, forma | null }
 *   POST /api/pagos/marcas/domiciliados         «Confirmar domiciliados»: { vencimientos } (solo DOMICILIADO_PREVISTO;
 *                                               fecha = la de vencimiento, forma DOMICILIACION)
 *   PUT  /api/pagos/marcas/:marca_id/anular     anular una marca { confirmar: true } (nunca se borra)
 *   PUT  /api/pagos/formas/:cif                 forma de pago del proveedor { forma | null } (null = por defecto)
 *
 * Toda ruta exige sesión; la escritura, además, Origin del mismo sitio (obligatorio), Sec-Fetch-Site same-origin si
 * viene y JSON. Nunca DELETE ni PATCH.
 *
 * FIXTURES: almacén en memoria con la semilla web/fixtures/pagos/pagos.json (y su fecha de referencia).
 * REAL: sin almacén (las tablas no existen): la lista sale del contrato `vencimientos` (cf_lectura, solo lectura) sin
 * marcas ni formas configuradas, y toda escritura responde 503 H6_PENDIENTE «Pendiente de tablas en Supabase».
 * La web nunca escribe en facturas, vencimientos ni conciliación.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import type { Contrato } from '../contrato.ts';
import { origenEscrituraValido } from '../rrhh/rutas.ts';
import {
  ERROR_H6_PENDIENTE, TEXTO_H6_PENDIENTE, construirPantalla, crearAlmacenPagos, esCifComparable, formaPorDefectoMarca, validarConfirmacion,
  validarDomiciliados, validarFormaProveedor, validarMarcar, type AlmacenPagos, type FormaPago, type ItemMarca,
  type PantallaVencimientosDTO, type SemillaPagos,
} from './pagos.ts';

export const PREFIJO_PAGOS = '/api/pagos/';
export const RUTA_SEMILLA_PAGOS = join(import.meta.dirname, '..', '..', '..', 'fixtures', 'pagos', 'pagos.json');

export function leerSemillaPagos(): SemillaPagos {
  const { hoy, formas, marcas } = JSON.parse(readFileSync(RUTA_SEMILLA_PAGOS, 'utf8')) as SemillaPagos;
  return { hoy, formas, marcas };
}

/** Rutas de escritura de H6 (método + patrón). */
export function esEscrituraPagos(metodo: string, ruta: string): boolean {
  if (metodo === 'POST') return ruta === '/api/pagos/marcas' || ruta === '/api/pagos/marcas/domiciliados';
  if (metodo === 'PUT') return /^\/api\/pagos\/marcas\/[0-9a-f-]{36}\/anular$/.test(ruta) || /^\/api\/pagos\/formas\/[A-Z0-9]{5,20}$/.test(ruta);
  return false;
}

const HTTP_ERROR: Readonly<Record<string, number>> = {
  VENCIMIENTO_NO_ENCONTRADO: 404, YA_PAGADO: 409, NO_DOMICILIADO_PREVISTO: 409, FORMA_SIN_CIF: 400,
  MARCA_NO_ENCONTRADA: 404, MARCA_YA_ANULADA: 409, CIF_NO_ENCONTRADO: 404, SIN_CAMBIOS: 409,
};
const MENSAJE_ERROR: Readonly<Record<string, string>> = {
  VENCIMIENTO_NO_ENCONTRADO: 'Algún vencimiento no existe o no es de PIO. Pulsa Actualizar.',
  YA_PAGADO: 'Algún vencimiento ya está marcado como pagado. No se ha marcado ninguno.',
  NO_DOMICILIADO_PREVISTO: 'Solo se confirman vencimientos domiciliados ya vencidos y sin marca. No se ha confirmado ninguno.',
  FORMA_SIN_CIF: 'Alguna factura no tiene CIF: elige la forma de pago.',
  MARCA_NO_ENCONTRADA: 'Esa marca de pago no existe.',
  MARCA_YA_ANULADA: 'Esa marca de pago ya está anulada.',
  CIF_NO_ENCONTRADO: 'Ese CIF no aparece en los vencimientos de PIO.',
  SIN_CAMBIOS: 'Ese proveedor ya tiene esa forma de pago.',
};

/** Hoy en el reloj del servidor (fecha local). */
function hoyServidor(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export interface OpcionesPagos {
  modo: 'FIXTURES' | 'REAL';
  contrato: Contrato;
  sesionValida: (req: FastifyRequest) => boolean;
  /** Autor de marcas y cambios (historial). */
  quien: string;
  /** FIXTURES: por defecto, uno nuevo con la semilla. REAL: nunca (tablas pendientes). */
  almacen?: AlmacenPagos;
}

export function registrarPagos(app: FastifyInstance, opciones: OpcionesPagos): void {
  const { modo, contrato, sesionValida, quien } = opciones;
  const almacen: AlmacenPagos | null = modo === 'FIXTURES' ? opciones.almacen ?? crearAlmacenPagos(leerSemillaPagos()) : null;

  app.addHook('onRequest', async (req, reply) => {
    const ruta = req.url.split('?')[0];
    if (!ruta.startsWith(PREFIJO_PAGOS)) return;
    if (!sesionValida(req)) return reply.code(401).header('cache-control', 'no-store').send({ error: 'NO_AUTENTICADO' });
    reply.header('cache-control', 'no-store');
    if (req.method === 'GET' || req.method === 'HEAD') return;
    if (!esEscrituraPagos(req.method, ruta)) return reply.code(405).send({ error: 'SOLO_LECTURA' });
    if (!origenEscrituraValido(req)) return reply.code(403).send({ error: 'ORIGEN_NO_PERMITIDO' });
    if (!/^application\/json\b/i.test(req.headers['content-type'] ?? '')) return reply.code(415).send({ error: 'SOLO_JSON' });
  });

  const error = (reply: FastifyReply, codigo: string) =>
    reply.code(HTTP_ERROR[codigo] ?? 400).send({ error: codigo, ...(MENSAJE_ERROR[codigo] ? { mensaje: MENSAJE_ERROR[codigo] } : {}) });
  const pendiente = (reply: FastifyReply) => reply.code(503).send({ error: ERROR_H6_PENDIENTE, mensaje: TEXTO_H6_PENDIENTE });
  const noValida = (reply: FastifyReply, errores: Record<string, string>) => reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores });
  const pantalla = async (): Promise<PantallaVencimientosDTO> =>
    construirPantalla(await contrato.vencimientos(), almacen?.fuente() ?? null, { hoy: almacen?.hoy ?? hoyServidor(), modo });

  app.get('/api/pagos/vencimientos', pantalla);

  app.post('/api/pagos/marcas', async (req, reply) => {
    if (almacen === null) return pendiente(reply);
    const v = validarMarcar(req.body, almacen.hoy);
    if (!v.ok) return noValida(reply, v.errores);
    const filas = new Map((await pantalla()).filas.map((f) => [f.vencimiento_id, f]));
    const items: ItemMarca[] = [];
    for (const id of v.datos.vencimientos) {
      const f = filas.get(id);
      if (!f) return error(reply, 'VENCIMIENTO_NO_ENCONTRADO');
      if (f.marca !== null) return error(reply, 'YA_PAGADO');
      // Forma por defecto: la del proveedor; un abono, COMPENSACION_ABONO (H6-3; también sin CIF).
      const defecto = formaPorDefectoMarca(f);
      if (v.datos.forma === null && defecto === 'SIN_DETERMINAR') return error(reply, 'FORMA_SIN_CIF');
      items.push({ vencimiento_id: id, fecha_pago: v.datos.fecha_pago, forma: v.datos.forma ?? (defecto as FormaPago), origen: 'MANUAL' });
    }
    const r = almacen.marcar(items, quien);
    return typeof r === 'string' ? error(reply, r) : reply.code(201).send({ marcas: r });
  });

  app.post('/api/pagos/marcas/domiciliados', async (req, reply) => {
    if (almacen === null) return pendiente(reply);
    const v = validarDomiciliados(req.body);
    if (!v.ok) return noValida(reply, v.errores);
    const filas = new Map((await pantalla()).filas.map((f) => [f.vencimiento_id, f]));
    const items: ItemMarca[] = [];
    for (const id of v.vencimientos) {
      const f = filas.get(id);
      if (!f) return error(reply, 'VENCIMIENTO_NO_ENCONTRADO');
      if (f.estado_pago !== 'DOMICILIADO_PREVISTO' || f.fecha_vencimiento === null) return error(reply, 'NO_DOMICILIADO_PREVISTO');
      items.push({ vencimiento_id: id, fecha_pago: f.fecha_vencimiento.slice(0, 10), forma: 'DOMICILIACION', origen: 'DOMICILIADOS' });
    }
    const r = almacen.marcar(items, quien);
    return typeof r === 'string' ? error(reply, r) : reply.code(201).send({ marcas: r });
  });

  app.put<{ Params: { id: string } }>('/api/pagos/marcas/:id/anular', async (req, reply) => {
    if (almacen === null) return pendiente(reply);
    if (!validarConfirmacion(req.body)) return noValida(reply, { confirmar: 'Confirma la anulación' });
    const r = almacen.anular(req.params.id, quien);
    return typeof r === 'string' ? error(reply, r) : { marca: r };
  });

  app.put<{ Params: { cif: string } }>('/api/pagos/formas/:cif', async (req, reply) => {
    if (almacen === null) return pendiente(reply);
    const v = validarFormaProveedor(req.body);
    if (!v.ok || !esCifComparable(req.params.cif)) return noValida(reply, v.ok ? { cif: 'CIF no válido' } : v.errores);
    const p = await pantalla();
    if (!p.proveedores.some((x) => x.cif === req.params.cif)) return error(reply, 'CIF_NO_ENCONTRADO');
    const r = almacen.fijarForma(req.params.cif, v.forma, quien);
    return typeof r === 'string' ? error(reply, r) : r;
  });
}
