# Reglas críticas

Actualizado: 2026-09-24.

## Seguridad y operación

- Farmatic es de solo lectura: nunca `INSERT`, `UPDATE`, `DELETE`, `MERGE`, DDL,
  `EXECUTE` con efectos laterales ni escrituras directas o indirectas.
- Supabase productivo, flags, workers, Task Scheduler y documentos reales requieren
  preflight, alcance explícito y confirmación de Pio.
- Solo PIO está autorizada. Una identidad de farmacia ausente, contradictoria o no
  demostrable bloquea la persistencia.
- Los nombres de archivo, rutas, hashes, carpetas y gold son metadatos técnicos; no
  prueban proveedor, farmacia, obligación económica ni sentido contable.
- Los valores documentales necesitan evidencia trazable. No se inventan importes,
  referencias, sentidos ni relaciones para completar una salida.
- Un movimiento solo es `CARGO` o `ABONO` con evidencia literal o estructural
  inequívoca. En otro caso conserva `sentido=null` y queda no evaluable donde
  corresponda.
- La consolidación solo fusiona cuando existe `MISMA_FACTURA_DEMOSTRADA`.
  Completitud, origen, orden o primera coincidencia no demuestran identidad.

## Extractores locales

- Todos los adaptadores registrados son habilitables para shadow, pero ninguno
  tiene autoridad productiva en el registro global
  `AUTORIDADES_EXTRACTORES_LOCALES`.
- Excepción acotada (Hito 2AP, 2026-09-24, `CONFIRMADO POR CÓDIGO` y
  `CONFIRMADO POR TEST`, sin ejecución productiva): el compositor manual
  `runtime_supabase/compositor_manual.py` concede autoridad solo a Alliance
  (`alliance-local`) mediante `AUTORIDAD_COMPOSITOR_MANUAL`, que exige puente
  multifactura certificado. Solo se usa con `ejecutar_una_manual()`; ningún
  scheduler ni la ruta automática lo referencian. Cualquier otro proveedor falla
  cerrado.
- LÍMITE CONOCIDO aceptado por Pio (Hito 2AQ, 2026-09-25): la omisión de una
  factura Alliance **entera** dentro de un PDF multifactura no es detectable por
  contenido. Alliance solo pagina por factura (`PAGINA 01 DE 03`) y no declara
  paginación de documento; `Hoja Z 6041` es el dato del Registro Mercantil.
  Evidencia: PDF real de 9 páginas con las páginas 8 y 9 retiradas (factura
  08011305 completa): las facturas 08011304 y 08011303 se autorizan y la omitida no
  deja rastro. No genera datos falsos: nada se inventa ni se persiste de la factura
  ausente; el efecto es una omisión. Una página faltante **dentro** de una factura sí
  se detecta (`factura_completa_demostrada=false` → inventario `REQUIERE_REVISION`,
  documento `PARCIAL`/`REVISION`). No se crea regla nueva ni se modifica
  `evaluar_completitud_local`. Control compensatorio requerido, `PENDIENTE` de hito
  propio y no implementado: detectar en conciliación albaranes Alliance sin factura
  asociada por periodo. Fijado por
  `test_limite_conocido_factura_alliance_entera_omitida`.
- Shadow conserva siempre la salida oficial; `adaptadores_productivos()` es un alias
  de compatibilidad y su nombre no concede autoridad.
- Solo Guimerà declara backend con OCR local. El resto usa PDFium nativo salvo que
  el contrato cambie y se certifique.
- SAFA no tiene extractor local propio y Beiersdorf está sin extractor
  implementado. `CONFIRMADO POR CÓDIGO`, 2026-09-24.

## Reglas confirmadas por proveedor

| Proveedor | Regla vigente confirmada |
|---|---|
| Alliance / Cencora | Conserva tablas y secciones documentales `CARGOS`/`ABONOS`, fiscalidad, vencimientos y relaciones 1:1 inequívocas sin fusionar objetos. `SERVICIO BASICO` y `CONDIC. COMERCIAL` son `CARGO` solo por decisión funcional explícita de Pio. Fuera de esas pruebas, el sentido queda indeterminado. |
| FEDEFARMA | `Total abonaments (consultar detalls)` se clasifica como `DEVOLUCION_MERCANCIA` sin derivar por ello el sentido. La cuota mensual de servicios cooperativos es `CONDICION_COOPERATIVA`; textos meramente registrales no crean movimientos. Conserva facturas internas segmentadas. |
| HEFAME | Declara controles documentales entre detalle, pedidos, servicios operativos, fiscalidad, total y vencimiento. Una diferencia solo produce resultado de control; no crea explicaciones ni movimientos. |
| COFARES | La elegibilidad local exige documento monopágina, segmentación determinista, filas completas y únicas, columnas inequívocas y evidencia integral. El sentido literal ausente no se infiere. El descuento por pronto pago sigue como gap funcional. |
| Guimerà | Dispone de adaptadores OCR actual e histórico; el OCR solo se reintenta ante `PENDIENTE_OCR`. El routing no usa filename ni hash. |
| DERMOFARM | Conserva evidencia y no inventa importes. La relación de abonos descontados en la primera factura del mes siguiente sigue pendiente de decisión funcional. |
| Suavinex | Conserva cuota IVA+RE agregada, vencimiento y punto verde documentados. Cualquier regla de albarán único debe ser explícita, nunca inferida. |
| Ecoceutics, Eports, Logista Pharma, L'Oréal, Moretti y Totalcare | Existen adaptadores locales basados en layouts certificados del corpus. Su presencia no autoriza generalizar a layouts no certificados ni inferir naturaleza o sentido solo por proveedor. |
| HPlus Consumo / Gas Casa / Pierre Fabre | Las clasificaciones y relaciones deben salir del contenido visible y de reglas aprobadas; el proveedor por sí solo no determina naturaleza, conciliación ni sentido. |

## Persistencia y conciliación

- Reglas aprobadas por Pio para la migración 17 (Hito 2AR, 2026-09-25;
  `CONFIRMADO POR TEST` en PostgreSQL 17 local, **NO desplegada**):
  - **R1 replay idempotente:** nunca deja claim, lock ni estado intermedio. Libera
    el claim del llamante, restaura `estado_lectura`/`estado_persistencia` al
    estado final de la ejecución original, registra
    `NORMALIZACION_REPLAY_IDEMPOTENTE` y no crea ni modifica facturas. Aplica a la
    RPC multifactura y a `cf_persistir_normalizacion`. Un fallo repetido con la
    misma clave y claim vigente cuenta como intento nuevo (clave derivada
    `:intento:<n>`); sin claim es retransmisión y no cambia nada.
  - **R2 proveedor no soportado:** clase `NO_SOPORTADO` → estado
    `PROVEEDOR_NO_SOPORTADO`, no reclamable, no cuenta como `ERROR` ni consume
    intentos. Solo vuelve a la cola con `cf_solicitar_reprocesado`.
  - **R3 errores persistentes:** `DEFECTO_DOCUMENTO`/`TRANSITORIO` incrementan
    `intentos_fallo_normalizacion`; por debajo del máximo → `ERROR` con
    `proximo_reintento_at` (1 h, 6 h); al alcanzar el máximo (3) → `REVISION`.
    Parámetros en `cf_configuracion` (`normalizacion_max_intentos`,
    `normalizacion_backoff`). El reprocesado explícito reinicia el contador.
  - **R4 ordering:** sin cambios. El selector ya excluye todo estado distinto de
    `PENDIENTE`/`ERROR` y los backoff futuros; la migración 17 no redefine el claim.
  - Clasificación de motivos: `runtime_supabase/clasificacion_fallos.py`; un motivo
    desconocido es `TRANSITORIO`, nunca `NO_SOPORTADO`.
- La RPC multifactura autorizada tiene siete parámetros, incluido
  `p_disparador`. La firma antigua de seis no está autorizada para `service_role`.
- Los disparadores permitidos son `AUTOMATICO`, `REPROCESADO` y
  `MANUAL_ONE_SHOT`.
- Una diferencia documental nunca genera automáticamente movimientos, sentidos,
  categorías ni explicaciones.
- Las relaciones con Farmatic conservan el identificador literal de proveedor; no
  se coacciona a número ni se normaliza destructivamente.
- En conciliación, SAFA, Alliance y Cencora pueden canonicalizarse dentro del grupo
  funcional autorizado. `CONFIRMADO POR CÓDIGO` y `CONFIRMADO POR TEST`,
  2026-09-24. Esto no crea un extractor SAFA: **extracción ≠ conciliación**.

## Capacidades no implementadas

- Conciliación bancaria: **NO IMPLEMENTADA**.
- Norma 43: **NO IMPLEMENTADA**.
- Telegram: **NO IMPLEMENTADO**.
- Interfaz web: **NO IMPLEMENTADA**.
- Beiersdorf: **SIN EXTRACTOR IMPLEMENTADO**.

Estado a 2026-09-24: `NO ENCONTRADO` en el código vigente. No se presentan como
módulos parciales.

## Pruebas

- Pytest debe usar directorios temporales mediante `CONTROLFARMACIAS_LOG_DIR` y
  `CONTROLFARMACIAS_DATA_DIR`.
- Los tests no pueden conectarse a Farmatic/Supabase reales ni escribir en
  `logs/` o `data/` productivos.
- Una suite verde demuestra solo lo cubierto por sus tests; no amplía autoridad
  productiva ni resuelve reglas funcionales pendientes.
