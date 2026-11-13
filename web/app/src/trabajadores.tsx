// TA1 Trabajadores: fichas (listado, alta, edición, baja) y detalle con objetivo anual provisional e historial.
// TA2: el calendario está en calendario.tsx (usa Modulo, SelectorFarmacia y EtiquetaFarmacia de aquí).
// TA-REAL: modo FIXTURES = datos de ejemplo (banner «Datos de ejemplo»); modo REAL = tablas reales (banner de datos
// reales; sin credencial, «Falta configurar la credencial de Trabajadores» y ningún dato). Categorías del esquema
// (titular = Farmacéutica titular, fuera del cómputo); fecha de alta obligatoria; «Anular» aparte, con confirmación;
// si faltan años del convenio, botón para crearlos con los valores firmados.
import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  CATEGORIAS, CONVENIO_ANUAL, FRANJA_JORNADA, HORAS_COMPLETA, HORAS_POR_DEFECTO, JORNADAS, LARGO_NOMBRE, TEXTO_ACCION, TEXTO_BANNER_EJEMPLO,
  TEXTO_BANNER_REAL, TEXTO_CAMPO, TEXTO_CATEGORIA, TEXTO_ESTADO_CONVENIO, TEXTO_FUERA_COMPUTO, TEXTO_JORNADA, TEXTO_PENDIENTE_T5, TEXTO_PROVISIONAL,
  TEXTO_REFERENCIA_PROVISIONAL, aniosConvenioQueFaltan, esTitular, filtroFarmacia, horasSemanales, porcentajeDerivado,
  type Categoria, type ConvenioAnual, type EstadoRrhhDTO, type EventoHistorial, type FarmaciaRrhh, type FiltroFarmacia, type Jornada, type Trabajadora,
  type TrabajadoraDetalleDTO, type TrabajadorasDTO,
} from '../server/rrhh/contrato.ts';
import { ErrorApi, enviar, useApi, useApiRecargable } from './api.ts';
import { fechaCorta, fechaHora } from './formato.ts';
import { Cabecera, MOVIL, useMedia } from './ui.tsx';

const HORAS = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 1 });
const horas = (h: number) => `${HORAS.format(h)} h`;
/** Hoy en el reloj del navegador (fecha local). */
export function hoyLocal(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
/** Mensaje de un error de escritura: el llano del servidor si lo hay. */
const textoErrorApi = (err: unknown, defecto: string) => (err instanceof ErrorApi && err.mensaje ? err.mensaje : defecto);

// ---------------------------------------------------------------------------
// Marco del módulo: cabecera, banner fijo y aviso de modo REAL
// ---------------------------------------------------------------------------

function Banner({ real }: { real: boolean }) {
  return real ? (
    <div className="rrhh-banner rrhh-banner-real" role="status" data-banner-real>
      <span className="rrhh-banner-marca" aria-hidden="true">Real</span>
      <span>{TEXTO_BANNER_REAL}</span>
    </div>
  ) : (
    <div className="rrhh-banner" role="status" data-banner-ejemplo>
      <span className="rrhh-banner-marca" aria-hidden="true">Ejemplo</span>
      <span>{TEXTO_BANNER_EJEMPLO}</span>
    </div>
  );
}

function SinConexion({ mensaje }: { mensaje: string }) {
  return (
    <section className="tarjeta rrhh-pendiente" data-rrhh-pendiente>
      <h2>{mensaje}</h2>
      <p className="tenue">Las fichas y el calendario se verán aquí cuando la web pueda conectar con las tablas del módulo. Hasta entonces no se muestra ningún dato.</p>
    </section>
  );
}

type Seccion = 'fichas' | 'calendario';
const SECCIONES = [
  { clave: 'fichas', texto: 'Fichas', a: '/trabajadores' },
  { clave: 'calendario', texto: 'Calendario', a: '/trabajadores/calendario' },
  { clave: 'guardias', texto: 'Guardias y festivos', hito: 'TA3' },
] as const;

function Secciones({ activa }: { activa: Seccion }) {
  return (
    <nav className="rrhh-secciones" aria-label="Secciones de Trabajadores">
      {SECCIONES.map((s) => ('a' in s
        ? <Link key={s.clave} to={s.a} className={`rrhh-seccion${s.clave === activa ? ' activa' : ''}`} aria-current={s.clave === activa ? 'page' : undefined}
          data-seccion={s.clave}>{s.texto}</Link>
        : <span key={s.clave} className="rrhh-seccion" aria-disabled="true">{s.texto}<span className="chip-proximamente">{s.hito}</span></span>))}
    </nav>
  );
}

/** Marco común: FIXTURES, banner de ejemplo; REAL conectado, banner de datos reales; REAL sin conexión, solo el aviso. */
export function Modulo({ subtitulo, seccion = 'fichas', children }: { subtitulo: string; seccion?: Seccion; children: ReactNode }) {
  const estado = useApi<EstadoRrhhDTO>('/api/rrhh/estado');
  const listo = estado.estado === 'ok' && (estado.datos.datos_ejemplo || estado.datos.conectado);
  return (
    <div className="rrhh">
      <Cabecera titulo="Trabajadores" subtitulo={subtitulo} />
      {listo && <Banner real={!estado.datos.datos_ejemplo} />}
      <Secciones activa={seccion} />
      {estado.estado === 'cargando' && <p className="tenue">Cargando…</p>}
      {estado.estado === 'error' && <p className="rrhh-error" role="alert">No se ha podido leer el módulo ({estado.mensaje}).</p>}
      {estado.estado === 'ok' && (listo ? children : <SinConexion mensaje={estado.datos.mensaje} />)}
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
function JornadaBarra({ t, referencia }: { t: Pick<Trabajadora, 'tipo_jornada' | 'horas_diarias'>; referencia: number | null }) {
  const pct = referencia === null ? null : porcentajeDerivado(t, { horas_semanales_referencia: referencia });
  return (
    <span className="rrhh-jornada" data-jornada={t.tipo_jornada}>
      <span className="rrhh-jornada-texto" data-horas-diarias>{TEXTO_JORNADA[t.tipo_jornada]} · {horas(t.horas_diarias)}/día</span>
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

/** Estado de la ficha: anulada, baja o activa. */
function EstadoFicha({ t, mini = false }: { t: Trabajadora; mini?: boolean }) {
  const c = mini ? ' insignia-mini' : '';
  if (t.anulada) return <span className={`insignia n${c}`} data-anulada>anulada</span>;
  if (t.fecha_baja) return <span className={`insignia n${c}`} data-baja>{mini ? 'baja' : 'Baja desde'} {fechaCorta(t.fecha_baja)}</span>;
  return mini ? null : <span className="insignia g">Activa</span>;
}

export function SelectorFarmacia({ valor, onChange }: { valor: FiltroFarmacia; onChange: (v: FiltroFarmacia) => void }) {
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
// Convenio: si faltan años firmados (REAL recién conectado), se crean con los valores firmados
// ---------------------------------------------------------------------------

function ConvenioQueFalta({ convenio, onCreado }: { convenio: ConvenioAnual[]; onCreado: () => void }) {
  const faltan = aniosConvenioQueFaltan(convenio);
  const [confirmar, setConfirmar] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (faltan.length === 0) return null;
  const crear = async () => {
    try {
      await enviar('/api/rrhh/convenio', 'POST', { anios: faltan });
      setConfirmar(false);
      onCreado();
    } catch (e) {
      setError(textoErrorApi(e, 'No se ha podido crear el convenio.'));
    }
  };
  const valores = CONVENIO_ANUAL.filter((c) => faltan.includes(c.anio));
  return (
    <section className="tarjeta rrhh-convenio-falta" data-convenio-falta={faltan.join(',')}>
      <p><strong>Faltan en la base de datos los años {faltan.join(', ')} del convenio.</strong> Sin ellos no hay objetivo anual ni porcentaje de jornada.</p>
      {!confirmar ? (
        <button type="button" className="boton-primario" onClick={() => { setConfirmar(true); setError(null); }} data-crear-convenio>
          Crear convenio {CONVENIO_ANUAL[0].anio}–{CONVENIO_ANUAL[CONVENIO_ANUAL.length - 1].anio} con los valores firmados
        </button>
      ) : (
        <div role="alertdialog" aria-labelledby="t-conf-convenio" data-confirmar-convenio>
          <p id="t-conf-convenio">Se crearán estos años (los que ya existen no se tocan):</p>
          <ul className="rrhh-convenio-valores">
            {valores.map((c) => (
              <li key={c.anio}>{c.anio}: jornada máxima {horas(c.jornada_max_horas)} · {c.asuntos_propios_dias} {c.asuntos_propios_dias === 1 ? 'día' : 'días'} de asuntos propios · permiso médico {horas(c.permiso_medico_horas)} · referencia {horas(c.horas_semanales_referencia)}/sem · {TEXTO_ESTADO_CONVENIO[c.estado].toLowerCase()}</li>
            ))}
          </ul>
          <div className="rrhh-botones">
            <button type="button" className="boton-primario" onClick={crear} data-crear-convenio-si>Sí, crear el convenio</button>
            <button type="button" className="boton-secundario" onClick={() => setConfirmar(false)}>Cancelar</button>
          </div>
        </div>
      )}
      {error && <p className="rrhh-error" role="alert">{error}</p>}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Formulario de ficha (alta y edición)
// ---------------------------------------------------------------------------

interface ValoresFicha { farmacia: FarmaciaRrhh; nombre: string; categoria: Categoria; tipo_jornada: Jornada; horas: string; fecha_alta: string }

/** "4,5" o "4.5" → 4.5; vacío o no numérico → NaN. */
const leerHoras = (s: string) => (s.trim() === '' ? NaN : Number(s.trim().replace(',', '.')));
const textoHoras = (h: number) => HORAS.format(h);

function FormularioFicha({ inicial, alta, referencia, onGuardada, onCancelar }: {
  inicial: ValoresFicha & { id?: string }; alta: boolean; referencia: number | null; onGuardada: (t: Trabajadora) => void; onCancelar: () => void;
}) {
  const [v, setV] = useState<ValoresFicha>(inicial);
  const [errores, setErrores] = useState<Record<string, string>>({});
  const [enviando, setEnviando] = useState(false);
  // Al corregir un campo se retira su error (y el general); el resto se mantiene hasta volver a guardar.
  const cambiar = (x: Partial<ValoresFicha>) => {
    setV((p) => ({ ...p, ...x }));
    const claves = Object.keys(x).flatMap((k) => (k === 'horas' ? ['horas_diarias'] : k === 'tipo_jornada' ? ['tipo_jornada', 'horas_diarias'] : [k]));
    setErrores((p) => Object.fromEntries(Object.entries(p).filter(([k]) => k !== '_' && !claves.includes(k))));
  };

  async function guardar(e: FormEvent) {
    e.preventDefault();
    const local: Record<string, string> = {};
    if (v.nombre.trim() === '') local.nombre = 'Escribe el nombre';
    const horasDia = leerHoras(v.horas);
    if (!Number.isFinite(horasDia) || horasDia <= 0 || horasDia > HORAS_COMPLETA) local.horas_diarias = 'Horas al día: más de 0 y como máximo 8';
    if (!/^\d{4}-\d{2}-\d{2}$/.test(v.fecha_alta)) local.fecha_alta = 'Indica la fecha de alta';
    if (Object.keys(local).length) { setErrores(local); return; }
    // El resto de reglas (completa = 8; media mañana < 8; decimales) las valida el servidor.
    const cuerpo = {
      ...(alta ? { farmacia: v.farmacia } : {}), nombre: v.nombre, categoria: v.categoria, tipo_jornada: v.tipo_jornada, horas_diarias: horasDia, fecha_alta: v.fecha_alta,
    };
    setEnviando(true);
    try {
      const t = alta
        ? await enviar<Trabajadora>('/api/rrhh/trabajadoras', 'POST', cuerpo)
        : await enviar<Trabajadora>(`/api/rrhh/trabajadoras/${inicial.id}`, 'PUT', cuerpo);
      onGuardada(t);
    } catch (err) {
      setErrores(err instanceof ErrorApi && Object.keys(err.errores).length ? err.errores : { _: textoErrorApi(err, 'No se ha podido guardar la ficha. Revisa los datos.') });
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
          {esTitular(v) && <span className="rrhh-campo-pista" data-pista-titular>fuera del cómputo del convenio; se registran sus horas</span>}
          <select name="categoria" value={v.categoria} onChange={(e) => cambiar({ categoria: e.target.value as Categoria })}>
            {CATEGORIAS.map((c) => <option key={c} value={c}>{TEXTO_CATEGORIA[c]}</option>)}
          </select>
          {error('categoria')}
        </label>
        <label className="rrhh-campo">Fecha de alta <span className="rrhh-campo-pista">obligatoria</span>
          <input type="date" name="fecha_alta" value={v.fecha_alta} aria-invalid={!!errores.fecha_alta} onChange={(e) => cambiar({ fecha_alta: e.target.value })} />
          {error('fecha_alta')}
        </label>
        <label className="rrhh-campo">Jornada
          <select name="tipo_jornada" value={v.tipo_jornada}
            onChange={(e) => { const j = e.target.value as Jornada; cambiar({ tipo_jornada: j, horas: textoHoras(HORAS_POR_DEFECTO[j]) }); }}>
            {JORNADAS.map((j) => <option key={j} value={j}>{TEXTO_JORNADA[j]}</option>)}
          </select>
          {error('tipo_jornada')}
        </label>
        <label className="rrhh-campo">Horas al día <span className="rrhh-campo-pista" data-franja>{FRANJA_JORNADA[v.tipo_jornada]}</span>
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
      </div>
      <div className="rrhh-botones">
        <button type="submit" className="boton-primario" disabled={enviando}>{alta ? 'Crear ficha' : 'Guardar cambios'}</button>
        <button type="button" className="boton-secundario" onClick={onCancelar}>Cancelar</button>
      </div>
    </form>
  );
}

const valoresDe = (t: Trabajadora): ValoresFicha & { id: string } => ({
  id: t.id, farmacia: t.farmacia, nombre: t.nombre, categoria: t.categoria, tipo_jornada: t.tipo_jornada, horas: textoHoras(t.horas_diarias), fecha_alta: t.fecha_alta,
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
      <ConvenioQueFalta convenio={d.convenio} onCreado={() => { setAviso('Convenio creado con los valores firmados.'); recargar(); }} />
      <div className="rrhh-barra-herramientas">
        <SelectorFarmacia valor={farmacia} onChange={(v) => cambiar({ farmacia: v === 'AMBAS' ? null : v })} />
        <label className="rrhh-check rrhh-bajas">
          <input type="checkbox" checked={bajas} onChange={(e) => cambiar({ bajas: e.target.checked ? '1' : null })} /> Incluir bajas y anuladas
        </label>
        {!alta && <button type="button" className="boton-primario" onClick={() => { setAlta(true); setAviso(null); }}>Nueva ficha</button>}
      </div>
      {aviso && <p className="rrhh-aviso-ok" role="status" data-aviso-rrhh>{aviso}</p>}
      {alta && (
        <FormularioFicha alta
          referencia={c?.horas_semanales_referencia ?? null}
          inicial={{ farmacia: farmacia === 'RITA' ? 'RITA' : 'PIO', nombre: '', categoria: 'TECNICA', tipo_jornada: 'COMPLETA', horas: textoHoras(HORAS_COMPLETA), fecha_alta: hoyLocal() }}
          onCancelar={() => setAlta(false)}
          onGuardada={(t) => { setAlta(false); setAviso(`Ficha creada: ${t.nombre} (${t.farmacia}).`); recargar(); }} />
      )}
      <p className="rrhh-resumen" data-resumen-fichas>
        {activas.length} {activas.length === 1 ? 'ficha activa' : 'fichas activas'} · {computan} en el cómputo del convenio
        {c && <> · jornada máxima {c.anio}: <strong>{horas(c.jornada_max_horas)}</strong> · jornada completa de referencia: <strong data-referencia-semanal>{horas(c.horas_semanales_referencia)}/sem</strong> <span className="tenue">({TEXTO_PROVISIONAL})</span></>}
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
              {!t.activa && <EstadoFicha t={t} />}
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
                    {esTitular(t) && <span className="insignia n insignia-mini rrhh-titular">titular</span>}
                    <EstadoFicha t={t} mini />
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
  if (campo === 'tipo_jornada') return TEXTO_JORNADA[v as Jornada] ?? String(v);
  if (campo === 'horas_diarias') return `${horas(Number(v))}/día`;
  if (campo === 'fecha_baja' || campo === 'fecha_alta') return fechaCorta(String(v));
  return String(v);
}

function Cambio({ h }: { h: EventoHistorial }) {
  const campos = Object.keys(h.despues ?? {});
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
      setError(err instanceof ErrorApi && err.codigo === 'YA_DE_BAJA' ? 'Esta ficha ya está de baja.'
        : err instanceof ErrorApi && err.errores.fecha_baja ? err.errores.fecha_baja : textoErrorApi(err, 'No se ha podido dar de baja.'));
    }
  }
  return (
    <form className="tarjeta rrhh-formulario rrhh-formulario-baja" onSubmit={confirmar} noValidate data-formulario-baja>
      <h2>Dar de baja</h2>
      <p className="tenue">La ficha se conserva con su historial; deja de salir en el listado salvo con «Incluir bajas y anuladas», y en el calendario sale hasta su fecha de baja.</p>
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

/** TA-REAL: anular = marcar como registro erróneo (no se borra); con confirmación expresa. */
function FormularioAnular({ t, onHecha, onCancelar }: { t: Trabajadora; onHecha: () => void; onCancelar: () => void }) {
  const [error, setError] = useState<string | null>(null);
  async function confirmar() {
    try {
      await enviar(`/api/rrhh/trabajadoras/${t.id}/anular`, 'PUT', { confirmar: true });
      onHecha();
    } catch (err) {
      setError(err instanceof ErrorApi && err.codigo === 'YA_ANULADA' ? 'Esta ficha ya está anulada.' : textoErrorApi(err, 'No se ha podido anular la ficha.'));
    }
  }
  return (
    <section className="tarjeta rrhh-formulario rrhh-formulario-baja" role="alertdialog" aria-labelledby="t-anular" data-formulario-anular>
      <h2 id="t-anular">Anular la ficha de {t.nombre}</h2>
      <p>Anular es solo para fichas creadas por error. La ficha no se borra: queda marcada como anulada, con su historial, y deja de salir en el listado y en el calendario. Para una persona que deja de trabajar, usa «Dar de baja».</p>
      {error && <p className="rrhh-error" role="alert">{error}</p>}
      <div className="rrhh-botones">
        <button type="button" className="boton-peligro" onClick={confirmar} data-anular-si>Sí, anular la ficha</button>
        <button type="button" className="boton-secundario" onClick={onCancelar}>Cancelar</button>
      </div>
    </section>
  );
}

function Detalle() {
  const { id = '' } = useParams();
  const { carga, recargar } = useApiRecargable<TrabajadoraDetalleDTO>(`/api/rrhh/trabajadoras/${id}`);
  const [modo, setModo] = useState<'ver' | 'editar' | 'baja' | 'anular'>('ver');
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
  const ir = (m: typeof modo) => { setModo(m); setAviso(null); };

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
              {esTitular(t) && <span className="insignia n">Titular</span>}
              <EstadoFicha t={t} />
            </div>
          </div>
          {modo === 'ver' && !t.anulada && (
            <div className="rrhh-botones">
              <button type="button" className="boton-secundario" onClick={() => ir('editar')}>Editar ficha</button>
              {t.activa && <button type="button" className="boton-peligro-suave" onClick={() => ir('baja')}>Dar de baja</button>}
              <button type="button" className="boton-peligro-suave" onClick={() => ir('anular')} data-anular>Anular</button>
            </div>
          )}
        </div>
        <dl className="kv-rejilla rrhh-kv">
          <div className="kv"><dt>Jornada</dt><dd><JornadaBarra t={t} referencia={ref} /></dd></div>
          <div className="kv"><dt>Computa en el convenio</dt><dd><Computa t={t} /></dd></div>
          <div className="kv"><dt>Fecha de alta</dt><dd data-fecha-alta>{fechaCorta(t.fecha_alta)}</dd></div>
        </dl>
      </section>

      {modo === 'editar' && (
        <FormularioFicha alta={false} inicial={valoresDe(t)} referencia={ref} onCancelar={() => setModo('ver')}
          onGuardada={() => { setModo('ver'); setAviso('Cambios guardados en la ficha.'); recargar(); }} />
      )}
      {modo === 'baja' && (
        <FormularioBaja id={t.id} onCancelar={() => setModo('ver')} onHecha={() => { setModo('ver'); setAviso('Ficha dada de baja.'); recargar(); }} />
      )}
      {modo === 'anular' && (
        <FormularioAnular t={t} onCancelar={() => setModo('ver')} onHecha={() => { setModo('ver'); setAviso('Ficha anulada.'); recargar(); }} />
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
        {objetivos.length === 0 && <p className="tenue" data-objetivo-sin-convenio>Sin años de convenio en la base de datos: créalos desde Fichas.</p>}
        <div className="rrhh-objetivos">
          {objetivos.map((o) => (
            <div key={o.anio} className={`rrhh-objetivo${o.anio === anio ? ' actual' : ''}`} data-objetivo={o.anio}>
              <span className="rrhh-objetivo-anio">{o.anio}</span>
              <span className="rrhh-objetivo-horas" data-objetivo-horas>{o.objetivo_horas === null ? TEXTO_FUERA_COMPUTO : horas(o.objetivo_horas)}</span>
              <span className="tenue rrhh-objetivo-calculo">
                {horas(o.jornada_max_horas)} × {horas(o.horas_semanales)} / {horas(o.horas_semanales_referencia)} ({PORCENTAJE.format(o.porcentaje_derivado)} %)
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

      {/* TA2-2: historial plegado por defecto; se despliega con un clic. */}
      <details className="tarjeta bloque rrhh-plegable" data-historial-ficha>
        <summary>
          <h2 id="t-historial">Historial de cambios</h2>
          <span className="tenue">{historial.length === 0 ? 'sin cambios' : `${historial.length} ${historial.length === 1 ? 'cambio' : 'cambios'}`}</span>
        </summary>
        {historial.length === 0
          ? <p className="tenue vacio" data-historial-vacio>Sin cambios registrados.</p>
          : <ul className="rrhh-historial">{historial.map((h) => <Cambio key={h.id} h={h} />)}</ul>}
      </details>
    </div>
  );
}
