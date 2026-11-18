/**
 * H6-REAL: sentencias de las tablas de pagos (migración 35). Parámetros siempre enlazados; farmacia fija PIO ($1).
 *
 *  - Lectura con cf_lectura (SELECT en vencimientos_marcas_pago, proveedores_forma_pago y pagos_historial), dentro de
 *    una transacción READ ONLY que termina en ROLLBACK (server/adaptador_real.ts).
 *  - Escritura con cf_pagos_web (SELECT, INSERT y UPDATE en las dos tablas; SELECT en el historial; NO lee facturas ni
 *    vencimientos), con set_config('cf.autor', …, true) en cada transacción (server/pagos/adaptador_real.ts).
 *  - La web nunca envía fecha_vencimiento ni importe de la marca: los copia el trigger.
 *  - Único UPDATE: anulada = true sobre una fila vigente. Corregir = anular + insertar en la misma transacción. Nunca
 *    DELETE. ON CONFLICT repite el predicado de los índices parciales (… where not anulada).
 *  - Ids comparados como texto (id::text = $n): no se presupone su tipo.
 *
 * Solo sintaxis TypeScript borrable.
 */

const MARCA = 'id, farmacia, factura_id, vencimiento_orden, fecha_vencimiento, importe, fecha_pago, forma, origen, anulada, created_at, updated_at';
const FORMA = 'id, farmacia, cif, forma, anulada, created_at, updated_at';

/** Marcas vigentes de la farmacia, cruzadas con el vencimiento actual (factura_id, orden) de una factura de la farmacia. */
const A_REVISAR = `from public.vencimientos_marcas_pago m
left join public.facturas f on f.id = m.factura_id and f.farmacia = m.farmacia
left join public.facturas_vencimientos v on v.factura_id = f.id and v.orden = m.vencimiento_orden
where m.farmacia = $1 and not m.anulada`;

export const SQL_PAGOS = {
  // --- Lectura (cf_lectura) -------------------------------------------------------------------------------------------
  marcasVigentes: `select ${MARCA} from public.vencimientos_marcas_pago where farmacia = $1 and not anulada`,
  formasVigentes: `select ${FORMA} from public.proveedores_forma_pago where farmacia = $1 and not anulada`,
  historial: 'select id, tabla, registro_id, farmacia, operacion, antes, despues, autor, created_at from public.pagos_historial '
    + 'where farmacia = $1 order by created_at desc, id desc limit 300',
  /** check:real: solo recuentos. A revisar = huérfanas + fecha o importe distintos del vencimiento actual. */
  diagnostico: 'select '
    + '(select count(*) from public.vencimientos_marcas_pago where farmacia = $1 and not anulada) as marcas_vigentes, '
    + '(select count(*) from public.vencimientos_marcas_pago where farmacia = $1 and anulada) as marcas_anuladas, '
    + `(select count(*) ${A_REVISAR} and (v.factura_id is null or v.fecha_vencimiento::date is distinct from m.fecha_vencimiento::date `
    + 'or v.importe is distinct from m.importe)) as marcas_a_revisar, '
    + `(select count(*) ${A_REVISAR} and v.factura_id is null) as marcas_huerfanas, `
    + '(select count(*) from public.proveedores_forma_pago where farmacia = $1 and not anulada) as formas_vigentes, '
    + '(select count(*) from public.pagos_historial where farmacia = $1) as historial',

  // --- Escritura (cf_pagos_web) ---------------------------------------------------------------------------------------
  autor: "select set_config('cf.autor', $1, true)",
  insertarMarcas: 'insert into public.vencimientos_marcas_pago (farmacia, factura_id, vencimiento_orden, fecha_pago, forma, origen) '
    + 'select $1::text, u.factura_id, u.vencimiento_orden, u.fecha_pago, u.forma, u.origen '
    + 'from unnest($2::uuid[], $3::int[], $4::date[], $5::text[], $6::text[]) as u(factura_id, vencimiento_orden, fecha_pago, forma, origen) '
    + `on conflict (farmacia, factura_id, vencimiento_orden) where not anulada do nothing returning ${MARCA}`,
  marcaPorId: 'select id, anulada from public.vencimientos_marcas_pago where id::text = $1 and farmacia = $2',
  anularMarca: `update public.vencimientos_marcas_pago set anulada = true where id::text = $1 and farmacia = $2 and not anulada returning ${MARCA}`,
  formaBloqueo: `select ${FORMA} from public.proveedores_forma_pago where farmacia = $1 and cif = $2 and not anulada for update`,
  anularForma: `update public.proveedores_forma_pago set anulada = true where id::text = $1 and not anulada returning ${FORMA}`,
  insertarForma: 'insert into public.proveedores_forma_pago (farmacia, cif, forma) values ($1, $2, $3) '
    + `on conflict (farmacia, cif) where not anulada do nothing returning ${FORMA}`,
  /** check:real con cf_pagos_web (READ ONLY): la credencial conecta y lee su tabla. */
  prueba: 'select count(*) as formas from public.proveedores_forma_pago where farmacia = $1',
} as const;

export const COLUMNAS_DIAGNOSTICO_PAGOS = ['marcas_vigentes', 'marcas_anuladas', 'marcas_a_revisar', 'marcas_huerfanas', 'formas_vigentes', 'historial'] as const;
