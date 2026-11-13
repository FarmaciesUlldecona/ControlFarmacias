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
} from '../../app/server/contrato.ts';
import { FICHEROS_DTO } from '../../app/server/adaptador_fixtures.ts';
import { ETIQUETAS_CLASE_NUMERO, ETIQUETAS_ESTADO_MATCHING, PDF_ORIGINAL, resumenCasado, vencimientoProximo } from '../../app/server/contrato.ts';
import {
  DICCIONARIO_CASADO, RELACION_CASADO, agruparLineas, avisosFactura, baseAlbaran, canonicalizarProveedor, claveCasado, claveRelacion,
  ESTADOS_MATCHING, ESTADOS_VERSION_ANTERIOR, ESTADO_LINEA, TEXTO_HEFAME_BASES, claveEstadoLinea, estadoSinDescripcion, coincideImporte, esEco360, insigniasFactura, origenAplicado, rangoImporteBuscado, textoEstadoMatching, textoEvento,
} from '../../app/server/detalle.ts';
import { COLUMNAS_SENTIDO, validarDiagnostico } from '../../app/server/adaptador_real.ts';
import { CONVENIO_ANUAL, HORARIO_COMPLETA, objetivosAnuales, validarTrabajadora } from '../../app/server/rrhh/contrato.ts';
import { crearAdaptadorRrhhFixtures, leerSemilla, leerSemillaEventos } from '../../app/server/rrhh/adaptador_fixtures.ts';
import {
  AVISO_NOTA_VACIA, COLOR_TIPO_EVENTO, FRANJAS_DE_JORNADA, LARGO_NOTA, TIPOS_EVENTO, describirCambio, esLaborable, horasFranja, leerNota, validarPeticionEventos,
} from '../../app/server/rrhh/eventos.ts';
import { COMERCIAL_POR_CIF, COMERCIAL_POR_LITERAL, nombreComercial, razonSocialSecundaria } from '../../app/server/proveedor_comercial.ts';
import { ALERTA_DUPLICADO, F05_SIN_TIPO_DOCUMENTAL, INCIDENCIAS_H4B, INCIDENCIAS_H4D, TIPO_DOCUMENTAL_H4C, generar } from './gen_fixtures.mjs';

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
const { inicio, facturas, facturaDetalle, conciliacionBandeja, vencimientos, cashflowSemanas, proveedores, configuracion } = dto;

// --- Contrato ------------------------------------------------------------------
comprobar('los 8 bloques del contrato tienen fichero', () => si(Object.keys(FICHEROS_DTO).length === 8 && Object.keys(CONSULTAS_POR_BLOQUE).length === 8, 'faltan bloques'));
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
comprobar('farmacia: solo PIO (ningún RITA)', () => {
  const malos = [];
  recorrer(dto, (k, v, ruta) => {
    if ((k === 'farmacia' || k === 'farmacia_activa') && v !== 'PIO') malos.push(ruta);
    if (typeof v === 'string' && /\bRITA\b/.test(v)) malos.push(ruta);
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
comprobar('F04: 3 vencimientos, el 3.º sin importe (null) y importe_conocido=false', () => {
  const v = vencimientos.vencimientos.filter((x) => x.factura_id === F(4)).sort((a, b) => a.orden - b.orden);
  return si(v.length === 3 && v[0].importe === 400 && v[1].importe === 150 && v[2].importe === null && v[2].importe_conocido === false, JSON.stringify(v.map((x) => x.importe)));
});
comprobar('vencimientos: totales con nulls contados aparte', () => {
  const t = vencimientos.totales;
  return si(t.sin_importe === vencimientos.vencimientos.filter((x) => x.importe === null).length && t.sin_importe >= 2, JSON.stringify(t));
});
comprobar('cashflow: igual a v_web_cashflow_semanal de H3a salvo los vencimientos de sentido no documentado (H4c-2)', () => {
  // H3a sumaba como cargo todo lo que no era ABONO. Los NO_DOCUMENTADO (F03 rectificativa, F05 sin tipo, F06 OTRO)
  // salen de los cargos y se cuentan aparte; el resto de la semana no cambia.
  const noDoc = new Set(Object.keys(TIPO_DOCUMENTAL_H4C).filter((id) => sentidoDocumental(TIPO_DOCUMENTAL_H4C[id]) === 'NO_DOCUMENTADO'));
  const venc = h3a('vencimientos');
  const lunes = (f) => { const d = new Date(f + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7)); return d.toISOString().slice(0, 10); };
  const esperado = h3a('cashflow_semanal').map(({ farmacia, ...r }) => { // eslint-disable-line no-unused-vars
    const nd = venc.filter((v) => noDoc.has(v.factura_id) && v.fecha_vencimiento && lunes(v.fecha_vencimiento) === r.semana);
    const restar = nd.reduce((a, v) => a + (v.importe ?? 0), 0);
    const quedan = venc.filter((v) => v.fecha_vencimiento && lunes(v.fecha_vencimiento) === r.semana && v.tipo_documento !== 'ABONO' && !noDoc.has(v.factura_id) && v.importe !== null);
    return {
      ...r,
      importe_cargos_conocido: quedan.length === 0 ? null : Math.round((r.importe_cargos_conocido - restar) * 10000) / 10000,
      vencimientos_sentido_no_documentado: nd.length,
    };
  }).sort((a, b) => String(a.semana).localeCompare(String(b.semana)));
  const obtenido = cashflowSemanas.semanas.map(({ semana_fin, ...r }) => r); // eslint-disable-line no-unused-vars
  const orden = (o) => Object.fromEntries(Object.entries(o).sort(([a], [b]) => a.localeCompare(b)));
  return si(isDeepStrictEqual(obtenido.map(orden), esperado.map(orden)), `obtenido ${JSON.stringify(obtenido)}`);
});
comprobar('cashflow: semana 2026-11-30 con cargos null (no 0)', () => {
  const s = cashflowSemanas.semanas.find((x) => x.semana === '2026-11-30');
  return si(s && s.importe_cargos_conocido === null && s.vencimientos_sin_importe === 1, JSON.stringify(s));
});
comprobar('abono F07: total y vencimiento con signo impreso (−45,30)', () => {
  const f = facturas.facturas.find((x) => x.factura_id === F(7));
  const v = vencimientos.vencimientos.find((x) => x.factura_id === F(7));
  return si(f.tipo_documento === 'ABONO' && f.importe_total === -45.3 && v.importe === -45.3 && cashflowSemanas.semanas.some((s) => s.importe_abonos_conocido === -45.3), 'abono mal');
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
  const s = cashflowSemanas.semanas.find((x) => x.semana === '2026-11-02');
  return si(v.length === 1 && v[0].tipo_documento === 'FACTURA' && v[0].tipo_documento_documental === null && v[0].sentido === 'NO_DOCUMENTADO'
    && t.sentido_no_documentado === 3 && t.importe_cargos_conocido === Math.round(cargos * 10000) / 10000 && t.importe_abonos_conocido === abonos
    && s.vencimientos_sentido_no_documentado === 1 && facturaDetalle[F05_SIN_TIPO_DOCUMENTAL].vencimientos[0]?.sentido === 'NO_DOCUMENTADO',
  JSON.stringify([t, s]));
});
comprobar('H4c: abono F07 sigue sumando como abono (tipo documental ABONO)', () => {
  const v = vencimientos.vencimientos.find((x) => x.factura_id === F(7));
  return si(v.sentido === 'ABONO' && vencimientos.totales.importe_abonos_conocido === -45.3, JSON.stringify(v));
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
    && g.length === 15 && casosAtencion.length === 26, JSON.stringify([inicio.atencion.tipos, inicio.atencion.casos]));
});
comprobar('H4d: orden fijo de grupos (1 diferencia … 8 correcciones) y casos del más reciente al más antiguo', () => {
  const g = inicio.atencion.grupos;
  const orden = g.map((x) => x.orden);
  const ordenado = orden.every((o, i) => i === 0 || orden[i - 1] <= o);
  const primeros = g.slice(0, 5).map((x) => x.clave);
  const casosOrdenados = g.every((x) => x.casos.every((c, i) => i === 0 || (x.casos[i - 1].fecha ?? '') >= (c.fecha ?? '')));
  // Dentro de 6 y 7 (un grupo por código): el grupo con el caso más reciente primero.
  const de7 = g.filter((x) => x.orden === 7).map((x) => x.clave.split(':')[1]);
  return si(ordenado && casosOrdenados && isDeepStrictEqual(primeros, ['DIFERENCIA_ALBARANES', 'DOCUMENTOS_DEFECTO', 'DUPLICADO_FARMATIC', 'VENCIMIENTO_SIN_SENTIDO', 'ALBARAN_NO_EN_FARMATIC'])
    && isDeepStrictEqual(de7, ['SENTIDO_NO_DOCUMENTADO', 'IMPORTE_VENCIMIENTO_NO_DOCUMENTADO', 'SENTIDO_NO_ETIQUETADO_DOCUMENTALMENTE',
      'CANDIDATO_ALBARAN_NO_PROMOVIDO', 'POSIBLE_DUPLICADO', 'CODIGO_FICTICIO_SIN_TRADUCCION'])
    && g.find((x) => x.orden === 8).clave === 'CORRECCION_APROBADA', JSON.stringify(g.map((x) => [x.orden, x.clave])));
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
    && g4.casos.length === esperados.length && esperados.length === 3 && isDeepStrictEqual(ids(g4.casos), ids(esperados))
    && isDeepStrictEqual(ids(g4.casos), [F(3), F(5), F(6)])
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
comprobar('H4d-3: diagnóstico check:real "sentido" (recuentos por origen; fixtures: 3 / 3 / 1)', () => {
  const sql = CONSULTAS_CHECK.diagnostico_sentido.sql;
  const cols = ['vencimiento_regla', 'incidencia_sentido_no_documentado', 'incidencia_sentido_no_etiquetado'];
  const faltan = cols.filter((c) => !sql.includes(`as ${c}`));
  // Mismo cálculo sobre las fixtures (lo que verá Pío en check:real si los datos fueran estos).
  const regla = vencimientos.vencimientos.filter((v) => v.sentido === 'NO_DOCUMENTADO').length;
  const inc = (c) => abiertasInicio.filter((i) => i.codigo === c).length;
  const g = (c) => grupo(`INCIDENCIA_AVISO:${c}`)?.casos.length ?? 0;
  return si(faltan.length === 0 && isDeepStrictEqual(COLUMNAS_SENTIDO, cols) && sql.includes("{tipo_documento,valor}") && !/\bf\.tipo_documento\b/.test(sql)
    && regla === 3 && grupo('VENCIMIENTO_SIN_SENTIDO').casos.length === regla
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
  const malos = Object.entries(DICCIONARIO_CASADO).filter(([k]) => k !== 'ESTADO:SIN_DESCRIPCION').filter(([, e]) => !e.texto || /^[A-Z_:]+$/.test(e.texto) || !/^[A-Z0-9]+:|\.sql:|^[0-9a-f]{7}:[a-z0-9_/]+\.py:\d/.test(e.fuente)); // H5-5: commit:fichero:línea
  return si(malos.length === 0 && Object.keys(DICCIONARIO_CASADO).length >= 20, malos.map(([k]) => k).join(', '));
});
comprobar('H5-2: las fixtures cubren las formas de casado (principal) y los tipos de relación (secundario)', () => {
  const claves = new Set(lineasTodas.map(claveCasado));
  const faltan = ['NUMERO:EXACTA', 'NUMERO:LETRA_FINAL', 'NUMERO:FINAL_DOCUMENTAL', 'NUMERO:INTERNO', 'HEFAME:EXACTO_ECONOMICO',
    'MOVIMIENTO', 'MOVIMIENTO:SIN_SENTIDO', 'SIN:SIN_COINCIDENCIA', 'SIN:AMBIGUO'].filter((k) => !claves.has(k));
  const rel = new Set(lineasTodas.map(claveRelacion));
  const faltanRel = ['UNO_A_UNO', 'UNO_A_VARIOS', 'MOVIMIENTO_NO_FARMATIC', 'SIN_COINCIDENCIA'].filter((k) => !rel.has(k));
  // R17: principal = forma del número de cada albarán (su número / numeración interna), secundario = misma recepción.
  const r17 = lineasTodas.filter((l) => l.tipo_relacion === 'UNO_A_VARIOS').map(claveCasado).join();
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
    && a7?.texto === '2 albaranes con diferencia' && a2 === undefined
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
  return si(malos.length === 0 && isDeepStrictEqual(f4.vencimientos_importes, [400, 150, null]), malos.join(', ') || JSON.stringify(f4.vencimientos_importes));
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
      && (ESTADOS_VERSION_ANTERIOR.includes(k) ? /^e18acf0:pruebas\/auditoria_2[tv]\/[a-z0-9_]+\.py:\d/.test(e.fuente) : /^C:\d/.test(e.fuente)))
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
comprobar('H5: listado: hoy, vencimiento próximo y "+N", importe pendiente, posible duplicado', () => {
  const f = (n) => facturas.facturas.find((x) => x.factura_id === F(n));
  const ok = facturas.hoy === '2026-11-02'
    && f(4).vencimiento_proximo.fecha_vencimiento === '2026-11-15' && f(4).vencimientos_total === 3 && !f(4).vencimiento_vencido
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
  const fuentes = [...Object.values(COMERCIAL_POR_CIF), ...Object.values(COMERCIAL_POR_LITERAL)]
    .every((e) => /^src\/facturas\/[\w/]+\.py:\d+$/.test(e.fuente) && /^[A-Z][A-Z ]*$/.test(e.nombre));
  const casos = [
    [nombreComercial('F30004444', null), 'HEFAME'], [nombreComercial('f-30.004.444', 'Otro literal'), 'HEFAME'],
    [nombreComercial(null, 'HDAD.FMCTCA.MEDIT.,S.C.L.'), 'HEFAME'], [nombreComercial('A50004324', null), 'ALLIANCE'],
    [nombreComercial(null, 'Alliance Healthcare España, S.A.'), 'ALLIANCE'], [nombreComercial('F-08-173395', null), 'FEDEFARMA'],
    [nombreComercial('ESA61674347', null), 'LOGISTA PHARMA'], [nombreComercial(null, 'GRUPO COFARES'), 'COFARES'],
    [nombreComercial(null, 'COFARES'), null], // sin equivalencia en src: literal del PDF
    [nombreComercial(null, 'FEDEFARMA'), null], [nombreComercial('B00000003', 'LABORATORIO X'), null],
    [nombreComercial('F30004444', 'ALLIANCE HEALTHCARE'), null], // CIF y literal en conflicto: falla cerrado
    [nombreComercial(null, null), null],
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
comprobar('TA1: fichas de ejemplo: PIO 3 completas + 1 media mañana (técnicas); RITA 5 completas + 1 media mañana + 1 media tarde (1 farmacéutica); titular en ambas', () => {
  const s = leerSemilla();
  const de = (f) => s.filter((t) => t.farmacia === f && !t.es_titular);
  const pio = de('PIO');
  const rita = de('RITA');
  const tit = s.filter((t) => t.es_titular);
  const cuenta = (ts, j) => ts.filter((t) => t.jornada === j).length;
  const ok = pio.length === 4 && cuenta(pio, 'COMPLETA') === 3 && cuenta(pio, 'MEDIA_MANANA') === 1 && pio.every((t) => t.categoria === 'TECNICO')
    && rita.length === 7 && cuenta(rita, 'COMPLETA') === 5 && cuenta(rita, 'MEDIA_MANANA') === 1 && cuenta(rita, 'MEDIA_TARDE') === 1
    && cuenta(pio, 'MEDIA_TARDE') === 0
    && rita.filter((t) => t.categoria === 'FARMACEUTICO').length === 1 && rita.filter((t) => t.categoria === 'TECNICO').length === 6
    && tit.length === 2 && new Set(tit.map((t) => t.farmacia)).size === 2 && new Set(tit.map((t) => t.nombre)).size === 1
    // TA1-2: jornada en horas diarias (lunes a viernes): completa 8 h; media mañana 4,5 h (también el titular).
    && [...pio, ...rita].filter((t) => t.jornada === 'COMPLETA').every((t) => t.horas_diarias === 8)
    && [...pio, ...rita, ...tit].filter((t) => t.jornada === 'MEDIA_MANANA').every((t) => t.horas_diarias === 4.5)
    // TA1-3: media tarde 3,5 h (17:00–20:30).
    && s.filter((t) => t.jornada === 'MEDIA_TARDE').every((t) => t.horas_diarias === 3.5)
    && s.every((t) => !('porcentaje_jornada' in t));
  return si(ok, JSON.stringify({ pio: pio.length, rita: rita.length, tit: tit.length }));
});
comprobar('TA1: solo nombre (sin DNI ni más datos personales); cada ficha pasa la validación de alta; ids únicos', () => {
  const s = leerSemilla();
  const permitidos = ['id', 'farmacia', 'nombre', 'categoria', 'jornada', 'horas_diarias', 'es_titular'];
  const extra = s.flatMap((t) => Object.keys(t).filter((k) => !permitidos.includes(k)));
  const invalidas = s.filter(({ id, ...t }) => !validarTrabajadora(t, 'alta').ok); // eslint-disable-line no-unused-vars
  const sinDni = !JSON.stringify(s).match(/\b\d{8}[A-Z]\b|dni|nif/i);
  return si(extra.length === 0 && invalidas.length === 0 && sinDni && new Set(s.map((t) => t.id)).size === s.length,
    JSON.stringify({ extra, invalidas: invalidas.map((t) => t.nombre) }));
});
comprobar('TA1-2: convenio por año (referencia 40 h/sem provisional) y objetivo = jornada máxima × horas semanales / referencia', () => {
  const conv = CONVENIO_ANUAL.map((c) => [c.anio, c.jornada_maxima_horas, c.horas_semanales_referencia, c.asuntos_propios_dias, c.permiso_medico_horas, c.estado].join());
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
    || (a.franja !== undefined && !FRANJAS_DE_JORNADA[fichas.get(a.trabajadora_id).jornada].includes(a.franja))
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
  const evs = a.eventos();
  const aus = evs.filter((e) => e.tipo !== 'JORNADA');
  const tipos = new Set(evs.map((e) => e.tipo));
  const ok = evs.length === 420 && aus.length === 41 && new Set(aus.map((e) => `${e.trabajadora_id}|${e.fecha}`)).size === 23
    && TIPOS_EVENTO.every((t) => tipos.has(t)) && aus.some((e) => e.farmacia === 'PIO') && aus.some((e) => e.farmacia === 'RITA')
    && evs.filter((e) => e.estado === 'CONFIRMADO').length === 105 && evs.every((e) => esLaborable(e.fecha))
    && new Set(evs.map((e) => `${e.trabajadora_id}|${e.fecha}|${e.franja}`)).size === evs.length; // uno por persona, día y franja
  return si(ok, JSON.stringify({ n: evs.length, aus: aus.length }));
});
comprobar('TA2-3: franjas y horas de la ficha (completa mañana 4,5 h + tarde 3,5 h = 8 h; medias, todas sus horas en su franja); farmacia de la ficha; sin historial de la carga', () => {
  const a = crearAdaptadorRrhhFixtures({ anioReferencia: 2026 });
  const fichas = new Map(a.trabajadoras('AMBAS', false).trabajadoras.map((t) => [t.id, t]));
  const malos = a.eventos().filter((e) => {
    const t = fichas.get(e.trabajadora_id);
    return !t || e.horas !== horasFranja(t, e.franja) || !FRANJAS_DE_JORNADA[t.jornada].includes(e.franja) || e.farmacia !== t.farmacia;
  });
  // Cada persona suma al día sus horas diarias (completa: 4,5 + 3,5 = 8).
  const porDia = new Map();
  for (const e of a.eventos()) porDia.set(`${e.trabajadora_id}|${e.fecha}`, (porDia.get(`${e.trabajadora_id}|${e.fecha}`) ?? 0) + e.horas);
  const sumaMal = [...porDia].filter(([k, h]) => fichas.get(k.split('|')[0]).horas_diarias !== h);
  const aina = (fr) => a.eventos().find((e) => e.trabajadora_id === 'e0000000-0000-4000-8000-000000000001' && e.franja === fr).horas;
  const irene = a.eventos().find((e) => e.trabajadora_id === 'e0000000-0000-4000-8000-000000000017');
  const conf = isDeepStrictEqual(HORARIO_COMPLETA, { MANANA: { horas: 4.5, desde: '9:00', hasta: '13:30' }, TARDE: { horas: 3.5, desde: '17:00', hasta: '20:30' } });
  return si(malos.length === 0 && sumaMal.length === 0 && conf && aina('MANANA') === 4.5 && aina('TARDE') === 3.5 && irene.franja === 'TARDE' && irene.horas === 3.5
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

// --- Informe ----------------------------------------------------------------------
for (const [estado, nombre, detalle] of resultados) console.log(`${estado.padEnd(4)} ${nombre}${detalle ? ' — ' + detalle : ''}`);
const fallos = resultados.filter((r) => r[0] !== 'OK').length;
console.log(`\n${resultados.length - fallos}/${resultados.length} OK`);
process.exit(fallos ? 1 : 0);
