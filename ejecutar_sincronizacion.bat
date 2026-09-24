@echo off

cd /d C:\ControlFarmacias\Programa

if not exist logs mkdir logs

echo ================================================== >> logs\automatizacion_albaranes.log
echo INICIO: %date% %time% >> logs\automatizacion_albaranes.log

C:\ControlFarmacias\Programa\.venv\Scripts\python.exe -m src.sincronizar_albaranes >> logs\automatizacion_albaranes.log 2>&1

set CODIGO_SALIDA=%ERRORLEVEL%

echo CODIGO DE SALIDA: %CODIGO_SALIDA% >> logs\automatizacion_albaranes.log
echo FIN: %date% %time% >> logs\automatizacion_albaranes.log
echo ================================================== >> logs\automatizacion_albaranes.log
echo. >> logs\automatizacion_albaranes.log

exit /b %CODIGO_SALIDA%
