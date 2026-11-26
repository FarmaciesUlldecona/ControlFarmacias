/**
 * TA4-2 Trabajadores: relleno automático de las guardias de un año por rotación (botón «Rellenar año completo» de la
 * vista Año del calendario, que también rellena la jornada habitual). Módulo puro (front y pruebas): a partir de las
 * vistas de guardias del año anterior y del año, y de las fichas, propone un plan que SOLO rellena huecos (nunca pisa
 * semanas, festivos ni guardias festivas que ya existen). Se muestra antes en una vista previa y se guarda tras
 * «Confirmar» como un único paso de deshacer (pasos inversos: anular, nunca borrar).
 *
 * Decisión de Pío (26/11/2026): «Relleno automático del año por rotación: OTRA → PIO → RITA, cíclica; la guardia semanal
 * y la guardia festiva de un día llevan rotaciones independientes que continúan desde el año anterior».
 *  - Guardia semanal: semana de lunes a domingo, identificada por su lunes (es del año de su lunes). Sigue la rotación
 *    desde la última semana con guardia anterior (año anterior o semanas ya existentes del año). Ej.: semana del
 *    27/12/2027 = PIO → semana del 3/1/2028 = RITA.
 *  - Guardia festiva: festivos del año ordenados por fecha; rotación propia desde el último festivo con guardia
 *    anterior. Ej.: 26/12/2027 = OTRA → 1/1/2028 = PIO.
 *  - Persona propuesta (solo PIO y RITA), por farmacia y por papel (G guardia semanal, A apoyo del sábado, GF guardia
 *    festiva): de las personas que hicieron ese papel en esa farmacia en los 12 meses anteriores (contando lo ya
 *    planificado), la que está de alta ese día y lleva más tiempo sin hacerlo; a igualdad, orden alfabético. El apoyo
 *    del sábado solo se propone en las farmacias donde ya se usa (alguien lo hizo en esos 12 meses).
 *  - Festivos del año, si aún no existen (por nombre): los del año anterior con el mismo día y mes, salvo los de
 *    FESTIVOS_PASCUA (Pascua calculada, sin dependencias). Los que caían en otra fecha móvil (relativa a la Pascua del
 *    año anterior) no se crean: se listan como «festivo a revisar».
 *  - Migración 34: PIO/RITA exigen persona (guardias_semana_personas_check y guardias_festivo_personas_check), así
 *    que sin persona disponible no se crea esa guardia: aviso «sin persona disponible» y queda sin asignar.
 *
 * Solo sintaxis TypeScript borrable.
 */
import type { Trabajadora } from './contrato.ts';
import { LUNES_MAX, LUNES_MIN, domingoDe, enAniosGuardia, personaDe, personaValida, sabadoDe, type AmbitoFestivoTa3, type FarmaciaGuardia, type GuardiasDTO, type PersonaGuardia } from './guardias.ts';
import { diaSemana, sumarDias } from './eventos.ts';
import type { OpGuardia } from './herramientas_guardia.ts';

/** Decisión de Pío (26/11/2026): rotación cíclica de farmacias de guardia (semanal y festiva, cada una la suya). */
export const ROTACION_FARMACIAS = ['OTRA', 'PIO', 'RITA'] as const satisfies readonly FarmaciaGuardia[];

/** Decisión de Pío (26/11/2026): festivos ligados a la Pascua (días desde el domingo de Pascua). Nombre normalizado. */
export const FESTIVOS_PASCUA: Readonly<Record<string, number>> = { 'DIVENDRES SANT': -2, 'DILLUNS PASQUA': 1 };

/**
 * Otras fechas relativas a la Pascua (Jueves Santo −3, Viernes Santo −2, Lunes de Pascua +1, Pentecostés +49, Segunda
 * Pascua +50, Corpus +60): un festivo del año anterior en una de ellas, sin estar en FESTIVOS_PASCUA, se lista para
 * revisar a mano (falla cerrado: no se copia al mismo día y mes).
 */
const DIAS_MOVILES_PASCUA = [-3, -2, 1, 49, 50, 60] as const;

/** Domingo de Pascua (calendario gregoriano; algoritmo anónimo de Meeus/Jones/Butcher). */
export function pascua(anio: number): string {
  const a = anio % 19;
  const b = Math.floor(anio / 100);
  const c = anio % 100;
  const d = Math.floor(b / 4);
  const e = b % 4;
  const f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4);
  const k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7;
  const m = Math.floor((a + 11 * h + 22 * l) / 451);
  const mes = Math.floor((h + l - 7 * m + 114) / 31);
  const dia = ((h + l - 7 * m + 114) % 31) + 1;
  return `${anio}-${String(mes).padStart(2, '0')}-${String(dia).padStart(2, '0')}`;
}

/** Nombre de festivo para comparar: sin acentos, en mayúsculas, espacios normalizados («Divendres Sant» → «DIVENDRES SANT»). */
export const normalizarNombreFestivo = (n: string) => n.normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().replace(/\s+/g, ' ').trim();

/** Farmacia siguiente en la rotación; sin ninguna anterior, la primera. */
export function siguienteFarmacia(f: FarmaciaGuardia | null): FarmaciaGuardia {
  if (f === null) return ROTACION_FARMACIAS[0];
  return ROTACION_FARMACIAS[(ROTACION_FARMACIAS.indexOf(f as (typeof ROTACION_FARMACIAS)[number]) + 1) % ROTACION_FARMACIAS.length];
}

// ---------------------------------------------------------------------------
// Plan
// ---------------------------------------------------------------------------

export type PapelGuardia = 'G' | 'A' | 'GF';
export interface SemanaRelleno { lunes: string; farmacia: FarmaciaGuardia; guardia: PersonaGuardia | null; apoyo: PersonaGuardia | null; crear: boolean }
export interface FestivoRelleno { fecha: string; nombre: string; ambito: AmbitoFestivoTa3; anterior: string; pascua: boolean }
export interface FestivaRelleno { fecha: string; nombre: string; farmacia: FarmaciaGuardia; persona: PersonaGuardia | null; crear: boolean; nuevo: boolean }
export type TipoAvisoRelleno = 'FESTIVO_A_REVISAR' | 'SIN_PERSONA' | 'FESTIVO_OCUPADO' | 'SIN_ANIO_ANTERIOR';
export interface AvisoRelleno { tipo: TipoAvisoRelleno; fecha: string | null; texto: string }
export interface PasoRelleno { op: OpGuardia; inversa: OpGuardia }
export interface PlanRelleno {
  anio: number;
  semanas: SemanaRelleno[];
  festivos: FestivoRelleno[];
  festivas: FestivaRelleno[];
  avisos: AvisoRelleno[];
  /** Operaciones en orden (festivos, semanas, guardias festivas), cada una con su paso inverso. */
  pasos: PasoRelleno[];
  /** «Guardias 2028 por rotación: 52 semanas, 14 festivos y 14 guardias festivas». */
  texto: string;
}

const dm = (f: string) => `${Number(f.slice(8))}/${Number(f.slice(5, 7))}`;
const plural = (n: number, uno: string, varios: string) => `${n} ${n === 1 ? uno : varios}`;
/** El mismo día de hace un año (los 12 meses anteriores empiezan ahí). */
const haceUnAnio = (f: string) => `${Number(f.slice(0, 4)) - 1}${f.slice(4)}`;

interface Hecho { farmacia: FarmaciaGuardia; papel: PapelGuardia; persona: string; fecha: string }

/**
 * Persona propuesta para un papel: de las que lo hicieron en esa farmacia en los 12 meses anteriores a `fecha`, la que
 * está de alta en `alta` y lleva más tiempo sin hacerlo; a igualdad, orden alfabético. `usado`: alguien lo hizo.
 */
export function personaPropuesta(hechos: readonly Hecho[], fichas: ReadonlyMap<string, Trabajadora>, farmacia: FarmaciaGuardia, papel: PapelGuardia,
  fecha: string, alta: readonly string[], excluir: string | null = null): { persona: Trabajadora | null; usado: boolean } {
  const desde = haceUnAnio(fecha);
  const ultima = new Map<string, string>();
  for (const h of hechos) {
    if (h.farmacia !== farmacia || h.papel !== papel || h.fecha < desde || h.fecha >= fecha) continue;
    if ((ultima.get(h.persona) ?? '') < h.fecha) ultima.set(h.persona, h.fecha);
  }
  const candidatas = [...ultima.entries()]
    .map(([id, f]) => ({ t: fichas.get(id), f }))
    .filter((x): x is { t: Trabajadora; f: string } => x.t !== undefined && x.t.id !== excluir && personaValida(x.t, farmacia, alta))
    .sort((a, b) => a.f.localeCompare(b.f) || a.t.nombre.localeCompare(b.t.nombre, 'es'));
  return { persona: candidatas[0]?.t ?? null, usado: ultima.size > 0 };
}

/**
 * Plan de relleno de un año. `previo`: vista del año anterior (null si no se puede leer: la rotación empieza en
 * ROTACION_FARMACIAS[0] y sin historial de personas, con aviso). `actual`: vista del año (lo que ya existe no se toca).
 */
export function planRellenoGuardias(o: { anio: number; previo: GuardiasDTO | null; actual: GuardiasDTO; fichas: readonly Trabajadora[] }): PlanRelleno {
  const { anio } = o;
  const ini = `${anio}-01-01`;
  const fin = `${anio}-12-31`;
  const fichas = new Map(o.fichas.map((t) => [t.id, t]));
  const avisos: AvisoRelleno[] = [];
  const pasos: PasoRelleno[] = [];
  if (o.previo === null) {
    avisos.push({ tipo: 'SIN_ANIO_ANTERIOR', fecha: null, texto: `Sin guardias de ${anio - 1}: la rotación empieza en ${ROTACION_FARMACIAS[0]} y no hay historial para proponer personas.` });
  }

  // Semanas y festivos conocidos (el año anterior y el año; lo del año manda).
  const semanas = new Map([...(o.previo?.semanas ?? []), ...o.actual.semanas].map((s) => [s.lunes, s]));
  const festivosVista = new Map([...(o.previo?.festivos ?? []), ...o.actual.festivos].map((f) => [f.fecha, f]));
  const hechos: Hecho[] = [];
  for (const s of semanas.values()) {
    if (s.farmacia === null || s.farmacia === 'OTRA') continue;
    if (s.guardia) hechos.push({ farmacia: s.farmacia, papel: 'G', persona: s.guardia.id, fecha: sabadoDe(s.lunes) });
    if (s.apoyo) hechos.push({ farmacia: s.farmacia, papel: 'A', persona: s.apoyo.id, fecha: sabadoDe(s.lunes) });
  }
  for (const f of festivosVista.values()) {
    if (f.guardia?.persona && f.guardia.farmacia !== 'OTRA') hechos.push({ farmacia: f.guardia.farmacia, papel: 'GF', persona: f.guardia.persona.id, fecha: f.fecha });
  }

  // 1. Festivos del año que aún no existen (por nombre), a partir de los del año anterior.
  const delAnio = o.actual.festivos.filter((f) => f.fecha >= ini && f.fecha <= fin);
  const nombres = new Set(delAnio.map((f) => normalizarNombreFestivo(f.nombre)));
  const ocupadas = new Map(delAnio.map((f) => [f.fecha, f.nombre]));
  const festivos: FestivoRelleno[] = [];
  const previos = (o.previo?.festivos ?? []).filter((f) => f.fecha.startsWith(`${anio - 1}-`)).sort((a, b) => a.fecha.localeCompare(b.fecha));
  const pascuaAntes = pascua(anio - 1);
  for (const f of previos) {
    const n = normalizarNombreFestivo(f.nombre);
    if (nombres.has(n)) continue;
    const desplazamiento = FESTIVOS_PASCUA[n];
    let fecha: string;
    if (desplazamiento !== undefined) fecha = sumarDias(pascua(anio), desplazamiento);
    else if (DIAS_MOVILES_PASCUA.some((k) => sumarDias(pascuaAntes, k) === f.fecha)) {
      avisos.push({ tipo: 'FESTIVO_A_REVISAR', fecha: f.fecha, texto: `Festivo a revisar: ${f.nombre} (${dm(f.fecha)}/${anio - 1}) cae en fecha móvil (relativa a la Pascua): no se crea; dalo de alta a mano.` });
      continue;
    } else if (f.fecha.slice(5) === '02-29') {
      avisos.push({ tipo: 'FESTIVO_A_REVISAR', fecha: f.fecha, texto: `Festivo a revisar: ${f.nombre} (29/2/${anio - 1}) no existe en ${anio}: no se crea.` });
      continue;
    } else fecha = `${anio}${f.fecha.slice(4)}`;
    if (!enAniosGuardia(fecha)) continue;
    const ya = ocupadas.get(fecha);
    if (ya !== undefined) {
      avisos.push({ tipo: 'FESTIVO_OCUPADO', fecha, texto: `Festivo a revisar: ${f.nombre} iría el ${dm(fecha)}, que ya es festivo (${ya}): no se crea.` });
      continue;
    }
    festivos.push({ fecha, nombre: f.nombre, ambito: f.ambito, anterior: f.fecha, pascua: desplazamiento !== undefined });
    nombres.add(n);
    ocupadas.set(fecha, f.nombre);
    pasos.push({ op: { k: 'festivo', fecha, nombre: f.nombre, ambito: f.ambito }, inversa: { k: 'anular_festivo', fecha } });
  }

  // 2. Guardia semanal: lunes del año, rotación desde la última semana con guardia anterior.
  const lunesAnio: string[] = [];
  for (let l = sumarDias(ini, (7 - diaSemana(ini)) % 7); l <= fin; l = sumarDias(l, 7)) if (l >= LUNES_MIN && l <= LUNES_MAX) lunesAnio.push(l);
  let ultima: FarmaciaGuardia | null = null;
  const primero = lunesAnio[0] ?? ini;
  for (const s of [...semanas.values()].filter((x) => x.lunes < primero && x.farmacia !== null).sort((a, b) => a.lunes.localeCompare(b.lunes))) ultima = s.farmacia;
  const semanasPlan: SemanaRelleno[] = [];
  for (const lunes of lunesAnio) {
    const s = semanas.get(lunes);
    if (s && s.farmacia !== null) { ultima = s.farmacia; continue; }
    const farmacia = siguienteFarmacia(ultima);
    ultima = farmacia;
    if (farmacia === 'OTRA') {
      semanasPlan.push({ lunes, farmacia, guardia: null, apoyo: null, crear: true });
      pasos.push({ op: { k: 'semana', lunes, farmacia, guardia: null, apoyo: null }, inversa: { k: 'anular_semana', lunes } });
      continue;
    }
    const [sab, dom] = [sabadoDe(lunes), domingoDe(lunes)];
    const g = personaPropuesta(hechos, fichas, farmacia, 'G', sab, [sab, dom]);
    if (g.persona === null) {
      semanasPlan.push({ lunes, farmacia, guardia: null, apoyo: null, crear: false });
      avisos.push({ tipo: 'SIN_PERSONA', fecha: lunes, texto: `Semana del ${dm(lunes)}: ${farmacia} sin persona disponible para la guardia; queda sin asignar.` });
      continue;
    }
    const a = personaPropuesta(hechos, fichas, farmacia, 'A', sab, [sab], g.persona.id);
    if (a.usado && a.persona === null) {
      avisos.push({ tipo: 'SIN_PERSONA', fecha: sab, texto: `Sábado ${dm(sab)}: ${farmacia} sin persona disponible para el apoyo; la guardia va sin apoyo.` });
    }
    hechos.push({ farmacia, papel: 'G', persona: g.persona.id, fecha: sab });
    if (a.persona) hechos.push({ farmacia, papel: 'A', persona: a.persona.id, fecha: sab });
    semanasPlan.push({ lunes, farmacia, guardia: personaDe(g.persona), apoyo: personaDe(a.persona ?? undefined), crear: true });
    pasos.push({ op: { k: 'semana', lunes, farmacia, guardia: g.persona.id, apoyo: a.persona?.id ?? null }, inversa: { k: 'anular_semana', lunes } });
  }

  // 3. Guardia festiva de un día: festivos del año (los que hay y los nuevos), rotación propia desde el último festivo
  //    con guardia anterior.
  const delPlan = new Set(festivos.map((f) => f.fecha));
  const todos = [...delAnio.map((f) => ({ fecha: f.fecha, nombre: f.nombre, guardia: f.guardia?.farmacia ?? null })),
    ...festivos.map((f) => ({ fecha: f.fecha, nombre: f.nombre, guardia: null }))].sort((a, b) => a.fecha.localeCompare(b.fecha));
  let ultimaF: FarmaciaGuardia | null = null;
  for (const f of [...festivosVista.values()].filter((x) => x.fecha < ini && x.guardia !== null).sort((a, b) => a.fecha.localeCompare(b.fecha))) ultimaF = f.guardia?.farmacia ?? null;
  const festivas: FestivaRelleno[] = [];
  for (const f of todos) {
    if (f.guardia !== null) { ultimaF = f.guardia; continue; }
    const farmacia = siguienteFarmacia(ultimaF);
    ultimaF = farmacia;
    const nuevo = delPlan.has(f.fecha);
    if (farmacia === 'OTRA') {
      festivas.push({ fecha: f.fecha, nombre: f.nombre, farmacia, persona: null, crear: true, nuevo });
      pasos.push({ op: { k: 'guardia_festivo', fecha: f.fecha, farmacia, persona: null }, inversa: { k: 'anular_guardia_festivo', fecha: f.fecha } });
      continue;
    }
    const p = personaPropuesta(hechos, fichas, farmacia, 'GF', f.fecha, [f.fecha]);
    if (p.persona === null) {
      festivas.push({ fecha: f.fecha, nombre: f.nombre, farmacia, persona: null, crear: false, nuevo });
      avisos.push({ tipo: 'SIN_PERSONA', fecha: f.fecha, texto: `${dm(f.fecha)} ${f.nombre}: ${farmacia} sin persona disponible para la guardia festiva; queda sin asignar.` });
      continue;
    }
    hechos.push({ farmacia, papel: 'GF', persona: p.persona.id, fecha: f.fecha });
    festivas.push({ fecha: f.fecha, nombre: f.nombre, farmacia, persona: personaDe(p.persona), crear: true, nuevo });
    pasos.push({ op: { k: 'guardia_festivo', fecha: f.fecha, farmacia, persona: p.persona.id }, inversa: { k: 'anular_guardia_festivo', fecha: f.fecha } });
  }

  // Pasos: festivos, semanas, guardias festivas (en ese orden; las guardias festivas necesitan su festivo).
  const orden = (op: OpGuardia) => (op.k === 'festivo' ? 0 : op.k === 'semana' ? 1 : 2);
  pasos.sort((a, b) => orden(a.op) - orden(b.op));
  const ns = semanasPlan.filter((s) => s.crear).length;
  const nf = festivas.filter((f) => f.crear).length;
  return {
    anio, semanas: semanasPlan, festivos, festivas, avisos, pasos,
    texto: `Guardias ${anio} por rotación: ${plural(ns, 'semana', 'semanas')}, ${plural(festivos.length, 'festivo', 'festivos')} y ${plural(nf, 'guardia festiva', 'guardias festivas')}`,
  };
}
