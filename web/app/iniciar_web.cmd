@echo off
rem ControlFarmacias web, fase 1. SOLO LO EJECUTA PIO.
rem Arranca la web en modo REAL en http://127.0.0.1:4747 (solo este equipo) y abre el navegador.
rem Cerrar esta ventana (o Ctrl+C) detiene la web.
setlocal
cd /d "%~dp0"
title ControlFarmacias web (modo REAL, 127.0.0.1:4747)
where node >nul 2>nul || (echo No se encuentra Node.js en este equipo. & pause & exit /b 1)
rem El modo y el puerto los fija este fichero: se ignoran los que hubiera en el entorno.
set "CF_MODO="
set "CF_PUERTO="
rem En segundo plano: espera a que la web responda (la pantalla de acceso devuelve 401) y abre el navegador.
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "for ($i = 0; $i -lt 90; $i++) { try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 'http://127.0.0.1:4747/' | Out-Null; break } catch { if ($_.Exception.Response) { break }; Start-Sleep -Seconds 1 } }; Start-Process 'http://127.0.0.1:4747/'"
call npm run dev:real
echo.
echo La web se ha detenido.
pause
