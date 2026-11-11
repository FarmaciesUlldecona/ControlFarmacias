// Piezas comunes de las pantallas (H5).
import { useEffect, useState, type ReactNode } from 'react';
import type { Color, Importe } from '../server/contrato.ts';
import { razonSocialSecundaria } from '../server/proveedor_comercial.ts';
import { euros } from './formato.ts';

/**
 * H5-8: proveedor = nombre comercial (principal) + razón social del PDF (secundaria, pequeña). Sin equivalencia: el
 * literal del PDF como principal (o el respaldo). Nombre largo: una línea con "…" y el completo en title.
 */
export function NombreProveedor({ comercial, razon, respaldo = null }: { comercial: string | null; razon: string | null; respaldo?: string | null }) {
  const principal = comercial ?? razon ?? respaldo ?? 'Proveedor sin identificar';
  const secundaria = razonSocialSecundaria(comercial, razon);
  return (
    <span className="nombre-proveedor" data-proveedor-principal={principal}>
      <span className="nombre-truncado" title={principal}>{principal}</span>
      {secundaria && <span className="razon-social nombre-truncado" title={secundaria} data-razon-social>{secundaria}</span>}
    </span>
  );
}

export const CLASE: Record<Color, string> = { verde: 'g', azul: 'b', naranja: 'o', rojo: 'r', gris: 'n' };

export function Insignia({ color, children, ...resto }: { color: Color; children: ReactNode } & Record<`data-${string}`, string | undefined>) {
  return <span className={`insignia ${CLASE[color]}`} {...resto}>{children}</span>;
}

export function Cabecera({ titulo, subtitulo, children }: { titulo: string; subtitulo: string; children?: ReactNode }) {
  return (
    <header className="cabecera">
      <div>
        <h1>{titulo}</h1>
        <div className="tenue subtitulo">{subtitulo}</div>
      </div>
      <div className="acciones">
        {children}
        <button type="button" className="boton-deshabilitado" disabled title="Disponible en fase 2">Sincronizar ahora</button>
      </div>
    </header>
  );
}

/** Importe de una factura: null = "desconocido" (nunca 0). */
export function ImporteTotal({ v, fino = false }: { v: Importe; fino?: boolean }) {
  const t = euros(v, fino);
  return t === null ? <span className="desconocido" data-importe-desconocido>desconocido</span> : <>{t}</>;
}

/** true mientras la consulta de medios se cumple (p. ej. móvil). */
export function useMedia(consulta: string): boolean {
  const [si, setSi] = useState(() => typeof window !== 'undefined' && window.matchMedia(consulta).matches);
  useEffect(() => {
    const m = window.matchMedia(consulta);
    const cambio = () => setSi(m.matches);
    cambio();
    m.addEventListener('change', cambio);
    return () => m.removeEventListener('change', cambio);
  }, [consulta]);
  return si;
}

export const MOVIL = '(max-width: 900px)';
