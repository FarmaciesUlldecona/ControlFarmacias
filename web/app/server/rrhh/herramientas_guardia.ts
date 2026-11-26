/**
 * TA3-4: herramientas de guardia del calendario de Trabajadores (Guardia, Apoyo sábado, Guardia otra farmacia, Festivo
 * y Goma sobre sus marcas). Módulo puro (front y pruebas): a partir de la vista de guardias del periodo y las fichas,
 * cada clic se traduce en un plan = operación de la API + pasos para volver a como estaba (deshacer) + texto + pregunta
 * de confirmación si sustituye algo de otra farmacia o da de baja un festivo. Si el clic no puede guardarse, un aviso
 * llano y ninguna operación.
 *
 * Reglas (las de TA3-REAL / migración 34, antes de escribir; el servidor y la BD las vuelven a aplicar):
 * - guardia: persona de su farmacia, de alta el sábado y el domingo de la semana; sustituye la guardia de la semana
 *   (anular + crear en REAL); conserva el apoyo si es de la misma farmacia y no es la nueva guardia.
 * - en un festivo, la herramienta Guardia pone la guardia del festivo (persona de su farmacia, de alta ese día).
 * - apoyo: en sábado, solo si la semana tiene guardia de la farmacia de la persona; distinto de la guardia; de alta.
 * - OTRA: semana o festivo de farmacia ajena, sin personas.
 * - festivo: común (farmacia null), nombre 1–60, ámbito (por defecto local); uno por día.
 *
 * Deshacer: los pasos inversos van por la clave (lunes o fecha), no por id; restaurar tras la goma crea filas nuevas
 * (ids nuevos) y los pasos anteriores de la pila siguen valiendo.
 *
 * Solo sintaxis TypeScript borrable.
 */
import type { Trabajadora } from './contrato.ts';
import { deAltaEl, diaSemana, lunesDe, sumarDias, textoPeriodoCambio } from './eventos.ts';
import {
  AMBITO_POR_DEFECTO, NOMBRE_FESTIVO_POR_DEFECTO, TEXTO_AMBITO, TEXTO_FARMACIA_GUARDIA, domingoDe, leerNombreFestivo, personaValida, sabadoDe,
  type AmbitoFestivoTa3, type FarmaciaGuardia, type FestivoVista, type GuardiasDTO, type SemanaGuardiaVista,
} from './guardias.ts';

// ---------------------------------------------------------------------------
// Operaciones y planes
// ---------------------------------------------------------------------------

export type OpGuardia =
  | { k: 'semana'; lunes: string; farmacia: FarmaciaGuardia; guardia: string | null; apoyo: string | null }
  | { k: 'anular_semana'; lunes: string }
  | { k: 'festivo'; fecha: string; nombre: string; ambito: AmbitoFestivoTa3 }
  | { k: 'anular_festivo'; fecha: string }
  | { k: 'guardia_festivo'; fecha: string; farmacia: FarmaciaGuardia; persona: string | null }
  | { k: 'anular_guardia_festivo'; fecha: string };

export interface PlanGuardia {
  /**
   * TA4: operaciones que van antes de `op`, en orden (crear el festivo del día, o anularlo y volver a crearlo con otro
   * nombre). Si `op` falla después de ellas, se ejecuta `inversa` para no dejar nada a medias.
   */
  previas?: OpGuardia[];
  op: OpGuardia;
  /** Pasos, en orden, para volver a como estaba (pila de deshacer). */
  inversa: OpGuardia[];
  /** Qué se ha hecho («Guardia PIO: Clara Roig Pujol, 4–10 ene 2027»). */
  texto: string;
  /** Pregunta antes de guardar (null: sin confirmación). */
  confirmar: string | null;
}
export type ResultadoPlan = PlanGuardia | { aviso: string };
export const esAviso = (r: ResultadoPlan): r is { aviso: string } => 'aviso' in r;

export interface ContextoGuardias {
  semana(lunes: string): SemanaGuardiaVista | undefined;
  festivo(fecha: string): FestivoVista | undefined;
  ficha(id: string): Trabajadora | undefined;
}
export function contextoGuardias(dto: GuardiasDTO | null, fichas: readonly Trabajadora[]): ContextoGuardias {
  const semanas = new Map((dto?.semanas ?? []).map((s) => [s.lunes, s]));
  const festivos = new Map((dto?.festivos ?? []).map((f) => [f.fecha, f]));
  const porId = new Map(fichas.map((t) => [t.id, t]));
  return { semana: (l) => semanas.get(l), festivo: (f) => festivos.get(f), ficha: (id) => porId.get(id) };
}

/** Petición HTTP de una operación (rutas de TA3 y TA3-4). */
export function peticionGuardia(op: OpGuardia): { metodo: 'PUT' | 'POST'; ruta: string; cuerpo: object } {
  switch (op.k) {
    case 'semana': return {
      metodo: 'PUT', ruta: `/api/rrhh/guardias/${op.lunes}`,
      cuerpo: op.farmacia === 'OTRA' ? { farmacia: 'OTRA' } : { farmacia: op.farmacia, persona_guardia_id: op.guardia, persona_apoyo_sabado_id: op.apoyo },
    };
    case 'anular_semana': return { metodo: 'PUT', ruta: `/api/rrhh/guardias/${op.lunes}/anular`, cuerpo: { confirmar: true } };
    case 'festivo': return { metodo: 'POST', ruta: '/api/rrhh/festivos', cuerpo: { fecha: op.fecha, nombre: op.nombre, ambito: op.ambito } };
    case 'anular_festivo': return { metodo: 'PUT', ruta: `/api/rrhh/festivos/${op.fecha}/anular`, cuerpo: { confirmar: true } };
    case 'guardia_festivo': return {
      metodo: 'PUT', ruta: `/api/rrhh/festivos/${op.fecha}/guardia`,
      cuerpo: op.farmacia === 'OTRA' ? { farmacia: 'OTRA' } : { farmacia: op.farmacia, persona_id: op.persona },
    };
    case 'anular_guardia_festivo': return { metodo: 'PUT', ruta: `/api/rrhh/festivos/${op.fecha}/guardia/anular`, cuerpo: { confirmar: true } };
  }
}

// ---------------------------------------------------------------------------
// Textos
// ---------------------------------------------------------------------------

const F_DIA = new Intl.DateTimeFormat('es-ES', { timeZone: 'UTC', day: 'numeric', month: 'short', year: 'numeric' });
export const textoDia = (f: string) => F_DIA.format(new Date(`${f}T00:00:00Z`));
const textoSemana = (lunes: string) => textoPeriodoCambio(lunes, sumarDias(lunes, 6));
const nombreFarmacia = (f: FarmaciaGuardia) => TEXTO_FARMACIA_GUARDIA[f];
const describirSemana = (s: SemanaGuardiaVista) => (s.farmacia === 'OTRA' ? nombreFarmacia('OTRA')
  : `${s.farmacia}${s.guardia ? ` (${s.guardia.nombre})` : ''}`);
const describirGuardiaFestivo = (g: NonNullable<FestivoVista['guardia']>) => (g.farmacia === 'OTRA' ? nombreFarmacia('OTRA')
  : `${g.farmacia}${g.persona ? ` (${g.persona.nombre})` : ''}`);
const NADA = 'No se ha guardado nada.';
const RECARGA = `Faltan los datos de guardia de ese periodo: recarga la página. ${NADA}`;

// ---------------------------------------------------------------------------
// Inversas (por clave)
// ---------------------------------------------------------------------------

/** Volver a la semana como estaba: su farmacia y personas, o sin asignar. */
export function restaurarSemana(lunes: string, s: SemanaGuardiaVista | undefined): OpGuardia[] {
  if (!s || s.farmacia === null) return [{ k: 'anular_semana', lunes }];
  return [{ k: 'semana', lunes, farmacia: s.farmacia, guardia: s.guardia?.id ?? null, apoyo: s.apoyo?.id ?? null }];
}
export function restaurarGuardiaFestivo(fecha: string, f: FestivoVista): OpGuardia[] {
  if (f.guardia === null) return [{ k: 'anular_guardia_festivo', fecha }];
  return [{ k: 'guardia_festivo', fecha, farmacia: f.guardia.farmacia, persona: f.guardia.persona?.id ?? null }];
}
/** Volver a dar de alta un festivo dado de baja con la goma, con su guardia (filas nuevas, ids nuevos). */
export function restaurarFestivo(f: FestivoVista): OpGuardia[] {
  return [{ k: 'festivo', fecha: f.fecha, nombre: f.nombre, ambito: f.ambito }, ...(f.guardia ? restaurarGuardiaFestivo(f.fecha, f).filter((o) => o.k === 'guardia_festivo') : [])];
}

// ---------------------------------------------------------------------------
// Herramientas
// ---------------------------------------------------------------------------

/** Guardia: clic en una persona en un día. En un festivo, guardia del festivo; si no, de toda la semana. */
export function planGuardia(ctx: ContextoGuardias, tid: string, fecha: string): ResultadoPlan {
  const t = ctx.ficha(tid);
  if (!t) return { aviso: `Esa persona ya no está activa. ${NADA}` };
  const farmacia: FarmaciaGuardia = t.farmacia;
  const fe = ctx.festivo(fecha);
  if (fe) {
    if (!personaValida(t, farmacia, [fecha])) return { aviso: `${t.nombre} no está de alta el ${textoDia(fecha)}. ${NADA}` };
    if (fe.guardia?.farmacia === farmacia && fe.guardia.persona?.id === tid) return { aviso: `${t.nombre} ya está de guardia en ${fe.nombre}.` };
    return {
      op: { k: 'guardia_festivo', fecha, farmacia, persona: tid },
      inversa: restaurarGuardiaFestivo(fecha, fe),
      texto: `Guardia de festivo ${farmacia}: ${t.nombre}, ${fe.nombre} (${textoDia(fecha)})`,
      confirmar: fe.guardia && fe.guardia.farmacia !== farmacia
        ? `${fe.nombre} (${textoDia(fecha)}) tiene guardia de ${describirGuardiaFestivo(fe.guardia)}. ¿Sustituirla por ${farmacia} (${t.nombre})?` : null,
    };
  }
  const lunes = lunesDe(fecha);
  const s = ctx.semana(lunes);
  if (!s) return { aviso: RECARGA };
  if (!personaValida(t, farmacia, [sabadoDe(lunes), domingoDe(lunes)])) {
    return { aviso: `${t.nombre} no está de alta el sábado y el domingo de la semana ${textoSemana(lunes)}: no puede hacer la guardia. ${NADA}` };
  }
  if (s.farmacia === farmacia && s.guardia?.id === tid) return { aviso: `${t.nombre} ya es la guardia de la semana ${textoSemana(lunes)}.` };
  const apoyo = s.farmacia === farmacia && s.apoyo && s.apoyo.id !== tid ? s.apoyo.id : null;
  return {
    op: { k: 'semana', lunes, farmacia, guardia: tid, apoyo },
    inversa: restaurarSemana(lunes, s),
    texto: `Guardia ${farmacia}: ${t.nombre}, semana ${textoSemana(lunes)}`,
    confirmar: s.farmacia !== null && s.farmacia !== farmacia
      ? `La semana ${textoSemana(lunes)} es de ${describirSemana(s)}. ¿Sustituirla por la guardia de ${farmacia} (${t.nombre})?` : null,
  };
}

/** Apoyo sábado: clic en una persona en un sábado de una semana con guardia de su farmacia. */
export function planApoyo(ctx: ContextoGuardias, tid: string, fecha: string): ResultadoPlan {
  const t = ctx.ficha(tid);
  if (!t) return { aviso: `Esa persona ya no está activa. ${NADA}` };
  if (diaSemana(fecha) !== 5) return { aviso: `El apoyo se pinta en el sábado: haz clic en el sábado de esa persona. ${NADA}` };
  const lunes = lunesDe(fecha);
  const s = ctx.semana(lunes);
  if (!s) return { aviso: RECARGA };
  if (s.farmacia !== t.farmacia || s.guardia === null) {
    return { aviso: `Ese fin de semana no hay guardia de ${t.farmacia}: pinta antes la guardia. ${NADA}` };
  }
  if (s.guardia.id === tid) return { aviso: `El apoyo del sábado tiene que ser otra persona: ${t.nombre} ya es la guardia. ${NADA}` };
  if (!personaValida(t, t.farmacia, [fecha])) return { aviso: `${t.nombre} no está de alta el sábado ${textoDia(fecha)}. ${NADA}` };
  if (s.apoyo?.id === tid) return { aviso: `${t.nombre} ya es el apoyo de ese sábado.` };
  return {
    op: { k: 'semana', lunes, farmacia: s.farmacia, guardia: s.guardia.id, apoyo: tid },
    inversa: restaurarSemana(lunes, s),
    texto: `Apoyo sábado ${t.farmacia}: ${t.nombre}, ${textoDia(fecha)}`,
    confirmar: null,
  };
}

/** Guardia otra farmacia: clic en la cabecera de un día: su semana (o el festivo, si lo es) pasa a OTRA. */
export function planOtra(ctx: ContextoGuardias, fecha: string): ResultadoPlan {
  const fe = ctx.festivo(fecha);
  if (fe) {
    if (fe.guardia?.farmacia === 'OTRA') return { aviso: `${fe.nombre} ya tiene la guardia en ${nombreFarmacia('OTRA')}.` };
    return {
      op: { k: 'guardia_festivo', fecha, farmacia: 'OTRA', persona: null },
      inversa: restaurarGuardiaFestivo(fecha, fe),
      texto: `Guardia de festivo ${nombreFarmacia('OTRA')}: ${fe.nombre} (${textoDia(fecha)})`,
      confirmar: fe.guardia ? `${fe.nombre} tiene guardia de ${describirGuardiaFestivo(fe.guardia)}. ¿Sustituirla por ${nombreFarmacia('OTRA')}?` : null,
    };
  }
  const lunes = lunesDe(fecha);
  const s = ctx.semana(lunes);
  if (!s) return { aviso: RECARGA };
  if (s.farmacia === 'OTRA') return { aviso: `La semana ${textoSemana(lunes)} ya es de ${nombreFarmacia('OTRA')}.` };
  return {
    op: { k: 'semana', lunes, farmacia: 'OTRA', guardia: null, apoyo: null },
    inversa: restaurarSemana(lunes, s),
    texto: `Guardia ${nombreFarmacia('OTRA')}: semana ${textoSemana(lunes)}`,
    confirmar: s.farmacia !== null ? `La semana ${textoSemana(lunes)} tiene guardia de ${describirSemana(s)}. ¿Sustituirla por ${nombreFarmacia('OTRA')}?` : null,
  };
}

/** Festivo: alta de un festivo común en ese día (nombre 1–60, ámbito por defecto local). */
export function planFestivo(ctx: ContextoGuardias, fecha: string, nombre: string, ambito: AmbitoFestivoTa3 = AMBITO_POR_DEFECTO): ResultadoPlan {
  const fe = ctx.festivo(fecha);
  if (fe) return { aviso: `Ese día ya es festivo (${fe.nombre}). ${NADA}` };
  const n = leerNombreFestivo(nombre);
  if (!n.ok) return { aviso: `${n.error}. ${NADA}` };
  return {
    op: { k: 'festivo', fecha, nombre: n.nombre, ambito },
    inversa: [{ k: 'anular_festivo', fecha }],
    texto: `Festivo: ${n.nombre} (${textoDia(fecha)}, ${TEXTO_AMBITO[ambito].toLowerCase()})`,
    confirmar: null,
  };
}

/**
 * TA4: Guardia festiva de un día (panel: farmacia, persona si PIO/RITA, nombre del festivo opcional). Tablas de la
 * migración 34: la guardia va en guardias_festivo (fecha, farmacia, persona) y exige un festivo común ese día
 * (festivos.descripcion = nombre, obligatorio en la BD):
 *  - día sin festivo: se crea (nombre escrito o NOMBRE_FESTIVO_POR_DEFECTO; ámbito por defecto) y después la guardia;
 *    deshacer = dar de baja ese festivo (la BD anula su guardia);
 *  - día festivo: se propone su nombre; si se cambia, el festivo se anula y se vuelve a crear con el nombre nuevo (no
 *    hay edición de festivos: anular + crear) y después la guardia; deshacer lo deja como estaba;
 *  - con el mismo nombre: solo la guardia (editar = anular + crear en REAL), deshacer = la guardia anterior.
 * OTRA nunca lleva persona; PIO/RITA, una persona de esa farmacia de alta ese día.
 */
export function planGuardiaFestiva(ctx: ContextoGuardias, fecha: string, farmacia: FarmaciaGuardia, persona: string | null, nombre: string): ResultadoPlan {
  let quien: string = nombreFarmacia('OTRA');
  let pid: string | null = null;
  if (farmacia !== 'OTRA') {
    if (!persona) return { aviso: `Elige la persona de guardia de ${farmacia}. ${NADA}` };
    const t = ctx.ficha(persona);
    if (!personaValida(t, farmacia, [fecha])) return { aviso: `${t?.nombre ?? 'Esa persona'} no es de ${farmacia} o no está de alta el ${textoDia(fecha)}. ${NADA}` };
    pid = persona;
    quien = `${farmacia} (${(t as Trabajadora).nombre})`;
  }
  const escrito = nombre.trim() === '' ? null : leerNombreFestivo(nombre);
  if (escrito && !escrito.ok) return { aviso: `${escrito.error}. ${NADA}` };
  const pedido = escrito && escrito.ok ? escrito.nombre : null;
  const op: OpGuardia = { k: 'guardia_festivo', fecha, farmacia, persona: pid };
  const fe = ctx.festivo(fecha);
  if (!fe) {
    const n = pedido ?? NOMBRE_FESTIVO_POR_DEFECTO;
    return {
      previas: [{ k: 'festivo', fecha, nombre: n, ambito: AMBITO_POR_DEFECTO }], op,
      inversa: [{ k: 'anular_festivo', fecha }],
      texto: `Guardia festiva ${quien}: ${n} (${textoDia(fecha)})`, confirmar: null,
    };
  }
  if (pedido !== null && pedido !== fe.nombre) {
    return {
      previas: [{ k: 'anular_festivo', fecha }, { k: 'festivo', fecha, nombre: pedido, ambito: fe.ambito }], op,
      inversa: [{ k: 'anular_festivo', fecha }, ...restaurarFestivo(fe)],
      texto: `Guardia festiva ${quien}: ${pedido} (antes «${fe.nombre}», ${textoDia(fecha)})`, confirmar: null,
    };
  }
  if (fe.guardia?.farmacia === farmacia && (fe.guardia.persona?.id ?? null) === pid) return { aviso: `${fe.nombre} ya tiene esa guardia festiva.` };
  return {
    op, inversa: restaurarGuardiaFestivo(fecha, fe),
    texto: `Guardia festiva ${quien}: ${fe.nombre} (${textoDia(fecha)})`, confirmar: null,
  };
}

/** TA4: personas de una farmacia que pueden hacer la guardia festiva de un día (de alta ese día). */
export function candidatasFestiva(fichas: readonly Trabajadora[], farmacia: FarmaciaGuardia, fecha: string): Trabajadora[] {
  return farmacia === 'OTRA' ? [] : fichas.filter((t) => t.farmacia === farmacia && deAltaEl(t, fecha));
}

// --- Goma (sobre la marca) -----------------------------------------------------------------------------------------

export function planGomaSemana(ctx: ContextoGuardias, lunes: string): ResultadoPlan {
  const s = ctx.semana(lunes);
  if (!s) return { aviso: RECARGA };
  if (s.farmacia === null) return { aviso: `La semana ${textoSemana(lunes)} no tiene guardia.` };
  return {
    op: { k: 'anular_semana', lunes },
    inversa: restaurarSemana(lunes, s),
    texto: `Quitada la guardia ${describirSemana(s)} de la semana ${textoSemana(lunes)}`,
    confirmar: null,
  };
}
export function planGomaApoyo(ctx: ContextoGuardias, lunes: string): ResultadoPlan {
  const s = ctx.semana(lunes);
  if (!s) return { aviso: RECARGA };
  if (s.farmacia === null || s.farmacia === 'OTRA' || s.apoyo === null || s.guardia === null) return { aviso: 'Ese sábado no tiene apoyo.' };
  return {
    op: { k: 'semana', lunes, farmacia: s.farmacia, guardia: s.guardia.id, apoyo: null },
    inversa: restaurarSemana(lunes, s),
    texto: `Quitado el apoyo del sábado (${s.apoyo.nombre}), ${textoDia(sabadoDe(lunes))}`,
    confirmar: null,
  };
}
export function planGomaFestivo(ctx: ContextoGuardias, fecha: string): ResultadoPlan {
  const fe = ctx.festivo(fecha);
  if (!fe) return { aviso: 'Ese día no es festivo.' };
  return {
    op: { k: 'anular_festivo', fecha },
    inversa: restaurarFestivo(fe),
    texto: `Festivo dado de baja: ${fe.nombre} (${textoDia(fecha)})${fe.guardia ? ', con su guardia' : ''}`,
    confirmar: `¿Dar de baja el festivo «${fe.nombre}» (${textoDia(fecha)})?${fe.guardia ? ` También se anula su guardia (${describirGuardiaFestivo(fe.guardia)}).` : ''} No se borra: queda en el historial.`,
  };
}
export function planGomaGuardiaFestivo(ctx: ContextoGuardias, fecha: string): ResultadoPlan {
  const fe = ctx.festivo(fecha);
  if (!fe) return { aviso: 'Ese día no es festivo.' };
  if (fe.guardia === null) return { aviso: `${fe.nombre} no tiene guardia.` };
  return {
    op: { k: 'anular_guardia_festivo', fecha },
    inversa: restaurarGuardiaFestivo(fecha, fe),
    texto: `Quitada la guardia de ${fe.nombre} (${describirGuardiaFestivo(fe.guardia)})`,
    confirmar: null,
  };
}

/** Vista año: guardia y apoyo de una semana elegidos en el selector (en lugar de pintar por fila). */
export function planSemanaElegida(ctx: ContextoGuardias, lunes: string, guardia: string, apoyo: string | null): ResultadoPlan {
  const t = ctx.ficha(guardia);
  if (!t) return { aviso: `Elige la persona de guardia. ${NADA}` };
  const s = ctx.semana(lunes);
  if (!s) return { aviso: RECARGA };
  if (apoyo !== null && apoyo === guardia) return { aviso: `El apoyo del sábado tiene que ser otra persona. ${NADA}` };
  if (!personaValida(t, t.farmacia, [sabadoDe(lunes), domingoDe(lunes)])) {
    return { aviso: `${t.nombre} no está de alta el sábado y el domingo de la semana ${textoSemana(lunes)}. ${NADA}` };
  }
  const a = apoyo === null ? undefined : ctx.ficha(apoyo);
  if (apoyo !== null && !personaValida(a, t.farmacia, [sabadoDe(lunes)])) return { aviso: `El apoyo tiene que ser de ${t.farmacia} y estar de alta ese sábado. ${NADA}` };
  if (s.farmacia === t.farmacia && s.guardia?.id === guardia && (s.apoyo?.id ?? null) === apoyo) return { aviso: 'Esa semana ya está así.' };
  return {
    op: { k: 'semana', lunes, farmacia: t.farmacia, guardia, apoyo },
    inversa: restaurarSemana(lunes, s),
    texto: `Guardia ${t.farmacia}: ${t.nombre}${a ? ` · apoyo ${a.nombre}` : ''}, semana ${textoSemana(lunes)}`,
    confirmar: s.farmacia !== null && s.farmacia !== t.farmacia
      ? `La semana ${textoSemana(lunes)} es de ${describirSemana(s)}. ¿Sustituirla por la guardia de ${t.farmacia} (${t.nombre})?` : null,
  };
}

/** Personas que pueden hacer la guardia (sábado y domingo) o el apoyo (sábado) de una semana, de una farmacia. */
export function candidatasSemana(fichas: readonly Trabajadora[], farmacia: FarmaciaGuardia, lunes: string, papel: 'guardia' | 'apoyo'): Trabajadora[] {
  const fechas = papel === 'guardia' ? [sabadoDe(lunes), domingoDe(lunes)] : [sabadoDe(lunes)];
  return farmacia === 'OTRA' ? [] : fichas.filter((t) => t.farmacia === farmacia && fechas.every((f) => deAltaEl(t, f)));
}

// ---------------------------------------------------------------------------
// Marcas del calendario (capa superpuesta a jornada y ausencias)
// ---------------------------------------------------------------------------

export interface MarcaGuardia {
  /** Farmacia de la guardia semanal de la persona (toda la semana, lunes a domingo). */
  guardia: FarmaciaGuardia | null;
  lunes: string | null;
  /** Apoyo del sábado (solo el sábado): farmacia de la semana. */
  apoyo: FarmaciaGuardia | null;
  /** Guardia de festivo de la persona ese día. */
  festivo: FarmaciaGuardia | null;
}
const claveMarca = (tid: string, fecha: string) => `${tid}|${fecha}`;

/** Marcas por persona y día: G (semana), A (sábado), GF (festivo). */
export function marcasGuardia(dto: GuardiasDTO | null): { de: (tid: string, fecha: string) => MarcaGuardia | undefined; otra: Set<string> } {
  const m = new Map<string, MarcaGuardia>();
  const otra = new Set<string>();
  const poner = (tid: string, fecha: string, x: Partial<MarcaGuardia>) => {
    const k = claveMarca(tid, fecha);
    m.set(k, { ...(m.get(k) ?? { guardia: null, lunes: null, apoyo: null, festivo: null }), ...x });
  };
  for (const s of dto?.semanas ?? []) {
    const dias = [0, 1, 2, 3, 4, 5, 6].map((n) => sumarDias(s.lunes, n));
    if (s.farmacia === 'OTRA') for (const f of dias) otra.add(f);
    if (s.farmacia && s.farmacia !== 'OTRA' && s.guardia) for (const f of dias) poner(s.guardia.id, f, { guardia: s.farmacia, lunes: s.lunes });
    if (s.apoyo && s.farmacia) poner(s.apoyo.id, sabadoDe(s.lunes), { apoyo: s.farmacia });
  }
  for (const f of dto?.festivos ?? []) {
    if (f.guardia?.persona) poner(f.guardia.persona.id, f.fecha, { festivo: f.guardia.farmacia });
  }
  return { de: (tid, fecha) => m.get(claveMarca(tid, fecha)), otra };
}
