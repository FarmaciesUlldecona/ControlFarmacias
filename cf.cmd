@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
"C:\ControlFarmacias\Programa\.venv\Scripts\python.exe" "C:\ControlFarmacias\ControlFarmacias_Orquestador_V0_2_dev\cli_operativo.py" %*
