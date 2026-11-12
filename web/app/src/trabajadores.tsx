// TA1 Trabajadores: fichas (listado, alta, edición, baja) y detalle con objetivo anual provisional e historial.
// Solo datos de ejemplo en memoria del servidor (modo FIXTURES). En modo REAL: "Módulo pendiente de conexión (T1)".
import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  CATEGORIAS, FRANJA_JORNADA, HORAS_COMPLETA, HORAS_POR_DEFECTO, JORNADAS, LARGO_NOMBRE, MENSAJE_PENDIENTE_T1, TEXTO_ACCION, TEXTO_BANNER_EJEMPLO,
  TEXTO_CAMPO, TEXTO_CATEGORIA, TEXTO_ESTADO_CONVENIO, TEXTO_FUERA_COMPUTO, TEXTO_JORNADA, TEXTO_PENDIENTE_T5, TEXTO_PROVISIONAL,
  TEXTO_REFERENCIA_PROVISIONAL, filtroFarmacia, horasSemanales, porcentajeDerivado,
  type Categoria, type EstadoRrhhDTO, type EventoHistorial, type FarmaciaRrhh, type FiltroFarmacia, type Jornada, type Trabajadora,
  type TrabajadoraDetalleDTO, type TrabajadorasDTO,
} from '../server/rrhh/contrato.ts';
import { ErrorApi, enviar, useApi, useApiRecargable } from './api.ts';
import { fechaCorta, fechaHora } from './formato.ts';
import { Cabecera, MOVIL, useMedia } from './ui.tsx';

const HORAS = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 1 });
const horas = (h: number) => `${HORAS.format(h)} h`;

// ---------------------------------------------------------------------------
// Marco del módulo: cabecera, banner fijo y aviso de modo REAL
// ---------------------------------------------------------------------------

function Banner() {
  return (
    <div className="rrhh-banner" role="status" data-banner-ejemplo>
      <span className="rrhh-banner-marca" aria-hidden="true">Ejemplo</span>
      <span>{TEXTO_BANNER_EJEMPLO}</span>
    </div>
  );
}

function Pendiente() {
  return (
    <section className="tarjeta rrhh-pendiente" data-rrhh-pendiente>
      <h2>{MENSAJE_PENDIENTE_T1}</h2>
      <p className="tenue">Las fichas de trabajadoras se verán aquí cuando el circuito cree las tablas del módulo. Hasta entonces no se muestra ningún dato.</p>
    </section>
  );
}

const SECCIONES = [
  { clave: 'fichas', texto: 'Fichas', a: '/trabajadores' },
  { clave: 'calendario', texto: 'Calendario', hito: 'TA2' },
  { clave: 'guardias', texto: 'Guardias y festivos', hito: 'TA3' },
] as const;

function Secciones() {
  return (
    <nav className="rrhh-secciones" aria-label="Secciones de Trabajadores">
      {SECCIONES.map((s) => ('a' in s
        ? <Link key={s.clave} to={s.a} className="rrhh-seccion activa" aria-current="page">{s.texto}</Link>
        : <span key={s.clave} className="rrhh-seccion" aria-disabled="true">{s.texto}<span className="chip-proximamente">{s.hito}</span></span>))}
    </nav>
  );
}

/** Marco común: en FIXTURES, banner fijo + contenido; en REAL, solo el aviso (nunca datos de ejemplo). */
function Modulo({ subtitulo, children }: { subtitulo: string; children: ReactNode }) {
  const estado = useApi<EstadoRrhhDTO>('/api/rrhh/estado');
  return (
    <div className="rrhh">
      <Cabecera titulo="Trabajadores" subtitulo={subtitulo} />
      {estado.estado === 'ok' && estado.datos.datos_ejemplo && <Banner />}
      <Secciones />
      {estado.estado === 'cargando' && <p className="tenue">Cargando…</p>}
      {estado.estado === 'error' && <p className="rrhh-error" role="alert">No se ha podido leer el módulo ({estado.mensaje}).</p>}
      {estado.estado === 'ok' && (estado.datos.datos_ejemplo ? children : <Pendiente />)}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Piezas
// ---------------------------------------------------------------------------

export function EtiquetaFarmacia({ f }: { f: FarmaciaRrhh }) {
  return <span className={`rrhh-farmacia f-${f.toLowerCase()}`} data-farmacia={f}>{f}</span>;
}

const PORCENTAJE = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 });

/**
 * Jornada (TA1-2): horas diarias (lunes a viernes) + porcentaje DERIVADO sobre la referencia semanal del año
 * (calculado, no editable) + barra de ese porcentaje (el elemento propio del módulo).
 */
function JornadaBarra({ t, referencia }: { t: Pick<Trabajadora, 'jornada' | 'horas_diarias'>; referencia: number | null }) {
  const pct = referencia === null ? null : porcentajeDerivado(t, { horas_semanales_referencia: referencia });
  return (
    <span className="rrhh-jornada" data-jornada={t.jornada}>
      <span className="rrhh-jornada-texto" data-horas-diarias>{TEXTO_JORNADA[t.jornada]} · {horas(t.horas_diarias)}/día</span>
      {pct !== null && (
        <span className="rrhh-jornada-calculo" data-porcentaje-derivado title={`Calculado: ${horas(horasSemanales(t))} a la semana / ${horas(referencia as number)} (${TEXTO_REFERENCIA_PROVISIONAL})`}>
          {PORCENTAJE.format(pct)} % · {horas(horasSemanales(t))}/sem
        </span>
      )}
      <span className="rrhh-barra" aria-hidden="true"><span style={{ width: `${Math.min(pct ?? 0, 100)}%` }} /></span>
    </span>
  );
}

function Computa({ t }: { t: Trabajadora }) {
  return t.computa_convenio
    ? <span data-computa="si">Sí</span>
    : <span className="tenue" data-computa="no">No · titular</span>;
}

function SelectorFarmacia({ valor, onChange }: { valor: FiltroFarmacia; onChange: (v: FiltroFarmacia) => void }) {
  const opciones: { v: FiltroFarmacia; texto: string }[] = [{ v: 'PIO', texto: 'PIO' }, { v: 'RITA', texto: 'RITA' }, { v: 'AMBAS', texto: 'Ambas' }];
  return (
    <div className="rrhh-selector" role="radiogroup" aria-label="Farmacia">
      {opciones.map((o) => (
        <button key={o.v} type="button" role="radio" aria-checked={valor === o.v} className={valor === o.v ? 'activa' : undefined}
          data-selector-farmacia={o.v} onClick={() => onChange(o.v)}>{o.texto}</button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Formulario de ficha (alta y edición)
// ---------------------------------------------------------------------------

interface ValoresFicha { farmacia: FarmaciaRrhh; nombre: string; categoria: Categoria; jornada: Jornada; horas: string; es_titular: boolean }

/** "4,5" o "4.5" → 4.5; vacío o no numérico → NaN. */
const leerHoras = (s: string) => (s.trim() === '' ? NaN : Number(s.trim().replace(',', '.')));
const textoHoras = (h: number) => HORAS.format(h);

function FormularioFicha({ inicial, alta, referencia, onGuardada, onCancelar }: {
  inicial: ValoresFicha; alta: boolean; referencia: number | null; onGuardada: (t: Trabajadora) => void; onCancelar: () => void;
}) {
  const [v, setV] = useState<ValoresFicha>(inicial);
  const [errores, setErrores] = useState<Record<string, string>>({});
  const [enviando, setEnviando] = useState(false);
  // Al corregir un campo se retira su error (y el general); el resto se mantiene hasta volver a guardar.
  const cambiar = (x: Partial<ValoresFicha>) => {
    setV((p) => ({ ...p, ...x }));
    const claves = Object.keys(x).flatMap((k) => (k === 'horas' ? ['horas_diarias'] : k === 'jornada' ? ['jornada', 'horas_diarias'] : [k]));
    setErrores((p) => Object.fromEntries(Object.entries(p).filter(([k]) => k !== '_' && !claves.includes(k))));
  };

  async function guardar(e: FormEvent) {
    e.preventDefault();
    const local: Record<string, string> = {};
    if (v.nombre.trim() === '') local.nombre = 'Escribe el nombre';
    const horasDia = leerHoras(v.horas);
    if (!Number.isFinite(horasDia) || horasDia <= 0 || horasDia > HORAS_COMPLETA) local.horas_diarias = 'Horas al día: más de 0 y como máximo 8';
    if (Object.keys(local).length) { setErrores(local); return; }
    // El resto de reglas (completa = 8; media mañana < 8; decimales) las valida el servidor.
    const cuerpo = { ...(alta ? { farmacia: v.farmacia } : {}), nombre: v.nombre, categoria: v.categoria, jornada: v.jornada, horas_diarias: horasDia, es_titular: v.es_titular };
    setEnviando(true);
    try {
      const t = alta
        ? await enviar<Trabajadora>('/api/rrhh/trabajadoras', 'POST', cuerpo)
        : await enviar<Trabajadora>(`/api/rrhh/trabajadoras/${(inicial as ValoresFicha & { id?: string }).id}`, 'PUT', cuerpo);
      onGuardada(t);
    } catch (err) {
      setErrores(err instanceof ErrorApi && Object.keys(err.errores).length ? err.errores : { _: 'No se ha podido guardar la ficha. Revisa los datos.' });
    } finally {
      setEnviando(false);
    }
  }

  const error = (k: string) => errores[k] && <span className="rrhh-campo-error" data-error-campo={k}>{errores[k]}</span>;
  return (
    <form className="tarjeta rrhh-formulario" onSubmit={guardar} noValidate data-formulario-ficha={alta ? 'alta' : 'edicion'}>
      <h2>{alta ? 'Nueva ficha' : 'Editar ficha'}</h2>
      {errores._ && <p className="rrhh-error" role="alert">{errores._}</p>}
      <div className="rrhh-campos">
        <label className="rrhh-campo rrhh-campo-ancho">Nombre
          <input name="nombre" value={v.nombre} maxLength={LARGO_NOMBRE} required autoComplete="off" aria-invalid={!!errores.nombre}
            onChange={(e) => cambiar({ nombre: e.target.value })} />
          {error('nombre')}
        </label>
        {alta ? (
          <label className="rrhh-campo">Farmacia
            <select name="farmacia" value={v.farmacia} onChange={(e) => cambiar({ farmacia: e.target.value as FarmaciaRrhh })}>
              <option value="PIO">PIO</option><option value="RITA">RITA</option>
            </select>
            {error('farmacia')}
          </label>
        ) : (
          <div className="rrhh-campo">Farmacia<span className="rrhh-fijo"><EtiquetaFarmacia f={v.farmacia} /> <span className="tenue">no se cambia</span></span></div>
        )}
        <label className="rrhh-campo">Categoría
          <select name="categoria" value={v.categoria} onChange={(e) => cambiar({ categoria: e.target.value as Categoria })}>
            {CATEGORIAS.map((c) => <option key={c} value={c}>{TEXTO_CATEGORIA[c]}</option>)}
          </select>
          {error('categoria')}
        </label>
        <label className="rrhh-campo">Jornada
          <select name="jornada" value={v.jornada}
            onChange={(e) => { const j = e.target.value as Jornada; cambiar({ jornada: j, horas: textoHoras(HORAS_POR_DEFECTO[j]) }); }}>
            {JORNADAS.map((j) => <option key={j} value={j}>{TEXTO_JORNADA[j]}</option>)}
          </select>
          {error('jornada')}
        </label>
        <label className="rrhh-campo">Horas al día <span className="rrhh-campo-pista" data-franja>{FRANJA_JORNADA[v.jornada]}</span>
          <span className="rrhh-sufijo"><input name="horas_diarias" inputMode="decimal" value={v.horas} aria-invalid={!!errores.horas_diarias}
            onChange={(e) => cambiar({ horas: e.target.value })} /><span aria-hidden="true">h</span></span>
          {error('horas_diarias')}
        </label>
        <div className="rrhh-campo">Porcentaje de jornada <span className="rrhh-campo-pista">calculado, no se edita</span>
          <span className="rrhh-calculado" data-porcentaje-formulario>
            {(() => {
              const h = leerHoras(v.horas);
              if (referencia === null || !Number.isFinite(h) || h <= 0) return '—';
              return `${PORCENTAJE.format(porcentajeDerivado({ horas_diarias: h }, { horas_semanales_referencia: referencia }))} % · ${horas(horasSemanales({ horas_diarias: h }))} de ${horas(referencia)}/sem`;
            })()}
          </span>
        </div>
        <label className="rrhh-check">
          <input type="checkbox" name="es_titular" checked={v.es_titular} onChange={(e) => cambiar({ es_titular: e.target.checked })} />
          Titular de la farmacia <span className="tenue">(fuera del cómputo del convenio; se registran sus horas)</span>
        </label>
      </div>
      <div className="rrhh-botones">
        <button type="submit" className="boton-primario" disabled={enviando}>{alta ? 'Crear ficha' : 'Guardar cambios'}</button>
        <button type="button" className="boton-secundario" onClick={onCancelar}>Cancelar</button>
      </div>
    </form>
  );
}

const valoresDe = (t: Trabajadora): ValoresFicha & { id: string } => ({
  id: t.id, farmacia: t.farmacia, nombre: t.nombre, categoria: t.categoria, jornada: t.jornada, horas: textoHoras(t.horas_diarias), es_titular: t.es_titular,
});

// ---------------------------------------------------------------------------
// Fichas (listado)
// ---------------------------------------------------------------------------

export function PaginaTrabajadores() {
  return (
    <Modulo subtitulo="Fichas del equipo de PIO y RITA">
      <Fichas />
    </Modulo>
  );
}

function Fichas() {
  const [params, setParams] = useSearchParams();
  const farmacia = filtroFarmacia(params.get('farmacia')) ?? 'AMBAS';
  const bajas = params.get('bajas') === '1';
  const { carga, recargar } = useApiRecargable<TrabajadorasDTO>(`/api/rrhh/trabajadoras?farmacia=${farmacia}${bajas ? '&bajas=1' : ''}`);
  const [alta, setAlta] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const movil = useMedia(MOVIL);
  const navegar = useNavigate();

  const cambiar = (x: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(x)) { if (v === null) p.delete(k); else p.set(k, v); }
    setParams(p, { replace: true });
  };

  if (carga.estado === 'cargando') return <p className="tenue">Cargando fichas…</p>;
  if (carga.estado === 'error') return <p className="rrhh-error" role="alert">No se han podido leer las fichas ({carga.mensaje}).</p>;
  const d = carga.datos;
  const activas = d.trabajadoras.filter((t) => t.activa);
  const computan = activas.filter((t) => t.computa_convenio).length;
  const c = d.convenio.find((x) => x.anio === d.anio_referencia);

  return (
    <div className="rrhh-fichas" data-rrhh-fichas>
      <div className="rrhh-barra-herramientas">
        <SelectorFarmacia valor={farmacia} onChange={(v) => cambiar({ farmacia: v === 'AMBAS' ? null : v })} />
        <label className="rrhh-check rrhh-bajas">
          <input type="checkbox" checked={bajas} onChange={(e) => cambiar({ bajas: e.target.checked ? '1' : null })} /> Incluir bajas
        </label>
        {!alta && <button type="button" className="boton-primario" onClick={() => { setAlta(true); setAviso(null); }}>Nueva ficha</button>}
      </div>
      {aviso && <p className="rrhh-aviso-ok" role="status" data-aviso-rrhh>{aviso}</p>}
      {alta && (
        <FormularioFicha alta
          referencia={c?.horas_semanales_referencia ?? null}
          inicial={{ farmacia: farmacia === 'RITA' ? 'RITA' : 'PIO', nombre: '', categoria: 'TECNICO', jornada: 'COMPLETA', horas: textoHoras(HORAS_COMPLETA), es_titular: false }}
          onCancelar={() => setAlta(false)}
          onGuardada={(t) => { setAlta(false); setAviso(`Ficha creada: ${t.nombre} (${t.farmacia}).`); recargar(); }} />
      )}
      <p className="rrhh-resumen" data-resumen-fichas>
        {activas.length} {activas.length === 1 ? 'ficha activa' : 'fichas activas'} · {computan} en el cómputo del convenio
        {c && <> · jornada máxima {c.anio}: <strong>{horas(c.jornada_maxima_horas)}</strong> · jornada completa de referencia: <strong data-referencia-semanal>{horas(c.horas_semanales_referencia)}/sem</strong> <span className="tenue">({TEXTO_PROVISIONAL})</span></>}
      </p>
      {d.trabajadoras.length === 0 ? (
        <p className="tarjeta rrhh-vacio">No hay fichas en esta farmacia. Crea la primera con «Nueva ficha».</p>
      ) : movil ? (
        <ul className="rrhh-tarjetas">
          {d.trabajadoras.map((t) => (
            <li key={t.id} className={`tarjeta rrhh-tarjeta${t.activa ? '' : ' de-baja'}`} data-ficha={t.id}>
              <div className="rrhh-tarjeta-cabecera">
                <Link to={`/trabajadores/${t.id}`} className="rrhh-nombre">{t.nombre}</Link>
                <EtiquetaFarmacia f={t.farmacia} />
              </div>
              <div className="rrhh-tarjeta-linea"><span className="tenue">{TEXTO_CATEGORIA[t.categoria]}</span><span><span className="tenue">Computa:</span> <Computa t={t} /></span></div>
              <JornadaBarra t={t} referencia={c?.horas_semanales_referencia ?? null} />
              {!t.activa && <span className="insignia n">Baja {fechaCorta(t.fecha_baja)}</span>}
            </li>
          ))}
        </ul>
      ) : (
        <div className="tarjeta rrhh-tabla-marco">
          <table className="tabla rrhh-tabla">
            <thead><tr><th scope="col">Nombre</th><th scope="col">Farmacia</th><th scope="col">Categoría</th><th scope="col">Jornada</th><th scope="col">Computa</th></tr></thead>
            <tbody>
              {d.trabajadoras.map((t) => (
                <tr key={t.id} data-ficha={t.id} className={t.activa ? undefined : 'de-baja'} onClick={() => navegar(`/trabajadores/${t.id}`)}>
                  <td>
                    <Link to={`/trabajadores/${t.id}`} className="rrhh-nombre" onClick={(e) => e.stopPropagation()}>{t.nombre}</Link>
                    {t.es_titular && <span className="insignia n insignia-mini rrhh-titular">titular</span>}
                    {!t.activa && <span className="insignia n insignia-mini">baja {fechaCorta(t.fecha_baja)}</span>}
                  </td>
                  <td><EtiquetaFarmacia f={t.farmacia} /></td>
                  <td>{TEXTO_CATEGORIA[t.categoria]}</td>
                  <td><JornadaBarra t={t} referencia={c?.horas_semanales_referencia ?? null} /></td>
                  <td><Computa t={t} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detalle de ficha
// ---------------------------------------------------------------------------

export function PaginaTrabajadora() {
  return (
    <Modulo subtitulo="Ficha, objetivo anual e historial de cambios">
      <Detalle />
    </Modulo>
  );
}

function valorLlano(campo: string, v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'boolean') return v ? 'Sí' : 'No';
  if (campo === 'categoria') return TEXTO_CATEGORIA[v as Categoria] ?? String(v);
  if (campo === 'jornada') return TEXTO_JORNADA[v as Jornada] ?? String(v);
  if (campo === 'horas_diarias') return `${horas(Number(v))}/día`;
  if (campo === 'fecha_baja') return fechaCorta(String(v));
  return String(v);
}

function Cambio({ h }: { h: EventoHistorial }) {
  const campos = Object.keys(h.despues ?? {}).filter((k) => !(h.accion === 'ALTA' && k === 'activa'));
  return (
    <li className="rrhh-cambio" data-historial={h.accion}>
      <div className="rrhh-cambio-cabecera">
        <strong>{TEXTO_ACCION[h.accion]}</strong>
        <span className="tenue">{fechaHora(h.cuando)} · {h.quien}</span>
      </div>
      <ul className="rrhh-cambio-campos">
        {campos.map((k) => (
          <li key={k}>
            <span className="tenue">{TEXTO_CAMPO[k] ?? k}:</span>{' '}
            {h.antes && k in h.antes && <><span className="rrhh-antes">{valorLlano(k, (h.antes as Record<string, unknown>)[k])}</span> → </>}
            <span className="rrhh-despues">{valorLlano(k, (h.despues as Record<string, unknown>)[k])}</span>
          </li>
        ))}
      </ul>
    </li>
  );
}

function FormularioBaja({ id, onHecha, onCancelar }: { id: string; onHecha: () => void; onCancelar: () => void }) {
  const [fecha, setFecha] = useState('');
  const [error, setError] = useState<string | null>(null);
  async function confirmar(e: FormEvent) {
    e.preventDefault();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(fecha)) { setError('Indica la fecha de baja'); return; }
    try {
      await enviar(`/api/rrhh/trabajadoras/${id}/baja`, 'PUT', { fecha_baja: fecha });
      onHecha();
    } catch (err) {
      setError(err instanceof ErrorApi && err.codigo === 'YA_DE_BAJA' ? 'Esta ficha ya está de baja.' : err instanceof ErrorApi && err.errores.fecha_baja ? err.errores.fecha_baja : 'No se ha podido dar de baja.');
    }
  }
  return (
    <form className="tarjeta rrhh-formulario rrhh-formulario-baja" onSubmit={confirmar} noValidate data-formulario-baja>
      <h2>Dar de baja</h2>
      <p className="tenue">La ficha se conserva con su historial; deja de salir en el listado salvo con «Incluir bajas».</p>
      <label className="rrhh-campo">Fecha de baja
        <input type="date" name="fecha_baja" value={fecha} onChange={(e) => setFecha(e.target.value)} aria-invalid={!!error} />
        {error && <span className="rrhh-campo-error" data-error-campo="fecha_baja">{error}</span>}
      </label>
      <div className="rrhh-botones">
        <button type="submit" className="boton-peligro">Confirmar baja</button>
        <button type="button" className="boton-secundario" onClick={onCancelar}>Cancelar</button>
      </div>
    </form>
  );
}

function Detalle() {
  const { id = '' } = useParams();
  const { carga, recargar } = useApiRecargable<TrabajadoraDetalleDTO>(`/api/rrhh/trabajadoras/${id}`);
  const [modo, setModo] = useState<'ver' | 'editar' | 'baja'>('ver');
  const [aviso, setAviso] = useState<string | null>(null);
  useEffect(() => { setModo('ver'); setAviso(null); }, [id]);

  if (carga.estado === 'cargando') return <p className="tenue">Cargando ficha…</p>;
  if (carga.estado === 'error') {
    return <p className="rrhh-error" role="alert">{carga.mensaje === 'TRABAJADORA_NO_ENCONTRADA' ? 'No existe esta ficha.' : `No se ha podido leer la ficha (${carga.mensaje}).`} <Link to="/trabajadores">Volver a fichas</Link></p>;
  }
  const { trabajadora: t, objetivos, historial } = carga.datos;
  const anio = Number(new Date().toISOString().slice(0, 4));
  // Referencia semanal del año en curso (o la del primer año del convenio).
  const ref = (objetivos.find((o) => o.anio === anio) ?? objetivos[0])?.horas_semanales_referencia ?? null;

  return (
    <div className="rrhh-detalle" data-detalle-ficha={t.id}>
      <p className="migas"><Link to="/trabajadores">← Fichas</Link></p>
      {aviso && <p className="rrhh-aviso-ok" role="status" data-aviso-rrhh>{aviso}</p>}
      <section className="tarjeta rrhh-ficha">
        <div className="rrhh-ficha-arriba">
          <div className="rrhh-ficha-titulo">
            <h2 data-nombre-ficha>{t.nombre}</h2>
            <div className="rrhh-ficha-meta">
              <EtiquetaFarmacia f={t.farmacia} />
              <span>{TEXTO_CATEGORIA[t.categoria]}</span>
              {t.es_titular && <span className="insignia n">Titular</span>}
              {t.activa ? <span className="insignia g">Activa</span> : <span className="insignia n" data-baja>Baja desde {fechaCorta(t.fecha_baja)}</span>}
            </div>
          </div>
          {modo === 'ver' && (
            <div className="rrhh-botones">
              <button type="button" className="boton-secundario" onClick={() => { setModo('editar'); setAviso(null); }}>Editar ficha</button>
              {t.activa && <button type="button" className="boton-peligro-suave" onClick={() => { setModo('baja'); setAviso(null); }}>Dar de baja</button>}
            </div>
          )}
        </div>
        <dl className="kv-rejilla rrhh-kv">
          <div className="kv"><dt>Jornada</dt><dd><JornadaBarra t={t} referencia={ref} /></dd></div>
          <div className="kv"><dt>Computa en el convenio</dt><dd><Computa t={t} /></dd></div>
        </dl>
      </section>

      {modo === 'editar' && (
        <FormularioFicha alta={false} inicial={valoresDe(t)} referencia={ref} onCancelar={() => setModo('ver')}
          onGuardada={() => { setModo('ver'); setAviso('Cambios guardados en la ficha.'); recargar(); }} />
      )}
      {modo === 'baja' && (
        <FormularioBaja id={t.id} onCancelar={() => setModo('ver')} onHecha={() => { setModo('ver'); setAviso('Ficha dada de baja.'); recargar(); }} />
      )}

      <section className="tarjeta bloque" aria-labelledby="t-objetivo">
        <div className="bloque-cabecera">
          <h2 id="t-objetivo">Objetivo anual de horas</h2>
          <span className="insignia o" data-provisional>{t.computa_convenio ? TEXTO_PROVISIONAL : TEXTO_FUERA_COMPUTO}</span>
        </div>
        <p className="bloque-nota tenue">
          {t.computa_convenio
            ? 'Jornada máxima del convenio de cada año por el porcentaje calculado de la ficha (sus horas semanales sobre la jornada completa de referencia).'
            : 'El titular no computa en el convenio; sus horas se registrarán igualmente.'}
        </p>
        <div className="rrhh-objetivos">
          {objetivos.map((o) => (
            <div key={o.anio} className={`rrhh-objetivo${o.anio === anio ? ' actual' : ''}`} data-objetivo={o.anio}>
              <span className="rrhh-objetivo-anio">{o.anio}</span>
              <span className="rrhh-objetivo-horas" data-objetivo-horas>{o.objetivo_horas === null ? TEXTO_FUERA_COMPUTO : horas(o.objetivo_horas)}</span>
              <span className="tenue rrhh-objetivo-calculo">
                {horas(o.jornada_maxima_horas)} × {horas(o.horas_semanales)} / {horas(o.horas_semanales_referencia)} ({PORCENTAJE.format(o.porcentaje_derivado)} %)
                <span className="rrhh-objetivo-estado">referencia {horas(o.horas_semanales_referencia)}/sem provisional · {TEXTO_ESTADO_CONVENIO[o.estado].toLowerCase()}</span>
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="tarjeta bloque" aria-labelledby="t-horas">
        <h2 id="t-horas">Horas de {anio}</h2>
        <dl className="rrhh-horas">
          {['Planificadas', 'Confirmadas', 'Pendientes'].map((x) => (
            <div key={x} className="rrhh-hueco" data-hueco-horas={x.toLowerCase()}>
              <dt>{x}</dt><dd>{TEXTO_PENDIENTE_T5}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="tarjeta bloque" aria-labelledby="t-historial">
        <h2 id="t-historial">Historial de cambios</h2>
        {historial.length === 0
          ? <p className="tenue vacio" data-historial-vacio>Sin cambios desde la carga de ejemplo.</p>
          : <ul className="rrhh-historial">{historial.map((h) => <Cambio key={h.id} h={h} />)}</ul>}
      </section>
    </div>
  );
}
