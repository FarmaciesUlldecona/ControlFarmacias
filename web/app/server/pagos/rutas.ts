/**
 * H6: API /api/pagos/* de la pantalla Vencimientos.
 *
 *   GET  /api/pagos/vencimientos                lista con estado, forma de pago y marca vigente (+ proveedores, huérfanas e historial)
 *   POST /api/pagos/marcas                      «Marcar pagado»: { vencimientos: [{factura_id, orden}], fecha_pago, forma | null }
 *   POST /api/pagos/marcas/domiciliados         «Confirmar domiciliados»: { vencimientos: [{factura_id, orden}] } (solo
 *                                               DOMICILIADO_PREVISTO ya vencido; fecha = la de vencimiento, forma DOMICILIACION)
 *   PUT  /api/pagos/marcas/:marca_id/anular     anular una marca { confirmar: true } (nunca se borra)
 *   PUT  /api/pagos/formas/:cif                 forma de pago del proveedor { forma | null } (null = por defecto)
 *
 * Toda ruta exige sesión; la escritura, además, Origin del mismo sitio (obligatorio), Sec-Fetch-Site same-origin si
 * viene y JSON. Nunca DELETE ni PATCH. El vencimiento se identifica por (factura_id, orden), nunca por su id.
 *
 * H6-REAL: el mismo flujo en los dos modos (AlmacenPagosAsync):
 *  - FIXTURES: almacén en memoria con la semilla web/fixtures/pagos/pagos.json (y su fecha de referencia).
 *  - REAL: vencimientos y marcas leídos con cf_lectura; escritura con cf_pagos_web (server/pagos/adaptador_real.ts). Sin
 *    la credencial de pagos, la lectura funciona y la escritura responde 503 «Falta configurar la credencial de pagos».
 * Antes de escribir, las reglas de la web (prepararMarcas / prepararDomiciliados) sobre la pantalla recién leída. Los
 * errores (de la web o de la BD) llegan como mensaje llano; la transacción ya está deshecha y no se reintenta.
 * La web nunca escribe en facturas, vencimientos ni conciliación.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import type { Contrato } from '../contrato.ts';
import { origenEscrituraValido } from '../rrhh/rutas.ts';
import { almacenFixtures, type AlmacenPagosAsync } from './almacen.ts';
import { errorPagos, traducirErrorPagos } from './errores_bd.ts';
import {
  construirPantalla, crearAlmacenPagos, esCifComparable, prepararDomiciliados, prepararMarcas, validarConfirmacion,
  validarDomiciliados, validarFormaProveedor, validarMarcar, type FilaVencimientoPago, type PantallaVencimientosDTO, type SemillaPagos,
} from './pagos.ts';

export const PREFIJO_PAGOS = '/api/pagos/';
export const RUTA_SEMILLA_PAGOS = join(import.meta.dirname, '..', '..', '..', 'fixtures', 'pagos', 'pagos.json');

export function leerSemillaPagos(): SemillaPagos {
  const { hoy, formas, marcas } = JSON.parse(readFileSync(RUTA_SEMILLA_PAGOS, 'utf8')) as SemillaPagos;
  return { hoy, formas, marcas };
}

/** Id de marca en la ruta de anular: uuid o entero (no se presupone el tipo de la columna). */
const ID_MARCA = /^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[1-9]\d{0,17})$/;

/** Rutas de escritura de H6 (método + patrón). */
export function esEscrituraPagos(metodo: string, ruta: string): boolean {
  if (metodo === 'POST') return ruta === '/api/pagos/marcas' || ruta === '/api/pagos/marcas/domiciliados';
  if (metodo === 'PUT') {
    const m = /^\/api\/pagos\/marcas\/([^/]+)\/anular$/.exec(ruta);
    return (m !== null && ID_MARCA.test(m[1])) || /^\/api\/pagos\/formas\/[A-Z0-9]{5,20}$/.test(ruta);
  }
  return false;
}

export interface OpcionesPagos {
  modo: 'FIXTURES' | 'REAL';
  contrato: Contrato;
  sesionValida: (req: FastifyRequest) => boolean;
  /** Autor de marcas y cambios (historial; en REAL, cf.autor de cada transacción). */
  quien: string;
  /** FIXTURES: por defecto, uno nuevo con la semilla. REAL: obligatorio (server/pagos/adaptador_real.ts). */
  almacen?: AlmacenPagosAsync;
}

/** Devuelve la pantalla de vencimientos (con sus marcas): la usa el cashflow (H7). */
export function registrarPagos(app: FastifyInstance, opciones: OpcionesPagos): { pantalla: () => Promise<PantallaVencimientosDTO> } {
  const { modo, contrato, sesionValida, quien } = opciones;
  if (modo === 'REAL' && !opciones.almacen) throw new Error('PAGOS_REAL_SIN_ALMACEN');
  const almacen: AlmacenPagosAsync = opciones.almacen ?? almacenFixtures(crearAlmacenPagos(leerSemillaPagos()));

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

  /** Error de la web o de la BD → { error, mensaje } llano (nunca el texto técnico). */
  const fallo = (reply: FastifyReply, e: unknown) => {
    const t = traducirErrorPagos(e);
    if (t.codigo === 'ERROR_BD') app.log.error({ msg: `pagos: ${(e instanceof Error ? e.message : String(e)).split('\n')[0].slice(0, 200)}` });
    return reply.code(t.http).send({ error: t.codigo, mensaje: t.mensaje });
  };
  const noValida = (reply: FastifyReply, errores: Record<string, string>) => reply.code(400).send({ error: 'DATOS_NO_VALIDOS', errores });
  const pantalla = async (): Promise<PantallaVencimientosDTO> =>
    construirPantalla(await contrato.vencimientos(), await almacen.fuente(), { modo, mensajeEscritura: almacen.sinEscritura?.mensaje ?? null });
  /** Sin credencial de pagos: 503 antes de leer nada. */
  const escritura = async (reply: FastifyReply, trabajo: () => Promise<unknown>) => {
    if (almacen.sinEscritura) { const e = errorPagos(almacen.sinEscritura.codigo); return reply.code(e.http).send({ error: e.codigo, mensaje: e.mensaje }); }
    try { return await trabajo(); } catch (e) { return fallo(reply, e); }
  };
  const porClave = (p: PantallaVencimientosDTO) => new Map(p.filas.flatMap((f): [string, FilaVencimientoPago][] => (f.clave === null ? [] : [[f.clave, f]])));

  app.get('/api/pagos/vencimientos', pantalla);

  app.post('/api/pagos/marcas', (req, reply) => escritura(reply, async () => {
    const v = validarMarcar(req.body, almacen.hoy());
    if (!v.ok) return noValida(reply, v.errores);
    const filas = porClave(await pantalla());
    const p = prepararMarcas(filas, v.datos);
    if (!p.ok) throw errorPagos(p.codigo);
    return reply.code(201).send({ marcas: await almacen.marcar(p.items, quien, (k) => filas.get(k)) });
  }));

  app.post('/api/pagos/marcas/domiciliados', (req, reply) => escritura(reply, async () => {
    const v = validarDomiciliados(req.body);
    if (!v.ok) return noValida(reply, v.errores);
    const filas = porClave(await pantalla());
    const p = prepararDomiciliados(filas, v.vencimientos, almacen.hoy());
    if (!p.ok) throw errorPagos(p.codigo);
    return reply.code(201).send({ marcas: await almacen.marcar(p.items, quien, (k) => filas.get(k)) });
  }));

  app.put<{ Params: { id: string } }>('/api/pagos/marcas/:id/anular', (req, reply) => escritura(reply, async () => {
    if (!validarConfirmacion(req.body)) return noValida(reply, { confirmar: 'Confirma la anulación' });
    return { marca: await almacen.anular(req.params.id, quien) };
  }));

  app.put<{ Params: { cif: string } }>('/api/pagos/formas/:cif', (req, reply) => escritura(reply, async () => {
    const v = validarFormaProveedor(req.body);
    if (!v.ok || !esCifComparable(req.params.cif)) return noValida(reply, v.ok ? { cif: 'CIF no válido' } : v.errores);
    const p = await pantalla();
    if (!p.proveedores.some((x) => x.cif === req.params.cif)) throw errorPagos('CIF_NO_ENCONTRADO');
    return almacen.fijarForma(req.params.cif, v.forma, quien);
  }));
  return { pantalla };
}
