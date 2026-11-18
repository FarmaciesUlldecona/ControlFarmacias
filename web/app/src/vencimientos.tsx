// H6: pantalla Vencimientos (maqueta web/docs/maquetas/Vencimientos.dc.html) sobre /api/pagos/vencimientos.
// Una fila por vencimiento con su estado de pago, forma de pago por proveedor (CIF) y marca manual. Filtros en la URL.
// Marcar, confirmar domiciliados, anular y editar la forma de pago: FIXTURES en memoria; H6-REAL en Supabase (cf_pagos_web).
// En REAL sin la credencial de pagos, solo lectura: los botones quedan deshabilitados con «Falta configurar la credencial
// de pagos». El vencimiento se identifica por (factura, orden). H6-REAL: estado «a revisar» (naranja) y marcas huérfanas.
// Importe ausente = «importe pendiente» (nunca 0), fuera de los totales y con su recuento a la vista.
// H6-4: calendario sobre la lista (calendario_vencimientos.tsx); sin tarjetas de totales por semana y mes (queda la
// cabecera de totales generales); la lista con las capacidades de Facturas (pestañas, filtros, búsqueda también por
// importe, orden por columna) más los filtros de H6. Filtros, orden y vista del calendario en la URL.
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  OPCIONES_CONCILIACION, OPCIONES_NORMALIZACION, OPCIONES_REVISION, etiquetaConciliacion, etiquetaNormalizacion, etiquetaRevision,
} from '../server/detalle.ts';
import {
  VISTA_POR_DEFECTO, cumpleCalendario, esVista, leerFiltroCalendario, valorFiltroCalendario,
  type FiltroCalendario, type VistaCalendario,
} from '../server/pagos/calendario.ts';
import {
  COLUMNAS_LISTA, COLUMNA_POR_DEFECTO, IMPORTES_LISTA, PESTANAS_VENCIMIENTOS, claveProveedor, columnaDe, cumpleBusquedaLista,
  cumpleEstadoFactura, cumpleImporte, direccionDe, opcionesProveedor, ordenar, pestanaDe,
} from '../server/pagos/lista.ts';
import {
  DICCIONARIO_ESTADOS, ESTADOS_IMPLEMENTADOS, FORMAS_PAGO, PERIODOS, TEXTO_CARGO_NEGATIVO, TEXTO_FORMA, TEXTO_NO_MARCABLE, TEXTO_NO_MARCABLE_PLURAL, TEXTO_SENTIDO,
  cumplePeriodo, esFechaIso, formaPorDefectoMarca, textoEstadoPago, totalGeneral,
  type BloqueTotal, type ColorEstadoPago, type EventoPagoVista, type FilaVencimientoPago, type MarcaHuerfana, type MarcaVista,
  type FormaEfectiva, type FormaPago, type MotivoNoMarcable, type PantallaVencimientosDTO, type ProveedorPagoVista, type TotalPeriodo,
} from '../server/pagos/pagos.ts';
import { ErrorApi, enviar, useApiRecargable } from './api.ts';
import { CalendarioVencimientos, textoFiltroCalendario } from './calendario_vencimientos.tsx';
import { euros, fechaCorta, fechaHora, plural } from './formato.ts';
import { Cabecera, MOVIL, NombreProveedor, useMedia } from './ui.tsx';

const CLASE_ESTADO: Record<ColorEstadoPago, string> = { azul: 'b', rojo: 'r', verde: 'g', gris: 'n', domiciliado: 'd', naranja: 'o' };
/** Clave de selección: (factura, orden); un vencimiento sin orden se puede seleccionar, pero no marcar. */
const sel = (f: FilaVencimientoPago) => f.clave ?? `sin-orden:${f.vencimiento_id}`;
/** Lo que se envía al marcar: nunca el id del vencimiento. */
const idDe = (f: FilaVencimientoPago) => ({ factura_id: f.factura_id, orden: f.orden as number });
const TEXTO_DIFERENCIA = { FECHA: 'la fecha', IMPORTE: 'el importe' } as const;
/** Filtros de la lista (todos en la URL; «Quitar filtros» los borra). Los de fecha no se aplican al calendario. */
const CLAVES_FILTRO = ['pestana', 'periodo', 'desde', 'hasta', 'cal', 'estado', 'forma', 'proveedor', 'sentido', 'importe', 'factura', 'revision', 'q'] as const;
type Filtros = Record<(typeof CLAVES_FILTRO)[number], string>;

const DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
const diaSemana = (iso: string) => DIAS[new Date(`${iso}T00:00:00Z`).getUTCDay()];

/** true si la fila pasa los filtros de la lista; `sinFecha`: sin los filtros de fecha (para el calendario). */
function cumpleFiltros(f: FilaVencimientoPago, x: Filtros, hoy: string, cal: FiltroCalendario | null, o: { sinFecha?: boolean; sinEstado?: boolean } = {}): boolean {
  if (!pestanaDe(x.pestana || null).cumple(f)) return false;
  if (!o.sinFecha && (!cumplePeriodo(f, x.periodo, hoy, { desde: x.desde, hasta: x.hasta }) || !cumpleCalendario(f, cal))) return false;
  if (!o.sinEstado && x.estado !== '' && f.estado_pago !== x.estado) return false;
  if (x.forma !== '' && f.forma_pago !== x.forma) return false;
  if (x.proveedor !== '' && claveProveedor(f) !== x.proveedor) return false;
  if (x.sentido !== '' && f.sentido !== x.sentido) return false;
  if (!cumpleImporte(f.importe, x.importe)) return false;
  if (!cumpleEstadoFactura(f, x.factura)) return false;
  if (x.revision !== '' && f.estado_revision !== x.revision) return false;
  return cumpleBusquedaLista(f, x.q);
}

function textoError(e: unknown, defecto: string): string {
  if (e instanceof ErrorApi) {
    if (e.mensaje) return e.mensaje;
    const campos = Object.values(e.errores);
    if (campos.length) return campos.join('. ');
  }
  return defecto;
}

// ---------------------------------------------------------------------------
// Piezas
// ---------------------------------------------------------------------------

function EstadoInsignia({ f }: { f: FilaVencimientoPago }) {
  const d = DICCIONARIO_ESTADOS[f.estado_pago];
  return <span className={`insignia ${CLASE_ESTADO[d.color]}`} data-estado-pago={f.estado_pago}>{textoEstadoPago(f.estado_pago, f.sentido)}</span>;
}

function Importe({ f }: { f: FilaVencimientoPago }) {
  const t = euros(f.importe);
  if (t === null) return <span className="desconocido" data-importe-pendiente>importe pendiente</span>;
  // H6-3: cargo con importe negativo: se muestra tal cual, con aviso, y no suma en los totales.
  return f.cargo_negativo
    ? <span className="ve-importe-negativo">{t}<span className="nota-celda ve-aviso-negativo" data-cargo-negativo>{TEXTO_CARGO_NEGATIVO}</span></span>
    : <>{t}</>;
}

function Sentido({ f }: { f: FilaVencimientoPago }) {
  return f.sentido === 'NO_DOCUMENTADO'
    ? <span className="insignia o" data-sentido={f.sentido} title="Sentido no documentado: no suma como cargo ni como abono">{TEXTO_SENTIDO[f.sentido].toLowerCase()}</span>
    : <span className={`ve-sentido ${f.sentido === 'ABONO' ? 'abono' : ''}`} data-sentido={f.sentido}>{TEXTO_SENTIDO[f.sentido]}</span>;
}

function Forma({ f }: { f: FilaVencimientoPago }) {
  return (
    <span className="ve-forma" data-forma={f.forma_pago}>
      {TEXTO_FORMA[f.forma_pago]}
      {f.forma_por_defecto && <span className="nota-celda">por defecto</span>}
      {f.sin_cif && <span className="nota-celda ve-sin-cif" data-sin-cif>sin CIF · se trata como transferencia</span>}
    </span>
  );
}

/** H6-REAL: qué ha cambiado desde que se marcó (marca «a revisar»): lo que tenía el vencimiento al marcarlo. */
function NotaRevisar({ m }: { m: MarcaVista }) {
  if (m.diferencias.length === 0) return null;
  const que = m.diferencias.map((d) => TEXTO_DIFERENCIA[d]).join(' y ');
  return (
    <span className="nota-celda ve-revisar" data-revisar={m.diferencias.join(',')}>
      Ha cambiado {que} desde que se marcó (entonces: vto. {fechaCorta(m.fecha_vencimiento)}, {euros(m.importe)}). No cuenta como pagado.
    </span>
  );
}

/** Anular una marca con confirmación (también las «a revisar» y las huérfanas). */
function AnularMarca({ m, nombre, disponible, motivo, clave, onAnular }: {
  m: MarcaVista; nombre: string; disponible: boolean; motivo: string | null; clave: string; onAnular: () => Promise<void>;
}) {
  const [confirmar, setConfirmar] = useState(false);
  if (!confirmar) {
    return (
      <button type="button" className="ve-enlace-boton" disabled={!disponible} title={disponible ? undefined : motivo ?? undefined}
        onClick={() => setConfirmar(true)} data-anular-marca={clave}>Anular marca</button>
    );
  }
  return (
    <span className="ve-confirmar" role="alertdialog" aria-label={`Anular la marca de pago de ${nombre}`} data-confirmar-anular={clave} data-marca-anular={m.marca_id}>
      <span>¿Anular la marca? Queda en el historial (no se borra).</span>
      <span className="ve-confirmar-botones">
        <button type="button" className="boton-peligro boton-mini" onClick={() => void onAnular().then(() => setConfirmar(false))} data-anular-si>Sí, anular</button>
        <button type="button" className="boton-secundario boton-mini" onClick={() => setConfirmar(false)}>Cancelar</button>
      </span>
    </span>
  );
}

function Estado({ f, d, onAnular }: { f: FilaVencimientoPago; d: PantallaVencimientosDTO; onAnular: (f: FilaVencimientoPago) => Promise<void> }) {
  const m = f.marca;
  return (
    <span className="ve-estado">
      <EstadoInsignia f={f} />
      {m && (
        <>
          <span className="nota-celda" data-marca={m.marca_id}>{fechaCorta(m.fecha_pago)} · {TEXTO_FORMA[m.forma]}{m.origen === 'DOMICILIADOS' ? ' · domiciliado confirmado' : ''}</span>
          <NotaRevisar m={m} />
          <AnularMarca m={m} nombre={f.numero_factura ?? 'la factura'} disponible={d.marcas_disponibles} motivo={d.mensaje_escritura}
            clave={f.vencimiento_id} onAnular={() => onAnular(f)} />
        </>
      )}
      {!m && f.no_marcable && <span className="nota-celda ve-no-marcable" data-no-marcable={f.no_marcable}>{TEXTO_NO_MARCABLE[f.no_marcable]}</span>}
    </span>
  );
}

function Proveedor({ f }: { f: FilaVencimientoPago }) {
  return <NombreProveedor comercial={f.proveedor_comercial} razon={f.proveedor_razon_social} respaldo={f.proveedor} />;
}

function Factura({ f }: { f: FilaVencimientoPago }) {
  return (
    <span className="ve-factura">
      <Link to={`/facturas/${f.factura_id}`} className="enlace-factura">{f.numero_factura ?? '(sin número)'}</Link>
      {f.vencimientos_factura > 1 && <span className="nota-celda">vencimiento {f.orden ?? '?'} de {f.vencimientos_factura}</span>}
    </span>
  );
}

function Casilla({ f, marcada, onCambio }: { f: FilaVencimientoPago; marcada: boolean; onCambio: (id: string) => void }) {
  return (
    <input type="checkbox" className="ve-casilla" checked={marcada} onChange={() => onCambio(sel(f))}
      aria-label={`Seleccionar ${f.numero_factura ?? 'factura sin número'}, vencimiento ${fechaCorta(f.fecha_vencimiento)}`} data-seleccionar={f.vencimiento_id} />
  );
}

// ---------------------------------------------------------------------------
// Totales
// ---------------------------------------------------------------------------

function Cifra({ etiqueta, b, clase, datos }: { etiqueta: string; b: BloqueTotal; clase: string; datos: string }) {
  return (
    <div className={`ve-cifra ${clase}`} data-total={datos}>
      <span className="ve-cifra-etiqueta">{etiqueta}</span>
      <span className="ve-cifra-n">{b.neto === null ? <span className="tenue">—</span> : euros(b.neto)}</span>
      {b.abonos !== null && (
        <span className="ve-cifra-nota">{b.cargos !== null ? `${euros(b.cargos)} cargos − ${euros(Math.abs(b.abonos))} abonos` : `solo abonos: ${euros(Math.abs(b.abonos))}`}</span>
      )}
    </div>
  );
}

function NotasTotal({ t }: { t: Omit<TotalPeriodo, 'clave' | 'desde' | 'hasta'> }) {
  const notas = [
    t.pagado.vencimientos ? `pagado ${euros(t.pagado.neto)} (${t.pagado.vencimientos})` : null,
    t.sin_importe ? plural(t.sin_importe, 'importe pendiente', 'importes pendientes') : null,
    t.sentido_no_documentado ? `${t.sentido_no_documentado} de sentido no documentado` : null,
    t.cargo_negativo ? plural(t.cargo_negativo, 'cargo con importe negativo', 'cargos con importe negativo') : null,
  ].filter(Boolean);
  return notas.length ? <span className="ve-total-notas" data-notas-total>{notas.join(' · ')}</span> : null;
}

/**
 * H6-4: solo la cabecera de totales generales de lo filtrado (sin tarjetas por semana ni por mes). H6-6: por estado,
 * como el resumen del calendario: Falta por pagar (pendiente, también domiciliado no vencido, + vencido sin pagar),
 * Domiciliado previsto (solo domiciliado ya vencido) y Abonos por compensar aparte (si hay); pagado en las notas.
 * H6-REAL: A revisar aparte (si hay).
 */
function Totales({ filas }: { filas: FilaVencimientoPago[] }) {
  const g = totalGeneral(filas);
  const hayAbonos = filas.some((f) => f.estado_pago === 'ABONO_PENDIENTE_COMPENSAR');
  const hayRevisar = filas.some((f) => f.estado_pago === 'A_REVISAR');
  return (
    <section className="ve-totales" aria-label="Totales de lo filtrado">
      <div className="ve-total-general tarjeta" data-total-general>
        <span className="ve-total-titulo">Todo lo filtrado <span className="tenue">· {plural(g.vencimientos, 'vencimiento', 'vencimientos')}</span></span>
        <div className="ve-cifras">
          <Cifra etiqueta="Falta por pagar" b={g.por_pagar} clase="por-pagar" datos="por_pagar" />
          <Cifra etiqueta="Domiciliado previsto" b={g.domiciliado} clase="domiciliado" datos="domiciliado" />
          {hayAbonos && <Cifra etiqueta="Abonos por compensar" b={g.abonos} clase="abonos" datos="abonos" />}
          {/* H6-REAL: marcas que ya no coinciden con su vencimiento: aparte, nunca como pagado. */}
          {hayRevisar && <Cifra etiqueta="A revisar" b={g.revisar} clase="revisar" datos="revisar" />}
        </div>
        <NotasTotal t={g} />
      </div>
    </section>
  );
}

function Selector({ nombre, etiqueta, valor, onChange, opciones, todos }: {
  nombre: string; etiqueta: string; valor: string; onChange: (v: string) => void;
  opciones: { valor: string; texto: string; grupo?: string }[]; todos: string;
}) {
  const grupos = [...new Set(opciones.map((o) => o.grupo ?? ''))];
  return (
    <label className="filtro">
      {etiqueta}
      <select name={nombre} value={valor} onChange={(e) => onChange(e.target.value)}>
        <option value="">{todos}</option>
        {grupos.map((g) => {
          const os = opciones.filter((o) => (o.grupo ?? '') === g).map((o) => <option key={o.valor} value={o.valor}>{o.texto}</option>);
          return g ? <optgroup key={g} label={g}>{os}</optgroup> : os;
        })}
      </select>
    </label>
  );
}

// ---------------------------------------------------------------------------
// Barra de selección y formulario de marcado
// ---------------------------------------------------------------------------

function BarraSeleccion({ seleccion, d, onHecho, onFallo, onQuitar }: {
  seleccion: FilaVencimientoPago[]; d: PantallaVencimientosDTO; onHecho: (t: string) => void; onFallo: (t: string) => void; onQuitar: () => void;
}) {
  const [abierto, setAbierto] = useState(false);
  const [fecha, setFecha] = useState(d.hoy);
  const [forma, setForma] = useState<'' | FormaPago>('');
  const [enviando, setEnviando] = useState(false);
  // Reglas previas (las de la BD): sin orden, sin fecha o sin importe no se marca; se dice por qué.
  const noMarcables = seleccion.filter((f) => f.marca === null && f.no_marcable !== null);
  const sinMarca = seleccion.filter((f) => f.marca === null && f.no_marcable === null);
  const domiciliados = sinMarca.filter((f) => f.estado_pago === 'DOMICILIADO_PREVISTO');
  const motivos = [...new Set(noMarcables.map((f) => f.no_marcable as MotivoNoMarcable))];
  // Forma por defecto de cada uno: la del proveedor; un abono, compensación con abono (H6-3).
  const sinCif = sinMarca.some((f) => formaPorDefectoMarca(f) === 'SIN_DETERMINAR');
  const formas = [...new Set(sinMarca.map(formaPorDefectoMarca))];
  const comun: FormaEfectiva | null = formas.length === 1 ? formas[0] : null;
  const pistaDefecto = comun && comun !== 'SIN_DETERMINAR' ? ` (${TEXTO_FORMA[comun].toLowerCase()})`
    : sinMarca.some((f) => f.sentido === 'ABONO') ? ' (abonos: compensación con abono)' : '';
  const disponible = d.marcas_disponibles;
  const motivo = d.mensaje_escritura ?? undefined;
  useEffect(() => { if (sinMarca.length === 0) setAbierto(false); }, [sinMarca.length]);

  async function marcar(e: FormEvent) {
    e.preventDefault();
    setEnviando(true);
    try {
      await enviar('/api/pagos/marcas', 'POST', { vencimientos: sinMarca.map(idDe), fecha_pago: fecha, forma: forma === '' ? null : forma });
      setAbierto(false);
      const abonos = sinMarca.every((f) => f.sentido === 'ABONO');
      onHecho(abonos
        ? `${plural(sinMarca.length, 'abono marcado', 'abonos marcados')} como compensado${sinMarca.length === 1 ? '' : 's'} / cobrado${sinMarca.length === 1 ? '' : 's'} el ${fechaCorta(fecha)}.`
        : `${plural(sinMarca.length, 'vencimiento marcado', 'vencimientos marcados')} como pagado${sinMarca.length === 1 ? '' : 's'} el ${fechaCorta(fecha)}.`);
    } catch (err) {
      onFallo(textoError(err, 'No se han podido marcar los vencimientos.'));
    } finally { setEnviando(false); }
  }
  async function confirmarDomiciliados() {
    setEnviando(true);
    try {
      await enviar('/api/pagos/marcas/domiciliados', 'POST', { vencimientos: domiciliados.map(idDe) });
      onHecho(`${plural(domiciliados.length, 'domiciliado confirmado', 'domiciliados confirmados')} con su fecha de vencimiento.`);
    } catch (err) {
      onFallo(textoError(err, 'No se han podido confirmar los domiciliados.'));
    } finally { setEnviando(false); }
  }

  return (
    <section className="ve-barra" aria-label="Vencimientos seleccionados" data-barra-seleccion>
      <div className="ve-barra-linea">
        <strong data-seleccionados>{plural(seleccion.length, 'seleccionado', 'seleccionados')}</strong>
        <button type="button" className="ve-boton-claro" disabled={!disponible || sinMarca.length === 0 || enviando}
          title={motivo} onClick={() => setAbierto((v) => !v)} aria-expanded={abierto} data-marcar-pagado>
          Marcar pagado{sinMarca.length !== seleccion.length ? ` (${sinMarca.length})` : ''}
        </button>
        <button type="button" className="ve-boton-claro domiciliado" disabled={!disponible || domiciliados.length === 0 || enviando}
          title={disponible ? 'Fecha de pago = fecha de vencimiento; forma: domiciliación' : motivo}
          onClick={() => void confirmarDomiciliados()} data-confirmar-domiciliados>
          Confirmar domiciliados ({domiciliados.length})
        </button>
        <button type="button" className="ve-boton-texto" onClick={onQuitar} data-quitar-seleccion>Quitar selección</button>
      </div>
      {motivos.map((m) => {
        const n = noMarcables.filter((f) => f.no_marcable === m).length;
        return (
          <p key={m} className="ve-aviso-campo ve-no-marcable-barra" data-aviso-no-marcable={m}>
            {n === 1 ? `Un vencimiento seleccionado ${TEXTO_NO_MARCABLE[m]}.` : `${n} vencimientos seleccionados ${TEXTO_NO_MARCABLE_PLURAL[m]}.`}
          </p>
        );
      })}
      {!disponible && <p className="ve-barra-pendiente" data-pendiente-tablas>{d.mensaje_escritura}: marcar, confirmar y anular no están disponibles (solo lectura).</p>}
      {abierto && disponible && (
        <form className="ve-marcar" onSubmit={marcar} noValidate data-formulario-marcar>
          <label className="rrhh-campo">Fecha de pago
            <input type="date" name="fecha_pago" value={fecha} max={d.hoy} onChange={(e) => setFecha(e.target.value)} required />
          </label>
          <label className="rrhh-campo">Forma de pago
            <select name="forma_pago" value={forma} onChange={(e) => setForma(e.target.value as '' | FormaPago)}>
              <option value="">La de cada proveedor{pistaDefecto}</option>
              {FORMAS_PAGO.map((x) => <option key={x} value={x}>{TEXTO_FORMA[x]}</option>)}
            </select>
          </label>
          <button type="submit" className="boton-primario" disabled={enviando || fecha === '' || fecha > d.hoy || (sinCif && forma === '')} data-marcar-si>
            {sinMarca.every((f) => f.sentido === 'ABONO')
              ? `Marcar ${sinMarca.length} como compensado${sinMarca.length === 1 ? '' : 's'} / cobrado${sinMarca.length === 1 ? '' : 's'}`
              : `Marcar ${plural(sinMarca.length, 'como pagado', 'como pagados')}`}
          </button>
          {sinCif && forma === '' && <p className="ve-aviso-campo" data-aviso-sin-cif>Alguna factura no tiene CIF: elige la forma de pago.</p>}
          {fecha > d.hoy && <p className="ve-aviso-campo">La fecha de pago no puede ser posterior a hoy.</p>}
        </form>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Forma de pago por proveedor
// ---------------------------------------------------------------------------

function FilaForma({ p, disponible, motivo, onHecho, onFallo }: { p: ProveedorPagoVista; disponible: boolean; motivo: string | null; onHecho: (t: string) => void; onFallo: (t: string) => void }) {
  const [forma, setForma] = useState<FormaPago>(p.forma);
  useEffect(() => setForma(p.forma), [p.forma]);
  async function guardar(valor: FormaPago | null) {
    try {
      await enviar(`/api/pagos/formas/${p.cif}`, 'PUT', { forma: valor });
      onHecho(valor === null ? `${p.nombre}: vuelve a domiciliación (por defecto).` : `${p.nombre}: forma de pago ${TEXTO_FORMA[valor].toLowerCase()}.`);
    } catch (err) {
      onFallo(textoError(err, 'No se ha podido guardar la forma de pago.'));
    }
  }
  return (
    <li className="ve-forma-fila" data-forma-proveedor={p.cif}>
      <span className="ve-forma-nombre">
        <span className="nombre-truncado" title={p.nombre}>{p.nombre}</span>
        <span className="tenue ve-cif">CIF {p.cif} · {plural(p.vencimientos, 'vencimiento', 'vencimientos')}</span>
      </span>
      <label className="ve-forma-campo">
        <span className="visualmente-oculto">Forma de pago de {p.nombre}</span>
        <select value={forma} disabled={!disponible} title={disponible ? undefined : motivo ?? undefined} onChange={(e) => setForma(e.target.value as FormaPago)} data-forma-select={p.cif}>
          {FORMAS_PAGO.map((x) => <option key={x} value={x}>{TEXTO_FORMA[x]}</option>)}
        </select>
      </label>
      <span className="ve-forma-origen">{p.por_defecto ? <span className="insignia n">por defecto</span> : <span className="insignia b">configurada</span>}</span>
      <span className="ve-forma-botones">
        <button type="button" className="boton-secundario boton-mini" disabled={!disponible || forma === p.forma} onClick={() => void guardar(forma)} data-guardar-forma={p.cif}>Guardar</button>
        {!p.por_defecto && <button type="button" className="boton-secundario boton-mini" disabled={!disponible} onClick={() => void guardar(null)} data-forma-defecto={p.cif}>Volver a por defecto</button>}
      </span>
    </li>
  );
}

function FormasProveedor({ d, onHecho, onFallo }: { d: PantallaVencimientosDTO; onHecho: (t: string) => void; onFallo: (t: string) => void }) {
  return (
    <section className="tarjeta bloque ve-formas" aria-labelledby="t-ve-formas">
      <div className="bloque-cabecera">
        <h2 id="t-ve-formas">Forma de pago por proveedor</h2>
        <span className="tenue">Por CIF. Sin configurar: domiciliación.</span>
      </div>
      {!d.marcas_disponibles && <p className="ve-barra-pendiente gris" data-formas-pendiente>{d.mensaje_escritura}: la forma de pago no se puede cambiar (solo lectura).</p>}
      <ul className="ve-formas-lista">
        {d.proveedores.map((p) => <FilaForma key={p.cif} p={p} disponible={d.marcas_disponibles} motivo={d.mensaje_escritura} onHecho={onHecho} onFallo={onFallo} />)}
      </ul>
      {d.sin_cif.vencimientos > 0 && (
        <p className="tenue ve-formas-sin-cif" data-formas-sin-cif>
          {plural(d.sin_cif.vencimientos, 'vencimiento', 'vencimientos')} de facturas sin CIF: forma sin determinar; se trata como transferencia (rojo si vence sin marca).
        </p>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// H6-REAL: marcas huérfanas (su vencimiento ya no existe): a revisar
// ---------------------------------------------------------------------------

function MarcasHuerfanas({ d, onAnular }: { d: PantallaVencimientosDTO; onAnular: (m: MarcaHuerfana) => Promise<void> }) {
  if (d.marcas_huerfanas.length === 0) return null;
  return (
    <section className="tarjeta bloque ve-huerfanas" aria-labelledby="t-ve-huerfanas" data-marcas-huerfanas>
      <div className="bloque-cabecera">
        <h2 id="t-ve-huerfanas">Marcas a revisar sin vencimiento</h2>
        <span className="insignia o">{plural(d.marcas_huerfanas.length, 'marca', 'marcas')}</span>
      </div>
      <p className="tenue">Su vencimiento ya no existe en la factura (el circuito lo ha cambiado). No cuentan como pagado. Revísalas y anúlalas si procede.</p>
      <ul className="ve-huerfanas-lista">
        {d.marcas_huerfanas.map((m) => (
          <li key={m.marca_id} data-marca-huerfana={m.marca_id}>
            <span>
              <Link to={`/facturas/${m.factura_id}`} className="enlace-factura">{m.numero_factura ?? 'Factura'}</Link>
              <span className="tenue"> · vencimiento {m.vencimiento_orden}{m.proveedor_nombre ? ` · ${m.proveedor_nombre}` : ''}</span>
            </span>
            <span className="nota-celda">Marcada: vto. {fechaCorta(m.fecha_vencimiento)}, {euros(m.importe)} · pagado el {fechaCorta(m.fecha_pago)} · {TEXTO_FORMA[m.forma]}</span>
            <AnularMarca m={m} nombre={m.numero_factura ?? 'la factura'} disponible={d.marcas_disponibles} motivo={d.mensaje_escritura}
              clave={`huerfana:${m.marca_id}`} onAnular={() => onAnular(m)} />
          </li>
        ))}
      </ul>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Historial
// ---------------------------------------------------------------------------

function textoEvento(e: EventoPagoVista): string {
  const factura = `${e.numero_factura ?? 'factura sin número'}${e.fecha_vencimiento ? ` (vto. ${fechaCorta(e.fecha_vencimiento)})` : ''}`;
  const prov = `${e.proveedor_nombre ?? 'proveedor'} (CIF ${e.cif})`;
  switch (e.accion) {
    case 'MARCA': return e.origen === 'DOMICILIADOS'
      ? `confirmó domiciliado ${factura}: pagado el ${fechaCorta(e.fecha_pago)} por domiciliación`
      : `marcó ${e.sentido === 'ABONO' ? 'compensado / cobrado' : 'pagado'} ${factura}: ${fechaCorta(e.fecha_pago)}, ${TEXTO_FORMA[e.forma as FormaPago].toLowerCase()}`;
    case 'ANULA_MARCA': return `anuló la marca de pago de ${factura} (${fechaCorta(e.fecha_pago)}, ${TEXTO_FORMA[e.forma as FormaPago].toLowerCase()})`;
    case 'FORMA': return `puso ${prov} en ${TEXTO_FORMA[e.forma as FormaPago].toLowerCase()}${e.forma_anterior ? ` (antes ${TEXTO_FORMA[e.forma_anterior].toLowerCase()})` : ' (antes domiciliación por defecto)'}`;
    case 'FORMA_POR_DEFECTO': return `devolvió ${prov} a domiciliación por defecto${e.forma_anterior ? ` (antes ${TEXTO_FORMA[e.forma_anterior].toLowerCase()})` : ''}`;
  }
}

function Historial({ eventos }: { eventos: EventoPagoVista[] }) {
  return (
    <details className="tarjeta ve-historial" data-historial-pagos>
      <summary><h2>Historial de marcas y formas de pago</h2><span className="insignia n">{eventos.length}</span></summary>
      {eventos.length === 0 ? <p className="tenue ve-historial-vacio">Aún no hay cambios.</p> : (
        <ol className="ve-historial-lista">
          {eventos.map((e) => (
            <li key={e.evento_id} data-evento={e.accion}>
              <span className="ve-historial-fecha">{fechaHora(e.at)}</span>
              <span><strong>{e.autor}</strong> {textoEvento(e)}</span>
            </li>
          ))}
        </ol>
      )}
    </details>
  );
}

// ---------------------------------------------------------------------------
// Página
// ---------------------------------------------------------------------------

export function PaginaVencimientos() {
  const { carga, recargando, recargar } = useApiRecargable<PantallaVencimientosDTO>('/api/pagos/vencimientos');
  const [params, setParams] = useSearchParams();
  const movil = useMedia(MOVIL);
  const [seleccion, setSeleccion] = useState<Set<string>>(new Set());
  const [aviso, setAviso] = useState<{ tipo: 'ok' | 'error'; texto: string } | null>(null);
  const d = carga.estado === 'ok' ? carga.datos : null;

  const filtros = Object.fromEntries(CLAVES_FILTRO.map((k) => [k, params.get(k) ?? ''])) as Filtros;
  const cal = leerFiltroCalendario(filtros.cal || null);
  const vista: VistaCalendario = esVista(params.get('vista')) ? params.get('vista') as VistaCalendario : VISTA_POR_DEFECTO;
  const fechaCal = esFechaIso(params.get('fecha')) ? params.get('fecha') as string : d?.hoy ?? '';
  const pestana = pestanaDe(filtros.pestana || null);
  const columna = columnaDe(params.get('orden'));
  const dir = direccionDe(params.get('dir'));
  // Parte siempre de los últimos parámetros escritos: dos cambios seguidos (p. ej. quitar el estado y elegir forma antes
  // de que React vuelva a pintar) no se pisan con parámetros viejos.
  const ultimos = useRef(params);
  ultimos.current = params;
  const cambiar = (cambios: Record<string, string | null>) => {
    const p = new URLSearchParams(ultimos.current);
    for (const [k, v] of Object.entries(cambios)) { if (v === null || v === '') p.delete(k); else p.set(k, v); }
    ultimos.current = p;
    setParams(p, { replace: true });
  };

  // Calendario: todos los filtros salvo los de fecha. Recuentos por estado: todos salvo el estado. Lista: todos, ordenada.
  const delCalendario = useMemo(() => (d ? d.filas.filter((f) => cumpleFiltros(f, filtros, d.hoy, cal, { sinFecha: true })) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [d, params]);
  const sinEstado = useMemo(() => (d ? d.filas.filter((f) => cumpleFiltros(f, filtros, d.hoy, cal, { sinEstado: true })) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [d, params]);
  // Pestañas: recuento con el resto de filtros (como Facturas).
  const sinPestana = useMemo(() => (d ? d.filas.filter((f) => cumpleFiltros(f, { ...filtros, pestana: '' }, d.hoy, cal)) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [d, params]);
  const filas = useMemo(() => ordenar(sinPestana.filter((f) => pestana.cumple(f)), columna.clave, dir === 1 ? 'asc' : 'desc'),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sinPestana, params]);
  const proveedores = useMemo(() => opcionesProveedor(d?.filas ?? []), [d]);
  const filtrarCalendario = (escala: FiltroCalendario['escala'], clave: string) => {
    const v = valorFiltroCalendario(escala, clave);
    // Un segundo clic sobre el mismo periodo quita el filtro. Elegir un periodo del calendario sustituye al de las pestañas.
    cambiar(filtros.cal === v ? { cal: null } : { cal: v, periodo: null, desde: null, hasta: null });
    desplazar.current = filtros.cal !== v;
  };
  // Tras filtrar desde el calendario, el filtro queda a la vista (en móvil, la lista empieza arriba).
  const desplazar = useRef(false);
  useEffect(() => {
    if (!desplazar.current || !cal) return;
    desplazar.current = false;
    document.querySelector('[data-filtro-calendario]')?.scrollIntoView({ block: movil ? 'start' : 'nearest' });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtros.cal]);
  const visibles = new Set(filas.map(sel));
  // La selección solo guarda lo que está a la vista.
  useEffect(() => {
    setSeleccion((s) => { const n = new Set([...s].filter((id) => visibles.has(id))); return n.size === s.size ? s : n; });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filas]);
  const elegidas = filas.filter((f) => seleccion.has(sel(f)));
  const alternar = (id: string) => setSeleccion((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const todas = filas.length > 0 && elegidas.length === filas.length;
  const hayFiltros = CLAVES_FILTRO.some((k) => filtros[k] !== '');

  const hecho = (texto: string) => { setAviso({ tipo: 'ok', texto }); setSeleccion(new Set()); recargar(); };
  const fallo = (texto: string) => { setAviso({ tipo: 'error', texto }); recargar(); };
  async function anularMarca(marcaId: string, numero: string | null, vto: string | null) {
    try {
      await enviar(`/api/pagos/marcas/${marcaId}/anular`, 'PUT', { confirmar: true });
      hecho(`Marca de pago anulada: ${numero ?? 'factura sin número'} (vto. ${fechaCorta(vto)}).`);
    } catch (err) {
      fallo(textoError(err, 'No se ha podido anular la marca.'));
    }
  }
  const anular = async (f: FilaVencimientoPago) => { if (f.marca) await anularMarca(f.marca.marca_id, f.numero_factura, f.fecha_vencimiento); };
  const anularHuerfana = (m: MarcaHuerfana) => anularMarca(m.marca_id, m.numero_factura, m.fecha_vencimiento);

  const sinImporte = filas.filter((f) => f.importe === null).length;
  const negativos = filas.filter((f) => f.cargo_negativo).length;
  const subtitulo = d
    ? `${plural(d.filas.length, 'vencimiento', 'vencimientos')} de PIO · referencia: ${diaSemana(d.hoy)} ${fechaCorta(d.hoy)}`
    : 'Vencimientos de PIO y su estado de pago';

  return (
    <>
      <Cabecera titulo="Vencimientos" subtitulo={subtitulo}>
        <button type="button" className="boton-secundario" onClick={recargar} disabled={recargando}>Actualizar</button>
      </Cabecera>

      {carga.estado === 'cargando' && <p className="tenue">Leyendo vencimientos…</p>}
      {carga.estado === 'error' && (
        <section className="tarjeta bloque error" role="alert">
          <h2>No se han podido leer los vencimientos</h2>
          <p>La API local respondió <code className="codigo">{carga.mensaje}</code>. Pulsa Actualizar para volver a intentarlo.</p>
        </section>
      )}

      {d && (
        <div className="vencimientos" data-contrato-ok="vencimientos" aria-busy={recargando}>
          {d.modo === 'FIXTURES' && (
            <p className="rrhh-banner" data-banner-pagos="fixtures"><span className="rrhh-banner-marca">Ejemplo</span>Datos ficticios: las marcas de pago y las formas se guardan solo en memoria hasta reiniciar.</p>
          )}
          {d.modo === 'REAL' && !d.marcas_disponibles && (
            <p className="rrhh-banner ve-banner-real" data-banner-pagos="real">
              <span className="rrhh-banner-marca">Solo lectura</span>{d.mensaje_escritura}. Se ven las marcas y las formas guardadas, pero no se pueden cambiar.
            </p>
          )}
          {d.a_revisar > 0 && (
            <p className="ve-aviso-revisar" role="status" data-aviso-revisar={d.a_revisar}>
              {plural(d.a_revisar, 'marca de pago a revisar', 'marcas de pago a revisar')}: el vencimiento ha cambiado (o ya no existe) desde que se marcó. No cuentan como pagado.
            </p>
          )}
          {aviso && <p className={aviso.tipo === 'ok' ? 'rrhh-aviso-ok' : 'rrhh-error'} role={aviso.tipo === 'ok' ? 'status' : 'alert'} data-aviso-pagos={aviso.tipo}>{aviso.texto}</p>}

          <div className="ve-estados" role="group" aria-label="Filtrar por estado">
            {ESTADOS_IMPLEMENTADOS.map((e) => {
              const def = DICCIONARIO_ESTADOS[e];
              const activo = filtros.estado === e;
              // H6-REAL: las marcas huérfanas (sin fila) también cuentan como «a revisar».
              const n = sinEstado.filter((f) => f.estado_pago === e).length + (e === 'A_REVISAR' ? d.marcas_huerfanas.length : 0);
              if (e === 'A_REVISAR' && n === 0 && !activo) return null;
              return (
                <button key={e} type="button" className={`ve-estado-boton c-${def.color}${activo ? ' activo' : ''}`} aria-pressed={activo}
                  title={def.descripcion} onClick={() => cambiar({ estado: activo ? null : e })} data-filtro-estado={e}>
                  <span className="ve-estado-n">{n}</span>
                  <span className="ve-estado-texto">{def.texto.charAt(0).toUpperCase() + def.texto.slice(1)}</span>
                </button>
              );
            })}
            <span className="ve-estado-boton c-gris reservado" aria-disabled="true" title={DICCIONARIO_ESTADOS.PAGADO_BANCO.descripcion} data-estado-reservado="PAGADO_BANCO">
              <span className="ve-estado-n">—</span>
              <span className="ve-estado-texto">{DICCIONARIO_ESTADOS.PAGADO_BANCO.texto}<span className="ve-estado-sub">sin datos bancarios</span></span>
            </span>
          </div>

          <CalendarioVencimientos filas={delCalendario} hoy={d.hoy} vista={vista} fecha={fechaCal} filtro={cal}
            onNavegar={(v, f) => cambiar({ vista: v === VISTA_POR_DEFECTO ? null : v, fecha: f === d.hoy ? null : f })}
            onFiltrar={filtrarCalendario} />

          <h2 className="ve-lista-titulo" id="t-ve-lista">Lista de vencimientos</h2>
          <label className="buscar">
            <span>Buscar</span>
            <input type="search" name="q" placeholder="Proveedor, CIF, nº de factura o importe" value={filtros.q} onChange={(e) => cambiar({ q: e.target.value })} />
          </label>

          <div className="pestanas" role="tablist" aria-label="Estado de las facturas">
            {PESTANAS_VENCIMIENTOS.map((p) => (
              <button key={p.clave} type="button" role="tab" aria-selected={p.clave === pestana.clave}
                className={p.clave === pestana.clave ? 'pestana activa' : 'pestana'} data-pestana={p.clave}
                onClick={() => cambiar({ pestana: p.clave === 'todas' ? null : p.clave })}>
                {p.texto} <span className="pestana-n">{sinPestana.filter(p.cumple).length}</span>
              </button>
            ))}
          </div>

          <section className="tarjeta filtros" aria-label="Filtros">
            <Selector nombre="periodo" etiqueta="Vencimiento" todos="Cualquier fecha" valor={filtros.periodo}
              onChange={(v) => cambiar({ periodo: v, cal: null, ...(v === 'rango' ? {} : { desde: null, hasta: null }) })}
              opciones={PERIODOS.map((p) => ({ valor: p.clave, texto: p.texto }))} />
            {filtros.periodo === 'rango' && (
              <>
                <label className="filtro">Desde<input type="date" name="desde" value={filtros.desde} onChange={(e) => cambiar({ desde: e.target.value })} /></label>
                <label className="filtro">Hasta<input type="date" name="hasta" value={filtros.hasta} onChange={(e) => cambiar({ hasta: e.target.value })} /></label>
              </>
            )}
            <Selector nombre="estado" etiqueta="Estado de pago" todos="Todos" valor={filtros.estado} onChange={(v) => cambiar({ estado: v })}
              opciones={ESTADOS_IMPLEMENTADOS.map((e) => ({ valor: e, texto: DICCIONARIO_ESTADOS[e].texto }))} />
            <Selector nombre="forma" etiqueta="Forma de pago" todos="Todas" valor={filtros.forma} onChange={(v) => cambiar({ forma: v })}
              opciones={[...FORMAS_PAGO, 'SIN_DETERMINAR' as const].map((x) => ({ valor: x, texto: `${TEXTO_FORMA[x]}${x === 'SIN_DETERMINAR' ? ' (sin CIF)' : ''}` }))} />
            <Selector nombre="proveedor" etiqueta="Proveedor" todos="Todos" valor={filtros.proveedor} onChange={(v) => cambiar({ proveedor: v })}
              opciones={proveedores.map((o) => ({ valor: o.clave, texto: o.texto }))} />
            <Selector nombre="sentido" etiqueta="Sentido" todos="Todos" valor={filtros.sentido} onChange={(v) => cambiar({ sentido: v })}
              opciones={(['CARGO', 'ABONO', 'NO_DOCUMENTADO'] as const).map((s) => ({ valor: s, texto: TEXTO_SENTIDO[s] }))} />
            <Selector nombre="importe" etiqueta="Importe" todos="Cualquiera" valor={filtros.importe} onChange={(v) => cambiar({ importe: v })}
              opciones={IMPORTES_LISTA.map((o) => ({ valor: o.clave, texto: o.texto }))} />
            <Selector nombre="factura" etiqueta="Estado de la factura" todos="Todos" valor={filtros.factura} onChange={(v) => cambiar({ factura: v })}
              opciones={[
                ...OPCIONES_NORMALIZACION.map((e) => ({ valor: `norm:${e}`, texto: etiquetaNormalizacion(e).texto, grupo: 'Normalización' })),
                ...OPCIONES_CONCILIACION.map((e) => ({ valor: `conc:${e}`, texto: etiquetaConciliacion(e).texto, grupo: 'Conciliación' })),
              ]} />
            <Selector nombre="revision" etiqueta="Revisión Pío" todos="Todas" valor={filtros.revision} onChange={(v) => cambiar({ revision: v })}
              opciones={OPCIONES_REVISION.map((e) => ({ valor: e, texto: etiquetaRevision(e).texto }))} />
            {hayFiltros && (
              <button type="button" className="boton-secundario boton-limpiar" onClick={() => cambiar(Object.fromEntries(CLAVES_FILTRO.map((k) => [k, null])))}>Quitar filtros</button>
            )}
          </section>

          {cal && (
            <p className="ve-filtro-cal" data-filtro-calendario={filtros.cal}>
              <span className="ve-filtro-cal-texto"><span className="tenue">Calendario:</span> <strong>{textoFiltroCalendario(cal)}</strong></span>
              <button type="button" className="ve-filtro-cal-quitar" onClick={() => cambiar({ cal: null })} data-quitar-filtro-calendario
                aria-label={`Quitar el filtro del calendario (${textoFiltroCalendario(cal)})`}>Quitar <span aria-hidden="true">×</span></button>
            </p>
          )}

          <Totales filas={filas} />

          <div className="ve-lista-cabecera">
            <p className="tenue resumen-listado" data-resumen-listado aria-live="polite">
              {filas.length === 0 ? 'Ningún vencimiento cumple estos filtros.' : plural(filas.length, 'vencimiento', 'vencimientos')}
              {sinImporte > 0 && <span data-recuento-sin-importe> · {plural(sinImporte, 'con importe pendiente', 'con importe pendiente')} (fuera de los totales)</span>}
              {negativos > 0 && <span data-recuento-cargo-negativo> · {plural(negativos, 'cargo con importe negativo', 'cargos con importe negativo')}: revisar (fuera de los totales)</span>}
            </p>
            {movil && filas.length > 0 && (
              <span className="ve-orden-movil">
                <label className="filtro">Ordenar por
                  <select name="orden" value={columna.clave} onChange={(e) => cambiar({ orden: e.target.value === COLUMNA_POR_DEFECTO ? null : e.target.value })}>
                    {COLUMNAS_LISTA.map((c) => <option key={c.clave} value={c.clave}>{c.texto}</option>)}
                  </select>
                </label>
                <button type="button" className="boton-secundario ve-orden-dir" onClick={() => cambiar({ dir: dir === 1 ? 'desc' : null })}
                  aria-label={dir === 1 ? 'Orden ascendente; cambiar a descendente' : 'Orden descendente; cambiar a ascendente'} data-orden-dir>{dir === 1 ? '↑' : '↓'}</button>
              </span>
            )}
            {movil && filas.length > 0 && (
              <label className="rrhh-check ve-todas-movil">
                <input type="checkbox" checked={todas} onChange={() => setSeleccion(todas ? new Set() : new Set(filas.map(sel)))} data-seleccionar-todas />
                Seleccionar todos
              </label>
            )}
          </div>

          {elegidas.length > 0 && (
            <BarraSeleccion key={[...seleccion].sort().join()} seleccion={elegidas} d={d} onHecho={hecho} onFallo={fallo} onQuitar={() => setSeleccion(new Set())} />
          )}

          {filas.length > 0 && (movil ? (
            <ul className="ve-tarjetas" aria-label="Vencimientos">
              {filas.map((f) => (
                <li key={f.vencimiento_id} className={`tarjeta ve-tarjeta e-${f.estado_pago}${seleccion.has(sel(f)) ? ' elegida' : ''}`} data-vencimiento={f.vencimiento_id}>
                  <div className="ve-tarjeta-cabecera">
                    <Casilla f={f} marcada={seleccion.has(sel(f))} onCambio={alternar} />
                    <span className="ve-tarjeta-fecha">{fechaCorta(f.fecha_vencimiento)}</span>
                    <span className="ve-tarjeta-importe"><Importe f={f} /></span>
                  </div>
                  <Proveedor f={f} />
                  <div className="ve-tarjeta-linea"><Factura f={f} /><Sentido f={f} /></div>
                  <div className="ve-tarjeta-linea"><span className="tenue">Forma</span><Forma f={f} /></div>
                  <Estado f={f} d={d} onAnular={anular} />
                </li>
              ))}
            </ul>
          ) : (
            <div className="tarjeta tabla-desplazable">
              <table className="tabla ve-tabla">
                <thead>
                  <tr>
                    <th scope="col" className="ve-col-casilla">
                      <input type="checkbox" className="ve-casilla" checked={todas} aria-label="Seleccionar todos los vencimientos a la vista"
                        onChange={() => setSeleccion(todas ? new Set() : new Set(filas.map(sel)))} data-seleccionar-todas />
                    </th>
                    {COLUMNAS_LISTA.map((c) => {
                      const activa = c.clave === columna.clave;
                      return (
                        <th key={c.clave} scope="col" className={c.num ? 'num' : undefined} aria-sort={activa ? (dir === 1 ? 'ascending' : 'descending') : 'none'}>
                          <button type="button" className="ordenar" data-ordenar={c.clave}
                            onClick={() => cambiar(activa
                              ? { orden: c.clave === COLUMNA_POR_DEFECTO ? null : c.clave, dir: dir === 1 ? 'desc' : null }
                              : { orden: c.clave === COLUMNA_POR_DEFECTO ? null : c.clave, dir: null })}>
                            {c.texto}<span className="flecha" aria-hidden="true">{activa ? (dir === 1 ? '↑' : '↓') : '↕'}</span>
                          </button>
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {filas.map((f) => (
                    <tr key={f.vencimiento_id} className={`e-${f.estado_pago}${seleccion.has(sel(f)) ? ' elegida' : ''}`} data-vencimiento={f.vencimiento_id}>
                      <td className="ve-col-casilla"><Casilla f={f} marcada={seleccion.has(sel(f))} onCambio={alternar} /></td>
                      <td className="fecha">{fechaCorta(f.fecha_vencimiento)}</td>
                      <td className="proveedor"><Proveedor f={f} /></td>
                      <td><Factura f={f} /></td>
                      <td className="num"><Importe f={f} /></td>
                      <td><Sentido f={f} /></td>
                      <td><Forma f={f} /></td>
                      <td><Estado f={f} d={d} onAnular={anular} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}

          <MarcasHuerfanas d={d} onAnular={anularHuerfana} />
          <FormasProveedor d={d} onHecho={hecho} onFallo={fallo} />
          <Historial eventos={d.historial} />

          <p className="tenue nota-listado" data-nota-banco>
            Banco: <span className="pago-gris">{d.pago.texto}</span>. «Pagado (banco)» queda reservado hasta tener datos bancarios.
            Los totales restan los abonos de los cargos y no suman los vencimientos con importe pendiente, los de sentido no documentado
            ni los cargos con importe negativo.
          </p>
        </div>
      )}
    </>
  );
}
