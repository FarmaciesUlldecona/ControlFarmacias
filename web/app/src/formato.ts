// Formatos es-ES. Importe ausente (null) nunca se muestra como 0: quien llama decide el texto.
import type { Importe } from '../server/contrato.ts';

const EUR = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', useGrouping: 'always' });
const EUR_FINO = new Intl.NumberFormat('es-ES', {
  style: 'currency', currency: 'EUR', useGrouping: 'always', minimumFractionDigits: 2, maximumFractionDigits: 4,
});
const PORCENTAJE = new Intl.NumberFormat('es-ES', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 });

/** "1.234,56 €" o null si el importe es desconocido. */
export function euros(v: Importe, fino = false): string | null {
  return v === null ? null : (fino ? EUR_FINO : EUR).format(v);
}

export function porcentaje(v: number): string {
  return PORCENTAJE.format(v);
}

/** 'YYYY-MM-DD…' → '15/11/2026' (sin zona horaria: la fecha es la del documento). */
export function fechaCorta(iso: string | null): string {
  if (iso === null) return 'sin fecha';
  const [a, m, d] = iso.slice(0, 10).split('-');
  return `${d}/${m}/${a}`;
}

/** Instante → 'lunes, 2 de noviembre de 2026' en hora de Madrid. */
export function fechaLarga(instante: string): string {
  const t = new Intl.DateTimeFormat('es-ES', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Europe/Madrid',
  }).format(new Date(instante));
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** Instante → '19/10/2026 03:00' en hora de Madrid (null → 'sin fecha'). */
export function fechaHora(instante: string | null): string {
  if (instante === null) return 'sin fecha';
  return new Intl.DateTimeFormat('es-ES', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Madrid',
  }).format(new Date(instante)).replace(',', '');
}

/** Porcentaje literal de un tipo (10 → '10 %', 1.4 → '1,4 %'). */
export function tipoPorcentaje(v: number | null): string {
  return v === null ? '—' : `${new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 }).format(v)} %`;
}

export function hora(d: Date): string {
  return d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

/** "1 factura" / "3 facturas". */
export function plural(n: number, uno: string, varios: string): string {
  return `${n} ${n === 1 ? uno : varios}`;
}
