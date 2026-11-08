import type { ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import type { FacturaDetalleDTO, FacturasDTO } from '../server/contrato.ts';
import { useApi, type Carga } from './api.ts';
import type { Pantalla } from './App.tsx';

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
