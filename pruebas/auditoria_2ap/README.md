# Hito 2AP — compositor productivo del worker manual (certificación local)

Fecha: 2026-09-24. Sin conexión a Supabase ni Farmatic. Diseño en
[DISENO.md](DISENO.md). Inventario reproducible con
`python pruebas/auditoria_2ap/inventario_readonly.py <salida.json>` (solo lee
`C:\GoogleDrive\FACTURES PIO`).

## Origen de las 7 facturas productivas previas

| Factura | Hito | Extracción | Persistencia | Reutilizable |
|---|---|---|---|---|
| Logista 448.00 | 2I / 2K | `MotorDocumentoLocal` + ensamblado ad hoc en script | SQL directo (psycopg2) | No: ensamblado específico del script |
| COFARES 5460017198 | 2L2B | `MotorDocumentoLocal` + ensamblado ad hoc | SQL directo | No |
| Alliance 08009278/77/79 | 2R (2V renormaliza 08009277) | `MotorDocumentoLocal` + `adaptar_resultado_local` (en `src/`) | `cf_persistir_documento_multifactura` | **Sí** |
| HEFAME 0563834757 y 1132029554 | 2AA | `MotorDocumentoLocal` + ensamblado ad hoc | SQL directo | No |

## Inventario por contenido (junio–septiembre 2026, sin RITA)

146 PDF elegibles, 141 únicos por SHA-256. Layout determinado por los adaptadores
locales (`reconocer`), nunca por nombre de archivo:

| Layout | Docs | | Layout | Docs |
|---|---:|---|---|---:|
| alliance-local | 11 | | suavinex-historico-local | 4 |
| hefame-local | 10 | | fedefarma-local | 4 |
| cofares-local | 8 | | eports-local | 3 |
| ecoceutics-local | 5 | | hplus-consumo-local | 2 |
| logista / loreal / moretti / totalcare / dermofarm-h / gas-casa-h / pierre-fabre-h | 1 c/u | | | |

No clasificables: 87 = 71 sin layout reconocido (4 de ellos `PENDIENTE_OCR`) y
16 con excepción del motor local (`StopIteration`, `IndexError`, texto/cajas no
alineados). Multifactura detectada: 13 (11 Alliance, 2 FEDEFARMA).
Alliance: 11/11 documentos completos, 3–5 facturas cada uno, 43/43 facturas
autorizables por la barrera oficial (completas, validadas, identidad demostrada,
farmacia PIO resuelta por NIF).

## Proveedor elegido: Alliance

Único con puente certificado en `src/` ya usado en producción por la RPC
multifactura; mayor volumen reconocido; estructura estable (11/11 completos).

## Observación

Si falta una página de una factura Alliance, la completitud documental sigue
`true` pero esa factura queda `factura_completa_demostrada=false` y no se
autoriza; las demás facturas completas del PDF sí se autorizan. Es la regla
multifactura certificada (inventario completo, persistencia de segmentos
demostrados) y no se ha modificado.
