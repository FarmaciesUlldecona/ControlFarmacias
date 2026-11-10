import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useApi, type Carga } from './api.ts';
import type { Pantalla } from './App.tsx';
import { Cabecera } from './ui.tsx';

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

export function PaginaNoEncontrada() {
  return (
    <>
      <Cabecera titulo="Página no encontrada" subtitulo="La ruta no existe en la fase 1" />
      <p><Link to="/">Volver a Inicio</Link></p>
    </>
  );
}
