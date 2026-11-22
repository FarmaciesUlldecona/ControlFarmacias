// H8 (migración 36): «para revisar» de la noche automática (cf_noches_automaticas.para_revisar, la noche más reciente).
// La noche no reclama nada: la factura sigue pendiente de conciliar, sin incidencia ni conciliación. Por eso va en
// naranja (revisar), nunca en rojo ni como reclamación. Textos llanos y valor del motor tal cual (server/contrato.ts).
import { Link } from 'react-router-dom';
import type { ElementoRevisarNoche, RevisarNoche } from '../server/contrato.ts';
import { fechaCorta, plural } from './formato.ts';
import { NombreProveedor } from './ui.tsx';

const ddmm = (fecha: string) => fechaCorta(fecha).slice(0, 5);

/** Título del grupo: «Revisar: detectado por la noche (19/11/2026)». */
export function tituloRevisarNoche(r: RevisarNoche): string {
  return `Revisar: detectado por la noche${r.fecha ? ` (${fechaCorta(r.fecha)})` : ''}`;
}

/** Mensaje cuando no hay elementos que mostrar (o la lista no se puede leer); null si hay elementos. */
export function vacioRevisarNoche(r: RevisarNoche): string | null {
  if (r.fecha === null) return 'Todavía no hay ninguna noche automática registrada';
  if (!r.lista_valida) return `No se puede leer la lista para revisar de la noche del ${ddmm(r.fecha)}`;
  if (r.elementos.length === 0) return `Nada para revisar en la noche del ${ddmm(r.fecha)}`;
  return null;
}

function Evidencia({ e }: { e: ElementoRevisarNoche }) {
  const filas = Object.entries(e.evidencia);
  if (filas.length === 0 && e.tipo_literal === null) return null;
  return (
    <details className="noche-evidencia" data-noche-evidencia>
      <summary>Evidencia técnica</summary>
      <ul>
        {e.tipo_literal !== null && <li><code className="codigo">tipo: {e.tipo_literal}</code></li>}
        {filas.map(([k, v]) => (
          <li key={k}><code className="codigo">{k}: {typeof v === 'string' ? v : JSON.stringify(v)}</code></li>
        ))}
      </ul>
    </details>
  );
}

function Elemento({ e }: { e: ElementoRevisarNoche }) {
  const referencia = e.factura_id !== null ? e.numero_factura ?? 'factura sin número' : e.archivo_nombre ?? 'PDF sin nombre';
  return (
    <li className="caso" data-noche-elemento={e.tipo}>
      <div className="caso-cuerpo">
        <span className="caso-texto" data-noche-texto>{e.texto}</span>
        <span className="caso-ref tenue">
          {e.factura_id !== null && (e.proveedor_comercial !== null || e.proveedor_razon_social !== null)
            && <NombreProveedor comercial={e.proveedor_comercial} razon={e.proveedor_razon_social} respaldo={null} />}
          <span className="caso-referencia">{e.factura_id !== null ? referencia : `PDF ${referencia}`}</span>
        </span>
        <Evidencia e={e} />
      </div>
      <Link to={e.enlace} className="aviso-abrir" aria-label={`Abrir: ${e.texto} (${referencia})`}>Abrir</Link>
    </li>
  );
}

/** Conciliación: grupo propio con sus elementos, texto llano y enlace. */
export function RevisarNocheGrupo({ r }: { r: RevisarNoche }) {
  const vacio = vacioRevisarNoche(r);
  return (
    <section className="tarjeta bloque noche" aria-labelledby="t-noche" data-revisar-noche data-color="naranja">
      <div className="bloque-cabecera">
        <h2 id="t-noche"><span className="punto po" aria-hidden="true" /> {tituloRevisarNoche(r)}</h2>
        {vacio === null && <span className="insignia o" data-noche-casos={r.elementos.length}>{plural(r.elementos.length, 'caso', 'casos')}</span>}
      </div>
      <p className="tenue bloque-nota">
        Lo que la conciliación automática de la noche ha dejado para revisar. No es una reclamación: las facturas siguen
        pendientes de conciliar.
      </p>
      {vacio !== null ? <p className="tenue vacio" data-noche-vacio>{vacio}</p> : (
        <ul className="casos noche-casos">
          {r.elementos.map((e, n) => <Elemento key={`${e.tipo}-${e.factura_id ?? e.documento_id}-${n}`} e={e} />)}
        </ul>
      )}
    </section>
  );
}

/** Inicio: solo el recuento y el enlace a Conciliación. */
export function RevisarNocheResumen({ r }: { r: RevisarNoche }) {
  const vacio = vacioRevisarNoche(r);
  const naranja = vacio === null || (r.fecha !== null && !r.lista_valida);
  return (
    <section className={`tarjeta noche-resumen borde-${naranja ? 'naranja' : 'gris'}`} aria-label="Revisar: detectado por la noche" data-revisar-noche-inicio>
      <span className={`punto ${naranja ? 'po' : 'pn'}`} aria-hidden="true" />
      <span className="noche-resumen-texto">
        {vacio ?? <>{tituloRevisarNoche(r)}: <strong data-noche-recuento={r.elementos.length}>{plural(r.elementos.length, 'caso', 'casos')}</strong></>}
      </span>
      {vacio === null && <Link to="/conciliacion" className="enlace-bloque">Ver en Conciliación</Link>}
    </section>
  );
}
