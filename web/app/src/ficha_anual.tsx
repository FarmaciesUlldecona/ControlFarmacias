// TA-FICHA Trabajadores: ficha anual de cada persona (detalle) y tabla resumen de plantilla (pestaña Fichas).
// Los cálculos son del servidor (server/rrhh/ficha_anual.ts, comunes a FIXTURES y REAL); aquí solo se dibujan.
// Pieza propia: la regla de vacaciones, un día natural por casilla (verde disfrutado, azul planificado, vacía sin
// planificar; naranja si toca avisar; rojo por encima del derecho). Una media franja llena media casilla.
import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ANIOS_CONVENIO, TEXTO_CATEGORIA, type FiltroFarmacia } from '../server/rrhh/contrato.ts';
import { CODIGO_TIPO_EVENTO, COLOR_TIPO_EVENTO, TEXTO_TIPO_EVENTO, textoPeriodoCambio } from '../server/rrhh/eventos.ts';
import {
  TEXTO_DIAS_EXTRA_PENDIENTE, TEXTO_FESTIVOS_PENDIENTES,
  type AvisoFicha, type FichaAnual, type FichaAnualDTO, type Periodo, type ResumenPlantillaDTO,
} from '../server/rrhh/ficha_anual.ts';
import { useApiRecargable } from './api.ts';
import { fechaCorta } from './formato.ts';
import { MOVIL, useMedia } from './ui.tsx';
import { EtiquetaFarmacia, hoyLocal } from './trabajadores.tsx';

const NUM = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 1 });
const num = (x: number) => NUM.format(x);
const dias = (x: number) => `${num(x)} ${Math.abs(x) === 1 ? 'día' : 'días'}`;
const horas = (x: number) => `${num(x)} h`;

/** Año por defecto: el de hoy dentro de los del convenio (si no, el extremo más cercano). */
function anioPorDefecto(hoy: string): number {
  const a = Number(hoy.slice(0, 4));
  return Math.min(Math.max(a, Math.min(...ANIOS_CONVENIO)), Math.max(...ANIOS_CONVENIO));
}
function useAnio(): [number, (a: number) => void, string] {
  const [params, setParams] = useSearchParams();
  const hoy = hoyLocal();
  const v = Number(params.get('anio'));
  const anio = ANIOS_CONVENIO.includes(v) ? v : anioPorDefecto(hoy);
  const cambiar = (a: number) => {
    const p = new URLSearchParams(params);
    if (a === anioPorDefecto(hoy)) p.delete('anio'); else p.set('anio', String(a));
    setParams(p, { replace: true });
  };
  return [anio, cambiar, hoy];
}

function SelectorAnio({ valor, onChange }: { valor: number; onChange: (a: number) => void }) {
  return (
    <div className="rrhh-selector fa-selector-anio" role="radiogroup" aria-label="Año">
      {ANIOS_CONVENIO.map((a) => (
        <button key={a} type="button" role="radio" aria-checked={valor === a} className={valor === a ? 'activa' : undefined}
          data-selector-anio={a} onClick={() => onChange(a)}>{a}</button>
      ))}
    </div>
  );
}

function Avisos({ avisos }: { avisos: AvisoFicha[] }) {
  if (avisos.length === 0) return null;
  return (
    <ul className="fa-avisos" data-avisos-ficha>
      {avisos.map((a) => <li key={a.codigo} className={`fa-aviso${a.codigo === 'SIN_CONVENIO' ? ' gris' : ''}`} data-aviso={a.codigo}>{a.texto}</li>)}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Regla de vacaciones (un día natural por casilla)
// ---------------------------------------------------------------------------

type Mitad = 'disfrutada' | 'planificada' | 'pendiente' | 'exceso' | 'nada';

/** Estado de cada media casilla: primero lo disfrutado, después lo planificado y lo que falta hasta el derecho. */
export function mitadesRegla(v: Pick<FichaAnual['vacaciones'], 'derecho' | 'disfrutadas' | 'planificadas'>): Mitad[] {
  const usado = v.disfrutadas + v.planificadas;
  const total = Math.ceil(Math.max(v.derecho, usado));
  return Array.from({ length: total * 2 }, (_, k) => {
    const x = k / 2;
    if (x < v.disfrutadas) return x < v.derecho ? 'disfrutada' : 'exceso';
    if (x < usado) return x < v.derecho ? 'planificada' : 'exceso';
    return x < v.derecho ? 'pendiente' : 'nada';
  });
}

function ReglaVacaciones({ v, avisar }: { v: FichaAnual['vacaciones']; avisar: boolean }) {
  const mitades = mitadesRegla(v);
  const casillas = Array.from({ length: mitades.length / 2 }, (_, i) => [mitades[2 * i], mitades[2 * i + 1]] as const);
  const etiqueta = `Vacaciones: ${dias(v.disfrutadas)} disfrutados, ${dias(v.planificadas)} planificados, ${dias(Math.max(v.pendientes, 0))} sin planificar de ${dias(v.derecho)}`;
  return (
    <div className={`fa-regla${avisar ? ' avisar' : ''}`} role="img" aria-label={etiqueta} data-regla-vacaciones
      style={{ gridTemplateColumns: `repeat(${Math.max(casillas.length, 1)}, minmax(0, 1fr))` }}>
      {casillas.map(([a, b], i) => (
        <span key={i} className="fa-dia" data-a={a} data-b={b}><span /><span /></span>
      ))}
    </div>
  );
}

function Cifra({ valor, texto, clase, dato }: { valor: string; texto: string; clase: string; dato: string }) {
  return (
    <div className={`fa-cifra ${clase}`} data-cifra={dato}>
      <span className="fa-cifra-valor">{valor}</span>
      <span className="fa-cifra-texto">{texto}</span>
    </div>
  );
}

function BloqueVacaciones({ f }: { f: FichaAnual }) {
  const v = f.vacaciones;
  const avisar = f.avisos.some((a) => a.codigo === 'VACACIONES_SIN_PLANIFICAR');
  return (
    <section className="fa-bloque fa-vacaciones" aria-labelledby="t-fa-vac" data-bloque="vacaciones">
      <div className="fa-bloque-cabecera">
        <h3 id="t-fa-vac">Vacaciones</h3>
        <span className="fa-derecho" data-derecho-vacaciones>
          <strong>{dias(v.derecho)}</strong> naturales
          {v.proporcional
            ? <span className="tenue" data-proporcional> · proporcional: {f.dias_en_alta} de {f.dias_anio} días en alta ({num(v.base)} × {f.dias_en_alta}/{f.dias_anio}, redondeo hacia arriba)</span>
            : <span className="tenue"> · {num(v.base)} al año, también media jornada (provisional)</span>}
        </span>
      </div>
      <ReglaVacaciones v={v} avisar={avisar} />
      <div className="fa-cifras">
        <Cifra valor={num(v.disfrutadas)} texto={`disfrutados hasta hoy`} clase="verde" dato="disfrutadas" />
        <Cifra valor={num(v.planificadas)} texto="planificados desde mañana" clase="azul" dato="planificadas" />
        {v.pendientes >= 0
          ? <Cifra valor={num(v.pendientes)} texto="sin planificar" clase={avisar ? 'naranja' : 'gris'} dato="pendientes" />
          : <Cifra valor={num(-v.pendientes)} texto="por encima del derecho" clase="rojo" dato="pendientes" />}
      </div>
      <div className="fa-extra">
        <label className="fa-extra-campo">Días extra del año
          <input type="text" disabled value="" placeholder={TEXTO_DIAS_EXTRA_PENDIENTE} aria-describedby="fa-extra-nota" data-dias-extra />
        </label>
        <span id="fa-extra-nota" className="tenue">Se podrán anotar cuando exista la tabla de ajustes anuales.</span>
      </div>
      {v.periodos.length > 0 && (
        <ul className="fa-periodos" data-periodos-vacaciones>
          {v.periodos.map((p) => (
            <li key={p.desde} data-periodo-vacaciones={p.desde}>{textoPeriodoCambio(p.desde, p.hasta)} · {p.parcial ? 'media franja, 0,5 días' : dias(p.dias)}</li>
          ))}
        </ul>
      )}
      <p className="fa-nota tenue">Cada periodo cuenta los días naturales del primer al último día laborable seguidos, fines de semana y festivos intermedios incluidos. Una franja suelta de jornada completa cuenta medio día.</p>
    </section>
  );
}

function BloqueLibre({ f }: { f: FichaAnual }) {
  const l = f.libre_disposicion;
  return (
    <section className="fa-bloque" aria-labelledby="t-fa-ld" data-bloque="libre">
      <h3 id="t-fa-ld">Libre disposición</h3>
      {l.derecho === null ? <p className="tenue">Sin convenio de {f.anio}.</p> : (
        <>
          <p className="fa-grande" data-libre-restantes><strong>{num(l.restantes as number)}</strong> <span>de {dias(l.derecho)} {(l.restantes as number) < 0 ? 'de más' : 'restantes'}</span></p>
          <p className="tenue" data-libre-usadas>Usados: {dias(l.usadas)}{l.derecho === 0 ? ` · el convenio de ${f.anio} no da días de libre disposición` : ''}</p>
        </>
      )}
    </section>
  );
}

function BloqueMedico({ f }: { f: FichaAnual }) {
  const m = f.permiso_medico;
  const pct = m.horas ? Math.min(m.usadas / m.horas, 1) * 100 : 0;
  return (
    <section className="fa-bloque" aria-labelledby="t-fa-pm" data-bloque="medico">
      <h3 id="t-fa-pm">Permiso médico</h3>
      {m.horas === null ? <p className="tenue">Sin convenio de {f.anio}.</p> : (
        <>
          <p className="fa-grande" data-medico-usadas><strong>{num(m.usadas)}</strong> <span>de {horas(m.horas)} usadas</span></p>
          <span className={`fa-medidor${(m.restantes as number) < 0 ? ' rojo' : ''}`} aria-hidden="true"><span style={{ width: `${pct}%` }} /></span>
        </>
      )}
    </section>
  );
}

function BloqueBaja({ f }: { f: FichaAnual }) {
  return (
    <section className="fa-bloque" aria-labelledby="t-fa-baja" data-bloque="baja">
      <h3 id="t-fa-baja">Días de baja</h3>
      <p className="fa-grande" data-dias-baja><strong>{num(f.dias_baja)}</strong> <span>{f.dias_baja === 1 ? 'día' : 'días'} en {f.anio}</span></p>
    </section>
  );
}

function BloqueHoras({ f }: { f: FichaAnual }) {
  const h = f.horas;
  if (!h.computa) {
    return (
      <section className="fa-bloque fa-horas" aria-labelledby="t-fa-h" data-bloque="horas" data-horas-titular>
        <h3 id="t-fa-h">Horas registradas en {f.anio}</h3>
        <p className="fa-grande"><strong>{num(h.registradas)}</strong> <span>h · {horas(h.confirmadas)} confirmadas, {horas(h.planificadas)} planificadas</span></p>
        <p className="tenue">El titular no computa en el convenio: sus horas se registran sin objetivo.</p>
      </section>
    );
  }
  if (h.objetivo === null) {
    return (
      <section className="fa-bloque fa-horas" aria-labelledby="t-fa-h" data-bloque="horas">
        <h3 id="t-fa-h">Horas del año</h3>
        <p className="tenue">Sin convenio de {f.anio}: no hay objetivo. Registradas: {horas(h.registradas)}.</p>
      </section>
    );
  }
  const obj = h.objetivo;
  const escala = Math.max(obj, h.registradas) || 1;
  const conf = Math.min(h.confirmadas, obj);
  const plan = Math.min(h.planificadas, obj - conf);
  const exceso = h.exceso ?? 0;
  const pend = h.pendientes ?? 0;
  const w = (x: number) => `${(x / escala) * 100}%`;
  return (
    <section className="fa-bloque fa-horas" aria-labelledby="t-fa-h" data-bloque="horas">
      <div className="fa-bloque-cabecera">
        <h3 id="t-fa-h">Horas del año</h3>
        <span className="fa-derecho" data-objetivo-anual>objetivo <strong>{horas(obj)}</strong>
          {h.proporcional && <span className="tenue"> · proporcional a {f.dias_en_alta} de {f.dias_anio} días en alta (año completo: {horas(h.objetivo_anual as number)})</span>}
        </span>
      </div>
      <div className="fa-barra-horas" role="img" aria-label={`${horas(h.confirmadas)} confirmadas y ${horas(h.planificadas)} planificadas de ${horas(obj)}`}>
        <span className="verde" style={{ width: w(conf) }} />
        <span className="azul" style={{ width: w(plan) }} />
        <span className="naranja" style={{ width: w(exceso) }} />
        <span className="pendiente" style={{ width: w(pend) }} />
        <span className="fa-marca-objetivo" style={{ left: w(obj) }} aria-hidden="true" />
      </div>
      <div className="fa-cifras">
        <Cifra valor={num(h.confirmadas)} texto="h confirmadas" clase="verde" dato="confirmadas" />
        <Cifra valor={num(h.planificadas)} texto="h planificadas" clase="azul" dato="planificadas-h" />
        {h.exceso !== null
          ? <Cifra valor={num(h.exceso)} texto="h de exceso" clase="naranja" dato="exceso" />
          : <Cifra valor={num(pend)} texto="h sin planificar" clase="gris" dato="pendientes-h" />}
      </div>
      {h.exceso !== null && (
        <p className="fa-exceso" data-exceso-horas>Exceso de {horas(h.exceso)} ≈ {dias(h.exceso_dias as number)} que podrían ser vacaciones <span className="tenue">(estimación: exceso / {horas(f.trabajadora.horas_diarias)} al día)</span></p>
      )}
      <p className="fa-nota tenue" data-festivos-pendientes>{TEXTO_FESTIVOS_PENDIENTES}. Suman jornada, asuntos propios, permisos retribuidos, permiso médico, baja y descanso compensatorio.</p>
    </section>
  );
}

function enlaceCalendario(f: FichaAnual, p: Periodo) {
  return `/trabajadores/calendario?farmacia=${f.trabajadora.farmacia}&fecha=${p.desde}&persona=${f.trabajadora.id}`;
}

function BloqueAusencias({ f }: { f: FichaAnual }) {
  return (
    <section className="fa-bloque" aria-labelledby="t-fa-aus" data-bloque="ausencias">
      <h3 id="t-fa-aus">Próximas ausencias</h3>
      {f.proximas_ausencias.length === 0 ? <p className="tenue" data-sin-ausencias>Ninguna planificada desde hoy en {f.anio}.</p> : (
        <ul className="fa-ausencias">
          {f.proximas_ausencias.map((p) => (
            <li key={`${p.tipo}|${p.desde}`} data-ausencia={p.tipo}>
              <span className="fa-tipo" style={{ background: COLOR_TIPO_EVENTO[p.tipo] }} aria-hidden="true">{CODIGO_TIPO_EVENTO[p.tipo]}</span>
              <Link to={enlaceCalendario(f, p)}>{TEXTO_TIPO_EVENTO[p.tipo]}</Link>
              <span className="tenue">{textoPeriodoCambio(p.desde, p.hasta)}{p.parcial ? ' · media franja' : ''}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Ficha anual de una persona (en el detalle), con selector de año. */
export function FichaAnualSeccion({ id }: { id: string }) {
  const [anio, setAnio, hoy] = useAnio();
  const { carga } = useApiRecargable<FichaAnualDTO>(`/api/rrhh/trabajadoras/${id}/anual?anio=${anio}&hoy=${hoy}`);
  return (
    <section className="tarjeta bloque fa-ficha" aria-labelledby="t-fa" data-ficha-anual={anio}>
      <div className="bloque-cabecera fa-cabecera">
        <h2 id="t-fa">Año {anio}</h2>
        <SelectorAnio valor={anio} onChange={setAnio} />
      </div>
      {carga.estado === 'cargando' && <p className="tenue">Calculando…</p>}
      {carga.estado === 'error' && <p className="rrhh-error" role="alert">No se ha podido calcular la ficha ({carga.mensaje}).</p>}
      {carga.estado === 'ok' && (carga.datos.ficha === null ? (
        <p className="tenue" data-ficha-sin-datos={carga.datos.motivo}>
          {carga.datos.motivo === 'ANULADA' ? 'Ficha anulada: no tiene ficha anual.' : `Sin días de alta en ${carga.datos.anio}.`}
        </p>
      ) : (
        <FichaAnualCuerpo f={carga.datos.ficha} />
      ))}
    </section>
  );
}

function FichaAnualCuerpo({ f }: { f: FichaAnual }) {
  return (
    <>
      <p className="fa-calculo tenue">Calculado a {fechaCorta(f.hoy)} · {f.dias_en_alta} de {f.dias_anio} días en alta en {f.anio}</p>
      <Avisos avisos={f.avisos} />
      <div className="fa-rejilla">
        <BloqueVacaciones f={f} />
        <BloqueHoras f={f} />
        <BloqueLibre f={f} />
        <BloqueMedico f={f} />
        <BloqueBaja f={f} />
        <BloqueAusencias f={f} />
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Resumen de plantilla (pestaña Fichas, encima del listado)
// ---------------------------------------------------------------------------

type Columna = 'nombre' | 'farmacia' | 'vacaciones' | 'libre' | 'horas' | 'baja' | 'avisos';
const COLUMNAS: { c: Columna; texto: string; numero?: boolean }[] = [
  { c: 'nombre', texto: 'Persona' }, { c: 'farmacia', texto: 'Farmacia' }, { c: 'vacaciones', texto: 'Vacaciones sin planificar', numero: true },
  { c: 'libre', texto: 'Libre disposición', numero: true }, { c: 'horas', texto: 'Horas: faltan o exceso', numero: true },
  { c: 'baja', texto: 'Días de baja', numero: true }, { c: 'avisos', texto: 'Avisos' },
];
/** Valor de orden de cada columna (horas: registradas − objetivo; positivo = exceso; sin objetivo, al final). */
function valorOrden(f: FichaAnual, c: Columna): number | string {
  switch (c) {
    case 'nombre': return f.trabajadora.nombre;
    case 'farmacia': return f.trabajadora.farmacia;
    case 'vacaciones': return f.vacaciones.pendientes;
    case 'libre': return f.libre_disposicion.restantes ?? Number.NEGATIVE_INFINITY;
    case 'horas': return f.horas.objetivo === null ? Number.NEGATIVE_INFINITY : f.horas.registradas - f.horas.objetivo;
    case 'baja': return f.dias_baja;
    case 'avisos': return f.avisos.length;
  }
}

function TextoHoras({ f }: { f: FichaAnual }) {
  const h = f.horas;
  if (!h.computa) return <span className="tenue" data-horas-resumen="titular">sin objetivo · {horas(h.registradas)}</span>;
  if (h.objetivo === null) return <span className="tenue" data-horas-resumen="sin-convenio">sin convenio</span>;
  if (h.exceso !== null) return <span className="fa-texto-naranja" data-horas-resumen="exceso">exceso {horas(h.exceso)} ≈ {dias(h.exceso_dias as number)}</span>;
  return <span data-horas-resumen="faltan">faltan {horas(h.pendientes as number)}</span>;
}
function TextoVacaciones({ f }: { f: FichaAnual }) {
  const p = f.vacaciones.pendientes;
  const avisar = f.avisos.some((a) => a.codigo === 'VACACIONES_SIN_PLANIFICAR');
  if (p < 0) return <span className="fa-texto-rojo">{dias(-p)} de más</span>;
  return <span className={avisar ? 'fa-texto-naranja' : undefined}>{num(p)} <span className="tenue">de {num(f.vacaciones.derecho)}</span></span>;
}
function TextoLibre({ f }: { f: FichaAnual }) {
  const l = f.libre_disposicion;
  if (l.derecho === null) return <span className="tenue">—</span>;
  return <span className={(l.restantes as number) < 0 ? 'fa-texto-rojo' : undefined}>{num(l.restantes as number)} <span className="tenue">de {num(l.derecho)}</span></span>;
}

export function ResumenPlantilla({ farmacia }: { farmacia: FiltroFarmacia }) {
  const [anio, setAnio, hoy] = useAnio();
  const { carga } = useApiRecargable<ResumenPlantillaDTO>(`/api/rrhh/fichas?farmacia=${farmacia}&anio=${anio}&hoy=${hoy}`);
  const [orden, setOrden] = useState<{ c: Columna; asc: boolean } | null>(null);
  const movil = useMedia(MOVIL);
  const filas = carga.estado === 'ok' ? carga.datos.filas : [];
  const ordenadas = useMemo(() => {
    if (!orden) return filas;
    return [...filas].sort((a, b) => {
      const [x, y] = [valorOrden(a, orden.c), valorOrden(b, orden.c)];
      const r = typeof x === 'string' ? x.localeCompare(y as string, 'es') : (x as number) - (y as number);
      return (orden.asc ? r : -r) || a.trabajadora.nombre.localeCompare(b.trabajadora.nombre, 'es');
    });
  }, [filas, orden]);
  const ordenar = (c: Columna) => setOrden((o) => (o?.c === c ? { c, asc: !o.asc } : { c, asc: c === 'nombre' || c === 'farmacia' }));
  const conAvisos = filas.filter((f) => f.avisos.some((a) => a.codigo !== 'SIN_CONVENIO')).length;

  return (
    <section className="tarjeta bloque fa-resumen" aria-labelledby="t-fa-resumen" data-resumen-plantilla={anio}>
      <div className="bloque-cabecera fa-cabecera">
        <h2 id="t-fa-resumen">Resumen de plantilla {anio}</h2>
        <SelectorAnio valor={anio} onChange={setAnio} />
      </div>
      {carga.estado === 'cargando' && <p className="tenue">Calculando…</p>}
      {carga.estado === 'error' && <p className="rrhh-error" role="alert">No se ha podido calcular el resumen ({carga.mensaje}).</p>}
      {carga.estado === 'ok' && (
        <>
          <p className="fa-calculo tenue" data-resumen-pie>
            {filas.length} {filas.length === 1 ? 'persona' : 'personas'} · {conAvisos} con avisos · calculado a {fechaCorta(carga.datos.hoy)} · vacaciones: {carga.datos.reglas.vacaciones_dias} días naturales (provisional) · festivos aún no descontados (TA3)
          </p>
          {filas.length === 0 ? <p className="tenue">Nadie de alta en {anio} en esta farmacia.</p> : movil ? (
            <>
              <label className="fa-ordenar-movil">Ordenar por
                <select value={orden ? `${orden.c}:${orden.asc ? 'asc' : 'desc'}` : ''} data-ordenar-movil
                  onChange={(e) => { const [c, s] = e.target.value.split(':'); setOrden(c ? { c: c as Columna, asc: s === 'asc' } : null); }}>
                  <option value="">Orden de las fichas</option>
                  <option value="vacaciones:desc">Más vacaciones sin planificar</option>
                  <option value="horas:desc">Más exceso de horas</option>
                  <option value="baja:desc">Más días de baja</option>
                  <option value="avisos:desc">Más avisos</option>
                  <option value="nombre:asc">Nombre</option>
                </select>
              </label>
              <ul className="fa-tarjetas">
                {ordenadas.map((f) => (
                  <li key={f.trabajadora.id} className="fa-tarjeta" data-fila-resumen={f.trabajadora.id}>
                    <div className="rrhh-tarjeta-cabecera">
                      <Link to={`/trabajadores/${f.trabajadora.id}${anio === anioPorDefecto(hoy) ? '' : `?anio=${anio}`}`} className="rrhh-nombre">{f.trabajadora.nombre}</Link>
                      <EtiquetaFarmacia f={f.trabajadora.farmacia} />
                    </div>
                    <dl className="fa-tarjeta-datos">
                      <div><dt>Vacaciones sin planificar</dt><dd data-col="vacaciones"><TextoVacaciones f={f} /></dd></div>
                      <div><dt>Libre disposición</dt><dd data-col="libre"><TextoLibre f={f} /></dd></div>
                      <div><dt>Horas</dt><dd data-col="horas"><TextoHoras f={f} /></dd></div>
                      <div><dt>Días de baja</dt><dd data-col="baja">{num(f.dias_baja)}</dd></div>
                    </dl>
                    <Avisos avisos={f.avisos} />
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <div className="fa-tabla-marco">
              <table className="tabla fa-tabla">
                <thead>
                  <tr>
                    {COLUMNAS.map(({ c, texto, numero }) => (
                      <th key={c} scope="col" className={numero ? 'num' : undefined}
                        aria-sort={orden?.c === c ? (orden.asc ? 'ascending' : 'descending') : 'none'}>
                        <button type="button" className="fa-ordenar" onClick={() => ordenar(c)} data-ordenar={c}>
                          {texto}<span className="fa-flecha" aria-hidden="true">{orden?.c === c ? (orden.asc ? '▲' : '▼') : '↕'}</span>
                        </button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ordenadas.map((f) => (
                    <tr key={f.trabajadora.id} data-fila-resumen={f.trabajadora.id}>
                      <td>
                        <Link to={`/trabajadores/${f.trabajadora.id}${anio === anioPorDefecto(hoy) ? '' : `?anio=${anio}`}`} className="rrhh-nombre">{f.trabajadora.nombre}</Link>
                        <span className="tenue fa-categoria">{TEXTO_CATEGORIA[f.trabajadora.categoria]}</span>
                      </td>
                      <td><EtiquetaFarmacia f={f.trabajadora.farmacia} /></td>
                      <td className="num" data-col="vacaciones"><TextoVacaciones f={f} /></td>
                      <td className="num" data-col="libre"><TextoLibre f={f} /></td>
                      <td className="num" data-col="horas"><TextoHoras f={f} /></td>
                      <td className="num" data-col="baja">{num(f.dias_baja)}</td>
                      <td data-col="avisos">{f.avisos.length === 0 ? <span className="tenue">—</span> : <Avisos avisos={f.avisos} />}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
