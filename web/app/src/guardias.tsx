// TA3 Trabajadores: guardias y festivos. Pestaña «Guardias y festivos» y piezas que usa el calendario (banda de la
// semana de guardia en la vista año y cabecera «Guardia · Apoyo sábado» en semana y mes). TA3-REAL: también en REAL
// (migración 34); los festivos que crea la web son comunes a las dos farmacias, con ámbito elegible (por defecto local).
// TA3-4 (decisión de Marc): guardias, apoyos, OTRA y festivos se pintan en el calendario (herramientas de guardia); la
// pestaña pasa a lista de consulta del año, solo lectura, con «Editar en el calendario» que abre la semana.
// Horas fuera de cómputo: se registran, no suman en el año (HORARIO_GUARDIA, único punto).
import { type CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import { ANIOS_CONVENIO } from '../server/rrhh/contrato.ts';
import { CODIGO_TIPO_EVENTO, TEXTO_TIPO_EVENTO, diaSemana, lunesDe, textoPeriodoCambio } from '../server/rrhh/eventos.ts';
import {
  COLOR_FARMACIA_GUARDIA, HORARIO_GUARDIA, HORAS_SERVICIO, TEXTO_AMBITO, TEXTO_FARMACIA_GUARDIA, textoTramos,
  type FarmaciaGuardia, type FestivoVista, type GuardiasRespuestaDTO, type PersonaGuardia, type SemanaGuardiaVista,
} from '../server/rrhh/guardias.ts';
import { useApiRecargable } from './api.ts';
import { useAnio } from './ficha_anual.tsx';
import { Modulo } from './trabajadores.tsx';

const NUM = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 });
const horas = (h: number) => `${NUM.format(h)} h`;
const F_FESTIVO = new Intl.DateTimeFormat('es-ES', { timeZone: 'UTC', weekday: 'short', day: 'numeric', month: 'short' });
const fechaFestivo = (f: string) => F_FESTIVO.format(new Date(f + 'T00:00:00Z'));
/** Enlace al calendario en la semana de esa fecha (vista semana). */
export const rutaCalendarioSemana = (fecha: string) => `/trabajadores/calendario?fecha=${lunesDe(fecha)}`;

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

/**
 * Vista año: banda de la semana de guardia (color de la farmacia + iniciales). TA3-4: con una herramienta de guardia
 * activa es un botón (Guardia/Apoyo: selector de persona; OTRA; Goma) con el texto de lo que hará.
 */
export function BandaGuardia({ s, accion, onClick }: { s: SemanaGuardiaVista; accion?: string; onClick?: () => void }) {
  const titulo = `Semana ${textoPeriodoCambio(s.lunes, s.domingo)}: ${s.farmacia ? `${s.farmacia} · ` : ''}${textoGuardiaSemana(s)}`;
  const contenido = (
    <>
      <span className="gu-banda-cod" aria-hidden="true">{CODIGO_TIPO_EVENTO.TURNO_GUARDIA}</span>
      {s.farmacia && s.farmacia !== 'OTRA' && <span className="gu-banda-f">{s.farmacia}</span>}
      <span className="gu-banda-txt">{textoBanda(s)}</span>
    </>
  );
  const props = {
    className: `gu-banda${s.farmacia === null ? ' sin' : ''}${onClick ? ' activa' : ''}`, style: s.farmacia ? estiloGuardia(s.farmacia) : undefined,
    'data-banda-semana': s.lunes, 'data-banda-farmacia': s.farmacia ?? '',
  };
  return onClick
    ? <button type="button" {...props} title={`${titulo}. ${accion ?? ''}`} aria-label={`${titulo}. ${accion ?? ''}`} onClick={onClick}>{contenido}</button>
    : <span {...props} title={titulo} aria-label={titulo}>{contenido}</span>;
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

/**
 * Lectura de guardias y festivos de un periodo (datos null mientras carga o si falla: el calendario sigue sin ellas).
 * TA3-4: recargable tras cada herramienta de guardia.
 */
export function useGuardias(desde: string, hasta: string): { datos: GuardiasRespuestaDTO | null; recargar: () => void } {
  const { carga, recargar } = useApiRecargable<GuardiasRespuestaDTO>(`/api/rrhh/guardias?desde=${desde}&hasta=${hasta}`);
  return { datos: carga.estado === 'ok' ? carga.datos : null, recargar };
}

// ---------------------------------------------------------------------------
// Página (consulta del año, solo lectura)
// ---------------------------------------------------------------------------

export function PaginaGuardias() {
  return (
    <Modulo subtitulo="Guardias semanales y festivos de Ulldecona: PIO, RITA y OTRA (farmacia ajena)" seccion="guardias">
      <Guardias />
    </Modulo>
  );
}

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

  if (g.carga.estado === 'cargando') return <p className="tenue">Cargando guardias…</p>;
  if (g.carga.estado === 'error') return <p className="rrhh-error" role="alert">No se han podido leer las guardias ({g.carga.mensaje}).</p>;
  const d = g.carga.datos;
  return (
    <div className="gu" data-guardias={anio}>
      <div className="rrhh-barra-herramientas">
        <SelectorAnioGuardias valor={anio} onChange={setAnio} />
        <span className="tenue">{d.semanas.filter((s) => s.farmacia !== null).length} de {d.semanas.length} semanas asignadas · {d.festivos.length} festivos</span>
      </div>
      <p className="gu-solo-consulta" data-solo-consulta>
        <span className="rrhh-banner-marca">Consulta</span>
        <span>
          Guardias, apoyos, farmacia ajena y festivos se pintan en el calendario, con las herramientas de guardia de la paleta.
          {' '}<Link to={`/trabajadores/calendario?vista=anio&fecha=${anio}-01-01`} data-editar-calendario-anio>Abrir {anio} en el calendario</Link>
        </span>
      </p>
      <div className="gu-rejilla">
        <ListaSemanas semanas={d.semanas} hoy={hoy} />
        <div className="gu-lateral">
          <Horario />
          <ListaFestivos anio={anio} festivos={d.festivos} />
        </div>
      </div>
    </div>
  );
}

function NombrePersona({ p }: { p: PersonaGuardia | null }) {
  return p ? <span title={p.nombre}>{p.nombre}</span> : <span className="tenue">—</span>;
}

// ---------------------------------------------------------------------------
// Semanas
// ---------------------------------------------------------------------------

function ListaSemanas({ semanas, hoy }: { semanas: SemanaGuardiaVista[]; hoy: string }) {
  const actual = lunesDe(hoy);
  return (
    <section className="tarjeta gu-semanas" aria-labelledby="t-gu-semanas">
      <div className="bloque-cabecera"><h2 id="t-gu-semanas">Guardia semanal</h2><span className="tenue">de lunes a domingo; una por semana</span></div>
      <div className="gu-tabla-marco">
        <table className="tabla gu-tabla">
          <thead><tr><th scope="col">Semana</th><th scope="col">Farmacia</th><th scope="col">Guardia</th><th scope="col">Apoyo sábado</th><th scope="col" className="num">Horas</th><th scope="col"><span className="oculto">Calendario</span></th></tr></thead>
          <tbody>
            {semanas.map((s) => (
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
                <td>
                  <Link to={rutaCalendarioSemana(s.lunes)} className="gu-enlace-calendario" data-editar-semana={s.lunes}
                    aria-label={`Editar en el calendario la semana ${textoPeriodoCambio(s.lunes, s.domingo)}`}>Editar en el calendario</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Festivos
// ---------------------------------------------------------------------------

function ListaFestivos({ anio, festivos }: { anio: number; festivos: FestivoVista[] }) {
  return (
    <section className="tarjeta gu-festivos" aria-labelledby="t-gu-festivos">
      <div className="bloque-cabecera"><h2 id="t-gu-festivos">Festivos de {anio}</h2><span className="tenue">rotación de guardia propia</span></div>
      {festivos.length === 0 ? <p className="tenue" data-sin-festivos>Sin festivos en {anio}. Se dan de alta en el calendario, con la herramienta Festivo.</p> : (
        <ul className="gu-lista-festivos">
          {festivos.map((f) => (
            <li key={f.fecha} data-festivo={f.fecha} className={diaSemana(f.fecha) >= 5 ? 'finde' : undefined}>
              <div className="gu-festivo-linea">
                <span className="gu-festivo-fecha">{fechaFestivo(f.fecha)}</span>
                <span className="gu-festivo-nombre"><span data-nombre-festivo>{f.nombre}</span> <span className="tenue gu-festivo-ambito" data-ambito-festivo={f.ambito}>· {TEXTO_AMBITO[f.ambito].toLowerCase()}</span></span>
                <span className="gu-festivo-guardia" data-guardia-festivo>
                  {f.guardia ? <><ChipGuardia f={f.guardia.farmacia} /> {f.guardia.farmacia === 'OTRA' ? <span className="tenue">farmacia ajena</span> : <NombrePersona p={f.guardia.persona} />}</>
                    : <span className="tenue" data-sin-asignar>guardia sin asignar</span>}
                </span>
                <Link to={rutaCalendarioSemana(f.fecha)} className="gu-enlace-calendario" data-editar-festivo={f.fecha}
                  aria-label={`Editar en el calendario ${f.nombre} (${fechaFestivo(f.fecha)})`}>Editar en el calendario</Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
