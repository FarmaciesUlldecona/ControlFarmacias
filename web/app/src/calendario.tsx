// TA2 Trabajadores: calendario. Vistas semana / mes / año / por persona; paleta de tipos (también leyenda, colores
// configurables en este navegador); pintar con clic, selección múltiple o arrastrando; goma; rellenar jornada
// habitual; confirmar; deshacer el último cambio; historial de cada cambio. Solo datos de ejemplo en memoria del
// servidor (modo FIXTURES). En modo REAL: "Módulo pendiente de conexión (T1)" (marco Modulo).
// TA2-2: mañana y tarde por separado (en la semana, dos subfilas por persona; en mes y por persona, un clic es el día
// completo: sus franjas); rellenar el año completo; nota opcional por evento (sin datos de salud); historial plegado.
// TA2-4: mensajes en días laborables × personas; «Añadir nota» en la barra de selección (una franja: su editor; varias:
// la misma nota, omitiendo vacías y confirmadas); campo Nota siempre visible en el detalle del día.
import { useEffect, useRef, useState, type CSSProperties, type PointerEvent as EventoPuntero, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  CATEGORIAS, TEXTO_CATEGORIA, TEXTO_JORNADA, filtroFarmacia, type FarmaciaRrhh, type Trabajadora,
} from '../server/rrhh/contrato.ts';
import {
  AVISO_NOTA, AVISO_NOTA_VACIA, CODIGO_TIPO_EVENTO, COLOR_TIPO_EVENTO, FECHA_MAX, FECHA_MIN, FRANJAS, FRANJAS_DE_JORNADA, LARGO_NOTA, TEXTO_ESTADO_EVENTO, TEXTO_FRANJA,
  TEXTO_TIPO_EVENTO, TIPOS_EVENTO, describirCambio, diaSemana, esFecha, lunesDe, primeroDeMes, rangoFechas, sumarDias, sumarMeses, ultimoDeMes,
  type CalendarioDTO, type CambioCalendario, type Celda, type EventoCalendario, type Franja, type ResultadoCambioDTO, type TipoEvento, type TrazaEvento,
} from '../server/rrhh/eventos.ts';
import { ErrorApi, enviar, useApiRecargable } from './api.ts';
import { fechaHora } from './formato.ts';
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
  : `${TEXTO_TIPO_EVENTO[e.tipo]} ${horasTxt(e.horas)}${e.estado === 'CONFIRMADO' ? ' (confirmado)' : ''}${e.nota ? ` · nota: «${e.nota}»` : ''}`);
const descripcionEvento = (e: EventoCalendario, conFranja = true) =>
  `${conFranja ? `${TEXTO_FRANJA[e.franja]}: ` : ''}${TEXTO_TIPO_EVENTO[e.tipo]}, ${horasTxt(e.horas)}, ${TEXTO_ESTADO_EVENTO[e.estado]}${e.nota ? `. Nota: ${e.nota}` : ''}`;

// ---------------------------------------------------------------------------
// Colores (configurables en la leyenda; solo en este navegador)
// ---------------------------------------------------------------------------

type Colores = Record<TipoEvento, string>;
const CLAVE_COLORES = 'cf.rrhh.calendario.colores.v1';
const HEX = /^#[0-9a-f]{6}$/i;

function leerColores(): Colores {
  const c: Colores = { ...COLOR_TIPO_EVENTO };
  try {
    const g = JSON.parse(localStorage.getItem(CLAVE_COLORES) ?? '{}') as Record<string, unknown>;
    for (const t of TIPOS_EVENTO) if (typeof g[t] === 'string' && HEX.test(g[t] as string)) c[t] = g[t] as string;
  } catch { /* sin almacenamiento: colores por defecto */ }
  return c;
}
function useColores(): [Colores, (t: TipoEvento | null, color?: string) => void] {
  const [c, setC] = useState<Colores>(leerColores);
  const cambiar = (t: TipoEvento | null, color?: string) => setC((p) => {
    const n = t === null ? { ...COLOR_TIPO_EVENTO } : { ...p, [t]: color ?? p[t] };
    try { localStorage.setItem(CLAVE_COLORES, JSON.stringify(n)); } catch { /* sin almacenamiento */ }
    return n;
  });
  return [c, cambiar];
}
const lineal = (v: number) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
const luminancia = (hex: string) => {
  const [r, g, b] = [1, 3, 5].map((i) => lineal(parseInt(hex.slice(i, i + 2), 16) / 255));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const OSCURO = '#18211e';
/** Texto blanco u oscuro sobre el color, el de más contraste. */
function textoSobre(hex: string): string {
  const l = luminancia(hex);
  return 1.05 / (l + 0.05) >= (l + 0.05) / (luminancia(OSCURO) + 0.05) ? '#ffffff' : OSCURO;
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

type Herramienta = { k: 'seleccion' } | { k: 'goma' } | { k: 'tipo'; tipo: TipoEvento };
type Aviso = { ok: boolean; texto: string } | null;

const ERRORES: Readonly<Record<string, string>> = {
  TRABAJADORA_NO_VALIDA: 'Alguna persona ya no está activa: no se ha cambiado nada.',
  FRANJA_NO_VALIDA: 'Esa persona no trabaja en esa franja: no se ha cambiado nada.',
  EVENTO_NO_ENCONTRADO: 'Esa franja ya no tiene evento: no se ha cambiado nada.',
  EVENTO_CONFIRMADO: 'Esa franja está confirmada: quita antes la confirmación para cambiar sus horas o su nota.',
  NADA_QUE_DESHACER: 'No queda ningún cambio por deshacer.',
  NO_ES_EL_ULTIMO: 'Hay un cambio más reciente: recarga y vuelve a deshacer.',
  ESTADO_CAMBIADO: 'Los días de ese cambio ya no están como los dejó: no se ha deshecho nada.',
  DATOS_NO_VALIDOS: 'Datos no válidos: no se ha cambiado nada.',
};
function textoError(e: unknown): string {
  if (!(e instanceof ErrorApi)) return 'No se ha podido guardar.';
  if (e.codigo === 'DATOS_NO_VALIDOS' && e.errores.nota) return `${e.errores.nota}: no se ha cambiado nada.`;
  return ERRORES[e.codigo] ?? `No se ha podido guardar (${e.codigo}).`;
}
function textoResultado(r: ResultadoCambioDTO): Aviso {
  const o = r.omitidas_confirmadas;
  const v = r.omitidas_vacias;
  const omitidas = (o > 0 ? ` ${o} ${o === 1 ? 'franja confirmada no se ha tocado' : 'franjas confirmadas no se han tocado'} (quita antes la confirmación).` : '')
    + (v > 0 ? ` ${v} ${v === 1 ? 'franja vacía no se ha anotado' : 'franjas vacías no se han anotado'}: ${AVISO_NOTA_VACIA.charAt(0).toLowerCase()}${AVISO_NOTA_VACIA.slice(1)}.` : '');
  if (r.cambio === null) {
    if (v > 0 && o === 0) return { ok: false, texto: `${AVISO_NOTA_VACIA}.` };
    return { ok: o === 0 && v === 0, texto: `Sin cambios: esos días ya estaban así.${omitidas}` };
  }
  return { ok: true, texto: `${describirCambio(r.cambio)}.${omitidas}` };
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
  const [herr, setHerr] = useState<Herramienta>({ k: 'seleccion' });
  const [sel, setSel] = useState<Set<string>>(() => new Set());
  const [aviso, setAviso] = useState<Aviso>(null);
  const [confirmarAnio, setConfirmarAnio] = useState(false);
  const [colores, cambiarColor] = useColores();
  const cola = useRef<Promise<void>>(Promise.resolve());
  const datos = cal.carga.estado === 'ok' ? cal.carga.datos : null;

  useEffect(() => { setSel(new Set()); setConfirmarAnio(false); }, [farmacia, vista, desde, persona]);

  const cambiar = (x: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(x)) { if (v === null || v === '') p.delete(k); else p.set(k, v); }
    setParams(p, { replace: true });
  };

  /** Las escrituras van en cola: ningún trazo se pierde ni se cruza con otro. */
  const ejecutar = (tarea: () => Promise<void>) => { cola.current = cola.current.then(tarea).catch(() => undefined); };
  const recargar = () => { cal.recargar(); hist.recargar(); };
  const escribir = (ruta: string, cuerpo: object) => ejecutar(async () => {
    try { setAviso(textoResultado(await enviar<ResultadoCambioDTO>(ruta, 'POST', cuerpo))); } catch (e) { setAviso({ ok: false, texto: textoError(e) }); }
    recargar();
  });
  const cambioEventos = (cuerpo: object) => escribir('/api/rrhh/eventos', cuerpo);
  const ultimo = datos?.ultimo_cambio ?? null;
  const deshacer = () => { if (ultimo) escribir('/api/rrhh/eventos/deshacer', { cambio_id: ultimo.id }); };

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
  const rellenarAnio = () => { setConfirmarAnio(false); cambioEventos({ accion: 'RELLENAR', trabajadora_ids: idsAnio, desde: dq, hasta: hq }); };

  return (
    <div className="cal" data-calendario data-vista={vista}>
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

      {vista !== 'anio' && <Paleta herr={herr} onHerr={setHerr} colores={colores} onColor={cambiarColor} semana={vista === 'semana'} />}

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
        <button type="button" className="boton-secundario cal-deshacer" disabled={!ultimo} onClick={deshacer} data-accion="deshacer"
          title={ultimo ? `Deshacer: ${describirCambio(ultimo)} (Ctrl+Z)` : 'No hay cambios que deshacer'}>
          Deshacer{ultimo && <span className="cal-deshacer-que" data-deshacer-que>{describirCambio(ultimo)}</span>}
        </button>
      </div>

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
          <div className="rrhh-botones">
            <button type="button" className="boton-primario" onClick={rellenarAnio} data-confirmar-anio-si>Sí, rellenar {anioSel}</button>
            <button type="button" className="boton-secundario" onClick={() => setConfirmarAnio(false)}>Cancelar</button>
          </div>
        </div>
      )}

      {aviso && <p className={aviso.ok ? 'rrhh-aviso-ok' : 'rrhh-error'} role={aviso.ok ? 'status' : 'alert'} data-aviso-calendario>{aviso.texto}</p>}

      {cal.carga.estado === 'cargando' && <p className="tenue">Cargando calendario…</p>}
      {cal.carga.estado === 'error' && <p className="rrhh-error" role="alert">No se ha podido leer el calendario ({cal.carga.mensaje}).</p>}
      {datos && visibles.length === 0 && vista !== 'persona' && (
        <p className="tarjeta rrhh-vacio" data-calendario-vacio>Ninguna persona con estos filtros. Cambia la persona o la categoría.</p>
      )}

      {datos && visibles.length > 0 && rango && (
        <RejillaPeriodo vista={vista} desde={desde} hasta={hasta} hoyF={hoyF} trabajadoras={visibles} agrupar={farmacia === 'AMBAS'}
          eventos={eventos} sel={sel} herr={herr} colores={colores} tipoFiltro={tipoFiltro} onAplicar={aplicar} />
      )}
      {datos && vista === 'anio' && visibles.length > 0 && (
        <VistaAnio anio={anioSel} hoyF={hoyF} trabajadoras={visibles} eventos={eventos} colores={colores} tipoFiltro={tipoFiltro}
          onDia={(f) => cambiar({ vista: null, fecha: f })} />
      )}
      {datos && vista === 'persona' && (elegida
        ? <VistaPersona t={elegida} anio={anioSel} hoyF={hoyF} eventos={eventos} sel={sel} herr={herr} colores={colores}
            tipoFiltro={tipoFiltro} onAplicar={aplicar} />
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

function Paleta({ herr, onHerr, colores, onColor, semana }: {
  herr: Herramienta; onHerr: (h: Herramienta) => void; colores: Colores; onColor: (t: TipoEvento | null, c?: string) => void; semana: boolean;
}) {
  const [editar, setEditar] = useState(false);
  const activa = (h: Herramienta) => (h.k === herr.k && (h.k !== 'tipo' || (herr.k === 'tipo' && herr.tipo === h.tipo)));
  const accion = herr.k === 'seleccion' ? 'seleccionar' : herr.k === 'goma' ? 'borrar' : 'pintar';
  return (
    <section className="cal-paleta-marco" aria-label="Paleta y leyenda">
      <div className="cal-paleta" role="toolbar" aria-label="Herramienta">
        <button type="button" className="cal-herr cal-herr-sel" aria-pressed={activa({ k: 'seleccion' })} data-herramienta="seleccion"
          onClick={() => onHerr({ k: 'seleccion' })}><span className="cal-muestra-sel" aria-hidden="true" />Seleccionar</button>
        {TIPOS_EVENTO.map((t) => (
          <button key={t} type="button" className="cal-herr" aria-pressed={activa({ k: 'tipo', tipo: t })} data-herramienta={t} style={estiloColor(colores[t])}
            onClick={() => onHerr({ k: 'tipo', tipo: t })}>
            <span className="cal-muestra" aria-hidden="true">{CODIGO_TIPO_EVENTO[t]}</span>{TEXTO_TIPO_EVENTO[t]}
          </button>
        ))}
        <button type="button" className="cal-herr cal-herr-goma" aria-pressed={activa({ k: 'goma' })} data-herramienta="goma"
          onClick={() => onHerr({ k: 'goma' })}><span className="cal-muestra-goma" aria-hidden="true" />Goma</button>
      </div>
      <div className="cal-leyenda">
        <span className="cal-leyenda-estado"><span className="cal-mini e-planificado" aria-hidden="true" /> claro: planificado</span>
        <span className="cal-leyenda-estado"><span className="cal-mini e-confirmado" aria-hidden="true">✓</span> sólido: confirmado</span>
        <span className="cal-leyenda-estado"><span className="cal-nota-marca" aria-hidden="true">✎</span> con nota</span>
        <span className="tenue" data-ayuda-franjas>
          {semana
            ? `Arriba mañana (M), abajo tarde (T): clic en una franja o arrastre sobre las dos para ${accion} el día.`
            : `Arriba mañana, abajo tarde: un clic ${accion === 'seleccionar' ? 'selecciona' : accion === 'borrar' ? 'borra' : 'pinta'} el día completo (sus franjas).`}
        </span>
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
          <button type="button" className="boton-secundario" onClick={() => onColor(null)} data-restablecer-colores>Restablecer colores</button>
          <p className="tenue">Los colores se guardan solo en este navegador.</p>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Rejilla pintable (semana, mes y por persona)
// ---------------------------------------------------------------------------

interface Columna { clave: string; cabecera: ReactNode; titulo?: string; finde?: boolean; hoy?: boolean }
/**
 * Fila de la rejilla. Semana: una subfila por franja (cabecera de persona con rowSpan 2 en la de mañana); celda null
 * = franja que la persona no trabaja. Mes y por persona: una fila por persona o mes; celda null = día inexistente.
 */
interface Fila {
  clave: string; grupo?: FarmaciaRrhh; cabecera?: ReactNode; span?: number; titulo?: string; franja?: Franja;
  celdas: (Celda | null)[]; nombre?: string;
}
type Punto = [number, number];

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
      {!compacto && <span className="cal-ev-horas">{horasTxt(ev.horas)}</span>}
      {!compacto && ev.estado === 'CONFIRMADO' && <span className="cal-ev-ok" aria-hidden="true">✓</span>}
      {ev.nota && <span className="cal-ev-nota" aria-hidden="true" data-con-nota>✎</span>}
    </span>
  );
}

function Rejilla({ variante, columnas, filas, nombres, eventos, sel, herr, colores, tipoFiltro, hoyF, onAplicar, pie }: {
  variante: 'semana' | 'mes' | 'persona'; columnas: Columna[]; filas: Fila[]; nombres: Map<string, string>;
  eventos: Map<string, EventoCalendario>; sel: Set<string>; herr: Herramienta; colores: Colores; tipoFiltro: TipoEvento | '';
  hoyF: string; onAplicar: (c: Celda[]) => void; pie?: { titulo: string; valores: (number | null)[] };
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
  const columna = (j: number) => onAplicar(filas.flatMap((f) => (f.celdas[j] ? [f.celdas[j] as Celda] : [])));

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
            {columnas.map((c, j) => (
              <th key={c.clave} scope="col" className={`cal-col${c.finde ? ' finde' : ''}${c.hoy ? ' hoy' : ''}`} title={c.titulo} data-columna={c.clave}>
                {variante === 'persona' ? c.cabecera : (
                  <button type="button" className="cal-col-boton" onClick={() => columna(j)} aria-label={`${c.titulo}: aplicar a todas las personas`}>{c.cabecera}</button>
                )}
              </th>
            ))}
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
                if (!c) {
                  return f.franja
                    ? <td key={j} className={`cal-sin-franja${diaSemana(fechaCol) >= 5 ? ' finde' : ''}${fechaCol === hoyF ? ' hoy' : ''}`}
                        title={`${f.nombre ?? ''} no trabaja de ${TEXTO_FRANJA[f.franja]}`} aria-hidden="true" />
                    : <td key={j} className="cal-vacia" aria-hidden="true" />;
                }
                const k = clave(c);
                const evs = eventosDe(eventos, c);
                const finde = diaSemana(c.fecha) >= 5;
                const etiqueta = `${nombres.get(c.trabajadora_id) ?? ''}, ${F_LARGA.format(dia(c.fecha))}${c.franja ? `, ${TEXTO_FRANJA[c.franja]}` : ''}: ${evs.length
                  ? evs.map((e) => descripcionEvento(e, !c.franja)).join('; ') : 'libre'}`;
                const manana = eventos.get(claveEv(c.trabajadora_id, c.fecha, 'MANANA'));
                const tarde = eventos.get(claveEv(c.trabajadora_id, c.fecha, 'TARDE'));
                const unico = c.franja ? evs[0] ?? null : null;
                return (
                  <td key={k} className={`${finde ? 'finde' : ''}${c.fecha === hoyF ? ' hoy' : ''}`}>
                    <button type="button" className={`cal-celda${c.franja ? ' de-franja' : ' de-dia'}${sel.has(k) ? ' sel' : ''}${enTrazo?.has(k) ? ' trazo' : ''}`}
                      data-celda={k}
                      {...(c.franja
                        ? { 'data-tipo': unico?.tipo ?? '', 'data-estado': unico?.estado ?? '', 'data-horas': unico?.horas ?? '', 'data-nota': unico?.nota ?? '' }
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
          {TEXTO_JORNADA[t.jornada]} · {horasTxt(t.horas_diarias)}{t.es_titular ? ' · titular' : ''}
        </span>
      )}
    </span>
  );
}

/** Personas que trabajan (alguna franja de JORNADA) ese día. */
const trabajanEl = (trabajadoras: Trabajadora[], eventos: Map<string, EventoCalendario>, f: string) =>
  trabajadoras.filter((t) => FRANJAS.some((fr) => eventos.get(claveEv(t.id, f, fr))?.tipo === 'JORNADA')).length;

function RejillaPeriodo({ vista, desde, hasta, hoyF, trabajadoras, agrupar, eventos, sel, herr, colores, tipoFiltro, onAplicar }: {
  vista: Vista; desde: string; hasta: string; hoyF: string; trabajadoras: Trabajadora[]; agrupar: boolean;
  eventos: Map<string, EventoCalendario>; sel: Set<string>; herr: Herramienta; colores: Colores; tipoFiltro: TipoEvento | ''; onAplicar: (c: Celda[]) => void;
}) {
  const dias = rangoFechas(desde, hasta);
  const semana = vista === 'semana';
  const columnas: Columna[] = dias.map((f) => ({
    clave: f, titulo: mayuscula(F_LARGA.format(dia(f))), finde: diaSemana(f) >= 5, hoy: f === hoyF,
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
      // Dos subfilas por persona: mañana y tarde (la franja que no trabaja queda rayada).
      const propias = FRANJAS_DE_JORNADA[t.jornada];
      for (const franja of FRANJAS) {
        filas.push({
          clave: `${t.id}|${franja}`, franja, nombre: t.nombre, titulo: t.nombre,
          ...(franja === 'MANANA' ? { cabecera: <CabeceraPersona t={t} compacto={false} />, span: 2 } : {}),
          celdas: dias.map((f) => (dentro(f) && propias.includes(franja) ? { trabajadora_id: t.id, fecha: f, franja } : null)),
        });
      }
    } else {
      filas.push({
        clave: t.id, titulo: t.nombre, nombre: t.nombre, cabecera: <CabeceraPersona t={t} compacto />,
        celdas: dias.map((f) => (dentro(f) ? { trabajadora_id: t.id, fecha: f } : null)),
      });
    }
  }
  return (
    <Rejilla variante={semana ? 'semana' : 'mes'} columnas={columnas} filas={filas} nombres={new Map(trabajadoras.map((t) => [t.id, t.nombre]))}
      eventos={eventos} sel={sel} herr={herr} colores={colores} tipoFiltro={tipoFiltro} hoyF={hoyF} onAplicar={onAplicar}
      pie={{ titulo: 'Trabajan', valores: dias.map((f) => trabajanEl(trabajadoras, eventos, f)) }} />
  );
}

// ---------------------------------------------------------------------------
// Vista por persona: el año de una persona (12 meses × 31 días), pintable por día completo
// ---------------------------------------------------------------------------

function VistaPersona({ t, anio, hoyF, eventos, sel, herr, colores, tipoFiltro, onAplicar }: {
  t: Trabajadora; anio: string; hoyF: string; eventos: Map<string, EventoCalendario>; sel: Set<string>; herr: Herramienta; colores: Colores;
  tipoFiltro: TipoEvento | ''; onAplicar: (c: Celda[]) => void;
}) {
  const columnas: Columna[] = Array.from({ length: 31 }, (_, i) => ({ clave: String(i + 1), cabecera: i + 1 }));
  const filas: Fila[] = Array.from({ length: 12 }, (_, m) => {
    const primero = `${anio}-${String(m + 1).padStart(2, '0')}-01`;
    const ultimo = Number(ultimoDeMes(primero).slice(8));
    const mes = mayuscula(F_MES_SOLO.format(dia(primero)));
    return {
      clave: primero.slice(0, 7), titulo: mes, cabecera: <span className="cal-mes-nombre">{mes}</span>,
      celdas: columnas.map((_, d) => (d < ultimo ? { trabajadora_id: t.id, fecha: `${primero.slice(0, 8)}${String(d + 1).padStart(2, '0')}` } : null)),
    };
  });
  const delAnio = [...eventos.values()].filter((e) => e.trabajadora_id === t.id && e.fecha.startsWith(anio));
  return (
    <section className="cal-persona-vista" data-vista-persona={t.id}>
      <div className="cal-persona-cabecera">
        <h3><Link to={`/trabajadores/${t.id}`} className="rrhh-nombre">{t.nombre}</Link></h3>
        <EtiquetaFarmacia f={t.farmacia} />
        <span className="tenue">{TEXTO_CATEGORIA[t.categoria]} · {TEXTO_JORNADA[t.jornada]} · {horasTxt(t.horas_diarias)}/día</span>
      </div>
      <dl className="cal-totales" aria-label={`Días por tipo en ${anio}`}>
        {TIPOS_EVENTO.map((tipo) => {
          const n = new Set(delAnio.filter((e) => e.tipo === tipo).map((e) => e.fecha)).size;
          return (
            <div key={tipo} className="cal-total" data-total-tipo={tipo} style={estiloColor(colores[tipo])}>
              <dt><span className="cal-muestra" aria-hidden="true">{CODIGO_TIPO_EVENTO[tipo]}</span>{TEXTO_TIPO_EVENTO[tipo]}</dt>
              <dd>{n} {n === 1 ? 'día' : 'días'}</dd>
            </div>
          );
        })}
      </dl>
      <Rejilla variante="persona" columnas={columnas} filas={filas} nombres={new Map([[t.id, t.nombre]])} eventos={eventos} sel={sel} herr={herr}
        colores={colores} tipoFiltro={tipoFiltro} hoyF={hoyF} onAplicar={onAplicar} />
    </section>
  );
}

// ---------------------------------------------------------------------------
// Vista año: resumen por día (quién falta y cuántos trabajan)
// ---------------------------------------------------------------------------

function VistaAnio({ anio, hoyF, trabajadoras, eventos, colores, tipoFiltro, onDia }: {
  anio: string; hoyF: string; trabajadoras: Trabajadora[]; eventos: Map<string, EventoCalendario>; colores: Colores;
  tipoFiltro: TipoEvento | ''; onDia: (f: string) => void;
}) {
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
        return (
          <section key={primero} className="tarjeta cal-mes" data-mes={primero.slice(0, 7)}>
            <h3>{mayuscula(F_MES_SOLO.format(dia(primero)))} <span className="tenue">{total > 0 ? `${total} ${total === 1 ? 'ausencia' : 'ausencias'}` : ''}</span></h3>
            <div className="cal-mes-rejilla">
              {INICIALES.map((x) => <span key={x} className="cal-mes-dsem" aria-hidden="true">{x}</span>)}
              {Array.from({ length: diaSemana(primero) }, (_, i) => <span key={`h${i}`} aria-hidden="true" />)}
              {dias.map((f) => {
                const faltan = ausencias(f);
                const personas = new Set(faltan.map((e) => e.trabajadora_id)).size;
                const trabajan = new Set((porDia.get(f) ?? []).filter((e) => e.tipo === 'JORNADA').map((e) => e.trabajadora_id)).size;
                const titulo = `${mayuscula(F_LARGA.format(dia(f)))}: ${trabajan} trabajan${faltan.length
                  ? ` · ${faltan.map((e) => `${TEXTO_TIPO_EVENTO[e.tipo]}: ${nombre.get(e.trabajadora_id)}`).join('; ')}` : ''}`;
                return (
                  <button key={f} type="button" className={`cal-dia${diaSemana(f) >= 5 ? ' finde' : ''}${f === hoyF ? ' hoy' : ''}${trabajan ? ' con-jornada' : ''}`}
                    data-dia={f} data-ausencias={personas} data-trabajan={trabajan} title={titulo} aria-label={`${titulo}. Abrir la semana`}
                    onClick={() => onDia(f)}>
                    <span className="cal-dia-num">{Number(f.slice(8))}</span>
                    {faltan.length > 0 && (
                      <span className="cal-dia-marcas" aria-hidden="true">
                        {faltan.slice(0, 3).map((e) => <span key={e.id} className="cal-dia-marca" style={estiloColor(colores[e.tipo])} />)}
                        {faltan.length > 3 && <span className="cal-dia-mas">+{faltan.length - 3}</span>}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
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
  const [horas, setHoras] = useState(NUM.format(ev.horas));
  const [nota, setNota] = useState(ev.nota ?? '');
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setHoras(NUM.format(ev.horas)); setNota(ev.nota ?? ''); setError(null); }, [ev.id, ev.horas, ev.nota]);
  const bloqueado = ev.estado === 'CONFIRMADO';
  const guardar = () => {
    const h = Number(horas.trim().replace(',', '.'));
    if (!Number.isFinite(h) || h <= 0 || h > 12) { setError('Horas: más de 0 y como máximo 12'); return; }
    setError(null);
    onCambio({ accion: 'EDITAR', evento_id: ev.id, horas: h, nota: nota.trim() === '' ? null : nota });
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
  const franjasDe = (c: Celda): readonly Franja[] => (c.franja ? [c.franja] : FRANJAS_DE_JORNADA[fichas.get(c.trabajadora_id)?.jornada ?? 'COMPLETA']);
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
            {TIPOS_EVENTO.map((t) => <option key={t} value={t}>{TEXTO_TIPO_EVENTO[t]}</option>)}
          </select>
          <button type="button" className="boton-secundario" onClick={() => onCambio({ accion: 'PINTAR', tipo, celdas })} data-sel="pintar">Pintar</button>
        </span>
        <button type="button" className="boton-secundario" aria-expanded={anotar} onClick={pulsarAnotar} data-sel="anotar">
          <span className="cal-nota-marca" aria-hidden="true">✎</span> Añadir nota
        </button>
        <button type="button" className="boton-primario" onClick={() => onCambio({ accion: 'CONFIRMAR', celdas })} data-sel="confirmar">Confirmar</button>
        <button type="button" className="boton-secundario" onClick={() => onCambio({ accion: 'DESCONFIRMAR', celdas })} data-sel="desconfirmar">Quitar confirmación</button>
        <button type="button" className="boton-peligro-suave" onClick={() => onCambio({ accion: 'BORRAR', celdas })} data-sel="borrar">Borrar</button>
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
                  <span>{mayuscula(TEXTO_FRANJA[ev.franja])}: {TEXTO_TIPO_EVENTO[ev.tipo]} · {horasTxt(ev.horas)} · {TEXTO_ESTADO_EVENTO[ev.estado]}</span>
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
