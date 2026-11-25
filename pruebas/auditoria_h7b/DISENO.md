# H7b: Cashflow con previsión (vencimientos y apuntes manuales de la web), diseño

Estado (2026-11-25, tarde): **DISEÑO CORREGIDO a petición de la web y aprobado por Pio** (§2.1 y §6): la media
sale del diseño y de la BD (es la regla del motor de la web) y la prioridad con vencimientos pasa a «gana el mayor en
valor absoluto». **La 40 no se aplica sin el OK de Pio a este diseño corregido.** Sin código, sin migración y sin
producción.

Estado (2026-11-25): **DISEÑO con decisiones de Pio** (H7B-D1 a D8, D5 cambiada: prioridad por cuenta + categoría +
concepto + decena; migración 40), sin código, sin migración y sin producción; implementación otro día.

Estado (2026-11-24): **DISEÑO**, sin código, sin migración y sin producción. Rehecho sobre la petición de la web y
las decisiones de Pio del 2026-11-23 (empezar ya, con recurrentes, solo previsión futura), transmitidas el
2026-11-24. Sustituye al primer borrador de este fichero (c0a9cee), que no partía de la petición.

Etiquetas: `DECISIÓN DE PIO` (ya decidido), `CONFIRMADO POR CÓDIGO` (fichero:línea), `PROPUESTA` y
`DECISIÓN PENDIENTE`.

## 0. Petición y decisiones de Pio

**Objetivo (`DECISIÓN DE PIO`):** el Cashflow es la suma de tres fuentes, y el Excel pasa a ser provisional.

| Fuente | Qué aporta | Estado |
|---|---|---|
| **Norma 43** | Lo real: movimientos de banco | `NO IMPLEMENTADA` (REGLAS_CRITICAS «Capacidades no implementadas») |
| **Vencimientos** | Lo previsto con factura: `facturas_vencimientos` | Existe (solo PIO, que es la única farmacia con facturas) |
| **Apuntes manuales de la web** | Lo previsto sin factura | Este hito |

Mientras no haya Norma 43, el Excel importado (migración 38) sigue siendo la fuente de lo real y de los saldos.

**Decisiones de Pio ya tomadas (2026-11-23 y 2026-11-24):**

- **Apunte:** cuenta PIO o RITA; fecha futura respecto al último saldo de banco de la cuenta; categoría `RE`/`RS` de
  la plantilla; concepto; importe **positivo** (el sentido lo da la categoría); nota. Anular en lugar de borrar,
  autor por `cf.autor` e historial por trigger.
- **RITA:** su excepción se amplía **solo en Cashflow**, para admitir sus apuntes. Sus facturas siguen desactivadas.
- **Recurrente:** mensual, trimestral o anual; día; inicio; fin opcional. Las ocurrencias se calculan al leer y se
  puede anular una sola ocurrencia.
- **Conceptos nuevos**, siempre asociados a una categoría existente.
- **Prioridad** por cuenta, categoría y decena: **vencimientos > apunte > Excel > media**, sin doble cómputo.
  **Precisada por Pio el 2026-11-25 (H7B-D5):** por cuenta + categoría + **concepto** + decena (§2.1).
  **Corregida el 2026-11-25, tarde (petición de la web, aprobada por Pio; §2.1):** previsión = apunte > Excel > media
  (la primera que exista); con vencimientos gana el **mayor en valor absoluto** entre los vencimientos y esa
  previsión (los vencimientos son un mínimo). La media no la define este diseño: es la regla del motor de la web.
- **Tablas:** `cf_cashflow_apuntes`, `cf_cashflow_recurrentes` y `cf_cashflow_conceptos`. RLS por módulo
  `CASHFLOW`, rol de escritura propio de la web (`INSERT`, `SELECT` y `UPDATE` solo de anulación), `SELECT` de
  `cf_lectura` (aprobado) y la excepción en REGLAS_CRITICAS.
- **Migración 41** según el encargo; **40 por la numeración decidida por Pio el 2026-11-25** (R21 = 39, H7b = 40,
  «Actualizar ahora» = 41). **AUTORIZACIÓN EXPRESA DE PIO:** nombrar el rol del sistema en la migración de H7b (la
  40) y su rollback, si hace falta.
- **Solo previsión futura:** nada de lo nuevo cambia lo pasado. Lo pasado lo da el banco (hoy, el Excel).

**Lo que no cambia** (`CONFIRMADO POR CÓDIGO`, `sql/migrations/38_cf_cashflow.sql` y REGLAS_CRITICAS «Cashflow
(H7)»):

- las tablas importadas (`cf_cashflow_importaciones`, `_importes`, `_saldos`) siguen siendo solo de inserción y su
  única escritura sigue siendo la RPC de importación;
- el cuadre E1 se sigue comprobando solo con lo importado;
- ningún rol de la web escribe ni tiene privilegios de escritura sobre ellas.

## 1. Tablas (`PROPUESTA`; migración 40)

Patrón de Pagos (H6, migración 35): tablas propias, anulación en lugar de borrado, autor por transacción e historial
por trigger. Sin `DELETE` ni `TRUNCATE` para nadie: un trigger los rechaza (`BORRADO_NO_PERMITIDO`). El único
`UPDATE` admitido es anular (`anulado` de false a true, con `anulado_por`, `anulado_at` y `motivo_anulacion`
obligatorio): `SOLO_ANULAR`. Corregir es anular y crear otro.

### 1.1 `cf_cashflow_conceptos`

| Columna | Regla |
|---|---|
| `id` | `uuid` |
| `cuenta` | `PIO` o `RITA` |
| `categoria` | Una categoría `RE`/`RS` de la **plantilla** de esa cuenta: existe en la importación vigente (§3) |
| `nombre` | 1–120 caracteres; único por (cuenta, categoría, nombre normalizado) entre los no anulados |
| `proveedor_cif` | Opcional: asocia el concepto a un proveedor, para colocar sus vencimientos (§2.2, H7B-D3) |
| `autor`, `creado_at`, anulación | Como arriba |

- Los conceptos de la plantilla (los que ya trae el Excel en `cf_cashflow_importes.concepto`) valen sin darlos de
  alta. Esta tabla guarda **solo los nuevos**, cada uno con su categoría existente.

### 1.2 `cf_cashflow_apuntes` (apuntes sueltos)

| Columna | Regla |
|---|---|
| `id` | `uuid` |
| `cuenta`, `farmacia` | `PIO` o `RITA`; la farmacia es la de la cuenta (la pone el trigger) |
| `fecha` | **Posterior al último saldo de banco de la cuenta** (§3) |
| `categoria` | De la plantilla de esa cuenta |
| `concepto` | De la plantilla o de `cf_cashflow_conceptos` (no anulado), en esa categoría |
| `importe` | `numeric(14,2)`, **> 0**. El sentido lo da la categoría: `RE` suma y `RS` resta |
| `nota` | Opcional, hasta 500 caracteres |
| `recurrente_id`, `fecha_ocurrencia` | Solo en las filas que **anulan una ocurrencia** (§1.3); entonces `importe` es nulo |
| `sustituido_por` | Opcional: factura y vencimiento que lo sustituyen (§2.3) |
| `autor`, `creado_at`, anulación | Como arriba |

### 1.3 `cf_cashflow_recurrentes`

| Columna | Regla |
|---|---|
| `id`, `cuenta`, `farmacia`, `categoria`, `concepto`, `importe`, `nota` | Como en un apunte |
| `frecuencia` | `MENSUAL`, `TRIMESTRAL` o `ANUAL` |
| `dia` | 1–31. Si el mes no tiene ese día, la ocurrencia cae el **último día del mes** (H7B-D1) |
| `inicio` | Fecha de la primera ocurrencia (fija el mes de referencia del trimestre y del año) |
| `fin` | Opcional, no anterior a `inicio` |
| `autor`, `creado_at`, anulación | Anular la recurrente anula todas sus ocurrencias futuras |

- **Ocurrencias calculadas al leer**, nunca guardadas: una función `stable`, sin `security definer`, o una vista
  `security_invoker` (regla del 2BN) devuelve (recurrente, fecha) entre dos fechas.
- **Solo cuentan las ocurrencias futuras:** posteriores al último saldo de banco de la cuenta (§3) y, como mucho,
  hasta la última decena de la importación vigente.
- **Anular una ocurrencia:** una fila en `cf_cashflow_apuntes` con `recurrente_id` y `fecha_ocurrencia`, sin importe.
  El trigger comprueba que esa fecha es una ocurrencia de esa recurrente. Así no hace falta una cuarta tabla de datos
  (H7B-D2).

### 1.4 Historial

- `cf_cashflow_apuntes_historial`: una fila por alta y por anulación de cualquiera de las tres tablas, con la tabla,
  el id, la acción, el autor y una copia de la fila. La escribe un trigger, solo inserción e inmutable, como
  `pagos_historial`.
- Pio enumeró tres tablas. El historial por trigger necesita una tabla más, y se propone esta (H7B-D2).

## 2. Lectura: prioridad sin doble cómputo (`PROPUESTA`)

### 2.1 La regla por celda

**H7B-D5 (DECISIÓN DE PIO, 2026-11-25):** una **celda** es (cuenta, categoría, **concepto**, decena).

- El concepto de un vencimiento es el concepto con su `proveedor_cif` (§2.2, H7B-D3). Un apunte o una recurrente
  llevan el suyo. El importe del Excel ya va por concepto (`cf_cashflow_importes.concepto`).
- Los vencimientos solo se comparan con la previsión **del mismo concepto**. Un apunte de otro concepto de la misma
  categoría y decena **suma**, porque es otra celda.
- El saldo y los totales por categoría suman las celdas de todos los conceptos.
- Esto sustituye la celda (cuenta, categoría, decena) de la propuesta del 2026-11-24. El texto que sigue vale
  leyendo «celda» con concepto.

**Regla corregida (DECISIÓN DE PIO, 2026-11-25, tarde, a petición de la web).** Para cada celda **futura** (después
del último saldo de banco de la cuenta):

1. **Previsión de la celda sin vencimientos:** la primera fuente que exista, por este orden:
   1. **apuntes**: los sueltos no anulados más las ocurrencias de recurrentes no anuladas; un apunte cuya
      **sustitución ha sido confirmada por Pio** (§2.3) está anulado y no cuenta;
   2. el **importe del Excel** vigente de esa celda;
   3. la **media** (H7B-D4 corregida): **no la define la BD**; la calcula el motor de la web
      (`server/cashflow/cashflow.ts`, en el repositorio de la web, que es la autoridad; citado sin comprobar). Regla
      (**DECISIÓN DE PIO, 2026-11-25**): por cuenta + concepto, la misma posición de decena (1–10, 11–20, 21–fin) de
      los **últimos 12 meses reales**; para RS Modelo, el mismo mes del año anterior.
2. **Con vencimientos** de facturas colocados en esa celda (§2.2): cuenta el **mayor en valor absoluto** entre la
   suma de los vencimientos y la previsión del punto 1. Los vencimientos son un mínimo: una previsión mayor no queda
   tapada por una factura menor.
3. **Sin vencimientos:** la previsión del punto 1.

- Cada celda toma un único importe: no hay doble cómputo. Un apunte y el importe del Excel de la misma celda nunca
  suman juntos, y los vencimientos no se suman a la previsión: se comparan con ella.
- La BD guarda los apuntes, las recurrentes y los conceptos y calcula las ocurrencias. La elección por celda (y la
  media) la hace el motor de la web, con la regla de arriba.
- **Las celdas pasadas** (hasta el último saldo de banco) solo usan lo real: hoy el Excel, y con Norma 43 el banco.
- La web muestra en cada celda **qué fuente se ha usado** y, aparte, las fuentes descartadas, para que se vea qué
  queda tapado.
- **Saldo previsto:** saldo de banco de la última decena cuadrada + Σ celdas futuras (`RE` suma, `RS` resta), decena
  a decena. El `saldo_formulas` del Excel no se toca.
- ~~Límite que Pio debe conocer (H7B-D5): un apunte de un gasto distinto de la misma categoría y decena que un
  vencimiento queda tapado~~. **Resuelto por Pio (2026-11-25):** con la celda por concepto, ese apunte suma. Con la
  regla corregida, el apunte del mismo concepto se compara con los vencimientos y cuenta el mayor.

### 2.2 Dónde cae un vencimiento

- **Cuenta:** la de la farmacia de la factura (hoy solo PIO; RITA no tiene facturas).
- **Decena:** la de `fecha_vencimiento`.
- **Importe y sentido:** el del vencimiento; el sentido sale de `datos_extraidos.tipo_documento.valor` (regla de Pio
  del 2026-11-08: `FACTURA` = salida `RS`, `ABONO` = entrada; un vencimiento no documentado no se suma).
- **Categoría:** la del concepto con el `proveedor_cif` de la factura en `cf_cashflow_conceptos` (H7B-D3).
  - Un vencimiento de un proveedor **sin concepto asociado** no se coloca en ninguna categoría. Va a una línea
    «vencimientos sin categoría», que suma en el saldo previsto y la web muestra para que se asocie. Así no se pierde
    ni se adivina su categoría.
- **Solo vencimientos futuros sin pagar:** los que tienen una marca de pago vigente (Pagos H6) no cuentan.
- Los vencimientos se leen; el Cashflow nunca los modifica.

### 2.3 Cuándo una factura real sustituye a un apunte

Por la regla corregida (§2.1), un vencimiento en la **misma celda** no tapa el apunte: cuenta el mayor de los dos. Para
que el apunte deje de contar hace falta una sustitución confirmada, que lo anula. Propuesta (H7B-D6), sin
automatismos:

- **Candidato:** un vencimiento futuro de la misma cuenta, de la categoría del apunte, en la misma decena o en la
  siguiente, con importe a ±5 % del apunte.
- Si un apunte tiene **exactamente un** candidato y ese candidato no lo es de otro apunte, la web lo muestra como
  «posible sustitución».
- **La sustitución la confirma Pio:** guarda `sustituido_por` (factura y orden del vencimiento) y el apunte
  deja de contar, con historial.
- Con cero o más de un candidato no se sugiere nada (falla cerrado).
- Para un recurrente se sustituye **una ocurrencia** (anulación de esa ocurrencia con la referencia a la factura), no
  la recurrente entera.

## 3. Validaciones en la BD (`PROPUESTA`)

En los triggers de alta, que fallan cerrado sin escribir nada:

- la cuenta es `PIO` o `RITA` y su farmacia está en el módulo `CASHFLOW` (`cf_modulos_farmacias`);
- **último saldo de banco de la cuenta:** la última decena con `saldo_bancos` no nulo de la importación vigente
  (E7: un nulo es «aún no cuadrada»). La fecha del apunte, o la primera ocurrencia que cuenta, debe ser posterior al
  final de esa decena (`FECHA_NO_FUTURA`). Con Norma 43, la referencia pasará a ser el último saldo del banco;
- sin importación vigente no se admite nada (`SIN_IMPORTACION_VIGENTE`);
- la categoría existe para esa cuenta en la importación vigente (`CATEGORIA_FUERA_DE_PLANTILLA`);
- el concepto existe en la plantilla o en `cf_cashflow_conceptos` en esa categoría (`CONCEPTO_DESCONOCIDO`);
- importe > 0 (`IMPORTE_NO_POSITIVO`), día y frecuencia válidos, fin no anterior a inicio;
- autor presente (`AUTOR_AUSENTE`).

Los triggers leen las tablas importadas con los privilegios de su propietario, como en la 35. El rol de la web no las
necesita para escribir.

## 4. Permisos y farmacia (`PROPUESTA`, sobre decisiones de Pio)

- **Rol de escritura propio de la web:** `cf_cashflow_web`, con `LOGIN`, sin `BYPASSRLS` y sin pertenecer a ningún
  rol.
  - `INSERT` y `SELECT` sobre `cf_cashflow_apuntes`, `cf_cashflow_recurrentes` y `cf_cashflow_conceptos`;
  - `UPDATE` **solo** de las columnas de anulación y de `sustituido_por`;
  - `SELECT` sobre el historial y `EXECUTE` sobre la función de ocurrencias.
  - Nada más: ni escritura en las tablas importadas, ni facturas, ni pagos, ni trabajadores.
  - Contraseña SCRAM fijada por Pio fuera del repositorio; prueba de acceso como `cf_pagos_web`.
  - La web lee las tablas importadas y los vencimientos con `cf_lectura`, como hoy.
- **`cf_lectura`:** `SELECT` sobre las tablas nuevas, el historial y la función de ocurrencias (`DECISIÓN DE PIO`),
  con la RLS del módulo `CASHFLOW` y sin funciones `security definer` (regla del 2BN).
- **RLS:** las filas de la cuenta de una farmacia del módulo `CASHFLOW` (hoy PIO y RITA).
- **Excepción de RITA (`DECISIÓN DE PIO`):** pasa de «solo sus datos bancarios del Excel importado» a «sus datos
  bancarios del Excel importado **y sus apuntes manuales de Cashflow**». Sigue siendo **solo del módulo Cashflow**:
  `farmacias_habilitadas` no cambia y sus facturas, albaranes, normalización y conciliación siguen desactivados.
  Recogida ya en REGLAS_CRITICAS («Cashflow (H7)», previsión H7b, no implementada); rige desde el despliegue de la
  migración de H7b.
- **Rol del sistema:** la 40 lo nombra solo si hace falta para quitarle los privilegios por defecto de Supabase
  sobre lo nuevo, como en la 35 y la 38. Autorizado por Pio solo en la migración de H7b (la 40) y su rollback.
- **El sistema no usa los apuntes para decidir nada.** Ni la importación, ni la noche, ni la conciliación los leen.
  En los postchecks de la noche y de las series 2BJ/2BP entran en `TABLAS_CASHFLOW`, informados aparte y sin
  afectar al veredicto.

## 5. Migración, tests y despliegue (`PROPUESTA`)

- **Migración 40** (`40_cf_cashflow_prevision.sql` y su rollback; exige la 39): tablas, triggers, función de
  ocurrencias, RLS, rol `cf_cashflow_web` sin contraseña y privilegios de `cf_lectura`. Numeración: H7B-D7.
- **Rollback 40:** falla cerrado si hay algún apunte, recurrente o concepto (`ROLLBACK_40_CON_DATOS`), como el de la
  38.
- **Tests previstos (PostgreSQL 17 local):**
  - la 40 es idempotente y el rollback deja el esquema de la 39;
  - cada validación de §3 rechaza con su motivo; no se puede borrar, reabrir ni cambiar el importe;
  - ocurrencias: mensual el día 31 en febrero (último día), trimestral y anual desde `inicio`, fin opcional, una
    ocurrencia anulada, solo las futuras;
  - la BD no elige fuente por celda ni calcula la media (§2.1): las pruebas de la regla por celda son del motor de
    la web; en la BD, que una sustitución confirmada anula el apunte;
  - vencimiento sin concepto asociado → «sin categoría»; vencimiento con marca de pago → no cuenta;
  - sustitución: un candidato se sugiere; cero o dos, no;
  - RLS y roles: `cf_cashflow_web` no escribe en ninguna otra tabla; `cf_lectura` lee lo nuevo y no escribe;
    RITA ve sus apuntes y ninguna factura;
  - una importación nueva de Cashflow no toca los apuntes y los apuntes no cambian el cuadre E1;
  - ensayo de `desplegar_40` con la imitación del `postgres` de Supabase, en la suite histórica.
- **Requisito previo (DECISIÓN DE PIO, 2026-11-25):** la 40 no se implementa ni se aplica sin el OK de Pio a este
  diseño corregido.
- **Tras desplegarla:** informar a la web del nombre del rol nuevo (`cf_cashflow_web`), sin credenciales.
- **Despliegue (40-D):** commit con código y push de Pio; flags apagados; preflight READ_ONLY; `desplegar_40` una vez
  con confirmación explícita de Pio; postcheck por fila (solo aparecen los objetos nuevos); Pio fija la contraseña;
  prueba de acceso; flags encendidos. Después, `docs/web/ESQUEMA_CASHFLOW.md` con las tablas nuevas, la regla por
  celda y la función de ocurrencias.

## 6. Decisiones de Pio

**CORRECCIÓN (petición de la web, aprobada por Pio, 2026-11-25, tarde):** sustituye lo que digan sobre la media y
la prioridad los puntos de abajo.

- **H7B-D4 corregida:** la media no se define en la BD; la calcula el motor de la web (`server/cashflow/cashflow.ts`,
  otro repositorio; la web es la autoridad): por cuenta + concepto, misma posición de decena (1–10, 11–20, 21–fin) de
  los **últimos 12 meses reales** (DECISIÓN DE PIO, 2026-11-25; sustituye a los 3 meses de la corrección anterior);
  RS Modelo, el mismo mes del año anterior. Se retira «las 6 últimas decenas cuadradas con el banco».
- **H7B-D5 corregida:** por cuenta + categoría + concepto + decena, previsión = apunte > Excel > media (la primera que
  exista); con vencimientos, el mayor en valor absoluto entre los vencimientos y esa previsión (los vencimientos son
  un mínimo); sin vencimientos, la previsión. Una sustitución confirmada por Pio anula el apunte. **La web ha
  confirmado esta regla de prioridad (motor H7-REAL-8).**
- **La 40 no se aplica sin el OK de Pio al diseño corregido.** Tras desplegarla, se informa a la web del nombre del
  rol nuevo, sin credenciales.

**DECIDIDAS por Pio (2026-11-25):** H7B-D5 cambia (abajo); el resto, D1–D4 y D6–D8, como se recomiendan.
Implementación otro día, como migración **40** (H7B-D7). *(D4 y D5: ver la corrección de arriba.)*

- **H7B-D5 (DECISIÓN DE PIO):** la prioridad se decide por **cuenta + categoría + concepto + decena**. Un vencimiento
  solo sustituye al apunte **del mismo concepto**; un apunte de otro concepto de la misma categoría y decena suma.
  Regla en §2.1.
- **H7B-D4 precisada por D5 (DECISIÓN DE PIO, 2026-11-25, confirmada):** la media también es por **cuenta + categoría
  + concepto + decena**: la del concepto en sus últimas 6 decenas reales (cuadradas con el banco) de la cuenta; sin 6
  decenas reales, no hay media. Sustituye la «media de esa categoría» de la tabla. Texto de la propuesta, como
  histórico:
- Consecuencia de D5 sobre D4 (propuesta del 2026-11-25): si la celda es por concepto, la media
  también debe serlo (la del concepto en sus últimas 6 decenas reales); una media de la categoría sumaría dos veces lo
  que ya cubre cada concepto. Propuesta: media por concepto.

Tabla de la propuesta del 2026-11-24 (histórico; D5 y D7 sustituidas por lo anterior):

| Id | Pregunta | Recomendación |
|---|---|---|
| H7B-D1 | Recurrente con día 29–31 en un mes más corto | Último día del mes |
| H7B-D2 | Historial y anulación de ocurrencias: ¿tablas extra? | Historial en `cf_cashflow_apuntes_historial` (necesario para el trigger); la anulación de una ocurrencia, como fila de `cf_cashflow_apuntes` (sin tabla extra) |
| H7B-D3 | ¿En qué categoría cae el vencimiento de cada proveedor? | Por un concepto con `proveedor_cif` en `cf_cashflow_conceptos`; sin él, línea «vencimientos sin categoría» |
| H7B-D4 | ¿Qué es la «media»? | Media de esa categoría en las últimas 6 decenas reales (cuadradas con el banco) de la cuenta; sin 6 decenas reales, no hay media |
| H7B-D5 | Un apunte de otro gasto en la misma celda que un vencimiento queda tapado | Aceptarlo (es la regla de una fuente por celda) y mostrarlo como descartado |
| H7B-D6 | Sustitución de un apunte por una factura | Candidato único (misma cuenta y categoría, decena igual o siguiente, ±5 %), confirmado por Pio |
| H7B-D7 | Numeración: cada migración exige la anterior y la 39 no existe todavía | **DECIDIDA (2026-11-25): H7b = 40**, tras R21 = 39 (`pruebas/auditoria_r21/DISENO.md` §9.10) |
| H7B-D8 | ¿Los vencimientos con marca de pago (H6) cuentan? | No: un vencimiento marcado como pagado ya no es previsión |
