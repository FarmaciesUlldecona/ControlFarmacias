/**
 * H5-8: nombre comercial de proveedor (uso R9 de solo lectura, autorizado por Pío). Solo presenta: nunca cambia
 * grupos, CIF ni identidades. Sin inventar: cada equivalencia sale de src/ (fichero:línea); lo que no está aquí se
 * muestra con el literal del PDF.
 *
 * Nombre = valor de ProveedorLocal (src/facturas/motor_local/catalogo.py:6-22) con "_" → " ".
 *  1. Por CIF normalizado (normalizarCif), solo los CIF que el adaptador del proveedor exige o lee como suyos.
 *  2. Por el literal, solo con las equivalencias de identidad del motor (canonicalizarProveedor, conciliacion.py:34-51,
 *     124-141) y el literal fijo que escribe el adaptador COFARES (cofares.py:211, sin CIF).
 * Si CIF y literal dan nombres distintos: null (falla cerrado; se muestra el literal).
 */

/**
 * Identidad del proveedor como la canonicaliza el motor (conciliacion.py:124-141): mayúsculas sin acentos, solo
 * A-Z/0-9, sin sufijos societarios; alias autorizados de Alliance (conciliacion.py:34-43) y de Hefame mercancía
 * (conciliacion.py:47-51). Sin imports (evita el ciclo contrato.ts ↔ detalle.ts); detalle.ts la reexporta.
 */
const ALIAS_ALLIANCE = ['SAFA', '1SAFA', 'ALLIANCE', 'ALLIANCEHEALTHCARE', 'ALLIANCEHEALTHCAREESPANA', 'CENCORA', '6PLATAFECO360AH'];
const ALIAS_HEFAME = ['3HEFAME', 'HEFAME', 'HDADFMCTCAMEDITSCL'];
export function canonicalizarProveedor(v: string | null): string | null {
  if (v === null) return null;
  const tokens = v.normalize('NFKD').replace(/\p{M}/gu, '').toUpperCase().match(/[A-Z0-9]+/g) ?? [];
  while (tokens.length && ['SA', 'SAU', 'SL', 'SLU', 'SRL'].includes(tokens[tokens.length - 1])) tokens.pop();
  for (const suf of [['S', 'A', 'U'], ['S', 'L', 'U'], ['S', 'A'], ['S', 'L']]) {
    if (tokens.slice(-suf.length).join(' ') === suf.join(' ')) { tokens.splice(-suf.length); break; }
  }
  const n = tokens.join('') || null;
  if (n !== null && ALIAS_ALLIANCE.includes(n)) return 'ALLIANCEHEALTHCARECENCORA';
  if (n !== null && ALIAS_HEFAME.includes(n)) return 'HEFAMEMERCANCIA';
  return n;
}

/** CIF comparable, igual que normalizarCif de contrato.ts (mayúsculas, solo A-Z/0-9; vacío → null). */
function cifComparable(v: string | null): string | null {
  const t = v === null ? '' : v.toUpperCase().replace(/[^A-Z0-9]/g, '');
  return t === '' ? null : t;
}

export interface EquivalenciaComercial { nombre: string; fuente: string }

/** CIF normalizado → nombre comercial. */
export const COMERCIAL_POR_CIF: Readonly<Record<string, EquivalenciaComercial>> = {
  // grupos_funcionales.py:41-45 (NIF F30004444 + layout hefame-local → grupo HEFAME); hefame.py:91-97; catalogo.py:9
  F30004444: { nombre: 'HEFAME', fuente: 'src/facturas/grupos_funcionales.py:41' },
  // alliance.py:308 (identidad legal: "ALLIANCE HEALTHCARE" y A50004324) y :440-441 (NIF del proveedor); catalogo.py:7
  A50004324: { nombre: 'ALLIANCE', fuente: 'src/facturas/motor_local/adaptadores/alliance.py:308' },
  // fedefarma.py:37 (identidad legal: "FEDERACIO FARMACEUTICA" y F-08-173395); catalogo.py:11
  F08173395: { nombre: 'FEDEFARMA', fuente: 'src/facturas/motor_local/adaptadores/fedefarma.py:37' },
  // gold_pequenos.py:391-394, 414 (AdaptadorLogista: CIF visible ESA61674347); catalogo.py:14
  ESA61674347: { nombre: 'LOGISTA PHARMA', fuente: 'src/facturas/motor_local/adaptadores/gold_pequenos.py:414' },
  // gold_pequenos.py:335-338, 347 (AdaptadorEports: NIF etiquetado B55688410); catalogo.py:13
  B55688410: { nombre: 'EPORTS', fuente: 'src/facturas/motor_local/adaptadores/gold_pequenos.py:347' },
  // gold_pequenos.py:441-444, 449 (AdaptadorMoretti: NIF visible B01959782); catalogo.py:15
  B01959782: { nombre: 'MORETTI', fuente: 'src/facturas/motor_local/adaptadores/gold_pequenos.py:449' },
  // gold_pequenos.py:473-476, 486 (AdaptadorTotalcare: NIF B-66438722); catalogo.py:16
  B66438722: { nombre: 'TOTALCARE', fuente: 'src/facturas/motor_local/adaptadores/gold_pequenos.py:486' },
  // gold_pequenos.py:509-512, 520 (AdaptadorLoreal: NIF A28050359); catalogo.py:17
  A28050359: { nombre: 'LOREAL', fuente: 'src/facturas/motor_local/adaptadores/gold_pequenos.py:520' },
  // hplus_consumo.py:39 (NIF legal B30462451); catalogo.py:10. No se agrupa en HEFAME: grupos_funcionales.py:47-56
  // exige además layout y contenido de consumibles, que la web no ve.
  B30462451: { nombre: 'HPLUS CONSUMO', fuente: 'src/facturas/motor_local/adaptadores/hplus_consumo.py:39' },
};

/** Literal canonicalizado (canonicalizarProveedor) → nombre comercial. */
export const COMERCIAL_POR_LITERAL: Readonly<Record<string, EquivalenciaComercial>> = {
  // Alias autorizados de Alliance (conciliacion.py:34-43 → ALLIANCEHEALTHCARECENCORA, :137-138)
  ALLIANCEHEALTHCARECENCORA: { nombre: 'ALLIANCE', fuente: 'src/facturas/runtime_supabase/conciliacion.py:34' },
  // Alias autorizados de Hefame mercancía (conciliacion.py:47-51 → HEFAMEMERCANCIA, :139-140; incluye HDAD...)
  HEFAMEMERCANCIA: { nombre: 'HEFAME', fuente: 'src/facturas/runtime_supabase/conciliacion.py:47' },
  // Literal fijo del adaptador COFARES (cofares.py:211 "GRUPO COFARES", sin NIF; ProveedorLocal.COFARES, registro.py:53)
  GRUPOCOFARES: { nombre: 'COFARES', fuente: 'src/facturas/motor_local/adaptadores/cofares.py:211' },
};

/** Nombre comercial de una factura (o null: se muestra el literal del PDF). */
export function nombreComercial(cif: string | null, literal: string | null): string | null {
  const c = cifComparable(cif);
  const porCif = c === null ? null : COMERCIAL_POR_CIF[c]?.nombre ?? null;
  const canon = canonicalizarProveedor(literal);
  const porLiteral = canon === null ? null : COMERCIAL_POR_LITERAL[canon]?.nombre ?? null;
  if (porCif !== null && porLiteral !== null && porCif !== porLiteral) return null;
  return porCif ?? porLiteral;
}

/** Nombre comercial de un grupo: el de todas sus facturas si coincide; si no, null. */
export function nombreComercialGrupo(nombres: (string | null)[]): string | null {
  const s = new Set(nombres);
  return s.size === 1 ? [...s][0] : null;
}

/** Minúsculas y sin acentos (misma normalización que la búsqueda del listado). */
export function plano(s: string): string {
  return s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().trim();
}

/** Razón social secundaria: solo si hay nombre comercial y el literal dice otra cosa. */
export function razonSocialSecundaria(comercial: string | null, razonSocial: string | null): string | null {
  if (comercial === null || razonSocial === null || razonSocial.trim() === '') return null;
  return plano(razonSocial) === plano(comercial) ? null : razonSocial.trim();
}
