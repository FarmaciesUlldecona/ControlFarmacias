# Inventario original — Hito 2AE

Capturado antes de modificar las tareas.

## ControlFarmacias - Importar facturas

- Estado: `Ready`; habilitada: `true`.
- Principal: `MOSTRADOR\Usuari` (`S-1-5-21-1664616495-3062778491-3524446278-1001`).
- LogonType: `Password`; RunLevel: `Limited`.
- Acción: `C:\ControlFarmacias\Programa\ejecutar_importacion_facturas.bat`.
- Argumentos: ninguno.
- StartIn: `C:\ControlFarmacias\Programa`.
- Trigger: diario a las 22:00, desde 25/07/2026.
- MultipleInstances: `IgnoreNew`; StartWhenAvailable: `true`.
- Reintentos: 3, intervalo 10 minutos; timeout: `PT0S`.
- Última ejecución: 17/09/2026 22:00; LastTaskResult: `1`.

## Sincronización ControlFarmacias

- Estado: `Ready`; habilitada: `true`.
- Principal: `MOSTRADOR\Usuari` (`S-1-5-21-1664616495-3062778491-3524446278-1001`).
- LogonType: `Password`; RunLevel: `HighestAvailable`.
- Acción: `C:\ControlFarmacias\Programa\.venv\Scripts\python.exe`.
- Argumentos: `-m src.sincronizar_albaranes`.
- StartIn: `C:\ControlFarmacias\Programa`.
- Trigger: diario a las 21:30, desde 19/07/2026.
- MultipleInstances: `IgnoreNew`; StartWhenAvailable: `true`.
- Reintentos: 3, intervalo 5 minutos; timeout efectivo: `PT72H`.
- Última ejecución: 17/09/2026 21:30:30; LastTaskResult: `1`.
