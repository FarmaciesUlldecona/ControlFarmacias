// TA4-2 Trabajadores: vista previa del relleno de guardias por rotación (dentro de la confirmación de «Rellenar año
// completo», vista Año). Lee las guardias del año anterior y todas las fichas (PIO y RITA, también con baja: el historial
// de personas lo necesita; la propuesta solo usa las de alta ese día). El plan lo calcula relleno_guardias.ts (puro);
// aquí solo se pinta: semanas, festivos y guardias festivas que se crearán, con farmacia y persona, y los avisos. Lo
// propuesto va en tono claro («planificado»): aún no existe.
import { useEffect, useState } from 'react';
import type { Trabajadora, TrabajadorasDTO } from '../server/rrhh/contrato.ts';
import { FECHA_MIN } from '../server/rrhh/eventos.ts';
import type { GuardiasRespuestaDTO } from '../server/rrhh/guardias.ts';
import type { PlanRelleno } from '../server/rrhh/relleno_guardias.ts';
import { obtener, type Carga } from './api.ts';
import { estiloGuardia, estiloGuardiaFestiva } from './guardias.tsx';

export interface DatosRelleno { previo: GuardiasRespuestaDTO | null; fichas: Trabajadora[] }

/** Datos del relleno (solo mientras la confirmación está abierta). El año anterior fuera del convenio: previo null. */
export function useDatosRelleno(activo: boolean, anio: number): Carga<DatosRelleno> | null {
  const [carga, setCarga] = useState<Carga<DatosRelleno> | null>(null);
  useEffect(() => {
    if (!activo) { setCarga(null); return; }
    const ac = new AbortController();
    setCarga({ estado: 'cargando' });
    const conPrevio = `${anio - 1}-01-01` >= FECHA_MIN;
    Promise.all([
      conPrevio ? obtener<GuardiasRespuestaDTO>(`/api/rrhh/guardias?anio=${anio - 1}`, ac.signal) : Promise.resolve(null),
      obtener<TrabajadorasDTO>('/api/rrhh/trabajadoras?farmacia=AMBAS&bajas=1', ac.signal),
    ]).then(([previo, t]) => setCarga({ estado: 'ok', datos: { previo, fichas: t.trabajadoras } }))
      .catch((e: unknown) => { if (!ac.signal.aborted) setCarga({ estado: 'error', mensaje: e instanceof Error ? e.message : 'error' }); });
    return () => ac.abort();
  }, [activo, anio]);
  return carga;
}

const dm = (f: string) => `${Number(f.slice(8))}/${Number(f.slice(5, 7))}`;
const quien = (farmacia: string, p: { nombre: string } | null, crear: boolean) =>
  (farmacia === 'OTRA' ? 'Otra farmacia' : p ? `${farmacia} · ${p.nombre}` : `${farmacia} · ${crear ? '—' : 'sin persona disponible'}`);

export function PreviaRelleno({ plan }: { plan: PlanRelleno }) {
  const semanas = plan.semanas;
  return (
    <div className="rl-previa" data-relleno-previa={plan.anio}>
      <p className="rl-resumen" data-relleno-resumen>{plan.texto}. Se crean como planificado (tono claro); no se toca nada de lo que ya existe.</p>
      {plan.avisos.length > 0 && (
        <ul className="rl-avisos" aria-label="Avisos del relleno">
          {plan.avisos.map((a, i) => <li key={i} data-relleno-aviso={a.tipo}>{a.texto}</li>)}
        </ul>
      )}
      <div className="rl-columnas">
        <section aria-label="Semanas">
          <h4>Semanas ({semanas.filter((s) => s.crear).length})</h4>
          {semanas.length === 0 ? <p className="tenue">Ninguna: todas las semanas ya tienen guardia.</p> : (
            <ol className="rl-lista">
              {semanas.map((s) => (
                <li key={s.lunes} className={s.crear ? 'planificado' : 'sin-crear'} data-relleno-semana={s.lunes} data-relleno-farmacia={s.farmacia}>
                  <span className="rl-fecha">{dm(s.lunes)}</span>
                  <span className="rl-marca" style={estiloGuardia(s.farmacia)}>{s.farmacia}</span>
                  <span>{s.farmacia === 'OTRA' ? 'Otra farmacia' : `G: ${s.guardia?.nombre ?? 'sin persona disponible'}${s.apoyo ? ` · A: ${s.apoyo.nombre}` : ''}`}</span>
                </li>
              ))}
            </ol>
          )}
        </section>
        <section aria-label="Festivos">
          <h4>Festivos nuevos ({plan.festivos.length})</h4>
          {plan.festivos.length === 0 ? <p className="tenue">Ninguno.</p> : (
            <ol className="rl-lista">
              {plan.festivos.map((f) => (
                <li key={f.fecha} className="planificado" data-relleno-festivo={f.fecha}>
                  <span className="rl-fecha">{dm(f.fecha)}</span> {f.nombre}
                  <span className="tenue"> ({f.pascua ? 'según la Pascua' : `como el ${dm(f.anterior)}`})</span>
                </li>
              ))}
            </ol>
          )}
          <h4>Guardias festivas ({plan.festivas.filter((f) => f.crear).length})</h4>
          {plan.festivas.length === 0 ? <p className="tenue">Ninguna: todos los festivos ya tienen guardia.</p> : (
            <ol className="rl-lista">
              {plan.festivas.map((f) => (
                <li key={f.fecha} className={f.crear ? 'planificado' : 'sin-crear'} data-relleno-festiva={f.fecha} data-relleno-farmacia={f.farmacia}>
                  <span className="rl-fecha">{dm(f.fecha)}</span>
                  <span className="rl-marca" style={estiloGuardiaFestiva(f.farmacia)}>{f.farmacia}</span>
                  <span>{f.nombre} → {quien(f.farmacia, f.persona, f.crear)}</span>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>
    </div>
  );
}
