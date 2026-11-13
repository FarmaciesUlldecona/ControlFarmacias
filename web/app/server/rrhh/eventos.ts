/**
 * TA2 Trabajadores: calendario (eventos_calendario). Contrato de eventos, fechas, validación de peticiones y almacén
 * en memoria con traza de cada cambio y deshacer. Puro: sin imports de Node (lo usan el servidor, el front, las
 * pruebas y check_fixtures). Guardias y festivos quedan para TA3.
 *
 * Reglas (plan de Pío, TA2 y TA2-2):
 *  - TA2-2: hasta un evento por persona, día y FRANJA (MANANA / TARDE). Ej.: mañana JORNADA y tarde PERMISO_MEDICO.
 *    Las franjas de cada persona salen de su ficha: completa, mañana y tarde; media mañana, solo mañana; media tarde,
 *    solo tarde. Pintar una franja que la persona no tiene falla cerrado. Un día sin franja = todas las de la persona.
 *  - Horas por franja: medias jornadas, horas_diarias; TA2-3: completa, mañana 4,5 h (9:00–13:30) + tarde 3,5 h
 *    (17:00–20:30) = 8 h, configurable en un único punto (HORARIO_COMPLETA, contrato.ts).
 *  - La farmacia es la de la ficha, nunca la del cliente.
 *  - Todo evento nuevo nace PLANIFICADO. CONFIRMADO lo marca Marc a mano (las horas realizadas se confirman a mano):
 *    lo confirmado no se pinta, no se borra ni se editan sus horas o su nota sin quitar antes la confirmación.
 *  - Rellenar jornada habitual (semana, mes o, TA2-2, año completo): JORNADA de lunes a viernes por franja según la
 *    ficha, sin sobrescribir nada ya pintado ni confirmado.
 *  - TA2-2: nota opcional por evento (máx. 200 caracteres) con el aviso «No anotes datos de salud ni diagnósticos».
 *  - Cada cambio queda en la traza (quién, cuándo, antes/después por evento) y se puede deshacer, del último hacia atrás.
 *  - TA2-4: el texto de cada cambio cuenta días × personas («Rellenado 2027: 261 días laborables × 5 personas»), con
 *    las franjas si alguna persona-día se tocó solo en parte. ANOTAR pone la misma nota en las franjas con evento de
 *    una selección; las vacías («Pinta primero un evento para poder anotarlo») y las confirmadas se omiten y se cuentan.
 *
 * Solo sintaxis TypeScript borrable.
 */
import { CONVENIO_ANUAL, HORARIO_COMPLETA, type FarmaciaRrhh, type FiltroFarmacia, type Jornada, type Trabajadora } from './contrato.ts';

// ---------------------------------------------------------------------------
// Tipos de evento, franjas y estados
// ---------------------------------------------------------------------------

export const TIPOS_EVENTO = [
  'JORNADA', 'VACACIONES', 'ASUNTOS_PROPIOS', 'PERMISO_RETRIBUIDO', 'PERMISO_NO_RETRIBUIDO', 'PERMISO_MEDICO',
  'DESCANSO_COMPENSATORIO', 'BAJA',
] as const;
export type TipoEvento = (typeof TIPOS_EVENTO)[number];
export const TEXTO_TIPO_EVENTO: Readonly<Record<TipoEvento, string>> = {
  JORNADA: 'Jornada', VACACIONES: 'Vacaciones', ASUNTOS_PROPIOS: 'Asuntos propios', PERMISO_RETRIBUIDO: 'Permiso retribuido',
  PERMISO_NO_RETRIBUIDO: 'Permiso no retribuido', PERMISO_MEDICO: 'Permiso médico', DESCANSO_COMPENSATORIO: 'Descanso compensatorio',
  BAJA: 'Baja',
};
/** Código corto que acompaña siempre al color (el color nunca va solo). */
export const CODIGO_TIPO_EVENTO: Readonly<Record<TipoEvento, string>> = {
  JORNADA: 'J', VACACIONES: 'V', ASUNTOS_PROPIOS: 'AP', PERMISO_RETRIBUIDO: 'PR', PERMISO_NO_RETRIBUIDO: 'PN', PERMISO_MEDICO: 'PM',
  DESCANSO_COMPENSATORIO: 'DC', BAJA: 'B',
};
/**
 * Color orientativo por tipo (plan de Pío: jornada azul, vacaciones amarillo, asuntos propios violeta, descanso
 * compensatorio turquesa, baja gris). Los tres permisos, sin color indicado, evitan verde, naranja y rojo (OK,
 * revisión, incidencia). Configurables en la leyenda (solo en el navegador de quien los cambia).
 */
export const COLOR_TIPO_EVENTO: Readonly<Record<TipoEvento, string>> = {
  JORNADA: '#2f6fd0', VACACIONES: '#e3b505', ASUNTOS_PROPIOS: '#8a55c9', PERMISO_RETRIBUIDO: '#d4609c',
  PERMISO_NO_RETRIBUIDO: '#a07a52', PERMISO_MEDICO: '#5146a8', DESCANSO_COMPENSATORIO: '#1a9e96', BAJA: '#8a9590',
};

/** TA2-2: franjas del día; un evento por persona, día y franja. */
export const FRANJAS = ['MANANA', 'TARDE'] as const;
export type Franja = (typeof FRANJAS)[number];
export const TEXTO_FRANJA: Readonly<Record<Franja, string>> = { MANANA: 'mañana', TARDE: 'tarde' };
/** Franjas que trabaja cada jornada de ficha. */
export const FRANJAS_DE_JORNADA: Readonly<Record<Jornada, readonly Franja[]>> = {
  COMPLETA: ['MANANA', 'TARDE'], MEDIA_MANANA: ['MANANA'], MEDIA_TARDE: ['TARDE'],
};
/**
 * Horas de una franja según la ficha. TA2-3: completa, el reparto de HORARIO_COMPLETA (contrato.ts, único punto:
 * mañana 4,5 h + tarde 3,5 h); media jornada, todas sus horas en su única franja.
 */
export function horasFranja(t: Pick<Trabajadora, 'jornada' | 'horas_diarias'>, franja: Franja): number {
  return t.jornada === 'COMPLETA' ? HORARIO_COMPLETA[franja].horas : t.horas_diarias;
}

export const ESTADOS_EVENTO = ['PLANIFICADO', 'CONFIRMADO'] as const;
export type EstadoEvento = (typeof ESTADOS_EVENTO)[number];
export const TEXTO_ESTADO_EVENTO: Readonly<Record<EstadoEvento, string>> = { PLANIFICADO: 'planificado', CONFIRMADO: 'confirmado' };

/** TA2-2: nota opcional por evento. */
export const LARGO_NOTA = 200;
export const AVISO_NOTA = 'No anotes datos de salud ni diagnósticos';

/** eventos_calendario: un evento por persona, día y franja. */
export interface EventoCalendario {
  id: string;
  farmacia: FarmaciaRrhh;
  trabajadora_id: string;
  /** YYYY-MM-DD. */
  fecha: string;
  franja: Franja;
  tipo: TipoEvento;
  horas: number;
  estado: EstadoEvento;
  /** Nota opcional (máx. 200 caracteres; sin datos de salud). */
  nota: string | null;
  creado_at: string;
  actualizado_at: string;
}

// ---------------------------------------------------------------------------
// Peticiones (POST /api/rrhh/eventos) y traza
// ---------------------------------------------------------------------------

/** TA2-4: ANOTAR = la misma nota en todas las franjas con evento de unas celdas (vacías y confirmadas se omiten). */
export const ACCIONES_EVENTOS = ['PINTAR', 'BORRAR', 'RELLENAR', 'CONFIRMAR', 'DESCONFIRMAR', 'EDITAR', 'ANOTAR'] as const;
export type AccionEventos = (typeof ACCIONES_EVENTOS)[number];
export type OrigenCambio = AccionEventos | 'DESHACER';
/** TA2-4: participio con que empieza el texto de cada cambio («Rellenado 2027: …»). */
export const TEXTO_ORIGEN: Readonly<Record<OrigenCambio, string>> = {
  PINTAR: 'Pintado', BORRAR: 'Borrado', RELLENAR: 'Rellenado', CONFIRMAR: 'Confirmado',
  DESCONFIRMAR: 'Quitada la confirmación', EDITAR: 'Editado', ANOTAR: 'Anotado', DESHACER: 'Deshecho',
};
/** TA2-4: mensaje al intentar anotar una franja sin evento. */
export const AVISO_NOTA_VACIA = 'Pinta primero un evento para poder anotarlo';

/** Un día de una persona; con franja, solo esa franja; sin franja, todas las franjas de su ficha. */
export interface Celda { trabajadora_id: string; fecha: string; franja?: Franja }
export interface Rango { trabajadora_ids: string[]; desde: string; hasta: string }
export type PeticionEventos =
  | { accion: 'PINTAR'; tipo: TipoEvento; celdas: Celda[] }
  | { accion: 'BORRAR'; celdas: Celda[] }
  | ({ accion: 'RELLENAR' } & Rango)
  | { accion: 'CONFIRMAR' | 'DESCONFIRMAR'; celdas: Celda[] }
  | ({ accion: 'CONFIRMAR' | 'DESCONFIRMAR' } & Rango)
  | { accion: 'EDITAR'; evento_id: string; horas?: number; nota?: string | null }
  | { accion: 'ANOTAR'; celdas: Celda[]; nota: string | null };

export type AccionTraza = 'CREAR' | 'EDITAR' | 'BORRAR';
/** Traza de un evento dentro de un cambio: antes/después completos (incluida la nota). */
export interface TrazaEvento {
  id: string;
  cambio_id: string;
  accion: AccionTraza;
  farmacia: FarmaciaRrhh;
  evento_id: string;
  trabajadora_id: string;
  /** Nombre de la ficha al hacer el cambio (para leer el historial). */
  nombre: string;
  fecha: string;
  franja: Franja;
  antes: EventoCalendario | null;
  despues: EventoCalendario | null;
}
/** Un cambio = una acción de Marc (un clic, un arrastre, rellenar, confirmar, deshacer). */
export interface CambioCalendario {
  id: string;
  origen: OrigenCambio;
  /** Tipo pintado (PINTAR); null en el resto. */
  tipo: TipoEvento | null;
  quien: string;
  cuando: string;
  farmacias: FarmaciaRrhh[];
  /** Eventos (franjas) afectados. */
  n: number;
  /** Días de persona afectados (una persona y un día, con una o dos franjas). */
  dias: number;
  /** TA2-4: fechas distintas afectadas (el «261» de «261 días laborables × 5 personas»). */
  fechas: number;
  /** TA2-4: true si todas esas fechas son de lunes a viernes. */
  laborables: boolean;
  /** TA2-4: true si en algún día de persona solo se tocó parte de sus franjas (el texto cuenta entonces las franjas). */
  parcial: boolean;
  /** Personas afectadas (una por ficha). */
  personas: string[];
  desde: string;
  hasta: string;
  /** TA2-4: periodo pedido (semana, mes o año al rellenar o confirmar por rango); si no, el afectado. */
  periodo: { desde: string; hasta: string };
  /** Franjas confirmadas que la acción no ha tocado. */
  omitidas_confirmadas: number;
  /** true si un DESHACER posterior lo revirtió. */
  deshecho: boolean;
  /** Solo en DESHACER: el cambio revertido. */
  deshace: { id: string; origen: OrigenCambio; tipo: TipoEvento | null; periodo: { desde: string; hasta: string } } | null;
  trazas: TrazaEvento[];
}
export type ResumenCambio = Omit<CambioCalendario, 'trazas'>;

export interface CalendarioDTO {
  farmacia: FiltroFarmacia;
  desde: string;
  hasta: string;
  /** Fichas activas de la farmacia elegida (personas de cada farmacia por separado). */
  trabajadoras: Trabajadora[];
  eventos: EventoCalendario[];
  /** Último cambio que se puede deshacer (de cualquier farmacia); null si no hay. */
  ultimo_cambio: ResumenCambio | null;
}
/** TA2-4: omitidas_vacias = franjas sin evento que ANOTAR no ha podido anotar (0 en el resto). */
export interface ResultadoCambioDTO { cambio: ResumenCambio | null; omitidas_confirmadas: number; omitidas_vacias: number }

// ---------------------------------------------------------------------------
// Fechas (YYYY-MM-DD, en UTC: sin husos ni horario de verano)
// ---------------------------------------------------------------------------

const DIA_MS = 86_400_000;
export function esFecha(s: unknown): s is string {
  return typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && new Date(s + 'T00:00:00Z').toISOString().slice(0, 10) === s;
}
export const aDia = (f: string) => Math.round(Date.UTC(Number(f.slice(0, 4)), Number(f.slice(5, 7)) - 1, Number(f.slice(8, 10))) / DIA_MS);
export const deDia = (d: number) => new Date(d * DIA_MS).toISOString().slice(0, 10);
export const sumarDias = (f: string, n: number) => deDia(aDia(f) + n);
export const diasEntre = (desde: string, hasta: string) => aDia(hasta) - aDia(desde);
/** 0 = lunes … 6 = domingo. */
export const diaSemana = (f: string) => (new Date(f + 'T00:00:00Z').getUTCDay() + 6) % 7;
export const esLaborable = (f: string) => diaSemana(f) < 5;
export const lunesDe = (f: string) => sumarDias(f, -diaSemana(f));
export const primeroDeMes = (f: string) => `${f.slice(0, 7)}-01`;
export function sumarMeses(f: string, n: number): string {
  const m = Number(f.slice(0, 4)) * 12 + Number(f.slice(5, 7)) - 1 + n;
  return `${String(Math.floor(m / 12)).padStart(4, '0')}-${String((m % 12) + 1).padStart(2, '0')}-01`;
}
export const ultimoDeMes = (f: string) => sumarDias(sumarMeses(f, 1), -1);
export function rangoFechas(desde: string, hasta: string): string[] {
  const r: string[] = [];
  for (let d = aDia(desde); d <= aDia(hasta); d++) r.push(deDia(d));
  return r;
}

/** Fechas admitidas: los años del convenio (fuera de ellos no hay jornada máxima con la que contar). */
const ANIOS = CONVENIO_ANUAL.map((c) => c.anio);
export const FECHA_MIN = `${Math.min(...ANIOS)}-01-01`;
export const FECHA_MAX = `${Math.max(...ANIOS)}-12-31`;
export const enAniosConvenio = (f: string) => f >= FECHA_MIN && f <= FECHA_MAX;
/** Máximos por petición (falla cerrado por encima). */
export const MAX_CELDAS = 1000;
export const MAX_PERSONAS = 100;
/** Rellenar y confirmar por rango: TA2-2, hasta un año entero (366 días). */
export const MAX_DIAS_RANGO = 366;
/** Lectura: hasta un año más los días de las semanas de los extremos. */
export const MAX_DIAS_LECTURA = 400;

// ---------------------------------------------------------------------------
// Validación (pura)
// ---------------------------------------------------------------------------

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export const esUuid = (v: unknown): v is string => typeof v === 'string' && UUID.test(v);
const esObjeto = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === 'object' && !Array.isArray(v);
export const HORAS_EVENTO_MAX = 12;

export type ErroresEventos = Partial<Record<string, string>>;
export type ResultadoPeticion = { ok: true; peticion: PeticionEventos } | { ok: false; errores: ErroresEventos };

/** Nota: texto de una línea (espacios normalizados), máx. 200, sin caracteres de control ni < >; vacía = null. */
export function leerNota(v: unknown): { ok: true; nota: string | null } | { ok: false; error: string } {
  if (v === null) return { ok: true, nota: null };
  if (typeof v !== 'string') return { ok: false, error: 'Nota no válida' };
  const n = v.trim().replace(/\s+/g, ' ');
  if (n === '') return { ok: true, nota: null };
  if (n.length > LARGO_NOTA) return { ok: false, error: `La nota tiene como máximo ${LARGO_NOTA} caracteres` };
  if (/[\u0000-\u001f<>]/.test(n)) return { ok: false, error: 'La nota tiene caracteres no válidos' };
  return { ok: true, nota: n };
}

const claveCelda = (c: Celda) => `${c.trabajadora_id}|${c.fecha}|${c.franja ?? ''}`;

function leerCeldas(v: unknown, errores: ErroresEventos): Celda[] {
  if (!Array.isArray(v) || v.length === 0 || v.length > MAX_CELDAS) { errores.celdas = `Entre 1 y ${MAX_CELDAS} días`; return []; }
  const vistas = new Set<string>();
  const celdas: Celda[] = [];
  for (const c of v) {
    if (!esObjeto(c) || Object.keys(c).some((k) => k !== 'trabajadora_id' && k !== 'fecha' && k !== 'franja') || !esUuid(c.trabajadora_id) || !esFecha(c.fecha)
      || ('franja' in c && !(FRANJAS as readonly unknown[]).includes(c.franja))) {
      errores.celdas = 'Día no válido'; return [];
    }
    if (!enAniosConvenio(c.fecha)) { errores.celdas = 'Fecha fuera de los años del convenio'; return []; }
    const celda: Celda = { trabajadora_id: c.trabajadora_id, fecha: c.fecha, ...('franja' in c ? { franja: c.franja as Franja } : {}) };
    if (!vistas.has(claveCelda(celda))) { vistas.add(claveCelda(celda)); celdas.push(celda); }
  }
  return celdas;
}

function leerRango(b: Record<string, unknown>, errores: ErroresEventos): Rango | null {
  const ids = b.trabajadora_ids;
  if (!Array.isArray(ids) || ids.length === 0 || ids.length > MAX_PERSONAS || !ids.every(esUuid) || new Set(ids).size !== ids.length) {
    errores.trabajadora_ids = 'Personas no válidas';
  }
  if (!esFecha(b.desde)) errores.desde = 'Fecha no válida';
  if (!esFecha(b.hasta)) errores.hasta = 'Fecha no válida';
  if (esFecha(b.desde) && esFecha(b.hasta)) {
    if (!enAniosConvenio(b.desde) || !enAniosConvenio(b.hasta)) errores.desde = 'Fecha fuera de los años del convenio';
    else if (b.hasta < b.desde) errores.hasta = 'La fecha final es anterior a la inicial';
    else if (diasEntre(b.desde, b.hasta) + 1 > MAX_DIAS_RANGO) errores.hasta = `Como máximo ${MAX_DIAS_RANGO} días`;
  }
  return errores.trabajadora_ids || errores.desde || errores.hasta ? null : { trabajadora_ids: ids as string[], desde: b.desde as string, hasta: b.hasta as string };
}

/** Valida el cuerpo de POST /api/rrhh/eventos: solo los campos de cada acción; falla cerrado ante cualquier otra forma. */
export function validarPeticionEventos(cuerpo: unknown): ResultadoPeticion {
  if (!esObjeto(cuerpo)) return { ok: false, errores: { _: 'Datos no válidos' } };
  const b = cuerpo;
  const accion = (ACCIONES_EVENTOS as readonly unknown[]).includes(b.accion) ? (b.accion as AccionEventos) : null;
  if (accion === null) return { ok: false, errores: { accion: 'Acción no válida' } };
  const porCeldas = 'celdas' in b;
  const admitidos: Record<AccionEventos, readonly string[]> = {
    PINTAR: ['accion', 'tipo', 'celdas'],
    BORRAR: ['accion', 'celdas'],
    RELLENAR: ['accion', 'trabajadora_ids', 'desde', 'hasta'],
    CONFIRMAR: porCeldas ? ['accion', 'celdas'] : ['accion', 'trabajadora_ids', 'desde', 'hasta'],
    DESCONFIRMAR: porCeldas ? ['accion', 'celdas'] : ['accion', 'trabajadora_ids', 'desde', 'hasta'],
    EDITAR: ['accion', 'evento_id', 'horas', 'nota'],
    ANOTAR: ['accion', 'celdas', 'nota'],
  };
  const errores: ErroresEventos = {};
  for (const k of Object.keys(b)) if (!admitidos[accion].includes(k)) errores[k] = 'Campo no admitido';

  let p: PeticionEventos | null = null;
  if (accion === 'PINTAR') {
    const tipo = (TIPOS_EVENTO as readonly unknown[]).includes(b.tipo) ? (b.tipo as TipoEvento) : null;
    if (tipo === null) errores.tipo = 'Elige un tipo de evento';
    const celdas = leerCeldas(b.celdas, errores);
    if (tipo !== null) p = { accion, tipo, celdas };
  } else if (accion === 'BORRAR' || ((accion === 'CONFIRMAR' || accion === 'DESCONFIRMAR') && porCeldas)) {
    p = { accion, celdas: leerCeldas(b.celdas, errores) } as PeticionEventos;
  } else if (accion === 'ANOTAR') {
    const celdas = leerCeldas(b.celdas, errores);
    const n = leerNota('nota' in b ? b.nota : undefined);
    if (!n.ok) errores.nota = n.error;
    else p = { accion, celdas, nota: n.nota };
  } else if (accion === 'RELLENAR' || accion === 'CONFIRMAR' || accion === 'DESCONFIRMAR') {
    const r = leerRango(b, errores);
    if (r) p = { accion, ...r } as PeticionEventos;
  } else {
    if (!esUuid(b.evento_id)) errores.evento_id = 'Evento no válido';
    const e: { accion: 'EDITAR'; evento_id: string; horas?: number; nota?: string | null } = { accion: 'EDITAR', evento_id: b.evento_id as string };
    if ('horas' in b) {
      const h = b.horas;
      if (typeof h === 'number' && Number.isFinite(h) && h > 0 && h <= HORAS_EVENTO_MAX && Math.abs(Math.round(h * 100) - h * 100) < 1e-9) e.horas = h;
      else errores.horas = `Horas: más de 0 y como máximo ${HORAS_EVENTO_MAX}`;
    }
    if ('nota' in b) {
      const n = leerNota(b.nota);
      if (n.ok) e.nota = n.nota; else errores.nota = n.error;
    }
    if (!('horas' in b) && !('nota' in b)) errores._ = 'Indica las horas o la nota';
    p = e;
  }
  if (Object.keys(errores).length > 0 || p === null) return { ok: false, errores: Object.keys(errores).length ? errores : { _: 'Datos no válidos' } };
  return { ok: true, peticion: p };
}

/** Cuerpo de POST /api/rrhh/eventos/deshacer: solo el id del último cambio (el que el cliente ve). */
export function validarDeshacer(cuerpo: unknown): { ok: true; cambio_id: string } | { ok: false; errores: ErroresEventos } {
  if (!esObjeto(cuerpo) || Object.keys(cuerpo).some((k) => k !== 'cambio_id') || !esUuid(cuerpo.cambio_id)) {
    return { ok: false, errores: { cambio_id: 'Cambio no válido' } };
  }
  return { ok: true, cambio_id: cuerpo.cambio_id };
}

const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const MESES_CORTOS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sept', 'oct', 'nov', 'dic'];
/** TA2-4: periodo legible: «2027», «noviembre de 2026», «10 nov 2026», «2–6 nov 2026», «28 dic 2026 – 3 ene 2027». */
export function textoPeriodoCambio(desde: string, hasta: string): string {
  const [a1, a2] = [desde.slice(0, 4), hasta.slice(0, 4)];
  const [m1, m2] = [Number(desde.slice(5, 7)) - 1, Number(hasta.slice(5, 7)) - 1];
  const [d1, d2] = [Number(desde.slice(8)), Number(hasta.slice(8))];
  if (a1 === a2 && desde.slice(5) === '01-01' && hasta.slice(5) === '12-31') return a1;
  if (desde.slice(0, 7) === hasta.slice(0, 7) && d1 === 1 && hasta === ultimoDeMes(hasta)) return `${MESES[m1]} de ${a1}`;
  if (desde === hasta) return `${d1} ${MESES_CORTOS[m1]} ${a1}`;
  if (desde.slice(0, 7) === hasta.slice(0, 7)) return `${d1}–${d2} ${MESES_CORTOS[m1]} ${a1}`;
  if (a1 === a2) return `${d1} ${MESES_CORTOS[m1]} – ${d2} ${MESES_CORTOS[m2]} ${a1}`;
  return `${d1} ${MESES_CORTOS[m1]} ${a1} – ${d2} ${MESES_CORTOS[m2]} ${a2}`;
}

const plural = (n: number, uno: string, varios: string) => `${n} ${n === 1 ? uno : varios}`;
/**
 * TA2-4: texto llano de un cambio, en días × personas (no días de persona): «Rellenado 2027: 261 días laborables ×
 * 5 personas»; con franjas sueltas, «Pintado Vacaciones 10 nov 2026: 1 día laborable × 1 persona · 1 franja»;
 * «Deshecho «Rellenado 2027»: 261 días laborables × 5 personas».
 */
export function describirCambio(c: Pick<ResumenCambio, 'origen' | 'tipo' | 'n' | 'fechas' | 'laborables' | 'parcial' | 'personas' | 'periodo' | 'deshace'>): string {
  const base = (o: OrigenCambio, t: TipoEvento | null, p: { desde: string; hasta: string }) =>
    `${TEXTO_ORIGEN[o]}${t ? ` ${TEXTO_TIPO_EVENTO[t]}` : ''} ${textoPeriodoCambio(p.desde, p.hasta)}`;
  const cuanto = `${plural(c.fechas, c.laborables ? 'día laborable' : 'día', c.laborables ? 'días laborables' : 'días')} × `
    + `${plural(c.personas.length, 'persona', 'personas')}${c.parcial ? ` · ${plural(c.n, 'franja', 'franjas')}` : ''}`;
  return c.origen === 'DESHACER' && c.deshace
    ? `${TEXTO_ORIGEN.DESHACER} «${base(c.deshace.origen, c.deshace.tipo, c.deshace.periodo)}»: ${cuanto}`
    : `${base(c.origen, c.tipo, c.periodo)}: ${cuanto}`;
}

// ---------------------------------------------------------------------------
// Almacén en memoria (RRHH_FIXTURES; en T1, tablas reales)
// ---------------------------------------------------------------------------

export type ErrorCambio = 'TRABAJADORA_NO_VALIDA' | 'FRANJA_NO_VALIDA' | 'EVENTO_NO_ENCONTRADO' | 'EVENTO_CONFIRMADO';
export type ErrorDeshacer = 'NADA_QUE_DESHACER' | 'NO_ES_EL_ULTIMO' | 'ESTADO_CAMBIADO';

export interface SemillaEventos {
  /** Ausencias de ejemplo: de lunes a viernes entre desde y hasta; sin franja, todas las de la ficha. */
  ausencias: { trabajadora_id: string; tipo: TipoEvento; desde: string; hasta: string; franja?: Franja; nota?: string }[];
  /** Jornada habitual de todas las fichas activas (sin pisar ausencias). */
  jornada_habitual: { desde: string; hasta: string };
  /** Días ya confirmados (todas las fichas). */
  confirmado: { desde: string; hasta: string };
}

type Operacion = { accion: AccionTraza; antes: EventoCalendario | null; despues: EventoCalendario | null };
type Hueco = { t: Trabajadora; fecha: string; franja: Franja };

export interface AlmacenEventos {
  cargarEjemplo(semilla: SemillaEventos, cuando: string): void;
  calendario(farmacia: FiltroFarmacia, desde: string, hasta: string): CalendarioDTO;
  aplicar(p: PeticionEventos, quien: string): ResultadoCambioDTO | ErrorCambio;
  deshacer(cambioId: string, quien: string): ResultadoCambioDTO | ErrorDeshacer;
  historial(farmacia: FiltroFarmacia): CambioCalendario[];
  todos(): EventoCalendario[];
}

const ordenFichas = (a: Trabajadora, b: Trabajadora) => a.farmacia.localeCompare(b.farmacia) || Number(a.es_titular) - Number(b.es_titular)
  || a.nombre.localeCompare(b.nombre, 'es');
const resumen = ({ trazas: _t, ...r }: CambioCalendario): ResumenCambio => ({
  ...r, farmacias: [...r.farmacias], personas: [...r.personas], periodo: { ...r.periodo }, deshace: r.deshace ? { ...r.deshace, periodo: { ...r.deshace.periodo } } : null,
});
const mismo = (a: EventoCalendario | null | undefined, b: EventoCalendario | null | undefined) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
/** TA2-4: medidas de un cambio a partir de sus trazas (también al filtrar el historial por farmacia). */
function medidas(ts: TrazaEvento[], fichas: Trabajadora[]) {
  const porDia = new Map<string, number>();
  for (const t of ts) { const k = `${t.trabajadora_id}|${t.fecha}`; porDia.set(k, (porDia.get(k) ?? 0) + 1); }
  const franjasFicha = new Map(fichas.map((t) => [t.id, FRANJAS_DE_JORNADA[t.jornada].length]));
  const fechas = [...new Set(ts.map((t) => t.fecha))];
  return {
    n: ts.length, dias: porDia.size, fechas: fechas.length, laborables: fechas.every(esLaborable),
    parcial: [...porDia].some(([k, n]) => n < (franjasFicha.get(k.split('|')[0]) ?? n)),
    personas: [...new Map(ts.map((t) => [t.trabajadora_id, t.nombre])).values()],
    farmacias: [...new Set(ts.map((t) => t.farmacia))].sort(),
  };
}
const ORDEN_FRANJA: Readonly<Record<Franja, number>> = { MANANA: 0, TARDE: 1 };

export function crearAlmacenEventos(o: {
  fichas: () => Trabajadora[]; ahora: () => string; nuevoId: () => string;
}): AlmacenEventos {
  const eventos = new Map<string, EventoCalendario>();
  const porCelda = new Map<string, string>();
  const cambios: CambioCalendario[] = [];
  const clave = (tid: string, fecha: string, franja: Franja) => `${tid}|${fecha}|${franja}`;
  const enCelda = (tid: string, fecha: string, franja: Franja) => { const id = porCelda.get(clave(tid, fecha, franja)); return id ? eventos.get(id) : undefined; };
  const fichaActiva = (id: string) => o.fichas().find((t) => t.id === id && t.activa);
  const nuevoEvento = (h: Hueco, tipo: TipoEvento, cuando: string, nota: string | null = null): EventoCalendario => ({
    id: o.nuevoId(), farmacia: h.t.farmacia, trabajadora_id: h.t.id, fecha: h.fecha, franja: h.franja, tipo, horas: horasFranja(h.t, h.franja),
    estado: 'PLANIFICADO', nota, creado_at: cuando, actualizado_at: cuando,
  });
  const poner = (e: EventoCalendario) => { eventos.set(e.id, { ...e }); porCelda.set(clave(e.trabajadora_id, e.fecha, e.franja), e.id); };
  const quitar = (e: EventoCalendario) => { eventos.delete(e.id); porCelda.delete(clave(e.trabajadora_id, e.fecha, e.franja)); };

  /** Aplica las operaciones (ya calculadas: todo o nada) y registra un cambio con su traza. */
  function registrar(ops: Operacion[], origen: OrigenCambio, tipo: TipoEvento | null, quien: string, cuando: string,
    omitidas: number, deshace: CambioCalendario | null, periodo: { desde: string; hasta: string } | null = null, vacias = 0): ResultadoCambioDTO {
    if (ops.length === 0) return { cambio: null, omitidas_confirmadas: omitidas, omitidas_vacias: vacias };
    const id = o.nuevoId();
    const nombres = new Map(o.fichas().map((t) => [t.id, t.nombre]));
    const trazas: TrazaEvento[] = ops.map((op) => {
      const e = (op.despues ?? op.antes) as EventoCalendario;
      if (op.antes) quitar(op.antes);
      if (op.despues) poner(op.despues);
      return {
        id: o.nuevoId(), cambio_id: id, accion: op.accion, farmacia: e.farmacia, evento_id: e.id, trabajadora_id: e.trabajadora_id,
        nombre: nombres.get(e.trabajadora_id) ?? '—', fecha: e.fecha, franja: e.franja,
        antes: op.antes ? { ...op.antes } : null, despues: op.despues ? { ...op.despues } : null,
      };
    });
    const fechas = trazas.map((t) => t.fecha).sort();
    const [desde, hasta] = [fechas[0], fechas[fechas.length - 1]];
    const c: CambioCalendario = {
      id, origen, tipo, quien, cuando, ...medidas(trazas, o.fichas()), desde, hasta,
      periodo: periodo ? { ...periodo } : deshace ? { ...deshace.periodo } : { desde, hasta }, omitidas_confirmadas: omitidas,
      deshecho: false, deshace: deshace ? { id: deshace.id, origen: deshace.origen, tipo: deshace.tipo, periodo: { ...deshace.periodo } } : null, trazas,
    };
    if (deshace) deshace.deshecho = true;
    cambios.push(c);
    return { cambio: resumen(c), omitidas_confirmadas: omitidas, omitidas_vacias: vacias };
  }

  /** Último cambio deshacible: el más reciente que no es un DESHACER ni está deshecho. */
  const ultimoDeshacible = () => [...cambios].reverse().find((c) => c.origen !== 'DESHACER' && !c.deshecho) ?? null;

  /** Huecos (persona, día, franja) de unas celdas: sin franja, todas las de la ficha; franja ajena: falla cerrado. */
  function huecosDeCeldas(celdas: Celda[]): Hueco[] | ErrorCambio {
    const r: Hueco[] = [];
    const vistos = new Set<string>();
    for (const c of celdas) {
      const t = fichaActiva(c.trabajadora_id);
      if (!t) return 'TRABAJADORA_NO_VALIDA';
      const propias = FRANJAS_DE_JORNADA[t.jornada];
      if (c.franja && !propias.includes(c.franja)) return 'FRANJA_NO_VALIDA';
      for (const franja of c.franja ? [c.franja] : propias) {
        const k = clave(t.id, c.fecha, franja);
        if (!vistos.has(k)) { vistos.add(k); r.push({ t, fecha: c.fecha, franja }); }
      }
    }
    return r;
  }
  function huecosDeRango(r: Rango, soloLaborables: boolean): Hueco[] | ErrorCambio {
    const fichas: Trabajadora[] = [];
    for (const id of r.trabajadora_ids) { const t = fichaActiva(id); if (!t) return 'TRABAJADORA_NO_VALIDA'; fichas.push(t); }
    const fechas = rangoFechas(r.desde, r.hasta).filter((f) => !soloLaborables || esLaborable(f));
    return fichas.flatMap((t) => fechas.flatMap((fecha) => FRANJAS_DE_JORNADA[t.jornada].map((franja) => ({ t, fecha, franja }))));
  }

  return {
    cargarEjemplo(s, cuando) {
      const fichas = o.fichas().filter((t) => t.activa);
      const ficha = (id: string) => fichas.find((t) => t.id === id);
      for (const a of s.ausencias) {
        const t = ficha(a.trabajadora_id);
        if (!t) throw new Error(`SEMILLA_EVENTOS: ficha ${a.trabajadora_id}`);
        if (a.franja && !FRANJAS_DE_JORNADA[t.jornada].includes(a.franja)) throw new Error(`SEMILLA_EVENTOS: franja ${a.trabajadora_id}`);
        const nota = a.nota === undefined ? null : leerNota(a.nota);
        if (nota !== null && !nota.ok) throw new Error(`SEMILLA_EVENTOS: nota ${a.trabajadora_id}`);
        for (const f of rangoFechas(a.desde, a.hasta)) {
          if (!esLaborable(f)) continue;
          for (const franja of a.franja ? [a.franja] : FRANJAS_DE_JORNADA[t.jornada]) {
            if (!enCelda(t.id, f, franja)) poner(nuevoEvento({ t, fecha: f, franja }, a.tipo, cuando, nota && nota.ok ? nota.nota : null));
          }
        }
      }
      for (const t of fichas) {
        for (const f of rangoFechas(s.jornada_habitual.desde, s.jornada_habitual.hasta)) {
          if (!esLaborable(f)) continue;
          for (const franja of FRANJAS_DE_JORNADA[t.jornada]) if (!enCelda(t.id, f, franja)) poner(nuevoEvento({ t, fecha: f, franja }, 'JORNADA', cuando));
        }
      }
      for (const e of eventos.values()) if (e.fecha >= s.confirmado.desde && e.fecha <= s.confirmado.hasta) e.estado = 'CONFIRMADO';
    },

    calendario(farmacia, desde, hasta) {
      const trabajadoras = o.fichas().filter((t) => t.activa && (farmacia === 'AMBAS' || t.farmacia === farmacia)).sort(ordenFichas).map((t) => ({ ...t }));
      const ids = new Set(trabajadoras.map((t) => t.id));
      const evs = [...eventos.values()].filter((e) => ids.has(e.trabajadora_id) && e.fecha >= desde && e.fecha <= hasta)
        .sort((a, b) => a.fecha.localeCompare(b.fecha) || a.trabajadora_id.localeCompare(b.trabajadora_id) || ORDEN_FRANJA[a.franja] - ORDEN_FRANJA[b.franja])
        .map((e) => ({ ...e }));
      const u = ultimoDeshacible();
      return { farmacia, desde, hasta, trabajadoras, eventos: evs, ultimo_cambio: u ? resumen(u) : null };
    },

    aplicar(p, quien) {
      const cuando = o.ahora();
      const ops: Operacion[] = [];
      let omitidas = 0;
      if (p.accion === 'EDITAR') {
        const e = eventos.get(p.evento_id);
        if (!e || !fichaActiva(e.trabajadora_id)) return 'EVENTO_NO_ENCONTRADO';
        if (e.estado === 'CONFIRMADO') return 'EVENTO_CONFIRMADO';
        const d: EventoCalendario = { ...e, ...(p.horas !== undefined ? { horas: p.horas } : {}), ...(p.nota !== undefined ? { nota: p.nota } : {}) };
        if (d.horas !== e.horas || d.nota !== e.nota) ops.push({ accion: 'EDITAR', antes: { ...e }, despues: { ...d, actualizado_at: cuando } });
        return registrar(ops, 'EDITAR', null, quien, cuando, 0, null);
      }
      if (p.accion === 'ANOTAR') {
        // TA2-4: la misma nota en las franjas con evento; las vacías y las confirmadas se omiten y se cuentan.
        const huecos = huecosDeCeldas(p.celdas);
        if (typeof huecos === 'string') return huecos;
        let vacias = 0;
        for (const h of huecos) {
          const e = enCelda(h.t.id, h.fecha, h.franja);
          if (!e) vacias++;
          else if (e.estado === 'CONFIRMADO') omitidas++;
          else if (e.nota !== p.nota) ops.push({ accion: 'EDITAR', antes: { ...e }, despues: { ...e, nota: p.nota, actualizado_at: cuando } });
        }
        return registrar(ops, 'ANOTAR', null, quien, cuando, omitidas, null, null, vacias);
      }
      // Falla cerrado: todas las personas activas y franjas propias, o no se aplica nada.
      const huecos = 'celdas' in p ? huecosDeCeldas(p.celdas) : huecosDeRango(p, p.accion === 'RELLENAR');
      if (typeof huecos === 'string') return huecos;
      for (const h of huecos) {
        const e = enCelda(h.t.id, h.fecha, h.franja);
        if (p.accion === 'PINTAR') {
          if (e?.estado === 'CONFIRMADO') { omitidas++; continue; }
          if (!e) ops.push({ accion: 'CREAR', antes: null, despues: nuevoEvento(h, p.tipo, cuando) });
          // Otro tipo: se sustituye con las horas de la ficha y sin nota (la nota era del evento anterior; queda en la traza).
          else if (e.tipo !== p.tipo) ops.push({ accion: 'EDITAR', antes: { ...e }, despues: { ...e, tipo: p.tipo, horas: horasFranja(h.t, h.franja), nota: null, actualizado_at: cuando } });
        } else if (p.accion === 'BORRAR') {
          if (e?.estado === 'CONFIRMADO') { omitidas++; continue; }
          if (e) ops.push({ accion: 'BORRAR', antes: { ...e }, despues: null });
        } else if (p.accion === 'RELLENAR') {
          if (!e) ops.push({ accion: 'CREAR', antes: null, despues: nuevoEvento(h, 'JORNADA', cuando) });
        } else {
          const de: EstadoEvento = p.accion === 'CONFIRMAR' ? 'PLANIFICADO' : 'CONFIRMADO';
          if (e && e.estado === de) ops.push({ accion: 'EDITAR', antes: { ...e }, despues: { ...e, estado: de === 'PLANIFICADO' ? 'CONFIRMADO' : 'PLANIFICADO', actualizado_at: cuando } });
        }
      }
      return registrar(ops, p.accion, p.accion === 'PINTAR' ? p.tipo : null, quien, cuando, omitidas, null,
        'celdas' in p ? null : { desde: p.desde, hasta: p.hasta });
    },

    deshacer(cambioId, quien) {
      const u = ultimoDeshacible();
      if (!u) return 'NADA_QUE_DESHACER';
      if (u.id !== cambioId) return 'NO_ES_EL_ULTIMO';
      // El estado actual de cada evento debe ser el que dejó el cambio; si no, no se toca nada.
      for (const t of u.trazas) {
        if (!mismo(eventos.get(t.evento_id), t.despues)) return 'ESTADO_CAMBIADO';
        if (t.accion === 'BORRAR' && enCelda(t.trabajadora_id, t.fecha, t.franja)) return 'ESTADO_CAMBIADO'; // la franja ya no está libre
      }
      const ops: Operacion[] = [...u.trazas].reverse().map((t) => ({
        accion: t.accion === 'CREAR' ? 'BORRAR' : t.accion === 'BORRAR' ? 'CREAR' : 'EDITAR', antes: t.despues, despues: t.antes,
      }));
      return registrar(ops, 'DESHACER', null, quien, o.ahora(), 0, u);
    },

    historial(farmacia) {
      return [...cambios].reverse()
        .map((c) => ({ ...c, trazas: c.trazas.filter((t) => farmacia === 'AMBAS' || t.farmacia === farmacia) }))
        .filter((c) => c.trazas.length > 0)
        .map((c) => ({
          ...c, ...medidas(c.trazas, o.fichas()), periodo: { ...c.periodo },
          deshace: c.deshace ? { ...c.deshace, periodo: { ...c.deshace.periodo } } : null,
        }));
    },

    todos: () => [...eventos.values()].map((e) => ({ ...e })),
  };
}
