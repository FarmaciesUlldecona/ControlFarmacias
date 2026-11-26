/**
 * H7-AP1: almacén de los apuntes manuales de Cashflow que usan las rutas, igual en los dos modos.
 *
 *  - FIXTURES: almacén en memoria con la semilla web/fixtures/cashflow/apuntes.json (como el de pagos). Simula los
 *    triggers de la migración 40 con los mismos códigos (apuntes.ts, errores_bd.ts): autor, farmacia, fechas de alta y
 *    anulación, «solo anular», motivo obligatorio, una sustitución por vencimiento.
 *  - REAL: server/cashflow/adaptador_real.ts (escritura con cf_cashflow_web; la lectura la hace cf_lectura junto con el
 *    cashflow).
 *
 * Toda operación que no se puede hacer LANZA ErrorCashflowBd (código y mensaje llano). Nunca se borra ni se reintenta.
 *
 * Solo sintaxis TypeScript borrable.
 */
import {
  calcularOcurrencias, comprobarAlta, comprobarAnular, comprobarAnularOcurrencia, conceptoDeAlta, ventanaOcurrencias,
  type AltaApunte, type ApunteCashflow, type ConceptoCashflow, type ContextoCashflow, type PrevisionesCashflow, type RecurrenteCashflow, type TablaAnulable,
} from './apuntes.ts';
import { MENSAJE_FALTA_CREDENCIAL_CASHFLOW, errorCashflow } from './errores_bd.ts';
import type { CuentaCashflow } from './cashflow.ts';

export interface ResultadoAlta {
  concepto: ConceptoCashflow | null;
  apunte: ApunteCashflow | null;
  recurrente: RecurrenteCashflow | null;
}
export interface Sustitucion { factura_id: string; vencimiento_orden: number }

export interface AlmacenCashflowAsync {
  /** null si se puede escribir; si no, por qué (REAL sin la credencial de Cashflow). */
  sinEscritura: { codigo: 'CREDENCIAL_CASHFLOW_AUSENTE'; mensaje: string } | null;
  /** FIXTURES: lo guardado en memoria. REAL: no existe (lo lee cf_lectura con el cashflow, en la misma transacción). */
  previsiones?: (hoy: string) => Promise<PrevisionesCashflow>;
  /** Alta de un apunte suelto o un recurrente (con su concepto nuevo, si lo hay), en una transacción. */
  alta(a: AltaApunte, autor: string): Promise<ResultadoAlta>;
  /** Editar = anular (con motivo) + dar de alta, en la misma transacción. */
  editar(anterior: { tabla: TablaAnulable; id: string }, motivo: string, a: AltaApunte, autor: string): Promise<ResultadoAlta & { anulado: ApunteCashflow | RecurrenteCashflow }>;
  anular(tabla: TablaAnulable, id: string, motivo: string, autor: string): Promise<ApunteCashflow | RecurrenteCashflow>;
  /** Alta de la anulación de una ocurrencia (el motivo va en la nota); con la sustitución, si la confirma Marc. */
  anularOcurrencia(recurrenteId: string, fecha: string, motivo: string, autor: string, sustitucion: Sustitucion | null): Promise<ApunteCashflow>;
  /** Anula un apunte suelto guardando el vencimiento que lo sustituye. */
  sustituirApunte(apunteId: string, motivo: string, sustitucion: Sustitucion, autor: string): Promise<ApunteCashflow>;
  cerrar?(): Promise<void>;
}

/** Semilla de FIXTURES (filas con la forma de la migración 40; las ocurrencias se calculan). */
export interface SemillaApuntes {
  hoy: string;
  conceptos: ConceptoCashflow[];
  recurrentes: RecurrenteCashflow[];
  apuntes: ApunteCashflow[];
}

/** REAL sin la credencial de Cashflow: la lectura sigue; cualquier escritura, 503. */
export function almacenSinEscritura(): AlmacenCashflowAsync {
  const no = async (): Promise<never> => { throw errorCashflow('CREDENCIAL_CASHFLOW_AUSENTE'); };
  return {
    sinEscritura: { codigo: 'CREDENCIAL_CASHFLOW_AUSENTE', mensaje: MENSAJE_FALTA_CREDENCIAL_CASHFLOW },
    alta: no, editar: no, anular: no, anularOcurrencia: no, sustituirApunte: no,
  };
}

const copia = <T>(x: T): T => structuredClone(x);

/**
 * FIXTURES: almacén en memoria. `datos`: lo importado (la semilla de cashflow.json), para la plantilla y las fechas
 * futuras, como las triggers de la BD.
 */
export function crearAlmacenCashflowFixtures(semilla: SemillaApuntes, datos: () => ContextoCashflow['datos']): AlmacenCashflowAsync {
  let conceptos = copia(semilla.conceptos);
  let recurrentes = copia(semilla.recurrentes);
  let apuntes = copia(semilla.apuntes);
  let n = 0;
  const nuevoId = () => { n += 1; return `a7a00000-0000-4000-8000-${String(n).padStart(12, '0')}`; };
  // Alta en la fecha de referencia de la semilla (capturas estables), un segundo más por cada fila.
  const ahora = () => new Date(Date.parse(`${semilla.hoy}T09:00:00.000Z`) + n * 1000).toISOString();
  const previsiones = (hoy: string = semilla.hoy): PrevisionesCashflow => {
    const ventana = ventanaOcurrencias(hoy);
    return { conceptos: copia(conceptos), recurrentes: copia(recurrentes), apuntes: copia(apuntes), ocurrencias: calcularOcurrencias({ recurrentes, apuntes }, ventana.desde, ventana.hasta), ventana };
  };
  const ctx = (): ContextoCashflow => ({ datos: datos(), previsiones: previsiones() });
  /** Una «transacción»: si algo falla, todo vuelve como estaba. */
  const transaccion = <T>(autor: string, trabajo: () => T): T => {
    if (autor.trim() === '' || autor.length > 60) throw errorCashflow('AUTOR_AUSENTE');
    const antes = { conceptos: copia(conceptos), recurrentes: copia(recurrentes), apuntes: copia(apuntes), n };
    try { return trabajo(); } catch (e) {
      ({ conceptos, recurrentes, apuntes, n } = antes);
      throw e;
    }
  };
  const comunes = (cuenta: CuentaCashflow, categoria: string, autor: string) => ({
    id: nuevoId(), cuenta, farmacia: cuenta, categoria, autor, creado_at: ahora(), anulado: false, anulado_por: null, anulado_at: null, motivo_anulacion: null,
  });
  const motivoValido = (m: string) => { const t = m.trim(); if (t === '') throw errorCashflow('MOTIVO_ANULACION_AUSENTE'); return t; };

  const darDeAlta = (a: AltaApunte, autor: string): ResultadoAlta => {
    const fallo = comprobarAlta(a, ctx());
    if (fallo) throw errorCashflow(fallo.codigo);
    const cuenta = a.cuenta as CuentaCashflow;
    let concepto: ConceptoCashflow | null = null;
    if (a.concepto_nuevo !== null) {
      concepto = { ...comunes(cuenta, a.categoria, autor), nombre: a.concepto_nuevo.nombre, proveedor_cif: a.concepto_nuevo.proveedor_cif };
      conceptos.push(concepto);
    }
    const nombre = conceptoDeAlta(a);
    if (a.tipo === 'SUELTO') {
      const apunte: ApunteCashflow = {
        ...comunes(cuenta, a.categoria, autor), fecha: a.fecha as string, concepto: nombre, importe: a.importe, nota: a.nota,
        recurrente_id: null, fecha_ocurrencia: null, sustituido_factura_id: null, sustituido_vencimiento_orden: null,
      };
      apuntes.push(apunte);
      return { concepto, apunte: copia(apunte), recurrente: null };
    }
    const recurrente: RecurrenteCashflow = {
      ...comunes(cuenta, a.categoria, autor), concepto: nombre, importe: a.importe as number, nota: a.nota,
      frecuencia: a.frecuencia as RecurrenteCashflow['frecuencia'], dia: a.dia as number, inicio: a.inicio as string, fin: a.fin,
    };
    recurrentes.push(recurrente);
    return { concepto, apunte: null, recurrente: copia(recurrente) };
  };
  const anularFila = (tabla: TablaAnulable, id: string, motivo: string, autor: string, sustitucion: { factura_id: string; vencimiento_orden: number } | null = null) => {
    const m = motivoValido(motivo);
    const fallo = comprobarAnular(tabla, id, previsiones());
    if (fallo) throw errorCashflow(fallo.codigo);
    const fila = tabla === 'APUNTE' ? apuntes.find((x) => x.id === id) as ApunteCashflow : recurrentes.find((x) => x.id === id) as RecurrenteCashflow;
    if (sustitucion !== null && tabla === 'APUNTE') {
      // Un vencimiento sustituye a un solo apunte (en la BD, índice único: 23505).
      if (apuntes.some((x) => x.sustituido_factura_id === sustitucion.factura_id && x.sustituido_vencimiento_orden === sustitucion.vencimiento_orden)) throw errorCashflow('DUPLICADO');
      Object.assign(fila, { sustituido_factura_id: sustitucion.factura_id, sustituido_vencimiento_orden: sustitucion.vencimiento_orden });
    }
    Object.assign(fila, { anulado: true, anulado_por: autor, anulado_at: ahora(), motivo_anulacion: m });
    return copia(fila);
  };

  return {
    sinEscritura: null,
    previsiones: async (hoy) => previsiones(hoy),
    alta: async (a, autor) => transaccion(autor, () => darDeAlta(a, autor)),
    editar: async (anterior, motivo, a, autor) => transaccion(autor, () => {
      const anulado = anularFila(anterior.tabla, anterior.id, motivo, autor);
      return { ...darDeAlta(a, autor), anulado };
    }),
    anular: async (tabla, id, motivo, autor) => transaccion(autor, () => anularFila(tabla, id, motivo, autor)),
    anularOcurrencia: async (recurrenteId, fecha, motivo, autor, sustitucion) => transaccion(autor, () => {
      const nota = motivoValido(motivo);
      const fallo = comprobarAnularOcurrencia(recurrenteId, fecha, ctx());
      if (fallo) throw errorCashflow(fallo.codigo);
      if (sustitucion !== null && apuntes.some((x) => x.sustituido_factura_id === sustitucion.factura_id && x.sustituido_vencimiento_orden === sustitucion.vencimiento_orden)) throw errorCashflow('DUPLICADO');
      const r = recurrentes.find((x) => x.id === recurrenteId) as RecurrenteCashflow;
      // Como el trigger: cuenta, categoría y concepto del recurrente; fecha = fecha de la ocurrencia; sin importe.
      const apunte: ApunteCashflow = {
        ...comunes(r.cuenta, r.categoria, autor), fecha, concepto: r.concepto, importe: null, nota,
        recurrente_id: r.id, fecha_ocurrencia: fecha, sustituido_factura_id: sustitucion?.factura_id ?? null, sustituido_vencimiento_orden: sustitucion?.vencimiento_orden ?? null,
      };
      apuntes.push(apunte);
      return copia(apunte);
    }),
    sustituirApunte: async (apunteId, motivo, sustitucion, autor) => transaccion(autor, () => anularFila('APUNTE', apunteId, motivo, autor, sustitucion) as ApunteCashflow),
  };
}
