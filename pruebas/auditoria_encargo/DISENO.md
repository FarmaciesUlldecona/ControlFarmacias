# ENCARGO: «ENCARGO» a secas es mercancía (R10, adaptador Alliance 1.3.1) y enriquecimiento R12 de 08012619

Decisión de Pio (2026-11-14). Solo local; sin push (lo hace Pio). **El enriquecimiento de este documento NO se ha
ejecutado**: es el diseño para un hito posterior, con su propia confirmación.

## 1. Cambio

- **R10 ampliada:** el tipo de pedido Alliance `ENCARGO` (literal exacto, sin más texto) es mercancía en el bloque
  `CARGOS`, igual que `ENCARGO VACUNAS`. La prueba de recepción sigue siendo el cruce con `Supabase.albaranes` en la
  conciliación. En `ABONOS` no está certificado: sigue `NO_DEMOSTRABLE` (`TIPO_PEDIDO_NO_CERTIFICADO`).
- **Adaptador:** `alliance-local` 1.3.0 → **1.3.1** (`src/facturas/motor_local/adaptadores/alliance.py`).
- **Automatización (D1):** la autoridad del compositor automático pasa a `alliance-local` **1.3.1**; la 1.3.0 deja de
  estar certificada para la ruta automática (`src/facturas/runtime_supabase/compositor_automatico.py`).

## 2. Banco Alliance completo, 1.3.0 frente a 1.3.1

Fuera del repositorio, en `C:\ControlFarmacias\evidencias_encargo\` (`SHA256SUMS.txt`). Scripts:
`scripts/banco_alliance.py` (motor local + puente multifactura, en memoria, sin red) y `scripts/analizar_cambios.py`.

- Corpus: los 91 PDF distintos (por SHA) del espejo `C:\GoogleDrive\FACTURES PIO` con el NIF de Alliance
  (A50004324): 78 reconocidos como `alliance-local`; 13 sin layout (los mismos con las dos versiones).
- **89 documentos:** idénticos salvo el número de versión.
- **2 documentos** cambian, cada uno en una sola fila `ENCARGO`, y **nada más** (salida del adaptador y salida
  normalizada, factura a factura, quitando el albarán nuevo, su clasificación y la incidencia de no promoción):

| PDF | Factura | Fila (página) | Antes | Después |
|---|---|---|---|---|
| `ALLIANCE VTO 20.12-6.1.27-20.1.27-6.2.27 PIO.pdf` | 08012619 | `14-10-2026 ENCARGO 08D50803 7,10 7,42` (p. 5) | `NO_DEMOSTRABLE`, incidencia `CANDIDATO_ALBARAN_NO_PROMOVIDO` (`TIPO_PEDIDO_NO_CERTIFICADO`, `ENCARGO`) | albarán 08D50803 promovido (117 → 118); incidencia retirada |
| `ALLIANCE VTO 7.3.26 PIO.pdf` | 08016545 | `29-12-2025 ENCARGO 08E58484 4,11 4,29` (p. 3) | igual | albarán 08E58484 promovido (122 → 123); incidencia retirada |

- Las otras 3 facturas del documento de 08012619 (08012620, 08012621 y 08012622) quedan idénticas.
- **08016545 no estaba en el encargo:** es el segundo documento afectado. Su estado en Supabase no se ha consultado.
  Queda `PENDIENTE` de decisión de Pio (mismo camino R12 si sigue `PENDIENTE_CONCILIAR`).
- En la fila de 08E58484 el literal de fila arrastra un `50830` de la dirección vertical del proveedor; número,
  fecha, base y total salen de sus columnas y son correctos.

## 3. Diseño del enriquecimiento R12 de 08012619 (sin ejecutar)

Mismo camino que el 2BB (08007971, 2026-10-21): R12 (`cf_enriquecer_factura`, migración 20), **no** reprocesado.
Solo la factura 08012619; las otras 3 facturas del documento no se tocan.

**Antes (puertas):**

1. Commit de la 1.3.1 empujado a `origin/main` (puerta git) y fuera de la ventana de la noche (22:15).
2. READ_ONLY (`pruebas/auditoria_2bb/enriquecimiento_readonly.py preflight 08012619 <espejo> <salida>`):
   - 08012619 en `PENDIENTE_CONCILIAR`, sin claim; 0 locks, claims y `NORMALIZANDO`; flags apagados; tareas sin
     ejecutar en ese momento;
   - el PDF del espejo con el SHA registrado; extracción autorizada local con la 1.3.1 e identidad económica idéntica
     (número, fecha, total 12.867,73, CIF);
   - **payload exacto esperado:** 1 albarán (`08D50803`, 14-10-2026, base 7,10, total 7,42, `ENCARGO`, `CARGO`),
     **0 movimientos y 0 vencimientos**. Cualquier otra cosa → PARA. En particular, un vencimiento con importe NULL
     lo rellenaría R12 y dejaría de ser «solo la línea 08D50803»: Pio decide;
   - el albarán operacional 08D50803 (IdContador 294483, SAFA, 14/10, PUC 7,42) sin reserva de otra factura (R15).
3. Snapshot con huellas por fila (pre), repetido justo antes de ejecutar: idéntico o PARA.

**Ejecución:** `pruebas/auditoria_2az/enriquecer_una_vez.py`, **una** invocación, con la clave idempotente prevista en
el preflight. Sin reintento.

**Después (postcheck 2AX por fila):** solo cambian filas de 08012619: +1 `facturas_albaranes_extraidos` (08D50803) y
+1 evento `FACTURA_ENRIQUECIDA`. Las otras 3 facturas del documento, la cabecera, sus movimientos y vencimientos,
`cf_configuracion`, la operación y las reservas, idénticos. Cualquier otra fila → PARA.

**Efecto previsto (por cálculo, sin simular sobre producción):** líneas 12.861,09 + 7,42 y movimientos −0,76 =
12.867,75 frente a 12.867,73: diferencia documental −0,02 (dentro de la tolerancia). La conciliación de 08012619 iría
después, con el plan 2BP y su confirmación por tanda.

## 4. Fuera de alcance

- Volver a normalizar documentos ya persistidos: no se hace (la identidad no cambia; el camino es R12).
- 08016545: solo se anota (§2).
