# Hito 2BF-D — comandos exactos (producción; cada paso con confirmación de Pio)

Preparado el 2026-10-28. **Ejecutado en producción el 2026-10-29** (pasos 0–8 y 10; el paso 9 se adelantó con
una ejecución manual de la tarea de sincronización): ver `docs/contexto/ESTADO_ACTUAL.md`. Diseño y reglas en
`pruebas/auditoria_2bf/DISENO.md`. **Las escrituras (pasos 2, 5 y 7) las ejecuta Pio en terminal.**

## Convenciones

- Todos los comandos en PowerShell, desde `C:\ControlFarmacias\Programa`, con
  `.venv\Scripts\python.exe -B`.
- Evidencias (fuera del repositorio; las herramientas se niegan a escribir dentro):
  `C:\ControlFarmacias\evidencias_2bf_d\` (en adelante `$E`):
  `$E = "C:\ControlFarmacias\evidencias_2bf_d"`.
- **Usuari** = sesión Windows `MOSTRADOR\Usuari`. No toca Farmatic. Pasos 0–3 y 8 (capturas), 5 y 10.
  Los pasos 1–3 y 8 (capturas) necesitan `CONTROLFARMACIAS_SUPABASE_DB_URL` en la sesión (conexión directa,
  propietario `postgres`; como en el 2BD-D, los scripts la leen por dentro sin mostrarla). El paso 5 usa el
  `service_role` del `.env`.
- **RO** = sesión `MOSTRADOR\ControlFarmaciasRO` (Farmatic certificado READ_ONLY; el hook de Claude Code lo
  exige para Farmatic), con el `service_role` del `.env`. Pasos 4, 6, 7 y 8 (`informe`).
- `registrar` (paso 5) **no lee ni importa Farmatic** (test `test_registrar_no_carga_farmatic`), así que va
  con Usuari y `registrado_por` queda como `Usuari`: es quien registra.
- Las capturas consultan las tareas solo con `Get-ScheduledTaskInfo`. La captura `pre` para si una tarea
  está en ejecución o a menos de 60 min: no empezar entre las 20:30 y las 22:30 (sincronización 21:30,
  importación 22:00). Hacer los pasos 1–8 en la misma franja, sin una noche por medio.
- Cualquier salida distinta de la esperada → **PARAR** y avisar a Pio. Ningún paso se reintenta sin su
  confirmación; ningún rollback sin su confirmación.

## Datos fijos

- Commit de la 23: `a457093173fa0b21dda9b97de09ea502a6dc526b`.
- SHA-256 (LF) de `sql/migrations/23_cf_aprobaciones_albaranes.sql`:
  `fce9837958719df5d91755ca080ecb8c58a6fb18f1051afacc1de49b30821f4e`.
- Aprobación: `pruebas/auditoria_2bf/aprobacion_279410.json` (52 → `0002`, 08C16912 → 08C16912A).

## Paso 0 — puerta (Usuari, Claude; sin conexión a producción)

```powershell
git status --short
git log -n 1 --format=%H -- sql/migrations/23_cf_aprobaciones_albaranes.sql
.venv\Scripts\python.exe -B -c "import hashlib;print(hashlib.sha256(open('sql/migrations/23_cf_aprobaciones_albaranes.sql','rb').read().replace(b'\r\n',b'\n')).hexdigest())"
.venv\Scripts\python.exe -B pruebas\auditoria_2bf_d\preflight_readonly.py local 22 $E\local_22.json
.venv\Scripts\python.exe -B pruebas\auditoria_2bf_d\preflight_readonly.py local 23 $E\local_23.json
.venv\Scripts\python.exe -B pruebas\auditoria_2bf_d\preflight_readonly.py alcance $E\local_22.json $E\local_23.json $E\alcance.json
```

Debe salir: árbol limpio; el commit y el SHA de «Datos fijos»; `local` usa Docker local (PostgreSQL 17 sin
red); `alcance` con código 0, `eliminados: []` y en `nuevos` las tablas `albaranes_aprobaciones` y
`albaranes_aprobaciones_aplicadas`, su secuencia y las funciones nuevas; `cf_resincronizar_albaran`
cambiada; ni `tabla:albaranes` ni `tabla:albaranes_cambios`. Además, la suite completa en verde.

## Paso 1 — preflight READ_ONLY (Usuari, Claude con autorización de Pio)

```powershell
.venv\Scripts\python.exe -B pruebas\auditoria_2bf_d\preflight_readonly.py precondiciones $E\precondiciones.json
.venv\Scripts\python.exe -B pruebas\auditoria_2bf_d\preflight_readonly.py captura pre $E\pre.json
.venv\Scripts\python.exe -B pruebas\auditoria_2bf_d\preflight_readonly.py comparar_pre $E\pre.json $E\local_22.json $E\alcance.json $E\comparar_pre.json
```

Debe salir:
- `precondiciones`: `PRECONDICIONES_OK`, 9 × `true`, `transaction_read_only: on`.
- `captura pre`: `CAPTURA_OK`, sin `fallos`. Marcas `22_*` a `true` y `23_*` a `false`; `flags`
  `[false, false, false, "{PIO}"]`. `revisiones_objetivo` = las dos `REVISION` de 279410
  (`08C16912 → 08C16912A` y `52 → 0002 `); reservas = líneas vigentes.
- `comparar_pre`: `ESQUEMA_22_CONFIRMADO`.

## Paso 2 — despliegue de la 23 (Usuari, **Pio**)

```powershell
.venv\Scripts\python.exe -B pruebas\auditoria_2bf\desplegar_23.py a457093173fa0b21dda9b97de09ea502a6dc526b fce9837958719df5d91755ca080ecb8c58a6fb18f1051afacc1de49b30821f4e $E\despliegue_23.json
```

Debe salir: `"resultado": "APLICADA"`, `precondiciones` 9 × `true` y `postcondiciones`
`{albaranes_aprobaciones: 0, albaranes_aprobaciones_aplicadas: 0, historial_sin_cambios: true, rpcs: true,
resync_solo_pendientes: true, privilegios: true}`. Si sale `REVERTIDA`, no se ha cambiado nada: **PARAR**.

## Paso 3 — postcheck criterio 2AX (Usuari, Claude)

```powershell
.venv\Scripts\python.exe -B pruebas\auditoria_2bf_d\preflight_readonly.py captura post $E\post.json
.venv\Scripts\python.exe -B pruebas\auditoria_2bf_d\preflight_readonly.py comparar_despliegue $E\pre.json $E\post.json $E\local_23.json $E\alcance.json $E\despliegue_postcheck.json
```

Debe salir: `captura post` con `CAPTURA_OK`, marcas `23_*` a `true` y aprobaciones y aplicaciones a 0.
`comparar_despliegue` con `POSTCHECK_OK`:
- `objetos_cambiados` = el alcance;
- c1, c2 y c3 a `true`;
- huellas por fila idénticas en todas las tablas (también `albaranes_cambios`), con reservas, operación y
  configuración idénticas.

## Paso 4 — informe de 279410 (RO) y base del paso 8 (Usuari)

```powershell
# RO (Pio, o Claude en VS Code abierto como ControlFarmaciasRO)
.venv\Scripts\python.exe -B pruebas\auditoria_2bf\aplicar_aprobacion.py informe 279410 $E\informe_279410_0.json
# Usuari (Claude): captura justo antes de registrar
.venv\Scripts\python.exe -B pruebas\auditoria_2bf_d\preflight_readonly.py captura post $E\antes_aprobacion.json
```

Debe salir:
- `informe` con `INFORME_SIN_ESCRITURA`, `reservado_por_factura: null` y `aprobaciones: []`;
- en `pendientes` y en `detectado_ahora`, `numero_albaran 08C16912 → 08C16912A` e
  `id_proveedor 52 → "0002 "`;
- captura con `CAPTURA_OK`.

## Paso 5 — registrar la aprobación (Usuari, **Pio**)

```powershell
.venv\Scripts\python.exe -B pruebas\auditoria_2bf\aplicar_aprobacion.py registrar pruebas\auditoria_2bf\aprobacion_279410.json $E\registrar_279410.json
```

Debe salir: `{"accion": "REGISTRADA", "aprobacion_id": <N>, ...}`. **Anotar `<N>`.** `YA_REGISTRADA` con un
id indica que ya estaba registrada (idempotente): usar ese id. Solo escribe una fila en
`albaranes_aprobaciones`; no toca `albaranes`.

## Paso 6 — previsión (RO)

```powershell
.venv\Scripts\python.exe -B pruebas\auditoria_2bf\aplicar_aprobacion.py informe 279410 $E\informe_279410_1.json
```

Debe salir: la aprobación `<N>` con `"prevision": "APLICABLE"`. Cualquier otra → **PARAR** (no aplicar).

## Paso 7 — aplicar (RO, **Pio**)

```powershell
.venv\Scripts\python.exe -B pruebas\auditoria_2bf\aplicar_aprobacion.py aplicar <N> $E\aplicar_<N>.json
```

Debe salir: `"resultado": "APLICADA"`, con código 0 y `revisiones_resueltas` = los dos ids del paso 1. Crea
`$E\aplicar_aprobacion_<N>.guard`, que no se borra. `NO_APLICADA` (código 3) no escribe nada y el albarán
sigue en revisión: **PARAR**, sin reintentar.

## Paso 8 — comprobación de la aplicación

```powershell
# RO
.venv\Scripts\python.exe -B pruebas\auditoria_2bf\aplicar_aprobacion.py informe 279410 $E\informe_279410_2.json
# Usuari (Claude)
.venv\Scripts\python.exe -B pruebas\auditoria_2bf_d\preflight_readonly.py captura post_aplicar $E\post_aplicar.json
.venv\Scripts\python.exe -B pruebas\auditoria_2bf_d\preflight_readonly.py comparar_aplicacion $E\antes_aprobacion.json $E\post_aplicar.json $E\aplicacion_postcheck.json
```

Debe salir:
- `informe`: aprobación `<N>` con `YA_APLICADA` y `pendientes: []`.
- `comparar_aplicacion`: `APLICACION_OK`.
  - 279410 cambia solo `numero_albaran` (08C16912A), `id_proveedor` (`0002 `) y `fecha_actualizacion`;
    `proveedor` sigue CINFA.
  - Aparecen una aprobación (la del JSON) y una aplicación, que resuelve las dos revisiones.
  - Todo lo demás queda idéntico: el resto de albaranes, el historial, las reservas, el esquema y la
    operación.

## Paso 9 — primera noche con la 23 (tarea programada, principal RO; automático)

A la mañana siguiente:
- `logs\automatizacion_albaranes.log` con `CODIGO DE SALIDA: 0` y sin `Albarán en revisión | IdContador:
  279410`.
- `Get-ScheduledTaskInfo` (solo lectura): `LastTaskResult = 0`.
- `informe 279410` (RO) con dos filas `ACTUALIZADO` nuevas: `proveedor CINFA → 1.- SAFA` e
  `id_recepcion null → 50781`. Sin revisiones nuevas.

## Paso 10 — simulación de 08007972 (Usuari, Claude; sin claim ni escritura)

```powershell
.venv\Scripts\python.exe -B pruebas\auditoria_2bd_d\conciliacion_2at.py auditoria candidato $E\candidato_08007972.json
```

Debe salir: candidato n.º 1 = 08007972, con 08C16912 casando con 279410 (`08C16912A`, letra final; proveedor
SAFA). El resultado previsto es `CONCILIADA` (explicado ≈ 464,75 de 464,76; `INFERIDO` de la simulación del
2BD-D: 41,89 + 422,86). La conciliación real **no** forma parte del 2BF-D: requiere otra confirmación de Pio.

## Rollback (solo con confirmación de Pio; Usuari)

`sql/migrations/23_cf_aprobaciones_albaranes.rollback.sql` devuelve el esquema 22 exacto. Se pierden las
aprobaciones y las aplicaciones; los valores ya aplicados en `albaranes` se conservan.
