/**
 * TA-REAL: adaptador RRHH_REAL del módulo Trabajadores. Tablas reales de la migración 31 con el rol
 * cf_trabajadores_web (SELECT, INSERT y UPDATE; sin DELETE). Solo lo ejecuta Pío (dev:real / check:real).
 *
 *  - Credencial: CF_TRAB_USER y CF_TRAB_PASSWORD en web/app/.env.web (gitignored); host, puerto, base y CA
 *    compartidos con cf_lectura (CF_LECTURA_HOST, CF_LECTURA_PORT, CF_LECTURA_DB, CF_LECTURA_CA). Si falta la
 *    credencial, el módulo muestra «Falta configurar la credencial de Trabajadores» y no conecta.
 *  - Pool propio (máx. 2 conexiones; el rol admite 5) y TLS con verificación de la CA existente (verify-full).
 *  - Lectura: transacción READ ONLY que termina siempre en ROLLBACK.
 *  - Escritura: cada una en su transacción, con set_config('cf.autor', <autor>, true) dentro (nunca de sesión). Ante
 *    cualquier error, ROLLBACK y mensaje llano (errores_bd.ts). Nunca se reintenta solo.
 *  - Nada se borra: fichas con fecha_baja o anulada; eventos solo INSERT / UPDATE. Goma y deshacer de pintados
 *    nuevos desactivados (anularEventos = false) hasta que exista eventos_calendario.anulado.
 *  - Rellenar: INSERT … ON CONFLICT (trabajadora_id, fecha, franja) DO NOTHING, por lotes (cada sentencia muy por
 *    debajo de los 60 s de statement_timeout del rol). Confirmar y anotar: UPDATE por lotes.
 *  - Horas: se leen de v_eventos_calendario_horas (horas_efectivas).
 *  - Historial: trabajadores_historial (lo escribe el trigger). Las filas de una misma transacción comparten
 *    created_at: cada grupo es un cambio. El origen (Pintado, Rellenado…) lo aporta la sesión si el cambio se hizo en
 *    ella; si no, se deduce de las filas (inferirOrigen). Deshacer: solo los cambios de esta sesión del servidor.
 *
 * Solo sintaxis TypeScript borrable.
 */
import { existsSync, readFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { isAbsolute, join } from 'node:path';
import { parseEnv } from 'node:util';
import pg from 'pg';
import { RUTA_CA_DEFECTO, RUTA_ENV_WEB, leerCertificadoCA } from '../adaptador_real.ts';
import {
  CATEGORIAS, CONVENIO_ANUAL, FARMACIAS_RRHH, JORNADAS, MENSAJE_FALTA_CREDENCIAL, accionActualizacion, aniosConvenioQueFaltan,
  camposAlta, computaConvenio, diferencias, farmaciasDe, objetivosAnuales, ordenFichas,
  type ConvenioAnual, type EventoHistorial, type FarmaciaRrhh, type Festivo, type GuardiaFarmacia, type Trabajadora,
} from './contrato.ts';
import {
  ESTADOS_EVENTO, FECHA_MAX, FRANJAS, TIPOS_EVENTO, construirCambio, horasEfectivas, inferirOrigen, notasProximas, planDeshacer,
  planificar, resumen,
  type CambioCalendario, type EventoCalendario, type Franja, type Operacion, type ResultadoCambioDTO,
} from './eventos.ts';
import { traducirErrorBd } from './errores_bd.ts';
import type { AdaptadorRrhh } from './adaptador_fixtures.ts';

// ---------------------------------------------------------------------------
// Configuración (credencial en .env.web; Code nunca la lee ni la crea)
// ---------------------------------------------------------------------------

/** Variables nuevas de .env.web (solo Trabajadores). */
export const VARIABLES_TRAB = ['CF_TRAB_USER', 'CF_TRAB_PASSWORD'] as const;
/** Compartidas con cf_lectura. */
export const VARIABLES_COMPARTIDAS = ['CF_LECTURA_HOST', 'CF_LECTURA_PORT', 'CF_LECTURA_DB'] as const;
export const ROL_TRABAJADORES = 'cf_trabajadores_web';
export const MAX_CONEXIONES = 2;
/** Filas por sentencia al insertar o actualizar eventos (un año de 13 personas son unas 6.800 franjas). */
export const TAM_LOTE = 500;

export type ConfigRrhh = { ok: true; config: pg.PoolConfig } | { ok: false; codigo: string; mensaje: string };

/** Lee .env.web (solo el modo REAL, ejecutado por Pío). Sin fichero: objeto vacío (falta la credencial). */
export function leerEnvWeb(ruta: string = RUTA_ENV_WEB): Record<string, string | undefined> {
  return existsSync(ruta) ? parseEnv(readFileSync(ruta, 'utf8')) : {};
}

const OID = { INT8: 20, NUMERIC: 1700, DATE: 1082, TIMESTAMP: 1114, TIMESTAMPTZ: 1184 };
/** int8, numeric y fechas como texto (sin pérdida ni desplazamiento de zona); el mapeo los convierte. */
const TIPOS_TEXTO = new Set<number>([OID.INT8, OID.NUMERIC, OID.DATE, OID.TIMESTAMP, OID.TIMESTAMPTZ]);
const tipos = {
  getTypeParser(oid: number, formato?: 'text' | 'binary') {
    if (TIPOS_TEXTO.has(oid)) return (v: string) => v;
    return pg.types.getTypeParser(oid, formato);
  },
};

/**
 * Configuración del pool. Falla cerrado: sin CF_TRAB_USER / CF_TRAB_PASSWORD → «Falta configurar la credencial de
 * Trabajadores»; usuario distinto de cf_trabajadores_web (directo o del pooler) → no conecta; sin CA válida → no conecta.
 */
export function configuracionRrhh(env: Record<string, string | undefined>, leerCA: (ruta: string) => string = leerCertificadoCA): ConfigRrhh {
  if (VARIABLES_TRAB.some((v) => !env[v])) return { ok: false, codigo: 'CREDENCIAL_TRABAJADORES_AUSENTE', mensaje: MENSAJE_FALTA_CREDENCIAL };
  const faltan = VARIABLES_COMPARTIDAS.filter((v) => !env[v]);
  if (faltan.length) return { ok: false, codigo: 'ENV_WEB_INCOMPLETO', mensaje: `Falta configurar la conexión (${faltan.join(', ')})` };
  const usuario = env.CF_TRAB_USER as string;
  if (usuario !== ROL_TRABAJADORES && !usuario.startsWith(`${ROL_TRABAJADORES}.`)) {
    return { ok: false, codigo: 'USUARIO_NO_CF_TRABAJADORES_WEB', mensaje: `La credencial de Trabajadores debe ser del rol ${ROL_TRABAJADORES}` };
  }
  const puerto = Number(env.CF_LECTURA_PORT);
  if (!Number.isInteger(puerto) || puerto <= 0 || puerto > 65535) return { ok: false, codigo: 'PUERTO_NO_VALIDO', mensaje: 'Puerto de la base de datos no válido' };
  const v = env.CF_LECTURA_CA;
  const rutaCA = !v ? RUTA_CA_DEFECTO : isAbsolute(v) ? v : join(import.meta.dirname, '..', '..', v);
  let ca: string;
  try { ca = leerCA(rutaCA); } catch (e) {
    return { ok: false, codigo: 'CERTIFICADO_CA', mensaje: `Certificado CA no válido: ${(e instanceof Error ? e.message : String(e)).split(':')[0]}` };
  }
  return {
    ok: true,
    config: {
      host: env.CF_LECTURA_HOST, port: puerto, database: env.CF_LECTURA_DB, user: usuario, password: env.CF_TRAB_PASSWORD,
      ssl: { rejectUnauthorized: true, ca }, max: MAX_CONEXIONES, idleTimeoutMillis: 30_000, connectionTimeoutMillis: 10_000,
      application_name: 'cf_web_trabajadores', types: tipos,
    },
  };
}

// ---------------------------------------------------------------------------
// Pool (inyectable: las pruebas usan uno simulado, sin conexión)
// ---------------------------------------------------------------------------

export type Fila = Record<string, unknown>;
export interface ClienteBd { query(sql: string, params?: unknown[]): Promise<{ rows: Fila[] }>; release(destruir?: boolean): void }
export interface PoolBd { connect(): Promise<ClienteBd>; end(): Promise<void> }

export function crearPoolRrhh(config: pg.PoolConfig): PoolBd {
  const pool = new pg.Pool(config);
  // Un error de una conexión inactiva no tumba el servidor; la siguiente consulta dará el error llano.
  pool.on('error', (e) => console.warn(`Trabajadores: conexión cerrada por la base de datos (${String((e as { code?: string }).code ?? '')})`));
  return {
    connect: async () => {
      const c = await pool.connect();
      return { query: (sql, params) => c.query(sql, params as unknown[]), release: (d) => c.release(d) };
    },
    end: () => pool.end(),
  };
}

// ---------------------------------------------------------------------------
// Consultas (solo tablas del módulo; parámetros siempre enlazados)
// ---------------------------------------------------------------------------

export const SQL = {
  autor: "select set_config('cf.autor', $1, true)",
  ahora: 'select now()::text as ahora',
  fichas: 'select * from public.trabajadoras where farmacia = any($1::text[]) and ($2::boolean or (not anulada and fecha_baja is null))',
  fichasTodas: 'select * from public.trabajadoras where farmacia = any($1::text[])',
  ficha: 'select * from public.trabajadoras where id = $1::uuid',
  fichaBloqueo: 'select * from public.trabajadoras where id = $1::uuid for update',
  fichasPorId: 'select * from public.trabajadoras where id = any($1::uuid[])',
  fichasPeriodo: 'select * from public.trabajadoras where farmacia = any($1::text[]) and not anulada and fecha_alta <= $3::date and (fecha_baja is null or fecha_baja >= $2::date)',
  insertarFicha: 'insert into public.trabajadoras (farmacia, nombre, categoria, tipo_jornada, horas_diarias, computa_convenio, fecha_alta) values ($1, $2, $3, $4, $5::numeric, $6, $7::date) returning *',
  editarFicha: 'update public.trabajadoras set nombre = $2, categoria = $3, tipo_jornada = $4, horas_diarias = $5::numeric, computa_convenio = $6, fecha_alta = $7::date where id = $1::uuid returning *',
  bajaFicha: 'update public.trabajadoras set fecha_baja = $2::date where id = $1::uuid returning *',
  anularFicha: 'update public.trabajadoras set anulada = true where id = $1::uuid returning *',
  convenio: 'select * from public.convenio_anual order by anio',
  crearConvenio: 'insert into public.convenio_anual (anio, jornada_max_horas, asuntos_propios_dias, permiso_medico_horas, horas_semanales_referencia, estado, fuente) '
    + 'select * from unnest($1::int[], $2::numeric[], $3::numeric[], $4::numeric[], $5::numeric[], $6::text[], $7::text[]) on conflict (anio) do nothing returning *',
  historialFicha: "select * from public.trabajadores_historial where tabla = 'trabajadoras' and registro_id = $1 order by id desc",
  historialFichas: "select * from public.trabajadores_historial where tabla = 'trabajadoras' and farmacia = any($1::text[]) order by id desc limit 200",
  eventosPeriodo: 'select * from public.v_eventos_calendario_horas where trabajadora_id = any($1::uuid[]) and fecha between $2::date and $3::date order by fecha, trabajadora_id, franja',
  notas: 'select e.* from public.v_eventos_calendario_horas e join public.trabajadoras t on t.id = e.trabajadora_id '
    + 'where e.farmacia = any($1::text[]) and e.fecha between $2::date and $3::date and e.nota is not null and not t.anulada order by e.fecha limit 500',
  eventoBloqueo: 'select * from public.eventos_calendario where id = $1::uuid for update',
  eventosCeldasBloqueo: 'select * from public.eventos_calendario where trabajadora_id = any($1::uuid[]) and fecha = any($2::date[]) for update',
  eventosRangoBloqueo: 'select * from public.eventos_calendario where trabajadora_id = any($1::uuid[]) and fecha between $2::date and $3::date for update',
  eventosPorIdBloqueo: 'select * from public.eventos_calendario where id = any($1::uuid[]) for update',
  insertarEventos: 'insert into public.eventos_calendario (trabajadora_id, farmacia, fecha, franja, tipo, estado, horas, nota) '
    + 'select * from unnest($1::uuid[], $2::text[], $3::date[], $4::text[], $5::text[], $6::text[], $7::numeric[], $8::text[]) '
    + 'on conflict (trabajadora_id, fecha, franja) do nothing returning *',
  actualizarEventos: 'update public.eventos_calendario e set tipo = v.tipo, estado = v.estado, horas = v.horas, nota = v.nota '
    + 'from unnest($1::uuid[], $2::text[], $3::text[], $4::numeric[], $5::text[]) as v(id, tipo, estado, horas, nota) where e.id = v.id returning e.*',
  historialEventos: "with g as (select distinct created_at from public.trabajadores_historial where tabla = 'eventos_calendario' and farmacia = any($1::text[]) "
    + 'order by created_at desc limit 30) select h.*, h.created_at::text as grupo from public.trabajadores_historial h join g on g.created_at = h.created_at '
    + "where h.tabla = 'eventos_calendario' and h.farmacia = any($1::text[]) order by h.created_at desc, h.id",
  guardias: 'select * from public.guardias_farmacia where farmacia = any($1::text[]) and not anulada order by fecha',
  festivos: 'select * from public.festivos where (farmacia is null or farmacia = any($1::text[])) and not anulado order by fecha',
  diagnostico: 'select (select count(*) from public.trabajadoras) as trabajadoras, (select count(*) from public.convenio_anual) as convenio_anual, '
    + '(select count(*) from public.eventos_calendario) as eventos_calendario, (select count(*) from public.guardias_farmacia) as guardias_farmacia, '
    + '(select count(*) from public.festivos) as festivos, (select count(*) from public.trabajadores_historial) as trabajadores_historial, '
    + "(select farmacias from public.cf_modulos_farmacias where modulo = 'TRABAJADORES') as modulo, "
    + "(select coalesce(array_agg(anio order by anio), '{}') from public.convenio_anual) as anios",
} as const;

// ---------------------------------------------------------------------------
// Mapeo de filas (también de antes/después jsonb del historial)
// ---------------------------------------------------------------------------

/** Instante ISO de un timestamptz en texto ('2026-11-13 10:00:00.123+00') o en jsonb ('…T…+00:00'). */
export function instante(v: unknown): string {
  if (v instanceof Date) return v.toISOString();
  const s = String(v);
  const d = new Date(s.replace(' ', 'T').replace(/([+-]\d{2})$/, '$1:00'));
  return Number.isNaN(d.getTime()) ? s : d.toISOString();
}
const fecha = (v: unknown) => (v instanceof Date ? v.toISOString() : String(v)).slice(0, 10);
const num = (v: unknown) => Number(v);
const deLista = <T extends string>(lista: readonly T[], v: unknown, campo: string): T => {
  if (!(lista as readonly unknown[]).includes(v)) throw new Error(`VALOR_NO_PREVISTO: ${campo}`);
  return v as T;
};

export function filaATrabajadora(r: Fila): Trabajadora {
  const anulada = r.anulada === true;
  const fechaBaja = r.fecha_baja === null || r.fecha_baja === undefined ? null : fecha(r.fecha_baja);
  return {
    id: String(r.id), farmacia: deLista(FARMACIAS_RRHH, r.farmacia, 'farmacia'), nombre: String(r.nombre),
    categoria: deLista(CATEGORIAS, r.categoria, 'categoria'), tipo_jornada: deLista(JORNADAS, r.tipo_jornada, 'tipo_jornada'),
    horas_diarias: num(r.horas_diarias), computa_convenio: r.computa_convenio === true, fecha_alta: fecha(r.fecha_alta),
    fecha_baja: fechaBaja, anulada, created_at: instante(r.created_at), updated_at: instante(r.updated_at), activa: !anulada && fechaBaja === null,
  };
}

/** Evento de la tabla o de la vista; sin horas_efectivas (tabla o jsonb), se calculan como la vista con la ficha. */
export function filaAEvento(r: Fila, ficha: Pick<Trabajadora, 'tipo_jornada' | 'horas_diarias'> | undefined): EventoCalendario {
  const horas = r.horas === null || r.horas === undefined ? null : num(r.horas);
  const franja = deLista(FRANJAS, r.franja, 'franja') as Franja;
  const efectivas = r.horas_efectivas !== undefined && r.horas_efectivas !== null ? num(r.horas_efectivas)
    : ficha ? horasEfectivas({ horas, franja }, ficha) : (horas ?? 0);
  return {
    id: String(r.id), farmacia: deLista(FARMACIAS_RRHH, r.farmacia, 'farmacia'), trabajadora_id: String(r.trabajadora_id), fecha: fecha(r.fecha),
    franja, tipo: deLista(TIPOS_EVENTO, r.tipo, 'tipo'), horas, horas_efectivas: efectivas, estado: deLista(ESTADOS_EVENTO, r.estado, 'estado'),
    nota: r.nota === null || r.nota === undefined ? null : String(r.nota), created_at: instante(r.created_at), updated_at: instante(r.updated_at),
  };
}

export function filaAConvenio(r: Fila): ConvenioAnual {
  return {
    anio: num(r.anio), jornada_max_horas: num(r.jornada_max_horas), asuntos_propios_dias: num(r.asuntos_propios_dias),
    permiso_medico_horas: num(r.permiso_medico_horas), horas_semanales_referencia: num(r.horas_semanales_referencia),
    estado: deLista(['FIRMADO_PENDIENTE_PUBLICACION', 'PUBLICADO'] as const, r.estado, 'estado'), fuente: String(r.fuente),
  };
}

const jsonb = (v: unknown): Fila | null => (v === null || v === undefined ? null : typeof v === 'string' ? JSON.parse(v) as Fila : v as Fila);

/** Historial de fichas desde trabajadores_historial (más reciente primero): alta, edición, baja o anulación. */
export function historialFichas(filas: Fila[]): EventoHistorial[] {
  return filas.map((h) => {
    const despues = filaATrabajadora(jsonb(h.despues) as Fila);
    const antesFila = jsonb(h.antes);
    const base = { id: String(h.id), farmacia: despues.farmacia, entidad: 'trabajadora' as const, entidad_id: despues.id, quien: String(h.autor), cuando: instante(h.created_at) };
    if (h.operacion === 'INSERT' || antesFila === null) return { ...base, accion: 'ALTA' as const, antes: null, despues: camposAlta(despues) };
    const antes = filaATrabajadora(antesFila);
    const d = diferencias(antes, despues);
    return { ...base, accion: accionActualizacion(antes, despues), antes: d.antes, despues: d.despues };
  });
}

/**
 * Cambios del calendario desde trabajadores_historial: un cambio por transacción (mismo created_at, columna `grupo`),
 * con la marca de la sesión si se hizo en ella (origen, periodo, deshecho) o el origen deducido de las filas.
 */
export function cambiosDesdeHistorial(filas: Fila[], fichas: readonly Trabajadora[], sesion: ReadonlyMap<string, CambioCalendario>): CambioCalendario[] {
  const ficha = new Map(fichas.map((t) => [t.id, t]));
  const grupos = new Map<string, Fila[]>();
  for (const f of filas) { const g = String(f.grupo ?? f.created_at); grupos.set(g, [...(grupos.get(g) ?? []), f]); }
  return [...grupos].map(([g, fs]) => {
    const ops: Operacion[] = fs.map((h) => {
      const d = jsonb(h.despues) as Fila;
      const a = jsonb(h.antes);
      const t = ficha.get(String(d.trabajadora_id));
      return { accion: h.operacion === 'INSERT' ? 'CREAR' : 'EDITAR', antes: a ? filaAEvento(a, t) : null, despues: filaAEvento(d, t) };
    });
    const marca = sesion.get(g);
    const deducido = marca ? null : inferirOrigen(ops);
    let n = 0;
    const c = construirCambio({
      id: marca?.id ?? `historial-${String(fs[0].id)}`, ops, origen: marca?.origen ?? (deducido as NonNullable<typeof deducido>).origen,
      tipo: marca ? marca.tipo : (deducido as NonNullable<typeof deducido>).tipo, quien: String(fs[0].autor), cuando: instante(fs[0].created_at),
      omitidas: marca?.omitidas_confirmadas ?? 0, deshace: marca?.deshace ?? null, periodo: marca?.periodo ?? null, fichas, nuevoId: () => `${g}#${n++}`,
    });
    return { ...c, deshecho: marca?.deshecho ?? false };
  });
}

/** Lotes de como mucho `tam` elementos. */
export function lotes<T>(xs: readonly T[], tam: number = TAM_LOTE): T[][] {
  const r: T[][] = [];
  for (let i = 0; i < xs.length; i += tam) r.push(xs.slice(i, i + tam));
  return r;
}

// ---------------------------------------------------------------------------
// Adaptador
// ---------------------------------------------------------------------------

export interface DiagnosticoTrabajadores {
  trabajadoras: number; convenio_anual: number; eventos_calendario: number; guardias_farmacia: number; festivos: number;
  trabajadores_historial: number; modulo_pio_rita: boolean; anios_convenio: number[]; anios_convenio_faltan: number[];
}
export type AdaptadorRrhhReal = AdaptadorRrhh & { diagnostico(): Promise<DiagnosticoTrabajadores> };

export function crearAdaptadorRrhhReal(o: { pool: PoolBd; nuevoId?: () => string; tamLote?: number; anio?: () => number }): AdaptadorRrhhReal {
  const { pool } = o;
  const nuevoId = o.nuevoId ?? randomUUID;
  const tamLote = o.tamLote ?? TAM_LOTE;
  const anio = o.anio ?? (() => new Date().getFullYear());
  /** Cambios del calendario hechos en esta sesión del servidor (deshacer y origen del historial), por created_at. */
  const sesion = new Map<string, CambioCalendario>();
  const cambiosSesion: CambioCalendario[] = [];
  const ultimoDeshacible = () => [...cambiosSesion].reverse().find((c) => c.origen !== 'DESHACER' && !c.deshecho) ?? null;

  async function conCliente<T>(trabajo: (c: ClienteBd) => Promise<T>): Promise<T> {
    let c: ClienteBd;
    try { c = await pool.connect(); } catch (e) { throw traducirErrorBd(e); }
    let roto = false;
    try { return await trabajo(c); } catch (e) { roto = true; throw e; } finally { c.release(roto); }
  }
  /** Lectura: transacción READ ONLY, siempre ROLLBACK. */
  const leer = <T>(trabajo: (c: ClienteBd) => Promise<T>) => conCliente(async (c) => {
    try {
      await c.query('begin transaction read only');
      const r = await trabajo(c);
      await c.query('rollback');
      return r;
    } catch (e) {
      try { await c.query('rollback'); } catch { /* conexión rota: se descarta */ }
      throw traducirErrorBd(e);
    }
  });
  /** Escritura: una transacción con el autor fijado DENTRO (set_config local); error → ROLLBACK y mensaje llano. */
  const escribir = <T>(quien: string, trabajo: (c: ClienteBd) => Promise<T>) => conCliente(async (c) => {
    if (quien.trim() === '' || quien.length > 60) throw new Error('AUTOR_NO_VALIDO');
    try {
      await c.query('begin');
      await c.query(SQL.autor, [quien]);
      const r = await trabajo(c);
      await c.query('commit');
      return r;
    } catch (e) {
      try { await c.query('rollback'); } catch { /* conexión rota: se descarta */ }
      throw traducirErrorBd(e);
    }
  });

  const fichasDe = async (c: ClienteBd, ids: string[]) => (ids.length ? (await c.query(SQL.fichasPorId, [ids])).rows.map(filaATrabajadora) : []);
  const convenioDe = async (c: ClienteBd) => (await c.query(SQL.convenio)).rows.map(filaAConvenio);

  /** Ejecuta las operaciones del plan por lotes; devuelve las realmente hechas (las altas en conflicto no cuentan). */
  async function ejecutar(c: ClienteBd, ops: Operacion[], fichas: Map<string, Trabajadora>): Promise<Operacion[]> {
    if (ops.some((op) => op.accion === 'BORRAR')) throw new Error('BORRAR_SIN_ANULAR');
    const hechas: Operacion[] = [];
    for (const lote of lotes(ops.filter((op) => op.accion === 'CREAR').map((op) => op.despues as EventoCalendario), tamLote)) {
      const r = await c.query(SQL.insertarEventos, [
        lote.map((e) => e.trabajadora_id), lote.map((e) => e.farmacia), lote.map((e) => e.fecha), lote.map((e) => e.franja),
        lote.map((e) => e.tipo), lote.map((e) => e.estado), lote.map((e) => e.horas), lote.map((e) => e.nota),
      ]);
      for (const f of r.rows) hechas.push({ accion: 'CREAR', antes: null, despues: filaAEvento(f, fichas.get(String(f.trabajadora_id))) });
    }
    for (const lote of lotes(ops.filter((op) => op.accion === 'EDITAR'), tamLote)) {
      const ds = lote.map((op) => op.despues as EventoCalendario);
      const r = await c.query(SQL.actualizarEventos, [ds.map((e) => e.id), ds.map((e) => e.tipo), ds.map((e) => e.estado), ds.map((e) => e.horas), ds.map((e) => e.nota)]);
      const porId = new Map(r.rows.map((f) => [String(f.id), f]));
      for (const op of lote) {
        const f = porId.get((op.despues as EventoCalendario).id);
        if (!f) throw new Error('EVENTO_NO_ACTUALIZADO');
        hechas.push({ accion: 'EDITAR', antes: op.antes, despues: filaAEvento(f, fichas.get(String(f.trabajadora_id))) });
      }
    }
    return hechas;
  }

  /** Registra en la sesión un cambio ya confirmado (COMMIT hecho). */
  const anotarSesion = (clave: string, cambio: CambioCalendario, deshecho: CambioCalendario | null) => {
    sesion.set(clave, cambio);
    cambiosSesion.push(cambio);
    if (deshecho) deshecho.deshecho = true;
  };

  return {
    anularEventos: false,

    trabajadoras: (farmacia, incluirBajas) => leer(async (c) => {
      const ts = (await c.query(SQL.fichas, [farmaciasDe(farmacia), incluirBajas])).rows.map(filaATrabajadora).sort(ordenFichas);
      return { farmacia, trabajadoras: ts, convenio: await convenioDe(c), anio_referencia: anio() };
    }),
    trabajadora: (id) => leer(async (c) => {
      const f = (await c.query(SQL.ficha, [id])).rows[0];
      if (!f) return null;
      const t = filaATrabajadora(f);
      return { trabajadora: t, objetivos: objetivosAnuales(t, await convenioDe(c)), historial: historialFichas((await c.query(SQL.historialFicha, [id])).rows) };
    }),
    convenio: () => leer(convenioDe),
    crearConvenio: (anios, quien) => escribir(quien, async (c) => {
      const cs = CONVENIO_ANUAL.filter((x) => anios.includes(x.anio));
      const r = await c.query(SQL.crearConvenio, [cs.map((x) => x.anio), cs.map((x) => x.jornada_max_horas), cs.map((x) => x.asuntos_propios_dias),
        cs.map((x) => x.permiso_medico_horas), cs.map((x) => x.horas_semanales_referencia), cs.map((x) => x.estado), cs.map((x) => x.fuente)]);
      return r.rows.map(filaAConvenio).sort((a, b) => a.anio - b.anio);
    }),
    historial: (farmacia) => leer(async (c) => historialFichas((await c.query(SQL.historialFichas, [farmaciasDe(farmacia)])).rows)),

    crear: (datos, quien) => escribir(quien, async (c) => {
      if (!datos.farmacia) throw new Error('FARMACIA_OBLIGATORIA');
      const r = await c.query(SQL.insertarFicha, [datos.farmacia, datos.nombre, datos.categoria, datos.tipo_jornada, datos.horas_diarias,
        computaConvenio(datos.categoria), datos.fecha_alta]);
      return filaATrabajadora(r.rows[0]);
    }),
    editar: (id, datos, quien) => escribir(quien, async (c) => {
      const f = (await c.query(SQL.fichaBloqueo, [id])).rows[0];
      if (!f) return null;
      const previo = filaATrabajadora(f);
      if (previo.anulada) return null;
      if (previo.fecha_baja !== null && previo.fecha_baja < datos.fecha_alta) return 'BAJA_ANTES_DEL_ALTA' as const;
      const nuevo: Trabajadora = { ...previo, nombre: datos.nombre, categoria: datos.categoria, tipo_jornada: datos.tipo_jornada,
        horas_diarias: datos.horas_diarias, computa_convenio: computaConvenio(datos.categoria), fecha_alta: datos.fecha_alta };
      if (Object.keys(diferencias(previo, nuevo).despues).length === 0) return previo; // sin cambios: ninguna fila de historial
      const r = await c.query(SQL.editarFicha, [id, nuevo.nombre, nuevo.categoria, nuevo.tipo_jornada, nuevo.horas_diarias, nuevo.computa_convenio, nuevo.fecha_alta]);
      return filaATrabajadora(r.rows[0]);
    }),
    darDeBaja: (id, fechaBaja, quien) => escribir(quien, async (c) => {
      const f = (await c.query(SQL.fichaBloqueo, [id])).rows[0];
      if (!f) return null;
      const previo = filaATrabajadora(f);
      if (previo.anulada) return null;
      if (previo.fecha_baja !== null) return 'YA_DE_BAJA' as const;
      if (fechaBaja < previo.fecha_alta) return 'BAJA_ANTES_DEL_ALTA' as const;
      return filaATrabajadora((await c.query(SQL.bajaFicha, [id, fechaBaja])).rows[0]);
    }),
    anular: (id, quien) => escribir(quien, async (c) => {
      const f = (await c.query(SQL.fichaBloqueo, [id])).rows[0];
      if (!f) return null;
      if (f.anulada === true) return 'YA_ANULADA' as const;
      return filaATrabajadora((await c.query(SQL.anularFicha, [id])).rows[0]);
    }),

    calendario: (farmacia, desde, hasta) => leer(async (c) => {
      const ts = (await c.query(SQL.fichasPeriodo, [farmaciasDe(farmacia), desde, hasta])).rows.map(filaATrabajadora).sort(ordenFichas);
      const porId = new Map(ts.map((t) => [t.id, t]));
      const evs = ts.length ? (await c.query(SQL.eventosPeriodo, [ts.map((t) => t.id), desde, hasta])).rows.map((f) => filaAEvento(f, porId.get(String(f.trabajadora_id)))) : [];
      const u = ultimoDeshacible();
      return { farmacia, desde, hasta, trabajadoras: ts, eventos: evs, ultimo_cambio: u ? resumen(u) : null, anular_eventos: false };
    }),
    notasProximas: (farmacia, desde) => leer(async (c) => {
      const fs = farmaciasDe(farmacia);
      const ts = (await c.query(SQL.fichasTodas, [fs])).rows.map(filaATrabajadora);
      const porId = new Map(ts.map((t) => [t.id, t]));
      const evs = (await c.query(SQL.notas, [fs, desde, FECHA_MAX])).rows.map((f) => filaAEvento(f, porId.get(String(f.trabajadora_id))));
      return notasProximas(evs, ts, farmacia, desde);
    }),

    async cambiarEventos(p, quien) {
      if (p.accion === 'BORRAR') return 'ANULAR_EVENTOS_PENDIENTE';
      const r = await escribir(quien, async (c) => {
        const clave = String((await c.query(SQL.ahora)).rows[0]?.ahora);
        const cuando = instante(clave);
        // Estado actual de lo que se va a tocar, bloqueado hasta el COMMIT.
        let filas: Fila[];
        let ids: string[];
        if (p.accion === 'EDITAR') {
          filas = (await c.query(SQL.eventoBloqueo, [p.evento_id])).rows;
          ids = filas.map((f) => String(f.trabajadora_id));
        } else if ('celdas' in p) {
          ids = [...new Set(p.celdas.map((x) => x.trabajadora_id))];
          filas = (await c.query(SQL.eventosCeldasBloqueo, [ids, [...new Set(p.celdas.map((x) => x.fecha))]])).rows;
        } else {
          ids = p.trabajadora_ids;
          filas = (await c.query(SQL.eventosRangoBloqueo, [ids, p.desde, p.hasta])).rows;
        }
        const fichas = await fichasDe(c, ids);
        const fm = new Map(fichas.map((t) => [t.id, t]));
        const evs = filas.map((f) => filaAEvento(f, fm.get(String(f.trabajadora_id))));
        const porId = new Map(evs.map((e) => [e.id, e]));
        const porCelda = new Map(evs.map((e) => [`${e.trabajadora_id}|${e.fecha}|${e.franja}`, e]));
        const pl = planificar(p, {
          ficha: (id) => fm.get(id), enCelda: (t, f, fr) => porCelda.get(`${t}|${f}|${fr}`), evento: (id) => porId.get(id), nuevoId, cuando,
        });
        if (typeof pl === 'string') return { r: pl };
        const ops = pl.ops.length ? await ejecutar(c, pl.ops, fm) : [];
        if (ops.length === 0) return { r: { cambio: null, omitidas_confirmadas: pl.omitidas, omitidas_vacias: pl.vacias } as ResultadoCambioDTO };
        const cambio = construirCambio({ id: nuevoId(), ops, origen: pl.origen, tipo: pl.tipo, quien, cuando, omitidas: pl.omitidas, deshace: null, periodo: pl.periodo, fichas, nuevoId });
        return { r: { cambio: resumen(cambio), omitidas_confirmadas: pl.omitidas, omitidas_vacias: pl.vacias } as ResultadoCambioDTO, nuevo: { clave, cambio } };
      });
      if (r.nuevo) anotarSesion(r.nuevo.clave, r.nuevo.cambio, null);
      return r.r;
    },

    async deshacerEventos(cambioId, quien) {
      const u = ultimoDeshacible();
      if (!u) return 'NADA_QUE_DESHACER';
      if (u.id !== cambioId) return 'NO_ES_EL_ULTIMO';
      if (u.trazas.some((t) => t.accion !== 'EDITAR')) return 'ANULAR_EVENTOS_PENDIENTE';
      const r = await escribir(quien, async (c) => {
        const clave = String((await c.query(SQL.ahora)).rows[0]?.ahora);
        const filas = (await c.query(SQL.eventosPorIdBloqueo, [[...new Set(u.trazas.map((t) => t.evento_id))]])).rows;
        const fichas = await fichasDe(c, [...new Set(filas.map((f) => String(f.trabajadora_id)))]);
        const fm = new Map(fichas.map((t) => [t.id, t]));
        const actual = new Map(filas.map((f) => [String(f.id), filaAEvento(f, fm.get(String(f.trabajadora_id)))]));
        const ops = planDeshacer(u, (id) => actual.get(id), () => undefined, false);
        if (typeof ops === 'string') return { r: ops };
        const hechas = await ejecutar(c, ops, fm);
        const cambio = construirCambio({ id: nuevoId(), ops: hechas, origen: 'DESHACER', tipo: null, quien, cuando: instante(clave), omitidas: 0, deshace: u, periodo: null, fichas, nuevoId });
        return { r: { cambio: resumen(cambio), omitidas_confirmadas: 0, omitidas_vacias: 0 } as ResultadoCambioDTO, nuevo: { clave, cambio } };
      });
      if (r.nuevo) anotarSesion(r.nuevo.clave, r.nuevo.cambio, u);
      return r.r;
    },

    historialEventos: (farmacia) => leer(async (c) => {
      const fs = farmaciasDe(farmacia);
      const filas = (await c.query(SQL.historialEventos, [fs])).rows;
      const fichas = (await c.query(SQL.fichasTodas, [fs])).rows.map(filaATrabajadora);
      return cambiosDesdeHistorial(filas, fichas, sesion);
    }),

    guardias: (farmacia) => leer(async (c) => (await c.query(SQL.guardias, [farmaciasDe(farmacia)])).rows.map((f): GuardiaFarmacia => ({
      id: String(f.id), farmacia: f.farmacia as FarmaciaRrhh, fecha: fecha(f.fecha), nota: f.nota === null ? null : String(f.nota), anulada: f.anulada === true,
    }))),
    festivos: (farmacia) => leer(async (c) => (await c.query(SQL.festivos, [farmaciasDe(farmacia)])).rows.map((f): Festivo => ({
      id: String(f.id), fecha: fecha(f.fecha), ambito: f.ambito as Festivo['ambito'], farmacia: (f.farmacia ?? null) as FarmaciaRrhh | null,
      descripcion: String(f.descripcion), anulado: f.anulado === true,
    }))),

    /** check:real: recuentos por tabla, módulo TRABAJADORES = PIO/RITA y años de convenio. Solo lectura. */
    diagnostico: () => leer(async (c) => {
      const f = (await c.query(SQL.diagnostico)).rows[0] ?? {};
      const n = (k: string) => { const v = Number(f[k]); if (!Number.isSafeInteger(v) || v < 0) throw new Error(`DIAGNOSTICO_NO_ES_RECUENTO: ${k}`); return v; };
      const modulo = Array.isArray(f.modulo) ? [...(f.modulo as string[])].sort() : [];
      const anios = Array.isArray(f.anios) ? (f.anios as unknown[]).map(Number) : [];
      return {
        trabajadoras: n('trabajadoras'), convenio_anual: n('convenio_anual'), eventos_calendario: n('eventos_calendario'),
        guardias_farmacia: n('guardias_farmacia'), festivos: n('festivos'), trabajadores_historial: n('trabajadores_historial'),
        modulo_pio_rita: modulo.length === 2 && modulo[0] === 'PIO' && modulo[1] === 'RITA',
        anios_convenio: anios, anios_convenio_faltan: aniosConvenioQueFaltan(anios.map((a) => ({ anio: a }))),
      };
    }),

    cerrar: () => pool.end(),
  };
}
