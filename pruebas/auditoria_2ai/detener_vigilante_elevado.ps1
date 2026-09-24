# Detiene exclusivamente el vigilante temporal del Hito 2AI.
# No consulta ni modifica la tarea programada.

$ErrorActionPreference = "Stop"
$watchdogPid = 6140
$resultPath = Join-Path $PSScriptRoot "watchdog_detencion.txt"
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$watchdogPid" -ErrorAction SilentlyContinue

if ($null -eq $process) {
    $result = "STOPPED_AT=$((Get-Date).ToString('o'))`nSTATUS=ALREADY_STOPPED"
}
elseif ($process.CommandLine -notlike "*vigilar_primera_ejecucion_elevado.ps1*") {
    throw "FAIL_CLOSED: el PID no corresponde al vigilante esperado."
}
else {
    Stop-Process -Id $watchdogPid -Force
    $result = "STOPPED_AT=$((Get-Date).ToString('o'))`nSTATUS=WATCHDOG_STOPPED`nPID=$watchdogPid"
}

[IO.File]::WriteAllText($resultPath, $result, [Text.UTF8Encoding]::new($false))
