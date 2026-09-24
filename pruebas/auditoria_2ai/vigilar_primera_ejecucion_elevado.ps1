# Vigilante temporal de Hito 2AI. No ejecuta la tarea.
# Ante ausencia, duplicidad o error, deja la tarea deshabilitada.

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$expectedCommand = "C:\ControlFarmacias\Programa\ejecutar_sincronizacion.bat"
$baselineLastRun = [datetime]"2026-09-22T17:56:24"
$scheduledStart = [datetime]"2026-09-22T21:30:00"
$deadline = [datetime]"2026-09-22T22:00:00"
$statusPath = Join-Path $PSScriptRoot "watchdog_status.txt"
$resultPath = Join-Path $PSScriptRoot "watchdog_result.txt"

function Write-Result([string]$status, [object]$task, [int]$eventCount) {
    $lines = @(
        "FINISHED_AT=$((Get-Date).ToString('o'))"
        "STATUS=$status"
        "ENABLED=$($task.Enabled)"
        "LAST_RUN=$($task.LastRunTime)"
        "LAST_RESULT=$($task.LastTaskResult)"
        "EVENT100_COUNT=$eventCount"
        "RUN_METHOD_USED=False"
    ) -join [Environment]::NewLine
    [IO.File]::WriteAllText($resultPath, $lines, [Text.UTF8Encoding]::new($false))
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Se requiere una consola elevada."
}

$service = New-Object -ComObject "Schedule.Service"
$service.Connect()
$folder = $service.GetFolder("\")
$tasks = @($folder.GetTasks(1) | Where-Object {
    ([xml]$_.Xml).Task.Actions.Exec.Command -eq $expectedCommand
})
if ($tasks.Count -ne 1) { throw "Tarea no identificada de forma unica." }
$task = $tasks[0]
if (-not $task.Enabled) { throw "La tarea no esta habilitada al iniciar vigilancia." }
if ([datetime]$task.LastRunTime -ne $baselineLastRun) {
    $task.Enabled = $false
    throw "LastRunTime inicial inesperado; tarea deshabilitada."
}

while ((Get-Date) -lt $deadline) {
    $instances = @($task.GetInstances(0))
    $events = @()
    if ((Get-Date) -ge $scheduledStart) {
        $events = @(Get-WinEvent -FilterHashtable @{
            LogName = "Microsoft-Windows-TaskScheduler/Operational"
            Id = 100
            StartTime = $scheduledStart.AddSeconds(-5)
        } | Where-Object { $_.Message -like "*ControlFarmacias*" })
    }

    if ($events.Count -gt 1 -or $instances.Count -gt 1) {
        $task.Enabled = $false
        Write-Result "DUPLICATE_FAIL_CLOSED" $task $events.Count
        exit 2
    }

    if ([datetime]$task.LastRunTime -gt $baselineLastRun -and $instances.Count -eq 0) {
        if ($task.LastTaskResult -eq 0 -and $events.Count -eq 1) {
            Write-Result "AUTOMATIC_SUCCESS" $task $events.Count
            exit 0
        }
        $task.Enabled = $false
        Write-Result "EXECUTION_FAILED_CLOSED" $task $events.Count
        exit 3
    }

    $status = @(
        "CHECKED_AT=$((Get-Date).ToString('o'))"
        "ENABLED=$($task.Enabled)"
        "INSTANCES=$($instances.Count)"
        "EVENT100_COUNT=$($events.Count)"
        "LAST_RUN=$($task.LastRunTime)"
    ) -join [Environment]::NewLine
    [IO.File]::WriteAllText($statusPath, $status, [Text.UTF8Encoding]::new($false))
    Start-Sleep -Seconds 10
}

$task.Enabled = $false
Write-Result "TIMEOUT_FAIL_CLOSED" $task 0
exit 4
