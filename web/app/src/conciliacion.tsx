// H8: pantalla Conciliación (decisión de Marc): doble comprobación por factura, (1) albaranes ↔ factura (motor
// existente) y (2) banco ↔ pago (Norma 43, futura). Solo lectura, solo PIO. Cuatro pestañas en la URL (?pestana=):
// Doble comprobación (por defecto), Albaranes, Sin factura y Banco. Acciones visibles y deshabilitadas.
// Solo presenta: diferencias y tolerancias son las del motor; importe ausente = null, nunca 0.
import { useMemo, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import type { AlbaranSinFactura, Alerta, Color, ConciliacionBandejaDTO, FacturaBandeja, Importe, OpcionFiltroProveedor, SinFactura, TipoAbonoEnBloque } from '../server/contrato.ts';
import {
  MARCAS_ALBARANES, OPCIONES_MARCA_ALBARANES, bandejaAlbaranes, cabeceraAlbaranes, coberturaProveedores, cumpleFiltrosDoble,
  enlaceVencimiento, facturasRevisarNoche, marcaAlbaranes, marcaBanco, resumenDoble, type FiltrosDoble, type TramoResumen,
} from '../server/conciliacion.ts';
import { useApiRecargable } from './api.ts';
import { Selector } from './facturas.tsx';
import { euros, fechaCorta, plural, porcentaje } from './formato.ts';
import { RevisarNocheGrupo } from './revisar_noche.tsx';
import { CLASE, Cabecera, ImporteTotal, Insignia, MOVIL, NombreProveedor, useMedia } from './ui.tsx';

const PESTANAS = [
  { clave: 'doble', texto: 'Doble comprobación' },
  { clave: 'albaranes', texto: 'Albaranes' },
  { clave: 'sin-factura', texto: 'Sin factura' },
  { clave: 'banco', texto: 'Banco' },
] as const;
type ClavePestana = (typeof PESTANAS)[number]['clave'];

const FASE_POSTERIOR = 'Disponible en una fase posterior';
const PUNTO: Record<Color, string> = { verde: 'pg', azul: 'pb', naranja: 'po', rojo: 'pr', gris: 'pn' };

function Euros({ v, vacio = 'sin importe' }: { v: Importe; vacio?: string }) {
  const t = euros(v);
  return t === null ? <span className="tenue">{vacio}</span> : <>{t}</>;
}
const ddmm = (f: string) => fechaCorta(f).slice(0, 5);

/** Nombre del grupo de proveedor (comercial; si no, el literal más frecuente del grupo). */
function nombreGrupo(o: OpcionFiltroProveedor | undefined, clave: string): string {
  return o ? o.comercial ?? o.etiqueta : clave;
}

// ---------------------------------------------------------------------------
// Marcas
// ---------------------------------------------------------------------------

function MarcaAlbaranesCelda({ fa }: { fa: FacturaBandeja }) {
  const m = marcaAlbaranes(fa);
  return (
    <span className="cc-marca-celda">
      <span className={`cc-marca cc-${m.color}`} data-marca-albaranes={m.clave}>
        <span className="cc-simbolo" aria-hidden="true">{m.simbolo}</span>{m.texto}
      </span>
      {/* Diferencia del motor al céntimo, tal cual (nunca recalculada). */}
      {m.diferencia_motor !== null && (m.clave === 'CONCILIADA' || m.clave === 'DIFERENCIA' || m.clave === 'REVISION') && (
        <span className="nota-celda" data-diferencia-motor>dif. {euros(m.diferencia_motor)}</span>
      )}
    </span>
  );
}

function MarcaBancoCelda({ fa }: { fa: FacturaBandeja }) {
  const m = marcaBanco(fa.banco);
  return (
    <span className={`cc-marca cc-${m.color}`} data-marca-banco={m.clave}>
      <span className="cc-simbolo" aria-hidden="true">{m.simbolo}</span>{m.texto}
    </span>
  );
}

function IndicadorNoche() {
  return <Insignia color="naranja" data-indicador-noche>revisar (noche)</Insignia>;
}

function Vencimiento({ fa }: { fa: FacturaBandeja }) {
  const v = fa.vencimiento_proximo;
  if (v === null) return <span className="tenue">sin vencimientos</span>;
  return (
    <span className="cc-venc" data-vencimiento-proximo>
      {v.fecha_vencimiento ? fechaCorta(v.fecha_vencimiento) : 'sin fecha'}
      {fa.vencimiento_vencido && <span className="nota-celda">vencido</span>}
      {v.importe === null && <span className="nota-celda desconocido">importe pendiente</span>}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Pestaña 1: Doble comprobación
// ---------------------------------------------------------------------------

function Tramo({ clave, titulo, nota, t, color }: { clave: string; titulo: string; nota: string; t: TramoResumen; color: Color }) {
  return (
    <div className={`tarjeta cc-tramo c-${color}`} data-tramo={clave}>
      <span className="cc-tramo-titulo"><span className={`punto ${PUNTO[color]}`} aria-hidden="true" />{titulo}</span>
      <strong className="cc-tramo-importe" data-tramo-importe>{t.importe === null ? '0,00 €' : euros(t.importe)}</strong>
      <span className="tenue cc-tramo-nota">{plural(t.facturas, 'factura', 'facturas')} · {nota}</span>
    </div>
  );
}

const CLAVES_FILTRO = ['proveedor', 'estado', 'q'] as const;

function DobleComprobacion({ d, params, cambiar }: { d: ConciliacionBandejaDTO; params: URLSearchParams; cambiar: (c: Record<string, string | null>) => void }) {
  const movil = useMedia(MOVIL);
  const filtros: FiltrosDoble = { proveedor: params.get('proveedor') ?? '', estado: params.get('estado') ?? '', q: params.get('q') ?? '' };
  const noche = useMemo(() => facturasRevisarNoche(d.revisar_noche), [d]);
  const r = useMemo(() => resumenDoble(d.facturas), [d]);
  const opcionDe = new Map(d.proveedores_filtro.map((o) => [o.clave, o]));
  // Orden: las que necesitan algo primero (prioridad del motor), luego fecha (como la bandeja del contrato).
  const visibles = d.facturas.filter((fa) => cumpleFiltrosDoble(fa, filtros, noche));
  const hayFiltros = CLAVES_FILTRO.some((k) => filtros[k] !== '');
  return (
    <>
      <section className="cc-tramos" aria-label="Resumen en euros">
        <Tramo clave="verificado_doble" titulo="Verificado doble" nota="albaranes y banco" t={r.verificado_doble} color="verde" />
        <Tramo clave="solo_albaranes" titulo="Solo albaranes" nota="falta el banco" t={r.solo_albaranes} color="azul" />
        <Tramo clave="ninguna" titulo="Ninguna" nota="sin comprobar" t={r.ninguna} color="gris" />
      </section>
      <p className="tenue cc-nota" data-sin-importe-doble>
        {r.sin_importe === 0 ? 'Todas las facturas tienen importe.' : `${plural(r.sin_importe, 'factura', 'facturas')} sin importe, fuera de los totales.`}
        {' '}El banco aún no se comprueba: hasta la conciliación bancaria nada queda «verificado doble».
      </p>

      <RevisarNocheGrupo r={d.revisar_noche} />

      <label className="buscar">
        <span>Buscar</span>
        <input type="search" name="q" placeholder="Proveedor, nº de factura o importe" value={filtros.q} onChange={(e) => cambiar({ q: e.target.value })} />
      </label>
      <section className="tarjeta filtros" aria-label="Filtros">
        <Selector nombre="proveedor" etiqueta="Proveedor" todos="Todos" valor={filtros.proveedor} onChange={(v) => cambiar({ proveedor: v })}
          opciones={d.proveedores_filtro.map((o) => ({ valor: o.clave, texto: `${o.comercial ?? o.etiqueta}${o.sin_cif ? ' (sin CIF)' : ''}` }))} />
        <Selector nombre="estado" etiqueta="Albaranes" todos="Todos" valor={filtros.estado} onChange={(v) => cambiar({ estado: v })}
          opciones={[...OPCIONES_MARCA_ALBARANES.map((k) => ({ valor: k, texto: `${MARCAS_ALBARANES[k].simbolo} ${MARCAS_ALBARANES[k].texto}` })),
            { valor: 'noche', texto: 'Revisar (noche)' }]} />
        {hayFiltros && (
          <button type="button" className="boton-secundario boton-limpiar" onClick={() => cambiar(Object.fromEntries(CLAVES_FILTRO.map((k) => [k, null])))}>Quitar filtros</button>
        )}
      </section>
      <p className="tenue resumen-listado" data-resumen-listado aria-live="polite">
        {visibles.length === 0 ? 'Ninguna factura cumple estos filtros.' : plural(visibles.length, 'factura', 'facturas')}
      </p>

      {visibles.length > 0 && (movil ? (
        <ul className="cc-tarjetas">
          {visibles.map((fa) => (
            <li key={fa.factura_id} className="tarjeta cc-tarjeta" data-factura={fa.factura_id}>
              <div className="cc-tarjeta-cabecera">
                <NombreProveedor comercial={fa.proveedor_comercial} razon={fa.proveedor_razon_social} respaldo={nombreGrupo(opcionDe.get(fa.proveedor_grupo), fa.proveedor_etiqueta)} />
                <strong><ImporteTotal v={fa.importe_total} /></strong>
              </div>
              <div className="cc-tarjeta-linea">
                <Link to={`/facturas/${fa.factura_id}`} className="enlace-factura">{fa.numero_factura ?? '(sin número)'}</Link>
                <Vencimiento fa={fa} />
              </div>
              <div className="cc-tarjeta-marcas">
                <span><span className="tenue">Albaranes</span> <MarcaAlbaranesCelda fa={fa} /></span>
                <span><span className="tenue">Banco</span> <MarcaBancoCelda fa={fa} /></span>
                {noche.has(fa.factura_id) && <IndicadorNoche />}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <div className="tarjeta tabla-desplazable">
          <table className="tabla cc-tabla">
            <thead>
              <tr>
                <th scope="col">Proveedor</th><th scope="col">Nº factura</th><th scope="col" className="num">Importe</th>
                <th scope="col">Próximo vencimiento</th><th scope="col">1 · Albaranes</th><th scope="col">2 · Banco</th>
              </tr>
            </thead>
            <tbody>
              {visibles.map((fa) => (
                <tr key={fa.factura_id} data-factura={fa.factura_id}>
                  <td className="proveedor"><NombreProveedor comercial={fa.proveedor_comercial} razon={fa.proveedor_razon_social} respaldo={nombreGrupo(opcionDe.get(fa.proveedor_grupo), fa.proveedor_etiqueta)} /></td>
                  <td><Link to={`/facturas/${fa.factura_id}`} className="enlace-factura">{fa.numero_factura ?? '(sin número)'}</Link></td>
                  <td className="num"><ImporteTotal v={fa.importe_total} /></td>
                  <td><Vencimiento fa={fa} /></td>
                  <td><span className="cc-marca-con-noche"><MarcaAlbaranesCelda fa={fa} />{noche.has(fa.factura_id) && <IndicadorNoche />}</span></td>
                  <td><MarcaBancoCelda fa={fa} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Pestaña 2: Albaranes
// ---------------------------------------------------------------------------

function Cifra({ clave, titulo, children, color }: { clave: string; titulo: string; children: ReactNode; color: Color }) {
  return (
    <div className={`tarjeta cc-tramo c-${color}`} data-cifra={clave}>
      <span className="cc-tramo-titulo"><span className={`punto ${PUNTO[color]}`} aria-hidden="true" />{titulo}</span>
      <strong className="cc-tramo-importe">{children}</strong>
    </div>
  );
}

function Barra({ ratio, etiqueta }: { ratio: number | null; etiqueta: string }) {
  const ancho = ratio === null ? 0 : Math.max(0, Math.min(1, ratio)) * 100;
  return (
    <div className="barra cc-barra" role="img" aria-label={etiqueta}>
      <div className="barra-relleno" style={{ width: `${ancho}%` }} />
    </div>
  );
}

function CoberturaProveedores({ d }: { d: ConciliacionBandejaDTO }) {
  const filas = coberturaProveedores(d.facturas, d.sin_factura);
  return (
    <section className="tarjeta bloque" aria-labelledby="t-cob-prov">
      <h2 id="t-cob-prov">Cobertura por proveedor</h2>
      <ul className="cc-cobertura">
        {filas.map((f) => f.tipo === 'LECTOR' ? (
          <li key={f.clave} className="cc-cob-fila" data-cobertura-proveedor={f.clave}>
            <span className="cc-cob-nombre" data-cobertura-nombre>{f.nombre_mostrado}</span>
            <Barra ratio={f.cobertura.ratio} etiqueta={f.cobertura.ratio === null ? 'Cobertura sin dato' : `Cobertura ${porcentaje(f.cobertura.ratio)}`} />
            <span className="cc-cob-cifra" data-cobertura-cifra>
              {f.cobertura.ratio === null ? 'sin importe' : porcentaje(f.cobertura.ratio)}
              <span className="tenue"> · <Euros v={f.cobertura.conciliado} vacio="—" /> de <Euros v={f.cobertura.facturado} vacio="—" />
                {f.cobertura.sin_importe > 0 && ` · ${plural(f.cobertura.sin_importe, 'factura', 'facturas')} sin importe, fuera`}</span>
              {/* H8-5: en la misma fila, sus albaranes de Farmatic pendientes de automatizar (antes, una fila «sin lector» aparte). */}
              {f.pendientes && (
                <span className="tenue cc-cob-pendientes" data-cobertura-pendientes={f.pendientes.albaranes}>
                  Además, {plural(f.pendientes.albaranes, 'albarán', 'albaranes')} en Farmatic sin factura, pendientes de automatizar · <Euros v={f.pendientes.importe} />
                  {f.pendientes.sin_importe > 0 && ` (${f.pendientes.sin_importe} sin importe)`}
                </span>
              )}
            </span>
          </li>
        ) : (
          <li key={f.clave} className="cc-cob-fila cc-sin-lector" data-cobertura-proveedor={f.clave}>
            <span className="cc-cob-nombre">{f.proveedor}</span>
            <span className="insignia n" data-sin-lector>sin lector</span>
            <span className="cc-cob-cifra tenue">{plural(f.albaranes, 'albarán', 'albaranes')} en Farmatic · <Euros v={f.importe} /></span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Bandeja({ d }: { d: ConciliacionBandejaDTO }) {
  const grupos = bandejaAlbaranes(d.facturas);
  const opcionDe = new Map(d.proveedores_filtro.map((o) => [o.clave, o]));
  return (
    <section className="tarjeta bloque" aria-labelledby="t-bandeja">
      <div className="bloque-cabecera">
        <h2 id="t-bandeja">Bandeja: facturas sin conciliar</h2>
        <span className="tenue">Primero el dinero en riesgo: el vencimiento más próximo y, después, el importe</span>
      </div>
      {grupos.length === 0 ? <p className="tenue vacio">Todas las facturas están conciliadas con sus albaranes.</p> : (
        <ul className="cc-bandeja">
          {grupos.map((g) => (
            <li key={g.proveedor_grupo} className="cc-bandeja-proveedor" data-bandeja-proveedor={g.proveedor_grupo}>
              <div className="cc-bandeja-cabecera">
                <strong>{nombreGrupo(opcionDe.get(g.proveedor_grupo), g.proveedor_grupo)}</strong>
                <span className="tenue">{plural(g.facturas, 'factura', 'facturas')} · <Euros v={g.importe} />{g.sin_importe > 0 && ` · ${g.sin_importe} sin importe`}</span>
              </div>
              {g.motivos.map((m) => (
                <div key={m.clave} className="cc-motivo" data-motivo={m.clave}>
                  <span className={`insignia ${CLASE[m.color]}`}>{m.texto}</span>
                  <ul className="cc-motivo-facturas">
                    {m.facturas.map((fa) => {
                      const v = fa.vencimiento_proximo?.fecha_vencimiento ?? null;
                      return (
                        <li key={fa.factura_id} data-bandeja-factura={fa.factura_id}>
                          <Link to={`/facturas/${fa.factura_id}`} className="enlace-factura">{fa.numero_factura ?? '(sin número)'}</Link>
                          <span className="num"><ImporteTotal v={fa.importe_total} /></span>
                          {v !== null ? (
                            <Link to={enlaceVencimiento(v)} className="cc-cobra" data-se-cobra>
                              {fa.vencimiento_vencido ? `venció el ${ddmm(v)}` : `se cobra el ${ddmm(v)}`}
                            </Link>
                          ) : <span className="tenue">sin vencimiento</span>}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Detalle literal de una alerta (claves y valores del contrato, sin recalcular). */
function DetalleAlerta({ a }: { a: Alerta }) {
  const pares = Object.entries(a.detalle).filter(([k]) => k !== 'filas');
  const filas = Array.isArray(a.detalle.filas) ? (a.detalle.filas as Record<string, unknown>[]) : [];
  const valor = (v: unknown) => (v === null || v === undefined ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v));
  return (
    <details className="noche-evidencia" data-alerta-detalle>
      <summary>Detalle completo</summary>
      <ul>
        <li><code className="codigo">id_contador: {a.id_contadores.join(', ')}</code></li>
        {pares.map(([k, v]) => <li key={k}><code className="codigo">{k}: {valor(v)}</code></li>)}
        {filas.map((f, i) => (
          <li key={i}><code className="codigo">{['numero_albaran', 'id_contador', 'fecha', 'importe_puc', 'proveedor'].map((k) => `${k}: ${valor(f[k])}`).join(' · ')}</code></li>
        ))}
      </ul>
    </details>
  );
}

function Alertas({ d }: { d: ConciliacionBandejaDTO }) {
  const tipos: { tipo: Alerta['tipo']; titulo: string }[] = [
    { tipo: 'POSIBLE_DUPLICADO_FARMATIC', titulo: 'Duplicados en Farmatic' },
    { tipo: 'ALBARAN_FACTURADO_NO_EN_FARMATIC', titulo: 'Albarán facturado que ya no está en Farmatic' },
    { tipo: 'CORRECCION_APROBADA', titulo: 'Correcciones de albarán aprobadas' },
  ];
  return (
    <section id="alertas" className="tarjeta bloque" aria-labelledby="t-alertas">
      <h2 id="t-alertas">Alertas de albaranes</h2>
      {tipos.map(({ tipo, titulo }) => {
        const xs = d.alertas.filter((a) => a.tipo === tipo);
        return (
          <div key={tipo} className="cc-alertas-tipo" data-alertas-tipo={tipo}>
            <h3>{titulo} <span className="tenue">({xs.length})</span></h3>
            {xs.length === 0 ? <p className="tenue vacio">Ninguna.</p> : (
              <ul className="casos noche-casos">
                {xs.map((a, i) => (
                  <li key={`${tipo}-${i}`} className="caso" data-alerta={tipo}>
                    <div className="caso-cuerpo">
                      <span className="caso-texto"><span className={`punto ${PUNTO[a.color]}`} aria-hidden="true" /> {a.titulo}</span>
                      <span className="caso-ref tenue">
                        {a.proveedor && <span>{a.proveedor}</span>}
                        {a.numero_albaran && <span className="caso-referencia">albarán {a.numero_albaran}</span>}
                        {a.numero_factura && <span className="caso-referencia">factura {a.numero_factura}</span>}
                        {a.fecha && <span className="caso-fecha">{fechaCorta(a.fecha)}</span>}
                      </span>
                      <DetalleAlerta a={a} />
                    </div>
                    {a.factura_id && <Link to={`/facturas/${a.factura_id}`} className="aviso-abrir" aria-label={`Abrir factura ${a.numero_factura ?? ''}`}>Abrir</Link>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </section>
  );
}

function PestanaAlbaranes({ d }: { d: ConciliacionBandejaDTO }) {
  const c = cabeceraAlbaranes(d);
  const cob = c.cobertura;
  return (
    <>
      <section className="cc-tramos" aria-label="Albaranes ↔ factura">
        <Cifra clave="cobertura" titulo="Cobertura en euros" color="verde">
          <span data-cobertura>{cob.ratio === null ? 'Sin dato' : porcentaje(cob.ratio)}</span>
          <span className="tenue cc-tramo-nota"><Euros v={cob.conciliado} vacio="—" /> conciliados de <Euros v={cob.facturado} vacio="—" /> facturados conocidos
            {cob.sin_importe > 0 && ` · ${plural(cob.sin_importe, 'factura', 'facturas')} sin importe, fuera`}</span>
        </Cifra>
        <Cifra clave="conciliadas" titulo="Conciliadas" color="verde">{c.conciliadas}</Cifra>
        <Cifra clave="pendientes" titulo="Pendientes" color="azul">{c.pendientes}</Cifra>
        <Cifra clave="revision" titulo="En revisión" color="naranja">{c.en_revision}</Cifra>
      </section>
      <CoberturaProveedores d={d} />
      <RevisarNocheGrupo r={d.revisar_noche} />
      <Bandeja d={d} />
      <Alertas d={d} />
    </>
  );
}

// ---------------------------------------------------------------------------
// Pestaña 3: Sin factura
// ---------------------------------------------------------------------------

/** H8-3: reparto del total por grupo (solo los que tienen albaranes), en el orden de la pantalla. */
function repartoSinFactura(sf: SinFactura): string[] {
  const g = sf.grupos;
  const partes: [number, string][] = [
    [g.AUTO_ALERTA.albaranes, 'en alerta'], [g.AUTO_RECIENTE.albaranes, 'en plazo'],
    [g.AUTO_ANTERIOR.albaranes, 'anteriores al primer albarán conciliado'], [g.AUTO_SIN_DESDE.albaranes, 'sin poder comprobar'],
    [g.LEIDO.albaranes + g.LEIDO_ANTERIOR.albaranes, 'leídos sin conciliación automática'],
    [g.SIN_LECTOR.albaranes + g.SIN_PROVEEDOR.albaranes, 'pendientes de automatizar'], [g.TRASPASO.albaranes, 'traspasos entre farmacias'],
    [g.DEVOLUCION_BLOQUE.albaranes, 'devoluciones de abono en bloque'], [g.AUSENTE.albaranes, 'excluidos'],
  ];
  return partes.filter(([n]) => n > 0).map(([n, t]) => `${n} ${t}`);
}

/** H8-5: antigüedad del albarán más antiguo (el detalle llega del más antiguo al más reciente, los sin fecha al final). */
function textoMasAntiguo(detalle: readonly AlbaranSinFactura[]): string {
  const d = detalle[0]?.dias ?? null;
  return d === null ? 'sin fecha' : `el más antiguo, de ${plural(d, 'día', 'días')}`;
}

interface EstadoSf { clave: string; color: 'naranja' | 'gris'; texto: string }

/**
 * H8-5: un proveedor de «Sin factura», plegado por defecto. Cabecera: nombre (y literal de Farmatic debajo si difiere),
 * nº de albaranes, importe, antigüedad del más antiguo y estado. Al desplegar: notas y los `limite` más antiguos.
 */
function ProveedorSinFactura({ nombre, secundario, nota, albaranes, importe, sinImporte, detalle, limite, estado, clave, children }: {
  nombre: string; secundario: string | null; nota?: string | null; albaranes: number; importe: Importe; sinImporte: number;
  detalle: readonly AlbaranSinFactura[]; limite: number; estado: EstadoSf; clave: string; children?: ReactNode;
}) {
  const alerta = estado.clave === 'alerta';
  return (
    <details className={`cc-sf-desplegable cc-sf-${estado.color}`} data-sf-desplegable={`${estado.clave}:${clave}`}>
      <summary className="cc-sf-cabecera">
        <span className="cc-cob-nombre" data-sf-nombre>{nombre}
          {secundario && <span className="nota-celda" data-sf-literal>{secundario}</span>}
          {nota && <span className="nota-celda">{nota}</span>}</span>
        <span className="tenue" data-sf-n={albaranes}>{plural(albaranes, 'albarán', 'albaranes')}</span>
        <span className="num" data-sf-importe><Euros v={importe} />{sinImporte > 0 && <span className="nota-celda">{sinImporte} sin importe</span>}</span>
        <span className="tenue" data-sf-mas-antiguo={detalle[0]?.dias ?? ''}>{textoMasAntiguo(detalle)}</span>
        <span className={`insignia ${estado.color === 'naranja' ? 'o' : 'n'}`} data-sf-estado={estado.clave}>{estado.texto}</span>
      </summary>
      <div className="cc-sf-cuerpo">
        {children}
        {detalle.length < albaranes && (
          <p className="tenue cc-sf-truncado" data-sf-truncado={clave}>
            Se muestran los {detalle.length} más antiguos de {albaranes}; el recuento y el importe son de todos.
          </p>
        )}
        <table className="tabla cc-sf-tabla" data-sf-detalle={detalle.length} data-sf-limite={limite}>
          <thead><tr><th scope="col">Albarán</th><th scope="col">Fecha</th><th scope="col" className="num">Antigüedad</th><th scope="col" className="num">Importe (PUC)</th></tr></thead>
          <tbody>
            {detalle.map((a, i) => (
              <tr key={`${a.id_contador ?? 'x'}-${i}`} data-sf-albaran={a.numero_albaran ?? ''}>
                <td className="numero">{a.numero_albaran ?? 'sin número'}</td>
                <td>{a.fecha ? fechaCorta(a.fecha) : <span className="tenue">sin fecha</span>}</td>
                <td className="num">{a.dias === null ? <span className="tenue">—</span>
                  : alerta ? <span className="insignia o" data-antiguedad={a.dias}>{a.dias} días</span>
                    : <span data-dias={a.dias}>{a.dias} días</span>}</td>
                <td className="num"><Euros v={a.importe} vacio="no consta" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function PestanaSinFactura({ sf }: { sf: SinFactura }) {
  const conAlertas = sf.con_lector.filter((p) => p.alertas_total > 0);
  const sinDesde = sf.con_lector.filter((p) => p.sin_desde.albaranes > 0);
  const reparto = repartoSinFactura(sf);
  const lim = sf.limite_detalle;
  return (
    <>
      <p className="tenue cc-nota">
        Albaranes de Farmatic que ninguna conciliación vigente ha reservado. Si el proveedor tiene facturas leídas y
        conciliación automática, un albarán suyo con más de {sf.dias_alerta} días sin factura es alerta. Lo demás se muestra en gris.
      </p>
      <p className="tenue cc-nota" data-sf-total={sf.total.albaranes}>
        En total, {plural(sf.total.albaranes, 'albarán sin reservar', 'albaranes sin reservar')} (<Euros v={sf.total.importe} />)
        {reparto.length > 0 && <>: {reparto.join(', ')}</>}.
      </p>
      <p className="tenue cc-nota" data-sf-ausentes={sf.excluidos_ausentes.albaranes}>
        {sf.excluidos_ausentes.albaranes === 0 ? 'Ningún albarán excluido por no estar ya en Farmatic.'
          : <>{plural(sf.excluidos_ausentes.albaranes, 'excluido', 'excluidos')} por no estar ya en Farmatic (<Euros v={sf.excluidos_ausentes.importe} />).</>}
      </p>
      <section className="tarjeta bloque cc-sf-alertas" aria-labelledby="t-sf-alertas" data-sf-alertas>
        <div className="bloque-cabecera">
          <h2 id="t-sf-alertas"><span className="punto po" aria-hidden="true" /> Con conciliación automática: más de {sf.dias_alerta} días sin factura</h2>
          <span className={`insignia ${sf.totales.alertas > 0 ? 'o' : 'n'}`} data-sf-total-alertas={sf.totales.alertas}>
            {plural(sf.totales.alertas, 'albarán', 'albaranes')} · <Euros v={sf.totales.importe_alertas} vacio="sin importe" />
            {sf.totales.alertas_sin_importe > 0 && ` (${sf.totales.alertas_sin_importe} sin importe)`}
          </span>
        </div>
        {/* H8-4: si hay albaranes sin fecha de inicio, no se puede afirmar que ninguno pase del plazo. */}
        {conAlertas.length === 0 ? (
          <p className="tenue vacio" data-sf-vacio>
            {sf.grupos.AUTO_SIN_DESDE.albaranes > 0
              ? `Ninguno en alerta; ${sf.grupos.AUTO_SIN_DESDE.albaranes} sin poder comprobar.`
              : `Ningún albarán de un proveedor con conciliación automática pasa de ${sf.dias_alerta} días sin factura.`}
          </p>
        ) : (
          <ul className="cc-sf-lista">
            {conAlertas.map((p) => (
              <li key={p.clave} data-sf-proveedor={p.clave}>
                <ProveedorSinFactura clave={p.clave} nombre={p.proveedor} secundario={p.literal_farmatic} albaranes={p.alertas_total}
                  importe={p.importe_alertas} sinImporte={p.alertas_sin_importe} detalle={p.alertas} limite={lim}
                  estado={{ clave: 'alerta', color: 'naranja', texto: `más de ${sf.dias_alerta} días` }} />
              </li>
            ))}
          </ul>
        )}
        {/* H8-5: los «sin poder comprobar», también desplegables; naranja de revisión, nunca alerta. */}
        {sinDesde.length > 0 && (
          <ul className="cc-sf-lista" data-sf-sin-desde-lista>
            {sinDesde.map((p) => (
              <li key={`s-${p.clave}`} data-sf-sin-desde={p.clave}>
                <ProveedorSinFactura clave={p.clave} nombre={p.proveedor} secundario={p.literal_farmatic} albaranes={p.sin_desde.albaranes}
                  importe={p.sin_desde.importe} sinImporte={p.sin_desde.sin_importe} detalle={p.detalle_sin_desde} limite={lim}
                  estado={{ clave: 'sin-desde', color: 'naranja', texto: 'sin poder comprobar' }}>
                  <p className="cc-sf-explicacion cc-naranja" data-sf-sin-desde-nota>
                    Sin poder comprobar: ninguno de sus albaranes conciliados tiene fecha, así que no hay fecha de inicio. Revísalo.
                  </p>
                </ProveedorSinFactura>
              </li>
            ))}
          </ul>
        )}
        {sf.con_lector.some((p) => p.recientes.albaranes > 0 || p.anteriores.albaranes > 0) && (
          <ul className="cc-sf-notas tenue">
            {sf.con_lector.filter((p) => p.recientes.albaranes > 0).map((p) => (
              <li key={`r-${p.clave}`} data-sf-recientes={p.clave}>{p.proveedor}: {plural(p.recientes.albaranes, 'albarán', 'albaranes')} de menos de {sf.dias_alerta} días, aún en plazo (<Euros v={p.recientes.importe} />)</li>
            ))}
            {sf.con_lector.filter((p) => p.anteriores.albaranes > 0).map((p) => (
              <li key={`a-${p.clave}`} data-sf-anteriores={p.clave}>{p.proveedor}: {plural(p.anteriores.albaranes, 'albarán anterior', 'albaranes anteriores')} a su primer albarán conciliado{p.desde ? ` (${fechaCorta(p.desde)})` : ''}, sin alerta</li>
            ))}
          </ul>
        )}
      </section>
      {/* H8-2: facturas leídas, pero ninguna conciliación automática reserva sus albaranes: gris, nunca alerta. */}
      <section className="tarjeta bloque" aria-labelledby="t-sf-leido" data-sf-leido>
        <div className="bloque-cabecera">
          <h2 id="t-sf-leido"><span className="punto pn" aria-hidden="true" /> Leído, sin conciliación automática</h2>
          <span className="insignia n">{plural(sf.totales.leido_sin_conciliacion.albaranes, 'albarán', 'albaranes')} · <Euros v={sf.totales.leido_sin_conciliacion.importe} /></span>
        </div>
        {sf.leido_sin_conciliacion.length === 0 ? <p className="tenue vacio">Todos los proveedores con facturas leídas tienen conciliación automática.</p> : (
          <ul className="cc-sf-lista">
            {sf.leido_sin_conciliacion.map((s) => (
              <li key={s.clave} data-sf-leido-proveedor={s.clave}>
                <ProveedorSinFactura clave={s.clave} nombre={s.proveedor} secundario={s.literal_farmatic} albaranes={s.albaranes}
                  importe={s.importe} sinImporte={s.sin_importe} detalle={s.detalle} limite={lim}
                  estado={{ clave: 'leido', color: 'gris', texto: 'sin conciliación automática' }}>
                  <ul className="cc-sf-notas tenue">
                    {s.desde && <li>Desde el {fechaCorta(s.desde)}, lo que cubren sus facturas leídas.</li>}
                    {s.anteriores.albaranes > 0 && <li data-sf-leido-anteriores={s.anteriores.albaranes}>
                      Además, {plural(s.anteriores.albaranes, 'albarán anterior', 'albaranes anteriores')} (<Euros v={s.anteriores.importe} />), sin detalle.</li>}
                  </ul>
                </ProveedorSinFactura>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="tarjeta bloque" aria-labelledby="t-sf-sin-lector" data-sf-sin-lector>
        <div className="bloque-cabecera">
          <h2 id="t-sf-sin-lector"><span className="punto pn" aria-hidden="true" /> Pendiente de automatizar</h2>
          <span className="insignia n">{plural(sf.totales.sin_lector.albaranes, 'albarán', 'albaranes')} · <Euros v={sf.totales.sin_lector.importe} /></span>
        </div>
        {sf.sin_lector.length === 0 ? <p className="tenue vacio">Ningún albarán de proveedores sin lector.</p> : (
          <ul className="cc-sf-lista">
            {sf.sin_lector.map((s) => (
              <li key={s.clave ?? 'sin_identificar'} data-sf-gris={s.clave ?? 'sin_identificar'}>
                <ProveedorSinFactura clave={s.clave ?? 'sin_identificar'} nombre={s.proveedor} secundario={s.literal_farmatic}
                  nota={s.identificado ? null : 'proveedor no determinado con certeza'} albaranes={s.albaranes} importe={s.importe}
                  sinImporte={s.sin_importe} detalle={s.detalle} limite={lim} estado={{ clave: 'pendiente', color: 'gris', texto: 'pendiente de automatizar' }} />
              </li>
            ))}
          </ul>
        )}
      </section>
      {/* H8-4 (decisión A de Marc): otra farmacia del grupo como proveedor en Farmatic: gris aparte, nunca alerta. */}
      <section className="tarjeta bloque" aria-labelledby="t-sf-traspasos" data-sf-traspasos>
        <div className="bloque-cabecera">
          <h2 id="t-sf-traspasos"><span className="punto pn" aria-hidden="true" /> Traspasos entre farmacias (sin factura)</h2>
          <span className="insignia n">{plural(sf.grupos.TRASPASO.albaranes, 'albarán', 'albaranes')} · <Euros v={sf.grupos.TRASPASO.importe} /></span>
        </div>
        {sf.traspasos.length === 0 ? <p className="tenue vacio">Ningún albarán de traspaso entre farmacias.</p> : (
          <ul className="cc-sf-lista">
            {sf.traspasos.map((s) => (
              <li key={`${s.farmacia_origen}-${s.clave ?? ''}`} data-sf-traspaso={s.farmacia_origen}>
                <ProveedorSinFactura clave={`${s.farmacia_origen}-${s.clave ?? ''}`} nombre={s.proveedor} secundario={s.literal_farmatic}
                  nota={`farmacia ${s.farmacia_origen}: traspaso, no lleva factura`} albaranes={s.albaranes} importe={s.importe}
                  sinImporte={s.sin_importe} detalle={s.detalle} limite={lim} estado={{ clave: 'traspaso', color: 'gris', texto: 'traspaso' }} />
              </li>
            ))}
          </ul>
        )}
      </section>
      {/* H8-6 (decisión de Pío, 26/11/2026): devoluciones Alliance que se abonan en bloque: gris, nunca alerta ni dinero
          pendiente, fuera de la cobertura. Un desplegable por tipo con su subtotal y su nota. */}
      <section className="tarjeta bloque" aria-labelledby="t-sf-bloque" data-sf-devoluciones-bloque={sf.grupos.DEVOLUCION_BLOQUE.albaranes}>
        <div className="bloque-cabecera">
          <h2 id="t-sf-bloque"><span className="punto pn" aria-hidden="true" /> Devoluciones (abono en bloque)</h2>
          <span className="insignia n">{plural(sf.grupos.DEVOLUCION_BLOQUE.albaranes, 'albarán', 'albaranes')} · <Euros v={sf.grupos.DEVOLUCION_BLOQUE.importe} /></span>
        </div>
        <p className="tenue cc-nota" data-sf-bloque-subtitulo>Alliance abona las devoluciones en bloque (ABONOS AGRUPADOS). Pendiente de regla de casado.</p>
        {sf.devoluciones_bloque.every((b) => b.albaranes === 0) ? <p className="tenue vacio">Ninguna devolución de abono en bloque.</p> : (
          <ul className="cc-sf-lista">
            {sf.devoluciones_bloque.filter((b) => b.albaranes > 0).map((b) => (
              <li key={b.tipo} data-sf-bloque-tipo={b.tipo}>
                <ProveedorSinFactura clave={b.tipo} nombre={ETIQUETA_TIPO_BLOQUE[b.tipo]} secundario={null} nota={b.nota}
                  albaranes={b.albaranes} importe={b.importe} sinImporte={b.sin_importe} detalle={b.detalle} limite={lim}
                  estado={{ clave: 'bloque', color: 'gris', texto: 'abono en bloque' }} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

/** H8-6: nombre de cada tipo de devolución en bloque en la pantalla. */
const ETIQUETA_TIPO_BLOQUE: Record<TipoAbonoEnBloque, string> = {
  SAFA: 'SAFA', SAFA_RECIENTE: 'SAFA recientes', ECO360: 'ECO360', SAFA_CADUCITATS: 'SAFA CADUCITATS',
};

// ---------------------------------------------------------------------------
// Pestaña 4: Banco
// ---------------------------------------------------------------------------

function PestanaBanco() {
  return (
    <section className="tarjeta bloque cc-banco" aria-labelledby="t-banco" data-banco-pendiente>
      <h2 id="t-banco"><span className="punto pn" aria-hidden="true" /> Pendiente: conciliación bancaria (Norma 43)</h2>
      <p className="tenue">Cuando lleguen los movimientos del banco, esta pestaña:</p>
      <ul className="cc-banco-lista">
        <li>Casará los movimientos del banco con los vencimientos de las facturas.</li>
        <li>Marcará cada factura como «pagado (banco)», la segunda comprobación.</li>
        <li>Detectará pagos sin factura, recibos devueltos y cargos duplicados.</li>
      </ul>
      <p className="tenue">Todavía no hay datos bancarios.</p>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Página
// ---------------------------------------------------------------------------

export function PaginaConciliacion() {
  const { carga, recargando, recargar } = useApiRecargable<ConciliacionBandejaDTO>('/api/conciliacion');
  const [params, setParams] = useSearchParams();
  const d = carga.estado === 'ok' ? carga.datos : null;
  const pestana: ClavePestana = PESTANAS.find((p) => p.clave === params.get('pestana'))?.clave ?? 'doble';
  const cambiar = (cambios: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(cambios)) { if (v === null || v === '') p.delete(k); else p.set(k, v); }
    setParams(p, { replace: true });
  };
  return (
    <>
      <Cabecera titulo="Conciliación" subtitulo="Doble comprobación de cada factura: albaranes de Farmatic y banco">
        <button type="button" className="boton-secundario" onClick={recargar} disabled={recargando}>Actualizar</button>
        <button type="button" className="boton-deshabilitado" disabled title={FASE_POSTERIOR} aria-describedby="cc-fase">Reintentar conciliación</button>
        <button type="button" className="boton-deshabilitado" disabled title={FASE_POSTERIOR} aria-describedby="cc-fase">Cerrar con justificación</button>
        <span id="cc-fase" className="tenue cc-fase">{FASE_POSTERIOR}</span>
      </Cabecera>

      {carga.estado === 'cargando' && <p className="tenue">Leyendo la conciliación…</p>}
      {carga.estado === 'error' && (
        <section className="tarjeta bloque error" role="alert">
          <h2>No se ha podido leer la conciliación</h2>
          <p>La API local respondió <code className="codigo">{carga.mensaje}</code>. Pulsa Actualizar para volver a intentarlo.</p>
        </section>
      )}

      {d && (
        <div className="conciliacion" data-contrato-ok="conciliacionBandeja" aria-busy={recargando}>
          <div className="pestanas" role="tablist" aria-label="Comprobaciones">
            {PESTANAS.map((p) => (
              <button key={p.clave} type="button" role="tab" aria-selected={p.clave === pestana}
                className={p.clave === pestana ? 'pestana activa' : 'pestana'} data-pestana={p.clave}
                onClick={() => cambiar({ pestana: p.clave === 'doble' ? null : p.clave })}>
                {p.texto}
                {p.clave === 'sin-factura' && d.sin_factura.totales.alertas > 0 && <span className="pestana-n">{d.sin_factura.totales.alertas}</span>}
              </button>
            ))}
          </div>
          <div role="tabpanel" className="cc-panel" data-panel={pestana}>
            {pestana === 'doble' && <DobleComprobacion d={d} params={params} cambiar={cambiar} />}
            {pestana === 'albaranes' && <PestanaAlbaranes d={d} />}
            {pestana === 'sin-factura' && <PestanaSinFactura sf={d.sin_factura} />}
            {pestana === 'banco' && <PestanaBanco />}
          </div>
        </div>
      )}
    </>
  );
}
