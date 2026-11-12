/**
 * TA1: adaptador RRHH_FIXTURES. Datos de ejemplo en memoria del servidor, con escritura (alta, edición, baja); cada
 * cambio queda en el historial (quién, cuándo, antes/después). Todo se pierde al reiniciar. Nunca toca la BD.
 *
 * Solo sintaxis TypeScript borrable.
 */
import { randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  CONVENIO_ANUAL, diferencias, objetivosAnuales,
  type ConvenioAnual, type DatosTrabajadora, type EventoCalendario, type EventoHistorial, type FarmaciaRrhh, type Festivo,
  type FiltroFarmacia, type GuardiaFarmacia, type Trabajadora, type TrabajadoraDetalleDTO, type TrabajadorasDTO,
} from './contrato.ts';

export const RUTA_SEMILLA = join(import.meta.dirname, '..', '..', '..', 'fixtures', 'rrhh', 'trabajadoras.json');
/** Instante fijo de la carga de ejemplo (las fichas de ejemplo no tienen fecha real). */
export const CARGA_EJEMPLO_AT = '2026-11-01T08:00:00.000Z';

export type SemillaTrabajadora = Omit<Trabajadora, 'computa_convenio' | 'activa' | 'fecha_baja' | 'creado_at' | 'actualizado_at'>;

/** Interfaz común del módulo (FIXTURES ahora; T1: tablas reales). */
export interface AdaptadorRrhh {
  trabajadoras(farmacia: FiltroFarmacia, incluirBajas: boolean): TrabajadorasDTO;
  trabajadora(id: string): TrabajadoraDetalleDTO | null;
  convenio(): ConvenioAnual[];
  historial(farmacia: FiltroFarmacia): EventoHistorial[];
  crear(datos: DatosTrabajadora, quien: string): Trabajadora;
  editar(id: string, datos: DatosTrabajadora, quien: string): Trabajadora | null;
  darDeBaja(id: string, fecha: string, quien: string): Trabajadora | 'YA_DE_BAJA' | null;
  // TA2–TA3: interfaz preparada; sin datos en TA1.
  eventos(farmacia: FiltroFarmacia): EventoCalendario[];
  guardias(farmacia: FiltroFarmacia): GuardiaFarmacia[];
  festivos(farmacia: FiltroFarmacia): Festivo[];
}

export function leerSemilla(ruta: string = RUTA_SEMILLA): SemillaTrabajadora[] {
  return (JSON.parse(readFileSync(ruta, 'utf8')) as { trabajadoras: SemillaTrabajadora[] }).trabajadoras;
}

const enFiltro = (f: FiltroFarmacia, farmacia: FarmaciaRrhh | null) => f === 'AMBAS' || farmacia === null || farmacia === f;
/**
 * El historial solo crece (append): el orden de registro es el orden real. Más reciente primero sin ordenar por
 * `cuando`, que puede repetirse dentro del mismo milisegundo.
 */
const masRecientePrimero = (hs: EventoHistorial[]) => [...hs].reverse();
const ordenNombre = (a: Trabajadora, b: Trabajadora) => a.farmacia.localeCompare(b.farmacia) || Number(a.es_titular) - Number(b.es_titular)
  || a.nombre.localeCompare(b.nombre, 'es');

/** `ahora` y `nuevoId` inyectables para pruebas. */
export function crearAdaptadorRrhhFixtures(opciones: {
  semilla?: SemillaTrabajadora[]; ahora?: () => string; nuevoId?: () => string; anioReferencia?: number;
} = {}): AdaptadorRrhh {
  const ahora = opciones.ahora ?? (() => new Date().toISOString());
  const nuevoId = opciones.nuevoId ?? randomUUID;
  const anioReferencia = opciones.anioReferencia ?? Number(ahora().slice(0, 4));
  const fichas = new Map<string, Trabajadora>();
  for (const s of opciones.semilla ?? leerSemilla()) {
    fichas.set(s.id, { ...s, computa_convenio: !s.es_titular, activa: true, fecha_baja: null, creado_at: CARGA_EJEMPLO_AT, actualizado_at: CARGA_EJEMPLO_AT });
  }
  const historial: EventoHistorial[] = [];
  const registrar = (t: Trabajadora, accion: EventoHistorial['accion'], quien: string, antes: Partial<Trabajadora> | null, despues: Partial<Trabajadora> | null) => {
    historial.push({ id: nuevoId(), farmacia: t.farmacia, entidad: 'trabajadora', entidad_id: t.id, accion, quien, cuando: ahora(), antes, despues });
  };
  const copia = (t: Trabajadora): Trabajadora => ({ ...t });

  return {
    trabajadoras(farmacia, incluirBajas) {
      const ts = [...fichas.values()].filter((t) => enFiltro(farmacia, t.farmacia) && (incluirBajas || t.activa)).sort(ordenNombre).map(copia);
      return { farmacia, trabajadoras: ts, convenio: [...CONVENIO_ANUAL], anio_referencia: anioReferencia };
    },
    trabajadora(id) {
      const t = fichas.get(id);
      if (!t) return null;
      return {
        trabajadora: copia(t),
        objetivos: objetivosAnuales(t),
        historial: masRecientePrimero(historial.filter((h) => h.entidad_id === id)),
      };
    },
    convenio: () => [...CONVENIO_ANUAL],
    historial: (farmacia) => masRecientePrimero(historial.filter((h) => enFiltro(farmacia, h.farmacia))),
    crear(datos, quien) {
      if (!datos.farmacia) throw new Error('FARMACIA_OBLIGATORIA');
      const t: Trabajadora = {
        id: nuevoId(), farmacia: datos.farmacia, nombre: datos.nombre, categoria: datos.categoria, jornada: datos.jornada,
        horas_diarias: datos.horas_diarias, es_titular: datos.es_titular, computa_convenio: !datos.es_titular,
        activa: true, fecha_baja: null, creado_at: ahora(), actualizado_at: ahora(),
      };
      fichas.set(t.id, t);
      registrar(t, 'ALTA', quien, null, {
        farmacia: t.farmacia, nombre: t.nombre, categoria: t.categoria, jornada: t.jornada, horas_diarias: t.horas_diarias,
        es_titular: t.es_titular, computa_convenio: t.computa_convenio, activa: t.activa,
      });
      return copia(t);
    },
    editar(id, datos, quien) {
      const previo = fichas.get(id);
      if (!previo) return null;
      const nuevo: Trabajadora = {
        ...previo, nombre: datos.nombre, categoria: datos.categoria, jornada: datos.jornada,
        horas_diarias: datos.horas_diarias, es_titular: datos.es_titular, computa_convenio: !datos.es_titular,
      };
      const d = diferencias(previo, nuevo);
      if (Object.keys(d.despues).length === 0) return copia(previo); // sin cambios: no se registra nada
      nuevo.actualizado_at = ahora();
      fichas.set(id, nuevo);
      registrar(nuevo, 'EDICION', quien, d.antes, d.despues);
      return copia(nuevo);
    },
    darDeBaja(id, fecha, quien) {
      const previo = fichas.get(id);
      if (!previo) return null;
      if (!previo.activa) return 'YA_DE_BAJA';
      const nuevo: Trabajadora = { ...previo, activa: false, fecha_baja: fecha, actualizado_at: ahora() };
      fichas.set(id, nuevo);
      const d = diferencias(previo, nuevo);
      registrar(nuevo, 'BAJA', quien, d.antes, d.despues);
      return copia(nuevo);
    },
    eventos: () => [],
    guardias: () => [],
    festivos: () => [],
  };
}
