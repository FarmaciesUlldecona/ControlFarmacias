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
  tiene autoridad productiva.
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
