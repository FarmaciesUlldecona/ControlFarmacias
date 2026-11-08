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
  TEXTO_INCIDENCIA, etiquetaYAlias, grupoProveedor, nombreCanonico, normalizarCif, resumenDuplicados, resumenPar08C66676,
  textoIncidencia,
} from '../../app/server/contrato.ts';
import { FICHEROS_DTO } from '../../app/server/adaptador_fixtures.ts';
import { validarDiagnostico } from '../../app/server/adaptador_real.ts';
import { ALERTA_DUPLICADO, INCIDENCIAS_H4B, generar } from './gen_fixtures.mjs';

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
comprobar('cashflow: igual a v_web_cashflow_semanal de H3a', () => {
  const esperado = h3a('cashflow_semanal').map(({ farmacia, ...r }) => r).sort((a, b) => String(a.semana).localeCompare(String(b.semana))); // eslint-disable-line no-unused-vars
  const obtenido = cashflowSemanas.semanas.map(({ semana_fin, ...r }) => r); // eslint-disable-line no-unused-vars
  return si(isDeepStrictEqual(obtenido, esperado), `obtenido ${JSON.stringify(obtenido)}`);
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
comprobar('inicio (1A): atención — con defecto en rojo, sin automatizar en gris', () => {
  const def = inicio.atencion.filter((a) => a.tipo === 'Con defecto');
  const sa = inicio.atencion.filter((a) => a.tipo === 'Sin automatizar');
  return si(def.length === 2 && def.every((a) => a.color === 'rojo') && sa.length === 4 && sa.every((a) => a.color === 'gris') && !inicio.atencion.some((a) => a.tipo === 'Sin leer'),
    JSON.stringify(inicio.atencion.map((a) => [a.tipo, a.color])));
});
comprobar('inicio: incidencias abiertas = todas las ABIERTA (documento + factura)', () => {
  const ab = h3a('incidencias').filter((i) => i.estado === 'ABIERTA');
  return si(inicio.incidencias.abiertas === ab.length && inicio.incidencias.bloqueantes === ab.filter((i) => i.bloqueante).length, JSON.stringify(inicio.incidencias));
});
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
  const ab = h3a('incidencias').filter((i) => i.estado === 'ABIERTA');
  const items = inicio.atencion.filter((a) => a.tipo.startsWith('Incidencia') || a.tipo === 'Posible duplicado');
  const sinTexto = items.filter((a) => !a.texto);
  const facturaMal = ab.filter((i) => i.factura_id && !items.some((a) => a.factura_id === i.factura_id));
  return si(items.length === ab.length && sinTexto.length === 0 && facturaMal.length === 0, `${items.length} items / ${ab.length} abiertas`);
});
comprobar('H3b: varios PROVEEDOR_NO_SOPORTADO (≥3) sin factura', () => {
  const pns = facturas.documentos_sin_factura.filter((d) => d.estado_lectura === 'PROVEEDOR_NO_SOPORTADO');
  return si(pns.length >= 3, `${pns.length}`);
});
comprobar('H3b: mapa proveedor×estado cuadra con documentos e incluye "Sin identificar"', () => {
  const m = proveedores.mapa_documentos;
  const total = m.filas.reduce((a, f) => a + f.total, 0);
  const sumaCeldas = m.filas.every((f) => Object.values(f.por_estado).reduce((a, n) => a + n, 0) === f.total);
  return si(total === inicio.documentos.total && sumaCeldas && m.filas.some((f) => f.clave === 'sin_identificar') && m.filas.filter((f) => f.por_estado.PROVEEDOR_NO_SOPORTADO > 0).length >= 3, JSON.stringify(m.filas.map((f) => [f.proveedor, f.total])));
});
comprobar('proveedores: importes null-aware (FEDEFARMA, sin CIF, sin importe conocido = null)', () => {
  const fed = proveedores.proveedores.find((p) => p.clave === 'nombre:FEDEFARMA');
  return si(fed && fed.sin_cif && fed.importe_total_conocido === null && fed.facturas_sin_importe === 1, JSON.stringify(fed));
});

// --- Casos H4b ---------------------------------------------------------------------
comprobar('H4b: proveedores agrupados por CIF (nunca proveedor_id); sin CIF por nombre canónico R9', () => {
  const ps = proveedores.proveedores;
  const malos = ps.filter((p) => !/^(cif:[A-Z0-9]+|nombre:[A-Z0-9]+|sin_identificar)$/.test(p.clave) || 'id' in p || 'proveedor_id' in p);
  const claves = ps.map((p) => p.clave);
  return si(malos.length === 0 && isDeepStrictEqual(claves, ['cif:B00000003', 'cif:A00000001', 'cif:B00000002', 'nombre:FEDEFARMA'])
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
comprobar('H4b: funciones puras de CIF y nombre canónico', () => {
  const casos = [
    [normalizarCif(' b-0000.0003 '), 'B00000003'], [normalizarCif('  '), null], [normalizarCif(null), null],
    [nombreCanonico('Alliance Healthcare España, S.A.'), 'ALLIANCEHEALTHCAREESPANASA'],
    [nombreCanonico(' - '), null],
    [grupoProveedor('B00000003', 'X').clave, 'cif:B00000003'], [grupoProveedor(null, 'Fedefarma').clave, 'nombre:FEDEFARMA'],
    [grupoProveedor('', '  ').clave, 'sin_identificar'],
    [etiquetaYAlias(['B', 'A', 'B', null]).etiqueta, 'B'], [etiquetaYAlias(['B', 'A']).etiqueta, 'A'],
  ];
  const malos = casos.map(([a, b], i) => (a === b ? null : `#${i}: ${a}≠${b}`)).filter(Boolean);
  return si(malos.length === 0, malos.join(', '));
});
comprobar('H4b: incidencias INFO solo en el detalle de factura (ni contador ni atención de Inicio)', () => {
  const info = facturaDetalle[F(2)].incidencias.filter((i) => i.severidad === 'INFO');
  const enInicio = inicio.atencion.some((a) => a.codigo === 'MONEDA_NO_DOCUMENTADA');
  const abiertasNoInfo = [...h3a('incidencias'), ...INCIDENCIAS_H4B].filter((i) => i.estado === 'ABIERTA' && i.severidad !== 'INFO').length;
  return si(info.length === 1 && info[0].codigo === 'MONEDA_NO_DOCUMENTADA' && !enInicio && inicio.incidencias.abiertas === abiertasNoInfo
    && facturas.facturas.find((f) => f.factura_id === F(2)).incidencias_abiertas === 1, `info=${info.length} enInicio=${enInicio} abiertas=${inicio.incidencias.abiertas}/${abiertasNoInfo}`);
});
comprobar('H4b: textos de incidencia: diccionario por código; sin entrada, mensaje_usuario', () => {
  const t = (c) => inicio.atencion.find((a) => a.codigo === c)?.texto;
  return si(textoIncidencia({ codigo: 'MONEDA_NO_DOCUMENTADA', mensaje_usuario: 'x' }) === 'La factura no indica la moneda'
    && t('POSIBLE_DUPLICADO') === TEXTO_INCIDENCIA.POSIBLE_DUPLICADO
    && t('VALOR_SIN_EVIDENCIA') === 'El total de la factura no tiene evidencia legible en el documento.'
    && textoIncidencia({ codigo: 'CODIGO_DESCONOCIDO', mensaje_usuario: null }) === 'Incidencia CODIGO_DESCONOCIDO', 'textos mal');
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

// --- Informe ----------------------------------------------------------------------
for (const [estado, nombre, detalle] of resultados) console.log(`${estado.padEnd(4)} ${nombre}${detalle ? ' — ' + detalle : ''}`);
const fallos = resultados.filter((r) => r[0] !== 'OK').length;
console.log(`\n${resultados.length - fallos}/${resultados.length} OK`);
process.exit(fallos ? 1 : 0);
