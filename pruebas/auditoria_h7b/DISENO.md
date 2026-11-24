# H7b: apuntes manuales de Cashflow desde la web (diseño)

Estado (2026-11-24): **DISEÑO, todo `PROPUESTA`**. Sin código, sin migración y sin producción. Encargo de Pio del
2026-11-24: diseñar los apuntes manuales de Cashflow que pide la web.

Etiquetas: `CONFIRMADO POR CÓDIGO` (fichero:línea), `PROPUESTA`, `SUPUESTO` (falta confirmarlo con Pio o con la web)
y `DECISIÓN PENDIENTE`.

## 0. Qué se pide y qué no sabemos todavía

- **`SUPUESTO`:** la petición de la web no está escrita en el repositorio. Este diseño supone que la web quiere
  **añadir apuntes que no están en el Excel** (por ejemplo, un pago o un cobro previsto) para verlos en el Cashflow sin
  esperar a que Pio los pase al Excel. Si la web pide otra cosa (por ejemplo, corregir importes importados), este
  diseño no vale: corregir lo importado está prohibido (solo inserción, REGLAS_CRITICAS «Cashflow (H7)»).
- **Lo que no cambia** (`CONFIRMADO POR CÓDIGO`, migración 38 y REGLAS_CRITICAS «Cashflow (H7)»):
  - el Excel de Pio sigue siendo la fuente de los importes y saldos importados;
  - las tablas `cf_cashflow_importaciones`, `cf_cashflow_importes` y `cf_cashflow_saldos` siguen siendo solo de
    inserción, y su única escritura sigue siendo la RPC de importación;
  - el cuadre E1 (`saldo_inicial + Σ RE − Σ RS = saldo_formulas`) se sigue comprobando solo con lo importado;
  - la web sigue leyendo esas tablas con `cf_lectura`.

## 1. Modelo (`PROPUESTA`)

Precedente: Pagos (H6, migración 35), la única escritura de la web fuera de Trabajadores. Se copia su patrón: tabla
propia, rol propio, anulación en lugar de borrado, autor por transacción e historial por trigger.

### 1.1 Tabla `cf_cashflow_apuntes_manuales`

| Columna | Tipo y regla |
|---|---|
| `id` | `uuid` por defecto |
| `cuenta` | `text`, referencia a `cf_cashflow_cuentas(codigo)` (`PIO`, `RITA`, `SL`) |
| `farmacia` | `text`, la de la cuenta (la pone el trigger; `SL` sin farmacia), con el mismo check que `cf_cashflow_importes` |
| `decena_inicio` | `date`; día 1, 11 o 21 |
| `categoria` | `text`, `^R[ES] ` como en `cf_cashflow_importes`; además, una categoría existente de esa cuenta en la importación vigente (H7B-D4) |
| `concepto` | `text`, de 1 a 200 caracteres, obligatorio |
| `importe` | `numeric(14,2)`, distinto de 0, con el mismo criterio de signo que el Excel (E1: el sentido lo da `RE`/`RS`) |
| `estado` | `ABIERTO`, `PASADO_AL_EXCEL` o `ANULADO` |
| `autor`, `creado_at` | del `cf.autor` de la transacción (sin él, `AUTOR_AUSENTE`) y `now()` |
| `cerrado_por`, `cerrado_at`, `motivo_cierre` | solo al pasar a `PASADO_AL_EXCEL` o `ANULADO`; el motivo es obligatorio |

- **Sin `DELETE` ni `TRUNCATE`** para nadie; un trigger los rechaza (`BORRADO_NO_PERMITIDO`), como en la 35 y la 38.
- **`UPDATE` solo para cerrar:** `ABIERTO` → `PASADO_AL_EXCEL` o `ANULADO`, y nada más (`SOLO_CERRAR`). Corregir es
  anular y crear otro. Un apunte cerrado no se reabre.
- **Historial** `cf_cashflow_apuntes_historial`: lo escribe un trigger en cada alta y cada cierre, solo inserción e
  inmutable, como `pagos_historial`.

### 1.2 Cómo los ve la web

- La web muestra, por cuenta y decena, **dos cifras separadas**:
  - el saldo del Excel (`saldo_formulas` de la importación vigente), sin tocar;
  - el **saldo con apuntes** = saldo del Excel + Σ apuntes `ABIERTO` de esa cuenta hasta esa decena (los `RS` restan,
    con su signo, igual que en E1).
- Los apuntes se marcan siempre como manuales y con su autor. Nunca se mezclan con los importes importados ni cambian
  el cuadre E1.
- **Duplicados:** cuando Pio pasa el apunte al Excel, el apunte sigue `ABIERTO` y contaría dos veces. La web debe
  cerrarlo como `PASADO_AL_EXCEL`. El sistema **no** lo detecta solo: emparejar un apunte con un importe del Excel por
  importe y decena no es seguro, y ante la duda se falla cerrado (H7B-D6). Como ayuda, la web puede avisar cuando una
  importación nueva trae un importe igual en la misma cuenta, decena y categoría, pero el cierre lo hace una persona.

### 1.3 El sistema no usa los apuntes

- Ni la importación de Cashflow, ni la noche, ni la conciliación, ni ningún otro proceso los leen para decidir nada.
- En los postchecks de la noche y de las series 2BJ/2BP entran en `TABLAS_CASHFLOW`, informados aparte y sin afectar
  al veredicto, como Pagos.

## 2. Permisos y farmacia (`PROPUESTA`)

- **Rol nuevo `cf_cashflow_web`** (H7B-D2): `SELECT` e `INSERT` sobre `cf_cashflow_apuntes_manuales`, `UPDATE` solo de
  las columnas de cierre y `SELECT` sobre el historial. Nada más: ni facturas, ni pagos, ni trabajadores, **ni las
  tablas importadas de Cashflow**. REGLAS_CRITICAS «Cashflow (H7)» dice que ningún rol de la web tiene privilegios
  sobre ellas, y no hace falta cambiarlo: las validaciones de §3 las hace el trigger, que se ejecuta con los
  privilegios de su propietario, como en la 35. La web sigue leyendo lo importado con `cf_lectura`. Contraseña SCRAM fijada por Pio fuera del repositorio, como
  `cf_pagos_web`.
- **`cf_lectura`** lee las dos tablas nuevas con la regla de módulo de la 38 (sin funciones security definer, regla
  del 2BN).
- **Farmacia:** PIO. **RITA, no, salvo decisión de Pio:** su excepción vigente es SOLO para sus datos bancarios del
  Excel importado (REGLAS_CRITICAS «Cashflow (H7)»), y un apunte manual no sale del Excel. Admitir apuntes de RITA
  **amplía esa excepción** y exige su decisión expresa en REGLAS_CRITICAS (H7B-D3). RITA sigue sin facturas en
  cualquier caso. La cuenta `SL`, sin farmacia, solo si Pio lo decide.
- **Autorización:** como en la 35 y la 38, la migración tendría que nombrar el rol del sistema para quitarle los
  privilegios por defecto de Supabase sobre lo nuevo. Hace falta una **AUTORIZACIÓN EXPRESA de Pio** solo para esa
  migración y su rollback (H7B-D8). Sin ella no se implementa.

## 3. Validaciones en la BD (`PROPUESTA`)

Todas en el trigger de alta, fallando cerrado sin escribir nada:

- la cuenta existe y está permitida: PIO, y RITA o `SL` solo si Pio los admite (H7B-D3);
- `decena_inicio` es inicio de decena y está dentro del rango permitido (H7B-D5);
- la categoría existe para esa cuenta en la importación vigente (H7B-D4); sin importación vigente, no se admite
  ningún apunte (`SIN_IMPORTACION_VIGENTE`);
- importe distinto de 0 y concepto no vacío;
- autor presente (`AUTOR_AUSENTE`).

## 4. Migración, tests y despliegue (`PROPUESTA`)

- **Numeración:** 39 = «Actualizar ahora», 40 = R21 (DISEÑO §9 de `pruebas/auditoria_r21/DISENO.md`). Esta sería la
  **41** (H7B-D9). Requiere la 38.
- **Rollback 41:** falla cerrado si hay algún apunte (`ROLLBACK_41_CON_APUNTES`), como el de la 38.
- **Tests previstos (PostgreSQL 17 local):**
  - la 41 es idempotente y el rollback vuelve al esquema anterior;
  - el rol nuevo inserta y cierra, y no puede borrar, reabrir, cambiar el importe ni tocar ninguna otra tabla;
  - cada validación de §3 rechaza con su motivo;
  - `cf_lectura` lee según la farmacia del módulo y no ve lo de otra;
  - una importación nueva de Cashflow no toca los apuntes y los apuntes no cambian el cuadre de la importación;
  - el postcheck informa las tablas nuevas aparte;
  - el ensayo de `desplegar_41` con la imitación del `postgres` de Supabase, en la suite histórica;
  - la prueba de acceso `probar_acceso_cf_cashflow_web.py` (terminal de Pio).
- **Despliegue (41-D):** commit con código y push de Pio; flags apagados; preflight READ_ONLY; `desplegar_41` una vez
  con confirmación explícita de Pio; postcheck por fila (solo aparecen los objetos nuevos); Pio fija la contraseña;
  prueba de acceso; flags encendidos. Después, `docs/web/ESQUEMA_CASHFLOW.md` con las tablas nuevas para la web.

## 5. Decisiones para Pio

| Id | Pregunta | Recomendación |
|---|---|---|
| H7B-D1 | ¿Qué pide exactamente la web? Hace falta el texto de la petición | Confirmar el `SUPUESTO` de §0: apuntes que no están en el Excel, nunca corregir lo importado |
| H7B-D2 | ¿Rol nuevo o ampliar `cf_pagos_web`? | Rol nuevo `cf_cashflow_web`, limitado a estas tablas (cada rol de la web, un solo módulo) |
| H7B-D3 | ¿Qué cuentas admiten apuntes: PIO, RITA, SL? | Solo PIO. RITA amplía su excepción (hoy solo datos bancarios del Excel importado) y exige decisión expresa en REGLAS_CRITICAS; SL solo si Pio lo pide |
| H7B-D4 | ¿Categorías libres o solo las existentes? | Solo las de esa cuenta en la importación vigente; una nueva se añade en el Excel |
| H7B-D5 | ¿Qué decenas? | Desde la decena actual (en `Europe/Madrid`) hasta la última de la importación vigente; nunca decenas pasadas |
| H7B-D6 | ¿Se cierra solo un apunte cuando aparece en el Excel? | No. Lo cierra una persona como `PASADO_AL_EXCEL`; la web solo avisa de posibles duplicados |
| H7B-D7 | ¿Los apuntes cuentan en el saldo que muestra la web? | Solo en una cifra aparte («saldo con apuntes»); el saldo del Excel no cambia |
| H7B-D8 | Autorización para nombrar el rol del sistema solo en la 41 y su rollback | Necesaria para implementar, como en la 35 y la 38 |
| H7B-D9 | Numeración | 41 (39 = «Actualizar ahora», 40 = R21) |
