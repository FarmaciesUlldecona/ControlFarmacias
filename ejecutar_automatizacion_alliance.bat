@echo off
rem Hito AUTO-ALLIANCE: tarea "ControlFarmacias - Automatizacion Alliance", 22:15 locales, identidad Usuari.
rem Modo: SOMBRA hasta AUTO-ON (decision de Pio); en AUTO-ON se cambia a REAL con un commit.
rem PENDIENTE de AUTO-S: Pio lo compara con el .bat de importacion antes de crear la tarea.
cd /d C:\ControlFarmacias\Programa
.venv\Scripts\python.exe -m src.facturas.runtime_supabase.noche_automatica SOMBRA C:\ControlFarmacias\noches_auto
exit /b %ERRORLEVEL%
