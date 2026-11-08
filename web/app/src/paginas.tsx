import type { ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { textoIncidencia, type FacturaDetalleDTO, type FacturasDTO, type Incidencia, type Vencimiento } from '../server/contrato.ts';
import { useApi, type Carga } from './api.ts';
import type { Pantalla } from './App.tsx';
import { euros, fechaCorta } from './formato.ts';
import { ImporteVencimiento } from './inicio.tsx';

function Cabecera({ titulo, subtitulo }: { titulo: string; subtitulo: string }) {
  return (
    <header className="cabecera">
      <div>
        <h1>{titulo}</h1>
        <div className="tenue subtitulo">{subtitulo}</div>
      </div>
      <button type="button" className="boton-deshabilitado" disabled title="Disponible en fase 2">
        Sincronizar ahora
      </button>
    </header>
  );
}

function EstadoContrato({ bloque, carga }: { bloque: string; carga: Carga<unknown> }) {
  if (carga.estado === 'cargando') return <span className="insignia n">Contrato {bloque}: cargando…</span>;
  if (carga.estado === 'error') return <span className="insignia r">Contrato {bloque}: error ({carga.mensaje})</span>;
  return <span className="insignia g" data-contrato-ok={bloque}>Contrato {bloque}: datos recibidos</span>;
}

function EnConstruccion({ bloque, carga, children }: { bloque: string; carga: Carga<unknown>; children?: ReactNode }) {
  return (
    <section className="tarjeta en-construccion" aria-label="En construcción">
      <div className="en-construccion-titulo">
        <span className="punto pn" aria-hidden="true" />
        <h2>En construcción</h2>
      </div>
      <p className="tenue">Esta pantalla se construirá en el siguiente hito sobre el contrato de datos.</p>
      <div><EstadoContrato bloque={bloque} carga={carga} /></div>
      {children}
    </section>
  );
}

export function PaginaEnConstruccion({ pantalla }: { pantalla: Pantalla }) {
  const carga = useApi<unknown>(pantalla.api);
  return (
    <>
      <Cabecera titulo={pantalla.titulo} subtitulo={pantalla.subtitulo} />
      <EnConstruccion bloque={pantalla.bloque} carga={carga} />
    </>
  );
}

/** Facturas: además del aviso, acceso provisional al detalle de cada factura. */
export function PaginaFacturas({ pantalla }: { pantalla: Pantalla }) {
  const carga = useApi<FacturasDTO>(pantalla.api);
  return (
    <>
      <Cabecera titulo={pantalla.titulo} subtitulo={pantalla.subtitulo} />
      <EnConstruccion bloque={pantalla.bloque} carga={carga}>
        {carga.estado === 'ok' && (
          <nav className="acceso-provisional" aria-label="Acceso provisional al detalle">
            <span className="tenue">Acceso provisional al detalle:</span>
            <ul>
              {carga.datos.facturas.map((f) => (
                <li key={f.factura_id}>
                  <Link to={`/facturas/${f.factura_id}`}>{f.numero_factura ?? '(sin número)'}</Link>
                </li>
              ))}
            </ul>
          </nav>
        )}
      </EnConstruccion>
    </>
  );
}

const SENTIDO: Record<Vencimiento['sentido'], string> = { CARGO: 'cargo', ABONO: 'abono', NO_DOCUMENTADO: 'sentido no documentado' };

/**
 * H4c: vencimientos de la factura. Importe null = "importe pendiente" (R14); junto a él, el total de la factura
 * como referencia separada y rotulada "total factura": nunca se asigna al vencimiento.
 */
function VencimientosFactura({ vencimientos }: { vencimientos: Vencimiento[] }) {
  return (
    <section className="tarjeta bloque detalle-vencimientos" aria-labelledby="t-vencimientos-factura">
      <h2 id="t-vencimientos-factura">Vencimientos</h2>
      {vencimientos.length === 0 ? (
        <p className="tenue vacio">La factura no documenta vencimientos.</p>
      ) : (
        <table className="tabla">
          <thead><tr><th scope="col">Vencimiento</th><th scope="col">Fecha</th><th scope="col" className="num">Importe</th></tr></thead>
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
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}

/** H4d: incidencias de la factura en texto llano; el código técnico solo como etiqueta pequeña. Aquí sí salen las INFO y MONEDA_NO_DOCUMENTADA. */
function IncidenciasFactura({ incidencias }: { incidencias: Incidencia[] }) {
  return (
    <section className="tarjeta bloque detalle-vencimientos" aria-labelledby="t-incidencias-factura">
      <h2 id="t-incidencias-factura">Incidencias</h2>
      {incidencias.length === 0 ? (
        <p className="tenue vacio">La factura no tiene incidencias.</p>
      ) : (
        <ul className="casos casos-detalle">
          {incidencias.map((i) => (
            <li key={i.incidencia_id} className="caso" data-incidencia={i.codigo}>
              <div className="caso-cuerpo">
                <span className="caso-texto">{textoIncidencia(i)}</span>
                <span className="caso-ref tenue">
                  <span>{i.estado === 'ABIERTA' ? 'Abierta' : 'Resuelta'}{i.bloqueante ? ' · bloqueante' : ''}</span>
                  <code className="codigo">{i.codigo}</code>
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function PaginaDetalle() {
  const { id = '' } = useParams();
  const carga = useApi<FacturaDetalleDTO>(`/api/facturas/${encodeURIComponent(id)}`);
  const f = carga.estado === 'ok' ? carga.datos.factura : null;
  const titulo = f ? `Factura ${f.numero_factura ?? '(sin número)'}` : 'Factura';
  const subtitulo = f ? (f.proveedor ?? 'Proveedor sin identificar') : 'Detalle de la factura';
  return (
    <>
      <p className="migas"><Link to="/facturas">Facturas</Link> / Detalle</p>
      <Cabecera titulo={titulo} subtitulo={subtitulo} />
      <EnConstruccion bloque="facturaDetalle" carga={carga} />
      {carga.estado === 'ok' && <VencimientosFactura vencimientos={carga.datos.vencimientos} />}
      {carga.estado === 'ok' && <IncidenciasFactura incidencias={carga.datos.incidencias} />}
    </>
  );
}

export function PaginaNoEncontrada() {
  return (
    <>
      <Cabecera titulo="Página no encontrada" subtitulo="La ruta no existe en la fase 1" />
      <p><Link to="/">Volver a Inicio</Link></p>
    </>
  );
}
