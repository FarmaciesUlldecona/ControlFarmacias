/**
 * H7: pantalla Cashflow (solo lectura). Decenas (3 pasadas y 9 próximas) o meses (3 y 9); PIO, RITA o consolidado.
 * El cálculo es el de server/cashflow/cashflow.ts: el front lo repite al cambiar «Media / Excel» (elección guardada solo
 * en este navegador). En REAL, «Pendiente de tablas en Supabase».
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import type { Importe } from '../server/contrato.ts';
import { DICCIONARIO_ESTADOS } from '../server/pagos/pagos.ts';
import {
  CATEGORIAS_MEDIA, TEXTO_FUENTE, TEXTO_H7_PENDIENTE, TEXTO_POSIBLE_DUPLICADO, VISTAS_CUENTA, avisosColumna, calcularCashflow, celdaColumna,
  columnasVista, finDecena, porCategoria, resumenColumna, saldoColumna, tipoColumna, totalCategoria,
  type AvisoCashflow, type CashflowDTO, type Celda, type CeldaColumna, type Columna, type Eleccion, type Escala,
  type ResultadoCashflow, type ResultadoVista, type TipoColumna, type VencimientoCashflow, type VistaCuenta,
} from '../server/cashflow/cashflow.ts';
import { useApiRecargable } from './api.ts';
import { euros, fechaCorta, fechaHora, plural } from './formato.ts';
import { Cabecera, MOVIL, useMedia } from './ui.tsx';

// ---------------------------------------------------------------------------
// Formato
// ---------------------------------------------------------------------------

const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
const ENTERO = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0, useGrouping: 'always' });
const menos = (s: string) => s.replace('-', '−');
/** Cifra de tabla: euros sin decimales (el desglose da el importe exacto). */
export function cifra(v: Importe): string {
  return v === null ? '—' : menos(ENTERO.format(Math.round(v) === 0 ? 0 : v));
}
export function eurosExactos(v: Importe): string {
  return v === null ? 'importe pendiente' : menos(euros(v) ?? '');
}
export function textoDecena(d: string): string {
  return `${Number(d.slice(8))}–${Number(finDecena(d).slice(8))} ${MESES[Number(d.slice(5, 7)) - 1]}`;
}
export const textoDecenaLargo = (d: string) => `${textoDecena(d)} ${d.slice(0, 4)}`;
const textoMes = (ym: string) => `${MESES[Number(ym.slice(5, 7)) - 1]} ${ym.slice(0, 4)}`;
const textoColumna = (c: Columna) => (c.escala === 'decenas' ? textoDecena(c.clave) : textoMes(c.clave));
const textoColumnaLargo = (c: Columna) => (c.escala === 'decenas' ? textoDecenaLargo(c.clave) : textoMes(c.clave));
const NOMBRE_VISTA: Record<VistaCuenta, string> = { PIO: 'PIO', RITA: 'RITA', CONSOLIDADO: 'Consolidado' };
const TEXTO_TIPO: Record<TipoColumna, string> = { real: 'Real', previsto: 'Previsto', mixto: 'Real + previsto' };

// ---------------------------------------------------------------------------
// «Media / Excel»: solo en este navegador (try/catch: sin almacenamiento, por defecto)
// ---------------------------------------------------------------------------

const CLAVE_ELECCION = 'cf.cashflow.eleccion.v1';
function leerElecciones(): Record<string, Eleccion> {
  try {
    const v = JSON.parse(window.localStorage.getItem(CLAVE_ELECCION) ?? '{}') as unknown;
    if (v === null || typeof v !== 'object' || Array.isArray(v)) return {};
    return Object.fromEntries(Object.entries(v).filter(([k, x]) => Object.hasOwn(CATEGORIAS_MEDIA, k) && (x === 'media' || x === 'excel')));
  } catch {
    return {};
  }
}
function guardarElecciones(e: Record<string, Eleccion>): void {
  try { window.localStorage.setItem(CLAVE_ELECCION, JSON.stringify(e)); } catch { /* sin almacenamiento: la elección dura la visita */ }
}

// ---------------------------------------------------------------------------
// Cabecera de datos y avisos
// ---------------------------------------------------------------------------

function textoAviso(a: AvisoCashflow): ReactNode {
  const periodo = a.decena === null ? '' : a.hasta && a.hasta !== a.decena ? `del ${textoDecenaLargo(a.decena)} al ${textoDecenaLargo(a.hasta)}` : textoDecenaLargo(a.decena);
  if (a.codigo === 'CUENTA_CUBIERTA') {
    return (
      <>
        <strong>{a.cuenta} en negativo</strong> ({periodo}). {a.cubre} la cubre con <strong className="cf-num">{eurosExactos(a.importe)}</strong>.{' '}
        Devolución prevista: {a.devolucion ? <strong>{textoDecenaLargo(a.devolucion)}</strong> : 'no dentro del horizonte'}.
      </>
    );
  }
  if (a.codigo === 'CONSOLIDADO_NEGATIVO') {
    const peor = a.decenas.find((x) => x.importe === a.importe)?.decena ?? a.decena;
    return (
      <>
        <strong>Consolidado en negativo</strong> ({periodo}). Faltan <strong className="cf-num">{eurosExactos(a.importe)}</strong>
        {a.decenas.length > 1 && peor ? <> en el peor momento ({textoDecenaLargo(peor)})</> : null}.
      </>
    );
  }
  return a.decena ? <>{a.texto} ({textoDecenaLargo(a.decena)})</> : a.texto;
}

function ListaAvisos({ avisos }: { avisos: AvisoCashflow[] }) {
  const saldo = avisos.filter((a) => a.tipo !== 'gris');
  return (
    <section className="tarjeta cf-avisos" aria-labelledby="t-cf-avisos" id="cf-avisos">
      <h2 id="t-cf-avisos">Avisos de saldo <span className="tenue">(mínimo 0 €)</span></h2>
      {saldo.length === 0 ? <p className="tenue">Ningún saldo previsto queda por debajo del mínimo.</p> : (
        <ul>
          {saldo.map((a, i) => (
            <li key={i} className={`cf-aviso ${a.tipo}`} data-cf-aviso={a.tipo} data-decena={a.decena ?? ''}>
              <span className="cf-aviso-icono" aria-hidden="true">{a.tipo === 'rojo' ? '■' : '▲'}</span>
              <span className="cf-aviso-etiqueta">{a.tipo === 'rojo' ? 'Falta saldo' : 'Cuenta cubierta'}</span>
              <span className="cf-aviso-texto">{textoAviso(a)}{a.incompleto && <span className="tenue"> Con importes pendientes: puede ser peor.</span>}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Resumen({ r, d }: { r: ResultadoCashflow; d: CashflowDTO }) {
  const proximo = r.avisos.find((a) => a.tipo !== 'gris') ?? null;
  const imp = r.importacion;
  const antigua = r.avisos.some((a) => a.codigo === 'IMPORTACION_ANTIGUA' || a.codigo === 'IMPORTACION_FALLIDA' || a.codigo === 'SIN_IMPORTACION_VIGENTE');
  return (
    <div className="cf-resumen" data-cf-resumen>
      {VISTAS_CUENTA.map((v) => {
        const x = r.vistas[v];
        return (
          <div key={v} className={`cf-ficha${v === 'CONSOLIDADO' ? ' consolidado' : ''}`} data-cf-saldo-actual={v}>
            <span className="cf-ficha-titulo"><span className={`cf-muestra s-${v.toLowerCase()}`} aria-hidden="true" />Saldo {NOMBRE_VISTA[v]}</span>
            <span className="cf-ficha-cifra cf-num">{x ? eurosExactos(x.saldo_partida) : '—'}</span>
            <span className="cf-ficha-nota">{x?.ultima_real ? `Banco al ${fechaCorta(finDecena(x.ultima_real))}` : 'Sin saldo de banco'}</span>
          </div>
        );
      })}
      <a href="#cf-avisos" className={`cf-ficha aviso ${proximo?.tipo ?? 'ok'}`} data-cf-proximo-aviso={proximo?.tipo ?? 'ninguno'}>
        <span className="cf-ficha-titulo">Próximo aviso</span>
        {proximo ? (
          <>
            <span className="cf-ficha-cifra">{proximo.decena ? textoDecenaLargo(proximo.decena) : '—'}</span>
            <span className="cf-ficha-nota">{proximo.codigo === 'CONSOLIDADO_NEGATIVO' ? `Faltan ${eurosExactos(proximo.importe)}` : `${proximo.cuenta} cubierta por ${proximo.cubre}`}</span>
          </>
        ) : (
          <><span className="cf-ficha-cifra">Ninguno</span><span className="cf-ficha-nota">en el horizonte</span></>
        )}
      </a>
      <div className={`cf-ficha${antigua ? ' gris' : ''}`} data-cf-importacion>
        <span className="cf-ficha-titulo">Última importación</span>
        <span className="cf-ficha-cifra">{imp.vigente ? fechaHora(imp.vigente.importado_at) : 'Ninguna vigente'}</span>
        <span className="cf-ficha-nota">{imp.vigente ? `${imp.vigente.origen} · hace ${plural(imp.dias ?? 0, 'día', 'días')}` : `Referencia ${fechaCorta(d.hoy)}`}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Gráfico de saldo previsto
// ---------------------------------------------------------------------------

const SERIES: { vista: VistaCuenta; clase: string }[] = [
  { vista: 'PIO', clase: 's-pio' }, { vista: 'RITA', clase: 's-rita' }, { vista: 'CONSOLIDADO', clase: 's-consolidado' },
];
function pasoBonito(rango: number): number {
  const bruto = rango / 4;
  const p = 10 ** Math.floor(Math.log10(bruto || 1));
  const n = bruto / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}

function Grafico({ r, cols, vista, movil }: { r: ResultadoCashflow; cols: Columna[]; vista: VistaCuenta; movil: boolean }) {
  const [foco, setFoco] = useState<number | null>(null);
  const W = movil ? 340 : 1000;
  const H = movil ? 260 : 280;
  const M = { l: movil ? 46 : 64, r: movil ? 8 : 96, t: 18, b: 30 };
  const series = SERIES.filter((s) => r.vistas[s.vista]);
  const puntos = series.map((s) => cols.map((c) => saldoColumna(r.vistas[s.vista], c).saldo));
  // Marcas de aviso: en el saldo de la peor decena de la columna (en «Mes», el cierre del mes puede ser positivo).
  const marcas = cols.flatMap((c, i) => avisosColumna(r.avisos, c).flatMap((a) => {
    const peor = a.decenas.filter((x) => c.decenas.includes(x.decena)).sort((p, q) => q.importe - p.importe)[0];
    const v = a.tipo === 'rojo' ? r.vistas.CONSOLIDADO : r.vistas[a.cuenta as VistaCuenta];
    const s = peor ? v?.decenas[peor.decena]?.saldo ?? null : null;
    return s === null ? [] : [{ i, a, s, decena: peor.decena }];
  }));
  const valores = [...puntos.flat(), ...marcas.map((m) => m.s)].filter((v): v is number => v !== null);
  if (valores.length === 0) return <p className="tenue">Sin saldos que dibujar.</p>;
  const paso = pasoBonito(Math.max(...valores, 0) - Math.min(...valores, 0));
  const lo = Math.floor(Math.min(...valores, 0) / paso) * paso;
  const hi = Math.ceil(Math.max(...valores, 0) / paso) * paso;
  const ancho = (W - M.l - M.r) / cols.length;
  const x = (i: number) => M.l + (i + 0.5) * ancho;
  const y = (v: number) => M.t + ((hi - v) / (hi - lo || 1)) * (H - M.t - M.b);
  const ticks: number[] = [];
  for (let t = lo; t <= hi + paso / 2; t += paso) ticks.push(t);
  const tipos = cols.map((c) => tipoColumna(r.vistas.CONSOLIDADO, c));
  const ultimoReal = tipos.lastIndexOf('real');
  // Tramo: real (continuo) hasta la última columna real; previsto (discontinuo) desde ella.
  const tramo = (vals: Importe[], desde: number, hasta: number) => {
    let dd = '';
    let abierto = false;
    for (let i = Math.max(desde, 0); i <= hasta; i++) {
      const v = vals[i];
      if (v === null) { abierto = false; continue; }
      dd += `${abierto ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      abierto = true;
    }
    return dd;
  };
  // Etiquetas directas al final de cada línea, sin solaparse (en móvil, solo la leyenda).
  const finales = movil ? [] : series.map((s, k) => {
    const vals = puntos[k];
    const j = vals.map((v, i) => (v === null ? -1 : i)).filter((i) => i >= 0).pop();
    return { s, yv: j === undefined ? null : y(vals[j] as number) };
  }).filter((e) => e.yv !== null).sort((a, b) => (a.yv as number) - (b.yv as number));
  for (let k = 1; k < finales.length; k++) if ((finales[k].yv as number) - (finales[k - 1].yv as number) < 15) finales[k].yv = (finales[k - 1].yv as number) + 15;
  const f = foco === null ? null : cols[foco];
  return (
    <div className="cf-grafico" data-cf-grafico>
      <div className="cf-leyenda" aria-hidden="true">
        {series.map((s) => <span key={s.vista} className={`cf-leyenda-serie${s.vista === vista ? ' activa' : ''}`}><span className={`cf-linea-muestra ${s.clase}`} />{NOMBRE_VISTA[s.vista]}</span>)}
        <span className="cf-leyenda-serie"><span className="cf-linea-muestra discontinua" />Previsto</span>
        <span className="cf-leyenda-serie"><span className="cf-marca-muestra naranja">▲</span>Cuenta cubierta</span>
        <span className="cf-leyenda-serie"><span className="cf-marca-muestra rojo">■</span>Consolidado en negativo</span>
      </div>
      <div className="cf-grafico-lienzo">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Saldo previsto por cuenta y consolidado; la tabla de abajo tiene las cifras" onMouseLeave={() => setFoco(null)}>
          {ultimoReal >= 0 && <rect className="cf-zona-real" x={M.l} y={M.t} width={(ultimoReal + 1) * ancho} height={H - M.t - M.b} />}
          {ultimoReal >= 0 && <text className="cf-zona-texto" x={M.l + 6} y={M.t + 12}>Real</text>}
          {ultimoReal < cols.length - 1 && <text className="cf-zona-texto" x={M.l + (ultimoReal + 1) * ancho + 6} y={M.t + 12}>Previsto</text>}
          {ticks.map((t) => (
            <g key={t}>
              <line className={t === 0 ? 'cf-cero' : 'cf-reja'} x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} />
              <text className="cf-eje" x={M.l - 8} y={y(t) + 4} textAnchor="end">{t === 0 ? '0 €' : cifra(t)}</text>
            </g>
          ))}
          {cols.map((c, i) => (movil && i % 3 !== 0 ? null : (
            <text key={c.clave} className={`cf-eje${c.actual ? ' actual' : ''}`} x={x(i)} y={H - 10} textAnchor="middle">{textoColumna(c)}</text>
          )))}
          {series.map((s, k) => (
            <g key={s.vista} className={`cf-serie ${s.clase}${s.vista === vista ? ' activa' : ''}`} data-cf-serie={s.vista}>
              <path d={tramo(puntos[k], 0, ultimoReal)} />
              <path className="previsto" d={tramo(puntos[k], ultimoReal, cols.length - 1)} />
            </g>
          ))}
          {marcas.map(({ i, a, s, decena }, n) => (a.tipo === 'rojo'
            ? <rect key={n} className="cf-marca rojo" x={x(i) - 6} y={y(s) - 6} width={12} height={12} data-cf-marca="rojo" data-columna={cols[i].clave} data-decena={decena} />
            : <path key={n} className="cf-marca naranja" d={`M${x(i)},${y(s) - 8}L${x(i) + 7},${y(s) + 5}L${x(i) - 7},${y(s) + 5}Z`} data-cf-marca="naranja" data-columna={cols[i].clave} data-decena={decena} />))}
          {finales.map((e) => <text key={e.s.vista} className={`cf-etiqueta ${e.s.clase}`} x={W - M.r + 8} y={(e.yv as number) + 4}>{NOMBRE_VISTA[e.s.vista]}</text>)}
          {foco !== null && <line className="cf-guia" x1={x(foco)} x2={x(foco)} y1={M.t} y2={H - M.b} />}
          {cols.map((c, i) => (
            <rect key={c.clave} className="cf-zona-foco" x={M.l + i * ancho} y={M.t} width={ancho} height={H - M.t - M.b} onMouseEnter={() => setFoco(i)} />
          ))}
        </svg>
        {f && foco !== null && (
          <div className={`cf-tooltip${foco > cols.length / 2 ? ' izquierda' : ''}`} style={{ left: `${(x(foco) / W) * 100}%` }} role="status" data-cf-tooltip>
            <strong>{textoColumnaLargo(f)}</strong> <span className="tenue">{TEXTO_TIPO[tipos[foco]]}</span>
            {series.map((s, k) => (
              <span key={s.vista} className="cf-tooltip-fila"><span className={`cf-muestra ${s.clase}`} />{NOMBRE_VISTA[s.vista]}<span className="cf-num">{eurosExactos(puntos[k][foco])}</span></span>
            ))}
            {avisosColumna(r.avisos, f).map((a, n) => <span key={n} className={`cf-tooltip-aviso ${a.tipo}`}>{a.tipo === 'rojo' ? 'Consolidado en negativo' : `${a.cuenta} cubierta por ${a.cubre}`}</span>)}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tabla
// ---------------------------------------------------------------------------

interface Abrir { titulo: string; col: Columna; celda: CeldaColumna }

function CeldaTabla({ c, col, titulo, onAbrir, clave }: { c: CeldaColumna | null; col: Columna; titulo: string; onAbrir: (a: Abrir) => void; clave: string }) {
  if (c === null) return <td className={`cf-c vacia ${col.actual ? 'actual' : ''}`} />;
  const usaMedia = c.fuentes.includes('MEDIA') && c.celdas.some((x) => x.fuente === 'MEDIA' && x.en_saldo);
  const fuente = c.tipo === 'real' ? 'real' : c.fuentes.includes('VENCIMIENTOS') ? 'vencimientos' : usaMedia ? 'media' : 'excel';
  return (
    <td className={`cf-c ${c.tipo} f-${fuente}${col.actual ? ' actual' : ''}`} data-cf-celda={clave} data-cf-tipo={c.tipo} data-cf-fuente={fuente}>
      <button type="button" className="cf-cbtn" onClick={() => onAbrir({ titulo, col, celda: c })}
        title={`${titulo} · ${textoColumnaLargo(col)}: ${eurosExactos(c.importe)} (ver de dónde sale)`}>
        <span className="cf-linea1">
          {c.diferencia && <span className="cf-dif" title={TEXTO_POSIBLE_DUPLICADO} data-cf-diferencia>!</span>}
          <span className="cf-num">{c.importe === null && c.desconocidos > 0 ? 'pend.' : cifra(c.importe)}</span>
        </span>
        {c.desconocidos > 0 && <span className="cf-sub aviso">+{c.desconocidos} sin importe</span>}
        {c.sin_usar !== null && <span className="cf-sub" data-cf-alt>{usaMedia ? 'Excel' : 'Media'} {cifra(c.sin_usar)}</span>}
      </button>
    </td>
  );
}

function FilaTotal({ etiqueta, v, cols, valor, clase = '', datos }: { etiqueta: ReactNode; v: ResultadoVista; cols: Columna[]; valor: (c: Columna) => ReactNode; clase?: string; datos?: string }) {
  return (
    <tr className={`cf-total ${clase}`} data-cf-total={datos}>
      <th scope="row">{etiqueta}</th>
      {cols.map((c) => <td key={c.clave} className={`cf-c ${tipoColumna(v, c)}${c.actual ? ' actual' : ''}`}>{valor(c)}</td>)}
    </tr>
  );
}

function Tabla({ r, v, cols, elecciones, onElegir, onAbrir }: {
  r: ResultadoCashflow; v: ResultadoVista; cols: Columna[]; elecciones: Record<string, Eleccion>;
  onElegir: (categoria: string, e: Eleccion) => void; onAbrir: (a: Abrir) => void;
}) {
  const [abiertas, setAbiertas] = useState<Set<string>>(new Set());
  const grupos = porCategoria(v.lineas);
  const alternar = (c: string) => setAbiertas((s) => { const n = new Set(s); if (n.has(c)) n.delete(c); else n.add(c); return n; });
  const consolidado = v.vista === 'CONSOLIDADO';

  const bloque = (gs: typeof grupos) => gs.map((g) => {
    const abierta = abiertas.has(g.categoria);
    const media = Object.hasOwn(CATEGORIAS_MEDIA, g.categoria);
    return [
      <tr key={g.categoria} className="cf-categoria" data-cf-categoria={g.categoria}>
        <th scope="row">
          <span className="cf-cat-cabeza">
            <button type="button" className="cf-plegar" aria-expanded={abierta} onClick={() => alternar(g.categoria)} data-cf-plegar={g.categoria}>
              <span className="cf-chevron" aria-hidden="true">{abierta ? '▾' : '▸'}</span>
              {/* Fuera de la farmacia la sección ya da el nombre: Entradas / Salidas. */}
              {g.clase === 'FARMACIA' ? g.categoria.replace(/^R[ES]\s+/, '') : g.sentido === 'ENTRADA' ? 'Entradas' : 'Salidas'}
            </button>
            {media && (
              <span className="cf-eleccion" role="group" aria-label={`Previsión de ${g.categoria}`} data-cf-eleccion={g.categoria}>
                {(['media', 'excel'] as const).map((e) => (
                  <button key={e} type="button" aria-pressed={(elecciones[g.categoria] ?? 'media') === e} data-opcion={e} onClick={() => onElegir(g.categoria, e)}>
                    {e === 'media' ? 'Media' : 'Excel'}
                  </button>
                ))}
              </span>
            )}
          </span>
        </th>
        {cols.map((c) => <CeldaTabla key={c.clave} c={totalCategoria(g.lineas, c, v)} col={c} titulo={g.categoria} onAbrir={onAbrir} clave={`${g.categoria}|*|${c.clave}`} />)}
      </tr>,
      ...(abierta ? g.lineas.map((l) => (
        <tr key={l.clave} className={`cf-concepto${l.media ? ' media' : ''}`} data-cf-concepto={l.concepto}>
          <th scope="row"><span className="cf-concepto-nombre" title={l.concepto}>{l.concepto}</span></th>
          {cols.map((c) => <CeldaTabla key={c.clave} c={celdaColumna(l, c, v)} col={c} titulo={`${l.concepto} (${g.categoria})`} onAbrir={onAbrir} clave={`${g.categoria}|${l.concepto}|${c.clave}`} />)}
        </tr>
      )) : []),
    ];
  });
  const seccion = (titulo: string, clave: string) => (
    <tr className="cf-seccion" data-cf-seccion={clave}><th scope="rowgroup" colSpan={cols.length + 1}>{titulo}</th></tr>
  );
  const entradas = grupos.filter((g) => g.clase === 'FARMACIA' && g.sentido === 'ENTRADA');
  const salidas = grupos.filter((g) => g.clase === 'FARMACIA' && g.sentido === 'SALIDA');
  const noRel = grupos.filter((g) => g.clase === 'NO_RELACIONADA');
  const trasp = grupos.filter((g) => g.clase === 'TRASPASO');
  const total = (campo: Parameters<typeof resumenColumna>[2]) => (c: Columna) => <span className="cf-num">{cifra(resumenColumna(v, c, campo))}</span>;

  return (
    <div className="cf-tabla-marco" tabIndex={0} aria-label="Tabla de cashflow (desplazable)">
      <table className="cf-tabla" data-cf-tabla={v.vista}>
        <caption className="visualmente-oculto">Cashflow de {NOMBRE_VISTA[v.vista]} por {cols[0]?.escala === 'mes' ? 'mes' : 'decena'}, en euros</caption>
        <thead>
          <tr>
            <th scope="col" className="cf-esquina">€ <span className="tenue">(sin decimales)</span></th>
            {cols.map((c) => {
              const t = tipoColumna(v, c);
              return (
                <th key={c.clave} scope="col" className={`cf-col ${t}${c.actual ? ' actual' : ''}`} data-cf-columna={c.clave} data-cf-tipo={t}>
                  <span className="cf-col-texto">{textoColumna(c)}</span>
                  <span className="cf-col-anio">{c.clave.slice(0, 4)}{c.actual ? ' · hoy' : ''}</span>
                  <span className={`cf-col-tipo ${t}`}>{TEXTO_TIPO[t]}</span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {seccion('Entradas', 'entradas')}
          {bloque(entradas)}
          <FilaTotal etiqueta="Total entradas" v={v} cols={cols} valor={total('entradas')} datos="entradas" />
          {seccion('Salidas', 'salidas')}
          {bloque(salidas)}
          <FilaTotal etiqueta="Total salidas" v={v} cols={cols} valor={total('salidas')} datos="salidas" />
          <FilaTotal etiqueta="Cash flow generado farmacia" v={v} cols={cols} valor={total('farmacia')} clase="generado" datos="farmacia" />
          {noRel.length > 0 && seccion('No relacionadas con la farmacia (cuentan en el saldo)', 'no_relacionadas')}
          {bloque(noRel)}
          {noRel.length > 0 && <FilaTotal etiqueta="Total no relacionadas" v={v} cols={cols} valor={total('no_relacionadas')} datos="no_relacionadas" />}
          {!consolidado && trasp.length > 0 && seccion('Traspasos entre cuentas propias', 'traspasos')}
          {!consolidado && bloque(trasp)}
          {consolidado && (
            <tr className="cf-neutro" data-cf-traspasos-neutros><th scope="row">Traspasos entre cuentas propias</th><td colSpan={cols.length} className="tenue">Neutros en el consolidado: salen de una cuenta y entran en la otra.</td></tr>
          )}
          <FilaTotal etiqueta="Saldo final" v={v} cols={cols} clase="saldo" datos="saldo" valor={(c) => {
            const s = saldoColumna(v, c);
            const negativo = s.saldo !== null && s.saldo < 0;
            const dif = s.bancos !== null && s.formulas !== null && Math.round(s.bancos * 100) !== Math.round(s.formulas * 100);
            const avisos = avisosColumna(r.avisos, c).filter((a) => (consolidado ? a.tipo === 'rojo' : a.cuenta === v.vista && a.tipo === 'naranja'));
            return (
              <span className={`cf-saldo${negativo ? ' negativo' : ''}${avisos.length ? ` ${avisos.some((a) => a.tipo === 'rojo') ? 'rojo' : 'naranja'}` : ''}`} data-cf-saldo={c.clave}
                title={dif ? `Banco ${eurosExactos(s.bancos)} · fórmulas del Excel ${eurosExactos(s.formulas)}` : eurosExactos(s.saldo)}>
                <span className="cf-num">{cifra(s.saldo)}</span>
                {s.incompleto && <span className="cf-sub aviso" title="Hay importes pendientes: el saldo no los incluye">incompleto</span>}
                {dif && <span className="cf-sub" data-cf-dif-formulas>fórmulas {cifra(s.formulas)}</span>}
              </span>
            );
          }} />
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Desglose de una celda
// ---------------------------------------------------------------------------

function ListaVenc({ vs, titulo }: { vs: VencimientoCashflow[]; titulo: string }) {
  if (vs.length === 0) return null;
  return (
    <>
      <h4>{titulo}</h4>
      <ul className="cf-venc">
        {vs.map((x) => (
          <li key={x.vencimiento_id} data-cf-venc={x.vencimiento_id}>
            <Link to={`/facturas/${x.factura_id}`}>{x.numero_factura ?? 'Factura sin número'}</Link>
            <span>{x.proveedor_nombre}</span>
            <span className="tenue">vto. {fechaCorta(x.fecha_vencimiento)} · {DICCIONARIO_ESTADOS[x.estado_pago].texto}{x.fecha_pago ? ` el ${fechaCorta(x.fecha_pago)}` : ''}</span>
            <span className="cf-num">{eurosExactos(x.importe)}</span>
          </li>
        ))}
      </ul>
    </>
  );
}

function DesgloseCelda({ c, d }: { c: Celda; d: CashflowDTO }) {
  const unidad = c.media?.unidad === 'meses' ? 'meses' : 'decenas';
  return (
    <section className="cf-desglose-celda" data-cf-desglose-fuente={c.fuente}>
      <h3>
        {c.cuenta} · {textoDecenaLargo(c.decena)} · <span className={`cf-fuente f-${c.fuente.toLowerCase()}`}>{TEXTO_FUENTE[c.fuente]}</span>
        <span className="cf-num cf-desglose-cifra">{eurosExactos(c.importe)}</span>
      </h3>
      {!c.en_saldo && (
        <p className="cf-nota" data-cf-no-suma>No entra en el saldo: para esta categoría se usa {c.fuente === 'MEDIA' ? 'lo anotado en el Excel' : 'la media'} (cámbialo con «Media / Excel»).</p>
      )}
      {c.fuente === 'REAL' && <p>Anotado en el Excel en una decena que ya tiene saldo de banco{c.excel_filas > 1 ? ` (${c.excel_filas} filas)` : ''}.</p>}
      {c.fuente === 'EXCEL' && (
        <p>Anotado en las decenas futuras del Excel{c.excel_filas > 1 ? ` (${c.excel_filas} filas)` : ''}
          {d.importaciones.find((i) => i.vigente) ? <>, importación del {fechaHora(d.importaciones.find((i) => i.vigente)!.importado_at)}</> : null}.</p>
      )}
      {c.vencimientos && (
        <>
          <p>Vencimientos de <strong>{c.vencimientos.comercial}</strong> en el sistema para esta decena: sustituyen a lo anotado en el Excel.
            Neto (cargos − abonos): <strong className="cf-num">{eurosExactos(c.vencimientos.neto)}</strong>.</p>
          <p className={c.diferencia ? 'cf-nota naranja' : 'tenue'} data-cf-comparacion={c.diferencia ? 'diferencia' : 'igual'}>
            Excel: {c.excel_filas > 0 ? eurosExactos(c.excel) : 'sin anotar'}.
            {c.diferencia ? <> <strong>Posible duplicado o diferencia</strong>{c.importe !== null && c.excel !== null ? `: ${eurosExactos(Math.round((c.importe - c.excel) * 100) / 100)} entre los dos` : ''}.</> : c.excel_filas > 0 ? ' Coinciden.' : ''}
          </p>
          <ListaVenc vs={c.vencimientos.incluidos} titulo="Suman" />
          {c.vencimientos.sin_importe > 0 && <p className="cf-nota">{plural(c.vencimientos.sin_importe, 'vencimiento sin importe', 'vencimientos sin importe')}: no suman (importe pendiente).</p>}
          <ListaVenc vs={c.vencimientos.ya_en_banco} titulo="Ya pagados antes del último saldo de banco (no suman)" />
          <ListaVenc vs={c.vencimientos.no_documentado} titulo="Sentido no documentado (no suman)" />
          <ListaVenc vs={c.vencimientos.cargo_negativo} titulo="Importe negativo: revisar (no suman)" />
        </>
      )}
      {c.media && (
        <>
          <p>Media de {plural(c.media.base.length, unidad === 'meses' ? 'mes real' : 'decena real', unidad === 'meses' ? 'meses reales' : 'decenas reales')}
            {unidad === 'meses' && c.media.decena_habitual ? <>, en la {c.media.decena_habitual}.ª decena del mes (la habitual del cobro)</> : null}:</p>
          <ul className="cf-media" data-cf-media>
            {c.media.base.map((b) => <li key={b.clave}><span>{unidad === 'meses' ? textoMes(b.clave) : textoDecenaLargo(b.clave)}</span><span className="cf-num">{eurosExactos(b.importe)}</span></li>)}
            <li className="cf-media-total"><span>Media ({c.media.base.length > 0 ? `suma ÷ ${c.media.base.length}` : 'sin datos'})</span><span className="cf-num">{eurosExactos(c.media.media)}</span></li>
          </ul>
        </>
      )}
      {c.desconocidos > 0 && !c.vencimientos && <p className="cf-nota">{plural(c.desconocidos, 'fila sin importe', 'filas sin importe')}: no suman.</p>}
    </section>
  );
}

function Desglose({ abrir, d, onCerrar }: { abrir: Abrir; d: CashflowDTO; onCerrar: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onCerrar(); };
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [onCerrar]);
  const celdas = abrir.celda.celdas.flatMap((c) => (c.partes.length ? c.partes : [c]));
  return (
    <div className="cf-velo" onClick={onCerrar}>
      <div className="cf-desglose tarjeta" role="dialog" aria-modal="true" aria-labelledby="t-cf-desglose" tabIndex={-1} ref={ref}
        onClick={(e) => { e.stopPropagation(); if ((e.target as HTMLElement).closest('a')) onCerrar(); }} data-cf-desglose>
        <header>
          <div>
            <h2 id="t-cf-desglose">{abrir.titulo}</h2>
            <span className="tenue">{textoColumnaLargo(abrir.col)} · {TEXTO_TIPO[abrir.celda.tipo]} · total {eurosExactos(abrir.celda.importe)}</span>
          </div>
          <button type="button" className="boton-secundario" onClick={onCerrar}>Cerrar</button>
        </header>
        <div className="cf-desglose-cuerpo">
          {celdas.map((c, i) => <DesgloseCelda key={i} c={c} d={d} />)}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Lo que queda fuera
// ---------------------------------------------------------------------------

function Fuera({ r }: { r: ResultadoCashflow }) {
  const f = r.fuera;
  const filas: [string, number, string][] = [
    ['sin-concepto', f.venc_sin_concepto.length, 'vencimientos de PIO sin concepto en el Excel (su proveedor no tiene correspondencia por nombre comercial)'],
    ['no-suman', f.venc_no_suman.length, 'vencimientos con concepto que no suman (ya pagados, sentido no documentado o importe negativo): cuenta el Excel'],
    ['decenas-reales', f.venc_en_decenas_reales.length, 'vencimientos sin pagar con fecha en decenas ya reales (lo real es el Excel)'],
    ['sin-fecha', f.venc_sin_fecha, 'vencimientos sin fecha'],
    ['otras-cuentas', f.filas_otras_cuentas, 'filas de otras cuentas (no PIO ni RITA)'],
    ['no-reconocidas', f.filas_no_reconocidas, `filas con categoría sin RE/RS${f.categorias_no_reconocidas.length ? `: ${f.categorias_no_reconocidas.join(', ')}` : ''}`],
    ['decena-no-valida', f.filas_decena_no_valida, 'filas con una decena no válida'],
  ];
  const visibles = filas.filter(([, n]) => n > 0);
  const proveedores = [...new Set(f.venc_sin_concepto.map((v) => v.proveedor_nombre))].sort();
  return (
    <details className="tarjeta cf-fuera" data-cf-fuera>
      <summary>Fuera de la previsión <span className="insignia n">{visibles.reduce((a, [, n]) => a + n, 0)}</span></summary>
      {visibles.length === 0 ? <p className="tenue">Nada queda fuera.</p> : (
        <ul>
          {visibles.map(([k, n, t]) => <li key={k} data-cf-fuera-item={k}><strong className="cf-num">{n}</strong> {t}</li>)}
        </ul>
      )}
      {proveedores.length > 0 && <p className="tenue">Proveedores sin correspondencia: {proveedores.join(', ')}.</p>}
    </details>
  );
}

// ---------------------------------------------------------------------------
// Página
// ---------------------------------------------------------------------------

export function PaginaCashflow() {
  const { carga, recargando, recargar } = useApiRecargable<CashflowDTO>('/api/cashflow');
  const [params, setParams] = useSearchParams();
  const movil = useMedia(MOVIL);
  const escala: Escala = params.get('escala') === 'mes' ? 'mes' : 'decenas';
  const p = params.get('cuenta');
  const vista: VistaCuenta = p === 'PIO' || p === 'RITA' ? p : 'CONSOLIDADO';
  const [elecciones, setElecciones] = useState<Record<string, Eleccion>>(leerElecciones);
  const [abrir, setAbrir] = useState<Abrir | null>(null);
  const cerrar = useCallback(() => setAbrir(null), []);
  const d = carga.estado === 'ok' ? carga.datos : null;
  const r = useMemo(() => (d ? calcularCashflow(d, elecciones) : null), [d, elecciones]);
  const cols = useMemo(() => (d ? columnasVista(d.hoy, escala, d.config) : []), [d, escala]);
  const cambiar = (k: string, valor: string | null) => {
    const n = new URLSearchParams(params);
    if (valor === null) n.delete(k); else n.set(k, valor);
    setParams(n, { replace: true });
  };
  const elegir = (categoria: string, e: Eleccion) => {
    const n = { ...elecciones, [categoria]: e };
    setElecciones(n);
    guardarElecciones(n);
  };
  const pendiente = carga.estado === 'error' && carga.mensaje === TEXTO_H7_PENDIENTE;
  const v = r?.vistas[vista] ?? null;
  const grises = r?.avisos.filter((a) => a.tipo === 'gris') ?? [];

  return (
    <>
      <Cabecera titulo="Cashflow" subtitulo={d ? `Saldo real y previsto de PIO y RITA · referencia: ${fechaCorta(d.hoy)}` : 'Saldo real y previsto de PIO y RITA'}>
        <button type="button" className="boton-secundario" onClick={recargar} disabled={recargando}>Actualizar</button>
      </Cabecera>

      {carga.estado === 'cargando' && <p className="tenue">Leyendo el cashflow…</p>}
      {pendiente && (
        <section className="tarjeta cf-pendiente" data-cf-pendiente data-contrato-ok="cashflow">
          <span className="insignia n">Solo lectura</span>
          <h2>{TEXTO_H7_PENDIENTE}</h2>
          <p>Esta pantalla leerá el Excel de cashflow que importa el circuito (importaciones, cuentas, importes por decena y saldos de banco) cuando existan sus tablas. Hasta entonces no muestra ninguna cifra.</p>
        </section>
      )}
      {carga.estado === 'error' && !pendiente && (
        <section className="tarjeta bloque error" role="alert">
          <h2>No se ha podido leer el cashflow</h2>
          <p>La API local respondió <code className="codigo">{carga.mensaje}</code>. Pulsa Actualizar para volver a intentarlo.</p>
        </section>
      )}

      {d && r && v && (
        <div className="cashflow" data-contrato-ok="cashflow" aria-busy={recargando}>
          {d.modo === 'FIXTURES' && (
            <p className="rrhh-banner" data-banner-cashflow="fixtures"><span className="rrhh-banner-marca">Ejemplo</span>Datos ficticios con la forma del Excel importado: PIO y RITA, 2026 y 2027.</p>
          )}
          {grises.map((a, i) => <p key={i} className="cf-aviso-gris" role="status" data-cf-aviso="gris" data-codigo={a.codigo}>{textoAviso(a)}</p>)}

          <Resumen r={r} d={d} />

          <div className="cf-controles">
            <div className="cf-segmento" role="group" aria-label="Escala">
              {(['decenas', 'mes'] as const).map((e) => (
                <button key={e} type="button" aria-pressed={escala === e} data-cf-escala={e} onClick={() => cambiar('escala', e === 'decenas' ? null : e)}>
                  {e === 'decenas' ? 'Decenas' : 'Mes'}
                </button>
              ))}
            </div>
            <div className="cf-segmento" role="group" aria-label="Cuenta">
              {VISTAS_CUENTA.filter((x) => r.vistas[x]).map((x) => (
                <button key={x} type="button" aria-pressed={vista === x} data-cf-cuenta={x} onClick={() => cambiar('cuenta', x === 'CONSOLIDADO' ? null : x)}>
                  {NOMBRE_VISTA[x]}
                </button>
              ))}
            </div>
            <span className="cf-leyenda-fuentes tenue">
              <span className="cf-fuente-m f-vencimientos" /> vencimientos del sistema
              <span className="cf-fuente-m f-media" /> media
              <span className="cf-fuente-m f-excel" /> Excel
              <span className="cf-dif estatico">!</span> {TEXTO_POSIBLE_DUPLICADO}
            </span>
          </div>

          <section className="tarjeta cf-bloque" aria-labelledby="t-cf-grafico">
            <h2 id="t-cf-grafico">Saldo {escala === 'mes' ? 'a fin de mes' : 'al cierre de cada decena'}</h2>
            <Grafico r={r} cols={cols} vista={vista} movil={movil} />
          </section>

          <ListaAvisos avisos={r.avisos} />

          <section className="tarjeta cf-bloque" aria-labelledby="t-cf-tabla">
            <h2 id="t-cf-tabla">{NOMBRE_VISTA[vista]}: real frente a previsto</h2>
            <p className="tenue cf-ayuda">Pulsa una cifra para ver de dónde sale. Cada categoría se despliega por concepto.</p>
            <Tabla r={r} v={v} cols={cols} elecciones={r.elecciones} onElegir={elegir} onAbrir={setAbrir} />
          </section>

          <Fuera r={r} />
          {abrir && <Desglose abrir={abrir} d={d} onCerrar={cerrar} />}
        </div>
      )}
    </>
  );
}
