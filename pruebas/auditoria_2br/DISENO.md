# Hito 2BR: detalle por línea en la conciliación (migración 30)

Solo local. Sin push. Producción no tocada.

## 1. Hallazgo (web, 2026-11-08)

`conciliacion_detalles` guarda `importe_documental`, `importe_farmatic` y `diferencia` en NULL
(`sql/migrations/24_cf_r17_recepcion.sql:338-354`, el alta no los incluye) y el estado de cada detalle es el de la
factura (`src/facturas/runtime_supabase/repositorios.py:614` antes del 2BR: `COINCIDE` si la factura es
`CONCILIADA`, si no `DIFERENCIA`). La web no puede decir qué línea explica una diferencia.

## 2. Diseño: valores por línea

Cada detalle guarda el importe del PDF, el importe de Farmatic, la diferencia y el estado **de su línea**. El
resultado de la factura (`conciliar_importes`, R11, tolerancia, resultado, `importe_explicado`, `diferencia`) **no
cambia**. Tolerancia por línea: **0,05** (la misma con la que casa una línea y la de R17).

| Detalle | PDF (`importe_documental`) | Farmatic (`importe_farmatic`) | `diferencia` | `estado` |
|---|---|---|---|---|
| Albarán casado 1:1 | importe de la línea, con signo (ABONO en negativo) | importe aplicado (PUC, o PVP con número exacto) | PDF − Farmatic | `COINCIDE` si \|dif\| ≤ 0,05; si no `DIFERENCIA` |
| Línea R17 (dos detalles `UNO_A_VARIOS`) | el de la línea, en los dos | el PUC de cada albarán | PDF − suma de la pareja, la misma en los dos | igual, el mismo en los dos |
| Línea sin coincidencia | importe de la línea | vacío | = PDF | `DIFERENCIA` |
| Línea sin importe documental (o de otra factura) | vacío | el aplicado, si lo hay | vacía | `NO_EVALUABLE` |
| Movimiento documental o ajuste fiscal | importe aplicado | vacío (sin contraparte en Farmatic) | vacía | `NO_EVALUABLE` |

- Una factura `CONCILIADA` por la tolerancia R11 (hasta 0,50) puede tener alguna línea en `DIFERENCIA`, y una en
  `DIFERENCIA` tiene en `COINCIDE` todas las líneas que casan: es la información que pedía la web.
- En R17, para sumar importes del PDF por línea se agrupa por `factura_albaran_extraido_id` (los dos detalles
  repiten el de la línea).
- **DECISIÓN DE PIO (2026-11-09):** los movimientos quedan `NO_EVALUABLE` («no se compara con Farmatic»); se acepta
  el cambio de clave idempotente; primero desplegar la 30 y después conciliar.
- No se rellenan `numero_albaran_documental` ni `numero_albaran_farmatic` (fuera del alcance; siguen en la
  provenance).

## 3. Una sola definición, en la BD y en Python

- **BD:** `cf_detalles_por_linea(factura, detalles jsonb)` (SQL, `stable`, solo el propietario la ejecuta). Lee el
  importe y el tipo de la línea en `facturas_albaranes_extraidos` **de esa factura**.
- **`cf_persistir_conciliacion` (30)** = texto exacto de la 24 con tres cambios (generador
  `generar_migracion_30.py`, reemplazos comprobados únicos): guarda los valores que calcula la BD; si el resultado
  trae `importe_documental` en un detalle, sus cuatro valores deben coincidir o rechaza
  `DETALLE_LINEA_NO_COINCIDE:<orden>` (sin escrituras). Un resultado sin esos campos (código anterior) se acepta y la
  BD guarda sus propios valores.
- **Python:** `conciliacion.valores_por_linea` (espejo exacto) y `DetalleConciliacion.importe_documental` (lo
  rellenan `detalle_desde_busqueda` y `detalles_desde_busqueda`); `payload_conciliacion` envía los cuatro valores por
  detalle.
- La clave idempotente (`sha256` del resultado) cambia respecto del código anterior porque el resultado lleva los
  valores nuevos: una reevaluación con la misma evidencia hecha con el código anterior no es replay del nuevo (crea
  intento). Con el mismo código, misma evidencia → misma clave.

## 4. Migración 30 y rollback

- Requiere la 29 (`MIGRACION_29_AUSENTE`). Idempotente.
- **Relleno determinista, una vez:** si no existe `conciliacion_detalles_previo_30`, la crea, guarda en ella los
  cuatro valores actuales de cada detalle y los recalcula con `cf_detalles_por_linea` sobre los detalles de cada
  conciliación (todas, vigentes o no; en producción, las 17). No toca `facturas`, `conciliaciones`, reservas ni
  historial: **el resultado de cada factura y de cada conciliación no cambia**.
- `conciliacion_detalles_previo_30`: RLS activada, sin privilegios para `anon`, `authenticated`, el rol del sistema ni
  `cf_lectura`.
- **Rollback** (`30_cf_detalle_por_linea.rollback.sql`): reinstala el texto exacto de la 24, devuelve a cada detalle
  rellenado sus valores previos exactos y deja los detalles persistidos después de la 30 con la semántica anterior
  (importes NULL, estado de la factura); elimina la tabla y la función. Esquema = 29.
- **Orden de despliegue:** primero la 30 y después conciliar con el código 2BR. Con la 29, el código 2BR persiste el
  estado por línea que envía, pero los importes por línea siguen en NULL.

## 5. `desplegar_30.py`

Patrón de `desplegar_29.py`: SHA LF del commit, destino productivo demostrado, una transacción.

- **Precondiciones (9):** 29 aplicada; 30 no aplicada; importes por línea todos NULL (estado de partida del
  hallazgo); privilegios mínimos 19; flags; sin locks de conciliación; sin locks de normalización; reservas
  coherentes (R15); propietarios `postgres` (2AX).
- **Postcondiciones (5):** datos sin cambios (conteos y huellas de facturas, conciliaciones, reservas y de cada
  detalle sin los cuatro valores); relleno igual a `cf_detalles_por_linea` y un valor previo por detalle; valores
  previos = valores antes del relleno; privilegios; propietarios (objetos nuevos del rol que despliega, `postgres` en
  Supabase; la RPC sigue siendo de `postgres`). Registra un resumen por tipo y estado.
- **Ensayo** con el rol que imita al `postgres` de Supabase (norma 2BN-D): aplicado, segundo intento revertido en
  precondiciones y rollback con la imitación (esquema 29 y detalles exactamente como antes). Las plantillas de test
  aplican la 30 como `postgres`, como en Supabase (con la imitación los dos objetos nuevos serían del rol imitador).

## 6. Tests

- `tests/facturas/runtime_supabase/test_detalle_por_linea_2br.py` (10, sin BD): 1:1, abono, sin coincidencia, sin
  importe, R17, movimientos y ajustes, resultado de la factura igual y payload.
- `tests/facturas/runtime_supabase/test_integracion_pg17_2br.py` (16): rollback = esquema 29; exige la 29;
  privilegios; **relleno = conciliar con la 30** (08007969 real, `CONCILIADA` con R17 y `DIFERENCIA` sin la recepción
  común: mismos detalles, mismo resultado, sin cambios en el resto); la BD acepta los valores correctos, rechaza 5
  incoherentes y calcula los suyos si no vienen; **espejo Python = SQL** en 11 casos (incluida la línea de otra
  factura, que la BD deja `NO_EVALUABLE` y rechazaría); rollback exacto; precondiciones de solo lectura; ensayo
  completo de `desplegar_30.py`.
- `test_conciliacion_manual_2av.py`: el detalle sintético lleva su importe del PDF (su estado es el de su línea).
