// El front solo habla con la API local (mismo origen, 127.0.0.1).
import { useEffect, useState } from 'react';

export interface EstadoApi {
  modo: 'FIXTURES' | 'REAL';
  farmacia: string;
  solo_lectura: boolean;
  usuario: string;
}

/**
 * Sesión caducada (p. ej. servidor reiniciado): en la web compilada se recarga la página y el servidor
 * muestra la pantalla de acceso. En desarrollo con Vite no (evita un bucle de recargas).
 */
function sesionCaducada(): void {
  if (import.meta.env.PROD) window.location.reload();
}

export type Carga<T> =
  | { estado: 'cargando' }
  | { estado: 'ok'; datos: T }
  | { estado: 'error'; mensaje: string };

export async function obtener<T>(ruta: string, señal?: AbortSignal): Promise<T> {
  if (!ruta.startsWith('/api/')) throw new Error('RUTA_NO_LOCAL');
  const r = await fetch(ruta, { signal: señal, headers: { accept: 'application/json' } });
  if (r.status === 401) {
    sesionCaducada();
    throw new Error('NO_AUTENTICADO');
  }
  if (!r.ok) {
    const cuerpo = (await r.json().catch(() => ({}))) as { error?: string };
    throw new Error(cuerpo.error ?? `HTTP ${r.status}`);
  }
  return (await r.json()) as T;
}

export interface CargaRecargable<T> {
  carga: Carga<T>;
  /** true mientras se relee con datos anteriores todavía en pantalla. */
  recargando: boolean;
  /** Hora (del navegador) de la última lectura correcta. */
  leidoAt: Date | null;
  recargar: () => void;
}

/** Como useApi, pero con "Actualizar": relee sin vaciar la pantalla y guarda la hora de lectura. */
export function useApiRecargable<T>(ruta: string): CargaRecargable<T> {
  const [carga, setCarga] = useState<Carga<T>>({ estado: 'cargando' });
  const [recargando, setRecargando] = useState(false);
  const [leidoAt, setLeidoAt] = useState<Date | null>(null);
  const [vez, setVez] = useState(0);
  useEffect(() => {
    const ctl = new AbortController();
    setRecargando(true);
    obtener<T>(ruta, ctl.signal)
      .then((datos) => { setCarga({ estado: 'ok', datos }); setLeidoAt(new Date()); })
      .catch((e: unknown) => {
        if (!ctl.signal.aborted) setCarga({ estado: 'error', mensaje: e instanceof Error ? e.message : String(e) });
      })
      .finally(() => { if (!ctl.signal.aborted) setRecargando(false); });
    return () => ctl.abort();
  }, [ruta, vez]);
  return { carga, recargando, leidoAt, recargar: () => setVez((v) => v + 1) };
}

export function useApi<T>(ruta: string): Carga<T> {
  const [carga, setCarga] = useState<Carga<T>>({ estado: 'cargando' });
  useEffect(() => {
    const ctl = new AbortController();
    setCarga({ estado: 'cargando' });
    obtener<T>(ruta, ctl.signal)
      .then((datos) => setCarga({ estado: 'ok', datos }))
      .catch((e: unknown) => {
        if (!ctl.signal.aborted) setCarga({ estado: 'error', mensaje: e instanceof Error ? e.message : String(e) });
      });
    return () => ctl.abort();
  }, [ruta]);
  return carga;
}
