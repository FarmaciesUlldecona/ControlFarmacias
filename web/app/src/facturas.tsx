// H5: listado de Facturas (maqueta web/docs/maquetas/Facturas.dc.html) sobre el contrato `facturas`.
// Solo presenta: diferencias y tolerancias del motor tal cual; importe null = "desconocido" / "importe pendiente".
// Pestañas, filtros, búsqueda, orden y página viven en la URL (?pestana=…&q=…), así "Volver" conserva el listado.
import { useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import type { FacturaListado, FacturasDTO, OpcionFiltroProveedor } from '../server/contrato.ts';
import {
  OPCIONES_CONCILIACION, OPCIONES_NORMALIZACION, OPCIONES_REVISION, etiquetaConciliacion, etiquetaNormalizacion,
  coincideImporte, etiquetaRevision, insigniasFactura,
} from '../server/detalle.ts';
import { useApiRecargable } from './api.ts';
import { euros, fechaCorta, plural } from './formato.ts';
import { ImporteVencimiento } from './inicio.tsx';
import { Cabecera, ImporteTotal, Insignia, MOVIL, useMedia } from './ui.tsx';

export const POR_PAGINA = 50;

// ---------------------------------------------------------------------------
// Pestañas
// ---------------------------------------------------------------------------

const PESTANAS = [
  { clave: 'todas', texto: 'Todas', cumple: () => true },
  { clave: 'conciliadas', texto: 'Conciliadas', cumple: (f: FacturaListado) => f.estado_conciliacion_cf === 'CONCILIADA' },
  { clave: 'pendientes', texto: 'Pendientes de conciliar', cumple: (f: FacturaListado) => f.estado_conciliacion_cf === 'PENDIENTE_CONCILIAR' },
  // Igual que el contador "Requieren revisión" de Inicio: normalización o conciliación en revisión.
  { clave: 'revision', texto: 'En revisión', cumple: (f: FacturaListado) => f.estado_normalizacion === 'REQUIERE_REVISION' || f.estado_conciliacion_cf === 'REVISION_CONCILIACION' },
  { clave: 'no-revisadas', texto: 'No revisadas por Pío', cumple: (f: FacturaListado) => f.estado_revision === 'PENDIENTE_REVISION_PIO' },
] as const;

// ---------------------------------------------------------------------------
// Fechas (ISO YYYY-MM-DD, sin zona: "hoy" es el del contrato)
// ---------------------------------------------------------------------------

function dia(iso: string, n: number): string {
  const d = new Date(iso + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
function lunes(iso: string): string {
  const d = new Date(iso + 'T00:00:00Z');
  return dia(iso, -((d.getUTCDay() + 6) % 7));
}
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const nombreMes = (ym: string) => `${MESES[Number(ym.slice(5, 7)) - 1]} ${ym.slice(0, 4)}`;

// ---------------------------------------------------------------------------
// Filtros
// ---------------------------------------------------------------------------

interface Filtros { proveedor: string; fecha: string; venc: string; estado: string; importe: string; revision: string; q: string }

const IMPORTES = [
  { clave: 'hasta200', texto: 'Hasta 200 €' },
  { clave: '200a1000', texto: 'De 200 a 1.000 €' },
  { clave: 'mas1000', texto: 'Más de 1.000 €' },
  { clave: 'sin', texto: 'Sin importe conocido' },
];
const VENCIMIENTOS = [
  { clave: 'vencido', texto: 'Ya vencido' },
  { clave: 'semana', texto: 'Esta semana' },
  { clave: 'proxima', texto: 'Próxima semana' },
  { clave: 'mes', texto: 'Este mes' },
  { clave: 'pendiente', texto: 'Con importe pendiente' },
  { clave: 'sin', texto: 'Sin vencimiento con fecha' },
];

/** Minúsculas y sin acentos, para la búsqueda. */
export function plano(s: string): string {
  return s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().trim();
}

/** Texto en el que busca la búsqueda global: proveedor (etiqueta y literal), nº de factura e importe (es-ES y con punto). */
/** Texto de la búsqueda global: proveedor (etiqueta y literal) y nº de factura. Los importes van por coincideImporte. */
function textoBusqueda(f: FacturaListado): string {
  return plano([f.proveedor_etiqueta, f.proveedor_literal ?? '', f.proveedor ?? '', f.numero_factura ?? ''].join(' '));
}

/**
 * H5-2: un importe ("5000", "5.000", "5000,1", "45,30 €") busca en el total de la factura y en los importes de sus
 * vencimientos (rangoImporteBuscado); además, cualquier consulta busca como texto en proveedor y nº de factura.
 */
function cumpleBusqueda(f: FacturaListado, q: string): boolean {
  if (q.trim() === '') return true;
  if (coincideImporte(q, [f.importe_total, ...f.vencimientos_importes])) return true;
  return plano(q).split(/\s+/).every((p) => textoBusqueda(f).includes(p));
}

function cumpleFiltros(f: FacturaListado, x: Filtros, hoy: string): boolean {
  if (x.proveedor && f.proveedor_grupo !== x.proveedor) return false;
  if (x.fecha) {
    const ff = f.fecha_factura?.slice(0, 10) ?? null;
    if (x.fecha === 'ultimos30') { if (ff === null || ff < dia(hoy, -30) || ff > hoy) return false; }
    else if (x.fecha.startsWith('mes:')) { if (ff === null || ff.slice(0, 7) !== x.fecha.slice(4)) return false; }
  }
  if (x.venc) {
    const v = f.vencimiento_proximo;
    const fv = v?.fecha_vencimiento?.slice(0, 10) ?? null;
    const l = lunes(hoy);
    const ok = x.venc === 'vencido' ? f.vencimiento_vencido
      : x.venc === 'semana' ? fv !== null && fv >= l && fv <= dia(l, 6)
      : x.venc === 'proxima' ? fv !== null && fv >= dia(l, 7) && fv <= dia(l, 13)
      : x.venc === 'mes' ? fv !== null && fv.slice(0, 7) === hoy.slice(0, 7)
      : x.venc === 'pendiente' ? f.vencimientos_importes.some((i) => i === null)
      : x.venc === 'sin' ? fv === null : true;
    if (!ok) return false;
  }
  if (x.estado) {
    const [eje, valor] = x.estado.split(':');
    if (eje === 'norm' && f.estado_normalizacion !== valor) return false;
    if (eje === 'conc' && f.estado_conciliacion_cf !== valor) return false;
    if (eje === 'dif' && !(f.conciliacion?.diferencia != null && f.conciliacion.diferencia !== 0)) return false;
  }
  if (x.importe) {
    const t = f.importe_total;
    // Abonos: por su valor absoluto (un abono de −45,30 € entra en "Hasta 200 €").
    const a = t === null ? null : Math.abs(t);
    const ok = x.importe === 'sin' ? t === null
      : a === null ? false
      : x.importe === 'hasta200' ? a <= 200
      : x.importe === '200a1000' ? a > 200 && a <= 1000
      : x.importe === 'mas1000' ? a > 1000 : true;
    if (!ok) return false;
  }
  if (x.revision && f.estado_revision !== x.revision) return false;
  return cumpleBusqueda(f, x.q);
}

// ---------------------------------------------------------------------------
// Orden (los null siempre al final)
// ---------------------------------------------------------------------------

type Valor = string | number | null;
const COLUMNAS: { clave: string; texto: string; num?: boolean; valor: (f: FacturaListado) => Valor }[] = [
  { clave: 'proveedor', texto: 'Proveedor', valor: (f) => plano(f.proveedor_etiqueta) },
  { clave: 'numero', texto: 'Nº factura', valor: (f) => f.numero_factura },
  { clave: 'fecha', texto: 'Fecha', valor: (f) => f.fecha_factura },
  { clave: 'total', texto: 'Total', num: true, valor: (f) => f.importe_total },
  { clave: 'vencimiento', texto: 'Vencimiento', valor: (f) => f.vencimiento_proximo?.fecha_vencimiento ?? null },
  { clave: 'normalizacion', texto: 'Normalización', valor: (f) => etiquetaNormalizacion(f.estado_normalizacion).texto },
  { clave: 'conciliacion', texto: 'Conciliación', valor: (f) => etiquetaConciliacion(f.estado_conciliacion_cf).texto },
  { clave: 'revision', texto: 'Revisión Pío', valor: (f) => etiquetaRevision(f.estado_revision).texto },
  { clave: 'pago', texto: 'Pago', valor: () => 'sin datos bancarios' },
];

function comparar(a: Valor, b: Valor, dir: 1 | -1): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return (typeof a === 'number' && typeof b === 'number' ? a - b : String(a).localeCompare(String(b), 'es')) * dir;
}

// ---------------------------------------------------------------------------
// Celdas
// ---------------------------------------------------------------------------

function Conciliacion({ f }: { f: FacturaListado }) {
  const e = etiquetaConciliacion(f.estado_conciliacion_cf);
  const c = f.conciliacion;
  // Diferencia: la del motor, tal cual (solo si existe y no es 0); no evaluable si el motor no pudo calcularla.
  const dif = c === null ? null : c.resultado === 'NO_EVALUABLE' ? 'no evaluable'
    : c.diferencia !== null && c.diferencia !== 0 ? `dif. ${euros(c.diferencia, true)}` : null;
  return (
    <span className="celda-estado">
      <Insignia color={e.color} data-conciliacion={f.estado_conciliacion_cf}>{e.texto}</Insignia>
      {dif && <span className="nota-celda" data-diferencia-motor>{dif}</span>}
    </span>
  );
}

function VencimientoCelda({ f }: { f: FacturaListado }) {
  const v = f.vencimiento_proximo;
  if (v === null) return <span className="tenue">sin vencimientos</span>;
  const mas = f.vencimientos_total - 1;
  return (
    <span className="celda-vencimiento" data-vencimiento-listado>
      <span className="fecha">{fechaCorta(v.fecha_vencimiento)}</span>
      {mas > 0 && <span className="insignia n mas" data-mas title={`${plural(mas, 'vencimiento más', 'vencimientos más')}; todos en el detalle`}>+{mas}</span>}
      {f.vencimiento_vencido && <span className="nota-celda">vencido</span>}
      {v.importe === null && <span className="nota-celda"><ImporteVencimiento v={null} /></span>}
    </span>
  );
}

function Insignias({ f }: { f: FacturaListado }) {
  const xs = insigniasFactura(f);
  if (xs.length === 0) return null;
  return <span className="insignias-fila">{xs.map((i) => <Insignia key={i.clave} color={i.color} data-insignia={i.clave}>{i.texto}</Insignia>)}</span>;
}

function Proveedor({ f, opcion }: { f: FacturaListado; opcion: OpcionFiltroProveedor | undefined }) {
  return (
    <span className="celda-proveedor">
      <span className="nombre-truncado" title={f.proveedor_etiqueta}>{f.proveedor_etiqueta}</span>
      {opcion?.sin_cif && <span className="nota-celda">sin CIF</span>}
    </span>
  );
}

function Fila({ f, opcion }: { f: FacturaListado; opcion: OpcionFiltroProveedor | undefined }) {
  const n = etiquetaNormalizacion(f.estado_normalizacion);
  const r = etiquetaRevision(f.estado_revision);
  return (
    <tr data-factura={f.factura_id}>
      <td className="proveedor"><Proveedor f={f} opcion={opcion} /></td>
      <td>
        <Link to={`/facturas/${f.factura_id}`} className="enlace-factura">{f.numero_factura ?? '(sin número)'}</Link>
        <Insignias f={f} />
      </td>
      <td className="fecha">{fechaCorta(f.fecha_factura)}</td>
      <td className="num total"><ImporteTotal v={f.importe_total} /></td>
      <td><VencimientoCelda f={f} /></td>
      <td><Insignia color={n.color}>{n.texto}</Insignia></td>
      <td><Conciliacion f={f} /></td>
      <td><Insignia color={r.color}>{r.texto}</Insignia></td>
      <td><span className="pago-gris">sin datos bancarios</span></td>
    </tr>
  );
}

function Tarjeta({ f, opcion }: { f: FacturaListado; opcion: OpcionFiltroProveedor | undefined }) {
  const n = etiquetaNormalizacion(f.estado_normalizacion);
  const r = etiquetaRevision(f.estado_revision);
  return (
    <li className="tarjeta tarjeta-factura" data-factura={f.factura_id}>
      <div className="tf-cabecera">
        <Proveedor f={f} opcion={opcion} />
        <span className="tf-total"><ImporteTotal v={f.importe_total} /></span>
      </div>
      <div className="tf-numero">
        <Link to={`/facturas/${f.factura_id}`} className="enlace-factura">{f.numero_factura ?? '(sin número)'}</Link>
        <span className="tenue">{fechaCorta(f.fecha_factura)}</span>
      </div>
      <Insignias f={f} />
      <div className="tf-linea"><span className="tenue">Vencimiento</span><VencimientoCelda f={f} /></div>
      <div className="tf-estados">
        <Insignia color={n.color}>{n.texto}</Insignia>
        <Conciliacion f={f} />
        <Insignia color={r.color}>{r.texto}</Insignia>
      </div>
      <div className="tf-linea"><span className="tenue">Pago</span><span className="pago-gris">sin datos bancarios</span></div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Página
// ---------------------------------------------------------------------------

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

const CLAVES_FILTRO = ['proveedor', 'fecha', 'venc', 'estado', 'importe', 'revision', 'q'] as const;

export function PaginaFacturas() {
  const { carga, recargando, recargar } = useApiRecargable<FacturasDTO>('/api/facturas');
  const [params, setParams] = useSearchParams();
  const movil = useMedia(MOVIL);
  const d = carga.estado === 'ok' ? carga.datos : null;

  const filtros: Filtros = Object.fromEntries(CLAVES_FILTRO.map((k) => [k, params.get(k) ?? ''])) as unknown as Filtros;
  const pestana = PESTANAS.find((p) => p.clave === params.get('pestana')) ?? PESTANAS[0];
  const columna = COLUMNAS.find((c) => c.clave === params.get('orden')) ?? COLUMNAS[2];
  const dir: 1 | -1 = params.get('dir') === 'asc' ? 1 : params.get('dir') === 'desc' ? -1 : columna.clave === 'fecha' ? -1 : 1;
  const pagina = Math.max(1, Number(params.get('pagina')) || 1);

  const cambiar = (cambios: Record<string, string | null>, conservarPagina = false) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(cambios)) { if (v === null || v === '') p.delete(k); else p.set(k, v); }
    if (!conservarPagina) p.delete('pagina');
    setParams(p, { replace: true });
  };

  const filtradas = useMemo(() => (d ? d.facturas.filter((f) => cumpleFiltros(f, filtros, d.hoy)) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [d, params]);
  const enPestana = useMemo(() => filtradas.filter(pestana.cumple)
    .map((f, i) => ({ f, i }))
    .sort((a, b) => comparar(columna.valor(a.f), columna.valor(b.f), dir) || a.i - b.i)
    .map((x) => x.f), [filtradas, pestana, columna, dir]);
  const paginas = Math.max(1, Math.ceil(enPestana.length / POR_PAGINA));
  const actual = Math.min(pagina, paginas);
  const visibles = enPestana.slice((actual - 1) * POR_PAGINA, actual * POR_PAGINA);
  const opcionDe = new Map((d?.proveedores_filtro ?? []).map((o) => [o.clave, o]));
  const hayFiltros = CLAVES_FILTRO.some((k) => filtros[k] !== '');

  const meses = d ? [...new Set(d.facturas.map((f) => f.fecha_factura?.slice(0, 7)).filter((x): x is string => !!x))].sort().reverse() : [];

  return (
    <>
      <Cabecera titulo="Facturas" subtitulo={d ? `${plural(d.facturas.length, 'factura', 'facturas')} de PIO${d.documentos_sin_factura.length ? ` · ${plural(d.documentos_sin_factura.length, 'PDF', 'PDF')} sin factura` : ''}` : 'Facturas normalizadas de PIO'}>
        <button type="button" className="boton-secundario" onClick={recargar} disabled={recargando}>Actualizar</button>
      </Cabecera>

      {carga.estado === 'cargando' && <p className="tenue">Leyendo facturas…</p>}
      {carga.estado === 'error' && (
        <section className="tarjeta bloque error" role="alert">
          <h2>No se han podido leer las facturas</h2>
          <p>La API local respondió <code className="codigo">{carga.mensaje}</code>. Pulsa Actualizar para volver a intentarlo.</p>
        </section>
      )}

      {d && (
        <div className="facturas" data-contrato-ok="facturas" aria-busy={recargando}>
          <label className="buscar">
            <span>Buscar</span>
            <input type="search" name="q" placeholder="Proveedor, nº de factura o importe" value={filtros.q}
              onChange={(e) => cambiar({ q: e.target.value })} />
          </label>

          <div className="pestanas" role="tablist" aria-label="Estado de las facturas">
            {PESTANAS.map((p) => (
              <button key={p.clave} type="button" role="tab" aria-selected={p.clave === pestana.clave}
                className={p.clave === pestana.clave ? 'pestana activa' : 'pestana'} data-pestana={p.clave}
                onClick={() => cambiar({ pestana: p.clave === 'todas' ? null : p.clave })}>
                {p.texto} <span className="pestana-n">{filtradas.filter(p.cumple).length}</span>
              </button>
            ))}
          </div>

          <section className="tarjeta filtros" aria-label="Filtros">
            <Selector nombre="proveedor" etiqueta="Proveedor" todos="Todos" valor={filtros.proveedor} onChange={(v) => cambiar({ proveedor: v })}
              opciones={d.proveedores_filtro.map((o) => ({ valor: o.clave, texto: `${o.etiqueta}${o.sin_cif ? ' (sin CIF)' : ''}` }))} />
            <Selector nombre="fecha" etiqueta="Fecha factura" todos="Todas" valor={filtros.fecha} onChange={(v) => cambiar({ fecha: v })}
              opciones={[{ valor: 'ultimos30', texto: 'Últimos 30 días' }, ...meses.map((m) => ({ valor: `mes:${m}`, texto: nombreMes(m) }))]} />
            <Selector nombre="venc" etiqueta="Vencimiento" todos="Cualquiera" valor={filtros.venc} onChange={(v) => cambiar({ venc: v })}
              opciones={VENCIMIENTOS.map((o) => ({ valor: o.clave, texto: o.texto }))} />
            <Selector nombre="estado" etiqueta="Estado" todos="Todos" valor={filtros.estado} onChange={(v) => cambiar({ estado: v })}
              opciones={[
                ...OPCIONES_NORMALIZACION.map((e) => ({ valor: `norm:${e}`, texto: etiquetaNormalizacion(e).texto, grupo: 'Normalización' })),
                ...OPCIONES_CONCILIACION.map((e) => ({ valor: `conc:${e}`, texto: etiquetaConciliacion(e).texto, grupo: 'Conciliación' })),
                { valor: 'dif:motor', texto: 'Con diferencia del motor', grupo: 'Conciliación' },
              ]} />
            <Selector nombre="importe" etiqueta="Importe" todos="Cualquiera" valor={filtros.importe} onChange={(v) => cambiar({ importe: v })}
              opciones={IMPORTES.map((o) => ({ valor: o.clave, texto: o.texto }))} />
            <Selector nombre="revision" etiqueta="Revisión Pío" todos="Todas" valor={filtros.revision} onChange={(v) => cambiar({ revision: v })}
              opciones={OPCIONES_REVISION.map((e) => ({ valor: e, texto: etiquetaRevision(e).texto }))} />
            {hayFiltros && (
              <button type="button" className="boton-secundario boton-limpiar"
                onClick={() => cambiar(Object.fromEntries(CLAVES_FILTRO.map((k) => [k, null])))}>Quitar filtros</button>
            )}
          </section>

          <p className="tenue resumen-listado" data-resumen-listado aria-live="polite">
            {enPestana.length === 0 ? 'Ninguna factura cumple estos filtros.'
              : `${plural(enPestana.length, 'factura', 'facturas')}${paginas > 1 ? ` · página ${actual} de ${paginas}` : ''}`}
          </p>

          {enPestana.length > 0 && (movil ? (
            <ul className="tarjetas-facturas" aria-label="Facturas">
              {visibles.map((f) => <Tarjeta key={f.factura_id} f={f} opcion={opcionDe.get(f.proveedor_grupo)} />)}
            </ul>
          ) : (
            <div className="tarjeta tabla-desplazable">
              <table className="tabla tabla-facturas">
                <thead>
                  <tr>
                    {COLUMNAS.map((c) => {
                      const activa = c.clave === columna.clave;
                      return (
                        <th key={c.clave} scope="col" className={c.num ? 'num' : undefined}
                          aria-sort={activa ? (dir === 1 ? 'ascending' : 'descending') : 'none'}>
                          <button type="button" className="ordenar" data-ordenar={c.clave}
                            onClick={() => cambiar({ orden: c.clave, dir: activa ? (dir === 1 ? 'desc' : 'asc') : 'asc' })}>
                            {c.texto}<span className="flecha" aria-hidden="true">{activa ? (dir === 1 ? '↑' : '↓') : '↕'}</span>
                          </button>
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {visibles.map((f) => <Fila key={f.factura_id} f={f} opcion={opcionDe.get(f.proveedor_grupo)} />)}
                </tbody>
              </table>
            </div>
          ))}

          {paginas > 1 && (
            <nav className="paginacion" aria-label="Páginas">
              <button type="button" className="boton-secundario" disabled={actual <= 1} onClick={() => cambiar({ pagina: String(actual - 1) }, true)}>Anterior</button>
              <span className="tenue" data-pagina>Página {actual} de {paginas}</span>
              <button type="button" className="boton-secundario" disabled={actual >= paginas} onClick={() => cambiar({ pagina: String(actual + 1) }, true)}>Siguiente</button>
            </nav>
          )}

          <p className="tenue nota-listado">
            Una factura con varios vencimientos muestra el próximo y “+N”; todos se ven en el detalle. Pago: sin datos bancarios en esta fase.
          </p>
        </div>
      )}
    </>
  );
}
