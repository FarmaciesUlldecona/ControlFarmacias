/**
 * H7-AP1: sentencias de los apuntes manuales de Cashflow (migración 40, docs/referencia/ESQUEMA_CASHFLOW.md). Parámetros
 * siempre enlazados.
 *
 *  - Lectura con cf_lectura (SELECT en cf_cashflow_conceptos, _recurrentes y _apuntes; EXECUTE de cf_cashflow_ocurrencias;
 *    misma RLS: PIO y RITA), dentro de la transacción READ ONLY y REPEATABLE READ del cashflow (server/adaptador_real.ts).
 *  - Escritura con cf_cashflow_web (SELECT e INSERT en las tres tablas; UPDATE solo de anulado, motivo_anulacion y, en
 *    apuntes, la sustitución), una transacción por operación con set_config('cf.autor', …, true) dentro. Nunca DELETE.
 *    La web no envía farmacia, autor ni fechas de alta o anulación: las pone el trigger.
 *  - ON CONFLICT: el esquema no documenta los índices únicos parciales (nombre de concepto sin mayúsculas ni espacios
 *    repetidos, CIF por cuenta, una sustitución por vencimiento): repetir un predicado que no coincide haría fallar
 *    cualquier alta, así que no se usa; un 23505 llega como «Ya existe» (errores_bd.ts).
 *
 * Solo sintaxis TypeScript borrable.
 */

const COMUNES = 'id::text as id, cuenta, farmacia, categoria, autor, creado_at, anulado, anulado_por, anulado_at, motivo_anulacion';
export const COLUMNAS_CONCEPTO = `${COMUNES}, nombre, proveedor_cif`;
export const COLUMNAS_RECURRENTE = `${COMUNES}, concepto, importe::text as importe, nota, frecuencia, dia, inicio::text as inicio, fin::text as fin`;
export const COLUMNAS_APUNTE = `${COMUNES}, fecha::text as fecha, concepto, importe::text as importe, nota, recurrente_id::text as recurrente_id, `
  + 'fecha_ocurrencia::text as fecha_ocurrencia, sustituido_factura_id::text as sustituido_factura_id, sustituido_vencimiento_orden';

export const OBJETOS_APUNTES = ['cf_cashflow_conceptos', 'cf_cashflow_recurrentes', 'cf_cashflow_apuntes', 'cf_cashflow_ocurrencias'] as const;

/** Lectura (cf_lectura). $1 = cuentas de la pantalla (text[]). Ocurrencias: $1 desde, $2 hasta (date). */
export const SQL_LECTURA_APUNTES = {
  conceptos: `select ${COLUMNAS_CONCEPTO} from public.cf_cashflow_conceptos where cuenta = any($1::text[]) order by creado_at, id`,
  recurrentes: `select ${COLUMNAS_RECURRENTE} from public.cf_cashflow_recurrentes where cuenta = any($1::text[]) order by creado_at, id`,
  apuntes: `select ${COLUMNAS_APUNTE} from public.cf_cashflow_apuntes where cuenta = any($1::text[]) order by creado_at, id`,
  ocurrencias: 'select o.recurrente_id::text as recurrente_id, o.cuenta, o.farmacia, o.categoria, o.concepto, o.importe::text as importe, o.fecha::text as fecha '
    + 'from public.cf_cashflow_ocurrencias($1::date, $2::date) o order by o.fecha, o.recurrente_id',
  /** check:real: solo recuentos. $1 = hoy, $2 = hoy + 12 meses (ocurrencias). */
  diagnostico: 'select '
    + '(select count(*) from public.cf_cashflow_apuntes where not anulado and recurrente_id is null) as apuntes_vigentes, '
    + '(select count(*) from public.cf_cashflow_apuntes where anulado and recurrente_id is null) as apuntes_anulados, '
    + '(select count(*) from public.cf_cashflow_apuntes where sustituido_factura_id is not null) as apuntes_sustituidos, '
    + '(select count(*) from public.cf_cashflow_apuntes where not anulado and recurrente_id is not null) as ocurrencias_anuladas, '
    + '(select count(*) from public.cf_cashflow_recurrentes where not anulado) as recurrentes_vigentes, '
    + '(select count(*) from public.cf_cashflow_recurrentes where anulado) as recurrentes_anulados, '
    + '(select count(*) from public.cf_cashflow_ocurrencias($1::date, $2::date)) as ocurrencias_12_meses, '
    + '(select count(*) from public.cf_cashflow_conceptos where not anulado) as conceptos_nuevos, '
    + '(select count(*) from public.cf_cashflow_conceptos where anulado) as conceptos_anulados',
} as const;
export const COLUMNAS_DIAGNOSTICO_APUNTES = ['apuntes_vigentes', 'apuntes_anulados', 'apuntes_sustituidos', 'ocurrencias_anuladas',
  'recurrentes_vigentes', 'recurrentes_anulados', 'ocurrencias_12_meses', 'conceptos_nuevos', 'conceptos_anulados'] as const;

/** Escritura (cf_cashflow_web). */
export const SQL_ESCRITURA_APUNTES = {
  autor: "select set_config('cf.autor', $1, true)",
  insertarConcepto: 'insert into public.cf_cashflow_conceptos (cuenta, categoria, nombre, proveedor_cif) values ($1, $2, $3, $4) '
    + `returning ${COLUMNAS_CONCEPTO}`,
  insertarApunte: 'insert into public.cf_cashflow_apuntes (cuenta, categoria, concepto, fecha, importe, nota) '
    + `values ($1, $2, $3, $4::date, $5::numeric, $6) returning ${COLUMNAS_APUNTE}`,
  insertarRecurrente: 'insert into public.cf_cashflow_recurrentes (cuenta, categoria, concepto, importe, nota, frecuencia, dia, inicio, fin) '
    + `values ($1, $2, $3, $4::numeric, $5, $6, $7::int, $8::date, $9::date) returning ${COLUMNAS_RECURRENTE}`,
  /** Anulación de una ocurrencia: cuenta, categoría, concepto y fecha los copia el trigger del recurrente; sin importe. */
  anularOcurrencia: 'insert into public.cf_cashflow_apuntes (recurrente_id, fecha_ocurrencia, nota, sustituido_factura_id, sustituido_vencimiento_orden) '
    + `values ($1::uuid, $2::date, $3, $4::uuid, $5::int) returning ${COLUMNAS_APUNTE}`,
  anularApunte: 'update public.cf_cashflow_apuntes set anulado = true, motivo_anulacion = $2 '
    + `where id = $1::uuid and not anulado and recurrente_id is null returning ${COLUMNAS_APUNTE}`,
  /** Sustitución confirmada por Marc: se guarda al anular el apunte suelto. */
  sustituirApunte: 'update public.cf_cashflow_apuntes set anulado = true, motivo_anulacion = $2, sustituido_factura_id = $3::uuid, sustituido_vencimiento_orden = $4::int '
    + `where id = $1::uuid and not anulado and recurrente_id is null returning ${COLUMNAS_APUNTE}`,
  anularRecurrente: 'update public.cf_cashflow_recurrentes set anulado = true, motivo_anulacion = $2 '
    + `where id = $1::uuid and not anulado returning ${COLUMNAS_RECURRENTE}`,
  apuntePorId: 'select id::text as id, anulado, recurrente_id::text as recurrente_id from public.cf_cashflow_apuntes where id = $1::uuid',
  recurrentePorId: 'select id::text as id, anulado from public.cf_cashflow_recurrentes where id = $1::uuid',
  /** check:real con cf_cashflow_web (READ ONLY): la credencial conecta y lee sus tablas. Solo el recuento. */
  prueba: 'select (select count(*) from public.cf_cashflow_conceptos) + (select count(*) from public.cf_cashflow_recurrentes) '
    + '+ (select count(*) from public.cf_cashflow_apuntes) as filas',
} as const;
