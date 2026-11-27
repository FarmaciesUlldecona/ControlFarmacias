# FACTURAS-0: Paso 0 de la fábrica de lectores (diseño)

Encargo de Pio del 2026-11-27. **Solo diseño:** sin código y sin escrituras en producción. Lo que se ha leído de producción
ha sido una única lectura READ_ONLY autorizada por Pio.

Contexto y estrategia (fuera del repositorio): `C:\ControlFarmacias\estrategia_facturas\INFORME_FACTURAS_0.md`.
Evidencias: `C:\ControlFarmacias\estrategia_facturas\lectura_ro\` (`SHA256SUMS.txt` en la carpeta superior).

Etiquetas: `CONFIRMADO POR LECTURA` (READ_ONLY o espejo local), `CONFIRMADO POR CÓDIGO`, `PROPUESTA` (pendiente de
decisión de Pio) e `INFERIDO`.

## 0. Decisiones de Pio (2026-11-27)

| Id | Decisión |
|---|---|
| **F0-1** | Estrategia «fábrica de lectores»: un lector determinista por proveedor, escrito a partir de facturas reales. **Nunca IA leyendo facturas por la noche** |
| **F0-2** | Aprobado el **Paso 0**: verificador de literalidad independiente del lector, contrato mínimo obligatorio y aviso de proveedor nuevo en `para_revisar` |
| **F0-3** | El contrato mínimo corrige cinco fallos: (1) CIF del emisor en su columna; (2) tipo de documento real; (3) importe real de cada vencimiento; (4) no persistir si el cuadre fiscal falla; (5) comprobar que albaranes + movimientos = total. **Sin romper Alliance** |
| **F0-4** | HEFAME: recargo de equivalencia de la clase «No.» al **5,2 %** |
| **F0-5** | Orden de lectores: **HEFAME** y después los otros 7 del 80 % por importe: Cofares, Suavinex, Fedefarma, Dermofarm, Pierre Fabre, Kenvue y Ecoceutics |

**Decisiones de Pio, segunda tanda (2026-11-27):**

| Id | Decisión |
|---|---|
| **F0-6** | HEFAME, página 2: 0,01 por componente en lo recalculado; exacto en lo impreso (§6.1, tal como se recomienda) |
| **F0-7** | HEFAME, conciliación: número sin ceros a la izquierda; ventana de 0 a +4 días; 0,01 por fila; internos y `91…` solo con candidato único (§6.2, tal como se recomienda) |
| **F0-8** | Redondeo documental de §3.5: `mín(0,01 × filas; 0,50)` |
| **F0-9** | La 42 corrige `tipo_documento` también en las facturas existentes (§3.2), con aviso a la web |
| **F0-10** | Numeración: **42 = Paso 0**; «Actualizar ahora» pasa a la **43** |

Siguen como `PROPUESTA`, pendientes de Pio, las demás piezas de §2–§5.

## 0a. Paso 0a: verificador de literalidad implementado (2026-11-27)

`CONFIRMADO POR TEST` y `CONFIRMADO POR MEDICIÓN` (banco local, sin producción).

- **Código.** `src/facturas/certificacion/literalidad.py`, versión 0.1.0, con los tests de
  `tests/facturas/certificacion/test_literalidad.py`.
  - Solo importa `pypdf` y la biblioteca estándar; un test lo comprueba.
  - No tiene migración y no está enchufado a la noche ni a la persistencia.
  - Implementa §2, con dos detalles:
    - la página citada debe caer dentro de la factura;
    - las evidencias de un valor deben repetir el literal del campo.
  - Listas cerradas: derivadas = {R14}; decisiones de Pio = {} (ningún valor documentado de Alliance la usa).
- **Banco Alliance 1.3.2.** Scripts y salidas en `C:\ControlFarmacias\estrategia_facturas\banco_literalidad\`:
  - **94 PDF Alliance** distintos del espejo. 81 tienen salida de `alliance-local` (179 facturas). Los 13 restantes
    no los reconoce el lector, así que no hay nada que verificar.
  - **179 de 179 facturas `LITERALIDAD_OK`.**

    | Clase | Valores documentados |
    |---|---|
    | Verificados `LITERAL` | 48.835 |
    | `DERIVADO` por R14 (importe del vencimiento) | 179 |
    | Fallidos (`NO_LITERAL`) | **0** |
    | `NO_EVALUABLE` | **0** |

  - Tiempo del verificador: 0,39 s como máximo por documento; 54 s el banco entero, con el lector.
  - Los valores normalizados del proveedor (por ejemplo, `ESPANA` en lugar de `ESPAÑA`) se aceptan como texto: el
    valor, sin acentos ni puntuación, está contenido en el literal impreso.
- **Sensibilidad** (mutaciones sobre la salida normalizada del banco):
  - **38.700 de 38.700 mutaciones detectadas:**

    | Mutación | Casos |
    |---|---|
    | Importe +0,01 | 20.524 |
    | Fecha +1 día | 9.062 |
    | Número de albarán con un carácter cambiado | 8.704 |
    | Signo de movimiento cambiado | 410 |

  - **Límite medido: verificar el payload de un documento contra el PDF del documento siguiente.** Siguen pasando
    como `LITERAL` 3.648 valores (7 %). Son literales cortos o repetidos que aparecen en cualquier factura de
    Alliance: tipo de pedido, porcentajes, datos fijos del proveedor e importes que coinciden.
  - La comprobación «el literal aparece en la página» **no ancla la fila**.
  - **Mejora propuesta (0.2.0):** exigir también que el `fila_literal` de la evidencia aparezca en la página, o la
    posición (`bbox`) con una herramienta independiente, antes de usar el verificador como bloqueante. **Aprobada
    por Pio e implementada** (§0b).

## 0b. Verificador 0.2.0: anclaje a la fila o bloque (2026-11-27)

Aprobado por Pio. `CONFIRMADO POR TEST` (56 tests) y `CONFIRMADO POR MEDICIÓN`, con el mismo banco y la misma
prueba de mutaciones.

- **Qué añade.** Además de estar en la página:
  1. **El literal está en su fila o bloque.**
     - `pypdf` da cada fragmento de texto con su posición (`visitor_text`, coordenadas desde el borde superior,
       como las del lector).
     - Un fragmento horizontal entra si su línea base cae en la banda vertical de `bbox_fila` ∪ `bbox`, con un
       margen de 1,5 pt arriba y 3 pt abajo. Un fragmento vertical (texto girado) entra si cae en la franja
       horizontal del bloque.
     - El literal tiene que estar entero en un fragmento del bloque, o componerse de trozos consecutivos de al
       menos 4 caracteres. Cada trozo debe estar en un fragmento del bloque y, si repite fragmento, quedar más a la
       derecha que el trozo anterior. Así se cubren los bloques de varias líneas y las filas con etiquetas y
       valores intercalados.
  2. **La fila entera que vio el lector (`fila_literal`) está en esa misma posición.**
     - Cuenta la identidad completa de la fila: fecha, número e importes.
     - En una fila horizontal no cuentan las palabras que solo aparecen en texto vertical que la cruza. Por
       ejemplo, el «1º» del texto legal del margen de Alliance, que el lector mete en algunas filas.
- **Falla cerrado:**
  - una página girada, o sin posiciones de `pypdf`, da `FILA_NO_EVALUABLE` (`NO_EVALUABLE`);
  - una evidencia sin caja da `EVIDENCIA_SIN_FILA` (`NO_LITERAL`).
- **Banco Alliance 1.3.2** (94 PDF, 81 con salida): **179 de 179 facturas `LITERALIDAD_OK`**, con 48.835
  literales, 179 derivados por R14, 0 fallos y 0 `NO_EVALUABLE`. Tarda 0,52 s como máximo por documento.
  - **Causas encontradas y corregidas en la 0.2.0** antes de llegar a 0 fallos:
    - **NIF de Alliance en el texto legal vertical:** se ancla por la franja horizontal.
    - **Dirección del destinatario en dos líneas, con la etiqueta a la derecha:** se usa el bloque `bbox` ∪
      `bbox_fila` y la composición por trozos.
    - **Fila de totales con etiquetas y valores en fragmentos distintos:** se permite reutilizar un fragmento en
      orden.
    - **«1º» del texto vertical dentro de 7 filas de albarán:** no cuenta en la fila.
- **Mutaciones:** 38.700 de 38.700 detectadas, igual que en la 0.1.0.
- **Prueba cruzada** (la salida de cada documento contra el PDF del documento siguiente):

  | Resultado | 0.1.0 | 0.2.0 |
  |---|---|---|
  | Valores que pasan | 3.648 (7 %) | **1.270 (2,6 %)** |
  | De ellos, el **mismo dato** en el mismo campo del otro documento | — | 1.186 |
  | Porcentajes de la **cabecera fija** de impuestos de Alliance | — | 84 |
  | **Coincidencias reales de importes o fechas** | ~10 | **0** |

  - **Mismo dato (1.186):** está impreso igual en la misma fila de los dos PDF. Son los tipos de IVA y de RE, el
    nombre, el NIF y el domicilio de Alliance, «FACTURA DUPLICADO», el bloque del destinatario (la misma farmacia)
    y 3 filas de cuota de servicio iguales en los dos meses.
  - **Cabecera fija (84):** la fila «CONCEPTO 4 10 21 4 10 21 0,50 1,40 5,20» sale en toda factura Alliance,
    aunque el otro documento no tenga ese tramo. Que pasen es correcto: el dato está, literal, en esa fila del
    otro PDF.
  - **Ajustes de la 0.2.0 tras el banco HEFAME (2026-11-27):**
    - una tirada de `pypdf` sin posición (matriz identidad: el valor que sigue a su etiqueta en el mismo objeto de
      texto) hereda la posición de la tirada posicionada anterior;
    - una tirada entera cuenta como trozo aunque mida menos de 4 caracteres (la etiqueta «IVA»).

    Tras estos ajustes, el banco Alliance sigue en 179/179 OK, las mutaciones en 38.700/38.700 y la prueba
    cruzada sin cambios.
  - **El 2,6 % que queda está explicado caso por caso.** Para bajarlo a 0 haría falta distinguir dos PDF con el
    mismo texto en la misma fila, y eso ya no es una cuestión de literalidad, sino de identidad del documento (SHA
    e identidad de la factura, que se comprueban aparte).

## 1. Estado confirmado de los documentos

Lectura READ_ONLY de `documentos_facturas` (2026-11-27, `transaction_read_only = on`; `lectura_ro\documentos.json`).

- **PIO, `CONFIRMADO POR LECTURA`:**

  | Estado | Clase | Documentos |
  |---|---|---|
  | `NORMALIZADA` | — | 27 |
  | `PROVEEDOR_NO_SOPORTADO` | `NO_SOPORTADO` | 204 |
  | `REVISION` | `DEFECTO_DOCUMENTO` | 35 |

- **Código de error y lector.**
  - Los 239 documentos tienen `ultimo_error_codigo = DocumentoNoAptoManual`. El código no distingue «sin lector»
    de «lector sin autoridad».
  - La última ejecución lo distingue en `lector.layout`:
    - 46 documentos con layout reconocido sin autoridad: `totalcare-local` 4, `cofares-local` 3,
      `dermofarm-historico-local` 1, `suavinex-historico-local` 1, `ecoceutics-local` 1,
      `hplus-consumo-local` 1, `eports-local` 1 y `hefame-local` 1;
    - 46 con un layout nulo;
    - el resto, sin lector registrado en la ejecución (`INFERIDO`: ejecuciones anteriores a la migración 37).
- **Cruce con el espejo, en local por SHA-256:** 238 de 239 tienen PDF. El que falta es, presumiblemente, el documento 84 de
  la serie 2BJ, que ya faltaba en el espejo (`INFERIDO`).
  - En 7 documentos no hay texto en ninguna página.
  - En 101, la expresión regular no encuentra el CIF del emisor (Cofares, Suavinex, Fedefarma, Kenvue y otros, con
    el CIF en otro formato). Para esos documentos, el proveedor sigue siendo el `INFERIDO` del informe.
- **Confirmados por CIF en el texto:**

  | Proveedor | Documentos | `PROVEEDOR_NO_SOPORTADO` | `REVISION` |
  |---|---|---|---|
  | HEFAME | 16 | 16 | 0 |
  | Ecoceutics | 23 | 19 | 4 |
  | Dermofarm | 12 | 11 | 1 |
  | Pierre Fabre | 9 | 9 | 0 |

### 1.1 HEFAME: 16 documentos, ni 22 ni 13 (`CONFIRMADO POR LECTURA`)

- **El diseño de HEFAME (15/11) contaba 13** en `PROVEEDOR_NO_SOPORTADO`. Eran las 14 facturas del espejo del 10/06
  al 31/10, menos 0563834757, que está `NORMALIZADA`. Los 13 siguen en `PROVEEDOR_NO_SOPORTADO`.
- **Después se importaron 3:**
  - la del 30.09 (H5), importada el 18/11;
  - la de la 2.ª decena de noviembre, el 16/11;
  - la de la 3.ª decena de noviembre, el 24/11. Es la única cuya ejecución registra `layout = hefame-local`.
- **Total: 13 + 3 = 16.** Todas tienen razón social y CIF `F30004444` en el texto y 2 páginas.
- **Los 22 del informe eran una estimación con 6 documentos de más.** Se atribuyeron a HEFAME por la etiqueta del
  fichero, sin el CIF en el texto. No son HEFAME: es justo el error que prohíbe R13 (el nombre del archivo no es
  fuente de ningún dato).
- El informe se corrige así: HEFAME tiene 16 documentos, unos 5.500 € en el periodo (`INFERIDO`), y sigue en el
  puesto 4.

## 2. Verificador de literalidad independiente del lector (`PROPUESTA`)

**Problema** (`CONFIRMADO POR CÓDIGO`):

- El `literal` lo construye el propio adaptador con sus palabras (`motor_local/adaptadores/base.py:121-160`). Nadie
  comprueba que el `valor` salga de ese literal.
- El control `EVIDENCIA_CERO_INVENCIONES` siempre da OK (`normalizador_v2/validadores.py:253`).
- Alliance escribe en el código el nombre y la dirección del proveedor (`adaptadores/alliance.py:470-479`).

**Diseño:**

- **Módulo nuevo** `src/facturas/certificacion/literalidad.py`. No importa nada de `motor_local/adaptadores`: solo
  lee la salida (el `DocumentoNormalizado`) y el PDF.
- **Motor de texto distinto del lector:** el lector usa `pypdfium2`; el verificador usará **`pypdf`**, que ya está
  instalado en el `.venv`, así que no añade dependencias.
- **Cada valor documentado** (`{valor, literal, evidencias}`) se clasifica en uno de cuatro grupos:
  1. **LITERAL.** El literal aparece, con espacios normalizados, en el texto que `pypdf` saca de la página citada.
     Además, el valor se reconstruye del literal con un analizador declarado: importe en formato es-ES (`1.234,56`,
     signo delante o detrás como `30,39-`), fecha (`dd/mm/aa`, `dd.mm.aaaa`), número o CIF. Si el resultado no es
     igual al valor → `NO_LITERAL`.
  2. **DERIVADO.** El valor no aparece en el PDF, pero lo produce una regla con nombre aprobada por Pio a partir de
     entradas que sí son LITERAL. Ejemplos:
     - R14: el importe del vencimiento es el TOTAL FACTURA;
     - H1: el cargo cooperativo de 80,00 sale del desfase de la base S.R.;
     - las sumas.

     El verificador recalcula el valor con la regla y lo compara.
  3. **DECISIÓN DE PIO** (`sentido_fuente: DECISION_FUNCIONAL_PIO`, como H2, H3 o R10). Se admite solo si la regla
     figura en la lista cerrada del verificador.
  4. **CONSTANTE DEL LECTOR**, como el nombre y la dirección de Alliance. Solo se admite si también aparece en el
     texto de la página. Si no aparece → `NO_LITERAL`.
- **Resultado por factura:** `LITERALIDAD_OK`, `LITERALIDAD_FALLO` (con la lista de campos) o `NO_EVALUABLE` (por
  ejemplo, si `pypdf` no saca texto de la página). En la certificación de un lector, `NO_EVALUABLE` cuenta como
  fallo.
- **Uso:**
  1. **En la certificación** de cada lector, sobre su banco (§5): 100 % LITERAL, DERIVADO o DECISIÓN.
  2. **En el worker, antes de persistir:** primero en **sombra**, que registra el resultado en
     `normalizacion_ejecuciones.pasos` sin bloquear. Pasa a bloqueante con una decisión de Pio, después de medir.
- **Medición previa, sin producción:** el banco Alliance 1.3.2 completo (94 documentos) y las 15 facturas HEFAME.
  - El objetivo es 0 `NO_LITERAL` en Alliance.
  - Cada `NO_EVALUABLE` por diferencias entre `pypdfium2` y `pypdf` (orden, ligaduras o espacios) se explica antes
    de activar el modo bloqueante.
  - Se mide también el tiempo de `pypdf` en el documento Alliance más grande (posición 122, 274 líneas), frente a
    los límites de la noche.

## 3. Contrato mínimo obligatorio (`PROPUESTA`)

Comprobador nuevo `src/facturas/certificacion/contrato.py`, independiente del lector, como el verificador de §2. Se
ejecuta después de los validadores actuales y antes de la RPC de persistencia. Cada fallo F0-3 se corrige así.

### 3.1 CIF del emisor en su columna

- **Hoy** (`CONFIRMADO POR CÓDIGO`): el CIF solo queda en `facturas.datos_extraidos.proveedor.nif`.
  `facturas.proveedor_cif` existe (migración 06) pero la RPC de la migración 28 no la rellena (`28:203-210`).
- **Propuesta:**
  - **Migración 42:** la RPC escribe `proveedor_cif` con `proveedor.nif.valor`.
  - **El contrato exige** que el CIF tenga formato de CIF o NIF válido, que aparezca literal (§2) y que esté en el
    **maestro de emisores** de §5.1 asociado a ese lector. Si no → falla cerrado (`CIF_EMISOR_NO_CERTIFICADO`).
  - **Alliance:** `A50004324`, ya exigido por su reconocedor (`alliance.py:326`).

### 3.2 Tipo de documento real

- **Hoy:** Alliance emite `FACTURA_DUPLICADO`, que la RPC no admite y guarda en la columna `tipo_documento` como
  `'OTRO'` (`28:215-220`). El sentido del Cashflow se lee de `datos_extraidos.tipo_documento.valor`, nunca de la
  columna (REGLAS_CRITICAS, decisión del 2026-11-08), así que la columna `'OTRO'` no afecta a pagos ni a Cashflow.
- **Propuesta:**
  - **Contrato:** el tipo es obligatorio y pertenece a `{FACTURA, FACTURA_DUPLICADO, ABONO, FACTURA_RECTIFICATIVA}`.
    El signo del total tiene que ser coherente: `ABONO` → total ≤ 0 o un literal de abono declarado por el lector.
    Un tipo desconocido falla cerrado.
  - **Migración 42:** la RPC guarda `FACTURA_DUPLICADO` como `FACTURA` en la columna. El JSON no cambia, así que la
    regla de Cashflow sigue igual.
  - **Pregunta para Pio:** ¿corrige la 42 la columna de las facturas ya persistidas, a partir de su `datos_extraidos`?
    Solo cambiaría esa columna, con postcheck por fila. Recomendación: **sí**, con aviso a la web, aunque la web no
    debe leer esa columna para el sentido.

### 3.3 Importe real de cada vencimiento

- **Hoy:** en Alliance, R14 copia el TOTAL FACTURA cuando hay una sola fecha, porque Alliance no imprime el importe
  del vencimiento. Con varias fechas el importe queda nulo. El control de la suma es **circular** para R14 y no
  bloquea.
- **Propuesta:**
  - **Contrato:** cada vencimiento lleva su importe con origen **LITERAL** (leído del PDF) o **DERIVADO** con una regla
    con nombre (R14 es la única aprobada).
  - **Prohibido** deducir un importe sin regla. Si el PDF no lo trae y no hay regla, el importe queda nulo, con una
    incidencia, y la factura no certifica los vencimientos.
  - **Suma = total al céntimo, solo con importes LITERAL.** Con R14 el control queda `NO_APLICA (DERIVADO R14)` y
    deja de contar como OK.
  - **Alliance no cambia:** R14 se mantiene tal cual; solo se etiqueta su origen.
  - **HEFAME y los demás lectores** leen el importe de cada plazo, porque está impreso. Por ejemplo, 0563842626 tiene 2.
  - **Migración 42:** `facturas_vencimientos.provenance` guarda el origen (`LITERAL` o `DERIVADO:R14`).

### 3.4 No persistir si el cuadre fiscal falla

- **Hoy:** `CUADRE_TOTAL` y `TRAMO_n_IVA`/`TRAMO_n_RE` con `FALLO` solo dan `VALIDADA_CON_INCIDENCIAS`
  (`validadores.py:156-189`). La RPC guarda esas facturas como `NORMALIZADA` (`28:199-201`) y el fallo solo bloquea
  la conciliación (`FISCALIDAD_INCOHERENTE`).
- **Propuesta:**
  - **Contrato:** con cualquier `FALLO` fiscal no se llama a la RPC. El documento pasa directamente a `REVISION` con
    motivo `CUADRE_FISCAL` (la vía `DEFECTO_DIRECTO_A_REVISION` de la 37; no gasta reintentos, porque un PDF no
    cambia al reintentar).
  - **Defensa en la BD (migración 42):** la RPC rechaza (`CUADRE_FISCAL_FALLIDO`) una factura cuyos `controles`
    traigan `CUADRE_TOTAL` o `TRAMO_*` en `FALLO`.
  - **La tolerancia no cambia:** 0,01 € (`TOLERANCIA_EUR`).
  - **Riesgo para Alliance, que se mide antes:** cuántas facturas Alliance del banco de 94 y de las persistidas tienen
    hoy un `FALLO` fiscal. Objetivo: 0. Si alguna lo tiene, se explica a Pio antes de activar el bloqueo.

### 3.5 Albaranes + movimientos = total

- **Hoy:** no hay cuadre documental.
  - `CUADRE_ALBARANES` sale `NO_APLICA` porque el puente multifactura no pasa el subtotal (`multifactura.py:268`).
  - `FILAS_VS_TOTAL_COMPRAS` de Alliance es `NO_EVALUABLE` (`alliance.py:943`).
  - Solo lo comprueba la conciliación (MIXTA `TOTAL_NO_EXPLICADO`, R11).
- **Propuesta:**
  - **Contrato:** Σ albaranes (`importe_total`, con signo por sentido) + Σ movimientos (con signo) = `TOTAL FACTURA`.
  - **Tolerancia documental de redondeo:** la factura redondea por producto y el lector por fila.
    **Propuesta:** `mín(0,01 × n.º de filas; 0,50)`, con la misma forma que R11.
  - Si la diferencia la supera → `REVISION` con motivo `TOTAL_DOCUMENTAL_NO_EXPLICADO` y la diferencia.
- **Casos Alliance conocidos** (`CONFIRMADO POR LECTURA` en el diagnóstico de 08005254):

  | Factura | Diferencia | Causa | Con la tolerancia propuesta |
  |---|---|---|---|
  | 08009278 | +0,02 | Redondeo | Pasa |
  | 08009279 | +0,02 | Redondeo | Pasa |
  | 08005254 | 1,52 | PACTO COMERCIAL, que está solo en el resumen fiscal | **Fallaría, y debe fallar**: falta un movimiento. Lo corrige la versión 1.3.3 (PACTO COMERCIAL = `CARGO`), ya decidida |

- **Medición previa:** el banco Alliance de 94 documentos, con una tabla de diferencias por factura.
  - **Condición para activar:** solo fallan las facturas con una causa documental explicada (como el PACTO
    COMERCIAL).
  - Si fallara una factura Alliance sin causa → no se activa, y se lleva a Pio.

### 3.6 Implantación sin romper Alliance (`PROPUESTA`)

1. **Código** (contrato y literalidad) y **migración 42**, en local (PostgreSQL 17) con suite completa e histórica.
2. **Banco Alliance 1.3.2 → 1.3.2 + contrato** sobre los 94 documentos.
   - Payload persistido idéntico salvo `proveedor_cif`, la columna `tipo_documento` y el origen de los vencimientos.
   - Lista cerrada de facturas que el contrato rechazaría, cada una explicada.
3. **Despliegue de la 42** con preflight y confirmación de Pio. El nuevo `cf_configuracion.contrato_minimo` empieza
   en `SOMBRA`.
4. **Noches en sombra:** el contrato y la literalidad se registran pero no bloquean. Lo que habrían bloqueado se
   compara con lo esperado.
5. **Paso a `BLOQUEANTE`:** decisión de Pio, con la lista de las noches en sombra.

## 4. Aviso de proveedor sin lector en `para_revisar` (`PROPUESTA`)

- **Hoy** (`CONFIRMADO POR CÓDIGO`):
  - el documento queda en `PROVEEDOR_NO_SOPORTADO` sin gastar intento;
  - la noche solo lo cuenta (`noche_automatica.py:482-488`);
  - `para_revisar` solo recibe los `DEFECTO` (`:489-492`).
- **Propuesta:**
  - **Identificador de emisor** (`src/facturas/certificacion/emisor.py`), independiente de los lectores. Busca CIF
    válidos en el texto de la página 1 y descarta los CIF y NIF de la farmacia (lista cerrada en el código; los datos de
    personas no salen en ningún registro ni informe). Devuelve el CIF del emisor o `null`.
  - **Entrada nueva en `para_revisar`:**
    ```
    {tipo: "PROVEEDOR_SIN_LECTOR", documento_id, cif_emisor, proveedor_maestro,
     layout_reconocido, motivo: "SIN_LECTOR" | "LECTOR_SIN_AUTORIDAD" | "EMISOR_NUEVO" | "SIN_TEXTO"}
    ```
    - `layout_reconocido` sale de `ejecucion.lector.layout`, que ya existe.
    - `EMISOR_NUEVO` = CIF fuera del maestro.
    - `SIN_TEXTO` = PDF sin texto.
  - En `resumen.txt`, una línea propia por cada `EMISOR_NUEVO`.
  - **Sin IA y sin cambio de estado:** el documento sigue en `PROVEEDOR_NO_SOPORTADO` sin gastar intento. La entrada
    solo informa.
  - **Para confirmar en la implementación:** que la fila de `cf_noches_automaticas` admite la entrada nueva sin
    cambios de esquema.
  - Telegram sigue sin implementar (REGLAS_CRITICAS).

## 5. Piezas comunes de la fábrica (`PROPUESTA`)

1. **Maestro de emisores** (`src/facturas/certificacion/maestro_emisores.py`), versionado en el código como la
   autoridad. Asocia cada CIF a su proveedor, su lector, la versión certificada y su estado (`SIN_LECTOR`, `SOMBRA` o
   `CERTIFICADO`). Lo alimentan el inventario y cada certificación. No da autoridad: la autoridad sigue en
   `compositor_automatico.py:40-42` y en la ruta manual.
2. **Ficha por proveedor:** `pruebas/auditoria_<proveedor>/DISENO.md`, con el layout, las señales, las decisiones de
   Pio y los casos raros, como la de HEFAME.
3. **Verdad conocida:** un JSON por factura del banco, con cabecera, impuestos por tipo, vencimientos y número de
   albaranes y de movimientos, citando la página.
   - La escribe un agente distinto del que escribe el lector, o sale del gold y de Farmatic.
   - Pio la valida por muestreo.
   - El agente `adaptador-facturas` no la escribe.
4. **Criterio de certificación**, al 100 % sobre el banco:
   - literalidad (§2);
   - contrato (§3);
   - igualdad con la verdad conocida;
   - simulación de conciliación con cada factura no `CONCILIADA` explicada;
   - determinismo;
   - un caso negativo;
   - revisor PASS.
5. **Versión y autoridad:** como alliance-local 1.3.x. La tupla `(id, versión exacta)` se da por decisión de Pio. Cada
   cambio de versión exige un banco completo de la versión anterior frente a la nueva, y lo ya persistido se corrige
   por R12.

**Esfuerzo estimado del Paso 0** (`INFERIDO`):

| Pieza | Sesiones |
|---|---|
| Literalidad | 1,5–2 |
| Contrato y migración 42 | 1,5–2 |
| Aviso, identificador de emisor y maestro | 1 |
| Banco Alliance y medición | 0,5 |
| **Total** | **4,5–5,5**, más despliegue y noches en sombra |

## 6. HEFAME: las dos decisiones pendientes (para Pio)

Sale de `pruebas/auditoria_hefame/DISENO.md` §2.5 y §4. Con F0-4 (RE «No.» al 5,2 %) quedan estas dos.

### 6.1 Tolerancia del control de la página 2

- **Qué es:** el lector rehace la página 2 (base, IVA y recargo por clase, y el total) a partir de las filas de la
  página 1 y la compara con lo impreso.
- **El problema:** HEFAME calcula la página 2 con las líneas de producto, que no vienen en el PDF. Por eso, al
  rehacerla, a veces sale 1 céntimo distinto. En una factura (0563863435) incluso la base de la página 2 difiere en
  0,01 de los totales de la página 1.
- **Las opciones:**
  - **Exacto:** fallarían 8 de las 14 facturas medidas, aunque estén bien. HEFAME no llegaría nunca a funcionar.
  - **0,01 por componente:** pasan las 14. Cualquier diferencia mayor sigue parando el lector.
- **Recomendación: 0,01 por componente rehecho**, con una condición. Lo que HEFAME imprime y no hay que rehacer se
  exige **exacto**: la suma de los totales impresos por clase = `Total Factura` impreso = suma de los vencimientos
  impresos. Así se tolera el redondeo y no se tolera ningún error de lectura.

### 6.2 Reglas de conciliación (§4 del diseño de HEFAME)

Cómo casar cada fila de la factura con su albarán de Farmatic.

1. **Número sin ceros a la izquierda.** Desde octubre, HEFAME imprime 7 dígitos (`7070398`) y Farmatic guarda 10
   (`0007070398`). Se comparan quitando los ceros, solo si los dos son numéricos.
   **Recomendación: sí.**
2. **Ventana de fechas.**
   - Lo medido: Farmatic registra el albarán el mismo día o hasta 4 días después en 35 de los 36 casados por número.
     El restante estaba a 70 días y era una coincidencia de número falsa.
   - Las opciones: **0 a +4 días** o **±3 días** (como R15b).
   - **Recomendación: 0 a +4.** Encaja con lo medido y no admite fechas de Farmatic anteriores a la factura.
   - Fuera de la ventana no se casa, aunque el número coincida.
3. **Tolerancia por fila: 0,01.**
   - Con ella casan 32 de las 36.
   - Las otras 4 (1,82 frente a 2,02; 0,74/0,77; 126,25/104,54; 97,06/93,68) son diferencias reales: deben ir a
     `DIFERENCIA` para que las revises, no esconderse.
   - Los albaranes internos `Q…`/`R…` y los `91…` (H4) casan por importe (PUC) a ±3 días **solo con un candidato
     único**. Si hay dos filas iguales, como las de 3,91 en 0563801595, no se casa (R15).
   - **Recomendación: sí.**
   - La tolerancia de la conciliación de la factura entera sigue siendo la de R11.

Con F0-4 y estas dos decisiones, el diseño de HEFAME queda cerrado para escribir hefame-local 1.3.0 sobre el Paso 0.

**DECISIÓN DE PIO (2026-11-27, F0-6 y F0-7):** aprobadas §6.1 y §6.2 tal como se recomiendan.
