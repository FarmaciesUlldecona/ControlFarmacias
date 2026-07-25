@echo off

cd /d C:\ControlFarmacias\Programa

if not exist logs mkdir logs

echo ================================================== >> logs\automatizacion_facturas.log
echo INICIO: %date% %time% >> logs\automatizacion_facturas.log

C:\ControlFarmacias\Programa\.venv\Scripts\python.exe -m src.facturas.importar_facturas_drive >> logs\automatizacion_facturas.log 2>&1

set CODIGO_SALIDA=%ERRORLEVEL%

echo CODIGO DE SALIDA: %CODIGO_SALIDA% >> logs\automatizacion_facturas.log
echo FIN: %date% %time% >> logs\automatizacion_facturas.log
echo ================================================== >> logs\automatizacion_facturas.log
echo. >> logs\automatizacion_facturas.log

exit /b %CODIGO_SALIDA%