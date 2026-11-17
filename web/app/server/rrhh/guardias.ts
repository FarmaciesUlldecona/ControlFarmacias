/**
 * TA3 Trabajadores: guardias y festivos. Contrato, reglas, horas fuera de cómputo y almacén en memoria (FIXTURES).
 * Puro: sin imports de Node (lo usan el servidor, el front, las pruebas y check_fixtures).
 *
 * Contexto (Pío): en Ulldecona hay 3 farmacias (PIO, RITA y una ajena, OTRA). La guardia semanal rota entre las 3;
 * los festivos tienen su propia rotación, que puede no coincidir con la semanal.
 *
 * Modelo (TA3-REAL: migración 34 en producción; en FIXTURES, almacén en memoria con las mismas reglas):
 *  - guardias_semana: lunes (semana = lunes a domingo; una no anulada por lunes), farmacia PIO|RITA|OTRA, persona de
 *    guardia y persona de apoyo del sábado (opcional); anulada.
 *  - festivos: fecha, ambito NACIONAL|AUTONOMICO|LOCAL (por defecto LOCAL), farmacia (la web crea y usa solo los
 *    comunes: farmacia null), descripcion (= nombre; la BD admite 1–100, la web limita a 60); anulado. Uno no anulado
 *    por (fecha, farmacia). La baja lo anula (nunca se borra).
 *  - guardias_festivo: fecha (debe ser un festivo común no anulado), farmacia PIO|RITA|OTRA y persona; anulada. Una no
 *    anulada por fecha. Si el festivo se anula, cambia de fecha o pasa a tener farmacia, la BD anula su guardia.
 *  - Editar = anular la fila vigente + crear la nueva en la misma transacción (REAL); autor por cf.autor; nunca DELETE.
 * Reglas (las mismas que la BD):
 *  - OTRA (farmacia ajena) nunca lleva personas.
 *  - PIO/RITA: la persona es de esa farmacia y está de alta los días del servicio (guardia: sábado y domingo; apoyo:
 *    sábado; festivo: ese día). El titular puede hacer guardia (no computa, pero se registra).
 *  - El apoyo del sábado es distinto de la persona de guardia.
 *  - Guardia de festivo: por defecto, la persona de guardia de esa semana si es la misma farmacia; editable.
 * Horas FUERA DE CÓMPUTO (se registran, no suman en el año): HORARIO_GUARDIA, único punto de configuración.
 * Criterio provisional (a confirmar por Pío): un festivo que cae en el sábado o el domingo de una semana de guardia
 * sustituye ese día (guardia y apoyo); cuenta solo la guardia del festivo (no se suman las dos).
 * Los tipos ya previstos dan nombre, código y color: Turno de guardia (G), Localizada (L) y Festivo (F). TA3 no crea
 * filas en eventos_calendario: las horas salen de estas tablas.
 *
 * Solo sintaxis TypeScript borrable.
 */
import { esFecha, type FarmaciaRrhh, type Trabajadora } from './contrato.ts';
import { FECHA_MAX, FECHA_MIN, deAltaEl, diaSemana, lunesDe, sumarDias } from './eventos.ts';

// ---------------------------------------------------------------------------
// Farmacias, horario y textos
// ---------------------------------------------------------------------------

/** OTRA = la tercera farmacia de Ulldecona (ajena): solo ocupa el turno, sin personas. */
export const FARMACIAS_GUARDIA = ['PIO', 'RITA', 'OTRA'] as const;
export type FarmaciaGuardia = (typeof FARMACIAS_GUARDIA)[number];
export const TEXTO_FARMACIA_GUARDIA: Readonly<Record<FarmaciaGuardia, string>> = { PIO: 'PIO', RITA: 'RITA', OTRA: 'OTRA (farmacia ajena)' };
/**
 * Colores de guardia por farmacia: propios, distintos de los de los tipos de evento y de los de estado (verde, azul,
 * naranja, rojo). OTRA, gris. El color nunca va solo: siempre con la farmacia o las iniciales.
 */
export const COLOR_FARMACIA_GUARDIA: Readonly<Record<FarmaciaGuardia, string>> = { PIO: '#6d2e6b', RITA: '#6b7518', OTRA: '#c9cec9' };

export interface Tramo { desde: string; hasta: string }
/**
 * ÚNICO PUNTO del horario de guardia (decisión de Pío, TA3). Horas fuera de cómputo: se registran, no computan.
 *  - Guardia: sábado 9:00–13:30 y 18:00–20:00 (6,5 h); domingo 10:00–13:00 (3 h).
 *  - Apoyo del sábado: 9:00–13:30 (4,5 h).
 *  - Festivo de guardia: 10:00–13:00 (3 h).
 *  - Localizada por teléfono: sin horas, solo constancia (= la persona de guardia, toda la semana).
 */
export const HORARIO_GUARDIA = {
  GUARDIA_SABADO: [{ desde: '9:00', hasta: '13:30' }, { desde: '18:00', hasta: '20:00' }],
  GUARDIA_DOMINGO: [{ desde: '10:00', hasta: '13:00' }],
  APOYO_SABADO: [{ desde: '9:00', hasta: '13:30' }],
  FESTIVO: [{ desde: '10:00', hasta: '13:00' }],
  LOCALIZADA: [],
} as const satisfies Record<string, readonly Tramo[]>;
export type ServicioGuardia = keyof typeof HORARIO_GUARDIA;

const minutos = (h: string) => { const [a, b] = h.split(':').map(Number); return a * 60 + b; };
/** Horas de unos tramos (sin redondeos intermedios). */
export const horasTramos = (ts: readonly Tramo[]) => ts.reduce((s, t) => s + minutos(t.hasta) - minutos(t.desde), 0) / 60;
/** Horas de cada servicio, derivadas del horario. */
export const HORAS_SERVICIO: Readonly<Record<ServicioGuardia, number>> = Object.fromEntries(
  Object.entries(HORARIO_GUARDIA).map(([k, ts]) => [k, horasTramos(ts)]),
) as Record<ServicioGuardia, number>;
export const textoTramos = (ts: readonly Tramo[]) => ts.map((t) => `${t.desde}–${t.hasta}`).join(' y ');

export const LARGO_NOMBRE_FESTIVO = 60;
/** Ámbito del festivo (columna festivos.ambito); la web elige al crear, por defecto LOCAL. */
export const AMBITOS_FESTIVO = ['LOCAL', 'AUTONOMICO', 'NACIONAL'] as const;
export type AmbitoFestivoTa3 = (typeof AMBITOS_FESTIVO)[number];
export const AMBITO_POR_DEFECTO: AmbitoFestivoTa3 = 'LOCAL';
export const TEXTO_AMBITO: Readonly<Record<AmbitoFestivoTa3, string>> = { LOCAL: 'Local', AUTONOMICO: 'Autonómico', NACIONAL: 'Nacional' };

// ---------------------------------------------------------------------------
// Tablas (migración 34)
// ---------------------------------------------------------------------------

export interface GuardiaSemana {
  id: string;
  /** YYYY-MM-DD, siempre lunes. */
  lunes: string;
  farmacia: FarmaciaGuardia;
  /** null solo en OTRA. */
  persona_guardia_id: string | null;
  persona_apoyo_sabado_id: string | null;
  anulada: boolean;
}
/** Festivo común (festivos con farmacia null); nombre = descripcion. */
export interface FestivoTa3 {
  id: string;
  fecha: string;
  nombre: string;
  ambito: AmbitoFestivoTa3;
  anulado: boolean;
}
export interface GuardiaFestivo {
  id: string;
  fecha: string;
  farmacia: FarmaciaGuardia;
  /** null solo en OTRA. */
  persona_id: string | null;
  anulada: boolean;
}

// ---------------------------------------------------------------------------
// DTO de la API /api/rrhh/guardias y /api/rrhh/festivos
// ---------------------------------------------------------------------------

export interface PersonaGuardia { id: string; nombre: string; farmacia: FarmaciaRrhh; iniciales: string }
export interface SemanaGuardiaVista {
  lunes: string;
  domingo: string;
  /** null = semana sin asignar. */
  farmacia: FarmaciaGuardia | null;
  guardia: PersonaGuardia | null;
  apoyo: PersonaGuardia | null;
  /** Horas fuera de cómputo de la semana (los festivos de fin de semana las sustituyen). */
  horas_guardia: number;
  horas_apoyo: number;
  /** Fechas de la semana que son festivo. */
  festivos: string[];
}
export interface FestivoVista {
  fecha: string;
  nombre: string;
  ambito: AmbitoFestivoTa3;
  /** null = sin guardia asignada. */
  guardia: { farmacia: FarmaciaGuardia; persona: PersonaGuardia | null } | null;
  /** Guardia de esa semana (para la persona por defecto). */
  semana: { farmacia: FarmaciaGuardia; guardia: PersonaGuardia | null } | null;
}
export interface GuardiasDTO {
  disponible: true;
  desde: string;
  hasta: string;
  semanas: SemanaGuardiaVista[];
  festivos: FestivoVista[];
}
/** TA3-REAL: siempre disponible (FIXTURES y REAL). */
export type GuardiasRespuestaDTO = GuardiasDTO;

/** Bloque «Guardias del año» de la ficha anual. */
export interface ResumenGuardiasPersona {
  anio: number;
  /** Semanas como persona de guardia (por el año del sábado). También semanas localizada por teléfono. */
  semanas_guardia: number;
  sabados_apoyo: number;
  festivos_guardia: number;
  horas_guardia: number;
  horas_apoyo: number;
  horas_festivo: number;
  /** Horas fuera de cómputo totales (no suman en el objetivo del año). */
  horas_total: number;
}

// ---------------------------------------------------------------------------
// Validación (pura)
// ---------------------------------------------------------------------------

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const esObjeto = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === 'object' && !Array.isArray(v);
const esFarmaciaGuardia = (v: unknown): v is FarmaciaGuardia => (FARMACIAS_GUARDIA as readonly unknown[]).includes(v);
export type ErroresGuardia = Partial<Record<string, string>>;

/** Primer y último lunes admitidos: semanas que tocan los años del convenio. */
export const LUNES_MIN = lunesDe(FECHA_MIN);
export const LUNES_MAX = lunesDe(FECHA_MAX);
export const esLunesAdmitido = (f: unknown): f is string => esFecha(f) && diaSemana(f) === 0 && f >= LUNES_MIN && f <= LUNES_MAX;
export const enAniosGuardia = (f: string) => f >= FECHA_MIN && f <= FECHA_MAX;

export interface DatosGuardiaSemana { lunes: string; farmacia: FarmaciaGuardia; persona_guardia_id: string | null; persona_apoyo_sabado_id: string | null }

/** Persona: uuid o null/ausente. */
function leerPersona(b: Record<string, unknown>, k: string, errores: ErroresGuardia): string | null {
  const v = b[k];
  if (v === undefined || v === null || v === '') return null;
  if (typeof v !== 'string' || !UUID.test(v)) { errores[k] = 'Persona no válida'; return null; }
  return v;
}

/** Cuerpo de PUT /api/rrhh/guardias/:lunes: { farmacia, persona_guardia_id?, persona_apoyo_sabado_id? }. Falla cerrado. */
export function validarGuardiaSemana(lunes: unknown, cuerpo: unknown): { ok: true; datos: DatosGuardiaSemana } | { ok: false; errores: ErroresGuardia } {
  if (!esObjeto(cuerpo)) return { ok: false, errores: { _: 'Datos no válidos' } };
  const errores: ErroresGuardia = {};
  for (const k of Object.keys(cuerpo)) if (!['farmacia', 'persona_guardia_id', 'persona_apoyo_sabado_id'].includes(k)) errores[k] = 'Campo no admitido';
  if (!esLunesAdmitido(lunes)) errores.lunes = 'La semana empieza en lunes, dentro de los años del convenio';
  const farmacia = esFarmaciaGuardia(cuerpo.farmacia) ? cuerpo.farmacia : null;
  if (farmacia === null) errores.farmacia = 'Elige PIO, RITA u OTRA';
  const guardia = leerPersona(cuerpo, 'persona_guardia_id', errores);
  const apoyo = leerPersona(cuerpo, 'persona_apoyo_sabado_id', errores);
  if (farmacia === 'OTRA' && (guardia !== null || apoyo !== null)) errores.farmacia = 'La farmacia ajena (OTRA) no lleva personas';
  if ((farmacia === 'PIO' || farmacia === 'RITA') && guardia === null && !errores.persona_guardia_id) errores.persona_guardia_id = 'Elige la persona de guardia';
  if (guardia !== null && guardia === apoyo) errores.persona_apoyo_sabado_id = 'El apoyo del sábado tiene que ser otra persona';
  if (Object.keys(errores).length > 0) return { ok: false, errores };
  return { ok: true, datos: { lunes: lunes as string, farmacia: farmacia as FarmaciaGuardia, persona_guardia_id: guardia, persona_apoyo_sabado_id: apoyo } };
}

/** Nombre del festivo: una línea (espacios normalizados), 1–60 caracteres, sin caracteres de control ni < >. */
export function leerNombreFestivo(v: unknown): { ok: true; nombre: string } | { ok: false; error: string } {
  if (typeof v !== 'string') return { ok: false, error: 'Escribe el nombre del festivo' };
  const n = v.trim().replace(/\s+/g, ' ');
  if (n === '') return { ok: false, error: 'Escribe el nombre del festivo' };
  if (n.length > LARGO_NOMBRE_FESTIVO) return { ok: false, error: `Máximo ${LARGO_NOMBRE_FESTIVO} caracteres` };
  if (/[\u0000-\u001f<>]/.test(n)) return { ok: false, error: 'El nombre tiene caracteres no válidos' };
  return { ok: true, nombre: n };
}

/** Cuerpo de POST /api/rrhh/festivos: { fecha, nombre, ambito? } (ámbito por defecto LOCAL). */
export function validarFestivo(cuerpo: unknown): { ok: true; fecha: string; nombre: string; ambito: AmbitoFestivoTa3 } | { ok: false; errores: ErroresGuardia } {
  if (!esObjeto(cuerpo)) return { ok: false, errores: { _: 'Datos no válidos' } };
  const errores: ErroresGuardia = {};
  for (const k of Object.keys(cuerpo)) if (k !== 'fecha' && k !== 'nombre' && k !== 'ambito') errores[k] = 'Campo no admitido';
  if (!esFecha(cuerpo.fecha)) errores.fecha = 'Indica la fecha';
  else if (!enAniosGuardia(cuerpo.fecha)) errores.fecha = 'Fecha fuera de los años del convenio';
  const n = leerNombreFestivo(cuerpo.nombre);
  if (!n.ok) errores.nombre = n.error;
  const ambito = cuerpo.ambito === undefined || cuerpo.ambito === null || cuerpo.ambito === '' ? AMBITO_POR_DEFECTO : cuerpo.ambito;
  if (!(AMBITOS_FESTIVO as readonly unknown[]).includes(ambito)) errores.ambito = 'Elige local, autonómico o nacional';
  if (Object.keys(errores).length > 0 || !n.ok) return { ok: false, errores };
  return { ok: true, fecha: cuerpo.fecha as string, nombre: n.nombre, ambito: ambito as AmbitoFestivoTa3 };
}

/**
 * Cuerpo de PUT /api/rrhh/festivos/:fecha/guardia: { farmacia, persona_id? }. Sin persona en PIO/RITA = la de guardia
 * de esa semana si es la misma farmacia (la resuelve el almacén).
 */
export function validarGuardiaFestivo(cuerpo: unknown): { ok: true; farmacia: FarmaciaGuardia; persona_id: string | null } | { ok: false; errores: ErroresGuardia } {
  if (!esObjeto(cuerpo)) return { ok: false, errores: { _: 'Datos no válidos' } };
  const errores: ErroresGuardia = {};
  for (const k of Object.keys(cuerpo)) if (k !== 'farmacia' && k !== 'persona_id') errores[k] = 'Campo no admitido';
  const farmacia = esFarmaciaGuardia(cuerpo.farmacia) ? cuerpo.farmacia : null;
  if (farmacia === null) errores.farmacia = 'Elige PIO, RITA u OTRA';
  const persona = leerPersona(cuerpo, 'persona_id', errores);
  if (farmacia === 'OTRA' && persona !== null) errores.farmacia = 'La farmacia ajena (OTRA) no lleva personas';
  if (Object.keys(errores).length > 0) return { ok: false, errores };
  return { ok: true, farmacia: farmacia as FarmaciaGuardia, persona_id: persona };
}

// ---------------------------------------------------------------------------
// Reglas de personas y horas (puras)
// ---------------------------------------------------------------------------

export type ErrorGuardia = 'PERSONA_NO_VALIDA' | 'APOYO_IGUAL_GUARDIA' | 'OTRA_SIN_PERSONAS' | 'PERSONA_OBLIGATORIA'
  | 'NO_ES_FESTIVO' | 'FESTIVO_DUPLICADO' | 'SIN_FESTIVO' | 'SIN_GUARDIA';

export const sabadoDe = (lunes: string) => sumarDias(lunes, 5);
export const domingoDe = (lunes: string) => sumarDias(lunes, 6);

/** La persona puede cubrir el servicio: ficha sin anular, de esa farmacia y de alta en todas esas fechas (titular incluido). */
export function personaValida(t: Trabajadora | undefined, farmacia: FarmaciaGuardia, fechas: readonly string[]): boolean {
  return !!t && farmacia !== 'OTRA' && t.farmacia === farmacia && fechas.every((f) => deAltaEl(t, f));
}

/** Reglas de una guardia semanal sobre las fichas vigentes; null = válida. */
export function reglasSemana(d: DatosGuardiaSemana, ficha: (id: string) => Trabajadora | undefined): ErrorGuardia | null {
  if (d.farmacia === 'OTRA') return d.persona_guardia_id !== null || d.persona_apoyo_sabado_id !== null ? 'OTRA_SIN_PERSONAS' : null;
  if (d.persona_guardia_id === null) return 'PERSONA_OBLIGATORIA';
  if (d.persona_guardia_id === d.persona_apoyo_sabado_id) return 'APOYO_IGUAL_GUARDIA';
  if (!personaValida(ficha(d.persona_guardia_id), d.farmacia, [sabadoDe(d.lunes), domingoDe(d.lunes)])) return 'PERSONA_NO_VALIDA';
  if (d.persona_apoyo_sabado_id !== null && !personaValida(ficha(d.persona_apoyo_sabado_id), d.farmacia, [sabadoDe(d.lunes)])) return 'PERSONA_NO_VALIDA';
  return null;
}

/** Iniciales de un nombre: las dos primeras palabras sin partículas («Aina Bosch Ferrer» → «AB»; «Titular de ejemplo» → «TE»). */
export function iniciales(nombre: string): string {
  const p = nombre.trim().split(/\s+/).filter((x) => x !== '' && !/^(de|del|la|las|los|el|i|y)$/i.test(x));
  return p.slice(0, 2).map((x) => x.charAt(0).toUpperCase()).join('');
}

export interface DatosGuardias { semanas: readonly GuardiaSemana[]; festivos: readonly FestivoTa3[]; guardiasFestivo: readonly GuardiaFestivo[] }
const vigentes = (d: DatosGuardias) => ({
  semanas: d.semanas.filter((s) => !s.anulada),
  festivos: new Map(d.festivos.filter((f) => !f.anulado).map((f) => [f.fecha, f])),
  gf: new Map(d.guardiasFestivo.filter((g) => !g.anulada).map((g) => [g.fecha, g])),
});

/**
 * Horas fuera de cómputo de una semana para su persona de guardia y su apoyo: sábado y domingo según HORARIO_GUARDIA;
 * un festivo en sábado o domingo sustituye ese día (cuenta la guardia del festivo, no la semanal).
 */
export function horasSemana(lunes: string, esFestivo: (f: string) => boolean): { guardia: number; apoyo: number } {
  const sab = esFestivo(sabadoDe(lunes));
  const dom = esFestivo(domingoDe(lunes));
  return {
    guardia: (sab ? 0 : HORAS_SERVICIO.GUARDIA_SABADO) + (dom ? 0 : HORAS_SERVICIO.GUARDIA_DOMINGO),
    apoyo: sab ? 0 : HORAS_SERVICIO.APOYO_SABADO,
  };
}

const r2 = (x: number) => Math.round(x * 100) / 100;

/**
 * «Guardias del año» de una persona: semanas de guardia (y localizada) y sábados de apoyo por el año del sábado; horas
 * de cada día por su propia fecha; festivos de guardia por su fecha. Solo filas no anuladas.
 */
export function resumenGuardiasPersona(tid: string, anio: number, d: DatosGuardias): ResumenGuardiasPersona {
  const v = vigentes(d);
  const enAnio = (f: string) => f.startsWith(`${anio}-`);
  const festivo = (f: string) => v.festivos.has(f);
  let semanas = 0; let apoyos = 0; let hg = 0; let ha = 0;
  for (const s of v.semanas) {
    if (s.farmacia === 'OTRA') continue;
    const [sab, dom] = [sabadoDe(s.lunes), domingoDe(s.lunes)];
    if (s.persona_guardia_id === tid) {
      if (enAnio(sab)) semanas++;
      if (enAnio(sab) && !festivo(sab)) hg += HORAS_SERVICIO.GUARDIA_SABADO;
      if (enAnio(dom) && !festivo(dom)) hg += HORAS_SERVICIO.GUARDIA_DOMINGO;
    }
    if (s.persona_apoyo_sabado_id === tid && enAnio(sab)) {
      apoyos++;
      if (!festivo(sab)) ha += HORAS_SERVICIO.APOYO_SABADO;
    }
  }
  const festivos = [...v.gf.values()].filter((g) => g.persona_id === tid && enAnio(g.fecha) && festivo(g.fecha)).length;
  const hf = festivos * HORAS_SERVICIO.FESTIVO;
  return {
    anio, semanas_guardia: semanas, sabados_apoyo: apoyos, festivos_guardia: festivos,
    horas_guardia: r2(hg), horas_apoyo: r2(ha), horas_festivo: r2(hf), horas_total: r2(hg + ha + hf),
  };
}

// ---------------------------------------------------------------------------
// Semilla de ejemplo (fixtures/rrhh/guardias.json)
// ---------------------------------------------------------------------------

export interface SemillaGuardias {
  /** Rotación semanal: semana i (desde el lunes `desde`) = farmacias[i % 3]; cada farmacia recorre su lista por turnos. */
  rotacion: {
    desde: string; hasta: string; farmacias: FarmaciaGuardia[];
    PIO: { guardia: string; apoyo: string | null }[]; RITA: { guardia: string; apoyo: string | null }[];
  };
  festivos: { fecha: string; nombre: string; guardia?: { farmacia: FarmaciaGuardia; persona: string | null } }[];
}

/** Semanas de la rotación de ejemplo (puras; check_fixtures las vuelve a comprobar con las reglas). */
export function semanasDeRotacion(r: SemillaGuardias['rotacion']): Omit<GuardiaSemana, 'id'>[] {
  const res: Omit<GuardiaSemana, 'id'>[] = [];
  const turnos: Record<FarmaciaGuardia, number> = { PIO: 0, RITA: 0, OTRA: 0 };
  for (let i = 0, l = r.desde; l <= r.hasta; i++, l = sumarDias(l, 7)) {
    const farmacia = r.farmacias[i % r.farmacias.length];
    const k = turnos[farmacia]++;
    const p = farmacia === 'OTRA' ? null : r[farmacia][k % r[farmacia].length];
    res.push({ lunes: l, farmacia, persona_guardia_id: p?.guardia ?? null, persona_apoyo_sabado_id: p?.apoyo ?? null, anulada: false });
  }
  return res;
}

// ---------------------------------------------------------------------------
// Almacén en memoria (RRHH_FIXTURES)
// ---------------------------------------------------------------------------

type Quizas<T> = T | Promise<T>;
export type ResultadoSemana = SemanaGuardiaVista | ErrorGuardia;
export type ResultadoFestivo = FestivoVista | ErrorGuardia;

/**
 * TA3-REAL: interfaz común de guardias y festivos. FIXTURES: almacén en memoria (síncrono). REAL: tablas de la
 * migración 34 con cf_trabajadores_web (asíncrono; cada escritura en su transacción con cf.autor).
 */
export interface GuardiasTa3 {
  vista(desde: string, hasta: string): Quizas<GuardiasDTO>;
  guardarSemana(d: DatosGuardiaSemana, quien: string): Quizas<ResultadoSemana>;
  crearFestivo(fecha: string, nombre: string, ambito: AmbitoFestivoTa3, quien: string): Quizas<ResultadoFestivo>;
  /** Baja del festivo: lo anula (y su guardia: en REAL la anula la BD). */
  anularFestivo(fecha: string, quien: string): Quizas<ResultadoFestivo>;
  guardarGuardiaFestivo(fecha: string, farmacia: FarmaciaGuardia, persona: string | null, quien: string): Quizas<ResultadoFestivo>;
  /** TA3-4 (goma del calendario): anula la guardia de una semana (PIO, RITA u OTRA); queda sin asignar. */
  anularSemana(lunes: string, quien: string): Quizas<ResultadoSemana>;
  /** TA3-4 (goma del calendario): anula la guardia de un festivo; el festivo sigue. */
  anularGuardiaFestivo(fecha: string, quien: string): Quizas<ResultadoFestivo>;
  /** TA3-2: fechas de los festivos dados de alta en un año (puente en las vacaciones de la ficha anual). */
  fechasFestivo(anio: number): Quizas<string[]>;
  resumenPersona(tid: string, anio: number): Quizas<ResumenGuardiasPersona>;
}

export interface AlmacenGuardias extends GuardiasTa3 {
  vista(desde: string, hasta: string): GuardiasDTO;
  guardarSemana(d: DatosGuardiaSemana): ResultadoSemana;
  crearFestivo(fecha: string, nombre: string, ambito?: AmbitoFestivoTa3): ResultadoFestivo;
  anularFestivo(fecha: string): ResultadoFestivo;
  guardarGuardiaFestivo(fecha: string, farmacia: FarmaciaGuardia, persona: string | null): ResultadoFestivo;
  anularSemana(lunes: string): ResultadoSemana;
  anularGuardiaFestivo(fecha: string): ResultadoFestivo;
  esFestivo(fecha: string): boolean;
  fechasFestivo(anio: number): string[];
  resumenPersona(tid: string, anio: number): ResumenGuardiasPersona;
  /** Todas las filas, anuladas incluidas (pruebas y check_fixtures). */
  datos(): { semanas: GuardiaSemana[]; festivos: FestivoTa3[]; guardiasFestivo: GuardiaFestivo[] };
}

// ---------------------------------------------------------------------------
// Vistas (puras; FIXTURES y REAL las construyen igual a partir de sus filas)
// ---------------------------------------------------------------------------

export type BuscarPersona = (id: string | null) => PersonaGuardia | null;
export const personaDe = (t: Trabajadora | undefined): PersonaGuardia | null =>
  (t ? { id: t.id, nombre: t.nombre, farmacia: t.farmacia, iniciales: iniciales(t.nombre) } : null);

/** Filas vigentes indexadas (las anuladas no cuentan). */
export function indice(d: DatosGuardias) {
  const v = vigentes(d);
  const semanas = new Map(v.semanas.map((s) => [s.lunes, s]));
  return {
    semana: (lunes: string) => semanas.get(lunes),
    festivo: (f: string) => v.festivos.get(f),
    gf: (f: string) => v.gf.get(f),
    esFestivo: (f: string) => v.festivos.has(f),
    festivos: [...v.festivos.values()],
  };
}

export function vistaSemanaDe(lunes: string, d: DatosGuardias, persona: BuscarPersona): SemanaGuardiaVista {
  const ix = indice(d);
  const s = ix.semana(lunes);
  const h = horasSemana(lunes, ix.esFestivo);
  const conGuardia = s !== undefined && s.farmacia !== 'OTRA';
  return {
    lunes, domingo: domingoDe(lunes), farmacia: s?.farmacia ?? null, guardia: persona(s?.persona_guardia_id ?? null), apoyo: persona(s?.persona_apoyo_sabado_id ?? null),
    horas_guardia: conGuardia ? h.guardia : 0, horas_apoyo: conGuardia && s.persona_apoyo_sabado_id !== null ? h.apoyo : 0,
    festivos: [0, 1, 2, 3, 4, 5, 6].map((n) => sumarDias(lunes, n)).filter(ix.esFestivo),
  };
}

export function vistaFestivoDe(f: FestivoTa3, d: DatosGuardias, persona: BuscarPersona): FestivoVista {
  const ix = indice(d);
  const g = ix.gf(f.fecha);
  const s = ix.semana(lunesDe(f.fecha));
  return {
    fecha: f.fecha, nombre: f.nombre, ambito: f.ambito,
    guardia: g ? { farmacia: g.farmacia, persona: persona(g.persona_id) } : null,
    semana: s ? { farmacia: s.farmacia, guardia: persona(s.persona_guardia_id) } : null,
  };
}

/** Lunes cuyas semanas tocan el periodo (dentro de los años del convenio). */
export function lunesDelPeriodo(desde: string, hasta: string): string[] {
  const lunes: string[] = [];
  for (let l = lunesDe(desde); l <= hasta; l = sumarDias(l, 7)) if (l >= LUNES_MIN && l <= LUNES_MAX) lunes.push(l);
  return lunes;
}

/** Vista de un periodo. `d` debe contener las filas de las semanas que lo tocan (de lunes a domingo). */
export function vistaGuardias(desde: string, hasta: string, d: DatosGuardias, persona: BuscarPersona): GuardiasDTO {
  return {
    disponible: true, desde, hasta, semanas: lunesDelPeriodo(desde, hasta).map((l) => vistaSemanaDe(l, d, persona)),
    festivos: indice(d).festivos.filter((f) => f.fecha >= desde && f.fecha <= hasta).sort((a, b) => a.fecha.localeCompare(b.fecha))
      .map((f) => vistaFestivoDe(f, d, persona)),
  };
}

/** Persona por defecto de la guardia de un festivo: la de guardia de esa semana si es la misma farmacia. */
export function personaPorDefecto(farmacia: FarmaciaGuardia, semana: GuardiaSemana | undefined): string | null {
  return semana && semana.farmacia === farmacia && farmacia !== 'OTRA' ? semana.persona_guardia_id : null;
}

/** Reglas de la guardia de un festivo (como la BD); devuelve la persona resuelta o el error. */
export function reglasGuardiaFestivo(fecha: string, farmacia: FarmaciaGuardia, personaId: string | null, o: {
  esFestivoComun: boolean; semana: GuardiaSemana | undefined; ficha: (id: string) => Trabajadora | undefined;
}): { persona: string | null } | ErrorGuardia {
  if (!o.esFestivoComun) return 'NO_ES_FESTIVO';
  if (farmacia === 'OTRA') return personaId !== null ? 'OTRA_SIN_PERSONAS' : { persona: null };
  const pid = personaId ?? personaPorDefecto(farmacia, o.semana);
  if (pid === null) return 'PERSONA_OBLIGATORIA';
  if (!personaValida(o.ficha(pid), farmacia, [fecha])) return 'PERSONA_NO_VALIDA';
  return { persona: pid };
}

export function crearAlmacenGuardias(o: { fichas: () => Trabajadora[]; nuevoId: () => string; semilla?: SemillaGuardias | null }): AlmacenGuardias {
  let semanas: GuardiaSemana[] = [];
  let festivos: FestivoTa3[] = [];
  let gfs: GuardiaFestivo[] = [];
  const ficha = (id: string) => o.fichas().find((t) => t.id === id);
  const persona: BuscarPersona = (id) => (id === null ? null : personaDe(ficha(id)));
  const datosAhora = (): DatosGuardias => ({ semanas, festivos, guardiasFestivo: gfs });
  const festivoDe = (f: string) => festivos.find((x) => x.fecha === f && !x.anulado);
  const esFestivo = (f: string) => festivoDe(f) !== undefined;
  const semanaDe = (lunes: string) => semanas.find((s) => s.lunes === lunes && !s.anulada);
  const gfDe = (f: string) => gfs.find((g) => g.fecha === f && !g.anulada);
  const vistaSemana = (lunes: string) => vistaSemanaDe(lunes, datosAhora(), persona);
  const vistaFestivo = (f: FestivoTa3) => vistaFestivoDe(f, datosAhora(), persona);

  const almacen: AlmacenGuardias = {
    vista: (desde, hasta) => vistaGuardias(desde, hasta, datosAhora(), persona),
    guardarSemana(d) {
      const e = reglasSemana(d, ficha);
      if (e) return e;
      const previa = semanaDe(d.lunes);
      const n: GuardiaSemana = { id: previa?.id ?? o.nuevoId(), lunes: d.lunes, farmacia: d.farmacia, persona_guardia_id: d.persona_guardia_id, persona_apoyo_sabado_id: d.persona_apoyo_sabado_id, anulada: false };
      semanas = previa ? semanas.map((s) => (s.id === previa.id ? n : s)) : [...semanas, n];
      return vistaSemana(d.lunes);
    },
    crearFestivo(fecha, nombre, ambito = AMBITO_POR_DEFECTO) {
      if (festivoDe(fecha)) return 'FESTIVO_DUPLICADO';
      const f: FestivoTa3 = { id: o.nuevoId(), fecha, nombre, ambito, anulado: false };
      festivos = [...festivos, f];
      return vistaFestivo(f);
    },
    anularFestivo(fecha) {
      const f = festivoDe(fecha);
      if (!f) return 'SIN_FESTIVO';
      const g = gfDe(fecha);
      const vista = vistaFestivo(f);
      festivos = festivos.map((x) => (x.id === f.id ? { ...x, anulado: true } : x));
      if (g) gfs = gfs.map((x) => (x.id === g.id ? { ...x, anulada: true } : x));
      return vista;
    },
    guardarGuardiaFestivo(fecha, farmacia, personaId) {
      const f = festivoDe(fecha);
      const r = reglasGuardiaFestivo(fecha, farmacia, personaId, { esFestivoComun: f !== undefined, semana: semanaDe(lunesDe(fecha)), ficha });
      if (typeof r === 'string' || !f) return typeof r === 'string' ? r : 'NO_ES_FESTIVO';
      const previa = gfDe(fecha);
      const n: GuardiaFestivo = { id: previa?.id ?? o.nuevoId(), fecha, farmacia, persona_id: r.persona, anulada: false };
      gfs = previa ? gfs.map((g) => (g.id === previa.id ? n : g)) : [...gfs, n];
      return vistaFestivo(f);
    },
    anularSemana(lunes) {
      const s = semanaDe(lunes);
      if (!s) return 'SIN_GUARDIA';
      semanas = semanas.map((x) => (x.id === s.id ? { ...x, anulada: true } : x));
      return vistaSemana(lunes);
    },
    anularGuardiaFestivo(fecha) {
      const f = festivoDe(fecha);
      const g = gfDe(fecha);
      if (!f) return 'SIN_FESTIVO';
      if (!g) return 'SIN_GUARDIA';
      gfs = gfs.map((x) => (x.id === g.id ? { ...x, anulada: true } : x));
      return vistaFestivo(f);
    },
    esFestivo,
    fechasFestivo: (anio) => festivos.filter((f) => !f.anulado && f.fecha.startsWith(`${anio}-`)).map((f) => f.fecha).sort(),
    resumenPersona: (tid, anio) => resumenGuardiasPersona(tid, anio, { semanas, festivos, guardiasFestivo: gfs }),
    datos: () => ({ semanas: semanas.map((s) => ({ ...s })), festivos: festivos.map((f) => ({ ...f })), guardiasFestivo: gfs.map((g) => ({ ...g })) }),
  };

  // Semilla de ejemplo: pasa por las mismas reglas (falla al cargar si no las cumple).
  if (o.semilla) {
    for (const s of semanasDeRotacion(o.semilla.rotacion)) {
      const r = almacen.guardarSemana(s);
      if (typeof r === 'string') throw new Error(`SEMILLA_GUARDIAS: semana ${s.lunes}: ${r}`);
    }
    for (const f of o.semilla.festivos) {
      const n = leerNombreFestivo(f.nombre);
      if (!esFecha(f.fecha) || !enAniosGuardia(f.fecha) || !n.ok) throw new Error(`SEMILLA_GUARDIAS: festivo ${f.fecha}`);
      const r = almacen.crearFestivo(f.fecha, n.nombre);
      if (typeof r === 'string') throw new Error(`SEMILLA_GUARDIAS: festivo ${f.fecha}: ${r}`);
      if (f.guardia) {
        const g = almacen.guardarGuardiaFestivo(f.fecha, f.guardia.farmacia, f.guardia.persona);
        if (typeof g === 'string') throw new Error(`SEMILLA_GUARDIAS: guardia del festivo ${f.fecha}: ${g}`);
      }
    }
  }
  return almacen;
}
