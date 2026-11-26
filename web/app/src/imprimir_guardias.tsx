// TA4 Trabajadores: vista de impresión de las guardias de un año, en una sola hoja A4 vertical. El PDF lo genera el
// navegador (Imprimir → Guardar como PDF): sin dependencias nuevas. Respeta el filtro de farmacia del calendario
// (?farmacia=PIO|RITA; sin él, las dos) y los colores elegidos en «Cambiar colores» (mismo almacenamiento).
// Contenido: cabecera con fecha de impresión; 12 meses en rejilla 3×4 con la barra de la guardia semanal de cada semana
// (farmacia e iniciales de guardia y apoyo del sábado) y los días con guardia festiva marcados; lista de festivos del año
// con su guardia; leyenda de colores e iniciales. Legible en blanco y negro: la farmacia va también como texto.
// Solo lectura: lee /api/rrhh/guardias (las mismas tablas de la migración 34 que el calendario).
import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { esFecha, lunesDe, primeroDeMes, sumarDias, ultimoDeMes } from '../server/rrhh/eventos.ts';
import { TEXTO_FARMACIA_GUARDIA, type FarmaciaGuardia, type FestivoVista, type GuardiasRespuestaDTO, type PersonaGuardia, type SemanaGuardiaVista } from '../server/rrhh/guardias.ts';
import { useApi } from './api.ts';
import { estiloGuardia, estiloGuardiaFestiva, leerColoresGuardia, textoSobre, varsColoresGuardia } from './guardias.tsx';

const FARMACIAS: readonly FarmaciaGuardia[] = ['PIO', 'RITA', 'OTRA'];
const INICIALES_DIA = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
const MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
const dm = (f: string) => `${Number(f.slice(8))}/${Number(f.slice(5, 7))}`;
function hoyLocal(): string {
  const d = new Date();
  return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`;
}

/** Farmacia del filtro (PIO o RITA); cualquier otra cosa: las dos. */
export function filtroImpresion(v: string | null): 'PIO' | 'RITA' | null {
  return v === 'PIO' || v === 'RITA' ? v : null;
}
/** «Guardias 2027 · PIO y RITA» (según filtro). */
export function tituloImpresion(anio: string, filtro: 'PIO' | 'RITA' | null): string {
  return `Guardias ${anio} · ${filtro ?? 'PIO y RITA'}`;
}
/** Línea de la lista de festivos: «6/1 Reis → Farmacia RITA (Raquel Ferrer)», «→ Otra farmacia» o «→ sin asignar». */
export function lineaFestivo(f: FestivoVista): string {
  const g = f.guardia;
  const destino = g === null ? 'sin asignar' : g.farmacia === 'OTRA' ? 'Otra farmacia' : `Farmacia ${g.farmacia}${g.persona ? ` (${g.persona.nombre})` : ''}`;
  return `${dm(f.fecha)} ${f.nombre} → ${destino}`;
}
/** Texto de la barra semanal: «PIO · G: CR · A: MS»; «OTRA»; sin asignar «—». */
export function textoBarraImpresion(s: SemanaGuardiaVista): string {
  if (s.farmacia === null) return '—';
  if (s.farmacia === 'OTRA') return 'OTRA';
  return `${s.farmacia} · G: ${s.guardia?.iniciales ?? '—'}${s.apoyo ? ` · A: ${s.apoyo.iniciales}` : ''}`;
}

export function PaginaImprimirGuardias() {
  const [params] = useSearchParams();
  const pa = params.get('anio') ?? '';
  const anio = /^\d{4}$/.test(pa) && esFecha(`${pa}-01-01`) ? pa : String(new Date().getFullYear());
  const filtro = filtroImpresion(params.get('farmacia'));
  const carga = useApi<GuardiasRespuestaDTO>(`/api/rrhh/guardias?desde=${anio}-01-01&hasta=${anio}-12-31`);
  const colores = leerColoresGuardia();
  const titulo = tituloImpresion(anio, filtro);
  useEffect(() => { document.title = titulo; }, [titulo]);
  return (
    <div className="imp" style={varsColoresGuardia(colores)} data-impresion-guardias={anio} data-impresion-filtro={filtro ?? 'AMBAS'}>
      <div className="imp-barra no-imprimir">
        <button type="button" className="boton-primario" onClick={() => window.print()} data-imprimir>Imprimir / Guardar como PDF</button>
        <span className="tenue">Una hoja A4 vertical. En el diálogo de impresión, «Guardar como PDF» genera el PDF.</span>
      </div>
      {carga.estado === 'cargando' && <p className="tenue no-imprimir">Cargando guardias…</p>}
      {carga.estado === 'error' && <p className="rrhh-error no-imprimir" role="alert">No se han podido leer las guardias ({carga.mensaje}).</p>}
      {carga.estado === 'ok' && <Hoja anio={anio} filtro={filtro} datos={carga.datos} titulo={titulo} colores={colores} />}
    </div>
  );
}

function Hoja({ anio, filtro, datos, titulo, colores }: {
  anio: string; filtro: 'PIO' | 'RITA' | null; datos: GuardiasRespuestaDTO; titulo: string; colores: ReturnType<typeof leerColoresGuardia>;
}) {
  const semanas = new Map(datos.semanas.map((s) => [s.lunes, s]));
  const festivos = datos.festivos.filter((f) => f.fecha.startsWith(anio)).sort((a, b) => a.fecha.localeCompare(b.fecha));
  const porFecha = new Map(festivos.map((f) => [f.fecha, f]));
  /** Con filtro, la farmacia no filtrada va en gris neutro (con su nombre como texto). */
  const visible = (f: FarmaciaGuardia | null) => f !== null && f !== 'OTRA' && (filtro === null || f === filtro);
  // Iniciales → nombre completo de las personas que salen en la hoja.
  const personas = new Map<string, PersonaGuardia>();
  for (const s of datos.semanas) {
    if (!visible(s.farmacia)) continue;
    for (const p of [s.guardia, s.apoyo]) if (p) personas.set(p.id, p);
  }
  for (const f of festivos) if (f.guardia?.persona && visible(f.guardia.farmacia)) personas.set(f.guardia.persona.id, f.guardia.persona);
  const leyendaPersonas = [...personas.values()].sort((a, b) => a.farmacia.localeCompare(b.farmacia) || a.iniciales.localeCompare(b.iniciales));
  return (
    <section className="imp-hoja" aria-label={titulo} data-hoja-a4>
      <header className="imp-cabecera">
        <h1 data-imp-titulo>{titulo}</h1>
        <span className="imp-fecha" data-imp-fecha>Impreso el {hoyLocal()}</span>
      </header>
      <div className="imp-meses" data-imp-rejilla>
        {MESES.map((nombreMes, m) => {
          const primero = `${anio}-${String(m + 1).padStart(2, '0')}-01`;
          const ultimo = ultimoDeMes(primero);
          const lunes: string[] = [];
          for (let l = lunesDe(primeroDeMes(primero)); l <= ultimo; l = sumarDias(l, 7)) lunes.push(l);
          return (
            <section key={m} className="imp-mes" data-imp-mes={primero.slice(0, 7)}>
              <h2>{nombreMes}</h2>
              <div className="imp-dsem">{INICIALES_DIA.map((d) => <span key={d}>{d}</span>)}</div>
              {lunes.map((l) => {
                const s = semanas.get(l);
                const deOtra = s?.farmacia === 'OTRA';
                const color = s && s.farmacia !== null && (deOtra || visible(s.farmacia));
                return (
                  <div key={l} className="imp-semana">
                    <div className="imp-dias">
                      {[0, 1, 2, 3, 4, 5, 6].map((n) => {
                        const f = sumarDias(l, n);
                        if (f.slice(0, 7) !== primero.slice(0, 7)) return <span key={n} className="imp-dia fuera" />;
                        const fe = porFecha.get(f);
                        const conColor = fe?.guardia && (fe.guardia.farmacia === 'OTRA' || visible(fe.guardia.farmacia));
                        return (
                          <span key={n} className={`imp-dia${n >= 5 ? ' finde' : ''}${fe ? ' festivo' : ''}`} title={fe ? lineaFestivo(fe) : undefined}
                            style={conColor && fe?.guardia ? estiloGuardiaFestiva(fe.guardia.farmacia) : undefined}
                            {...(fe ? { 'data-imp-festivo': f, 'data-imp-festiva-farmacia': fe.guardia?.farmacia ?? '' } : {})}>
                            {Number(f.slice(8))}
                          </span>
                        );
                      })}
                    </div>
                    {s && s.farmacia !== null && (
                      <div className={`imp-barra-semana${color ? '' : ' neutra'}${deOtra ? ' otra' : ''}`} style={color ? estiloGuardia(s.farmacia) : undefined}
                        data-imp-semana={l} data-imp-farmacia={s.farmacia}>{textoBarraImpresion(s)}</div>
                    )}
                  </div>
                );
              })}
            </section>
          );
        })}
      </div>
      <section className="imp-festivos" aria-label={`Festivos de ${anio}`}>
        <h2>Festivos {anio}</h2>
        {festivos.length === 0 ? <p className="tenue">Sin festivos dados de alta.</p> : (
          <ol data-imp-festivos>
            {/* TA4-3: fondo tipo subrayador con el color de la guardia festiva de su farmacia (el elegido en «Cambiar
                colores»; texto blanco o negro por contraste). Sin guardia: sin fondo. Con filtro, como los días: la
                otra farmacia sin color (su nombre sigue como texto). */}
            {festivos.map((f) => {
              const g = f.guardia;
              const resaltar = g !== null && (g.farmacia === 'OTRA' || visible(g.farmacia));
              return (
                <li key={f.fecha} data-imp-festivo-linea={f.fecha}>
                  <span className={resaltar ? 'imp-resalte' : undefined} style={resaltar && g ? estiloGuardiaFestiva(g.farmacia) : undefined}
                    data-imp-resalte={resaltar && g ? g.farmacia : ''}>{lineaFestivo(f)}</span>
                </li>
              );
            })}
          </ol>
        )}
      </section>
      <footer className="imp-leyenda" aria-label="Leyenda">
        <div className="imp-leyenda-colores">
          {(['semanal', 'festiva'] as const).map((t) => (
            <span key={t} className="imp-leyenda-fila" data-imp-leyenda={t}>
              <strong>{t === 'semanal' ? 'Guardia semanal:' : 'Guardia festiva:'}</strong>
              {FARMACIAS.filter((f) => f === 'OTRA' || filtro === null || f === filtro).map((f) => (
                <span key={f} className="imp-muestra" style={{ background: colores[t][f], color: textoSobre(colores[t][f]) }} data-imp-muestra={`${t}|${f}`}>
                  {f === 'OTRA' ? 'OTRA' : f}
                </span>
              ))}
            </span>
          ))}
          <span className="imp-leyenda-fila tenue">G: guardia · A: apoyo del sábado · OTRA: {TEXTO_FARMACIA_GUARDIA.OTRA}</span>
        </div>
        {leyendaPersonas.length > 0 && (
          <p className="imp-leyenda-personas" data-imp-personas>
            {leyendaPersonas.map((p) => <span key={p.id}><strong>{p.iniciales}</strong> {p.nombre} ({p.farmacia})</span>)}
          </p>
        )}
      </footer>
    </section>
  );
}
