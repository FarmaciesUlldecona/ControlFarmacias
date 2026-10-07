# Hito 2AZ (final) — Diseño

Alliance completa (R10, R14 y D8), emparejamiento por PUC (D11), tolerancia proporcional (R11) y
enriquecimiento de facturas persistidas (R12). R13: el nombre del archivo nunca es fuente ni control.

Fecha: 2026-10-06. Solo certificación local; nada se despliega.
- Migraciones 01–19 intactas. Todo lo de base de datos va en
  `sql/migrations/20_cf_alliance_tolerancia_enriquecimiento.sql` (+ `.rollback.sql`).
- No se tocan el selector (`cf_reclamar_factura_conciliacion_nucleo`), el ordering, la elegibilidad
  (`cf_evaluar_elegibilidad_conciliacion`, con su 0,05 documental fija) ni otros proveedores.

## 0. Hallazgos de la Fase 1 que condicionan el diseño (READ_ONLY, volcado 2026-10-06 18:05 UTC)

- **1.1 / D11.** 08B96275 (COSTO TELEVENTA, 6,51 €; base 6,23 €) no está en `Supabase.albaranes`
  (registrado hoy en Farmatic por Pío; llegará con la sincronización nocturna).
  - Con R10, la regla actual de emparejamiento lo casaría con **08B96475**: número distinto en un dígito,
    PUC 2,09, **PVP 6,49**, dentro de la tolerancia de 0,05.
  - Saldría CONCILIADA con 0,02 de diferencia: una conciliación falsa que ocultaría el error real.
  - D11 lo impide.
- **1.2.** Filas COSTO TELEVENTA:
  - 08B79008 (08006570) y 08B96274 (08007501), de 0,00 € y ausentes de Supabase: pasan a ser filas
    informativas.
  - 08B96275, de 6,51 €: es mercancía.
- **1.3.** La diferencia de 08011733 (18,07 €) se compone así:
  - 15,91 €: `SERVICIO COVID19` 08D32860, que existe en Supabase con PUC 15,91 (pasa a mercancía);
  - 2,11 €: 08D28707, ambiguo entre 2 candidatos (Q040658/2026 y 08M82343); sigue sin casar;
  - 0,05 €: redondeos de 42 albaranes casados.
  - Con R10 quedan 2,16 € de diferencia.
- **1.4.** Cada factura Alliance imprime una única «FECHA VENCIMIENTO» en la cabecera de cada hoja, y el
  «TOTAL FACTURA» en su hoja de totales (la primera). Base de R14.

## 1. Adaptador Alliance (`src/facturas/motor_local/adaptadores/alliance.py`)

### R10 — Clasificación de filas (`clasificar_fila_economica_alliance`)

Orden de evaluación:
1. **Importe 0,00** (cualquier tipo y bloque) → concepto `INFORMATIVA_IMPORTE_CERO`, regla
   `IMPORTE_CERO_INFORMATIVO`.
   - No se promueve ni genera movimiento. Queda registrada en `candidatos_fila`, y por tanto en
     `datos_extraidos`.
   - Incidencia no bloqueante `FILA_IMPORTE_CERO_INFORMATIVA` con las referencias afectadas.
2. Sentido y signo incoherentes → `NO_DEMOSTRABLE` (sin cambios).
3. Relación documental inequívoca con el resumen (sin cambios).
4. `ABONOS AGRUPADOS` (sin cambios).
5. **Mercancía:** `TIPOS_PEDIDO_MERCANCIA_ALLIANCE` añade `DIRECTO`, `ENCARGO VACUNAS`,
   `MIS RESERVAS`, `TELEVENTA 2`, `COSTO TELEVENTA` y `SERVICIO COVID19`.
   - Bloque CARGOS con importe positivo → `ALBARAN_MERCANCIA`.
   - Se promueve con las mismas condiciones de rol y segmentación.
   - El cruce con `Supabase.albaranes` en la conciliación es la prueba de mercancía recibida.
6. **Abono:** tipo `ECOCEUTICS` en el bloque ABONOS con importe negativo → `ABONO`, categoría
   `ABONO_COMERCIAL`.
   - Mismo precedente que `ABONOS AGRUPADOS`: genera un movimiento ABONO que resta y la factura pasa a
     MIXTA.
   - La persistencia lo guarda con categoría `OTRO`.
7. Cualquier otro tipo → `NO_DEMOSTRABLE` (falla cerrado).

**D8.** La incidencia `CANDIDATO_ALBARAN_NO_PROMOVIDO` sigue siendo no bloqueante, pero lleva un motivo
veraz por causa, junto con `tipos_pedido` (literales) y `cantidad`:
- `TIPO_PEDIDO_NO_CERTIFICADO` si la regla es `ESTRUCTURA_Y_CONCEPTO_INSUFICIENTES`;
- `SENTIDO_O_SIGNO_NO_COHERENTE` si la regla es `SENTIDO_Y_SIGNO_NO_COHERENTES_O_NO_DOCUMENTADOS`.

### R14 — Vencimientos (`_vencimientos`)

**Regla:** en la hoja de totales de la factura, que es su primera página (la que contiene TOTAL BASE
IMPONIBLE, IVA, RE y TOTAL FACTURA):
- Si la línea de identidad contiene **exactamente una** fecha de vencimiento y el `TOTAL FACTURA` de
  **esa misma hoja** es legible:
  - importe del vencimiento = ese total;
  - evidencia: la palabra del total en esa hoja;
  - regla `R14_TOTAL_MISMA_HOJA_VENCIMIENTO_UNICO`.
- Si hay más de una fecha o el total no es legible: vencimiento **sin importe** e incidencia
  `IMPORTE_VENCIMIENTO_NO_DOCUMENTADO`, como hoy.

**Repeticiones en las demás hojas:**
- La misma fecha en las cabeceras de otras hojas se añade como evidencia del mismo vencimiento; no crea
  otro.
- Una fecha distinta en otra hoja crea un vencimiento contradictorio sin importe. El de la hoja de
  totales también pierde el importe y se emite la incidencia `VENCIMIENTO_CONTRADICTORIO_ENTRE_HOJAS`
  (falla cerrado).

**Otros:**
- `IMPORTE_VENCIMIENTO_NO_DOCUMENTADO` solo se emite si queda algún vencimiento sin importe.
- R13: nunca se usa el nombre del archivo.

### Versiones y claves
- `AdaptadorAlliance.version`: `1.2.0` → **`1.3.0`**.
- `version_normalizador` del puente multifactura (y su `regla_version`): `multifactura-local-1` →
  **`multifactura-local-2`**. Se guarda en `normalizacion_ejecuciones.normalizador_version`.
- **Claves de normalización** (`normalizacion:{doc}:{disparador}:{sha256(resultado)}`):
  - cambian para todo documento Alliance;
  - los documentos pendientes se normalizan por primera vez sin conflicto;
  - los 2 documentos Alliance ya normalizados (`ae53897a` y `ffee3c1c`) **no se reprocesan**: la RPC
    multifactura hace `on conflict do update` y borra y reinserta las filas hijas, también en facturas
    conciliadas. Para ellos existe R12.

## 2. D11 — Emparejamiento (`conciliacion.buscar_candidato_albaran`)

- Para cada candidato se calcula primero la coincidencia de número.
  - Con número **EXACTO** se admite el importe compatible por PUC o por PVP, como hoy.
  - Con número **distinto o no disponible** solo se admite el **PUC**, con la tolerancia de importe
    actual (0,05) y candidato único.
- Casar por PVP sin número exacto queda prohibido.
- No cambia nada más: ventana, proveedor (R9) ni desempates. El ramal HEFAME ya exige número exacto.
- **Efecto:**
  - 08007501 sin 08B96275 queda **sin casar** (SIN_COINCIDENCIA): DIFERENCIA, no conciliada.
  - Con 08B96275 (PUC 6,51) casa por número exacto.
  - Los casos de control (08007973, 08009277, 08009278, 08009279 y Q039904/2026↔08C18299) siguen casando
    igual, por número exacto o por PUC.

## 3. R11 — Tolerancia proporcional

`tolerancia = máx(suelo; mín(por_albarán × n; tope))`, con n = detalles `UNO_A_UNO`.

**Parámetros** en `cf_configuracion` (migración 20):
- `conciliacion_tolerancia_suelo` 0,0500, `conciliacion_tolerancia_por_albaran` 0,0100 y
  `conciliacion_tolerancia_tope` 0,5000;
- check `cf_configuracion_tolerancia_r11_check`: `0 < suelo <= tope <= 1,00` y
  `0 <= por_albaran <= 0,05`.

**Python** (misma regla para la ruta automática y la manual, porque ambas pasan por
`WorkerConciliacion._procesar`):
- `ReglaTolerancia(suelo, por_albaran, tope).para(n)`.
- `conciliar_importes(..., regla=)` calcula n y devuelve `ResultadoConciliacion` con `albaranes_casados`
  y `regla_tolerancia`.
- El worker aplica siempre la regla; por defecto R11 con `suelo = tolerancia`.
- `ConfiguracionRuntime` añade `tolerancia_por_albaran` y `tolerancia_tope`, que lee
  `obtener_configuracion`; el compositor construye la regla desde la configuración.
- `construir_worker_automatico` exige suelo ≤ 0,05, por_albarán ≤ 0,01 y tope ≤ 0,50.

**Registro y validación en BD.** `cf_persistir_conciliacion` se redefine en la 20: es el cuerpo de la 18
más la validación R11, solo en la rama de inserción nueva (tras claim y disparador; el replay no
cambia):
- La tolerancia del payload debe ser igual a la R11 calculada en el servidor desde los detalles y la
  configuración; si no, `TOLERANCIA_NO_COINCIDE_CON_R11`.
- Si llega `tolerancia_regla`, debe coincidir con la configuración; si no,
  `TOLERANCIA_REGLA_NO_COINCIDE`.
- `CONCILIADA` exige \|dif\| ≤ tolerancia y `DIFERENCIA` exige \|dif\| > tolerancia; si no,
  `RESULTADO_INCOHERENTE_CON_TOLERANCIA`.
- La tolerancia aplicada queda en `conciliaciones.tolerancia`, y su desglose en
  `conciliaciones.provenance.tolerancia_regla` = {suelo, por_albaran, tope, albaranes_casados,
  tolerancia}, calculado por el servidor.
- El payload Python añade `tolerancia_regla`, así que las claves nuevas difieren de las anteriores. Solo
  afecta a conciliaciones futuras.

## 4. R12 — Enriquecimiento de facturas persistidas

**RPC** `public.cf_enriquecer_factura(p_factura_id uuid, p_worker_id text, p_idempotency_key text,
p_enriquecimiento jsonb) returns jsonb`:
- `security definer`, `set search_path = public`, owner `postgres`;
- `REVOKE ALL ... FROM public, anon, authenticated` y `GRANT EXECUTE ... TO service_role`;
- una transacción, con la factura bloqueada `for update`.

**Payload**, construido en Python con el extractor vigente:
```
{documento_id, archivo_hash, normalizador_version,
 identidad: {numero_factura, fecha_factura, importe_total, proveedor_cif, identidad_economica_clave},
 albaranes: [objeto albarán del DocumentoNormalizado],
 movimientos: [objeto movimiento_comercial],
 vencimientos: [{fecha: {valor: {iso}}, importe: {valor, literal, evidencia}, regla}]}
```

**Validaciones**, todas fail-closed:
1. `worker_id` e `idempotency_key` obligatorios; la clave empieza por `enriquecimiento:{factura_id}:`.
2. La factura existe y su farmacia está habilitada.
3. **Replay:** si ya hay un `FACTURA_ENRIQUECIDA` con esa clave y el mismo hash de payload, devuelve
   `{replay: true}` **sin escribir nada**. Con otro hash: `IDEMPOTENCY_KEY_REUTILIZADA`.
4. `estado_conciliacion_cf = 'PENDIENTE_CONCILIAR'`; si no, `FACTURA_YA_CONCILIADA` o
   `FACTURA_EN_REVISION_CONCILIACION`. Sin claim vigente; si no,
   `FACTURA_RECLAMADA_EN_CONCILIACION`.
5. Mismo documento y mismo SHA; si no, `DOCUMENTO_NO_COINCIDE` o `SHA_NO_COINCIDE`.
6. Identidad idéntica: número, fecha, total, CIF (`proveedor_cif`, o `datos_extraidos.proveedor.nif` si
   está vacío) y `identidad_economica_clave`. Si no, `IDENTIDAD_NO_COINCIDE:<campo>`.
7. Albaranes: ningún número ya presente (`ALBARAN_YA_PRESENTE`).
8. Movimientos:
   - ninguno ya presente por (descripción, sentido, importe) (`MOVIMIENTO_YA_PRESENTE`);
   - solo si la factura es MIXTA (`MOVIMIENTOS_REQUIEREN_NATURALEZA_MIXTA`): cambiar la naturaleza
     modificaría la factura.
9. Vencimientos: cada uno debe localizar **exactamente una** fila de `facturas_vencimientos` de la
   factura con esa fecha (`VENCIMIENTO_NO_LOCALIZADO`).
   - El importe de esa fila debe ser NULL; si ya tiene valor, se rechaza con
     `VENCIMIENTO_CON_IMPORTE_EXISTENTE`. Nunca se sobrescribe.
   - Importe exigido distinto de NULL.
10. Al menos una fila nueva o un importe que rellenar (`SIN_FILAS_NUEVAS`).

**Escritura:**
- **Inserciones** en `facturas_albaranes_extraidos` y `facturas_movimientos`:
  - mapeo exacto de la migración 17, con `orden = máx + i` y `normalizacion_ejecucion_id = null`;
  - `provenance` = objeto original más `enriquecimiento: {idempotency_key, worker_id,
    normalizador_version}`.
- **Vencimientos:** `update ... set importe = <valor> where importe is null`, y se añade la clave nueva
  `enriquecimiento_importe` a la `provenance`, sin tocar las existentes.
- La fila de la factura y sus importes **no se modifican**.
- **Historial** `FACTURA_ENRIQUECIDA`: `estado_nuevo` = {albaranes_anadidos, movimientos_anadidos,
  vencimientos_rellenados} y `detalle` = {idempotency_key, payload_sha256, normalizador_version,
  worker_id}.

**Elegibilidad:** sin cambios en la función. Una MERCANCIA con albaranes nuevos pasa a `APTA_MERCANCIA`.

**Límite de lectura:** tras la 19, `service_role` no tiene SELECT sobre `facturas_vencimientos`. Por eso
Python decide qué vencimientos proponer a partir de `facturas.datos_extraidos` (importe NULL en la
versión persistida). Si un vencimiento ya se rellenó, la RPC rechaza la propuesta: falla cerrado
(documentado).

**Python:**
- `runtime_supabase/enriquecimiento.py`, con `construir_enriquecimiento` (pura) y
  `clave_idempotente_enriquecimiento`.
- `WorkerEnriquecimiento.ejecutar(factura_id)`: lee los datos con `service_role`; materializa el PDF
  verificando el SHA (`MaterializadorStoragePrivado`); extrae con `ExtractorDocumentalAutorizado`;
  construye el payload y llama a la RPC.
- Compositor: `construir_worker_enriquecimiento_manual(...)`.

**Script one-shot:** `pruebas/auditoria_2az/enriquecer_una_vez.py <factura_esperada> <salida> <dir>`.
- Revalidación READ_ONLY: factura existente, `PENDIENTE_CONCILIAR`, sin claim, flags `f|f|f|{PIO}`,
  workers y locks a 0.
- Guard exclusivo, UNA llamada sin reintento y lectura posterior.
- No se ejecuta en producción; se ensaya completo en PostgreSQL 17 local.

## 5. Despliegue (2AZ-D; no se ejecuta en este hito)

`pruebas/auditoria_2az/desplegar_20.py <commit> <sha256_lf> <salida>` sigue el patrón de
`desplegar_19.py`:
- comprobación del SHA contra el commit y una sola transacción;
- precondiciones: 19 aplicada, 18 presente, 20 no aplicada, flags seguros, sin claims ni locks y
  conciliaciones = 13;
- un segundo intento falla en las precondiciones y revierte.

**Orden:** primero la 20 y después el código, sin conciliaciones entre medias.
- Con la 20 y el código antiguo, una conciliación con más de 5 albaranes casados es rechazada por R11
  (falla cerrado).
- Con el código nuevo sin la 20, `obtener_configuracion` falla antes de cualquier claim.

## 6. Impacto sobre datos existentes

Ninguno sin acción explícita. La 20 solo añade columnas con valor por defecto, un check y una función
nueva, y redefine `cf_persistir_conciliacion`; no hay DML sobre filas. Las 13 conciliaciones y las 12
facturas quedan idénticas, verificado con huellas en `pg17_local`. 08007971 y sus vencimientos solo
cambian si se ejecuta el script de enriquecimiento, en un hito con confirmación de Pío.

## 7. Contratos certificados que se modifican (dentro del alcance descrito)

- **Adaptador Alliance:** 1.3.0, con R10 ampliada, filas a 0,00, D8 y R14.
- **Puente multifactura:** `multifactura-local-2`.
- **`buscar_candidato_albaran`:** D11.
- **`conciliar_importes`:** parámetro `regla`.
- **`ResultadoConciliacion`:** dos campos opcionales.
- **`payload_conciliacion`:** `tolerancia_regla`.
- **`WorkerConciliacion` y `construir_worker_conciliacion`:** R11.
- **`ConfiguracionRuntime` y `obtener_configuracion`:** dos campos.
- **`construir_worker_automatico`:** controles.
- **`cf_persistir_conciliacion`:** R11.
- **Nueva RPC:** `cf_enriquecer_factura`.
- **Simulador `simulador_conciliacion_2av`:** R11.
- **Tests existentes** cuyas expectativas fijan la versión 1.2.0 de Alliance, el motivo antiguo o el
  emparejamiento por PVP sin número: se actualizan con justificación.

## 8. Hitos futuros registrados (NO se implementan)

- a) Cierre manual de conciliación con justificación de Pío para facturas en `REVISION_CONCILIACION`:
  sin alterar albaranes ni importes, con provenance e historial.
- b) Informe periódico de «albaranes facturados no encontrados en Farmatic» por proveedor y periodo.
- Hito COFARES, clasificación de Pío:
  - total de devoluciones = abono;
  - servicio integral de distribución = cargo sin albarán;
  - domiciliación bancaria = cargo sin albarán;
  - desglose del recargo de equivalencia obligatorio.
