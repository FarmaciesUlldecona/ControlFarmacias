// H3b: comprueba los DTO ficticios de web/fixtures/dto/ contra el contrato y las reglas de la web.
// No conecta a nada. Código de salida 0 = todo OK; 1 = algún FAIL.
//
// Uso: node web/fixtures/scripts/check_fixtures.mjs   (o `npm run fixtures:check` en web/app)
import { existsSync, readFileSync } from 'node:fs';
import { isDeepStrictEqual } from 'node:util';
import { join } from 'node:path';
import {
  CONSULTAS, CONSULTAS_CHECK, CONSULTAS_POR_BLOQUE, OBJETOS_PERMITIDOS, OBJETOS_VETADOS, PAGO_SIN_DATOS,
  gruposDuplicadoFarmatic, idProveedorR9, numeroAlbaranBase,
  TEXTO_INCIDENCIA, cifFactura, etiquetaYAlias, grupoProveedor, normalizarCif, resumenDuplicados, resumenPar08C66676,
  CATEGORIAS_TIPO_DOCUMENTAL, CODIGOS_SOLO_DETALLE, TEXTO_SIN_TRADUCCION, categoriaTipoDocumental, sentidoDocumental, textoIncidencia,
  construirAtencion, DIAS_ALERTA_SIN_FACTURA, GRUPOS_SIN_FACTURA, TRASPASOS_ENTRE_FARMACIAS, literalFarmaticSinPrefijo, BANCO_SIN_DATOS,
} from '../../app/server/contrato.ts';
import {
  bandejaAlbaranes, cabeceraAlbaranes, claveNombreProveedor, coberturaProveedores, marcaAlbaranes, recuentoAlertas, resumenDoble,
} from '../../app/server/conciliacion.ts';
import { FICHEROS_DTO } from '../../app/server/adaptador_fixtures.ts';
import { ETIQUETAS_CLASE_NUMERO, ETIQUETAS_ESTADO_MATCHING, PDF_ORIGINAL, resumenCasado, vencimientoProximo } from '../../app/server/contrato.ts';
import {
  DICCIONARIO_CASADO, RELACION_CASADO, agruparLineas, avisosFactura, baseAlbaran, canonicalizarProveedor, claveCasado, claveRelacion,
  ESTADOS_MATCHING, ESTADOS_VERSION_ANTERIOR, ESTADO_LINEA, TEXTO_HEFAME_BASES, claveEstadoLinea, estadoSinDescripcion, coincideImporte, esEco360, insigniasFactura, origenAplicado, rangoImporteBuscado, textoEstadoMatching, textoEvento,
  codigoReglaDesconocido,
} from '../../app/server/detalle.ts';
import { COLUMNAS_SENTIDO, validarDiagnostico } from '../../app/server/adaptador_real.ts';
import {
  CATEGORIAS, CONVENIO_ANUAL, FUENTE_VACACIONES, HORARIO_COMPLETA, HORAS_VISTA_COMPLETA, JORNADAS, VACACIONES_DIAS_NATURALES, esTitular, objetivosAnuales,
  validarAjuste, validarTrabajadora,
} from '../../app/server/rrhh/contrato.ts';
import { crearAdaptadorRrhhFixtures, leerSemilla, leerSemillaAjustes, leerSemillaEventos } from '../../app/server/rrhh/adaptador_fixtures.ts';
import { SQL as SQL_RRHH } from '../../app/server/rrhh/adaptador_real.ts';
import {
  AVISO_NOTA_VACIA, COLOR_TIPO_EVENTO, FRANJAS_DE_JORNADA, LARGO_NOTA, TIPOS_EVENTO, TIPOS_PINTABLES, TIPOS_SIN_HORAS, describirCambio, esLaborable, horasFranja,
  horasQueSuman, leerNota, validarPeticionEventos,
} from '../../app/server/rrhh/eventos.ts';
import { traducirErrorBd } from '../../app/server/rrhh/errores_bd.ts';
import { COLOR_FARMACIA_GUARDIA, FARMACIAS_GUARDIA, HORAS_SERVICIO, reglasSemana, validarFestivo } from '../../app/server/rrhh/guardias.ts';
import { leerSemillaFichaAnual } from '../../app/server/rrhh/adaptador_fixtures.ts';
import { AVISO_VACACIONES_DESDE, REDONDEO_PROPORCIONAL, TIPOS_HORAS_COMPUTAN, calcularFichaAnual, resumenPlantilla } from '../../app/server/rrhh/ficha_anual.ts';
import { COMERCIAL_POR_CIF, COMERCIAL_POR_LITERAL, nombreComercial, razonSocialSecundaria } from '../../app/server/proveedor_comercial.ts';
import { DEVOLUCIONES_H8_6, ULTIMA_FACTURA_ALLIANCE_H8_6 } from './gen_fixtures.mjs';
import { NOTA_ABONO_EN_BLOQUE, PROVEEDORES_ABONO_EN_BLOQUE, clasificarAbonoEnBloque } from '../../app/server/contrato.ts';
import { ALERTA_DUPLICADO, F05_SIN_TIPO_DOCUMENTAL, INCIDENCIAS_H4B, INCIDENCIAS_H4D, TIPO_DOCUMENTAL_H4C, VENCIMIENTOS_H6_3, generar } from './gen_fixtures.mjs';
import {
  DICCIONARIO_ESTADOS, ESTADOS_IMPLEMENTADOS, MENSAJE_FALTA_CREDENCIAL_PAGOS, construirPantalla, crearAlmacenPagos, totalesPorPeriodo,
} from '../../app/server/pagos/pagos.ts';
import { SQL_PAGOS } from '../../app/server/pagos/sql.ts';
import { leerSemillaPagos } from '../../app/server/pagos/rutas.ts';
import { agregar as agregarCalendario, resumenAnio, sinFecha as sinFechaCalendario } from '../../app/server/pagos/calendario.ts';
import { PESTANAS_VENCIMIENTOS, cumpleBusquedaLista } from '../../app/server/pagos/lista.ts';
import {
  CONFIG_CASHFLOW, calcularCashflow, columnasVista, esDecenaInicio, finDecena, resolverEquivalencias, traspasosNoCompensados,
} from '../../app/server/cashflow/cashflow.ts';
import { vencimientoCashflow } from '../../app/server/cashflow/rutas.ts';
import { FILAS_EQUIVALENTES, FUERA_HORIZONTE, PAGO_HACE_8_MESES, RUTA_CASHFLOW, generarCashflow, serializarCashflow } from './gen_cashflow.mjs';

const RAIZ = join(import.meta.dirname, '..');
const DTO = join(RAIZ, 'dto');
const h3a = (n) => JSON.parse(readFileSync(join(RAIZ, `v_web_${n}.json`), 'utf8'));
const F = (n) => `f0000000-0000-4000-8000-0000000000${String(n).padStart(2, '0')}`;

const resultados = [];
function comprobar(nombre, fn) {
  try {
    const r = fn();
    resultados.push([r === true ? 'OK' : 'FAIL', nombre, r === true ? '' : String(r)]);
  } catch (e) {
    resultados.push(['FAIL', nombre, e instanceof Error ? e.message : String(e)]);
  }
}
const si = (cond, msg) => (cond ? true : msg);

/** Recorre un valor JSON llamando a fn(clave, valor, ruta). */
function recorrer(v, fn, ruta = '$') {
  if (Array.isArray(v)) v.forEach((x, i) => recorrer(x, fn, `${ruta}[${i}]`));
  else if (v && typeof v === 'object') for (const [k, x] of Object.entries(v)) { fn(k, x, `${ruta}.${k}`); recorrer(x, fn, `${ruta}.${k}`); }
}

// --- Carga -------------------------------------------------------------------
const dto = {};
for (const [bloque, fichero] of Object.entries(FICHEROS_DTO)) {
  comprobar(`existe dto/${fichero} (${bloque})`, () => si(existsSync(join(DTO, fichero)), 'no existe'));
  if (existsSync(join(DTO, fichero))) dto[bloque] = JSON.parse(readFileSync(join(DTO, fichero), 'utf8'));
}
const { inicio, facturas, facturaDetalle, conciliacionBandeja, vencimientos, proveedores, configuracion } = dto;

// --- Contrato ------------------------------------------------------------------
// H7: el bloque cashflowSemanas de H3a se retira (la pantalla Cashflow tiene su propio contrato): 7 bloques.
comprobar('los 7 bloques del contrato tienen fichero (sin el cashflow semanal de H3a)', () => si(Object.keys(FICHEROS_DTO).length === 7 && Object.keys(CONSULTAS_POR_BLOQUE).length === 7
  && !('cashflowSemanas' in FICHEROS_DTO) && !('cashflowSemanas' in CONSULTAS_POR_BLOQUE), 'faltan o sobran bloques'));
comprobar('DTO al día: idénticos a regenerarlos con el contrato', () => {
  const nuevos = generar();
  const distintos = Object.entries(FICHEROS_DTO).filter(([b, f]) => !isDeepStrictEqual(nuevos[f], dto[b])).map(([, f]) => f);
  return si(distintos.length === 0, `desactualizados: ${distintos.join(', ')} (ejecuta fixtures:gen)`);
});
comprobar('consultas: solo objetos de la lista cerrada 2BN, sin v_dashboard_diario', () => {
  const malos = [];
  for (const [n, c] of Object.entries({ ...CONSULTAS, ...CONSULTAS_CHECK })) {
    for (const o of c.objetos) if (!OBJETOS_PERMITIDOS.includes(o) || OBJETOS_VETADOS.includes(o)) malos.push(`${n}:${o}`);
    // Toda referencia public.<objeto> del SQL debe estar declarada y permitida.
    for (const m of c.sql.matchAll(/public\.([a-z_]+)/g)) if (!c.objetos.includes(m[1])) malos.push(`${n}:${m[1]} (no declarado)`);
    if (/resultado_json|v_dashboard_diario|service_role/.test(c.sql)) malos.push(`${n}: texto vetado`);
    if (/\b(insert|update|delete|truncate|grant|alter|create|drop)\b/i.test(c.sql)) malos.push(`${n}: escritura`);
    if (/public\.cf_[a-z_]+\s*\(/.test(c.sql)) malos.push(`${n}: llama a una función de BD`);
    if (!/\$1/.test(c.sql) || !/cross join hab/.test(c.sql)) malos.push(`${n}: sin filtro de farmacia/habilitación`);
  }
  return si(malos.length === 0, malos.join('; '));
});

// --- Reglas transversales ------------------------------------------------------
// H8-4 (decisión A de Marc): única excepción, acotada: en los albaranes de PIO, la otra farmacia figura como proveedor de
// Farmatic (traspaso). Solo en sin_factura.traspasos[i], solo farmacia_origen y proveedor, y solo con los valores de
// TRASPASOS_ENTRE_FARMACIAS (farmacia y literal sin prefijo). Cualquier otro RITA sigue fallando.
const RUTA_TRASPASO = /^\$\.conciliacionBandeja\.sin_factura\.traspasos\[\d+\]\.(farmacia_origen|proveedor)$/;
const valorTraspasoPermitido = (ruta, v) => RUTA_TRASPASO.test(ruta)
  && TRASPASOS_ENTRE_FARMACIAS.some((t) => v === t.farmacia || v === literalFarmaticSinPrefijo(t.literal_farmatic));
comprobar('farmacia: solo PIO (ningún RITA; excepción acotada: traspasos entre farmacias)', () => {
  const malos = [];
  recorrer(dto, (k, v, ruta) => {
    if ((k === 'farmacia' || k === 'farmacia_activa') && v !== 'PIO') malos.push(ruta);
    if (typeof v === 'string' && /\bRITA\b/.test(v) && !valorTraspasoPermitido(ruta, v)) malos.push(ruta);
  });
  return si(malos.length === 0, malos.slice(0, 5).join(', '));
});
comprobar('nunca resultado_json en los DTO', () => {
  const malos = [];
  recorrer(dto, (k, _v, ruta) => { if (k === 'resultado_json') malos.push(ruta); });
  return si(malos.length === 0, malos.join(', '));
});
comprobar('estado de pago: siempre gris, "sin datos bancarios"', () => {
  const malos = [];
  recorrer(dto, (k, v, ruta) => { if (k === 'pago' && !isDeepStrictEqual(v, PAGO_SIN_DATOS)) malos.push(ruta); });
  return si(malos.length === 0, malos.join(', '));
});
comprobar('tres estados separados en cada factura', () => {
  const todas = [...facturas.facturas, ...conciliacionBandeja.facturas, ...Object.values(facturaDetalle).map((d) => d.factura)];
  const malas = todas.filter((f) => !f.estado_normalizacion || !f.estado_conciliacion_cf || !f.estado_revision);
  return si(malas.length === 0, malas.map((f) => f.factura_id).join(', '));
});
comprobar('tolerancia y diferencia: las del motor (sin recalcular)', () => {
  const fuente = new Map(h3a('factura_detalle').map((r) => [r.factura_id, r]));
  const malas = [];
  for (const f of [...facturas.facturas, ...conciliacionBandeja.facturas, ...Object.values(facturaDetalle).map((d) => d.factura)]) {
    const r = fuente.get(f.factura_id);
    const c = f.conciliacion;
    if (!r) { malas.push(`${f.factura_id}: sin fuente`); continue; }
    if ((r.conciliacion_id ?? null) === null ? c !== null
      : (c.tolerancia !== r.conciliacion_tolerancia || c.diferencia !== r.conciliacion_diferencia
        || !isDeepStrictEqual(c.tolerancia_regla, r.conciliacion_tolerancia_regla))) malas.push(f.factura_id);
  }
  return si(malas.length === 0, malas.join(', '));
});

// --- Importe ausente = null, nunca 0 --------------------------------------------
comprobar('F06: importe_total null en facturas, detalle y bandeja', () => {
  const f06 = [facturas.facturas.find((f) => f.factura_id === F(6)), facturaDetalle[F(6)]?.factura, conciliacionBandeja.facturas.find((f) => f.factura_id === F(6))];
  return si(f06.every((f) => f && f.importe_total === null), JSON.stringify(f06.map((f) => f?.importe_total)));
});
comprobar('F04: 3 vencimientos de H3a (el 3.º sin importe, importe_conocido=false) + 1 negativo «a cuenta» de H6-3', () => {
  const v = vencimientos.vencimientos.filter((x) => x.factura_id === F(4)).sort((a, b) => a.orden - b.orden);
  return si(v.length === 4 && v[0].importe === 400 && v[1].importe === 150 && v[2].importe === null && v[2].importe_conocido === false
    && v[3].importe === -25 && v.every((x) => x.vencimientos_factura === 4), JSON.stringify(v.map((x) => x.importe)));
});
comprobar('vencimientos: totales con nulls contados aparte', () => {
  const t = vencimientos.totales;
  return si(t.sin_importe === vencimientos.vencimientos.filter((x) => x.importe === null).length && t.sin_importe >= 2, JSON.stringify(t));
});
// H7: las comprobaciones del cashflow semanal de H3a (v_web_cashflow_semanal) se retiran con su bloque; el cashflow
// nuevo se comprueba en «Casos H7».
comprobar('abono F07: total y vencimiento con signo impreso (−45,30)', () => {
  const f = facturas.facturas.find((x) => x.factura_id === F(7));
  const v = vencimientos.vencimientos.find((x) => x.factura_id === F(7));
  return si(f.tipo_documento === 'ABONO' && f.importe_total === -45.3 && v.importe === -45.3, 'abono mal');
});

// --- Inicio --------------------------------------------------------------------
comprobar('inicio: contadores de facturas iguales a H3a (3 ejes separados)', () => {
  const r = h3a('inicio_resumen')[0];
  const o = inicio;
  const pares = [
    [o.facturas.total, r.facturas], [o.requieren_revision, r.requieren_revision],
    [o.normalizacion.PENDIENTE, r.norm_pendiente], [o.normalizacion.NORMALIZANDO, r.norm_en_curso],
    [o.normalizacion.NORMALIZADA, r.norm_ok], [o.normalizacion.REQUIERE_REVISION, r.norm_revision],
    [o.conciliacion.PENDIENTE_CONCILIAR, r.conc_pendiente], [o.conciliacion.CONCILIADA, r.conc_ok],
    [o.conciliacion.REVISION_CONCILIACION, r.conc_revision], [o.conciliacion.NO_APLICA, r.conc_no_aplica],
    [o.revision.NO_REQUERIDA, r.rev_no_requerida], [o.revision.PENDIENTE_REVISION_PIO, r.rev_pendiente],
    [o.revision.VALIDADA_PIO, r.rev_validada], [o.facturas.sin_importe, r.facturas_sin_importe],
    [o.facturas.importe_total_conocido, r.importe_total_conocido], [o.documentos.pendientes_procesar, r.pendientes_procesar],
  ];
  const malos = pares.map(([a, b], i) => (a === b ? null : `#${i}: ${a}≠${b}`)).filter(Boolean);
  return si(malos.length === 0, malos.join(', '));
});
comprobar('inicio (1A): "Documentos con defecto" = ERROR + REVISION (1 + 1)', () => {
  const d = inicio.documentos;
  return si(d.con_defecto === d.por_estado.ERROR + d.por_estado.REVISION && d.por_estado.ERROR === 1 && d.por_estado.REVISION === 1 && d.con_defecto === 2, JSON.stringify(d));
});
comprobar('inicio (1A): "Sin automatizar" = PROVEEDOR_NO_SOPORTADO (4), aparte de con defecto', () => {
  const d = inicio.documentos;
  return si(d.sin_automatizar === d.por_estado.PROVEEDOR_NO_SOPORTADO && d.sin_automatizar === 4 && !('documentos_sin_leer' in d), JSON.stringify(d));
});
const grupo = (clave) => inicio.atencion.grupos.find((g) => g.clave === clave);
const casosAtencion = inicio.atencion.grupos.flatMap((g) => g.casos.map((c) => ({ ...c, grupo: g })));
/** H4d-2: códigos solo de detalle (decisión de Pío), escritos aquí a mano para no depender del contrato. */
const SOLO_DETALLE = ['MONEDA_NO_DOCUMENTADA', 'REPRESENTACIONES_CONSOLIDADAS', 'FILAS_DUPLICADAS_EVIDENCIA_IDENTICA',
  'FILA_IMPORTE_CERO_INFORMATIVA', 'ALBARANES_CONSUMIBLES_SOLO_REFERENCIA_DOCUMENTAL'];
/** Incidencias abiertas que deben salir en Inicio: sin INFO ni códigos solo de detalle. */
const abiertasInicio = [...h3a('incidencias'), ...INCIDENCIAS_H4B, ...INCIDENCIAS_H4D]
  .filter((i) => i.estado === 'ABIERTA' && i.severidad !== 'INFO' && !SOLO_DETALLE.includes(i.codigo));
comprobar('inicio (1A): atención — con defecto en rojo (2); los PDF sin automatizar no salen (H4d-2), solo en su contador gris (4)', () => {
  const def = grupo('DOCUMENTOS_DEFECTO');
  return si(def?.casos.length === 2 && def.color === 'rojo' && !grupo('SIN_AUTOMATIZAR')
    && !casosAtencion.some((c) => c.codigo === 'PROVEEDOR_NO_SOPORTADO') && inicio.documentos.sin_automatizar === 4,
  JSON.stringify(inicio.atencion.grupos.map((g) => [g.clave, g.color, g.casos.length])));
});
comprobar('inicio: incidencias abiertas = las ABIERTA sin INFO ni MONEDA_NO_DOCUMENTADA (documento + factura)', () =>
  si(inicio.incidencias.abiertas === abiertasInicio.length && inicio.incidencias.abiertas === 13
    && inicio.incidencias.bloqueantes === abiertasInicio.filter((i) => i.bloqueante).length, JSON.stringify(inicio.incidencias)));
comprobar('inicio: luna del mes (F06, 0,0184 €)', () => si(inicio.luna_mes.ejecuciones === 1 && inicio.luna_mes.coste === 0.0184, JSON.stringify(inicio.luna_mes)));

// --- Casos H3a mantenidos --------------------------------------------------------
comprobar('H3a: F01–F08 presentes con detalle propio', () => {
  const ids = Array.from({ length: 8 }, (_, i) => F(i + 1));
  const faltan = ids.filter((id) => !facturas.facturas.some((f) => f.factura_id === id) || !facturaDetalle[id]);
  return si(faltan.length === 0 && Object.keys(facturaDetalle).length === facturas.facturas.length, `faltan ${faltan.join(', ')}`);
});
comprobar('H3a: multifactura D03 → F03 + F04', () => {
  const d3 = 'd0000000-0000-4000-8000-000000000003';
  return si(facturas.facturas.filter((f) => f.documento_id === d3).length === 2, 'D03 sin 2 facturas');
});
comprobar('H3a: F02 conciliada con diferencia dentro de R11 (0,07 ≤ 0,08 del motor)', () => {
  const c = facturas.facturas.find((f) => f.factura_id === F(2)).conciliacion;
  return si(c.resultado === 'CONCILIADA' && c.diferencia === 0.07 && c.tolerancia === 0.08, JSON.stringify(c));
});
comprobar('H3a: F03 DIFERENCIA 41,90; F05 REVISION_CONCILIACION', () => {
  const f3 = facturas.facturas.find((f) => f.factura_id === F(3));
  const f5 = facturas.facturas.find((f) => f.factura_id === F(5));
  return si(f3.conciliacion.resultado === 'DIFERENCIA' && f3.conciliacion.diferencia === 41.9 && f5.estado_conciliacion_cf === 'REVISION_CONCILIACION', 'mal');
});
comprobar('H3a: F07 movimiento NO_EVALUABLE con importe_aplicado null', () => {
  const l = facturaDetalle[F(7)].lineas.find((x) => x.tipo_relacion === 'MOVIMIENTO_NO_FARMATIC');
  return si(l && l.estado_linea === 'NO_EVALUABLE' && l.importe_aplicado === null && l.sentido_documental === null, JSON.stringify(l));
});
comprobar('H3a: posible duplicado F01 + F08 (incidencia)', () =>
  si([F(1), F(8)].every((id) => facturaDetalle[id].incidencias.some((i) => i.codigo === 'POSIBLE_DUPLICADO')), 'sin incidencia'));
comprobar('H3a: albaranes no localizados (SIN_COINCIDENCIA) en F03 y F05', () =>
  si([F(3), F(5)].every((id) => facturaDetalle[id].lineas.some((l) => l.tipo_relacion === 'SIN_COINCIDENCIA')), 'falta'));

// --- Casos nuevos H3b -------------------------------------------------------------
const alertas = (tipo) => inicio.alertas.filter((a) => a.tipo === tipo);
comprobar('H3b: alerta albarán facturado no en Farmatic (rojo, con factura, VALIDADA)', () => {
  const a = alertas('ALBARAN_FACTURADO_NO_EN_FARMATIC');
  return si(a.length >= 1 && a.every((x) => x.color === 'rojo' && x.factura_id && x.id_contadores.length === 1 && x.validacion === 'VALIDADA'), JSON.stringify(a));
});
comprobar('H3d regla B: 08C66676 = 08C66676A (mismo proveedor R9 y mismo importe) → una alerta VALIDADA naranja en Inicio y bandeja', () => {
  const malos = [];
  for (const [nombre, d] of [['inicio', inicio], ['bandeja', conciliacionBandeja]]) {
    const a = d.alertas.filter((x) => x.tipo === 'POSIBLE_DUPLICADO_FARMATIC');
    if (!(a.length === 1 && a[0].validacion === 'VALIDADA' && a[0].color === 'naranja' && a[0].numero_albaran === '08C66676'
      && isDeepStrictEqual(a[0].id_contadores, [900301, 900302]) && a[0].detalle.importe_puc === 57.4)) malos.push(`${nombre}: ${JSON.stringify(a)}`);
  }
  return si(malos.length === 0 && CONSULTAS_POR_BLOQUE.inicio.includes('alertas_duplicado_farmatic')
    && CONSULTAS_POR_BLOQUE.conciliacionBandeja.includes('alertas_duplicado_farmatic'), malos.join('; ') || 'consulta ausente en algún bloque');
});
comprobar('H3d regla B: 08C70015 / 08C70015A con distinto importe → sin alerta', () => {
  const con = [...inicio.alertas, ...conciliacionBandeja.alertas].filter((x) => x.id_contadores.some((n) => n === 900311 || n === 900312));
  return si(con.length === 0, JSON.stringify(con));
});
comprobar('H3d regla B: funciones puras (letra final, R9, importe null no cumple)', () => {
  const alb = (id, numero, prov, imp) => ({ id_contador: id, numero_albaran: numero, id_proveedor: prov, proveedor: null, fecha: null, importe_puc: imp });
  const casos = [
    [numeroAlbaranBase(' 08c66676a '), '08C66676'],
    [numeroAlbaranBase('08C66676'), '08C66676'],
    [idProveedorR9('0002'), '2'], [idProveedorR9('000'), '0'], [idProveedorR9('  '), null],
    [gruposDuplicadoFarmatic([alb(1, '08C1', '02', 5), alb(2, '08C1A', '2', 5)]).length, 1],
    [gruposDuplicadoFarmatic([alb(1, '08C1', '2', 5), alb(2, '08C1A', '2', 6)]).length, 0],
    [gruposDuplicadoFarmatic([alb(1, '08C1', '2', null), alb(2, '08C1A', '2', null)]).length, 0],
    [gruposDuplicadoFarmatic([alb(1, '08C1', '2', 5), alb(2, '08C1A', '3', 5)]).length, 0],
    [gruposDuplicadoFarmatic([alb(1, '08C1', null, 5), alb(2, '08C1A', null, 5)]).length, 0],
  ];
  const malos = casos.map(([a, b], i) => (a === b ? null : `#${i}: ${a}≠${b}`)).filter(Boolean);
  return si(malos.length === 0, malos.join(', '));
});
comprobar('ninguna alerta PENDIENTE_VALIDAR (todas las reglas actuales validadas)', () => {
  const pend = [...inicio.alertas, ...conciliacionBandeja.alertas].filter((x) => x.validacion !== 'VALIDADA');
  return si(pend.length === 0, JSON.stringify(pend));
});
comprobar('H3b: correcciones aprobadas (aplicada verde, pendiente azul)', () => {
  const a = alertas('CORRECCION_APROBADA');
  return si(a.some((x) => x.color === 'verde') && a.some((x) => x.color === 'azul'), JSON.stringify(a.map((x) => x.color)));
});
comprobar('alertas de Inicio = alertas validadas de la bandeja', () =>
  si(isDeepStrictEqual(inicio.alertas, conciliacionBandeja.alertas.filter((x) => x.validacion === 'VALIDADA')), 'distintas'));
comprobar('inicio: atención incluye cada incidencia abierta (lenguaje llano) y las de factura enlazan a su factura', () => {
  const deIncidencia = ['INCIDENCIA_ERROR', 'INCIDENCIA_AVISO'];
  const items = casosAtencion.filter((c) => deIncidencia.includes(c.grupo.categoria) && c.codigo !== 'REQUIERE_REVISION');
  const sinTexto = casosAtencion.filter((c) => !c.texto);
  const facturaMal = abiertasInicio.filter((i) => i.factura_id && !casosAtencion.some((c) => c.factura_id === i.factura_id && c.codigo === i.codigo && c.enlace === `/facturas/${i.factura_id}`));
  return si(items.length === abiertasInicio.length && sinTexto.length === 0 && facturaMal.length === 0, `${items.length} casos / ${abiertasInicio.length} abiertas`);
});
comprobar('H3b: varios PROVEEDOR_NO_SOPORTADO (≥3) sin factura', () => {
  const pns = facturas.documentos_sin_factura.filter((d) => d.estado_lectura === 'PROVEEDOR_NO_SOPORTADO');
  return si(pns.length >= 3, `${pns.length}`);
});
comprobar('H3b: mapa proveedor×estado cuadra con documentos y tiene PDF sin factura', () => {
  const m = proveedores.mapa_documentos;
  const total = m.filas.reduce((a, f) => a + f.total, 0);
  const sumaCeldas = m.filas.every((f) => Object.values(f.por_estado).reduce((a, n) => a + n, 0) === f.total);
  return si(total === inicio.documentos.total && sumaCeldas && m.filas.filter((f) => f.por_estado.PROVEEDOR_NO_SOPORTADO > 0).length >= 3, JSON.stringify(m.filas.map((f) => [f.proveedor, f.total])));
});
comprobar('proveedores: importes null-aware (FEDEFARMA, sin CIF, sin importe conocido = null)', () => {
  const fed = proveedores.proveedores.find((p) => p.clave === 'id:4');
  return si(fed && fed.sin_cif && fed.etiqueta === 'FEDEFARMA' && fed.importe_total_conocido === null && fed.facturas_sin_importe === 1, JSON.stringify(fed));
});

// --- Casos H4b ---------------------------------------------------------------------
comprobar('H4b/H4c: proveedores agrupados por CIF (nunca proveedor_id); sin CIF por id_proveedor_albaranes R9', () => {
  const ps = proveedores.proveedores;
  const malos = ps.filter((p) => !/^(cif:[A-Z0-9]+|id:[^\s]+|sin_identificar)$/.test(p.clave) || 'id' in p || 'proveedor_id' in p);
  const claves = ps.map((p) => p.clave);
  return si(malos.length === 0 && isDeepStrictEqual(claves, ['cif:B00000003', 'cif:A00000001', 'cif:F30004444', 'id:4'])
    && ps.reduce((a, p) => a + p.facturas, 0) === facturas.facturas.length && !CONSULTAS_POR_BLOQUE.proveedores.includes('proveedores'), JSON.stringify(claves));
});
comprobar('H4b: etiqueta = literal más frecuente del CIF; resto como alias (F02 "b-00000003" normalizado)', () => {
  const al = proveedores.proveedores.find((p) => p.clave === 'cif:B00000003');
  return si(al && al.etiqueta === 'ALLIANCEHEALTHCARECENCORA' && isDeepStrictEqual(al.alias, ['Alliance Healthcare España']) && al.facturas === 3 && !al.sin_cif, JSON.stringify(al));
});
comprobar('H4b: filtro de proveedor de Facturas con el mismo criterio que Proveedores', () => {
  const op = facturas.proveedores_filtro;
  const igual = isDeepStrictEqual(op.map((o) => [o.clave, o.etiqueta, o.sin_cif, o.facturas]), proveedores.proveedores.map((p) => [p.clave, p.etiqueta, p.sin_cif, p.facturas]));
  const todas = facturas.facturas.every((f) => op.some((o) => o.clave === f.proveedor_grupo));
  const f02 = facturas.facturas.find((f) => f.factura_id === F(2));
  return si(igual && todas && f02.proveedor_grupo === 'cif:B00000003', JSON.stringify(op));
});
comprobar('H4b/H4c: funciones puras de CIF (como el motor) y grupo de respaldo R9', () => {
  const casos = [
    [normalizarCif(' b-0000.0003 '), 'B00000003'], [normalizarCif('es/b_00000003'), 'ESB00000003'],
    [normalizarCif('  '), null], [normalizarCif(null), null], [normalizarCif('-.'), null],
    // Precedencia del motor (migración 20): columna si no está vacía; si no, datos_extraidos.
    [cifFactura(null, 'b-00000003'), 'B00000003'], [cifFactura('', 'B00000003'), 'B00000003'],
    [cifFactura('A00000001', 'B00000003'), 'A00000001'], [cifFactura(null, null), null],
    [grupoProveedor('B00000003', '0004').clave, 'cif:B00000003'], [grupoProveedor(null, '0004').clave, 'id:4'],
    [grupoProveedor(null, ' 4 ').clave, 'id:4'], [grupoProveedor(null, 'ABC1').clave, 'id:ABC1'],
    [grupoProveedor('', '  ').clave, 'sin_identificar'], [grupoProveedor(null, null).sin_cif, true],
    [etiquetaYAlias(['B', 'A', 'B', null]).etiqueta, 'B'], [etiquetaYAlias(['B', 'A']).etiqueta, 'A'],
  ];
  const malos = casos.map(([a, b], i) => (a === b ? null : `#${i}: ${a}≠${b}`)).filter(Boolean);
  return si(malos.length === 0, malos.join(', '));
});

// --- Casos H4c ---------------------------------------------------------------------
comprobar('H4c: CIF solo en datos_extraidos (columna vacía, como en producción) y agrupa por él', () => {
  const todas = facturas.facturas;
  const conColumna = todas.filter((f) => f.proveedor_cif !== null);
  const f02 = todas.find((f) => f.factura_id === F(2));
  const det = facturaDetalle[F(2)];
  return si(conColumna.length === 0 && todas.filter((f) => f.proveedor_nif_documental !== null).length === 7
    && f02.proveedor_nif_documental === 'b-00000003' && f02.proveedor_grupo === 'cif:B00000003'
    && det.datos_extraidos.proveedor.nif.valor === 'b-00000003' && det.proveedor.cif === 'B00000003' && det.proveedor.proveedor_cif === null,
  JSON.stringify(todas.map((f) => [f.factura_id.slice(-2), f.proveedor_cif, f.proveedor_nif_documental, f.proveedor_grupo])));
});
comprobar('H4c: consultas leen el CIF de datos_extraidos {proveedor,nif,valor} con la normalización del motor', () => {
  const sql = [CONSULTAS.facturas.sql, CONSULTAS.documentos.sql, CONSULTAS_CHECK.diagnostico_proveedores.sql].join('\n');
  return si(sql.includes("datos_extraidos #>> '{proveedor,nif,valor}'") && sql.includes("'[^A-Z0-9]'") && !sql.includes('[[:space:].-]'), 'sql');
});
comprobar('H4c: sin CIF → grupo de respaldo id_proveedor_albaranes R9 ("0004" → id:4), marcado sin CIF', () => {
  const f06 = facturas.facturas.find((f) => f.factura_id === F(6));
  const op = facturas.proveedores_filtro.find((o) => o.clave === 'id:4');
  return si(f06.proveedor_nif_documental === null && f06.id_proveedor_albaranes === '0004' && f06.proveedor_grupo === 'id:4' && op?.sin_cif === true, JSON.stringify([f06.proveedor_grupo, op]));
});
comprobar('H4c: vencimiento con importe null → la UI dice "importe pendiente" y el total de factura va aparte', () => {
  const v = facturaDetalle[F(4)].vencimientos.find((x) => x.importe === null);
  return si(v && v.importe_conocido === false && v.importe_factura === 568.05 && v.importe === null, JSON.stringify(v));
});
comprobar('H4c-2: regla de sentido de Pío (solo tipo documental; nunca la columna)', () => {
  const casos = [
    [sentidoDocumental('FACTURA'), 'CARGO'], [sentidoDocumental(' factura '), 'CARGO'], [sentidoDocumental('FACTURA_DUPLICADO'), 'CARGO'],
    [sentidoDocumental('ABONO'), 'ABONO'],
    [sentidoDocumental('FACTURA_RECTIFICATIVA'), 'NO_DOCUMENTADO'], [sentidoDocumental('FACTURA RECTIFICATIVA'), 'NO_DOCUMENTADO'],
    [sentidoDocumental('RECTIFICATIVA_ABONO'), 'NO_DOCUMENTADO'],
    [sentidoDocumental(null), 'NO_DOCUMENTADO'], [sentidoDocumental(''), 'NO_DOCUMENTADO'], [sentidoDocumental('  '), 'NO_DOCUMENTADO'],
    [sentidoDocumental('OTRO'), 'NO_DOCUMENTADO'], [sentidoDocumental('PROFORMA'), 'NO_DOCUMENTADO'],
  ];
  const malos = casos.map(([a, b], i) => (a === b ? null : `#${i}: ${a}≠${b}`)).filter(Boolean);
  return si(malos.length === 0, malos.join(', '));
});
comprobar('H4c-2: sentido por factura en fixtures (F08 duplicado cargo, F03 rectificativa, F06 OTRO, F05 vacío, F07 abono)', () => {
  const s = (n) => facturas.facturas.find((f) => f.factura_id === F(n));
  const esperado = { 1: 'CARGO', 2: 'CARGO', 3: 'NO_DOCUMENTADO', 4: 'CARGO', 5: 'NO_DOCUMENTADO', 6: 'NO_DOCUMENTADO', 7: 'ABONO', 8: 'CARGO' };
  const malos = Object.entries(esperado).filter(([n, se]) => s(Number(n)).sentido !== se).map(([n]) => `F0${n}=${s(Number(n)).sentido}`);
  // La columna no decide: F08 tiene la columna en OTRO (persistencia) y es cargo; F03 la tiene en FACTURA_RECTIFICATIVA y no suma.
  return si(malos.length === 0 && s(8).tipo_documento === 'OTRO' && s(8).tipo_documento_documental === 'FACTURA_DUPLICADO'
    && s(6).tipo_documento_documental === 'OTRO' && s(3).tipo_documento === 'FACTURA_RECTIFICATIVA'
    && facturaDetalle[F(8)].datos_extraidos.tipo_documento.valor === 'FACTURA_DUPLICADO'
    && vencimientos.vencimientos.every((v) => v.sentido === s(Number(v.factura_id.slice(-2))).sentido), malos.join(', '));
});
comprobar('H4c-2: diagnóstico tipo_documento con etiquetas fijas (recuentos de las fixtures y SQL)', () => {
  const n = Object.fromEntries(CATEGORIAS_TIPO_DOCUMENTAL.map((c) => [c, 0]));
  for (const f of facturas.facturas) n[categoriaTipoDocumental(f.tipo_documento_documental)] += 1;
  const casos = [
    [categoriaTipoDocumental('Factura_Rectificativa'), 'factura_rectificativa'], [categoriaTipoDocumental('RECTIFICATIVA'), 'factura_rectificativa'],
    [categoriaTipoDocumental(' '), 'vacio_o_null'], [categoriaTipoDocumental(null), 'vacio_o_null'],
    [categoriaTipoDocumental('ALBARAN'), 'otros_valores'], [categoriaTipoDocumental('otro'), 'otro'],
  ];
  const malos = casos.map(([a, b], i) => (a === b ? null : `#${i}: ${a}≠${b}`)).filter(Boolean);
  const sql = CONSULTAS_CHECK.diagnostico_tipo_documento.sql;
  const faltan = ['facturas', ...CATEGORIAS_TIPO_DOCUMENTAL].filter((c) => !sql.includes(`as ${c}`));
  let rechaza = false;
  try { validarDiagnostico({ otros_valores: ['PROFORMA X'] }); } catch { rechaza = true; }
  // Solo el tipo documental; nunca la columna f.tipo_documento.
  return si(malos.length === 0 && faltan.length === 0 && rechaza && sql.includes("{tipo_documento,valor}") && !/\bf\.tipo_documento\b/.test(sql)
    && isDeepStrictEqual(n, { factura: 3, factura_duplicado: 1, abono: 1, factura_rectificativa: 1, otro: 1, vacio_o_null: 1, otros_valores: 0 }),
  `${malos.join(', ')} faltan=${faltan.join(',')} n=${JSON.stringify(n)}`);
});
comprobar('H4c: F05 sin tipo documental → sentido no documentado; nunca suma como cargo ni abono', () => {
  const v = vencimientos.vencimientos.filter((x) => x.factura_id === F05_SIN_TIPO_DOCUMENTAL);
  const t = vencimientos.totales;
  const cargos = vencimientos.vencimientos.filter((x) => x.sentido === 'CARGO' && x.importe !== null).reduce((a, x) => a + x.importe, 0);
  const abonos = vencimientos.vencimientos.filter((x) => x.sentido === 'ABONO' && x.importe !== null).reduce((a, x) => a + x.importe, 0);
  return si(v.length === 1 && v[0].tipo_documento === 'FACTURA' && v[0].tipo_documento_documental === null && v[0].sentido === 'NO_DOCUMENTADO'
    && t.sentido_no_documentado === 4 /* H6-REAL: +V13 de FEDEFARMA */ && t.importe_cargos_conocido === Math.round(cargos * 10000) / 10000 && t.importe_abonos_conocido === abonos
    && facturaDetalle[F05_SIN_TIPO_DOCUMENTAL].vencimientos[0]?.sentido === 'NO_DOCUMENTADO',
  JSON.stringify(t));
});
comprobar('H4c: abono F07 sigue sumando como abono (tipo documental ABONO)', () => {
  // H6-3: F07 tiene dos vencimientos (−45,30 de H3a y −20,00 vencido): los dos suman como abono.
  const vs = vencimientos.vencimientos.filter((x) => x.factura_id === F(7));
  return si(vs.length === 2 && vs.every((v) => v.sentido === 'ABONO') && vencimientos.totales.importe_abonos_conocido === -65.3, JSON.stringify(vs));
});
comprobar('H4c: mapa — PDF con factura por su grupo; sin factura por proveedor_id del catálogo o solo por estado', () => {
  const m = proveedores.mapa_documentos.filas;
  const por = (o) => m.filter((f) => f.origen === o);
  const sinProv = por('SIN_PROVEEDOR');
  const cat = por('CATALOGO');
  const conFacturas = por('FACTURAS').reduce((a, f) => a + f.total, 0);
  const sinFactura = facturas.documentos_sin_factura;
  const esperadosSinProv = sinFactura.filter((d) => d.proveedor_id === null).length;
  const nombresArchivo = new Set(inicio.documentos.total ? sinFactura.map((d) => d.archivo_nombre) : []);
  return si(sinProv.length === 1 && sinProv[0].clave === 'sin_factura_sin_proveedor' && sinProv[0].total === esperadosSinProv && esperadosSinProv === 3
    && cat.length >= 2 && cat.every((f) => f.clave.startsWith('catalogo:') && f.sin_cif)
    && cat.reduce((a, f) => a + f.total, 0) + sinProv[0].total === sinFactura.length
    && conFacturas === inicio.documentos.total - sinFactura.length
    && m.every((f) => !nombresArchivo.has(f.proveedor)) && m.every((f) => f.origen !== 'FACTURAS' || proveedores.proveedores.some((p) => p.clave === f.clave)),
  JSON.stringify(m.map((f) => [f.origen, f.clave, f.proveedor, f.total])));
});
comprobar('H4c: diagnósticos de check:real solo devuelven recuentos (columnas declaradas)', () => {
  const p = CONSULTAS_CHECK.diagnostico_proveedores.sql;
  const v = CONSULTAS_CHECK.diagnostico_vencimientos.sql;
  const d = CONSULTAS_CHECK.diagnostico_documentos.sql;
  const faltan = [
    ...['facturas_cif_columna', 'facturas_cif_datos_extraidos', 'cif_distintos', 'facturas_sin_cif', 'facturas_sin_cif_con_id_r9'].filter((c) => !p.includes(`as ${c}`)),
    ...['vencimientos_tipo_documento_null', 'vencimientos_tipo_documental_null', 'vencimientos_tipo_otro', 'vencimientos_sentido_no_documentado'].filter((c) => !v.includes(`as ${c}`)),
    ...['pdf_sin_factura', 'pdf_sin_factura_con_proveedor_id', 'pdf_sin_factura_con_proveedor_catalogo', 'pdf_sin_factura_sin_proveedor'].filter((c) => !d.includes(`as ${c}`)),
  ];
  let rechaza = false;
  try { validarDiagnostico({ x: 'B00000003' }); } catch { rechaza = true; }
  return si(faltan.length === 0 && rechaza && !/archivo_nombre/.test(d), faltan.join(', ') || 'validarDiagnostico acepta texto');
});
comprobar('H4b: incidencias INFO solo en el detalle de factura (ni contador ni atención de Inicio)', () => {
  const info = facturaDetalle[F(2)].incidencias.filter((i) => i.severidad === 'INFO');
  const enInicio = casosAtencion.some((c) => c.codigo === 'MONEDA_NO_DOCUMENTADA');
  return si(info.length === 1 && info[0].codigo === 'MONEDA_NO_DOCUMENTADA' && !enInicio && inicio.incidencias.abiertas === abiertasInicio.length
    && facturas.facturas.find((f) => f.factura_id === F(2)).incidencias_abiertas === 3, `info=${info.length} enInicio=${enInicio} abiertas=${inicio.incidencias.abiertas}/${abiertasInicio.length}`);
});
comprobar('H4b/H4d: textos de incidencia por código (nunca mensaje_usuario); sin entrada, "Aviso técnico del motor"', () => {
  const t = (c) => casosAtencion.find((a) => a.codigo === c)?.texto;
  return si(textoIncidencia({ codigo: 'MONEDA_NO_DOCUMENTADA' }) === 'La factura no indica la moneda'
    && t('POSIBLE_DUPLICADO') === TEXTO_INCIDENCIA.POSIBLE_DUPLICADO
    && t('VALOR_SIN_EVIDENCIA') === TEXTO_INCIDENCIA.VALOR_SIN_EVIDENCIA
    && textoIncidencia({ codigo: 'CODIGO_DESCONOCIDO' }) === TEXTO_SIN_TRADUCCION
    && t('CODIGO_FICTICIO_SIN_TRADUCCION') === 'Aviso técnico del motor (ver detalle)', 'textos mal');
});

// --- Casos H4d ---------------------------------------------------------------------
comprobar('H4d: cabecera "N tipos, M casos" y una fila por tipo', () => {
  const g = inicio.atencion.grupos;
  const claves = new Set(g.map((x) => x.clave));
  return si(inicio.atencion.tipos === g.length && inicio.atencion.casos === casosAtencion.length && claves.size === g.length
    // H6-REAL: +1 vencimiento sin sentido (V13). H8: las alertas de albaranes (1 duplicado, 1 no en Farmatic y 2
    // correcciones: grupos 3, 5 y 8) salen de Inicio a Conciliación → 12 tipos, 23 casos.
    && g.length === 12 && casosAtencion.length === 23
    && !g.some((x) => ['DUPLICADO_FARMATIC', 'ALBARAN_NO_EN_FARMATIC', 'CORRECCION_APROBADA'].includes(x.categoria)) && inicio.alertas.length === 4,
  JSON.stringify([inicio.atencion.tipos, inicio.atencion.casos]));
});
comprobar('H4d: orden fijo de grupos (1 diferencia … 8 correcciones) y casos del más reciente al más antiguo', () => {
  const g = inicio.atencion.grupos;
  const orden = g.map((x) => x.orden);
  const ordenado = orden.every((o, i) => i === 0 || orden[i - 1] <= o);
  const primeros = g.slice(0, 5).map((x) => x.clave);
  const casosOrdenados = g.every((x) => x.casos.every((c, i) => i === 0 || (x.casos[i - 1].fecha ?? '') >= (c.fecha ?? '')));
  // Dentro de 6 y 7 (un grupo por código): el grupo con el caso más reciente primero.
  const de7 = g.filter((x) => x.orden === 7).map((x) => x.clave.split(':')[1]);
  // H8: sin los grupos de alertas (3, 5 y 8), que están en Conciliación. construirAtencion los sigue sabiendo ordenar.
  const conAlertas = construirAtencion([], [], [], inicio.alertas, []).map((x) => x.orden);
  return si(ordenado && casosOrdenados && isDeepStrictEqual(primeros, ['DIFERENCIA_ALBARANES', 'DOCUMENTOS_DEFECTO', 'VENCIMIENTO_SIN_SENTIDO',
    'INCIDENCIA_ERROR:REQUIERE_REVISION', 'INCIDENCIA_ERROR:SEGUNDA_LECTURA_FALLIDA'])
    && isDeepStrictEqual(de7, ['SENTIDO_NO_DOCUMENTADO', 'IMPORTE_VENCIMIENTO_NO_DOCUMENTADO', 'SENTIDO_NO_ETIQUETADO_DOCUMENTALMENTE',
      'CANDIDATO_ALBARAN_NO_PROMOVIDO', 'POSIBLE_DUPLICADO', 'CODIGO_FICTICIO_SIN_TRADUCCION'])
    && !g.some((x) => x.orden === 8) && isDeepStrictEqual(conAlertas, [3, 5, 8]), JSON.stringify(g.map((x) => [x.orden, x.clave])));
});
comprobar('H4d: colores (1–2 y ERROR rojo; revisión, 3–5 y AVISO naranja; correcciones gris; duplicado y sentido nunca rojo)', () => {
  const malos = inicio.atencion.grupos.filter((g) => {
    // H4d-2: "Facturas con datos por revisar" sigue en el grupo 6 pero en naranja (revisión = naranja).
    const esperado = g.clave === 'INCIDENCIA_ERROR:REQUIERE_REVISION' ? 'naranja'
      : [1, 2, 6].includes(g.orden) ? 'rojo' : [3, 4, 5, 7].includes(g.orden) ? 'naranja' : 'gris';
    return g.color !== esperado;
  });
  const sentidoError = grupo('INCIDENCIA_AVISO:SENTIDO_NO_DOCUMENTADO').casos.some((c) => c.factura_id === F(2)); // SENTIDO con severidad ERROR
  const dup = inicio.atencion.grupos.filter((g) => /DUPLICADO|SENTIDO/.test(g.clave));
  return si(malos.length === 0 && sentidoError && dup.length >= 3 && dup.every((g) => g.color !== 'rojo'),
    JSON.stringify(inicio.atencion.grupos.map((g) => [g.orden, g.clave, g.color])));
});
comprobar('H4d: agrupación por código (2 IMPORTE_VENCIMIENTO, 3 SENTIDO, 2 CANDIDATO con texto según motivo)', () => {
  const iv = grupo('INCIDENCIA_AVISO:IMPORTE_VENCIMIENTO_NO_DOCUMENTADO');
  const ca = grupo('INCIDENCIA_AVISO:CANDIDATO_ALBARAN_NO_PROMOVIDO');
  return si(iv.casos.length === 2 && grupo('INCIDENCIA_AVISO:SENTIDO_NO_DOCUMENTADO').casos.length === 3 && ca.casos.length === 2
    && ca.casos.map((c) => c.texto).sort().join('|') === [TEXTO_INCIDENCIA.SENTIDO_O_SIGNO_NO_COHERENTE, TEXTO_INCIDENCIA.TIPO_PEDIDO_NO_CERTIFICADO].sort().join('|')
    && !casosAtencion.some((c) => /^[A-Z_]+$/.test(c.texto)), JSON.stringify(ca.casos.map((c) => c.texto)));
});
comprobar('H4d: MONEDA_NO_DOCUMENTADA (AVISO) fuera de Inicio y de sus contadores; visible en el detalle de F04', () => {
  const det = facturaDetalle[F(4)].incidencias.filter((i) => i.codigo === 'MONEDA_NO_DOCUMENTADA');
  return si(det.length === 1 && det[0].severidad === 'AVISO' && !casosAtencion.some((c) => c.codigo === 'MONEDA_NO_DOCUMENTADA')
    && !inicio.atencion.grupos.some((g) => g.clave.includes('MONEDA')), JSON.stringify(det));
});
comprobar('H4d-2: códigos solo de detalle fuera de Inicio y del contador; visibles en el detalle de su factura', () => {
  const malos = [];
  for (const codigo of SOLO_DETALLE) {
    const fx = INCIDENCIAS_H4D.find((i) => i.codigo === codigo);
    if (!fx) { malos.push(`${codigo}: sin fixture`); continue; }
    if (!isDeepStrictEqual([...CODIGOS_SOLO_DETALLE].sort(), [...SOLO_DETALLE].sort())) malos.push('CODIGOS_SOLO_DETALLE distinto');
    if (casosAtencion.some((c) => c.codigo === codigo)) malos.push(`${codigo}: en Inicio`);
    if (!facturaDetalle[fx.factura_id].incidencias.some((i) => i.codigo === codigo)) malos.push(`${codigo}: no está en el detalle`);
  }
  return si(malos.length === 0 && inicio.incidencias.abiertas === 13, [...new Set(malos)].join('; ') || `abiertas=${inicio.incidencias.abiertas}`);
});
comprobar('H4d-3: grupo 4 = solo vencimientos con sentido NO_DOCUMENTADO (regla de Pío), naranja, texto fijo', () => {
  const g4 = grupo('VENCIMIENTO_SIN_SENTIDO');
  const esperados = vencimientos.vencimientos.filter((v) => v.sentido === 'NO_DOCUMENTADO');
  const ids = (xs) => xs.map((x) => x.factura_id).sort();
  return si(g4 && g4.orden === 4 && g4.color === 'naranja' && g4.titulo === 'Vencimiento sin cargo/abono documentado'
    && g4.casos.length === esperados.length && esperados.length === 4 && isDeepStrictEqual(ids(g4.casos), ids(esperados))
    && isDeepStrictEqual(ids(g4.casos), [F(3), F(5), F(6), F(6)]) // H6-REAL: F06 con dos vencimientos (V08 y V13)
    && g4.casos.every((c) => c.texto === 'No se sabe si esta factura es un pago o un abono; no se suma en el cashflow' && c.codigo === null
      && c.enlace === `/facturas/${c.factura_id}`), JSON.stringify(g4));
});
comprobar('H4d-3: incidencias de sentido del motor en su propio grupo del nivel 7, naranja, con texto de movimiento/línea', () => {
  const nd = grupo('INCIDENCIA_AVISO:SENTIDO_NO_DOCUMENTADO');
  const ne = grupo('INCIDENCIA_AVISO:SENTIDO_NO_ETIQUETADO_DOCUMENTALMENTE');
  return si(nd && ne && [nd, ne].every((g) => g.orden === 7 && g.color === 'naranja')
    && nd.casos.length === 3 && nd.casos.every((c) => c.texto === TEXTO_INCIDENCIA.SENTIDO_NO_DOCUMENTADO && /movimiento/.test(c.texto))
    && ne.casos.length === 1 && ne.casos[0].texto === TEXTO_INCIDENCIA.SENTIDO_NO_ETIQUETADO_DOCUMENTALMENTE && /línea/.test(ne.casos[0].texto)
    && !grupo('SENTIDO_NO_DOCUMENTADO') && !grupo('VENCIMIENTO_SIN_SENTIDO').casos.some((c) => c.codigo !== null),
  JSON.stringify([nd, ne].map((g) => g && [g.clave, g.color, g.casos.length])));
});
comprobar('H4d-3: diagnóstico check:real "sentido" (recuentos por origen; fixtures: 4 / 3 / 1; H6-REAL: +V13)', () => {
  const sql = CONSULTAS_CHECK.diagnostico_sentido.sql;
  const cols = ['vencimiento_regla', 'incidencia_sentido_no_documentado', 'incidencia_sentido_no_etiquetado'];
  const faltan = cols.filter((c) => !sql.includes(`as ${c}`));
  // Mismo cálculo sobre las fixtures (lo que verá Pío en check:real si los datos fueran estos).
  const regla = vencimientos.vencimientos.filter((v) => v.sentido === 'NO_DOCUMENTADO').length;
  const inc = (c) => abiertasInicio.filter((i) => i.codigo === c).length;
  const g = (c) => grupo(`INCIDENCIA_AVISO:${c}`)?.casos.length ?? 0;
  return si(faltan.length === 0 && isDeepStrictEqual(COLUMNAS_SENTIDO, cols) && sql.includes("{tipo_documento,valor}") && !/\bf\.tipo_documento\b/.test(sql)
    && regla === 4 && grupo('VENCIMIENTO_SIN_SENTIDO').casos.length === regla
    && inc('SENTIDO_NO_DOCUMENTADO') === 3 && g('SENTIDO_NO_DOCUMENTADO') === 3
    && inc('SENTIDO_NO_ETIQUETADO_DOCUMENTALMENTE') === 1 && g('SENTIDO_NO_ETIQUETADO_DOCUMENTALMENTE') === 1, faltan.join(', ') || 'recuentos');
});
comprobar('H4d: diccionario completo (cada código emitido por el motor tiene texto; nunca el código como texto)', () => {
  const motor = ['ARCHIVO_NO_ENCONTRADO', 'RUTA_NO_ES_ARCHIVO', 'FORMATO_NO_ADMITIDO', 'RESULTADO_INVALIDO', 'ERROR_PROCESAMIENTO',
    'PENDIENTE_OCR', 'LAYOUT_NO_RECONOCIDO', 'LAYOUT_DESCONOCIDO', 'LAYOUT_AMBIGUO', 'SEGUNDA_LECTURA_FALLIDA', 'RESUMEN_FISCAL_OCR_INCOMPLETO',
    'TOTALES_IMPUESTOS_OCR_INCOMPLETOS', 'DETALLE_OCR_PARCIAL', 'CAMPOS_DETALLE_NO_RECUPERADOS_OCR', 'VALOR_SIN_EVIDENCIA',
    'CAMPOS_PENDIENTES_TRAS_EXTRACCION', 'MONEDA_NO_DOCUMENTADA', 'PROVEEDOR_NIF_NO_DOCUMENTADO', 'PROVEEDOR_DIRECCION_NO_DOCUMENTADA',
    'TIPOS_FISCALES_NO_DOCUMENTADOS', 'IMPORTE_VENCIMIENTO_NO_DOCUMENTADO', 'IMPORTE_VENCIMIENTO_NO_VISIBLE', 'VENCIMIENTO_CONTRADICTORIO_ENTRE_HOJAS',
    'SENTIDO_NO_DOCUMENTADO', 'SENTIDO_NO_ETIQUETADO_DOCUMENTALMENTE', 'IMPORTE_MOVIMIENTO_NO_DOCUMENTADO', 'CATEGORIA_MOVIMIENTO_NO_DECIDIDA',
    'CANDIDATO_ALBARAN_NO_PROMOVIDO', 'TIPO_PEDIDO_NO_CERTIFICADO', 'SENTIDO_O_SIGNO_NO_COHERENTE', 'FILA_IMPORTE_CERO_INFORMATIVA',
    'ROL_FILA_INDETERMINADO', 'FILAS_DUPLICADAS_EVIDENCIA_IDENTICA', 'ALBARANES_CONSUMIBLES_SOLO_REFERENCIA_DOCUMENTAL',
    'COMPONENTE_DOCUMENTAL_AUSENTE', 'DIFERENCIA_CONCILIACION_NO_EXPLICADA', 'POSIBLE_DUPLICADO', 'DUPLICADO_CONFLICTIVO',
    'CONFLICTO_ENTRE_REPRESENTACIONES', 'EQUIVALENCIA_DOCUMENTAL_INSUFICIENTE', 'REPRESENTACIONES_CONSOLIDADAS'];
  const faltan = motor.filter((c) => textoIncidencia({ codigo: c }) === TEXTO_SIN_TRADUCCION);
  const comoCodigo = Object.values(TEXTO_INCIDENCIA).filter((t) => /^[A-Z_]+$/.test(t));
  return si(faltan.length === 0 && comoCodigo.length === 0, faltan.join(', '));
});
comprobar('H4d: próximos vencimientos marcan "posible duplicado" (F01 con incidencia POSIBLE_DUPLICADO)', () => {
  const pv = inicio.proximos_vencimientos;
  const conDup = new Set(abiertasInicio.filter((i) => i.codigo === 'POSIBLE_DUPLICADO').map((i) => i.factura_id));
  return si(pv.length === 5 && pv.every((v) => v.posible_duplicado === conDup.has(v.factura_id)) && pv.some((v) => v.posible_duplicado),
    JSON.stringify(pv.map((v) => [v.factura_id.slice(-2), v.posible_duplicado])));
});
comprobar('H4b: diagnóstico duplicados (2 candidatos, 1 tras filtro de importe)', () => {
  const d = resumenDuplicados(ALERTA_DUPLICADO);
  return si(isDeepStrictEqual(d, { candidatos: 2, albaranes_candidatos: 4, tras_filtro_importe: 1, limite_200_alcanzado: false }), JSON.stringify(d));
});
comprobar('H4b: diagnóstico par 08C66676 (sí/no y nombres de columna; nunca valores)', () => {
  const filas = ALERTA_DUPLICADO[0].detalle.map((r) => ({ ...r, importe_pvp: 99.1, importe_coste: r.numero_albaran.endsWith('A') ? 1 : 2, numero_par_diagnostico: r.numero_albaran }));
  const d = validarDiagnostico(resumenPar08C66676(filas, ['importe_coste', 'importe_puc', 'importe_pvp']));
  const falta = validarDiagnostico(resumenPar08C66676(filas.slice(0, 1), ['importe_puc']));
  let rechaza = false;
  try { validarDiagnostico({ x: ['08C66676'] }); } catch { rechaza = true; }
  return si(isDeepStrictEqual(d, { filas_08C66676: 1, filas_08C66676A: 1, existen_ambos: true, comparable_uno_a_uno: true,
    mismo_proveedor_r9: true, mismo_importe_puc: true, otras_columnas_importe_coinciden: ['importe_pvp'] })
    && falta.existen_ambos === false && rechaza, JSON.stringify([d, falta]));
});
comprobar('configuración: interruptores apagados, solo PIO, R11 0,05/0,01/0,50', () => {
  const c = configuracion;
  return si(isDeepStrictEqual(c.farmacias_habilitadas, ['PIO']) && !c.normalizacion_automatica && !c.conciliacion_automatica && !c.luna_habilitada
    && c.conciliacion_tolerancia_suelo === 0.05 && c.conciliacion_tolerancia_por_albaran === 0.01 && c.conciliacion_tolerancia_tope === 0.5, JSON.stringify(c));
});

// --- Casos H5: pantalla Facturas ----------------------------------------------------
const lineasTodas = Object.values(facturaDetalle).flatMap((x) => x.lineas);
comprobar('H5: diccionario de tipos de casado completo, con texto llano y fuente (fichero:línea)', () => {
  // H5-5: commit:fichero:línea; H8: R20 cita su migración («migración 36»).
  const malos = Object.entries(DICCIONARIO_CASADO).filter(([k]) => k !== 'ESTADO:SIN_DESCRIPCION').filter(([, e]) => !e.texto || /^[A-Z_:]+$/.test(e.texto) || !/^[A-Z0-9]+:|\.sql:|^[0-9a-f]{7}:[a-z0-9_/]+\.py:\d|^migración \d+$/.test(e.fuente));
  return si(malos.length === 0 && Object.keys(DICCIONARIO_CASADO).length >= 20, malos.map(([k]) => k).join(', '));
});
comprobar('H5-2: las fixtures cubren las formas de casado (principal) y los tipos de relación (secundario)', () => {
  const claves = new Set(lineasTodas.map(claveCasado));
  const faltan = ['NUMERO:EXACTA', 'NUMERO:LETRA_FINAL', 'NUMERO:FINAL_DOCUMENTAL', 'NUMERO:INTERNO', 'HEFAME:EXACTO_ECONOMICO',
    'MOVIMIENTO', 'MOVIMIENTO:SIN_SENTIDO', 'SIN:SIN_COINCIDENCIA', 'SIN:AMBIGUO', 'R20:PARTIDO'].filter((k) => !claves.has(k));
  const rel = new Set(lineasTodas.map(claveRelacion));
  const faltanRel = ['UNO_A_UNO', 'UNO_A_VARIOS', 'MOVIMIENTO_NO_FARMATIC', 'SIN_COINCIDENCIA'].filter((k) => !rel.has(k));
  // R17: principal = forma del número de cada albarán (su número / numeración interna), secundario = misma recepción.
  // H8: R20 también es UNO_A_VARIOS; la regla los distingue.
  const r17 = lineasTodas.filter((l) => l.tipo_relacion === 'UNO_A_VARIOS' && l.regla === 'R17').map(claveCasado).join();
  return si(faltan.length === 0 && faltanRel.length === 0 && r17 === 'NUMERO:EXACTA,NUMERO:INTERNO'
    && !claves.has('SIN:OTRO') && !claves.has('NUMERO:OTRO') && Object.keys(RELACION_CASADO).every((k) => RELACION_CASADO[k].texto && RELACION_CASADO[k].fuente),
  `faltan ${[...faltan, ...faltanRel].join(', ')} · r17 ${r17}`);
});
comprobar('H5-7: líneas con la forma de producción tras la migración 30 (valores por línea de cf_detalles_por_linea)', () => {
  // Fórmula de 30_cf_detalle_por_linea.sql:43-70, escrita aparte del generador para contrastarlo.
  const r4 = (v) => Math.round(v * 10000) / 10000;
  const suma = new Map();
  for (const l of lineasTodas) {
    if (['UNO_A_UNO', 'UNO_A_VARIOS', 'VARIOS_A_UNO'].includes(l.tipo_relacion)) {
      const k = `${l.factura_id}|${l.factura_albaran_extraido_id}`; suma.set(k, r4((suma.get(k) ?? 0) + l.importe_aplicado));
    }
  }
  const malas = lineasTodas.filter((l) => {
    const mov = l.tipo_relacion === 'MOVIMIENTO_NO_FARMATIC'; const sin = l.tipo_relacion === 'SIN_COINCIDENCIA';
    const t = l.albaran_importe_total;
    const doc = mov || t === null ? null : l.sentido_documental === 'ABONO' ? -Math.abs(t) : t;
    const pdf = mov ? l.importe_aplicado : doc;
    const far = mov || sin ? null : l.importe_aplicado;
    const dif = mov || doc === null ? null : sin ? doc : r4(doc - suma.get(`${l.factura_id}|${l.factura_albaran_extraido_id}`));
    const est = mov || doc === null ? 'NO_EVALUABLE' : sin ? 'DIFERENCIA' : Math.abs(dif) <= 0.05 ? 'COINCIDE' : 'DIFERENCIA';
    return l.importe_documental !== pdf || l.importe_farmatic !== far || l.diferencia !== dif || l.estado_linea !== est
      || (l.factura_albaran_extraido_id === null && (l.albaran_importe_total !== null || l.albaran_importe_base !== null));
  });
  const mov = facturaDetalle[F(4)].lineas.find((l) => l.tipo_relacion === 'MOVIMIENTO_NO_FARMATIC');
  const estados = new Set(lineasTodas.map((l) => l.estado_linea));
  // Ningún null convertido en 0: el movimiento de F07 sin importe aplicado queda sin importe del PDF.
  const m7 = facturaDetalle[F(7)].lineas.find((l) => l.tipo_relacion === 'MOVIMIENTO_NO_FARMATIC');
  return si(malas.length === 0 && mov.magnitud_usada === 'IMPORTE' && ['COINCIDE', 'DIFERENCIA', 'NO_EVALUABLE'].every((e) => estados.has(e))
    && m7.importe_aplicado === null && m7.importe_documental === null,
  malas.map((l) => `${l.factura_id.slice(-2)}/${l.orden}`).join(', '));
});
comprobar('H5-7: estados por línea en la web (texto y color), aviso «N albaranes con diferencia» y advertencia Hefame', () => {
  const k = (n, orden) => claveEstadoLinea(facturaDetalle[F(n)].lineas.find((l) => l.orden === orden));
  const casos = [[k(3, 1), 'DIFERENCIA'], [k(3, 2), 'COINCIDE'], [k(2, 6), 'NO_EVALUABLE_SIN_PDF'], [k(7, 5), 'NO_EVALUABLE'],
    [k(4, 4), 'NO_EVALUABLE'], [claveEstadoLinea({ estado_linea: 'RARO', importe_farmatic: null }), 'OTRO']];
  const malos = casos.map(([a, b], i) => (a === b ? null : `#${i}: ${a}≠${b}`)).filter(Boolean);
  const e = ESTADO_LINEA;
  const aviso = (n) => avisosFactura(facturaDetalle[F(n)]).find((a) => a.clave === 'lineas-con-diferencia');
  const a3 = aviso(3), a5 = aviso(5), a7 = aviso(7), a2 = aviso(2);
  const ok = malos.length === 0 && e.COINCIDE.color === 'verde' && e.DIFERENCIA.color === 'rojo' && e.NO_EVALUABLE.color === 'gris'
    && e.NO_EVALUABLE.texto === 'Sin contraparte en Farmatic' && e.NO_EVALUABLE_SIN_PDF.texto === 'Sin importe del PDF para comparar'
    // F03: línea 1 (casada) + línea 4 (sin casar); R17 (dos detalles) cuenta como una línea y está en COINCIDE.
    && a3?.texto === '2 albaranes con diferencia' && a3.detalle === 'De ellos, 1 sin casar en Farmatic'
    && a5?.texto === '4 albaranes con diferencia' && a5.detalle.includes(TEXTO_HEFAME_BASES)
    // H8: F02 línea 2 (R20, dos detalles) en DIFERENCIA: cuenta una vez.
    && a7?.texto === '2 albaranes con diferencia' && a2?.texto === '1 albarán con diferencia' && a2.detalle === null
    && TEXTO_HEFAME_BASES === 'El motor compara la base neta del PDF (sin IVA) con el importe de Farmatic (con IVA): la diferencia incluye el IVA y el recargo';
  return si(ok, `${malos.join(', ')} | ${JSON.stringify([a3, a5, a7, a2])}`);
});
comprobar('H5-2: bases: Hefame base neta, resto con IVA y RE (criterio de proveedor del motor); aplicado = PUC o PVP', () => {
  const casos = [
    [baseAlbaran(facturaDetalle[F(5)].factura.proveedor_literal), 'BASE_NETA'],
    [baseAlbaran(facturaDetalle[F(2)].factura.proveedor_literal), 'CON_IVA'],
    [baseAlbaran(facturaDetalle[F(3)].factura.proveedor_literal), 'CON_IVA'],
    [canonicalizarProveedor('Alliance Healthcare España, S.A.'), 'ALLIANCEHEALTHCARECENCORA'],
    [canonicalizarProveedor('Hefame'), 'HEFAMEMERCANCIA'],
    [canonicalizarProveedor('Cofares S.L.'), 'COFARES'],
    [origenAplicado(facturaDetalle[F(1)].lineas[0]), 'PUC'],
    [origenAplicado({ importe_aplicado: -45.3, importe_puc: 45.3, importe_pvp: null }), 'PUC'],
    [origenAplicado({ importe_aplicado: 10, importe_puc: 9, importe_pvp: 10 }), 'PVP'],
    [origenAplicado({ importe_aplicado: 10, importe_puc: 9, importe_pvp: null }), null],
  ];
  const malos = casos.map(([a, b], i) => (a === b ? null : `#${i}: ${a}≠${b}`)).filter(Boolean);
  const f05 = facturaDetalle[F(5)].lineas.filter((l) => l.tipo_relacion === 'UNO_A_UNO');
  return si(malos.length === 0 && f05.every((l) => l.albaran_importe_base === null && l.albaran_importe_total !== null), malos.join(', '));
});
comprobar('H5-2: búsqueda por importe (sin coma = de N,00 a N,99; con coma = exacto; puntos, espacios y € ignorados)', () => {
  const r = (q) => JSON.stringify(rangoImporteBuscado(q));
  const casos = [
    [r('5000'), '{"desde":500000,"hasta":500099}'], [r('5.000'), '{"desde":500000,"hasta":500099}'], [r('5 000 €'), '{"desde":500000,"hasta":500099}'],
    [r('5000,1'), '{"desde":500010,"hasta":500010}'], [r('5.000,10'), '{"desde":500010,"hasta":500010}'], [r('-45,30'), '{"desde":4530,"hasta":4530}'],
    [r('abc'), 'null'], [r('5000,123'), 'null'], [r('5,000,1'), 'null'], [r(''), 'null'],
    [coincideImporte('5000', [5000]), true], [coincideImporte('5000', [5000.99]), true], [coincideImporte('5000', [5001]), false],
    [coincideImporte('5000', [4999.99]), false], [coincideImporte('5000,1', [5000.1]), true], [coincideImporte('5000,1', [5000.11]), false],
    [coincideImporte('45,30', [-45.3]), true], [coincideImporte('5000', [null]), false],
  ];
  const malos = casos.map(([a, b], i) => (a === b ? null : `#${i}: ${a}≠${b}`)).filter(Boolean);
  const f4 = facturas.facturas.find((x) => x.factura_id === F(4));
  return si(malos.length === 0 && isDeepStrictEqual(f4.vencimientos_importes, [400, 150, null, -25]), malos.join(', ') || JSON.stringify(f4.vencimientos_importes));
});
comprobar('H5-3: diagnóstico de casado (etiquetas fijas; no previstos listados solo si son código; el resto en otros_no_codigo)', () => {
  const PAT = /^[A-Z0-9_]{1,40}$/;
  // Mismo CASE que SQL_ETIQUETA, en JS, sobre las líneas de las fixtures.
  const etq = (v, lista) => (v === null || v === '' ? 'sin_valor' : lista.includes(v) ? v.toLowerCase() : PAT.test(v) ? `no_previsto:${v}` : 'otros_no_codigo');
  const filasDiag = [];
  const contar = (eje, valores) => { const m = new Map(); for (const v of valores) m.set(v, (m.get(v) ?? 0) + 1); for (const [e, n] of m) filasDiag.push({ eje, etiqueta: e, n: String(n) }); };
  contar('clase_numero', lineasTodas.map((l) => etq(l.clase_numero, ETIQUETAS_CLASE_NUMERO)));
  contar('estado_matching', lineasTodas.map((l) => etq(l.estado_matching, ETIQUETAS_ESTADO_MATCHING)));
  const d = resumenCasado(filasDiag);
  const rechaza = (fila) => { try { resumenCasado([fila]); return false; } catch { return true; } };
  const total = (eje) => Object.entries(d).filter(([k]) => k.startsWith(eje + '.')).reduce((a, [, n]) => a + n, 0);
  const sql = CONSULTAS_CHECK.diagnostico_casado.sql;
  return si(d['estado_matching.no_previsto.ESTADO_FUTURO_PRUEBA'] === 1 && d['clase_numero.no_previsto.CLASE_FUTURA_PRUEBA'] === 1
    && d['estado_matching.otros_no_codigo'] === 1 && d['estado_matching.albaran_ya_conciliado'] === 1 && d['clase_numero.no_disponible'] === 1
    && d['estado_matching.match_r17'] === 2 && !Object.keys(d).some((k) => k.includes('raro'))
    && total('clase_numero') === lineasTodas.length && total('estado_matching') === lineasTodas.length
    // Falla cerrado: etiqueta literal, no_previsto que no es código o que es una etiqueta fija, eje ajeno.
    && rechaza({ eje: 'clase_numero', etiqueta: 'VALOR_LITERAL', n: '1' })
    && rechaza({ eje: 'estado_matching', etiqueta: 'no_previsto:valor raro', n: '1' })
    && rechaza({ eje: 'estado_matching', etiqueta: `no_previsto:${'A'.repeat(41)}`, n: '1' })
    && rechaza({ eje: 'estado_matching', etiqueta: 'no_previsto:MATCH_UNICO', n: '1' })
    && rechaza({ eje: 'otro_eje', etiqueta: 'no_previsto:X', n: '1' })
    && sql.includes("~ '^[A-Z0-9_]{1,40}$'") && sql.includes("'otros_no_codigo'") && !sql.includes("'otros_valores'"), JSON.stringify(d));
});
comprobar('H5-3: diccionario de estado_matching = valores que escribe el motor (12), con texto llano y fuente', () => {
  const claves = Object.keys(ESTADOS_MATCHING).sort();
  const ok = isDeepStrictEqual(claves, [...ETIQUETAS_ESTADO_MATCHING].sort())
    && Object.entries(ESTADOS_MATCHING).every(([k, e]) => e.texto && !/^[A-Z_]+$/.test(e.texto)
      // H5-5: los de la versión anterior citan commit:fichero:línea; los actuales, conciliacion.py (C:).
      // H8: MATCH_R20, su migración. H7-REAL-8: MATCH_R21, la regla del circuito (provenance.regla).
      && (ESTADOS_VERSION_ANTERIOR.includes(k) ? /^e18acf0:pruebas\/auditoria_2[tv]\/[a-z0-9_]+\.py:\d/.test(e.fuente)
        : k === 'MATCH_R20' ? e.fuente === 'migración 36' : k === 'MATCH_R21' ? /^R21:provenance\.regla/.test(e.fuente) : /^C:\d/.test(e.fuente)))
    && DICCIONARIO_CASADO['ESTADO:SIN_DESCRIPCION'].texto === 'Estado del motor sin descripción (ver evidencia técnica)'
    && textoEstadoMatching('MATCH_UNICO') !== null && textoEstadoMatching('ESTADO_FUTURO_PRUEBA') === null;
  return si(ok, claves.join(', '));
});
comprobar('H5-5: EXACTO y ECONOMICO_UNICO (versión anterior del motor): texto llano marcado, casados, diagnóstico con etiqueta fija', () => {
  const l1 = facturaDetalle[F(1)].lineas.find((l) => l.orden === 1);
  const l2 = facturaDetalle[F(1)].lineas.find((l) => l.orden === 2);
  const d = resumenCasado([{ eje: 'estado_matching', etiqueta: 'exacto', n: '266' }, { eje: 'estado_matching', etiqueta: 'economico_unico', n: '8' }]);
  const rechaza = (fila) => { try { resumenCasado([fila]); return false; } catch { return true; } };
  const ok = l1.estado_matching === 'EXACTO' && l2.estado_matching === 'ECONOMICO_UNICO' && l1.clase_numero === null && l2.clase_numero === null
    && claveCasado(l1) === 'ANTERIOR:EXACTO' && claveCasado(l2) === 'ANTERIOR:ECONOMICO_UNICO'
    && ['ANTERIOR:EXACTO', 'ANTERIOR:ECONOMICO_UNICO'].every((k) => DICCIONARIO_CASADO[k].color === 'verde' && DICCIONARIO_CASADO[k].texto.includes('versión anterior del motor'))
    && ESTADOS_VERSION_ANTERIOR.every((k) => ESTADOS_MATCHING[k].version_anterior === true && /^Versión anterior del motor: /.test(textoEstadoMatching(k)))
    && !estadoSinDescripcion(l1) && !estadoSinDescripcion(l2)
    // H5-6: texto neutro de EXACTO (el motor anterior admitía prefijo o letra final): nunca "mismo número".
    && DICCIONARIO_CASADO['ANTERIOR:EXACTO'].texto === 'Un único albarán; el motor anterior lo dio por número coincidente (versión anterior del motor)'
    && ![DICCIONARIO_CASADO['ANTERIOR:EXACTO'].texto, ESTADOS_MATCHING.EXACTO.texto].some((t) => /mismo número/i.test(t))
    && d['estado_matching.exacto'] === 266 && d['estado_matching.economico_unico'] === 8
    && rechaza({ eje: 'estado_matching', etiqueta: 'no_previsto:EXACTO', n: '1' })
    && [l1, l2].every((l) => l.estado_linea === 'COINCIDE' && l.importe_aplicado !== null);
  return si(ok, `${claveCasado(l1)} ${claveCasado(l2)} ${JSON.stringify([d['estado_matching.exacto'], d['estado_matching.economico_unico']])}`);
});
comprobar('H5-3: fixtures: NO_DISPONIBLE, estado no previsto, valor no código y clase no prevista → sin descripción; aviso en el detalle', () => {
  const k = (n, orden) => claveCasado(facturaDetalle[F(n)].lineas.find((l) => l.orden === orden));
  const casos = [[k(7, 1), 'NUMERO:NO_DISPONIBLE'], [k(7, 3), 'ESTADO:SIN_DESCRIPCION'], [k(7, 4), 'ESTADO:SIN_DESCRIPCION'],
    [k(7, 5), 'SIN:ALBARAN_YA_CONCILIADO'], [k(4, 2), 'ESTADO:SIN_DESCRIPCION']];
  const malos = casos.map(([a, b], i) => (a === b ? null : `#${i}: ${a}≠${b}`)).filter(Boolean);
  const av7 = avisosFactura(facturaDetalle[F(7)]).map((a) => a.clave);
  const f7 = facturaDetalle[F(7)];
  return si(malos.length === 0 && av7.includes('lineas-ESTADO:SIN_DESCRIPCION') && av7.includes('lineas-SIN:ALBARAN_YA_CONCILIADO')
    && f7.lineas.filter((l) => l.tipo_relacion === 'SIN_COINCIDENCIA').every((l) => l.importe_aplicado === 0), malos.join(', ') || av7.join(', '));
});
comprobar('H5: ECO360 (id 154) solo en F02 línea 7; claves sintéticas de sin coincidencia', () => {
  const eco = lineasTodas.filter(esEco360);
  const l = (tipo, extra = {}) => ({ tipo_relacion: tipo, estado_matching: null, clase_numero: null, papel_r17: null, sentido_documental: 'CARGO', estado_linea: 'COINCIDE', ...extra });
  const casos = [
    [claveCasado(l('SIN_COINCIDENCIA', { estado_matching: 'ALBARAN_YA_CONCILIADO' })), 'SIN:ALBARAN_YA_CONCILIADO'],
    [claveCasado(l('SIN_COINCIDENCIA', { estado_matching: 'NUMERO_PROVEEDOR_DISTINTO' })), 'SIN:NUMERO_PROVEEDOR_DISTINTO'],
    [claveCasado(l('SIN_COINCIDENCIA', { estado_matching: 'CONFLICTO_R17' })), 'SIN:CONFLICTO_R17'],
    [claveCasado(l('SIN_COINCIDENCIA', { estado_matching: 'DESCONOCIDO_X' })), 'ESTADO:SIN_DESCRIPCION'], [claveCasado(l('SIN_COINCIDENCIA', { estado_matching: null })), 'SIN:OTRO'],
    [claveCasado(l('UNO_A_UNO', { clase_numero: 'SIN_PATRON' })), 'NUMERO:SIN_PATRON'],
    [claveCasado(l('UNO_A_UNO', { clase_numero: 'RARO' })), 'ESTADO:SIN_DESCRIPCION'], [claveCasado(l('UNO_A_UNO', { clase_numero: null })), 'NUMERO:OTRO'],
    [claveCasado(l('VARIOS_A_UNO', { clase_numero: 'EXACTA' })), 'NUMERO:EXACTA'],
    [claveRelacion(l('VARIOS_A_UNO')), 'VARIOS_A_UNO'],
    [claveCasado(l('UNO_A_UNO', { coincidencia_numero: 'EXACTA' })), 'NUMERO:EXACTA'],
    [claveCasado(l('MOVIMIENTO_NO_FARMATIC', { sentido_documental: 'ABONO' })), 'MOVIMIENTO:ABONO'],
    [esEco360({ farmatic_id_proveedor: '0154', farmatic_proveedor: null }), true],
  ];
  const malos = casos.map(([a, b], i) => (a === b ? null : `#${i}: ${a}≠${b}`)).filter(Boolean);
  return si(eco.length === 1 && eco[0].factura_id === F(2) && eco[0].orden === 7 && malos.length === 0, `eco=${eco.length} ${malos.join(', ')}`);
});
comprobar('H5: R17 en F03: dos detalles UNO_A_VARIOS con el mismo albarán documental (una línea), PUC 60,00 + 38,70', () => {
  const d = facturaDetalle[F(3)];
  const r17 = d.lineas.filter((x) => x.tipo_relacion === 'UNO_A_VARIOS');
  const g = agruparLineas(d.lineas.filter((x) => x.tipo_relacion !== 'MOVIMIENTO_NO_FARMATIC'));
  return si(r17.length === 2 && r17[0].factura_albaran_extraido_id === r17[1].factura_albaran_extraido_id
    && isDeepStrictEqual(r17.map((x) => x.importe_aplicado), [60, 38.7]) && g.length === 3 && g[1].detalles.length === 2
    && d.albaranes_extraidos.length === 3, JSON.stringify(r17.map((x) => [x.orden, x.papel_r17, x.importe_aplicado])));
});
// --- H8 (migración 36): R20 y «para revisar» de la noche -----------------------------------------------------------
comprobar('H8: R20 en F02: una línea = 2 filas UNO_A_VARIOS (mismo albarán documental), exacto + variante; importes del motor', () => {
  const d = facturaDetalle[F(2)];
  const r20 = d.lineas.filter((x) => x.regla === 'R20');
  const g = agruparLineas(d.lineas.filter((x) => x.tipo_relacion !== 'MOVIMIENTO_NO_FARMATIC')).filter((x) => x.detalles.some((l) => l.regla === 'R20'));
  const malos = [];
  for (const x of g) {
    const [a, b] = x.detalles;
    if (x.detalles.length !== 2 || a.factura_albaran_extraido_id !== b.factura_albaran_extraido_id) malos.push('pareja');
    if (!x.detalles.every((l) => l.tipo_relacion === 'UNO_A_VARIOS' && l.estado_matching === 'MATCH_R20')) malos.push('tipo');
    if (a.papel_r20 !== 'NUMERO' || a.clase_numero !== 'EXACTA' || a.coincidencia_numero_literal !== true) malos.push('exacto');
    if (b.papel_r20 !== 'LETRA_FINAL' || b.clase_numero !== 'LETRA_FINAL' || b.coincidencia_numero_literal !== false) malos.push('variante');
    if (a.importe_documental !== b.importe_documental || a.diferencia !== b.diferencia || a.estado_linea !== b.estado_linea) malos.push('comunes');
    if (x.detalles.some((l) => l.importe_farmatic !== l.importe_aplicado)) malos.push('farmatic');
  }
  const [l2, l4] = g;
  const suma = (x) => Math.round((x.detalles[0].importe_farmatic + x.detalles[1].importe_farmatic) * 100) / 100;
  const ok = malos.length === 0 && r20.length === 4 && g.length === 2
    && l2.documental.numero === '08X20002' && suma(l2) === 43.09 && l2.detalles[0].diferencia === 1.21 && l2.detalles[0].estado_linea === 'DIFERENCIA'
    && l4.documental.numero === '08X20004' && suma(l4) === 156.73 && l4.detalles[0].diferencia === 0.01 && l4.detalles[0].estado_linea === 'COINCIDE'
    && g.every((x) => x.detalles.every((l) => claveCasado(l) === 'R20:PARTIDO'))
    && DICCIONARIO_CASADO['R20:PARTIDO'].texto === 'Albarán partido en Farmatic' && DICCIONARIO_CASADO['R20:PARTIDO'].fuente === 'migración 36'
    // R17 sigue siendo R17 (la regla distingue).
    && facturaDetalle[F(3)].lineas.filter((l) => l.tipo_relacion === 'UNO_A_VARIOS').every((l) => claveCasado(l).startsWith('NUMERO:'))
    // El explicado de la conciliación no cambia: lo aplicado de F02 suma lo mismo que antes de R20.
    && Math.round(d.lineas.reduce((s, l) => s + (l.importe_aplicado ?? 0), 0) * 100) / 100 === 472.15;
  return si(ok, `${malos.join(',')} ${JSON.stringify(g.map((x) => [x.documental.numero, x.detalles.map((l) => [l.orden, l.papel_r20, l.importe_farmatic, l.diferencia, l.estado_linea])]))}`
    + ` aplicado=${d.lineas.reduce((s, l) => s + (l.importe_aplicado ?? 0), 0)}`);
});
// --- H8-5: etiquetas de R21 y R22 ------------------------------------------------------------------------------------
comprobar('H8-5: R21 (F05 línea 3) y R22 (F04 línea 1) con su etiqueta; código de regla desconocido, tal cual; ambas facturas en Conciliación', () => {
  const l = (n, orden) => facturaDetalle[F(n)].lineas.find((x) => x.orden === orden);
  const r21 = l(5, 3);
  const r22 = l(4, 1);
  const enBandeja = (n) => JSON.stringify(conciliacionBandeja).includes(F(n));
  const ok = r21.regla === 'R21' && claveCasado(r21) === 'R21:COMPLEMENTARIOS'
    && DICCIONARIO_CASADO['R21:COMPLEMENTARIOS'].texto === 'Albarán con complementarios de la misma recepción'
    && r22.regla === 'R22' && claveCasado(r22) === 'R22:ANULADO' && DICCIONARIO_CASADO['R22:ANULADO'].texto === 'Cargo anulado por su abono (neto 0)'
    // Mandan sobre un estado del motor nuevo para la web.
    && claveCasado({ ...r21, estado_matching: 'MATCH_R21' }) === 'R21:COMPLEMENTARIOS'
    && codigoReglaDesconocido({ regla: 'R23' }) === 'R23' && codigoReglaDesconocido(r21) === null && codigoReglaDesconocido({ regla: 'R20' }) === null
    // H7-REAL-8: F05 línea 3 lleva el estado MATCH_R21 (conocido); con otra regla, casada por su número.
    && codigoReglaDesconocido({ regla: null }) === null && r21.estado_matching === 'MATCH_R21' && claveCasado({ ...r21, regla: 'R23' }) === 'NUMERO:EXACTA'
    && textoEstadoMatching('MATCH_R21') !== null
    && enBandeja(5) && enBandeja(4)
    && lineasTodas.filter((x) => x.regla === 'R21' || x.regla === 'R22').length === 2;
  return si(ok, JSON.stringify([r21?.regla, claveCasado(r21), r22?.regla, claveCasado(r22)]));
});
comprobar('H8: «para revisar» de la noche (01/11/2026): solo PIO, los cuatro tipos con texto llano y el valor del motor sin recalcular', () => {
  const r = conciliacionBandeja.revisar_noche;
  const t = (tipo) => r.elementos.filter((e) => e.tipo === tipo).map((e) => e.texto);
  const ok = r.fecha === '2026-11-01' && r.lista_valida && isDeepStrictEqual(inicio.revisar_noche, r)
    && r.elementos.length === 6 && !r.elementos.some((e) => e.numero_factura === 'OTRA-FARMACIA')
    && isDeepStrictEqual(t('DIFERENCIA').sort(), ['Diferencia simulada de 118,16 €', 'Diferencia simulada de 2,0350 €'])
    && isDeepStrictEqual(t('NO_ALLIANCE'), ['Proveedor aún sin conciliación automática'])
    && isDeepStrictEqual(t('R18_PENDIENTE'), ['Pendiente de la regla R18'])
    && isDeepStrictEqual(t('DEFECTO'), ['Documento con defecto tras 3 intentos'])
    && r.elementos.find((e) => e.tipo === 'R18_PENDIENTE').evidencia.fallo === 'R18_SIN_EVIDENCIA_FICTICIO'
    && r.elementos.find((e) => e.tipo === 'R18_PENDIENTE').evidencia.r18?.estado === 'PENDIENTE'
    && r.elementos.find((e) => e.tipo === 'OTRO')?.tipo_literal === 'TIPO_FUTURO_PRUEBA'
    && r.elementos.find((e) => e.tipo === 'DEFECTO').enlace === '/facturas' && r.elementos.find((e) => e.tipo === 'DEFECTO').archivo_nombre !== null
    && r.elementos.filter((e) => e.factura_id !== null).every((e) => e.enlace === `/facturas/${e.factura_id}`)
    && isDeepStrictEqual(r.por_tipo, { DIFERENCIA: 2, NO_ALLIANCE: 1, R18_PENDIENTE: 1, DEFECTO: 1, OTRO: 1 })
    // La noche no reclama: las facturas siguen en PENDIENTE_CONCILIAR (y no suma en «Necesita tu atención»).
    && r.elementos.filter((e) => e.factura_id !== null).every((e) => facturaDetalle[e.factura_id].factura.estado_conciliacion_cf === 'PENDIENTE_CONCILIAR')
    && configuracion.conciliacion_r20 === true
    && CONSULTAS_POR_BLOQUE.inicio.includes('noche_revisar') && CONSULTAS_POR_BLOQUE.conciliacionBandeja.includes('noche_revisar')
    && OBJETOS_PERMITIDOS.includes('cf_noches_automaticas');
  return si(ok, JSON.stringify({ fecha: r.fecha, n: r.elementos.length, por_tipo: r.por_tipo, textos: r.elementos.map((e) => e.texto) }));
});
// --- H8: pantalla Conciliación (doble comprobación) -------------------------------------------------------------
comprobar('H8: doble comprobación: las cuatro marcas de albaranes, banco siempre «sin datos bancarios», resumen en € y sin importe fuera', () => {
  const fs = conciliacionBandeja.facturas;
  const m = (n) => marcaAlbaranes(fs.find((x) => x.factura_id === F(n))).clave;
  const marcas = [1, 2, 3, 4, 5, 6, 7, 8].map(m);
  const r = resumenDoble(fs);
  const f2 = fs.find((x) => x.factura_id === F(2));
  const ok = isDeepStrictEqual(marcas, ['CONCILIADA', 'CONCILIADA', 'DIFERENCIA', 'CONCILIADA', 'REVISION', 'PENDIENTE', 'DIFERENCIA', 'PENDIENTE'])
    && fs.every((x) => isDeepStrictEqual(x.banco, BANCO_SIN_DATOS))
    && marcaAlbaranes(f2).diferencia_motor === f2.conciliacion.diferencia // la del motor, sin recalcular
    && marcaAlbaranes(fs.find((x) => x.factura_id === F(3))).diferencia_motor === 41.9
    && r.verificado_doble.facturas === 0 && r.verificado_doble.importe === null && r.solo_albaranes.facturas === 3
    && r.sin_importe === fs.filter((x) => x.importe_total === null).length && r.sin_importe > 0
    && r.solo_albaranes.facturas + r.ninguna.facturas + r.sin_importe === fs.length
    && fs.find((x) => x.factura_id === F(3)).vencimiento_proximo.fecha_vencimiento === '2026-11-14' // vencimiento próximo con diferencia
    && conciliacionBandeja.hoy === '2026-11-02' && conciliacionBandeja.proveedores_filtro.length > 0
    && fs.every((x) => x.proveedor_grupo && x.proveedor_etiqueta);
  return si(ok, JSON.stringify({ marcas, r }));
});
comprobar('H8: Albaranes: cabecera, bandeja por proveedor → motivo ordenada por dinero en riesgo, cobertura con «sin lector» y alertas', () => {
  const c = cabeceraAlbaranes(conciliacionBandeja);
  const b = bandejaAlbaranes(conciliacionBandeja.facturas);
  const orden = b.flatMap((g) => g.motivos.flatMap((m) => m.facturas.map((x) => x.factura_id.slice(-2))));
  const motivos = Object.fromEntries(b.flatMap((g) => g.motivos.flatMap((m) => m.facturas.map((x) => [x.factura_id.slice(-2), m.clave]))));
  const cob = coberturaProveedores(conciliacionBandeja.facturas, conciliacionBandeja.sin_factura);
  const ra = recuentoAlertas(conciliacionBandeja);
  const ok = c.conciliadas === 3 && c.pendientes === 4 && c.en_revision === 1 && c.cobertura.sin_importe === 1
    && isDeepStrictEqual(orden, ['08', '05', '03', '07', '06'])
    && motivos['05'] === 'REVISION' && motivos['03'] === 'NO_LOCALIZADO' && motivos['08'] === 'PENDIENTE'
    && cob.filter((x) => x.tipo === 'SIN_LECTOR').length === 3 && cob.findIndex((x) => x.tipo === 'SIN_LECTOR') === cob.filter((x) => x.tipo === 'LECTOR').length
    && ra.duplicados === 1 && ra.no_en_farmatic === 1 && ra.correcciones === 2;
  return si(ok, JSON.stringify({ c, orden, motivos, ra }));
});
comprobar('H8: Sin factura: con lector > 30 días → alerta (antigüedad e importe); recientes y anteriores sin alerta; sin lector gris; sin proveedor nunca alerta', () => {
  const sf = conciliacionBandeja.sin_factura;
  const cof = sf.con_lector.find((p) => p.clave === '1');
  const all = sf.con_lector.find((p) => p.clave === '2');
  // H8-2: Fedefarma (F06, sin conciliación) → «Leído, sin conciliación automática», nunca alerta; 2 ausentes excluidos.
  const ok = DIAS_ALERTA_SIN_FACTURA === 30 && sf.dias_alerta === 30
    && sf.totales.alertas === 2 && sf.totales.importe_alertas === 84.3 && sf.totales.alertas_sin_importe === 1
    && isDeepStrictEqual(sf.con_lector.filter((p) => p.alertas.length).map((p) => p.clave), ['1'])
    && !sf.con_lector.some((p) => p.clave === '4')
    && isDeepStrictEqual(sf.leido_sin_conciliacion.map((p) => [p.clave, p.proveedor, p.albaranes, p.importe]), [['4', 'FEDEFARMA', 3, 455]])
    && conciliacionBandeja.facturas.find((x) => x.factura_id === F(6)).conciliacion === null
    && isDeepStrictEqual(sf.excluidos_ausentes, { albaranes: 2, importe: 130.5, sin_importe: 0 })
    && isDeepStrictEqual(cof.alertas.map((a) => [a.numero_albaran, a.dias, a.importe]), [['77501', 51, 84.3], ['77502', 35, null]])
    // H8-6: + una devolución de COFARES en plazo (−15) y, en ALLIANCE, la de 0,00, la positiva y la discrepancia (no entran).
    && cof.recientes.albaranes === 2 && cof.recientes.importe === 105
    && all.alertas.length === 0 && all.recientes.albaranes === 4 && all.anteriores.albaranes === 412 && all.anteriores.sin_importe === 3
    // H8-5: más COFARES (41) y HPLUS CONSUMO (42) pendientes de automatizar.
    && isDeepStrictEqual(sf.sin_lector.map((s) => [s.clave, s.identificado]), [['37', true], ['41', true], ['88', true], ['42', true], [null, false]])
    && sf.sin_lector[4].proveedor === 'Proveedor sin identificar' && sf.totales.sin_lector.albaranes === 34
    && sf.con_lector.every((p) => !/^Proveedor \d/.test(p.proveedor));
  return si(ok, JSON.stringify({ totales: sf.totales, con: sf.con_lector.map((p) => [p.clave, p.proveedor, p.alertas.length]) }));
});
comprobar('H8-6: Devoluciones (abono en bloque): una de cada tipo y una reciente; 0,00, reservada, positiva, discrepancia y otro proveedor no entran', () => {
  const sf = conciliacionBandeja.sin_factura;
  const tipos = sf.devoluciones_bloque.map((b) => [b.tipo, b.albaranes, b.importe, b.detalle.map((a) => a.numero_albaran).join()]);
  const clas = DEVOLUCIONES_H8_6.map((d) => [d.caso, clasificarAbonoEnBloque(d, ULTIMA_FACTURA_ALLIANCE_H8_6)]);
  const enBloque = new Set(sf.devoluciones_bloque.flatMap((b) => b.detalle.map((a) => a.numero_albaran)));
  const fuera = DEVOLUCIONES_H8_6.filter((d) => d.esperado === null).map((d) => d.numero_albaran);
  const cob = coberturaProveedores(conciliacionBandeja.facturas, sf);
  const ok = isDeepStrictEqual(tipos, [['SAFA', 2, -123.36, 'DV-SAFA-01,DV-SAFA-02'], ['SAFA_RECIENTE', 1, -12.4, 'DV-SAFA-03'],
    ['ECO360', 1, -30, 'DV-ECO-01'], ['SAFA_CADUCITATS', 1, -8.9, 'DV-CAD-01']])
    && isDeepStrictEqual(sf.grupos.DEVOLUCION_BLOQUE, { albaranes: 5, importe: -174.66, sin_importe: 0 })
    && sf.devoluciones_bloque.every((b) => b.nota === NOTA_ABONO_EN_BLOQUE[b.tipo])
    && clas.filter(([, c]) => c.discrepancia).map(([k]) => k).join() === 'discrepancia'
    && clas.filter(([, c]) => c.tipo === null).map(([k]) => k).join() === 'importe_cero,reservada,positiva,discrepancia,otro_proveedor'
    && fuera.every((n) => !enBloque.has(n))
    // Nunca alerta, ni en «pendiente de automatizar», ni en la cobertura.
    && sf.totales.alertas === 2 && sf.con_lector.every((p) => p.alertas.every((a) => !/^DV-/.test(a.numero_albaran ?? '')))
    && !sf.sin_lector.some((s) => s.clave === '143') && !cob.some((f) => f.clave.includes('143'))
    && isDeepStrictEqual(PROVEEDORES_ABONO_EN_BLOQUE.map((p) => [p.id, p.literal, p.tipo]),
      [['2', '1.- SAFA', 'SAFA'], ['154', '6- PLATAF. ECO360 AH', 'ECO360'], ['143', 'SAFA CADUCITATS I DEVOLUCIONS', 'SAFA_CADUCITATS']]);
  return si(ok, JSON.stringify({ tipos, grupo: sf.grupos.DEVOLUCION_BLOQUE, clas }));
});
comprobar('H8-3/H8-4/H8-5/H8-6: Sin factura: grupos exhaustivos y excluyentes que suman el total (617 > 50); sin poder comprobar y anteriores de leído visibles', () => {
  const sf = conciliacionBandeja.sin_factura;
  const suma = GRUPOS_SIN_FACTURA.reduce((a, g) => a + sf.grupos[g].albaranes, 0);
  const sumaImp = Math.round(GRUPOS_SIN_FACTURA.reduce((a, g) => a + (sf.grupos[g].importe ?? 0), 0) * 100) / 100;
  const sumaSin = GRUPOS_SIN_FACTURA.reduce((a, g) => a + sf.grupos[g].sin_importe, 0);
  const log = sf.con_lector.find((p) => p.clave === '7');
  const fed = sf.leido_sin_conciliacion.find((p) => p.clave === '4');
  const ok = isDeepStrictEqual(Object.keys(sf.grupos), [...GRUPOS_SIN_FACTURA])
    && sf.total.albaranes === 617 && suma === 617 && sumaImp === 54758.8 && sf.total.importe === 54758.8 && sumaSin === sf.total.sin_importe
    && sf.limite_detalle === 100 && sf.con_lector.every((p) => p.alertas.length === Math.min(p.alertas_total, 100))
    && log?.sin_desde.albaranes === 1 && log.alertas_total === 0
    && fed?.anteriores.albaranes === 6 && fed.albaranes === 3;
  return si(ok, JSON.stringify({ total: sf.total, suma, sumaImp, sumaSin }));
});
comprobar('H8-4: Sin factura: nombres comerciales sin prefijo de Farmatic, traspasos entre farmacias aparte y fuera de la cobertura', () => {
  const sf = conciliacionBandeja.sin_factura;
  const nombre = (k) => sf.con_lector.find((p) => p.clave === k)?.proveedor;
  const cob = coberturaProveedores(conciliacionBandeja.facturas, sf);
  const ok = nombre('2') === 'ALLIANCE' && nombre('9') === 'HEFAME' && nombre('7') === 'LOGISTAPHARMA'
    && sf.con_lector.find((p) => p.clave === '9').anteriores.albaranes === 134
    && sf.sin_lector.find((s) => s.clave === '37').proveedor === 'LABORATORIOS ISDIN (FICTICIO)'
    && [...sf.con_lector, ...sf.sin_lector, ...sf.leido_sin_conciliacion].every((p) => !/^\s*\d+\s*\.?\s*-/.test(p.proveedor))
    && isDeepStrictEqual(sf.traspasos.map((t) => [t.clave, t.farmacia_origen, t.proveedor, t.albaranes, t.importe]), [['40', 'RITA', 'FFARMACIA RITA', 12, 1840]])
    && !sf.sin_lector.some((s) => s.clave === '40')
    && !cob.some((f) => f.clave.includes('40') || (f.tipo === 'SIN_LECTOR' && /RITA/.test(f.proveedor)))
    && TRASPASOS_ENTRE_FARMACIAS.length === 1 && TRASPASOS_ENTRE_FARMACIAS[0].farmacia === 'RITA';
  return si(ok, JSON.stringify({ con: sf.con_lector.map((p) => [p.clave, p.proveedor]), traspasos: sf.traspasos }));
});
comprobar('H8-5: Sin factura: detalle por bloque (≤ 100, del más antiguo al más reciente) que cuadra con su recuento; HPLUS = HEFAME', () => {
  const sf = conciliacionBandeja.sin_factura;
  const bloques = [
    ...sf.con_lector.filter((p) => p.alertas_total > 0).map((p) => ['alerta', p.clave, p.alertas_total, p.alertas]),
    ...sf.con_lector.filter((p) => p.sin_desde.albaranes > 0).map((p) => ['sin_desde', p.clave, p.sin_desde.albaranes, p.detalle_sin_desde]),
    ...sf.leido_sin_conciliacion.map((p) => ['leido', p.clave, p.albaranes, p.detalle]),
    ...sf.sin_lector.map((p) => ['pendiente', p.clave, p.albaranes, p.detalle]),
    ...sf.traspasos.map((p) => ['traspaso', p.clave, p.albaranes, p.detalle]),
  ];
  const ordenado = (xs) => xs.every((a, i) => i === 0 || a.dias === null || (xs[i - 1].dias !== null && xs[i - 1].dias >= a.dias));
  const malos = bloques.filter(([, , n, xs]) => xs.length !== Math.min(n, sf.limite_detalle) || !ordenado(xs)).map(([b, k]) => `${b}:${k}`);
  const hplus = sf.sin_lector.find((s) => s.clave === '42');
  const isdin = sf.sin_lector.find((s) => s.clave === '37');
  const ok = malos.length === 0 && bloques.length === 9
    && hplus?.proveedor === 'HEFAME' && hplus.literal_farmatic === 'HPLUS CONSUMO'
    && sf.con_lector.find((p) => p.clave === '2').literal_farmatic === 'SAFA' && isdin.literal_farmatic === null
    && isdin.detalle[0].dias === 37 && isdin.detalle[0].numero_albaran === 'IS-001'
    && sf.sin_lector.find((s) => s.clave === '88').detalle[0].importe === null
    && sf.leido_sin_conciliacion[0].detalle.map((a) => a.numero_albaran).join() === 'FD-ALB-3301,FD-ALB-3302,FD-ALB-3303';
  return si(ok, JSON.stringify({ malos, n: bloques.length, hplus, isdin: isdin?.detalle[0] }));
});
comprobar('H8-5: Cobertura: una fila por nombre comercial (COFARES con sus pendientes de Farmatic en la misma fila; HPLUS en HEFAME); sin duplicados', () => {
  const sf = conciliacionBandeja.sin_factura;
  const cob = coberturaProveedores(conciliacionBandeja.facturas, sf);
  const nombre = (f) => (f.tipo === 'LECTOR' ? f.nombre_mostrado : f.proveedor);
  const claves = cob.map((f) => `${f.tipo === 'SIN_LECTOR' && f.clave === 'farmatic:sin_identificar' ? 'sin:' : ''}${claveNombreProveedor(nombre(f))}`);
  const cof = cob.filter((f) => /COFARES/.test(nombre(f)));
  const hef = cob.filter((f) => /HEFAME/.test(nombre(f)));
  const ok = new Set(claves).size === claves.length
    && cof.length === 1 && cof[0].tipo === 'LECTOR' && isDeepStrictEqual(cof[0].pendientes, { albaranes: 6, importe: 742.1, sin_importe: 0 })
    && hef.length === 1 && hef[0].tipo === 'LECTOR' && isDeepStrictEqual(hef[0].pendientes, { albaranes: 3, importe: 87.6, sin_importe: 0 })
    && isDeepStrictEqual(cob.filter((f) => f.tipo === 'SIN_LECTOR').map((f) => [f.proveedor, f.albaranes]),
      [['LABORATORIOS ISDIN (FICTICIO)', 18], ['DISTRIBUCIONES BETA (FICTICIO)', 5], ['Proveedor sin identificar', 2]]);
  return si(ok, JSON.stringify(cob.map((f) => [f.tipo, nombre(f), f.tipo === 'LECTOR' ? f.pendientes : f.albaranes])));
});
comprobar('H5: listado: hoy, vencimiento próximo y "+N", importe pendiente, posible duplicado', () => {
  const f = (n) => facturas.facturas.find((x) => x.factura_id === F(n));
  const ok = facturas.hoy === '2026-11-02'
    && f(4).vencimiento_proximo.fecha_vencimiento === '2026-11-15' && f(4).vencimientos_total === 4 && !f(4).vencimiento_vencido
    && f(7).vencimiento_proximo.fecha_vencimiento === '2026-11-21' && f(7).vencimientos_total === 2
    && f(6).vencimiento_proximo.importe === null && f(6).importe_total === null
    && facturas.facturas.filter((x) => x.posible_duplicado).map((x) => x.factura_id).sort().join() === [F(1), F(8)].join()
    && facturas.facturas.every((x) => x.proveedor_etiqueta && x.proveedor_grupo);
  const v = (fecha, orden) => ({ fecha_vencimiento: fecha, orden, importe: 1 });
  const puros = vencimientoProximo([v('2026-10-01', 1), v('2026-10-20', 2)], '2026-11-02').vencido === true
    && vencimientoProximo([v('2026-10-01', 1), v('2026-10-20', 2)], '2026-11-02').proximo.orden === 2
    && vencimientoProximo([v(null, 2), v(null, 1)], '2026-11-02').proximo.orden === 1
    && vencimientoProximo([], '2026-11-02').proximo === null;
  return si(ok && puros, JSON.stringify({ hoy: facturas.hoy, f4: f(4).vencimiento_proximo?.fecha_vencimiento, puros }));
});
comprobar('H5: insignias del listado (posible duplicado, abono y sentido no documentado por la regla de Pío)', () => {
  const ins = Object.fromEntries(facturas.facturas.map((x) => [x.factura_id.slice(-2), insigniasFactura(x).map((i) => i.clave).join('+')]));
  return si(isDeepStrictEqual(ins, { '01': 'posible-duplicado', '02': '', '03': 'sentido-no-documentado', '04': '', '05': 'sentido-no-documentado',
    '06': 'sentido-no-documentado', '07': 'abono', '08': 'posible-duplicado' }), JSON.stringify(ins));
});
comprobar('H5: impuestos de las fixtures coherentes con los totales de cada factura (sin tramos si faltan base o IVA)', () => {
  const malas = Object.values(facturaDetalle).filter((d) => {
    const x = d.impuestos;
    if (d.factura.base_imponible_total === null || d.factura.iva_total === null) return x.length !== 0;
    const s = (k) => Math.round(x.reduce((a, t) => a + (t[k] ?? 0), 0) * 100) / 100;
    return x.length === 0 || s('base_imponible') !== d.factura.base_imponible_total || s('cuota_iva') !== d.factura.iva_total;
  });
  return si(malas.length === 0, malas.map((d) => d.factura.numero_factura).join(', '));
});
comprobar('H5: avisos del detalle (diferencia del motor, albarán no localizado, sentido nunca rojo) y PDF no legible por cf_lectura', () => {
  const a3 = avisosFactura(facturaDetalle[F(3)]).map((a) => a.clave);
  const a2 = avisosFactura(facturaDetalle[F(2)]);
  const sentido2 = a2.find((a) => a.codigo === 'SENTIDO_NO_DOCUMENTADO');
  const pdf = Object.values(facturaDetalle).every((d) => isDeepStrictEqual(d.pdf_original, PDF_ORIGINAL) && d.pdf_original.disponible === false);
  const otras = facturaDetalle[F(3)].otras_facturas_pdf.map((o) => o.factura_id).join() === F(4) && facturaDetalle[F(4)].otras_facturas_pdf.map((o) => o.factura_id).join() === F(3);
  return si(['diferencia', 'lineas-SIN:SIN_COINCIDENCIA', 'sentido'].every((k) => a3.includes(k)) && sentido2?.color === 'naranja' && pdf && otras
    && CONSULTAS_POR_BLOQUE.facturaDetalle.includes('factura_otras_pdf'), JSON.stringify({ a3, sentido2, pdf, otras }));
});
comprobar('H5: historial en texto llano (eventos de las fixtures traducidos)', () => {
  const ev = [...new Set(Object.values(facturaDetalle).flatMap((d) => d.historial.map((h) => h.evento)))];
  const sin = ev.filter((e) => textoEvento(e) === e);
  return si(sin.length === 0, sin.join(', '));
});

// --- Casos H5-8 --------------------------------------------------------------------
comprobar('H5-8: equivalencias de nombre comercial con fuente src/ fichero:línea; sin equivalencia o en conflicto → null', () => {
  // H8-5: única fuente que no es src/: HPLUS CONSUMO → HEFAME, decisión de Pío (22/11/2026), solo por su CIF y su literal.
  const DECISION_PIO = 'decisión de Pío, 22/11/2026';
  // H7-REAL-7: KENVUE (JNTL CONSUMER… / JHONSON & JHONSON), decisión de Pío (25/11/2026), solo por el literal.
  const DECISION_KENVUE = 'decisión de Pío, 25/11/2026';
  const porDecision = [...Object.entries(COMERCIAL_POR_CIF), ...Object.entries(COMERCIAL_POR_LITERAL)].filter(([, e]) => e.fuente === DECISION_PIO);
  const porKenvue = [...Object.entries(COMERCIAL_POR_CIF), ...Object.entries(COMERCIAL_POR_LITERAL)].filter(([, e]) => e.fuente === DECISION_KENVUE);
  const fuentes = [...Object.values(COMERCIAL_POR_CIF), ...Object.values(COMERCIAL_POR_LITERAL)]
    .every((e) => (/^src\/facturas\/[\w/]+\.py:\d+$/.test(e.fuente) || e.fuente === DECISION_PIO || e.fuente === DECISION_KENVUE) && /^[A-Z][A-Z ]*$/.test(e.nombre))
    && isDeepStrictEqual(porDecision.map(([k, e]) => [k, e.nombre]), [['B30462451', 'HEFAME'], ['HPLUSCONSUMO', 'HEFAME']])
    && porKenvue.every(([k, e]) => !Object.hasOwn(COMERCIAL_POR_CIF, k) && e.nombre === 'KENVUE')
    && nombreComercial(null, 'JNTL Consumer Health (Spain), S.L.') === 'KENVUE' && nombreComercial(null, 'JHONSON & JHONSON') === 'KENVUE'
    && nombreComercial(null, 'KENVUE') === 'KENVUE';
  const casos = [
    [nombreComercial('F30004444', null), 'HEFAME'], [nombreComercial('f-30.004.444', 'Otro literal'), 'HEFAME'],
    [nombreComercial(null, 'HDAD.FMCTCA.MEDIT.,S.C.L.'), 'HEFAME'], [nombreComercial('A50004324', null), 'ALLIANCE'],
    [nombreComercial(null, 'Alliance Healthcare España, S.A.'), 'ALLIANCE'], [nombreComercial('F-08-173395', null), 'FEDEFARMA'],
    [nombreComercial('ESA61674347', null), 'LOGISTA PHARMA'], [nombreComercial(null, 'GRUPO COFARES'), 'COFARES'],
    [nombreComercial(null, 'COFARES'), null], // sin equivalencia en src: literal del PDF
    [nombreComercial(null, 'FEDEFARMA'), null], [nombreComercial('B00000003', 'LABORATORIO X'), null],
    [nombreComercial('F30004444', 'ALLIANCE HEALTHCARE'), null], // CIF y literal en conflicto: falla cerrado
    [nombreComercial(null, null), null],
    // H8-5: HPLUS CONSUMO = HEFAME (decisión de Pío), por CIF y por literal; la razón social real sigue debajo.
    [nombreComercial('B30462451', 'HPLUS CONSUMO, S.L.'), 'HEFAME'], [nombreComercial(null, 'HPLUS CONSUMO SL'), 'HEFAME'],
    [razonSocialSecundaria('HEFAME', 'HPLUS CONSUMO, S.L.'), 'HPLUS CONSUMO, S.L.'],
    [razonSocialSecundaria('HEFAME', 'HDAD.FMCTCA.MEDIT.,S.C.L.'), 'HDAD.FMCTCA.MEDIT.,S.C.L.'], [razonSocialSecundaria('HEFAME', 'Hefame'), null],
    [razonSocialSecundaria(null, 'COFARES'), null],
  ];
  const malos = casos.filter(([a, b]) => a !== b);
  return si(fuentes && malos.length === 0, JSON.stringify(malos));
});
comprobar('H5-8: listado, filtro, Inicio y detalle con nombre comercial + razón social del PDF (mismo criterio)', () => {
  const f5 = facturas.facturas.find((f) => f.factura_id === F(5));
  const f2 = facturas.facturas.find((f) => f.factura_id === F(2));
  const f7 = facturas.facturas.find((f) => f.factura_id === F(7));
  const op = Object.fromEntries(facturas.proveedores_filtro.map((o) => [o.clave, o.comercial]));
  const pv = Object.fromEntries(proveedores.proveedores.map((p) => [p.clave, p.comercial]));
  const mapa = proveedores.mapa_documentos.filas.find((x) => x.clave === 'cif:F30004444');
  const det = facturaDetalle[F(5)].proveedor;
  const inicio = JSON.parse(readFileSync(join(DTO, 'inicio.json'), 'utf8'));
  const vAl = inicio.proximos_vencimientos.filter((v) => v.proveedor_comercial === 'ALLIANCE').length;
  const casosF5 = inicio.atencion.grupos.flatMap((g) => g.casos).filter((c) => c.factura_id === F(5));
  return si(f5.proveedor_comercial === 'HEFAME' && f5.proveedor_razon_social === 'HDAD.FMCTCA.MEDIT.,S.C.L.' && f5.proveedor_cif_comparable === 'F30004444'
    && f2.proveedor_comercial === 'ALLIANCE' && f2.proveedor_razon_social === 'Alliance Healthcare España'
    && f7.proveedor_comercial === null && f7.proveedor_razon_social === 'COFARES'
    && isDeepStrictEqual(op, pv) && op['cif:F30004444'] === 'HEFAME' && op['cif:B00000003'] === 'ALLIANCE' && op['cif:A00000001'] === null
    && mapa?.comercial === 'HEFAME' && det.comercial === 'HEFAME' && det.razon_social === 'HDAD.FMCTCA.MEDIT.,S.C.L.' && det.cif === 'F30004444'
    && vAl > 0 && casosF5.length > 0 && casosF5.every((c) => c.proveedor_comercial === 'HEFAME'),
  JSON.stringify({ f5, op, pv, det, vAl, casosF5: casosF5.length }));
});
comprobar('H5-8: fiscalidad Hefame (F05) sin tipo de IVA: tramo con tipos null, importes conocidos (positivos)', () => {
  const x = facturaDetalle[F(5)].impuestos;
  const otros = Object.entries(facturaDetalle).filter(([id]) => id !== F(5)).flatMap(([, d]) => d.impuestos);
  return si(x.length === 1 && x[0].tipo_iva === null && x[0].tipo_recargo_equivalencia === null && x[0].concepto === null
    && x[0].cuota_iva > 0 && x[0].cuota_recargo_equivalencia > 0 && otros.every((t) => t.tipo_iva !== null), JSON.stringify(x));
});

// --- Casos TA1 (Trabajadores, datos de ejemplo en memoria) --------------------------
comprobar('TA1/TA-REAL: fichas de ejemplo: PIO 3 completas + 1 media mañana (técnicas); RITA 5 completas + 1 media mañana + 1 media tarde (1 farmacéutica adjunta); titular (FARMACEUTICA_TITULAR) en ambas', () => {
  const s = leerSemilla();
  const de = (f) => s.filter((t) => t.farmacia === f && !esTitular(t));
  const pio = de('PIO');
  const rita = de('RITA');
  const tit = s.filter(esTitular);
  const cuenta = (ts, j) => ts.filter((t) => t.tipo_jornada === j).length;
  const ok = pio.length === 4 && cuenta(pio, 'COMPLETA') === 3 && cuenta(pio, 'MEDIA_MANANA') === 1 && pio.every((t) => t.categoria === 'TECNICA')
    && rita.length === 7 && cuenta(rita, 'COMPLETA') === 5 && cuenta(rita, 'MEDIA_MANANA') === 1 && cuenta(rita, 'MEDIA_TARDE') === 1
    && cuenta(pio, 'MEDIA_TARDE') === 0
    && rita.filter((t) => t.categoria === 'FARMACEUTICA_ADJUNTA').length === 1 && rita.filter((t) => t.categoria === 'TECNICA').length === 6
    && tit.length === 2 && new Set(tit.map((t) => t.farmacia)).size === 2 && new Set(tit.map((t) => t.nombre)).size === 1
    // TA-REAL: valores del esquema (migración 31) y fecha de alta obligatoria.
    // TA-FICHA: Paula (RITA, media mañana) con alta el 1 de julio (derecho proporcional); el resto, 1 de enero.
    && s.every((t) => CATEGORIAS.includes(t.categoria) && JORNADAS.includes(t.tipo_jornada)
      && t.fecha_alta === (t.id === 'e0000000-0000-4000-8000-000000000016' ? '2026-07-01' : '2026-01-01'))
    // TA1-2: jornada en horas diarias (lunes a viernes): completa 8 h; media mañana 4,5 h (también el titular).
    && [...pio, ...rita].filter((t) => t.tipo_jornada === 'COMPLETA').every((t) => t.horas_diarias === 8)
    && [...pio, ...rita, ...tit].filter((t) => t.tipo_jornada === 'MEDIA_MANANA').every((t) => t.horas_diarias === 4.5)
    // TA1-3: media tarde 3,5 h (17:00–20:30).
    && s.filter((t) => t.tipo_jornada === 'MEDIA_TARDE').every((t) => t.horas_diarias === 3.5)
    && s.every((t) => !('porcentaje_jornada' in t));
  return si(ok, JSON.stringify({ pio: pio.length, rita: rita.length, tit: tit.length }));
});
comprobar('TA1: solo nombre (sin DNI ni más datos personales); cada ficha pasa la validación de alta; ids únicos', () => {
  const s = leerSemilla();
  const permitidos = ['id', 'farmacia', 'nombre', 'categoria', 'tipo_jornada', 'horas_diarias', 'fecha_alta'];
  const extra = s.flatMap((t) => Object.keys(t).filter((k) => !permitidos.includes(k)));
  const invalidas = s.filter(({ id, ...t }) => !validarTrabajadora(t, 'alta').ok); // eslint-disable-line no-unused-vars
  const sinDni = !JSON.stringify(s).match(/\b\d{8}[A-Z]\b|dni|nif/i);
  return si(extra.length === 0 && invalidas.length === 0 && sinDni && new Set(s.map((t) => t.id)).size === s.length,
    JSON.stringify({ extra, invalidas: invalidas.map((t) => t.nombre) }));
});
comprobar('TA1-2: convenio por año (referencia 40 h/sem provisional) y objetivo = jornada máxima × horas semanales / referencia', () => {
  const conv = CONVENIO_ANUAL.map((c) => [c.anio, c.jornada_max_horas, c.horas_semanales_referencia, c.asuntos_propios_dias, c.permiso_medico_horas, c.estado].join());
  const a = crearAdaptadorRrhhFixtures({ anioReferencia: 2026 });
  const ficha = (id) => a.trabajadora(id);
  const obj = (id) => ficha(id).objetivos.map((o) => o.objetivo_horas);
  const casos = [
    [obj('e0000000-0000-4000-8000-000000000001'), [1767, 1752, 1752]], // completa 8 h/día = 40 h/sem = 100 %
    [obj('e0000000-0000-4000-8000-000000000004'), [993.9, 985.5, 985.5]], // PIO media mañana 4,5 h/día (ejemplo de Pío: 993,9 h)
    [obj('e0000000-0000-4000-8000-000000000016'), [993.9, 985.5, 985.5]], // RITA media mañana 4,5 h/día
    [obj('e0000000-0000-4000-8000-000000000017'), [773.1, 766.5, 766.5]], // TA1-3: RITA media tarde 3,5 h/día (17,5 h/sem)
    [ficha('e0000000-0000-4000-8000-000000000017').objetivos.map((o) => o.porcentaje_derivado), [43.75, 43.75, 43.75]],
    [obj('e0000000-0000-4000-8000-000000000021'), [null, null, null]], // titular PIO
    [obj('e0000000-0000-4000-8000-000000000022'), [null, null, null]], // titular RITA
    [ficha('e0000000-0000-4000-8000-000000000004').objetivos.map((o) => o.porcentaje_derivado), [56.25, 56.25, 56.25]],
    [objetivosAnuales({ horas_diarias: 6, computa_convenio: true }).map((o) => o.objetivo_horas), [1325.3, 1314, 1314]],
  ];
  const malos = casos.filter(([x, e]) => !isDeepStrictEqual(x, e));
  return si(isDeepStrictEqual(conv, ['2026,1767,40,1,24,FIRMADO_PENDIENTE_PUBLICACION', '2027,1752,40,0,24,FIRMADO_PENDIENTE_PUBLICACION',
    '2028,1752,40,0,24,FIRMADO_PENDIENTE_PUBLICACION']) && malos.length === 0, JSON.stringify(malos));
});

// --- Casos TA2 (calendario, datos de ejemplo en memoria) ---------------------------
comprobar('TA2: semilla de eventos: solo fichas de ejemplo, tipos de TA2 sin JORNADA, franjas propias, notas válidas, noviembre de 2026', () => {
  const s = leerSemillaEventos();
  const fichas = new Map(leerSemilla().map((t) => [t.id, t]));
  const malos = s.ausencias.filter((a) => !fichas.has(a.trabajadora_id) || !TIPOS_EVENTO.includes(a.tipo) || a.tipo === 'JORNADA'
    || a.hasta < a.desde || !a.desde.startsWith('2026-11') || !a.hasta.startsWith('2026-11')
    || (a.franja !== undefined && !FRANJAS_DE_JORNADA[fichas.get(a.trabajadora_id).tipo_jornada].includes(a.franja))
    || (a.nota !== undefined && !(leerNota(a.nota).ok && leerNota(a.nota).nota === a.nota)));
  const permitidos = ['trabajadora_id', 'tipo', 'desde', 'hasta', 'franja', 'nota'];
  const extra = s.ausencias.flatMap((a) => Object.keys(a).filter((k) => !permitidos.includes(k)));
  // TA2-2: notas de ejemplo sin datos de salud: nunca en permisos médicos ni bajas.
  const notaSalud = s.ausencias.filter((a) => a.nota !== undefined && (a.tipo === 'PERMISO_MEDICO' || a.tipo === 'BAJA' || /m[eé]dic|diagn|enferm|salud/i.test(a.nota)));
  return si(malos.length === 0 && extra.length === 0 && notaSalud.length === 0 && s.jornada_habitual.desde === '2026-11-02' && s.jornada_habitual.hasta === '2026-11-29'
    && s.confirmado.desde === '2026-11-02' && s.confirmado.hasta === '2026-11-08', JSON.stringify({ malos, extra, notaSalud }));
});
comprobar('TA2-2: carga por franja: 21 franjas/día (8 completas × 2 + 5 medias) × 20 laborables = 420; 41 de ausencia (23 días de persona); 105 confirmados', () => {
  const a = crearAdaptadorRrhhFixtures({ anioReferencia: 2026 });
  const evs = a.eventos().filter((e) => e.fecha.startsWith('2026-11')); // TA-FICHA suma eventos fuera de noviembre
  const aus = evs.filter((e) => e.tipo !== 'JORNADA');
  const tipos = new Set(evs.map((e) => e.tipo));
  const ok = evs.length === 420 && aus.length === 41 && new Set(aus.map((e) => `${e.trabajadora_id}|${e.fecha}`)).size === 23
    && TIPOS_PINTABLES.every((t) => tipos.has(t)) && aus.some((e) => e.farmacia === 'PIO') && aus.some((e) => e.farmacia === 'RITA')
    && evs.filter((e) => e.estado === 'CONFIRMADO').length === 105 && evs.every((e) => esLaborable(e.fecha))
    && new Set(evs.map((e) => `${e.trabajadora_id}|${e.fecha}|${e.franja}`)).size === evs.length; // uno por persona, día y franja
  return si(ok, JSON.stringify({ n: evs.length, aus: aus.length }));
});
comprobar('TA2-3: franjas y horas de la ficha (completa mañana 4,5 h + tarde 3,5 h = 8 h; medias, todas sus horas en su franja); farmacia de la ficha; sin historial de la carga', () => {
  const a = crearAdaptadorRrhhFixtures({ anioReferencia: 2026 });
  const fichas = new Map(a.trabajadoras('AMBAS', false).trabajadoras.map((t) => [t.id, t]));
  const malos = a.eventos().filter((e) => {
    const t = fichas.get(e.trabajadora_id);
    // TA-REAL: horas null (las de la ficha) y horas_efectivas como la vista.
    return !t || e.horas !== null || e.horas_efectivas !== horasFranja(t, e.franja) || !FRANJAS_DE_JORNADA[t.tipo_jornada].includes(e.franja) || e.farmacia !== t.farmacia;
  });
  // Cada persona suma al día sus horas diarias (completa: 4,5 + 3,5 = 8).
  const porDia = new Map();
  for (const e of a.eventos().filter((x) => x.fecha.startsWith('2026-11'))) porDia.set(`${e.trabajadora_id}|${e.fecha}`, (porDia.get(`${e.trabajadora_id}|${e.fecha}`) ?? 0) + e.horas_efectivas);
  const sumaMal = [...porDia].filter(([k, h]) => fichas.get(k.split('|')[0]).horas_diarias !== h);
  const aina = (fr) => a.eventos().find((e) => e.trabajadora_id === 'e0000000-0000-4000-8000-000000000001' && e.franja === fr).horas_efectivas;
  const irene = a.eventos().find((e) => e.trabajadora_id === 'e0000000-0000-4000-8000-000000000017');
  const conf = isDeepStrictEqual(HORARIO_COMPLETA, { MANANA: { horas: 4.5, desde: '9:00', hasta: '13:30' }, TARDE: { horas: 3.5, desde: '17:00', hasta: '20:30' } })
    && HORAS_VISTA_COMPLETA.MANANA === HORARIO_COMPLETA.MANANA.horas && HORAS_VISTA_COMPLETA.TARDE === HORARIO_COMPLETA.TARDE.horas;
  return si(malos.length === 0 && sumaMal.length === 0 && conf && aina('MANANA') === 4.5 && aina('TARDE') === 3.5 && irene.franja === 'TARDE' && irene.horas_efectivas === 3.5
    && a.historialEventos('AMBAS').length === 0, JSON.stringify({ malos: malos.slice(0, 3), sumaMal: sumaMal.slice(0, 3) }));
});
comprobar('TA2-2: días con mañana y tarde distintas (Núria 10 nov, Rosa 18 nov) y notas de ejemplo (≤ 200, sin datos de salud)', () => {
  const a = crearAdaptadorRrhhFixtures({ anioReferencia: 2026 });
  const dia = (n, f) => a.eventos().filter((e) => e.trabajadora_id === `e0000000-0000-4000-8000-0000000000${n}` && e.fecha === f)
    .sort((x, y) => x.franja.localeCompare(y.franja)).map((e) => `${e.franja}:${e.tipo}`).join();
  const notas = a.eventos().filter((e) => e.nota !== null);
  return si(dia('03', '2026-11-10') === 'MANANA:JORNADA,TARDE:PERMISO_MEDICO' && dia('15', '2026-11-18') === 'MANANA:ASUNTOS_PROPIOS,TARDE:JORNADA'
    && notas.length === 5 && notas.every((e) => e.nota.length <= LARGO_NOTA && e.tipo !== 'PERMISO_MEDICO' && e.tipo !== 'BAJA'),
  JSON.stringify({ n: notas.length, nuria: dia('03', '2026-11-10'), rosa: dia('15', '2026-11-18') }));
});
comprobar('TA2-4: mensajes en días laborables × personas (Rellenado 2027: 261 × 5) y ANOTAR omite vacías y confirmadas contándolas', () => {
  const a = crearAdaptadorRrhhFixtures({ anioReferencia: 2026 });
  const pio = a.trabajadoras('PIO', false).trabajadoras.map((t) => t.id);
  const pedir = (b) => { const v = validarPeticionEventos(b); if (!v.ok) throw new Error(JSON.stringify(v.errores)); return a.cambiarEventos(v.peticion, 'Marc'); };
  const r = pedir({ accion: 'RELLENAR', trabajadora_ids: pio, desde: '2027-01-01', hasta: '2027-12-31' });
  const d = a.deshacerEventos(r.cambio.id, 'Marc');
  const aina = 'e0000000-0000-4000-8000-000000000001';
  // Aina 6-8 nov: 6 confirmado (2 franjas), 7-8 fin de semana (4 vacías) → nada que anotar.
  const n = pedir({ accion: 'ANOTAR', celdas: ['2026-11-06', '2026-11-07', '2026-11-08'].map((fecha) => ({ trabajadora_id: aina, fecha })), nota: 'Formación' });
  const textos = [describirCambio(r.cambio), describirCambio(d.cambio)];
  return si(pio.length === 5 && isDeepStrictEqual(textos, ['Rellenado 2027: 261 días laborables × 5 personas', 'Deshecho «Rellenado 2027»: 261 días laborables × 5 personas'])
    && n.cambio === null && n.omitidas_vacias === 4 && n.omitidas_confirmadas === 2 && AVISO_NOTA_VACIA === 'Pinta primero un evento para poder anotarlo',
  JSON.stringify({ textos, n }));
});
comprobar('TA2: colores orientativos de Pío (jornada azul, vacaciones amarillo, asuntos propios violeta, descanso turquesa, baja gris)', () => {
  const c = COLOR_TIPO_EVENTO;
  return si(c.JORNADA === '#2f6fd0' && c.VACACIONES === '#e3b505' && c.ASUNTOS_PROPIOS === '#8a55c9' && c.DESCANSO_COMPENSATORIO === '#1a9e96'
    && c.BAJA === '#8a9590' && Object.keys(c).length === TIPOS_EVENTO.length, JSON.stringify(c));
});

// --- Casos TA-REAL (contrato = migración 31; adaptador FIXTURES con las mismas reglas) --------------
comprobar('TA-REAL: 11 tipos (FESTIVO, TURNO_GUARDIA y LOCALIZADA para TA3, no se pintan); guardia y localizada no suman horas', () => {
  const ta3 = TIPOS_EVENTO.filter((t) => !TIPOS_PINTABLES.includes(t));
  const pintarTa3 = ta3.map((tipo) => validarPeticionEventos({ accion: 'PINTAR', tipo, celdas: [{ trabajadora_id: 'e0000000-0000-4000-8000-000000000001', fecha: '2026-12-07' }] }).ok);
  return si(TIPOS_EVENTO.length === 11 && isDeepStrictEqual(ta3, ['FESTIVO', 'TURNO_GUARDIA', 'LOCALIZADA']) && pintarTa3.every((x) => x === false)
    && isDeepStrictEqual([...TIPOS_SIN_HORAS], ['TURNO_GUARDIA', 'LOCALIZADA']) && horasQueSuman({ tipo: 'LOCALIZADA', horas_efectivas: 4.5 }) === 0
    && horasQueSuman({ tipo: 'JORNADA', horas_efectivas: 4.5 }) === 4.5, JSON.stringify({ ta3, pintarTa3 }));
});
comprobar('TA-REAL: titular = FARMACEUTICA_TITULAR (fuera del cómputo); anular no borra; baja no anterior al alta; eventos solo dentro del alta', () => {
  const a = crearAdaptadorRrhhFixtures({ anioReferencia: 2026 });
  const tit = a.trabajadoras('AMBAS', false).trabajadoras.filter(esTitular);
  const clara = 'e0000000-0000-4000-8000-000000000002';
  const antesAlta = a.darDeBaja(clara, '2025-12-31', 'Marc');
  a.darDeBaja(clara, '2026-11-30', 'Marc');
  const v = validarPeticionEventos({ accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ trabajadora_id: clara, fecha: '2026-12-07' }] });
  const fuera = a.cambiarEventos(v.peticion, 'Marc');
  const an = a.anular('e0000000-0000-4000-8000-000000000003', 'Marc');
  const sigue = a.trabajadoras('PIO', true).trabajadoras.some((t) => t.id === an.id && t.anulada);
  return si(tit.length === 2 && tit.every((t) => !t.computa_convenio) && antesAlta === 'BAJA_ANTES_DEL_ALTA' && fuera === 'EVENTO_FUERA_DEL_ALTA'
    && an.anulada === true && sigue && a.trabajadora(an.id).historial[0].accion === 'ANULACION', JSON.stringify({ antesAlta, fuera }));
});
comprobar('TA-REAL-2: la goma anula (no borra; no se lee; la franja queda libre); deshacer un pintado lo anula; lo confirmado no se toca', () => {
  const a = crearAdaptadorRrhhFixtures({ anioReferencia: 2026 });
  const aina = 'e0000000-0000-4000-8000-000000000001';
  const pedir = (b) => { const v = validarPeticionEventos(b); if (!v.ok) throw new Error(JSON.stringify(v.errores)); return a.cambiarEventos(v.peticion, 'Marc'); };
  const goma = pedir({ accion: 'BORRAR', celdas: [{ trabajadora_id: aina, fecha: '2026-11-09' }] });
  const leidos = a.calendario('PIO', '2026-11-09', '2026-11-15').eventos.filter((e) => e.trabajadora_id === aina && e.fecha === '2026-11-09').length;
  const anulados = a.eventosAnulados().filter((e) => e.trabajadora_id === aina && e.fecha === '2026-11-09' && e.anulado === true).length;
  const repinta = pedir({ accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ trabajadora_id: aina, fecha: '2026-11-09' }] });
  const dp = a.deshacerEventos(repinta.cambio.id, 'Marc');
  const conf = pedir({ accion: 'BORRAR', celdas: [{ trabajadora_id: aina, fecha: '2026-11-03' }] });
  return si(goma.cambio?.n === 2 && leidos === 0 && anulados === 2 && repinta.cambio?.creados === 2 && typeof dp === 'object' && dp.cambio.origen === 'DESHACER'
    && a.eventos().filter((e) => e.trabajadora_id === aina && e.fecha === '2026-11-09').length === 0
    && conf.cambio === null && conf.omitidas_confirmadas === 2, JSON.stringify({ goma: goma.cambio?.n, leidos, anulados, conf }));
});
comprobar('TA-REAL-2: SQL de eventos del adaptador REAL: inserción ON CONFLICT … WHERE NOT anulado; lecturas y actualizaciones solo de no anulados; nunca DELETE', () => {
  const tabla = Object.entries(SQL_RRHH).filter(([, s]) => /from public\.eventos_calendario|update public\.eventos_calendario/.test(s));
  const sinFiltro = tabla.filter(([, s]) => !/not (e\.)?anulado/.test(s)).map(([k]) => k);
  const borra = Object.entries(SQL_RRHH).filter(([, s]) => /\bdelete\b/i.test(s)).map(([k]) => k);
  return si(/on conflict \(trabajadora_id, fecha, franja\) where not anulado do nothing/.test(SQL_RRHH.insertarEventos) && tabla.length >= 6
    && sinFiltro.length === 0 && borra.length === 0, JSON.stringify({ sinFiltro, borra }));
});
comprobar('TA-REAL-2: ausencia anulada de ejemplo (Rosa 14–18 sep): 10 franjas anuladas, ninguna se lee', () => {
  const a = crearAdaptadorRrhhFixtures({ anioReferencia: 2026 });
  const rosa = 'e0000000-0000-4000-8000-000000000015';
  const anul = a.eventosAnulados().filter((e) => e.trabajadora_id === rosa && e.fecha >= '2026-09-14' && e.fecha <= '2026-09-18');
  const leidos = a.eventos().filter((e) => e.trabajadora_id === rosa && e.fecha >= '2026-09-14' && e.fecha <= '2026-09-18');
  return si(anul.length === 10 && anul.every((e) => e.anulado === true && e.tipo === 'VACACIONES') && leidos.length === 0, JSON.stringify({ anul: anul.length, leidos: leidos.length }));
});
comprobar('TA-REAL-2: convenio con vacaciones (30 días, «decisión de Pío, pendiente de texto publicado») en 2026–2028; completar solo esos dos campos', () => {
  const a = crearAdaptadorRrhhFixtures({ convenio: [{ ...CONVENIO_ANUAL[0], vacaciones_dias_naturales: null, vacaciones_fuente: null }] });
  const hechos = a.completarVacacionesConvenio([2026], 'Marc');
  return si(VACACIONES_DIAS_NATURALES === 30 && FUENTE_VACACIONES === 'decisión de Pío, pendiente de texto publicado'
    && CONVENIO_ANUAL.every((c) => c.vacaciones_dias_naturales === 30 && c.vacaciones_fuente === FUENTE_VACACIONES)
    && hechos.length === 1 && isDeepStrictEqual(a.convenio()[0], { ...CONVENIO_ANUAL[0] }) && a.completarVacacionesConvenio([2026], 'Marc').length === 0
    && /^update public\.convenio_anual set vacaciones_dias_naturales = \$2, vacaciones_fuente = \$3 where /.test(SQL_RRHH.completarVacaciones), JSON.stringify(hechos));
});
comprobar('TA-REAL-2/2b: ajustes de ejemplo (Rosa 2 días extra en 2026; Clara anulado) con las columnas de producción (farmacia de la ficha, sin autor), notas sin datos de salud; uno no anulado por persona y año', () => {
  const s = leerSemillaAjustes();
  const fichas = new Map(leerSemilla().map((t) => [t.id, t]));
  const malos = s.filter((x) => !fichas.has(x.trabajadora_id) || !validarAjuste({ vacaciones_dias_extra: x.vacaciones_dias_extra, nota: x.nota }).ok || 'autor' in x
    || fichas.get(x.trabajadora_id)?.farmacia !== x.farmacia
    || /salud|diagn|médic|medic|enferm/i.test(x.nota ?? ''));
  const vivos = s.filter((x) => !x.anulada).map((x) => `${x.trabajadora_id}|${x.anio}`);
  return si(malos.length === 0 && new Set(vivos).size === vivos.length && s.length === 2 && s.filter((x) => x.anulada).length === 1, JSON.stringify(malos));
});
comprobar('TA-REAL: notas próximas de ejemplo desde el 13 nov (Rosa 18, Elena 25 y 26; la misma nota del día una vez)', () => {
  const a = crearAdaptadorRrhhFixtures({ anioReferencia: 2026 });
  const n = a.notasProximas('AMBAS', '2026-11-13').map((x) => `${x.nombre}|${x.fecha}`);
  return si(isDeepStrictEqual(n, ['Rosa Camps Oliver|2026-11-18', 'Elena Mas Garriga|2026-11-25', 'Elena Mas Garriga|2026-11-26'])
    && a.notasProximas('RITA', '2026-11-06').length === 2, JSON.stringify(n));
});
comprobar('TA-REAL: errores de la BD → código y mensaje llano (P0001, 42501, 23505, 23514, 23503, 57014/25P03, 53300)', () => {
  const caso = (code, message = 'x') => traducirErrorBd(Object.assign(new Error(message), { code })).codigo;
  const r = [caso('P0001', 'AUTOR_AUSENTE'), caso('P0001', 'FARMACIA_NO_HABILITADA_EN_MODULO:X'), caso('P0001', 'EVENTO_FUERA_DEL_ALTA:a:b'), caso('42501'),
    caso('23505'), caso('23514'), caso('23503'), caso('57014'), caso('25P03'), caso('53300')];
  return si(isDeepStrictEqual(r, ['AUTOR_AUSENTE', 'FARMACIA_NO_HABILITADA_EN_MODULO', 'EVENTO_FUERA_DEL_ALTA', 'PERMISO_DENEGADO', 'DUPLICADO', 'REGLA_TABLA',
    'REGISTRO_RELACIONADO', 'TIEMPO_AGOTADO', 'TIEMPO_AGOTADO', 'SIN_CONEXIONES']), JSON.stringify(r));
});

// --- Casos TA-FICHA (ficha anual y resumen de plantilla, datos de ejemplo) ----------
const fichaEjemplo = (() => {
  const a = crearAdaptadorRrhhFixtures({ anioReferencia: 2026 });
  const cal = a.calendario('AMBAS', '2026-01-01', '2026-12-31');
  const filas = resumenPlantilla(cal.trabajadoras, cal.eventos, a.convenio(), 2026, '2026-11-13', { ajustes: a.ajustes('AMBAS', 2026) });
  return { a, cal, de: (n) => filas.find((f) => f.trabajadora.id === `e0000000-0000-4000-8000-0000000000${n}`), filas };
})();
comprobar('TA-REAL-2: ficha anual: base del convenio + días extra (Rosa 30 + 2 = 32, 32 pendientes; Clara, ajuste anulado: 30); sin dato del convenio, «pendiente»', () => {
  const r = fichaEjemplo.de('15').vacaciones;
  const c = fichaEjemplo.de('02').vacaciones;
  const { a, cal } = fichaEjemplo;
  const t = cal.trabajadoras.find((x) => x.id === 'e0000000-0000-4000-8000-000000000015');
  const sin = calcularFichaAnual(t, cal.eventos, [{ ...a.convenio()[0], vacaciones_dias_naturales: null, vacaciones_fuente: null }], 2026, '2026-11-13',
    { ajustes: a.ajustes('AMBAS', 2026) });
  return si(r.derecho_base === 30 && r.dias_extra === 2 && r.derecho === 32 && r.pendientes === 32 && c.dias_extra === 0 && c.derecho === 30
    && sin.vacaciones.derecho === null && sin.vacaciones.pendientes === null && sin.avisos.some((x) => x.codigo === 'VACACIONES_SIN_DATO'), JSON.stringify({ r, c }));
});
comprobar('TA-FICHA: semilla solo de RITA y fuera de noviembre; reglas en un único punto (30 días del convenio, entero hacia arriba, 1 de octubre)', () => {
  const s = leerSemillaFichaAnual();
  const fichas = new Map(leerSemilla().map((t) => [t.id, t]));
  const malos = [...s.ausencias, ...s.jornada_extra].filter((x) => fichas.get(x.trabajadora_id)?.farmacia !== 'RITA' || x.desde.startsWith('2026-11') || x.hasta.startsWith('2026-11'));
  return si(malos.length === 0 && VACACIONES_DIAS_NATURALES === 30 && REDONDEO_PROPORCIONAL === 'ENTERO_ARRIBA' && AVISO_VACACIONES_DESDE === '10-01',
    JSON.stringify(malos));
});
comprobar('TA-FICHA: vacaciones en días naturales (Sílvia 3–14 ago = 12 + media franja 0,5 + 23–27 nov = 5), media jornada (Paula 5) y alta a mitad de año (derecho 16)', () => {
  const s = fichaEjemplo.de('13').vacaciones;
  const p = fichaEjemplo.de('16').vacaciones;
  return si(isDeepStrictEqual(s.periodos.map((x) => x.dias), [12, 0.5, 5]) && s.disfrutadas === 12.5 && s.planificadas === 5 && s.pendientes === 12.5
    && p.derecho === 16 && p.proporcional && p.disfrutadas === 5, JSON.stringify({ s, p }));
});
comprobar('TA-FICHA/TA-FICHA-2: exceso de horas (Judit 129 h ≈ 16,1 días, con su descanso compensatorio del 6 nov que suma 8 h), baja (Marta 11 días), aviso de octubre (Sílvia sí, Laura no)', () => {
  const j = fichaEjemplo.de('14');
  const cods = (n) => fichaEjemplo.de(n).avisos.map((x) => x.codigo);
  return si(TIPOS_HORAS_COMPUTAN.includes('DESCANSO_COMPENSATORIO') && !TIPOS_HORAS_COMPUTAN.includes('VACACIONES') && !TIPOS_HORAS_COMPUTAN.includes('PERMISO_NO_RETRIBUIDO')
    && j.horas.confirmadas === 1776 && j.horas.exceso === 129 && j.horas.exceso_dias === 16.1 && fichaEjemplo.de('12').dias_baja === 11
    && cods('13').includes('VACACIONES_SIN_PLANIFICAR') && cods('11').length === 0, JSON.stringify({ h: j.horas, s: cods('13'), l: cods('11') }));
});
comprobar('TA-FICHA: libre disposición (Rosa media franja 0,5 de 1), permiso médico (Laura 8 de 24 h), titular sin objetivo; el 30 sep no hay aviso de octubre', () => {
  const { a, cal, de } = fichaEjemplo;
  const silvia = cal.trabajadoras.find((t) => t.id === 'e0000000-0000-4000-8000-000000000013');
  const sep = calcularFichaAnual(silvia, cal.eventos, a.convenio(), 2026, '2026-09-30');
  return si(de('15').libre_disposicion.usadas === 0.5 && de('15').libre_disposicion.restantes === 0.5 && de('11').permiso_medico.usadas === 8
    && de('22').horas.objetivo === null && sep.avisos.length === 0 && fichaEjemplo.filas.length === 13, JSON.stringify(sep.avisos));
});

// --- Casos TA3 (guardias y festivos, datos de ejemplo) ------------------------------
const aG3 = crearAdaptadorRrhhFixtures({ anioReferencia: 2026 });
const g3 = aG3.guardiasTa3;
const g3d = g3.datos();
const fichasG3 = new Map(leerSemilla().map((t) => [t.id, t]));
comprobar('TA3: horario de guardia en un único punto (sábado 6,5 h, domingo 3 h, apoyo 4,5 h, festivo 3 h, localizada sin horas); colores propios', () => {
  const colores = Object.values(COLOR_FARMACIA_GUARDIA).map((c) => c.toLowerCase());
  const deEventos = Object.values(COLOR_TIPO_EVENTO).map((c) => c.toLowerCase());
  return si(isDeepStrictEqual(HORAS_SERVICIO, { GUARDIA_SABADO: 6.5, GUARDIA_DOMINGO: 3, APOYO_SABADO: 4.5, FESTIVO: 3, LOCALIZADA: 0 })
    && isDeepStrictEqual(FARMACIAS_GUARDIA, ['PIO', 'RITA', 'OTRA']) && colores.every((c) => !deEventos.includes(c)) && new Set(colores).size === 3,
  JSON.stringify(HORAS_SERVICIO));
});
comprobar('TA3: semilla de guardias 2026: 53 semanas (una por lunes) rotando PIO/RITA/OTRA; OTRA sin personas; personas de su farmacia y de alta; apoyo distinto', () => {
  const ficha = (id) => aG3.trabajadoras('AMBAS', true).trabajadoras.find((t) => t.id === id);
  const malas = g3d.semanas.filter((s) => s.anulada || reglasSemana(s, ficha) !== null || (s.farmacia !== 'OTRA' && fichasG3.get(s.persona_guardia_id)?.farmacia !== s.farmacia));
  const lunes = g3d.semanas.map((s) => s.lunes);
  return si(malas.length === 0 && g3d.semanas.length === 53 && new Set(lunes).size === 53 && lunes[0] === '2025-12-29' && lunes[52] === '2026-12-28'
    && g3d.semanas.every((s, i) => s.farmacia === ['PIO', 'RITA', 'OTRA'][i % 3]), JSON.stringify(malas.map((s) => s.lunes)));
});
comprobar('TA3: festivos de ejemplo 2026 (15, uno por día, nombre ≤ 60, todos en 2026; el 31 ago sin guardia); guardias de festivo solo en festivos, OTRA sin persona', () => {
  const festivos = new Set(g3d.festivos.filter((f) => !f.anulado).map((f) => f.fecha));
  const malos = g3d.festivos.filter((f) => !validarFestivo({ fecha: f.fecha, nombre: f.nombre }).ok || !f.fecha.startsWith('2026-'));
  const gfMalas = g3d.guardiasFestivo.filter((g) => !festivos.has(g.fecha) || (g.farmacia === 'OTRA') !== (g.persona_id === null)
    || (g.persona_id !== null && fichasG3.get(g.persona_id)?.farmacia !== g.farmacia));
  return si(malos.length === 0 && gfMalas.length === 0 && festivos.size === 15 && g3d.festivos.length === 15 && g3d.guardiasFestivo.length === 14
    && !g3d.guardiasFestivo.some((g) => g.fecha === '2026-08-31'), JSON.stringify({ malos, gfMalas }));
});
comprobar('TA3: persona por defecto de la guardia del festivo (Año Nuevo: semana PIO de Aina → Aina); rotación propia (no siempre la semanal)', () => {
  const v = g3.vista('2026-01-01', '2026-12-31');
  const anio = v.festivos.find((f) => f.fecha === '2026-01-01');
  const distintos = v.festivos.filter((f) => f.guardia && f.semana && f.guardia.farmacia !== f.semana.farmacia).length;
  return si(anio?.guardia?.persona?.id === 'e0000000-0000-4000-8000-000000000001' && distintos >= 5, JSON.stringify({ anio, distintos }));
});
comprobar('TA3: «Guardias del año» de Aina 2026 = 5 semanas, 4 sábados de apoyo, 2 festivos, 71,5 h fuera de cómputo; las horas del año no cambian', () => {
  const r = g3.resumenPersona('e0000000-0000-4000-8000-000000000001', 2026);
  const aina = fichaEjemplo.de('01');
  return si(isDeepStrictEqual([r.semanas_guardia, r.sabados_apoyo, r.festivos_guardia, r.horas_total], [5, 4, 2, 71.5]) && aina.horas.objetivo !== null
    && !TIPOS_HORAS_COMPUTAN.includes('TURNO_GUARDIA') && !TIPOS_HORAS_COMPUTAN.includes('LOCALIZADA') && !TIPOS_HORAS_COMPUTAN.includes('FESTIVO'), JSON.stringify(r));
});
comprobar('TA3: rellenar salta festivos (8 dic 2026); pintar sobre festivo se permite con aviso', () => {
  const a = crearAdaptadorRrhhFixtures({ anioReferencia: 2026 });
  const aina = 'e0000000-0000-4000-8000-000000000001';
  const r = a.cambiarEventos({ accion: 'RELLENAR', trabajadora_ids: [aina], desde: '2026-12-07', hasta: '2026-12-13' }, 'Marc');
  const el8 = a.eventos().filter((e) => e.trabajadora_id === aina && e.fecha === '2026-12-08').length;
  const p = a.cambiarEventos({ accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ trabajadora_id: aina, fecha: '2026-12-08' }] }, 'Marc');
  return si(typeof r === 'object' && r.cambio?.fechas === 4 && el8 === 0 && typeof p === 'object' && isDeepStrictEqual(p.festivos_pintados, ['2026-12-08']),
    JSON.stringify({ r: typeof r === 'object' ? r.cambio?.fechas : r, el8, p: typeof p === 'object' ? p.festivos_pintados : p }));
});
comprobar('TA3-2: festivo de alta entre vacaciones = puente (24 + 28 dic, 25 festivo = 5 días); sin festivo 1 + 1; el objetivo no descuenta festivos', () => {
  const a = crearAdaptadorRrhhFixtures({ anioReferencia: 2026 });
  const aina = 'e0000000-0000-4000-8000-000000000001';
  a.cambiarEventos({ accion: 'PINTAR', tipo: 'VACACIONES', celdas: [{ trabajadora_id: aina, fecha: '2026-12-24' }, { trabajadora_id: aina, fecha: '2026-12-28' }] }, 'Marc');
  const cal = a.calendario('PIO', '2026-01-01', '2026-12-31');
  const t = cal.trabajadoras.find((x) => x.id === aina);
  const dias = (festivos) => calcularFichaAnual(t, cal.eventos, a.convenio(), 2026, '2026-11-13', { festivos }).vacaciones.periodos
    .filter((p) => p.desde >= '2026-12-24').map((p) => p.dias);
  const con = dias(a.guardiasTa3.fechasFestivo(2026));
  const obj = (festivos) => calcularFichaAnual(t, cal.eventos, a.convenio(), 2026, '2026-11-13', { festivos }).horas.objetivo;
  return si(isDeepStrictEqual(con, [5]) && isDeepStrictEqual(dias([]), [1, 1]) && obj([]) === obj(a.guardiasTa3.fechasFestivo(2026)) && obj([]) === 1767,
    JSON.stringify({ con, sin: dias([]), obj: obj([]) }));
});
comprobar('TA3: propuesta SQL (docs/propuesta_tablas_ta3.sql) sin aplicar: autor por cf.autor sin columna, anulado en vez de DELETE, RLS, grants y rollback', () => {
  const ruta = join(RAIZ, '..', 'docs', 'propuesta_tablas_ta3.sql');
  if (!existsSync(ruta)) return 'falta la propuesta';
  const s = readFileSync(ruta, 'utf8');
  const tablas = s.match(/create table public\.\w+ \([^;]*\);/g) ?? [];
  return si(/NO APLICAR/.test(s) && /cf\.autor/.test(s) && tablas.length >= 2 && tablas.every((t) => !/\bautor\b/.test(t))
    && /enable row level security/.test(s) && /grant select, insert, update on [^;]*to cf_trabajadores_web/.test(s) && /grant select on [^;]*to cf_lectura/.test(s)
    && /ROLLBACK/.test(s) && /DECISIONES PARA EL CIRCUITO/.test(s) && !/^grant [^;]*\bdelete\b/im.test(s), 'faltan elementos');
});

// --- H6: Vencimientos (estados de pago, forma por proveedor, marcas) ---------------------------------------------
const semillaPagos = leerSemillaPagos();
const pantallaH6 = construirPantalla(vencimientos, crearAlmacenPagos(semillaPagos).fuente(), { hoy: semillaPagos.hoy, modo: 'FIXTURES' });
comprobar('H6: vencimientos con nombre comercial (como Facturas) y CIF comparable de su factura; FEDEFARMA sin CIF', () => {
  const vs = vencimientos.vencimientos;
  const fact = new Map(facturas.facturas.map((f) => [f.factura_id, f]));
  const igual = vs.every((v) => v.proveedor_comercial === fact.get(v.factura_id).proveedor_comercial && v.proveedor_cif_comparable === fact.get(v.factura_id).proveedor_cif_comparable);
  const sinCif = vs.filter((v) => v.proveedor_cif_comparable === null).map((v) => v.numero_factura);
  return si(igual && isDeepStrictEqual(sinCif, ['FD-26/04471', 'FD-26/04471']) && CONSULTAS.vencimientos.sql.includes('f.proveedor_literal')
    && CONSULTAS.vencimientos.objetos.every((o) => OBJETOS_PERMITIDOS.includes(o)), JSON.stringify({ igual, sinCif }));
});
comprobar('H6/H6-REAL: semilla de pagos coherente (hoy 16/11/2026; marcas por (factura, orden) con fecha e importe copiados del vencimiento; una vigente por vencimiento y una forma por CIF)', () => {
  const porClave = new Map(vencimientos.vencimientos.map((v) => [`${v.factura_id}#${v.orden}`, v]));
  const cifs = new Set(vencimientos.vencimientos.map((v) => v.proveedor_cif_comparable).filter(Boolean));
  const vig = semillaPagos.marcas.filter((m) => !m.anulada);
  const fvig = semillaPagos.formas.filter((f) => !f.anulada);
  const copiaBien = (m) => { const v = porClave.get(`${m.factura_id}#${m.vencimiento_orden}`); return v && v.fecha_vencimiento.slice(0, 10) === m.fecha_vencimiento && v.importe === m.importe; };
  return si(semillaPagos.hoy === '2026-11-16' && semillaPagos.marcas.every(copiaBien) && semillaPagos.marcas.every((m) => !('vencimiento_id' in m) && m.farmacia === 'PIO')
    && semillaPagos.formas.every((f) => cifs.has(f.cif))
    && new Set(vig.map((m) => `${m.factura_id}#${m.vencimiento_orden}`)).size === vig.length && new Set(fvig.map((f) => f.cif)).size === fvig.length
    && semillaPagos.marcas.some((m) => m.anulada) && semillaPagos.marcas.every((m) => m.fecha_pago <= semillaPagos.hoy), 'semilla incoherente');
});
comprobar('H6/H6-3/H6-REAL: los fixtures cubren los estados (4 pendientes, 3 rojos, 4 domiciliados previstos, 1 abono pendiente de compensar, 1 pagado a mano; ninguno a revisar); PAGADO_BANCO solo reservado', () => {
  const n = Object.fromEntries(ESTADOS_IMPLEMENTADOS.map((e) => [e, pantallaH6.filas.filter((f) => f.estado_pago === e).length]));
  return si(isDeepStrictEqual(n, { PENDIENTE: 4, VENCIDO_SIN_PAGAR: 3, DOMICILIADO_PREVISTO: 4, ABONO_PENDIENTE_COMPENSAR: 1, A_REVISAR: 0, PAGADO_MANUAL: 1 })
    && pantallaH6.a_revisar === 0 && pantallaH6.marcas_huerfanas.length === 0
    && !pantallaH6.filas.some((f) => f.estado_pago === 'PAGADO_BANCO') && DICCIONARIO_ESTADOS.PAGADO_BANCO.implementado === false
    && DICCIONARIO_ESTADOS.DOMICILIADO_PREVISTO.color !== 'rojo', JSON.stringify(n));
});
comprobar('H6: sin CIF = forma sin determinar con aviso (V08 sin importe: no marcable; V13 con importe: marcable); sin configurar = domiciliación por defecto', () => {
  const f8 = pantallaH6.filas.find((f) => f.vencimiento_id.endsWith('08'));
  const f13 = pantallaH6.filas.find((f) => f.vencimiento_id.endsWith('13'));
  const cof = pantallaH6.proveedores.find((p) => p.cif === 'A00000001');
  return si(f8.forma_pago === 'SIN_DETERMINAR' && f8.sin_cif && f8.no_marcable === 'SIN_IMPORTE' && f13.sin_cif && f13.no_marcable === null && f13.importe === 96.8
    && f13.sentido === 'NO_DOCUMENTADO' && pantallaH6.sin_cif.vencimientos === 2 && cof.forma === 'DOMICILIACION' && cof.por_defecto,
    JSON.stringify({ f8: f8.forma_pago, cof }));
});
comprobar('H6-6: totales por mes por estado (noviembre: falta por pagar 731,66 con el abono domiciliado no vencido −45,30; domiciliado previsto 150; octubre: domiciliado 400, abono por compensar −20 aparte, cargo negativo fuera)', () => {
  const nov = totalesPorPeriodo(pantallaH6.filas, 'mes').find((t) => t.clave === '2026-11');
  const oct = totalesPorPeriodo(pantallaH6.filas, 'mes').find((t) => t.clave === '2026-10');
  return si(nov.por_pagar.neto === 731.66 && nov.por_pagar.abonos === -45.3 && nov.domiciliado.neto === 150 && nov.abonos.neto === null
    && nov.sin_importe === 2 && nov.sentido_no_documentado === 2 && nov.cargo_negativo === 0
    && oct.domiciliado.neto === 400 && oct.domiciliado.cargos === 400 && oct.abonos.neto === -20
    && oct.cargo_negativo === 1 && oct.por_pagar.neto === null, JSON.stringify({ nov, oct }));
});
comprobar('H6-3: abono vencido = «Abono pendiente de compensar» (azul); cargo negativo con aviso y fuera de totales; check:real cuenta ambos (solo números)', () => {
  const v = (n) => pantallaH6.filas.find((f) => f.vencimiento_id === `90000000-0000-4000-8000-0000000000${n}`);
  const sql = CONSULTAS_CHECK.diagnostico_vencimientos.sql;
  const cols = ['vencimientos_cargo_importe_negativo', 'vencimientos_abono', 'vencimientos_abono_vencidos', 'vencimientos_abono_no_vencidos', 'vencimientos_abono_sin_fecha'];
  return si(v('12').estado_pago === 'ABONO_PENDIENTE_COMPENSAR' && DICCIONARIO_ESTADOS.ABONO_PENDIENTE_COMPENSAR.color === 'azul'
    && v('09').estado_pago === 'PENDIENTE' && v('11').cargo_negativo && v('11').sentido === 'CARGO'
    && pantallaH6.filas.filter((f) => f.cargo_negativo).length === 1 && cols.every((c) => sql.includes(`as ${c}`)),
  JSON.stringify({ v12: v('12').estado_pago, v11: v('11').cargo_negativo }));
});
comprobar('H6-REAL: REAL sin credencial de pagos: solo lectura con «Falta configurar la credencial de pagos»; sin marcas, lo vencido con CIF figura como domiciliado previsto', () => {
  const p = construirPantalla(vencimientos, null, { hoy: semillaPagos.hoy, modo: 'REAL', mensajeEscritura: MENSAJE_FALTA_CREDENCIAL_PAGOS });
  const vencidos = p.filas.filter((f) => f.vencido);
  return si(!p.marcas_disponibles && p.mensaje_escritura === 'Falta configurar la credencial de pagos' && p.historial.length === 0
    && vencidos.length === 9 && vencidos.filter((f) => f.estado_pago === 'DOMICILIADO_PREVISTO').length === 8
    && vencidos.filter((f) => f.estado_pago === 'ABONO_PENDIENTE_COMPENSAR').length === 1 && p.filas.every((f) => f.marca === null), JSON.stringify(vencidos.map((f) => f.estado_pago)));
});
comprobar('H6: propuesta SQL (docs/propuesta_tablas_h6_pagos.sql) sin aplicar: autor por cf.autor sin columna, una vigente por clave, anular en vez de DELETE, RLS PIO, historial por trigger, rol propio, rollback', () => {
  const ruta = join(RAIZ, '..', 'docs', 'propuesta_tablas_h6_pagos.sql');
  if (!existsSync(ruta)) return 'falta la propuesta';
  const s = readFileSync(ruta, 'utf8');
  const tablas = (s.match(/create table public\.\w+ \([^;]*\);/g) ?? []).filter((t) => /vencimientos_marcas_pago|proveedores_forma_pago/.test(t.split('(')[0]));
  return si(/NO APLICAR/.test(s) && /cf\.autor/.test(s) && tablas.length === 2 && tablas.every((t) => !/\bautor\b/.test(t) && /anulada boolean/.test(t))
    && /vencimiento_id, fecha_pago|vencimiento_id uuid not null/.test(s) && /cif text not null/.test(s)
    && /\(farmacia, vencimiento_id\) where not anulada/.test(s) && /\(farmacia, cif\) where not anulada/.test(s)
    && /enable row level security/.test(s) && /farmacia = 'PIO'/.test(s) && /BORRADO_NO_PERMITIDO/.test(s) && /cf_h6_historial/.test(s)
    && /grant select, insert, update on public\.vencimientos_marcas_pago, public\.proveedores_forma_pago to cf_pagos_web/.test(s)
    && /grant select on [^;]*vencimientos_marcas_pago[^;]*to cf_lectura/.test(s) && !/^grant [^;]*\bdelete\b/im.test(s)
    && /ROLLBACK/.test(s) && /A CONFIRMAR/.test(s) && /DECISIONES PARA EL CIRCUITO/.test(s)
    && !/facturas_vencimientos[^;\n]*to cf_pagos_web/.test(s), 'faltan elementos');
});

// --- H6-4: Vencimientos en calendario -------------------------------------------------------------------------------
comprobar('H6-4: calendario: 04/11 con 2 pagos (304,74 €, rojo); noviembre 9 pagos y 881,66 € (2 pendientes y 2 no documentados fuera); octubre 380 € (cargo negativo fuera, violeta); sin cambiar los fixtures', () => {
  const dia = agregarCalendario(pantallaH6.filas, 'dia');
  const d4 = dia.get('2026-11-04');
  const anio = resumenAnio(pantallaH6.filas, '2026');
  const [oct, nov] = [anio[9], anio[10]];
  const colores = Object.fromEntries([...dia].map(([k, r]) => [k, r.color]));
  const esperado = {
    '2026-10-29': 'azul', '2026-10-30': 'domiciliado', '2026-10-31': 'domiciliado', '2026-11-04': 'rojo', '2026-11-07': 'verde',
    '2026-11-11': 'rojo', '2026-11-14': 'domiciliado', '2026-11-15': 'domiciliado', '2026-11-19': 'neutro', '2026-11-21': 'neutro', '2026-11-30': 'neutro',
    '2026-12-19': 'neutro', // H6-REAL: V13 (FEDEFARMA, sentido no documentado: no suma)
  };
  const dic = anio[11];
  return si(d4.pagos === 2 && d4.total.neto === 304.74 && d4.color === 'rojo'
    && nov.pagos === 9 && nov.total.neto === 881.66 && nov.sin_importe === 2 && nov.sentido_no_documentado === 2 && nov.color === 'rojo'
    && oct.pagos === 3 && oct.total.neto === 380 && oct.cargo_negativo === 1 && oct.color === 'domiciliado'
    && dic.pagos === 1 && dic.total.neto === null && dic.sentido_no_documentado === 1
    && anio.filter((m) => m.pagos > 0).length === 3 && nov.intensidad === 4 && isDeepStrictEqual(colores, esperado)
    && sinFechaCalendario(pantallaH6.filas) === 0 && pantallaH6.filas.length === 13,
  JSON.stringify({ d4: d4 && [d4.pagos, d4.total.neto, d4.color], nov: [nov.pagos, nov.total.neto], oct: [oct.pagos, oct.total.neto], colores }));
});
comprobar('H6-4: lista con las pestañas de Facturas (13 / 6 conciliadas / 6 pendientes / 3 en revisión / 4 no revisadas; H6-REAL: +V13) y búsqueda por importe', () => {
  const n = Object.fromEntries(PESTANAS_VENCIMIENTOS.map((t) => [t.clave, pantallaH6.filas.filter(t.cumple).length]));
  const porImporte = pantallaH6.filas.filter((f) => cumpleBusquedaLista(f, '152,37')).length;
  return si(isDeepStrictEqual(n, { todas: 13, conciliadas: 6, pendientes: 6, revision: 3, 'no-revisadas': 4 }) && porImporte === 2, JSON.stringify({ n, porImporte }));
});

// --- H6-REAL: marcas de pago en REAL (migración 35) ------------------------------------------------------------------
comprobar('H6-REAL: A_REVISAR (marca que ya no coincide o huérfana): naranja, nunca pagado, fuera de pagado en totales y cashflow', () => {
  const v2 = vencimientos.vencimientos.find((v) => v.vencimiento_id.endsWith('02'));
  const m = { ...semillaPagos.marcas[1], factura_id: v2.factura_id, vencimiento_orden: v2.orden, fecha_vencimiento: v2.fecha_vencimiento, importe: 400, anulada: false };
  const huerfana = { ...m, marca_id: '70000000-0000-4000-8000-000000000098', vencimiento_orden: 9, importe: 10 };
  const marcas = new Map([[`${m.factura_id}#${m.vencimiento_orden}`, m], [`${huerfana.factura_id}#9`, huerfana]]);
  const p = construirPantalla(vencimientos, { hoy: semillaPagos.hoy, formas: new Map(), marcas, historial: [] }, { modo: 'REAL' });
  const f2 = p.filas.find((f) => f.vencimiento_id.endsWith('02'));
  const t = totalesPorPeriodo(p.filas, 'mes').find((x) => x.clave === '2026-11');
  return si(f2.estado_pago === 'A_REVISAR' && DICCIONARIO_ESTADOS.A_REVISAR.color === 'naranja' && f2.marca.diferencias.join() === 'IMPORTE'
    && p.a_revisar === 2 && p.marcas_huerfanas.length === 1 && t.pagado.vencimientos === 0 && t.revisar.neto === 472.22
    && vencimientoCashflow(f2).fecha_pago === null, JSON.stringify({ e: f2.estado_pago, a: p.a_revisar, t: t.revisar }));
});
comprobar('H6-REAL: SQL de pagos: la web no envía fecha ni importe; ON CONFLICT con el predicado; único UPDATE anulada = true; nunca DELETE; autor por transacción', () => {
  const s = SQL_PAGOS;
  const updates = Object.values(s).filter((q) => /^update /.test(q));
  return si(!/\b(fecha_vencimiento|importe)\b/.test(s.insertarMarcas.split('returning')[0])
    && /on conflict \(farmacia, factura_id, vencimiento_orden\) where not anulada do nothing/.test(s.insertarMarcas)
    && /on conflict \(farmacia, cif\) where not anulada do nothing/.test(s.insertarForma)
    && updates.length === 2 && updates.every((q) => / set anulada = true where .* and not anulada returning /.test(q))
    && !Object.values(s).some((q) => /\bdelete\b/i.test(q)) && s.autor === "select set_config('cf.autor', $1, true)"
    && !/facturas/.test([s.insertarMarcas, s.anularMarca, s.marcaPorId, s.formaBloqueo, s.anularForma, s.insertarForma, s.prueba].join(' ')), 'SQL de pagos fuera de las reglas');
});

// --- Casos H7: Cashflow (datos ficticios con la forma del contrato del circuito) -------------------------------------
const cashflowSemilla = JSON.parse(readFileSync(RUTA_CASHFLOW, 'utf8'));
const cashflowDatos = { ...cashflowSemilla, vencimientos: pantallaH6.filas.map(vencimientoCashflow) };
const CATEGORIAS_OBLIGATORIAS = ['RE Cobro TPV', 'RE Cobro efectivo', 'RE Cobro SOE', 'RS Modelo 303', 'RS Modelo 111', 'RS Traspasos', 'RE Traspasos'];
comprobar('H7: cashflow.json al día (idéntico a regenerarlo con gen_cashflow.mjs) y sin cashflow_semanas de H3a', () =>
  si(readFileSync(RUTA_CASHFLOW, 'utf8') === serializarCashflow(generarCashflow()) && !Object.values(FICHEROS_DTO).includes('cashflow_semanas.json'),
    'desactualizado (npm run fixtures:cashflow)'));
comprobar('H7-REAL: forma final del contrato (migración 38): importaciones, cuentas PIO|RITA|SL, importes y saldos de la vigente con farmacia de su cuenta, importe ≠ 0, saldo único por cuenta y decena', () => {
  const claves = (o) => Object.keys(o).sort().join(',');
  const malos = [];
  const vigentes = cashflowSemilla.importaciones.filter((i) => i.vigente);
  for (const i of cashflowSemilla.importaciones) {
    if (claves(i) !== 'archivo_nombre,detalle_error,estado,filas,importacion_id,importado_at,origen,vigente' || !['NOCHE', 'MANUAL'].includes(i.origen)
      || !['OK', 'ERROR'].includes(i.estado) || (i.estado === 'OK' && i.detalle_error !== null) || (i.vigente && i.estado !== 'OK')) malos.push(`importación ${claves(i)}`);
  }
  if (vigentes.length !== 1) malos.push(`vigentes ${vigentes.length}`);
  const id = vigentes[0]?.importacion_id;
  for (const c of cashflowSemilla.cuentas) if (claves(c) !== 'codigo,farmacia' || !['PIO', 'RITA', 'SL'].includes(c.codigo) || c.farmacia !== (c.codigo === 'SL' ? null : c.codigo)) malos.push(`cuenta ${c.codigo}`);
  for (const f of cashflowSemilla.importes) {
    if (claves(f) !== 'categoria,concepto,cuenta,decena_fin,decena_inicio,farmacia,id,importacion_id,importe' || !esDecenaInicio(f.decena_inicio) || f.decena_fin !== finDecena(f.decena_inicio)
      || !/^R[ES] /.test(f.categoria) || f.importacion_id !== id || f.farmacia !== f.cuenta || !['PIO', 'RITA'].includes(f.cuenta) || f.importe === 0) malos.push(`importe ${JSON.stringify(f)}`);
  }
  const unicos = new Set(cashflowSemilla.saldos.map((s) => `${s.cuenta}|${s.decena_inicio}`));
  if (unicos.size !== cashflowSemilla.saldos.length) malos.push('saldos repetidos');
  for (const s of cashflowSemilla.saldos) {
    if (claves(s) !== 'cuenta,decena_inicio,farmacia,id,importacion_id,saldo_bancos,saldo_formulas,saldo_inicial' || !esDecenaInicio(s.decena_inicio)
      || s.importacion_id !== id || s.farmacia !== s.cuenta) malos.push(`saldo ${JSON.stringify(s)}`);
  }
  if (!isDeepStrictEqual(cashflowSemilla.otras_cuentas, [])) malos.push('otras_cuentas');
  const anios = new Set(cashflowSemilla.importes.map((f) => f.decena_inicio.slice(0, 4)));
  const cuentas = new Set(cashflowSemilla.importes.map((f) => f.cuenta));
  return si(malos.length === 0 && anios.has('2026') && anios.has('2027') && cuentas.has('PIO') && cuentas.has('RITA')
    && CATEGORIAS_OBLIGATORIAS.every((c) => cashflowSemilla.importes.some((f) => f.categoria === c))
    && cashflowSemilla.importes.some((f) => f.cuenta === 'RITA' && f.categoria === 'RE Cobro efectivo' && f.concepto === 'COBRO EFECTIU'), malos.slice(0, 3).join('; '));
});
comprobar('H7 (media): naranja RITA cubierta por PIO 11–20/12/2026 con devolución en la SOE (21–31/12); rojo del consolidado 11–20/01/2027; importación de hace 6 días (único gris: ninguno por traspasos)', () => {
  const r = calcularCashflow(cashflowDatos);
  const n = r.avisos.filter((a) => a.tipo === 'naranja');
  const rojo = r.avisos.filter((a) => a.tipo === 'rojo');
  const soe = r.vistas.RITA.lineas.find((l) => l.categoria === 'RE Cobro SOE' && l.celdas['2026-12-21']?.en_saldo);
  return si(n.length === 1 && n[0].cuenta === 'RITA' && n[0].cubre === 'PIO' && n[0].decena === '2026-12-11' && n[0].devolucion === '2026-12-21' && soe !== undefined
    && rojo.length === 1 && rojo[0].decena === '2027-01-11' && rojo[0].importe === 2598.36 && n[0].importe === 5008.33
    && isDeepStrictEqual(r.avisos.filter((a) => a.tipo === 'gris').map((a) => a.codigo), ['IMPORTACION_ANTIGUA']) && r.importacion.dias === 6,
  JSON.stringify(r.avisos.map((a) => [a.tipo, a.codigo, a.cuenta, a.decena, a.importe, a.devolucion])));
});
comprobar('H7-REAL-9: previsión por concepto: media de 12 meses en su línea; Excel frente a media (gana el mayor); concepto sin Excel junto a otro anotado: su media; sin línea de media de categoría', () => {
  const r = calcularCashflow(cashflowDatos);
  const L = (v, cat, con) => r.vistas[v].lineas.find((l) => l.categoria === cat && l.concepto === con);
  const tpv = L('PIO', 'RE Cobro TPV', 'TPV CaixaBank');
  const base12 = tpv.celdas['2026-11-11'].media.base.map((b) => b.clave);
  // Excel superior a la media: TPV de Navidad 12.500 frente a 9.000; RITA HEFAME 9.800 frente a 2.000 → el Excel.
  const nav = tpv.celdas['2026-12-21'];
  const hef = L('RITA', 'RS Proveedores', 'HEFAME').celdas['2026-12-01'];
  // Excel inferior a la media: ALLIANCE 11–20/11, 520 frente a 6.000 → la media (y los vencimientos, 472,22, menores).
  const all = L('PIO', 'RS Proveedores', 'ALLIANCE').celdas['2026-11-11'];
  // Concepto sin Excel en una decena con Excel de otro concepto de la categoría: su propia media (RITA COFARES 1–10/12).
  const cof = L('RITA', 'RS Proveedores', 'COFARES').celdas['2026-12-01'];
  const soe = L('RITA', 'RE Cobro SOE', 'CatSalut receptes');
  const ok = tpv.celdas['2026-11-11'].fuente === 'MEDIA' && tpv.celdas['2026-11-11'].importe === 10000 && base12.length === 12 && base12[0] === '2025-11-11' && base12[11] === '2026-10-11'
    && nav.fuente === 'EXCEL' && nav.importe === 12500 && isDeepStrictEqual(nav.frente, { excel: 12500, media: 9000 })
    && hef.fuente === 'EXCEL' && hef.importe === -9800 && isDeepStrictEqual(hef.frente, { excel: -9800, media: -2000 })
    && all.fuente === 'MEDIA' && all.importe === -6000 && isDeepStrictEqual(all.frente, { excel: -520, media: -6000 })
    && cof.fuente === 'MEDIA' && cof.importe === -3000
    && soe.celdas['2026-11-21'].importe === 20000 && soe.celdas['2026-11-11'] === undefined
    && ['PIO', 'RITA', 'CONSOLIDADO'].every((v) => r.vistas[v].lineas.every((l) => !l.media && l.concepto !== 'Media calculada'))
    && r.vistas.PIO.decenas['2026-11-11'].saldo === 22262.49 && !r.categorias_media.includes('RE Traspasos');
  return si(ok, JSON.stringify({ nav: nav.fuente, hef: hef.fuente, all: [all.fuente, all.importe], cof: [cof?.fuente, cof?.importe], s: r.vistas.PIO.decenas['2026-11-11'].saldo }));
});
comprobar('H7-REAL-9: sin doble cómputo: cada concepto y decena futura tiene una sola cifra; el saldo previsto = anterior + Σ de esas cifras', () => {
  const r = calcularCashflow(cashflowDatos);
  const malos = [];
  for (const v of ['PIO', 'RITA']) {
    const x = r.vistas[v];
    const claves = x.lineas.map((l) => l.clave);
    if (new Set(claves).size !== claves.length) malos.push(`${v} líneas repetidas`);
    let s = x.saldo_partida;
    for (const d of r.decenas.filter((dd) => dd > x.ultima_real)) {
      const suma = x.lineas.reduce((a, l) => a + Math.round((l.celdas[d]?.en_saldo ? l.celdas[d].importe ?? 0 : 0) * 100), 0);
      s = Math.round(s * 100 + suma) / 100;
      if (s !== x.decenas[d].saldo) { malos.push(`${v} ${d}`); break; }
    }
  }
  return si(malos.length === 0, malos.join(', '));
});
comprobar('H7-REAL-2: «RS Modelo …» con el mismo mes del año anterior (PIO 303 ene-2027 = ene-2026: 8.500; 111: 1.500); sin año anterior real, nada', () => {
  const r = calcularCashflow(cashflowDatos);
  const m = (v, cat) => r.vistas[v].lineas.find((l) => l.categoria === cat).celdas;
  const c = m('PIO', 'RS Modelo 303');
  return si(c['2027-01-11'].importe === -8500 && c['2027-01-11'].media.regla === 'ANIO_ANTERIOR' && c['2026-11-11'] === undefined && c['2027-12-11'] === undefined
    && m('PIO', 'RS Modelo 111')['2027-01-11'].importe === -1500 && m('RITA', 'RS Modelo 303')['2027-01-11'].importe === -3100, JSON.stringify(c['2027-01-11']?.media));
});
comprobar('H7-REAL-4: traspasos externos (conceptos fuera de TRASPASOS_INTERNOS) con media por concepto y en el consolidado; el Excel manda', () => {
  const r = calcularCashflow(cashflowDatos);
  const f = r.vistas.PIO.lineas.find((l) => l.concepto === 'TRASPASO A FONDOS/VALORS');
  const sl = r.vistas.RITA.lineas.find((l) => l.concepto === 'TRASPASO A LA SL (JUBILACIO ETC)');
  return si(f?.clase === 'TRASPASO_EXTERNO' && f.celdas['2026-12-01'].importe === -1000 && f.celdas['2027-02-01'].fuente === 'EXCEL' && f.celdas['2027-02-01'].importe === -2500
    && sl?.clase === 'TRASPASO_EXTERNO' && sl.celdas['2026-11-11'].importe === -500 && r.vistas.CONSOLIDADO.lineas.some((l) => l.concepto === 'TRASPASO A FONDOS/VALORS')
    && r.vistas.CONSOLIDADO.decenas['2026-12-01'].traspasos_externos === -1000, JSON.stringify({ f: f?.clase, sl: sl?.clase }));
});
comprobar('H7-REAL-2/4: traspasos internos sin media; los no compensados sin aviso y solo de las decenas visibles; RITA con su efectivo (COBRO EFECTIU)', () => {
  const r = calcularCashflow(cashflowDatos);
  const nc = traspasosNoCompensados(r.vistas.CONSOLIDADO, columnasVista(r.hoy, 'decenas'));
  const ef = r.vistas.RITA.lineas.find((l) => l.categoria === 'RE Cobro efectivo' && l.concepto === 'COBRO EFECTIU');
  return si(isDeepStrictEqual(nc, [{ decena: '2026-10-21', importe: -16000 }]) && r.avisos.every((a) => !/TRASPASO/.test(a.codigo))
    && ['PIO', 'RITA'].every((v) => r.vistas[v].lineas.every((l) => l.clase !== 'TRASPASO' || Object.values(l.celdas).every((c) => c.fuente !== 'MEDIA')))
    && ef !== undefined && ef.celdas['2026-11-01'].fuente === 'REAL' && ef.celdas['2026-11-11'].fuente === 'MEDIA' && ef.celdas['2026-11-11'].importe === 1200, JSON.stringify(nc));
});
comprobar('H7-REAL-9: ALLIANCE 11–20/11/2026: media (6.000) > Excel (520) → base = media; mayor que los vencimientos (F02, 472,22) → la media («posible duplicado o diferencia»); RITA sin vencimientos; SL fuera', () => {
  const r = calcularCashflow(cashflowDatos);
  const c = r.vistas.PIO.lineas.find((l) => l.concepto === 'ALLIANCE').celdas['2026-11-11'];
  const rita = r.vistas.RITA.lineas.every((l) => Object.values(l.celdas).every((x) => x.fuente !== 'VENCIMIENTOS' && x.vencimientos === null));
  return si(c.fuente === 'MEDIA' && c.importe === -6000 && c.vencimientos.neto === 472.22 && c.excel === -520 && c.diferencia && c.vencimientos.incluidos[0].factura_id === F(2)
    && isDeepStrictEqual(c.comparada, { fuente: 'VENCIMIENTOS', importe: -472.22 }) && c.media?.base.length === 12
    && rita && isDeepStrictEqual(r.fuera.cuentas_fuera, ['SL']) && r.fuera.filas_otras_cuentas === 0 && r.vistas.PIO.saldo_partida === 25000 && r.vistas.RITA.saldo_partida === 2000,
  JSON.stringify({ fuente: c.fuente, importe: c.importe, excel: c.excel, fuera: r.fuera.cuentas_fuera }));
});
comprobar('H7-REAL: cuadre de control (saldo_inicial + ΣRE − ΣRS = saldo_formulas) en todas las decenas de PIO y RITA; E7 solo en PIO 21–31/10/2026 (−35,20)', () => {
  const r = calcularCashflow(cashflowDatos);
  const malos = [];
  const dif = [];
  for (const v of ['PIO', 'RITA']) {
    for (const [d, x] of Object.entries(r.vistas[v].decenas)) {
      if (cashflowSemilla.saldos.some((s) => s.cuenta === v && s.decena_inicio === d) && x.cuadra !== true) malos.push(`${v} ${d}`);
      if (x.diferencia_banco !== null) dif.push([v, d, x.diferencia_banco]);
    }
  }
  return si(malos.length === 0 && isDeepStrictEqual(dif, [['PIO', '2026-10-21', -35.2]]) && !r.avisos.some((a) => a.codigo === 'IMPORTACION_NO_CUADRA'),
    JSON.stringify({ malos: malos.slice(0, 3), dif }));
});
comprobar('H7-2: signo de la celda: RS negativo (abono COFARES −250, PIO 11–20/07/2026) reduce las salidas; RE negativo (regularización −120, RITA 21–30/11/2026) reduce las entradas', () => {
  const r = calcularCashflow(cashflowDatos);
  const rs = cashflowSemilla.importes.filter((f) => f.categoria.startsWith('RS ') && f.importe < 0);
  const re = cashflowSemilla.importes.filter((f) => f.categoria.startsWith('RE ') && f.importe < 0);
  const cof = r.vistas.PIO.lineas.find((l) => l.categoria === 'RS Proveedores' && l.concepto === 'COFARES').celdas['2026-07-11'];
  const reg = r.vistas.RITA.lineas.find((l) => l.concepto === 'Regularización mutua').celdas['2026-11-21'];
  return si(rs.length === 1 && re.length === 1 && cof.importe === -4250 && reg.importe === -120, JSON.stringify({ rs, re, cof: cof.importe, reg: reg.importe }));
});
comprobar('H7: traspasos neutros en el consolidado; «no relacionadas» fuera del cash flow generado farmacia', () => {
  const r = calcularCashflow(cashflowDatos);
  const sep = r.vistas.CONSOLIDADO.decenas['2026-09-11'];
  const dic = r.vistas.PIO.decenas['2026-12-01'];
  return si(sep.traspasos === 0 && r.vistas.CONSOLIDADO.lineas.every((l) => l.clase !== 'TRASPASO') && dic.no_relacionadas === -550
    && Math.round((dic.farmacia + dic.no_relacionadas + dic.traspasos_externos) * 100) === Math.round(dic.neto * 100), JSON.stringify({ sep, dic }));
});
comprobar('H7-REAL-7: equivalencias de concepto: JNTL CONSUMER (ORALDI…) + JHONSON & JHONSON (PIO 11–20/03/2026) = una línea KENVUE con la suma (−500); saldos por decena idénticos sin la equivalencia', () => {
  const r = calcularCashflow(cashflowDatos);
  const k = r.vistas.PIO.lineas.filter((l) => l.categoria === 'RS Proveedores' && l.concepto === 'KENVUE');
  const alias = r.vistas.PIO.lineas.filter((l) => /JNTL|JHONSON/.test(l.concepto));
  // Sin la equivalencia: los mismos importes con un concepto que no casa con ningún alias.
  const sin = calcularCashflow({ ...cashflowDatos, importes: cashflowDatos.importes.map((f) => (/^(JNTL|JHONSON)/.test(f.concepto ?? '') ? { ...f, concepto: `ZZ ${f.concepto}` } : f)) });
  const distintos = ['PIO', 'RITA', 'CONSOLIDADO'].flatMap((v) => r.decenas.filter((d) => r.vistas[v].decenas[d].saldo !== sin.vistas[v].decenas[d].saldo).map((d) => `${v} ${d}`));
  const c = k[0]?.celdas['2026-03-11'];
  return si(FILAS_EQUIVALENTES.length === 2 && k.length === 1 && alias.length === 0 && c?.importe === -500 && c.excel_filas === 2 && c.fuente === 'REAL'
    && isDeepStrictEqual(k[0].incluye, ['JHONSON & JHONSON', 'JNTL CONSUMER (ORALDINE) S.L.'])
    && r.vistas.CONSOLIDADO.lineas.find((l) => l.concepto === 'KENVUE')?.incluye.length === 2
    && sin.vistas.PIO.lineas.filter((l) => /^ZZ /.test(l.concepto)).length === 2 && distintos.length === 0,
  JSON.stringify({ k: k.length, alias: alias.map((l) => l.concepto), c: c?.importe, distintos: distintos.slice(0, 3) }));
});
comprobar('H7-REAL-8: media de 12 meses: la reparación de PIO de 21–31/03/2026 (6.000) entra en la media de la 3.ª decena (−500), no en la de 3 meses', () => {
  const r = calcularCashflow(cashflowDatos);
  const r3 = calcularCashflow({ ...cashflowDatos, config: { ...CONFIG_CASHFLOW, meses_media: 3 } });
  const m = (x) => x.vistas.PIO.lineas.find((l) => l.categoria === PAGO_HACE_8_MESES.categoria && l.concepto === PAGO_HACE_8_MESES.concepto)?.celdas['2026-11-21'];
  const c = m(r);
  return si(CONFIG_CASHFLOW.meses_media === 12 && c?.importe === -500 && c.media.base.length === 12 && c.media.base.some((b) => b.clave === PAGO_HACE_8_MESES.decena_inicio)
    && m(r3) === undefined, JSON.stringify({ c12: c?.importe, c3: m(r3)?.importe }));
});
comprobar('H7-REAL-8: fusiones por prefijo: PIO «DERMOPHARMACIE I PERF…» → «DERMOFARMACIA PERFUMERIA SL» (texto del Excel, 120 + 80); RITA ambiguo (dos nombres), sin fusionar; saldos idénticos sin fusiones', () => {
  const r = calcularCashflow(cashflowDatos);
  const nombres = (v) => r.vistas[v].lineas.filter((l) => l.categoria === 'RS Proveedores' && /^DERMO/.test(l.concepto)).map((l) => l.concepto).sort();
  const pio = r.vistas.PIO.lineas.find((l) => l.concepto === 'DERMOFARMACIA PERFUMERIA SL');
  // Sin fusiones: los alias de CONCEPTOS_EQUIVALENTES con otro nombre (mismos importes); el resto, igual.
  const alias = new Set(['PIO', 'RITA'].flatMap((c) => [...resolverEquivalencias(cashflowDatos.importes.filter((f) => f.cuenta === c && f.concepto !== null).map((f) => f.concepto)).mapa.keys()]));
  const sinFusiones = calcularCashflow({ ...cashflowDatos, importes: cashflowDatos.importes.map((f) => (alias.has(f.concepto) ? { ...f, concepto: `ZZ ${f.concepto}` } : f)) });
  const distintos = ['PIO', 'RITA', 'CONSOLIDADO'].flatMap((v) => r.decenas.filter((d) => r.vistas[v].decenas[d].saldo !== sinFusiones.vistas[v].decenas[d].saldo).map((d) => `${v} ${d}`));
  return si(isDeepStrictEqual(nombres('PIO'), ['DERMOFARMACIA PERFUMERIA SL']) && pio.celdas['2026-03-11'].importe === -200 && isDeepStrictEqual(pio.incluye, ['DERMOPHARMACIE I PERFUMERIA'])
    && isDeepStrictEqual(nombres('RITA'), ['DERMOFARMACIA PERFUMERIA SL', 'DERMOFARMACIA PERFUMES BCN', 'DERMOPHARMACIE I PERFUMERIA'])
    && isDeepStrictEqual(r.equivalencias, { filas: { PIO: 3, RITA: 0 }, ambiguas: 1, sin_coincidencia: 1 })
    && sinFusiones.equivalencias.filas.PIO === 0 && distintos.length === 0,
  JSON.stringify({ pio: nombres('PIO'), rita: nombres('RITA'), eq: r.equivalencias, distintos: distintos.slice(0, 3) }));
});
comprobar('H7-REAL-7: avisos de saldo solo dentro del horizonte (12 meses previstos, como el indicador): la obra de 11–20/12/2027 deja el consolidado en negativo sin aviso', () => {
  const r = calcularCashflow(cashflowDatos);
  const C = r.vistas.CONSOLIDADO;
  const fin = '2027-11-01';
  const negativoFuera = r.decenas.filter((d) => d > fin && C.decenas[d].saldo !== null && C.decenas[d].saldo < 0);
  return si(negativoFuera.includes(FUERA_HORIZONTE.decena_inicio) && r.avisos.every((a) => a.decenas.every((x) => x.decena <= fin))
    && r.avisos.filter((a) => a.tipo !== 'gris').length === 2, JSON.stringify({ negativoFuera, avisos: r.avisos.map((a) => [a.tipo, a.decena, a.hasta]) }));
});

// --- Informe ----------------------------------------------------------------------
for (const [estado, nombre, detalle] of resultados) console.log(`${estado.padEnd(4)} ${nombre}${detalle ? ' — ' + detalle : ''}`);
const fallos = resultados.filter((r) => r[0] !== 'OK').length;
console.log(`\n${resultados.length - fallos}/${resultados.length} OK`);
process.exit(fallos ? 1 : 0);
