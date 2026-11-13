/**
 * TA1: adaptador RRHH_FIXTURES. Datos de ejemplo en memoria del servidor, con escritura (alta, edición, baja,
 * TA-REAL: anulación y convenio); cada cambio queda en el historial (quién, cuándo, antes/después). Todo se pierde
 * al reiniciar. Nunca toca la BD. Mismas reglas que las tablas reales (migración 31): alta obligatoria, baja no
 * anterior al alta, eventos solo dentro del alta, nombre único por farmacia entre las fichas sin anular.
 *
 * Solo sintaxis TypeScript borrable.
 */
import { randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  CONVENIO_ANUAL, accionActualizacion, camposAlta, computaConvenio, diferencias, objetivosAnuales, ordenFichas,
  type ConvenioAnual, type DatosTrabajadora, type EventoHistorial, type FarmaciaRrhh, type Festivo,
  type FiltroFarmacia, type GuardiaFarmacia, type Trabajadora, type TrabajadoraDetalleDTO, type TrabajadorasDTO,
} from './contrato.ts';
import {
  crearAlmacenEventos, type CalendarioDTO, type CambioCalendario, type ErrorCambio, type ErrorDeshacer, type EventoCalendario,
  type NotaProxima, type PeticionEventos, type ResultadoCambioDTO, type SemillaEventos,
} from './eventos.ts';

export const RUTA_SEMILLA = join(import.meta.dirname, '..', '..', '..', 'fixtures', 'rrhh', 'trabajadoras.json');
/** TA2: semanas de ejemplo del calendario (ausencias, jornada habitual y una semana confirmada). */
export const RUTA_SEMILLA_EVENTOS = join(import.meta.dirname, '..', '..', '..', 'fixtures', 'rrhh', 'eventos.json');
/** Instante fijo de la carga de ejemplo (las fichas de ejemplo no tienen fecha real). */
export const CARGA_EJEMPLO_AT = '2026-11-01T08:00:00.000Z';

export type SemillaTrabajadora = Pick<Trabajadora, 'id' | 'farmacia' | 'nombre' | 'categoria' | 'tipo_jornada' | 'horas_diarias' | 'fecha_alta'>;

type Quizas<T> = T | Promise<T>;
export type ResultadoEdicion = Trabajadora | 'BAJA_ANTES_DEL_ALTA' | 'NOMBRE_DUPLICADO' | null;
export type ResultadoBaja = Trabajadora | 'YA_DE_BAJA' | 'BAJA_ANTES_DEL_ALTA' | null;
export type ResultadoAnulacion = Trabajadora | 'YA_ANULADA' | null;

/** Interfaz común del módulo: RRHH_FIXTURES (síncrono, en memoria) y RRHH_REAL (tablas reales, asíncrono). */
export interface AdaptadorRrhh {
  /** TA-REAL: false en REAL hasta que exista eventos_calendario.anulado. */
  readonly anularEventos: boolean;
  trabajadoras(farmacia: FiltroFarmacia, incluirBajas: boolean): Quizas<TrabajadorasDTO>;
  trabajadora(id: string): Quizas<TrabajadoraDetalleDTO | null>;
  convenio(): Quizas<ConvenioAnual[]>;
  /** Crea los años firmados que falten (los que ya existen no se tocan). Devuelve los creados. */
  crearConvenio(anios: number[], quien: string): Quizas<ConvenioAnual[]>;
  historial(farmacia: FiltroFarmacia): Quizas<EventoHistorial[]>;
  crear(datos: DatosTrabajadora, quien: string): Quizas<Trabajadora | 'NOMBRE_DUPLICADO'>;
  editar(id: string, datos: DatosTrabajadora, quien: string): Quizas<ResultadoEdicion>;
  darDeBaja(id: string, fecha: string, quien: string): Quizas<ResultadoBaja>;
  anular(id: string, quien: string): Quizas<ResultadoAnulacion>;
  // TA2: calendario (eventos con traza y deshacer).
  calendario(farmacia: FiltroFarmacia, desde: string, hasta: string): Quizas<CalendarioDTO>;
  notasProximas(farmacia: FiltroFarmacia, desde: string): Quizas<NotaProxima[]>;
  cambiarEventos(p: PeticionEventos, quien: string): Quizas<ResultadoCambioDTO | ErrorCambio>;
  deshacerEventos(cambioId: string, quien: string): Quizas<ResultadoCambioDTO | ErrorDeshacer>;
  historialEventos(farmacia: FiltroFarmacia): Quizas<CambioCalendario[]>;
  // TA3: interfaz preparada.
  guardias(farmacia: FiltroFarmacia): Quizas<GuardiaFarmacia[]>;
  festivos(farmacia: FiltroFarmacia): Quizas<Festivo[]>;
  cerrar?(): Promise<void>;
}

/** RRHH_FIXTURES: todo síncrono, y además todos los eventos (pruebas y check_fixtures). */
export interface AdaptadorRrhhFixtures extends AdaptadorRrhh {
  trabajadoras(farmacia: FiltroFarmacia, incluirBajas: boolean): TrabajadorasDTO;
  trabajadora(id: string): TrabajadoraDetalleDTO | null;
  convenio(): ConvenioAnual[];
  crearConvenio(anios: number[], quien: string): ConvenioAnual[];
  historial(farmacia: FiltroFarmacia): EventoHistorial[];
  crear(datos: DatosTrabajadora, quien: string): Trabajadora | 'NOMBRE_DUPLICADO';
  editar(id: string, datos: DatosTrabajadora, quien: string): ResultadoEdicion;
  darDeBaja(id: string, fecha: string, quien: string): ResultadoBaja;
  anular(id: string, quien: string): ResultadoAnulacion;
  calendario(farmacia: FiltroFarmacia, desde: string, hasta: string): CalendarioDTO;
  notasProximas(farmacia: FiltroFarmacia, desde: string): NotaProxima[];
  cambiarEventos(p: PeticionEventos, quien: string): ResultadoCambioDTO | ErrorCambio;
  deshacerEventos(cambioId: string, quien: string): ResultadoCambioDTO | ErrorDeshacer;
  historialEventos(farmacia: FiltroFarmacia): CambioCalendario[];
  guardias(farmacia: FiltroFarmacia): GuardiaFarmacia[];
  festivos(farmacia: FiltroFarmacia): Festivo[];
  eventos(): EventoCalendario[];
}

export function leerSemilla(ruta: string = RUTA_SEMILLA): SemillaTrabajadora[] {
  return (JSON.parse(readFileSync(ruta, 'utf8')) as { trabajadoras: SemillaTrabajadora[] }).trabajadoras;
}

export function leerSemillaEventos(ruta: string = RUTA_SEMILLA_EVENTOS): SemillaEventos {
  const { ausencias, jornada_habitual, confirmado } = JSON.parse(readFileSync(ruta, 'utf8')) as SemillaEventos;
  return { ausencias, jornada_habitual, confirmado };
}

const enFiltro = (f: FiltroFarmacia, farmacia: FarmaciaRrhh | null) => f === 'AMBAS' || farmacia === null || farmacia === f;
/**
 * El historial solo crece (append): el orden de registro es el orden real. Más reciente primero sin ordenar por
 * `cuando`, que puede repetirse dentro del mismo milisegundo.
 */
const masRecientePrimero = (hs: EventoHistorial[]) => [...hs].reverse();
/** activa (derivado): sin anular y sin fecha de baja. */
const conActiva = (t: Trabajadora): Trabajadora => ({ ...t, activa: !t.anulada && t.fecha_baja === null });

/** `ahora` y `nuevoId` inyectables para pruebas; `convenio` permite empezar sin años (prueba del botón de crear). */
export function crearAdaptadorRrhhFixtures(opciones: {
  semilla?: SemillaTrabajadora[]; semillaEventos?: SemillaEventos | null; ahora?: () => string; nuevoId?: () => string; anioReferencia?: number;
  convenio?: readonly ConvenioAnual[]; anularEventos?: boolean;
} = {}): AdaptadorRrhhFixtures {
  const ahora = opciones.ahora ?? (() => new Date().toISOString());
  const nuevoId = opciones.nuevoId ?? randomUUID;
  const anioReferencia = opciones.anioReferencia ?? Number(ahora().slice(0, 4));
  const anularEventos = opciones.anularEventos ?? true;
  let convenio: ConvenioAnual[] = (opciones.convenio ?? CONVENIO_ANUAL).map((c) => ({ ...c }));
  const fichas = new Map<string, Trabajadora>();
  for (const s of opciones.semilla ?? leerSemilla()) {
    fichas.set(s.id, conActiva({
      ...s, computa_convenio: computaConvenio(s.categoria), fecha_baja: null, anulada: false,
      created_at: CARGA_EJEMPLO_AT, updated_at: CARGA_EJEMPLO_AT, activa: true,
    }));
  }
  const historial: EventoHistorial[] = [];
  const registrar = (t: Trabajadora, accion: EventoHistorial['accion'], quien: string, antes: Partial<Trabajadora> | null, despues: Partial<Trabajadora> | null) => {
    historial.push({ id: nuevoId(), farmacia: t.farmacia, entidad: 'trabajadora', entidad_id: t.id, accion, quien, cuando: ahora(), antes, despues });
  };
  const copia = (t: Trabajadora): Trabajadora => ({ ...t });
  /** Índice único de la tabla: (farmacia, lower(nombre)) entre las fichas sin anular. */
  const nombreOcupado = (farmacia: FarmaciaRrhh, nombre: string, salvo: string | null) =>
    [...fichas.values()].some((t) => !t.anulada && t.id !== salvo && t.farmacia === farmacia && t.nombre.toLowerCase() === nombre.toLowerCase());
  // TA2: calendario sobre las mismas fichas (siempre las vigentes: altas, ediciones, bajas y anulaciones cuentan al momento).
  const almacen = crearAlmacenEventos({ fichas: () => [...fichas.values()], ahora, nuevoId, anularEventos });
  const semillaEventos = opciones.semillaEventos === undefined ? leerSemillaEventos() : opciones.semillaEventos;
  if (semillaEventos) almacen.cargarEjemplo(semillaEventos, CARGA_EJEMPLO_AT);
  /** Actualiza la ficha y registra el historial (anulación, baja o edición). */
  const actualizar = (previo: Trabajadora, nuevo: Trabajadora, quien: string): Trabajadora => {
    const n = conActiva({ ...nuevo, updated_at: ahora() });
    fichas.set(n.id, n);
    const d = diferencias(previo, n);
    registrar(n, accionActualizacion(previo, n), quien, d.antes, d.despues);
    return copia(n);
  };

  return {
    anularEventos,
    trabajadoras(farmacia, incluirBajas) {
      const ts = [...fichas.values()].filter((t) => enFiltro(farmacia, t.farmacia) && (incluirBajas || t.activa)).sort(ordenFichas).map(copia);
      return { farmacia, trabajadoras: ts, convenio: convenio.map((c) => ({ ...c })), anio_referencia: anioReferencia };
    },
    trabajadora(id) {
      const t = fichas.get(id);
      if (!t) return null;
      return {
        trabajadora: copia(t),
        objetivos: objetivosAnuales(t, convenio),
        historial: masRecientePrimero(historial.filter((h) => h.entidad_id === id)),
      };
    },
    convenio: () => convenio.map((c) => ({ ...c })),
    crearConvenio(anios) {
      const nuevos = CONVENIO_ANUAL.filter((c) => anios.includes(c.anio) && !convenio.some((x) => x.anio === c.anio)).map((c) => ({ ...c }));
      convenio = [...convenio, ...nuevos].sort((a, b) => a.anio - b.anio);
      return nuevos;
    },
    historial: (farmacia) => masRecientePrimero(historial.filter((h) => enFiltro(farmacia, h.farmacia))),
    crear(datos, quien) {
      if (!datos.farmacia) throw new Error('FARMACIA_OBLIGATORIA');
      if (nombreOcupado(datos.farmacia, datos.nombre, null)) return 'NOMBRE_DUPLICADO';
      const t: Trabajadora = conActiva({
        id: nuevoId(), farmacia: datos.farmacia, nombre: datos.nombre, categoria: datos.categoria, tipo_jornada: datos.tipo_jornada,
        horas_diarias: datos.horas_diarias, computa_convenio: computaConvenio(datos.categoria), fecha_alta: datos.fecha_alta,
        fecha_baja: null, anulada: false, created_at: ahora(), updated_at: ahora(), activa: true,
      });
      fichas.set(t.id, t);
      registrar(t, 'ALTA', quien, null, camposAlta(t));
      return copia(t);
    },
    editar(id, datos, quien) {
      const previo = fichas.get(id);
      if (!previo || previo.anulada) return null;
      if (previo.fecha_baja !== null && previo.fecha_baja < datos.fecha_alta) return 'BAJA_ANTES_DEL_ALTA';
      if (nombreOcupado(previo.farmacia, datos.nombre, id)) return 'NOMBRE_DUPLICADO';
      const nuevo: Trabajadora = {
        ...previo, nombre: datos.nombre, categoria: datos.categoria, tipo_jornada: datos.tipo_jornada,
        horas_diarias: datos.horas_diarias, computa_convenio: computaConvenio(datos.categoria), fecha_alta: datos.fecha_alta,
      };
      if (Object.keys(diferencias(previo, nuevo).despues).length === 0) return copia(previo); // sin cambios: no se registra nada
      return actualizar(previo, nuevo, quien);
    },
    darDeBaja(id, fecha, quien) {
      const previo = fichas.get(id);
      if (!previo || previo.anulada) return null;
      if (previo.fecha_baja !== null) return 'YA_DE_BAJA';
      if (fecha < previo.fecha_alta) return 'BAJA_ANTES_DEL_ALTA';
      return actualizar(previo, { ...previo, fecha_baja: fecha }, quien);
    },
    anular(id, quien) {
      const previo = fichas.get(id);
      if (!previo) return null;
      if (previo.anulada) return 'YA_ANULADA';
      return actualizar(previo, { ...previo, anulada: true }, quien);
    },
    calendario: (farmacia, desde, hasta) => almacen.calendario(farmacia, desde, hasta),
    notasProximas: (farmacia, desde) => almacen.notasProximas(farmacia, desde),
    cambiarEventos: (p, quien) => almacen.aplicar(p, quien),
    deshacerEventos: (id, quien) => almacen.deshacer(id, quien),
    historialEventos: (farmacia) => almacen.historial(farmacia),
    eventos: () => almacen.todos(),
    guardias: () => [],
    festivos: () => [],
  };
}
