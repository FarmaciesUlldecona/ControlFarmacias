/**
 * H7-AP1: apuntes manuales de Cashflow (migración 40). Formulario (desde una celda futura, «Añadir apunte» o para
 * editar = anular + crear), sección «Apuntes manuales» (sueltos y recurrentes vigentes, filtro por cuenta, anular con
 * motivo, anular una ocurrencia) y sugerencias de sustitución por una factura (botón Confirmar; nunca automático).
 * Las reglas son las de server/cashflow/apuntes.ts (las mismas que la BD, con sus códigos); el servidor y la BD las
 * vuelven a comprobar. Sin la credencial de Cashflow (REAL), todo se ve y los botones de escritura quedan desactivados.
 */
import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { Importe } from '../server/contrato.ts';
import { CUENTAS_CASHFLOW, clasificarCategoria, type CashflowDTO, type CuentaCashflow } from '../server/cashflow/cashflow.ts';
import {
  FRECUENCIAS, GRUPOS_CATEGORIA, LARGO, TEXTO_FRECUENCIA, candidatosSustitucion, comprobarAlta, limiteFuturo, listaApuntes, plantillaCuenta,
  primerDiaFuturo, validarAlta,
  type AltaApunte, type ApunteCashflow, type CandidatoSustitucion, type ContextoCashflow, type RecurrenteCashflow, type TablaAnulable, type TipoAlta,
} from '../server/cashflow/apuntes.ts';
import { MENSAJES_CASHFLOW, type CodigoErrorCashflow } from '../server/cashflow/errores_bd.ts';
import { ErrorApi, enviar } from './api.ts';
import { euros, fechaCorta, plural } from './formato.ts';

// ---------------------------------------------------------------------------
// Piezas comunes
// ---------------------------------------------------------------------------

const menos = (s: string) => s.replace('-', '−');
export const eurosApunte = (v: Importe) => (v === null ? 'importe pendiente' : menos(euros(v) ?? ''));
/** Mensaje de un código de la web o de la BD, sin el «No se ha guardado nada» (aún no se ha enviado). */
const mensaje = (codigo: CodigoErrorCashflow) => MENSAJES_CASHFLOW[codigo].mensaje.replace(/\s*No se ha guardado nada\.$/, '');
const textoError = (e: unknown) => (e instanceof ErrorApi ? e.mensaje ?? Object.values(e.errores)[0] ?? e.codigo : e instanceof Error ? e.message : String(e));
/** Salida (RS) con signo negativo; entrada (RE) positiva: como en la tabla. */
const conSigno = (categoria: string, importe: number) => (clasificarCategoria(categoria)?.sentido === 'SALIDA' ? -importe : importe);
const sentidoTexto = (categoria: string) => {
  const c = clasificarCategoria(categoria);
  return c === null ? '' : c.sentido === 'SALIDA' ? 'salida: resta del saldo' : 'entrada: suma al saldo';
};
export const contextoDe = (d: CashflowDTO): ContextoCashflow => ({ datos: d, previsiones: d.previsiones });

/** Ventana lateral (desglose, alta y edición). */
export function Dialogo({ titulo, subtitulo, onCerrar, children, datos }: { titulo: string; subtitulo: string; onCerrar: () => void; children: ReactNode; datos?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onCerrar(); };
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [onCerrar]);
  return (
    <div className="cf-velo" onClick={onCerrar}>
      <div className="cf-desglose tarjeta" role="dialog" aria-modal="true" aria-labelledby="t-cf-desglose" tabIndex={-1} ref={ref}
        onClick={(e) => { e.stopPropagation(); if ((e.target as HTMLElement).closest('a')) onCerrar(); }} data-cf-desglose={datos ?? ''}>
        <header>
          <div>
            <h2 id="t-cf-desglose">{titulo}</h2>
            <span className="tenue">{subtitulo}</span>
          </div>
          <button type="button" className="boton-secundario" onClick={onCerrar}>Cerrar</button>
        </header>
        <div className="cf-desglose-cuerpo">{children}</div>
      </div>
    </div>
  );
}

/** Botón de anular que pide el motivo (obligatorio) antes de confirmar. */
function AnularConMotivo({ etiqueta, deshabilitado, titulo, onConfirmar, datos }: {
  etiqueta: string; deshabilitado: string | null; titulo: string; onConfirmar: (motivo: string) => Promise<void>; datos: string;
}) {
  const [abierto, setAbierto] = useState(false);
  const [motivo, setMotivo] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  if (!abierto) {
    return (
      <button type="button" className="boton-mini boton-peligro-suave" data-ap-anular={datos} disabled={deshabilitado !== null}
        title={deshabilitado ?? titulo} onClick={() => { setAbierto(true); setError(null); }}>{etiqueta}</button>
    );
  }
  const confirmar = async () => {
    if (motivo.trim() === '') { setError(mensaje('MOTIVO_ANULACION_AUSENTE')); return; }
    setEnviando(true);
    try { await onConfirmar(motivo.trim()); } catch (e) { setError(textoError(e)); setEnviando(false); }
  };
  return (
    <span className="ap-anular" data-ap-anulando={datos}>
      <input type="text" className="ap-motivo" data-ap-motivo maxLength={LARGO.motivo} placeholder="Motivo (obligatorio)" aria-label={`Motivo: ${titulo}`}
        value={motivo} onChange={(e) => setMotivo(e.target.value)} aria-invalid={error !== null} autoFocus
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); void confirmar(); } }} />
      <button type="button" className="boton-mini boton-peligro" data-ap-confirmar-anular disabled={enviando} onClick={() => void confirmar()}>Confirmar anulación</button>
      <button type="button" className="boton-mini boton-secundario" onClick={() => { setAbierto(false); setMotivo(''); setError(null); }}>Cancelar</button>
      {error && <span className="rrhh-campo-error" role="alert" data-ap-error>{error}</span>}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Formulario: apunte suelto o recurrente
// ---------------------------------------------------------------------------

const NUEVO = '__nuevo__';
interface Estado {
  tipo: TipoAlta; cuenta: string; categoria: string; concepto: string; nombreNuevo: string; cif: string;
  importe: string; fecha: string; frecuencia: string; dia: string; inicio: string; fin: string; nota: string; motivo: string;
}
/** Celda de la que sale el formulario: cuenta, categoría y concepto fijos; fecha dentro de la decena (o el mes). */
export interface CeldaFija { cuenta: CuentaCashflow; categoria: string; concepto: string; desde: string; hasta: string; texto: string }
/** Edición: lo anterior se anula (con motivo) y se crea lo nuevo en la misma transacción. */
export interface Edicion { tabla: TablaAnulable; fila: ApunteCashflow | RecurrenteCashflow }

function estadoInicial(fija: CeldaFija | null, edicion: Edicion | null): Estado {
  const base: Estado = {
    tipo: 'SUELTO', cuenta: fija?.cuenta ?? 'PIO', categoria: fija?.categoria ?? '', concepto: fija?.concepto ?? '', nombreNuevo: '', cif: '',
    importe: '', fecha: '', frecuencia: 'MENSUAL', dia: '', inicio: '', fin: '', nota: '', motivo: '',
  };
  if (edicion === null) return base;
  const f = edicion.fila;
  const comun = { ...base, cuenta: f.cuenta, categoria: f.categoria, concepto: f.concepto, nota: f.nota ?? '' };
  if (edicion.tabla === 'APUNTE') {
    const a = f as ApunteCashflow;
    return { ...comun, tipo: 'SUELTO', importe: a.importe === null ? '' : String(a.importe), fecha: a.fecha };
  }
  const r = f as RecurrenteCashflow;
  return { ...comun, tipo: 'RECURRENTE', importe: String(r.importe), frecuencia: r.frecuencia, dia: String(r.dia), inicio: r.inicio, fin: r.fin ?? '' };
}
const numero = (s: string) => (s.trim() === '' ? null : Number(s.replace(',', '.')));

function cuerpoAlta(e: Estado): Record<string, unknown> {
  const nuevo = e.concepto === NUEVO;
  return {
    tipo: e.tipo, cuenta: e.cuenta, categoria: e.categoria,
    concepto: nuevo || e.concepto === '' ? null : e.concepto,
    concepto_nuevo: nuevo ? { nombre: e.nombreNuevo, proveedor_cif: e.cif.trim() === '' ? null : e.cif.trim().toUpperCase() } : null,
    importe: numero(e.importe), nota: e.nota.trim() === '' ? null : e.nota,
    fecha: e.tipo === 'SUELTO' ? e.fecha || null : null,
    frecuencia: e.tipo === 'RECURRENTE' ? e.frecuencia : null, dia: e.tipo === 'RECURRENTE' ? numero(e.dia) : null,
    inicio: e.tipo === 'RECURRENTE' ? e.inicio || null : null, fin: e.tipo === 'RECURRENTE' ? e.fin || null : null,
  };
}

export function FormularioApunte({ d, fija = null, edicion = null, onHecho, onCancelar }: {
  d: CashflowDTO; fija?: CeldaFija | null; edicion?: Edicion | null; onHecho: (texto: string) => void; onCancelar?: () => void;
}) {
  const [e, setE] = useState<Estado>(() => estadoInicial(fija, edicion));
  const [errores, setErrores] = useState<Record<string, string>>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const escritura = d.escritura_cashflow;
  const ctx = contextoDe(d);
  const plantilla = useMemo(() => plantillaCuenta(d, d.previsiones, e.cuenta), [d, e.cuenta]);
  const cat = plantilla.find((c) => c.categoria === e.categoria) ?? null;
  const limite = limiteFuturo(d, e.cuenta);
  const minimo = limite === null ? undefined : [primerDiaFuturo(limite), fija?.desde ?? ''].sort().reverse()[0];
  const cambiar = (k: keyof Estado, v: string) => { setErrores({}); setGeneral(null); setE((x) => {
    const n = { ...x, [k]: v };
    if (k === 'cuenta') { n.categoria = ''; n.concepto = ''; }
    if (k === 'categoria') n.concepto = '';
    // Recurrente: el día, el de «desde» (si no se ha elegido otro).
    if (k === 'inicio' && v && x.dia === '') n.dia = String(Number(v.slice(8)));
    return n;
  }); };
  const campo = (k: string, etiqueta: string, control: ReactNode, pista?: string, ancho = false) => (
    <label className={`rrhh-campo${ancho ? ' rrhh-campo-ancho' : ''}`}>
      <span>{etiqueta}{pista && <span className="rrhh-campo-pista"> {pista}</span>}</span>
      {control}
      {errores[k] && <span className="rrhh-campo-error" data-ap-error-campo={k}>{errores[k]}</span>}
    </label>
  );
  const enviarFormulario = async (ev: FormEvent) => {
    ev.preventDefault();
    setErrores({});
    setGeneral(null);
    const cuerpo = cuerpoAlta(e);
    const v = validarAlta(cuerpo);
    if (!v.ok) { setErrores(v.errores); return; }
    // Las mismas reglas que la BD, con lo que la pantalla ya ha leído (editar: como si lo anterior ya estuviera anulado).
    const sin = edicion === null ? ctx : { ...ctx, previsiones: { ...ctx.previsiones, apuntes: ctx.previsiones.apuntes.filter((x) => x.id !== edicion.fila.id), recurrentes: ctx.previsiones.recurrentes.filter((x) => x.id !== edicion.fila.id) } };
    const f = comprobarAlta(v.datos as AltaApunte, sin);
    if (f) { if (f.campo) setErrores({ [f.campo]: mensaje(f.codigo) }); else setGeneral(mensaje(f.codigo)); return; }
    if (fija && v.datos.tipo === 'SUELTO' && v.datos.fecha !== null && (v.datos.fecha < fija.desde || v.datos.fecha > fija.hasta)) {
      setErrores({ fecha: `La fecha tiene que estar dentro de ${fija.texto}.` });
      return;
    }
    if (edicion !== null && e.motivo.trim() === '') { setErrores({ motivo: mensaje('MOTIVO_ANULACION_AUSENTE') }); return; }
    setEnviando(true);
    try {
      if (edicion === null) await enviar('/api/cashflow/apuntes', 'POST', cuerpo);
      else await enviar('/api/cashflow/apuntes/editar', 'POST', { anterior: { tabla: edicion.tabla, id: edicion.fila.id }, motivo: e.motivo.trim(), alta: cuerpo });
      onHecho(edicion !== null ? 'Cambio guardado: el anterior queda anulado con su motivo.' : e.tipo === 'SUELTO' ? 'Apunte manual guardado.' : 'Recurrente guardado.');
    } catch (err) {
      setGeneral(textoError(err));
      setEnviando(false);
    }
  };
  const sinEscritura = escritura.habilitada ? null : escritura.mensaje ?? mensaje('CREDENCIAL_CASHFLOW_AUSENTE');
  const sentido = sentidoTexto(e.categoria);
  return (
    <form className="ap-form" onSubmit={enviarFormulario} noValidate data-ap-form={edicion ? 'editar' : fija ? 'celda' : 'nuevo'}>
      <div className="cf-segmento" role="group" aria-label="Tipo de apunte">
        {(['SUELTO', 'RECURRENTE'] as const).map((t) => (
          <button key={t} type="button" aria-pressed={e.tipo === t} data-ap-tipo={t} onClick={() => cambiar('tipo', t)}>
            {t === 'SUELTO' ? 'Apunte manual' : 'Recurrente'}
          </button>
        ))}
      </div>
      {fija ? (
        <p className="ap-fijo" data-ap-fijo>
          <strong>{fija.cuenta}</strong> · {fija.categoria} · <strong>{fija.concepto}</strong>
          <span className="tenue"> ({sentido}) · {fija.texto}</span>
        </p>
      ) : (
        <div className="rrhh-campos">
          {campo('cuenta', 'Cuenta', (
            <select data-ap-campo="cuenta" value={e.cuenta} onChange={(x) => cambiar('cuenta', x.target.value)}>
              {CUENTAS_CASHFLOW.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          ), e.cuenta === 'RITA' ? 'solo su propia cuenta' : undefined)}
          {campo('categoria', 'Categoría', (
            <select data-ap-campo="categoria" value={e.categoria} onChange={(x) => cambiar('categoria', x.target.value)} aria-invalid={!!errores.categoria}>
              <option value="">Elige…</option>
              {GRUPOS_CATEGORIA.map((g) => {
                const cs = plantilla.filter((c) => c.grupo === g);
                return cs.length === 0 ? null : <optgroup key={g} label={g}>{cs.map((c) => <option key={c.categoria} value={c.categoria}>{c.categoria}</option>)}</optgroup>;
              })}
            </select>
          ), sentido ? `(${sentido})` : undefined)}
          {campo('concepto', 'Concepto', (
            <select data-ap-campo="concepto" value={e.concepto} onChange={(x) => cambiar('concepto', x.target.value)} disabled={cat === null} aria-invalid={!!errores.concepto}>
              <option value="">Elige…</option>
              {(cat?.conceptos ?? []).map((c) => <option key={c.nombre} value={c.nombre}>{c.nombre}{c.nuevo ? ' (nuevo)' : ''}</option>)}
              <option value={NUEVO}>+ Concepto nuevo…</option>
            </select>
          ))}
          {e.concepto === NUEVO && campo('concepto_nuevo', 'Nombre del concepto nuevo', (
            <input type="text" data-ap-campo="concepto_nuevo" maxLength={LARGO.nombre} value={e.nombreNuevo} onChange={(x) => cambiar('nombreNuevo', x.target.value)} aria-invalid={!!errores.concepto_nuevo} />
          ), `en ${e.categoria || 'la categoría'}`)}
          {e.concepto === NUEVO && campo('proveedor_cif', 'CIF del proveedor', (
            <input type="text" data-ap-campo="proveedor_cif" maxLength={20} value={e.cif} onChange={(x) => cambiar('cif', x.target.value)} aria-invalid={!!errores.proveedor_cif} />
          ), 'opcional: coloca sus facturas')}
        </div>
      )}
      <div className="rrhh-campos">
        {campo('importe', `Importe${sentido ? ` (${sentido.split(':')[0]})` : ''}`, (
          <input type="number" inputMode="decimal" min="0.01" step="0.01" data-ap-campo="importe" value={e.importe} onChange={(x) => cambiar('importe', x.target.value)} aria-invalid={!!errores.importe} />
        ), '€, siempre positivo')}
        {e.tipo === 'SUELTO' && campo('fecha', 'Fecha', (
          <input type="date" data-ap-campo="fecha" min={minimo} max={fija?.hasta} value={e.fecha} onChange={(x) => cambiar('fecha', x.target.value)} aria-invalid={!!errores.fecha} />
        ), fija ? 'dentro de la columna' : 'solo futura')}
        {e.tipo === 'RECURRENTE' && campo('frecuencia', 'Periodicidad', (
          <select data-ap-campo="frecuencia" value={e.frecuencia} onChange={(x) => cambiar('frecuencia', x.target.value)}>
            {FRECUENCIAS.map((f) => <option key={f} value={f}>{TEXTO_FRECUENCIA[f]}</option>)}
          </select>
        ))}
        {e.tipo === 'RECURRENTE' && campo('dia', 'Día del mes', (
          <input type="number" min="1" max="31" step="1" data-ap-campo="dia" value={e.dia} onChange={(x) => cambiar('dia', x.target.value)} aria-invalid={!!errores.dia} />
        ), 'si el mes no lo tiene, el último')}
        {e.tipo === 'RECURRENTE' && campo('inicio', 'Desde', (
          <input type="date" data-ap-campo="inicio" min={minimo} value={e.inicio} onChange={(x) => cambiar('inicio', x.target.value)} aria-invalid={!!errores.inicio} />
        ), 'primera vez')}
        {e.tipo === 'RECURRENTE' && campo('fin', 'Hasta', (
          <input type="date" data-ap-campo="fin" min={e.inicio || minimo} value={e.fin} onChange={(x) => cambiar('fin', x.target.value)} aria-invalid={!!errores.fin} />
        ), 'opcional')}
        {campo('nota', 'Nota', (
          <input type="text" data-ap-campo="nota" maxLength={LARGO.nota} value={e.nota} onChange={(x) => cambiar('nota', x.target.value)} aria-invalid={!!errores.nota} />
        ), 'opcional', true)}
        {edicion !== null && campo('motivo', 'Motivo del cambio', (
          <input type="text" data-ap-campo="motivo" maxLength={LARGO.motivo} value={e.motivo} onChange={(x) => cambiar('motivo', x.target.value)} aria-invalid={!!errores.motivo} />
        ), 'obligatorio: lo anterior queda anulado con él', true)}
      </div>
      {limite !== null && <p className="tenue ap-ayuda">Solo fechas futuras: después del {fechaCorta(limite)} (último saldo de banco de {e.cuenta}). Autor: {escritura.autor}.</p>}
      {general && <p className="rrhh-error" role="alert" data-ap-error>{general}</p>}
      <div className="rrhh-botones">
        <button type="submit" className="boton-primario" data-ap-guardar disabled={enviando || sinEscritura !== null} title={sinEscritura ?? undefined}>
          {edicion ? 'Guardar cambio' : 'Guardar'}
        </button>
        {onCancelar && <button type="button" className="boton-secundario" onClick={onCancelar}>Cancelar</button>}
      </div>
      {sinEscritura && <p className="cf-nota" data-ap-sin-escritura>{sinEscritura}</p>}
    </form>
  );
}

// ---------------------------------------------------------------------------
// Sugerencias de sustitución (nunca automáticas)
// ---------------------------------------------------------------------------

export function Sugerencia({ c, d, onHecho }: { c: CandidatoSustitucion; d: CashflowDTO; onHecho: (texto: string) => void }) {
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const sinEscritura = d.escritura_cashflow.habilitada ? null : d.escritura_cashflow.mensaje;
  const v = c.vencimiento;
  const confirmar = async () => {
    setEnviando(true);
    setError(null);
    try {
      await enviar('/api/cashflow/sustituciones', 'POST', {
        apunte_id: c.apunte_id, recurrente_id: c.recurrente_id, fecha_ocurrencia: c.tipo === 'OCURRENCIA' ? c.fecha : null,
        factura_id: v.factura_id, vencimiento_orden: v.vencimiento_orden,
      });
      onHecho(`Apunte sustituido por la factura ${v.numero_factura ?? 'sin número'}: queda anulado y cuenta el vencimiento.`);
    } catch (e) { setError(textoError(e)); setEnviando(false); }
  };
  return (
    <li className="ap-sugerencia" data-ap-sugerencia={c.clave}>
      <span className="ap-sugerencia-texto">
        <strong>Sustituir apunte por factura <Link to={`/facturas/${v.factura_id}`}>{v.numero_factura ?? 'sin número'}</Link></strong>
        <span className="tenue">
          {c.cuenta} · {c.concepto}: {c.tipo === 'OCURRENCIA' ? 'ocurrencia' : 'apunte'} del {fechaCorta(c.fecha)} <span className="cf-num">{eurosApunte(conSigno(c.categoria, c.importe))}</span>
          {' → '}vencimiento del {fechaCorta(v.fecha_vencimiento)} <span className="cf-num">{eurosApunte(conSigno(c.categoria, Math.abs(v.importe)))}</span>
          {c.diferencia !== 0 && <> (diferencia {eurosApunte(c.diferencia)})</>}
        </span>
      </span>
      <button type="button" className="boton-mini boton-primario" data-ap-confirmar-sustitucion disabled={enviando || sinEscritura !== null} title={sinEscritura ?? 'Anula el apunte y guarda la factura que lo sustituye'}
        onClick={() => void confirmar()}>Confirmar</button>
      {error && <span className="rrhh-campo-error" role="alert" data-ap-error>{error}</span>}
    </li>
  );
}

// ---------------------------------------------------------------------------
// Sección «Apuntes manuales»
// ---------------------------------------------------------------------------

const textoRecurrente = (r: RecurrenteCashflow) =>
  `${TEXTO_FRECUENCIA[r.frecuencia]}, día ${r.dia}, desde ${fechaCorta(r.inicio)}${r.fin ? ` hasta ${fechaCorta(r.fin)}` : ' sin fin'}`;

export function SeccionApuntes({ d, aviso, onCambio }: { d: CashflowDTO; aviso: string | null; onCambio: (texto: string) => void }) {
  const [filtro, setFiltro] = useState<CuentaCashflow | null>(null);
  const [nuevo, setNuevo] = useState(false);
  const [editar, setEditar] = useState<Edicion | null>(null);
  const ctx = contextoDe(d);
  const lista = listaApuntes(ctx, filtro);
  const sugerencias = candidatosSustitucion(ctx, d.vencimientos).filter((c) => filtro === null || c.cuenta === filtro);
  const escritura = d.escritura_cashflow;
  const sinEscritura = escritura.habilitada ? null : escritura.mensaje ?? mensaje('CREDENCIAL_CASHFLOW_AUSENTE');
  const hecho = (t: string) => { setNuevo(false); setEditar(null); onCambio(t); };
  const anular = (tabla: TablaAnulable, id: string) => async (motivo: string) => {
    await enviar(`/api/cashflow/${tabla === 'APUNTE' ? 'apuntes' : 'recurrentes'}/${id}/anular`, 'PUT', { motivo });
    onCambio(tabla === 'APUNTE' ? 'Apunte anulado.' : 'Recurrente anulado: todas sus ocurrencias dejan de contar.');
  };
  const anularOcurrencia = (id: string, fecha: string) => async (motivo: string) => {
    await enviar(`/api/cashflow/recurrentes/${id}/anular-ocurrencia`, 'POST', { fecha_ocurrencia: fecha, motivo });
    onCambio(`Ocurrencia del ${fechaCorta(fecha)} anulada.`);
  };
  const autor = (x: { autor: string; creado_at: string }) => <span className="tenue">{x.autor} · {fechaCorta(x.creado_at)}</span>;
  return (
    <section className="tarjeta cf-bloque ap-seccion" aria-labelledby="t-ap" data-ap-seccion>
      <div className="ap-cabecera">
        <h2 id="t-ap">Apuntes manuales <span className="insignia b" data-ap-total>{lista.sueltos.length + lista.recurrentes.length}</span></h2>
        <div className="cf-segmento" role="group" aria-label="Cuenta de los apuntes">
          {([null, ...CUENTAS_CASHFLOW] as const).map((c) => (
            <button key={c ?? 'todas'} type="button" aria-pressed={filtro === c} data-ap-filtro={c ?? 'TODAS'} onClick={() => setFiltro(c)}>{c ?? 'Todas'}</button>
          ))}
        </div>
        <button type="button" className="boton-primario" data-ap-anadir disabled={sinEscritura !== null} title={sinEscritura ?? 'Apunte suelto o recurrente, en cualquier concepto o en uno nuevo'}
          onClick={() => { setEditar(null); setNuevo(true); }}>Añadir apunte</button>
      </div>
      <p className="tenue cf-ayuda">Previsión sin factura: mandan sobre el Excel y la media de su concepto y decena; con vencimientos, cuenta el mayor. Nunca se borran: se anulan con su motivo.</p>
      {sinEscritura && <p className="cf-aviso-gris" role="status" data-ap-sin-escritura>{sinEscritura}</p>}
      {aviso && <p className="rrhh-aviso-ok" role="status" data-ap-aviso-ok>{aviso}</p>}

      {sugerencias.length > 0 && (
        <div className="ap-bloque" data-ap-sugerencias={sugerencias.length}>
          <h3>Facturas que coinciden con un apunte <span className="tenue">(mismo concepto, misma decena o la siguiente, ±5 %)</span></h3>
          <ul className="ap-lista">{sugerencias.map((c) => <Sugerencia key={c.clave} c={c} d={d} onHecho={onCambio} />)}</ul>
        </div>
      )}

      <div className="ap-bloque">
        <h3>Apuntes sueltos</h3>
        {lista.sueltos.length === 0 ? <p className="tenue">Ninguno{filtro ? ` en ${filtro}` : ''}.</p> : (
          <ul className="ap-lista">
            {lista.sueltos.map((a) => (
              <li key={a.id} className="ap-fila" data-ap-suelto={a.id}>
                <span className="ap-fecha">{fechaCorta(a.fecha)}</span>
                <span className="ap-que"><strong>{a.cuenta}</strong> · {a.categoria} · <strong>{a.concepto}</strong>{a.nota && <span className="tenue"> — {a.nota}</span>}</span>
                <span className="cf-num ap-importe">{eurosApunte(conSigno(a.categoria, a.importe as number))}</span>
                {autor(a)}
                <span className="ap-acciones">
                  <button type="button" className="boton-mini boton-secundario" data-ap-editar={a.id} disabled={sinEscritura !== null} title={sinEscritura ?? 'Anular y crear otro'}
                    onClick={() => { setNuevo(false); setEditar({ tabla: 'APUNTE', fila: a }); }}>Editar</button>
                  <AnularConMotivo etiqueta="Anular" titulo={`Anular el apunte del ${fechaCorta(a.fecha)}`} deshabilitado={sinEscritura} datos={a.id} onConfirmar={anular('APUNTE', a.id)} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="ap-bloque">
        <h3>Recurrentes</h3>
        {lista.recurrentes.length === 0 ? <p className="tenue">Ninguno{filtro ? ` en ${filtro}` : ''}.</p> : (
          <ul className="ap-lista">
            {lista.recurrentes.map(({ recurrente: r, proximas, anuladas }) => (
              <li key={r.id} className="ap-fila ap-recurrente" data-ap-recurrente={r.id}>
                <span className="ap-fecha">{TEXTO_FRECUENCIA[r.frecuencia]}</span>
                <span className="ap-que"><strong>{r.cuenta}</strong> · {r.categoria} · <strong>{r.concepto}</strong>{r.nota && <span className="tenue"> — {r.nota}</span>}
                  <span className="tenue ap-regla" data-ap-regla>{textoRecurrente(r)}</span></span>
                <span className="cf-num ap-importe">{eurosApunte(conSigno(r.categoria, r.importe))}</span>
                {autor(r)}
                <span className="ap-acciones">
                  <button type="button" className="boton-mini boton-secundario" data-ap-editar={r.id} disabled={sinEscritura !== null} title={sinEscritura ?? 'Anular y crear otro'}
                    onClick={() => { setNuevo(false); setEditar({ tabla: 'RECURRENTE', fila: r }); }}>Editar</button>
                  <AnularConMotivo etiqueta="Anular recurrente" titulo="Anular el recurrente y todas sus ocurrencias" deshabilitado={sinEscritura} datos={r.id} onConfirmar={anular('RECURRENTE', r.id)} />
                </span>
                <div className="ap-ocurrencias">
                  <span className="tenue">Próximas:</span>
                  {proximas.length === 0 && <span className="tenue">ninguna futura</span>}
                  {proximas.map((f) => (
                    <span key={f} className="ap-ocurrencia" data-ap-ocurrencia={`${r.id}|${f}`}>
                      <span className="cf-num">{fechaCorta(f)}</span>
                      <AnularConMotivo etiqueta="Anular esta" titulo={`Anular solo la del ${fechaCorta(f)}`} deshabilitado={sinEscritura} datos={`${r.id}|${f}`} onConfirmar={anularOcurrencia(r.id, f)} />
                    </span>
                  ))}
                </div>
                {anuladas.length > 0 && (
                  <div className="ap-ocurrencias tenue" data-ap-anuladas={anuladas.length}>
                    Anuladas: {anuladas.map((a) => `${fechaCorta(a.fecha_ocurrencia)}${a.nota ? ` (${a.nota})` : ''}`).join('; ')}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      {(lista.anulados > 0 || lista.sustituidos > 0) && (
        <p className="tenue" data-ap-anulados={lista.anulados}>
          {plural(lista.anulados, 'apunte o recurrente anulado', 'apuntes o recurrentes anulados')}{lista.sustituidos > 0 ? `, ${plural(lista.sustituidos, 'sustituido', 'sustituidos')} por una factura` : ''} (no se listan; quedan en el historial).
        </p>
      )}

      {(nuevo || editar) && (
        <Dialogo titulo={editar ? 'Editar apunte' : 'Añadir apunte'} subtitulo={editar ? 'Lo anterior queda anulado con el motivo y se crea lo nuevo' : 'Apunte suelto o recurrente · solo fechas futuras'}
          onCerrar={() => { setNuevo(false); setEditar(null); }} datos="apunte">
          <FormularioApunte d={d} edicion={editar} onHecho={hecho} onCancelar={() => { setNuevo(false); setEditar(null); }} />
        </Dialogo>
      )}
    </section>
  );
}
