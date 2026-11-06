# Reglas críticas

Actualizado: 2026-11-06 (2BN-D: aclaración de la norma de hooks, forma documentada permitida; ensayos de despliegue con el rol que imita al postgres de Supabase; puerta git con excepción documental, decisión de Pio; 2BK-D: barrera de commit con
FAIL solo por T2; 2BK: norma de parada ante hooks, denegaciones y clasificador; 2BJ: serie
supervisada de normalización, solo local; 2BI-D: migración 25
desplegada; 2BI: claims huérfanos de normalización; 2BH: evidencia mecánica
de la suite; 2BG: regla R19, aplicada a 08007970; 2BE-D: migración 24 desplegada y norma de tests antes
de commit; 2BE: regla R17; 2BF-D: migración 23 desplegada).

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
- **Hooks, denegaciones y clasificador (Pio, 2026-11-02, Hito 2BK).** Si un hook, una denegación de
  permiso o el clasificador bloquean una acción, el agente **PARA e informa** a Pio de qué intentaba y
  qué lo bloqueó. Nunca reformula, parte, ofusca ni cambia de herramienta la acción para esquivar el
  bloqueo. Origen: en el diagnóstico del 2BK se partió el nombre de un rol para pasar un hook y el
  clasificador lo rechazó.
  **Aclaración (Pio, 2026-11-06, 2BN-D):** PROHIBIDO reformular una acción para conseguir lo que un hook
  impide. PERMITIDO usar la forma documentada de una acción autorizada (por ejemplo, `git` sin `-C`, desde el
  directorio de trabajo, para la misma lectura del repositorio). En la duda, PARA.
- **Puerta git antes de una ejecución productiva (tandas de la serie, despliegues).** Árbol siempre limpio y
  HEAD == `origin/main`. **Excepción acotada (DECISIÓN DE PIO, 2026-11-05):** HEAD puede ir por delante de
  `origin/main` solo si los commits pendientes tocan exclusivamente documentación (`docs/` o `*.md`); se
  comprueba antes de cada tanda con `git diff --name-only origin/main..HEAD`. Cualquier otro archivo: PARA.

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
  `CONFIRMADO POR TEST` en PostgreSQL 17 local y `CONFIRMADO EN PRODUCCIÓN`,
  desplegada en el Hito 2AS el 2026-09-25):
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
    `proximo_reintento_at` (1 h, 6 h, 24 h); al alcanzar el máximo (4, decisión
    de Pio en 2AS) → `REVISION`.
    Parámetros en `cf_configuracion` (`normalizacion_max_intentos`,
    `normalizacion_backoff`). El reprocesado explícito reinicia el contador.
  - **R4 ordering:** sin cambios. El selector ya excluye todo estado distinto de
    `PENDIENTE`/`ERROR` y los backoff futuros; la migración 17 no redefine el claim.
  - Clasificación de motivos: `runtime_supabase/clasificacion_fallos.py`; un motivo
    desconocido es `TRANSITORIO`, nunca `NO_SOPORTADO`.
- Reglas aprobadas por Pio para la migración 18 (Hito 2AV, 2026-09-25;
  `CONFIRMADO POR TEST` en PostgreSQL 17 local y `CONFIRMADO EN PRODUCCIÓN`,
  desplegada en el Hito 2AW el 2026-09-28; primera conciliación manual one-shot
  productiva en el Hito 2AT rev2, 2026-10-06, ver `ESTADO_ACTUAL.md`):
  - **R5 claim manual de conciliación:** `p_modo_ejecucion` `AUTOMATICO` o
    `MANUAL_ONE_SHOT`. `MANUAL_ONE_SHOT` solo omite `conciliacion_automatica`;
    selector y ordering idénticos a la migración 14; como máximo 1 factura; sin
    preselección. Envoltorio `cf_reclamar_factura_conciliacion_manual_one_shot`.
  - **R6 cierre atómico:** `cf_persistir_conciliacion` escribe cabecera, detalles,
    `es_actual`, estado de factura, liberación del lock e historial en una
    transacción, con clave idempotente
    `conciliacion:{factura}:{disparador}:{sha256 del resultado}`. Replay: no
    duplica, libera el claim del llamante, restaura el estado y registra
    `CONCILIACION_REPLAY_IDEMPOTENTE`.
  - **R7 fallos con backoff:** `cf_registrar_fallo_conciliacion`; 4 intentos con
    1 h / 6 h / 24 h (`cf_configuracion.conciliacion_max_intentos`,
    `conciliacion_backoff`); el 4.º pasa a `REVISION_CONCILIACION`, no
    reclamable. Solo vuelve con `cf_solicitar_reintento_conciliacion`, que
    reinicia el presupuesto; un éxito lo pone a 0.
  - **D-A (2AW) DIFERENCIA con backoff:** un resultado distinto de
    `CONCILIADA` consume intento con el mismo contador y backoff que los fallos
    (clase `DIFERENCIA`); al 4.º, `REVISION_CONCILIACION`. La cola no se
    bloquea: el siguiente claim toma el n.º 2.
  - **D-B (2AW):** `cf_solicitar_reintento_conciliacion` solo con EXECUTE para
    `service_role` (retirado a authenticated, como `cf_solicitar_reprocesado`).
  - **D-C (2AW):** tolerancia sin cambios (0,05).
  - **R8 provenance:** disparador `MANUAL_ONE_SHOT` en la ruta manual y
    `AUTOMATICO` en la automática, validado contra el modo del claim.
  - **R9 `id_proveedor` tolerante:** solo en la comparación de
    `buscar_candidato_albaran` (trim y ceros a la izquierda: `'2' == '0002' == '0002 '`);
    los literales se conservan.
- Reglas aprobadas por Pio en el Hito 2AZ (2026-10-06/07; `CONFIRMADO POR TEST` en
  PostgreSQL 17 local; migración 20 `CONFIRMADO EN PRODUCCIÓN`, desplegada en el
  Hito 2AZ-D el 2026-10-08; diseño en
  `pruebas/auditoria_2az/DISENO.md`):
  - **R10 tipos de pedido Alliance** (adaptador 1.3.0):
    - Mercancía (se promueve; la prueba de recepción es el cruce con
      `Supabase.albaranes`): `DIRECTO`, `ENCARGO VACUNAS`, `MIS RESERVAS`,
      `TELEVENTA 2`, `COSTO TELEVENTA` y `SERVICIO COVID19`, además de los ya
      certificados.
    - `ECOCEUTICS` en el bloque ABONOS → ABONO (resta).
    - Filas de importe 0,00 → informativas: se registran, no se promueven y no
      bloquean.
    - Cualquier otro tipo falla cerrado con motivo `TIPO_PEDIDO_NO_CERTIFICADO` y el
      literal (D8).
  - **R11 tolerancia de conciliación:** `máx(suelo; mín(por_albarán × n; tope))`,
    con suelo 0,05, por_albarán 0,01, tope 0,50 y n = albaranes casados.
    - Parámetros en `cf_configuracion`, con check.
    - Misma regla en la ruta manual y en la automática.
    - `cf_persistir_conciliacion` la valida y la registra en
      `conciliaciones.provenance.tolerancia_regla`.
    - La elegibilidad (control documental, 0,05) no cambia.
  - **R12 enriquecimiento** (`cf_enriquecer_factura`): camino propio, NO
    reprocesado.
    - Solo facturas `PENDIENTE_CONCILIAR`, mismo documento y SHA e identidad
      económica idéntica.
    - Solo añade albaranes y movimientos (movimientos solo en MIXTA) y rellena
      importes de vencimiento NULL; nunca sobrescribe.
    - Idempotente por clave (replay sin escrituras), con provenance e historial
      `FACTURA_ENRIQUECIDA`.
  - **R13:** el nombre del archivo nunca es fuente ni control de ningún dato
    (tampoco vencimientos).
  - **R14 vencimientos Alliance:** en la hoja de totales de cada factura, con
    exactamente una fecha de vencimiento y el TOTAL FACTURA legible en esa hoja, el
    importe del vencimiento es ese total. Si hay más de una fecha o el total no es
    legible, queda sin importe e incidencia.
  - **D11 emparejamiento:** sin número de albarán exacto solo se admite casar por
    PUC (tolerancia de importe actual y candidato único). Casar por PVP sin número
    exacto queda prohibido.
- Reglas aprobadas por Pio en el Hito 2BA (2026-10-08/09; `CONFIRMADO POR TEST` en
  PostgreSQL 17 local; migración 21 `CONFIRMADO EN PRODUCCIÓN`, desplegada en el Hito 2BA-D el
  2026-10-19). Código en
  `runtime_supabase/conciliacion.py` (`clasificar_numero_albaran`,
  `buscar_candidato_albaran`, `buscar_albaranes_factura`) y
  `sql/migrations/21_cf_exclusividad_albaranes.sql`:
  - **R15 exclusividad de albaranes** (corrige D12):
    - un albarán de Farmatic (farmacia, IdContador) justifica como máximo una línea de
      una conciliación vigente;
    - BD: tabla `conciliacion_albaranes_reservados` (clave primaria farmacia +
      IdContador), escrita solo por `cf_persistir_conciliacion`; `service_role` solo
      `SELECT`. Rechazo `ALBARAN_YA_CONCILIADO:<farmacia>:<IdContador>` si dos líneas
      del resultado comparten albarán o si está reservado por otra factura. Un nuevo
      intento de la misma factura reutiliza sus albaranes y las reservas pasan a la
      conciliación vigente. La carga inicial toma las conciliaciones vigentes; si dos
      comparten albarán, la migración aborta (falla cerrado);
    - Python: salta los albaranes reservados por otras facturas; dentro de una factura
      un albarán solo justifica una línea y se resuelven primero las líneas con
      coincidencia de número; si la línea solo encuentra un albarán ocupado, estado
      `ALBARAN_YA_CONCILIADO`;
    - opción 2: nunca se toma por importe un albarán cuyo número es exactamente el de
      una línea documental de otra factura (sin filtro de fecha ni de farmacia: más
      números = más conservador). Por número sí.
  - **R15b Alliance sin coincidencia de número:** solo casa por importe (PUC) con
    numeración interna de Farmatic (letra + 6 dígitos + `/` + año, p. ej.
    `Q039904/2026`). Cualquier otro número (formato Alliance distinto, SAFA de 12
    dígitos…) falla cerrado con estado `NUMERO_PROVEEDOR_DISTINTO`.
  - **R15c ventanas de fecha:** ±15 días con coincidencia de número; ±3 días sin ella
    (solo PUC, D11 se mantiene).
  - **R16 elegibilidad con tolerancia proporcional:**
    `cf_evaluar_elegibilidad_conciliacion` usa la regla de R11 con n = líneas sumadas
    (albaranes con importe + movimientos) en todas sus comparaciones. Sustituye a la
    tolerancia fija 0,05 de la elegibilidad.
  - **Reglas de numeración** (decisiones de Pio; `clase_numero` en la provenance de
    cada detalle):
    - `EXACTA`: mismo número normalizado;
    - `LETRA_FINAL` (solo Alliance): `08` + letra + 5 dígitos con una letra final
      sobre el número documental (`08C52171A` = `08C52171`);
    - `FINAL_DOCUMENTAL` (cualquier proveedor): número de Farmatic de 8 o más dígitos
      que es el final del documental (Logista `9319977575` ↔ `19977575`);
    - estas tres cuentan como coincidencia de número: ventana ±15, PUC o PVP y
      preferencia sobre las coincidencias solo por importe;
    - el número exacto se impone a la letra final y al final del documental;
    - varias coincidencias por letra final o final del documental que el importe no
      separa → no casa (la fecha no desempata);
    - `INTERNO`: numeración interna de Farmatic (ver R15b), casa por PUC a ±3 días;
    - `PROVEEDOR` (solo Alliance): otro número; nunca casa por importe;
    - `SIN_PATRON` (resto de proveedores): casa por PUC a ±3 días;
    - HEFAME conserva su ruta propia (número exacto e importe operativo).
  - **Lectura paginada:** las lecturas de albaranes, reservas y líneas extraídas usan
    `leer_paginado` (`range` hasta página vacía), porque PostgREST corta cada respuesta
    (1.000 filas por defecto).
  - **Orden de despliegue:** primero la 21 y después el código. El código 2BA sin la
    21 falla cerrado (no existe la tabla de reservas).
- Reglas de Pio del Hito 2BF (2026-10-28; `CONFIRMADO POR TEST` en PostgreSQL 17 local; migración 23
  **desplegada en producción** en el 2BF-D, 2026-10-29, y aplicada a 279410; diseño en
  `pruebas/auditoria_2bf/DISENO.md`):
  - **R18 resolución de revisiones de albaranes:** solo `CAMBIO_IDENTIDAD`, con aprobación de Pio registrada
    en BD (`albaranes_aprobaciones`: quién, cuándo, `IdContador`, cambio exacto). Se aplica solo si el
    cambio que Farmatic muestra ahora coincide exactamente con lo aprobado (equivalencia de identidad de la
    22: `btrim` y R9) y está registrado como revisión pendiente; si no, sigue en revisión sin escrituras.
    Nunca si el albarán está reservado (R15) o ausente. Solo los campos aprobados, con el literal de
    Farmatic, y con historial (`albaranes_aprobaciones_aplicadas`). Una aprobación se aplica una vez.
  - **R18b resincronización:** no registra de nuevo una revisión idéntica pendiente.
- Regla de Pio del Hito 2BE (2026-10-29; `CONFIRMADO POR TEST` en PostgreSQL 17 local; migración 24
  **desplegada en producción** en el 2BE-D, 2026-10-29, y aplicada a 08007969; diseño en
  `pruebas/auditoria_2be/DISENO.md`):
  - **R17 línea = albarán de su número + 1 interno de la misma recepción:** una línea documental (cargo) que
    no casa 1:1 puede casar con la suma de **dos** albaranes de la misma recepción de Farmatic
    (`albaranes.id_recepcion`):
    - el de su número, exacto o letra final (el exacto se impone), con ventana de ±15;
    - uno con numeración interna de Farmatic (`[A-Z]\d{6}/\d{4}`).

    Condiciones: ninguno reservado (R15) ni casado por otra línea; mismo proveedor (R9); PUC + PUC dentro de
    la tolerancia por línea (0,05). Solo 1+1. Ambos quedan reservados.
    - Falla cerrado: más de una pareja → `AMBIGUO_R17`; la misma pareja para dos líneas → `CONFLICTO_R17`.
    - Se persiste como dos detalles `UNO_A_VARIOS` con el mismo origen documental, y la BD los revalida
      (`cf_linea_r17_valida`, rechazo `LINEA_R17_NO_VALIDA`).
    - R11 cuenta la línea R17 como un albarán casado (confirmado por Pio en el 2BE-D).
    - No aplica a HEFAME ni a abonos.
    - Deuda menor aceptada por Pio (2BE-D): la BD no revalida la ventana de ±15 días ni que el interno no sea el
      número de una línea de otra factura; solo lo comprueba Python.
  - **Orden de despliegue:** primero la 24 y después conciliar con el código 2BE. Con la 23, una línea R17 se
    rechaza (`TOLERANCIA_REGLA_NO_COINCIDE`) y consume un intento.
- Regla de Pio del Hito 2BG (2026-10-30; `CONFIRMADO POR TEST`, sin migración; aplicada en producción en la
  conciliación de 08007970 el 2026-10-30; diseño en `pruebas/auditoria_2bg/DISENO.md`):
  - **R19 ECO360 = grupo Alliance/SAFA en conciliación:** el proveedor de Farmatic «6- PLATAF. ECO360 AH»
    (id 154, con R9) es siempre compra a Alliance/SAFA, sin excepciones, y pertenece al grupo
    Alliance/SAFA/Cencora: por nombre canónico y por id (154 ≡ 2). Ninguna otra plataforma se trata igual.
    - Se conservan los literales; se mantienen todas las reglas de numeración, ventanas y R15/R15b (nunca casa
      por importe con número de proveedor distinto).
    - R17 sigue exigiendo el mismo id con R9 (la BD lo revalida): ECO360 + interno SAFA no es pareja.
    - Solo conciliación: la resincronización de albaranes y la extracción no cambian.
- Reglas de Pio del Hito 2BI (2026-10-30; `CONFIRMADO POR TEST` en PostgreSQL 17 local; migración 25
  **desplegada en producción** en el 2BI-D, 2026-10-30; diseño en `pruebas/auditoria_2bi/DISENO.md`):
  - **Claims huérfanos de normalización:** un documento en `NORMALIZANDO` cuyo lock caducó hace más de la
    gracia (30 min; mínimo 15) se recupera solo con el script one-shot `recuperar_huerfanos.py`, con
    confirmación de Pio y guard por documento (RPC `cf_recuperar_claim_huerfano_normalizacion`).
    - Huérfano limpio: fallo `TRANSITORIO` `CLAIM_HUERFANO` mediante `cf_registrar_fallo_normalizacion`
      (cuenta como intento, R3: backoff y `REVISION` al 4.º).
    - Con cualquier señal de persistencia parcial (`estado_persistencia ≠ PENDIENTE`, facturas enlazadas,
      ejecuciones o eventos posteriores al claim): `REVISION`, sin reencolar ni tocar nada más.
    - Idempotente (`NO_APLICA`). Un worker que siga vivo ya no puede persistir: falla cerrado.
    - Sin cambios en el claim, el selector ni la persistencia (R4).
  - **Worker de normalización:** `worker_id` único por ejecución; Ctrl+C y `SystemExit` registran el fallo
    antes de relanzarse.
  - Conciliación: sin recuperación propia (2AT: el claim no cambia de estado, el lock caduca y el guardado
    es atómico desde la 18).
- Reglas de Pio del Hito 2BJ (2026-10-30; `CONFIRMADO POR TEST` en PostgreSQL 17 local; diseño en
  `pruebas/auditoria_2bj/DISENO.md`):
  - **Serie supervisada de normalización** (`pruebas/auditoria_2bj/serie_normalizacion.py`):
    - tandas de `ejecutar_una_manual()` (cada una, un documento `MANUAL_ONE_SHOT`, sin flags): 5 la primera y
      luego hasta 20;
    - corte al persistir cada Alliance;
    - ejecuta Claude con confirmación expresa de Pio **por tanda**;
    - plan READ_ONLY previo con la predicción de cada documento.
  - **PARADA ante cualquier desviación del plan:** excepción, huérfano, resultado o facturas distintos, fila
    ajena cambiada, n.º 1 fuera del plan o sin predicción, o puerta fallida. Se aplica el postcheck 2AX por
    fila de cada tanda.
  - Los defectos de extracción previstos por el plan consumen intentos (R3) y no son parada.
  - Conciliación posterior: un n.º 1 que simula DIFERENCIA → PARADA y Pio decide caso a caso (serie de
    conciliación **no implementada**).
- Clasificación de Pio para el futuro hito COFARES (**NO implementada**):
  - total de devoluciones = abono;
  - servicio integral de distribución = cargo sin albarán;
  - domiciliación bancaria = cargo sin albarán;
  - desglose del recargo de equivalencia obligatorio.
- La RPC multifactura autorizada tiene siete parámetros, incluido
  `p_disparador`. La firma antigua de seis no está autorizada para `service_role`.
- Los disparadores permitidos son `AUTOMATICO`, `REPROCESADO` y
  `MANUAL_ONE_SHOT`.
- Una diferencia documental nunca genera automáticamente movimientos, sentidos,
  categorías ni explicaciones.
- Las relaciones con Farmatic conservan el identificador literal de proveedor; no
  se coacciona a número ni se normaliza destructivamente.
- En conciliación, SAFA, Alliance y Cencora (y ECO360 por R19, 2BG) pueden canonicalizarse dentro del grupo
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

- **Criterio de postcheck de privilegios (Pio, Hito 2AX, 2026-09-29)** para todo
  despliegue futuro: (1) producción antes vs después: solo cambian los objetos
  del alcance de la migración; (2) los objetos del alcance quedan iguales a la
  referencia local; (3) los objetos fuera de alcance quedan idénticos antes y
  después. Cualquier otra diferencia → PARAR (sin rollback sin confirmación de
  Pio). Las diferencias conocidas del baseline local fuera de alcance no son
  motivo de parada si cumplen (3).
- **Preflight de propietarios (2AX):** ningún objeto de `public` con propietario
  distinto de `postgres`; si aparece → PARAR.
- **Norma de Pio (Hito 2AX, 2026-09-28):** todo script de despliegue productivo
  se ensaya COMPLETO en local antes de usarlo en producción: de principio a fin
  (verificación de SHA contra el commit, precondiciones, aplicación, commit y
  registro) contra un PostgreSQL 17 local que reproduzca la matriz y los
  privilegios de producción, más un segundo ensayo que debe fallar en
  precondiciones y revertir sin cambios. Además, su consulta de precondiciones
  se ejecuta antes en producción en una transacción READ_ONLY. Motivo: el primer
  intento de desplegar la 19 falló por un `select` omitido en las precondiciones
  (sin cambios en producción). Referencia:
  `tests/facturas/runtime_supabase/test_ensayo_despliegue_19_2ax.py`.
- **Norma de Pio (Hito 2BN-D, 2026-11-05): todo ensayo de despliegue usa un rol que imita al `postgres` de
  Supabase**, nunca un superusuario: LOGIN, `CREATEROLE`, `REPLICATION`, `BYPASSRLS`, **sin** `SUPERUSER`, con
  los privilegios de propietario de `public` (miembro de `postgres` con herencia y sin poder adoptarlo).
  Helper: `pg17_local.rol_supabase` / `sql_como_supabase` (rol `cf_postgres_supabase`); la conexión del ensayo
  del script de despliegue y el rollback se hacen con ese rol. Motivo: el primer despliegue de la 29 se revirtió
  en producción por un `ALTER ROLE … NOSUPERUSER` que local aceptaba como superusuario. Se aplica a los
  despliegues pendientes desde el 2BN-D (los ya desplegados no se reensayan).
- **Norma de Pio de tests antes de commit (Hito 2BE-D, 2026-10-29), sin excepciones:**
  - **suite completa con `pg17_local`** (`pytest tests/ --basetemp=<propio>`, con Docker disponible: ningún
    test `pg17_local` omitido) si el commit toca `src/`, `sql/`, scripts de despliegue o cualquier código que
    acceda a Supabase o Farmatic, también las herramientas de `pruebas/`;
  - si solo toca documentación: **suite rápida** (`pytest tests/ -m "not pg17_local" --basetemp=<propio>`);
  - en la duda: suite completa.
  - La suite exigida se ejecuta sobre el estado exacto que se commitea y debe quedar en verde (0 failed,
    0 errors).
  - **Evidencia mecánica (Hito 2BH, 2026-10-30):** cada ejecución de pytest añade una línea a
    `logs/agentes/suites.jsonl` (`tests/registro_suite.py`) con la huella exacta del árbol probado (la de la
    barrera de commit, calculada al empezar y al terminar), passed/failed/errors/skipped, fechas, alcance
    (`completa`, `rapida` o `parcial`) y `verde`. «Documentación» = ficheros `.md` fuera de `.claude/`.
    - La **barrera de commit** exige una línea con la huella actual, alcance suficiente y en verde
      (`commit_sin_suite`, `commit_suite_roja`).
    - `revisor-reglas` (T2) lee ese registro y comprueba una línea con `base` = HEAD, `rutas` = `git status`,
      alcance suficiente y `verde`.
    - Ya no basta con declarar la suite en el encargo.
    - **Excepción de Pio (2026-11-02):** un FAIL de `revisor-reglas` cuya **única** regla fallida es T2 no
      bloquea el commit si hay un PASS posterior de la misma huella (y la suite registrada sigue exigida).
      Cualquier otro FAIL, o un FAIL sin el detalle de reglas registrado (solo se registra si la tabla trae
      las 14 reglas, cada una una vez y con un resultado reconocido), sigue bloqueando. Hooks:
      `registrar_uso_agente.py` (`reglas_fail`) y `estado_git.py` (`_veredicto_grupo`).
- Pytest debe usar directorios temporales mediante `CONTROLFARMACIAS_LOG_DIR` y
  `CONTROLFARMACIAS_DATA_DIR`.
- Los tests no pueden conectarse a Farmatic/Supabase reales ni escribir en
  `logs/` o `data/` productivos. Única excepción (2BH): el ejecutor de pytest, no un test, añade la línea de
  la ejecución a `logs/agentes/suites.jsonl`.
- Una suite verde demuestra solo lo cubierto por sus tests; no amplía autoridad
  productiva ni resuelve reglas funcionales pendientes.
