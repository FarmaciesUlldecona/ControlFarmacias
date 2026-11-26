// H7-AP1: apuntes manuales de Cashflow (migración 40). Ocurrencias de recurrentes (meses cortos → último día del mes),
// reglas del alta con los códigos de la BD, motor (el apunte manda sobre el Excel y la media; con vencimientos, el mayor
// en valor absoluto), sugerencia de sustitución (mismo concepto, misma decena o la siguiente, ±5 %), traducción de todos
// los códigos del esquema, lectura REAL simulada (cf_lectura), escritura REAL simulada (cf_cashflow_web: una transacción
// por operación con cf.autor, nunca DELETE), credencial y API en FIXTURES y REAL sin credencial.
// npm run test:unit
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { after, describe, test } from 'node:test';
import Fastify from 'fastify';
import { CLAVE_FIXTURES, USUARIO } from '../acceso.ts';
import { crearServidor, modulosEscritura } from '../index.ts';
import type { Fila } from '../contrato.ts';
import { calcularCashflow, finDecena, type ImporteCashflow, type SaldoCashflow, type VencimientoCashflow } from '../cashflow/cashflow.ts';
import {
  apuntesMotor, calcularOcurrencias, candidatoDe, candidatosSustitucion, comprobarAlta, comprobarAnularOcurrencia, fechaOcurrencia, fechasRecurrente,
  grupoCategoria, limiteFuturo, listaApuntes, plantillaCuenta, previsionesVacias, validarAlta, validarMotivo, validarSustitucion, ventanaOcurrencias,
  type AltaApunte, type ApunteCashflow, type ConceptoCashflow, type ContextoCashflow, type PrevisionesCashflow, type RecurrenteCashflow,
} from '../cashflow/apuntes.ts';
import { almacenSinEscritura, crearAlmacenCashflowFixtures } from '../cashflow/almacen.ts';
import { configuracionCashflow, crearAlmacenCashflowReal, MAX_CONEXIONES_CASHFLOW } from '../cashflow/adaptador_real.ts';
import { CODIGOS_BD_CASHFLOW, ErrorCashflowBd, MENSAJES_CASHFLOW, traducirErrorCashflow } from '../cashflow/errores_bd.ts';
import { leerPrevisionesReal } from '../cashflow/lectura_real.ts';
import { esEscrituraCashflow, leerSemillaApuntes, leerSemillaCashflow, registrarCashflow, vencimientoCashflow } from '../cashflow/rutas.ts';
import { SQL_ESCRITURA_APUNTES, SQL_LECTURA_APUNTES } from '../cashflow/sql_apuntes.ts';
import { construirPantalla, crearAlmacenPagos } from '../pagos/pagos.ts';
import { leerSemillaPagos } from '../pagos/rutas.ts';
import { crearAdaptadorFixtures } from '../adaptador_fixtures.ts';

const ESQUEMA = join(import.meta.dirname, '..', '..', '..', 'docs', 'referencia', 'ESQUEMA_CASHFLOW.md');
const U = (n: number) => `d0000000-0000-4000-8000-${String(n).padStart(12, '0')}`;

// --- Datos sintéticos: PIO y RITA con saldo de banco hasta 01–10/11/2026 -----------------------------------------
let n = 0;
const fila = (cuenta: string, d: string, categoria: string, concepto: string | null, importe: number | null): ImporteCashflow =>
  ({ id: `m${++n}`, importacion_id: 'i1', cuenta, farmacia: cuenta, decena_inicio: d, decena_fin: finDecena(d), categoria, concepto, importe });
const banco = (cuenta: string, d: string, s: number | null): SaldoCashflow =>
  ({ id: `s${++n}`, importacion_id: 'i1', cuenta, farmacia: cuenta, decena_inicio: d, saldo_inicial: null, saldo_formulas: s, saldo_bancos: s });
const IMP = [{ importacion_id: 'i1', archivo_nombre: 'Cashflow.xlsx', origen: 'NOCHE', estado: 'OK', detalle_error: null, filas: 3, importado_at: '2026-11-15T08:00:00.000Z', vigente: true }];
const CUENTAS = [{ codigo: 'PIO', farmacia: 'PIO' }, { codigo: 'RITA', farmacia: 'RITA' }];
const IMPORTES = [
  fila('PIO', '2026-11-01', 'RS Proveedores', 'ALLIANCE', 600), fila('PIO', '2026-11-01', 'RS Gastos generales', 'Luz', 100),
  fila('PIO', '2026-11-01', 'RE Cobro TPV', 'TPV', 1000), fila('RITA', '2026-11-01', 'RS Gastos generales', 'Luz', 200),
];
const SALDOS = [banco('PIO', '2026-11-01', 5000), banco('RITA', '2026-11-01', 1000)];
const DATOS = { importaciones: IMP, cuentas: CUENTAS, importes: IMPORTES, saldos: SALDOS };
const comunes = (id: string, cuenta: 'PIO' | 'RITA', categoria: string) => ({
  id, cuenta, farmacia: cuenta, categoria, autor: 'Marc', creado_at: '2026-11-12T10:00:00.000Z', anulado: false, anulado_por: null, anulado_at: null, motivo_anulacion: null,
});
const apunte = (o: Partial<ApunteCashflow> & { id: string }): ApunteCashflow => ({
  ...comunes(o.id, 'PIO', 'RS Proveedores'), fecha: '2026-11-15', concepto: 'ALLIANCE', importe: 460, nota: null, recurrente_id: null, fecha_ocurrencia: null,
  sustituido_factura_id: null, sustituido_vencimiento_orden: null, ...o,
});
const recurrente = (o: Partial<RecurrenteCashflow> & { id: string }): RecurrenteCashflow => ({
  ...comunes(o.id, 'RITA', 'RS Gastos generales'), concepto: 'Luz', importe: 180, nota: 'Cuota', frecuencia: 'MENSUAL', dia: 31, inicio: '2027-01-31', fin: '2027-05-31', ...o,
});
const concepto = (o: Partial<ConceptoCashflow> & { id: string }): ConceptoCashflow => ({ ...comunes(o.id, 'PIO', 'RS Proveedores'), nombre: 'Lab Nuevo', proveedor_cif: null, ...o });
const previsiones = (o: Partial<PrevisionesCashflow> = {}): PrevisionesCashflow => {
  const p = { ...previsionesVacias('2026-11-16'), ...o };
  return { ...p, ocurrencias: o.ocurrencias ?? calcularOcurrencias(p, p.ventana.desde, p.ventana.hasta) };
};
const ctx = (p: Partial<PrevisionesCashflow> = {}, datos: Partial<typeof DATOS> = {}): ContextoCashflow => ({ datos: { ...DATOS, ...datos }, previsiones: previsiones(p) });
const alta = (o: Partial<AltaApunte> = {}): AltaApunte => ({
  tipo: 'SUELTO', cuenta: 'PIO', categoria: 'RS Gastos generales', concepto: 'Luz', concepto_nuevo: null, importe: 100, nota: null,
  fecha: '2026-11-20', frecuencia: null, dia: null, inicio: null, fin: null, ...o,
});
const rec = (o: Partial<AltaApunte> = {}) => alta({ tipo: 'RECURRENTE', fecha: null, frecuencia: 'MENSUAL', dia: 31, inicio: '2027-01-31', fin: null, ...o });
const venc = (o: Partial<VencimientoCashflow> = {}): VencimientoCashflow => ({
  vencimiento_id: 'v1', factura_id: U(900), vencimiento_orden: 1, numero_factura: 'AL-1', proveedor_comercial: 'ALLIANCE', proveedor_cif: 'B00000003',
  proveedor_nombre: 'ALLIANCE', fecha_vencimiento: '2026-11-16', importe: 472.22, sentido: 'CARGO', estado_pago: 'PENDIENTE', fecha_pago: null, cargo_negativo: false, ...o,
});
const codigo = (f: ReturnType<typeof comprobarAlta>) => f?.codigo ?? null;

describe('H7-AP1: ocurrencias de recurrentes', () => {
  test('mensual el 31: en los meses cortos, el último día (28/02, 30/04); trimestral; anual el 29/02; ventana y fin', () => {
    assert.deepEqual(fechasRecurrente({ frecuencia: 'MENSUAL', dia: 31, inicio: '2027-01-31', fin: '2027-05-31' }, '2026-01-01', '2030-12-31'),
      ['2027-01-31', '2027-02-28', '2027-03-31', '2027-04-30', '2027-05-31']);
    assert.deepEqual(fechasRecurrente({ frecuencia: 'MENSUAL', dia: 31, inicio: '2027-01-31', fin: null }, '2027-03-01', '2027-04-30'), ['2027-03-31', '2027-04-30']);
    assert.deepEqual(fechasRecurrente({ frecuencia: 'TRIMESTRAL', dia: 15, inicio: '2027-01-15', fin: null }, '2027-01-01', '2027-12-31'),
      ['2027-01-15', '2027-04-15', '2027-07-15', '2027-10-15']);
    assert.deepEqual(fechasRecurrente({ frecuencia: 'ANUAL', dia: 29, inicio: '2028-02-29', fin: null }, '2028-01-01', '2032-12-31'),
      ['2028-02-29', '2029-02-28', '2030-02-28', '2031-02-28', '2032-02-29']);
    assert.equal(fechaOcurrencia('2026-02', 30), '2026-02-28');
    assert.equal(fechaOcurrencia('2028-02', 31), '2028-02-29');
  });
  test('cf_cashflow_ocurrencias: sin las anuladas una a una ni las de un recurrente anulado; una anulación anulada no cuenta', () => {
    const r = recurrente({ id: U(1) });
    const anul = apunte({ id: U(2), cuenta: 'RITA', categoria: r.categoria, concepto: r.concepto, importe: null, fecha: '2027-03-31', recurrente_id: r.id, fecha_ocurrencia: '2027-03-31' });
    const v = ventanaOcurrencias('2026-11-16');
    assert.deepEqual(v, { desde: '2025-11-01', hasta: '2029-11-30' });
    assert.deepEqual(calcularOcurrencias({ recurrentes: [r], apuntes: [anul] }, v.desde, v.hasta).map((o) => o.fecha), ['2027-01-31', '2027-02-28', '2027-04-30', '2027-05-31']);
    assert.equal(calcularOcurrencias({ recurrentes: [{ ...r, anulado: true }], apuntes: [] }, v.desde, v.hasta).length, 0);
    assert.equal(calcularOcurrencias({ recurrentes: [r], apuntes: [{ ...anul, anulado: true }] }, v.desde, v.hasta).length, 5);
    const o = calcularOcurrencias({ recurrentes: [r], apuntes: [] }, v.desde, v.hasta)[1];
    assert.deepEqual(o, { recurrente_id: r.id, cuenta: 'RITA', farmacia: 'RITA', categoria: 'RS Gastos generales', concepto: 'Luz', importe: 180, fecha: '2027-02-28' });
  });
});

describe('H7-AP1: reglas del alta (mismos códigos que la BD)', () => {
  test('apunte suelto: cuenta, farmacia, vigente, plantilla, concepto, importe, fecha y solo fechas futuras', () => {
    assert.equal(comprobarAlta(alta(), ctx()), null);
    assert.equal(codigo(comprobarAlta(alta({ cuenta: 'SL' }), ctx())), 'CUENTA_NO_VALIDA');
    assert.equal(codigo(comprobarAlta(alta({ cuenta: 'RITA' }), ctx({}, { cuentas: [CUENTAS[0]] }))), 'FARMACIA_NO_HABILITADA');
    assert.equal(codigo(comprobarAlta(alta(), ctx({}, { importaciones: [] }))), 'SIN_IMPORTACION_VIGENTE');
    assert.equal(codigo(comprobarAlta(alta({ categoria: 'RS Otra' }), ctx())), 'CATEGORIA_FUERA_DE_PLANTILLA');
    assert.equal(codigo(comprobarAlta(alta({ concepto: 'Agua' }), ctx())), 'CONCEPTO_DESCONOCIDO');
    assert.equal(codigo(comprobarAlta(alta({ importe: 0 }), ctx())), 'IMPORTE_NO_POSITIVO');
    assert.equal(codigo(comprobarAlta(alta({ importe: null }), ctx())), 'IMPORTE_NO_POSITIVO');
    assert.equal(codigo(comprobarAlta(alta({ fecha: null }), ctx())), 'FECHA_AUSENTE');
    // Límite: fin de la última decena con saldo de banco (01–10/11/2026 → 10/11/2026).
    assert.equal(limiteFuturo(DATOS, 'PIO'), '2026-11-10');
    assert.equal(codigo(comprobarAlta(alta({ fecha: '2026-11-10' }), ctx())), 'FECHA_NO_FUTURA');
    assert.equal(comprobarAlta(alta({ fecha: '2026-11-11' }), ctx()), null);
    assert.equal(codigo(comprobarAlta(alta(), ctx({}, { saldos: [{ ...SALDOS[0], saldo_bancos: null }, SALDOS[1]] }))), 'SIN_SALDO_DE_BANCO');
    // RITA: sobre su propia cuenta (excepción del 17/11/2026).
    assert.equal(comprobarAlta(alta({ cuenta: 'RITA' }), ctx()), null);
    assert.equal(codigo(comprobarAlta(alta({ cuenta: 'RITA', categoria: 'RS Proveedores', concepto: 'ALLIANCE' }), ctx())), 'CATEGORIA_FUERA_DE_PLANTILLA');
  });
  test('recurrente: periodicidad, día, desde, hasta, «desde» es la primera ocurrencia y futura', () => {
    assert.equal(comprobarAlta(rec(), ctx()), null);
    assert.equal(comprobarAlta(rec({ inicio: '2027-02-28' }), ctx()), null); // 31 en febrero → 28
    assert.equal(codigo(comprobarAlta(rec({ inicio: '2027-02-27' }), ctx())), 'INICIO_NO_ES_OCURRENCIA');
    assert.equal(codigo(comprobarAlta(rec({ frecuencia: 'SEMANAL' }), ctx())), 'FRECUENCIA_NO_VALIDA');
    assert.equal(codigo(comprobarAlta(rec({ dia: 0 }), ctx())), 'DIA_NO_VALIDO');
    assert.equal(codigo(comprobarAlta(rec({ dia: 32 }), ctx())), 'DIA_NO_VALIDO');
    assert.equal(codigo(comprobarAlta(rec({ inicio: null }), ctx())), 'INICIO_AUSENTE');
    assert.equal(codigo(comprobarAlta(rec({ fin: '2027-01-30' }), ctx())), 'FIN_ANTERIOR_A_INICIO');
    assert.equal(codigo(comprobarAlta(rec({ dia: 5, inicio: '2026-11-05' }), ctx())), 'FECHA_NO_FUTURA');
  });
  test('concepto nuevo: asociado a una categoría de la plantilla; sin repetir nombre (mayúsculas y espacios) ni CIF de la cuenta; después, en la plantilla', () => {
    const nuevo = (nombre: string, proveedor_cif: string | null = null) => alta({ concepto: null, concepto_nuevo: { nombre, proveedor_cif } });
    assert.equal(comprobarAlta(nuevo('Agua'), ctx()), null);
    assert.equal(codigo(comprobarAlta(nuevo('LUZ'), ctx())), 'CONCEPTO_YA_EXISTE');
    const k = concepto({ id: U(3), categoria: 'RS Gastos generales', nombre: 'Agua', proveedor_cif: 'B12345678' });
    assert.equal(codigo(comprobarAlta(nuevo('agua'), ctx({ conceptos: [k] }))), 'CONCEPTO_YA_EXISTE');
    assert.equal(codigo(comprobarAlta(nuevo('Gas', 'B12345678'), ctx({ conceptos: [k] }))), 'CIF_YA_ASIGNADO');
    assert.equal(comprobarAlta(nuevo('Gas', 'B12345678'), ctx({ conceptos: [{ ...k, anulado: true }] })), null);
    assert.equal(comprobarAlta(alta({ concepto: 'Agua' }), ctx({ conceptos: [k] })), null);
    assert.equal(codigo(comprobarAlta(alta({ concepto: 'Agua' }), ctx({ conceptos: [{ ...k, anulado: true }] }))), 'CONCEPTO_DESCONOCIDO');
    // Grupos del formulario: ingresos, proveedores, laboratorios y gastos.
    assert.deepEqual(['RE Cobro TPV', 'RS Proveedores', 'RS Laboratorios', 'RS Gastos generales'].map(grupoCategoria), ['Ingresos', 'Proveedores', 'Laboratorios', 'Gastos']);
    const pl = plantillaCuenta(DATOS, previsiones({ conceptos: [k] }), 'PIO');
    assert.deepEqual(pl.map((c) => [c.categoria, c.grupo, c.conceptos.map((x) => `${x.nombre}${x.nuevo ? '*' : ''}`)]),
      [['RE Cobro TPV', 'Ingresos', ['TPV']], ['RS Proveedores', 'Proveedores', ['ALLIANCE']], ['RS Gastos generales', 'Gastos', ['Agua*', 'Luz']]]);
  });
  test('forma del cuerpo (tipos y largos) y motivo obligatorio', () => {
    assert.equal(validarAlta({ ...alta(), importe: 'mil' }).ok, false);
    const v = validarAlta({ ...alta(), importe: 10.555, nota: 'x'.repeat(501), concepto: null, concepto_nuevo: { nombre: 'A', proveedor_cif: 'b-1' } });
    assert.ok(!v.ok && ['importe', 'nota', 'proveedor_cif'].every((k) => k in v.errores), JSON.stringify(!v.ok && v.errores));
    const ambos = validarAlta({ ...alta(), concepto_nuevo: { nombre: 'Agua' } });
    assert.ok(!ambos.ok && 'concepto' in ambos.errores);
    const ok = validarAlta({ ...alta(), nota: '  hola  ', concepto: null, concepto_nuevo: { nombre: '  Agua   fría ', proveedor_cif: 'b12345678' } });
    assert.ok(ok.ok && ok.datos.nota === 'hola' && ok.datos.concepto_nuevo?.nombre === 'Agua fría' && ok.datos.concepto_nuevo.proveedor_cif === 'B12345678');
    assert.deepEqual(validarMotivo({ motivo: '   ' }), { ok: false, codigo: 'MOTIVO_ANULACION_AUSENTE' });
    assert.deepEqual(validarMotivo({}), { ok: false, codigo: 'MOTIVO_ANULACION_AUSENTE' });
    assert.deepEqual(validarMotivo({ motivo: ' Duplicado ' }), { ok: true, motivo: 'Duplicado' });
  });
  test('anular una ocurrencia: del recurrente vigente, fecha que es ocurrencia vigente y futura', () => {
    const r = recurrente({ id: U(1), cuenta: 'PIO', categoria: 'RS Gastos generales', inicio: '2026-11-30', dia: 30, fin: null });
    assert.equal(comprobarAnularOcurrencia(r.id, '2026-12-30', ctx({ recurrentes: [r] })), null);
    assert.equal(comprobarAnularOcurrencia(r.id, '2026-12-29', ctx({ recurrentes: [r] }))?.codigo, 'OCURRENCIA_NO_VALIDA');
    assert.equal(comprobarAnularOcurrencia(U(9), '2026-12-30', ctx({ recurrentes: [r] }))?.codigo, 'RECURRENTE_NO_ENCONTRADA');
    assert.equal(comprobarAnularOcurrencia(r.id, '2026-12-30', ctx({ recurrentes: [{ ...r, anulado: true }] }))?.codigo, 'RECURRENTE_ANULADA');
    const ya = apunte({ id: U(2), cuenta: 'PIO', importe: null, fecha: '2026-12-30', recurrente_id: r.id, fecha_ocurrencia: '2026-12-30' });
    assert.equal(comprobarAnularOcurrencia(r.id, '2026-12-30', ctx({ recurrentes: [r], apuntes: [ya] }))?.codigo, 'OCURRENCIA_NO_VALIDA');
  });
});

describe('H7-AP1: motor (el apunte manda; con vencimientos, el mayor en valor absoluto)', () => {
  const calcular = (p: PrevisionesCashflow, vencimientos: VencimientoCashflow[] = []) =>
    calcularCashflow({ ...DATOS, hoy: '2026-11-16', vencimientos, apuntes_manuales: apuntesMotor(p) });
  const celdaPio = (r: ReturnType<typeof calcular>, concepto: string, d: string) => r.vistas.PIO.lineas.find((l) => l.concepto === concepto)?.celdas[d];
  test('vencimiento mayor que el apunte: ganan los vencimientos; el apunte queda a la vista (comparado y en la celda)', () => {
    const r = calcular(previsiones({ apuntes: [apunte({ id: U(1), importe: 400, nota: 'Pedido grande' })] }), [venc()]);
    const c = celdaPio(r, 'ALLIANCE', '2026-11-11');
    assert.deepEqual([c?.fuente, c?.importe, c?.comparada], ['VENCIMIENTOS', -472.22, { fuente: 'MANUAL', importe: -400 }]);
    assert.deepEqual(c?.apuntes.map((a) => [a.tipo, a.id, a.nota, a.autor, a.fecha]), [['SUELTO', U(1), 'Pedido grande', 'Marc', '2026-11-15']]);
    const m = celdaPio(calcular(previsiones({ apuntes: [apunte({ id: U(1), importe: 500 })] }), [venc()]), 'ALLIANCE', '2026-11-11');
    assert.deepEqual([m?.fuente, m?.importe, m?.comparada], ['MANUAL', -500, { fuente: 'VENCIMIENTOS', importe: -472.22 }]);
  });
  test('apunte en un concepto con media: manda el apunte (la media, a la vista sin sumar); apunte de entrada (RE) suma; ocurrencias como apuntes', () => {
    const r = calcular(previsiones({ apuntes: [apunte({ id: U(1), categoria: 'RE Cobro TPV', concepto: 'TPV', importe: 250, fecha: '2026-12-02' })] }));
    const c = celdaPio(r, 'TPV', '2026-12-01');
    assert.deepEqual([c?.fuente, c?.importe, c?.media?.media, c?.en_saldo], ['MANUAL', 250, 1000, true]);
    const sin = calcular(previsiones());
    assert.equal(Math.round(((r.vistas.PIO.decenas['2026-12-01'].saldo as number) - (sin.vistas.PIO.decenas['2026-12-01'].saldo as number)) * 100), (250 - 1000) * 100);
    // Recurrente de RITA (31 → 28/02): una cifra en cada 3.ª decena, con su origen.
    const rr = calcular(previsiones({ recurrentes: [recurrente({ id: U(5) })] }));
    const luz = rr.vistas.RITA.lineas.find((l) => l.concepto === 'Luz');
    assert.deepEqual(['2027-01-21', '2027-02-21', '2027-03-21'].map((d) => [luz?.celdas[d]?.fuente, luz?.celdas[d]?.importe, luz?.celdas[d]?.apuntes[0]?.fecha]),
      [['MANUAL', -180, '2027-01-31'], ['MANUAL', -180, '2027-02-28'], ['MANUAL', -180, '2027-03-31']]);
    assert.equal(rr.vistas.CONSOLIDADO.lineas.find((l) => l.concepto === 'Luz')?.celdas['2027-02-21']?.apuntes.length, 1);
    // Concepto nuevo con su apunte: línea propia.
    const k = calcular(previsiones({ apuntes: [apunte({ id: U(1), categoria: 'RS Gastos generales', concepto: 'Agua', importe: 70, fecha: '2026-11-25' })] }));
    assert.equal(celdaPio(k, 'Agua', '2026-11-21')?.importe, -70);
    // Apunte en una decena ya real: no cuenta (lo real es el Excel).
    const real = calcular(previsiones({ apuntes: [apunte({ id: U(1), fecha: '2026-11-05' })] }));
    assert.equal(celdaPio(real, 'ALLIANCE', '2026-11-01')?.fuente, 'REAL');
  });
});

describe('H7-AP1: sugerencia de sustitución por una factura', () => {
  test('mismo concepto (nombre comercial o CIF del concepto nuevo), misma decena o la siguiente, ±5 %; nunca RITA ni un vencimiento ya usado', () => {
    const conA = (a: Partial<ApunteCashflow>, vs: VencimientoCashflow[] = [venc()], o: Partial<PrevisionesCashflow> = {}) =>
      candidatosSustitucion(ctx({ apuntes: [apunte({ id: U(1), ...a })], ...o }), vs);
    const c = conA({});
    assert.deepEqual(c.map((x) => [x.tipo, x.apunte_id, x.vencimiento.factura_id, x.vencimiento.vencimiento_orden, x.diferencia]), [['SUELTO', U(1), U(900), 1, 12.22]]);
    // ±5 % del apunte: 450 → 22,50 de margen (22,22 entra); 449 → 22,45 (23,22 no).
    assert.equal(conA({ importe: 450 }).length, 1);
    assert.equal(conA({ importe: 449 }).length, 0);
    assert.equal(conA({ importe: 497 }).length, 1);
    assert.equal(conA({ importe: 498 }).length, 0);
    // Decena: la misma o la siguiente; nunca la anterior ni dos después.
    assert.equal(conA({}, [venc({ fecha_vencimiento: '2026-11-25' })]).length, 1);
    assert.equal(conA({}, [venc({ fecha_vencimiento: '2026-12-01' })]).length, 0);
    assert.equal(conA({ fecha: '2026-11-25' }, [venc({ fecha_vencimiento: '2026-11-12' })]).length, 0);
    // Otro proveedor, abono en una salida, cargo negativo, sin orden, sin importe: no.
    for (const v of [venc({ proveedor_comercial: 'HEFAME' }), venc({ sentido: 'ABONO' }), venc({ cargo_negativo: true }), venc({ vencimiento_orden: null }), venc({ importe: null })]) assert.equal(conA({}, [v]).length, 0);
    // RITA: sin vencimientos ni facturas.
    assert.equal(conA({ cuenta: 'RITA', farmacia: 'RITA' }).length, 0);
    // Un vencimiento ya usado en otra sustitución no vuelve a salir.
    const usado = apunte({ id: U(2), anulado: true, sustituido_factura_id: U(900), sustituido_vencimiento_orden: 1 });
    assert.equal(candidatosSustitucion(ctx({ apuntes: [apunte({ id: U(1) }), usado] }), [venc()]).length, 0);
    // Concepto nuevo con CIF: sus facturas coinciden por el CIF.
    const k = concepto({ id: U(3), nombre: 'Lab Nuevo', proveedor_cif: 'B12345678' });
    assert.equal(conA({ concepto: 'Lab Nuevo' }, [venc({ proveedor_comercial: null, proveedor_cif: 'B12345678' })], { conceptos: [k] }).length, 1);
    assert.equal(conA({ concepto: 'Lab Nuevo' }, [venc({ proveedor_comercial: null, proveedor_cif: 'B12345678' })]).length, 0);
    // Ocurrencia de un recurrente de PIO.
    const r = recurrente({ id: U(4), cuenta: 'PIO', farmacia: 'PIO', categoria: 'RS Proveedores', concepto: 'ALLIANCE', importe: 470, dia: 15, inicio: '2026-11-15', fin: '2026-11-15' });
    const o = candidatosSustitucion(ctx({ recurrentes: [r] }), [venc()]);
    assert.deepEqual(o.map((x) => [x.tipo, x.recurrente_id, x.fecha]), [['OCURRENCIA', U(4), '2026-11-15']]);
    // Petición: la de un candidato o null.
    const s = validarSustitucion({ recurrente_id: U(4), fecha_ocurrencia: '2026-11-15', factura_id: U(900), vencimiento_orden: 1 });
    assert.ok(s.ok && candidatoDe(o, s.datos) !== null);
    assert.equal(validarSustitucion({ apunte_id: U(1), recurrente_id: U(4), fecha_ocurrencia: '2026-11-15', factura_id: U(900), vencimiento_orden: 1 }).ok, false);
  });
});

describe('H7-AP1: códigos de error', () => {
  test('todos los códigos del esquema (más FECHA_AUSENTE y MOTIVO_ANULACION_AUSENTE) llegan con su mensaje llano', () => {
    const doc = readFileSync(ESQUEMA, 'utf8');
    const tramo = doc.slice(doc.indexOf('### Validaciones al dar de alta'), doc.indexOf('### Anular (nunca borrar)'));
    const delEsquema = new Set([...tramo.matchAll(/`([A-Z][A-Z_]{3,})`/g)].map((m) => m[1]).filter((c) => !['UPDATE', 'DELETE', 'TRUNCATE', 'CASHFLOW', 'PIO', 'RITA'].includes(c)));
    assert.deepEqual([...delEsquema].sort(), [...CODIGOS_BD_CASHFLOW].sort());
    assert.equal(CODIGOS_BD_CASHFLOW.length, 28);
    assert.ok(CODIGOS_BD_CASHFLOW.includes('FECHA_AUSENTE') && CODIGOS_BD_CASHFLOW.includes('MOTIVO_ANULACION_AUSENTE'));
    for (const c of CODIGOS_BD_CASHFLOW) {
      const t = traducirErrorCashflow(Object.assign(new Error(`${c}: detalle técnico con SQL`), { code: 'P0001' }));
      assert.equal(t.codigo, c);
      assert.ok(!t.mensaje.includes('SQL') && t.mensaje.length > 10);
    }
    const pg = (code: string, message = 'x') => traducirErrorCashflow(Object.assign(new Error(message), { code })).codigo;
    assert.deepEqual([pg('23505'), pg('23514'), pg('42501'), pg('42501', 'new row violates row-level security policy'), pg('57014'), pg('53300'), pg('ECONNREFUSED'), pg('XX000'), pg('P0001', 'OTRO_CODIGO')],
      ['DUPLICADO', 'REGLA_TABLA', 'PERMISO_DENEGADO', 'RLS_DENEGADO', 'TIEMPO_AGOTADO', 'SIN_CONEXIONES', 'SIN_CONEXION', 'ERROR_BD', 'ERROR_BD']);
    assert.equal(MENSAJES_CASHFLOW.CREDENCIAL_CASHFLOW_AUSENTE.http, 503);
  });
});

// --- Lectura REAL simulada (cf_lectura) ------------------------------------------------------------------------------
const FILAS_REAL: Record<string, Fila[]> = {
  [SQL_LECTURA_APUNTES.conceptos]: [{ id: U(1), cuenta: 'PIO', farmacia: 'PIO', categoria: 'RS Gastos generales', autor: 'Marc', creado_at: '2026-11-12 10:15:00+00', anulado: false, anulado_por: null, anulado_at: null, motivo_anulacion: null, nombre: 'Ascensor', proveedor_cif: null }],
  [SQL_LECTURA_APUNTES.recurrentes]: [{ id: U(2), cuenta: 'RITA', farmacia: 'RITA', categoria: 'RS Gastos generales', autor: 'Marc', creado_at: '2026-11-12 10:30:00+00', anulado: false, anulado_por: null, anulado_at: null, motivo_anulacion: null, concepto: 'Luz', importe: '180.00', nota: null, frecuencia: 'MENSUAL', dia: 31, inicio: '2027-01-31', fin: null }],
  [SQL_LECTURA_APUNTES.apuntes]: [
    { id: U(3), cuenta: 'PIO', farmacia: 'PIO', categoria: 'RS Gastos generales', autor: 'Marc', creado_at: '2026-11-12 10:16:00+00', anulado: false, anulado_por: null, anulado_at: null, motivo_anulacion: null, fecha: '2027-02-05', concepto: 'Ascensor', importe: '350.00', nota: 'Revisión', recurrente_id: null, fecha_ocurrencia: null, sustituido_factura_id: null, sustituido_vencimiento_orden: null },
    { id: U(4), cuenta: 'RITA', farmacia: 'RITA', categoria: 'RS Gastos generales', autor: 'Marc', creado_at: '2026-11-12 10:31:00+00', anulado: false, anulado_por: null, anulado_at: null, motivo_anulacion: null, fecha: '2027-03-31', concepto: 'Luz', importe: null, nota: 'Promoción', recurrente_id: U(2), fecha_ocurrencia: '2027-03-31', sustituido_factura_id: null, sustituido_vencimiento_orden: null },
  ],
  [SQL_LECTURA_APUNTES.ocurrencias]: [
    { recurrente_id: U(2), cuenta: 'RITA', farmacia: 'RITA', categoria: 'RS Gastos generales', concepto: 'Luz', importe: '180.00', fecha: '2027-01-31' },
    { recurrente_id: U(2), cuenta: 'RITA', farmacia: 'RITA', categoria: 'RS Gastos generales', concepto: 'Luz', importe: '180.00', fecha: '2027-02-28' },
  ],
};
const consultar = (filas: Record<string, Fila[]>, log: { sql: string; params: unknown[] }[] = []) => async (sql: string, params: unknown[]) => { log.push({ sql, params }); return filas[sql] ?? []; };

describe('H7-AP1: lectura REAL de los apuntes (cf_lectura, base simulada)', () => {
  test('solo SELECT de las tres tablas y de cf_cashflow_ocurrencias; cuentas PIO y RITA; ventana de ocurrencias de la BD', async () => {
    for (const sql of Object.values(SQL_LECTURA_APUNTES)) {
      assert.match(sql, /^select /);
      assert.doesNotMatch(sql, /\b(insert|update|delete|truncate|grant|alter|create|drop|merge|copy|set_config)\b/i);
      for (const t of sql.match(/public\.\w+/g) ?? []) assert.ok(['public.cf_cashflow_conceptos', 'public.cf_cashflow_recurrentes', 'public.cf_cashflow_apuntes', 'public.cf_cashflow_ocurrencias'].includes(t), t);
    }
    const log: { sql: string; params: unknown[] }[] = [];
    const p = await leerPrevisionesReal(consultar(FILAS_REAL, log), '2026-11-16');
    assert.deepEqual(log.map((x) => x.params), [[['PIO', 'RITA']], [['PIO', 'RITA']], [['PIO', 'RITA']], ['2025-11-01', '2029-11-30']]);
    assert.deepEqual([p.conceptos.length, p.recurrentes[0].importe, p.recurrentes[0].dia, p.apuntes[0].importe, p.apuntes[1].importe, p.apuntes[1].recurrente_id, p.ocurrencias.map((o) => o.fecha)],
      [1, 180, 31, 350, null, U(2), ['2027-01-31', '2027-02-28']]);
    assert.equal(p.conceptos[0].creado_at, '2026-11-12T10:15:00.000Z');
    // Con el motor: el apunte y las ocurrencias de la BD.
    assert.equal(apuntesMotor(p).length, 3);
  });
  test('falla cerrado: farmacia que no es la de su cuenta, cuenta ajena, apunte sin forma de suelto ni de anulación, ocurrencia de un recurrente no leído', async () => {
    const con = (k: string, f: (x: Fila[]) => Fila[]) => leerPrevisionesReal(consultar({ ...FILAS_REAL, [k]: f(FILAS_REAL[k]) }), '2026-11-16');
    await assert.rejects(con(SQL_LECTURA_APUNTES.conceptos, (x) => [{ ...x[0], farmacia: 'RITA' }]), /CASHFLOW_FARMACIA_NO_CUADRA/);
    await assert.rejects(con(SQL_LECTURA_APUNTES.conceptos, (x) => [{ ...x[0], cuenta: 'SL', farmacia: null }]), /CASHFLOW_CUENTA_NO_PEDIDA/);
    await assert.rejects(con(SQL_LECTURA_APUNTES.apuntes, (x) => [{ ...x[0], importe: null }]), /tipo de apunte/);
    await assert.rejects(con(SQL_LECTURA_APUNTES.apuntes, (x) => [{ ...x[1], importe: '10.00' }]), /tipo de apunte/);
    await assert.rejects(con(SQL_LECTURA_APUNTES.ocurrencias, (x) => [{ ...x[0], recurrente_id: U(99) }]), /CASHFLOW_OCURRENCIA_INESPERADA/);
    await assert.rejects(con(SQL_LECTURA_APUNTES.recurrentes, (x) => [{ ...x[0], frecuencia: 'SEMANAL' }]), /frecuencia/);
    await assert.rejects(con(SQL_LECTURA_APUNTES.apuntes, (x) => [x[0], x[0]]), /CASHFLOW_ID_REPETIDO/);
  });
});

// --- Escritura REAL simulada (cf_cashflow_web) ---------------------------------------------------------------------
type Paso = { sql: string; params: unknown[] };
function poolFalso(responder: (sql: string, params: unknown[]) => Fila[] | Error) {
  const log: Paso[] = [];
  return {
    log,
    pool: {
      connect: async () => ({
        query: async (sql: string, params?: unknown[]) => { log.push({ sql, params: params ?? [] }); const r = responder(sql, params ?? []); if (r instanceof Error) throw r; return { rows: r }; },
        release: () => {},
      }),
      end: async () => {},
    },
  };
}
const filaApunte = FILAS_REAL[SQL_LECTURA_APUNTES.apuntes][0];
const filaConcepto = FILAS_REAL[SQL_LECTURA_APUNTES.conceptos][0];
const filaRec = FILAS_REAL[SQL_LECTURA_APUNTES.recurrentes][0];

describe('H7-AP1: escritura REAL (cf_cashflow_web, base simulada)', () => {
  test('alta con concepto nuevo: una transacción con cf.autor dentro; farmacia y autor no se envían; importe positivo en texto', async () => {
    const { log, pool } = poolFalso((sql) => (sql === SQL_ESCRITURA_APUNTES.insertarConcepto ? [filaConcepto] : sql === SQL_ESCRITURA_APUNTES.insertarApunte ? [filaApunte] : []));
    const a = crearAlmacenCashflowReal({ pool });
    assert.equal(a.sinEscritura, null);
    const r = await a.alta(alta({ concepto: null, concepto_nuevo: { nombre: 'Ascensor', proveedor_cif: null }, importe: 350, fecha: '2027-02-05', nota: 'Revisión' }), 'Marc');
    assert.deepEqual(log.map((x) => x.sql), ['begin', SQL_ESCRITURA_APUNTES.autor, SQL_ESCRITURA_APUNTES.insertarConcepto, SQL_ESCRITURA_APUNTES.insertarApunte, 'commit']);
    assert.deepEqual(log[1].params, ['Marc']);
    assert.deepEqual(log[2].params, ['PIO', 'RS Gastos generales', 'Ascensor', null]);
    assert.deepEqual(log[3].params, ['PIO', 'RS Gastos generales', 'Ascensor', '2027-02-05', '350.00', 'Revisión']);
    assert.deepEqual([r.concepto?.nombre, r.apunte?.importe, r.recurrente], ['Ascensor', 350, null]);
  });
  test('recurrente; error de la BD → ROLLBACK y mensaje llano, sin reintento', async () => {
    const { log, pool } = poolFalso((sql) => (sql === SQL_ESCRITURA_APUNTES.insertarRecurrente ? Object.assign(new Error('FECHA_NO_FUTURA: ninguna ocurrencia'), { code: 'P0001' }) : []));
    const a = crearAlmacenCashflowReal({ pool });
    await assert.rejects(a.alta(rec({ cuenta: 'RITA' }), 'Marc'), (e: unknown) => e instanceof ErrorCashflowBd && e.codigo === 'FECHA_NO_FUTURA');
    assert.deepEqual(log.map((x) => x.sql), ['begin', SQL_ESCRITURA_APUNTES.autor, SQL_ESCRITURA_APUNTES.insertarRecurrente, 'rollback']);
    assert.deepEqual(log[2].params, ['RITA', 'RS Gastos generales', 'Luz', '100.00', null, 'MENSUAL', 31, '2027-01-31', null]);
    const ok = poolFalso((sql) => (sql === SQL_ESCRITURA_APUNTES.insertarRecurrente ? [filaRec] : []));
    assert.equal((await crearAlmacenCashflowReal({ pool: ok.pool }).alta(rec({ cuenta: 'RITA' }), 'Marc')).recurrente?.dia, 31);
  });
  test('anular (nunca borrar): UPDATE … where not anulado; sin fila: no existe o ya anulado (SOLO_ANULAR); editar = anular + alta en la misma transacción', async () => {
    const anulado = { ...filaApunte, anulado: true, anulado_por: 'Marc', anulado_at: '2026-11-16 09:00:00+00', motivo_anulacion: 'Duplicado' };
    const p1 = poolFalso((sql) => (sql === SQL_ESCRITURA_APUNTES.anularApunte ? [anulado] : []));
    assert.equal(((await crearAlmacenCashflowReal({ pool: p1.pool }).anular('APUNTE', U(3), ' Duplicado ', 'Marc')) as ApunteCashflow).motivo_anulacion, 'Duplicado');
    assert.deepEqual(p1.log[2].params, [U(3), 'Duplicado']);
    const p2 = poolFalso((sql) => (sql === SQL_ESCRITURA_APUNTES.apuntePorId ? [{ id: U(3), anulado: true, recurrente_id: null }] : []));
    await assert.rejects(crearAlmacenCashflowReal({ pool: p2.pool }).anular('APUNTE', U(3), 'x', 'Marc'), (e: unknown) => (e as ErrorCashflowBd).codigo === 'SOLO_ANULAR');
    assert.ok(p2.log.some((x) => x.sql === 'rollback') && !p2.log.some((x) => x.sql === 'commit'));
    const p3 = poolFalso(() => []);
    await assert.rejects(crearAlmacenCashflowReal({ pool: p3.pool }).anular('RECURRENTE', U(9), 'x', 'Marc'), (e: unknown) => (e as ErrorCashflowBd).codigo === 'RECURRENTE_NO_ENCONTRADA');
    await assert.rejects(crearAlmacenCashflowReal({ pool: p3.pool }).anular('APUNTE', U(9), '  ', 'Marc'), (e: unknown) => (e as ErrorCashflowBd).codigo === 'MOTIVO_ANULACION_AUSENTE');
    const p4 = poolFalso((sql) => (sql === SQL_ESCRITURA_APUNTES.anularApunte ? [anulado] : sql === SQL_ESCRITURA_APUNTES.insertarApunte ? [filaApunte] : []));
    const ed = await crearAlmacenCashflowReal({ pool: p4.pool }).editar({ tabla: 'APUNTE', id: U(3) }, 'Importe corregido', alta({ fecha: '2027-02-05' }), 'Marc');
    assert.deepEqual(p4.log.map((x) => x.sql), ['begin', SQL_ESCRITURA_APUNTES.autor, SQL_ESCRITURA_APUNTES.anularApunte, SQL_ESCRITURA_APUNTES.insertarApunte, 'commit']);
    assert.equal(ed.anulado.anulado, true);
  });
  test('anular una ocurrencia (alta sin importe) y sustitución confirmada (al anular el suelto o en el alta de la anulación)', async () => {
    const anulacion = FILAS_REAL[SQL_LECTURA_APUNTES.apuntes][1];
    const p = poolFalso((sql) => (sql === SQL_ESCRITURA_APUNTES.anularOcurrencia ? [anulacion] : sql === SQL_ESCRITURA_APUNTES.sustituirApunte ? [{ ...filaApunte, anulado: true, sustituido_factura_id: U(900), sustituido_vencimiento_orden: 1 }] : []));
    const a = crearAlmacenCashflowReal({ pool: p.pool });
    await a.anularOcurrencia(U(2), '2027-03-31', 'Promoción', 'Marc', null);
    assert.deepEqual(p.log[2].params, [U(2), '2027-03-31', 'Promoción', null, null]);
    const s = await a.sustituirApunte(U(3), 'Sustituido por la factura AL-1', { factura_id: U(900), vencimiento_orden: 1 }, 'Marc');
    assert.deepEqual([s.sustituido_factura_id, s.sustituido_vencimiento_orden], [U(900), 1]);
    assert.deepEqual(p.log.at(-2)?.params, [U(3), 'Sustituido por la factura AL-1', U(900), 1]);
    await a.anularOcurrencia(U(2), '2027-03-31', 'Sustituido', 'Marc', { factura_id: U(900), vencimiento_orden: 2 });
    assert.deepEqual(p.log.at(-2)?.params, [U(2), '2027-03-31', 'Sustituido', U(900), 2]);
  });
  test('ninguna sentencia borra; los UPDATE solo tocan la anulación y la sustitución', () => {
    for (const sql of Object.values(SQL_ESCRITURA_APUNTES)) assert.doesNotMatch(sql, /\b(delete|truncate|drop|alter|grant)\b/i);
    for (const sql of Object.values(SQL_ESCRITURA_APUNTES).filter((s) => /^update /.test(s))) {
      const set = /set (.*) where/.exec(sql)?.[1] ?? '';
      for (const c of set.split(',').map((x) => x.trim().split(' ')[0])) assert.ok(['anulado', 'motivo_anulacion', 'sustituido_factura_id', 'sustituido_vencimiento_orden'].includes(c), c);
    }
    for (const sql of Object.values(SQL_ESCRITURA_APUNTES).filter((s) => /^insert /.test(s))) assert.doesNotMatch(sql.split('values')[0], /\b(farmacia|autor|creado_at|anulado)\b/);
  });
  test('sin credencial: solo lectura (CREDENCIAL_CASHFLOW_AUSENTE en cada escritura); configuración: rol cf_cashflow_web, pool de 2, CA', async () => {
    const a = crearAlmacenCashflowReal({ pool: null });
    assert.equal(a.sinEscritura?.codigo, 'CREDENCIAL_CASHFLOW_AUSENTE');
    await assert.rejects(a.alta(alta(), 'Marc'), (e: unknown) => (e as ErrorCashflowBd).codigo === 'CREDENCIAL_CASHFLOW_AUSENTE');
    await assert.rejects(a.probarCredencial(), (e: unknown) => (e as ErrorCashflowBd).codigo === 'CREDENCIAL_CASHFLOW_AUSENTE');
    const env = { CF_LECTURA_HOST: 'h', CF_LECTURA_PORT: '6543', CF_LECTURA_DB: 'postgres', CF_CASHFLOW_USER: 'cf_cashflow_web.ref', CF_CASHFLOW_PASSWORD: 'x' };
    const ca = () => 'PEM';
    assert.equal((configuracionCashflow({ ...env, CF_CASHFLOW_PASSWORD: undefined }, ca) as { codigo: string }).codigo, 'CREDENCIAL_CASHFLOW_AUSENTE');
    assert.equal((configuracionCashflow({ ...env, CF_CASHFLOW_USER: 'cf_pagos_web' }, ca) as { codigo: string }).codigo, 'USUARIO_NO_CF_CASHFLOW_WEB');
    assert.equal((configuracionCashflow({ ...env, CF_LECTURA_HOST: undefined }, ca) as { codigo: string }).codigo, 'ENV_WEB_INCOMPLETO');
    assert.equal((configuracionCashflow(env, () => { throw new Error('FALTA_CERTIFICADO_CA: x'); }) as { codigo: string }).codigo, 'CERTIFICADO_CA');
    const ok = configuracionCashflow(env, ca);
    assert.ok(ok.ok && ok.config.max === MAX_CONEXIONES_CASHFLOW && MAX_CONEXIONES_CASHFLOW === 2 && ok.config.user === 'cf_cashflow_web.ref'
      && (ok.config.ssl as { rejectUnauthorized: boolean }).rejectUnauthorized === true);
    // check:real: la credencial conecta y cuenta (READ ONLY, sin escribir).
    const p = poolFalso((sql) => (sql === SQL_ESCRITURA_APUNTES.prueba ? [{ filas: '7' }] : []));
    assert.deepEqual(await crearAlmacenCashflowReal({ pool: p.pool }).probarCredencial(), { filas: 7 });
    assert.deepEqual(p.log.map((x) => x.sql), ['begin transaction read only', SQL_ESCRITURA_APUNTES.prueba, 'rollback']);
  });
  test('rótulo REAL «escritura: Trabajadores, Pagos, Cashflow» (solo con la credencial de Cashflow)', () => {
    const si = { sinEscritura: null };
    const no = { sinEscritura: { codigo: 'CREDENCIAL_CASHFLOW_AUSENTE' as const, mensaje: 'x' } };
    assert.deepEqual(modulosEscritura('REAL', { trabajadores: true, pagos: si, cashflow: si }), ['Trabajadores', 'Pagos', 'Cashflow']);
    assert.deepEqual(modulosEscritura('REAL', { trabajadores: true, pagos: si, cashflow: no }), ['Trabajadores', 'Pagos']);
    assert.deepEqual(modulosEscritura('FIXTURES', { trabajadores: true, pagos: si, cashflow: si }), []);
  });
});

describe('H7-AP1: semilla de FIXTURES', () => {
  test('casos: suelto, concepto nuevo, recurrente con el 31 en un mes corto, ocurrencia anulada, apunte que gana al Excel y a la media; lo visible hasta el 21/01/2027 no cambia', async () => {
    const s = leerSemillaApuntes();
    const datos = leerSemillaCashflow();
    const a = crearAlmacenCashflowFixtures(s, () => datos);
    const p = await (a.previsiones as NonNullable<typeof a.previsiones>)(s.hoy);
    assert.deepEqual([p.conceptos.length, p.recurrentes.length, p.apuntes.length], [1, 1, 4]);
    assert.deepEqual(p.ocurrencias.map((o) => o.fecha), ['2027-01-31', '2027-02-28', '2027-04-30', '2027-05-31', '2027-06-30', '2027-07-31', '2027-08-31', '2027-09-30', '2027-10-31', '2027-11-30', '2027-12-31']);
    const pagos = crearAlmacenPagos(leerSemillaPagos());
    const vencs = construirPantalla(await crearAdaptadorFixtures().vencimientos(), pagos.fuente(), { hoy: pagos.hoy, modo: 'FIXTURES' }).filas.map(vencimientoCashflow);
    const base = { ...datos, vencimientos: [] as VencimientoCashflow[] };
    const r = calcularCashflow({ ...base, apuntes_manuales: apuntesMotor(p) });
    const sin = calcularCashflow(base);
    const L = (v: 'PIO' | 'RITA', con: string) => r.vistas[v].lineas.find((l) => l.concepto === con);
    const fondos = L('PIO', 'TRASPASO A FONDOS/VALORS')?.celdas['2027-02-01'];
    assert.deepEqual([fondos?.fuente, fondos?.importe, fondos?.excel, fondos?.media?.media], ['MANUAL', -2000, -2500, -1000]);
    assert.deepEqual([L('PIO', 'Mantenimiento ascensor')?.celdas['2027-02-01']?.importe, L('PIO', 'Mantenimiento ascensor')?.celdas['2027-02-01']?.apuntes[0]?.nota], [-350, 'Revisión anual del ascensor']);
    const sum = L('RITA', 'Suministros');
    assert.deepEqual([sum?.celdas['2027-02-21']?.importe, sum?.celdas['2027-02-21']?.apuntes[0]?.fecha, sum?.celdas['2027-03-21']], [-180, '2027-02-28', undefined]);
    // El anulado (PIO Suministros 15/02/2027) no cuenta.
    assert.equal(L('PIO', 'Suministros')?.celdas['2027-02-11']?.fuente, 'MEDIA');
    for (const v of ['PIO', 'RITA', 'CONSOLIDADO'] as const) for (const d of r.decenas.filter((x) => x < '2027-01-21')) assert.equal(r.vistas[v].decenas[d].saldo, sin.vistas[v].decenas[d].saldo, `${v} ${d}`);
    assert.deepEqual(r.avisos.map((x) => [x.tipo, x.decena, x.importe]), sin.avisos.map((x) => [x.tipo, x.decena, x.importe]));
    // Sin sugerencias en la semilla (el único vencimiento futuro con concepto es ALLIANCE 11–20/11, sin apunte).
    assert.equal(candidatosSustitucion({ datos, previsiones: p }, vencs).length, 0);
    assert.ok(vencs.some((v) => v.vencimiento_orden === 1 && v.proveedor_cif === 'B00000003'));
    // «Apuntes manuales»: sueltos vigentes 2, recurrente 1 con sus próximas, anulados 1.
    const lista = listaApuntes({ datos, previsiones: p }, null);
    assert.deepEqual([lista.sueltos.length, lista.recurrentes.length, lista.recurrentes[0].proximas.length, lista.recurrentes[0].anuladas.length, lista.anulados], [2, 1, 6, 1, 1]);
    assert.equal(listaApuntes({ datos, previsiones: p }, 'RITA').sueltos.length, 0);
  });
});

describe('H7-AP1: API /api/cashflow/… (FIXTURES)', async () => {
  const app = await crearServidor('FIXTURES');
  after(() => app.close());
  const H = { host: '127.0.0.1:4747' };
  const login = await app.inject({
    method: 'POST', url: '/api/login', headers: { ...H, 'content-type': 'application/x-www-form-urlencoded' },
    payload: new URLSearchParams({ usuario: USUARIO, clave: CLAVE_FIXTURES, destino: '/' }).toString(),
  });
  const cookie = String(login.headers['set-cookie']).split(';')[0];
  const W = { ...H, cookie, origin: 'http://127.0.0.1:4747', 'content-type': 'application/json' };
  const get = async () => (await app.inject({ method: 'GET', url: '/api/cashflow', headers: { ...H, cookie } })).json();
  const post = (url: string, body: unknown) => app.inject({ method: 'POST', url, headers: W, payload: JSON.stringify(body) });
  const put = (url: string, body: unknown) => app.inject({ method: 'PUT', url, headers: W, payload: JSON.stringify(body) });
  const cuerpo = (o: Record<string, unknown> = {}) => ({ tipo: 'SUELTO', cuenta: 'PIO', categoria: 'RS Gastos generales', concepto: 'Suministros', importe: 99, fecha: '2027-03-05', nota: 'Prueba', ...o });

  test('lectura: previsiones de la semilla y escritura habilitada (autor Marc); rutas protegidas (sesión, Origin, JSON; nunca DELETE)', async () => {
    const d = await get();
    assert.deepEqual([d.previsiones.conceptos.length, d.previsiones.recurrentes.length, d.previsiones.apuntes.length, d.previsiones.ocurrencias.length], [1, 1, 4, 11]);
    assert.deepEqual(d.escritura_cashflow, { habilitada: true, codigo: null, mensaje: null, autor: 'Marc' });
    assert.equal((await app.inject({ method: 'POST', url: '/api/cashflow/apuntes', headers: { ...H, 'content-type': 'application/json' }, payload: '{}' })).statusCode, 401);
    assert.equal((await app.inject({ method: 'POST', url: '/api/cashflow/apuntes', headers: { ...H, cookie, 'content-type': 'application/json' }, payload: '{}' })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: '/api/cashflow/apuntes', headers: { ...W, 'content-type': 'application/x-www-form-urlencoded' }, payload: 'a=1' })).statusCode, 415);
    assert.equal((await app.inject({ method: 'DELETE', url: `/api/cashflow/apuntes/e7a00000-0000-4000-8000-000000000101`, headers: W })).statusCode, 405);
    assert.equal((await app.inject({ method: 'PATCH', url: `/api/cashflow/apuntes/e7a00000-0000-4000-8000-000000000101/anular`, headers: W, payload: '{}' })).statusCode, 405);
    assert.ok(esEscrituraCashflow('PUT', '/api/cashflow/recurrentes/b7a00000-0000-4000-8000-000000000201/anular') && !esEscrituraCashflow('PUT', '/api/cashflow/apuntes/x/anular') && !esEscrituraCashflow('POST', '/api/cashflow'));
  });

  test('alta: suelto (201, autor Marc, farmacia de la cuenta); errores con los códigos de la BD y su campo; recurrente con concepto nuevo', async () => {
    const r = await post('/api/cashflow/apuntes', cuerpo());
    assert.equal(r.statusCode, 201);
    assert.deepEqual([r.json().apunte.autor, r.json().apunte.farmacia, r.json().apunte.importe], ['Marc', 'PIO', 99]);
    const e = (await post('/api/cashflow/apuntes', cuerpo({ fecha: '2026-11-10' }))).json();
    assert.deepEqual([e.error, e.campo], ['FECHA_NO_FUTURA', 'fecha']);
    assert.match(e.mensaje, /Solo fechas futuras/);
    assert.equal((await post('/api/cashflow/apuntes', cuerpo({ concepto: 'Inventado' }))).json().error, 'CONCEPTO_DESCONOCIDO');
    assert.equal((await post('/api/cashflow/apuntes', cuerpo({ concepto: null, concepto_nuevo: { nombre: 'mantenimiento  ASCENSOR' } }))).json().error, 'CONCEPTO_YA_EXISTE');
    assert.equal((await post('/api/cashflow/apuntes', cuerpo({ importe: 'mucho' }))).json().error, 'DATOS_NO_VALIDOS');
    const n = await post('/api/cashflow/apuntes', cuerpo({ tipo: 'RECURRENTE', concepto: null, concepto_nuevo: { nombre: 'Seguro del local', proveedor_cif: null }, importe: 600, fecha: null, frecuencia: 'ANUAL', dia: 31, inicio: '2027-06-30', fin: null }));
    assert.equal(n.statusCode, 201, n.body);
    assert.deepEqual([n.json().concepto.nombre, n.json().recurrente.inicio, n.json().recurrente.dia], ['Seguro del local', '2027-06-30', 31]);
    const d = await get();
    assert.deepEqual([d.previsiones.apuntes.length, d.previsiones.conceptos.length, d.previsiones.ocurrencias.filter((o: { recurrente_id: string }) => o.recurrente_id === n.json().recurrente.id).map((o: { fecha: string }) => o.fecha)],
      [5, 2, ['2027-06-30', '2028-06-30', '2029-06-30']]);
  });

  test('anular con motivo obligatorio; lo anulado no se reabre; anular una ocurrencia; editar = anular + crear; anular un recurrente anula sus ocurrencias', async () => {
    const id = 'e7a00000-0000-4000-8000-000000000101';
    assert.equal((await put(`/api/cashflow/apuntes/${id}/anular`, { motivo: '  ' })).json().error, 'MOTIVO_ANULACION_AUSENTE');
    const a = await put(`/api/cashflow/apuntes/${id}/anular`, { motivo: 'Ya no se hace' });
    assert.deepEqual([a.statusCode, a.json().anulado.anulado, a.json().anulado.motivo_anulacion, a.json().anulado.anulado_por], [200, true, 'Ya no se hace', 'Marc']);
    assert.equal((await put(`/api/cashflow/apuntes/${id}/anular`, { motivo: 'otra vez' })).json().error, 'SOLO_ANULAR');
    const rid = 'b7a00000-0000-4000-8000-000000000201';
    const o = await post(`/api/cashflow/recurrentes/${rid}/anular-ocurrencia`, { fecha_ocurrencia: '2027-02-28', motivo: 'Febrero sin cuota' });
    assert.deepEqual([o.statusCode, o.json().apunte.importe, o.json().apunte.recurrente_id, o.json().apunte.nota, o.json().apunte.cuenta], [201, null, rid, 'Febrero sin cuota', 'RITA']);
    assert.equal((await post(`/api/cashflow/recurrentes/${rid}/anular-ocurrencia`, { fecha_ocurrencia: '2027-02-28', motivo: 'x' })).json().error, 'OCURRENCIA_NO_VALIDA');
    assert.equal((await post(`/api/cashflow/recurrentes/${rid}/anular-ocurrencia`, { fecha_ocurrencia: '2027-02-27', motivo: 'x' })).json().error, 'OCURRENCIA_NO_VALIDA');
    const suelto = (await get()).previsiones.apuntes.find((x: ApunteCashflow) => x.nota === 'Prueba' && !x.anulado);
    const ed = await post('/api/cashflow/apuntes/editar', { anterior: { tabla: 'APUNTE', id: suelto.id }, motivo: 'Importe corregido', alta: cuerpo({ importe: 120 }) });
    assert.equal(ed.statusCode, 201, ed.body);
    assert.deepEqual([ed.json().anulado.motivo_anulacion, ed.json().apunte.importe], ['Importe corregido', 120]);
    assert.equal((await post('/api/cashflow/apuntes/editar', { anterior: { tabla: 'APUNTE', id: suelto.id }, alta: cuerpo() })).json().error, 'MOTIVO_ANULACION_AUSENTE');
    const ar = await put(`/api/cashflow/recurrentes/${rid}/anular`, { motivo: 'Contrato cancelado' });
    assert.equal(ar.statusCode, 200);
    assert.equal((await get()).previsiones.ocurrencias.filter((x: { recurrente_id: string }) => x.recurrente_id === rid).length, 0);
  });

  test('sustitución: solo si la factura es candidata (mismo concepto, decena, ±5 %); anula el apunte con el vencimiento; un vencimiento, una sola vez', async () => {
    const F2 = 'f0000000-0000-4000-8000-000000000002';
    const lejos = (await post('/api/cashflow/apuntes', cuerpo({ categoria: 'RS Proveedores', concepto: 'ALLIANCE', importe: 300, fecha: '2026-11-15' }))).json().apunte;
    assert.equal((await post('/api/cashflow/sustituciones', { apunte_id: lejos.id, factura_id: F2, vencimiento_orden: 1 })).json().error, 'SUSTITUCION_NO_CANDIDATA');
    const cerca = (await post('/api/cashflow/apuntes', cuerpo({ categoria: 'RS Proveedores', concepto: 'ALLIANCE', importe: 460, fecha: '2026-11-15' }))).json().apunte;
    const s = await post('/api/cashflow/sustituciones', { apunte_id: cerca.id, factura_id: F2, vencimiento_orden: 1 });
    assert.equal(s.statusCode, 201, s.body);
    assert.deepEqual([s.json().apunte.anulado, s.json().apunte.sustituido_factura_id, s.json().apunte.sustituido_vencimiento_orden], [true, F2, 1]);
    assert.match(s.json().apunte.motivo_anulacion, /^Sustituido por la factura AL-26-100577/);
    assert.equal((await post('/api/cashflow/sustituciones', { apunte_id: lejos.id, factura_id: F2, vencimiento_orden: 1 })).json().error, 'VENCIMIENTO_YA_SUSTITUYE');
    assert.equal((await post('/api/cashflow/sustituciones', { apunte_id: 'x', factura_id: F2, vencimiento_orden: 1 })).json().error, 'DATOS_NO_VALIDOS');
    await put(`/api/cashflow/apuntes/${lejos.id}/anular`, { motivo: 'Limpieza de la prueba' });
  });
});

describe('H7-AP1: REAL sin la credencial de Cashflow', () => {
  test('la lectura sigue (previsiones de cf_lectura); escribir responde 503 con «Falta configurar la credencial de Cashflow»', async () => {
    const datos = leerSemillaCashflow();
    const app = Fastify();
    const vencs = await crearAdaptadorFixtures().vencimientos();
    const pagos = crearAlmacenPagos(leerSemillaPagos());
    registrarCashflow(app, {
      modo: 'REAL', hoy: () => datos.hoy, sesionValida: () => true, almacen: almacenSinEscritura(),
      leerReal: async () => ({ ...datos, previsiones: previsionesVacias(datos.hoy) }),
      pantallaPagos: async () => construirPantalla(vencs, pagos.fuente(), { hoy: pagos.hoy, modo: 'REAL' }),
    });
    const d = (await app.inject({ method: 'GET', url: '/api/cashflow' })).json();
    assert.deepEqual([d.escritura_cashflow.habilitada, d.escritura_cashflow.codigo], [false, 'CREDENCIAL_CASHFLOW_AUSENTE']);
    assert.match(d.escritura_cashflow.mensaje, /Falta configurar la credencial de Cashflow/);
    const W = { host: '127.0.0.1:4747', origin: 'http://127.0.0.1:4747', 'content-type': 'application/json' };
    const r = await app.inject({ method: 'POST', url: '/api/cashflow/apuntes', headers: W, payload: JSON.stringify(alta({ fecha: '2027-02-05' })) });
    assert.deepEqual([r.statusCode, r.json().error], [503, 'CREDENCIAL_CASHFLOW_AUSENTE']);
    // REAL sin previsiones en la lectura: falla cerrado.
    const mal = Fastify();
    registrarCashflow(mal, { modo: 'REAL', hoy: () => datos.hoy, leerReal: async () => datos, pantallaPagos: async () => construirPantalla(vencs, pagos.fuente(), { hoy: pagos.hoy, modo: 'REAL' }) });
    assert.equal((await mal.inject({ method: 'GET', url: '/api/cashflow' })).statusCode, 500);
  });
});
