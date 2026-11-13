/**
 * TA1 Trabajadores: contrato de datos del módulo RRHH. Puro (no conecta a nada). Lo usan el servidor, el front,
 * las pruebas y check_fixtures.
 *
 * TA-REAL: alineado con el esquema real (migración 31, sql/migrations/31_cf_trabajadores.sql): tablas trabajadoras,
 * convenio_anual, eventos_calendario (./eventos.ts), guardias_farmacia, festivos y trabajadores_historial (lo escribe
 * un trigger). Mismos nombres de columna y mismos valores. Dos adaptadores con la misma interfaz:
 * RRHH_FIXTURES (datos de ejemplo en memoria, para las pruebas) y RRHH_REAL (rol cf_trabajadores_web, ./adaptador_real.ts).
 *
 * Decisiones de Pío:
 *  - Farmacias PIO y RITA, solo en este módulo (cf_modulos_farmacias.TRABAJADORES); datos separados por farmacia.
 *  - Solo el nombre (sin DNI ni más datos personales).
 *  - TA-REAL: categorías del esquema: FARMACEUTICA_TITULAR, FARMACEUTICA_ADJUNTA, TECNICA, AUXILIAR, OTRA. Titular =
 *    FARMACEUTICA_TITULAR, fuera del cómputo (computa_convenio false); el resto computa.
 *  - Jornada (tipo_jornada) por horas diarias de lunes a viernes: COMPLETA = 8 h; MEDIA_MANANA y MEDIA_TARDE > 0 y < 8.
 *    Porcentaje DERIVADO = horas semanales / horas_semanales_referencia del año (convenio_anual; 40 h); nunca se edita.
 *  - TA-REAL: fecha_alta obligatoria (por defecto hoy, editable). «Dar de baja» = fecha_baja; «Anular» = acción aparte,
 *    con confirmación, para registros erróneos (anulada). Nunca se borra nada.
 *  - Convenio por año (convenio_anual): firmado, pendiente de publicación oficial.
 *  - Autor del historial "Marc" (AUTOR_HISTORIAL): en REAL, set_config('cf.autor', …, true) en cada transacción.
 *
 * Solo sintaxis TypeScript borrable (Node la ejecuta sin compilar).
 */

export const FARMACIAS_RRHH = ['PIO', 'RITA'] as const;
export type FarmaciaRrhh = (typeof FARMACIAS_RRHH)[number];
/** Filtro del selector: una farmacia o las dos. */
export type FiltroFarmacia = FarmaciaRrhh | 'AMBAS';
export const farmaciasDe = (f: FiltroFarmacia): FarmaciaRrhh[] => (f === 'AMBAS' ? [...FARMACIAS_RRHH] : [f]);

/** TA-REAL: categorías de trabajadoras.categoria (check de la migración 31). */
export const CATEGORIAS = ['FARMACEUTICA_TITULAR', 'FARMACEUTICA_ADJUNTA', 'TECNICA', 'AUXILIAR', 'OTRA'] as const;
export type Categoria = (typeof CATEGORIAS)[number];
export const TEXTO_CATEGORIA: Readonly<Record<Categoria, string>> = {
  FARMACEUTICA_TITULAR: 'Farmacéutica titular', FARMACEUTICA_ADJUNTA: 'Farmacéutica adjunta', TECNICA: 'Técnica',
  AUXILIAR: 'Auxiliar', OTRA: 'Otra',
};
/** Titular = categoría FARMACEUTICA_TITULAR (fuera del cómputo del convenio). */
export const esTitular = (t: Pick<Trabajadora, 'categoria'>) => t.categoria === 'FARMACEUTICA_TITULAR';
/** computa_convenio se deriva de la categoría al guardar (titular: false). */
export const computaConvenio = (categoria: Categoria) => categoria !== 'FARMACEUTICA_TITULAR';

export const JORNADAS = ['COMPLETA', 'MEDIA_MANANA', 'MEDIA_TARDE'] as const;
export type Jornada = (typeof JORNADAS)[number];
export const TEXTO_JORNADA: Readonly<Record<Jornada, string>> = { COMPLETA: 'Completa', MEDIA_MANANA: 'Media mañana', MEDIA_TARDE: 'Media tarde' };
/**
 * TA1-2/TA1-3: horas diarias (lunes a viernes). COMPLETA, exactamente 8; MEDIA_MANANA, por defecto 4,5; MEDIA_TARDE
 * (decisión de Pío, TA1-3), por defecto 3,5 (17:00–20:30). Las medias jornadas: más de 0 y menos de 8, editables.
 */
export const HORAS_COMPLETA = 8;
export const HORAS_MEDIA_MANANA = 4.5;
export const HORAS_MEDIA_TARDE = 3.5;
/** Horas por defecto de cada jornada. */
export const HORAS_POR_DEFECTO: Readonly<Record<Jornada, number>> = { COMPLETA: HORAS_COMPLETA, MEDIA_MANANA: HORAS_MEDIA_MANANA, MEDIA_TARDE: HORAS_MEDIA_TARDE };
/**
 * TA2-3: ÚNICO PUNTO del reparto por franja de la jornada completa (horario real de Pío): mañana 4,5 h (9:00–13:30) +
 * tarde 3,5 h (17:00–20:30) = 8 h. Falla al cargar si la suma no es la jornada completa.
 * TA-REAL: la vista v_eventos_calendario_horas repite este reparto (4,50 / 3,50) para las horas vacías; si cambia
 * aquí, hay que cambiar también la vista (HORAS_VISTA_COMPLETA lo vigila en las pruebas).
 */
export const HORARIO_COMPLETA = {
  MANANA: { horas: 4.5, desde: '9:00', hasta: '13:30' },
  TARDE: { horas: 3.5, desde: '17:00', hasta: '20:30' },
} as const satisfies Record<'MANANA' | 'TARDE', { horas: number; desde: string; hasta: string }>;
if (HORARIO_COMPLETA.MANANA.horas + HORARIO_COMPLETA.TARDE.horas !== HORAS_COMPLETA) throw new Error('HORARIO_COMPLETA: la suma no es la jornada completa');
/** Reparto que usa la vista v_eventos_calendario_horas (migración 31) para la jornada completa. */
export const HORAS_VISTA_COMPLETA = { MANANA: 4.5, TARDE: 3.5 } as const;
const tramo = (f: 'MANANA' | 'TARDE') => `${HORARIO_COMPLETA[f].desde}–${HORARIO_COMPLETA[f].hasta}`;
/** Franja de cada jornada (pista del formulario). */
export const FRANJA_JORNADA: Readonly<Record<Jornada, string>> = {
  COMPLETA: `de lunes a viernes, ${tramo('MANANA')} y ${tramo('TARDE')}`, MEDIA_MANANA: 'de lunes a viernes, de mañana', MEDIA_TARDE: 'de lunes a viernes, de tarde (17:00–20:30)',
};
export const DIAS_SEMANA = 5;
/** Autor que figura en el historial (decisión de Pío, TA1-2; en REAL, cf.autor de cada transacción). */
export const AUTOR_HISTORIAL = 'Marc';

/** Banner fijo del módulo en modo de ejemplo. */
export const TEXTO_BANNER_EJEMPLO = 'Datos de ejemplo: los cambios no se guardan hasta conectar las tablas reales';
/** TA-REAL: banner en modo REAL (nunca dice «datos de ejemplo»). */
export const TEXTO_BANNER_REAL = 'Datos reales: cada cambio se guarda en la base de datos con autor Marc';
/** TA-REAL: modo REAL sin CF_TRAB_USER / CF_TRAB_PASSWORD en .env.web. */
export const MENSAJE_FALTA_CREDENCIAL = 'Falta configurar la credencial de Trabajadores';
export const ERROR_FALTA_CREDENCIAL = 'CREDENCIAL_TRABAJADORES_AUSENTE';
export const TEXTO_PROVISIONAL = 'provisional: convenio pendiente de publicación';
/** Rótulo de la referencia de jornada completa (horas_semanales_referencia de convenio_anual). */
export const TEXTO_REFERENCIA_PROVISIONAL = 'referencia provisional';
export const TEXTO_FUERA_COMPUTO = 'fuera del cómputo';
export const TEXTO_PENDIENTE_T5 = 'pendiente motor de horas (T5)';

// ---------------------------------------------------------------------------
// Tablas (columnas de la migración 31)
// ---------------------------------------------------------------------------

/** trabajadoras: una ficha por persona y farmacia (el titular tiene una en cada farmacia). */
export interface Trabajadora {
  id: string;
  farmacia: FarmaciaRrhh;
  nombre: string;
  categoria: Categoria;
  tipo_jornada: Jornada;
  /** Horas por día, de lunes a viernes. COMPLETA = 8; MEDIA_MANANA y MEDIA_TARDE > 0 y < 8. */
  horas_diarias: number;
  /** Titular (FARMACEUTICA_TITULAR): false. Se guarda en la tabla. */
  computa_convenio: boolean;
  /** YYYY-MM-DD, obligatoria. */
  fecha_alta: string;
  /** YYYY-MM-DD; null si no hay baja. */
  fecha_baja: string | null;
  /** Registro erróneo anulado (nunca se borra). */
  anulada: boolean;
  created_at: string;
  updated_at: string;
  /** DERIVADO (no es columna): sin anular y sin fecha de baja. */
  activa: boolean;
}

export type EstadoConvenio = 'FIRMADO_PENDIENTE_PUBLICACION' | 'PUBLICADO';
export const TEXTO_ESTADO_CONVENIO: Readonly<Record<EstadoConvenio, string>> = {
  FIRMADO_PENDIENTE_PUBLICACION: 'Firmado, pendiente de publicación oficial',
  PUBLICADO: 'Publicado',
};

/** convenio_anual: un registro por año (común a PIO y RITA). */
export interface ConvenioAnual {
  anio: number;
  jornada_max_horas: number;
  asuntos_propios_dias: number;
  permiso_medico_horas: number;
  /** Horas semanales de la jornada completa de referencia (40). Base del porcentaje derivado. */
  horas_semanales_referencia: number;
  estado: EstadoConvenio;
  fuente: string;
}

/** Valores firmados (decisión de Pío, T0 y TA1-2). En REAL vienen de convenio_anual; si faltan, se crean con estos. */
export const FUENTE_CONVENIO = 'Convenio firmado, pendiente de publicación oficial (valores confirmados por Pío)';
export const CONVENIO_ANUAL: readonly ConvenioAnual[] = [
  { anio: 2026, jornada_max_horas: 1767, asuntos_propios_dias: 1, permiso_medico_horas: 24, horas_semanales_referencia: 40, estado: 'FIRMADO_PENDIENTE_PUBLICACION', fuente: FUENTE_CONVENIO },
  { anio: 2027, jornada_max_horas: 1752, asuntos_propios_dias: 0, permiso_medico_horas: 24, horas_semanales_referencia: 40, estado: 'FIRMADO_PENDIENTE_PUBLICACION', fuente: FUENTE_CONVENIO },
  { anio: 2028, jornada_max_horas: 1752, asuntos_propios_dias: 0, permiso_medico_horas: 24, horas_semanales_referencia: 40, estado: 'FIRMADO_PENDIENTE_PUBLICACION', fuente: FUENTE_CONVENIO },
];
export const ANIOS_CONVENIO: readonly number[] = CONVENIO_ANUAL.map((c) => c.anio);
/** Años firmados que faltan en un convenio leído. */
export const aniosConvenioQueFaltan = (convenio: readonly Pick<ConvenioAnual, 'anio'>[]) => ANIOS_CONVENIO.filter((a) => !convenio.some((c) => c.anio === a));

export type AccionHistorial = 'ALTA' | 'EDICION' | 'BAJA' | 'ANULACION';
export const TEXTO_ACCION: Readonly<Record<AccionHistorial, string>> = { ALTA: 'Alta', EDICION: 'Edición', BAJA: 'Baja', ANULACION: 'Anulación' };

/** Historial de una ficha (en REAL, filas de trabajadores_historial): quién, cuándo, antes/después de lo cambiado. */
export interface EventoHistorial {
  id: string;
  farmacia: FarmaciaRrhh;
  entidad: 'trabajadora';
  entidad_id: string;
  accion: AccionHistorial;
  quien: string;
  cuando: string;
  antes: Partial<Trabajadora> | null;
  despues: Partial<Trabajadora> | null;
}

// --- TA2: eventos_calendario en ./eventos.ts. TA3 (sin pantalla) ---------------------------------------------

/** guardias_farmacia (TA3): días de guardia de la farmacia. */
export interface GuardiaFarmacia {
  id: string;
  farmacia: FarmaciaRrhh;
  fecha: string;
  nota: string | null;
  anulada: boolean;
}
export type AmbitoFestivo = 'NACIONAL' | 'AUTONOMICO' | 'LOCAL';
/** festivos (TA3). */
export interface Festivo {
  id: string;
  fecha: string;
  ambito: AmbitoFestivo;
  /** null = festivo común a las dos farmacias (obligatoria si es LOCAL). */
  farmacia: FarmaciaRrhh | null;
  descripcion: string;
  anulado: boolean;
}

// ---------------------------------------------------------------------------
// DTO de la API /api/rrhh/*
// ---------------------------------------------------------------------------

export interface EstadoRrhhDTO {
  modo: 'FIXTURES' | 'REAL';
  conectado: boolean;
  datos_ejemplo: boolean;
  mensaje: string;
  /** TA-REAL: false en REAL hasta que exista eventos_calendario.anulado (goma y deshacer de pintados nuevos). */
  anular_eventos: boolean;
}

export interface TrabajadorasDTO {
  farmacia: FiltroFarmacia;
  trabajadoras: Trabajadora[];
  convenio: ConvenioAnual[];
  anio_referencia: number;
}

/** Objetivo anual provisional de una ficha para un año del convenio. */
export interface ObjetivoAnual {
  anio: number;
  jornada_max_horas: number;
  horas_semanales: number;
  horas_semanales_referencia: number;
  /** Derivado (horas semanales / referencia × 100), sin redondear; nunca editable. */
  porcentaje_derivado: number;
  /** null = fuera del cómputo (titular). */
  objetivo_horas: number | null;
  estado: EstadoConvenio;
}

export interface TrabajadoraDetalleDTO {
  trabajadora: Trabajadora;
  objetivos: ObjetivoAnual[];
  historial: EventoHistorial[];
}

/** Cuerpo de alta (POST) y edición (PUT; sin farmacia: no se cambia de farmacia). */
export interface DatosTrabajadora {
  farmacia?: FarmaciaRrhh;
  nombre: string;
  categoria: Categoria;
  tipo_jornada: Jornada;
  horas_diarias: number;
  fecha_alta: string;
}

// ---------------------------------------------------------------------------
// Funciones
// ---------------------------------------------------------------------------

/** YYYY-MM-DD válida (UTC). */
export function esFecha(s: unknown): s is string {
  return typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && new Date(s + 'T00:00:00Z').toISOString().slice(0, 10) === s;
}

/** Horas semanales de una ficha: horas diarias × 5 (lunes a viernes). */
export function horasSemanales(t: Pick<Trabajadora, 'horas_diarias'>): number {
  return Math.round(t.horas_diarias * DIAS_SEMANA * 100) / 100;
}

/** Porcentaje DERIVADO = horas semanales / referencia semanal del año × 100 (sin redondear). Nunca se edita. */
export function porcentajeDerivado(t: Pick<Trabajadora, 'horas_diarias'>, c: Pick<ConvenioAnual, 'horas_semanales_referencia'>): number {
  return horasSemanales(t) / c.horas_semanales_referencia * 100;
}

/**
 * Objetivo anual provisional = jornada máxima del año × (horas semanales / referencia semanal), redondeado a 0,1 h
 * una sola vez al final (p. ej. 2026, 4,5 h/día: 1767 × 22,5 / 40 = 993,9 h). Titular: null (fuera del cómputo).
 */
export function objetivoAnual(t: Pick<Trabajadora, 'horas_diarias' | 'computa_convenio'>, c: ConvenioAnual): ObjetivoAnual {
  const hs = horasSemanales(t);
  return {
    anio: c.anio,
    jornada_max_horas: c.jornada_max_horas,
    horas_semanales: hs,
    horas_semanales_referencia: c.horas_semanales_referencia,
    porcentaje_derivado: porcentajeDerivado(t, c),
    objetivo_horas: t.computa_convenio ? Math.round(c.jornada_max_horas * hs * 10 / c.horas_semanales_referencia) / 10 : null,
    estado: c.estado,
  };
}

export function objetivosAnuales(t: Pick<Trabajadora, 'horas_diarias' | 'computa_convenio'>, convenio: readonly ConvenioAnual[] = CONVENIO_ANUAL): ObjetivoAnual[] {
  return [...convenio].sort((a, b) => a.anio - b.anio).map((c) => objetivoAnual(t, c));
}

export function filtroFarmacia(v: unknown): FiltroFarmacia | null {
  return v === 'PIO' || v === 'RITA' || v === 'AMBAS' ? v : null;
}

/** Orden de las fichas: farmacia, titular al final, nombre. */
export const ordenFichas = (a: Trabajadora, b: Trabajadora) => a.farmacia.localeCompare(b.farmacia) || Number(esTitular(a)) - Number(esTitular(b))
  || a.nombre.localeCompare(b.nombre, 'es');

/** Campos admitidos en alta y edición. Cualquier otro (DNI, teléfono…) se rechaza. */
const CAMPOS_ALTA = ['farmacia', 'nombre', 'categoria', 'tipo_jornada', 'horas_diarias', 'fecha_alta'] as const;
const CAMPOS_EDICION = ['nombre', 'categoria', 'tipo_jornada', 'horas_diarias', 'fecha_alta'] as const;
export const LARGO_NOMBRE = 80;
/** Fechas de alta admitidas. */
export const FECHA_ALTA_MIN = '1980-01-01';
export const FECHA_ALTA_MAX = '2100-12-31';

export type ErroresCampos = Partial<Record<string, string>>;
export type ResultadoValidacion = { ok: true; datos: DatosTrabajadora } | { ok: false; errores: ErroresCampos };

/**
 * Valida el cuerpo de alta o edición: solo los campos admitidos (el porcentaje es derivado: nunca se admite);
 * nombre obligatorio (1–80 caracteres, sin saltos); categoría y tipo_jornada de las listas del esquema; horas_diarias
 * número > 0 y ≤ 8 con hasta 2 decimales (COMPLETA = 8, por defecto si falta; MEDIA_MANANA < 8, por defecto 4,5;
 * MEDIA_TARDE < 8, por defecto 3,5); fecha_alta obligatoria (YYYY-MM-DD). Falla cerrado ante cualquier otra forma.
 */
export function validarTrabajadora(cuerpo: unknown, modo: 'alta' | 'edicion'): ResultadoValidacion {
  if (cuerpo === null || typeof cuerpo !== 'object' || Array.isArray(cuerpo)) return { ok: false, errores: { _: 'Datos no válidos' } };
  const b = cuerpo as Record<string, unknown>;
  const errores: ErroresCampos = {};
  const admitidos: readonly string[] = modo === 'alta' ? CAMPOS_ALTA : CAMPOS_EDICION;
  for (const k of Object.keys(b)) if (!admitidos.includes(k)) errores[k] = 'Campo no admitido';

  let farmacia: FarmaciaRrhh | undefined;
  if (modo === 'alta') {
    if (b.farmacia === 'PIO' || b.farmacia === 'RITA') farmacia = b.farmacia;
    else errores.farmacia = 'Elige PIO o RITA';
  }
  const nombre = typeof b.nombre === 'string' ? b.nombre.trim().replace(/\s+/g, ' ') : '';
  if (nombre === '') errores.nombre = 'Escribe el nombre';
  else if (nombre.length > LARGO_NOMBRE) errores.nombre = `Máximo ${LARGO_NOMBRE} caracteres`;
  else if (/[\u0000-\u001f<>]/.test(nombre)) errores.nombre = 'El nombre tiene caracteres no válidos';

  const categoria = (CATEGORIAS as readonly unknown[]).includes(b.categoria) ? (b.categoria as Categoria) : null;
  if (categoria === null) errores.categoria = 'Elige una categoría';
  const jornada = (JORNADAS as readonly unknown[]).includes(b.tipo_jornada) ? (b.tipo_jornada as Jornada) : null;
  if (jornada === null) errores.tipo_jornada = 'Elige la jornada';

  let horasDia: number | null = null;
  const h = b.horas_diarias;
  if (h === undefined || h === null || h === '') horasDia = jornada === null ? null : HORAS_POR_DEFECTO[jornada];
  else if (typeof h === 'number' && Number.isFinite(h) && h > 0 && h <= HORAS_COMPLETA && Math.abs(Math.round(h * 100) - h * 100) < 1e-9) horasDia = h; // hasta 2 decimales
  if (horasDia === null && jornada !== null) errores.horas_diarias = 'Horas al día: más de 0 y como máximo 8';
  else if (horasDia !== null && jornada === 'COMPLETA' && horasDia !== HORAS_COMPLETA) errores.horas_diarias = 'La jornada completa son 8 h al día';
  else if (horasDia !== null && jornada === 'MEDIA_MANANA' && horasDia >= HORAS_COMPLETA) errores.horas_diarias = 'La media mañana es menos de 8 h al día';
  else if (horasDia !== null && jornada === 'MEDIA_TARDE' && horasDia >= HORAS_COMPLETA) errores.horas_diarias = 'La media tarde es menos de 8 h al día';

  const alta = b.fecha_alta;
  if (!esFecha(alta)) errores.fecha_alta = 'Indica la fecha de alta';
  else if (alta < FECHA_ALTA_MIN || alta > FECHA_ALTA_MAX) errores.fecha_alta = 'Fecha de alta fuera de rango';

  if (Object.keys(errores).length > 0) return { ok: false, errores };
  return {
    ok: true,
    datos: {
      ...(farmacia ? { farmacia } : {}),
      nombre, categoria: categoria as Categoria, tipo_jornada: jornada as Jornada, horas_diarias: horasDia as number, fecha_alta: alta as string,
    },
  };
}

/** Fecha de baja: YYYY-MM-DD válida. */
export function validarFechaBaja(cuerpo: unknown): { ok: true; fecha: string } | { ok: false; errores: ErroresCampos } {
  const b = cuerpo !== null && typeof cuerpo === 'object' && !Array.isArray(cuerpo) ? (cuerpo as Record<string, unknown>) : null;
  if (b === null) return { ok: false, errores: { _: 'Datos no válidos' } };
  const extra = Object.keys(b).filter((k) => k !== 'fecha_baja');
  if (extra.length) return { ok: false, errores: Object.fromEntries(extra.map((k) => [k, 'Campo no admitido'])) };
  if (!esFecha(b.fecha_baja)) return { ok: false, errores: { fecha_baja: 'Indica la fecha de baja' } };
  return { ok: true, fecha: b.fecha_baja };
}

/** TA-REAL: anular exige confirmación explícita ({ "confirmar": true }). */
export function validarAnulacion(cuerpo: unknown): { ok: true } | { ok: false; errores: ErroresCampos } {
  const ok = cuerpo !== null && typeof cuerpo === 'object' && !Array.isArray(cuerpo)
    && Object.keys(cuerpo).length === 1 && (cuerpo as Record<string, unknown>).confirmar === true;
  return ok ? { ok: true } : { ok: false, errores: { confirmar: 'Confirma la anulación' } };
}

/** TA-REAL: crear convenio: { "anios": [...] } con años firmados (2026–2028), sin repetir. */
export function validarCrearConvenio(cuerpo: unknown): { ok: true; anios: number[] } | { ok: false; errores: ErroresCampos } {
  const b = cuerpo !== null && typeof cuerpo === 'object' && !Array.isArray(cuerpo) ? (cuerpo as Record<string, unknown>) : null;
  const anios = b?.anios;
  if (b === null || Object.keys(b).some((k) => k !== 'anios') || !Array.isArray(anios) || anios.length === 0
    || !anios.every((a) => ANIOS_CONVENIO.includes(a as number)) || new Set(anios).size !== anios.length) {
    return { ok: false, errores: { anios: `Años del convenio firmado: ${ANIOS_CONVENIO.join(', ')}` } };
  }
  return { ok: true, anios: [...(anios as number[])].sort() };
}

/** Campos de la ficha que se comparan en el historial (solo antes/después de lo cambiado). */
const CLAVES_HISTORIAL = ['nombre', 'categoria', 'tipo_jornada', 'horas_diarias', 'computa_convenio', 'fecha_alta', 'fecha_baja', 'anulada'] as const;
export function diferencias(antes: Trabajadora, despues: Trabajadora): { antes: Partial<Trabajadora>; despues: Partial<Trabajadora> } {
  const a: Partial<Trabajadora> = {};
  const d: Partial<Trabajadora> = {};
  for (const k of CLAVES_HISTORIAL) {
    if (antes[k] !== despues[k]) { (a as Record<string, unknown>)[k] = antes[k]; (d as Record<string, unknown>)[k] = despues[k]; }
  }
  return { antes: a, despues: d };
}
/** Campos de un alta en el historial. */
export const camposAlta = (t: Trabajadora): Partial<Trabajadora> => ({
  farmacia: t.farmacia, nombre: t.nombre, categoria: t.categoria, tipo_jornada: t.tipo_jornada, horas_diarias: t.horas_diarias,
  computa_convenio: t.computa_convenio, fecha_alta: t.fecha_alta,
});
/** Acción del historial de una actualización: anulación, baja o edición. */
export function accionActualizacion(antes: Trabajadora, despues: Trabajadora): AccionHistorial {
  if (despues.anulada && !antes.anulada) return 'ANULACION';
  if (despues.fecha_baja !== null && antes.fecha_baja === null) return 'BAJA';
  return 'EDICION';
}

/** Texto llano de un campo del historial. */
export const TEXTO_CAMPO: Readonly<Record<string, string>> = {
  nombre: 'Nombre', farmacia: 'Farmacia', categoria: 'Categoría', tipo_jornada: 'Jornada', horas_diarias: 'Horas al día',
  computa_convenio: 'Computa en el convenio', fecha_alta: 'Fecha de alta', fecha_baja: 'Fecha de baja', anulada: 'Anulada',
};
