/**
 * TA-FICHA Trabajadores: ficha anual de cada persona y resumen de plantilla. Puro (sin Node ni BD): lo usan el
 * servidor (FIXTURES y REAL, sobre las mismas lecturas: fichas y eventos del año —calendario— y convenio_anual), las
 * pruebas y check_fixtures. En REAL todo esto es solo lectura.
 *
 * Reglas de Pío (TA-FICHA):
 *  - Vacaciones: TA-REAL-2, los días naturales del año salen de convenio_anual.vacaciones_dias_naturales (30 al crear o
 *    completar 2026–2028); sin el dato, «pendiente» (derecho null). Media jornada: los mismos días. Alta o baja dentro
 *    del año: proporcional a los días en alta, redondeado al entero hacia arriba (REDONDEO_PROPORCIONAL, configurable).
 *  - TA-REAL-2: días extra por persona y año (trabajadoras_ajustes_anuales, la fila no anulada): derecho = base
 *    (proporcional si procede) + extra.
 *  - Conteo en días naturales: un periodo de vacaciones va del primer al último día laborable seguidos de VACACIONES y
 *    cuentan todos los días naturales entre ambos (fines de semana y festivos intermedios incluidos). Una sola franja de
 *    una jornada completa = 0,5 días; la franja única de una media jornada = 1 día.
 *  - Libre disposición: convenio_anual.asuntos_propios_dias del año; mismas medias franjas (0,5 / 1).
 *  - Permiso médico: convenio_anual.permiso_medico_horas (24) frente a las horas_efectivas de PERMISO_MEDICO.
 *  - Horas del año (solo si computa el convenio): objetivo, confirmadas, planificadas y pendientes; si confirmadas +
 *    planificadas superan el objetivo, «Exceso de X h ≈ Y días que podrían ser vacaciones» (estimación; Y = X / horas
 *    diarias). Festivos aún no descontados (TA3). Titular: horas registradas, sin objetivo.
 *  - Aviso si desde el 1 de octubre (AVISO_VACACIONES_DESDE, configurable) quedan vacaciones sin planificar.
 *  - Días de baja: solo el número (nunca el motivo).
 *
 * Solo sintaxis TypeScript borrable.
 */
import { ANIOS_CONVENIO, objetivoAnual, ordenFichas, type AjusteAnual, type ConvenioAnual, type FiltroFarmacia, type Trabajadora } from './contrato.ts';
import { FRANJAS_DE_JORNADA, aDia, deDia, esLaborable, horasQueSuman, type EventoCalendario, type TipoEvento } from './eventos.ts';

// ---------------------------------------------------------------------------
// Constantes (únicos puntos de cada regla)
// ---------------------------------------------------------------------------

export type Redondeo = 'ENTERO_ARRIBA' | 'MEDIO_DIA_ARRIBA';
/** Redondeo del derecho proporcional (alta o baja dentro del año). Regla de Pío: entero hacia arriba. */
export const REDONDEO_PROPORCIONAL: Redondeo = 'ENTERO_ARRIBA';
/** MM-DD desde el que se avisa de vacaciones sin planificar (regla de Pío: 1 de octubre). */
export const AVISO_VACACIONES_DESDE = '10-01';
/**
 * Tipos cuyas horas_efectivas cuentan para el objetivo anual (tiempo de trabajo o permiso retribuido). TA-FICHA-2 (regla
 * de Pío): el descanso compensatorio (día libre tras la semana de guardia de 24 h) cuenta como trabajado, con las horas
 * de la jornada normal de la persona. No cuentan: vacaciones (el objetivo ya las descuenta), permiso no retribuido,
 * festivo, guardia y localizada (TA3).
 */
export const TIPOS_HORAS_COMPUTAN: readonly TipoEvento[] = ['JORNADA', 'ASUNTOS_PROPIOS', 'PERMISO_RETRIBUIDO', 'PERMISO_MEDICO', 'BAJA', 'DESCANSO_COMPENSATORIO'];
/** Tipos que son ausencia (próximas ausencias). */
export const TIPOS_AUSENCIA: readonly TipoEvento[] = [
  'VACACIONES', 'ASUNTOS_PROPIOS', 'PERMISO_RETRIBUIDO', 'PERMISO_NO_RETRIBUIDO', 'PERMISO_MEDICO', 'DESCANSO_COMPENSATORIO', 'BAJA',
];
export const MAX_PROXIMAS_AUSENCIAS = 3;
export const TEXTO_FESTIVOS_PENDIENTES = 'Festivos aún no descontados (TA3)';
/** TA-REAL-2: vacaciones sin dato en convenio_anual. */
export const TEXTO_VACACIONES_PENDIENTE = 'pendiente';

/** `ajustes`: filas de trabajadoras_ajustes_anuales (se usa la no anulada de la persona y el año). */
export interface OpcionesFicha { redondeo?: Redondeo; avisoDesde?: string; ajustes?: readonly AjusteAnual[] }

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

/** Periodo de un tipo: días naturales del primer al último día laborable seguidos; media franja suelta = parcial. */
export interface Periodo { tipo: TipoEvento; desde: string; hasta: string; dias: number; parcial: boolean }

export type CodigoAviso = 'VACACIONES_SIN_PLANIFICAR' | 'VACACIONES_DE_MAS' | 'EXCESO_HORAS' | 'LIBRE_DISPOSICION_DE_MAS'
  | 'PERMISO_MEDICO_DE_MAS' | 'SIN_CONVENIO' | 'VACACIONES_SIN_DATO';
export interface AvisoFicha { codigo: CodigoAviso; texto: string }

export interface FichaAnual {
  trabajadora: Trabajadora;
  anio: number;
  hoy: string;
  dias_en_alta: number;
  dias_anio: number;
  /** true si convenio_anual tiene el año. */
  convenio_anio: boolean;
  vacaciones: {
    /** convenio_anual.vacaciones_dias_naturales del año; null = pendiente. */
    base: number | null;
    fuente: string | null;
    proporcional: boolean;
    /** Base, proporcional y redondeada si hay alta o baja en el año; null = pendiente. */
    derecho_base: number | null;
    /** Días extra del ajuste no anulado (0 sin ajuste). */
    dias_extra: number;
    ajuste: AjusteAnual | null;
    /** derecho_base + dias_extra; null = pendiente. */
    derecho: number | null;
    disfrutadas: number; planificadas: number;
    /** derecho − disfrutadas − planificadas (negativo = por encima del derecho); null = pendiente. */
    pendientes: number | null;
    periodos: Periodo[];
  };
  libre_disposicion: { derecho: number | null; usadas: number; restantes: number | null };
  permiso_medico: { horas: number | null; usadas: number; restantes: number | null };
  horas: {
    computa: boolean;
    /** Objetivo del año (proporcional si alta o baja dentro del año); null si no computa o no hay convenio. */
    objetivo: number | null;
    /** Objetivo del año completo (contrato.objetivoAnual). */
    objetivo_anual: number | null;
    proporcional: boolean;
    confirmadas: number; planificadas: number; registradas: number;
    pendientes: number | null; exceso: number | null;
    /** Estimación: exceso / horas diarias (1 decimal). */
    exceso_dias: number | null;
  };
  proximas_ausencias: Periodo[];
  dias_baja: number;
  avisos: AvisoFicha[];
}

export interface ReglasFichaDTO {
  /** Del convenio del año (null = pendiente). */
  vacaciones_dias: number | null; vacaciones_fuente: string | null;
  redondeo: Redondeo; aviso_desde: string; anios: number[]; tipos_horas: TipoEvento[];
}
export interface ResumenPlantillaDTO { farmacia: FiltroFarmacia; anio: number; hoy: string; filas: FichaAnual[]; reglas: ReglasFichaDTO }
export interface FichaAnualDTO {
  anio: number; hoy: string; reglas: ReglasFichaDTO;
  ficha: FichaAnual | null;
  /** Sin ficha: anulada o sin días de alta en el año. */
  motivo: 'ANULADA' | 'SIN_ALTA_EN_EL_ANIO' | null;
}

export const reglasFicha = (convenio: readonly ConvenioAnual[], anio: number, o: OpcionesFicha = {}): ReglasFichaDTO => {
  const c = convenio.find((x) => x.anio === anio) ?? null;
  return {
    vacaciones_dias: c?.vacaciones_dias_naturales ?? null, vacaciones_fuente: c?.vacaciones_fuente ?? null, redondeo: o.redondeo ?? REDONDEO_PROPORCIONAL,
    aviso_desde: o.avisoDesde ?? AVISO_VACACIONES_DESDE, anios: [...ANIOS_CONVENIO], tipos_horas: [...TIPOS_HORAS_COMPUTAN],
  };
};
/** Ajuste no anulado de una persona y un año. */
export const ajusteDe = (ajustes: readonly AjusteAnual[] | undefined, trabajadoraId: string, anio: number): AjusteAnual | null =>
  (ajustes ?? []).find((a) => a.trabajadora_id === trabajadoraId && a.anio === anio && !a.anulada) ?? null;

// ---------------------------------------------------------------------------
// Reglas
// ---------------------------------------------------------------------------

const r2 = (x: number) => Math.round(x * 100) / 100;
const r1 = (x: number) => Math.round(x * 10) / 10;
const EPS = 1e-9;
const NUM = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 });
const n = (x: number) => NUM.format(x);
const dias = (x: number) => `${n(x)} ${x === 1 ? 'día' : 'días'}`;

export const diasDelAnio = (anio: number) => aDia(`${anio + 1}-01-01`) - aDia(`${anio}-01-01`);

/** Días en alta dentro del año (de fecha_alta a fecha_baja, ambos incluidos); anulada: 0. */
export function diasEnAlta(t: Pick<Trabajadora, 'fecha_alta' | 'fecha_baja' | 'anulada'>, anio: number): number {
  if (t.anulada) return 0;
  const ini = t.fecha_alta > `${anio}-01-01` ? t.fecha_alta : `${anio}-01-01`;
  const fin = t.fecha_baja !== null && t.fecha_baja < `${anio}-12-31` ? t.fecha_baja : `${anio}-12-31`;
  return fin < ini ? 0 : aDia(fin) - aDia(ini) + 1;
}

export function redondear(x: number, modo: Redondeo): number {
  const r = modo === 'ENTERO_ARRIBA' ? Math.ceil(x - EPS) : Math.ceil(x * 2 - EPS) / 2;
  return r === 0 ? 0 : r; // sin -0
}

/**
 * Derecho de vacaciones del convenio (`base`, días naturales; también media jornada); alta o baja en el año,
 * proporcional y redondeado. Sin base (convenio sin el dato): derecho null («pendiente»).
 */
export function derechoVacaciones(t: Pick<Trabajadora, 'fecha_alta' | 'fecha_baja' | 'anulada'>, anio: number, base: number | null, o: OpcionesFicha = {}) {
  const enAlta = diasEnAlta(t, anio);
  const total = diasDelAnio(anio);
  const proporcional = enAlta < total;
  const derecho = base === null ? null : proporcional ? redondear(base * enAlta / total, o.redondeo ?? REDONDEO_PROPORCIONAL) : base;
  return { base, dias_en_alta: enAlta, dias_anio: total, proporcional, derecho };
}

/**
 * Valor de cada día de un tipo: franjas con ese tipo / franjas de la ficha (completa: 0,5 por franja; media jornada:
 * su franja única = 1). Como máximo 1 por día.
 */
export function valoresPorDia(evs: readonly Pick<EventoCalendario, 'fecha' | 'tipo'>[], t: Pick<Trabajadora, 'tipo_jornada'>, tipo: TipoEvento): Map<string, number> {
  const franjas = FRANJAS_DE_JORNADA[t.tipo_jornada].length;
  const m = new Map<string, number>();
  for (const e of evs) if (e.tipo === tipo) m.set(e.fecha, Math.min(1, (m.get(e.fecha) ?? 0) + 1 / franjas));
  return m;
}

/** Entre a y b (excluidos) todos los días son puente (no laborables: fin de semana o festivo de la persona). */
function seguidos(a: string, b: string, puente: (f: string) => boolean): boolean {
  for (let d = aDia(a) + 1; d < aDia(b); d++) if (!puente(deDia(d))) return false;
  return true;
}

/**
 * Periodos de un tipo en días naturales: días completos seguidos (solo separados por días no laborables) forman un
 * periodo que cuenta todos los días naturales del primero al último; un día con media franja cuenta 0,5 por separado.
 */
export function periodos(evs: readonly Pick<EventoCalendario, 'fecha' | 'tipo'>[], t: Pick<Trabajadora, 'tipo_jornada'>, tipo: TipoEvento,
  puente: (f: string) => boolean = (f) => !esLaborable(f)): Periodo[] {
  const m = valoresPorDia(evs, t, tipo);
  const r: Periodo[] = [];
  let actual: Periodo | null = null;
  for (const f of [...m.keys()].sort()) {
    const v = m.get(f) as number;
    if (v < 1 - EPS) { actual = null; r.push({ tipo, desde: f, hasta: f, dias: v, parcial: true }); continue; }
    if (actual && seguidos(actual.hasta, f, puente)) { actual.hasta = f; actual.dias = aDia(f) - aDia(actual.desde) + 1; }
    else { actual = { tipo, desde: f, hasta: f, dias: 1, parcial: false }; r.push(actual); }
  }
  return r;
}

/** Reparte los días de unos periodos en hasta hoy (incluido) y desde mañana. */
export function partirEnHoy(ps: readonly Periodo[], hoy: string): { hasta_hoy: number; desde_manana: number } {
  let pasado = 0;
  let futuro = 0;
  for (const p of ps) {
    if (p.parcial) { if (p.desde <= hoy) pasado += p.dias; else futuro += p.dias; continue; }
    const fin = p.hasta < hoy ? p.hasta : hoy;
    const ya = fin >= p.desde ? aDia(fin) - aDia(p.desde) + 1 : 0;
    pasado += ya;
    futuro += p.dias - ya;
  }
  return { hasta_hoy: pasado, desde_manana: futuro };
}

const suma = (ps: readonly Periodo[]) => ps.reduce((s, p) => s + p.dias, 0);

/** Ficha anual de una persona. `eventos`: los suyos (se filtran por persona y año por si acaso). */
export function calcularFichaAnual(t: Trabajadora, eventos: readonly EventoCalendario[], convenio: readonly ConvenioAnual[], anio: number, hoy: string,
  o: OpcionesFicha = {}): FichaAnual {
  const evs = eventos.filter((e) => e.trabajadora_id === t.id && e.fecha.startsWith(`${anio}-`));
  const c = convenio.find((x) => x.anio === anio) ?? null;
  const festivos = new Set(evs.filter((e) => e.tipo === 'FESTIVO').map((e) => e.fecha));
  const puente = (f: string) => !esLaborable(f) || festivos.has(f);

  // Vacaciones: base del convenio (o pendiente) + días extra del ajuste.
  const der = derechoVacaciones(t, anio, c?.vacaciones_dias_naturales ?? null, o);
  const ajuste = ajusteDe(o.ajustes, t.id, anio);
  const extra = ajuste?.vacaciones_dias_extra ?? 0;
  const derechoVac = der.derecho === null ? null : der.derecho + extra;
  const pv = periodos(evs, t, 'VACACIONES', puente);
  const vac = partirEnHoy(pv, hoy);
  const pendientesVac = derechoVac === null ? null : derechoVac - vac.hasta_hoy - vac.desde_manana;

  // Libre disposición y permiso médico.
  const usadasLd = [...valoresPorDia(evs, t, 'ASUNTOS_PROPIOS').values()].reduce((s, v) => s + v, 0);
  const usadasPm = r2(evs.filter((e) => e.tipo === 'PERMISO_MEDICO').reduce((s, e) => s + e.horas_efectivas, 0));

  // Horas del año.
  const cuentan = evs.filter((e) => TIPOS_HORAS_COMPUTAN.includes(e.tipo));
  const confirmadas = r2(cuentan.filter((e) => e.estado === 'CONFIRMADO').reduce((s, e) => s + horasQueSuman(e), 0));
  const planificadas = r2(cuentan.filter((e) => e.estado === 'PLANIFICADO').reduce((s, e) => s + horasQueSuman(e), 0));
  const registradas = r2(confirmadas + planificadas);
  const objetivoAnio = c && t.computa_convenio ? objetivoAnual(t, c).objetivo_horas : null;
  const objetivo = objetivoAnio === null ? null : der.proporcional ? r1(objetivoAnio * der.dias_en_alta / der.dias_anio) : objetivoAnio;
  const exceso = objetivo !== null && registradas > objetivo + EPS ? r2(registradas - objetivo) : null;

  // Próximas ausencias (desde hoy) y días de baja.
  const ausencias = TIPOS_AUSENCIA.flatMap((tipo) => periodos(evs, t, tipo, puente))
    .filter((p) => p.hasta >= hoy).sort((a, b) => a.desde.localeCompare(b.desde) || a.tipo.localeCompare(b.tipo)).slice(0, MAX_PROXIMAS_AUSENCIAS);
  const diasBaja = suma(periodos(evs, t, 'BAJA', puente));

  const ficha: FichaAnual = {
    trabajadora: { ...t }, anio, hoy, dias_en_alta: der.dias_en_alta, dias_anio: der.dias_anio, convenio_anio: c !== null,
    vacaciones: {
      base: der.base, fuente: c?.vacaciones_fuente ?? null, proporcional: der.proporcional, derecho_base: der.derecho, dias_extra: extra,
      ajuste: ajuste ? { ...ajuste } : null, derecho: derechoVac,
      disfrutadas: vac.hasta_hoy, planificadas: vac.desde_manana, pendientes: pendientesVac, periodos: pv,
    },
    libre_disposicion: { derecho: c ? c.asuntos_propios_dias : null, usadas: usadasLd, restantes: c ? c.asuntos_propios_dias - usadasLd : null },
    permiso_medico: { horas: c ? c.permiso_medico_horas : null, usadas: usadasPm, restantes: c ? r2(c.permiso_medico_horas - usadasPm) : null },
    horas: {
      computa: t.computa_convenio, objetivo, objetivo_anual: objetivoAnio, proporcional: objetivo !== null && der.proporcional,
      confirmadas, planificadas, registradas,
      pendientes: objetivo === null ? null : exceso !== null ? 0 : r2(objetivo - registradas),
      exceso, exceso_dias: exceso === null ? null : r1(exceso / t.horas_diarias),
    },
    proximas_ausencias: ausencias,
    dias_baja: diasBaja,
    avisos: [],
  };
  ficha.avisos = avisosDe(ficha, o);
  return ficha;
}

/** Avisos de la ficha (texto llano; el de octubre, solo dentro del año y desde la fecha configurada). */
export function avisosDe(f: FichaAnual, o: OpcionesFicha = {}): AvisoFicha[] {
  const a: AvisoFicha[] = [];
  if (!f.convenio_anio) a.push({ codigo: 'SIN_CONVENIO', texto: `Sin convenio de ${f.anio} en la base de datos` });
  else if (f.vacaciones.base === null) a.push({ codigo: 'VACACIONES_SIN_DATO', texto: `Vacaciones de ${f.anio} pendientes: el convenio no tiene los días` });
  const desde = `${f.anio}-${o.avisoDesde ?? AVISO_VACACIONES_DESDE}`;
  const pend = f.vacaciones.pendientes;
  if (pend !== null && pend > EPS && f.hoy >= desde && f.hoy <= `${f.anio}-12-31` && f.dias_en_alta > 0) {
    a.push({ codigo: 'VACACIONES_SIN_PLANIFICAR', texto: `Quedan ${dias(pend)} de vacaciones sin planificar` });
  }
  if (pend !== null && pend < -EPS) a.push({ codigo: 'VACACIONES_DE_MAS', texto: `${dias(-pend)} de vacaciones por encima del derecho` });
  if (f.horas.exceso !== null) {
    a.push({ codigo: 'EXCESO_HORAS', texto: `Exceso de ${n(f.horas.exceso)} h ≈ ${dias(f.horas.exceso_dias as number)} que podrían ser vacaciones (estimación)` });
  }
  if (f.libre_disposicion.restantes !== null && f.libre_disposicion.restantes < -EPS) {
    a.push({ codigo: 'LIBRE_DISPOSICION_DE_MAS', texto: `${dias(-f.libre_disposicion.restantes)} de libre disposición por encima del convenio` });
  }
  if (f.permiso_medico.restantes !== null && f.permiso_medico.restantes < -EPS) {
    a.push({ codigo: 'PERMISO_MEDICO_DE_MAS', texto: `${n(-f.permiso_medico.restantes)} h de permiso médico por encima del convenio` });
  }
  return a;
}

/** Resumen de plantilla: una ficha anual por persona sin anular y con algún día de alta en el año. */
export function resumenPlantilla(fichas: readonly Trabajadora[], eventos: readonly EventoCalendario[], convenio: readonly ConvenioAnual[], anio: number, hoy: string,
  o: OpcionesFicha = {}): FichaAnual[] {
  const porPersona = new Map<string, EventoCalendario[]>();
  for (const e of eventos) { const l = porPersona.get(e.trabajadora_id); if (l) l.push(e); else porPersona.set(e.trabajadora_id, [e]); }
  return fichas.filter((t) => diasEnAlta(t, anio) > 0).sort(ordenFichas)
    .map((t) => calcularFichaAnual(t, porPersona.get(t.id) ?? [], convenio, anio, hoy, o));
}

/** Año admitido (los del convenio firmado). */
export const anioFicha = (v: unknown): number | null => {
  const a = typeof v === 'string' && /^\d{4}$/.test(v) ? Number(v) : typeof v === 'number' ? v : NaN;
  return ANIOS_CONVENIO.includes(a) ? a : null;
};
