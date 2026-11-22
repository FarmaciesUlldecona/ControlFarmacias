@echo off
rem Hito 38-B: tarea "ControlFarmacias - Importar Cashflow", 23:45 locales (C2), identidad Usuari.
rem Importacion nocturna del Excel de cashflow (origen NOCHE, modo REAL): la unica escritura es la RPC de la
rem migracion 38. No acepta categorias nuevas (C5): eso solo lo hace Pio con la importacion manual.
rem Volver atras: Pio deshabilita la tarea. La tarea la crea Pio, con su confirmacion.
rem Registro: mismo patron que el .bat de la automatizacion Alliance, en logs\importacion_cashflow.log, con la ruta
rem completa de Python.

cd /d C:\ControlFarmacias\Programa

if not exist logs mkdir logs

echo ================================================== >> logs\importacion_cashflow.log
echo INICIO: %date% %time% >> logs\importacion_cashflow.log

C:\ControlFarmacias\Programa\.venv\Scripts\python.exe -m src.cashflow.importar_cashflow NOCHE REAL >> logs\importacion_cashflow.log 2>&1

set CODIGO_SALIDA=%ERRORLEVEL%

echo CODIGO DE SALIDA: %CODIGO_SALIDA% >> logs\importacion_cashflow.log
echo FIN: %date% %time% >> logs\importacion_cashflow.log
echo ================================================== >> logs\importacion_cashflow.log
echo. >> logs\importacion_cashflow.log

exit /b %CODIGO_SALIDA%
