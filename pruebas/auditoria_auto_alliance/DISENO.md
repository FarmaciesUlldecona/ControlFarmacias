# Hito AUTO-ALLIANCE: normalización y conciliación nocturnas automáticas, solo Alliance (diseño)

**Estado:** diseño con las decisiones de Pio del 2026-11-12 (§7) y plan de hitos aprobado (§8). **AUTO-A implementado
solo en local** (`CONFIRMADO POR TEST`, ver ESTADO_ACTUAL). Sin producción.

**Objetivo:** cada noche, después de la importación de facturas y de la sincronización de albaranes, el sistema
normaliza y concilia **solo** las facturas Alliance nuevas, sin intervención. Pio revisa por la mañana únicamente lo
que no cuadra.

**Punto de partida** (código y ESTADO_ACTUAL a 2026-11-12):

- **Tareas nocturnas.** El Programador de tareas lanza dos:
  - «ControlFarmacias - Importar facturas»: a las 21:00 locales, como `Usuari`, con
    `ejecutar_importacion_facturas.bat`;
  - «Sincronización ControlFarmacias»: a las 21:30, como `ControlFarmaciasRO`, con
    `ejecutar_sincronizacion.bat`.

  Ninguna de las dos alcanza `runtime_supabase` (`CONFIRMADO POR CÓDIGO`, 2AZ-D).
- **Flags apagados:** `normalizacion_automatica=false`, `conciliacion_automatica=false` y `luna_habilitada=false`;
  `farmacias_habilitadas={PIO}`.
- **Los flags ya los aplica la base de datos.** El claim `AUTOMATICO` solo reclama si su flag está en `true`
  (`16_cf_worker_manual_one_shot.sql:41`, `18_cf_conciliacion_manual_atomica.sql:95`). `MANUAL_ONE_SHOT` es lo único
  que se lo salta.
- **`WorkerAutomatico`** (`worker_automatico.py`) ya existe: hace un claim de cada tipo por llamada y no arranca con
  Luna, con farmacias distintas de `{PIO}` ni con tolerancia superior a R11. Ningún proceso lo compone ni lo programa.
- **Autoridad de extracción:**
  - registro global: ningún extractor la tiene;
  - Alliance (`alliance-local`, con puente certificado) solo la tiene en el compositor manual del 2AP;
  - REGLAS_CRITICAS se actualiza con D1 (§7).
- **Cola actual:**
  - documentos: 16 `PENDIENTE`, 12 `ERROR` con intentos restantes, 7 `REVISION` y 135 `PROVEEDOR_NO_SOPORTADO`
    (datos del 5/11);
  - facturas: 2 no elegibles (`0563834757`, HEFAME, y `08012619`).

## 1. Qué se activa y en qué orden

1. **Compositor automático Alliance** (D1). Va en `src/facturas/runtime_supabase/`.
   - **Autoridad:** reutiliza la del compositor manual, solo `alliance-local` y solo en su versión certificada, con
     el puente multifactura certificado. Cualquier otro proveedor, layout o versión no certificada falla cerrado
     (R2).
   - **Qué construye:** un `WorkerAutomatico` con ese worker de normalización y el worker de conciliación con R11.
   - **Disparador:** `AUTOMATICO` (R8).
2. **Orquestador nocturno** (D6). Va en `src/facturas/runtime_supabase/noche_automatica.py`; se lanza con
   `python -m` desde un `.bat` versionado como los actuales.
   - Es el único que llama a `WorkerAutomatico.ejecutar_una()`.
   - Tiene dos modos:
     - `SOMBRA`: solo lectura más la fila de resumen (§8);
     - `REAL`.
3. **Migración 32: tabla de resumen nocturno** (D4, §3). Es lo único que la web lee para el aviso «última noche».
4. **Tarea programada «ControlFarmacias - Automatización Alliance»** (D7). Se lanza a las **22:15 locales**, como una
   tarea separada.
   - **Identidad de Windows: `Usuari`** (decisión de Pio). Es la identidad que ya escribe en Supabase en la tarea de
     importación, con la misma credencial del sistema del `.env`.
   - **Por qué `Usuari`:**
     - la automatización no toca Farmatic;
     - un usuario nuevo duplicaría la clave del sistema en otro perfil.
   - **Separación que se mantiene:** `ControlFarmaciasRO` = Farmatic (solo lectura); `Usuari` = Supabase.
   - **Puerta:** las dos tareas anteriores han terminado esta noche con código 0 y ninguna está en ejecución.
   - **Equipo apagado:** si está apagado esa noche, no se ejecuta. La noche siguiente procesa lo acumulado, dentro
     de los límites del §4.
5. **Flags** en `cf_configuracion`: `normalizacion_automatica=true` y `conciliacion_automatica=true`. Los pone Pio
   en el editor SQL, y solo en la activación (§8). Son el interruptor general.
   - Luna sigue en `false` y las farmacias habilitadas siguen en `{PIO}`.

**Orden de cada noche:**

```text
21:00 Importar facturas (Usuari; Drive -> documentos_facturas)            [sin cambios]
21:30 Sincronización de albaranes (ControlFarmaciasRO; Farmatic, lectura)  [sin cambios]
22:15 Automatización Alliance (Usuari):
      guard de la noche -> puertas -> snapshot pre -> normalización (hasta N)
      -> conciliación (hasta M) -> snapshot post -> postcheck 2AX por fila
      -> informe en fichero + fila en la tabla de resumen nocturno
```

- **La conciliación va después de la sincronización:** sin los albaranes de la noche, una factura nueva saldría
  `DIFERENCIA`.
- **La normalización va antes de la conciliación:** así las facturas Alliance de la noche se concilian en la misma
  ejecución.

## 2. Solo Alliance; el resto, como hoy

- **Normalización.**
  - El proveedor no se conoce antes de extraer, y la regla S5 prohíbe inferirlo por nombre, ruta o carpeta. El
    worker reclama en el orden oficial.
  - Resultados posibles:
    - **Alliance** → normalizado y persistido, igual que en la serie 2BJ.
    - **Otro proveedor** → `PROVEEDOR_NO_SOPORTADO` (R2), sin consumir intentos ni extraer datos. Es el mismo
      estado que dejó la serie en 135 documentos.
    - **Defecto en un Alliance** → `ERROR` con backoff y, al 4.º intento, `REVISION` (R3).
  - Los 12 `ERROR` actuales se resuelven **antes**, con la serie 2BJ (D3). Así la noche solo ve lo nuevo.
    **D3 ajustada (DECISIÓN DE PIO, 2026-11-13):** la serie no resuelve un defecto de extracción, solo le consume
    un intento (R3). Los defectos se agotan con tandas antes de AUTO-ON (el 2026-11-13 y una tanda pequeña cada
    día de la fase de sombra), para que no ocupen los huecos de la noche.
- **Conciliación.**
  - Antes de cada claim, el orquestador simula en READ_ONLY el n.º 1 del orden oficial (R5).
  - Si el n.º 1 no es Alliance, no se reclama y se para la conciliación de esa noche. «Alliance» = el grupo
    Alliance/SAFA/Cencora tal como ya lo identifica la conciliación (R19).
- **Fuera de alcance:**
  - otras farmacias;
  - Luna;
  - el resto de proveedores;
  - Farmatic;
  - la web, salvo leer la tabla de resumen nocturno;
  - el módulo de Trabajadores.

## 3. Paradas, alertas y tabla de resumen nocturno

Dos tipos de resultado:

- **Parada:** corta la noche entera.
- **Para revisar:** se anota, no se toca y la noche continúa.

Nunca se arregla nada ni se reintenta.

| Caso | Tipo | Comportamiento |
|---|---|---|
| Puerta fallida al empezar (§5) | parada | La noche no arranca. |
| Excepción no prevista o fila ajena cambiada | parada | Postcheck igualmente (2BK). |
| **Huérfano** (`NORMALIZANDO` o claim vivo tras una ejecución) | parada | Recuperación solo con `recuperar_huerfanos.py` y confirmación de Pio (2BI). |
| **Defecto** de extracción de un Alliance (R3) | para revisar | Consume intento y va al informe con su motivo; al 4.º, `REVISION`. |
| Proveedor no soportado (R2) | informativo | Va al informe como recuento. |
| **Diferencia:** el n.º 1 simula un resultado distinto de `CONCILIADA` (D2) | para revisar y fin de la conciliación de esa noche | No se reclama. Lo decide Pio, con la regla de las series. Se revisará tras un mes de uso (§8). |
| **Revisión R18 pendiente** que afecta al n.º 1 (número de albarán del PDF o reserva) | para revisar y fin de la conciliación de esa noche | No se reclama. Pio decide la aprobación R18. |
| Resultado real distinto del simulado (estado, diferencia o clave idempotente) | parada | |
| Límite N o M alcanzado, o 60 minutos | fin normal | «Quedan X». |
| Flag apagado durante la noche | fin normal | La BD no entrega más claims `AUTOMATICO`. |

**Migración 32, tabla `cf_noches_automaticas`** (D4). Una fila por noche:

- `fecha` (fecha local, clave primaria);
- `modo` (`SOMBRA` o `REAL`);
- `inicio` y `fin`;
- `resultado` (`NOCHE_OK`, `FIN_LIMITE` o `PARADA`) y `motivo`;
- `commit` y `limites`;
- recuentos:
  - `documentos_reclamados`;
  - `alliance_persistidos` y `facturas_creadas`;
  - `no_soportados` y `defectos`;
  - `conciliadas`;
- `para_revisar` (jsonb: factura o documento, motivo y diferencia simulada);
- `cola_restante` (jsonb);
- `informe_sha256`;
- `created_at`.

Reglas de la tabla:

- Una fila por fecha: el guard de la noche es un `INSERT` con clave única.
- La escribe solo el orquestador, con la credencial del sistema. **AUTORIZACIÓN EXPRESA DE PIO (2026-11-12):** la 32 y
  su rollback nombran el rol del sistema (solo esos dos ficheros) para darle `SELECT`, `INSERT` y `UPDATE` y quitarle
  `DELETE`, `TRUNCATE`, `REFERENCES` y `TRIGGER`. Motivo (ensayo de AUTO-A): con los privilegios por defecto de
  Supabase, el resultado dependía de quién crea la tabla y el rol del sistema conservaba `DELETE` y `TRUNCATE`.
- **Lectura:**
  - `cf_lectura`: `SELECT` y política RLS de lectura;
  - `anon` y `authenticated`: sin privilegios (se revocan los que Supabase da por defecto);
  - `cf_trabajadores_web`: nada.
- **Sin datos de facturas fuera de PIO:** se cumple porque solo existen facturas de PIO.
- Sigue el patrón 2AX: desplegar_32, precondiciones y postcondiciones, ensayo con la imitación del `postgres` de
  Supabase, y postcheck.

**Cómo se entera Pio** (Telegram está **NO IMPLEMENTADO**):

1. **La web** (con `cf_lectura`) muestra:
   - «última noche: OK, FIN_LIMITE o PARADA, y el motivo», desde la tabla de resumen nocturno;
   - lo que no cuadra, desde las tablas actuales: facturas `PENDIENTE_CONCILIAR` en `para_revisar` o en
     `REVISION_CONCILIACION`, documentos en `ERROR` o `REVISION`, y revisiones R18 pendientes.
2. **Informe de la mañana** en `C:\ControlFarmacias\noches_auto\<fecha>\`: `informe.json`, un resumen de texto,
   snapshots y `SHA256SUMS`. Además, revisión READ_ONLY con Claude, como la noche de las series.

## 4. Límites por noche y vuelta atrás

- **Límites** (D5):
  - la primera noche `REAL`, 5 documentos y 5 conciliaciones;
  - después, 20 y 20, siempre que haya 3 noches `REAL` previas con resultado `NOCHE_OK` o `FIN_LIMITE`. Lo decide el
    propio orquestador leyendo la tabla de resumen nocturno, como `_tandas_previas_ok` en las series. Una noche
    `PARADA` vuelve a 5 y 5 hasta encadenar otras 3;
  - máximo 60 minutos por noche;
  - una sola ejecución por noche (guard con la fila de la tabla);
  - ninguna serie manual mientras los flags estén encendidos (puerta de las series).
- **Apagar:**
  1. Pio pone los flags en `false` en el editor SQL. El efecto es inmediato: la BD no entrega más claims
     `AUTOMATICO`.
  2. Opcionalmente, deshabilitar la tarea.
  3. Los dos flags son independientes. Con la conciliación automática apagada, se concilia a mano con la serie 2BP
     (`MANUAL_ONE_SHOT`).
- **Lo hecho no se deshace solo.** Queda con su historial, su clave idempotente y su postcheck, como en las series.
  Corregirlo es una decisión de Pio con el reprocesado o el reintento existentes.

## 5. Qué se reutiliza y qué falta

**Se reutiliza:**

- **Puertas:**
  - operación y configuración (`_puertas_operacion`);
  - tareas, adaptada: las dos de esta noche terminadas con código 0 y ninguna en ejecución;
  - migraciones 25, 27, 30, 31 y 32;
  - 0 NORMALIZANDO y 0 huérfanos;
  - git: árbol limpio y HEAD = `origin/main`, o por delante solo con documentación.
- **Snapshot por fila y postcheck 2AX por fila** de las series.
- **Simulación READ_ONLY de conciliación** en cadena (`_simular`, R15), con resultado real igual al simulado.
- **Scripts y módulos:** `conflictos_r18`, `noche_readonly` y `clasificacion_fallos`.
- **Protecciones de `WorkerAutomatico`:** sin Luna, solo PIO y R11.

**Falta:**

1. Compositor automático Alliance, solo con la versión certificada.
2. Orquestador nocturno con los modos `SOMBRA` y `REAL`, los límites y la tabla de resumen nocturno.
3. Migración 32 con su rollback y `desplegar_32.py`.
4. Puertas adaptadas a la noche. La normalización no tiene plan previo: se sustituye por la comprobación posterior
   de facturas, totales y filas cambiadas.
5. `.bat` versionado (`ejecutar_automatizacion_alliance.bat`, escrito sin mirar el de importación, decisión de Pio).
   La tarea la crea Pio, como `Usuari`. **`PENDIENTE` de AUTO-S:** Pio lo compara con el `.bat` de importación antes de
   crear la tarea.
6. Vista «última noche» en la web, fuera de este repositorio.
7. Documentación: REGLAS_CRITICAS (D1 ya anotada; paradas y límites al implementar), ESTADO_ACTUAL y el
   procedimiento de apagado.
8. `PENDIENTE` de baja prioridad: comprobar, desde una sesión de `ControlFarmaciasRO`, qué credencial de base de
   datos usa la sincronización.

## 6. Riesgos y cómo se prueban antes de activar

| Riesgo | Mitigación | Prueba antes de activar |
|---|---|---|
| R1 Extracción con autoridad de un proveedor no Alliance o de una versión no certificada | Autoridad solo para `alliance-local` certificado; el resto falla cerrado | Tests con PDF reales de otros proveedores y con una versión de adaptador no certificada → `PROVEEDOR_NO_SOPORTADO` o fallo cerrado, 0 facturas |
| R2 Factura Alliance omitida entera en un PDF multifactura (límite 2AQ aceptado) | Nada se inventa | El informe lista facturas por PDF |
| R3 Conciliación mal casada | Simulación `CONCILIADA` antes de reclamar; real = simulado; postcheck por fila | PostgreSQL 17 local: diferencia, R17 y reserva cruzada |
| R4 R18 pendiente | Puerta R18 por factura | Test con una revisión pendiente sobre el n.º 1 |
| R5 Huérfano o caída a mitad de la noche | Puerta de huérfanos; `worker_id` único; recuperación solo manual | Test que mata el proceso a mitad del claim |
| R6 Coincide con una serie o sincronización manual | Guard de la noche; puertas de claims y locks; series solo con los flags apagados | Test de dos ejecuciones simultáneas |
| R7 Código no certificado | Puerta git | Árbol sucio o HEAD distinto → parada |
| R8 Cambio de hora o tareas retrasadas | La puerta exige las tareas de esta noche terminadas | Test con tareas sin ejecutar o en ejecución |
| R9 Flag apagado durante la noche | La BD no entrega claims | Test en PostgreSQL 17 local |
| R10 La fila de resumen nocturno no se puede escribir | El informe en fichero existe siempre; la noche siguiente para si falta la fila anterior de una noche iniciada | Test con la tabla sin privilegio de escritura |

## 7. Decisiones de Pio (2026-11-12)

| # | Decisión |
|---|---|
| D1 | **Sí:** autoridad Alliance en la ruta automática, solo Alliance y solo su versión certificada. Regla actualizada en REGLAS_CRITICAS («Extractores locales»). |
| D2 | El n.º 1 que simula `DIFERENCIA` para la conciliación de esa noche (regla de las series). **Revisar tras un mes de uso.** |
| D3 | Resolver antes los 12 `ERROR` con la serie 2BJ. **Ajustada (2026-11-13):** los defectos se agotan con tandas antes de AUTO-ON (ese día y una pequeña cada día de la fase de sombra). |
| D4 | **Sí:** tabla de resumen nocturno (migración 32), con lectura para `cf_lectura`. |
| D5 | 5 + 5 la primera noche, después 20 + 20, máximo 60 minutos. |
| D6 | El orquestador vive en `src/`. |
| D7 | Tarea separada a las 22:15, con la puerta de las dos anteriores, con la identidad `Usuari` (motivos en el §1, punto 4). |

## 8. Plan de hitos

Cada hito tiene su propia confirmación de Pio. Producción solo con preflight, alcance explícito y confirmación.

| Hito | Qué | Dónde | Cierre |
|---|---|---|---|
| **AUTO-A** (local) | Compositor automático Alliance; orquestador en `src/` (modos `SOMBRA`/`REAL`, límites, puertas, paradas, informe); migración 32, rollback y `desplegar_32.py`; `.bat`; tests en PostgreSQL 17 local (casos de §3 y §6, ensayo de despliegue y rollback de la 32 con la imitación del `postgres` de Supabase); REGLAS_CRITICAS y ESTADO_ACTUAL | local | suite completa (aviso previo por Docker), revisor PASS, commit; push de Pio |
| **AUTO-COLA** (producción, con las series) | Serie 2BJ para los 12 `ERROR` y los `PENDIENTE` (D3); serie 2BP para las facturas que salgan | producción, tandas confirmadas | cola sin `PENDIENTE` ni `ERROR` reclamables; la noche solo verá lo nuevo. Puede ir en paralelo a AUTO-A. Los defectos que queden en `ERROR` se agotan con una tanda pequeña cada día de AUTO-S (D3 ajustada) |
| **AUTO-32-D** (despliegue) | Puerta, noche, precondiciones y captura pre; `desplegar_32.py`, una vez; captura post, postcheck 2AX y comprobación de lectura con `cf_lectura` | producción | 32 `APLICADA`; la web puede leer la tabla |
| **AUTO-S** (modo sombra) | Pio crea la tarea de las 22:15 como `Usuari` con el `.bat` en modo `SOMBRA`; flags apagados. Cada noche: puertas, la fila `SOMBRA` (única escritura) y lo que *haría* (documentos y conciliaciones simuladas). Revisión READ_ONLY cada mañana | producción | 3 a 5 noches `SOMBRA` coherentes con lo que hacen después las series; OK de Pio |
| **AUTO-ON** (activación) | Pio cambia el `.bat` a `REAL` (commit) y enciende los dos flags. Primera noche 5 + 5; revisión de la mañana (informe, postcheck y noche READ_ONLY); 20 + 20 automático tras 3 noches buenas | producción | primera noche `NOCHE_OK` o `FIN_LIMITE` |
| **AUTO-R** (revisión) | Un mes después de AUTO-ON: revisar D2 (parada por diferencia) y los límites con los datos de la tabla de resumen nocturno | decisión de Pio | decisión registrada en REGLAS_CRITICAS |

**DECISIÓN DE PIO (2026-11-12):** en el modo `SOMBRA` el orquestador **sí** escribe su fila en la tabla de resumen
nocturno, que es su **única escritura**. Plan de hitos aprobado por Pio el 2026-11-12.

## 9. `PENDIENTE` para el próximo commit con código (observaciones del revisor en AUTO-A)

Textos desfasados, sin regla incumplida (decisión de Pio, 2026-11-13: corregirlos en el próximo commit que toque
código, con su suite completa):

1. REGLAS_CRITICAS, regla del 2AP: «ningún scheduler ni la ruta automática lo referencian» ya está matizada por D1;
   ajustar la frase.
2. Docstring de `tests/facturas/runtime_supabase/test_integracion_pg17_32_auto_alliance.py`: habla de «privilegios por
   defecto»; la 32 concede los privilegios explícitamente (opción A).
3. Comentario de `src/facturas/runtime_supabase/noche_automatica.py` que cita «(R10)» por el riesgo del diseño; se
   confunde con la regla R10 de REGLAS_CRITICAS.

Mejora aprobada por Pio (2026-11-13, tras AUTO-32-D), en el mismo commit: en los postchecks, las tablas de Trabajadores
se informan aparte y no hacen fallar el veredicto.

Decisión de Pio (2026-11-13, tras crear la tarea de sombra), en el mismo commit: `ejecutar_automatizacion_alliance.bat`
guarda registro con el mismo patrón que el `.bat` de importación de facturas, en `logs\automatizacion_alliance.log`,
con la ruta completa de Python.

**HECHO (commit ENCARGO, 2026-11-14):** los tres textos, la mejora de los postchecks (noche: Trabajadores leído en su
propia sesión READ_ONLY e informado en `postcheck.trabajadores`; series 2BJ y 2BP: fuera del criterio 2AX e
informado en `postcheck.trabajadores`) y el registro del `.bat`.
