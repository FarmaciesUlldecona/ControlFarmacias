// TA3 Trabajadores: guardias y festivos. Pestaña «Guardias y festivos» (lista anual por semana con farmacia, guardia y
// apoyo del sábado; lista de festivos con alta, baja y su guardia) y piezas que usa el calendario (banda de la semana
// de guardia en la vista año y cabecera «Guardia · Apoyo sábado» en semana y mes). Solo modo FIXTURES: en REAL las
// tablas no existen todavía; la pestaña sale deshabilitada con «Pendiente de tablas en Supabase».
// Horas fuera de cómputo: se registran, no suman en el año (HORARIO_GUARDIA, único punto).
import { useEffect, useState, type CSSProperties, type FormEvent } from 'react';
import { ANIOS_CONVENIO, type Trabajadora, type TrabajadorasDTO } from '../server/rrhh/contrato.ts';
import { CODIGO_TIPO_EVENTO, TEXTO_TIPO_EVENTO, deAltaEl, diaSemana, lunesDe, textoPeriodoCambio } from '../server/rrhh/eventos.ts';
import {
  COLOR_FARMACIA_GUARDIA, FARMACIAS_GUARDIA, HORARIO_GUARDIA, HORAS_SERVICIO, LARGO_NOMBRE_FESTIVO, TEXTO_FARMACIA_GUARDIA,
  domingoDe, sabadoDe, textoTramos,
  type FarmaciaGuardia, type FestivoVista, type GuardiasRespuestaDTO, type PersonaGuardia, type SemanaGuardiaVista,
} from '../server/rrhh/guardias.ts';
import { ErrorApi, enviar, useApiRecargable } from './api.ts';
import { useAnio } from './ficha_anual.tsx';
import { Modulo } from './trabajadores.tsx';

const NUM = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 });
const horas = (h: number) => `${NUM.format(h)} h`;
const F_FESTIVO = new Intl.DateTimeFormat('es-ES', { timeZone: 'UTC', weekday: 'short', day: 'numeric', month: 'short' });
const fechaFestivo = (f: string) => F_FESTIVO.format(new Date(f + 'T00:00:00Z'));
const textoError = (e: unknown, defecto: string) => {
  if (!(e instanceof ErrorApi)) return defecto;
  const campos = Object.values(e.errores);
  return e.mensaje ?? (campos.length > 0 ? campos.join(' · ') : defecto);
};

// ---------------------------------------------------------------------------
// Piezas comunes (también en el calendario)
// ---------------------------------------------------------------------------

/** Color de la farmacia de guardia (OTRA, gris claro con texto oscuro). */
export const estiloGuardia = (f: FarmaciaGuardia) =>
  ({ '--g': COLOR_FARMACIA_GUARDIA[f], '--gt': f === 'OTRA' ? 'var(--gris-texto)' : '#ffffff' }) as CSSProperties;

export function ChipGuardia({ f }: { f: FarmaciaGuardia }) {
  return <span className="gu-chip" style={estiloGuardia(f)} data-guardia-farmacia={f}>{f}</span>;
}

/** Texto corto de una semana para la banda del año: «G: AB · A: CD»; OTRA; sin asignar. */
export function textoBanda(s: SemanaGuardiaVista): string {
  if (s.farmacia === null) return 'sin asignar';
  if (s.farmacia === 'OTRA') return 'OTRA';
  return `G: ${s.guardia?.iniciales ?? '—'}${s.apoyo ? ` · A: ${s.apoyo.iniciales}` : ''}`;
}
/** Texto largo: «Guardia: Nombre · Apoyo sábado: Nombre». */
export function textoGuardiaSemana(s: SemanaGuardiaVista): string {
  if (s.farmacia === null) return 'Guardia: sin asignar';
  if (s.farmacia === 'OTRA') return `Guardia: ${TEXTO_FARMACIA_GUARDIA.OTRA}`;
  return `Guardia: ${s.guardia?.nombre ?? '—'} · Apoyo sábado: ${s.apoyo?.nombre ?? '—'}`;
}
const textoGuardiaFestivo = (f: FestivoVista) => (f.guardia === null ? 'guardia sin asignar'
  : f.guardia.farmacia === 'OTRA' ? `guardia ${TEXTO_FARMACIA_GUARDIA.OTRA}` : `guardia ${f.guardia.farmacia} · ${f.guardia.persona?.nombre ?? '—'}`);

/** Vista año: banda de la semana de guardia (color de la farmacia + iniciales). */
export function BandaGuardia({ s }: { s: SemanaGuardiaVista }) {
  const titulo = `Semana ${textoPeriodoCambio(s.lunes, s.domingo)}: ${s.farmacia ? `${s.farmacia} · ` : ''}${textoGuardiaSemana(s)}`;
  return (
    <span className={`gu-banda${s.farmacia === null ? ' sin' : ''}`} style={s.farmacia ? estiloGuardia(s.farmacia) : undefined}
      data-banda-semana={s.lunes} data-banda-farmacia={s.farmacia ?? ''} title={titulo} aria-label={titulo}>
      <span className="gu-banda-cod" aria-hidden="true">{CODIGO_TIPO_EVENTO.TURNO_GUARDIA}</span>
      {s.farmacia && s.farmacia !== 'OTRA' && <span className="gu-banda-f">{s.farmacia}</span>}
      <span className="gu-banda-txt">{textoBanda(s)}</span>
    </span>
  );
}

/** Semana y mes: «Guardia: Nombre · Apoyo sábado: Nombre» de cada semana del periodo y los festivos con su nombre. */
export function CabeceraGuardias({ datos }: { datos: GuardiasRespuestaDTO | null }) {
  if (datos === null || !datos.disponible) return null;
  return (
    <section className="gu-cabecera" aria-label="Guardias y festivos del periodo" data-cabecera-guardias>
      <ul className="gu-semanas-linea">
        {datos.semanas.map((s) => (
          <li key={s.lunes} data-cabecera-semana={s.lunes}>
            {datos.semanas.length > 1 && <span className="tenue gu-cuando">{textoPeriodoCambio(s.lunes, s.domingo)}</span>}
            {s.farmacia ? <ChipGuardia f={s.farmacia} /> : <span className="gu-chip sin">—</span>}
            <span data-texto-guardia>{textoGuardiaSemana(s)}</span>
          </li>
        ))}
      </ul>
      {datos.festivos.length > 0 && (
        <ul className="gu-festivos-linea">
          {datos.festivos.map((f) => (
            <li key={f.fecha} data-cabecera-festivo={f.fecha}>
              <span className="gu-f" aria-hidden="true">{CODIGO_TIPO_EVENTO.FESTIVO}</span>
              <strong>{fechaFestivo(f.fecha)}</strong> {f.nombre} <span className="tenue">· {textoGuardiaFestivo(f)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Lectura de guardias y festivos de un periodo (null mientras carga o si falla: el calendario sigue sin ellas). */
export function useGuardias(desde: string, hasta: string): GuardiasRespuestaDTO | null {
  const { carga } = useApiRecargable<GuardiasRespuestaDTO>(`/api/rrhh/guardias?desde=${desde}&hasta=${hasta}`);
  return carga.estado === 'ok' ? carga.datos : null;
}

// ---------------------------------------------------------------------------
// Página
// ---------------------------------------------------------------------------

export function PaginaGuardias() {
  return (
    <Modulo subtitulo="Guardias semanales y festivos de Ulldecona: PIO, RITA y OTRA (farmacia ajena)" seccion="guardias">
      <Guardias />
    </Modulo>
  );
}

type Aviso = { ok: boolean; texto: string } | null;

function Horario() {
  const h = HORARIO_GUARDIA;
  return (
    <section className="tarjeta gu-horario" aria-labelledby="t-gu-horario" data-horario-guardia>
      <h2 id="t-gu-horario">Horario de guardia</h2>
      <dl>
        <div><dt><span className="gu-f g" aria-hidden="true">{CODIGO_TIPO_EVENTO.TURNO_GUARDIA}</span>{TEXTO_TIPO_EVENTO.TURNO_GUARDIA}</dt>
          <dd>sábado {textoTramos(h.GUARDIA_SABADO)} ({horas(HORAS_SERVICIO.GUARDIA_SABADO)}) · domingo {textoTramos(h.GUARDIA_DOMINGO)} ({horas(HORAS_SERVICIO.GUARDIA_DOMINGO)})</dd></div>
        <div><dt><span className="gu-f a" aria-hidden="true">A</span>Apoyo del sábado</dt>
          <dd>{textoTramos(h.APOYO_SABADO)} ({horas(HORAS_SERVICIO.APOYO_SABADO)})</dd></div>
        <div><dt><span className="gu-f" aria-hidden="true">{CODIGO_TIPO_EVENTO.FESTIVO}</span>Festivo de guardia</dt>
          <dd>{textoTramos(h.FESTIVO)} ({horas(HORAS_SERVICIO.FESTIVO)})</dd></div>
        <div><dt><span className="gu-f l" aria-hidden="true">{CODIGO_TIPO_EVENTO.LOCALIZADA}</span>{TEXTO_TIPO_EVENTO.LOCALIZADA} por teléfono</dt>
          <dd>la persona de guardia, toda la semana; sin horas, solo constancia</dd></div>
      </dl>
      <p className="tenue gu-nota">Horas fuera de cómputo: se registran y salen en la ficha anual, pero no suman en las horas del año. Un festivo en sábado o domingo sustituye ese día de la semana de guardia.</p>
    </section>
  );
}

function SelectorAnioGuardias({ valor, onChange }: { valor: number; onChange: (a: number) => void }) {
  return (
    <div className="rrhh-selector" role="radiogroup" aria-label="Año">
      {ANIOS_CONVENIO.map((a) => (
        <button key={a} type="button" role="radio" aria-checked={valor === a} className={valor === a ? 'activa' : undefined}
          data-selector-anio={a} onClick={() => onChange(a)}>{a}</button>
      ))}
    </div>
  );
}

function Guardias() {
  const [anio, setAnio, hoy] = useAnio();
  const g = useApiRecargable<GuardiasRespuestaDTO>(`/api/rrhh/guardias?anio=${anio}`);
  const fichas = useApiRecargable<TrabajadorasDTO>('/api/rrhh/trabajadoras?farmacia=AMBAS&bajas=1');
  const [aviso, setAviso] = useState<Aviso>(null);
  useEffect(() => setAviso(null), [anio]);

  if (g.carga.estado === 'cargando' || fichas.carga.estado === 'cargando') return <p className="tenue">Cargando guardias…</p>;
  if (g.carga.estado === 'error') return <p className="rrhh-error" role="alert">No se han podido leer las guardias ({g.carga.mensaje}).</p>;
  if (fichas.carga.estado === 'error') return <p className="rrhh-error" role="alert">No se han podido leer las fichas ({fichas.carga.mensaje}).</p>;
  const d = g.carga.datos;
  if (!d.disponible) {
    return (
      <section className="tarjeta rrhh-pendiente" data-ta3-pendiente>
        <h2>{d.mensaje}</h2>
        <p className="tenue">Las guardias semanales y los festivos se podrán ver y editar cuando existan sus tablas.</p>
      </section>
    );
  }
  const personas = fichas.carga.datos.trabajadoras.filter((t) => !t.anulada);
  const hecho = (texto: string) => { setAviso({ ok: true, texto }); g.recargar(); };
  const fallo = (texto: string) => setAviso({ ok: false, texto });
  return (
    <div className="gu" data-guardias={anio}>
      <div className="rrhh-barra-herramientas">
        <SelectorAnioGuardias valor={anio} onChange={setAnio} />
        <span className="tenue">{d.semanas.filter((s) => s.farmacia !== null).length} de {d.semanas.length} semanas asignadas · {d.festivos.length} festivos</span>
      </div>
      {aviso && <p className={aviso.ok ? 'rrhh-aviso-ok' : 'rrhh-error'} role={aviso.ok ? 'status' : 'alert'} data-aviso-guardias>{aviso.texto}</p>}
      <div className="gu-rejilla">
        <ListaSemanas semanas={d.semanas} personas={personas} hoy={hoy} onHecho={hecho} onFallo={fallo} />
        <div className="gu-lateral">
          <Horario />
          <ListaFestivos anio={anio} festivos={d.festivos} personas={personas} onHecho={hecho} onFallo={fallo} />
        </div>
      </div>
    </div>
  );
}

/** Personas de una farmacia de alta en todas esas fechas (titular incluido). */
const candidatas = (personas: Trabajadora[], farmacia: FarmaciaGuardia, fechas: string[]) =>
  farmacia === 'OTRA' ? [] : personas.filter((t) => t.farmacia === farmacia && fechas.every((f) => deAltaEl(t, f)));

function NombrePersona({ p }: { p: PersonaGuardia | null }) {
  return p ? <span title={p.nombre}>{p.nombre}</span> : <span className="tenue">—</span>;
}

// ---------------------------------------------------------------------------
// Semanas
// ---------------------------------------------------------------------------

function ListaSemanas({ semanas, personas, hoy, onHecho, onFallo }: {
  semanas: SemanaGuardiaVista[]; personas: Trabajadora[]; hoy: string; onHecho: (t: string) => void; onFallo: (t: string) => void;
}) {
  const [editando, setEditando] = useState<string | null>(null);
  const actual = lunesDe(hoy);
  return (
    <section className="tarjeta gu-semanas" aria-labelledby="t-gu-semanas">
      <div className="bloque-cabecera"><h2 id="t-gu-semanas">Guardia semanal</h2><span className="tenue">de lunes a domingo; una por semana</span></div>
      <div className="gu-tabla-marco">
        <table className="tabla gu-tabla">
          <thead><tr><th scope="col">Semana</th><th scope="col">Farmacia</th><th scope="col">Guardia</th><th scope="col">Apoyo sábado</th><th scope="col" className="num">Horas</th><th scope="col"><span className="oculto">Acción</span></th></tr></thead>
          <tbody>
            {semanas.map((s) => (editando === s.lunes
              ? <EditorSemana key={s.lunes} s={s} personas={personas} onCancelar={() => setEditando(null)}
                  onHecho={(t) => { setEditando(null); onHecho(t); }} onFallo={onFallo} />
              : (
                <tr key={s.lunes} data-semana={s.lunes} className={`${s.lunes === actual ? 'actual' : ''}${s.farmacia === null ? ' sin' : ''}`}>
                  <th scope="row" className="gu-semana-cuando">
                    <span className="gu-barra" style={s.farmacia ? estiloGuardia(s.farmacia) : undefined} aria-hidden="true" />
                    {textoPeriodoCambio(s.lunes, s.domingo)}
                    {s.festivos.length > 0 && <span className="gu-f" title={`${s.festivos.length} festivo(s)`} aria-label="con festivo">{CODIGO_TIPO_EVENTO.FESTIVO}</span>}
                  </th>
                  <td>{s.farmacia ? <ChipGuardia f={s.farmacia} /> : <span className="tenue" data-sin-asignar>sin asignar</span>}</td>
                  <td data-col="guardia">{s.farmacia === 'OTRA' ? <span className="tenue">farmacia ajena</span> : <NombrePersona p={s.guardia} />}</td>
                  <td data-col="apoyo">{s.farmacia === 'OTRA' ? <span className="tenue">—</span> : <NombrePersona p={s.apoyo} />}</td>
                  <td className="num tenue" data-col="horas">{s.horas_guardia + s.horas_apoyo > 0 ? horas(s.horas_guardia + s.horas_apoyo) : '—'}</td>
                  <td><button type="button" className="boton-secundario boton-mini" onClick={() => setEditando(s.lunes)} data-editar-semana={s.lunes}>Editar</button></td>
                </tr>
              )))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function EditorSemana({ s, personas, onCancelar, onHecho, onFallo }: {
  s: SemanaGuardiaVista; personas: Trabajadora[]; onCancelar: () => void; onHecho: (t: string) => void; onFallo: (t: string) => void;
}) {
  const [farmacia, setFarmacia] = useState<FarmaciaGuardia>(s.farmacia ?? 'PIO');
  const [guardia, setGuardia] = useState(s.guardia?.id ?? '');
  const [apoyo, setApoyo] = useState(s.apoyo?.id ?? '');
  const opcionesGuardia = candidatas(personas, farmacia, [sabadoDe(s.lunes), domingoDe(s.lunes)]);
  const opcionesApoyo = candidatas(personas, farmacia, [sabadoDe(s.lunes)]).filter((t) => t.id !== guardia);
  const cambiarFarmacia = (f: FarmaciaGuardia) => { setFarmacia(f); setGuardia(''); setApoyo(''); };
  async function guardar(e: FormEvent) {
    e.preventDefault();
    const cuerpo = farmacia === 'OTRA' ? { farmacia } : { farmacia, persona_guardia_id: guardia || null, persona_apoyo_sabado_id: apoyo || null };
    try {
      await enviar(`/api/rrhh/guardias/${s.lunes}`, 'PUT', cuerpo);
      onHecho(`Guardia de la semana ${textoPeriodoCambio(s.lunes, s.domingo)} guardada.`);
    } catch (err) {
      onFallo(textoError(err, 'No se ha podido guardar la guardia.'));
    }
  }
  const id = `gu-sem-${s.lunes}`;
  return (
    <tr className="gu-editando" data-editor-semana={s.lunes}>
      <th scope="row" className="gu-semana-cuando">{textoPeriodoCambio(s.lunes, s.domingo)}</th>
      <td>
        <select form={id} aria-label="Farmacia de guardia" value={farmacia} onChange={(e) => cambiarFarmacia(e.target.value as FarmaciaGuardia)} data-campo="farmacia">
          {FARMACIAS_GUARDIA.map((f) => <option key={f} value={f}>{TEXTO_FARMACIA_GUARDIA[f]}</option>)}
        </select>
      </td>
      <td>
        {farmacia === 'OTRA' ? <span className="tenue">sin personas</span> : (
          <select form={id} aria-label="Persona de guardia" value={guardia} onChange={(e) => { setGuardia(e.target.value); if (e.target.value === apoyo) setApoyo(''); }} data-campo="guardia">
            <option value="">Elige…</option>
            {opcionesGuardia.map((t) => <option key={t.id} value={t.id}>{t.nombre}</option>)}
          </select>
        )}
      </td>
      <td>
        {farmacia === 'OTRA' ? <span className="tenue">—</span> : (
          <select form={id} aria-label="Apoyo del sábado" value={apoyo} onChange={(e) => setApoyo(e.target.value)} data-campo="apoyo">
            <option value="">Sin apoyo</option>
            {opcionesApoyo.map((t) => <option key={t.id} value={t.id}>{t.nombre}</option>)}
          </select>
        )}
      </td>
      <td />
      <td>
        <form id={id} onSubmit={guardar} noValidate className="gu-botones">
          <button type="submit" className="boton-primario boton-mini" data-guardar-semana>Guardar</button>
          <button type="button" className="boton-secundario boton-mini" onClick={onCancelar}>Cancelar</button>
        </form>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Festivos
// ---------------------------------------------------------------------------

function ListaFestivos({ anio, festivos, personas, onHecho, onFallo }: {
  anio: number; festivos: FestivoVista[]; personas: Trabajadora[]; onHecho: (t: string) => void; onFallo: (t: string) => void;
}) {
  const [fecha, setFecha] = useState('');
  const [nombre, setNombre] = useState('');
  const [editando, setEditando] = useState<string | null>(null);
  const [baja, setBaja] = useState<string | null>(null);
  async function alta(e: FormEvent) {
    e.preventDefault();
    try {
      await enviar('/api/rrhh/festivos', 'POST', { fecha, nombre });
      setFecha(''); setNombre('');
      onHecho(`Festivo añadido: ${fechaFestivo(fecha)}, ${nombre.trim()}.`);
    } catch (err) {
      onFallo(textoError(err, 'No se ha podido añadir el festivo.'));
    }
  }
  async function darDeBaja(f: FestivoVista) {
    try {
      await enviar(`/api/rrhh/festivos/${f.fecha}/anular`, 'PUT', { confirmar: true });
      setBaja(null);
      onHecho(`Festivo dado de baja: ${fechaFestivo(f.fecha)}, ${f.nombre}.`);
    } catch (err) {
      onFallo(textoError(err, 'No se ha podido dar de baja el festivo.'));
    }
  }
  return (
    <section className="tarjeta gu-festivos" aria-labelledby="t-gu-festivos">
      <div className="bloque-cabecera"><h2 id="t-gu-festivos">Festivos de {anio}</h2><span className="tenue">rotación de guardia propia</span></div>
      <form className="gu-alta" onSubmit={alta} noValidate data-alta-festivo>
        <label className="rrhh-campo">Fecha
          <input type="date" name="fecha_festivo" min={`${anio}-01-01`} max={`${anio}-12-31`} value={fecha} onChange={(e) => setFecha(e.target.value)} />
        </label>
        <label className="rrhh-campo gu-alta-nombre">Nombre
          <input name="nombre_festivo" maxLength={LARGO_NOMBRE_FESTIVO} value={nombre} autoComplete="off" onChange={(e) => setNombre(e.target.value)} />
        </label>
        <button type="submit" className="boton-primario" data-anadir-festivo>Añadir festivo</button>
      </form>
      {festivos.length === 0 ? <p className="tenue" data-sin-festivos>Sin festivos en {anio}. Añade el primero con la fecha y el nombre.</p> : (
        <ul className="gu-lista-festivos">
          {festivos.map((f) => (
            <li key={f.fecha} data-festivo={f.fecha} className={diaSemana(f.fecha) >= 5 ? 'finde' : undefined}>
              <div className="gu-festivo-linea">
                <span className="gu-festivo-fecha">{fechaFestivo(f.fecha)}</span>
                <span className="gu-festivo-nombre" data-nombre-festivo>{f.nombre}</span>
                <span className="gu-festivo-guardia" data-guardia-festivo>
                  {f.guardia ? <><ChipGuardia f={f.guardia.farmacia} /> {f.guardia.farmacia === 'OTRA' ? <span className="tenue">farmacia ajena</span> : <NombrePersona p={f.guardia.persona} />}</>
                    : <span className="tenue" data-sin-asignar>guardia sin asignar</span>}
                </span>
                {editando !== f.fecha && baja !== f.fecha && (
                  <span className="gu-botones">
                    <button type="button" className="boton-secundario boton-mini" onClick={() => { setEditando(f.fecha); setBaja(null); }} data-editar-festivo={f.fecha}>Guardia</button>
                    <button type="button" className="boton-peligro-suave boton-mini" onClick={() => { setBaja(f.fecha); setEditando(null); }} data-baja-festivo={f.fecha}>Dar de baja</button>
                  </span>
                )}
              </div>
              {editando === f.fecha && (
                <EditorGuardiaFestivo f={f} personas={personas} onCancelar={() => setEditando(null)}
                  onHecho={(t) => { setEditando(null); onHecho(t); }} onFallo={onFallo} />
              )}
              {baja === f.fecha && (
                <div className="gu-confirmar" role="alertdialog" aria-label={`Dar de baja ${f.nombre}`} data-confirmar-baja={f.fecha}>
                  <span>¿Dar de baja «{f.nombre}»? Se anula con su guardia (no se borra).</span>
                  <button type="button" className="boton-peligro boton-mini" onClick={() => darDeBaja(f)} data-baja-festivo-si>Sí, dar de baja</button>
                  <button type="button" className="boton-secundario boton-mini" onClick={() => setBaja(null)}>Cancelar</button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Persona por defecto: la de guardia de esa semana si es la misma farmacia (editable). */
const porDefecto = (f: FestivoVista, farmacia: FarmaciaGuardia) =>
  (f.semana && f.semana.farmacia === farmacia && f.semana.guardia ? f.semana.guardia.id : '');

function EditorGuardiaFestivo({ f, personas, onCancelar, onHecho, onFallo }: {
  f: FestivoVista; personas: Trabajadora[]; onCancelar: () => void; onHecho: (t: string) => void; onFallo: (t: string) => void;
}) {
  const inicial: FarmaciaGuardia = f.guardia?.farmacia ?? f.semana?.farmacia ?? 'PIO';
  const [farmacia, setFarmacia] = useState<FarmaciaGuardia>(inicial);
  const [persona, setPersona] = useState(f.guardia?.persona?.id ?? porDefecto(f, inicial));
  const opciones = candidatas(personas, farmacia, [f.fecha]);
  const defecto = porDefecto(f, farmacia);
  async function guardar(e: FormEvent) {
    e.preventDefault();
    try {
      await enviar(`/api/rrhh/festivos/${f.fecha}/guardia`, 'PUT', farmacia === 'OTRA' ? { farmacia } : { farmacia, persona_id: persona || null });
      onHecho(`Guardia del festivo ${fechaFestivo(f.fecha)} guardada.`);
    } catch (err) {
      onFallo(textoError(err, 'No se ha podido guardar la guardia del festivo.'));
    }
  }
  return (
    <form className="gu-editor-festivo" onSubmit={guardar} noValidate data-editor-festivo={f.fecha}>
      <label className="rrhh-campo">Farmacia
        <select value={farmacia} onChange={(e) => { const n = e.target.value as FarmaciaGuardia; setFarmacia(n); setPersona(porDefecto(f, n)); }} data-campo="farmacia">
          {FARMACIAS_GUARDIA.map((x) => <option key={x} value={x}>{TEXTO_FARMACIA_GUARDIA[x]}</option>)}
        </select>
      </label>
      {farmacia !== 'OTRA' && (
        <label className="rrhh-campo">Persona
          {defecto && <span className="rrhh-campo-pista" data-pista-defecto>por defecto, la de guardia de esa semana</span>}
          <select value={persona} onChange={(e) => setPersona(e.target.value)} data-campo="persona">
            <option value="">Elige…</option>
            {opciones.map((t) => <option key={t.id} value={t.id}>{t.nombre}</option>)}
          </select>
        </label>
      )}
      <span className="gu-botones">
        <button type="submit" className="boton-primario boton-mini" data-guardar-festivo>Guardar</button>
        <button type="button" className="boton-secundario boton-mini" onClick={onCancelar}>Cancelar</button>
      </span>
    </form>
  );
}
