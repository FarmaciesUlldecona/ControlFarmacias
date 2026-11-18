// H6-4: calendario de vencimientos sobre la lista. Vistas Día / Semana / Mes (por defecto) / Año.
// Cada día con pagos: total (cargos − abonos, misma regla de totales de H6) y globo con el nº de pagos; color = peor
// estado. Cursor encima o foco de teclado: desplegable con cada pago y la suma; en pantalla táctil, un toque abre el
// detalle con «Filtrar la lista a este día». Clic en un día, una semana o un mes: filtra la lista inferior.
// H6-5: un día con pagos se marca siempre (color del peor estado y globo), aunque ninguno sume; sin total, la celda dice
// por qué («importe pendiente»…). Bajo el título del periodo, su resumen (Total = Pagado + Domiciliado previsto + Falta
// por pagar − Abonos por compensar) y, si el periodo visible está vacío, aviso con saltos a las fechas con pagos.
// Reutiliza la barra del calendario de Trabajadores (cal-vistas, cal-navegar, cal-periodo); la rejilla es propia
// (importes por día, no personas por franja).
import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent as EventoPuntero } from 'react';
import {
  COLOR_DIA, LEYENDA_COLOR, VISTAS_CALENDARIO, agrupar, agregar, claveDe, moverVista, periodoVista, rejillaMes, resumenAnio, resumenPeriodo,
  resumir, semanaIso, sinFecha, textoSinTotal, vecinosConPagos,
  type FiltroCalendario, type GrupoResumenPeriodo, type MesDelAnio, type ResumenCalendario, type ResumenPeriodo, type VistaCalendario,
} from '../server/pagos/calendario.ts';
import {
  DICCIONARIO_ESTADOS, TEXTO_CARGO_NEGATIVO, sumarDiasIso, textoEstadoPago, type ColorEstadoPago, type FilaVencimientoPago,
} from '../server/pagos/pagos.ts';
import { euros, plural } from './formato.ts';

// ---------------------------------------------------------------------------
// Textos
// ---------------------------------------------------------------------------

const fmt = (o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('es-ES', { timeZone: 'UTC', ...o });
const F_LARGA = fmt({ weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
const F_DIA_MES = fmt({ day: 'numeric', month: 'short' });
const F_MES = fmt({ month: 'long', year: 'numeric' });
const F_MES_SOLO = fmt({ month: 'long' });
const F_DSEM = fmt({ weekday: 'short' });
const aFecha = (f: string) => new Date(`${f}T00:00:00Z`);
const mayuscula = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const INICIALES = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
const NOMBRES_DIA = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];

export const textoDia = (f: string) => mayuscula(F_LARGA.format(aFecha(f)));
export const textoMes = (ym: string) => mayuscula(F_MES.format(aFecha(`${ym}-01`)));
export function textoSemana(desde: string, hasta: string): string {
  const [d1, d2] = [Number(desde.slice(8)), Number(hasta.slice(8))];
  if (desde.slice(0, 7) === hasta.slice(0, 7)) return `${d1}–${d2} ${F_DIA_MES.format(aFecha(hasta)).replace(/^\d+\s/, '')} ${hasta.slice(0, 4)}`;
  if (desde.slice(0, 4) === hasta.slice(0, 4)) return `${F_DIA_MES.format(aFecha(desde))} – ${F_DIA_MES.format(aFecha(hasta))} ${hasta.slice(0, 4)}`;
  return `${F_DIA_MES.format(aFecha(desde))} ${desde.slice(0, 4)} – ${F_DIA_MES.format(aFecha(hasta))} ${hasta.slice(0, 4)}`;
}
/** Texto del filtro de calendario activo («martes, 4 de noviembre de 2026», «semana 2–8 nov 2026», «noviembre de 2026»). */
export function textoFiltroCalendario(f: FiltroCalendario): string {
  if (f.escala === 'dia') return textoDia(f.clave);
  if (f.escala === 'semana') return `Semana ${semanaIso(f.desde)} · ${textoSemana(f.desde, f.hasta)}`;
  return textoMes(f.clave);
}
function textoPeriodoVista(vista: VistaCalendario, desde: string, hasta: string): string {
  if (vista === 'dia') return textoDia(desde);
  if (vista === 'semana') return textoSemana(desde, hasta);
  if (vista === 'mes') return textoMes(desde.slice(0, 7));
  return desde.slice(0, 4);
}

/**
 * Importe corto para celdas estrechas (móvil, PC estrecho): «305€», «2,5k€», «1M€». El importe exacto está siempre en
 * la etiqueta accesible y en el desplegable. Nunca se usa para null.
 */
export function eurosCorto(v: number): string {
  const s = v < 0 ? '-' : '';
  const a = Math.abs(v);
  const n = (x: number, dec: number) => new Intl.NumberFormat('es-ES', { maximumFractionDigits: dec, useGrouping: false }).format(x);
  if (Math.round(a) < 1000) return `${s}${n(a, 0)}€`;
  if (a < 999_500) return `${s}${n(a / 1000, a < 99_950 ? 1 : 0)}k€`;
  return `${s}${n(a / 1_000_000, 1)}M€`;
}

const CLASE_ESTADO: Record<ColorEstadoPago, string> = { azul: 'b', rojo: 'r', verde: 'g', gris: 'n', domiciliado: 'd', naranja: 'o' };
const nombreProveedor = (f: FilaVencimientoPago) => f.proveedor_comercial ?? f.proveedor_razon_social ?? f.proveedor ?? 'Proveedor sin identificar';

function notasFuera(r: ResumenCalendario): string[] {
  return [
    r.sin_importe ? plural(r.sin_importe, 'importe pendiente', 'importes pendientes') : null,
    r.sentido_no_documentado ? `${r.sentido_no_documentado} de sentido no documentado` : null,
    r.cargo_negativo ? plural(r.cargo_negativo, 'cargo con importe negativo', 'cargos con importe negativo') : null,
  ].filter((x): x is string => x !== null);
}
/** Etiqueta accesible de un periodo: pagos, total exacto, lo que queda fuera y el peor estado. */
function etiquetaResumen(titulo: string, r: ResumenCalendario | undefined): string {
  if (!r || r.pagos === 0) return `${titulo}: sin pagos`;
  const fuera = notasFuera(r);
  return `${titulo}: ${plural(r.pagos, 'pago', 'pagos')}, total ${euros(r.total.neto) ?? `sin importe que sume (${textoSinTotal(r)?.largo ?? 'nada suma'})`}`
    + `${fuera.length ? ` (fuera del total: ${fuera.join(', ')})` : ''}`
    + `${r.peor ? `; peor estado: ${DICCIONARIO_ESTADOS[r.peor].texto.toLowerCase()}` : ''}`;
}

// ---------------------------------------------------------------------------
// Piezas
// ---------------------------------------------------------------------------

/**
 * Total de un periodo: completo si cabe; en celdas estrechas, corto (container query). H6-5: si nada suma, dice por
 * qué («importe pendiente», «importe negativo», «sentido no documentado»), nunca «—» ni 0.
 */
function ImporteCelda({ r }: { r: ResumenCalendario }) {
  if (r.total.neto === null) {
    const s = textoSinTotal(r);
    return (
      <span className="vc-importe vc-importe-nulo" data-importe-dia="" data-sin-total={s?.largo ?? ''}>
        <span className="vc-importe-largo">{s?.largo ?? '—'}</span>
        <span className="vc-importe-corto" aria-hidden="true">{s?.corto ?? '—'}</span>
      </span>
    );
  }
  const t = euros(r.total.neto) as string;
  return (
    <span className="vc-importe" data-importe-dia={t}>
      <span className="vc-importe-largo">{t}</span>
      <span className="vc-importe-corto" aria-hidden="true">{eurosCorto(r.total.neto)}</span>
    </span>
  );
}

function Globo({ n }: { n: number }) {
  return <span className="vc-globo" data-globo={n} aria-hidden="true">{n}</span>;
}

/** Lista de pagos de un día (desplegable, hoja táctil y vista Día) con la suma final. */
function DetallePagos({ filas, r, max }: { filas: FilaVencimientoPago[]; r: ResumenCalendario; max?: number }) {
  const vistos = max === undefined ? filas : filas.slice(0, max);
  const fuera = notasFuera(r);
  return (
    <>
      <ul className="vc-pagos">
        {vistos.map((f) => {
          const d = DICCIONARIO_ESTADOS[f.estado_pago];
          const imp = euros(f.importe);
          return (
            <li key={f.vencimiento_id} className="vc-pago" data-pago={f.vencimiento_id}>
              <span className="vc-pago-proveedor" title={nombreProveedor(f)}>{nombreProveedor(f)}</span>
              <span className="vc-pago-importe">
                {imp === null ? <span className="desconocido">importe pendiente</span> : imp}
                {f.cargo_negativo && <span className="vc-pago-aviso">{TEXTO_CARGO_NEGATIVO}</span>}
                {f.sentido === 'NO_DOCUMENTADO' && imp !== null && <span className="vc-pago-aviso">sentido no documentado</span>}
              </span>
              <span className={`insignia ${CLASE_ESTADO[d.color]} vc-pago-estado`} data-estado-pago={f.estado_pago}>{textoEstadoPago(f.estado_pago, f.sentido)}</span>
            </li>
          );
        })}
      </ul>
      {vistos.length < filas.length && <p className="vc-mas tenue">y {plural(filas.length - vistos.length, 'pago más', 'pagos más')}</p>}
      <p className="vc-suma" data-suma-dia>
        <span>Total</span>
        <strong>{euros(r.total.neto) ?? <span className="desconocido" data-suma-sin-total>{textoSinTotal(r)?.largo ?? 'sin importe que sume'}</span>}</strong>
      </p>
      {fuera.length > 0 && <p className="vc-fuera" data-fuera-total>Fuera del total: {fuera.join(' · ')}</p>}
    </>
  );
}

// ---------------------------------------------------------------------------
// Día (celda del mes y cabecera de la semana): botón que filtra + desplegable
// ---------------------------------------------------------------------------

type Apertura = { fecha: string; modo: 'raton' | 'foco' | 'toque' } | null;

interface PropsDia {
  fecha: string;
  r: ResumenCalendario | undefined;
  filas: FilaVencimientoPago[];
  hoy: string;
  fuera?: boolean;
  elegido: boolean;
  enfocable: boolean;
  lado: 'izq' | 'centro' | 'der';
  variante: 'mes' | 'semana';
  apertura: Apertura;
  onAbrir: (a: Apertura) => void;
  onFiltrar: () => void;
  onTecla?: (e: KeyboardEvent<HTMLButtonElement>) => void;
  onFoco?: () => void;
}

function Dia({ fecha, r, filas, hoy, fuera, elegido, enfocable, lado, variante, apertura, onAbrir, onFiltrar, onTecla, onFoco }: PropsDia) {
  const toque = useRef(false);
  const abierto = apertura?.fecha === fecha && apertura.modo !== 'toque' && !!r;
  const id = `vc-desplegable-${fecha}`;
  const num = Number(fecha.slice(8));
  const titulo = textoDia(fecha);
  const enHoja = apertura?.fecha === fecha && apertura.modo === 'toque';
  const clase = ['vc-dia', `v-${variante}`, r?.color ? `c-${r.color}` : 'sin-pagos', fuera ? 'fuera' : '', fecha === hoy ? 'hoy' : '', elegido || enHoja ? 'elegido' : '']
    .filter(Boolean).join(' ');
  return (
    <div className={`vc-dia-marco l-${lado}`}>
      <button type="button" className={clase} data-dia={fecha} data-color-dia={r?.color ?? 'ninguno'} aria-pressed={elegido}
        tabIndex={enfocable ? 0 : -1} aria-label={`${etiquetaResumen(titulo, r)}. Filtrar la lista a este día`}
        aria-describedby={abierto ? id : undefined}
        onPointerDown={(e: EventoPuntero) => { toque.current = e.pointerType === 'touch'; }}
        onPointerEnter={(e: EventoPuntero) => { if (e.pointerType === 'mouse' && r) onAbrir({ fecha, modo: 'raton' }); }}
        onPointerLeave={(e: EventoPuntero) => { if (e.pointerType === 'mouse' && apertura?.fecha === fecha && apertura.modo === 'raton') onAbrir(null); }}
        onFocus={() => { onFoco?.(); if (!toque.current && r) onAbrir({ fecha, modo: 'foco' }); }}
        onBlur={() => { if (apertura?.fecha === fecha && apertura.modo === 'foco') onAbrir(null); }}
        onKeyDown={(e) => {
          if (e.key === 'Escape' && apertura?.fecha === fecha) { e.preventDefault(); onAbrir(null); return; }
          onTecla?.(e);
        }}
        onClick={() => {
          if (toque.current && r) {
            // Pantalla táctil: el toque abre el detalle (que tiene su botón para filtrar); un segundo toque lo cierra.
            onAbrir(apertura?.fecha === fecha && apertura.modo === 'toque' ? null : { fecha, modo: 'toque' });
            return;
          }
          onAbrir(null);
          onFiltrar();
        }}>
        <span className="vc-dia-cabeza">
          {variante === 'semana' && <span className="vc-dia-sem">{F_DSEM.format(aFecha(fecha))}</span>}
          <span className="vc-dia-num">{num}</span>
          {r && <Globo n={r.pagos} />}
        </span>
        <span className="vc-dia-cuerpo">
          {r && <ImporteCelda r={r} />}
          {r && r.total.neto !== null && notasFuera(r).length > 0 && <span className="vc-dia-fuera" aria-hidden="true">{r.sin_importe + r.sentido_no_documentado + r.cargo_negativo} fuera</span>}
        </span>
      </button>
      {abierto && r && (
        <div className="vc-desplegable" role="tooltip" id={id} data-desplegable={fecha}>
          <p className="vc-desplegable-titulo">{titulo} <span className="tenue">· {plural(r.pagos, 'pago', 'pagos')}</span></p>
          <DetallePagos filas={filas} r={r} max={8} />
          <p className="vc-desplegable-pista tenue">Clic: ver solo este día en la lista</p>
        </div>
      )}
    </div>
  );
}

/** Hoja inferior (pantalla táctil): detalle del día tocado y botón para filtrar la lista. */
function HojaToque({ fecha, filas, r, onCerrar, onFiltrar }: { fecha: string; filas: FilaVencimientoPago[]; r: ResumenCalendario; onCerrar: () => void; onFiltrar: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { ref.current?.focus(); }, [fecha]);
  return (
    <div className="vc-hoja" role="dialog" aria-modal="false" aria-labelledby="vc-hoja-titulo" tabIndex={-1} ref={ref} data-hoja-dia={fecha}
      onKeyDown={(e) => { if (e.key === 'Escape') onCerrar(); }}>
      <div className="vc-hoja-cabecera">
        <p className="vc-desplegable-titulo" id="vc-hoja-titulo">{textoDia(fecha)} <span className="tenue">· {plural(r.pagos, 'pago', 'pagos')}</span></p>
        <button type="button" className="vc-cerrar" onClick={onCerrar} aria-label="Cerrar el detalle del día">×</button>
      </div>
      <div className="vc-hoja-cuerpo"><DetallePagos filas={filas} r={r} /></div>
      <button type="button" className="boton-primario vc-hoja-filtrar" onClick={onFiltrar} data-filtrar-dia={fecha}>Filtrar la lista a este día</button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Vistas
// ---------------------------------------------------------------------------

interface PropsVista {
  filas: FilaVencimientoPago[];
  fecha: string;
  hoy: string;
  filtro: FiltroCalendario | null;
  apertura: Apertura;
  onAbrir: (a: Apertura) => void;
  onFiltrar: (escala: FiltroCalendario['escala'], clave: string) => void;
}

const lado = (i: number): 'izq' | 'centro' | 'der' => (i <= 2 ? 'izq' : i >= 4 ? 'der' : 'centro');
const esElegido = (filtro: FiltroCalendario | null, escala: FiltroCalendario['escala'], clave: string) => filtro?.escala === escala && filtro.clave === clave;

function VistaMes({ filas, fecha, hoy, filtro, apertura, onAbrir, onFiltrar }: PropsVista) {
  const semanas = rejillaMes(fecha);
  const mes = fecha.slice(0, 7);
  const porDia = agrupar(filas, 'dia');
  const resDia = agregar(filas, 'dia');
  const resSem = agregar(filas, 'semana');
  const todas = semanas.flat();
  // Foco itinerante: una sola parada de tabulación en la rejilla; flechas para moverse (±1 día, ±1 semana).
  const inicial = todas.includes(hoy) ? hoy : `${mes}-01`;
  const [foco, setFoco] = useState(inicial);
  const enRejilla = todas.includes(foco) ? foco : inicial;
  const rejilla = useRef<HTMLDivElement>(null);
  function tecla(e: KeyboardEvent<HTMLButtonElement>, f: string) {
    const salto: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
    let destino: string | null = null;
    if (e.key in salto) destino = sumarDiasIso(f, salto[e.key]);
    else if (e.key === 'Home') destino = semanas.find((s) => s.includes(f))?.[0] ?? null;
    else if (e.key === 'End') destino = semanas.find((s) => s.includes(f))?.[6] ?? null;
    if (destino === null) return;
    e.preventDefault();
    if (!todas.includes(destino)) return;
    setFoco(destino);
    rejilla.current?.querySelector<HTMLButtonElement>(`[data-dia="${destino}"]`)?.focus();
  }
  return (
    <div className="vc-mes" role="grid" aria-label={`Vencimientos de ${textoMes(mes).toLowerCase()}`} ref={rejilla} data-vista-mes={mes}>
      <div className="vc-fila vc-fila-cabecera" role="row">
        <span className="vc-cab-sem" role="columnheader"><abbr title="Semana">Sem.</abbr></span>
        {INICIALES.map((x, i) => <span key={x} className={`vc-cab${i >= 5 ? ' finde' : ''}`} role="columnheader"><abbr title={NOMBRES_DIA[i]}>{x}</abbr></span>)}
      </div>
      {semanas.map((s) => {
        const lunes = s[0];
        const rs = resSem.get(lunes);
        const titulo = `Semana ${semanaIso(lunes)} (${textoSemana(s[0], s[6])})`;
        return (
          <div className="vc-fila" role="row" key={lunes}>
            <span role="rowheader" className="vc-sem-marco">
              <button type="button" className={`vc-sem${esElegido(filtro, 'semana', lunes) ? ' elegido' : ''}${rs ? '' : ' sin-pagos'}`} data-semana={lunes}
                aria-pressed={esElegido(filtro, 'semana', lunes)} aria-label={`${etiquetaResumen(titulo, rs)}. Filtrar la lista a esta semana`}
                onClick={() => onFiltrar('semana', lunes)}>
                <span className="vc-sem-n">{semanaIso(lunes)}</span>
                {rs && <ImporteCelda r={rs} />}
              </button>
            </span>
            {s.map((d, i) => (
              <span role="gridcell" key={d} className="vc-celda">
                <Dia fecha={d} r={resDia.get(d)} filas={porDia.get(d) ?? []} hoy={hoy} fuera={d.slice(0, 7) !== mes}
                  elegido={esElegido(filtro, 'dia', d)} enfocable={d === enRejilla} lado={lado(i)} variante="mes"
                  apertura={apertura} onAbrir={onAbrir} onFiltrar={() => onFiltrar('dia', d)}
                  onTecla={(e) => tecla(e, d)} onFoco={() => setFoco(d)} />
              </span>
            ))}
          </div>
        );
      })}
    </div>
  );
}

function VistaSemana({ filas, fecha, hoy, filtro, apertura, onAbrir, onFiltrar }: PropsVista) {
  const { desde } = periodoVista('semana', fecha);
  const dias = Array.from({ length: 7 }, (_, i) => sumarDiasIso(desde, i));
  const porDia = agrupar(filas, 'dia');
  const resDia = agregar(filas, 'dia');
  return (
    <ol className="vc-semana" aria-label={`Semana ${semanaIso(desde)}`} data-vista-semana={desde}>
      {dias.map((d, i) => {
        const fs = porDia.get(d) ?? [];
        return (
          <li key={d} className={`vc-semana-dia${i >= 5 ? ' finde' : ''}`}>
            <Dia fecha={d} r={resDia.get(d)} filas={fs} hoy={hoy} elegido={esElegido(filtro, 'dia', d)} enfocable lado={lado(i)} variante="semana"
              apertura={apertura} onAbrir={onAbrir} onFiltrar={() => onFiltrar('dia', d)} />
            {fs.length > 0 && (
              <ul className="vc-semana-pagos">
                {fs.map((f) => (
                  <li key={f.vencimiento_id} className={`vc-mini c-${COLOR_DIA[f.estado_pago]}`} data-pago-semana={f.vencimiento_id}>
                    <span className="vc-mini-proveedor" title={nombreProveedor(f)}>{nombreProveedor(f)}</span>
                    <span className="vc-mini-importe">{euros(f.importe) ?? <span className="desconocido">pendiente</span>}</span>
                  </li>
                ))}
              </ul>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function VistaDia({ filas, fecha }: Pick<PropsVista, 'filas' | 'fecha'>) {
  const fs = agrupar(filas, 'dia').get(fecha) ?? [];
  const r = resumir(fs, fecha, 'dia');
  return (
    <div className={`vc-vista-dia${r.color ? ` c-${r.color}` : ''}`} data-vista-dia={fecha} data-color-dia={r.color ?? 'ninguno'}>
      {fs.length === 0 ? <p className="tenue vc-vacio">Ningún vencimiento este día.</p> : (
        <>
          <p className="vc-vista-dia-resumen">
            <span className={`vc-vista-dia-total${r.total.neto === null ? ' vc-importe-nulo' : ''}`} data-importe-dia={euros(r.total.neto) ?? ''}>{euros(r.total.neto) ?? textoSinTotal(r)?.largo ?? '—'}</span>
            <span className="tenue">{plural(r.pagos, 'pago', 'pagos')}{r.peor ? ` · peor estado: ${DICCIONARIO_ESTADOS[r.peor].texto.toLowerCase()}` : ''}</span>
          </p>
          <DetallePagos filas={fs} r={r} />
        </>
      )}
    </div>
  );
}

function VistaAnio({ filas, fecha, filtro, onFiltrar, onVerMes }: Pick<PropsVista, 'filas' | 'fecha' | 'filtro' | 'onFiltrar'> & { onVerMes: (ym: string) => void }) {
  const anio = fecha.slice(0, 4);
  const meses: MesDelAnio[] = resumenAnio(filas, anio);
  return (
    <>
      <ol className="vc-anio" aria-label={`Meses de ${anio}`} data-vista-anio={anio}>
        {meses.map((m) => {
          const nombre = mayuscula(F_MES_SOLO.format(aFecha(m.desde)));
          const elegido = esElegido(filtro, 'mes', m.clave);
          const fuera = notasFuera(m);
          return (
            <li key={m.clave} className={`vc-mes-tarjeta i-${m.intensidad}${elegido ? ' elegido' : ''}`} data-mes={m.clave} data-intensidad={m.intensidad}>
              <button type="button" className="vc-mes-boton" aria-pressed={elegido} onClick={() => onFiltrar('mes', m.clave)}
                aria-label={`${etiquetaResumen(`${nombre} de ${anio}`, m)}. Filtrar la lista a este mes`}>
                <span className="vc-mes-nombre">{nombre}</span>
                <span className="vc-mes-total" data-importe-mes={euros(m.total.neto) ?? ''}>{m.pagos === 0 ? <span className="tenue">sin pagos</span> : euros(m.total.neto) ?? <span className="vc-importe-nulo">{textoSinTotal(m)?.largo ?? '—'}</span>}</span>
                <span className="vc-mes-nota">{m.pagos > 0 ? plural(m.pagos, 'pago', 'pagos') : ' '}{fuera.length ? ` · fuera del total: ${fuera.join(', ')}` : ''}</span>
              </button>
              <button type="button" className="vc-ver-mes" onClick={() => onVerMes(m.clave)} aria-label={`Ver ${nombre.toLowerCase()} en el calendario`}>Ver mes</button>
            </li>
          );
        })}
      </ol>
      <p className="vc-leyenda-intensidad tenue" aria-hidden="true">
        Por importe del mes: <span className="vc-escala"><i className="i-1" /><i className="i-2" /><i className="i-3" /><i className="i-4" /></span> más
      </p>
    </>
  );
}

// ---------------------------------------------------------------------------
// H6-5: resumen del periodo visible (junto al título) y aviso de periodo vacío
// ---------------------------------------------------------------------------

const textoFechaCorta = (f: string) => `${F_DIA_MES.format(aFecha(f))} ${f.slice(0, 4)}`;

/** Cifra de un grupo: «—» si no tiene pagos; «sin importe» si los tiene pero ninguno suma (nunca 0 inventado). */
function valorGrupo(b: GrupoResumenPeriodo, abs = false): string {
  if (b.pagos === 0) return '—';
  if (b.neto === null) return 'sin importe';
  return euros(abs ? Math.abs(b.neto) : b.neto) as string;
}

function Termino({ id, etiqueta, b, op, abs }: { id: string; etiqueta: string; b: GrupoResumenPeriodo; op: string; abs?: boolean }) {
  return (
    <div className={`vc-r vc-r-${id}${b.pagos === 0 ? ' vacio' : ''}`} data-resumen={id} data-op={op} data-centimos={Math.round((b.neto ?? 0) * 100)}>
      <dt>{etiqueta}{b.pagos > 0 && <span className="vc-r-n"> · {b.pagos}</span>}</dt>
      <dd>{valorGrupo(b, abs)}</dd>
    </div>
  );
}

/**
 * Total del periodo visible = Pagado + Domiciliado previsto + Falta por pagar (− Abonos pendientes de compensar), con la
 * misma regla de totales de H6. Lo que no suma (sin importe, cargo negativo, sentido no documentado), con su recuento.
 */
function ResumenDelPeriodo({ r, titulo, vecinos, onIr }: {
  r: ResumenPeriodo; titulo: string; vecinos: ReturnType<typeof vecinosConPagos>; onIr: (fecha: string) => void;
}) {
  if (r.pagos === 0) {
    return (
      <div className="vc-resumen vc-resumen-vacio" data-resumen-periodo data-resumen-pagos="0">
        {vecinos.fuera === 0 ? <p className="tenue">Ningún pago en este periodo con estos filtros.</p> : (
          <p className="vc-aviso-vacio" data-aviso-periodo-vacio role="status">
            <span>Ningún pago en este periodo con estos filtros; hay {plural(vecinos.fuera, 'pago', 'pagos')} en otras fechas.</span>
            {vecinos.antes && <button type="button" className="boton-secundario boton-mini" onClick={() => onIr(vecinos.antes as string)} data-ir-anterior={vecinos.antes}>‹ Ir al anterior ({textoFechaCorta(vecinos.antes)})</button>}
            {vecinos.despues && <button type="button" className="boton-secundario boton-mini" onClick={() => onIr(vecinos.despues as string)} data-ir-siguiente={vecinos.despues}>Ir al siguiente ({textoFechaCorta(vecinos.despues)}) ›</button>}
          </p>
        )}
      </div>
    );
  }
  const { pagado, domiciliado, falta, abonos, revisar } = r.grupos;
  const fuera = [
    r.sin_importe ? `${r.sin_importe} sin importe` : null,
    r.cargo_negativo ? plural(r.cargo_negativo, 'cargo negativo', 'cargos negativos') : null,
    r.sentido_no_documentado ? `${r.sentido_no_documentado} de sentido no documentado` : null,
  ].filter((x): x is string => x !== null);
  return (
    <div className="vc-resumen" data-resumen-periodo data-resumen-pagos={r.pagos} data-resumen-cuadra={String(r.cuadra)}>
      <dl className="vc-resumen-cifras" aria-label={`Resumen de ${titulo}`}>
        <div className="vc-r vc-r-total" data-resumen="total" data-centimos={Math.round((r.total.neto ?? 0) * 100)}>
          <dt>Total<span className="vc-r-n"> · {plural(r.pagos, 'pago', 'pagos')}</span></dt>
          <dd>{euros(r.total.neto) ?? <span className="vc-importe-nulo">{textoSinTotal(r)?.largo ?? 'sin importe'}</span>}</dd>
        </div>
        <Termino id="pagado" etiqueta="Pagado" b={pagado} op="=" />
        <Termino id="domiciliado" etiqueta="Domiciliado previsto" b={domiciliado} op="+" />
        <Termino id="falta" etiqueta="Falta por pagar" b={falta} op="+" />
        {abonos.pagos > 0 && <Termino id="abonos" etiqueta="Abonos por compensar" b={abonos} op={abonos.neto !== null && abonos.neto < 0 ? '−' : '+'} abs />}
        {/* H6-REAL: marcas que ya no coinciden con su vencimiento: nunca como pagado. */}
        {revisar.pagos > 0 && <Termino id="revisar" etiqueta="A revisar" b={revisar} op={revisar.neto !== null && revisar.neto < 0 ? '−' : '+'} abs />}
      </dl>
      {fuera.length > 0 && <p className="vc-resumen-fuera" data-resumen-fuera>Fuera de los totales: {fuera.join(' · ')}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Calendario
// ---------------------------------------------------------------------------

export function CalendarioVencimientos({ filas, hoy, vista, fecha, filtro, onNavegar, onFiltrar }: {
  /** Filas con los filtros de la lista salvo los de fecha (periodo, rango y el propio calendario). */
  filas: FilaVencimientoPago[];
  hoy: string;
  vista: VistaCalendario;
  fecha: string;
  filtro: FiltroCalendario | null;
  onNavegar: (vista: VistaCalendario, fecha: string) => void;
  onFiltrar: (escala: FiltroCalendario['escala'], clave: string) => void;
}) {
  const [apertura, setApertura] = useState<Apertura>(null);
  const { desde, hasta } = periodoVista(vista, fecha);
  const sinF = sinFecha(filas);
  useEffect(() => { setApertura(null); }, [vista, fecha]);
  const hoja = apertura?.modo === 'toque' ? apertura.fecha : null;
  const filasHoja = hoja ? agrupar(filas, 'dia').get(hoja) ?? [] : [];
  const nombrePeriodo = { dia: 'día', semana: 'semana', mes: 'mes', anio: 'año' }[vista];
  const filtrar = (escala: FiltroCalendario['escala'], clave: string) => { setApertura(null); onFiltrar(escala, clave); };
  const props: PropsVista = { filas, fecha, hoy, filtro, apertura, onAbrir: setApertura, onFiltrar: filtrar };

  return (
    <section className="tarjeta vc" aria-labelledby="t-vc" data-calendario-vencimientos data-vista-cal={vista}>
      <h2 id="t-vc" className="visualmente-oculto">Calendario de vencimientos</h2>
      <div className="cal-barra vc-barra">
        <div className="cal-vistas" role="group" aria-label="Vista del calendario">
          {VISTAS_CALENDARIO.map((x) => (
            <button key={x.v} type="button" className={x.v === vista ? 'activa' : undefined} aria-pressed={x.v === vista}
              onClick={() => onNavegar(x.v, fecha)} data-vista={x.v}>{x.texto}</button>
          ))}
        </div>
        <div className="cal-navegar">
          <button type="button" className="boton-secundario" onClick={() => onNavegar(vista, moverVista(vista, fecha, -1))} aria-label={`${mayuscula(nombrePeriodo)} anterior`} data-cal-anterior>‹</button>
          <button type="button" className="boton-secundario" onClick={() => onNavegar(vista, hoy)} data-cal-hoy>Hoy</button>
          <button type="button" className="boton-secundario" onClick={() => onNavegar(vista, moverVista(vista, fecha, 1))} aria-label={`${mayuscula(nombrePeriodo)} siguiente`} data-cal-siguiente>›</button>
          <h3 className="cal-periodo vc-periodo" data-periodo-cal aria-live="polite">{textoPeriodoVista(vista, desde, hasta)}</h3>
        </div>
        {vista !== 'anio' && (
          <button type="button" className="boton-secundario vc-mostrar" data-mostrar-periodo
            onClick={() => filtrar(vista === 'mes' ? 'mes' : vista === 'semana' ? 'semana' : 'dia', claveDe(fecha, vista))}>
            Ver {vista === 'semana' ? 'esta semana' : `este ${nombrePeriodo}`} en la lista
          </button>
        )}
      </div>
      <ResumenDelPeriodo r={resumenPeriodo(filas, desde, hasta)} titulo={textoPeriodoVista(vista, desde, hasta).toLowerCase()}
        vecinos={vecinosConPagos(filas, desde, hasta)} onIr={(f) => onNavegar(vista, f)} />
      {vista !== 'anio' && (
        <ul className="vc-leyenda" aria-label="Color del día: el peor estado de sus pagos">
          {LEYENDA_COLOR.map((x) => <li key={x.color}><i className={`vc-muestra c-${x.color}`} aria-hidden="true" />{x.texto}</li>)}
          <li className="tenue vc-leyenda-globo"><span className="vc-globo" aria-hidden="true">2</span>nº de pagos</li>
        </ul>
      )}

      {vista === 'mes' && <VistaMes key={fecha.slice(0, 7)} {...props} />}
      {vista === 'semana' && <VistaSemana {...props} />}
      {vista === 'dia' && <VistaDia filas={filas} fecha={fecha} />}
      {vista === 'anio' && <VistaAnio filas={filas} fecha={fecha} filtro={filtro} onFiltrar={filtrar} onVerMes={(ym) => onNavegar('mes', `${ym}-01`)} />}

      <p className="tenue vc-nota">
        Total del día: cargos − abonos, también lo ya pagado. No suman los importes pendientes, el sentido no documentado ni los
        cargos con importe negativo (se cuentan aparte).{sinF > 0 && <span data-sin-fecha-cal> {plural(sinF, 'vencimiento sin fecha no aparece', 'vencimientos sin fecha no aparecen')} en el calendario (sí en la lista).</span>}
      </p>

      {hoja && filasHoja.length > 0 && (
        <HojaToque fecha={hoja} filas={filasHoja} r={resumir(filasHoja, hoja, 'dia')} onCerrar={() => setApertura(null)}
          onFiltrar={() => filtrar('dia', hoja)} />
      )}
    </section>
  );
}
