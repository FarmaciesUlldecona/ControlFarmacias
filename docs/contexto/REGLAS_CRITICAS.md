# Reglas críticas

Actualizado: 2026-11-22 (presentaciones de la web, decisiones de Pio: HPLUS CONSUMO = HEFAME solo como nombre comercial y decisión 6A, albaranes de PIO de `4.- FFARMACIA RITA` como traspasos sin factura, aparte y sin alerta; 38-B, decisiones de Pio: categoría nueva = ausente de toda importación OK anterior de esa cuenta, y C7 «Cashflow no en ejecución» en la puerta de la noche y de los preflights; 38-B: script de importación de Cashflow implementado en local, sin ejecutar contra producción, con la RPC de la 38 como única escritura, C5 sin escribir nada hasta la manual y la tarea de las 23:45 sin crear; H7-D: migración 38 de Cashflow desplegada en producción, confirmación explícita de Pio, y prueba de acceso de cf_lectura ACCESO_OK; H7: migración 38 de Cashflow implementada en local, con RPC de solo inserción, cuadre sin margen por saldo y `TABLAS_CASHFLOW` en los postchecks, decisiones de Pio; 2026-11-21, 37-D: migración 37 desplegada en producción, confirmación explícita de Pio; migración 37: defectos de extracción directos a `REVISION`, implementada en local, decisiones de Pio D1–D7, con la autorización expresa para nombrar el rol del sistema solo en la 37 y su rollback; 2026-11-20, Hito SUITE: suite paralela con pytest-xdist 3.8.0 y 8 workers, suite histórica, regla de reparación y barrera de despliegue, decisiones de Pio D1–D8, con excepciones expresas para los ficheros que nombran el registro de suites; 2026-11-19, 36-D: migración 36 desplegada en producción, confirmación explícita de Pio; HEFAME: liquidaciones comerciales como `ABONO` y números `91…` por numeración interna, decisiones de Pio H3/H4; R20: migración 36 implementada en local, con la marca `conciliacion_r20` y la ventana de ±15 días en la BD, decisiones de Pio; numeración R20 = 36, defectos = 37, Cashflow = 38, y autorización C3 reconfirmada solo para la 38, decisión de Pio; puerta git con el main leído del remoto con `ls-remote` en la noche, 2BJ, 2BP y
despliegues, que exigen el commit ya subido; el revisor lee con Read los ficheros de src/, sql/, tests/ y pruebas/ que
cita el diff, decisión de Pio; 2026-11-18, HEFAME: cargo cooperativo de 80,00 y `APROAFA` como `CARGO`, decisiones de Pio H1/H2, con H6/H7; AUTO-ON: automatización Alliance en modo `REAL`, confirmación explícita de Pio, y vuelta
atrás con los flags; 2026-11-17, H6-D: migración 35 desplegada en producción y prueba de acceso de `cf_pagos_web`
`ACCESO_OK`; decisiones de Pio para Cashflow (H7): excepción de RITA solo con sus datos bancarios, lista cerrada de
`cf_lectura` ampliada a `cf_cashflow_*` con la migración 38 (renumerada), estado de importación y signo del importe; H6: migración 35 de Pagos, marcas de pago y forma de pago por proveedor, solo local, y
autorización de Pio para nombrar el rol del sistema solo en la 35 y su rollback; 2026-11-16, COD-1611: tablas de Pagos
fuera del veredicto de los postchecks y tarea de Alliance en la puerta de tareas; migración 34 desplegada en producción, hito TRAB-34-D; TRAB-34: migración 34 de
Trabajadores, guardias y festivos de TA3, solo local, y
autorización de Pio para nombrar el rol del sistema solo en la 34 y su rollback; 2026-11-15: migración 33
desplegada en producción, hito TRAB-33-D; 2026-11-14: migración 33 de
Trabajadores, solo local, y autorización de Pio para nombrar el rol del
sistema solo en la 33 y su rollback; decisiones de Pio: R10 ampliada con `ENCARGO`, adaptador Alliance 1.3.1 y autoridad D1
en 1.3.1; veredicto INCONCLUSO del revisor; 2026-11-13: excepción existente y cerrada de `pg17_local.py` para emular la API de Supabase en la base local de tests, decisión de Pio; 2026-11-12, AUTO-A: automatización Alliance solo local, migración 32 y autorización de Pio para nombrar el rol del sistema solo en la 32 y su rollback; D1 de AUTO-ALLIANCE implementada solo en local, no activada; contraseñas de roles siempre con SCRAM, decisión de Pio; Trabajadores: migración 31 desplegada en producción, hito TRAB-D; LOCALIZADA y TURNO_GUARDIA no computan; decisiones de Pio: RITA habilitada solo para el esquema de Trabajadores, rol de escritura de la web limitado a Trabajadores, fichajes de Farmatic pospuestos; 2026-11-10, 2BS: huecos de barreras_agentes, incidente de la sesión WEB-COMMIT y segundo incidente como ejemplos prohibidos, regla permanente sobre nombrar el rol del sistema, R9 de lectura ampliada a cualquier presentación de la web; 2BR-D: decisión de Pio, opción A, relleno de las conciliaciones de septiembre con la fórmula única; 2BP: serie supervisada de conciliación, solo local; decisiones de Pio sobre el 2BR; 2BR: detalle por línea en la conciliación, migración 30, solo local; decisiones de Pio: sentido de vencimientos desde datos_extraidos.tipo_documento.valor; R9 de solo lectura para la web; 2BQ: excepción expresa de Pio para nombrar el rol del sistema en dos ediciones de staging; exclusión de los esquemas internos de Supabase en la comparación con la referencia local; 2BN-D: aclaración de la norma de hooks, forma documentada permitida; ensayos de despliegue con el rol que imita al postgres de Supabase; puerta git con excepción documental, decisión de Pio; 2BK-D: barrera de commit con
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
- **Contraseñas de roles de base de datos (DECISIÓN DE PIO, 2026-11-12, TRAB-D):** se fijan **siempre** con SCRAM
  (`set password_encryption = 'scram-sha-256'` en la misma sesión, antes del `alter role … password`); el pooler
  de Supabase rechaza otro formato. Las fija Pio, fuera del repositorio; nunca en el repositorio, en argumentos,
  en el chat ni en salidas. Tras fijarla o cambiarla, prueba de acceso por el pooler.
- Solo PIO está autorizada. Una identidad de farmacia ausente, contradictoria o no
  demostrable bloquea la persistencia.
  **Excepción por módulo (DECISIÓN DE PIO, 2026-11-12, Trabajadores):** RITA está habilitada **SOLO** para el
  esquema de Trabajadores (trabajadoras, convenio, calendario, guardias y festivos). Facturas, albaranes,
  normalización y conciliación siguen **solo PIO**: `cf_configuracion.farmacias_habilitadas` no cambia
  (`{PIO}`) y el permiso de farmacia de Trabajadores es propio del módulo, nunca global. Ver «Trabajadores».
  **Excepción Cashflow (DECISIÓN DE PIO, 2026-11-17):** RITA es visible en el módulo CASHFLOW **SOLO** con sus
  datos bancarios del Excel importado; sus facturas siguen desactivadas. Ver «Cashflow (H7)».
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
  **Excepción expresa de Pio (2026-11-06, Hito 2BQ, una sola vez):** el hook bloqueó un comando que escribía el
  nombre del rol del sistema; Pio autorizó usar Edit SOLO para dos ediciones de la base local de tests
  (`sql/staging/`): los GRANT de EXECUTE sobre cuatro funciones en `08_supabase_alineacion.sql` y el rol del sistema
  en `grant usage on schema public` de `00_baseline_controlfarmacias.sql`. Motivo: alinear la base local con Supabase
  (0 diferencias frente a producción). Nunca en migraciones, scripts de despliegue, preflights ni nada que conecte a
  producción. Cualquier otra edición que nombre ese rol requiere autorización nueva.
  **Ejemplo prohibido (incidente de la sesión WEB-COMMIT, Hito 2BS, 2026-11-10):** tras dos bloqueos, el agente
  leyó `logs/agentes` con Glob y buscó la clave del sistema con otro patrón (separador cambiado). Se comprobó
  que no hubo exposición de claves. **Cambiar de herramienta o de patrón para obtener lo bloqueado está
  PROHIBIDO**, aunque la herramienta nueva no esté bloqueada. Desde el 2BS, `barreras_agentes.py` cierra esos
  huecos: `logs/agentes` no se lee, busca ni escribe con ninguna herramienta, y la clave del sistema se
  detecta en texto normalizado (sin mayúsculas, separadores ni comodines, más los nombres de sus variables) en
  rutas, patrones, comandos y URL de todas las herramientas.
  **Segundo incidente (Hito 2BS, 2026-11-10; DECISIÓN DE PIO):** el hook bloqueó un comando de Bash que aplicaba
  al propio hook un parche que nombraba el rol del sistema, y el agente hizo las mismas ediciones con Edit.
  Pio las autorizó a posteriori. **Aunque el contenido sea legítimo: PARA y pide autorización ANTES, nunca
  después.**
  **Regla permanente (Pio, 2026-11-10, 2BS):** el mantenimiento de la barrera puede nombrar el rol del sistema
  SOLO en `.claude/hooks/barreras_agentes.py` y `tests/test_hook_barreras_agentes.py`, y SOLO si la orden de
  Pio lo indica expresamente. Cualquier otro fichero: autorización nueva.
  **Excepción existente (DECISIÓN DE PIO, 2026-11-13):** `tests/facturas/runtime_supabase/pg17_local.py` usa el rol
  del sistema para emular la API de Supabase en la base local de tests. Es imprescindible y queda cerrada: cualquier
  mención nueva del rol, en ese fichero o en otro, requiere autorización nueva.
  **Regla permanente (Pio, 2026-11-10, 2BS):** la documentación (`docs/*.md`) puede nombrar `logs/agentes` y el
  registro de suites como TEXTO para documentar la barrera. Buscarlos en comandos de shell sigue bloqueado y
  nada se lee ni se escribe dentro de `logs/`.
- **Puerta git antes de una ejecución productiva (tandas de la serie, despliegues).** Árbol siempre limpio y
  HEAD == `origin/main`. **Excepción acotada (DECISIÓN DE PIO, 2026-11-05):** HEAD puede ir por delante de
  `origin/main` solo si los commits pendientes tocan exclusivamente documentación (`docs/` o `*.md`); se
  comprueba antes de cada tanda con `git diff --name-only origin/main..HEAD`. Cualquier otro archivo: PARA.
  **El main del remoto se lee del remoto (encargo de Pio, 2026-11-19):** la noche, las series 2BJ y 2BP y los
  despliegues usan el módulo común `src/facturas/runtime_supabase/puerta_git.py`, que lee el main con
  `git ls-remote origin refs/heads/main` (20 s como máximo, sin pedir credenciales) y no la referencia local
  `origin/main`, que sin fetch podía dar un falso OK (el 18/11 seguía en 885150d con 1ca8cc3 ya subido). Falla
  cerrado: remoto ilegible → `GIT_ORIGEN_NO_DETERMINABLE`; sha del remoto que no existe en local (falta un fetch) →
  `GIT_ORIGEN_DESCONOCIDO_LOCALMENTE`; el remoto debe ser ancestro de HEAD y lo pendiente solo documentación. La
  puerta no hace fetch ni cambia referencias. El informe de la noche registra head, origin_local y origin_remoto.
  **Despliegues:** el commit indicado debe estar ya contenido en el main del remoto (subido por Pio); si no,
  `GIT_COMMIT_NO_SUBIDO` y no se conecta (scripts `desplegar_31` a `desplegar_35` y los siguientes).
  **revisor-reglas (DECISIÓN DE PIO, 2026-11-18):** además del diff, REGLAS_CRITICAS y los ficheros que toca el diff,
  puede LEER (solo con Read) los ficheros de `src/`, `sql/`, `tests/` y `pruebas/` que el diff cite por su ruta;
  `logs/`, `.env*` y el resto siguen bloqueados.

## Extractores locales

- Todos los adaptadores registrados son habilitables para shadow, pero ninguno
  tiene autoridad productiva en el registro global
  `AUTORIDADES_EXTRACTORES_LOCALES`.
- Excepción acotada (Hito 2AP, 2026-09-24, `CONFIRMADO POR CÓDIGO` y
  `CONFIRMADO POR TEST`, sin ejecución productiva): el compositor manual
  `runtime_supabase/compositor_manual.py` concede autoridad solo a Alliance
  (`alliance-local`) mediante `AUTORIDAD_COMPOSITOR_MANUAL`, que exige puente
  multifactura certificado. Solo se usa con `ejecutar_una_manual()` y ningún
  scheduler lo ejecuta; la ruta automática reutiliza sus piezas solo a través del
  compositor automático (ampliación D1, debajo). Cualquier otro proveedor falla
  cerrado.
  **Ampliación (DECISIÓN DE PIO, 2026-11-12, D1 del Hito AUTO-ALLIANCE; diseño en
  `pruebas/auditoria_auto_alliance/DISENO.md`):** la ruta automática puede tener
  autoridad de extracción **solo para Alliance** y **solo su versión certificada**
  (`alliance-local` con puente multifactura certificado), mediante un compositor
  automático que reutiliza esa misma autoridad; cualquier otro proveedor, layout o
  versión falla cerrado (R2). **IMPLEMENTADA SOLO EN LOCAL** (Hito AUTO-A,
  2026-11-12, `CONFIRMADO POR TEST` en PostgreSQL 17 local:
  `runtime_supabase/compositor_automatico.py`, autoridad `alliance-local` 1.3.0, y
  el orquestador `runtime_supabase/noche_automatica.py`). **Versión certificada
  actualizada (DECISIÓN DE PIO, 2026-11-14):** `alliance-local` **1.3.1** (R10 con
  `ENCARGO`); la 1.3.0 ya no tiene autoridad en la ruta automática. **ACTIVADA EN AUTO-ON
  (CONFIRMACIÓN EXPLÍCITA DE PIO, 2026-11-18):** la tarea de las 22:15 ejecuta el orquestador en
  modo `REAL`; los flags `normalizacion_automatica` y `conciliacion_automatica` los enciende
  Pio en el editor SQL y son el interruptor general (ver «Automatización Alliance»).
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
| HEFAME | Declara controles documentales entre detalle, pedidos, servicios operativos, fiscalidad, total y vencimiento. Una diferencia solo produce resultado de control; no crea explicaciones ni movimientos, salvo estas dos decisiones funcionales explícitas de Pio (2026-11-18, `pruebas/auditoria_hefame/DISENO.md` §0): el desfase de 80,00 de base S.R. de la factura de fin de mes es el **cargo cooperativo HEFAME**, fijo cada mes (H1), y `APROAFA` (aportación a la Asociación para la Promoción de la Asistencia Farmacéutica en España) es `CARGO` (H2). Un desfase distinto de 80,00, en otra clase, negativo o fuera del fin de mes, y un `APROAFA` negativo, fallan cerrados (H6, H7). Decisiones de Pio del 2026-11-19: `Resumen Liquidaciones Comerciales` son pequeños descuentos sobre especialidad (IVA 4 %, base S.R.) y son `ABONO` (H3); los números de 9 dígitos que empiezan por `91` son albaranes normales que Farmatic registra con numeración interna `Q…`/`R…`, y casan por numeración interna, importe y fecha con candidato único, como R15b (H4). La autoridad productiva de `hefame-local` sigue desactivada. |
| COFARES | La elegibilidad local exige documento monopágina, segmentación determinista, filas completas y únicas, columnas inequívocas y evidencia integral. El sentido literal ausente no se infiere. El descuento por pronto pago sigue como gap funcional. |
| Guimerà | Dispone de adaptadores OCR actual e histórico; el OCR solo se reintenta ante `PENDIENTE_OCR`. El routing no usa filename ni hash. |
| DERMOFARM | Conserva evidencia y no inventa importes. La relación de abonos descontados en la primera factura del mes siguiente sigue pendiente de decisión funcional. |
| Suavinex | Conserva cuota IVA+RE agregada, vencimiento y punto verde documentados. Cualquier regla de albarán único debe ser explícita, nunca inferida. |
| Ecoceutics, Eports, Logista Pharma, L'Oréal, Moretti y Totalcare | Existen adaptadores locales basados en layouts certificados del corpus. Su presencia no autoriza generalizar a layouts no certificados ni inferir naturaleza o sentido solo por proveedor. |
| HPlus Consumo / Gas Casa / Pierre Fabre | Las clasificaciones y relaciones deben salir del contenido visible y de reglas aprobadas; el proveedor por sí solo no determina naturaleza, conciliación ni sentido. HPlus Consumo se muestra en la web como HEFAME, solo como nombre comercial (decisión de Pio, 2026-11-22; ver R9 en «Persistencia y conciliación»). |

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
- **Migración 37: defectos de extracción directos a `REVISION`** (DECISIONES DE PIO D1–D7, 2026-11-15, 2026-11-18
  y 2026-11-19; diseño en `pruebas/auditoria_37/DISENO.md`). `CONFIRMADO POR TEST` en PostgreSQL 17 local y
  **desplegada en producción** en el 37-D, 2026-11-21, con confirmación explícita de Pio (`APLICADA`, postcheck por
  fila OK; ver ESTADO_ACTUAL). Rige la R3 revisada.
  - **R3 revisada (con la 37 en la BD):** `DEFECTO_DOCUMENTO` suma un intento (D4) y pasa a `REVISION` en el
    primer fallo, sin espera; el historial lo marca con `regla: DEFECTO_DIRECTO_A_REVISION`. `TRANSITORIO` y
    `NO_SOPORTADO`, sin cambios. Sin la 37 rige la R3 de la 17.
  - **Motivos (D5):** lista A, de extracción (15 motivos y el código `ErrorCompletitudDocumental`), y lista B, de
    identidad de farmacia (`FARMACIA_DOCUMENTO_NO_DEMOSTRABLE`, `FARMACIA_DOCUMENTO_CONTRADICTORIA` y el código
    `ErrorFarmaciaDocumental`): `DEFECTO_DOCUMENTO`. Lista C, de almacenamiento (`SHA256_NO_COINCIDE`,
    `SHA256_REGISTRADO_INVALIDO`, `OBJETO_STORAGE_VACIO`, `DOCUMENTO_RECLAMADO_NO_LOCALIZADO`,
    `RUTA_STORAGE_NO_COINCIDE_CON_CLAIM`, `RUTA_STORAGE_NO_SEGURA`): `TRANSITORIO`, con reintentos y espera. Un
    motivo nuevo solo pasa a defecto con una decisión de Pio.
  - **Lector (D2, D6):** columna `normalizacion_ejecuciones.lector` (adaptador, versión y layout del extractor
    autorizado; layout null si el fallo es anterior a reconocerlo; null en las ejecuciones anteriores a la 37). Llega
    por un 8.º parámetro `p_lector` de `cf_registrar_fallo_normalizacion`. La firma de 7 parámetros se conserva y
    llama a la de 8 con el lector null.
  - **El código usa el 8.º parámetro solo si detecta la 37** con una sesión de solo lectura (catálogo:
    `lectura_readonly.defectos_37_en_bd`), como R20; sin ella, la llamada de 7 parámetros de siempre.
  - **Reprocesado:** un documento en `REVISION` por defecto solo vuelve a la cola con `cf_solicitar_reprocesado`,
    acción de Pio, cuando cambie el lector (§3 del diseño). Nunca automático. Los 22 en `REVISION` de antes de la
    37 esperan a ese cambio (D3).
  - **AUTORIZACIÓN EXPRESA DE PIO (2026-11-19, D7):** nombrar el rol del sistema **solo** en
    `sql/migrations/37_cf_defectos_directos_a_revision.sql` y su rollback, para el EXECUTE de la firma nueva.
    `desplegar_37.py` lo comprueba sin nombrarlo (mismos beneficiarios que la firma de 7 parámetros y nada para
    anon, authenticated ni PUBLIC). Tests, scripts y documentación no lo nombran; cualquier otro fichero,
    autorización nueva.
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
    **Decisión de Pio (2026-11-08):** fuera de `buscar_candidato_albaran` y de los usos aprobados en R17, R18 y
    R19, la R9 solo se permite como uso de LECTURA para mostrar en la web (agrupar proveedores sin CIF y detectar posibles duplicados en Farmatic).
    Sin efecto en datos ni en conciliaciones: no escribe, no cambia literales ni decide casamientos.
    **Ampliación (DECISIÓN DE PIO, 2026-11-10, 2BS):** la web puede usar la R9 para CUALQUIER presentación de
    solo lectura: por ejemplo, agrupar proveedores sin CIF, avisar de duplicados en Farmatic o mostrar notas
    como «ECO360 = Alliance». **Nunca** para decidir casamientos ni para cambiar datos.
    **Presentaciones de la web (DECISIONES DE PIO, 2026-11-22; la web ya las aplica):**
    - **HPLUS CONSUMO = HEFAME** solo como nombre comercial en la web: son bolsas de papel compradas a Hefame. No
      cambia el motor, la extracción, la normalización ni la conciliación, y no autoriza a casar documentos de uno
      con albaranes del otro.
    - **Decisión 6A:** los albaranes de Farmatic de PIO con proveedor `4.- FFARMACIA RITA` son traspasos entre
      farmacias, sin factura. La web los muestra aparte y **nunca como alerta** (por ejemplo, de albarán sin
      factura). No cambia la conciliación ni habilita a RITA: siguen siendo albaranes de PIO.
- Reglas aprobadas por Pio en el Hito 2AZ (2026-10-06/07; `CONFIRMADO POR TEST` en
  PostgreSQL 17 local; migración 20 `CONFIRMADO EN PRODUCCIÓN`, desplegada en el
  Hito 2AZ-D el 2026-10-08; diseño en
  `pruebas/auditoria_2az/DISENO.md`):
  - **R10 tipos de pedido Alliance** (adaptador 1.3.0; **1.3.1** desde el 2026-11-14):
    - Mercancía (se promueve; la prueba de recepción es el cruce con
      `Supabase.albaranes`): `DIRECTO`, `ENCARGO VACUNAS`, `MIS RESERVAS`,
      `TELEVENTA 2`, `COSTO TELEVENTA` y `SERVICIO COVID19`, además de los ya
      certificados.
    - **Ampliación (DECISIÓN DE PIO, 2026-11-14; adaptador 1.3.1):** `ENCARGO` a secas (literal exacto) es
      mercancía en el bloque CARGOS (caso 08012619 / 08D50803). En ABONOS no está certificado. Banco Alliance
      completo 1.3.0 frente a 1.3.1: solo cambian las filas `ENCARGO` (08D50803 en 08012619 y 08E58484 en 08016545);
      diseño y evidencias en `pruebas/auditoria_encargo/DISENO.md`. Los documentos ya persistidos no se vuelven a
      normalizar: el camino es R12, con confirmación de Pio por factura.
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
- Regla de Pio R20 (DECISIÓN DE PIO, 2026-11-19; `CONFIRMADO POR TEST` en PostgreSQL 17 local; migración 36
  **desplegada en producción** en el 36-D, 2026-11-19, con confirmación explícita de Pio; diseño en
  `pruebas/auditoria_r20/DISENO.md`; origen: 08013495 / 08D79747):
  - **R20 línea = su albarán exacto + su variante con letra final:** una línea documental (cargo) que queda sin
    casar tras el 1:1 y R17 puede casar con la suma de **dos** albaranes de la misma recepción: el de su número
    **exacto** y su variante con **una letra final** (`08X99999` + `08X99999A`), los dos a ±15 días de la línea.
    - Mismas condiciones que R17: ninguno reservado (R15) ni casado por otra línea, y el número de la variante no es
      una línea de otra factura; mismo proveedor (R9); PUC + PUC dentro de 0,05; solo 1+1; solo cargos; nunca HEFAME
      ni abonos. En la práctica, solo Alliance (la letra final solo se define para Alliance).
    - Falla cerrado contando juntas las parejas R17 y R20 de una línea: más de una → `AMBIGUO_R17`/`AMBIGUO_R20`; un
      albarán en las parejas de dos líneas → `CONFLICTO_R17`/`CONFLICTO_R20`.
    - Se persiste como dos detalles `UNO_A_VARIOS` (`regla: R20`). La BD los revalida en `cf_linea_r17_valida`,
      redefinida por la 36 sin regenerar la RPC; el rechazo sigue siendo `LINEA_R17_NO_VALIDA`. **En R20 la BD sí
      comprueba la ventana de ±15 días** (decisión de Pio). R11 cuenta la línea como un albarán casado.
  - **Marca y conmutador:** `cf_configuracion.conciliacion_r20` (default `true`). El código usa R20 solo si la
    detecta en la BD, con una sesión de solo lectura (`information_schema` y, solo si la columna existe, su valor). Sin
    la 36, o con la marca a `false` (apaga R20 sin rollback), la línea sigue sin casar y la noche deja la factura para
    revisar, sin reclamarla ni gastar intentos. Por eso el código puede subirse antes de desplegar la 36.
  - **Primera conciliación tras el despliegue (36-D):** 08013495 la hace la noche (decisión de Pio).
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
  - Los defectos de extracción previstos por el plan no son parada. Con la 37 en la BD pasan a `REVISION` en el
    primer fallo; sin ella, consumen intentos (R3 de la 17).
  - Conciliación posterior: un n.º 1 que simula DIFERENCIA → PARADA y Pio decide caso a caso (serie de
    conciliación **no implementada**).
- Diseño del Hito 2BR (2026-11-09; `CONFIRMADO POR TEST` en PostgreSQL 17 local; migración 30 **desplegada en
  producción** el 2026-11-10, 2BR-D, `APLICADA` con postcheck 2AX OK, ver ESTADO_ACTUAL; diseño en
  `pruebas/auditoria_2br/DISENO.md`):
  - **Detalle por línea:** cada detalle guarda el importe del PDF (con signo), el de Farmatic (el aplicado), la
    diferencia y el estado de **su línea**; tolerancia por línea 0,05. Sin coincidencia → `DIFERENCIA`; sin importe
    documental o movimiento sin contraparte en Farmatic → `NO_EVALUABLE` (**DECISIÓN DE PIO, 2026-11-09:** los
    movimientos, `NO_EVALUABLE`). R17: la misma diferencia y estado en los dos detalles.
  - El resultado de la factura no cambia. La BD calcula los valores (`cf_detalles_por_linea`) y rechaza
    `DETALLE_LINEA_NO_COINCIDE` si el resultado trae otros.
  - **Orden de despliegue (DECISIÓN DE PIO, 2026-11-09):** primero desplegar la 30 y después conciliar.
  - **Clave idempotente (DECISIÓN DE PIO, 2026-11-09):** aceptado que cambie respecto del código anterior (el resultado
    lleva los valores por línea): una reevaluación con el código nuevo de una conciliación del anterior es intento
    nuevo, no replay.
  - **Relleno de las conciliaciones de septiembre (DECISIÓN DE PIO, 2026-11-10, 2BR-D, opción A):** se rellenan las
    17 conciliaciones con la fórmula única, también los 744 detalles de las 12 de septiembre (anteriores a la 24) que
    ya tenían importes por línea. Sus valores antiguos van a `conciliacion_detalles_previo_30` (rollback exacto);
    `provenance` no se toca (el `estado_matching` antiguo queda intacto). La precondición 3 de `desplegar_30.py`
    exige exactamente esos 744 detalles, de esas 12 conciliaciones, con su huella; cualquier otro dato → PARA.
- Reglas de Pio del Hito 2BP (2026-11-09; `CONFIRMADO POR TEST` en PostgreSQL 17 local; diseño en
  `pruebas/auditoria_2bp/DISENO.md`):
  - **Serie supervisada de conciliación** (`pruebas/auditoria_2bp/serie_conciliacion.py`), mismo esquema que la 2BJ:
    - plan READ_ONLY con la simulación de cada factura pendiente en el orden del selector, en cadena (R15), con el
      resultado previsto (`CONCILIADA` / `DIFERENCIA` y cuánto);
    - tandas de `ejecutar_una_manual_conciliacion()` con confirmación de Pio por tanda (5 la primera, luego hasta 20) y
      puertas git, de operación y de tareas;
    - **exige la migración 30 desplegada** antes de cada ejecución;
    - **PARADA si el n.º 1 simula DIFERENCIA** (o un fallo): Pio decide caso a caso (`decisiones_pio` del plan, para
      esa factura y esa diferencia);
    - PARADA ante cualquier desviación del plan; postcheck 2AX por fila, también al parar.
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
- **Sentido de los vencimientos (decisión de Pio, 2026-11-08):** se toma de
  `datos_extraidos.tipo_documento.valor`, NUNCA de la columna `tipo_documento`. `FACTURA` o
  `FACTURA_DUPLICADO` = cargo; `ABONO` = abono; `FACTURA_RECTIFICATIVA`, vacío u `OTRO` = no documentado (no se
  suma en el cashflow).
- Las relaciones con Farmatic conservan el identificador literal de proveedor; no
  se coacciona a número ni se normaliza destructivamente.
- En conciliación, SAFA, Alliance y Cencora (y ECO360 por R19, 2BG) pueden canonicalizarse dentro del grupo
  funcional autorizado. `CONFIRMADO POR CÓDIGO` y `CONFIRMADO POR TEST`,
  2026-09-24. Esto no crea un extractor SAFA: **extracción ≠ conciliación**.

## Trabajadores

Decisiones de Pio (2026-11-12, chat de la web, y respuestas a las 10 preguntas del diseño). Diseño en
`pruebas/auditoria_trab/DISENO.md` (OK final de Pio; migración 31 `CONFIRMADO POR TEST` y **desplegada en
producción** el 2026-11-12, hito TRAB-D, `CONFIRMADO EN PRODUCCIÓN`; ver ESTADO_ACTUAL).

- **Farmacias:** PIO y RITA, solo en este módulo (excepción por módulo de «Seguridad y operación»). Los tests
  demuestran que facturas, albaranes y conciliación siguen solo PIO.
- **Rol de escritura de la web en Trabajadores limitado EXCLUSIVAMENTE a sus tablas:** credencial propia (nunca la
  del sistema ni la de `cf_lectura`); `SELECT`, `INSERT` y `UPDATE` solo sobre las tablas del módulo; **sin `DELETE`**
  (un registro se anula y la anulación queda en el historial); ningún privilegio sobre el resto del esquema. La web
  escribe en Trabajadores (`cf_trabajadores_web`) y **solo** en `vencimientos_marcas_pago` y `proveedores_forma_pago`
  (`cf_pagos_web`, H6; ver «Pagos (H6)»).
- **Historial solo de inserción**, escrito por trigger; el autor lo indica la web (por ahora «Marc») y sin autor la
  escritura falla.
- **Sin datos de salud ni DNI:** las trabajadoras no guardan DNI; la nota de un evento tiene como máximo 200
  caracteres (comprobado en la BD) y la web avisa de no anotar datos de salud.
- **Fichajes de Farmatic: POSPUESTOS.** Las horas se confirman a mano en la web; no se lee Farmatic para este módulo.
- **Cómputo (DECISIÓN DE PIO, 2026-11-12):** `TURNO_GUARDIA` (también el festivo trabajado) y `LOCALIZADA` **no
  computan**: se registran, no suman horas.
- **Rol de escritura de la web:** `cf_trabajadores_web` (migración 31). Contraseña fijada por Pio fuera del
  repositorio, con SCRAM (ver «Seguridad y operación»); prueba de acceso `ACCESO_OK` (2026-11-12).
- **Franja contraria a una media jornada:** no se bloquea en la BD (cambios de turno); la web avisa.
- **Rol del sistema sin privilegios** sobre las tablas del módulo: la migración 31 le revoca los privilegios por
  defecto de Supabase. **AUTORIZACIÓN EXPRESA DE PIO (2026-11-12):** nombrar el rol del sistema **solo** en
  `sql/migrations/31_cf_trabajadores.sql` y su rollback (excepción a la regla permanente del 2BS). Tests, scripts de
  despliegue y documentación no lo nombran; cualquier otro fichero, autorización nueva.

- **Migración 33 (petición de la web, OK de Pio, 2026-11-14; desplegada en producción el 2026-11-15, hito
  TRAB-33-D, `CONFIRMADO EN PRODUCCIÓN`; ver ESTADO_ACTUAL):** eventos anulados (unicidad solo entre no anulados;
  **la web debe usar** `ON CONFLICT (trabajadora_id, fecha, franja) WHERE NOT anulado`: el anterior falla desde el
  despliegue), vacaciones del convenio (30 días en 2026–2028, decisión de Pio pendiente de texto publicado; las filas
  del convenio las crea la web, decisión de Pio del 2026-11-15) y `trabajadoras_ajustes_anuales` (mismas reglas que el resto del
  módulo: RLS por farmacia, sin DELETE, autor e historial). Diseño en `pruebas/auditoria_trab/DISENO_33.md`.
  **AUTORIZACIÓN EXPRESA DE PIO (2026-11-14):** nombrar el rol del sistema **solo** en
  `sql/migrations/33_cf_trabajadores_ajustes.sql` y su rollback; tests, scripts y documentación no lo nombran.

- **Migración 34 (TA3, petición de la web, OK de Pio, 2026-11-16; desplegada en producción el 2026-11-16, hito
  TRAB-34-D, `CONFIRMADO EN PRODUCCIÓN`; ver ESTADO_ACTUAL):**
  - `guardias_semana`: una por semana, PIO, RITA u `OTRA`; la persona de guardia y el apoyo del sábado son
    trabajadoras de esa farmacia, y `OTRA` va sin personas.
  - `guardias_festivo`: una por festivo común vigente.
  - `festivos` se reutiliza: un festivo LOCAL puede no llevar farmacia (vacía = las dos).
  - `guardias_farmacia` se retira: la migración y `desplegar_34.py` **se paran si tiene filas** (decisión de Pio).
    Retirada en producción (estaba vacía); **la web no debe usarla**.
  - Los únicos son parciales (entre no anulados): un `ON CONFLICT` de la web debe repetir el predicado
    (`WHERE NOT anulada` en las guardias, `WHERE NOT anulado` en `festivos`).
  - Mismas reglas que el resto del módulo: autor por `cf.autor`, anulación en lugar de DELETE, historial por trigger,
    RLS por farmacia del módulo, con las filas `OTRA` visibles para PIO y RITA.
  - Diseño en `pruebas/auditoria_trab/DISENO_34.md`.
  - **AUTORIZACIÓN EXPRESA DE PIO (2026-11-16):** nombrar el rol del sistema **solo** en
    `sql/migrations/34_cf_trabajadores_guardias.sql` y su rollback; tests, scripts y documentación no lo nombran.

## Pagos (H6)

Petición de la web, excepción autorizada por Pio; decisiones D1–D9 aprobadas el 2026-11-16. Diseño en
`pruebas/auditoria_h6/DISENO.md`. Migración 35 (`sql/migrations/35_cf_pagos_marcas.sql`) **desplegada en
producción** el 2026-11-17 (hito H6-D, `CONFIRMADO EN PRODUCCIÓN`; ver ESTADO_ACTUAL), con `desplegar_35.py` ensayado
antes con la imitación del `postgres` de Supabase.

- **Escritura de la web, solo en dos tablas.** `cf_pagos_web` tiene `SELECT`, `INSERT` y `UPDATE` sobre
  `vencimientos_marcas_pago` y `proveedores_forma_pago`, `SELECT` sobre `pagos_historial` y `EXECUTE` solo sobre la
  función de su RLS (`cf_pagos_farmacia_habilitada`). Nunca escribe en `facturas`, `facturas_vencimientos`,
  conciliación, albaranes ni ninguna otra tabla, ni las lee.
- **Anulación en lugar de DELETE.** Nadie tiene `DELETE` ni `TRUNCATE` y un trigger los rechaza
  (`BORRADO_NO_PERMITIDO`). Una fila solo admite pasar `anulada` de false a true (`SOLO_ANULAR`): corregir es anular y
  crear otra, y una anulada no se reactiva.
- **Autor e historial.** El autor va por transacción (`set local cf.autor`); sin él, `AUTOR_AUSENTE`. El historial
  (`pagos_historial`) lo escribe un trigger, solo por inserción, y es inmutable.
- **El sistema no usa las marcas.** Ni la normalización, ni la conciliación, ni la persistencia, ni la noche leen estas
  tablas para decidir nada, y las marcas no cambian ningún estado de factura, vencimiento ni conciliación. En los
  postchecks se informan aparte (`TABLAS_PAGOS`, ver «Pruebas»).
- **Cuando haya banco, manda el banco.** La conciliación bancaria y la Norma 43 siguen `NO IMPLEMENTADAS`; cuando
  existan, su estado prevalece sobre la marca manual, que se conserva como histórico. `PAGADO_BANCO` queda reservado,
  sin esquema (D6).
- **Farmacia (D1).** La misma fuente que facturas: `cf_configuracion.farmacias_habilitadas` (hoy solo PIO), en los
  triggers y en la RLS. No usa la excepción por módulo de Trabajadores. La marca es de la farmacia de su factura.
- **Vencimiento por `(factura_id, vencimiento_orden)`, sin claves externas (D7).** El trigger copia fecha e importe
  al marcar: si un reproceso los cambia, la web muestra la marca «a revisar», **nunca «pagado»**. No se marca un
  vencimiento sin importe o sin fecha.
- **Fecha de pago no posterior a hoy en `Europe/Madrid` (D3).** `DOMICILIADOS` (D2) exige forma `DOMICILIACION`,
  fecha de pago = fecha de vencimiento y vencimiento ya pasado.
- **Lectura (D4).** `cf_lectura` lee las tres tablas con la regla de farmacia de la 29, sin ejecutar ninguna función
  security definer (regla del 2BN, que se mantiene).
- **Únicos parciales** (una marca vigente por vencimiento y una forma vigente por CIF): un `ON CONFLICT` de la web debe
  repetir el predicado `WHERE NOT anulada`.
- **Contraseña de `cf_pagos_web`:** fijada por Pio fuera del repositorio, con SCRAM, tras H6-D (ver «Seguridad y
  operación»); prueba de acceso `ACCESO_OK` (2026-11-17, `pruebas/auditoria_h6/probar_acceso_cf_pagos_web.py`).
- **AUTORIZACIÓN EXPRESA DE PIO (2026-11-16, D8):** nombrar el rol del sistema **solo** en
  `sql/migrations/35_cf_pagos_marcas.sql` y su rollback, para quitarle los privilegios por defecto de Supabase sobre lo
  nuevo. Tests, scripts y documentación no lo nombran; cualquier otro fichero, autorización nueva.

## Cashflow (H7)

Decisiones de Pio (2026-11-17, C1–C8; 2026-11-18, E1–E7 y las dos propuestas de redondeo; 2026-11-22, respuestas
del hito H7). Diseño en `pruebas/auditoria_h7/DISENO.md`. **Migración 38** `CONFIRMADO POR TEST` en PostgreSQL 17
local y **desplegada en producción** en el H7-D, 2026-11-22, con confirmación explícita de Pio (`APLICADA`, postcheck
por fila OK, prueba de acceso de `cf_lectura` `ACCESO_OK`; ver ESTADO_ACTUAL). El script de importación
(`src/cashflow/importar_cashflow.py`, hito 38-B) está implementado en local (`CONFIRMADO POR TEST`) y **no se ha
ejecutado contra producción**: las tablas siguen vacías salvo las cuentas fijas. La tarea de las 23:45 no existe;
la crea Pio, con su confirmación. **Excepción (DECISIÓN DE PIO, 2026-11-22):** los ensayos de la 37 y de la 38
entran en `SUITE_HISTORICA` en el commit del 38-B, no en el de su «D».

- **Excepción de farmacia:** RITA es visible en el módulo CASHFLOW **SOLO** con sus datos bancarios del Excel
  importado. Sus facturas siguen desactivadas: `cf_configuracion.farmacias_habilitadas` no cambia y facturas,
  albaranes, normalización y conciliación siguen solo PIO. La excepción es propia del módulo, nunca global.
- **Lista cerrada de `cf_lectura`:** la migración 38 la amplía con las cuatro tablas `cf_cashflow_*` (`SELECT`, con
  RLS sin funciones security definer, regla del 2BN): cuentas, saldos e importes visibles si su farmacia está en el
  módulo `CASHFLOW` o no tienen farmacia (`SL`); importaciones, todas. Ningún rol de la web, ni anon ni
  authenticated, tiene privilegios sobre ellas.
- **Permiso por módulo (C4):** `cf_modulos_farmacias` admite `CASHFLOW = {PIO, RITA}`; Trabajadores filtra por su
  propio módulo y no cambia.
- **Solo inserción:** nadie escribe directamente en las tablas. La única escritura es la RPC
  `cf_cashflow_registrar_importacion` (security definer, EXECUTE solo para el rol del sistema), que vuelve a validarlo
  todo en la BD y falla cerrado sin escribir nada. Un trigger rechaza `UPDATE` (`SOLO_INSERCION`), `DELETE` y
  `TRUNCATE` (`BORRADO_NO_PERMITIDO`); la única excepción es el cambio de `vigente` que hace la RPC. Una sola
  importación vigente; un hash no se importa dos veces; un `ERROR` no tiene importes ni saldos ni es vigente.
- **Cuadre (E1):** saldo inicial + Σ`RE` − Σ`RS` = saldo según fórmulas, con el signo de la celda (un `RS` positivo
  es una salida). En la BD, margen de 0,005 por importe redondeado de esa cuenta y decena (propuesta aprobada) y
  **ninguno por saldo redondeado** (decisión de Pio, 2026-11-22). Importes y saldos llegan al céntimo.
- **Decenas:** empiezan el día 1, 11 o 21 y acaban el 10, el 20 o el último día del mes. E5: la decena sin saldo
  (primera de `SL`) no lleva importes. E7: el saldo de bancos vacío o distinto del de fórmulas nunca es error.
- **Categorías nuevas (C5):** las controla el script de importación (38-B); la RPC no las comprueba (decisión de
  Pio, 2026-11-22). **DECISIÓN DE PIO (2026-11-22):** un par (cuenta, categoría) es nuevo si no aparece en ninguna
  importación `OK` anterior de esa cuenta (no solo en la vigente). La noche no escribe nada (código 4) y no se
  registra como `ERROR`, para que el mismo fichero pueda aceptarse; solo la importación manual con
  `--aceptar-categorias-nuevas` los acepta.
- **Tarea de Cashflow en las puertas (C7; orden de Pio del 2026-11-22):** no es obligatoria ni previa, pero la noche
  y los preflights (2AT, 2BD-D en adelante y las series 2BJ/2BP) paran si está en ejecución.
- **Script de importación (38-B):** `python -m src.cashflow.importar_cashflow <NOCHE|MANUAL> <SIMULAR|REAL>
  [--aceptar-categorias-nuevas]`. Su **única escritura es la RPC de la 38**, con el cliente del sistema de la noche;
  nunca un `INSERT`. Lee en sesión READ_ONLY; nunca abre ni escribe el original (trabaja sobre una copia estable fuera
  del repositorio). `SIMULAR` no escribe en la BD. Puertas: git en `REAL`, ninguna tarea en ejecución, ninguna noche
  `EN_CURSO`, la 38 presente y la carpeta C1. Postcheck por fila antes y después: solo cambian las filas de esa
  importación. Informe sin conceptos ni categorías. Lanzarlo pide confirmación (regla `ask` `*importar_cashflow*`).
  Concreciones en DISENO §10: las cuatro primeras, decididas por Pio el 2026-11-22; el resto, `PROPUESTA`.
- **Postchecks:** `TABLAS_CASHFLOW` en la noche y en las series 2BJ y 2BP, fuera del criterio por fila e informadas
  aparte (`postcheck["cashflow"]`), sin afectar al veredicto, como Pagos.
- **Despliegue y acceso:** `pruebas/auditoria_h7/desplegar_38.py` (ensayado con la imitación del `postgres` de
  Supabase y ejecutado una sola vez en el H7-D) y `pruebas/auditoria_h7/probar_acceso_cf_lectura_cashflow.py`
  (terminal de Pio). Por orden de Pio (2026-11-22), `desplegar_38.py` solo se toca con Read/Edit y, fuera de su única
  ejecución en el H7-D, solo lo cargan los tests de `pytest tests/...`. No se vuelve a ejecutar: con la 38 aplicada,
  su precondición 1 falla cerrado.
- **Rollback** al esquema 37: falla cerrado si hay alguna importación (`ROLLBACK_38_CASHFLOW_CON_DATOS`).
- **Numeración (DECISIÓN DE PIO, 2026-11-19):** R20 = migración 36, defectos de extracción directos a REVISION = 37,
  Cashflow = 38 (antes 36 y 37). Cada migración exige la anterior.
- **AUTORIZACIÓN EXPRESA DE PIO (C3, 2026-11-17; reconfirmada el 2026-11-19 tras renumerar):** nombrar el rol del
  sistema **SOLO** en `sql/migrations/38_*.sql` y su rollback. Tests, scripts y documentación no lo nombran; cualquier
  otro fichero, autorización nueva.
- **Importación:** su estado es `OK` o `ERROR`. El importe conserva el signo de la celda del Excel; no se deduce ni se
  invierte.

## Automatización Alliance

Decisiones de Pio (2026-11-12) en `pruebas/auditoria_auto_alliance/DISENO.md` (D1–D7 y plan de hitos). Hito AUTO-A
**solo local** (`CONFIRMADO POR TEST`); migración 32 **desplegada en producción** (AUTO-32-D, 2026-11-13); 4 noches
`SOMBRA` con `NOCHE_OK` (AUTO-S, 14→15 a 17→18/11). **AUTO-ON (CONFIRMACIÓN EXPLÍCITA DE PIO, 2026-11-18):** el `.bat`
pasa a `REAL` y Pio enciende los dos flags. Primera noche `REAL` con 5 + 5.

- **Apagar (vuelta atrás):** Pio pone los dos flags en `false` en el editor SQL. El efecto es inmediato: la BD no
  entrega más claims `AUTOMATICO`, y si la noche está en marcha termina con normalidad. Con el `.bat` en `REAL` y los
  flags apagados, la noche para en la puerta (`REAL_CON_FLAGS_APAGADOS`) sin escribir nada más que su fila. Para
  dejarlo limpio, Pio deshabilita la tarea o se devuelve el `.bat` a `SOMBRA` con un commit. Lo hecho no se deshace
  solo.
- **Con los flags encendidos,** las series 2BJ y 2BP y los preflights de despliegue fallan cerrados (exigen los flags
  apagados): una tanda manual o un despliegue requieren que Pio apague los flags durante esa ventana.

- **Orquestador nocturno** (`runtime_supabase/noche_automatica.py`, tarea de las 22:15 como `Usuari` con
  `ejecutar_automatizacion_alliance.bat`): modos `SOMBRA` (flags apagados; su única escritura es la fila de resumen
  nocturno, decisión de Pio) y `REAL` (claims `AUTOMATICO`, que exigen los flags en la BD; cada fase solo con su flag).
- **Puertas:** las dos tareas de esta noche terminadas con código 0; flags según el modo; Luna `false`; solo PIO;
  tolerancias R11 certificadas; 0 locks, claims y NORMALIZANDO; migraciones presentes; puerta git; ninguna noche
  anterior `EN_CURSO`.
- **Paradas** (cortan la noche): puerta fallida, excepción, huérfano o claim vivo, documento o factura reclamados
  distintos del previsto, resultado real distinto del simulado, fila ajena cambiada (postcheck 2AX por fila).
- **Para revisar** (fin de la conciliación de esa noche, sin reclamar): n.º 1 que simula un resultado distinto de
  `CONCILIADA` (D2, revisión tras un mes de uso), que no es Alliance (R19) o con una revisión R18 pendiente.
- **Límites (D5):** 5 + 5 hasta 3 noches `REAL` buenas seguidas; después 20 + 20; una `PARADA` reinicia la cuenta;
  60 minutos; una sola noche por fecha (fila de `cf_noches_automaticas`).
- **Migración 32** (`cf_noches_automaticas`): lectura para `cf_lectura`; nada para anon, authenticated ni PUBLIC.
  **AUTORIZACIÓN EXPRESA DE PIO (2026-11-12):** nombrar el rol del sistema **solo** en
  `sql/migrations/32_cf_noches_automaticas.sql` y su rollback (excepción a la regla permanente del 2BS) para darle
  `SELECT`, `INSERT` y `UPDATE` sobre la tabla y quitarle `DELETE`, `TRUNCATE`, `REFERENCES` y `TRIGGER`.
  `desplegar_32.py` lo comprueba sin nombrarlo (un único beneficiario además del propietario y `cf_lectura`, con
  lectura y escritura y sin borrado). Tests, scripts y documentación no lo nombran; cualquier otro fichero,
  autorización nueva.

## Capacidades no implementadas

- Conciliación bancaria: **NO IMPLEMENTADA**.
- Norma 43: **NO IMPLEMENTADA**.
- Telegram: **NO IMPLEMENTADO**.
- Interfaz web: **PARCIALMENTE IMPLEMENTADA** (Pio, 2026-11-12). Vive fuera de este repositorio. Hoy solo lee
  Supabase con `cf_lectura` (R9 de lectura); escribe en el módulo de Trabajadores, con un rol propio,
  `cf_trabajadores_web`, desplegado el 2026-11-12 (ver «Trabajadores»), y su única otra escritura prevista son las
  marcas de pago y la forma de pago por proveedor (`cf_pagos_web`, H6, migración 35 desplegada el 2026-11-17; ver
  «Pagos (H6)»).
- Beiersdorf: **SIN EXTRACTOR IMPLEMENTADO**.

Estado a 2026-09-24: `NO ENCONTRADO` en el código vigente. No se presentan como
módulos parciales.

## Pruebas

- **Tablas que escribe la web en los postchecks (Pio, 2026-11-13 para Trabajadores; 2026-11-16 para Pagos, H6):**
  `TABLAS_TRABAJADORES` y `TABLAS_PAGOS` (`noche_automatica.py`) quedan fuera del snapshot 2AX y del criterio por
  fila de la noche y de las series 2BJ/2BP; se informan aparte y **no hacen fallar el veredicto**.
- **Puerta de tareas (Pio, 2026-11-15):** las tres tareas son obligatorias, también «ControlFarmacias -
  Automatizacion Alliance» (`auditoria_readonly.TAREAS_ESPERADAS`).

- **Criterio de postcheck de privilegios (Pio, Hito 2AX, 2026-09-29)** para todo
  despliegue futuro: (1) producción antes vs después: solo cambian los objetos
  del alcance de la migración; (2) los objetos del alcance quedan iguales a la
  referencia local; (3) los objetos fuera de alcance quedan idénticos antes y
  después. Cualquier otra diferencia → PARAR (sin rollback sin confirmación de
  Pio). Las diferencias conocidas del baseline local fuera de alcance no son
  motivo de parada si cumplen (3).
  **Exclusión explícita (Pio, 2026-11-06, Hito 2BQ):** los esquemas internos de Supabase (`auth`, `storage`,
  `graphql`, `realtime`, `vault`, `pgsodium`, `pgsodium_masks`, `supabase_functions`, `net`, `cron`) no se comparan
  con la referencia local (2): la base local no los reproduce. Siguen dentro de (1) y (3), antes frente a después.
  Desde el 2BQ la base local reproduce todo lo demás (0 diferencias frente a la captura del intento 3 del 2BN-D):
  una diferencia nueva con la referencia es motivo de parada, no una excepción.
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
  - **suite completa con `pg17_local`** (desde el Hito SUITE, `pytest tests/ -m "not historica" --basetemp=<propio>`,
    en paralelo, con Docker disponible: ningún test `pg17_local` omitido) **más la histórica** cuando la exige el
    Hito SUITE (abajo), si el commit toca `src/`, `sql/`, scripts de despliegue o cualquier código que
    acceda a Supabase o Farmatic, también las herramientas de `pruebas/`;
  - si solo toca documentación: **suite rápida** (`pytest tests/ -m "not pg17_local" --basetemp=<propio>`);
  - en la duda: suite completa.
  - La suite exigida se ejecuta sobre el estado exacto que se commitea y debe quedar en verde (0 failed,
    0 errors).
  - **Evidencia mecánica (Hito 2BH, 2026-10-30):** cada ejecución de pytest añade una línea a
    `logs/agentes/suites.jsonl` (`tests/registro_suite.py`) con la huella exacta del árbol probado (la de la
    barrera de commit, calculada al empezar y al terminar), passed/failed/errors/skipped, fechas, alcance
    (`total`, `completa`, `historica`, `rapida` o `parcial`, Hito SUITE) y `verde`. «Documentación» = ficheros
    `.md` fuera de `.claude/`.
    - La **barrera de commit** exige una línea con la huella actual, alcance suficiente y en verde
      (`commit_sin_suite`, `commit_suite_roja`).
    - `revisor-reglas` (T2) comprueba una línea con `base` = HEAD, `rutas` = `git status`, alcance suficiente y
      `verde`. **Desde el 2BS** no lee el registro: ejecuta `tests/consultar_suite.py`, un script de solo lectura
      que responde `PASS`/`FAIL` con el resumen de la línea válida y sin exponer el fichero.
    - Ya no basta con declarar la suite en el encargo.
    - **Excepción de Pio (2026-11-02):** un FAIL de `revisor-reglas` cuya **única** regla fallida es T2 no
      bloquea el commit si hay un PASS posterior de la misma huella (y la suite registrada sigue exigida).
      Cualquier otro FAIL, o un FAIL sin el detalle de reglas registrado (solo se registra si la tabla trae
      las 14 reglas, cada una una vez y con un resultado reconocido), sigue bloqueando. Hooks:
      `registrar_uso_agente.py` (`reglas_fail`) y `estado_git.py` (`_veredicto_grupo`).
    - **INCONCLUSO (DECISIÓN DE PIO, 2026-11-14):** cuando un bloqueo (hook o denegación) impide a
      `revisor-reglas` comprobar una regla, la marca `INCONCLUSO`, no `FAIL`, y su veredicto es
      `VEREDICTO: INCONCLUSO` si no hay ningún `FAIL`. Un INCONCLUSO **más un PASS posterior sobre la misma
      huella** no bloquea el commit; sin ese PASS, bloquea (`commit_revisor_inconcluso`). Un **FAIL real sigue
      bloqueando** siempre. Fallo cerrado: un INCONCLUSO sin la tabla completa y fiable, o con algún `FAIL` en la
      tabla, cuenta como FAIL; un PASS cuya tabla trae alguna regla INCONCLUSO cuenta como INCONCLUSO. Hooks:
      `registrar_uso_agente.py` (`veredicto_revisor`, `reglas_inconclusas`), `estado_git.py`
      (`_veredicto_grupo`) y `barreras_agentes.py` (`barrera_commit`).
- **Hito SUITE (DECISIONES DE PIO D1–D8, 2026-11-20; diseño y medición en `pruebas/auditoria_suite/DISENO.md`):**
  - **Suite paralela:** pytest-xdist **3.8.0**, fijado en `requirements-tests.txt` y exigido por `pytest.ini`
    (`required_plugins`); `addopts = -n 8 --dist loadgroup` (8 tras medir 4 y 8 workers, D2). Cada worker tiene su
    propio contenedor `pg17_local` sin red; los ensayos de despliegue usan **un contenedor TCP limpio por módulo**
    (solo 127.0.0.1; D5 corregida por Pio: uno por worker no vale, porque los roles son comunes al clúster). Reparto
    por **familia de plantillas** (`FAMILIAS`, D3). `-n 0` ejecuta en serie.
  - **Alcances del registro:** `total` (sin `-m`), **`completa`** (`-m "not historica"`, la de cada commit de
    código), `historica` (`-m historica`), `rapida` (`-m "not pg17_local"`) y `parcial`. Con xdist solo escribe el
    proceso principal.
  - **Suite histórica (D4):** ensayos de despliegue y rollbacks de migraciones ya desplegadas, en `SUITE_HISTORICA`
    (`tests/facturas/runtime_supabase/conftest.py`). Al desplegar una migración, sus ensayos entran ahí en el
    commit del «D». La barrera exige la histórica (o total) en verde:
    - **sobre la misma huella** si el cambio toca `sql/`, `pg17_local.py`, ese `conftest.py`, un `desplegar_*` o
      `preflight*` de `pruebas/`, `pruebas/auditoria_2at/`, `puerta_git.py` o un módulo de `SUITE_HISTORICA`;
    - **de 7 días o menos** (la última del repositorio) en cualquier otro commit de código;
    - **antes de cada despliegue:** la barrera bloquea la ejecución de un script `desplegar_<n>` sin histórica en
      verde sobre la huella actual (`despliegue_sin_historica`).
  - **Regla de reparación (D6, D7):** una ejecución parcial en verde equivale a la `completa` sobre su huella si,
    respecto de la última `completa`/`total` roja con la misma base:
    - **(a)** el árbol no ha cambiado, la roja tiene **como máximo 3** fallados y la **primera** parcial posterior
      los ejecuta todos (**1 repetición**);
    - **(b)** solo cambian módulos `tests/**/test_*.py` y la parcial ejecuta todos los fallados y **enteros** los
      módulos cambiados (como argumento, sin `-k`/`-m` ni deseleccionados). `tests/conftest.py`,
      `tests/facturas/runtime_supabase/pg17_local.py`, `tests/registro_suite.py`, `tests/consultar_suite.py` y
      cualquier otro fichero de `tests/` que no sea un módulo `test_*.py` **cuentan como código**;
    - **(c)** si toca código: suite completa.
    
    T2 (`tests/consultar_suite.py`) aplica las mismas reglas. Hooks: `estado_git.py` (`completa_valida`,
    `historica_valida`, `suites_para_commit`, `es_despliegue`) y `barreras_agentes.py` (`barrera_commit`,
    `barrera_despliegue`; `commit_sin_historica`, `commit_historica_roja`).
  - **Excepciones expresas de Pio (2026-11-20, Hito SUITE):** Read y Edit, **sin scripts por Bash**, sobre los
    ficheros que nombran el registro de suites por ser su infraestructura —
    `tests/test_registro_suite_2bh.py` (solo para un fichero temporal en `tmp_path`),
    `.claude/hooks/barreras_agentes.py`, `.claude/hooks/estado_git.py`, `tests/test_hook_barreras_agentes.py` y
    `tests/consultar_suite.py`— y ejecutar sus tests con pytest. Nada se lee ni se escribe en `logs/agentes`.
    Cualquier otro fichero que lo nombre: autorización nueva.
- Pytest debe usar directorios temporales mediante `CONTROLFARMACIAS_LOG_DIR` y
  `CONTROLFARMACIAS_DATA_DIR`.
- Los tests no pueden conectarse a Farmatic/Supabase reales ni escribir en
  `logs/` o `data/` productivos. Única excepción (2BH): el ejecutor de pytest, no un test, añade la línea de
  la ejecución a `logs/agentes/suites.jsonl`.
- Una suite verde demuestra solo lo cubierto por sus tests; no amplía autoridad
  productiva ni resuelve reglas funcionales pendientes.
