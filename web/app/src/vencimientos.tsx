// H6: pantalla Vencimientos (maqueta web/docs/maquetas/Vencimientos.dc.html) sobre /api/pagos/vencimientos.
// Una fila por vencimiento con su estado de pago, forma de pago por proveedor (CIF) y marca manual. Filtros en la URL.
// FIXTURES: marcar, confirmar domiciliados, anular y editar la forma de pago (en memoria). REAL: solo lectura; los
// botones quedan deshabilitados con «Pendiente de tablas en Supabase».
// Importe ausente = «importe pendiente» (nunca 0), fuera de los totales y con su recuento a la vista.
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  DICCIONARIO_ESTADOS, ESTADOS_IMPLEMENTADOS, FORMAS_PAGO, PERIODOS, TEXTO_CARGO_NEGATIVO, TEXTO_FORMA, TEXTO_H6_PENDIENTE, TEXTO_SENTIDO,
  cumpleBusquedaPago, cumplePeriodo, formaPorDefectoMarca, textoEstadoPago, totalGeneral, totalesPorPeriodo,
  type BloqueTotal, type ColorEstadoPago, type EventoPagoVista, type FilaVencimientoPago,
  type FormaEfectiva, type FormaPago, type PantallaVencimientosDTO, type ProveedorPagoVista, type TotalPeriodo,
} from '../server/pagos/pagos.ts';
import { ErrorApi, enviar, useApiRecargable } from './api.ts';
import { euros, fechaCorta, fechaHora, plural } from './formato.ts';
import { Cabecera, MOVIL, NombreProveedor, useMedia } from './ui.tsx';

const CLASE_ESTADO: Record<ColorEstadoPago, string> = { azul: 'b', rojo: 'r', verde: 'g', gris: 'n', domiciliado: 'd' };
const CLAVES_FILTRO = ['periodo', 'desde', 'hasta', 'estado', 'forma', 'q'] as const;
type Filtros = Record<(typeof CLAVES_FILTRO)[number], string>;

const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
const diaMes = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
const diaSemana = (iso: string) => DIAS[new Date(`${iso}T00:00:00Z`).getUTCDay()];
function textoPeriodo(t: TotalPeriodo, periodo: 'semana' | 'mes'): string {
  if (t.clave === null) return 'Sin fecha de vencimiento';
  if (periodo === 'mes') return `${MESES[Number(t.clave.slice(5, 7)) - 1]} ${t.clave.slice(0, 4)}`;
  return `${diaMes(t.desde as string)} – ${diaMes(t.hasta as string)}`;
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

function Estado({ f, disponible, onAnular }: { f: FilaVencimientoPago; disponible: boolean; onAnular: (f: FilaVencimientoPago) => Promise<void> }) {
  const [confirmar, setConfirmar] = useState(false);
  const m = f.marca;
  return (
    <span className="ve-estado">
      <EstadoInsignia f={f} />
      {m && (
        <>
          <span className="nota-celda" data-marca={m.marca_id}>{fechaCorta(m.fecha_pago)} · {TEXTO_FORMA[m.forma]}{m.origen === 'DOMICILIADOS' ? ' · domiciliado confirmado' : ''}</span>
          {!confirmar && (
            <button type="button" className="ve-enlace-boton" disabled={!disponible} title={disponible ? undefined : TEXTO_H6_PENDIENTE}
              onClick={() => setConfirmar(true)} data-anular-marca={f.vencimiento_id}>Anular marca</button>
          )}
          {confirmar && (
            <span className="ve-confirmar" role="alertdialog" aria-label={`Anular la marca de pago de ${f.numero_factura ?? 'la factura'}`} data-confirmar-anular={f.vencimiento_id}>
              <span>¿Anular la marca? Queda en el historial (no se borra).</span>
              <span className="ve-confirmar-botones">
                <button type="button" className="boton-peligro boton-mini" onClick={() => void onAnular(f).then(() => setConfirmar(false))} data-anular-si>Sí, anular</button>
                <button type="button" className="boton-secundario boton-mini" onClick={() => setConfirmar(false)}>Cancelar</button>
              </span>
            </span>
          )}
        </>
      )}
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
    <input type="checkbox" className="ve-casilla" checked={marcada} onChange={() => onCambio(f.vencimiento_id)}
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

function Totales({ filas, periodo, onPeriodo }: { filas: FilaVencimientoPago[]; periodo: 'semana' | 'mes'; onPeriodo: (p: 'semana' | 'mes') => void }) {
  const ts = totalesPorPeriodo(filas, periodo);
  const g = totalGeneral(filas);
  return (
    <section className="ve-totales" aria-labelledby="t-ve-totales">
      <div className="bloque-cabecera">
        <h2 id="t-ve-totales">Totales {periodo === 'semana' ? 'por semana' : 'por mes'}</h2>
        <div className="rrhh-selector" role="group" aria-label="Agrupar totales">
          <button type="button" className={periodo === 'semana' ? 'activa' : undefined} aria-pressed={periodo === 'semana'} onClick={() => onPeriodo('semana')} data-totales="semana">Semana</button>
          <button type="button" className={periodo === 'mes' ? 'activa' : undefined} aria-pressed={periodo === 'mes'} onClick={() => onPeriodo('mes')} data-totales="mes">Mes</button>
        </div>
      </div>
      <div className="ve-total-general tarjeta" data-total-general>
        <span className="ve-total-titulo">Todo lo filtrado <span className="tenue">· {plural(g.vencimientos, 'vencimiento', 'vencimientos')}</span></span>
        <div className="ve-cifras">
          <Cifra etiqueta="Por pagar" b={g.por_pagar} clase="por-pagar" datos="por_pagar" />
          <Cifra etiqueta="Domiciliado previsto" b={g.domiciliado} clase="domiciliado" datos="domiciliado" />
        </div>
        <NotasTotal t={g} />
      </div>
      {ts.length > 0 && (
        <ol className="ve-periodos" aria-label={periodo === 'semana' ? 'Semanas' : 'Meses'}>
          {ts.map((t) => (
            <li key={t.clave ?? 'sin'} className="tarjeta ve-periodo" data-periodo={t.clave ?? 'sin-fecha'}>
              <span className="ve-periodo-titulo">{textoPeriodo(t, periodo)} <span className="tenue">· {t.vencimientos}</span></span>
              <div className="ve-cifras">
                <Cifra etiqueta="Por pagar" b={t.por_pagar} clase="por-pagar" datos="por_pagar" />
                <Cifra etiqueta="Domiciliado" b={t.domiciliado} clase="domiciliado" datos="domiciliado" />
              </div>
              <NotasTotal t={t} />
            </li>
          ))}
        </ol>
      )}
    </section>
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
  const sinMarca = seleccion.filter((f) => f.marca === null);
  const domiciliados = seleccion.filter((f) => f.estado_pago === 'DOMICILIADO_PREVISTO');
  // Forma por defecto de cada uno: la del proveedor; un abono, compensación con abono (H6-3).
  const sinCif = sinMarca.some((f) => formaPorDefectoMarca(f) === 'SIN_DETERMINAR');
  const formas = [...new Set(sinMarca.map(formaPorDefectoMarca))];
  const comun: FormaEfectiva | null = formas.length === 1 ? formas[0] : null;
  const pistaDefecto = comun && comun !== 'SIN_DETERMINAR' ? ` (${TEXTO_FORMA[comun].toLowerCase()})`
    : sinMarca.some((f) => f.sentido === 'ABONO') ? ' (abonos: compensación con abono)' : '';
  const disponible = d.marcas_disponibles;
  useEffect(() => { if (sinMarca.length === 0) setAbierto(false); }, [sinMarca.length]);

  async function marcar(e: FormEvent) {
    e.preventDefault();
    setEnviando(true);
    try {
      await enviar('/api/pagos/marcas', 'POST', { vencimientos: sinMarca.map((f) => f.vencimiento_id), fecha_pago: fecha, forma: forma === '' ? null : forma });
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
      await enviar('/api/pagos/marcas/domiciliados', 'POST', { vencimientos: domiciliados.map((f) => f.vencimiento_id) });
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
          title={disponible ? undefined : TEXTO_H6_PENDIENTE} onClick={() => setAbierto((v) => !v)} aria-expanded={abierto} data-marcar-pagado>
          Marcar pagado{sinMarca.length !== seleccion.length ? ` (${sinMarca.length})` : ''}
        </button>
        <button type="button" className="ve-boton-claro domiciliado" disabled={!disponible || domiciliados.length === 0 || enviando}
          title={disponible ? 'Fecha de pago = fecha de vencimiento; forma: domiciliación' : TEXTO_H6_PENDIENTE}
          onClick={() => void confirmarDomiciliados()} data-confirmar-domiciliados>
          Confirmar domiciliados ({domiciliados.length})
        </button>
        <button type="button" className="ve-boton-texto" onClick={onQuitar} data-quitar-seleccion>Quitar selección</button>
      </div>
      {!disponible && <p className="ve-barra-pendiente" data-pendiente-tablas>{TEXTO_H6_PENDIENTE}: marcar, confirmar y anular estarán disponibles cuando existan las tablas de pagos.</p>}
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

function FilaForma({ p, disponible, onHecho, onFallo }: { p: ProveedorPagoVista; disponible: boolean; onHecho: (t: string) => void; onFallo: (t: string) => void }) {
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
        <select value={forma} disabled={!disponible} title={disponible ? undefined : TEXTO_H6_PENDIENTE} onChange={(e) => setForma(e.target.value as FormaPago)} data-forma-select={p.cif}>
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
      {!d.marcas_disponibles && <p className="ve-barra-pendiente gris" data-formas-pendiente>{TEXTO_H6_PENDIENTE}: la forma de pago no se puede cambiar todavía.</p>}
      <ul className="ve-formas-lista">
        {d.proveedores.map((p) => <FilaForma key={p.cif} p={p} disponible={d.marcas_disponibles} onHecho={onHecho} onFallo={onFallo} />)}
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
  const agrupar: 'semana' | 'mes' = params.get('totales') === 'mes' ? 'mes' : 'semana';
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

  // Filtros de periodo, forma y búsqueda (los recuentos por estado se calculan sobre esto); después, el estado.
  const sinEstado = useMemo(() => (d ? d.filas.filter((f) => cumplePeriodo(f, filtros.periodo, d.hoy, { desde: filtros.desde, hasta: filtros.hasta })
    && (filtros.forma === '' || f.forma_pago === filtros.forma) && cumpleBusquedaPago(f, filtros.q)) : []),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  [d, params]);
  const filas = useMemo(() => sinEstado.filter((f) => filtros.estado === '' || f.estado_pago === filtros.estado),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sinEstado, params]);
  const visibles = new Set(filas.map((f) => f.vencimiento_id));
  // La selección solo guarda lo que está a la vista.
  useEffect(() => {
    setSeleccion((s) => { const n = new Set([...s].filter((id) => visibles.has(id))); return n.size === s.size ? s : n; });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filas]);
  const elegidas = filas.filter((f) => seleccion.has(f.vencimiento_id));
  const alternar = (id: string) => setSeleccion((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const todas = filas.length > 0 && elegidas.length === filas.length;
  const hayFiltros = CLAVES_FILTRO.some((k) => filtros[k] !== '');

  const hecho = (texto: string) => { setAviso({ tipo: 'ok', texto }); setSeleccion(new Set()); recargar(); };
  const fallo = (texto: string) => { setAviso({ tipo: 'error', texto }); recargar(); };
  async function anular(f: FilaVencimientoPago) {
    if (!f.marca) return;
    try {
      await enviar(`/api/pagos/marcas/${f.marca.marca_id}/anular`, 'PUT', { confirmar: true });
      hecho(`Marca de pago anulada: ${f.numero_factura ?? 'factura sin número'} (vto. ${fechaCorta(f.fecha_vencimiento)}).`);
    } catch (err) {
      fallo(textoError(err, 'No se ha podido anular la marca.'));
    }
  }

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
          {d.marcas_disponibles ? (
            <p className="rrhh-banner" data-banner-pagos="fixtures"><span className="rrhh-banner-marca">Ejemplo</span>Datos ficticios: las marcas de pago y las formas se guardan solo en memoria hasta reiniciar.</p>
          ) : (
            <p className="rrhh-banner ve-banner-real" data-banner-pagos="real">
              <span className="rrhh-banner-marca">Solo lectura</span>Marcas de pago: {TEXTO_H6_PENDIENTE}. Sin marcas, lo vencido por domiciliación figura como previsto.
            </p>
          )}
          {aviso && <p className={aviso.tipo === 'ok' ? 'rrhh-aviso-ok' : 'rrhh-error'} role={aviso.tipo === 'ok' ? 'status' : 'alert'} data-aviso-pagos={aviso.tipo}>{aviso.texto}</p>}

          <div className="ve-estados" role="group" aria-label="Filtrar por estado">
            {ESTADOS_IMPLEMENTADOS.map((e) => {
              const def = DICCIONARIO_ESTADOS[e];
              const n = sinEstado.filter((f) => f.estado_pago === e).length;
              const activo = filtros.estado === e;
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

          <div className="pestanas" role="tablist" aria-label="Periodo">
            <button type="button" role="tab" aria-selected={filtros.periodo === ''} className={filtros.periodo === '' ? 'pestana activa' : 'pestana'}
              onClick={() => cambiar({ periodo: null, desde: null, hasta: null })} data-periodo-filtro="">Todos</button>
            {PERIODOS.map((p) => (
              <button key={p.clave} type="button" role="tab" aria-selected={filtros.periodo === p.clave}
                className={filtros.periodo === p.clave ? 'pestana activa' : 'pestana'} data-periodo-filtro={p.clave}
                onClick={() => cambiar({ periodo: p.clave, ...(p.clave === 'rango' ? {} : { desde: null, hasta: null }) })}>{p.texto}</button>
            ))}
          </div>

          <section className="tarjeta filtros" aria-label="Filtros">
            {filtros.periodo === 'rango' && (
              <>
                <label className="filtro">Desde<input type="date" name="desde" value={filtros.desde} onChange={(e) => cambiar({ desde: e.target.value })} /></label>
                <label className="filtro">Hasta<input type="date" name="hasta" value={filtros.hasta} onChange={(e) => cambiar({ hasta: e.target.value })} /></label>
              </>
            )}
            <label className="filtro">Estado
              <select name="estado" value={filtros.estado} onChange={(e) => cambiar({ estado: e.target.value })}>
                <option value="">Todos</option>
                {ESTADOS_IMPLEMENTADOS.map((e) => <option key={e} value={e}>{DICCIONARIO_ESTADOS[e].texto}</option>)}
              </select>
            </label>
            <label className="filtro">Forma de pago
              <select name="forma" value={filtros.forma} onChange={(e) => cambiar({ forma: e.target.value })}>
                <option value="">Todas</option>
                {[...FORMAS_PAGO, 'SIN_DETERMINAR' as const].map((x) => <option key={x} value={x}>{TEXTO_FORMA[x]}{x === 'SIN_DETERMINAR' ? ' (sin CIF)' : ''}</option>)}
              </select>
            </label>
            <label className="filtro ve-buscar">Buscar
              <input type="search" name="q" placeholder="Proveedor, CIF o nº de factura" value={filtros.q} onChange={(e) => cambiar({ q: e.target.value })} />
            </label>
            {hayFiltros && (
              <button type="button" className="boton-secundario boton-limpiar" onClick={() => cambiar(Object.fromEntries(CLAVES_FILTRO.map((k) => [k, null])))}>Quitar filtros</button>
            )}
          </section>

          <Totales filas={filas} periodo={agrupar} onPeriodo={(p) => cambiar({ totales: p === 'semana' ? null : p })} />

          <div className="ve-lista-cabecera">
            <p className="tenue resumen-listado" data-resumen-listado aria-live="polite">
              {filas.length === 0 ? 'Ningún vencimiento cumple estos filtros.' : plural(filas.length, 'vencimiento', 'vencimientos')}
              {sinImporte > 0 && <span data-recuento-sin-importe> · {plural(sinImporte, 'con importe pendiente', 'con importe pendiente')} (fuera de los totales)</span>}
              {negativos > 0 && <span data-recuento-cargo-negativo> · {plural(negativos, 'cargo con importe negativo', 'cargos con importe negativo')}: revisar (fuera de los totales)</span>}
            </p>
            {movil && filas.length > 0 && (
              <label className="rrhh-check ve-todas-movil">
                <input type="checkbox" checked={todas} onChange={() => setSeleccion(todas ? new Set() : new Set(filas.map((f) => f.vencimiento_id)))} data-seleccionar-todas />
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
                <li key={f.vencimiento_id} className={`tarjeta ve-tarjeta e-${f.estado_pago}${seleccion.has(f.vencimiento_id) ? ' elegida' : ''}`} data-vencimiento={f.vencimiento_id}>
                  <div className="ve-tarjeta-cabecera">
                    <Casilla f={f} marcada={seleccion.has(f.vencimiento_id)} onCambio={alternar} />
                    <span className="ve-tarjeta-fecha">{fechaCorta(f.fecha_vencimiento)}</span>
                    <span className="ve-tarjeta-importe"><Importe f={f} /></span>
                  </div>
                  <Proveedor f={f} />
                  <div className="ve-tarjeta-linea"><Factura f={f} /><Sentido f={f} /></div>
                  <div className="ve-tarjeta-linea"><span className="tenue">Forma</span><Forma f={f} /></div>
                  <Estado f={f} disponible={d.marcas_disponibles} onAnular={anular} />
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
                        onChange={() => setSeleccion(todas ? new Set() : new Set(filas.map((f) => f.vencimiento_id)))} data-seleccionar-todas />
                    </th>
                    <th scope="col">Fecha</th>
                    <th scope="col">Proveedor</th>
                    <th scope="col">Nº factura</th>
                    <th scope="col" className="num">Importe</th>
                    <th scope="col">Sentido</th>
                    <th scope="col">Forma de pago</th>
                    <th scope="col">Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {filas.map((f) => (
                    <tr key={f.vencimiento_id} className={`e-${f.estado_pago}${seleccion.has(f.vencimiento_id) ? ' elegida' : ''}`} data-vencimiento={f.vencimiento_id}>
                      <td className="ve-col-casilla"><Casilla f={f} marcada={seleccion.has(f.vencimiento_id)} onCambio={alternar} /></td>
                      <td className="fecha">{fechaCorta(f.fecha_vencimiento)}</td>
                      <td className="proveedor"><Proveedor f={f} /></td>
                      <td><Factura f={f} /></td>
                      <td className="num"><Importe f={f} /></td>
                      <td><Sentido f={f} /></td>
                      <td><Forma f={f} /></td>
                      <td><Estado f={f} disponible={d.marcas_disponibles} onAnular={anular} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}

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
