/**
 * TA1 Trabajadores: contrato de datos del módulo RRHH. Puro (no conecta a nada). Lo usan el servidor, el front,
 * las pruebas y check_fixtures.
 *
 * Esquema propuesto al circuito para T1 (tablas reales, que creará el circuito): trabajadoras, convenio_anual,
 * eventos_calendario (TA2, ./eventos.ts, con su traza), guardias_farmacia, festivos, historial. En TA1 solo hay datos de ejemplo en memoria
 * (adaptador RRHH_FIXTURES); en modo REAL el módulo responde "Módulo pendiente de conexión (T1)".
 *
 * Decisiones de Pío (T0):
 *  - Farmacias PIO y RITA, solo en este módulo; datos separados por farmacia.
 *  - Solo el nombre (sin DNI ni más datos personales).
 *  - Categorías TECNICO / FARMACEUTICO / AUXILIAR / OTRA.
 *  - TA1-2: jornada por horas diarias (lunes a viernes): COMPLETA = 8 h/día; MEDIA_MANANA = menos de 8 h/día, siempre de
 *    mañana (4,5 h/día en las fichas de ejemplo). Porcentaje DERIVADO = horas semanales / referencia semanal del año
 *    (40 h, provisional, en convenio_anual); nunca se edita.
 *  - Titular fuera del cómputo del convenio, con registro de horas (dos fichas, una por farmacia).
 *  - Convenio por año (CONVENIO_ANUAL): firmado, pendiente de publicación oficial.
 *  - TA1-2: autor del historial "Marc" (AUTOR_HISTORIAL).
 *
 * Solo sintaxis TypeScript borrable (Node la ejecuta sin compilar).
 */

export const FARMACIAS_RRHH = ['PIO', 'RITA'] as const;
export type FarmaciaRrhh = (typeof FARMACIAS_RRHH)[number];
/** Filtro del selector: una farmacia o las dos. */
export type FiltroFarmacia = FarmaciaRrhh | 'AMBAS';

export const CATEGORIAS = ['TECNICO', 'FARMACEUTICO', 'AUXILIAR', 'OTRA'] as const;
export type Categoria = (typeof CATEGORIAS)[number];
export const TEXTO_CATEGORIA: Readonly<Record<Categoria, string>> = {
  TECNICO: 'Técnica', FARMACEUTICO: 'Farmacéutica', AUXILIAR: 'Auxiliar', OTRA: 'Otra',
};

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
 * tarde 3,5 h (17:00–20:30) = 8 h. Para un cambio de horario se toca solo esto; el rellenado, las horas de cada
 * franja y los textos lo leen de aquí. Falla al cargar si la suma no es la jornada completa.
 */
export const HORARIO_COMPLETA = {
  MANANA: { horas: 4.5, desde: '9:00', hasta: '13:30' },
  TARDE: { horas: 3.5, desde: '17:00', hasta: '20:30' },
} as const satisfies Record<'MANANA' | 'TARDE', { horas: number; desde: string; hasta: string }>;
if (HORARIO_COMPLETA.MANANA.horas + HORARIO_COMPLETA.TARDE.horas !== HORAS_COMPLETA) throw new Error('HORARIO_COMPLETA: la suma no es la jornada completa');
const tramo = (f: 'MANANA' | 'TARDE') => `${HORARIO_COMPLETA[f].desde}–${HORARIO_COMPLETA[f].hasta}`;
/** Franja de cada jornada (pista del formulario). */
export const FRANJA_JORNADA: Readonly<Record<Jornada, string>> = {
  COMPLETA: `de lunes a viernes, ${tramo('MANANA')} y ${tramo('TARDE')}`, MEDIA_MANANA: 'de lunes a viernes, de mañana', MEDIA_TARDE: 'de lunes a viernes, de tarde (17:00–20:30)',
};
export const DIAS_SEMANA = 5;
/** Autor que figura en el historial (decisión de Pío, TA1-2). */
export const AUTOR_HISTORIAL = 'Marc';

/** Mensaje de las rutas /api/rrhh/* en modo REAL (nunca datos de ejemplo como reales). */
export const MENSAJE_PENDIENTE_T1 = 'Módulo pendiente de conexión (T1)';
export const ERROR_PENDIENTE_T1 = 'MODULO_PENDIENTE_T1';
/** Banner fijo del módulo en modo de ejemplo. */
export const TEXTO_BANNER_EJEMPLO = 'Datos de ejemplo: los cambios no se guardan hasta conectar las tablas reales';
export const TEXTO_PROVISIONAL = 'provisional: convenio pendiente de publicación';
/** Rótulo de la referencia de jornada completa (horas_semanales_referencia). */
export const TEXTO_REFERENCIA_PROVISIONAL = 'referencia provisional';
export const TEXTO_FUERA_COMPUTO = 'fuera del cómputo';
export const TEXTO_PENDIENTE_T5 = 'pendiente motor de horas (T5)';

// ---------------------------------------------------------------------------
// Tablas (forma propuesta para T1)
// ---------------------------------------------------------------------------

/** trabajadoras: una ficha por persona y farmacia (el titular tiene una en cada farmacia). */
export interface Trabajadora {
  id: string;
  farmacia: FarmaciaRrhh;
  nombre: string;
  categoria: Categoria;
  jornada: Jornada;
  /** Horas por día, de lunes a viernes. COMPLETA = 8; MEDIA_MANANA y MEDIA_TARDE > 0 y < 8. */
  horas_diarias: number;
  /** Titular de la farmacia: fuera del cómputo del convenio, con registro de horas. */
  es_titular: boolean;
  /** Derivado: computa en el convenio = no es titular. */
  computa_convenio: boolean;
  activa: boolean;
  /** YYYY-MM-DD; null si sigue activa. */
  fecha_baja: string | null;
  creado_at: string;
  actualizado_at: string;
}

export type EstadoConvenio = 'FIRMADO_PENDIENTE_PUBLICACION' | 'PUBLICADO';
export const TEXTO_ESTADO_CONVENIO: Readonly<Record<EstadoConvenio, string>> = {
  FIRMADO_PENDIENTE_PUBLICACION: 'Firmado, pendiente de publicación oficial',
  PUBLICADO: 'Publicado',
};

/** convenio_anual: un registro por año (común a PIO y RITA). */
export interface ConvenioAnual {
  anio: number;
  jornada_maxima_horas: number;
  /** TA1-2: horas semanales de la jornada completa de referencia (provisional: 40). Base del porcentaje derivado. */
  horas_semanales_referencia: number;
  asuntos_propios_dias: number;
  permiso_medico_horas: number;
  estado: EstadoConvenio;
}

/** Decisión de Pío (T0 y TA1-2). En T1 vendrá de la tabla convenio_anual. */
export const CONVENIO_ANUAL: readonly ConvenioAnual[] = [
  { anio: 2026, jornada_maxima_horas: 1767, horas_semanales_referencia: 40, asuntos_propios_dias: 1, permiso_medico_horas: 24, estado: 'FIRMADO_PENDIENTE_PUBLICACION' },
  { anio: 2027, jornada_maxima_horas: 1752, horas_semanales_referencia: 40, asuntos_propios_dias: 0, permiso_medico_horas: 24, estado: 'FIRMADO_PENDIENTE_PUBLICACION' },
  { anio: 2028, jornada_maxima_horas: 1752, horas_semanales_referencia: 40, asuntos_propios_dias: 0, permiso_medico_horas: 24, estado: 'FIRMADO_PENDIENTE_PUBLICACION' },
];

export type AccionHistorial = 'ALTA' | 'EDICION' | 'BAJA';
export const TEXTO_ACCION: Readonly<Record<AccionHistorial, string>> = { ALTA: 'Alta', EDICION: 'Edición', BAJA: 'Baja' };

/** historial: cada cambio, con quién, cuándo y antes/después. */
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

// --- TA2: eventos_calendario en ./eventos.ts. Preparado para TA3 (sin pantalla ni datos) ---------------------

/** guardias_farmacia (TA3): días de guardia de la farmacia. */
export interface GuardiaFarmacia {
  id: string;
  farmacia: FarmaciaRrhh;
  fecha: string;
  /** Turnos de guardia asignados (trabajadora y horas); vacío hasta TA3. */
  turnos: { trabajadora_id: string; horas: number | null }[];
}
/** festivos (TA3). */
export interface Festivo {
  id: string;
  /** null = festivo común a las dos farmacias. */
  farmacia: FarmaciaRrhh | null;
  fecha: string;
  descripcion: string;
}

// ---------------------------------------------------------------------------
// DTO de la API /api/rrhh/*
// ---------------------------------------------------------------------------

export interface EstadoRrhhDTO {
  modo: 'FIXTURES' | 'REAL';
  conectado: boolean;
  datos_ejemplo: boolean;
  mensaje: string;
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
  jornada_maxima_horas: number;
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
  jornada: Jornada;
  horas_diarias: number;
  es_titular: boolean;
}

// ---------------------------------------------------------------------------
// Funciones
// ---------------------------------------------------------------------------

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
    jornada_maxima_horas: c.jornada_maxima_horas,
    horas_semanales: hs,
    horas_semanales_referencia: c.horas_semanales_referencia,
    porcentaje_derivado: porcentajeDerivado(t, c),
    objetivo_horas: t.computa_convenio ? Math.round(c.jornada_maxima_horas * hs * 10 / c.horas_semanales_referencia) / 10 : null,
    estado: c.estado,
  };
}

export function objetivosAnuales(t: Pick<Trabajadora, 'horas_diarias' | 'computa_convenio'>, convenio: readonly ConvenioAnual[] = CONVENIO_ANUAL): ObjetivoAnual[] {
  return [...convenio].sort((a, b) => a.anio - b.anio).map((c) => objetivoAnual(t, c));
}

export function filtroFarmacia(v: unknown): FiltroFarmacia | null {
  return v === 'PIO' || v === 'RITA' || v === 'AMBAS' ? v : null;
}

/** Campos admitidos en alta y edición. Cualquier otro (DNI, teléfono…) se rechaza. */
const CAMPOS_ALTA = ['farmacia', 'nombre', 'categoria', 'jornada', 'horas_diarias', 'es_titular'] as const;
const CAMPOS_EDICION = ['nombre', 'categoria', 'jornada', 'horas_diarias', 'es_titular'] as const;
export const LARGO_NOMBRE = 80;

export type ErroresCampos = Partial<Record<string, string>>;
export type ResultadoValidacion = { ok: true; datos: DatosTrabajadora } | { ok: false; errores: ErroresCampos };

/**
 * Valida el cuerpo de alta o edición: solo los campos admitidos (el porcentaje es derivado: nunca se admite);
 * nombre obligatorio (1–80 caracteres, sin saltos); categoría y jornada de las listas; horas_diarias número > 0 y
 * ≤ 8 con hasta 2 decimales (COMPLETA = 8, por defecto si falta; MEDIA_MANANA < 8, por defecto 4,5; MEDIA_TARDE < 8,
 * por defecto 3,5); es_titular
 * booleano. Falla cerrado ante cualquier otra forma.
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
  const jornada = (JORNADAS as readonly unknown[]).includes(b.jornada) ? (b.jornada as Jornada) : null;
  if (jornada === null) errores.jornada = 'Elige la jornada';

  let horasDia: number | null = null;
  const h = b.horas_diarias;
  if (h === undefined || h === null || h === '') horasDia = jornada === null ? null : HORAS_POR_DEFECTO[jornada];
  else if (typeof h === 'number' && Number.isFinite(h) && h > 0 && h <= HORAS_COMPLETA && Math.abs(Math.round(h * 100) - h * 100) < 1e-9) horasDia = h; // hasta 2 decimales
  if (horasDia === null && jornada !== null) errores.horas_diarias = 'Horas al día: más de 0 y como máximo 8';
  else if (horasDia !== null && jornada === 'COMPLETA' && horasDia !== HORAS_COMPLETA) errores.horas_diarias = 'La jornada completa son 8 h al día';
  else if (horasDia !== null && jornada === 'MEDIA_MANANA' && horasDia >= HORAS_COMPLETA) errores.horas_diarias = 'La media mañana es menos de 8 h al día';
  else if (horasDia !== null && jornada === 'MEDIA_TARDE' && horasDia >= HORAS_COMPLETA) errores.horas_diarias = 'La media tarde es menos de 8 h al día';

  if (typeof b.es_titular !== 'boolean') errores.es_titular = 'Indica si es titular';

  if (Object.keys(errores).length > 0) return { ok: false, errores };
  return {
    ok: true,
    datos: {
      ...(farmacia ? { farmacia } : {}),
      nombre, categoria: categoria as Categoria, jornada: jornada as Jornada,
      horas_diarias: horasDia as number, es_titular: b.es_titular as boolean,
    },
  };
}

/** Fecha de baja: YYYY-MM-DD válida. */
export function validarFechaBaja(cuerpo: unknown): { ok: true; fecha: string } | { ok: false; errores: ErroresCampos } {
  const b = cuerpo !== null && typeof cuerpo === 'object' && !Array.isArray(cuerpo) ? (cuerpo as Record<string, unknown>) : null;
  if (b === null) return { ok: false, errores: { _: 'Datos no válidos' } };
  const extra = Object.keys(b).filter((k) => k !== 'fecha_baja');
  if (extra.length) return { ok: false, errores: Object.fromEntries(extra.map((k) => [k, 'Campo no admitido'])) };
  const f = b.fecha_baja;
  if (typeof f !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(f) || new Date(f + 'T00:00:00Z').toISOString().slice(0, 10) !== f) {
    return { ok: false, errores: { fecha_baja: 'Indica la fecha de baja' } };
  }
  return { ok: true, fecha: f };
}

/** Campos de la ficha que cambian (para el historial: solo antes/después de lo cambiado). */
export function diferencias(antes: Trabajadora, despues: Trabajadora): { antes: Partial<Trabajadora>; despues: Partial<Trabajadora> } {
  const a: Partial<Trabajadora> = {};
  const d: Partial<Trabajadora> = {};
  const claves = ['nombre', 'categoria', 'jornada', 'horas_diarias', 'es_titular', 'computa_convenio', 'activa', 'fecha_baja'] as const;
  for (const k of claves) {
    if (antes[k] !== despues[k]) { (a as Record<string, unknown>)[k] = antes[k]; (d as Record<string, unknown>)[k] = despues[k]; }
  }
  return { antes: a, despues: d };
}

/** Texto llano de un campo del historial. */
export const TEXTO_CAMPO: Readonly<Record<string, string>> = {
  nombre: 'Nombre', farmacia: 'Farmacia', categoria: 'Categoría', jornada: 'Jornada', horas_diarias: 'Horas al día',
  es_titular: 'Titular', computa_convenio: 'Computa en el convenio', activa: 'Activa', fecha_baja: 'Fecha de baja',
};
