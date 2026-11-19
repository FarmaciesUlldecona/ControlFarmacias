# H7: importación del Excel de cashflow de Pio a Supabase (migración 38). DISEÑO

Estado: **DISEÑO CON LAS DECISIONES DE PIO C1–C8** (2026-11-17), **EXCEL VERIFICADO Y DECISIONES E1–E7**
(2026-11-18, §0 y §1). Sin código, sin migración y sin tocar producción.

- **Origen:** petición de la web (H7 Cashflow). La pantalla ya está hecha en FIXTURES contra el contrato de la petición
  (commit H7 en `web/fase1`, que no se ha leído para este diseño).
- **Decisiones de Pio ya tomadas (2026-11-17)** y registradas en REGLAS_CRITICAS, sección «Cashflow (H7)» (96a871b):
  - el Excel es la referencia (gold standard); nunca se escribe en él;
  - RITA entra en Cashflow **solo** con sus datos bancarios del Excel, y sus facturas siguen desactivadas;
  - la lista cerrada de `cf_lectura` se amplía con las tablas `cf_cashflow_*` en la migración 38;
  - la importación queda en `OK` o `ERROR`, y el importe conserva el signo de la celda;
  - se importa cada noche y, además, a mano cuando Pio lo lance.
- **Añadidos del chat del circuito:** la migración es la 38 (renumerada el 2026-11-19, decisión de Pio: R20 = 36,
  defectos directos a REVISION = 37, Cashflow = 38); `TABLAS_CASHFLOW` en los postchecks; tarea nocturna como `Usuari`,
  sin solaparse con las demás; rol del sistema nombrado solo en la 38 y su rollback (C3, reconfirmada el 2026-11-19).
- **Etiquetas:** lo que se afirma del esquema actual está `CONFIRMADO POR CÓDIGO` (con fichero:línea). Lo que se
  afirma del Excel está `CONFIRMADO POR VERIFICACIÓN` (§1, 2026-11-18). Lo demás es `PROPUESTA`.

## 0. Decisiones de Pio (2026-11-17)

Donde las secciones siguientes dicen `PROPUESTA` para C1–C8, queda decidido.

| Id | Decisión de Pio |
|---|---|
| **C1** | **Ruta:** carpeta `C:\GoogleDrive\CASHFLOW`. El fichero es el **único** `.xlsm` cuyo nombre empieza por `CASHFLOW` (el nombre puede variar). Si hay más de uno o ninguno, la importación es `ERROR`. Se ignoran los temporales `~$` (§2.1) |
| **C2** | Tarea nocturna a las **23:45** (§5.1) |
| **C3** | **AUTORIZACIÓN EXPRESA DE PIO** (2026-11-17; reconfirmada el 2026-11-19 tras renumerar) para nombrar el rol del sistema **solo** en `sql/migrations/38_*.sql` y su rollback. Tests, scripts y documentación no lo nombran; cualquier otro fichero, autorización nueva. Se registra en REGLAS_CRITICAS al implementar la 38 (§3.6) |
| **C4** | Sí: fila `CASHFLOW = {PIO, RITA}` en `cf_modulos_farmacias` (§3.1) |
| **C5** | Categoría nueva: `ERROR` hasta que Pio la acepte con la importación manual (§2.4) |
| **C6** | Mismo fichero que la última importación: no se escribe nada y el informe dice `SIN_CAMBIOS` (§2.5) |
| **C7** | Sí: la tarea de Cashflow no es obligatoria en la puerta de la noche ni en la de los preflights; solo se comprueba que no está en ejecución (§5.2) |
| **C8** | Sí: `farmacia` en importes y saldos, `saldo_inicial` en saldos e `id` en los dos (§3.7) |

### Decisiones de Pio tras la verificación del Excel (2026-11-18)

| Id | Decisión de Pio |
|---|---|
| **E1** | **Cuadre = saldo inicial + ΣRE − ΣRS.** Las salidas `RS` están en positivo en las celdas: un `RS` positivo es una salida. El importe se guarda con el signo de la celda y la web interpreta el sentido por el prefijo de la categoría (§2.4, §3.5, §3.7) |
| **E2** | El texto que sale de una fórmula y las celdas con solo espacios cuentan como **vacías**. Cualquier otro texto en una celda de importe es `ERROR` (§2.3) |
| **E3** | **Pio no modifica el Excel.** Un importe con más de 2 decimales se **redondea al céntimo (half-up)** y se avisa en el informe (hoja, celda, valor original y redondeado), sin `ERROR`. El cuadre se comprueba con los valores guardados en el Excel **sin redondear** (§2.3, §2.4, §4) |
| **E4** | «Hoja ignorada con datos» = hoja ignorada con **algún importe distinto de 0** (§2.4) |
| **E5** | `SL` sin saldo en la primera decena: **aceptado** (§2.4) |
| **E6** | Las hojas no listadas se ignoran (§2.2) |
| **E7** | Saldo según bancos distinto del de fórmulas: **nunca `ERROR`** (§2.4) |

## 1. Verificación del Excel: HECHA (2026-11-18)

`CONFIRMADO POR VERIFICACIÓN`. Chequeo READ_ONLY, fuera del repositorio, sobre una copia del fichero de la ruta C1.
Se abrió con `openpyxl` 3.1.5 con `keep_vba=False`, sin ejecutar macros, dos veces: con y sin `data_only`. El informe
no contiene conceptos ni categorías: solo recuentos, posiciones de celda, fechas de decena y sumas de control.
Evidencias en `C:\ControlFarmacias\evidencias_h7_excel\` (copia, `verificacion_excel.json`, `verificacion_2.json`,
los dos scripts y `SHA256SUMS.txt`).

- **Selección (C1):** un único candidato y ningún temporal `~$`. El nombre actual no es «CASHFLOW» a secas (lleva
  sufijos), lo que confirma que se elige por prefijo. El SHA-256 del original es el mismo antes y después de copiar.
- **Hojas:** `PÍO`, `RITA` y `SL` visibles. `Banco_4` a `Banco_10` están ocultas: son una plantilla con fórmulas y
  **ningún importe**. Además hay ocho hojas que la web no menciona (de SOE, posición de tesorería, comparativa,
  gráficas y control de cambios); se ignoran (E6).
- **Fórmulas:** ninguna sin valor guardado.
- **Encabezados:** las filas 2 y 3 traen **fechas completas** (`datetime`). En las tres hojas hay 180 decenas
  consecutivas, del 2024-01-01 al 2028-12-31, que empiezan el día 1, 11 o 21. Las columnas `TOTAL` están en `AN`,
  `BY`, `DJ`, `EU` y `GF`.
- **Categorías:** todas con prefijo `RE` o `RS`. PÍO y RITA tienen 38 categorías distintas cada una, y SL, 47.
- **Filas de saldo:** encontradas por texto, una vez cada una: PÍO 4/260/261, RITA 4/205/206 y SL 4/92/93.
- **Saldo inicial = saldo final de la decena anterior** en todas las decenas.
- **Importes:** PÍO 3204 y RITA 1917, distintos de 0. `SL` no tiene ninguno.
  - `RE` siempre positivo.
  - `RS` positivo, salvo 12 negativos en PÍO y 11 en RITA (probablemente devoluciones).
- **Cuadre:** con la suma literal fallan 115 de 180 decenas en PÍO y 117 en RITA. Con **saldo inicial + ΣRE − ΣRS**
  cuadran **180 de 180** en las dos (E1).
- **Texto en celdas de importe:** 3 en PÍO y 13 en RITA. La mayoría salen de fórmulas y tienen un carácter; tres
  son solo espacios (E2).
- **Más de 2 decimales:** una celda en PÍO y otra en RITA, las dos de fórmula (E3).
- **Saldo según bancos:** vacío en 77 decenas de cada hoja. Igual al de fórmulas en 8 (PÍO) y 33 (RITA); distinto en
  95 (PÍO) y 70 (RITA) (E7).
- **SL:** no tiene saldo en la primera decena (columna D) (E5).
- **Búsqueda previa, antes de C1 (2026-11-17):** sin resultado útil fuera de la ruta C1. No se buscó en
  `C:\ControlFarmacias` entero porque el hook bloquea esa búsqueda (abarca `logs/agentes`).

## 2. Lectura del Excel

### 2.1 Fichero, copia y huella

- **Selección del fichero (C1):** en `C:\GoogleDrive\CASHFLOW`, los `.xlsm` cuyo nombre empieza por `CASHFLOW`, sin
  contar los que empiezan por `~$` (temporales de Excel). Tiene que haber exactamente uno. Con ninguno
  (`EXCEL_NO_ENCONTRADO`) o con más de uno (`EXCEL_AMBIGUO`), la importación es `ERROR` y se conserva la vigente. El
  nombre puede cambiar entre importaciones.
- El script nunca abre el original. Lo copia, aunque esté abierto en Excel, a
  `C:\ControlFarmacias\cashflow\copias\<fecha>_<sha8>.xlsm`, fuera del repositorio, y trabaja sobre la copia.
- Si la copia falla o el fichero cambia mientras se copia (el SHA-256 de antes y el de después son distintos), la
  importación queda en `ERROR` y se conserva la vigente anterior.
- `archivo_hash` es el SHA-256 de la copia, y `archivo_nombre`, el nombre del original, sin la ruta.

### 2.2 Estructura esperada (según la web, confirmada en §1)

- **Hojas `PÍO`, `RITA` y `SL`:** cuentas bancarias de PIO, de RITA y sin farmacia; `SL` está vacía en 2026. Se
  ignoran `Banco_4` a `Banco_10` (salvo que tengan importes, §2.4) y cualquier otra hoja no listada (E6).
- **Columnas de decena:** desde la columna D. La fila 2 es el inicio de la decena (día 1, 11 o 21) y la fila 3, el fin.
  Se ignoran las columnas cuyo encabezado empieza por «TOTAL»; se localizan por el texto, no por la letra.
- **Columna A:** categoría, «RE …» (entrada) o «RS …» (salida). **Columna B:** concepto.
- **Filas sin columna A:** totales, saldos y cuadre. Solo se leen las tres de saldo, localizadas por el texto de la
  columna B en cada hoja, porque PÍO y RITA tienen filas distintas.
- **Fechas:** cada columna da `decena_inicio` y `decena_fin` como fechas completas (confirmado en §1). Un encabezado
  que no sea fecha es `ERROR`, y se exige que las decenas sean consecutivas, sin huecos ni repeticiones.

### 2.3 Importes

- Valor guardado de la celda con su signo, sin deducirlo de la categoría ni invertirlo (decisión de Pio; E1). Un `RS`
  positivo es una salida.
- `0` y celda vacía no se guardan.
- **Texto (E2):** cuentan como vacías, y no se guardan, las celdas con fórmula cuyo valor guardado es texto y las
  celdas que solo contienen espacios. Cualquier otro texto en una celda de importe es `ERROR`. El informe da cuántas
  se trataron como vacías y su posición (hoja y celda), nunca su contenido.
- **Decimales (E3):** se pasa a `numeric(14,2)`. Si un valor tiene más de 2 decimales significativos (diferencia con su
  redondeo mayor que 0,000001), se **redondea al céntimo (half-up)**, no es `ERROR` y el informe lo avisa con hoja,
  celda, valor original y valor redondeado. Pio no modifica el Excel.
- Los saldos se guardan también al céntimo. `PROPUESTA` (extensión de E3, pendiente de confirmar por Pio): un saldo con
  más de 2 decimales se redondea igual y se avisa.

### 2.4 Fallo cerrado

Cualquiera de estos casos da `ERROR`, con un `detalle_error` sin conceptos, y la importación vigente anterior se
mantiene:

- una celda con fórmula sin valor guardado;
- una hoja esperada que falta, o una hoja ignorada con algún importe distinto de 0 en una fila de categoría (E4).
  Las fórmulas de plantilla sin importes, como las de `Banco_4` a `Banco_10`, no cuentan como datos;
- encabezados de decena ilegibles, no consecutivos o repetidos;
- una fila con importes y sin categoría, o una categoría sin prefijo `RE` o `RS`;
- una fila de saldo que falta o está repetida;
- un texto en una celda de importe que no sea de fórmula ni solo espacios (E2);
- un cuadre que falla (E1): en alguna decena, **saldo inicial + ΣRE − ΣRS** no es igual al saldo según fórmulas (al
  céntimo). Se calcula con los valores guardados en el Excel **sin redondear** (E3).
  - **`SL` sin saldo en la primera decena (E5):** aceptado. Esa decena de `SL` no tiene fila en `cf_cashflow_saldos` y
    se omite del cuadre siempre que no tenga importes. Cualquier otra decena sin saldo inicial o sin saldo según
    fórmulas sigue siendo `ERROR`.
  - Que el saldo según bancos esté vacío no es error: quiere decir que la decena aún no está cuadrada, y se guarda
    `null`.
  - Si está informado y no coincide con el de fórmulas, **nunca es `ERROR`** (E7): es una diferencia que muestra la
    web.
- **Categorías nuevas (C5):** una categoría que no estaba en la importación vigente.
  - **PROPUESTA:** en la importación nocturna, `ERROR`. Pio la acepta lanzando la manual con
    `--aceptar-categorias-nuevas`, que informa de cuántas son, sin nombrarlas.
  - Alternativa: aceptar cualquier categoría con prefijo `RE` o `RS`. Es menos cerrado.

### 2.5 Mismo fichero (C6)

Si el SHA-256 es igual al de la última importación registrada, sea `OK` o `ERROR`, no se escribe nada y el informe
dice `SIN_CAMBIOS`. Así un `ERROR` no se repite cada noche. Al corregir el Excel, cambia la huella y se vuelve a
importar.

## 3. Esquema propuesto (migración 38)

Se mantienen los nombres de tablas y columnas de la petición. Las diferencias están en §3.7.

### 3.1 Permiso por módulo

- `cf_modulos_farmacias` solo admite el módulo `TRABAJADORES` (`31_cf_trabajadores.sql:31-34`). La 38 amplía el check a
  `('TRABAJADORES', 'CASHFLOW')` e inserta `CASHFLOW = {PIO, RITA}` (C4).
- `cf_configuracion.farmacias_habilitadas` no cambia (`{PIO}`), y facturas, albaranes y conciliación siguen solo PIO.
- **Efecto en los postchecks:** `cf_modulos_farmacias` está en `TABLAS_TRABAJADORES`. Su fila nueva y su check
  ampliado son un cambio dentro del alcance de la 38, que `desplegar_38` y su postcheck esperan; para las noches se
  informa aparte, como el resto de Trabajadores.
- Alternativa: una tabla propia de Cashflow, que no toca la de Trabajadores. **No se propone**, porque la web ya usa
  `cf_modulos_farmacias`.

### 3.2 `cf_cashflow_cuentas`

| Columna | Tipo | Regla |
|---|---|---|
| `codigo` | text | PK; `PIO`, `RITA` o `SL` |
| `farmacia` | text | `PIO`, `RITA` o null (`SL`) |
| `hoja` | text | not null; `PÍO`, `RITA` o `SL` |

Se carga en la propia migración con las tres filas y no la escribe nadie más: es fija.

### 3.3 `cf_cashflow_importaciones`

| Columna | Tipo | Regla |
|---|---|---|
| `id` | uuid | PK |
| `archivo_nombre` | text | not null; sin ruta |
| `archivo_hash` | text | not null; `^[0-9a-f]{64}$` |
| `origen` | text | `NOCHE` o `MANUAL` |
| `estado` | text | `OK` o `ERROR` |
| `detalle_error` | text | not null si `ERROR`, null si `OK`; códigos y recuentos, nunca conceptos |
| `filas` | integer | importes guardados; 0 si `ERROR` |
| `importado_at` | timestamptz | `now()` |
| `vigente` | boolean | not null; solo puede ser true si `OK` |

- **Único parcial:** `(vigente) WHERE vigente`, de modo que solo hay una importación vigente.
- Una importación `ERROR` no tiene importes ni saldos (check en la RPC, §3.5).

### 3.4 `cf_cashflow_importes` y `cf_cashflow_saldos`

**`cf_cashflow_importes`**
- `id` (bigint identity), `importacion_id` (FK a importaciones), `cuenta` (FK a cuentas), `farmacia`;
- `decena_inicio` y `decena_fin` (date, con `decena_fin >= decena_inicio`);
- `categoria` (literal de la columna A, `^R[ES] `);
- `concepto` (columna B);
- `importe` (`numeric(14,2)`, distinto de 0; con el signo de la celda, de modo que un `RS` positivo es una salida, E1);
- `fila_excel` (integer).

**`cf_cashflow_saldos`**
- `id`, `importacion_id`, `cuenta`, `farmacia`, `decena_inicio`;
- `saldo_inicial`, `saldo_formulas` (not null) y `saldo_bancos` (null si está vacío);
- único `(importacion_id, cuenta, decena_inicio)`.

En los dos, `farmacia` se copia de la cuenta (null en `SL`) y un check comprueba que coincide.

### 3.5 Escritura: una sola RPC, solo inserción

- **Nadie escribe directamente en las tablas:** ni la web, ni `cf_lectura`, ni el rol del sistema. Se quitan todos
  los privilegios de escritura.
- **RPC `cf_cashflow_registrar_importacion(p_importacion jsonb, p_importes jsonb, p_saldos jsonb)`**, security
  definer, `search_path` fijo y EXECUTE solo para el rol del sistema. En una transacción:
  - inserta la importación, sus importes y sus saldos;
  - si es `OK` y todo valida, pone `vigente = false` en la anterior y `vigente = true` en la nueva;
  - si es `ERROR`, solo inserta la importación, con `vigente = false`; la vigente anterior no cambia;
  - **vuelve a validar en la BD** (falla cerrado aunque el script tenga un fallo): cuadre de saldos (E1), cuentas y
    farmacias, decenas, importes distintos de 0, número de filas igual a `filas`, y que no exista ya una importación
    con ese hash. Si algo falla, la transacción entera se deshace y el script registra un `ERROR` aparte;
  - **cuadre en la BD:** saldo inicial + Σ importes `RE` − Σ importes `RS` = saldo según fórmulas, con los importes
    ya redondeados. `PROPUESTA` (pendiente de confirmar por Pio): como el cuadre exacto se hace en el script con los
    valores sin redondear (E3), la RPC admite en cada decena una diferencia de hasta 0,005 por importe redondeado de
    esa cuenta y decena. El script marca esos importes en `p_importes` con un campo de validación que no se guarda.
    Sin importes redondeados, la diferencia admitida es 0;
  - toda la importación entra o no entra nada: nunca queda a medias.
- **Solo inserción:** un trigger rechaza `UPDATE`, `DELETE` y `TRUNCATE` en todas las tablas (`BORRADO_NO_PERMITIDO`,
  `SOLO_INSERCION`). La única excepción es el cambio de `vigente` que hace la RPC: se reconoce por una variable de
  transacción que solo pone la RPC.
- **Las importaciones antiguas se conservan.** Las copias del Excel se guardan en disco (§2.1); su limpieza la decide
  Pio, más adelante.

### 3.6 Lectura, RLS y rol del sistema

- **`cf_lectura`:** `SELECT` en las cuatro tablas, con lo que queda ampliada su lista cerrada (decisión de Pio).
- **RLS** en las cuatro tablas, con la regla de la 31 y sin funciones security definer (regla del 2BN):
  `farmacia is null or exists (select 1 from cf_modulos_farmacias m where m.modulo = 'CASHFLOW' and farmacia =
  any(m.farmacias))`. Así `SL` es visible para PIO y para RITA. Las importaciones no tienen farmacia: son visibles
  para `cf_lectura`.
- **Ningún rol de la web** (`cf_trabajadores_web`, `cf_pagos_web`) tiene privilegios sobre estas tablas.
- **Rol del sistema (C3):** la 38 le quita los privilegios por defecto de Supabase sobre las tablas y la secuencia
  nuevas, y le da EXECUTE solo sobre la RPC. Para eso hay que nombrarlo.
  - **AUTORIZACIÓN EXPRESA DE PIO (2026-11-17, C3; reconfirmada el 2026-11-19 tras renumerar)**, limitada a `sql/migrations/38_*.sql` y su rollback. Tests,
    scripts y documentación no lo nombran.
- `anon`, `authenticated` y `public` no tienen nada.

### 3.7 Diferencias con el contrato de la web (C8)

- **`farmacia` en `cf_cashflow_importes` y `cf_cashflow_saldos`:** columna añadida para la RLS, sin subconsulta a
  cuentas. La web puede ignorarla.
- **`saldo_inicial` en `cf_cashflow_saldos`:** añadida para comprobar el cuadre en la BD. La web puede ignorarla o
  usarla.
- **`id` en importes y saldos:** añadido (la petición no lo nombra).
- **Escritura por RPC** en lugar de inserciones directas: no afecta a la web, que solo lee.
- **Sentido del importe (E1):** la web lo interpreta por el prefijo de la categoría. `RE` es entrada y `RS` es salida,
  y un `RS` positivo resta del saldo. Un `RS` negativo (devolución) suma.
- El resto de nombres de tablas y columnas, igual que en la petición.

## 4. Script de importación

`src/cashflow/importar_cashflow.py` (`PROPUESTA`; sin código en este hito).

- **Modos:**
  - `--noche` lo lanza la tarea;
  - `--manual` lo lanza Pio, con origen `MANUAL`. Con `--simular`, lee, valida e informa sin escribir nada.
- **Puertas** (las mismas en los dos modos):
  - ninguna de las tres tareas en ejecución;
  - ninguna noche `EN_CURSO` en `cf_noches_automaticas`;
  - la migración 38 presente;
  - la ruta configurada existe.
  Si una falla, no escribe nada y termina con código distinto de 0.
- **Postcheck propio por fila (2AX):** antes y después de la escritura. Solo pueden cambiar las tablas `cf_cashflow_*`
  y solo con las filas de esa importación (y el cambio de `vigente`). Cualquier otra fila cambiada da `PARADA`.
- **Informe** en `C:\ControlFarmacias\cashflow\informes\<fecha>\` (`informe.json`, `resumen.txt` y `SHA256SUMS.txt`),
  fuera del repositorio. Contiene:
  - estado, origen y hash del fichero;
  - por cuenta: número de decenas, de filas, de entradas y de salidas, y suma de control de los importes;
  - el cuadre (decenas que cuadran y decenas sin saldo de bancos);
  - avisos de redondeo (E3): hoja, celda, valor original y valor redondeado;
  - celdas de texto tratadas como vacías (E2): número y posición (hoja y celda), sin contenido;
  - categorías nuevas, solo su número.
  **Nunca contiene conceptos ni categorías.**
- **Credenciales:** las mismas del sistema que usa la noche, sin variables nuevas. La contraseña o clave nunca aparece
  en argumentos ni en salidas.

## 5. Tarea nocturna

### 5.1 Hora (C2)

Hoy, según Task Scheduler:
- «ControlFarmacias - Importar facturas», 21:00, como `Usuari`;
- «Sincronización ControlFarmacias», 21:30, como el usuario de solo lectura;
- «ControlFarmacias - Automatizacion Alliance», 22:15, como `Usuari`, con un límite de 60 minutos (D5 de AUTO-A), así
  que termina como tarde a las 23:15.

**PROPUESTA: «ControlFarmacias - Importar Cashflow» a las 23:45, como `Usuari`.** Deja 30 minutos de margen tras el
límite de la noche y recoge los cambios del Excel del día.
- Alternativa: las 20:30. Va antes de todo, pero no recoge lo que Pio anote por la tarde.
- La tarea no se crea en este hito: se crea en el hito de despliegue, con la confirmación de Pio.

### 5.2 Puertas entre tareas (C7)

- **La tarea de Cashflow no arranca** si cualquiera de las otras tres está en ejecución o hay una noche `EN_CURSO`
  (§4).
- **La noche de las 22:15 y los preflights:** la tarea de Cashflow **no entra** en `TAREAS_PREVIAS` ni en
  `TAREAS_ESPERADAS`. Un fallo del Excel no para las facturas. Solo se añade la comprobación «Cashflow no en
  ejecución».
- La importación manual tampoco arranca entre las 21:00 y la hora de Cashflow si alguna tarea está en ejecución.

## 6. Postchecks de la noche y de las series

Igual que `TABLAS_PAGOS` (COD-1611):

- **`TABLAS_CASHFLOW`** en `src/facturas/runtime_supabase/noche_automatica.py`, junto a `TABLAS_PAGOS`
  (`noche_automatica.py:79-81`): `cf_cashflow_importaciones`, `cf_cashflow_cuentas`, `cf_cashflow_importes` y
  `cf_cashflow_saldos`.
  - Se añade a `TABLAS_FUERA_DEL_SNAPSHOT`.
  - Se lee aparte con `snapshot_aparte` (`noche_automatica.py:306-311`).
  - Se informa en `postcheck["cashflow"]`, con `afecta_al_veredicto: False`.
- **Series 2BJ y 2BP:** se tratan igual que `TABLAS_PAGOS`: fuera del criterio por fila e informadas aparte.
- **Orden:** este cambio va en el commit de la 38 (o antes), y siempre antes de desplegarla.

## 7. Plan de hitos

1. **Este diseño** (solo documentación).
2. **Hecho:** decisiones de Pio C1–C8 (2026-11-17), verificación del Excel real (2026-11-18, §1, READ_ONLY, sobre
   una copia fuera del repositorio) y decisiones de Pio E1–E7 (2026-11-18, §0).
3. **H7, solo local:**
   - migración 38 y su rollback (falla cerrado si hay importaciones);
   - `desplegar_38.py`, ensayado con la imitación del `postgres` de Supabase;
   - `importar_cashflow.py`, con tests sobre un Excel ficticio generado en el test (ningún dato real en el
     repositorio): estructura cambiada, fórmula sin valor, cuadre roto, cuadre con `RS` positivos y negativos,
     categoría nueva, mismo hash, decenas, signo, vigente, texto de fórmula y solo espacios como vacío, otro texto como
     `ERROR`, redondeo half-up con aviso, hoja ignorada con plantilla sin importes y con importes, y `SL` sin saldo en
     la primera decena;
   - `TABLAS_CASHFLOW` en la noche y las series;
   - suite completa y revisor PASS.
4. **H7-D:**
   - preflight READ_ONLY, `desplegar_38` una vez con la confirmación de Pio, y postcheck por fila;
   - primera importación `--manual --simular`; después, la real `--manual`;
   - creación de la tarea, con la confirmación de Pio.
5. **Web:** pasa de FIXTURES a lectura real con `cf_lectura` cuando haya una importación `OK` vigente.

## 8. Fuera de alcance

- Escribir en el Excel o ejecutar sus macros.
- Conciliación bancaria y Norma 43: siguen `NO IMPLEMENTADAS`. El saldo según bancos es el que Pio anota en el Excel,
  no un extracto.
- Facturas de RITA: siguen desactivadas.
- Previsiones y avisos: los calcula la web; el sistema no los guarda.
