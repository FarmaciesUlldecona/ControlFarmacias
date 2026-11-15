@echo off
rem Hito AUTO-ALLIANCE: tarea "ControlFarmacias - Automatizacion Alliance", 22:15 locales, identidad Usuari.
rem Modo: SOMBRA hasta AUTO-ON (decision de Pio); en AUTO-ON se cambia a REAL con un commit.
rem Registro (decision de Pio, 2026-11-13): mismo patron que el .bat de importacion de facturas, en
rem logs\automatizacion_alliance.log, con la ruta completa de Python.

cd /d C:\ControlFarmacias\Programa

if not exist logs mkdir logs

echo ================================================== >> logs\automatizacion_alliance.log
echo INICIO: %date% %time% >> logs\automatizacion_alliance.log

C:\ControlFarmacias\Programa\.venv\Scripts\python.exe -m src.facturas.runtime_supabase.noche_automatica SOMBRA C:\ControlFarmacias\noches_auto >> logs\automatizacion_alliance.log 2>&1

set CODIGO_SALIDA=%ERRORLEVEL%

echo CODIGO DE SALIDA: %CODIGO_SALIDA% >> logs\automatizacion_alliance.log
echo FIN: %date% %time% >> logs\automatizacion_alliance.log
echo ================================================== >> logs\automatizacion_alliance.log
echo. >> logs\automatizacion_alliance.log

exit /b %CODIGO_SALIDA%
