# Hito 2AP — diseño del compositor productivo del worker manual

Fecha: 2026-09-24. Alcance: implementación y certificación local. Sin producción.

## Contratos exigidos por `WorkerNormalizacion` (sin modificar)

| Pieza | Contrato certificado | Consumidor |
|---|---|---|
| `materializar_pdf` | `Callable[[DocumentoTrabajo], Path]` | `_procesar_documento` |
| `orquestador` | objeto con `extraer(ruta, campos_requeridos) -> ResultadoExtraccionProductiva` | `_procesar_documento` |
| etapa del orquestador | `ExtractorCampos`: `codigo: str`, `extraer(ruta_pdf: Path, campos_pendientes: frozenset[str]) -> ResultadoEtapa`; solo puede devolver campos pendientes | `OrquestadorExtraccionProductiva._aplicar_etapa` |
| `ensamblar_documento` | `Callable[[DocumentoTrabajo, ResultadoExtraccionProductiva], dict]` | `_procesar_documento`, antes de `validar_documento_antes_de_persistir` |
| persistencia | `persistir_documento_automatico(documento, resultado, hash, worker_id, disparador, idempotency_key)` | ruta multifactura de 7 parámetros |

`ejecutar_una_manual()` delega en `ejecutar_una_manual_one_shot()`, que pasa el
literal `MANUAL_ONE_SHOT` a `_procesar_documento`, y de ahí a
`persistir_documento_automatico(..., disparador)` → `p_disparador`. Cualquier
excepción termina en `fallar_ejecucion` (FAIL-CLOSED) sin nuevo claim.

## Diferencia con `motor_local`

`MotorDocumentoLocal.extraer(ruta) -> DocumentoExtraidoLocal` devuelve la
extracción documental completa, no campos pendientes. El shadow
(`motor_local/shadow.py`) conserva la salida oficial y nunca la aplica.

## Estrategia de adaptación (sin tocar contratos certificados)

Módulo nuevo `src/facturas/runtime_supabase/compositor_manual.py`:

1. `MaterializadorStoragePrivado`: lee `archivo_ruta` y `archivo_hash` de la fila
   `documentos_facturas` **por el `documento_id` ya reclamado** (no es selector),
   exige que la ruta coincida con la reclamada, descarga del bucket privado
   `facturas-pdf`, verifica SHA-256 y escribe `<directorio>/<documento_id>.pdf`.
   SHA distinto, objeto inexistente, fila ausente o ruta insegura → excepción.
2. `ExtractorDocumentalAutorizado` (etapa `ExtractorCampos`): ejecuta
   `MotorDocumentoLocal(BackendPdfium())`, determina el layout **por contenido**,
   exige autoridad manual del proveedor y aplica el puente certificado
   `adaptar_resultado_local`. Resuelve los campos
   `proveedor_layout` y `documento_normalizado_v2` solo si todo es demostrable.
   En otro caso no resuelve nada y deja el motivo en `provenance`.
   La ruta temporal se sustituye en metadatos técnicos por `sha256:<hash>` para
   que el hash normalizado no dependa del directorio de trabajo.
3. `ensamblar_documento_manual`: devuelve `documento_normalizado_v2` solo si el
   orquestador terminó sin campos pendientes; en otro caso lanza
   `DocumentoNoAptoManual` con el motivo (proveedor no soportado, error de
   extracción, requiere Luna/OCR…).
4. `construir_worker_manual_productivo(cliente, configuracion, worker_id,
   directorio_trabajo)`: único punto de composición. Construye
   `RepositorioRuntimeSupabase`, orquestador sin Luna
   (`extractor_luna=None`, `luna_habilitada=False`), worker de conciliación
   certificado (requerido por `construir_worker_automatico`, no usado por la ruta
   manual) y devuelve `WorkerAutomatico`. Rechaza `luna_habilitada=true` y
   farmacias distintas de `("PIO",)`. No lee ni escribe flags: recibe la
   configuración ya obtenida por el llamante.

## Autoridad productiva por proveedor

El registro global `AUTORIDADES_EXTRACTORES_LOCALES` es contrato certificado
(tests exigen todo `False`) y **no se modifica**. Se crea una autoridad distinta y
más estrecha, válida solo dentro del compositor manual:

`AUTORIDAD_COMPOSITOR_MANUAL = {ProveedorLocal.ALLIANCE: "alliance-local"}`
(inmutable). Cualquier proveedor ausente queda desactivado. Además cada entrada
debe estar cubierta por el puente certificado (`adaptar_resultado_local` solo
admite `alliance-local`); un test impide ampliar la lista sin puente.

## Proveedor no soportado / Luna

- Layout reconocido pero sin autoridad manual, o no reconocido →
  campos pendientes → incidencia certificada `CAMPOS_PENDIENTES_TRAS_EXTRACCION`
  → ensamblado lanza `PROVEEDOR_NO_SOPORTADO_MANUAL` → `fallar_ejecucion`.
- Documento sin texto nativo (`PENDIENTE_OCR`) → los campos quedan pendientes; con
  `luna_habilitada=false` y sin extractor Luna el orquestador no invoca Luna →
  `REQUIERE_OCR_O_LUNA_NO_AUTORIZADO` → `fallar_ejecucion`.
- Excepción del motor local → `EXTRACCION_LOCAL_ERROR` → `fallar_ejecucion`.

Persistencia, farmacia documental PIO, completitud, identidad económica,
duplicados y selección de segmentos siguen exclusivamente en las barreras
certificadas (`validar_documento_antes_de_persistir`, `preparar_documento`,
`persistir_documento_automatico` y la RPC multifactura).
