# Normalizador de Facturas V2 — especificación funcional y técnica cerrada

## 1. Propósito y condición de verdad

El Normalizador de Facturas V2 transforma un PDF en una **verdad documental normalizada, fiable, trazable y equivalente al segundo gold validado manualmente**. Su responsabilidad termina en lo que el propio documento permite demostrar. La conciliación con albaranes de Farmatic es un proceso posterior e independiente.

Esta especificación fija el contrato conceptual para una implementación futura. No es un schema productivo, un prompt ni una implementación.

## 2. Alcance

Incluye:

- lectura de uno o varios documentos factura contenidos en un PDF;
- extracción y normalización de identidad, páginas, proveedor, destinatario, fechas, totales, fiscalidad, vencimientos, albaranes o documentos de entrega explícitos, movimientos y referencias;
- validaciones deterministas generales, económicas, fiscales, de completitud y duplicidad;
- reglas pequeñas, versionadas y justificadas por proveedor o formato;
- segunda lectura selectiva cuando exista evidencia objetiva de lectura estructural incompleta;
- deduplicación, consolidación, incidencias, discrepancias, estado final y trazabilidad de cada dato y decisión.

## 3. Fuera de alcance

Quedan expresamente fuera:

- consultar, escribir o conciliar contra Farmatic, SQL Server o Supabase;
- asociar albaranes documentales con albaranes internos, códigos Q u otras claves operativas;
- usar nombres de archivo, históricos, bases de datos o resultados gold como fuente de datos de una factura;
- corregir números, fechas, identificadores o importes para hacerlos coincidir con otra fuente o cuadrar aritméticamente;
- crear motores independientes por proveedor salvo necesidad futura demostrada y aprobada;
- modificar modelos, prompts, schemas de extracción, proveedores de IA o estrategia aprobada;
- decidir contabilidad, contabilizar, pagar o validar la conciliación comercial posterior.

## 4. Arquitectura y flujo aprobado

Flujo nominal y único:

```text
PDF
  -> Luna V2
  -> validaciones deterministas
  -> reglas pequeñas por proveedor/formato
  -> [solo si hay evidencia objetiva de lectura estructural incompleta]
       Google Document AI Splitter
       -> Luna V2 por segmentos
       -> consolidación y deduplicación deterministas
  -> validación final
  -> DOCUMENTO normalizado
```

El Splitter no es universal, no mejora por definición una extracción y nunca sustituye las validaciones. Sus resultados son candidatos: solo se incorporan si tienen soporte literal localizable, superan los mismos controles y no introducen una contradicción no resuelta.

## 5. Principios innegociables

1. **Cero invenciones.** Todo valor necesita evidencia visible y localizable en el PDF.
2. **Ausencia explícita.** Un escalar no demostrable es `null`; una colección sin elementos demostrables es `[]`.
3. **El nombre del archivo no es evidencia.** Solo sirve como `archivo_origen` técnico.
4. **Literalidad.** Se conserva el literal fuente. Una forma normalizada auxiliar no puede corregirlo, completarlo ni reemplazarlo.
5. **No forzar cuadre.** Las diferencias se conservan y registran; no se alteran filas, albaranes, impuestos ni totales.
6. **Semántica estricta.** `Delivery`, `Pedido`, `PO` u `Order` son referencias, no albaranes, salvo identificación explícita como albarán o documento de entrega.
7. **Generalidad controlada.** Hay un normalizador general, configuración versionada y reglas pequeñas. Un proveedor no obtiene un motor propio sin necesidad demostrada.
8. **El gold evalúa, no informa la extracción.** Los artefactos congelados justifican esta especificación y futuros tests; no se consultan ni se usan durante producción.

## 6. Convenciones de tipos y representación

| Tipo conceptual | Representación y regla |
|---|---|
| `Texto` | Cadena Unicode. Se conserva la grafía visible; no se completa desde el archivo ni desde históricos. |
| `Entero` | Entero sin decimales. |
| `Decimal` | Decimal de punto fijo, nunca binario flotante para validar importes. Conserva el valor visible y su precisión relevante. |
| `Booleano` | `true` o `false`; no admite `null` cuando la regla lo determina. |
| `FechaDocumental` | Objeto `{literal: Texto, iso: Texto|null}`. `iso` usa `AAAA-MM-DD` solo si día, mes y año son inequívocos; `literal` nunca se altera. |
| `Evidencia` | Objeto `{pagina: Entero, segmento_id: Texto|null, literal: Texto, ubicacion: Objeto|null}`. `ubicacion` puede contener coordenadas del motor; la página y el literal son obligatorios para todo dato documental no nulo. |
| `ValorDocumentado<T>` | Objeto `{valor: T, literal: Texto, evidencia: Evidencia[]}` para valores escalares extraídos. Al menos una evidencia. |
| `Lista<T>` | Array ordenado; vacío se representa como `[]`, nunca `null`. |
| `Mapa` | Objeto de claves conocidas; extensiones técnicas deben estar versionadas y no cambiar semántica funcional. |

Las tablas siguientes indican `N` (no nulo) o `S` (nullable). `1`, `0..1` y `0..n` expresan cardinalidad. Los identificadores técnicos se generan de forma determinista a partir del contenido y contexto estable; no son evidencia documental.

## 7. Schema conceptual

### 7.1 DOCUMENTO

| Campo | Tipo | Nulable | Cardinalidad | Significado e invariantes |
|---|---|---:|---:|---|
| `documento_id` | `Texto` | N | 1 | Identificador técnico estable e idempotente del PDF; no deriva solo del nombre. |
| `archivo_origen` | `Texto` | N | 1 | Nombre o ruta lógica de entrada para trazabilidad; jamás evidencia funcional. |
| `tipo_contenido` | enum | N | 1 | `PDF_NATIVO`, `PDF_IMAGEN`, `PDF_MIXTO` o `PDF_NO_LEIBLE`; clasificación técnica, no tipo de factura. |
| `numero_paginas` | `Entero` | S | 0..1 | Páginas verificadas del PDF. `null` si el PDF no pudo abrirse. Si existe, es mayor que cero. |
| `estado_documento` | `EstadoValidacion` | N | 1 | Agregación determinista de estados de lectura/facturas según §12. |
| `estrategia_lectura` | `EstrategiaLectura` | N | 1 | Estrategia efectivamente ejecutada, no la recomendada. |
| `facturas` | `Lista<FACTURA>` | N | 0..n | Facturas documentales únicas. Es `[]` ante fallo o ausencia demostrada; el estado explica el caso. |
| `metadata_tecnica` | `MetadataTecnica` | N | 1 | Versiones, tiempos, intentos, segmentos, configuración y trazas sin credenciales ni texto innecesario. |

**Invariantes de DOCUMENTO:** las páginas de cada factura están dentro de `1..numero_paginas`; `pagina_inicio <= pagina_fin`; cada factura pertenece al PDF; una portada/resumen descartada no aparece en `facturas`; una lectura segmentada conserva el vínculo con páginas originales.

### 7.2 FACTURA

| Campo | Tipo | Nulable | Cardinalidad | Significado e invariantes |
|---|---|---:|---:|---|
| `factura_id` | `Texto` | N | 1 | ID técnico determinista. La clave funcional preferida es proveedor normalizado + número literal. |
| `tipo_documento` | `ValorDocumentado<Texto>` | S | 0..1 | Literal explícito (`Factura`, `Factura rectificativa`, etc.); no se infiere un tipo ausente. |
| `naturaleza_principal` | `NaturalezaPrincipal` | N | 1 | Clasificación funcional definida en §9. |
| `estado_validacion` | `EstadoValidacion` | N | 1 | Resultado y suficiencia de la factura. |
| `requiere_conciliacion_albaranes` | `Booleano` | N | 1 | Regla de negocio documental, no resultado de conciliación. |
| `pagina_inicio` | `Entero` | N | 1 | Primera página original que sustenta la factura. |
| `pagina_fin` | `Entero` | N | 1 | Última página original que sustenta la factura. |
| `proveedor` | `Tercero` | S | 0..1 | Emisor visible y alias funcional auxiliar. El literal se conserva. |
| `numero_factura` | `ValorDocumentado<Texto>` | S | 0..1 | Identificador completo visible, incluidos prefijos, espacios y componentes significativos. |
| `fecha_factura` | `ValorDocumentado<FechaDocumental>` | S | 0..1 | Fecha de emisión explícita. |
| `destinatario` | `Tercero` | S | 0..1 | Destinatario visible; su ausencia o ilegibilidad se valida. |
| `totales` | `Totales` | N | 1 | Valores impresos; cada componente puede ser `null`. |
| `vencimientos` | `Lista<Vencimiento>` | N | 0..n | Solo vencimientos visibles. |
| `impuestos` | `Lista<TramoImpuesto>` | N | 0..n | Tramos impresos; no reconstruidos. |
| `albaranes` | `Lista<AlbaranDocumental>` | N | 0..n | Solo albaranes o documentos de entrega identificados explícitamente. |
| `movimientos_comerciales` | `Lista<MovimientoComercial>` | N | 0..n | Conceptos comerciales separados de albaranes e impuestos. |
| `forma_pago` | `FormaPago` | S | 0..1 | Medio/condición visible de pago, independiente de vencimientos. |
| `referencias_documentales` | `Lista<ReferenciaDocumental>` | N | 0..n | Delivery, pedido, PO, order y otras referencias no convertidas en albarán. |
| `discrepancias_documentales` | `Lista<DiscrepanciaDocumental>` | N | 0..n | Diferencias o ambigüedades conservadas. |
| `incidencias` | `Lista<Incidencia>` | N | 0..n | Problemas de extracción, suficiencia o técnica. |
| `validaciones` | `Lista<ResultadoValidacion>` | N | 1..n | Registro exhaustivo de controles ejecutados y no aplicables. |

### 7.3 Objetos anidados

| Objeto | Campos y reglas |
|---|---|
| `Tercero` | `nombre: ValorDocumentado<Texto>|null`, `nif: ValorDocumentado<Texto>|null`, `direccion: ValorDocumentado<Texto>|null`, `alias_funcional: Texto|null`. El alias nunca sustituye al nombre literal. |
| `Totales` | `moneda: ValorDocumentado<Texto>|null`, `base_imponible: ValorDocumentado<Decimal>|null`, `iva: ValorDocumentado<Decimal>|null`, `recargo_equivalencia: ValorDocumentado<Decimal>|null`, `otros: ValorDocumentado<Decimal>|null`, `total: ValorDocumentado<Decimal>|null`. `otros` solo si existe concepto totalizador visible; no absorbe diferencias. |
| `Vencimiento` | `orden: Entero`, `fecha: ValorDocumentado<FechaDocumental>|null`, `importe: ValorDocumentado<Decimal>|null`, `medio_pago: ValorDocumentado<Texto>|null`. Requiere al menos fecha o importe visible. |
| `TramoImpuesto` | `orden: Entero`, `descripcion_literal: ValorDocumentado<Texto>|null`, `base: ValorDocumentado<Decimal>|null`, `tipo_iva: ValorDocumentado<Decimal>|null`, `cuota_iva: ValorDocumentado<Decimal>|null`, `tipo_recargo_equivalencia: ValorDocumentado<Decimal>|null`, `cuota_recargo_equivalencia: ValorDocumentado<Decimal>|null`, `total_tramo: ValorDocumentado<Decimal>|null`. |
| `AlbaranDocumental` | `orden: Entero`, `fecha: ValorDocumentado<FechaDocumental>|null`, `numero: ValorDocumentado<Texto>`, `tipo_movimiento: Sentido`, `tipo_pedido: ValorDocumentado<Texto>|null`, `importe_base: ValorDocumentado<Decimal>|null`, `importe_total: ValorDocumentado<Decimal>|null`. `numero` exige identificación explícita como albarán/documento de entrega. |
| `MovimientoComercial` | `orden: Entero`, `tipo: TipoMovimiento`, `descripcion_literal: ValorDocumentado<Texto>`, `sentido: Sentido`, `base: ValorDocumentado<Decimal>|null`, `iva: ValorDocumentado<Decimal>|null`, `recargo_equivalencia: ValorDocumentado<Decimal>|null`, `importe: ValorDocumentado<Decimal>|null`. |
| `FormaPago` | `descripcion_literal: ValorDocumentado<Texto>`, `referencia: ValorDocumentado<Texto>|null`. No genera vencimientos. |
| `ReferenciaDocumental` | `orden: Entero`, `tipo: TipoReferencia`, `identificador: ValorDocumentado<Texto>`, `descripcion_literal: ValorDocumentado<Texto>|null`. Es independiente de `albaranes`. |
| `DiscrepanciaDocumental` | `tipo: TipoDiscrepancia`, `descripcion: Texto`, `importe_diferencia: Decimal|null`, `valores_implicados: Lista<ValorDocumentado<Decimal|Texto>>`, `material: Booleano`. Describe, no corrige. |
| `Incidencia` | `codigo: Texto`, `severidad: INFO|AVISO|ERROR`, `descripcion: Texto`, `paginas: Lista<Entero>`, `bloqueante: Booleano`, `evidencias: Lista<Evidencia>`. |
| `ResultadoValidacion` | `codigo: Texto`, `resultado: OK|FALLO|NO_APLICA|NO_EVALUABLE`, `descripcion: Texto`, `valores: Mapa`, `tolerancia_aplicada: Decimal|null`, `evidencias: Lista<Evidencia>`, `regla_version: Texto`. |
| `MetadataTecnica` | `version_normalizador: Texto`, `version_configuracion: Texto`, `lector_primario: Texto`, `intentos: Lista<IntentoLectura>`, `segmentos: Lista<Segmento>`, `huella_contenido: Texto|null`, `inicio: Texto`, `fin: Texto`, `duracion_ms: Entero`, `correlacion_id: Texto`. Sin secretos. |
| `IntentoLectura` | `orden`, `estrategia`, `estado_tecnico`, `motivo`, `paginas_o_segmentos`, `version_lector`, `duracion_ms`. Registra también fallos y descartes. |
| `Segmento` | `segmento_id`, `pagina_inicio`, `pagina_fin`, `origen: SPLITTER`, `estado`, y correspondencia inequívoca con páginas originales. |

## 8. Política de importes y signos

Los importes de `MovimientoComercial` y `AlbaranDocumental` se almacenan como **magnitudes no negativas** cuando el documento permite separar magnitud y sentido; `sentido` es siempre obligatorio y determina el efecto: `CARGO` suma y `ABONO` resta. Si el literal contiene signo, este se conserva en `literal`, pero `valor` contiene la magnitud. Un signo contrario al rótulo produce discrepancia/incidencia y no se resuelve por inferencia. Totales e impuestos conservan el valor y signo impresos porque no representan movimientos normalizados.

Para cálculos de control se usa `efecto(x) = +x` para `CARGO` y `-x` para `ABONO`. Nunca se cambia un importe para satisfacer una igualdad.

## 9. Enumeraciones

| Enum | Valores cerrados |
|---|---|
| `NaturalezaPrincipal` | `MERCANCIA`, `SERVICIOS`, `MIXTA`, `CONDICIONES_COMERCIALES` |
| `EstadoValidacion` | `VALIDADA`, `VALIDADA_CON_INCIDENCIAS`, `REQUIERE_SEGUNDA_LECTURA`, `REQUIERE_REVISION`, `ERROR_TECNICO` |
| `EstrategiaLectura` | `LUNA_V2`, `LUNA_V2_MAS_SPLITTER_SEGMENTADO` |
| `TipoReferencia` | `DELIVERY`, `PEDIDO`, `PO`, `ORDER`, `DOCUMENTO`, `OTRA` |
| `TipoDiscrepancia` | `CUADRE_FISCAL`, `CUADRE_ALBARANES`, `SUBTOTAL_NO_EXPLICADO`, `IDENTIFICADOR_AMBIGUO`, `OTRA` |
| `TipoMovimiento` | `RAPPEL`, `ABONO_COMERCIAL`, `DEVOLUCION_MERCANCIA`, `DESCUENTO`, `BONIFICACION`, `SERVICIO`, `CONDICION_COMERCIAL`, `OTRO` |
| `Sentido` | `ABONO`, `CARGO` |

`tipo_documento`, `tipo_pedido`, descripciones y rótulos no se fuerzan a una enumeración cuando el documento usa vocabulario propio; se conserva el literal.

## 10. Clasificación de naturaleza y conciliación

- `MERCANCIA`: predominan productos o entregas. Normalmente `requiere_conciliacion_albaranes=true`. La ausencia de albaranes visibles no autoriza inventarlos; puede generar incidencia o segunda lectura según señales objetivas.
- `SERVICIOS`: predominan prestaciones no entregas de mercancía. Normalmente `requiere_conciliacion_albaranes=false`, `albaranes=[]`, y la ausencia de albaranes no es incidencia.
- `MIXTA`: conviven mercancía y servicios materiales. Requiere conciliación si existe componente de mercancía conciliable; servicios y movimientos permanecen separados.
- `CONDICIONES_COMERCIALES`: factura o liquidación de condiciones, cargos o bonificaciones sin entrega conciliable. `requiere_conciliacion_albaranes=false` salvo evidencia explícita contraria que exigiría revisión de configuración aprobada.

La clasificación usa contenido visible, no proveedor ni nombre del fichero por sí solos.

## 11. Algoritmo determinista

1. Verificar apertura, tipo y páginas del PDF; crear trazabilidad técnica.
2. Ejecutar Luna V2 una vez sobre el documento conforme al presupuesto configurado.
3. Convertir cada candidato al schema conceptual, manteniendo literal y evidencia.
4. Aplicar reglas generales y luego reglas pequeñas de proveedor/formato versionadas.
5. Descartar portadas/resúmenes solo mediante la regla cerrada de §14.
6. Deduplicar candidatos según §18 y ejecutar todas las validaciones aplicables.
7. Evaluar en conjunto las señales de segunda lectura de §17. Si se satisfacen, marcar transitoriamente `REQUIERE_SEGUNDA_LECTURA` y registrar razones.
8. Si no se requiere segunda lectura, asignar el estado final por precedencia.
9. Si se requiere y hay presupuesto, ejecutar Splitter, Luna V2 por segmentos, consolidar y validar otra vez. Una fila segmentada sin evidencia inequívoca se rechaza.
10. Emitir `DOCUMENTO` con datos, controles, configuración y trazas. Ningún fallo elimina evidencia válida ya obtenida; su suficiencia queda reflejada en el estado.

## 12. Estados, precedencia y transiciones

Precedencia final, de mayor a menor gravedad:

1. `ERROR_TECNICO`: no se puede abrir/procesar el PDF o un fallo técnico impide producir un resultado evaluable. Un fallo del Splitter no convierte automáticamente en error técnico una primera lectura evaluable; se aplica la regla posterior indicada abajo.
2. `REQUIERE_REVISION`: tras todas las lecturas permitidas, faltan datos esenciales, existen conflictos no resolubles o la completitud/fiabilidad no alcanza el contrato.
3. `REQUIERE_SEGUNDA_LECTURA`: estado transitorio emitible solo si hay evidencia objetiva de incompletitud pero la segunda lectura no se ha ejecutado aún por límite técnico o presupuesto. Nunca equivale a validación.
4. `VALIDADA_CON_INCIDENCIAS`: la verdad documental es fiable y utilizable, pero conserva discrepancias o faltas no críticas y explícitas.
5. `VALIDADA`: datos suficientes y coherentes dentro de tolerancia, sin incidencias materiales.

Transiciones:

```text
lectura primaria correcta
  -> VALIDADA | VALIDADA_CON_INCIDENCIAS
  -> REQUIERE_SEGUNDA_LECTURA (si se cumplen criterios combinados)

REQUIERE_SEGUNDA_LECTURA
  -> VALIDADA | VALIDADA_CON_INCIDENCIAS (segunda lectura completa y validada)
  -> REQUIERE_REVISION (segunda lectura insuficiente, contradictoria o falla, existiendo primera lectura evaluable)
  -> ERROR_TECNICO (no existe resultado evaluable por fallo técnico global)
```

`estado_documento` es el peor estado final de sus facturas según la precedencia anterior. Si `facturas=[]`, será `ERROR_TECNICO` ante fallo técnico o `REQUIERE_REVISION` cuando el PDF sea legible pero no se pueda determinar con fiabilidad si contiene facturas. Todas las transiciones registran regla, señales, intento, resultado y evidencias.

## 13. Validaciones generales

Por cada factura se registran, como mínimo:

- proveedor visible y, si existe, NIF;
- número de factura completo;
- fecha de factura visible;
- total de factura visible;
- destinatario visible (nombre y demás datos que realmente aparezcan);
- rango de páginas válido y sin solapamientos contradictorios;
- coherencia de naturaleza y `requiere_conciliacion_albaranes`;
- duplicados dentro del PDF y, si el llamador aporta resultados del mismo contenido, idempotencia por huella;
- evidencia para todo valor no nulo;
- ausencia de uso del nombre del archivo como fuente.

Proveedor + número de factura es la clave funcional preferida. Fecha + importe solo apoyan el emparejamiento y jamás fusionan facturas con números distintos. Si proveedor o número faltan, no se fabrica clave documental: se mantiene ID técnico, se registra insuficiencia y se evalúa revisión.

## 14. Portadas, resúmenes y multifaktura

Una página sin número de factura no constituye una factura adicional cuando concurren **todas** estas condiciones:

1. es portada, resumen o aviso del mismo PDF y proveedor;
2. no muestra número de factura propio;
3. su total es exactamente, con la tolerancia configurada, la suma de facturas numeradas contenidas en el documento;
4. no contiene evidencia de una obligación fiscal independiente.

Se registra como elemento descartado en validaciones/metadata, con la suma comprobada. Si falta alguna condición, no se descarta por inferencia: queda en revisión.

## 15. Validaciones económicas y fiscales

La configuración versionada define moneda y `tolerancia_monetaria`. Para EUR el valor por defecto aprobado es **0,01 EUR**, coherente con el evaluador congelado. Una comparación aproxima cuando `abs(a-b) <= tolerancia_monetaria`. La tolerancia se registra en cada control y puede parametrizarse por moneda o formato mediante configuración aprobada, nunca cambiarse ad hoc para una factura.

Controles económicos:

- si están visibles, comprobar `base_imponible + iva + recargo_equivalencia + otros ≈ total`;
- comprobar subtotales documentales contra la suma con sentido de albaranes/movimientos solo cuando los conceptos sean comparables;
- una diferencia superior a tolerancia genera la discrepancia adecuada; no impide `VALIDADA_CON_INCIDENCIAS` si la identidad, los totales literales y la extracción siguen siendo fiables;
- no crear `otros`, movimientos ni albaranes para absorber una diferencia.

Controles fiscales por tramo:

- cuando base, tipo y cuota sean visibles, comparar `redondear_centimos(base × tipo / 100) ≈ cuota`;
- aplicar el mismo control al recargo de equivalencia;
- comparar suma de bases, cuotas IVA y cuotas RE de los tramos visibles con los totales impresos correspondientes;
- comparar, si existe, base + cuotas con total del tramo y total de factura;
- no reconstruir tramos omitidos, no redistribuir redondeos y no inferir tipos a partir de cuotas.

Un campo necesario no visible produce `NO_EVALUABLE`, no `OK`. Las diferencias fiscales se registran como `CUADRE_FISCAL` con ambos valores y diferencia.

## 16. Vencimientos

Solo se emiten vencimientos explícitamente visibles. Está prohibido obtenerlos del nombre del archivo, fechas históricas, condiciones habituales o cálculo desde la fecha de factura. La forma de pago no genera por sí misma fecha ni importe de vencimiento. Para Farmacia Guimerá 624 y 743 el resultado obligatorio es `vencimientos=[]`.

## 17. Segunda lectura selectiva con Splitter

### 17.1 Decisión determinista por señales combinadas

No existe un umbral numérico único universal. La activación requiere una regla versionada que combine contexto compatible y evidencias independientes. Las señales permitidas son:

- naturaleza `MERCANCIA` o `MIXTA` con componente de mercancía;
- tabla de entregas/albaranes multipágina;
- continuidad de tabla, repetición de cabecera o filas que cruzan páginas;
- cero o muy pocos albaranes extraídos frente a múltiples identificadores o rótulos visibles inequívocos;
- subtotal documental no explicado por las filas extraídas;
- alta presencia visible de referencias/filas `CARGO`, `ABONO` o `ALBARAN/ALBARÁN`;
- diferencia material entre subtotal y detalle sin movimientos visibles que la expliquen;
- proveedor/formato incluido en configuración versionada por mejora demostrada.

Reglas cerradas:

- `mercancía` por sí sola no activa Splitter;
- `proveedor` por sí solo no activa Splitter;
- una diferencia aritmética aislada puede pedir revisión, pero no demuestra incompletitud estructural;
- activación ordinaria exige al menos una señal estructural (tabla multipágina/continuidad/conteo visible incompatible) y una señal de resultado incompleto, o una regla proveedor+formato demostrada que codifique esa combinación;
- las señales cuentan candidatos para decidir releer, pero nunca crean registros.

Cada decisión guarda señales observadas, páginas, conteos, regla/configuración, motivo de activación o no activación y presupuesto disponible.

### 17.2 Presupuesto, límites y fallos

La configuración versionada fija, al menos: máximo de invocaciones de Splitter por PDF, máximo de segmentos, páginas por segmento, reintentos por operación, tiempo máximo y coste máximo. Al alcanzar un límite no se excede: si la segunda lectura era necesaria se conserva `REQUIERE_SEGUNDA_LECTURA`; si se intentó y no fue suficiente, `REQUIERE_REVISION`.

Si Splitter o Luna por segmentos falla y la lectura primaria es evaluable pero objetivamente incompleta, el resultado es `REQUIERE_REVISION`, con el fallo trazado. Si el fallo impide cualquier resultado evaluable, es `ERROR_TECNICO`. No se oculta el intento ni se degrada silenciosamente a `VALIDADA`.

### 17.3 Consolidación posterior

La segunda lectura conserva páginas originales, orden y literal. Se admiten filas nuevas solo con evidencia explícita. Ante versiones idénticas se conserva una sola; ante versiones contradictorias del mismo identificador no se elige por conveniencia aritmética: se conserva el conflicto como incidencia y se marca revisión cuando afecte a fiabilidad.

## 18. Deduplicación

1. Facturas: proveedor funcional normalizado + número completo exacto es clave preferida. Alias aprobados pueden normalizar proveedor sin cambiar el literal.
2. Fecha e importe sirven para confirmar, detectar portada-resumen o señalar conflicto; no sustituyen un número ni fusionan números distintos.
3. Albaranes: dentro de una factura, se deduplican por número literal completo y, cuando sea necesario, fecha/tipo/orden visible. Repeticiones documentales que representen movimientos distintos se conservan.
4. Identificadores compuestos se comparan completos. Quitar `P`, `PA`, `RE`, espacios o prefijos no es deduplicación.
5. Primaria y segmentos: candidatos con la misma evidencia/identidad se unen sin perder procedencia; diferencias se registran.
6. Ejecutar dos veces con mismo PDF, configuración y versiones produce el mismo contenido funcional e IDs.

## 19. Movimientos comerciales

Los movimientos no son albaranes ni referencias. Se usa el tipo más específico demostrado por el literal y contexto; si no es posible, `OTRO`. `ABO/DEVO` no equivale automáticamente a `RAPPEL`. La descripción literal es obligatoria. Bases, IVA, RE e importe solo se rellenan cuando estén asociados visiblemente al concepto.

Una bonificación o devolución conserva su magnitud positiva y `sentido=ABONO`; un servicio o cargo conserva magnitud positiva y `sentido=CARGO`. Conceptos sin importe asociado conservan `null`. Un movimiento nunca se inventa para explicar una diferencia.

## 20. Referencias documentales

Las referencias se extraen en colección independiente. `DELIVERY`, `PEDIDO`, `PO`, `ORDER` o `DOCUMENTO` no entran en `albaranes` sin rótulo inequívoco de albarán/documento de entrega. Una misma cadena no se duplica como referencia y albarán salvo que el PDF le otorgue explícitamente ambas funciones; el caso se traza.

## 21. Discrepancias e incidencias

- `CUADRE_FISCAL`: fórmulas o sumas fiscales fuera de tolerancia.
- `CUADRE_ALBARANES`: suma de albaranes comparables distinta del subtotal/total documental.
- `SUBTOTAL_NO_EXPLICADO`: diferencia material que no corresponde a movimientos visibles.
- `IDENTIFICADOR_AMBIGUO`: literal incompleto, compuesto o con interpretaciones no resolubles.
- `OTRA`: discrepancia demostrada no cubierta.

`material` indica si la diferencia afecta a fiabilidad/uso, no si debe corregirse. `VALIDADA_CON_INCIDENCIAS` está permitido cuando los valores documentales son fiables y la discrepancia no impide representarlos. Una falta crítica o conflicto no resoluble conduce a `REQUIERE_REVISION`.

## 22. Reglas pequeñas por proveedor y casos aprobados

### 22.1 Alliance / Cencora

- `CENCORA`, `AH`, `ALLIANCE` y `ALLIANCE HEALTHCARE` identifican el mismo proveedor funcional para clave/deduplicación; se conserva siempre el nombre literal visible.
- El destinatario `PUIG SALOMON PIUS` se conserva literal, sin corregirlo.
- `RAPPEL GenerAH`, `ABONOS CLUBS`, `SERVICIO BASICO` y `SERV.PLATAF.360` son movimientos/conceptos comerciales, no albaranes conciliables.
- En 08009277: `08P10588` corresponde a `ABONOS CLUBS`, `08P10623` a `RAPPEL GenerAH` y `08Z34777` a `SERV.PLATAF.360`; se excluyen de `albaranes` y se conservan como movimientos con su literal/evidencia.
- Baseline B perdió 162 registros de detalle de 08009277; C recuperó 162/162. Este patrón justifica Splitter selectivo para el formato Alliance denso cuando concurran las señales de §17.
- En 08009278 se conserva total 3824,59 y suma de albaranes 3824,61; en 08009279, total 141,01 y suma 141,03. En ambos se registra `CUADRE_ALBARANES` por 0,02 EUR y no se altera albarán alguno.

### 22.2 FEDEFARMA

- Identificadores como `P PA 2620-2173388` y `P RE 2605-0221864` se conservan completos. No se reducen a su número base.
- Se separan albaranes, `abonaments`, `Bonificacio pagament inmediat` y `Condicio Operativa` según su semántica visible.
- La portada sin número por 409,58 no es cuarta factura: es exactamente 19,96 + 81,07 + 308,55 y cumple §14.
- `SI26-04567` y `VN26-0016742` son `SERVICIOS`, no requieren conciliación y tienen `albaranes=[]` salvo evidencia explícita contraria.
- Los cinco fallos atribuidos a FEDEFARMA en B son representación de claves compuestas, no omisión de lectura. No activan Splitter por ese motivo; se resuelven conservando el identificador completo.

### 22.3 HEFAME

- Separar albaranes, `ABO/DEVO`, `APROAFA` y `Servicios Operativos`.
- `ABO/DEVO` no se mapea automáticamente a rappel; su tipo se determina solo por rótulo/contexto demostrable, o `OTRO`.
- Para 0563820041 se conservan: 12 documentos; `ABO/DEVO` 116,32 con sentido `ABONO`; `APROAFA` 0,26 con sentido `CARGO`; subtotal 484,64; `Servicios Operativos` 110,00; base fiscal 594,64; total 677,99; y diferencia no explicada 80,00.
- No se crea una compensación por 80,00. Se registra `SUBTOTAL_NO_EXPLICADO`; `VALIDADA_CON_INCIDENCIAS` es válido si el resto es fiable.

### 22.4 COFARES

- 5450053457 es `MERCANCIA`, requiere conciliación, conserva albaranes y separa devoluciones, `Serv Integral Distribucion` y `Domiciliacion bancaria` como movimientos/conceptos.
- 5460017198 es `CONDICIONES_COMERCIALES`, no requiere conciliación y conserva CIF `A80904576`.
- En 5460017198: `Servicio Logistico` tiene coste 115,00; `Cofares Directo` muestra 409,11 como volumen/base y 6,95 como coste; `Cargo Parafarmacia` conserva su desglose. Está prohibido interpretar 409,11 como coste.

### 22.5 L'ORÉAL

- `Delivery 504918055` es `ReferenciaDocumental(tipo=DELIVERY)`, no albarán.
- Si no hay número explícito de albarán/documento de entrega, `albaranes=[]`, aunque la factura de producto sea `MERCANCIA` y `requiere_conciliacion_albaranes=true`.
- PO y document number permanecen como referencias independientes según su rótulo.

### 22.6 MORETTI

- `005657AV26` y `005898AV26` se conservan como notas/documentos de entrega según el PDF y, por ello, como `AlbaranDocumental` con su tipo literal.
- El normalizador no añade números de Farmatic. La futura asociación uno-a-varios y los códigos Q pertenecen al conciliador posterior.

### 22.7 Farmacia Guimerá

- Para facturas 624 y 743, `vencimientos=[]` porque no hay vencimientos documentales demostrables.
- Son mercancía y pueden requerir conciliación, pero no se infieren albaranes ni vencimientos.

### 22.8 ECOCEUTICS / HYGIE31

- FR00263663 es `SERVICIOS`, `requiere_conciliacion_albaranes=false` y `albaranes=[]`; la ausencia no es incidencia.
- FR00263826 es `MERCANCIA`, `requiere_conciliacion_albaranes=true`.
- Su albarán/documento de entrega explícito es `2200656272`, fecha literal 03/07/2026. Sus importes individuales son `null` si el documento no los asocia explícitamente; no se distribuye el total.

## 23. Evidencia experimental y trazabilidad

Artefactos autorizados como evidencia congelada, nunca como entrada productiva:

- Baseline A: commit `9b33254`; resultados en `pruebas/facturas/resultados/benchmark_2o_gold_luna/`.
- Segundo gold manual: `pruebas/facturas/gold_standard/`.
- Baseline B (Luna V2): `pruebas/facturas/resultados/benchmark_2o_gold_luna_v2/`.
- Baseline C (Google Splitter + Luna V2): `pruebas/facturas/resultados/benchmark_2o_gold_google_splitter_luna_v2/`.
- Comparativa A/B/C: `pruebas/facturas/resultados/comparativa_2o_gold_a_b_c/`.
- Análisis forense B: `pruebas/facturas/resultados/analisis_errores_baseline_b/`.
- B, C, comparativa y análisis quedaron congelados en commit `05d793d33400b289106276f5e505aa3ab233566d`.

Resultado relevante: B tuvo 337 albaranes gold, 170 correctos y 167 ausentes. La distribución fue Alliance 08009277 = 162, FEDEFARMA = 5, resto = 0. C recuperó 162/162 de Alliance. Los cinco FEDEFARMA eran identificadores compuestos representados sin prefijo completo, no omisiones. La conclusión cerrada es Splitter selectivo para Alliance densa con señales objetivas, y no activación FEDEFARMA por ese error de representación.

## 24. Frontera con Farmatic y futuro conciliador

La salida de este componente es `factura_normalizada`: verdad documental, no verdad operativa. Un conciliador futuro recibirá:

```text
factura_normalizada + albaranes_Farmatic_solo_lectura -> asociaciones posteriores
```

Ese conciliador podrá tratar relaciones uno-a-varios, códigos internos o diferencias entre documentos y sistema. No puede retroescribir ni alterar la verdad documental. Esta V2 no accede a Farmatic y no implementa ninguna asociación.

## 25. Requisitos no funcionales

- **Determinismo:** mismas entradas, versiones y configuración producen igual contenido funcional, decisiones y orden.
- **Auditabilidad:** todo valor no nulo enlaza con literal, página y lectura; toda regla/validación indica versión y resultado.
- **Idempotencia:** reintentos no duplican facturas, albaranes, movimientos ni referencias.
- **Observabilidad:** se registran correlación, tiempos, intentos, estados, señales de Splitter, segmentos y métricas de completitud; nunca credenciales.
- **Seguridad y privacidad:** mínimo dato necesario, cifrado y controles de acceso en la implementación futura, sin secretos en logs ni artefactos; no se envía a servicios no aprobados.
- **Configuración versionada:** alias, reglas pequeñas, tolerancias, límites y formatos tienen versión inmutable por ejecución. Todo cambio exige revisión y regresión contra evidencia congelada.
- **Tolerancia a fallos:** reintentos limitados, resultado parcial trazado y estados según §12; no hay degradación silenciosa.
- **Cero dependencia del gold en ejecución:** tests y evaluación están separados del pipeline productivo.
- **Compatibilidad decimal:** cálculos con decimal exacto y redondeo explícito a céntimos solo para validar; se conservan los valores impresos.

## 26. Criterios de aceptación de una implementación futura

1. Produce exactamente el contrato conceptual y nulabilidad aquí definidos, sin usar gold, nombre de archivo, Farmatic o históricos como evidencia.
2. Cada campo no nulo dispone de literal y página; valores no demostrables son `null` o `[]`.
3. Implementa los cinco estados, su precedencia y transiciones, incluidos fallo y límite de segunda lectura.
4. Ejecuta y registra controles generales, económicos, fiscales, duplicados, páginas, destinatario y evidencia.
5. Usa 0,01 EUR por defecto para validación EUR y registra configuración; no fuerza cuadre.
6. Distingue albaranes, movimientos y referencias con las enumeraciones y política de signo definidas.
7. Descarta la portada FEDEFARMA solo por la regla conjunta cerrada y conserva identificadores compuestos completos.
8. Activa Splitter solo por criterios combinados trazables; recupera el detalle Alliance denso sin convertirlo en regla universal ni introducir identificadores no soportados.
9. Cumple todos los resultados esperados de §27 y no regresa los demás casos del segundo gold.
10. Es idempotente, determinista, observable, sin secretos, con configuración versionada y pruebas de fallo/límites.
11. No consulta ni implementa conciliación con Farmatic.
12. Una evaluación ciega confirma cero invenciones como prioridad y equivalencia funcional con el segundo gold manual.

## 27. Casos de prueba conceptuales trazados

| ID | Evidencia/caso | Estímulo | Resultado obligatorio |
|---|---|---|---|
| `CT-ALL-001` | Alliance 08009277 | Luna primaria omite detalle en tabla densa multipágina con continuidad y múltiples señales | `REQUIERE_SEGUNDA_LECTURA`; Splitter selectivo; recuperar 162/162 filas demostrables; separar 08P10588, 08P10623 y 08Z34777 como movimientos, no albaranes. |
| `CT-ALL-002` | Alliance 08009278 | Total 3824,59; suma filas 3824,61 | Conservar ambos; `CUADRE_ALBARANES=0,02`; no alterar filas; estado admisible `VALIDADA_CON_INCIDENCIAS`. |
| `CT-ALL-003` | Alliance 08009279 | Total 141,01; suma filas 141,03 | Igual política, diferencia 0,02. |
| `CT-FED-001` | FEDEFARMA multifaktura | Portada 409,58 y tres facturas 19,96/81,07/308,55 | Tres facturas, no cuatro; descarte trazado por suma exacta y ausencia de número. |
| `CT-FED-002` | FEDEFARMA | `P PA 2620-2173388`, `P RE 2605-0221864` y equivalentes | Identificadores completos; sin activación Splitter por pérdida de prefijo; abonaments/bonificación/condición separados. |
| `CT-FED-003` | SI26-04567 y VN26-0016742 | Facturas de servicios | `SERVICIOS`, no conciliación, `albaranes=[]`, sin incidencia por ausencia. |
| `CT-HEF-001` | HEFAME 0563820041 | 12 documentos y desglose aprobado | Conservar 12; ABO/DEVO ABONO 116,32; APROAFA CARGO 0,26; servicio 110,00; subtotal 484,64; base 594,64; total 677,99; discrepancia 80,00 sin compensación inventada. |
| `CT-COF-001` | Cofares 5450053457 | Mercancía con devoluciones y servicios | Conservar albaranes; movimientos separados; requiere conciliación. |
| `CT-COF-002` | Cofares 5460017198 | Condiciones comerciales | Sin conciliación; CIF A80904576; Servicio Logístico coste 115,00; Cofares Directo volumen/base 409,11 y coste 6,95; desglose de Cargo Parafarmacia. |
| `CT-LOR-001` | L'Oréal 3401124788 | Delivery 504918055 sin albarán explícito | Referencia `DELIVERY`; `albaranes=[]`; mercancía sigue requiriendo conciliación. |
| `CT-MOR-001` | Moretti 003463FV26 | Notas 005657AV26 y 005898AV26 | Dos documentos de entrega conservados; ninguna clave Farmatic/Q añadida. |
| `CT-GUI-001` | Guimerá 624 y 743 | No hay vencimiento visible | `vencimientos=[]`; no calcular por nombre/fecha/histórico. |
| `CT-ECO-001` | FR00263663 | Servicio | Sin conciliación, `albaranes=[]`, ausencia no incidente. |
| `CT-ECO-002` | FR00263826 | Mercancía y referencia explícita | Conciliación requerida; albarán 2200656272 de 03/07/2026; importes individuales `null`. |
| `CT-GEN-001` | PDF con Delivery/Pedido/PO/Order | Referencias sin rótulo de albarán | Solo `referencias_documentales`; no albaranes. |
| `CT-GEN-002` | PDF con dato ausente | Archivo/histórico sugiere valor | `null`/`[]`; no usar sugerencia; evidencia obligatoria. |
| `CT-GEN-003` | Fallo Splitter con primaria incompleta | Segunda lectura necesaria y primaria evaluable | `REQUIERE_REVISION`, fallo e intentos trazados; nunca validación silenciosa. |
| `CT-GEN-004` | Mismo PDF/configuración dos veces | Reejecución | Mismo contenido, IDs y orden; sin duplicados. |

## 28. Decisiones cerradas

- El producto es verdad documental; Farmatic se concilia después.
- Luna V2 es lectura primaria; Splitter + Luna V2 segmentada es segunda lectura selectiva.
- Splitter exige evidencia objetiva combinada y trazabilidad; no hay activación universal ni umbral único arbitrario.
- Cero invenciones prevalece sobre cobertura y cuadre.
- Ausencia es `null` o `[]`; archivo e históricos no son evidencia.
- Se conservan literales, identificadores compuestos y discrepancias.
- Albaranes, movimientos y referencias son colecciones semánticamente independientes.
- Magnitud positiva + sentido obligatorio es la política de movimientos y albaranes.
- Proveedor + número completo es la clave preferida; fecha + importe solo apoyan.
- Tolerancia EUR por defecto: 0,01; versionada y registrada.
- Normalizador general + configuración + reglas pequeñas; sin motores por proveedor no justificados.

## Movimientos comerciales y sentido nullable

Desde el contrato `normalizador-v2.4-luna-1`, albaranes y movimientos documentados pueden conservar `sentido = null`. La descripción o categoría de un concepto no demuestra por sí sola CARGO o ABONO. Tampoco se deriva sentido por signo, proveedor, identificador, prefijo, nombre de archivo, DIRECT, posición u orden.

Un movimiento con descripción demostrable no se descarta por carecer de sentido. Conserva `descripcion_literal`, `tipo`, importes y evidencia. `tipo` representa una categoría conceptual y no un sentido económico. Cuando el sentido no está documentado se añade `SENTIDO_NO_DOCUMENTADO`, no bloqueante, y cualquier control dependiente queda `NO_EVALUABLE`.

Para análisis históricos futuros se separan `CARGOS_CONFIRMADOS`, `ABONOS_CONFIRMADOS` y `SENTIDO_INDETERMINADO`; estos últimos nunca se agregan automáticamente a los dos primeros. La salida canónica usa `sentido`; el alias histórico de entrada `tipo_movimiento` se mantiene para `AlbaranDocumental`.

## 29. Cuestiones explícitamente fuera de alcance

No quedan decisiones funcionales abiertas necesarias para implementar este contrato. Cualquier elección futura sobre modelos/prompts, schema productivo físico, servicio de persistencia, infraestructura, nuevas tolerancias, nuevos proveedores, excepciones contables, acceso a Farmatic, algoritmo de conciliación, relaciones uno-a-varios o códigos Q requiere una tarea y aprobación separadas. Ninguna se resuelve por inferencia en esta especificación.
