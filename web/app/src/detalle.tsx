// H5: detalle de factura (maqueta web/docs/maquetas/Detalle.dc.html) sobre el contrato `facturaDetalle`.
// Solo presenta: diferencia, tolerancia (R11) y resultado son los del motor, tal cual; importe null nunca es 0.
// Móvil (≤ 900 px): pestañas Resumen / Detalle / PDF.
import { useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  textoIncidencia, type FacturaDetalleDTO, type Fila, type Importe, type Incidencia, type LineaConciliacion, type Vencimiento,
} from '../server/contrato.ts';
import {
  ESTADO_LINEA, TEXTO_HEFAME_BASES, agruparLineas, avisosFactura, baseAlbaran, claveEstadoLinea, etiquetaConciliacion, lineasConDiferencia, origenAplicado, etiquetaNormalizacion, etiquetaResultadoMotor, etiquetaRevision,
  textoEstadoMatching, textoEvento, tipoCasado, type BaseAlbaran, type GrupoLinea,
} from '../server/detalle.ts';
import { useApi } from './api.ts';
import { euros, fechaCorta, fechaHora, plural, tipoPorcentaje } from './formato.ts';
import { ImporteVencimiento } from './inicio.tsx';
import { CLASE, ImporteTotal, Insignia, MOVIL, NombreProveedor, useMedia } from './ui.tsx';

const num = (v: unknown): Importe => (typeof v === 'number' ? v : null);
const txt = (v: unknown): string | null => (typeof v === 'string' ? v : v === null || v === undefined ? null : String(v));

function Euros({ v, fino = false, vacio = '—' }: { v: Importe; fino?: boolean; vacio?: string }) {
  const t = euros(v, fino);
  return t === null ? <span className="tenue">{vacio}</span> : <>{t}</>;
}

function Desplegable({ id, titulo, insignia, abierto = false, children }: {
  id: string; titulo: string; insignia?: ReactNode; abierto?: boolean; children: ReactNode;
}) {
  return (
    <details className="tarjeta desplegable" open={abierto} data-seccion={id}>
      <summary><span className="desplegable-titulo">{titulo}</span>{insignia}</summary>
      <div className="desplegable-cuerpo">{children}</div>
    </details>
  );
}

// ---------------------------------------------------------------------------
// Cabecera resumen
// ---------------------------------------------------------------------------

const TIPO_DOCUMENTAL: Record<string, string> = {
  FACTURA: 'Factura', FACTURA_DUPLICADO: 'Factura (duplicado)', ABONO: 'Abono', FACTURA_RECTIFICATIVA: 'Factura rectificativa',
};

function VencimientosResumen({ vs }: { vs: Vencimiento[] }) {
  if (vs.length === 0) return <span className="tenue">no documentados</span>;
  return (
    <span className="kv-lista">
      {vs.map((v) => (
        <span key={v.vencimiento_id}>{fechaCorta(v.fecha_vencimiento)} · <ImporteVencimiento v={v.importe} /></span>
      ))}
    </span>
  );
}

function CabeceraFactura({ d }: { d: FacturaDetalleDTO }) {
  const f = d.factura;
  const n = etiquetaNormalizacion(f.estado_normalizacion);
  const c = etiquetaConciliacion(f.estado_conciliacion_cf);
  const r = etiquetaRevision(f.estado_revision);
  const tipo = f.tipo_documento_documental ? (TIPO_DOCUMENTAL[f.tipo_documento_documental.toUpperCase()] ?? f.tipo_documento_documental) : 'Tipo de documento no indicado';
  return (
    <section className="tarjeta cabecera-factura" aria-labelledby="t-factura">
      <div className="cf-arriba">
        <div className="cf-titulo">
          <div className="tenue cf-proveedor">
            <NombreProveedor comercial={d.proveedor.comercial} razon={d.proveedor.razon_social} respaldo={f.proveedor} />
            {d.proveedor.cif ? <span className="cf-cif" data-cif> · CIF {d.proveedor.cif}</span> : <span className="cf-cif"> · sin CIF</span>}
          </div>
          <h1 id="t-factura">{f.numero_factura ?? '(sin número)'}</h1>
          <div className="tenue cf-tipo">{tipo}</div>
        </div>
        <div className="cf-botones" aria-label="Acciones (fase 2)">
          {['Validar factura', 'Deshacer validación', 'Reintentar conciliación', 'Reprocesar factura'].map((b) => (
            <button key={b} type="button" className="boton-deshabilitado" disabled title="Disponible en fase 2">{b}</button>
          ))}
        </div>
      </div>
      <dl className="kv-rejilla">
        <div className="kv"><dt>Fecha</dt><dd>{fechaCorta(f.fecha_factura)}</dd></div>
        <div className="kv"><dt>Total</dt><dd className="cifra" data-total><ImporteTotal v={f.importe_total} /></dd></div>
        <div className="kv"><dt>{d.vencimientos.length > 1 ? 'Vencimientos' : 'Vencimiento'}</dt><dd><VencimientosResumen vs={d.vencimientos} /></dd></div>
        <div className="kv"><dt>Normalización</dt><dd><Insignia color={n.color} data-estado="normalizacion">{n.texto}</Insignia></dd></div>
        <div className="kv"><dt>Conciliación</dt><dd><Insignia color={c.color} data-estado="conciliacion">{c.texto}</Insignia></dd></div>
        <div className="kv"><dt>Revisión Pío</dt><dd><Insignia color={r.color} data-estado="revision">{r.texto}</Insignia></dd></div>
        <div className="kv"><dt>Pago</dt><dd className="pago-gris">sin datos bancarios</dd></div>
      </dl>
      <Avisos d={d} />
    </section>
  );
}

function Avisos({ d }: { d: FacturaDetalleDTO }) {
  const avisos = avisosFactura(d);
  if (avisos.length === 0) return <p className="aviso-ok" data-sin-avisos>Sin avisos: la factura está en orden.</p>;
  return (
    <ul className="avisos-detalle" aria-label="Avisos principales">
      {avisos.map((a) => (
        <li key={a.clave} className={`aviso-detalle av-${CLASE[a.color]}`} data-aviso-detalle={a.clave}>
          <span className="aviso-detalle-texto">{a.texto}</span>
          {a.detalle && <span className="aviso-detalle-extra">{a.detalle}</span>}
          {a.codigo && <code className="codigo">{a.codigo}</code>}
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Desplegables
// ---------------------------------------------------------------------------

/** H5-8: "10 % 13,68 €" si consta el tipo; si no, solo el importe (sin guion delante); importe null = "no consta". */
function TipoCuota({ tipo, cuota }: { tipo: Importe; cuota: Importe }) {
  return <>{tipo !== null && <><span className="tipo">{tipoPorcentaje(tipo)}</span> </>}<Euros v={cuota} vacio="no consta" /></>;
}

function Fiscalidad({ d }: { d: FacturaDetalleDTO }) {
  const f = d.factura;
  const xs = d.impuestos;
  const cuadre = f.cuadre_fiscal_correcto === null ? 'Cuadre fiscal sin comprobar'
    : f.cuadre_fiscal_correcto ? 'El desglose de impuestos cuadra con el total'
    : `El desglose de impuestos no cuadra con el total${f.diferencia_cuadre !== null ? `: diferencia de ${euros(f.diferencia_cuadre, true)}` : ''}`;
  return (
    <Desplegable id="fiscalidad" titulo="Fiscalidad" abierto insignia={<Insignia color="gris">{plural(xs.length, 'tipo', 'tipos')}</Insignia>}>
      {xs.length === 0 ? <p className="tenue vacio">La factura no trae desglose de impuestos.</p> : (
        <div className="tabla-desplazable">
          <table className="tabla tabla-fiscal">
            <thead><tr><th scope="col">Tipo</th><th scope="col" className="num">Base</th><th scope="col" className="num">IVA</th><th scope="col" className="num">Recargo eq.</th><th scope="col" className="num">Total tramo</th></tr></thead>
            <tbody>
              {xs.map((x: Fila, i) => (
                // H5-8: sin tipo → "tipo no indicado" y el importe solo (nunca "—" delante, que parecería un signo).
                <tr key={txt(x.id) ?? i} data-impuesto>
                  <td data-tipo-impuesto>{txt(x.concepto) ?? (num(x.tipo_iva) === null ? <span className="tenue">tipo no indicado</span> : `IVA ${tipoPorcentaje(num(x.tipo_iva))}`)}</td>
                  <td className="num"><Euros v={num(x.base_imponible)} vacio="no consta" /></td>
                  <td className="num" data-cuota="iva"><TipoCuota tipo={num(x.tipo_iva)} cuota={num(x.cuota_iva)} /></td>
                  <td className="num" data-cuota="re"><TipoCuota tipo={num(x.tipo_recargo_equivalencia)} cuota={num(x.cuota_recargo_equivalencia)} /></td>
                  <td className="num"><Euros v={num(x.total_tramo)} vacio="no consta" /></td>
                </tr>
              ))}
              <tr className="fila-total">
                <td>Totales de la factura</td>
                <td className="num"><Euros v={f.base_imponible_total} vacio="no consta" /></td>
                <td className="num"><Euros v={f.iva_total} vacio="no consta" /></td>
                <td className="num"><Euros v={f.recargo_equivalencia_total} vacio="no consta" /></td>
                <td className="num"><ImporteTotal v={f.importe_total} /></td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
      <p className="nota-seccion" data-cuadre>{cuadre}</p>
    </Desplegable>
  );
}

/** "Cómo casó": forma de casar el número como dato principal; el tipo de relación, secundario. */
function Casado({ l }: { l: LineaConciliacion }) {
  const c = tipoCasado(l);
  return (
    <span className="casado">
      <Insignia color={c.color} data-casado={c.clave}>{c.texto}</Insignia>
      <span className="nota-celda" data-relacion={c.relacion}>{c.relacion_texto}</span>
      {/* H5-3: en las líneas casadas, el estado del motor en texto llano (en las no casadas ya es el dato principal). */}
      {!c.clave.startsWith('SIN:') && c.clave !== 'ESTADO:SIN_DESCRIPCION' && textoEstadoMatching(l.estado_matching) && (
        <span className="nota-celda" data-estado-matching={l.estado_matching}>{textoEstadoMatching(l.estado_matching)}</span>
      )}
      {c.notas.map((n) => <span key={n} className="nota-celda" data-nota-casado>{n}</span>)}
    </span>
  );
}

/**
 * H5-7: valores por línea del motor (migración 30, cf_detalles_por_linea; conciliacion.py:695-730), tal cual.
 * importe_documental, importe_farmatic o diferencia null → «no consta», nunca 0.
 */
function ImporteLinea({ v, dato }: { v: Importe; dato: string }) {
  return v === null ? <span className="tenue" data-no-consta={dato}>no consta</span> : <span data-importe-linea={dato}>{euros(v)}</span>;
}
function DiferenciaLinea({ l }: { l: LineaConciliacion }) {
  if (l.diferencia === null) return <span className="tenue" data-no-consta="diferencia">no consta</span>;
  return <span data-diferencia-linea className={l.estado_linea === 'DIFERENCIA' ? 'dif-linea' : undefined}>{euros(l.diferencia)}</span>;
}
function EstadoLinea({ l }: { l: LineaConciliacion }) {
  const k = claveEstadoLinea(l);
  const e = ESTADO_LINEA[k];
  return <Insignia color={e.color} data-estado-linea={k}>{e.texto}</Insignia>;
}
/** Base sin IVA del PDF (informativa, no se compara). Hefame: su total de albarán es la base neta. */
function BasePdf({ g, base }: { g: GrupoLinea; base: BaseAlbaran }) {
  const v = base === 'BASE_NETA' ? g.documental.importe_total : g.documental.importe_base;
  return <span className="tenue" data-base-pdf><Euros v={v} vacio="no consta" /></span>;
}
function OrigenFarmatic({ l }: { l: LineaConciliacion }) {
  const o = origenAplicado(l);
  return o ? <span className="tipo tipo-despues" data-origen-aplicado={o}>{o}</span> : null;
}

/** Rótulo de la base de cada importe por línea. Hefame: el importe del PDF es la base neta (hefame.py:155-161). */
function encabezados(base: BaseAlbaran) {
  return {
    pdf: { titulo: 'Importe PDF', base: base === 'BASE_NETA' ? 'base neta sin IVA (Hefame)' : 'con IVA y RE' },
    farmatic: { titulo: 'Importe Farmatic', base: 'con IVA y RE · PUC o PVP' },
    diferencia: { titulo: 'Diferencia', base: 'la del motor · PDF − Farmatic' },
    base: { titulo: 'Base (PDF)', base: 'sin IVA · no se compara' },
  };
}
function Th({ e, num = true, k }: { e: { titulo: string; base: string }; num?: boolean; k: string }) {
  return <th scope="col" className={num ? 'num' : undefined} data-encabezado={k}>{e.titulo}<span className="th-base">{e.base}</span></th>;
}

/** R17: los dos detalles de una línea llevan el mismo importe del PDF, diferencia y estado; si no, se muestran por detalle. */
function valoresComunes(g: GrupoLinea): boolean {
  const [a, ...resto] = g.detalles;
  return resto.every((l) => l.importe_documental === a.importe_documental && l.diferencia === a.diferencia && l.estado_linea === a.estado_linea);
}

function FilasGrupo({ g, base }: { g: GrupoLinea; base: BaseAlbaran }) {
  const n = g.detalles.length;
  const comun = valoresComunes(g);
  return (
    <>
      {g.detalles.map((l, i) => {
        const celdaLinea = (c: ReactNode, cls = 'num') => (comun ? (i === 0 && <td rowSpan={n} className={cls}>{c}</td>) : <td className={cls}>{c}</td>);
        return (
          <tr key={l.detalle_id} data-linea={l.detalle_id} data-estado-linea-fila={l.estado_linea} className={i === n - 1 ? undefined : 'sin-borde'}>
            {i === 0 && (
              <td rowSpan={n} className="linea-pdf">
                <span className="numero">{g.documental.numero ?? 'sin número'}</span>
                <span className="tenue nota-celda">{fechaCorta(g.documental.fecha)}{g.documental.sentido === 'ABONO' ? ' · abono' : ''}</span>
              </td>
            )}
            {celdaLinea(<ImporteLinea v={l.importe_documental} dato="pdf" />)}
            <td className="linea-farmatic">
              {l.numero_albaran_farmatic ? (
                <>
                  <span className="numero">{l.numero_albaran_farmatic}</span>
                  <span className="tenue nota-celda">{fechaCorta(l.fecha_albaran_farmatic)}</span>
                </>
              ) : <span className="tenue">—</span>}
            </td>
            <td className="num"><span data-aplicado><ImporteLinea v={l.importe_farmatic} dato="farmatic" /><OrigenFarmatic l={l} /></span></td>
            {celdaLinea(<DiferenciaLinea l={l} />)}
            {celdaLinea(<EstadoLinea l={l} />, 'estado-linea')}
            <td><Casado l={l} /></td>
            {i === 0 && <td rowSpan={n} className="num"><BasePdf g={g} base={base} /></td>}
          </tr>
        );
      })}
    </>
  );
}

/** Móvil: una tarjeta por línea del PDF con sus albaranes de Farmatic, cómo casaron, diferencia y estado del motor. */
function AlbaranesLista({ grupos, base, explicado }: { grupos: GrupoLinea[]; base: BaseAlbaran; explicado: Importe }) {
  const e = encabezados(base);
  return (
    <>
      <ul className="lista-albaranes">
        {grupos.map((g) => (
          <li key={g.clave} className="la-linea">
            <div className="la-pdf">
              <span><span className="tenue">PDF</span> <strong>{g.documental.numero ?? 'sin número'}</strong> · {fechaCorta(g.documental.fecha)}</span>
              <span className="la-importe"><strong><ImporteLinea v={g.detalles[0].importe_documental} dato="pdf" /></strong><span className="th-base">{e.pdf.base}</span></span>
            </div>
            {g.detalles.map((l) => (
              <div key={l.detalle_id} className="la-farmatic" data-linea={l.detalle_id}>
                <div className="la-fila">
                  <span><span className="tenue">Farmatic</span> {l.numero_albaran_farmatic ?? '—'}</span>
                  <span className="la-importe"><span data-aplicado><ImporteLinea v={l.importe_farmatic} dato="farmatic" /><OrigenFarmatic l={l} /></span><span className="th-base">{e.farmatic.base}</span></span>
                </div>
                <Casado l={l} />
              </div>
            ))}
            {(valoresComunes(g) ? [g.detalles[0]] : g.detalles).map((l) => (
              <div key={`dif-${l.detalle_id}`} className="la-fila">
                <span><span className="tenue">Diferencia del motor</span> <DiferenciaLinea l={l} /></span>
                <EstadoLinea l={l} />
              </div>
            ))}
            <div className="la-fila tenue"><span>Base sin IVA (PDF, no se compara)</span><BasePdf g={g} base={base} /></div>
          </li>
        ))}
      </ul>
      <p className="nota-seccion">Explicado según el motor (con IVA y RE): <strong><Euros v={explicado} vacio="sin dato" /></strong></p>
    </>
  );
}

function Albaranes({ d }: { d: FacturaDetalleDTO }) {
  const grupos = agruparLineas(d.lineas.filter((l) => l.tipo_relacion !== 'MOVIMIENTO_NO_FARMATIC'));
  const sin = d.lineas.filter((l) => l.tipo_relacion === 'SIN_COINCIDENCIA').length;
  const dif = lineasConDiferencia(d.lineas).total;
  const c = d.factura.conciliacion;
  const movil = useMedia(MOVIL);
  const base = baseAlbaran(d.factura.proveedor_literal ?? d.factura.proveedor);
  const e = encabezados(base);
  return (
    <Desplegable id="albaranes" titulo="Albaranes" abierto
      insignia={dif > 0 ? <Insignia color="rojo" data-insignia-seccion>{plural(dif, 'con diferencia', 'con diferencia')}</Insignia>
        : sin > 0 ? <Insignia color="rojo" data-insignia-seccion>{plural(sin, 'sin casar', 'sin casar')}</Insignia>
        : <Insignia color="gris">{plural(grupos.length, 'línea', 'líneas')}</Insignia>}>
      {grupos.length === 0 ? <p className="tenue vacio">No hay líneas de albarán en la conciliación de esta factura.</p>
        : movil ? <AlbaranesLista grupos={grupos} base={base} explicado={c?.importe_explicado ?? null} /> : (
        <div className="tabla-desplazable">
          <table className="tabla tabla-albaranes">
            <thead>
              <tr>
                <th scope="col">Línea del PDF</th><Th k="pdf" e={e.pdf} />
                <th scope="col">Albarán Farmatic</th><Th k="farmatic" e={e.farmatic} />
                <Th k="diferencia" e={e.diferencia} /><th scope="col">Estado</th>
                <th scope="col">Cómo casó</th><Th k="base" e={e.base} />
              </tr>
            </thead>
            <tbody>
              {grupos.map((g) => <FilasGrupo key={g.clave} g={g} base={base} />)}
              <tr className="fila-total">
                <td colSpan={3}>Explicado según el motor</td>
                <td className="num" data-explicado><Euros v={c?.importe_explicado ?? null} vacio="sin dato" /></td>
                <td colSpan={4} />
              </tr>
            </tbody>
          </table>
        </div>
      )}
      {grupos.length > 0 && (
        <p className="nota-seccion" data-nota-bases>
          {base === 'BASE_NETA'
            ? <><strong data-aviso-hefame>Hefame. {TEXTO_HEFAME_BASES}.</strong> Para casar, el motor pasa la base neta a importe con IVA sin guardarlo.</>
            : 'El motor compara el importe de cada albarán del PDF con el PUC (o el PVP) de Farmatic, los dos con IVA y recargo. Cada línea coincide si su diferencia no pasa de 0,05 €.'}
          {' '}La diferencia total de la factura, con su tolerancia, está en Conciliación.
        </p>
      )}
    </Desplegable>
  );
}

function Movimientos({ d }: { d: FacturaDetalleDTO }) {
  const lineas = d.lineas.filter((l) => l.tipo_relacion === 'MOVIMIENTO_NO_FARMATIC');
  const total = d.movimientos.length + d.ajustes.length;
  return (
    <Desplegable id="movimientos" titulo="Cargos y abonos" abierto={total > 0}
      insignia={<Insignia color="gris">{total === 0 ? 'ninguno' : plural(total, 'movimiento', 'movimientos')}</Insignia>}>
      {total === 0 ? <p className="tenue vacio">Esta factura no tiene cargos, servicios ni abonos fuera de los albaranes.</p> : (
        <div className="tabla-desplazable">
          <table className="tabla">
            <thead><tr><th scope="col">Concepto</th><th scope="col">Sentido</th>
              <th scope="col" className="num" data-encabezado="mov-importe">Importe (PDF)<span className="th-base">con IVA y RE</span></th>
              <th scope="col" className="num" data-encabezado="mov-base">Base (PDF)<span className="th-base">sin IVA</span></th>
              <th scope="col" className="num" data-encabezado="mov-aplicado">Aplicado (motor)<span className="th-base">su base, abajo</span></th>
              <th scope="col">En la conciliación</th></tr></thead>
            <tbody>
              {d.movimientos.map((m, i) => {
                const l = lineas.find((x) => x.factura_movimiento_id === m.id);
                const sentido = txt(m.sentido);
                // magnitud_usada (conciliacion.py:703-722): IMPORTE = importe con IVA; BASE = base sin IVA (+ ajustes fiscales).
                const magnitud = l?.magnitud_usada === 'IMPORTE' ? 'con IVA y RE' : l?.magnitud_usada === 'BASE' ? 'base sin IVA' : null;
                return (
                  <tr key={txt(m.id) ?? i} data-movimiento>
                    <td>{txt(m.descripcion_literal) ?? 'sin concepto'}</td>
                    <td>{sentido === 'CARGO' ? 'Cargo' : sentido === 'ABONO' ? 'Abono' : <span className="desconocido">no documentado</span>}</td>
                    <td className="num"><Euros v={num(m.importe)} vacio="no consta" /></td>
                    <td className="num tenue"><Euros v={num(m.base)} vacio="no consta" /></td>
                    <td className="num" data-aplicado-movimiento>{l ? <><Euros v={l.importe_aplicado} vacio="no aplicado" />{magnitud && <span className="nota-celda" data-magnitud={l.magnitud_usada}>{magnitud}</span>}</> : <span className="tenue">—</span>}</td>
                    <td>{l ? <Casado l={l} /> : <span className="tenue">—</span>}</td>
                  </tr>
                );
              })}
              {d.ajustes.map((a, i) => (
                <tr key={txt(a.id) ?? `aj${i}`} data-ajuste>
                  <td>{txt(a.descripcion) ?? txt(a.tipo_ajuste) ?? 'ajuste'}</td>
                  <td>Ajuste</td>
                  <td className="num"><Euros v={num(a.importe)} vacio="no consta" /></td>
                  <td className="tenue">—</td><td className="tenue">—</td><td className="tenue">—</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Desplegable>
  );
}

const SENTIDO: Record<Vencimiento['sentido'], string> = { CARGO: 'cargo', ABONO: 'abono', NO_DOCUMENTADO: 'sentido no documentado' };

/**
 * H4c: vencimientos de la factura. Importe null = "importe pendiente" (R14); junto a él, el total de la factura
 * como referencia separada y rotulada "total factura": nunca se asigna al vencimiento.
 */
function VencimientosFactura({ vencimientos }: { vencimientos: Vencimiento[] }) {
  return (
    <Desplegable id="vencimientos" titulo="Vencimientos" abierto insignia={<Insignia color="gris">{vencimientos.length}</Insignia>}>
      {vencimientos.length === 0 ? (
        <p className="tenue vacio">La factura no documenta vencimientos.</p>
      ) : (
        <div className="tabla-desplazable">
        <table className="tabla detalle-vencimientos">
          <thead><tr><th scope="col">Vencimiento</th><th scope="col">Fecha</th><th scope="col" className="num">Importe</th><th scope="col" className="col-pago">Pago</th></tr></thead>
          <tbody>
            {vencimientos.map((v) => {
              const total = euros(v.importe_factura);
              return (
                <tr key={v.vencimiento_id} data-vencimiento={v.vencimiento_id}>
                  <td>
                    {v.orden ?? '?'} de {v.vencimientos_factura}
                    <span className="nota" data-sentido={v.sentido}>{SENTIDO[v.sentido]}</span>
                  </td>
                  <td className="fecha">{fechaCorta(v.fecha_vencimiento)}</td>
                  <td className="num">
                    <ImporteVencimiento v={v.importe} />
                    {v.importe === null && (
                      <span className="referencia-total" data-total-factura>
                        total factura: <strong>{total ?? 'no consta'}</strong> (referencia)
                      </span>
                    )}
                  </td>
                  <td className="pago-gris col-pago">sin datos bancarios</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      )}
    </Desplegable>
  );
}

function Regla({ regla }: { regla: unknown }) {
  if (!regla || typeof regla !== 'object' || Array.isArray(regla)) return null;
  const r = regla as Record<string, unknown>;
  // Parámetros literales del motor (texto "0.0500"): solo se formatean como euros, no se recalcula nada.
  const e = (v: unknown) => { const n = Number(v); return Number.isFinite(n) ? euros(n, true) : String(v); };
  const partes: string[] = [];
  if (r.suelo !== undefined) partes.push(`suelo ${e(r.suelo)}`);
  if (r.por_albaran !== undefined) partes.push(`${e(r.por_albaran)} por albarán`);
  if (r.albaranes_casados !== undefined) partes.push(`${String(r.albaranes_casados)} albaranes casados`);
  if (r.tope !== undefined) partes.push(`tope ${e(r.tope)}`);
  return partes.length ? <span className="nota-celda" data-regla-r11>R11: {partes.join(' · ')}</span> : null;
}

function ConciliacionSeccion({ d }: { d: FacturaDetalleDTO }) {
  const f = d.factura;
  const c = f.conciliacion;
  const res = etiquetaResultadoMotor(c?.resultado ?? null);
  return (
    <Desplegable id="conciliacion" titulo="Conciliación" abierto
      insignia={c ? <Insignia color={res.color}>{res.texto}</Insignia> : <Insignia color="gris">sin conciliar</Insignia>}>
      {c === null ? (
        <p className="tenue vacio">{f.requiere_conciliacion_albaranes === false
          ? 'Esta factura no necesita conciliarse con albaranes.'
          : 'La factura todavía no se ha conciliado con Farmatic.'}</p>
      ) : (
        <dl className="kv-rejilla kv-pequena">
          <div className="kv"><dt>Resultado del motor</dt><dd><span data-resultado-motor>{res.texto}</span> <code className="codigo">{c.resultado ?? 'sin resultado'}</code></dd></div>
          <div className="kv"><dt>Total según el motor</dt><dd><Euros v={c.importe_factura} fino vacio="sin dato" /></dd></div>
          <div className="kv"><dt>Explicado</dt><dd><Euros v={c.importe_explicado} fino vacio="sin dato" /></dd></div>
          <div className="kv"><dt>Diferencia exacta</dt><dd data-diferencia-exacta className={c.diferencia && c.resultado !== 'CONCILIADA' ? 'dif-linea' : undefined}>
            {c.diferencia === null ? <span className="tenue">no evaluable</span> : euros(c.diferencia, true)}</dd></div>
          <div className="kv"><dt>Tolerancia (motor, R11)</dt><dd><span data-tolerancia><Euros v={c.tolerancia} fino vacio="sin dato" /></span><Regla regla={c.tolerancia_regla} /></dd></div>
          <div className="kv"><dt>Último intento</dt><dd>
            <span data-ultimo-intento>{c.intento !== null ? `Intento ${c.intento}` : 'Intento sin número'} · {fechaHora(c.finalizado_at)}</span>
            <span className="nota-celda">{plural(f.conciliacion_intentos ?? 0, 'intento', 'intentos')}{f.conciliacion_intentos_fallo ? `, ${plural(f.conciliacion_intentos_fallo, 'fallido', 'fallidos')}` : ''}
              {f.conciliacion_proximo_at ? ` · próximo: ${fechaHora(f.conciliacion_proximo_at)}` : ''}</span>
          </dd></div>
        </dl>
      )}
    </Desplegable>
  );
}

/** H4d: incidencias de la factura en texto llano; el código técnico solo como etiqueta pequeña. Aquí sí salen las INFO y MONEDA_NO_DOCUMENTADA. */
function IncidenciasFactura({ incidencias }: { incidencias: Incidencia[] }) {
  const abiertas = incidencias.filter((i) => i.estado === 'ABIERTA').length;
  return (
    <Desplegable id="incidencias" titulo="Incidencias" abierto
      insignia={<Insignia color={abiertas ? 'naranja' : 'gris'}>{abiertas ? plural(abiertas, 'abierta', 'abiertas') : 'ninguna abierta'}</Insignia>}>
      {incidencias.length === 0 ? (
        <p className="tenue vacio">La factura no tiene incidencias.</p>
      ) : (
        <ul className="casos casos-detalle">
          {incidencias.map((i) => (
            <li key={i.incidencia_id} className="caso" data-incidencia={i.codigo}>
              <div className="caso-cuerpo">
                <span className="caso-texto">{textoIncidencia(i)}</span>
                <span className="caso-ref tenue">
                  <span>{i.estado === 'ABIERTA' ? 'Abierta' : 'Resuelta'}{i.bloqueante ? ' · bloqueante' : ''}{i.severidad ? ` · ${i.severidad.toLowerCase()}` : ''}</span>
                  <span className="caso-fecha">{fechaCorta(i.created_at)}</span>
                  <code className="codigo">{i.codigo}</code>
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Desplegable>
  );
}

function Historial({ d }: { d: FacturaDetalleDTO }) {
  return (
    <Desplegable id="historial" titulo="Historial" insignia={<Insignia color="gris">{d.historial.length}</Insignia>}>
      {d.historial.length === 0 ? <p className="tenue vacio">Sin eventos registrados.</p> : (
        <table className="tabla">
          <tbody>
            {d.historial.map((h) => (
              <tr key={h.evento_id} data-evento={h.evento}>
                <td className="fecha tenue">{fechaHora(h.created_at)}</td>
                <td>{textoEvento(h.evento)}{h.factura_id === null ? <span className="nota-celda">del PDF</span> : null}</td>
                <td className="tenue"><code className="codigo">{h.evento}</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Desplegable>
  );
}

function Evidencia({ d }: { d: FacturaDetalleDTO }) {
  const n = d.normalizacion;
  const sino = (v: boolean | null) => (v === null ? 'sin dato' : v ? 'sí' : 'no');
  const filas: [string, ReactNode][] = [
    ['Extractor', n.extractor_usado ?? 'sin dato'],
    ['Normalizador', n.normalizador_version ?? 'sin dato'],
    ['Ejecución', `${n.estado ?? 'sin estado'} · ${n.disparador ?? 'sin disparador'} · ${fechaHora(n.finalizado_at)}`],
    ['OCR', sino(n.uso_ocr)],
    ['IA (Luna)', n.uso_luna ? `sí · ${n.luna_modelo ?? 'modelo sin dato'} · ${n.tokens_total ?? '?'} tokens · ${euros(n.coste_luna, true) ?? 'coste desconocido'}${n.luna_campos.length ? ` · campos: ${n.luna_campos.join(', ')}` : ''}` : 'no utilizada'],
    ['Documento', `${d.documento.archivo_nombre ?? 'sin nombre'} · ${d.documento.estado_lectura ?? 'sin estado'}`],
    ['Huella del PDF', d.documento.archivo_hash ?? 'sin dato'],
    ['Proveedor', `CIF ${d.proveedor.cif ?? 'no consta'} · id albaranes ${d.proveedor.id_proveedor_albaranes ?? 'no consta'}`],
    ['Tipo documental', d.factura.tipo_documento_documental ?? 'no indicado'],
    ['Códigos de incidencia', d.incidencias.map((i) => i.codigo).join(', ') || 'ninguno'],
  ];
  return (
    <Desplegable id="evidencia" titulo="Evidencia técnica">
      <dl className="evidencia">
        {filas.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
      </dl>
      {d.lineas.length > 0 && (
        <ul className="evidencia-lineas" aria-label="Códigos por línea">
          {d.lineas.map((l) => (
            <li key={l.detalle_id}><code className="codigo">{[l.orden, l.tipo_relacion, l.estado_linea, l.estado_matching, l.clase_numero, l.regla, l.papel_r17].filter((x) => x !== null && x !== undefined).join(' · ')}</code></li>
          ))}
        </ul>
      )}
    </Desplegable>
  );
}

// ---------------------------------------------------------------------------
// PDF original
// ---------------------------------------------------------------------------

function PdfOriginal({ d }: { d: FacturaDetalleDTO }) {
  const f = d.factura;
  const paginas = f.pagina_inicio !== null
    ? `páginas ${f.pagina_inicio}${f.pagina_fin !== null && f.pagina_fin !== f.pagina_inicio ? `–${f.pagina_fin}` : ''}${d.documento.numero_paginas ? ` de ${d.documento.numero_paginas}` : ''}`
    : null;
  return (
    <aside className="tarjeta pdf-original" aria-labelledby="t-pdf" data-pdf-original={d.pdf_original.disponible ? 'disponible' : 'no-disponible'}>
      <div className="pdf-cabecera">
        <h2 id="t-pdf">PDF original</h2>
        {paginas && <span className="tenue">{paginas}</span>}
      </div>
      <div className="pdf-recuadro">
        <strong>PDF original: disponible en una fase posterior</strong>
        <p>El acceso de solo lectura de la web no puede abrir el almacén de archivos donde están los PDF. En esta fase no se piden permisos nuevos.</p>
        {d.documento.archivo_nombre && <p className="tenue pdf-nombre" title={d.documento.archivo_nombre}>{d.documento.archivo_nombre}</p>}
      </div>
      {d.otras_facturas_pdf.length > 0 && (
        <div className="pdf-otras">
          <span className="tenue">El PDF contiene también:</span>
          <ul>
            {d.otras_facturas_pdf.map((o) => (
              <li key={o.factura_id}><Link to={`/facturas/${o.factura_id}`}>{o.numero_factura ?? '(sin número)'}</Link>
                {o.pagina_inicio !== null && <span className="tenue"> · pág. {o.pagina_inicio}{o.pagina_fin && o.pagina_fin !== o.pagina_inicio ? `–${o.pagina_fin}` : ''}</span>}</li>
            ))}
          </ul>
        </div>
      )}
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Página
// ---------------------------------------------------------------------------

const PESTANAS_MOVIL = [
  { clave: 'resumen', texto: 'Resumen' },
  { clave: 'detalle', texto: 'Detalle' },
  { clave: 'pdf', texto: 'PDF' },
] as const;
type PestanaMovil = (typeof PESTANAS_MOVIL)[number]['clave'];

function Secciones({ d }: { d: FacturaDetalleDTO }) {
  return (
    <div className="secciones">
      <Fiscalidad d={d} />
      <Albaranes d={d} />
      <Movimientos d={d} />
      <VencimientosFactura vencimientos={d.vencimientos} />
      <ConciliacionSeccion d={d} />
      <IncidenciasFactura incidencias={d.incidencias} />
      <Historial d={d} />
      <Evidencia d={d} />
    </div>
  );
}

export function PaginaDetalle() {
  const { id = '' } = useParams();
  const carga = useApi<FacturaDetalleDTO>(`/api/facturas/${encodeURIComponent(id)}`);
  const movil = useMedia(MOVIL);
  const [pestana, setPestana] = useState<PestanaMovil>('resumen');
  const d = carga.estado === 'ok' ? carga.datos : null;

  return (
    <>
      <p className="migas"><Link to="/facturas">← Volver a facturas</Link></p>
      {carga.estado === 'cargando' && <p className="tenue">Leyendo la factura…</p>}
      {carga.estado === 'error' && (
        <section className="tarjeta bloque error" role="alert">
          <h1>{carga.mensaje === 'FACTURA_NO_ENCONTRADA' ? 'Factura no encontrada' : 'No se ha podido leer la factura'}</h1>
          <p>La API local respondió <code className="codigo">{carga.mensaje}</code>.</p>
        </section>
      )}
      {d && (
        <div className="detalle" data-contrato-ok="facturaDetalle">
          {movil ? (
            <>
              <div className="pestanas pestanas-movil" role="tablist" aria-label="Partes de la factura">
                {PESTANAS_MOVIL.map((p) => (
                  <button key={p.clave} type="button" role="tab" aria-selected={pestana === p.clave}
                    className={pestana === p.clave ? 'pestana activa' : 'pestana'} onClick={() => setPestana(p.clave)}>{p.texto}</button>
                ))}
              </div>
              {pestana === 'resumen' && <CabeceraFactura d={d} />}
              {pestana === 'detalle' && <Secciones d={d} />}
              {pestana === 'pdf' && <PdfOriginal d={d} />}
            </>
          ) : (
            <>
              <CabeceraFactura d={d} />
              <div className="detalle-cuerpo">
                <Secciones d={d} />
                <PdfOriginal d={d} />
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}
