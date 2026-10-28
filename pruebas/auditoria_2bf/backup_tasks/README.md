# Tarea «Sincronización ControlFarmacias» — copias del repositorio (Hito 2BF, 2026-10-28)

Las dos copias son exportaciones reales, copiadas byte a byte de `C:\ControlFarmacias\evidencias_2bd_ro\`
(`CONFIRMADO POR CERTIFICACIÓN ARCHIVADA`, 2026-10-28):

| Fichero | Origen | SHA-256 |
|---|---|---|
| `Sincronizacion_ControlFarmacias_antes_v2.xml` | `tarea_sincronizacion_antes.xml` (17:33, antes de activar la V2) | `3a880abeecbcff5ea521d37efc6c8b58429423acf39778b1c2a8749d2343713e` |
| `Sincronizacion_ControlFarmacias.xml` | `tarea_sincronizacion_v2.xml` (20:05, **vigente**, V2 activada por Pio) | `b3e327db53fba6753c43f9433e5c4fd9ad3bc6674a244ed857fdc547c9010a31` |

Acción vigente (`Actions/Exec`; es lo único que cambia entre las dos exportaciones):

```text
Command:   C:\Windows\System32\cmd.exe
Arguments: /c "set CONTROLFARMACIAS_ALBARANES_V2=1&&C:\ControlFarmacias\Programa\ejecutar_sincronizacion.bat"
```

- Sin espacio antes de `&&`: `cmd` deja la variable exactamente en `1`, que es lo que exige
  `src/supabase_client/resincronizacion_albaranes.py` (`activada()`). Con `=1 &&` valdría `"1 "` y la V2
  quedaría apagada sin aviso.
- El resto no cambia: principal SID `…-1009` (`MOSTRADOR\ControlFarmaciasRO`), `LogonType=Password`,
  `RunLevel=LeastPrivilege`, diaria a las 21:30, `StartWhenAvailable`, 3 reintentos cada 5 min, límite 72 h,
  `WorkingDirectory=C:\ControlFarmacias\Programa`.
- Ambos ficheros son UTF-16 LE con BOM, como los exporta Windows (Git los trata como binarios: sin
  conversión de fin de línea).
- Para volver a la V2 apagada basta la acción de `…_antes_v2.xml` (solo con confirmación de Pio).

`pruebas/auditoria_2ae/backup_tasks/` es el inventario **original** del 2AE (principal `Usuari`, acción
`python.exe -m src…`) y la base de `rollback_tasks.ps1`: no se modifica. Los scripts elevados de 2AH/2AI
localizan la tarea por `Command = …\ejecutar_sincronizacion.bat`; con la acción vigente no la encuentran y
fallan cerrado. Son históricos.

Comprobado por `tests/test_tarea_nocturna_v2_2bf.py` (SHA, acción y que solo cambia la acción).
