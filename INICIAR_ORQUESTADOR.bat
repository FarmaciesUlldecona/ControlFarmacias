@echo off
setlocal
cd /d "%~dp0"
echo.
echo CONTROLFARMACIAS - ORQUESTADOR V0
echo =================================
echo.
python orquestador.py --check
echo.
if errorlevel 1 (
  echo La comprobacion ha fallado.
  pause
  exit /b 1
)
echo.
echo Para la primera prueba segura ejecuta:
echo python orquestador.py --task tareas\00_prueba_segura.json
echo.
pause
