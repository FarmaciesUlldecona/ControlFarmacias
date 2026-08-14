# Inventario del normalizador actual para V2

**Paso 1 · diagnóstico local y estático · 2026-08-14**  
**HEAD inspeccionado:** `cdf3bd9fb71e3b7ff8ca691296c6b6fd4af7446d`  
**Estado del Orquestador:** `COMPLETADO`  
**Única escritura de la tarea:** este archivo.

## 1. Resumen ejecutivo

El repositorio no contiene un único «normalizador actual». Contiene cuatro ramas que hoy no están integradas extremo a extremo:

1. Una entrada productiva (`importar_facturas_drive.py`) localiza PDF, deduplica por hash y registra el documento en Supabase con `estado_lectura=PENDIENTE`; declara expresamente que no ejecuta IA ni crea facturas económicas (`src/facturas/importar_facturas_drive.py:768-798`, `993-1003`).
2. Un contrato genérico de motor y un motor simulado (`motores/base.py`, `motores/simulado.py`) producen las dataclasses históricas de `src/models/factura.py`, pero ningún motor real implementa esa interfaz.
3. Normalizadores deterministas (`normalizadores/`) consumen JSON ya extraído por Luna y, en Alliance/FEDEFARMA, una segunda transcripción literal. Producen `resultado_normalizado`, incidencias separadas y `validaciones_monetarias`; sus wrappers son runners de archivos de prueba, no una entrada productiva.
4. Runners experimentales independientes llaman OpenAI/Luna, Google Document AI o Azure, guardan respuestas y benchmarks. Baseline B y Google Splitter + Luna V2 son experimentos congelados, no componentes productivos.

Se censaron **662 archivos relevantes**: 66 archivos de código/configuración/especificación/tests y 596 archivos del corpus y resultados (se excluyen 4 `.pyc`). Clasificación exacta: **REUTILIZAR 3, ADAPTAR 20, SUSTITUIR 0, DEPRECAR 1, SOLO_TEST 52, SOLO_EXPERIMENTO 586**. La ausencia de `SUSTITUIR` significa que el diagnóstico recomienda crear el contrato V2 nuevo y adaptar piezas útiles; no que el sistema actual ya sea compatible.

Conclusiones principales:

- `comun.py`, `documento.py`, `ConfiguracionProveedor`, los normalizadores generalizados y las pruebas deterministas contienen lógica valiosa, pero sus formas de datos y estados son parciales respecto de V2.
- Baseline B es **reutilizable solo como base experimental de lectura literal** (PDF, schema estricto, multifaktura, límites, costes, trazas). No es el contrato V2 de producción: su `naturaleza_principal` modela CARGO/ABONO, mientras V2 modela MERCANCIA/SERVICIOS/MIXTA/CONDICIONES_COMERCIALES, y faltan evidencia, estado, validaciones, referencias e incidencias.
- El Splitter tiene una pieza reutilizable selectivamente: validación de segmentos contiguos y división física con `PdfReader/PdfWriter`. La selección/configuración del processor y el runner combinado siguen siendo experimentales.
- Azure subsiste solo en scripts y resultados experimentales; no hay importadores estáticos ni implementación del contrato `MotorExtraccionFacturas`.
- Se localizaron reglas/cobertura nominal de Alliance/Cencora, Dermofarm, Suavinex, FEDEFARMA, Hygie31/Ecoceutics, Guimerá, Pierre Fabre y Endesa. HEFAME, Cofares, L'Oréal, Moretti, Logista Pharma, Eports y Totalcare aparecen en gold/benchmarks, pero no tienen normalizador o configuración propia actual.
- No apareció una decisión de negocio nueva necesaria para cerrar este inventario. Las contradicciones halladas son técnicas y la especificación congelada permite resolverlas en un paso futuro.

## 2. Alcance, método y criterio de inclusión

Inspección exclusivamente local y estática. Se usaron `git rev-parse HEAD`, `git status --short`, `rg --files`, `rg -n`, `Get-Content`, `Get-ChildItem`, `Group-Object` y `Measure-Object`. No se importaron módulos Python, no se ejecutó pytest ni runner alguno, no se abrieron PDF con librerías y no se inició ningún proceso o llamada externa.

Se incluyó un archivo cuando cumple al menos uno de estos criterios:

- participa en localizar, registrar, extraer, dividir, normalizar, validar, representar o evaluar facturas;
- define configuración, schema, prompt o persistencia directamente usada por esos flujos;
- es test, documento fuente, gold, baseline o resultado congelado de dichos componentes;
- documenta la especificación V2 que sirve como única referencia comparativa.

Se excluyó ruido transitivo no específico (exploradores SQL, sincronización general de albaranes, documentación Farmatic no consumida por el normalizador), entornos, logs, cachés y 4 `.pyc`. `src/utils/logger.py` y `src/supabase_client/conexion_supabase.py` sí se incluyen por ser dependencias directas de la entrada productiva. `src/models/albaran.py` se incluye para hacer explícito que es un modelo histórico distinto del albarán documental de factura. No se leyó `.env` ni se muestran secretos.

El estado inicial ya contenía dos rutas no rastreadas: `pruebas/facturas/documentos/2o_gold_standard/` y `pruebas/orquestador_v0/`. Son preexistentes; esta tarea no las creó ni modificó. La primera entra en el censo por contener los 14 PDF del segundo gold; la segunda se excluye por no ser parte del normalizador.

## 3. Árbol de archivos y censo exacto

```text
Programa/                                                       662 relevantes
├── docs/normalizador_facturas_v2.md                               1
├── ejecutar_importacion_facturas.bat                              1
├── config/config.py                                               1
├── sql/migrations/06_reestructurar_documentos_y_facturas.sql      1
├── src/
│   ├── facturas/                                                 48
│   │   ├── normalizadores/                                       10
│   │   ├── motores/base.py, simulado.py, __init__.py              3
│   │   ├── motores/openai/                                        7
│   │   ├── motores/google/                                        3
│   │   ├── motores/azure/                                         5
│   │   ├── normalizar_*.py                                        5
│   │   ├── evaluar_*.py                                          10
│   │   └── entrada/config/patrón/duplicados                       5
│   ├── models/factura.py, models/albaran.py                        2
│   ├── probar_motores_facturas.py                                  1
│   ├── supabase_client/conexion_supabase.py                        1
│   └── utils/logger.py                                             1
├── tests/facturas/                                                 9
└── pruebas/facturas/                                             596 (sin 4 .pyc)
    ├── documentos/                                                 8
    ├── documentos/2o_gold_standard/                               14
    ├── gold_standard/                                             16
    ├── patron/                                                     1
    └── resultados/                                               557
        ├── analisis_errores_baseline_b/                           17
        ├── azure/                                                 12
        ├── benchmark_2o_gold_google_splitter_luna_v2/            147
        ├── benchmark_2o_gold_luna/                                72
        ├── benchmark_2o_gold_luna_v2/                             64
        ├── comparativa_2o_gold_a_b_c/                             14
        ├── google/                                                 7
        ├── openai/                                               223
        └── simulado/                                               1
```

Los grupos de resultados son exhaustivos por ruta: cada archivo no `.pyc` bajo esas carpetas queda incluido y clasificado. Contienen runners (5 `.py` en todo `pruebas/facturas`), prompt/schema/contrato/manifiestos, JSON originales y estructurados, metadatos, incidencias, evaluaciones, resúmenes y 20 PDF segmentados. Esta representación compacta evita confundir cientos de salidas homogéneas con componentes ejecutables, pero los recuentos proceden del árbol físico completo.

## 4. Arquitectura actual real

### 4.1 Entrada productiva de documentos, sin normalización

`ejecutar_importacion_facturas.bat` lanza `python -m src.facturas.importar_facturas_drive`. El módulo recorre una ruta fija de Google Drive local, filtra PDF por fecha y excluye las facturas de RITA mediante nombre/carpeta, mantiene un índice SQLite, calcula hash, comprueba duplicados en Supabase Storage y tabla, sube el PDF y crea `documentos_facturas` con estado pendiente. Reintenta errores de red hasta 3 veces con esperas 5/15 s. Salida: efectos en Storage/Supabase e índice local; **no** JSON normalizado. No se ejecutó en esta tarea.

### 4.2 Contrato genérico aislado

`MotorExtraccionFacturas.procesar()` valida ruta/extensión, mide tiempo, llama `extraer_documento()`, envuelve resultado/errores y valida `DocumentoFacturas` (`motores/base.py:68-216`). Solo `MotorSimulado` hereda el contrato. Los scripts reales de Azure/Google/OpenAI no heredan de él y no devuelven `ResultadoMotor`; por tanto es infraestructura incompleta, no pipeline real de IA.

### 4.3 Normalizadores deterministas

Entrada común: JSON de extracción con campos `{valor,evidencias}` y, según proveedor, metadatos y tablas literales. `valor_visible()` bloquea campos sin evidencia válida; `decimal_visible()` y `fecha_visible()` convierten únicamente valores respaldados (`comun.py:231-271`). `documento.py` construye cabecera, destinatario, vencimientos, impuestos, albaranes y ajustes; instancia `FacturaNormalizada`, registra errores estructurales y devuelve un sobre con versión, timestamps, procedencias y validaciones.

Bifurcaciones:

- **Estándar:** interpreta filas genéricas y aplica `ConfiguracionProveedor` para Hygie31, Guimerá, Pierre Fabre o Endesa.
- **Dermofarm/Suavinex:** adaptadores específicos sobre una extracción general.
- **FEDEFARMA:** fusiona extracción general y transcripción literal de tablas, con política explícita para conflictos/ausencias.
- **Alliance:** adaptador monolítico que reconstruye tablas fiscales, albaranes, ajustes y vencimientos desde extracción general + tablas literales.

Salida de los normalizadores: `resultado_normalizado` (schema histórico), `incidencias` separadas y `validaciones_monetarias`. No hay dispatcher por proveedor, persistencia productiva, estado V2, deduplicación interdocumental ni segunda lectura integrada. Cada wrapper `normalizar_*.py` está cableado a rutas de resultados experimentales y escribe nuevos JSON si se ejecuta.

### 4.4 Lectura y benchmarks experimentales

- OpenAI/Luna recibe PDF como data URL, usa Responses API con Pydantic o JSON Schema estricto, y guarda respuesta original, estructurada, metadatos, uso/coste e incidencias.
- Baseline A lee los 14 PDF completos y usa el schema Pydantic histórico.
- Baseline B lee los mismos PDF completos con `prompt_v2.txt` + `schema_v2.json` congelados y admite varias facturas por PDF.
- Baseline C ejecuta Google Custom Splitter sobre cada PDF, valida segmentos, genera PDF físicos por segmento y llama Luna con el mismo contrato B.
- Evaluadores y análisis comparan A/B/C con gold. Están desacoplados del importador productivo y de los normalizadores deterministas.
- Azure y Google Invoice Parser son pruebas anteriores específicas de Alliance, también desacopladas.

## 5. Mapa exhaustivo de componentes

“Consumidor no determinado” significa que `rg` no encontró importador estático; el archivo puede ejecutarse como CLI. Dependencias estándar (`json`, `pathlib`, etc.) se omiten.

| Archivo(s) | Propósito / símbolos principales | Importadores o consumidores estáticos | Dependencias relevantes | Ámbito | Clase y justificación |
|---|---|---|---|---|---|
| `docs/normalizador_facturas_v2.md` | Contrato conceptual aprobado | Pio/futuro desarrollo; no importable | Ninguna | producción futura | REUTILIZAR: fuente de verdad congelada |
| `src/facturas/__init__.py` | Marcador de paquete vacío | importación de paquete | — | producción | REUTILIZAR: neutro |
| `config/config.py` | `NOMBRE_FARMACIA` | importador Drive y conexión | entorno (no inspeccionado) | producción | ADAPTAR: configuración global, no V2 |
| `src/utils/logger.py` | `obtener_logger` | importador Drive | logging | producción | REUTILIZAR: utilidad genérica |
| `src/supabase_client/conexion_supabase.py` | cliente Supabase | importador Drive | SDK/configuración | producción | ADAPTAR: frontera de persistencia fuera de este paso |
| `ejecutar_importacion_facturas.bat` | entrada programable y log | tarea externa no determinada | Python/FS | producción | ADAPTAR: solo ingesta |
| `src/facturas/importar_facturas_drive.py` | descubrir, hash, índice, upload/registro | batch y 3 tests | config, Supabase, logger, SQLite | producción | ADAPTAR: conserva ingesta, carece de extracción V2 |
| `src/facturas/comprobar_duplicados_drive.py` | compara hashes/nombres locales | consumidor no determinado | Drive local, hash | producción/diagnóstico | ADAPTAR: deduplicación documental parcial |
| `sql/migrations/06_reestructurar_documentos_y_facturas.sql` | tablas documento/factura/vencimientos/impuestos/albaranes/ajustes | migración histórica; uso runtime no determinable | PostgreSQL | producción histórica | ADAPTAR: schema incompatible y fuera de implementación actual |
| `src/models/factura.py` | dataclasses y validación histórica | motor base/simulado, documento, wrappers/tests, patrón | dataclasses/Decimal | producción y pruebas | ADAPTAR: estructura útil pero contrato V2 parcial |
| `src/models/albaran.py` | modelo operacional `Albaran` ajeno al PDF | consumidores generales fuera del flujo de factura | dataclasses | producción histórica | DEPRECAR para V2: no representa `AlbaranDocumental` |
| `src/facturas/motores/__init__.py` | reexporta contrato base | consumidor no hallado | `base.py` | producción prevista | ADAPTAR |
| `src/facturas/motores/base.py` | `ResultadoMotor`, métricas, errores, ABC | `simulado.py`, reexport | modelo histórico | producción prevista | ADAPTAR: envoltura aprovechable, contrato desalineado |
| `src/facturas/motores/simulado.py` | implementación ficticia | `src/probar_motores_facturas.py` | base/modelos | pruebas | SOLO_TEST |
| `src/probar_motores_facturas.py` | runner del motor simulado | consumidor no determinado | simulado | pruebas | SOLO_TEST |
| `src/facturas/normalizadores/__init__.py` | reexporta normalizadores | consumidores no hallados por paquete | módulos específicos | producción prevista | ADAPTAR |
| `normalizadores/comun.py` | evidencia, alias, reglas, importes/fechas, validación monetaria, incidencias | todos los normalizadores y tests | Decimal/regex | producción prevista | ADAPTAR: primitivas sólidas, estados/schema parciales |
| `normalizadores/configuracion.py` | `ConfiguracionProveedor` | estándar, adaptadores, tests/configs | `AliasProveedor` | producción prevista | ADAPTAR: política útil; categoría histórica y datos PIO embebidos |
| `normalizadores/documento.py` | cabecera, destinatario, colecciones, ensamblado | estándar, Dermofarm, Suavinex, FEDEFARMA, tests | común/config/modelo | producción prevista | ADAPTAR: núcleo general más cercano, sobre no V2 |
| `normalizadores/conceptos.py` | clasifica conceptos/ajustes visibles | estándar y tests | común | producción prevista | ADAPTAR: precursor de movimientos, vocabulario incompleto |
| `normalizadores/estandar.py` | `normalizar_estandar` | wrapper y tests | común/config/documento/conceptos | producción prevista | ADAPTAR: generalizable, no dispatcher V2 |
| `normalizadores/alliance.py` | reglas Alliance, fiscalidad/tablas/albaranes/ajustes/vencimientos | wrapper y tests | común/modelo | producción prevista | ADAPTAR: cobertura valiosa con alta especificidad |
| `normalizadores/dermofarm.py` | signo de abono, fiscalidad, albaranes | wrapper y tests | común/config/documento | producción prevista | ADAPTAR |
| `normalizadores/fedefarma.py` | fusión general/literal, fiscalidad, movimientos | wrapper y tests | común/config/documento | producción prevista | ADAPTAR |
| `normalizadores/suavinex.py` | cuota agregada, punto verde, albarán único | wrapper y tests | común/config/documento | producción prevista | ADAPTAR |
| `src/facturas/configuraciones_estandar.py` | 4 configuraciones por proveedor | tests; wrappers reciben config externamente | ConfiguracionProveedor | producción prevista | ADAPTAR |
| `src/facturas/cargar_patron.py` | carga/valida patrón oficial | consumidor no determinado | `PatronFacturas` | pruebas | SOLO_TEST: patrón nunca debe orientar producción |
| `src/facturas/normalizar_alliance_08008427.py` | wrapper caso fijo | consumidor no determinado | normalizador Alliance/resultados | experimentación | SOLO_EXPERIMENTO |
| `src/facturas/normalizar_dermofarm.py` | wrapper caso fijo | consumidor no determinado | Dermofarm/modelo/resultados | experimentación | SOLO_EXPERIMENTO |
| `src/facturas/normalizar_estandar.py` | wrapper parametrizable que escribe resultado | consumidor no determinado | estándar/modelo | experimentación | SOLO_EXPERIMENTO |
| `src/facturas/normalizar_fedefarma.py` | wrapper caso fijo general+literal | consumidor no determinado | FEDEFARMA/modelo | experimentación | SOLO_EXPERIMENTO |
| `src/facturas/normalizar_suavinex.py` | wrapper caso fijo | consumidor no determinado | Suavinex/modelo | experimentación | SOLO_EXPERIMENTO |
| `src/facturas/evaluar_benchmark_luna_terra_sol.py` | evaluación de benchmark de modelos | consumidor no determinado | runner OpenAI/gold | experimentación | SOLO_EXPERIMENTO |
| `src/facturas/evaluar_muestra_completa_openai.py` | evalúa muestra contra patrón | consumidor no determinado | resultados/patrón | experimentación | SOLO_EXPERIMENTO |
| `src/facturas/evaluar_normalizacion_alliance_08008427.py` | comparación/aislamiento Alliance | consumidor no determinado | normalizado/patrón | experimentación | SOLO_EXPERIMENTO |
| `src/facturas/evaluar_normalizacion_dermofarm.py` | comparación/aislamiento | consumidor no determinado | normalizado/patrón | experimentación | SOLO_EXPERIMENTO |
| `src/facturas/evaluar_normalizacion_ecoceutics_estandar.py` | evaluación config Hygie31 | consumidor no determinado | normalizado/patrón | experimentación | SOLO_EXPERIMENTO |
| `src/facturas/evaluar_normalizacion_endesa_estandar.py` | evaluación config Endesa | consumidor no determinado | normalizado/patrón | experimentación | SOLO_EXPERIMENTO |
| `src/facturas/evaluar_normalizacion_fedefarma.py` | evaluación general+literal | consumidor no determinado | normalizado/patrón/resultados | experimentación | SOLO_EXPERIMENTO |
| `src/facturas/evaluar_normalizacion_guimera_estandar.py` | evaluación Guimerá | consumidor no determinado | normalizado/patrón | experimentación | SOLO_EXPERIMENTO |
| `src/facturas/evaluar_normalizacion_pierre_fabre_estandar.py` | evaluación Pierre Fabre | consumidor no determinado | normalizado/patrón | experimentación | SOLO_EXPERIMENTO |
| `src/facturas/evaluar_normalizacion_suavinex.py` | evaluación Suavinex | consumidor no determinado | normalizado/patrón | experimentación | SOLO_EXPERIMENTO |
| `motores/openai/__init__.py` | marcador | consumidor no hallado | — | experimentación | SOLO_EXPERIMENTO |
| `motores/openai/probar_extraccion_alliance.py` | schemas Pydantic, división PDF, Luna/otros modelos | varios runners OpenAI y Baseline A | OpenAI/Pydantic/pypdf/dotenv | experimentación | SOLO_EXPERIMENTO |
| `motores/openai/probar_extraccion_alliance_especializada.py` | extracción compleja Alliance | consumidor no hallado | OpenAI/Pydantic/pypdf | experimentación | SOLO_EXPERIMENTO |
| `motores/openai/probar_tablas_literales_alliance.py` | transcripción literal de tablas | benchmark de modelos | OpenAI/Pydantic/pypdf | experimentación | SOLO_EXPERIMENTO |
| `motores/openai/extraer_tablas_fedefarma.py` | transcripción página/secciones FEDEFARMA | wrapper/normalizador vía archivos, no import directo | OpenAI/Pydantic/pypdf | experimentación | SOLO_EXPERIMENTO |
| `motores/openai/probar_extraccion_restantes_patron.py` | lote de muestra con schema histórico | Baseline A importa prompt/schema | OpenAI/Pydantic | experimentación | SOLO_EXPERIMENTO |
| `motores/openai/benchmark_luna_terra_sol.py` | benchmark multi-modelo | evaluador | runners anteriores | experimentación | SOLO_EXPERIMENTO |
| `motores/google/__init__.py` | marcador | consumidor no hallado | — | experimentación | SOLO_EXPERIMENTO |
| `motores/google/probar_splitter.py` | llamada y persistencia Splitter antigua | Invoice Parser consume su JSON por ruta | Document AI/dotenv | experimentación | SOLO_EXPERIMENTO |
| `motores/google/probar_invoice_parser_alliance.py` | valida split, crea 4 PDF y llama Invoice Parser | consumidor no hallado | Document AI/pypdf | experimentación | SOLO_EXPERIMENTO |
| `motores/azure/__init__.py` | marcador | consumidor no hallado | — | experimentación | SOLO_EXPERIMENTO |
| `motores/azure/probar_conexion.py` | prueba `prebuilt-invoice` | consumidor no hallado | Azure SDK/dotenv | experimentación | SOLO_EXPERIMENTO |
| `motores/azure/probar_intervalos_alliance.py` | lectura por rangos | consumidor no hallado | Azure SDK | experimentación | SOLO_EXPERIMENTO |
| `motores/azure/probar_invoice_alliance_separado.py` | 4 PDF y llamadas sin retry | consumidor no hallado | Azure SDK/pypdf | experimentación | SOLO_EXPERIMENTO |
| `motores/azure/inspeccionar_respuesta.py` | inspección local de JSON Azure | consumidor no hallado | resultados Azure | experimentación | SOLO_EXPERIMENTO |

Los 9 tests se detallan en §13. Los 596 archivos del corpus se clasifican por cada ruta de §3: documentos/gold/patrón y `resultados/simulado` son SOLO_TEST (40); los otros 556 resultados/runners son SOLO_EXPERIMENTO. Su consumidor es el runner/evaluador que referencia la carpeta o revisión humana; para JSON/PDF generados individuales no puede determinarse un importador estático más preciso sin inventarlo.

## 6. Proveedores y reglas demostradas

| Proveedor | Archivos/cobertura | Regla demostrada actual | Compatibilidad/simplificación posible |
|---|---|---|---|
| Alliance / Cencora | `alliance.py`, wrapper, evaluador, test (33 tests), runners/tablas; gold Alliance | Alias exacto; tablas CARGOS/ABONOS; reconstrucción fiscal COMPRAS/GASTOS; albaranes por secciones; vencimientos y ajustes específicos | Parcial V2. Reutilizar parsing demostrado; mover evidencia/ensamblado general fuera del adaptador monolítico |
| Dermofarm | `dermofarm.py`, wrapper/evaluador, test (13) y PDF/resultado | exige ABONO visible, normaliza signo contable, fiscalidad y albaranes sin importes inventados | Parcial. La política cero invenciones es compatible; signo/naturaleza debe migrar a modelo V2 |
| Suavinex | `suavinex.py`, wrapper/evaluador, test (17), PDF/resultado | FACTURA exacta, cuota IVA+RE agregada separada, vencimiento visible, punto verde, regla configurable de albarán único | Parcial. La regla `albaran_unico_abarca_factura` es específica y debe quedar explícita, no inferida |
| FEDEFARMA | `fedefarma.py`, transcriptor literal, wrapper/evaluador, test (20), PDF y gold multifactura | limpia etiqueta de albarán, fusiona general/literal, distingue detalle de abonos, evita duplicar abono como ajuste | Parcial. Fusión/precedencia es útil; salida `ajustes` debe mapearse a movimientos sin perder sentido/evidencia |
| Ecoceutics / Hygie31 | `CONFIGURACION_HYGIE31`, estándar, test/evaluador, PDFs/gold | alias exactos, categoría MERCANCIA, conciliación true; no hay adaptador propio | Buena base general, pero V2 no permite clasificar naturaleza solo por proveedor; conservar alias/config, no la inferencia |
| Farmacia Guimerá | `CONFIGURACION_GUIMERA`, estándar, test/evaluador, PDFs/gold | canonización exacta y política de mercancía/conciliación | Igual que Hygie31; lógica general duplicada solo en runners/evaluadores |
| Pierre Fabre | configuración estándar, evaluador, PDF/resultado | configuración INTERNA y conciliación false; normaliza abono con pipeline estándar | Parcial; `categoria=INTERNA` no pertenece a NaturalezaPrincipal V2 |
| Endesa | configuración estándar, evaluador, PDF de gas/resultado | SUMINISTRO, conciliación false | Parcial; naturaleza V2 debe salir del contenido, no del proveedor |
| HEFAME | PDF + gold + resultados A/B/C; regla futura en especificación | **No hay regla/módulo/config actual** | Crear cobertura V2; no atribuir comportamiento al código actual |
| Cofares | 2 PDF + 2 gold + resultados | **No hay regla/módulo/config actual** | Crear solo reglas pequeñas demostradas por especificación/tests futuros |
| L'Oréal | PDF + gold + resultados | sin código específico | Igual |
| Moretti | PDF + gold + resultados | sin código específico | Igual |
| Logista Pharma | PDF + gold + resultados | sin código específico | Cobertura de corpus, no regla |
| Eports | PDF + gold + resultados | sin código específico | Cobertura de corpus, no regla |
| Totalcare | PDF + gold + resultados | sin código específico | Cobertura de corpus, no regla |

No se encontró módulo llamado Cofares, HEFAME o Cencora; Cencora aparece unido a Alliance en gold/especificación. No se infiere compatibilidad por mera presencia en resultados.

## 7. Schemas y modelos actuales

### 7.1 Contrato productivo/histórico Python

`FacturaNormalizada` (`src/models/factura.py:203-230`) contiene:

- escalares obligatorios por constructor pero nullable en varios casos: `tipo_documento`, `categoria`, `requiere_conciliacion_albaranes` (bool), `pagina_inicio`, `pagina_fin`, `proveedor_nombre`, `proveedor_cif`, `numero_factura`, `fecha_factura`, `base_imponible_total`, `iva_total`, `recargo_equivalencia_total`, `importe_total`;
- arrays no nulos con default `[]`: `vencimientos`, `impuestos`, `albaranes`, `ajustes`;
- `destinatario` nullable; `fecha_cargo`, periodos y `nota_revision` opcionales.

Objetos: `DestinatarioFactura(id_farmacia,nombre,cif,metodo_identificacion)`; `VencimientoFactura(orden,fecha_vencimiento,importe,origen_fecha,nota)`; `ImpuestoFactura(orden,base_imponible,tipo_iva,cuota_iva,tipo_recargo_equivalencia,cuota_recargo_equivalencia,nota)`; `AlbaranFactura(orden,numero_albaran,fecha_albaran,tipo_movimiento,importe_base,importe_total,descripcion)`; `AjusteFactura(orden,tipo_ajuste,descripcion,importe,incluido_en_base,incluido_en_total)`.

`DocumentoFacturas` (`347-375`) contiene `archivo`, `tipo_contenido`, `numero_paginas`, `necesita_lectura_visual`, `cantidad_documentos_esperados`, `facturas[]`. `PatronFacturas` añade `version_patron`, `farmacia`, `moneda`, `criterios_generales`, `documentos[]`; es contrato de pruebas, no de producción.

El sobre real de los normalizadores añade fuera de la dataclass: `version_normalizador`, `procesado_utc`, `archivo_origen`, `paginas_procesadas`, `fuentes`, `configuracion_aplicada`, `resultado_normalizado`, `validaciones_estructurales`, `validaciones_monetarias`; las incidencias se devuelven como segundo valor/lista y wrappers las escriben aparte (`documento.py:349-429`).

### 7.2 Persistencia histórica

La migración 06 separa `documentos_facturas`, `facturas`, `facturas_vencimientos`, `facturas_impuestos`, `facturas_albaranes_extraidos` y `facturas_ajustes`. Incluye estados de lectura/conciliación/pago y campos de revisión, pero no prueba que exista escritura runtime de facturas económicas: el único importador inspeccionado solo crea el documento pendiente. No se accedió a Supabase para verificar estado desplegado.

### 7.3 Contratos experimentales

- Pydantic histórico OpenAI: campos envueltos en `{valor,evidencias}`, una `FacturaExtraida` por llamada en runners iniciales; Baseline A añade raíz `facturas[]`.
- Baseline B: JSON Schema estricto con raíz `facturas[]`, 21 campos por factura, arrays no nulos y escalares nullable. Campos: `tipo_documento`, `naturaleza_principal`, conciliación, páginas, proveedor plano, número/fecha, cuatro totales, vencimientos, impuestos, albaranes, `movimientos_comerciales`, destinatario, forma de pago y discrepancias (`schema_v2.json:12-158`). No incluye evidencia.
- Gold segundo: 16 archivos (README, índice y 14 casos) con 18 facturas/documentos económicos, usado solo para evaluación ciega.

## 8. Tabla exhaustiva: schema actual frente a V2

Comparación de los **29 campos raíz** (8 DOCUMENTO + 21 FACTURA). Resultado: **5 compatibles, 13 parciales y 11 ausentes**.

| Campo V2 | Existe | Ubicación actual | Compatible | Cambio necesario |
|---|---:|---|---|---|
| DOCUMENTO.documento_id | NO | hash existe solo en importador/DB | NO | ID técnico determinista en contrato |
| archivo_origen | SÍ | `DocumentoFacturas.archivo`; sobres | PARCIAL | renombrar/separar de evidencia |
| tipo_contenido | SÍ | modelo y SQL | PARCIAL | enums actuales incompatibles entre sí y con V2 |
| numero_paginas | SÍ | modelo/SQL/metadatos | SÍ | permitir null solo ante fallo V2 |
| estado_documento | NO | `estado_lectura` DB no equivale | NO | agregación V2 |
| estrategia_lectura | NO | solo implícita en carpetas/metadata | NO | enum y registro efectivo |
| facturas | SÍ | `DocumentoFacturas.facturas`/schemas | SÍ | conservar lista vacía ante fallo con estado |
| metadata_tecnica | NO | metadata dispersa de runners | NO | objeto versionado sin secretos |
| FACTURA.factura_id | NO | UUID DB, no ID determinista de contrato | NO | generar determinísticamente |
| tipo_documento | SÍ | modelo/schema B | PARCIAL | `ValorDocumentado`, literal sin forzar |
| naturaleza_principal | NO | `categoria` histórica; schema B usa CARGO/ABONO | NO | enum V2 de naturaleza, no sentido económico |
| estado_validacion | NO | validaciones sueltas/flags DB | NO | precedencia y enum V2 |
| requiere_conciliacion_albaranes | SÍ | modelo/config/schema B | SÍ | determinar por contenido/regla aprobada, no proveedor solo |
| pagina_inicio | SÍ | modelo/schema B | SÍ | conservar página original tras split |
| pagina_fin | SÍ | modelo/schema B | SÍ | idem |
| proveedor | SÍ | nombre/cif planos | PARCIAL | `Tercero` documentado, dirección/alias separados |
| numero_factura | SÍ | escalar | PARCIAL | literal+evidencia |
| fecha_factura | SÍ | date/ISO | PARCIAL | `FechaDocumental` literal+ISO+evidencia |
| destinatario | SÍ | dataclass/config o schema B | PARCIAL | tercero visible; no mezclar `id_farmacia` interno con evidencia |
| totales | SÍ | cuatro escalares | PARCIAL | objeto, moneda/otros y evidencia |
| vencimientos | SÍ | array | PARCIAL | fecha documental, medio pago y evidencia; quitar `nota/origen_fecha` histórico o versionar |
| impuestos | SÍ | array | PARCIAL | descripción/total tramo/evidencia |
| albaranes | SÍ | array | PARCIAL | número obligatorio documentado, `tipo_pedido`, sentido y magnitud V2 |
| movimientos_comerciales | NO | `ajustes` se solapa parcialmente; B sí experimental | NO | modelo V2 separado; no conversión automática uno-a-uno |
| forma_pago | NO | texto puede aparecer como nota de vencimiento | NO | objeto independiente |
| referencias_documentales | NO | no existe; algunas referencias se bloquean | NO | lista tipada, no convertir a albarán |
| discrepancias_documentales | NO | incidencias/conflictos; B parcial | NO | objeto V2 que describe sin corregir |
| incidencias | SÍ | segundo retorno/JSON separado | PARCIAL | integrar por factura con código, severidad, páginas, bloqueo y evidencias |
| validaciones | SÍ | estructurales + monetarias | PARCIAL | registro exhaustivo OK/FALLO/NO_APLICA/NO_EVALUABLE, regla y evidencia |

Objetos anidados, exhaustividad de campos:

| Objeto V2 | Campos actuales equivalentes | Faltantes/incompatibles |
|---|---|---|
| `Tercero` | nombre, cif | nif se llama cif; faltan dirección documentada y alias separado; destinatario actual añade IDs internos |
| `Totales` | base, iva, recargo, total | moneda y otros; envoltura documentada |
| `Vencimiento` | orden, fecha, importe | medio_pago y evidencia; nombres diferentes |
| `TramoImpuesto` | orden, base, tipos/cuotas | descripción_literal, total_tramo, evidencia |
| `AlbaranDocumental` | orden, fecha, número, tipo_movimiento, importes | tipo_pedido, evidencia; política de magnitud/sentido no uniforme |
| `MovimientoComercial` | `AjusteFactura` aporta tipo/descripcion/importe | sentido, base/IVA/RE, taxonomía V2, evidencia; semántica no equivalente |
| `FormaPago` | ninguno estable | descripción/referencia documentadas |
| `ReferenciaDocumental` | ninguno | objeto completo |
| `DiscrepanciaDocumental` | incidencias ad hoc | tipo, materialidad, valores documentados, diferencia |
| `Incidencia` | orden/campo/tipo/nivel/descripcion/datos/decision | código V2 estable, páginas, bloqueante y evidencias tipadas; nivel enum distinto |
| `ResultadoValidacion` | nombre/estado/esperado/obtenido/diferencia/tolerancia | códigos V2, NO_APLICA, descripción, evidencia, regla_version; estado actual usa ERROR |
| `MetadataTecnica`/`IntentoLectura`/`Segmento` | metadata de runners y manifest C | falta contrato unificado, correlación, intentos/descartes y segmentos en producción |

## 9. Luna / OpenAI

Inventario ejecutable: 7 archivos en `motores/openai`, Baseline A `ejecutar_fase1.py`, Baseline B `ejecutar_b.py`, Baseline C `ejecutar_c.py`, además de prompt/schema/contrato y resultados. SDK: `openai.OpenAI`, Responses `parse` en runners Pydantic y `create` con `json_schema strict` en B/C. Entrada: PDF completo o páginas/segmentos físicos convertidos a base64 data URL. Multifaktura explícita en A (`LoteFacturas`) y B/C (`facturas[]`).

Modelos observados: Luna es el fijado en A/B/C; runners anteriores comparan Luna/Terra/Sol. Los timeouts son 180/300/600 s según runner; B/C usan 600 s. Los runners auditados fijan `max_retries=0` y registran `sin_reintento`; varios se detienen al primer fallo. Guardan modelo solicitado/utilizado, response id, duración, token usage, hashes, versión/hash de prompt/schema y estimación de coste. Los precios/límites están codificados por experimento y no deben tratarse como configuración productiva vigente.

**Dictamen Baseline B:** ADAPTAR como base de extractor literal, no reutilizar como contrato V2 final. Evidencia favorable: PDF directo, multifaktura, cero invenciones en prompt, schema estricto, contrato hash congelado, límite de coste, timeout, cero retries y logging reproducible (`ejecutar_b.py:18-35`, `182-353`). Incompatibilidades: naturaleza semánticamente errónea respecto a V2, conciliación nullable aunque V2 exige bool, páginas nullable, números JSON binarios, fechas sin literal/ISO, cero evidencias, documento/metadata/estados/validaciones/incidencias/referencias ausentes. Es experimental porque vive bajo `pruebas/.../resultados`, escribe allí y ningún punto productivo lo importa.

## 10. Google Splitter

Código localizado:

- `motores/google/probar_splitter.py`: runner antiguo de un processor configurado por variables de entorno; guarda respuesta original. Carga configuración desde entorno mediante dotenv. No se muestran valores.
- `motores/google/probar_invoice_parser_alliance.py`: valida el JSON del splitter, divide Alliance en cuatro PDF temporales por rangos fijados y llama un Invoice Parser diferente.
- Baseline C `...google_splitter_luna_v2/ejecutar_c.py`: usa credenciales por defecto de Google (`google.auth.default()`), región `eu`, busca exactamente un `CUSTOM_SPLITTING_PROCESSOR` y la versión `pretrained-splitter-v1.5-2025-07-14`, procesa cada PDF con `retry=None`, `timeout=600`, valida páginas contiguas, limita segmentos/llamadas, crea PDF físicos y llama Luna (`113-177`, `218-303`). No persiste el processor id en metadatos.

Entrada Google: bytes PDF `application/pdf`. Salida: entidades con page refs/confianza, JSON original/metadata/incidencias y manifest de segmentos. División física: `PdfReader` + `PdfWriter`; conserva mapping de páginas originales en manifest. Integración actual: solo Baseline C experimental; no conecta con importador ni normalizadores.

Reutilización selectiva potencial: validación de segmentos, límites, nombres neutros, hashes, correspondencia de páginas y `make_segment()`. Deben adaptarse al criterio selectivo V2: C aplica splitter a todos los documentos, mientras V2 solo lo permite por señales combinadas/presupuesto. Configuración/credenciales deben salir de runner experimental sin copiar valores ni asumir que el processor sigue desplegado.

## 11. Azure residual

Quedan 5 archivos de código y 12 resultados. Tres runners usan `azure.ai.documentintelligence.DocumentIntelligenceClient` con `prebuilt-invoice`; leen endpoint/clave desde variables de entorno vía dotenv. Uno divide Alliance, otro usa rangos y otro prueba conexión; `inspeccionar_respuesta.py` solo analiza JSON local. El runner separado fija retries del SDK a cero. No hay clase que implemente `MotorExtraccionFacturas`, importador desde producción, configuración V2 ni uso en Baselines A/B/C. Por inspección estática, su uso real es **residual/experimental**. No se verificó servicio, credenciales ni despliegue.

## 12. Validadores actuales y faltantes

Presentes:

- estructura: páginas positivas/ordenadas, campos mínimos, destinatario/id y orden correlativo de arrays (`FacturaNormalizada.validar`, `DocumentoFacturas.validar`);
- cero invenciones parcial: `valor_visible` exige evidencia; parsers rechazan formatos ambiguos; filas incompletas producen null/omisión e incidencia;
- aliases exactos, no subcadenas;
- suma monetaria Decimal con tolerancia y estados OK/ERROR/NO_EVALUABLE;
- por proveedor: sumas de bases/cuotas/totales, cuotas fiscales, reglas de abono y conflictos de fusión; Alliance/FEDEFARMA/Suavinex poseen controles adicionales;
- duplicado documental por hash en importador y script Drive; deduplicación de albaranes FEDEFARMA por número.

Faltantes frente a V2:

1. estado determinista de documento/factura y precedencia completa;
2. registro exhaustivo de controles no aplicables y `regla_version`;
3. evidencia V2 obligatoria en cada valor documental y validación explícita de “cero invenciones” sobre la salida;
4. páginas de factura comprobadas contra `numero_paginas` y mapping tras segmentación en pipeline productivo;
5. deduplicación funcional de factura y conflicto mismo proveedor+número con importes distintos;
6. controles generales de totales/fiscalidad aplicables de forma uniforme, incluido total de tramos y otros;
7. controles de vencimientos (sumas, fechas anteriores, duplicados) uniformes;
8. conciliación documental de albaranes, diferencia y ausencia/invención sin usar Farmatic;
9. separación/validación de movimientos, referencias, forma de pago y discrepancias;
10. señales deterministas y presupuesto de segunda lectura selectiva, consolidación y fallos;
11. portadas/resúmenes/multifactura validados en producción;
12. materialidad/severidad/bloqueo y agregación de incidencias.

## 13. Tests

Inspección estática: **9 archivos y 208 funciones `test_*` exactas**. No se ejecutaron.

| Archivo | Tests | Componente | Datos | Conservar en V2 |
|---|---:|---|---|---|
| `test_alliance.py` | 33 | adaptador Alliance | fixtures sintéticos + JSON real experimental | Sí, adaptar contrato/evidencia |
| `test_comun.py` | 22 | primitivas | sintético | Sí |
| `test_conceptos.py` | 11 | clasificación ajustes | sintético | Sí, reorientar a movimientos |
| `test_dermofarm.py` | 13 | Dermofarm | JSON real experimental mutado | Sí |
| `test_documento.py` | 53 | ensamblado general/modelo | sintético | Sí, núcleo del nuevo contrato |
| `test_estandar.py` | 36 | estándar + 4 configs | JSON real/sintético | Sí |
| `test_fedefarma.py` | 20 | fusión general/literal | JSON real + mutaciones | Sí |
| `test_suavinex.py` | 17 | reglas Suavinex | JSON real + mutaciones | Sí |
| `test_importar_facturas_drive.py` | 3 | exclusión RITA | tmp_path/mocks | Sí, fuera del normalizador puro |

Infraestructura adicional: 22 PDF locales, patrón oficial de primera muestra, 14 gold del segundo corpus (18 facturas), evaluadores A/B/C y análisis de errores. Los tests unitarios no invocan PDF real ni mockean el contrato Baseline B/Google Splitter; consumen JSON previamente generado.

Huecos: no hay tests de contrato DOCUMENTO V2, estados/precedencia, evidencia tipada, estrategia de lectura, selección de splitter, consolidación, referencias, discrepancias completas, deduplicación funcional, validaciones exhaustivas, HEFAME/Cofares/L'Oréal/Moretti/Logista/Eports/Totalcare, fallos técnicos, presupuesto/timeout, integración PDF→lector→normalizador ni persistencia idempotente. Tampoco hay test que demuestre que ningún dato del gold entra en prompts/producción más allá de búsquedas de aislamiento en algunos adaptadores.

## 14. Deuda y riesgos

### ALTO (6)

1. **Contratos incompatibles:** modelo histórico, Pydantic A, schema B, SQL y V2 difieren. Impacto: pérdida/cambio semántico en toda la salida.
2. **`naturaleza_principal` homónima con significado distinto en B:** CARGO/ABONO frente a naturaleza de actividad V2. Impacto: clasificación funcional errónea si se copia B.
3. **No existe pipeline productivo de lectura/normalización:** ingesta termina en PENDIENTE; runners escriben resultados locales. Impacto: arquitectura incompleta.
4. **Evidencia se pierde al normalizar:** se usa para aceptar valores pero la dataclass final almacena escalares. Impacto: incumplimiento de trazabilidad/cero invenciones verificable.
5. **Reglas de negocio por proveedor en configuración:** `categoria` y conciliación pueden depender del proveedor, mientras V2 exige contenido visible y reglas aprobadas. Superficie: estándar y adaptadores.
6. **Gold/patrón/resultados mezclados con runners:** rutas de producción prevista apuntan a `pruebas/resultados`; riesgo de acoplar evaluación o ground truth.

### MEDIO (6)

1. Alliance concentra 723 líneas y parsing tabular específico; cambios generales pueden romper reglas validadas.
2. Lógica general repetida entre adaptadores (cabecera, fiscalidad, incidencias, validaciones) pese a `documento.py`.
3. `ajustes` mezcla conceptos que V2 separa en movimientos/referencias/discrepancias; conversión ambigua.
4. Enums y nombres históricos (`categoria`, `PDF_DIGITAL`, `cantidad_documentos_esperados`, ERROR vs FALLO) aumentan errores de mapping.
5. Los runners cargan dotenv/credenciales y escriben artefactos al ejecutarse; una invocación accidental produce llamadas/costes.
6. SQL histórico tiene defaults y estados operativos que pueden enmascarar ausencia documental; además su despliegue real no se verificó.

### BAJO (3)

1. `src/models/albaran.py` comparte nombre conceptual pero no pertenece al documento factura; riesgo de importación equivocada.
2. `__init__.py` reexporta solo parte de módulos y no define dispatcher; descubrimiento implícito frágil.
3. Rutas/nombres de caso fijos y nombres históricos como `08008427` reducen reutilización y legibilidad.

Los riesgos 3 de ALTO y 6 de MEDIO combinan hechos estáticos con la inferencia explícita de impacto; no se afirma estado externo de Supabase ni de servicios.

## 15. Mapa preliminar, no plan

### REUTILIZAR TAL CUAL

- especificación `docs/normalizador_facturas_v2.md` como fuente de verdad;
- logger genérico y marcador de paquete;
- corpus/gold como infraestructura de pruebas ciega, sin leerlo desde producción.

### ADAPTAR

- `ConfiguracionProveedor`: conservar aliases/políticas aprobadas, separar identidad de farmacia y evitar naturaleza inferida por proveedor;
- `documento.py`: reutilizar construcción determinista, pero emitir objetos V2 y conservar evidencia/incidencias/validaciones dentro del contrato;
- `comun.py`: parsers Decimal/fecha, alias exacto, procedencias y validación monetaria; ampliar enums/resultado/evidencia;
- normalizador estándar y adaptadores Alliance/Dermofarm/Suavinex/FEDEFARMA; reducir a reglas pequeñas sobre núcleo común;
- `conceptos.py`: orientar a `MovimientoComercial` sin asumir equivalencia de `ajustes`;
- `models/factura.py`, `motores/base.py`, importador/config/conexión/SQL: alinear fronteras y tipos, sin afirmar migración;
- infraestructura de 208 tests y evaluadores locales;
- Baseline B como lector literal experimental y las funciones puras de segmentación/mapping del Splitter.

### CREAR NUEVO

- modelos DOCUMENTO/FACTURA V2 completos, evidencia, fechas documentales, metadata/intentos/segmentos;
- orquestación PDF→Luna B adaptado→normalización/validación→segunda lectura selectiva→consolidación;
- estados/precedencia, deduplicación funcional y validadores faltantes de §12;
- dispatcher de reglas de proveedor y cobertura de proveedores sin código.

### DEPRECAR

- `src/models/albaran.py` dentro del alcance V2 (puede seguir existiendo para albaranes operativos);
- wrappers/evaluadores/runners Azure/Google Invoice Parser/OpenAI antiguos como código de producción; conservarlos solo como evidencia histórica hasta decisión futura;
- nombres/contratos históricos (`categoria`, `ajustes`, `cantidad_documentos_esperados`) una vez exista sustitución V2.

Esto es clasificación, no fases, cronograma ni diseño de migración.

## 16. Preguntas y contradicciones para Pio

### (a) Diferencias técnicas resolubles en futura implementación

- Resolver el significado contradictorio de `naturaleza_principal` tomando la especificación congelada como autoridad y renombrando el sentido CARGO/ABONO del schema B.
- Decidir mappings técnicos de envolturas escalares a `ValorDocumentado`, `ajustes` a objetos V2 solo cuando la semántica sea demostrable, y metadata dispersa a `MetadataTecnica`.
- Integrar la división selectiva y mapping de páginas, no el comportamiento de Baseline C que divide todo.
- Mantener runners históricos fuera de producción y crear una frontera única del lector.

Estas no requieren nueva decisión de negocio en este Paso 1 porque V2 ya fija el resultado funcional.

### (b) Decisiones de negocio realmente pendientes

**Ninguna identificada para completar el inventario.** No se propone resolver aquí schema de base de datos, estrategia de despliegue, modelo/prompt definitivo ni migración: todos pertenecen a autorizaciones futuras. La revisión de Pio sí deberá confirmar el mapa antes del Paso 2, pero no hay contradicción que obligue a estado `REQUIERE_OK_PIO` en este diagnóstico.

## 17. Límites, evidencia consultada y validación final

Límites:

- análisis estático; no se validó comportamiento runtime, imports instalados, datos externos ni despliegue;
- no se abrió contenido binario de PDF/XLSX, aunque se censaron rutas y los scripts/manifiestos describen su uso;
- no se leyó `.env`, no se mostraron credenciales ni se verificaron processor ids/servicios;
- importadores dinámicos, tareas del sistema o consumidores externos al repositorio no pueden determinarse estáticamente;
- no se accedió a Supabase, Farmatic/SQL Server, Google, Azure, OpenAI ni red.

Evidencia principal: los 48 archivos de `src/facturas`, modelos, entrada productiva y migración; 9 tests; especificación V2; prompt/schema/contrato y runners A/B/C; manifiestos/resúmenes/análisis de errores y árbol completo de 596 artefactos. Referencias de línea se tomaron del HEAD indicado.

### Registro final del Orquestador

| Control | Resultado |
|---|---|
| Estado | COMPLETADO |
| Archivos relevantes | 662 exactos |
| Clasificación | REUTILIZAR 3 · ADAPTAR 20 · SUSTITUIR 0 · DEPRECAR 1 · SOLO_TEST 52 · SOLO_EXPERIMENTO 586 |
| Proveedores con reglas/config actual | 8 familias: Alliance/Cencora, Dermofarm, Suavinex, FEDEFARMA, Hygie31/Ecoceutics, Guimerá, Pierre Fabre, Endesa |
| Schema raíz V2 comparado | 29 campos: 5 compatibles · 13 parciales · 11 ausentes |
| Luna/Baseline B | base experimental adaptable; no contrato productivo V2 |
| Google Splitter | experimental; segmentación física/mapping reutilizables selectivamente |
| Azure | residual experimental, sin integración productiva |
| Validadores | estructurales/evidencia parcial/monetarios/proveedor; 12 grupos de faltantes |
| Tests | 9 archivos · 208 funciones exactas · no ejecutados |
| Riesgos | 6 ALTO · 6 MEDIO · 3 BAJO |
| Decisiones de negocio pendientes para cerrar Paso 1 | 0 |
| Procesos externos iniciados | 0 |
| APIs/red | 0 |
| Commit/push | 0 |

La comprobación final de `HEAD` y `git status --short` se realizó después de escribir el informe. El estado preexistente no autorizado se conserva; el único cambio atribuible a esta tarea es `docs/inventario_normalizador_actual_para_v2.md`.
