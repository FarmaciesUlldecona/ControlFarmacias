# Tarea «Sincronización ControlFarmacias» — copias del repositorio (Hito 2BF, 2026-10-28)

| Fichero | Contenido | Certeza |
|---|---|---|
| `Sincronizacion_ControlFarmacias_antes_v2.xml` | Copia byte a byte de la exportación real previa a activar la V2 (`C:\ControlFarmacias\evidencias_2bd_ro\tarea_sincronizacion_antes.xml`, 2026-10-28 17:33). SHA-256 `3a880abeecbcff5ea521d37efc6c8b58429423acf39778b1c2a8749d2343713e`. | `CONFIRMADO POR CERTIFICACIÓN ARCHIVADA` |
| `Sincronizacion_ControlFarmacias.xml` | **Vigente**: la exportación anterior con la acción que Pio dejó configurada al activar la V2. Solo cambia `Actions/Exec` (`Command` + `Arguments`). | Acción declarada por Pio el 2026-10-28; **no es una exportación nueva**. `PENDIENTE`: sustituirla por una exportación real en la próxima consulta autorizada de Task Scheduler. |

Acción vigente:

```text
cmd.exe /c "set CONTROLFARMACIAS_ALBARANES_V2=1&& C:\ControlFarmacias\Programa\ejecutar_sincronizacion.bat"
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

Comprobado por `tests/test_tarea_nocturna_v2_2bf.py`.
