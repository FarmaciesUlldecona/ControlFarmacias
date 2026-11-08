// H4: pantalla Inicio (maqueta web/docs/maquetas/Main.dc.html) sobre el contrato `inicio`.
// Solo presenta: no recalcula diferencias ni tolerancias; importe null = "desconocido", nunca 0.
import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { Alerta, Color, Importe, InicioDTO, ItemAtencion, Vencimiento } from '../server/contrato.ts';
import { useApiRecargable } from './api.ts';
import { euros, fechaCorta, fechaLarga, hora, plural, porcentaje } from './formato.ts';

const CLASE: Record<Color, string> = { verde: 'g', azul: 'b', naranja: 'o', rojo: 'r', gris: 'n' };
const PUNTO: Record<Color, string> = { verde: 'pg', azul: 'pb', naranja: 'po', rojo: 'pr', gris: 'pn' };
/** Orden de "Necesita tu atención": incidencias primero, información al final. */
const PRIORIDAD: Record<Color, number> = { rojo: 0, naranja: 1, azul: 2, gris: 3, verde: 4 };
const VISIBLES = 8;

// ---------------------------------------------------------------------------
// Contadores (sin importes)
// ---------------------------------------------------------------------------

interface Contador { clave: string; etiqueta: string; n: number; color: Color; pista: string; a: string }

function contadores(d: InicioDTO): Contador[] {
  const bloq = d.incidencias.bloqueantes;
  return [
    { clave: 'conciliadas', etiqueta: 'Conciliadas', n: d.conciliacion.CONCILIADA ?? 0, color: 'verde', pista: 'Cuadran con sus albaranes', a: '/conciliacion' },
    { clave: 'pendientes-conciliar', etiqueta: 'Pendientes de conciliar', n: d.conciliacion.PENDIENTE_CONCILIAR ?? 0, color: 'azul', pista: 'A la espera de cuadrar con albaranes', a: '/conciliacion' },
    { clave: 'requieren-revision', etiqueta: 'Requieren revisión', n: d.requieren_revision, color: 'naranja', pista: 'Normalización o conciliación incompleta', a: '/conciliacion' },
    { clave: 'pendientes-procesar', etiqueta: 'Pendientes de procesar', n: d.documentos.pendientes_procesar, color: 'azul', pista: 'PDF en cola de lectura', a: '/facturas' },
    { clave: 'con-defecto', etiqueta: 'Con defecto', n: d.documentos.con_defecto, color: 'rojo', pista: 'PDF ilegible o en revisión manual', a: '/facturas' },
    { clave: 'sin-automatizar', etiqueta: 'Sin automatizar', n: d.documentos.sin_automatizar, color: 'gris', pista: 'Proveedor que aún no se lee solo', a: '/facturas' },
    { clave: 'incidencias', etiqueta: 'Incidencias abiertas', n: d.incidencias.abiertas, color: 'rojo',
      pista: bloq === 0 ? 'Ninguna bloqueante' : `${plural(bloq, 'bloqueante', 'bloqueantes')}`, a: '#atencion' },
  ];
}

function Contadores({ d }: { d: InicioDTO }) {
  return (
    <section className="contadores" aria-label="Contadores">
      {contadores(d).map((c) => {
        const cuerpo = (
          <>
            <span className="contador-etiqueta"><span className={`punto ${PUNTO[c.color]}`} aria-hidden="true" />{c.etiqueta}</span>
            <span className="contador-n" data-contador={c.clave}>{c.n}</span>
            <span className="contador-pista tenue">{c.pista}</span>
          </>
        );
        return c.a.startsWith('#')
          ? <a key={c.clave} href={c.a} className={`tarjeta contador c-${c.color}`}>{cuerpo}</a>
          : <Link key={c.clave} to={c.a} className={`tarjeta contador c-${c.color}`}>{cuerpo}</Link>;
      })}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Cobertura en euros
// ---------------------------------------------------------------------------

function Cobertura({ d }: { d: InicioDTO }) {
  const { importe_facturado_conocido: fact, importe_conciliado_conocido: conc, facturas_sin_importe: sin } = d.cobertura;
  const ratio = fact !== null && conc !== null && fact !== 0 ? conc / fact : null;
  const ancho = ratio === null ? 0 : Math.max(0, Math.min(1, ratio)) * 100;
  return (
    <section className="tarjeta bloque cobertura" aria-labelledby="t-cobertura">
      <div>
        <h2 id="t-cobertura">Cobertura en euros</h2>
        <p className="tenue bloque-nota">Importe conciliado con albaranes sobre el importe facturado conocido</p>
      </div>
      <div className="cobertura-cifra">
        <span className="cobertura-pct" data-cobertura-pct>{ratio === null ? 'Sin dato' : porcentaje(ratio)}</span>
        <span className="cobertura-de">
          {conc === null ? 'Sin importe conciliado conocido' : <><strong>{euros(conc)}</strong> conciliados</>}
          <br />
          {fact === null ? 'sin importe facturado conocido' : <>de {euros(fact)} facturados</>}
        </span>
      </div>
      <div className="barra" role="img" aria-label={ratio === null ? 'Cobertura sin dato' : `Cobertura ${porcentaje(ratio)}`}>
        <div className="barra-relleno" style={{ width: `${ancho}%` }} />
      </div>
      <div className="insignias">
        <span className={`insignia ${sin > 0 ? 'o' : 'n'}`} data-sin-importe={sin}>
          {sin === 0 ? 'Todas las facturas tienen importe' : `${plural(sin, 'factura', 'facturas')} sin importe conocido, excluida${sin === 1 ? '' : 's'}`}
        </span>
        <span className="insignia n">Pago: {d.pago.texto}</span>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Próximos vencimientos
// ---------------------------------------------------------------------------

function ImporteCelda({ v }: { v: Importe }) {
  const t = euros(v);
  return t === null ? <span className="desconocido">desconocido</span> : <>{t}</>;
}

function notaVencimiento(v: Vencimiento): string[] {
  const notas: string[] = [];
  if (v.vencimientos_factura > 1) notas.push(`${v.orden ?? '?'} de ${v.vencimientos_factura}`);
  if (v.tipo_documento === 'ABONO') notas.push('abono');
  return notas;
}

function Vencimientos({ d }: { d: InicioDTO }) {
  const vs = d.proximos_vencimientos;
  return (
    <section className="tarjeta bloque" aria-labelledby="t-vencimientos">
      <div className="bloque-cabecera">
        <h2 id="t-vencimientos">Próximos vencimientos</h2>
        <Link to="/vencimientos" className="enlace-bloque">Ver calendario</Link>
      </div>
      {vs.length === 0 ? (
        <p className="tenue vacio">No hay vencimientos documentados a partir de hoy.</p>
      ) : (
        <table className="tabla">
          <thead><tr><th scope="col">Fecha</th><th scope="col">Proveedor</th><th scope="col" className="num">Importe</th></tr></thead>
          <tbody>
            {vs.map((v) => (
              <tr key={v.vencimiento_id} data-vencimiento={v.vencimiento_id}>
                <td className="fecha">{fechaCorta(v.fecha_vencimiento)}</td>
                <td className="proveedor">
                  <Link to={`/facturas/${v.factura_id}`}>{v.proveedor ?? 'Proveedor sin identificar'}</Link>
                  {notaVencimiento(v).map((n) => <span key={n} className="nota">{n}</span>)}
                </td>
                <td className="num"><ImporteCelda v={v.importe} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Necesita tu atención: avisos del contrato + alertas, en lenguaje llano
// ---------------------------------------------------------------------------

interface Aviso {
  clave: string;
  etiqueta: string;
  color: Color;
  texto: string;
  detalle: string | null;
  referencia: string;
  codigo: string | null;
  a: string;
}

function destinoItem(i: ItemAtencion): string {
  return i.factura_id ? `/facturas/${i.factura_id}` : '/facturas';
}

function detalleDiferencia(i: ItemAtencion): string | null {
  if (!('diferencia_motor' in i) || i.diferencia_motor === undefined) return null;
  const t = euros(i.diferencia_motor);
  return t === null ? 'Diferencia no evaluable' : `Diferencia según el motor: ${t}`;
}

function avisoDeItem(i: ItemAtencion, n: number): Aviso {
  return {
    clave: `i${n}`, etiqueta: i.tipo, color: i.color, texto: i.texto, detalle: detalleDiferencia(i),
    referencia: i.referencia, codigo: i.codigo, a: destinoItem(i),
  };
}

function avisoDeAlerta(a: Alerta, n: number): Aviso {
  const num = a.numero_albaran ?? '(sin número)';
  const base = { clave: `a${n}`, color: a.color, codigo: null, a: a.factura_id ? `/facturas/${a.factura_id}` : '/conciliacion' };
  switch (a.tipo) {
    case 'ALBARAN_FACTURADO_NO_EN_FARMATIC':
      return { ...base, etiqueta: 'Fuera de Farmatic', texto: `El albarán ${num} está en una factura, pero ya no aparece en Farmatic`, detalle: null,
        referencia: [a.proveedor, a.numero_factura].filter(Boolean).join(' ') };
    case 'POSIBLE_DUPLICADO_FARMATIC': {
      const filas = (a.detalle.filas as { numero_albaran: string | null }[] | undefined) ?? [];
      const imp = euros((a.detalle.importe_puc as Importe | undefined) ?? null);
      return { ...base, etiqueta: 'Duplicado en Farmatic',
        texto: `El albarán ${num} está ${a.id_contadores.length} veces en Farmatic con el mismo importe`,
        detalle: imp === null ? null : `Importe de cada uno: ${imp}`,
        referencia: [a.proveedor, filas.map((f) => f.numero_albaran).filter(Boolean).join(', ')].filter(Boolean).join(' · ') };
    }
    case 'CORRECCION_APROBADA':
      return { ...base, etiqueta: a.color === 'verde' ? 'Corrección aplicada' : 'Corrección pendiente',
        texto: a.color === 'verde' ? `Se aplicó la corrección aprobada del albarán ${num}` : `La corrección aprobada del albarán ${num} está pendiente de aplicar`,
        detalle: null, referencia: a.proveedor ?? '' };
  }
}

function Atencion({ d }: { d: InicioDTO }) {
  const [todos, setTodos] = useState(false);
  const avisos = [...d.alertas.map(avisoDeAlerta), ...d.atencion.map(avisoDeItem)]
    .map((a, n) => ({ a, n }))
    .sort((x, y) => PRIORIDAD[x.a.color] - PRIORIDAD[y.a.color] || x.n - y.n)
    .map((x) => x.a);
  const visibles = todos ? avisos : avisos.slice(0, VISIBLES);
  const ocultos = avisos.length - visibles.length;
  return (
    <section id="atencion" className="tarjeta bloque" aria-labelledby="t-atencion">
      <div className="bloque-cabecera">
        <h2 id="t-atencion">Necesita tu atención <span className="cuenta tenue">{avisos.length}</span></h2>
        <Link to="/conciliacion" className="enlace-bloque">Abrir bandeja de conciliación</Link>
      </div>
      {avisos.length === 0 ? (
        <p className="tenue vacio">Nada pendiente. Todo lo leído está en orden.</p>
      ) : (
        <ul className="avisos">
          {visibles.map((a) => (
            <li key={a.clave} className={`aviso borde-${a.color}`} data-aviso={a.etiqueta}>
              <span className={`insignia ${CLASE[a.color]}`}>{a.etiqueta}</span>
              <div className="aviso-cuerpo">
                <span className="aviso-texto">{a.texto}</span>
                {a.detalle && <span className="aviso-detalle">{a.detalle}</span>}
                <span className="aviso-ref tenue">
                  {a.referencia}
                  {a.codigo && <code className="codigo">{a.codigo}</code>}
                </span>
              </div>
              <Link to={a.a} className="aviso-abrir" aria-label={`Abrir: ${a.texto}`}>Abrir</Link>
            </li>
          ))}
        </ul>
      )}
      {avisos.length > VISIBLES && (
        <button type="button" className="boton-secundario" onClick={() => setTodos((v) => !v)} aria-expanded={todos}>
          {todos ? 'Mostrar solo los primeros' : `Mostrar ${plural(ocultos, 'aviso más', 'avisos más')}`}
        </button>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Página
// ---------------------------------------------------------------------------

export function PaginaInicio() {
  const { carga, recargando, leidoAt, recargar } = useApiRecargable<InicioDTO>('/api/inicio');
  const d = carga.estado === 'ok' ? carga.datos : null;
  return (
    <>
      <header className="cabecera">
        <div>
          <h1>Resumen del día</h1>
          <div className="tenue subtitulo">{d ? `Datos de PIO a ${fechaLarga(d.generado_at).replace(/^./, (c) => c.toLowerCase())}` : 'Estado de facturas, conciliación y documentos de PIO'}</div>
        </div>
        <div className="acciones">
          <span className="lectura tenue" aria-live="polite" data-lectura>
            {recargando ? 'Leyendo…' : leidoAt ? `Última lectura ${hora(leidoAt)}` : ''}
          </span>
          <button type="button" className="boton-secundario" onClick={recargar} disabled={recargando}>Actualizar</button>
          <button type="button" className="boton-deshabilitado" disabled title="Disponible en fase 2">Sincronizar ahora</button>
        </div>
      </header>

      {carga.estado === 'cargando' && <p className="tenue">Leyendo datos…</p>}
      {carga.estado === 'error' && (
        <section className="tarjeta bloque error" role="alert">
          <h2>No se han podido leer los datos</h2>
          <p>La API local respondió <code className="codigo">{carga.mensaje}</code>. Pulsa Actualizar para volver a intentarlo.</p>
        </section>
      )}

      {d && (
        <div className="inicio" data-contrato-ok="inicio" aria-busy={recargando}>
          <Contadores d={d} />
          <div className="fila-dos">
            <Cobertura d={d} />
            <Vencimientos d={d} />
          </div>
          <Atencion d={d} />
          <p className="tenue pie-inicio">
            IA usada este mes: Luna, {d.luna_mes.coste === null ? 'coste desconocido' : euros(d.luna_mes.coste, true)} ({plural(d.luna_mes.ejecuciones, 'lectura', 'lecturas')})
          </p>
        </div>
      )}
    </>
  );
}
