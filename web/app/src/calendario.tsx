// TA2 Trabajadores: calendario. Vistas semana / mes / año / por persona; paleta de tipos (también leyenda, colores
// configurables en este navegador); pintar con clic, selección múltiple o arrastrando; goma; rellenar jornada
// habitual; confirmar; deshacer el último cambio; historial de cada cambio. Solo datos de ejemplo en memoria del
// servidor (modo FIXTURES). En modo REAL: "Módulo pendiente de conexión (T1)" (marco Modulo).
// TA2-2: mañana y tarde por separado (en la semana, dos subfilas por persona; en mes y por persona, un clic es el día
// completo: sus franjas); rellenar el año completo; nota opcional por evento (sin datos de salud); historial plegado.
// TA2-4: mensajes en días laborables × personas; «Añadir nota» en la barra de selección (una franja: su editor; varias:
// la misma nota, omitiendo vacías y confirmadas); campo Nota siempre visible en el detalle del día.
// TA-REAL: horas = horas_efectivas (vacías = las de la ficha); 11 tipos (FESTIVO, TURNO_GUARDIA y LOCALIZADA se ven, se
// pintan desde TA3; guardia y localizada no suman horas); fuera del alta o la baja de la persona no se pinta; recuadro
// «Notas próximas» (de hoy en adelante). TA-REAL-2 (migración 33): goma y deshacer también en REAL (anulan, nunca borran);
// lo confirmado sigue bloqueado.
// TA3: festivos y guardias (guardias.tsx): vista año con una banda por semana de guardia (color de la farmacia e
// iniciales «G: XX · A: YY») y los festivos marcados con su farmacia de guardia; semana y mes con la cabecera
// «Guardia: Nombre · Apoyo sábado: Nombre» y los festivos con su nombre. Rellenar salta festivos; pintar sobre un
// festivo se permite, con aviso. TA3-REAL: también en REAL (migración 34).
// TA3-4 (decisión de Marc): las guardias se pintan aquí, no en la pestaña. Herramientas Guardia (clic en una persona:
// toda la semana de su farmacia; en un festivo, su guardia), Apoyo sábado, Guardia otra farmacia (cabecera del día:
// su semana o su festivo) y Festivo (cabecera del día: nombre y ámbito). La Goma, sobre sus marcas (G, A, GF, OTRA y el
// nombre del festivo) las anula; dar de baja un festivo pide confirmación. Sustituir algo de otra farmacia, también.
// Marcas en una capa superpuesta al pie de la celda (no tapan jornada ni ausencias): franja del color de la farmacia
// con «G», «A» el sábado del apoyo, «GF» en la guardia de festivo; semana OTRA en gris en la cabecera. Año: clic en la
// banda de la semana abre un selector de guardia y apoyo. Deshacer: una pila de la sesión con eventos y guardias; las
// guardias se deshacen con sus pasos inversos por clave (lunes o fecha), así que restaurar tras la goma crea filas nuevas.
// Las reglas y los avisos, en herramientas_guardia.ts (puro); el servidor y la BD las vuelven a aplicar.
import { useEffect, useRef, useState, type CSSProperties, type FormEvent, type PointerEvent as EventoPuntero, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  CATEGORIAS, TEXTO_CATEGORIA, TEXTO_JORNADA, esTitular, filtroFarmacia, type FarmaciaRrhh, type Trabajadora,
} from '../server/rrhh/contrato.ts';
import {
  AVISO_NOTA, AVISO_NOTA_VACIA, CODIGO_TIPO_EVENTO, COLOR_TIPO_EVENTO, FECHA_MAX, FECHA_MIN, FRANJAS, FRANJAS_DE_JORNADA, LARGO_NOTA,
  HORAS_EVENTO_MAX, TEXTO_ESTADO_EVENTO, TEXTO_FRANJA, TEXTO_TIPO_EVENTO, TIPOS_EVENTO, TIPOS_PINTABLES, TIPOS_SIN_HORAS, deAltaEl, describirCambio, diaSemana,
  esFecha, horasQueSuman, lunesDe, primeroDeMes, rangoFechas, sumarDias, sumarMeses, ultimoDeMes,
  type CalendarioDTO, type CambioCalendario, type Celda, type EventoCalendario, type Franja, type NotaProxima, type ResultadoCambioDTO, type TipoEvento,
  type TrazaEvento,
} from '../server/rrhh/eventos.ts';
import {
  AMBITOS_FESTIVO, AMBITO_POR_DEFECTO, LARGO_NOMBRE_FESTIVO, NOMBRE_FESTIVO_POR_DEFECTO, TEXTO_AMBITO, TEXTO_FARMACIA_GUARDIA, textoGuardiaFestiva,
  type AmbitoFestivoTa3, type FarmaciaGuardia, type FestivoVista, type GuardiasRespuestaDTO, type SemanaGuardiaVista,
} from '../server/rrhh/guardias.ts';
import {
  candidatasFestiva, candidatasSemana, contextoGuardias, esAviso, marcasGuardia, peticionGuardia, planApoyo, planFestivo, planGomaApoyo, planGomaFestivo,
  planGomaGuardiaFestivo, planGomaSemana, planGuardia, planGuardiaFestiva, planOtra, planSemanaElegida,
  type ContextoGuardias, type MarcaGuardia, type OpGuardia, type PlanGuardia, type ResultadoPlan,
} from '../server/rrhh/herramientas_guardia.ts';
import { planRellenoGuardias } from '../server/rrhh/relleno_guardias.ts';
import { ErrorApi, enviar, useApiRecargable } from './api.ts';
import { PreviaRelleno, useDatosRelleno } from './relleno_guardias.tsx';
import { fechaHora } from './formato.ts';
import {
  BandaGuardia, CabeceraGuardias, estiloGuardia, estiloGuardiaFestiva, guardarAlmacenColores, leerAlmacenColores, textoSobre, useColoresGuardia,
  useGuardias, varsColoresGuardia, type ColoresGuardia, type TipoColorGuardia,
} from './guardias.tsx';
import { EtiquetaFarmacia, Modulo, SelectorFarmacia } from './trabajadores.tsx';

// ---------------------------------------------------------------------------
// Fechas y textos
// ---------------------------------------------------------------------------

const fmt = (o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('es-ES', { timeZone: 'UTC', ...o });
const F_DIA_SEM = fmt({ weekday: 'short' });
const F_DIA_MES = fmt({ day: 'numeric', month: 'short' });
const F_LARGA = fmt({ weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
const F_CORTA = fmt({ weekday: 'short', day: 'numeric', month: 'short' });
const F_MES = fmt({ month: 'long', year: 'numeric' });
const F_MES_SOLO = fmt({ month: 'long' });
const dia = (f: string) => new Date(f + 'T00:00:00Z');
const NUM = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 });
const horasTxt = (h: number) => `${NUM.format(h)} h`;
const mayuscula = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const INICIALES = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];

/** Hoy en el reloj del navegador (fecha local, no UTC). */
function hoy(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
const acotar = (f: string) => (f < FECHA_MIN ? FECHA_MIN : f > FECHA_MAX ? FECHA_MAX : f);

type Vista = 'semana' | 'mes' | 'anio' | 'persona';
const VISTAS: readonly { v: Vista; texto: string }[] = [
  { v: 'semana', texto: 'Semana' }, { v: 'mes', texto: 'Mes' }, { v: 'anio', texto: 'Año' }, { v: 'persona', texto: 'Por persona' },
];

function periodo(vista: Vista, f: string): { desde: string; hasta: string } {
  if (vista === 'semana') { const l = lunesDe(f); return { desde: l, hasta: sumarDias(l, 6) }; }
  if (vista === 'mes') return { desde: primeroDeMes(f), hasta: ultimoDeMes(f) };
  return { desde: `${f.slice(0, 4)}-01-01`, hasta: `${f.slice(0, 4)}-12-31` };
}
function mover(vista: Vista, f: string, n: number): string {
  if (vista === 'semana') return sumarDias(lunesDe(f), 7 * n);
  if (vista === 'mes') return sumarMeses(primeroDeMes(f), n);
  return `${Number(f.slice(0, 4)) + n}-01-01`;
}
function textoPeriodo(vista: Vista, desde: string, hasta: string): string {
  if (vista === 'mes') return mayuscula(F_MES.format(dia(desde)));
  if (vista !== 'semana') return desde.slice(0, 4);
  const [d1, d2] = [Number(desde.slice(8)), Number(hasta.slice(8))];
  if (desde.slice(0, 7) === hasta.slice(0, 7)) return `${d1}–${d2} ${F_DIA_MES.format(dia(hasta)).replace(/^\d+\s/, '')} ${hasta.slice(0, 4)}`;
  if (desde.slice(0, 4) === hasta.slice(0, 4)) return `${F_DIA_MES.format(dia(desde))} – ${F_DIA_MES.format(dia(hasta))} ${hasta.slice(0, 4)}`;
  return `${F_DIA_MES.format(dia(desde))} ${desde.slice(0, 4)} – ${F_DIA_MES.format(dia(hasta))} ${hasta.slice(0, 4)}`;
}

/** Clave de una celda: con franja (semana) o del día completo (mes, por persona). */
const clave = (c: Celda) => `${c.trabajadora_id}|${c.fecha}${c.franja ? `|${c.franja}` : ''}`;
const claveEv = (tid: string, fecha: string, franja: Franja) => `${tid}|${fecha}|${franja}`;
const deClave = (k: string): Celda => {
  const [trabajadora_id, fecha, franja] = k.split('|');
  return { trabajadora_id, fecha, ...(franja ? { franja: franja as Franja } : {}) };
};
/** Eventos de una celda: su franja, o las dos franjas del día. */
const eventosDe = (m: Map<string, EventoCalendario>, c: Celda) => (c.franja ? [c.franja] : FRANJAS)
  .map((f) => m.get(claveEv(c.trabajadora_id, c.fecha, f))).filter((e): e is EventoCalendario => !!e);
const textoEvento = (e: EventoCalendario | null) => (e === null ? '—'
  : `${TEXTO_TIPO_EVENTO[e.tipo]} ${horasTxt(e.horas_efectivas)}${e.estado === 'CONFIRMADO' ? ' (confirmado)' : ''}${e.nota ? ` · nota: «${e.nota}»` : ''}`);
const descripcionEvento = (e: EventoCalendario, conFranja = true) =>
  `${conFranja ? `${TEXTO_FRANJA[e.franja]}: ` : ''}${TEXTO_TIPO_EVENTO[e.tipo]}, ${horasTxt(e.horas_efectivas)}, ${TEXTO_ESTADO_EVENTO[e.estado]}${e.nota ? `. Nota: ${e.nota}` : ''}`;

// ---------------------------------------------------------------------------
// Colores (configurables en la leyenda; solo en este navegador)
// ---------------------------------------------------------------------------

type Colores = Record<TipoEvento, string>;
const HEX = /^#[0-9a-f]{6}$/i;

function leerColores(): Colores {
  const c: Colores = { ...COLOR_TIPO_EVENTO };
  const g = leerAlmacenColores();
  for (const t of TIPOS_EVENTO) if (typeof g[t] === 'string' && HEX.test(g[t] as string)) c[t] = g[t] as string;
  return c;
}
/** TA4: se escribe mezclando en el objeto guardado (que también lleva los colores de guardia). */
function useColores(): [Colores, (t: TipoEvento | null, color?: string) => void] {
  const [c, setC] = useState<Colores>(leerColores);
  const cambiar = (t: TipoEvento | null, color?: string) => setC((p) => {
    const n = t === null ? { ...COLOR_TIPO_EVENTO } : { ...p, [t]: color ?? p[t] };
    guardarAlmacenColores(t === null ? Object.fromEntries(TIPOS_EVENTO.map((x) => [x, null])) : { [t]: n[t] });
    return n;
  });
  return [c, cambiar];
}
const estiloColor = (hex: string) => ({ '--c': hex, '--t': textoSobre(hex) }) as CSSProperties;

// ---------------------------------------------------------------------------
// Página
// ---------------------------------------------------------------------------

export function PaginaCalendario() {
  return (
    <Modulo subtitulo="Calendario de PIO y RITA: quién trabaja, cuándo y sus ausencias" seccion="calendario">
      <Calendario />
    </Modulo>
  );
}

/** TA3-4: herramientas de guardia (guardia, apoyo, otra, festivo); la goma también anula sus marcas. */
type HerramientaGuardia = 'guardia' | 'apoyo' | 'otra' | 'festivo' | 'festiva';
type Herramienta = { k: 'seleccion' } | { k: 'goma' } | { k: 'tipo'; tipo: TipoEvento } | { k: HerramientaGuardia };
type Aviso = { ok: boolean; texto: string } | null;
const HERRAMIENTAS_GUARDIA: readonly { k: HerramientaGuardia; cod: string; texto: string; ayuda: string }[] = [
  { k: 'guardia', cod: 'G', texto: 'Guardia', ayuda: 'Clic en una persona: guardia de su farmacia toda la semana (en un festivo, la guardia del festivo)' },
  { k: 'apoyo', cod: 'A', texto: 'Apoyo sábado', ayuda: 'Clic en una persona en el sábado de una semana con guardia de su farmacia' },
  { k: 'otra', cod: 'OTRA', texto: 'Guardia otra farmacia', ayuda: 'Clic en la cabecera de un día: su semana (o su festivo) de farmacia ajena' },
  { k: 'festivo', cod: 'F', texto: 'Festivo', ayuda: 'Clic en la cabecera de un día: nuevo festivo común con nombre y ámbito' },
  // TA4: guardia festiva de un día (panel: farmacia, persona y nombre del festivo).
  { k: 'festiva', cod: 'GF', texto: 'Guardia festiva', ayuda: 'Clic en un día (cabecera, persona o día del año): farmacia, persona y nombre del festivo de esa guardia' },
];
const esHerramientaGuardia = (h: Herramienta): h is { k: HerramientaGuardia } => HERRAMIENTAS_GUARDIA.some((x) => x.k === h.k);
/** Pila de deshacer de la sesión: cambios de eventos (los deshace el servidor) y de guardias (pasos inversos). */
type PasoPila = { k: 'eventos' } | { k: 'guardia'; texto: string; inversa: OpGuardia[] }
  /** TA4-2: «Rellenar año completo» con guardias por rotación: un solo paso (jornada del servidor + guardias). */
  | { k: 'relleno'; texto: string; inversa: OpGuardia[]; cambio: string | null };
const CLAVE_PILA = 'cf.rrhh.calendario.pila.v1';
/** Pila guardada en esta pestaña; cualquier cosa rara se descarta (falla cerrado: pila vacía). */
function leerPila(): PasoPila[] {
  try {
    const x = JSON.parse(sessionStorage.getItem(CLAVE_PILA) ?? '[]') as unknown;
    if (!Array.isArray(x)) return [];
    return x.filter((p): p is PasoPila => !!p && typeof p === 'object'
      && ((p as PasoPila).k === 'eventos' || ((p as PasoPila).k === 'guardia' && typeof (p as { texto?: unknown }).texto === 'string'
        && Array.isArray((p as { inversa?: unknown }).inversa))
        || ((p as PasoPila).k === 'relleno' && typeof (p as { texto?: unknown }).texto === 'string' && Array.isArray((p as { inversa?: unknown }).inversa)
          && ((p as { cambio?: unknown }).cambio === null || typeof (p as { cambio?: unknown }).cambio === 'string')))).slice(-100);
  } catch { return []; }
}
/** Diálogos de las herramientas de guardia. */
type Dialogo = null
  | { k: 'festivo'; fecha: string }
  | { k: 'confirmar'; plan: PlanGuardia }
  | { k: 'selector'; lunes: string; papel: 'guardia' | 'apoyo' }
  /** TA4: panel de la guardia festiva de un día (persona: la de la fila pulsada, si la hay). */
  | { k: 'festiva'; fecha: string; persona: string | null };
/** Goma sobre una marca de guardia. */
type MarcaGoma = 'semana' | 'apoyo' | 'guardia_festivo' | 'festivo';

const ERRORES: Readonly<Record<string, string>> = {
  TRABAJADORA_NO_VALIDA: 'Alguna persona ya no está activa: no se ha cambiado nada.',
  FRANJA_NO_VALIDA: 'Esa persona no trabaja en esa franja: no se ha cambiado nada.',
  EVENTO_NO_ENCONTRADO: 'Esa franja ya no tiene evento: no se ha cambiado nada.',
  EVENTO_CONFIRMADO: 'Esa franja está confirmada: quita antes la confirmación para cambiar sus horas o su nota.',
  NADA_QUE_DESHACER: 'No queda ningún cambio por deshacer.',
  NO_ES_EL_ULTIMO: 'Hay un cambio más reciente: recarga y vuelve a deshacer.',
  ESTADO_CAMBIADO: 'Los días de ese cambio ya no están como los dejó: no se ha deshecho nada.',
  DATOS_NO_VALIDOS: 'Datos no válidos: no se ha cambiado nada.',
  EVENTO_FUERA_DEL_ALTA: 'Ese día está fuera del alta o la baja de la persona: no se ha cambiado nada.',
};
const enviarOp = (op: OpGuardia) => { const p = peticionGuardia(op); return enviar(p.ruta, p.metodo, p.cuerpo); };
function textoError(e: unknown): string {
  if (!(e instanceof ErrorApi)) return 'No se ha podido guardar.';
  if (e.codigo === 'DATOS_NO_VALIDOS' && e.errores.nota) return `${e.errores.nota}: no se ha cambiado nada.`;
  if (ERRORES[e.codigo]) return ERRORES[e.codigo];
  // TA-REAL: errores de la base de datos con su mensaje llano (la transacción ya está deshecha).
  return e.mensaje ?? `No se ha podido guardar (${e.codigo}).`;
}
/** TA3: aviso (no error) al pintar sobre festivos: «Ojo: 25 dic es festivo (Navidad).» */
function textoFestivos(fechas: string[] | undefined, festivos: ReadonlyMap<string, FestivoVista>): string {
  if (!fechas || fechas.length === 0) return '';
  const lista = fechas.map((f) => `${F_DIA_MES.format(dia(f))}${festivos.has(f) ? ` (${festivos.get(f)?.nombre})` : ''}`).join(', ');
  return ` Ojo: ${fechas.length === 1 ? `${lista} es festivo` : `${lista} son festivos`}.`;
}
function textoResultado(r: ResultadoCambioDTO, festivos: ReadonlyMap<string, FestivoVista> = new Map()): Aviso {
  const o = r.omitidas_confirmadas;
  const v = r.omitidas_vacias;
  const omitidas = (o > 0 ? ` ${o} ${o === 1 ? 'franja confirmada no se ha tocado' : 'franjas confirmadas no se han tocado'} (quita antes la confirmación).` : '')
    + (v > 0 ? ` ${v} ${v === 1 ? 'franja vacía no se ha anotado' : 'franjas vacías no se han anotado'}: ${AVISO_NOTA_VACIA.charAt(0).toLowerCase()}${AVISO_NOTA_VACIA.slice(1)}.` : '');
  if (r.cambio === null) {
    if (v > 0 && o === 0) return { ok: false, texto: `${AVISO_NOTA_VACIA}.` };
    return { ok: o === 0 && v === 0, texto: `Sin cambios: esos días ya estaban así.${omitidas}` };
  }
  return { ok: true, texto: `${describirCambio(r.cambio)}.${omitidas}${textoFestivos(r.festivos_pintados, festivos)}` };
}

function Calendario() {
  const [params, setParams] = useSearchParams();
  const farmacia = filtroFarmacia(params.get('farmacia')) ?? 'AMBAS';
  const vista: Vista = VISTAS.find((x) => x.v === params.get('vista'))?.v ?? 'semana';
  const pf = params.get('fecha');
  const fecha = acotar(esFecha(pf) ? pf : hoy());
  const persona = params.get('persona') ?? '';
  const categoria = CATEGORIAS.find((c) => c === params.get('categoria')) ?? '';
  const tipoFiltro = TIPOS_EVENTO.find((t) => t === params.get('tipo')) ?? '';
  const { desde, hasta } = periodo(vista, fecha);
  const dq = desde < FECHA_MIN ? FECHA_MIN : desde;
  const hq = hasta > FECHA_MAX ? FECHA_MAX : hasta;

  const cal = useApiRecargable<CalendarioDTO>(`/api/rrhh/eventos?farmacia=${farmacia}&desde=${dq}&hasta=${hq}`);
  const hist = useApiRecargable<CambioCalendario[]>(`/api/rrhh/eventos/historial?farmacia=${farmacia}`);
  // TA-REAL «Notas próximas»: desde hoy (reloj del navegador); al pasar el día salen del recuadro.
  const notas = useApiRecargable<NotaProxima[]>(`/api/rrhh/eventos/notas?farmacia=${farmacia}&desde=${hoy()}`);
  // TA3: guardias y festivos del periodo (sin ellos, en REAL o si falla la lectura, el calendario sigue igual).
  const lecturaGuardias = useGuardias(dq, hq);
  const guardias = lecturaGuardias.datos;
  const festivos = new Map((guardias?.disponible ? guardias.festivos : []).map((f) => [f.fecha, f]));
  const [herr, setHerr] = useState<Herramienta>({ k: 'seleccion' });
  const [dialogo, setDialogo] = useState<Dialogo>(null);
  // Pila de deshacer de la sesión (estado para pintar el botón; ref para leerla dentro de la cola de escrituras).
  // Se guarda en sessionStorage (esta pestaña): sobrevive a recargar; si no hay almacenamiento, solo en memoria.
  const [pila, setPila] = useState<PasoPila[]>(leerPila);
  const pilaRef = useRef(pila);
  pilaRef.current = pila;
  useEffect(() => { try { sessionStorage.setItem(CLAVE_PILA, JSON.stringify(pila)); } catch { /* sin almacenamiento */ } }, [pila]);
  const apilar = (p: PasoPila) => setPila((x) => [...x, p].slice(-100));
  const [sel, setSel] = useState<Set<string>>(() => new Set());
  const [aviso, setAviso] = useState<Aviso>(null);
  const [confirmarAnio, setConfirmarAnio] = useState(false);
  // TA4-2: qué rellena «Rellenar año completo» en la vista Año (jornada habitual y guardias por rotación).
  const [incluirJornada, setIncluirJornada] = useState(true);
  const [incluirGuardias, setIncluirGuardias] = useState(true);
  const [colores, cambiarColor] = useColores();
  // TA4: colores de guardia (semanal y festiva por farmacia), en variables CSS del calendario.
  const [coloresGuardia, cambiarColorGuardia] = useColoresGuardia();
  const cola = useRef<Promise<void>>(Promise.resolve());
  const datos = cal.carga.estado === 'ok' ? cal.carga.datos : null;

  useEffect(() => { setSel(new Set()); setConfirmarAnio(false); setDialogo(null); }, [farmacia, vista, desde, persona]);
  // En la vista año solo valen Seleccionar, las herramientas de guardia y la goma.
  useEffect(() => { if (vista === 'anio' && herr.k === 'tipo') setHerr({ k: 'seleccion' }); }, [vista, herr.k]);

  const cambiar = (x: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(x)) { if (v === null || v === '') p.delete(k); else p.set(k, v); }
    setParams(p, { replace: true });
  };

  /** Las escrituras van en cola: ningún trazo se pierde ni se cruza con otro. */
  const ejecutar = (tarea: () => Promise<void>) => { cola.current = cola.current.then(tarea).catch(() => undefined); };
  const recargar = () => { cal.recargar(); hist.recargar(); notas.recargar(); };
  const escribir = (ruta: string, cuerpo: object) => ejecutar(async () => {
    try {
      const r = await enviar<ResultadoCambioDTO>(ruta, 'POST', cuerpo);
      setAviso(textoResultado(r, festivos));
      if (ruta === '/api/rrhh/eventos' && r.cambio !== null) apilar({ k: 'eventos' });
    } catch (e) { setAviso({ ok: false, texto: textoError(e) }); }
    recargar();
  });
  const cambioEventos = (cuerpo: object) => escribir('/api/rrhh/eventos', cuerpo);
  const ultimo = datos?.ultimo_cambio ?? null;

  // --- TA3-4: herramientas de guardia ---------------------------------------------------------------------------------
  const ctx: ContextoGuardias = contextoGuardias(guardias, datos?.trabajadoras ?? []);
  /** Guarda un plan (ya confirmado) y lo apila para deshacer; los errores de regla o de la BD, con su mensaje llano. */
  const guardarPlan = (p: PlanGuardia) => ejecutar(async () => {
    // TA4: pasos previos (crear o renombrar el festivo) y después la operación; si algo falla tras los previos, se
    // vuelve a como estaba con los pasos inversos (nada a medias).
    let hechas = 0;
    try {
      for (const op of [...(p.previas ?? []), p.op]) { await enviarOp(op); hechas += 1; }
      apilar({ k: 'guardia', texto: p.texto, inversa: p.inversa });
      setAviso({ ok: true, texto: `${p.texto}.` });
    } catch (e) {
      if (hechas > 0) { for (const op of p.inversa) { try { await enviarOp(op); } catch { /* sigue: se informa del error original */ } } }
      setAviso({ ok: false, texto: textoError(e) });
    }
    lecturaGuardias.recargar();
  });
  const ejecutarPlan = (r: ResultadoPlan) => {
    setDialogo(null);
    if (esAviso(r)) { setAviso({ ok: false, texto: r.aviso }); return; }
    if (r.confirmar) { setDialogo({ k: 'confirmar', plan: r }); return; }
    guardarPlan(r);
  };
  const conGuardias = guardias !== null;
  /** Clic en una persona con una herramienta de guardia. */
  const guardiaEnCelda = (h: HerramientaGuardia, c: Celda) => {
    if (h === 'guardia') ejecutarPlan(planGuardia(ctx, c.trabajadora_id, c.fecha));
    else if (h === 'apoyo') ejecutarPlan(planApoyo(ctx, c.trabajadora_id, c.fecha));
    else if (h === 'festiva') { setAviso(null); setDialogo({ k: 'festiva', fecha: c.fecha, persona: c.trabajadora_id }); }
    else guardiaEnCabecera(h, c.fecha);
  };
  /** Clic en la cabecera de un día (o en un día de la vista año) con una herramienta de guardia. */
  const guardiaEnCabecera = (h: HerramientaGuardia, fecha: string) => {
    if (h === 'otra') ejecutarPlan(planOtra(ctx, fecha));
    else if (h === 'festiva') { setAviso(null); setDialogo({ k: 'festiva', fecha, persona: null }); }
    else if (h === 'festivo') {
      if (festivos.has(fecha)) ejecutarPlan(planFestivo(ctx, fecha, '')); // aviso: ya es festivo
      else { setAviso(null); setDialogo({ k: 'festivo', fecha }); }
    }
    else setAviso({ ok: false, texto: `Con ${h === 'guardia' ? 'Guardia' : 'Apoyo sábado'}, haz clic en la fila de la persona, en el día que toca.` });
  };
  /** Goma sobre una marca (G, A, GF, OTRA o el festivo). */
  const gomaMarca = (m: MarcaGoma, fecha: string) => {
    if (m === 'semana') ejecutarPlan(planGomaSemana(ctx, lunesDe(fecha)));
    else if (m === 'apoyo') ejecutarPlan(planGomaApoyo(ctx, lunesDe(fecha)));
    else if (m === 'guardia_festivo') ejecutarPlan(planGomaGuardiaFestivo(ctx, fecha));
    else ejecutarPlan(planGomaFestivo(ctx, fecha));
  };
  const marcas = marcasGuardia(guardias);

  const cima = pila.length > 0 ? pila[pila.length - 1] : null;
  const deshacible = cima?.k === 'guardia' || cima?.k === 'relleno' || ultimo !== null;
  const textoDeshacer = cima?.k === 'guardia' || cima?.k === 'relleno' ? cima.texto : ultimo ? describirCambio(ultimo) : null;
  const deshacer = () => {
    const top = pilaRef.current.length > 0 ? pilaRef.current[pilaRef.current.length - 1] : null;
    if (top?.k === 'guardia') {
      setPila((x) => x.slice(0, -1));
      ejecutar(async () => {
        try {
          for (const op of top.inversa) await enviarOp(op);
          setAviso({ ok: true, texto: `Deshecho «${top.texto}».` });
        } catch (e) { setAviso({ ok: false, texto: `No se ha podido deshacer «${top.texto}»: ${textoError(e)}` }); }
        lecturaGuardias.recargar();
      });
      return;
    }
    if (top?.k === 'relleno') {
      // TA4-2: primero la jornada (cambio del servidor), después las guardias (anular lo creado).
      setPila((x) => x.slice(0, -1));
      ejecutar(async () => {
        try {
          if (top.cambio !== null) await enviar('/api/rrhh/eventos/deshacer', 'POST', { cambio_id: top.cambio });
          for (const op of top.inversa) await enviarOp(op);
          setAviso({ ok: true, texto: `Deshecho «${top.texto}».` });
        } catch (e) { setAviso({ ok: false, texto: `No se ha podido deshacer «${top.texto}»: ${textoError(e)}` }); }
        recargar();
        lecturaGuardias.recargar();
      });
      return;
    }
    if (top?.k === 'eventos') setPila((x) => x.slice(0, -1));
    if (!ultimo) return;
    escribir('/api/rrhh/eventos/deshacer', { cambio_id: ultimo.id });
  };

  // Ctrl+Z / Cmd+Z deshace el último cambio (fuera de los campos de texto).
  const deshacerRef = useRef(deshacer);
  deshacerRef.current = deshacer;
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 'z' || e.shiftKey) return;
      if ((e.target as HTMLElement | null)?.closest('input, select, textarea')) return;
      e.preventDefault();
      deshacerRef.current();
    };
    window.addEventListener('keydown', tecla);
    return () => window.removeEventListener('keydown', tecla);
  }, []);

  const aplicar = (celdas: Celda[]) => {
    if (celdas.length === 0) return;
    // TA3-4: con una herramienta de guardia cuenta la celda del clic (un arrastre, la primera).
    if (esHerramientaGuardia(herr)) { guardiaEnCelda(herr.k, celdas[0]); return; }
    if (herr.k === 'seleccion') {
      setSel((p) => {
        const n = new Set(p);
        if (celdas.length === 1 && n.has(clave(celdas[0]))) n.delete(clave(celdas[0]));
        else for (const c of celdas) n.add(clave(c));
        return n;
      });
      return;
    }
    cambioEventos(herr.k === 'goma' ? { accion: 'BORRAR', celdas } : { accion: 'PINTAR', tipo: herr.tipo, celdas });
  };

  const todas = datos?.trabajadoras ?? [];
  const visibles = todas.filter((t) => (!persona || t.id === persona) && (!categoria || t.categoria === categoria));
  const eventos = new Map((datos?.eventos ?? []).map((e) => [claveEv(e.trabajadora_id, e.fecha, e.franja), e]));
  const hoyF = hoy();
  const elegida = vista === 'persona' ? (todas.find((t) => t.id === persona) ?? visibles[0] ?? null) : null;
  const rango = vista === 'semana' || vista === 'mes';
  const nombrePeriodo = vista === 'semana' ? 'semana' : 'mes';
  const ids = visibles.map((t) => t.id);
  // TA2-2: año completo (vista año: personas visibles; por persona: la elegida).
  const anioSel = desde.slice(0, 4);
  const idsAnio = vista === 'persona' ? (elegida ? [elegida.id] : []) : ids;
  const anual = vista === 'anio' || vista === 'persona';
  const anioVacio = anual && datos !== null && idsAnio.length > 0 && !(datos.eventos.some((e) => idsAnio.includes(e.trabajadora_id)));
  // TA4-2: en la vista Año, el mismo botón también propone las guardias del año por rotación (vista previa y Confirmar).
  const conRelleno = vista === 'anio' && conGuardias && guardias !== null;
  const datosRelleno = useDatosRelleno(confirmarAnio && conRelleno, Number(anioSel));
  const planRelleno = conRelleno && guardias && datosRelleno?.estado === 'ok'
    ? planRellenoGuardias({ anio: Number(anioSel), previo: datosRelleno.datos.previo, actual: guardias, fichas: datosRelleno.datos.fichas }) : null;
  const jornadaSi = !conRelleno || incluirJornada;
  const guardiasSi = conRelleno && incluirGuardias && planRelleno !== null && planRelleno.pasos.length > 0;
  const rellenarAnio = () => {
    setConfirmarAnio(false);
    const cuerpo = { accion: 'RELLENAR', trabajadora_ids: idsAnio, desde: dq, hasta: hq };
    if (!guardiasSi || !planRelleno) { if (jornadaSi) cambioEventos(cuerpo); return; }
    const plan = planRelleno;
    ejecutar(async () => {
      // Guardias primero, en orden; si una falla, se anula lo ya creado (nada a medias) y no se rellena la jornada.
      const hechas: OpGuardia[] = [];
      try {
        for (const p of plan.pasos) { await enviarOp(p.op); hechas.unshift(p.inversa); }
      } catch (e) {
        for (const op of hechas) { try { await enviarOp(op); } catch { /* sigue: se informa del error original */ } }
        setAviso({ ok: false, texto: `No se ha rellenado nada: ${textoError(e)}` });
        lecturaGuardias.recargar();
        return;
      }
      let cambio: string | null = null;
      let jornada: Aviso = null;
      if (jornadaSi && idsAnio.length > 0) {
        try {
          const r = await enviar<ResultadoCambioDTO>('/api/rrhh/eventos', 'POST', cuerpo);
          cambio = r.cambio?.id ?? null;
          jornada = textoResultado(r, festivos);
        } catch (e) { jornada = { ok: false, texto: `La jornada habitual no se ha rellenado: ${textoError(e)}` }; }
      }
      apilar({ k: 'relleno', texto: plan.texto, inversa: hechas, cambio });
      setAviso({ ok: jornada?.ok ?? true, texto: `${plan.texto}.${jornada ? ` ${jornada.texto}` : ''}` });
      recargar();
      lecturaGuardias.recargar();
    });
  };

  return (
    <div className="cal" data-calendario data-vista={vista} style={varsColoresGuardia(coloresGuardia)}>
      <div className="cal-barra">
        <SelectorFarmacia valor={farmacia} onChange={(v) => cambiar({ farmacia: v === 'AMBAS' ? null : v, persona: null })} />
        <div className="cal-vistas" role="radiogroup" aria-label="Vista">
          {VISTAS.map((x) => (
            <button key={x.v} type="button" role="radio" aria-checked={vista === x.v} className={vista === x.v ? 'activa' : undefined}
              data-vista-boton={x.v} onClick={() => cambiar({ vista: x.v === 'semana' ? null : x.v })}>{x.texto}</button>
          ))}
        </div>
        <div className="cal-navegar">
          <button type="button" className="boton-secundario" aria-label="Periodo anterior" disabled={desde <= FECHA_MIN}
            onClick={() => cambiar({ fecha: mover(vista, fecha, -1) })} data-navegar="anterior">‹ Anterior</button>
          <button type="button" className="boton-secundario" onClick={() => cambiar({ fecha: null })} data-navegar="hoy">Hoy</button>
          <button type="button" className="boton-secundario" aria-label="Periodo siguiente" disabled={hasta >= FECHA_MAX}
            onClick={() => cambiar({ fecha: acotar(mover(vista, fecha, 1)) })} data-navegar="siguiente">Siguiente ›</button>
          <h2 className="cal-periodo" data-periodo aria-live="polite">{textoPeriodo(vista, desde, hasta)}</h2>
        </div>
      </div>

      <div className="cal-filtros">
        <label className="rrhh-campo">Persona
          <select value={vista === 'persona' ? (elegida?.id ?? '') : persona} onChange={(e) => cambiar({ persona: e.target.value })} data-filtro="persona">
            {vista !== 'persona' && <option value="">Todas las personas</option>}
            {todas.map((t) => <option key={t.id} value={t.id}>{t.nombre}{farmacia === 'AMBAS' ? ` · ${t.farmacia}` : ''}</option>)}
          </select>
        </label>
        <label className="rrhh-campo">Categoría
          <select value={categoria} onChange={(e) => cambiar({ categoria: e.target.value })} data-filtro="categoria">
            <option value="">Todas las categorías</option>
            {CATEGORIAS.map((c) => <option key={c} value={c}>{TEXTO_CATEGORIA[c]}</option>)}
          </select>
        </label>
        <label className="rrhh-campo">Tipo de evento
          <select value={tipoFiltro} onChange={(e) => cambiar({ tipo: e.target.value })} data-filtro="tipo">
            <option value="">Todos los tipos</option>
            {TIPOS_EVENTO.map((t) => <option key={t} value={t}>{TEXTO_TIPO_EVENTO[t]}</option>)}
          </select>
        </label>
      </div>

      <Paleta herr={herr} onHerr={(h) => { setHerr(h); setDialogo(null); }} colores={colores} onColor={cambiarColor} semana={vista === 'semana'}
        anio={vista === 'anio'} conGuardias={conGuardias && vista !== 'persona'} coloresGuardia={coloresGuardia} onColorGuardia={cambiarColorGuardia} />
      {vista === 'persona' && esHerramientaGuardia(herr) && (
        <p className="tenue" data-aviso-vista-persona>Las herramientas de guardia se usan en las vistas Semana, Mes y Año.</p>
      )}

      <div className="cal-acciones">
        {rango && (
          <>
            <button type="button" className="boton-secundario" disabled={ids.length === 0} data-accion="rellenar"
              title={`Jornada de lunes a viernes por franja según la ficha, en la ${nombrePeriodo} visible; no pisa lo ya pintado`}
              onClick={() => cambioEventos({ accion: 'RELLENAR', trabajadora_ids: ids, desde: dq, hasta: hq })}>Rellenar jornada habitual</button>
            <button type="button" className="boton-secundario" disabled={ids.length === 0} data-accion="confirmar-periodo"
              onClick={() => cambioEventos({ accion: 'CONFIRMAR', trabajadora_ids: ids, desde: dq, hasta: hq })}>Confirmar {nombrePeriodo}</button>
          </>
        )}
        {anual && (
          <button type="button" className="boton-secundario" disabled={idsAnio.length === 0} data-accion="rellenar-anio"
            aria-expanded={confirmarAnio} onClick={() => setConfirmarAnio(true)}>Rellenar año completo</button>
        )}
        {/* TA4: vista de impresión del año (A4 vertical), con el filtro de farmacia y los colores elegidos. */}
        {vista === 'anio' && (
          <a className="boton-secundario" href={`/trabajadores/guardias/imprimir?anio=${anioSel}${farmacia === 'AMBAS' ? '' : `&farmacia=${farmacia}`}`}
            target="_blank" rel="noopener" data-accion="imprimir-anio">Imprimir / PDF</a>
        )}
        <button type="button" className="boton-secundario cal-deshacer" disabled={!deshacible} onClick={deshacer} data-accion="deshacer"
          title={textoDeshacer ? `Deshacer: ${textoDeshacer} (Ctrl+Z)` : 'No hay cambios que deshacer'}>
          Deshacer{textoDeshacer && <span className="cal-deshacer-que" data-deshacer-que>{textoDeshacer}</span>}
        </button>
      </div>

      <NotasProximas carga={notas.carga} farmacia={farmacia} onDia={(f, persona) => cambiar({ vista: null, fecha: f, persona })} />

      {anioVacio && !confirmarAnio && (
        <div className="tarjeta cal-oferta" role="status" data-anio-vacio>
          <p><strong>{anioSel} está vacío</strong>{vista === 'persona' && elegida ? ` para ${elegida.nombre}` : ' para estas personas'}. ¿Rellenar la jornada habitual de todo el año?</p>
          <button type="button" className="boton-primario" onClick={() => setConfirmarAnio(true)} data-ofrecer-anio>Rellenar {anioSel}…</button>
        </div>
      )}
      {confirmarAnio && (
        <div className="tarjeta cal-oferta cal-confirmar" role="alertdialog" aria-labelledby="t-conf-anio" data-confirmar-anio>
          <p id="t-conf-anio">
            Se creará la jornada habitual (lunes a viernes, por franja según la ficha) de {idsAnio.length === 1 ? '1 persona' : `${idsAnio.length} personas`} en
            todo {anioSel}, sin tocar lo ya pintado ni lo confirmado. Se puede deshacer de una vez.
          </p>
          {conRelleno && (
            <div className="rl-incluir" data-relleno-guardias>
              <label><input type="checkbox" checked={incluirJornada} onChange={(e) => setIncluirJornada(e.target.checked)} data-relleno-incluir="jornada" /> Jornada habitual</label>
              <label><input type="checkbox" checked={incluirGuardias} onChange={(e) => setIncluirGuardias(e.target.checked)} data-relleno-incluir="guardias" />
                {' '}Guardias por rotación (OTRA → PIO → RITA): semanas, festivos y guardias festivas que falten</label>
            </div>
          )}
          {conRelleno && incluirGuardias && (
            datosRelleno?.estado === 'error' ? <p className="rrhh-error" role="alert">No se han podido leer los datos para proponer las guardias ({datosRelleno.mensaje}).</p>
              : planRelleno ? <PreviaRelleno plan={planRelleno} /> : <p className="tenue">Calculando la propuesta de guardias…</p>
          )}
          <div className="rrhh-botones">
            <button type="button" className="boton-primario" onClick={rellenarAnio} data-confirmar-anio-si
              disabled={(!jornadaSi && !guardiasSi) || (conRelleno && incluirGuardias && planRelleno === null)}>{conRelleno ? 'Confirmar' : `Sí, rellenar ${anioSel}`}</button>
            <button type="button" className="boton-secundario" onClick={() => setConfirmarAnio(false)}>Cancelar</button>
          </div>
        </div>
      )}

      {aviso && <p className={aviso.ok ? 'rrhh-aviso-ok' : 'rrhh-error'} role={aviso.ok ? 'status' : 'alert'} data-aviso-calendario>{aviso.texto}</p>}
      {dialogo?.k === 'festivo' && (
        <DialogoFestivo fecha={dialogo.fecha} onCancelar={() => setDialogo(null)}
          onCrear={(nombre, ambito) => ejecutarPlan(planFestivo(ctx, dialogo.fecha, nombre, ambito))} />
      )}
      {dialogo?.k === 'confirmar' && (
        <div className="tarjeta cal-oferta cal-confirmar gu-dialogo" role="alertdialog" aria-labelledby="t-conf-guardia" data-confirmar-guardia={dialogo.plan.op.k}>
          <p id="t-conf-guardia">{dialogo.plan.confirmar}</p>
          <div className="rrhh-botones">
            <button type="button" className={dialogo.plan.op.k === 'anular_festivo' ? 'boton-peligro' : 'boton-primario'} data-confirmar-guardia-si
              onClick={() => { const p = dialogo.plan; setDialogo(null); guardarPlan(p); }}>
              {dialogo.plan.op.k === 'anular_festivo' ? 'Sí, dar de baja' : 'Sí, sustituir'}
            </button>
            <button type="button" className="boton-secundario" onClick={() => setDialogo(null)} data-confirmar-guardia-no>Cancelar</button>
          </div>
        </div>
      )}
      {dialogo?.k === 'festiva' && (
        <DialogoGuardiaFestiva key={`${dialogo.fecha}|${dialogo.persona ?? ''}`} fecha={dialogo.fecha} festivo={festivos.get(dialogo.fecha)} fichas={todas}
          persona={dialogo.persona} farmaciaFiltro={farmacia === 'AMBAS' ? null : farmacia} onCancelar={() => setDialogo(null)}
          onGuardar={(f, p, n) => ejecutarPlan(planGuardiaFestiva(ctx, dialogo.fecha, f, p, n))}
          onAnular={() => ejecutarPlan(planGomaGuardiaFestivo(ctx, dialogo.fecha))} />
      )}
      {dialogo?.k === 'selector' && (
        <SelectorSemana lunes={dialogo.lunes} papel={dialogo.papel} semana={ctx.semana(dialogo.lunes)} fichas={todas}
          farmacia={farmacia === 'AMBAS' ? null : farmacia} onCancelar={() => setDialogo(null)}
          onGuardar={(g, a) => ejecutarPlan(planSemanaElegida(ctx, dialogo.lunes, g, a))} />
      )}

      {cal.carga.estado === 'cargando' && <p className="tenue">Cargando calendario…</p>}
      {cal.carga.estado === 'error' && <p className="rrhh-error" role="alert">No se ha podido leer el calendario ({cal.carga.mensaje}).</p>}
      {datos && visibles.length === 0 && vista !== 'persona' && (
        <p className="tarjeta rrhh-vacio" data-calendario-vacio>Ninguna persona con estos filtros. Cambia la persona o la categoría.</p>
      )}

      {rango && <CabeceraGuardias datos={guardias} />}
      {datos && visibles.length > 0 && rango && (
        <RejillaPeriodo vista={vista} desde={desde} hasta={hasta} hoyF={hoyF} trabajadoras={visibles} agrupar={farmacia === 'AMBAS'}
          eventos={eventos} sel={sel} herr={herr} colores={colores} tipoFiltro={tipoFiltro} onAplicar={aplicar} festivos={festivos}
          capa={conGuardias ? { de: marcas.de, otra: marcas.otra, goma: herr.k === 'goma', onGoma: gomaMarca, festivo: (f) => festivos.get(f) } : null}
          onCabecera={esHerramientaGuardia(herr) ? (f) => guardiaEnCabecera(herr.k, f) : null} />
      )}
      {datos && vista === 'anio' && visibles.length > 0 && (
        <VistaAnio anio={anioSel} hoyF={hoyF} trabajadoras={visibles} eventos={eventos} colores={colores} tipoFiltro={tipoFiltro}
          onDia={(f) => cambiar({ vista: null, fecha: f })} guardias={guardias} herr={herr}
          onBanda={(lunes) => {
            if (herr.k === 'guardia' || herr.k === 'apoyo') { setAviso(null); setDialogo({ k: 'selector', lunes, papel: herr.k }); }
            else if (herr.k === 'otra') ejecutarPlan(planOtra(ctx, lunes));
            else if (herr.k === 'goma') gomaMarca('semana', lunes);
          }}
          onDiaHerramienta={(f) => {
            if (herr.k === 'goma') { if (festivos.has(f)) gomaMarca('festivo', f); return; }
            if (herr.k === 'guardia' || herr.k === 'apoyo') { setAviso(null); setDialogo({ k: 'selector', lunes: lunesDe(f), papel: herr.k }); return; }
            if (esHerramientaGuardia(herr)) guardiaEnCabecera(herr.k, f);
          }} />
      )}
      {datos && vista === 'persona' && (elegida
        ? <VistaPersona t={elegida} anio={anioSel} hoyF={hoyF} eventos={eventos} sel={sel} herr={herr} colores={colores}
            tipoFiltro={tipoFiltro} onAplicar={aplicar}
            capa={conGuardias ? { de: marcas.de, otra: new Set(), goma: herr.k === 'goma', onGoma: gomaMarca, festivo: (f) => festivos.get(f) } : null} />
        : <p className="tarjeta rrhh-vacio">No hay personas en esta farmacia.</p>)}

      {sel.size > 0 && vista !== 'anio' && (
        <BarraSeleccion sel={sel} eventos={eventos} colores={colores} fichas={new Map(todas.map((t) => [t.id, t]))}
          onLimpiar={() => setSel(new Set())} onCambio={cambioEventos} />
      )}

      <Historial carga={hist.carga} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Paleta (también leyenda) y colores
// ---------------------------------------------------------------------------

function Paleta({ herr, onHerr, colores, onColor, semana, anio, conGuardias, coloresGuardia, onColorGuardia }: {
  herr: Herramienta; onHerr: (h: Herramienta) => void; colores: Colores; onColor: (t: TipoEvento | null, c?: string) => void; semana: boolean;
  /** Vista año: sin tipos de evento (allí no se pinta por día). */
  anio: boolean;
  /** TA3-4: herramientas de guardia (con la lectura de guardias disponible). */
  conGuardias: boolean;
  /** TA4: colores de guardia semanal y festiva, por farmacia. */
  coloresGuardia: ColoresGuardia; onColorGuardia: (t: TipoColorGuardia | null, f?: FarmaciaGuardia, c?: string) => void;
}) {
  const [editar, setEditar] = useState(false);
  const activa = (h: Herramienta) => (h.k === herr.k && (h.k !== 'tipo' || (herr.k === 'tipo' && herr.tipo === h.tipo)));
  const accion = herr.k === 'seleccion' ? 'seleccionar' : herr.k === 'goma' ? 'borrar' : 'pintar';
  const ayudaGuardia = HERRAMIENTAS_GUARDIA.find((x) => x.k === herr.k)?.ayuda;
  return (
    <section className="cal-paleta-marco" aria-label="Paleta y leyenda">
      <div className="cal-paleta" role="toolbar" aria-label="Herramienta">
        <button type="button" className="cal-herr cal-herr-sel" aria-pressed={activa({ k: 'seleccion' })} data-herramienta="seleccion"
          onClick={() => onHerr({ k: 'seleccion' })}><span className="cal-muestra-sel" aria-hidden="true" />{anio ? 'Abrir semana' : 'Seleccionar'}</button>
        {!anio && TIPOS_PINTABLES.map((t) => (
          <button key={t} type="button" className="cal-herr" aria-pressed={activa({ k: 'tipo', tipo: t })} data-herramienta={t} style={estiloColor(colores[t])}
            onClick={() => onHerr({ k: 'tipo', tipo: t })}>
            <span className="cal-muestra" aria-hidden="true">{CODIGO_TIPO_EVENTO[t]}</span>{TEXTO_TIPO_EVENTO[t]}
          </button>
        ))}
        {conGuardias && (
          <span className="cal-paleta-grupo" role="group" aria-label="Guardias y festivos" data-paleta-guardias>
            {HERRAMIENTAS_GUARDIA.map((x) => (
              <button key={x.k} type="button" className={`cal-herr cal-herr-guardia h-${x.k}`} aria-pressed={activa({ k: x.k })} data-herramienta={x.k}
                title={x.ayuda} onClick={() => onHerr({ k: x.k })}>
                <span className="cal-muestra gu-muestra" aria-hidden="true">{x.cod}</span>{x.texto}
              </button>
            ))}
          </span>
        )}
        <button type="button" className="cal-herr cal-herr-goma" aria-pressed={activa({ k: 'goma' })} data-herramienta="goma"
          title={`Quitar ${anio ? '' : 'eventos (se anulan y quedan en el historial; lo confirmado no se toca)'}${conGuardias ? `${anio ? '' : ' y '}guardias, apoyos, OTRA y festivos: clic sobre su marca` : ''}`}
          onClick={() => onHerr({ k: 'goma' })}><span className="cal-muestra-goma" aria-hidden="true" />Goma</button>
      </div>
      {ayudaGuardia && <p className="cal-ayuda-guardia" data-ayuda-guardia={herr.k} role="status">{ayudaGuardia}{herr.k === 'guardia' || herr.k === 'apoyo' ? (anio ? ' (en el año: clic en la banda de la semana).' : '.') : '.'}</p>}
      {herr.k === 'goma' && conGuardias && <p className="cal-ayuda-guardia" data-ayuda-guardia="goma" role="status">Goma: sobre una celda quita sus eventos; sobre una marca G, A, GF, OTRA o el nombre del festivo, la anula{anio ? ' (en el año: clic en la banda o en el festivo)' : ''}.</p>}
      <p className="tenue cal-tipos-ta3" data-tipos-ta3>
        {TIPOS_EVENTO.filter((t) => !TIPOS_PINTABLES.includes(t)).map((t) => TEXTO_TIPO_EVENTO[t]).join(', ')}: no se pintan como evento; guardias, apoyos y festivos se pintan con sus herramientas
        (consulta del año en <Link to="/trabajadores/guardias">Guardias y festivos</Link>).
        {' '}{TIPOS_SIN_HORAS.map((t) => TEXTO_TIPO_EVENTO[t]).join(' y ')} no suman horas.
      </p>
      <div className="cal-leyenda">
        <span className="cal-leyenda-estado"><span className="cal-mini e-planificado" aria-hidden="true" /> claro: planificado</span>
        <span className="cal-leyenda-estado"><span className="cal-mini e-confirmado" aria-hidden="true">✓</span> sólido: confirmado</span>
        <span className="cal-leyenda-estado"><span className="cal-nota-marca" aria-hidden="true">✎</span> con nota</span>
        {conGuardias && !anio && (
          <span className="cal-leyenda-estado gu-leyenda" data-leyenda-guardias>
            <span className="gu-marca g" style={estiloGuardia('PIO')} aria-hidden="true">G</span> guardia PIO
            <span className="gu-marca g" style={estiloGuardia('RITA')} aria-hidden="true">G</span> guardia RITA
            <span className="gu-marca a" style={estiloGuardia('PIO')} aria-hidden="true">A</span> apoyo sábado
            <span className="gu-marca gf" style={estiloGuardiaFestiva('PIO')} aria-hidden="true">GF</span> guardia festiva PIO
            <span className="gu-marca gf" style={estiloGuardiaFestiva('RITA')} aria-hidden="true">GF</span> guardia festiva RITA
            <span className="gu-col-otra-muestra" aria-hidden="true">OTRA</span> farmacia ajena
          </span>
        )}
        {!anio && <span className="tenue" data-ayuda-franjas>
          {semana
            ? `Arriba mañana (M), abajo tarde (T): clic en una franja o arrastre sobre las dos para ${accion} el día.`
            : `Arriba mañana, abajo tarde: un clic ${accion === 'seleccionar' ? 'selecciona' : accion === 'borrar' ? 'borra' : 'pinta'} el día completo (sus franjas).`}
        </span>}
        <button type="button" className="cal-enlace" aria-expanded={editar} onClick={() => setEditar(!editar)} data-editar-colores>
          {editar ? 'Cerrar colores' : 'Cambiar colores'}
        </button>
      </div>
      {editar && (
        <div className="cal-colores" data-panel-colores>
          {TIPOS_EVENTO.map((t) => (
            <label key={t} className="cal-color">
              <input type="color" value={colores[t]} onChange={(e) => onColor(t, e.target.value)} data-color={t} />
              {TEXTO_TIPO_EVENTO[t]}
            </label>
          ))}
          {/* TA4: guardia semanal y guardia festiva de un día, una por farmacia; el texto de la barra pasa a blanco u oscuro. */}
          <fieldset className="cal-colores-guardia" data-colores-guardia>
            <legend>Guardias</legend>
            {(['semanal', 'festiva'] as const).map((t) => (
              <div key={t} className="cal-colores-fila" data-colores-guardia-tipo={t}>
                <span className="cal-colores-titulo">{t === 'semanal' ? 'Guardia semanal' : 'Guardia festiva (un día)'}</span>
                {(['PIO', 'RITA', 'OTRA'] as const).map((f) => (
                  <label key={f} className="cal-color">
                    <input type="color" value={coloresGuardia[t][f]} onChange={(e) => onColorGuardia(t, f, e.target.value)} data-color-guardia={`${t}|${f}`} />
                    <span className="gu-marca muestra" style={{ background: coloresGuardia[t][f], color: textoSobre(coloresGuardia[t][f]) }} data-muestra-guardia={`${t}|${f}`}>
                      {f === 'OTRA' ? 'OTRA' : f}
                    </span>
                  </label>
                ))}
              </div>
            ))}
          </fieldset>
          <button type="button" className="boton-secundario" onClick={() => { onColor(null); onColorGuardia(null); }} data-restablecer-colores>Restaurar colores por defecto</button>
          <p className="tenue">Los colores se guardan solo en este navegador (también en la vista de impresión).</p>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Rejilla pintable (semana, mes y por persona)
// ---------------------------------------------------------------------------

/** TA3: festivo = nombre del festivo de ese día (columna marcada con su nombre). */
interface Columna { clave: string; cabecera: ReactNode; titulo?: string; finde?: boolean; hoy?: boolean; festivo?: string }
/**
 * Fila de la rejilla. Semana: una subfila por franja (cabecera de persona con rowSpan 2 en la de mañana); celda null
 * = franja que la persona no trabaja. Mes y por persona: una fila por persona o mes; celda null = día inexistente.
 */
interface Fila {
  clave: string; grupo?: FarmaciaRrhh; cabecera?: ReactNode; span?: number; titulo?: string; franja?: Franja;
  celdas: (Celda | null)[]; nombre?: string;
  /** TA3-4: persona de la fila y si lleva la capa de marcas de guardia (en la semana, la subfila de tarde). */
  tid?: string; capa?: boolean;
}
type Punto = [number, number];

/** TA3-4: capa de marcas de guardia de la rejilla. */
interface CapaGuardias {
  de: (tid: string, fecha: string) => MarcaGuardia | undefined;
  /** Días de semanas de farmacia ajena (cabecera en gris). */
  otra: ReadonlySet<string>;
  /** Goma activa: las marcas son botones que anulan. */
  goma: boolean;
  onGoma: (m: MarcaGoma, fecha: string) => void;
  /** TA4: festivo de un día (nombre y su guardia festiva), para la marca diaria y su popup. */
  festivo: (fecha: string) => FestivoVista | undefined;
}
/** TA4: marca diaria de la guardia festiva: color de la farmacia (festiva) + iniciales; OTRA en gris; sin guardia, «GF». */
function MarcaFestiva({ fe, compacta = false }: { fe: FestivoVista; compacta?: boolean }) {
  const g = fe.guardia;
  const texto = g === null ? 'GF' : g.farmacia === 'OTRA' ? 'OTRA' : `${compacta ? '' : `${g.farmacia} `}${g.persona?.iniciales ?? ''}`.trim() || g.farmacia;
  return (
    <span className={`gu-festiva${g === null ? ' sin' : ''}`} style={g ? estiloGuardiaFestiva(g.farmacia) : undefined} title={textoGuardiaFestiva(fe)}
      data-marca-festiva={fe.fecha} data-festiva-farmacia={g?.farmacia ?? ''}>{texto}</span>
  );
}
const TEXTO_GOMA: Readonly<Record<MarcaGoma, string>> = {
  semana: 'Quitar la guardia de esa semana', apoyo: 'Quitar el apoyo de ese sábado', guardia_festivo: 'Quitar la guardia de ese festivo', festivo: 'Dar de baja el festivo',
};
/** Marca de guardia: texto; con la goma, botón que la anula. */
function Marca({ clase, f, festiva = false, texto, titulo, goma, onGoma, datos }: {
  clase: string; f: FarmaciaGuardia; festiva?: boolean; texto: string; titulo: string; goma: MarcaGoma | null; onGoma?: () => void; datos: Record<string, string>;
}) {
  const estilo = festiva ? estiloGuardiaFestiva(f) : estiloGuardia(f);
  return goma && onGoma
    ? <button type="button" className={`gu-marca ${clase} goma`} style={estilo} title={`${TEXTO_GOMA[goma]}: ${titulo}`} aria-label={`${TEXTO_GOMA[goma]}: ${titulo}`}
        onClick={onGoma} data-goma-marca={goma} {...datos}>{texto}</button>
    : <span className={`gu-marca ${clase}`} style={estilo} title={titulo} {...datos}>{texto}</span>;
}
/** Al pie de la celda: franja de la guardia (toda la semana) con «G» el primer día visible; «A» y «GF». */
function CapaCelda({ m, tid, fecha, primero, capa }: { m: MarcaGuardia; tid: string; fecha: string; primero: boolean; capa: CapaGuardias }) {
  const goma = capa.goma;
  const d = (tipo: string) => ({ [`data-marca-${tipo}`]: `${tid}|${fecha}` });
  return (
    <span className="gu-capa" data-capa-guardia={`${tid}|${fecha}`}>
      {m.guardia && <span className="gu-franja" style={estiloGuardia(m.guardia)} data-franja-guardia={m.guardia} aria-hidden="true" />}
      {m.guardia && primero && (
        <Marca clase="g" f={m.guardia} texto="G" titulo={`guardia ${m.guardia}`} goma={goma ? 'semana' : null} onGoma={() => capa.onGoma('semana', fecha)} datos={d('g')} />
      )}
      {m.apoyo && <Marca clase="a" f={m.apoyo} texto="A" titulo={`apoyo del sábado ${m.apoyo}`} goma={goma ? 'apoyo' : null} onGoma={() => capa.onGoma('apoyo', fecha)} datos={d('a')} />}
      {m.festivo && (
        <Marca clase="gf" f={m.festivo} festiva texto="GF" titulo={capa.festivo(fecha) ? textoGuardiaFestiva(capa.festivo(fecha) as FestivoVista) : `guardia festiva ${m.festivo}`}
          goma={goma ? 'guardia_festivo' : null} onGoma={() => capa.onGoma('guardia_festivo', fecha)} datos={d('gf')} />
      )}
    </span>
  );
}
/** Texto de las marcas para la etiqueta accesible de la celda. */
const textoMarcas = (m: MarcaGuardia | undefined) => (m ? [
  m.guardia ? `semana de guardia ${m.guardia}` : '', m.apoyo ? 'apoyo del sábado' : '', m.festivo ? `guardia de festivo ${m.festivo}` : '',
].filter(Boolean).join(', ') : '');

function enRect(filas: Fila[], a: Punto, b: Punto): Celda[] {
  const [r0, r1] = [Math.min(a[0], b[0]), Math.max(a[0], b[0])];
  const [c0, c1] = [Math.min(a[1], b[1]), Math.max(a[1], b[1])];
  const r: Celda[] = [];
  for (let i = r0; i <= r1; i++) for (let j = c0; j <= c1; j++) { const c = filas[i]?.celdas[j]; if (c) r.push(c); }
  return r;
}

function Evento({ ev, color, atenuado, compacto }: { ev: EventoCalendario; color: string; atenuado: boolean; compacto: boolean }) {
  return (
    <span className={`cal-ev e-${ev.estado.toLowerCase()}${atenuado ? ' atenuado' : ''}`} style={estiloColor(color)} data-ev-franja={ev.franja} data-ev-tipo={ev.tipo}>
      <span className="cal-ev-cod">{CODIGO_TIPO_EVENTO[ev.tipo]}</span>
      {!compacto && <span className="cal-ev-horas">{horasTxt(ev.horas_efectivas)}</span>}
      {!compacto && ev.estado === 'CONFIRMADO' && <span className="cal-ev-ok" aria-hidden="true">✓</span>}
      {ev.nota && <span className="cal-ev-nota" aria-hidden="true" data-con-nota>✎</span>}
    </span>
  );
}

function Rejilla({ variante, columnas, filas, nombres, eventos, sel, herr, colores, tipoFiltro, hoyF, onAplicar, pie, capa = null, onCabecera = null }: {
  variante: 'semana' | 'mes' | 'persona'; columnas: Columna[]; filas: Fila[]; nombres: Map<string, string>;
  eventos: Map<string, EventoCalendario>; sel: Set<string>; herr: Herramienta; colores: Colores; tipoFiltro: TipoEvento | '';
  hoyF: string; onAplicar: (c: Celda[]) => void; pie?: { titulo: string; valores: (number | null)[] };
  /** TA3-4: marcas de guardia (null: sin lectura de guardias). */
  capa?: CapaGuardias | null;
  /** TA3-4: clic en la cabecera de un día con una herramienta de guardia (en lugar de aplicar a la columna). */
  onCabecera?: ((fecha: string) => void) | null;
}) {
  const [trazo, setTrazo] = useState<{ a: Punto; b: Punto } | null>(null);
  const trazoRef = useRef(trazo);
  const aplicarRef = useRef(onAplicar);
  aplicarRef.current = onAplicar;
  const filasRef = useRef(filas);
  filasRef.current = filas;
  const toque = useRef<Punto | null>(null);
  const ultimoPuntero = useRef(0);
  const poner = (t: { a: Punto; b: Punto } | null) => { trazoRef.current = t; setTrazo(t); };

  // Ratón y lápiz: el trazo termina al soltar en cualquier sitio.
  useEffect(() => {
    const fin = () => {
      const t = trazoRef.current;
      if (!t) return;
      poner(null);
      aplicarRef.current(enRect(filasRef.current, t.a, t.b));
    };
    window.addEventListener('pointerup', fin);
    return () => window.removeEventListener('pointerup', fin);
  }, []);

  const abajo = (e: EventoPuntero, p: Punto) => {
    if (e.button !== 0) return;
    ultimoPuntero.current = Date.now();
    // Toque: pintar con un toque (arrastrar desplaza la rejilla).
    if (e.pointerType === 'touch') { toque.current = p; return; }
    e.preventDefault();
    poner({ a: p, b: p });
  };
  const encima = (p: Punto) => { const t = trazoRef.current; if (t && (t.b[0] !== p[0] || t.b[1] !== p[1])) poner({ a: t.a, b: p }); };
  const arriba = (e: EventoPuntero, p: Punto) => {
    if (e.pointerType !== 'touch') return;
    const t = toque.current;
    toque.current = null;
    if (t && t[0] === p[0] && t[1] === p[1]) { const c = filas[p[0]].celdas[p[1]]; if (c) onAplicar([c]); }
  };
  /** Teclado (Intro / Espacio): el clic sin puntero reciente aplica la herramienta a esa celda. */
  const clic = (p: Punto) => {
    if (Date.now() - ultimoPuntero.current < 800) return;
    const c = filas[p[0]].celdas[p[1]];
    if (c) onAplicar([c]);
  };
  const columna = (j: number) => {
    if (onCabecera) { onCabecera(columnas[j].clave); return; }
    onAplicar(filas.flatMap((f) => (f.celdas[j] ? [f.celdas[j] as Celda] : [])));
  };

  const enTrazo = trazo ? new Set(enRect(filas, trazo.a, trazo.b).map(clave)) : null;
  const colorHerr = herr.k === 'tipo' ? colores[herr.tipo] : herr.k === 'goma' ? '#c8372d' : '#1d3b47';
  const semana = variante === 'semana';
  const atenuado = (e: EventoCalendario) => tipoFiltro !== '' && e.tipo !== tipoFiltro;

  return (
    <div className={`tarjeta cal-marco v-${variante}`} data-rejilla={variante} style={{ '--herr': colorHerr } as CSSProperties}>
      <table className="cal-rejilla">
        <colgroup>
          <col className="cal-c-nombre" />
          {semana && <col className="cal-c-franja" />}
          {columnas.map((c) => <col key={c.clave} />)}
        </colgroup>
        <thead>
          <tr>
            <th scope="col" className="cal-esquina" colSpan={semana ? 2 : 1}>{variante === 'persona' ? 'Mes' : 'Persona'}</th>
            {columnas.map((c, j) => {
              const otra = capa?.otra.has(c.clave) ?? false;
              // OTRA: la marca va en el primer día visible de la semana (lunes o primera columna).
              const marcaOtra = otra && (diaSemana(c.clave) === 0 || j === 0);
              const textoFestivo = c.festivo ? (semana ? c.festivo : CODIGO_TIPO_EVENTO.FESTIVO) : '';
              const accionCabecera = onCabecera ? 'herramienta de guardia' : 'aplicar a todas las personas';
              return (
                <th key={c.clave} scope="col" className={`cal-col${c.finde ? ' finde' : ''}${c.hoy ? ' hoy' : ''}${c.festivo ? ' festivo' : ''}${otra ? ' gu-otra' : ''}`}
                  title={`${c.festivo ? `${c.titulo} · Festivo: ${c.festivo}` : c.titulo}${otra ? ' · Guardia: OTRA (farmacia ajena)' : ''}`} data-columna={c.clave}
                  {...(c.festivo ? { 'data-festivo-columna': c.festivo } : {})} {...(otra ? { 'data-otra-columna': '' } : {})}>
                  {variante === 'persona' ? c.cabecera : (
                    <>
                      <button type="button" className="cal-col-boton" onClick={() => columna(j)}
                        aria-label={`${c.titulo}${c.festivo ? ` (festivo: ${c.festivo})` : ''}${otra ? ' (guardia OTRA)' : ''}: ${accionCabecera}`}>
                        {c.cabecera}
                        {c.festivo && !capa?.goma && <span className="cal-col-festivo">{textoFestivo}</span>}
                      </button>
                      {c.festivo && capa?.goma && (
                        <button type="button" className="cal-col-festivo goma" onClick={() => capa.onGoma('festivo', c.clave)} data-goma-festivo={c.clave}
                          title={`${TEXTO_GOMA.festivo}: ${c.festivo}`} aria-label={`${TEXTO_GOMA.festivo}: ${c.festivo}`}>{textoFestivo}</button>
                      )}
                      {/* TA4: marca diaria de la guardia festiva (con la goma, la anula). */}
                      {c.festivo && capa?.festivo(c.clave)?.guardia && (capa.goma
                        ? <button type="button" className="gu-festiva-goma" onClick={() => capa.onGoma('guardia_festivo', c.clave)} data-goma-festiva={c.clave}
                            aria-label={`${TEXTO_GOMA.guardia_festivo}: ${textoGuardiaFestiva(capa.festivo(c.clave) as FestivoVista)}`}>
                            <MarcaFestiva fe={capa.festivo(c.clave) as FestivoVista} compacta={!semana} />
                          </button>
                        : <MarcaFestiva fe={capa.festivo(c.clave) as FestivoVista} compacta={!semana} />)}
                      {marcaOtra && (capa?.goma
                        ? <button type="button" className="gu-col-otra goma" onClick={() => capa.onGoma('semana', c.clave)} data-goma-otra={c.clave} data-marca-otra={c.clave}
                            title="Quitar la guardia OTRA de esa semana" aria-label="Quitar la guardia OTRA de esa semana">OTRA</button>
                        : <span className="gu-col-otra" data-marca-otra={c.clave}>OTRA</span>)}
                    </>
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {filas.map((f, i) => (f.grupo ? (
            <tr key={f.clave} className="cal-grupo"><th scope="rowgroup" colSpan={columnas.length + (semana ? 2 : 1)}><EtiquetaFarmacia f={f.grupo} /></th></tr>
          ) : (
            <tr key={f.clave} data-fila={f.clave} className={f.franja ? `cal-sub s-${f.franja.toLowerCase()}` : undefined}>
              {f.cabecera !== undefined && <th scope="row" className="cal-fila" rowSpan={f.span} title={f.titulo}>{f.cabecera}</th>}
              {f.franja && <th scope="row" className="cal-franja" title={TEXTO_FRANJA[f.franja]}>{f.franja === 'MANANA' ? 'M' : 'T'}</th>}
              {f.celdas.map((c, j) => {
                const fechaCol = columnas[j]?.clave ?? '';
                // TA4: en «Por persona» las columnas son días del mes: la fecha es la de la celda.
                const fechaCapa = variante === 'persona' ? (c?.fecha ?? '') : fechaCol;
                // TA3-4: marcas de guardia de la persona ese día (capa al pie; no cambia la celda ni sus eventos).
                const m = capa && f.capa && f.tid && fechaCapa ? capa.de(f.tid, fechaCapa) : undefined;
                const capaCelda = m && capa && f.tid
                  ? <CapaCelda m={m} tid={f.tid} fecha={fechaCapa} primero={m.lunes === fechaCapa || j === 0} capa={capa} /> : null;
                const conCapa = capa && f.capa ? ' con-capa' : '';
                if (!c) {
                  return f.franja
                    ? <td key={j} className={`cal-sin-franja${diaSemana(fechaCol) >= 5 ? ' finde' : ''}${fechaCol === hoyF ? ' hoy' : ''}${conCapa}`}
                        title={`${f.nombre ?? ''} no trabaja de ${TEXTO_FRANJA[f.franja]}`} aria-hidden={capaCelda ? undefined : true}>{capaCelda}</td>
                    : <td key={j} className="cal-vacia" aria-hidden="true" />;
                }
                const k = clave(c);
                const evs = eventosDe(eventos, c);
                const finde = diaSemana(c.fecha) >= 5;
                const marcasTxt = textoMarcas(capa && f.tid ? capa.de(f.tid, c.fecha) : undefined);
                const etiqueta = `${nombres.get(c.trabajadora_id) ?? ''}, ${F_LARGA.format(dia(c.fecha))}${c.franja ? `, ${TEXTO_FRANJA[c.franja]}` : ''}: ${evs.length
                  ? evs.map((e) => descripcionEvento(e, !c.franja)).join('; ') : 'libre'}${marcasTxt ? `; ${marcasTxt}` : ''}`;
                const manana = eventos.get(claveEv(c.trabajadora_id, c.fecha, 'MANANA'));
                const tarde = eventos.get(claveEv(c.trabajadora_id, c.fecha, 'TARDE'));
                const unico = c.franja ? evs[0] ?? null : null;
                return (
                  <td key={k} className={`${finde ? 'finde' : ''}${c.fecha === hoyF ? ' hoy' : ''}${conCapa}`}>
                    <button type="button" className={`cal-celda${c.franja ? ' de-franja' : ' de-dia'}${sel.has(k) ? ' sel' : ''}${enTrazo?.has(k) ? ' trazo' : ''}`}
                      data-celda={k}
                      {...(c.franja
                        ? { 'data-tipo': unico?.tipo ?? '', 'data-estado': unico?.estado ?? '', 'data-horas': unico?.horas_efectivas ?? '', 'data-nota': unico?.nota ?? '' }
                        : { 'data-tipo-manana': manana?.tipo ?? '', 'data-tipo-tarde': tarde?.tipo ?? '' })}
                      aria-pressed={herr.k === 'seleccion' ? sel.has(k) : undefined} aria-label={etiqueta} title={etiqueta}
                      onPointerDown={(e) => abajo(e, [i, j])} onPointerEnter={() => encima([i, j])} onPointerUp={(e) => arriba(e, [i, j])}
                      onPointerCancel={() => { toque.current = null; }} onClick={() => clic([i, j])}>
                      {c.franja
                        ? unico && <Evento ev={unico} color={colores[unico.tipo]} atenuado={atenuado(unico)} compacto={false} />
                        : (
                          <>
                            <span className="cal-mitad m-manana">{manana && <Evento ev={manana} color={colores[manana.tipo]} atenuado={atenuado(manana)} compacto />}</span>
                            <span className="cal-mitad m-tarde">{tarde && <Evento ev={tarde} color={colores[tarde.tipo]} atenuado={atenuado(tarde)} compacto />}</span>
                          </>
                        )}
                    </button>
                    {capaCelda}
                  </td>
                );
              })}
            </tr>
          )))}
        </tbody>
        {pie && (
          <tfoot>
            <tr>
              <th scope="row" className="cal-fila" colSpan={semana ? 2 : 1}>{pie.titulo}</th>
              {pie.valores.map((v, j) => <td key={j} className="cal-pie" data-pie={columnas[j]?.clave}>{v ?? ''}</td>)}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}

function CabeceraPersona({ t, compacto }: { t: Trabajadora; compacto: boolean }) {
  return (
    <span className="cal-persona">
      <Link to={`/trabajadores/${t.id}`} className="rrhh-nombre" draggable={false}>{t.nombre}</Link>
      {!compacto && (
        <span className="cal-persona-jornada tenue">
          {TEXTO_JORNADA[t.tipo_jornada]} · {horasTxt(t.horas_diarias)}{esTitular(t) ? ' · titular' : ''}
        </span>
      )}
    </span>
  );
}

/** Personas que trabajan (alguna franja de JORNADA) ese día. */
const trabajanEl = (trabajadoras: Trabajadora[], eventos: Map<string, EventoCalendario>, f: string) =>
  trabajadoras.filter((t) => FRANJAS.some((fr) => eventos.get(claveEv(t.id, f, fr))?.tipo === 'JORNADA')).length;

function RejillaPeriodo({ vista, desde, hasta, hoyF, trabajadoras, agrupar, eventos, sel, herr, colores, tipoFiltro, onAplicar, festivos, capa, onCabecera }: {
  vista: Vista; desde: string; hasta: string; hoyF: string; trabajadoras: Trabajadora[]; agrupar: boolean;
  eventos: Map<string, EventoCalendario>; sel: Set<string>; herr: Herramienta; colores: Colores; tipoFiltro: TipoEvento | ''; onAplicar: (c: Celda[]) => void;
  festivos: ReadonlyMap<string, FestivoVista>; capa: CapaGuardias | null; onCabecera: ((fecha: string) => void) | null;
}) {
  const dias = rangoFechas(desde, hasta);
  const semana = vista === 'semana';
  const columnas: Columna[] = dias.map((f) => ({
    clave: f, titulo: mayuscula(F_LARGA.format(dia(f))), finde: diaSemana(f) >= 5, hoy: f === hoyF, festivo: festivos.get(f)?.nombre,
    cabecera: semana
      ? <><span className="cal-dsem">{F_DIA_SEM.format(dia(f))}</span> <span className="cal-dnum">{Number(f.slice(8))}</span></>
      : <><span className="cal-dsem">{INICIALES[diaSemana(f)]}</span><span className="cal-dnum">{Number(f.slice(8))}</span></>,
  }));
  const dentro = (f: string) => f >= FECHA_MIN && f <= FECHA_MAX;
  const filas: Fila[] = [];
  let grupo: FarmaciaRrhh | null = null;
  for (const t of trabajadoras) {
    if (agrupar && t.farmacia !== grupo) { grupo = t.farmacia; filas.push({ clave: `g-${grupo}`, grupo, celdas: [] }); }
    if (semana) {
      // Dos subfilas por persona: mañana y tarde (la franja que no trabaja, o fuera de su alta, queda rayada).
      const propias = FRANJAS_DE_JORNADA[t.tipo_jornada];
      for (const franja of FRANJAS) {
        filas.push({
          clave: `${t.id}|${franja}`, franja, nombre: t.nombre, titulo: t.nombre, tid: t.id, capa: franja === 'TARDE',
          ...(franja === 'MANANA' ? { cabecera: <CabeceraPersona t={t} compacto={false} />, span: 2 } : {}),
          celdas: dias.map((f) => (dentro(f) && deAltaEl(t, f) && propias.includes(franja) ? { trabajadora_id: t.id, fecha: f, franja } : null)),
        });
      }
    } else {
      filas.push({
        clave: t.id, titulo: t.nombre, nombre: t.nombre, cabecera: <CabeceraPersona t={t} compacto />, tid: t.id, capa: true,
        celdas: dias.map((f) => (dentro(f) && deAltaEl(t, f) ? { trabajadora_id: t.id, fecha: f } : null)),
      });
    }
  }
  return (
    <Rejilla variante={semana ? 'semana' : 'mes'} columnas={columnas} filas={filas} nombres={new Map(trabajadoras.map((t) => [t.id, t.nombre]))}
      eventos={eventos} sel={sel} herr={herr} colores={colores} tipoFiltro={tipoFiltro} hoyF={hoyF} onAplicar={onAplicar}
      pie={{ titulo: 'Trabajan', valores: dias.map((f) => trabajanEl(trabajadoras, eventos, f)) }} capa={capa} onCabecera={onCabecera} />
  );
}

// ---------------------------------------------------------------------------
// Vista por persona: el año de una persona (12 meses × 31 días), pintable por día completo
// ---------------------------------------------------------------------------

function VistaPersona({ t, anio, hoyF, eventos, sel, herr, colores, tipoFiltro, onAplicar, capa = null }: {
  t: Trabajadora; anio: string; hoyF: string; eventos: Map<string, EventoCalendario>; sel: Set<string>; herr: Herramienta; colores: Colores;
  tipoFiltro: TipoEvento | ''; onAplicar: (c: Celda[]) => void;
  /** TA4: marcas de guardia de la persona (semanal, apoyo y guardia festiva), como en semana y mes. */
  capa?: CapaGuardias | null;
}) {
  const columnas: Columna[] = Array.from({ length: 31 }, (_, i) => ({ clave: String(i + 1), cabecera: i + 1 }));
  const filas: Fila[] = Array.from({ length: 12 }, (_, m) => {
    const primero = `${anio}-${String(m + 1).padStart(2, '0')}-01`;
    const ultimo = Number(ultimoDeMes(primero).slice(8));
    const mes = mayuscula(F_MES_SOLO.format(dia(primero)));
    return {
      clave: primero.slice(0, 7), titulo: mes, cabecera: <span className="cal-mes-nombre">{mes}</span>, tid: t.id, capa: true,
      celdas: columnas.map((_, d) => {
        const f = `${primero.slice(0, 8)}${String(d + 1).padStart(2, '0')}`;
        return d < ultimo && deAltaEl(t, f) ? { trabajadora_id: t.id, fecha: f } : null;
      }),
    };
  });
  const delAnio = [...eventos.values()].filter((e) => e.trabajadora_id === t.id && e.fecha.startsWith(anio));
  // TA-REAL: horas por tipo (horas_efectivas); turno de guardia y localizada no suman.
  const horasDe = (tipo: TipoEvento) => delAnio.filter((e) => e.tipo === tipo).reduce((s, e) => s + horasQueSuman(e), 0);
  return (
    <section className="cal-persona-vista" data-vista-persona={t.id}>
      <div className="cal-persona-cabecera">
        <h3><Link to={`/trabajadores/${t.id}`} className="rrhh-nombre">{t.nombre}</Link></h3>
        <EtiquetaFarmacia f={t.farmacia} />
        <span className="tenue">{TEXTO_CATEGORIA[t.categoria]} · {TEXTO_JORNADA[t.tipo_jornada]} · {horasTxt(t.horas_diarias)}/día</span>
      </div>
      <dl className="cal-totales" aria-label={`Días por tipo en ${anio}`}>
        {TIPOS_EVENTO.map((tipo) => {
          const n = new Set(delAnio.filter((e) => e.tipo === tipo).map((e) => e.fecha)).size;
          // Los tipos de TA3 solo salen si hay alguno.
          if (n === 0 && !TIPOS_PINTABLES.includes(tipo)) return null;
          return (
            <div key={tipo} className="cal-total" data-total-tipo={tipo} style={estiloColor(colores[tipo])}>
              <dt><span className="cal-muestra" aria-hidden="true">{CODIGO_TIPO_EVENTO[tipo]}</span>{TEXTO_TIPO_EVENTO[tipo]}</dt>
              <dd>{n} {n === 1 ? 'día' : 'días'}{n > 0 && <span className="tenue" data-total-horas> · {TIPOS_SIN_HORAS.includes(tipo) ? 'no suma horas' : horasTxt(horasDe(tipo))}</span>}</dd>
            </div>
          );
        })}
      </dl>
      <Rejilla variante="persona" columnas={columnas} filas={filas} nombres={new Map([[t.id, t.nombre]])} eventos={eventos} sel={sel} herr={herr}
        colores={colores} tipoFiltro={tipoFiltro} hoyF={hoyF} onAplicar={onAplicar} capa={capa} />
    </section>
  );
}

// ---------------------------------------------------------------------------
// Vista año: resumen por día (quién falta y cuántos trabajan)
// ---------------------------------------------------------------------------

function VistaAnio({ anio, hoyF, trabajadoras, eventos, colores, tipoFiltro, onDia, guardias, herr, onBanda, onDiaHerramienta }: {
  anio: string; hoyF: string; trabajadoras: Trabajadora[]; eventos: Map<string, EventoCalendario>; colores: Colores;
  tipoFiltro: TipoEvento | ''; onDia: (f: string) => void; guardias: GuardiasRespuestaDTO | null;
  /** TA3-4: con una herramienta de guardia o la goma, la banda y los días actúan en lugar de abrir la semana. */
  herr: Herramienta; onBanda: (lunes: string) => void; onDiaHerramienta: (f: string) => void;
}) {
  const conHerr = esHerramientaGuardia(herr) || herr.k === 'goma';
  const accionBanda = herr.k === 'guardia' ? 'Elegir guardia y apoyo' : herr.k === 'apoyo' ? 'Elegir apoyo del sábado'
    : herr.k === 'otra' ? 'Poner OTRA (farmacia ajena)' : herr.k === 'goma' ? 'Quitar la guardia de la semana' : null;
  const bandaActiva = accionBanda !== null && guardias !== null;
  // TA3: semanas de guardia (por lunes) y festivos (por fecha); sin datos (REAL), ni bandas ni marcas.
  const semanas = new Map<string, SemanaGuardiaVista>((guardias?.disponible ? guardias.semanas : []).map((s) => [s.lunes, s]));
  const festivos = new Map<string, FestivoVista>((guardias?.disponible ? guardias.festivos : []).map((f) => [f.fecha, f]));
  const nombre = new Map(trabajadoras.map((t) => [t.id, t.nombre]));
  const porDia = new Map<string, EventoCalendario[]>();
  for (const e of eventos.values()) {
    if (!nombre.has(e.trabajadora_id) || !e.fecha.startsWith(anio)) continue;
    porDia.set(e.fecha, [...(porDia.get(e.fecha) ?? []), e]);
  }
  /** Ausencias de un día: una por persona y tipo (la franja no duplica). */
  const ausencias = (f: string) => {
    const vistos = new Map<string, EventoCalendario>();
    for (const e of porDia.get(f) ?? []) if (e.tipo !== 'JORNADA' && (tipoFiltro === '' || e.tipo === tipoFiltro)) vistos.set(`${e.trabajadora_id}|${e.tipo}`, e);
    return [...vistos.values()];
  };
  return (
    <div className="cal-anio" data-vista-anio={anio}>
      {Array.from({ length: 12 }, (_, m) => {
        const primero = `${anio}-${String(m + 1).padStart(2, '0')}-01`;
        const dias = rangoFechas(primero, ultimoDeMes(primero));
        const total = dias.reduce((s, f) => s + new Set(ausencias(f).map((e) => e.trabajadora_id)).size, 0);
        const ultimo = dias[dias.length - 1];
        const lunesMes: string[] = [];
        for (let l = lunesDe(primero); l <= ultimo; l = sumarDias(l, 7)) lunesMes.push(l);
        const diaBoton = (f: string) => {
          const faltan = ausencias(f);
          const personas = new Set(faltan.map((e) => e.trabajadora_id)).size;
          const trabajan = new Set((porDia.get(f) ?? []).filter((e) => e.tipo === 'JORNADA').map((e) => e.trabajadora_id)).size;
          const fe = festivos.get(f);
          // TA4: popup «6/1 Reis · Guardia festiva: RITA · Raquel» antes del resto del día.
          const titulo = `${fe ? `${textoGuardiaFestiva(fe)} · ` : ''}${mayuscula(F_LARGA.format(dia(f)))}: ${trabajan} trabajan${faltan.length
            ? ` · ${faltan.map((e) => `${TEXTO_TIPO_EVENTO[e.tipo]}: ${nombre.get(e.trabajadora_id)}`).join('; ')}` : ''}`;
          return (
            <button key={f} type="button" className={`cal-dia${diaSemana(f) >= 5 ? ' finde' : ''}${f === hoyF ? ' hoy' : ''}${trabajan ? ' con-jornada' : ''}${fe ? ' festivo' : ''}`}
              data-dia={f} data-ausencias={personas} data-trabajan={trabajan} title={titulo}
              aria-label={`${titulo}. ${conHerr ? (herr.k === 'goma' ? (fe ? 'Dar de baja el festivo' : 'Goma: solo sobre festivos y bandas') : 'Aplicar la herramienta') : 'Abrir la semana'}`}
              {...(fe ? { 'data-festivo': fe.guardia?.farmacia ?? '' } : {})}
              onClick={() => (conHerr ? onDiaHerramienta(f) : onDia(f))}>
              <span className="cal-dia-num">{Number(f.slice(8))}</span>
              {fe && (
                <span className={`cal-dia-festivo${fe.guardia ? ' con-guardia' : ''}`} style={fe.guardia ? estiloGuardiaFestiva(fe.guardia.farmacia) : undefined} aria-hidden="true"
                  data-marca-festiva={f} data-festiva-farmacia={fe.guardia?.farmacia ?? ''}>
                  {fe.guardia === null ? CODIGO_TIPO_EVENTO.FESTIVO : fe.guardia.farmacia === 'OTRA' ? 'OT' : (fe.guardia.persona?.iniciales ?? fe.guardia.farmacia.charAt(0))}
                </span>
              )}
              {faltan.length > 0 && (
                <span className="cal-dia-marcas" aria-hidden="true">
                  {faltan.slice(0, 3).map((e) => <span key={e.id} className="cal-dia-marca" style={estiloColor(colores[e.tipo])} />)}
                  {faltan.length > 3 && <span className="cal-dia-mas">+{faltan.length - 3}</span>}
                </span>
              )}
            </button>
          );
        };
        return (
          <section key={primero} className="tarjeta cal-mes" data-mes={primero.slice(0, 7)}>
            <h3>{mayuscula(F_MES_SOLO.format(dia(primero)))} <span className="tenue">{total > 0 ? `${total} ${total === 1 ? 'ausencia' : 'ausencias'}` : ''}</span></h3>
            <div className="cal-mes-rejilla">
              {INICIALES.map((x) => <span key={x} className="cal-mes-dsem" aria-hidden="true">{x}</span>)}
              {lunesMes.map((l) => {
                const s = semanas.get(l);
                return [
                  ...[0, 1, 2, 3, 4, 5, 6].map((n) => {
                    const f = sumarDias(l, n);
                    return f.slice(0, 7) === primero.slice(0, 7) ? diaBoton(f) : <span key={`h${f}`} aria-hidden="true" />;
                  }),
                  // TA3: banda de la semana de guardia (toda la fila), con el color de la farmacia y las iniciales.
                  ...(s ? [<BandaGuardia key={`b${l}`} s={s} {...(bandaActiva ? { accion: accionBanda, onClick: () => onBanda(l) } : {})} />] : []),
                ];
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TA3-4: diálogos de las herramientas de guardia
// ---------------------------------------------------------------------------

/** Festivo: nombre (1–60) y ámbito (por defecto local) del festivo común de ese día. */
function DialogoFestivo({ fecha, onCrear, onCancelar }: { fecha: string; onCrear: (nombre: string, ambito: AmbitoFestivoTa3) => void; onCancelar: () => void }) {
  const [nombre, setNombre] = useState('');
  const [ambito, setAmbito] = useState<AmbitoFestivoTa3>(AMBITO_POR_DEFECTO);
  const campo = useRef<HTMLInputElement>(null);
  useEffect(() => { campo.current?.focus(); }, [fecha]);
  const crear = (e: FormEvent) => { e.preventDefault(); onCrear(nombre, ambito); };
  return (
    <form className="tarjeta cal-oferta gu-dialogo" onSubmit={crear} noValidate aria-labelledby="t-nuevo-festivo" data-dialogo-festivo={fecha}
      onKeyDown={(e) => { if (e.key === 'Escape') onCancelar(); }}>
      <p id="t-nuevo-festivo"><strong>Nuevo festivo: {mayuscula(F_LARGA.format(dia(fecha)))}</strong> <span className="tenue">común a PIO y RITA</span></p>
      <div className="gu-dialogo-campos">
        <label className="rrhh-campo gu-alta-nombre">Nombre <span className="rrhh-campo-pista">{nombre.length}/{LARGO_NOMBRE_FESTIVO}</span>
          <input ref={campo} name="nombre_festivo" maxLength={LARGO_NOMBRE_FESTIVO} value={nombre} autoComplete="off" onChange={(e) => setNombre(e.target.value)} />
        </label>
        <label className="rrhh-campo">Ámbito
          <select name="ambito_festivo" value={ambito} onChange={(e) => setAmbito(e.target.value as AmbitoFestivoTa3)}>
            {AMBITOS_FESTIVO.map((a) => <option key={a} value={a}>{TEXTO_AMBITO[a]}</option>)}
          </select>
        </label>
      </div>
      <div className="rrhh-botones">
        <button type="submit" className="boton-primario" data-crear-festivo>Crear festivo</button>
        <button type="button" className="boton-secundario" onClick={onCancelar}>Cancelar</button>
      </div>
    </form>
  );
}

/**
 * TA4: guardia festiva de un día. Farmacia (PIO, RITA u OTRA), persona (solo PIO/RITA: personas de esa farmacia de alta
 * ese día) y nombre del festivo (opcional; si el día ya es festivo, se propone su nombre). Con guardia, también anular.
 */
function DialogoGuardiaFestiva({ fecha, festivo, fichas, persona, farmaciaFiltro, onGuardar, onAnular, onCancelar }: {
  fecha: string; festivo: FestivoVista | undefined; fichas: Trabajadora[]; persona: string | null; farmaciaFiltro: FarmaciaRrhh | null;
  onGuardar: (farmacia: FarmaciaGuardia, persona: string | null, nombre: string) => void; onAnular: () => void; onCancelar: () => void;
}) {
  const deFila = persona ? fichas.find((t) => t.id === persona) : undefined;
  const inicial: FarmaciaGuardia = festivo?.guardia?.farmacia ?? deFila?.farmacia ?? farmaciaFiltro ?? 'PIO';
  const [farmacia, setFarmacia] = useState<FarmaciaGuardia>(inicial);
  const [quien, setQuien] = useState<string>(deFila?.id ?? festivo?.guardia?.persona?.id ?? '');
  const [nombre, setNombre] = useState(festivo?.nombre ?? '');
  const campo = useRef<HTMLSelectElement>(null);
  useEffect(() => { campo.current?.focus(); }, [fecha]);
  const candidatas = candidatasFestiva(fichas, farmacia, fecha);
  // Al cambiar de farmacia, la persona tiene que ser de la nueva farmacia.
  const valida = candidatas.some((t) => t.id === quien) ? quien : '';
  const guardar = (e: FormEvent) => { e.preventDefault(); onGuardar(farmacia, farmacia === 'OTRA' ? null : valida || null, nombre); };
  return (
    <form className="tarjeta cal-oferta gu-dialogo" onSubmit={guardar} noValidate aria-labelledby="t-guardia-festiva" data-dialogo-festiva={fecha}
      onKeyDown={(e) => { if (e.key === 'Escape') onCancelar(); }}>
      <p id="t-guardia-festiva">
        <strong>Guardia festiva: {mayuscula(F_LARGA.format(dia(fecha)))}</strong>{' '}
        <span className="tenue">{festivo ? `festivo «${festivo.nombre}»${festivo.guardia ? ` · ahora: ${textoGuardiaFestiva(festivo).split(' · Guardia festiva: ')[1]}` : ''}` : 'aún no es festivo: se dará de alta'}</span>
      </p>
      <div className="gu-dialogo-campos">
        <label className="rrhh-campo">Farmacia
          <select ref={campo} name="farmacia_festiva" value={farmacia} onChange={(e) => setFarmacia(e.target.value as FarmaciaGuardia)} data-festiva-campo="farmacia">
            {(['PIO', 'RITA', 'OTRA'] as const).map((f) => <option key={f} value={f}>{TEXTO_FARMACIA_GUARDIA[f]}</option>)}
          </select>
        </label>
        {farmacia !== 'OTRA' && (
          <label className="rrhh-campo">Persona
            <select name="persona_festiva" value={valida} onChange={(e) => setQuien(e.target.value)} data-festiva-campo="persona">
              <option value="">Elige…</option>
              {candidatas.map((t) => <option key={t.id} value={t.id}>{t.nombre}</option>)}
            </select>
          </label>
        )}
        <label className="rrhh-campo gu-alta-nombre">Nombre del festivo <span className="rrhh-campo-pista">opcional · {nombre.length}/{LARGO_NOMBRE_FESTIVO}</span>
          <input name="nombre_festiva" maxLength={LARGO_NOMBRE_FESTIVO} value={nombre} autoComplete="off" placeholder={festivo ? festivo.nombre : `p. ej. Reis (si no: «${NOMBRE_FESTIVO_POR_DEFECTO}»)`}
            onChange={(e) => setNombre(e.target.value)} data-festiva-campo="nombre" />
        </label>
      </div>
      <div className="rrhh-botones">
        <button type="submit" className="boton-primario" data-guardar-festiva>{festivo?.guardia ? 'Guardar cambios' : 'Guardar guardia festiva'}</button>
        {festivo?.guardia && <button type="button" className="boton-peligro" onClick={onAnular} data-anular-festiva>Anular guardia festiva</button>}
        <button type="button" className="boton-secundario" onClick={onCancelar}>Cancelar</button>
      </div>
    </form>
  );
}

/** Vista año: guardia y apoyo de una semana (personas de la farmacia elegida, de alta ese fin de semana). */
function SelectorSemana({ lunes, papel, semana, fichas, farmacia, onGuardar, onCancelar }: {
  lunes: string; papel: 'guardia' | 'apoyo'; semana: SemanaGuardiaVista | undefined; fichas: Trabajadora[];
  /** Farmacia del filtro del calendario (null: AMBAS, se elige aquí). */
  farmacia: FarmaciaRrhh | null;
  onGuardar: (guardia: string, apoyo: string | null) => void; onCancelar: () => void;
}) {
  const inicial: FarmaciaRrhh = farmacia ?? (semana?.farmacia === 'PIO' || semana?.farmacia === 'RITA' ? semana.farmacia : 'PIO');
  const misma = semana?.farmacia === inicial;
  const [f, setF] = useState<FarmaciaRrhh>(inicial);
  const [guardia, setGuardia] = useState(misma ? semana?.guardia?.id ?? '' : '');
  const [apoyo, setApoyo] = useState(misma ? semana?.apoyo?.id ?? '' : '');
  const opcionesG = candidatasSemana(fichas, f, lunes, 'guardia');
  const opcionesA = candidatasSemana(fichas, f, lunes, 'apoyo').filter((t) => t.id !== guardia);
  const cambiarF = (n: FarmaciaRrhh) => {
    setF(n);
    const igual = semana?.farmacia === n;
    setGuardia(igual ? semana?.guardia?.id ?? '' : ''); setApoyo(igual ? semana?.apoyo?.id ?? '' : '');
  };
  const guardar = (e: FormEvent) => { e.preventDefault(); onGuardar(guardia, apoyo === '' ? null : apoyo); };
  return (
    <form className="tarjeta cal-oferta gu-dialogo" onSubmit={guardar} noValidate aria-labelledby="t-selector-semana" data-selector-semana={lunes}
      onKeyDown={(e) => { if (e.key === 'Escape') onCancelar(); }}>
      <p id="t-selector-semana"><strong>Semana {textoPeriodo('semana', lunes, sumarDias(lunes, 6))}</strong>
        <span className="tenue"> · {papel === 'apoyo' ? 'apoyo del sábado' : 'guardia y apoyo'}{semana?.farmacia ? ` · ahora: ${semana.farmacia === 'OTRA' ? 'OTRA (farmacia ajena)' : `${semana.farmacia}${semana.guardia ? `, ${semana.guardia.nombre}` : ''}`}` : ' · sin asignar'}</span></p>
      <div className="gu-dialogo-campos">
        {farmacia === null && (
          <label className="rrhh-campo">Farmacia
            <select value={f} onChange={(e) => cambiarF(e.target.value as FarmaciaRrhh)} data-selector-campo="farmacia">
              <option value="PIO">PIO</option><option value="RITA">RITA</option>
            </select>
          </label>
        )}
        <label className="rrhh-campo">Guardia (sábado y domingo)
          <select value={guardia} onChange={(e) => { setGuardia(e.target.value); if (e.target.value === apoyo) setApoyo(''); }} data-selector-campo="guardia">
            <option value="">Elige…</option>
            {opcionesG.map((t) => <option key={t.id} value={t.id}>{t.nombre}</option>)}
          </select>
        </label>
        <label className="rrhh-campo">Apoyo sábado
          <select value={apoyo} onChange={(e) => setApoyo(e.target.value)} data-selector-campo="apoyo">
            <option value="">Sin apoyo</option>
            {opcionesA.map((t) => <option key={t.id} value={t.id}>{t.nombre}</option>)}
          </select>
        </label>
      </div>
      <div className="rrhh-botones">
        <button type="submit" className="boton-primario" disabled={guardia === ''} data-selector-guardar>Guardar semana</button>
        <button type="button" className="boton-secundario" onClick={onCancelar}>Cancelar</button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Selección: pintar, borrar, confirmar; detalle del día con horas realizadas y nota (a mano)
// ---------------------------------------------------------------------------

/** Campo Nota con contador y aviso de salud (siempre visible en el detalle del día). */
function CampoNota({ valor, onValor, deshabilitado, error, nombre = 'nota_evento' }: {
  valor: string; onValor: (v: string) => void; deshabilitado?: boolean; error?: string | null; nombre?: string;
}) {
  return (
    <label className="rrhh-campo cal-editor-nota">Nota <span className="rrhh-campo-pista">opcional · {valor.length}/{LARGO_NOTA}</span>
      <input name={nombre} value={valor} maxLength={LARGO_NOTA} autoComplete="off" disabled={deshabilitado} aria-invalid={!!error}
        onChange={(e) => onValor(e.target.value)} />
      <span className="cal-aviso-nota" data-aviso-nota>{AVISO_NOTA}</span>
      {error && <span className="rrhh-campo-error" role="alert" data-error-campo="nota">{error}</span>}
    </label>
  );
}

function EditorEvento({ ev, onCambio }: { ev: EventoCalendario; onCambio: (cuerpo: object) => void }) {
  const inicial = NUM.format(ev.horas_efectivas);
  const [horas, setHoras] = useState(inicial);
  const [nota, setNota] = useState(ev.nota ?? '');
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setHoras(NUM.format(ev.horas_efectivas)); setNota(ev.nota ?? ''); setError(null); }, [ev.id, ev.horas_efectivas, ev.nota]);
  const bloqueado = ev.estado === 'CONFIRMADO';
  const guardar = () => {
    const h = Number(horas.trim().replace(',', '.'));
    if (!Number.isFinite(h) || h <= 0 || h > HORAS_EVENTO_MAX) { setError(`Horas: más de 0 y como máximo ${HORAS_EVENTO_MAX}`); return; }
    setError(null);
    // TA-REAL: las horas solo se envían si cambian (si no, el evento sigue con las de la ficha: horas vacías).
    onCambio({ accion: 'EDITAR', evento_id: ev.id, ...(horas.trim() !== inicial ? { horas: h } : {}), nota: nota.trim() === '' ? null : nota });
  };
  return (
    <div className="cal-editor" data-editor-evento={ev.franja}>
      <label className="rrhh-campo cal-editor-horas">Horas realizadas
        <span className="rrhh-sufijo"><input name="horas_evento" inputMode="decimal" value={horas} disabled={bloqueado} onChange={(e) => setHoras(e.target.value)}
          aria-invalid={!!error} /><span aria-hidden="true">h</span></span>
        {error && <span className="rrhh-campo-error" data-error-campo="horas">{error}</span>}
      </label>
      <CampoNota valor={nota} onValor={setNota} deshabilitado={bloqueado} />
      {bloqueado
        ? <span className="tenue cal-editor-bloqueo">Confirmado: quita la confirmación para cambiar las horas o la nota.</span>
        : <button type="button" className="boton-secundario" onClick={guardar} data-sel="guardar">Guardar</button>}
    </div>
  );
}

/** TA2-4: franja libre en el detalle: el campo Nota se ve, pero anotar pide pintar antes un evento. */
function EditorVacio({ franja }: { franja: Franja }) {
  const [nota, setNota] = useState('');
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="cal-editor" data-editor-vacio={franja}>
      <CampoNota valor={nota} error={error} onValor={(v) => { setNota(v); setError(v.trim() === '' ? null : AVISO_NOTA_VACIA); }} />
      <button type="button" className="boton-secundario" onClick={() => setError(AVISO_NOTA_VACIA)} data-sel="guardar-vacio">Guardar</button>
    </div>
  );
}

function BarraSeleccion({ sel, eventos, colores, fichas, onLimpiar, onCambio }: {
  sel: Set<string>; eventos: Map<string, EventoCalendario>; colores: Colores; fichas: Map<string, Trabajadora>;
  onLimpiar: () => void; onCambio: (cuerpo: object) => void;
}) {
  const celdas = [...sel].map(deClave);
  const [tipo, setTipo] = useState<TipoEvento>('VACACIONES');
  const [anotar, setAnotar] = useState(false);
  const [notaSel, setNotaSel] = useState('');
  const [mensaje, setMensaje] = useState<string | null>(null);
  const marco = useRef<HTMLElement>(null);
  const claveSel = [...sel].sort().join(',');
  useEffect(() => { setAnotar(false); setNotaSel(''); setMensaje(null); }, [claveSel]);

  // Franjas de la selección: la de la celda o, en un día completo, las de la ficha.
  const franjasDe = (c: Celda): readonly Franja[] => (c.franja ? [c.franja] : FRANJAS_DE_JORNADA[fichas.get(c.trabajadora_id)?.tipo_jornada ?? 'COMPLETA']);
  const huecos = celdas.flatMap((c) => franjasDe(c).map((f) => eventos.get(claveEv(c.trabajadora_id, c.fecha, f)) ?? null));
  const conEvento = huecos.filter((e): e is EventoCalendario => e !== null);
  const anotables = conEvento.filter((e) => e.estado !== 'CONFIRMADO');
  const vacias = huecos.length - conEvento.length;
  const confirmadas = conEvento.length - anotables.length;

  // Detalle del día: con una sola celda seleccionada (una franja o el día completo): todas sus franjas.
  const unica = celdas.length === 1 ? celdas[0] : null;
  const franjasDetalle = unica ? franjasDe(unica) : [];

  /** «Añadir nota»: 1 franja con evento, su editor; varias, la misma nota para todas; ninguna, pintar antes. */
  const pulsarAnotar = () => {
    setMensaje(null);
    if (conEvento.length === 0) { setAnotar(false); setMensaje(AVISO_NOTA_VACIA); return; }
    if (anotables.length === 0) { setAnotar(false); setMensaje('Esas franjas están confirmadas: quita antes la confirmación para anotarlas'); return; }
    if (unica && conEvento.length === 1) {
      const campo = marco.current?.querySelector<HTMLInputElement>(`[data-editor-evento="${anotables[0].franja}"] input[name="nota_evento"]`);
      if (campo) { campo.scrollIntoView({ block: 'nearest' }); campo.focus(); return; }
    }
    setNotaSel(anotables.length === 1 ? (anotables[0].nota ?? '') : '');
    setAnotar(true);
  };
  const aplicarNota = () => { onCambio({ accion: 'ANOTAR', celdas, nota: notaSel.trim() === '' ? null : notaSel }); setAnotar(false); };

  return (
    <section ref={marco} className="tarjeta cal-seleccion" aria-label="Días seleccionados" data-barra-seleccion>
      <strong data-seleccionados>{sel.size} {sel.size === 1 ? 'seleccionado' : 'seleccionados'}</strong>
      <div className="cal-seleccion-acciones">
        <span className="cal-pintar-como">
          <select value={tipo} onChange={(e) => setTipo(e.target.value as TipoEvento)} aria-label="Tipo para pintar la selección" data-tipo-seleccion
            style={estiloColor(colores[tipo])}>
            {TIPOS_PINTABLES.map((t) => <option key={t} value={t}>{TEXTO_TIPO_EVENTO[t]}</option>)}
          </select>
          <button type="button" className="boton-secundario" onClick={() => onCambio({ accion: 'PINTAR', tipo, celdas })} data-sel="pintar">Pintar</button>
        </span>
        <button type="button" className="boton-secundario" aria-expanded={anotar} onClick={pulsarAnotar} data-sel="anotar">
          <span className="cal-nota-marca" aria-hidden="true">✎</span> Añadir nota
        </button>
        <button type="button" className="boton-primario" onClick={() => onCambio({ accion: 'CONFIRMAR', celdas })} data-sel="confirmar">Confirmar</button>
        <button type="button" className="boton-secundario" onClick={() => onCambio({ accion: 'DESCONFIRMAR', celdas })} data-sel="desconfirmar">Quitar confirmación</button>
        <button type="button" className="boton-peligro-suave" title="Se anulan y quedan en el historial; lo confirmado no se toca"
          onClick={() => onCambio({ accion: 'BORRAR', celdas })} data-sel="borrar">Borrar</button>
        <button type="button" className="cal-enlace" onClick={onLimpiar} data-sel="limpiar">Quitar selección</button>
      </div>
      {mensaje && <p className="rrhh-error" role="alert" data-aviso-anotar>{mensaje}.</p>}
      {anotar && (
        <div className="cal-anotar" data-anotar-seleccion>
          <p className="cal-anotar-titulo">
            Misma nota para {anotables.length === 1 ? 'la franja con evento' : `las ${anotables.length} franjas con evento`}
            {(vacias > 0 || confirmadas > 0) && (
              <span className="tenue" data-anotar-omitidas>
                {' '}({vacias + confirmadas === 1 ? 'se omite' : 'se omiten'} {[vacias > 0 ? `${vacias} ${vacias === 1 ? 'vacía' : 'vacías'}` : '', confirmadas > 0 ? `${confirmadas} ${confirmadas === 1 ? 'confirmada' : 'confirmadas'}` : '']
                  .filter(Boolean).join(' y ')})
              </span>
            )}
          </p>
          <CampoNota valor={notaSel} onValor={setNotaSel} nombre="nota_seleccion" />
          <div className="rrhh-botones">
            <button type="button" className="boton-primario" disabled={notaSel.trim() === ''} onClick={aplicarNota} data-sel="aplicar-nota">Aplicar nota</button>
            <button type="button" className="boton-secundario" onClick={() => setAnotar(false)}>Cancelar</button>
          </div>
        </div>
      )}
      {unica && (
        <div className="cal-detalle" data-detalle-dia>
          <p className="cal-detalle-titulo">
            <strong>{fichas.get(unica.trabajadora_id)?.nombre}</strong> · {mayuscula(F_LARGA.format(dia(unica.fecha)))}{unica.franja ? ` · ${TEXTO_FRANJA[unica.franja]}` : ''}
          </p>
          {franjasDetalle.map((f) => {
            const ev = eventos.get(claveEv(unica.trabajadora_id, unica.fecha, f));
            return ev ? (
              <div key={ev.id} className="cal-detalle-ev" data-detalle-ev={ev.franja}>
                <span className="cal-detalle-que" style={estiloColor(colores[ev.tipo])}>
                  <span className="cal-muestra" aria-hidden="true">{CODIGO_TIPO_EVENTO[ev.tipo]}</span>
                  <span>{mayuscula(TEXTO_FRANJA[ev.franja])}: {TEXTO_TIPO_EVENTO[ev.tipo]} · {horasTxt(ev.horas_efectivas)}{ev.horas === null ? ' (de la ficha)' : ''} · {TEXTO_ESTADO_EVENTO[ev.estado]}</span>
                </span>
                {ev.nota && <span className="cal-detalle-nota" data-nota-detalle>Nota: {ev.nota}</span>}
                <EditorEvento ev={ev} onCambio={onCambio} />
              </div>
            ) : (
              <div key={f} className="cal-detalle-ev" data-detalle-libre={f}>
                <span className="cal-detalle-que cal-detalle-libre">{mayuscula(TEXTO_FRANJA[f])}: libre · elige un tipo y pulsa «Pintar»</span>
                <EditorVacio franja={f} />
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// TA-REAL «Notas próximas» (pedido por Pío): notas de hoy en adelante, por fecha
// ---------------------------------------------------------------------------

const MAX_NOTAS_VISIBLES = 6;

function NotasProximas({ carga, farmacia, onDia }: {
  carga: { estado: 'cargando' } | { estado: 'ok'; datos: NotaProxima[] } | { estado: 'error'; mensaje: string };
  farmacia: string; onDia: (fecha: string, persona: string) => void;
}) {
  const [todas, setTodas] = useState(false);
  if (carga.estado === 'cargando') return null;
  const linea = (n: NotaProxima) => (
    <li key={`${n.trabajadora_id}|${n.fecha}|${n.nota}`} data-nota-proxima={n.fecha}>
      <button type="button" className="cal-nota-proxima" onClick={() => onDia(n.fecha, n.trabajadora_id)}
        title="Abrir la semana de esa persona">
        <strong>{n.nombre}</strong>{farmacia === 'AMBAS' ? <> <EtiquetaFarmacia f={n.farmacia} /></> : null} — <span className="cal-nota-fecha">{F_CORTA.format(dia(n.fecha))}</span>: {n.nota}
      </button>
    </li>
  );
  return (
    <section className="tarjeta cal-notas" aria-labelledby="t-notas-proximas" data-notas-proximas>
      <h2 id="t-notas-proximas"><span className="cal-nota-marca" aria-hidden="true">✎</span> Notas próximas</h2>
      {carga.estado === 'error' && <p className="rrhh-error" role="alert">No se han podido leer las notas ({carga.mensaje}).</p>}
      {carga.estado === 'ok' && (carga.datos.length === 0
        ? <p className="tenue" data-notas-vacio>Sin notas de hoy en adelante.</p>
        : (
          <>
            <ul className="cal-notas-lista">{(todas ? carga.datos : carga.datos.slice(0, MAX_NOTAS_VISIBLES)).map(linea)}</ul>
            {carga.datos.length > MAX_NOTAS_VISIBLES && (
              <button type="button" className="cal-enlace" onClick={() => setTodas(!todas)} data-notas-todas>
                {todas ? 'Ver menos' : `Ver las ${carga.datos.length} notas`}
              </button>
            )}
          </>
        ))}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Historial de cambios del calendario (plegado por defecto)
// ---------------------------------------------------------------------------

function rangoTexto(desde: string, hasta: string) {
  return desde === hasta ? F_DIA_MES.format(dia(desde)) : `${F_DIA_MES.format(dia(desde))} – ${F_DIA_MES.format(dia(hasta))}`;
}
const MAX_CAMBIOS = 30;
const MAX_TRAZAS = 40;

function Traza({ t }: { t: TrazaEvento }) {
  return (
    <li>
      <span className="tenue">{t.nombre} · {F_CORTA.format(dia(t.fecha))} · {TEXTO_FRANJA[t.franja]}:</span>{' '}
      {t.antes && <><span className="rrhh-antes">{textoEvento(t.antes)}</span> → </>}
      <span className="rrhh-despues">{t.despues ? textoEvento(t.despues) : 'sin evento'}</span>
    </li>
  );
}

function Historial({ carga }: { carga: { estado: 'cargando' } | { estado: 'ok'; datos: CambioCalendario[] } | { estado: 'error'; mensaje: string } }) {
  const n = carga.estado === 'ok' ? carga.datos.length : null;
  return (
    <details className="tarjeta bloque cal-historial rrhh-plegable" data-historial-calendario>
      <summary>
        <h2>Historial de cambios del calendario</h2>
        <span className="tenue" data-historial-cuenta>{n === null ? '' : n === 0 ? 'sin cambios' : `${n} ${n === 1 ? 'cambio' : 'cambios'}`}</span>
      </summary>
      {carga.estado === 'cargando' && <p className="tenue">Cargando historial…</p>}
      {carga.estado === 'error' && <p className="rrhh-error" role="alert">No se ha podido leer el historial ({carga.mensaje}).</p>}
      {carga.estado === 'ok' && (carga.datos.length === 0
        ? <p className="tenue vacio" data-historial-vacio>Sin cambios desde la carga de ejemplo.</p>
        : (
          <ul className="rrhh-historial">
            {carga.datos.slice(0, MAX_CAMBIOS).map((c) => (
              <li key={c.id} className="rrhh-cambio" data-cambio={c.origen} data-deshecho={c.deshecho ? 'si' : 'no'}>
                <div className="rrhh-cambio-cabecera">
                  <strong data-cambio-texto>{describirCambio(c)}</strong>
                  {c.deshecho && <span className="insignia n insignia-mini">deshecho</span>}
                  <span className="tenue">{rangoTexto(c.desde, c.hasta)} · {c.personas.slice(0, 3).join(', ')}{c.personas.length > 3 ? ` y ${c.personas.length - 3} más` : ''}</span>
                  <span className="tenue">{fechaHora(c.cuando)} · {c.quien}</span>
                </div>
                <details className="cal-trazas">
                  <summary>Ver {c.n === 1 ? 'la franja' : `las ${c.n} franjas`}</summary>
                  <ul className="rrhh-cambio-campos">
                    {c.trazas.slice(0, MAX_TRAZAS).map((t) => <Traza key={t.id} t={t} />)}
                    {c.trazas.length > MAX_TRAZAS && <li className="tenue">y {c.trazas.length - MAX_TRAZAS} más</li>}
                  </ul>
                </details>
              </li>
            ))}
          </ul>
        ))}
    </details>
  );
}
