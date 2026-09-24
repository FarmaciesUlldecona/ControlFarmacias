# Hito 2AI: habilita exclusivamente el trigger nocturno ya existente.
# No contiene ni invoca Run, Start-ScheduledTask, BAT o Python.

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$expectedUserSid = "S-1-5-21-1664616495-3062778491-3524446278-1009"
$expectedCommand = "C:\ControlFarmacias\Programa\ejecutar_sincronizacion.bat"
$expectedWorkingDirectory = "C:\ControlFarmacias\Programa"
$resultPath = Join-Path $PSScriptRoot "resultado_habilitacion.txt"
$errorPath = Join-Path $PSScriptRoot "error_habilitacion.txt"

trap {
    $detail = @(
        "FAILED_AT=$((Get-Date).ToString('o'))"
        "ERROR=$($_.Exception.Message)"
        "HRESULT=0x{0:X8}" -f ($_.Exception.HResult -band 0xffffffff)
        "POSITION=$($_.InvocationInfo.PositionMessage)"
    ) -join [Environment]::NewLine
    [IO.File]::WriteAllText($errorPath, $detail, [Text.UTF8Encoding]::new($false))
    exit 1
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Se requiere una consola elevada."
}

$service = New-Object -ComObject "Schedule.Service"
$service.Connect()
$folder = $service.GetFolder("\")
$candidates = @($folder.GetTasks(1) | Where-Object {
    ([xml]$_.Xml).Task.Actions.Exec.Command -eq $expectedCommand
})
if ($candidates.Count -ne 1) {
    throw "FAIL_CLOSED: tarea no identificada de forma unica."
}
$task = $candidates[0]
$xml = [xml]$task.Xml
$now = Get-Date
$nextRun = [datetime]$task.NextRunTime
$lastRunBefore = [datetime]$task.LastRunTime

if ($task.Enabled) { throw "FAIL_CLOSED: la tarea ya estaba habilitada." }
if ($task.State -eq 4 -or @($task.GetInstances(0)).Count -ne 0) {
    throw "FAIL_CLOSED: existe una instancia en ejecucion."
}
if (($nextRun - $now).TotalMinutes -lt 60) {
    throw "FAIL_CLOSED: trigger automatico demasiado proximo."
}
if ($lastRunBefore.Date -ne $now.Date) {
    throw "FAIL_CLOSED: no se puede descartar una ejecucion perdida pendiente."
}
if ($xml.Task.Principals.Principal.UserId -ne $expectedUserSid) {
    throw "FAIL_CLOSED: principal inesperado."
}
if ($xml.Task.Actions.Exec.Command -ne $expectedCommand -or
    $xml.Task.Actions.Exec.WorkingDirectory -ne $expectedWorkingDirectory) {
    throw "FAIL_CLOSED: accion o StartIn inesperados."
}
if ($xml.Task.Triggers.CalendarTrigger.ScheduleByDay.DaysInterval -ne "1" -or
    ([datetime]$xml.Task.Triggers.CalendarTrigger.StartBoundary).TimeOfDay -ne ([timespan]::FromHours(21.5))) {
    throw "FAIL_CLOSED: trigger diario inesperado."
}

$task.Enabled = $true
Start-Sleep -Seconds 20

# Un arranque durante esta ventana no seria el trigger de las 21:30.
if (@($task.GetInstances(0)).Count -ne 0 -or [datetime]$task.LastRunTime -ne $lastRunBefore) {
    $task.Enabled = $false
    throw "FAIL_CLOSED: se detecto un arranque inmediato inesperado; tarea deshabilitada."
}

$result = @(
    "ENABLED_AT=$($now.ToString('o'))"
    "ENABLED=$($task.Enabled)"
    "NEXT_RUN=$($task.NextRunTime)"
    "LAST_RUN_UNCHANGED=$lastRunBefore"
    "IMMEDIATE_INSTANCES=0"
    "RUN_METHOD_USED=False"
) -join [Environment]::NewLine
[IO.File]::WriteAllText($resultPath, $result, [Text.UTF8Encoding]::new($false))
