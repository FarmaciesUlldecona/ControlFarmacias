# Hito 2AR — replay idempotente y fallos no bloqueantes (migración 17)

Fecha: 2026-09-25. Reglas R1–R4 aprobadas por Pio. Certificación exclusivamente
en PostgreSQL 17 local; migración 17 **no desplegada**.

## 1.1 D1 — retorno temprano del replay

**Punto exacto.** `sql/migrations/15_cf_multifactura.sql`, función
`cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[])`:

```sql
select id,resultado_json into ejecucion,replay from public.normalizacion_ejecuciones
  where documento_id=d.id and idempotency_key=p_idempotency_key;
if ejecucion is not null then
    if replay#>>'{multifactura,firma_solicitud}' is distinct from firma then raise exception 'IDEMPOTENCIA_PAYLOAD_DISTINTO'; end if;
    return ejecucion;          -- <- retorno antes de validar claim y de tocar el documento
end if;
```

El envoltorio de 7 parámetros (migración 16) llama a esa función y después
reescribe `disparador` de la ejecución devuelta, también en replay.

**Campos sin restaurar.** El claim (`cf_reclamar_documento_normalizacion_nucleo`)
cambia `estado_lectura='NORMALIZANDO'`, `bloqueado_por`, `bloqueado_hasta` y
`fecha_inicio_lectura`; `cf_solicitar_reprocesado` había puesto
`estado_lectura='PENDIENTE'` y `reprocesar_solicitado_at`. El replay no restaura
`estado_lectura` ni libera `bloqueado_por`/`bloqueado_hasta` ni limpia
`reprocesar_solicitado_at`. `estado_persistencia` e `inventario_facturas` no los
toca el claim ni el reprocesado: conservan el resultado original.

**Resultado original.** `normalizacion_ejecuciones` (fila por
`(documento_id, idempotency_key)`, con `resultado_json.multifactura`) e
`historial_facturas` evento `INVENTARIO_MULTIFACTURA`, cuyo
`estado_nuevo.estado_persistencia` y `detalle.ejecucion_id` fijan el estado final
de esa ejecución. La regla de la RPC 15 deriva
`estado_lectura = NORMALIZADA si COMPLETA, en otro caso REVISION`.

**Mismo patrón en otras RPC** (incluidas en el alcance):

| RPC | Migración | Patrón |
|---|---|---|
| `cf_persistir_normalizacion` (1 documento/factura) | 12 | `if v_ejecucion_id is not null then return` antes de validar claim; deja `NORMALIZANDO` y lock |
| `cf_registrar_fallo_normalizacion` | 12 | `if v_ejecucion_id is not null then return` antes de validar claim. **Agravante:** el worker usa la clave `normalizacion:{doc}:{disparador}:fallo` para todo fallo previo al hash, por lo que el 2º intento fallido de un documento (R3) repetiría clave, quedaría varado y no contaría intento |
| Conciliación V2 | 11/14 | No aplica: el claim no es idempotente por clave y `guardar_conciliacion` escribe tablas directamente, sin retorno temprano por clave |

## 1.2 D2 — motivos de fallo y clasificación

Transmisión actual: `WorkerNormalizacion._procesar_documento` captura cualquier
excepción y llama `repositorio.fallar_ejecucion(documento, type(exc).__name__,
str(exc), ...)` → RPC `p_error_codigo` (clase de excepción) y `p_error_detalle`
(texto del motivo). No hay enum.

Nuevo: `src/facturas/runtime_supabase/clasificacion_fallos.py` clasifica
`(codigo, detalle)` y `RepositorioRuntimeSupabase.fallar_ejecucion` envía
`p_clase_fallo`. `WorkerNormalizacion` y el protocolo `RepositorioNormalizacion`
no cambian. Motivo desconocido → `TRANSITORIO` (reintentos acotados; nunca se
oculta como no soportado).

| Motivo (detalle) | Origen | Clase |
|---|---|---|
| `PROVEEDOR_NO_SOPORTADO_MANUAL`, `PROVEEDOR_NO_RECONOCIDO` | extractor 2AP | NO_SOPORTADO (R2) |
| `REQUIERE_OCR_O_LUNA_NO_AUTORIZADO`, `LUNA_NO_AUTORIZADA_EN_COMPOSITOR_MANUAL` | extractor/ensamblado 2AP | NO_SOPORTADO (R2): capacidad no habilitada, no defecto del PDF |
| `ADAPTACION_NO_CERTIFICADA`, `ADAPTADOR_MULTIFACTURA_NO_CERTIFICADO` | puente multifactura | NO_SOPORTADO (R2): variante de layout sin puente certificado |
| `SHA256_NO_COINCIDE`, `SHA256_REGISTRADO_INVALIDO`, `RUTA_STORAGE_NO_COINCIDE_CON_CLAIM`, `RUTA_STORAGE_NO_SEGURA`, `OBJETO_STORAGE_VACIO`, `DOCUMENTO_RECLAMADO_NO_LOCALIZADO` | materializador 2AP | DEFECTO_DOCUMENTO (R3) |
| `EXTRACCION_LOCAL_ERROR` | motor local | DEFECTO_DOCUMENTO (R3): conservador, acaba visible en REVISION |
| `DOCUMENTO_INCOMPLETO`, `INVENTARIO_DOCUMENTAL_INVALIDO`, `SEGMENTO_DUPLICADO_O_AUSENTE`, `RANGO_FACTURA_INVALIDO`, `PROVENANCE_INCOMPLETA`, `SEGMENTOS_SOLAPADOS`, `EVIDENCIA_FUERA_DE_FACTURA`, `COBERTURA_DOCUMENTAL_INCOMPLETA`, `SELECCION_NO_PERTENECE_AL_DOCUMENTO` | `preparar_documento` | DEFECTO_DOCUMENTO (R3) |
| `EXTRACCION_INCOMPLETA_REQUIERE_REVISION` (`ErrorCompletitudDocumental`) | barrera completitud | DEFECTO_DOCUMENTO (R3) |
| `FARMACIA_DOCUMENTO_NO_DEMOSTRABLE`, `FARMACIA_DOCUMENTO_CONTRADICTORIA` (`ErrorFarmaciaDocumental`) | barrera farmacia | DEFECTO_DOCUMENTO (R3) |
| `NINGUNA_FACTURA_AUTORIZABLE_AUTOMATICAMENTE`, `CAMPOS_PENDIENTES_TRAS_EXTRACCION`, `DOCUMENTO_NORMALIZADO_AUSENTE` | persistencia/ensamblado | DEFECTO_DOCUMENTO (R3) |
| `IDEMPOTENCIA_PAYLOAD_DISTINTO`, `INVENTARIO_RELECTURA_INCOMPATIBLE` | RPC multifactura | DEFECTO_DOCUMENTO (R3): no se corrige reintentando |
| `OBJETO_STORAGE_NO_DISPONIBLE:*`, `CLAIM_DOCUMENTAL_NO_VALIDO`, errores de red/API, `CAMPOS_NO_SOLICITADOS`, cualquier otro | varios | TRANSITORIO (R3) |

## R2/R3 en base de datos

- `estado_lectura` admite `PROVEEDOR_NO_SOPORTADO` (check
  `cf_documentos_estado_lectura_check` redefinido).
- `NO_SOPORTADO` → `PROVEEDOR_NO_SOPORTADO`, sin backoff y **sin contar intento**.
- `DEFECTO_DOCUMENTO`/`TRANSITORIO` → `intentos_fallo_normalizacion += 1`;
  si `< max` → `ERROR` con `proximo_reintento_at = now() + backoff[n]`;
  si `>= max` → `REVISION`, `proximo_reintento_at = null`.
- Parámetros en `cf_configuracion`: `normalizacion_max_intentos = 3`,
  `normalizacion_backoff = {1 h, 6 h, 24 h}`. Con máximo 3 se aplican 1 h (tras el
  1.er fallo) y 6 h (tras el 2.º); el 3.er fallo pasa a `REVISION`. El valor de 24 h
  queda configurado para un máximo mayor (**decisión a confirmar por Pio**).
- Fallo repetido con la misma clave: si el llamante **tiene** el claim es un nuevo
  intento y se registra con clave derivada `<clave>:intento:<n>` (única por
  documento); si no lo tiene es una retransmisión y se devuelve la ejecución
  existente sin tocar nada.
- Éxito (`cf_persistir_normalizacion`) y `cf_solicitar_reprocesado` reinician
  `intentos_fallo_normalizacion`, `ultima_clase_fallo` y `proximo_reintento_at`.
  El reprocesado explícito es la única vía de vuelta a la cola para
  `PROVEEDOR_NO_SOPORTADO` y `REVISION`.

## R4 — selector sin cambios

El núcleo del selector (migración 16) ya filtra `estado_lectura in
('PENDIENTE','ERROR')` y `coalesce(proximo_reintento_at,'-infinity') <= now()`.
Por tanto `PROVEEDOR_NO_SOPORTADO`, `REVISION` y los errores en backoff quedan
excluidos **sin modificar el selector ni el ordering**. La migración 17 no
redefine ninguna función de claim.

## 1.3 Impacto en datos productivos

- Documentos hoy en `ERROR`: conservan `ERROR`, `intentos_fallo_normalizacion=0`
  y `proximo_reintento_at` actual (hoy siempre `null`), luego siguen siendo
  elegibles. En su siguiente fallo se aplican R2/R3. No se migra ningún dato; no
  hace falta script de transición. Conteo real: pendiente de preflight READ_ONLY
  autorizado (no disponible en este hito).
- Documentos en `REVISION` legados (`PARCIAL`): siguen no reclamables.
- Ruta automática: comparte núcleo y RPC; con `normalizacion_automatica=false` no
  reclama. Recibe los mismos arreglos al activarse en el futuro.
- Observación fuera de alcance: si un worker muere tras el claim sin llamar a
  ninguna RPC, el lock expira y el documento queda `NORMALIZANDO` (no reclamable).
  No es replay; queda anotado para un hito propio.
