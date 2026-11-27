/**
 * H7: pantalla Cashflow. Decenas (3 pasadas y 9 próximas) o meses (3 y 9); PIO, RITA o consolidado. H7-AP1: apuntes
 * manuales de la migración 40 (cashflow_apuntes.tsx): desde la celda futura de un concepto, «Añadir apunte» y la sección
 * «Apuntes manuales»; marca «a» en la celda.
 * El cálculo es el de server/cashflow/cashflow.ts: el front lo repite al cambiar «Media / Excel» (elección guardada solo
 * en este navegador). H7-REAL: importación vigente de las tablas cf_cashflow_*; sin vigente, «Todavía no hay datos
 * importados». El saldo final se abre en su desglose: banco frente a fórmulas (E7, informativa) y cuadre de control.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import type { Importe } from '../server/contrato.ts';
import { DICCIONARIO_ESTADOS } from '../server/pagos/pagos.ts';
import {
  CUENTAS_CASHFLOW, TEXTO_FUENTE, TEXTO_POSIBLE_DUPLICADO, TEXTO_SIN_DATOS, TOLERANCIA_CUADRE_POR_IMPORTE, VISTAS_CUENTA,
  avisosColumna, calcularCashflow, celdaColumna, columnasVista, finDecena, porCategoria, resumenColumna, saldoColumna, tipoColumna, totalCategoria,
  traspasosNoCompensados, variacionMensual, variacionOperativa, type TramoOperativo, type TramoVariacion,
  type AvisoCashflow, type CashflowDTO, type Celda, type CeldaColumna, type Columna, type Escala, type EstadoImportacion,
  type ResultadoCashflow, type ResultadoVista, type TipoColumna, type VencimientoCashflow, type VistaCuenta,
} from '../server/cashflow/cashflow.ts';
import { apuntesMotor, candidatosSustitucion, conceptoEnPlantilla, limiteFuturo, plantillaCuenta, primerDiaFuturo } from '../server/cashflow/apuntes.ts';
import { useApiRecargable } from './api.ts';
import { euros, fechaCorta, fechaHora, plural } from './formato.ts';
import { Cabecera, MOVIL, useMedia } from './ui.tsx';
import { Dialogo, FormularioApunte, SeccionApuntes, Sugerencia, contextoDe, type CeldaFija } from './cashflow_apuntes.tsx';

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
/** H7-REAL-8: textos de la comparación vencimientos ↔ previsión base (apunte, Excel o media). */
const TEXTO_FRENTE: Partial<Record<string, string>> = { EXCEL: 'a Excel', MEDIA: 'a la media', MANUAL: 'al apunte manual' };
const TEXTO_CUENTA: Partial<Record<string, string>> = { EXCEL: 'lo anotado en el Excel', MEDIA: 'la media del concepto', MANUAL: 'el apunte manual' };
const TEXTO_OTRA: Record<'MANUAL' | 'EXCEL' | 'MEDIA', string> = { EXCEL: 'Excel', MEDIA: 'media del concepto', MANUAL: 'apunte manual' };
/** Vencimientos de la celda con el signo de la línea (la cifra si ganaron; si no, «la otra» de la comparación). */
const vencConSigno = (c: Celda): Importe => (c.fuente === 'VENCIMIENTOS' ? c.importe : c.comparada?.fuente === 'VENCIMIENTOS' ? c.comparada.importe : null);
const TEXTO_ORIGEN: Record<string, string> = { NOCHE: 'importación nocturna', MANUAL: 'importación manual' };

// H7-REAL-9: el selector «Media / Excel» por categoría se ha retirado (la regla «gana el mayor entre Excel y media»
// aplica siempre); la elección que guardaba este navegador (cf.cashflow.eleccion.v1) ya no se lee.

// ---------------------------------------------------------------------------
// Cabecera de datos y avisos
// ---------------------------------------------------------------------------

function textoAviso(a: AvisoCashflow, imp?: EstadoImportacion): ReactNode {
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
  if (a.codigo === 'IMPORTACION_FALLIDA' && imp?.ultima) {
    return (
      <>
        La última importación del Excel falló ({fechaHora(imp.ultima.importado_at)}): <code className="codigo" data-cf-detalle-error>{imp.ultima.detalle_error ?? 'sin detalle'}</code>.{' '}
        {imp.vigente ? <>Se siguen mostrando los datos de la vigente, del {fechaHora(imp.vigente.importado_at)}.</> : 'No hay ninguna importación vigente.'}
      </>
    );
  }
  if (a.codigo === 'IMPORTACION_NO_CUADRA') {
    const MAX = 4;
    const lista = a.decenas.slice(0, MAX).map((x) => textoDecenaLargo(x.decena)).join(', ');
    return (
      <>
        Datos de la importación no cuadran en <strong>{a.cuenta}</strong>, {lista}
        {a.decenas.length > MAX ? ` y ${plural(a.decenas.length - MAX, 'decena más', 'decenas más')}` : ''}: saldo inicial + entradas − salidas no da el
        saldo de las fórmulas. La web no lo corrige; pulsa el saldo final de la decena para ver las cifras.
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
        <span className="cf-ficha-nota">{imp.vigente
          ? `${imp.vigente.archivo_nombre} · ${TEXTO_ORIGEN[imp.vigente.origen] ?? imp.vigente.origen} · hace ${plural(imp.dias ?? 0, 'día', 'días')}`
          : `Referencia ${fechaCorta(d.hoy)}`}</span>
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
  // H7-REAL-6: el ancho del dibujo es el ancho real del lienzo (1 unidad = 1 px), para que el texto del gráfico salga al
  // tamaño de --cf-tam-grafico sin encogerse ni crecer con la escala del SVG.
  const lienzo = useRef<HTMLDivElement | null>(null);
  const [medido, setMedido] = useState<number | null>(null);
  useEffect(() => {
    const el = lienzo.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const medir = () => { const w = Math.round(el.clientWidth); if (w > 0) setMedido(w); };
    medir();
    const ro = new ResizeObserver(medir);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const W = Math.max(medido ?? (movil ? 340 : 1000), movil ? 300 : 600);
  const H = movil ? 280 : 310;
  const M = { l: movil ? 64 : 92, r: movil ? 10 : 118, t: 22, b: 44 };
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
  for (let k = 1; k < finales.length; k++) if ((finales[k].yv as number) - (finales[k - 1].yv as number) < 18) finales[k].yv = (finales[k - 1].yv as number) + 18;
  const f = foco === null ? null : cols[foco];
  return (
    <div className="cf-grafico" data-cf-grafico>
      <div className="cf-leyenda" aria-hidden="true">
        {series.map((s) => <span key={s.vista} className={`cf-leyenda-serie${s.vista === vista ? ' activa' : ''}`}><span className={`cf-linea-muestra ${s.clase}`} />{NOMBRE_VISTA[s.vista]}</span>)}
        <span className="cf-leyenda-serie"><span className="cf-linea-muestra discontinua" />Previsto</span>
        <span className="cf-leyenda-serie"><span className="cf-marca-muestra naranja">▲</span>Cuenta cubierta</span>
        <span className="cf-leyenda-serie"><span className="cf-marca-muestra rojo">■</span>Consolidado en negativo</span>
      </div>
      <div className="cf-grafico-lienzo" ref={lienzo}>
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Saldo previsto por cuenta y consolidado; la tabla de abajo tiene las cifras" onMouseLeave={() => setFoco(null)}>
          {ultimoReal >= 0 && <rect className="cf-zona-real" x={M.l} y={M.t} width={(ultimoReal + 1) * ancho} height={H - M.t - M.b} />}
          {ultimoReal >= 0 && <text className="cf-zona-texto" x={M.l + 6} y={M.t + 15}>Real</text>}
          {ultimoReal < cols.length - 1 && <text className="cf-zona-texto" x={M.l + (ultimoReal + 1) * ancho + 6} y={M.t + 15}>Previsto</text>}
          {ticks.map((t) => (
            <g key={t}>
              <line className={t === 0 ? 'cf-cero' : 'cf-reja'} x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} />
              <text className="cf-eje" x={M.l - 8} y={y(t) + 5} textAnchor="end">{t === 0 ? '0 €' : cifra(t)}</text>
            </g>
          ))}
          {cols.map((c, i) => (movil && i % 3 !== 0 ? null : (
            // H7-REAL-6: a 14 px, «21–31 oct» no cabe en su columna: dos líneas (días y mes, o mes y año).
            <text key={c.clave} className={`cf-eje${c.actual ? ' actual' : ''}`} x={x(i)} y={H - M.b + 18} textAnchor="middle">
              {textoColumna(c).split(' ').map((p, k) => <tspan key={k} x={x(i)} dy={k === 0 ? 0 : 16}>{p}</tspan>)}
            </text>
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
          {finales.map((e) => <text key={e.s.vista} className={`cf-etiqueta ${e.s.clase}`} x={W - M.r + 8} y={(e.yv as number) + 5}>{NOMBRE_VISTA[e.s.vista]}</text>)}
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

/**
 * H7-REAL-4: indicador de control junto al gráfico: variación media mensual del consolidado, real (últimos 12 meses)
 * frente a prevista (12 siguientes). Si se parecen poco, la previsión merece revisión.
 */
function IndicadorVariacion({ r }: { r: ResultadoCashflow }) {
  const x = variacionMensual(r.vistas.CONSOLIDADO, r.decenas);
  // H7-REAL-10: lo que genera la farmacia sola (sin no relacionadas ni traspasos), junto al consolidado.
  const op = variacionOperativa(r.vistas.CONSOLIDADO, r.decenas);
  const conSigno = (t: { por_mes: number } | null) => (t === null ? '—' : `${t.por_mes > 0 ? '+' : ''}${eurosExactos(t.por_mes)}/mes`);
  const meses = (t: TramoVariacion | TramoOperativo | null) => (t === null ? 'sin datos' : `${String(t.meses).replace('.', ',')} meses, ${textoDecenaLargo(t.desde)} → ${textoDecenaLargo(t.hasta)}`);
  return (
    <div className="cf-indicador" data-cf-indicador>
      <span className="cf-indicador-titulo">Variación media mensual del consolidado</span>
      <span className="cf-indicador-dato" data-cf-variacion="real" title={meses(x.real)}>
        Real, últimos 12 meses <strong className="cf-num">{conSigno(x.real)}</strong>
      </span>
      <span className="cf-indicador-dato" data-cf-variacion="prevista" title={meses(x.prevista)}>
        Prevista, próximos 12 meses <strong className="cf-num">{conSigno(x.prevista)}</strong>
      </span>
      <span className="cf-indicador-titulo" data-cf-operativo-titulo>Operativo (solo farmacia)</span>
      <span className="cf-indicador-dato" data-cf-operativo="real" title={`${meses(op.real)}: cash flow generado farmacia, sin no relacionadas ni traspasos`}>
        Real <strong className="cf-num">{conSigno(op.real)}</strong>
      </span>
      <span className="cf-indicador-dato" data-cf-operativo="prevista" title={`${meses(op.prevista)}: cash flow generado farmacia, sin no relacionadas ni traspasos`}>
        Previsto <strong className="cf-num">{conSigno(op.prevista)}</strong>
      </span>
      <span className="tenue cf-indicador-nota">Si la prevista se aleja mucho de la real, revisa la previsión.</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tabla
// ---------------------------------------------------------------------------

interface Abrir {
  titulo: string; col: Columna; celda: CeldaColumna | null; externo?: boolean; incluye?: string[];
  /** H7-AP1: celda de un concepto en la vista de una cuenta: desde ella se anota un apunte manual. */
  linea?: { cuenta: VistaCuenta; categoria: string; concepto: string; incluye: string[] };
}

/** H7-AP1: popup de la marca «a»: «Apunte manual: nota · Marc · fecha». */
function textoApuntes(cs: readonly Celda[]): string {
  const xs = cs.flatMap((x) => x.apuntes.map((a) => ({ a, cuenta: x.fuente === 'MANUAL' })));
  const lineas = xs.map(({ a }) => `Apunte manual: ${a.nota ?? 'sin nota'} · ${a.autor} · ${fechaCorta(a.fecha)}`);
  return `${lineas.join('\n')}${xs.some((x) => !x.cuenta) ? '\n(ganan los vencimientos, mayores que el apunte)' : ''}`;
}

/** H7-REAL-10: popup de la marca «año»: la decena del año anterior que se usa y su importe. */
function textoAnio(cs: readonly Celda[]): string {
  return cs.filter((x) => x.media?.regla === 'ANIO_ANTERIOR').flatMap((x) => (x.media as NonNullable<Celda['media']>).base)
    .map((b) => `${textoDecenaLargo(b.clave)}, ${eurosExactos(b.importe)}`).join('; ');
}

function CeldaTabla({ c, col, titulo, onAbrir, clave, linea, previsto = false }: {
  c: CeldaColumna | null; col: Columna; titulo: string; onAbrir: (a: Abrir) => void; clave: string; linea?: Abrir['linea']; previsto?: boolean;
}) {
  if (c === null) {
    // H7-AP1: una celda vacía de un concepto, en una columna con decenas futuras, también se abre para anotar un apunte.
    if (!linea || linea.cuenta === 'CONSOLIDADO' || !previsto) return <td className={`cf-c vacia ${col.actual ? 'actual' : ''}`} />;
    return (
      <td className={`cf-c vacia ${col.actual ? 'actual' : ''}`} data-cf-celda={clave} data-cf-tipo="vacia">
        <button type="button" className="cf-cbtn cf-cbtn-vacio" onClick={() => onAbrir({ titulo, col, celda: null, linea })}
          aria-label={`${titulo} · ${textoColumnaLargo(col)}: sin movimientos`} title={`${titulo} · ${textoColumnaLargo(col)}: sin movimientos (anotar un apunte manual)`} />

      </td>
    );
  }
  const apuntes = c.celdas.flatMap((x) => x.apuntes);
  const usaMedia = c.fuentes.includes('MEDIA') && c.celdas.some((x) => x.fuente === 'MEDIA' && x.en_saldo);
  // H7-REAL-10: estimación que suma en la celda: media por posición («m») o año anterior («año»).
  const estimadas = c.celdas.filter((x) => !x.real && x.en_saldo && x.suma_media !== null);
  const conMedia = estimadas.some((x) => x.media?.regla !== 'ANIO_ANTERIOR');
  const conAnio = estimadas.some((x) => x.media?.regla === 'ANIO_ANTERIOR');
  // H7-REAL-10: en la cifra de un concepto y decena, la estimación del MES con la que se compara (regla 4), a la vista.
  const mes = c.celdas.length === 1 ? c.celdas[0].mes : null;
  const otra = mes === null ? null : { texto: mes.regla === 'ANIO_ANTERIOR' ? 'Año ant. mes' : 'Media mes', importe: mes.media };
  const fuente = c.tipo === 'real' ? 'real' : c.fuentes.includes('VENCIMIENTOS') ? 'vencimientos' : c.fuentes.includes('MANUAL') ? 'manual' : usaMedia ? 'media' : 'excel';
  return (
    <td className={`cf-c ${c.tipo} f-${fuente}${col.actual ? ' actual' : ''}`} data-cf-celda={clave} data-cf-tipo={c.tipo} data-cf-fuente={fuente}>
      <button type="button" className="cf-cbtn" onClick={() => onAbrir({ titulo, col, celda: c, linea })}
        title={`${titulo} · ${textoColumnaLargo(col)}: ${eurosExactos(c.importe)}${conMedia ? ' (incluye media calculada)' : ''}${conAnio ? ` (incluye año anterior: ${textoAnio(estimadas)})` : ''}${apuntes.length ? `\n${textoApuntes(c.celdas)}` : ''} (ver de dónde sale)`}>
        <span className="cf-linea1">
          {c.diferencia && <span className="cf-dif" title={TEXTO_POSIBLE_DUPLICADO} data-cf-diferencia>!</span>}
          {conMedia && <span className="cf-marca-media" title="Media calculada" aria-label="media" data-cf-marca-media>m</span>}
          {conAnio && <span className="cf-marca-anio" title={`Año anterior: ${textoAnio(estimadas)}`} aria-label="año anterior" data-cf-marca-anio>año</span>}
          {apuntes.length > 0 && <span className="cf-marca-apunte" title={textoApuntes(c.celdas)} aria-label="apunte manual" data-cf-marca-apunte={apuntes.length}>a</span>}
          <span className="cf-num">{c.importe === null && c.desconocidos > 0 ? 'pend.' : cifra(c.importe)}</span>
        </span>
        {c.desconocidos > 0 && <span className="cf-sub aviso">+{c.desconocidos} sin importe</span>}
        {otra !== null && <span className="cf-sub" data-cf-alt>{otra.texto} {cifra(otra.importe)}</span>}
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

function Tabla({ r, v, cols, onAbrir, onAbrirSaldo }: {
  r: ResultadoCashflow; v: ResultadoVista; cols: Columna[]; onAbrir: (a: Abrir) => void; onAbrirSaldo: (c: Columna) => void;
}) {
  const [abiertas, setAbiertas] = useState<Set<string>>(new Set());
  const grupos = porCategoria(v.lineas);
  const alternar = (c: string) => setAbiertas((s) => { const n = new Set(s); if (n.has(c)) n.delete(c); else n.add(c); return n; });
  const consolidado = v.vista === 'CONSOLIDADO';

  const bloque = (gs: typeof grupos) => gs.map((g) => {
    // H7-REAL-4: una categoría de traspasos puede salir dos veces (internos y externos): clave propia.
    const externo = g.clase === 'TRASPASO_EXTERNO';
    const k = externo ? `${g.categoria} (externo)` : g.categoria;
    const abierta = abiertas.has(k);
    const abrir = (a: Abrir) => onAbrir({ ...a, externo });
    return [
      <tr key={k} className="cf-categoria" data-cf-categoria={k}>
        <th scope="row">
          <span className="cf-cat-cabeza">
            <button type="button" className="cf-plegar" aria-expanded={abierta} onClick={() => alternar(k)} data-cf-plegar={k}>
              <span className="cf-chevron" aria-hidden="true">{abierta ? '▾' : '▸'}</span>
              {/* Fuera de la farmacia la sección ya da el nombre: Entradas / Salidas. */}
              {g.clase === 'FARMACIA' ? g.categoria.replace(/^R[ES]\s+/, '') : g.sentido === 'ENTRADA' ? 'Entradas' : 'Salidas'}
            </button>
          </span>
        </th>
        {cols.map((c) => <CeldaTabla key={c.clave} c={totalCategoria(g.lineas, c, v)} col={c} titulo={g.categoria} onAbrir={abrir} clave={`${k}|*|${c.clave}`} />)}
      </tr>,
      ...(abierta ? g.lineas.map((l) => (
        <tr key={l.clave} className={`cf-concepto${l.media ? ' media' : ''}`} data-cf-concepto={l.concepto}>
          <th scope="row"><span className="cf-concepto-nombre" title={l.incluye.length ? `${l.concepto} (incluye: ${l.incluye.join(', ')})` : l.concepto}>{l.concepto}</span></th>
          {cols.map((c) => <CeldaTabla key={c.clave} c={celdaColumna(l, c, v)} col={c} titulo={`${l.concepto} (${g.categoria})`} onAbrir={(a) => abrir({ ...a, incluye: l.incluye })} clave={`${k}|${l.concepto}|${c.clave}`}
            linea={{ cuenta: v.vista, categoria: l.categoria, concepto: l.concepto, incluye: l.incluye }} previsto={tipoColumna(v, c) !== 'real'} />)}
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
  const traspExt = grupos.filter((g) => g.clase === 'TRASPASO_EXTERNO');
  const sinCompensar = consolidado ? traspasosNoCompensados(v, cols) : [];
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
          {/* H7-REAL-4: traspasos externos (SL, fondos, valores…): entran o salen de verdad; también en el consolidado. */}
          {traspExt.length > 0 && seccion('Traspasos externos: SL, fondos, valores… (cuentan en el saldo)', 'traspasos_externos')}
          {bloque(traspExt)}
          {traspExt.length > 0 && <FilaTotal etiqueta="Total traspasos externos" v={v} cols={cols} valor={total('traspasos_externos')} datos="traspasos_externos" />}
          {!consolidado && trasp.length > 0 && seccion('Traspasos entre cuentas propias (PIO ↔ RITA)', 'traspasos')}
          {!consolidado && bloque(trasp)}
          {consolidado && (
            <tr className="cf-neutro" data-cf-traspasos-neutros>
              <th scope="row">Traspasos entre cuentas propias</th>
              <td colSpan={cols.length} className="tenue">
                Neutros en el consolidado: salen de una cuenta y entran en la otra.
                {/* H7-REAL-2: los que no se compensan (a la SL, fondos…) no son aviso: una sola línea plegada, de las decenas visibles. */}
                {sinCompensar.length > 0 && (
                  <details className="cf-traspasos-nc" data-cf-traspasos-no-compensados={sinCompensar.length}>
                    <summary>{plural(sinCompensar.length, 'decena con traspasos no compensados', 'decenas con traspasos no compensados')}</summary>
                    <ul>
                      {sinCompensar.map((x) => <li key={x.decena}><span>{textoDecenaLargo(x.decena)}</span><span className="cf-num">{eurosExactos(x.importe)}</span></li>)}
                    </ul>
                  </details>
                )}
              </td>
            </tr>
          )}
          <FilaTotal etiqueta="Saldo final" v={v} cols={cols} clase="saldo" datos="saldo" valor={(c) => {
            const s = saldoColumna(v, c);
            const negativo = s.saldo !== null && s.saldo < 0;
            const avisos = avisosColumna(r.avisos, c).filter((a) => (consolidado ? a.tipo === 'rojo' : a.cuenta === v.vista && a.tipo === 'naranja'));
            return (
              <button type="button" className="cf-cbtn cf-saldo-btn" onClick={() => onAbrirSaldo(c)}
                title={`Saldo ${textoColumnaLargo(c)}: ${eurosExactos(s.saldo)} (ver banco, fórmulas y cuadre)`}>
                <span className={`cf-saldo${negativo ? ' negativo' : ''}${avisos.length ? ` ${avisos.some((a) => a.tipo === 'rojo') ? 'rojo' : 'naranja'}` : ''}`} data-cf-saldo={c.clave}>
                  <span className="cf-num">{cifra(s.saldo)}</span>
                  {s.incompleto && <span className="cf-sub aviso" title="Hay importes pendientes: el saldo no los incluye">incompleto</span>}
                  {/* E7: diferencia informativa entre el banco y las fórmulas del Excel (nunca error). */}
                  {s.diferencia_banco !== null && <span className="cf-sub" data-cf-dif-banco>dif. banco {eurosExactos(s.diferencia_banco)}</span>}
                  {s.no_cuadra && <span className="cf-sub gris" data-cf-no-cuadra>no cuadra</span>}
                </span>
              </button>
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

const MESES_LARGOS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const textoMesLargo = (ym: string) => {
  const m = MESES_LARGOS[Number(ym.slice(5, 7)) - 1];
  return `${m[0].toUpperCase()}${m.slice(1)} de ${ym.slice(0, 4)}`;
};

/**
 * H7-REAL-10 (regla 4): lo conocido del mes (apunte, Excel o vencimientos) frente a la estimación del mes (media o año
 * anterior): gana el mayor en valor absoluto; si gana la estimación, la diferencia va a su decena habitual.
 */
function DetalleMes({ m }: { m: NonNullable<Celda['mes']> }) {
  const estim = m.regla === 'ANIO_ANTERIOR' ? 'el año anterior' : 'la media';
  return (
    <p className={`cf-nota${m.gana === 'MEDIA' ? '' : ' tenue'}`} data-cf-mes={m.gana === 'MEDIA' ? 'media' : 'conocido'}>
      {textoMesLargo(m.mes)}: conocido (Excel, apunte o vencimientos) <strong className="cf-num">{eurosExactos(Math.abs(m.conocido))}</strong>{' '}
      frente {m.regla === 'ANIO_ANTERIOR' ? 'al año anterior' : 'a la media'} del mes <strong className="cf-num">{eurosExactos(Math.abs(m.media))}</strong>
      {m.gana === 'MEDIA' && m.diferencia !== null && m.decena_diferencia !== null
        ? <> → gana {estim}: lo conocido en sus decenas y la diferencia <strong className="cf-num">{eurosExactos(Math.abs(m.diferencia))}</strong> en {textoDecenaLargo(m.decena_diferencia)}.</>
        : m.apunte
          ? <> → manda el apunte manual: sin {m.regla === 'ANIO_ANTERIOR' ? 'año anterior' : 'media'} este mes.</>
          : <> → cuenta lo conocido; sin {m.regla === 'ANIO_ANTERIOR' ? 'año anterior' : 'media'} este mes.</>}
    </p>
  );
}

function DesgloseCelda({ c, d, mostrarMes = true }: { c: Celda; d: CashflowDTO; mostrarMes?: boolean }) {
  return (
    <section className="cf-desglose-celda" data-cf-desglose-fuente={c.fuente}>
      <h3>
        {c.cuenta} · {textoDecenaLargo(c.decena)} · <span className={`cf-fuente f-${c.fuente.toLowerCase()}`}>{TEXTO_FUENTE[c.fuente]}</span>
        <span className="cf-num cf-desglose-cifra">{eurosExactos(c.importe)}</span>
      </h3>
      {/* H7-REAL-10: comparación por mes (una vez por concepto y mes en el desglose). */}
      {c.mes && mostrarMes && <DetalleMes m={c.mes} />}
      {c.suma_media !== null && c.fuente !== 'MEDIA' && (
        <p className="cf-nota" data-cf-suma-media>Incluye la diferencia de {c.media?.regla === 'ANIO_ANTERIOR' ? 'año anterior' : 'media'} del mes: <strong className="cf-num">{eurosExactos(c.suma_media)}</strong>.</p>
      )}
      {/* H7-AP1: el apunte manual manda sobre el Excel y la media; con vencimientos, gana el mayor en valor absoluto. */}
      {c.apuntes.length > 0 && (
        <>
          <p className={c.fuente === 'MANUAL' ? 'cf-nota azul' : 'cf-nota'} data-cf-apunte-manda={c.fuente === 'MANUAL' ? 'si' : 'no'}>
            {c.fuente === 'MANUAL'
              ? <>El apunte manual manda en esta decena{c.excel_filas > 0 ? <> sobre lo anotado en el Excel ({eurosExactos(c.excel)}), que no suma</> : null}.
                {c.media ? ' La media del concepto se compara con el mes entero.' : null}</>
              : <>Hay un apunte manual en esta decena, pero los vencimientos son mayores: cuentan ellos.</>}
          </p>
          <ul className="cf-venc" data-cf-apuntes>
            {c.apuntes.map((a) => (
              <li key={`${a.tipo}|${a.id}|${a.fecha}`} data-cf-apunte={a.id}>
                <span>Apunte manual: {a.nota ?? 'sin nota'} · {a.autor} · {fechaCorta(a.fecha)}</span>
                <span className="tenue">{a.tipo === 'OCURRENCIA' ? 'ocurrencia de un recurrente' : 'apunte suelto'} · creado el {fechaCorta(a.creado_at)}</span>
                <span className="cf-num">{eurosExactos((c.importe ?? c.comparada?.importe ?? 0) < 0 ? -a.importe : a.importe)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {c.fuente === 'REAL' && <p>Anotado en el Excel en una decena que ya tiene saldo de banco{c.excel_filas > 1 ? ` (${c.excel_filas} filas)` : ''}.</p>}
      {c.fuente === 'EXCEL' && (
        <p>Anotado en las decenas futuras del Excel{c.excel_filas > 1 ? ` (${c.excel_filas} filas)` : ''}
          {d.importaciones.find((i) => i.vigente) ? <>, importación del {fechaHora(d.importaciones.find((i) => i.vigente)!.importado_at)}</> : null}.</p>
      )}
      {c.vencimientos && (
        <>
          <h4 data-cf-parte="vencimientos">Vencimientos ({c.vencimientos.comercial})</h4>
          {/* H7-REAL-8: los vencimientos son un mínimo: se comparan con la previsión base (apunte, Excel o media) y gana el
              mayor en valor absoluto. Se dice qué ganó y el importe del otro. */}
          {c.fuente !== 'VENCIMIENTOS' && c.comparada?.fuente === 'VENCIMIENTOS' && (
            <p className="cf-nota" data-cf-venc-minimo={c.fuente.toLowerCase()}>
              Vencimientos conocidos <strong className="cf-num">{eurosExactos(Math.abs(c.comparada.importe))}</strong> (inferiores {TEXTO_FRENTE[c.fuente] ?? 'a la previsión'}):
              solo existen para las facturas ya recibidas, así que cuenta {TEXTO_CUENTA[c.fuente] ?? 'la previsión'}, <strong className="cf-num">{eurosExactos(c.importe === null ? null : Math.abs(c.importe))}</strong>.
            </p>
          )}
          {c.fuente === 'VENCIMIENTOS' && c.comparada && c.comparada.fuente !== 'VENCIMIENTOS' && (
            <p className="cf-nota" data-cf-venc-ganan={c.comparada.fuente.toLowerCase()}>
              Ganan los vencimientos: {TEXTO_OTRA[c.comparada.fuente]} <strong className="cf-num">{eurosExactos(Math.abs(c.comparada.importe))}</strong> (inferior a los vencimientos).
            </p>
          )}
          <p>Vencimientos de <strong>{c.vencimientos.comercial}</strong> en el sistema para esta decena: se comparan con la previsión del concepto (apunte, Excel o media, la primera que haya) y cuenta la mayor.
            Neto (cargos − abonos): <strong className="cf-num">{eurosExactos(c.vencimientos.neto)}</strong>.</p>
          <p className={c.diferencia ? 'cf-nota naranja' : 'tenue'} data-cf-comparacion={c.diferencia ? 'diferencia' : 'igual'}>
            Excel: {c.excel_filas > 0 ? eurosExactos(c.excel) : 'sin anotar'}.
            {c.diferencia ? <> <strong>Posible duplicado o diferencia</strong>{vencConSigno(c) !== null && c.excel !== null ? `: ${eurosExactos(Math.round(((vencConSigno(c) as number) - c.excel) * 100) / 100)} entre los dos` : ''}.</> : c.excel_filas > 0 ? ' Coinciden.' : ''}
          </p>
          <ListaVenc vs={c.vencimientos.incluidos} titulo="Suman" />
          {c.vencimientos.sin_importe > 0 && <p className="cf-nota">{plural(c.vencimientos.sin_importe, 'vencimiento sin importe', 'vencimientos sin importe')}: no suman (importe pendiente).</p>}
          <ListaVenc vs={c.vencimientos.ya_en_banco} titulo="Ya pagados antes del último saldo de banco (no suman)" />
          <ListaVenc vs={c.vencimientos.no_documentado} titulo="Sentido no documentado (no suman)" />
          <ListaVenc vs={c.vencimientos.cargo_negativo} titulo="Importe negativo: revisar (no suman)" />
        </>
      )}
      {c.media && c.apuntes.length === 0 && (
        <>
          {c.media.excluidos.length > 0 && (
            <>
              <h4 data-cf-parte="media-resto">Media del resto</h4>
              <p data-cf-excluidos>Sin {c.media.excluidos.join(', ')}: esta decena ya los prevé (vencimientos o Excel), así que no entran en la media.</p>
            </>
          )}
          {c.media.regla === 'ANIO_ANTERIOR'
            ? (c.media.motivo === 'ESPORADICO'
              ? <p data-cf-regla="anio_anterior" data-cf-motivo="esporadico">Año anterior: concepto esporádico (movimiento en {plural(c.media.meses_con_movimiento, 'mes', 'meses')} de los últimos 12): la misma decena del mismo mes del año anterior, no la media.</p>
              : <p data-cf-regla="anio_anterior" data-cf-motivo="modelo">Año anterior: impuesto trimestral («RS Modelo …»): la misma decena del mismo mes del año anterior, no la media.</p>)
            : (
              <>
                {/* H7-REAL-8: ventana de la media (decisión de Pío, 25/11/2026). */}
                <p className="cf-media-ventana" data-cf-media-ventana={c.media.base.length}>
                  <strong>Media de {c.media.base.length} {c.media.base.length === 1 ? 'mes' : 'meses'} (misma decena)</strong>
                </p>
                <p data-cf-regla="posicion">Media del concepto en la {c.media.posicion}.ª decena del mes en {c.media.base.length === 1 ? 'el último mes real' : `los últimos ${c.media.base.length} meses reales`}:</p>
              </>
            )}
          <ul className="cf-media" data-cf-media>
            {c.media.base.map((b) => <li key={b.clave}><span>{textoDecenaLargo(b.clave)}</span><span className="cf-num">{eurosExactos(b.importe)}</span></li>)}
            <li className="cf-media-total">
              <span>{c.media.regla === 'ANIO_ANTERIOR' ? 'Año anterior' : `Media (suma ÷ ${c.media.base.length})`}</span>
              <span className="cf-num">{eurosExactos(c.media.media)}</span>
            </li>
          </ul>
          {c.media.sin_importe > 0 && <p className="cf-nota">{plural(c.media.sin_importe, 'fila sin importe', 'filas sin importe')} en esas decenas: no suman en la media.</p>}
        </>
      )}
      {c.desconocidos > 0 && !c.vencimientos && <p className="cf-nota">{plural(c.desconocidos, 'fila sin importe', 'filas sin importe')}: no suman.</p>}
    </section>
  );
}

/**
 * H7-AP1: panel «Apunte manual» de la celda de un concepto (vista PIO o RITA) en una columna con decenas futuras: fecha
 * dentro de la columna y después del último saldo de banco. El concepto tiene que estar en la plantilla del Excel o
 * entre los conceptos nuevos (si la línea suma conceptos equivalentes, el primero que esté).
 */
function PanelApunte({ abrir, d, onCambio }: { abrir: Abrir; d: CashflowDTO; onCambio: (texto: string) => void }) {
  const l = abrir.linea;
  if (!l || l.cuenta === 'CONSOLIDADO') return null;
  const limite = limiteFuturo(d, l.cuenta);
  const desde = limite === null ? null : [primerDiaFuturo(limite), abrir.col.desde].sort()[1];
  if (desde === null || desde > abrir.col.hasta) return null; // columna ya real: lo real es el Excel
  const pl = plantillaCuenta(d, d.previsiones, l.cuenta);
  const concepto = [l.concepto, ...l.incluye].map((x) => conceptoEnPlantilla(pl, l.categoria, x)).find((x) => x !== null) ?? null;
  const fija: CeldaFija | null = concepto === null ? null : {
    cuenta: l.cuenta, categoria: l.categoria, concepto, desde, hasta: abrir.col.hasta,
    texto: abrir.col.escala === 'decenas' ? `la decena ${textoDecenaLargo(abrir.col.clave)}` : `el mes ${textoColumnaLargo(abrir.col)}`,
  };
  return (
    <section className="cf-desglose-celda ap-panel" data-ap-panel>
      <h3>Apunte manual <span className="tenue">· manda sobre el Excel y la media de este concepto</span></h3>
      {fija === null
        ? <p className="cf-nota" data-ap-panel-sin-plantilla>Este concepto no está en la plantilla del Excel vigente: usa «Añadir apunte» con un concepto nuevo.</p>
        : <FormularioApunte d={d} fija={fija} onHecho={onCambio} />}
    </section>
  );
}

function Desglose({ abrir, d, onCerrar, onCambio }: { abrir: Abrir; d: CashflowDTO; onCerrar: () => void; onCambio: (texto: string) => void }) {
  const celdas = (abrir.celda?.celdas ?? []).flatMap((c) => (c.partes.length ? c.partes : [c]));
  // H7-AP1: facturas que pueden sustituir a un apunte de esta celda.
  const ids = new Set(celdas.flatMap((c) => c.apuntes.map((a) => `${a.tipo}|${a.id}|${a.fecha}`)));
  const sugerencias = ids.size === 0 ? [] : candidatosSustitucion(contextoDe(d), d.vencimientos)
    .filter((c) => ids.has(c.tipo === 'SUELTO' ? `SUELTO|${c.apunte_id}|${c.fecha}` : `OCURRENCIA|${c.recurrente_id}|${c.fecha}`));
  const subtitulo = abrir.celda === null ? `${textoColumnaLargo(abrir.col)} · sin movimientos`
    : `${textoColumnaLargo(abrir.col)} · ${TEXTO_TIPO[abrir.celda.tipo]} · total ${eurosExactos(abrir.celda.importe)}`;
  return (
    <Dialogo titulo={abrir.titulo} subtitulo={subtitulo} onCerrar={onCerrar}>
      {abrir.externo && (
        <p className="cf-nota naranja" data-cf-traspaso-externo>
          <strong>Traspaso externo</strong> (SL, fondos, valores…): no es entre PIO y RITA, así que es una entrada o salida real y cuenta en el saldo de la cuenta y en el consolidado.
        </p>
      )}
      {/* H7-REAL-7: cifra que suma conceptos del Excel equivalentes (decisión de Pío, 25/11/2026). */}
      {abrir.incluye && abrir.incluye.length > 0 && (
        <p className="cf-nota" data-cf-incluye={abrir.incluye.join('|')}>
          Incluye: {abrir.incluye.join(', ')} (mismo proveedor en el Excel con otro nombre).
        </p>
      )}
      {celdas.map((c, i) => (
        <DesgloseCelda key={i} c={c} d={d}
          mostrarMes={c.mes === null || celdas.findIndex((x) => x.mes === c.mes) === i} />
      ))}
      {sugerencias.length > 0 && (
        <section className="cf-desglose-celda" data-ap-sugerencias-celda={sugerencias.length}>
          <h3>Factura que coincide con el apunte</h3>
          <ul className="ap-lista">{sugerencias.map((c) => <Sugerencia key={c.clave} c={c} d={d} onHecho={onCambio} />)}</ul>
        </section>
      )}
      <PanelApunte abrir={abrir} d={d} onCambio={onCambio} />
    </Dialogo>
  );
}

/** H7-REAL: saldo de una decena de una cuenta: banco frente a fórmulas (E7) y cuadre de control de la importación. */
function DesgloseSaldoDecena({ v, d }: { v: ResultadoVista; d: string }) {
  const x = v.decenas[d];
  if (!x) return null;
  const q = x.cuadre;
  const fila = (etiqueta: ReactNode, valor: ReactNode, clase = '') => <li className={clase}><span>{etiqueta}</span><span className="cf-num">{valor}</span></li>;
  return (
    <section className="cf-desglose-celda" data-cf-desglose-saldo={`${v.vista}|${d}`}>
      <h3>
        {v.vista} · {textoDecenaLargo(d)} · <span className="cf-fuente">{x.real ? 'Real' : 'Previsto'}</span>
        <span className="cf-num cf-desglose-cifra">{eurosExactos(x.saldo)}</span>
      </h3>
      <p className="tenue">{x.real ? 'Saldo real: el del banco.' : 'Saldo previsto: el anterior más entradas menos salidas de la previsión.'}</p>
      <ul className="cf-media">
        {fila('Saldo del banco', x.saldo_bancos === null ? 'aún no cuadrada con el banco' : eurosExactos(x.saldo_bancos))}
        {fila('Saldo según las fórmulas del Excel', eurosExactos(x.saldo_formulas))}
      </ul>
      {x.diferencia_banco !== null && (
        <p className="cf-nota" data-cf-e7>
          Diferencia banco − fórmulas: <strong className="cf-num">{eurosExactos(x.diferencia_banco)}</strong>. Es informativa: el saldo real es el del banco.
        </p>
      )}
      <h4>Cuadre de la importación</h4>
      {q === null ? <p className="tenue" data-cf-cuadre="sin-datos">Sin datos para comprobarlo (falta el saldo inicial, el de las fórmulas o algún importe).</p> : (
        <>
          <ul className="cf-media" data-cf-cuadre={q.cuadra ? 'cuadra' : 'no-cuadra'}>
            {fila('Saldo inicial', eurosExactos(q.saldo_inicial))}
            {fila('+ Entradas (RE)', eurosExactos(q.entradas))}
            {fila('− Salidas (RS)', eurosExactos(q.salidas))}
            {fila('= Resultado', eurosExactos(q.esperado), 'cf-media-total')}
            {fila('Saldo de las fórmulas', eurosExactos(q.saldo_formulas))}
          </ul>
          {q.cuadra
            ? <p className="tenue">Cuadra ({plural(q.filas, 'importe', 'importes')}; tolerancia {String(TOLERANCIA_CUADRE_POR_IMPORTE).replace('.', ',')} € por importe).</p>
            : <p className="cf-nota" data-cf-no-cuadra-detalle>Datos de la importación no cuadran: diferencia de <strong className="cf-num">{eurosExactos(q.diferencia)}</strong>. La web no lo corrige.</p>}
        </>
      )}
    </section>
  );
}

function DesgloseSaldo({ r, vista, col, onCerrar }: { r: ResultadoCashflow; vista: VistaCuenta; col: Columna; onCerrar: () => void }) {
  const cuentas = vista === 'CONSOLIDADO' ? CUENTAS_CASHFLOW.filter((c) => r.vistas[c]) : [vista];
  const s = saldoColumna(r.vistas[vista], col);
  return (
    <Dialogo titulo={`Saldo final ${NOMBRE_VISTA[vista]}`} subtitulo={`${textoColumnaLargo(col)} · ${TEXTO_TIPO[tipoColumna(r.vistas[vista], col)]} · ${eurosExactos(s.saldo)}`}
      onCerrar={onCerrar} datos="saldo">
      {cuentas.flatMap((c) => col.decenas.map((d) => <DesgloseSaldoDecena key={`${c}|${d}`} v={r.vistas[c]} d={d} />))}
    </Dialogo>
  );
}

// ---------------------------------------------------------------------------
// Lo que queda fuera
// ---------------------------------------------------------------------------

function Fuera({ r }: { r: ResultadoCashflow }) {
  const f = r.fuera;
  const filas: [string, number, string][] = [
    ['cuentas-fuera', f.cuentas_fuera.length, `${f.cuentas_fuera.length === 1 ? 'cuenta' : 'cuentas'} fuera de la pantalla: ${f.cuentas_fuera.join(', ')}`
      + (f.filas_otras_cuentas > 0 ? ` (${plural(f.filas_otras_cuentas, 'fila', 'filas')} en la importación vigente, no se suman)` : ' (sin filas en la importación vigente)')],
    ['sin-concepto', f.venc_sin_concepto.length, 'vencimientos de PIO sin concepto en el Excel (su proveedor no tiene correspondencia por nombre comercial)'],
    ['no-suman', f.venc_no_suman.length, 'vencimientos con concepto que no suman (ya pagados, sentido no documentado o importe negativo): cuenta el Excel'],
    ['decenas-reales', f.venc_en_decenas_reales.length, 'vencimientos sin pagar con fecha en decenas ya reales (lo real es el Excel)'],
    ['sin-fecha', f.venc_sin_fecha, 'vencimientos sin fecha'],
    ['otra-importacion', f.filas_otra_importacion, 'filas de una importación que no es la vigente (no se usan)'],
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
  const [abrir, setAbrir] = useState<Abrir | null>(null);
  const [abrirSaldo, setAbrirSaldo] = useState<Columna | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const cerrar = useCallback(() => setAbrir(null), []);
  const cerrarSaldo = useCallback(() => setAbrirSaldo(null), []);
  // H7-AP1: tras guardar o anular un apunte: se cierra el desglose, se relee y el aviso queda en «Apuntes manuales».
  const cambio = useCallback((texto: string) => { setAbrir(null); setAviso(texto); recargar(); }, [recargar]);
  const d = carga.estado === 'ok' ? carga.datos : null;
  // H7-AP1: los apuntes manuales (sueltos y ocurrencias) entran en el motor: mandan sobre el Excel y la media.
  const r = useMemo(() => (d ? calcularCashflow({ ...d, apuntes_manuales: apuntesMotor(d.previsiones) }) : null), [d]);
  const cols = useMemo(() => (d ? columnasVista(d.hoy, escala, d.config) : []), [d, escala]);
  const cambiar = (k: string, valor: string | null) => {
    const n = new URLSearchParams(params);
    if (valor === null) n.delete(k); else n.set(k, valor);
    setParams(n, { replace: true });
  };
  const v = r?.vistas[vista] ?? null;
  // Sin importación vigente: ninguna cifra («Todavía no hay datos importados»); sí el aviso de una ERROR.
  const sinDatos = r !== null && r.importacion.vigente === null;
  const grises = r?.avisos.filter((a) => a.tipo === 'gris' && !(sinDatos && a.codigo === 'SIN_IMPORTACION_VIGENTE')) ?? [];
  const avisosGrises = grises.map((a, i) => (
    <p key={i} className="cf-aviso-gris" role="status" data-cf-aviso="gris" data-codigo={a.codigo}>{textoAviso(a, r?.importacion)}</p>
  ));

  return (
    <>
      <Cabecera titulo="Cashflow" subtitulo={d ? `Saldo real y previsto de PIO y RITA · referencia: ${fechaCorta(d.hoy)}` : 'Saldo real y previsto de PIO y RITA'}>
        <button type="button" className="boton-secundario" onClick={recargar} disabled={recargando}>Actualizar</button>
      </Cabecera>

      {carga.estado === 'cargando' && <p className="tenue">Leyendo el cashflow…</p>}
      {d && sinDatos && (
        <div className="cashflow" data-contrato-ok="cashflow">
          {avisosGrises}
          <section className="tarjeta cf-pendiente" data-cf-sin-datos>
            <span className="insignia n">Solo lectura</span>
            <h2>{TEXTO_SIN_DATOS}</h2>
            <p>Esta pantalla muestra el Excel de cashflow que importa el circuito (por la noche o a mano). Cuando haya una importación correcta, aparecerán aquí los saldos reales y la previsión.</p>
          </section>
        </div>
      )}
      {carga.estado === 'error' && (
        <section className="tarjeta bloque error" role="alert">
          <h2>No se ha podido leer el cashflow</h2>
          <p>La API local respondió <code className="codigo">{carga.mensaje}</code>. Pulsa Actualizar para volver a intentarlo.</p>
        </section>
      )}

      {d && r && v && !sinDatos && (
        <div className="cashflow" data-contrato-ok="cashflow" aria-busy={recargando}>
          {d.modo === 'FIXTURES' && (
            <p className="rrhh-banner" data-banner-cashflow="fixtures"><span className="rrhh-banner-marca">Ejemplo</span>Datos ficticios con la forma del Excel importado: PIO y RITA, 2026 y 2027.</p>
          )}
          {avisosGrises}

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
              <span className="cf-fuente-m f-manual" /> <span className="cf-marca-apunte estatico" data-cf-leyenda-apunte>a</span> apunte manual
              <span className="cf-fuente-m f-media" /> <span className="cf-marca-media estatico">m</span> media
              {' '}<span className="cf-marca-anio estatico" data-cf-leyenda-anio>año</span> año anterior
              <span className="cf-fuente-m f-excel" /> Excel
              <span className="cf-dif estatico">!</span> {TEXTO_POSIBLE_DUPLICADO}
            </span>
          </div>

          <section className="tarjeta cf-bloque" aria-labelledby="t-cf-grafico">
            <h2 id="t-cf-grafico">Saldo {escala === 'mes' ? 'a fin de mes' : 'al cierre de cada decena'}</h2>
            <Grafico r={r} cols={cols} vista={vista} movil={movil} />
            <IndicadorVariacion r={r} />
          </section>

          <ListaAvisos avisos={r.avisos} />

          <section className="tarjeta cf-bloque" aria-labelledby="t-cf-tabla">
            <h2 id="t-cf-tabla">{NOMBRE_VISTA[vista]}: real frente a previsto</h2>
            <p className="tenue cf-ayuda">Pulsa una cifra para ver de dónde sale. Cada categoría se despliega por concepto; en PIO o RITA, la celda futura de un concepto permite anotar un apunte manual.</p>
            <Tabla v={v} cols={cols} onAbrir={setAbrir} onAbrirSaldo={setAbrirSaldo} r={r} />
          </section>

          <SeccionApuntes d={d} aviso={aviso} onCambio={cambio} />
          <Fuera r={r} />
          {abrir && <Desglose abrir={abrir} d={d} onCerrar={cerrar} onCambio={cambio} />}
          {abrirSaldo && <DesgloseSaldo r={r} vista={vista} col={abrirSaldo} onCerrar={cerrarSaldo} />}
        </div>
      )}
    </>
  );
}
