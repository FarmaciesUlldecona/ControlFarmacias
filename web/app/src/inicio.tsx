// H4: pantalla Inicio (maqueta web/docs/maquetas/Main.dc.html) sobre el contrato `inicio`.
// Solo presenta: no recalcula diferencias ni tolerancias; importe null nunca es 0 (vencimiento: "importe pendiente").
import { Link } from 'react-router-dom';
import type { CasoAtencion, Color, Importe, InicioDTO, VencimientoInicio } from '../server/contrato.ts';
import { useApiRecargable } from './api.ts';
import { NombreProveedor } from './ui.tsx';
import { euros, fechaCorta, fechaLarga, hora, plural, porcentaje } from './formato.ts';

const CLASE: Record<Color, string> = { verde: 'g', azul: 'b', naranja: 'o', rojo: 'r', gris: 'n' };
const PUNTO: Record<Color, string> = { verde: 'pg', azul: 'pb', naranja: 'po', rojo: 'pr', gris: 'pn' };

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

/** Vencimiento sin importe (R14): "importe pendiente"; nunca 0 ni el total de la factura. */
export function ImporteVencimiento({ v }: { v: Importe }) {
  const t = euros(v);
  return t === null ? <span className="desconocido" data-importe-pendiente>importe pendiente</span> : <>{t}</>;
}

function notaVencimiento(v: VencimientoInicio): string[] {
  const notas: string[] = [];
  if (v.vencimientos_factura > 1) notas.push(`${v.orden ?? '?'} de ${v.vencimientos_factura}`);
  if (v.sentido === 'ABONO') notas.push('abono');
  if (v.sentido === 'NO_DOCUMENTADO') notas.push('sentido no documentado');
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
        <table className="tabla tabla-fija">
          <colgroup><col className="col-fecha" /><col /><col className="col-importe" /></colgroup>
          <thead><tr><th scope="col">Fecha</th><th scope="col">Proveedor</th><th scope="col" className="num">Importe</th></tr></thead>
          <tbody>
            {vs.map((v) => (
              <tr key={v.vencimiento_id} data-vencimiento={v.vencimiento_id}>
                <td className="fecha">{fechaCorta(v.fecha_vencimiento)}</td>
                <td className="proveedor">
                  <Link to={`/facturas/${v.factura_id}`}><NombreProveedor comercial={v.proveedor_comercial} razon={v.proveedor_razon_social} respaldo={v.proveedor} /></Link>
                  {notaVencimiento(v).map((n) => <span key={n} className="nota">{n}</span>)}
                  {v.posible_duplicado && <span className="insignia o insignia-mini" data-posible-duplicado>posible duplicado</span>}
                </td>
                <td className="num"><ImporteVencimiento v={v.importe} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Necesita tu atención (H4d): una fila por tipo con su nº de casos; desplegable con los casos y su enlace
// ---------------------------------------------------------------------------

function detalleCaso(c: CasoAtencion): string | null {
  if (c.diferencia_motor !== undefined) {
    const t = euros(c.diferencia_motor);
    return t === null ? 'Diferencia no evaluable' : `Diferencia según el motor: ${t}`;
  }
  if (c.importe_duplicado !== undefined) {
    const t = euros(c.importe_duplicado);
    return t === null ? null : `Importe de cada uno: ${t}`;
  }
  return null;
}

function Caso({ c }: { c: CasoAtencion }) {
  const detalle = detalleCaso(c);
  return (
    <li className="caso" data-caso>
      <div className="caso-cuerpo">
        <span className="caso-texto">{c.texto}</span>
        {detalle && <span className="aviso-detalle">{detalle}</span>}
        <span className="caso-ref tenue">
          {(c.proveedor !== null || c.proveedor_comercial !== null || c.proveedor_razon_social !== null)
            && <NombreProveedor comercial={c.proveedor_comercial} razon={c.proveedor_razon_social} respaldo={c.proveedor} />}
          {c.referencia && <span className="caso-referencia">{c.referencia}</span>}
          {c.fecha && <span className="caso-fecha">{fechaCorta(c.fecha)}</span>}
          {c.codigo && <code className="codigo">{c.codigo}</code>}
        </span>
      </div>
      <Link to={c.enlace} className="aviso-abrir" aria-label={`Abrir: ${c.texto}`}>Abrir</Link>
    </li>
  );
}

function Atencion({ d }: { d: InicioDTO }) {
  const { tipos, casos, grupos } = d.atencion;
  return (
    <section id="atencion" className="tarjeta bloque" aria-labelledby="t-atencion">
      <div className="bloque-cabecera">
        <h2 id="t-atencion">Necesita tu atención <span className="cuenta tenue" data-atencion-resumen>— {plural(tipos, 'tipo', 'tipos')}, {plural(casos, 'caso', 'casos')}</span></h2>
        <Link to="/conciliacion" className="enlace-bloque">Abrir bandeja de conciliación</Link>
      </div>
      {grupos.length === 0 ? (
        <p className="tenue vacio">Nada pendiente. Todo lo leído está en orden.</p>
      ) : (
        <ul className="grupos">
          {grupos.map((g) => (
            <li key={g.clave} className={`grupo borde-${g.color}`} data-grupo={g.clave} data-color={g.color} data-orden={g.orden}>
              <details>
                <summary>
                  <span className={`punto ${PUNTO[g.color]}`} aria-hidden="true" />
                  <span className="grupo-titulo">{g.titulo}</span>
                  <span className={`insignia ${CLASE[g.color]}`} data-casos={g.casos.length}>{plural(g.casos.length, 'caso', 'casos')}</span>
                </summary>
                <ul className="casos">
                  {g.casos.map((c, n) => <Caso key={`${g.clave}-${n}`} c={c} />)}
                </ul>
              </details>
            </li>
          ))}
        </ul>
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
            {/* H5: con 0 lecturas, "IA no utilizada este mes" (nunca "0 lecturas" ni coste). */}
            {d.luna_mes.ejecuciones === 0 ? <span data-ia-mes="no-utilizada">IA no utilizada este mes</span> : (
              <span data-ia-mes="utilizada">IA usada este mes: Luna, {d.luna_mes.coste === null ? 'coste desconocido' : euros(d.luna_mes.coste, true)} ({plural(d.luna_mes.ejecuciones, 'lectura', 'lecturas')})</span>
            )}
          </p>
        </div>
      )}
    </>
  );
}
