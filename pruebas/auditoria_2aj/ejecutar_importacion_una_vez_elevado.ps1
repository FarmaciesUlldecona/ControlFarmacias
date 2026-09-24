# Hito 2AJ: una unica llamada oficial a la tarea real de importacion.
# No ejecuta BAT ni Python directamente y deja la tarea deshabilitada.

$ErrorActionPreference = "Stop"
$expectedCommand = "C:\ControlFarmacias\Programa\ejecutar_importacion_facturas.bat"
$expectedWorkingDirectory = "C:\ControlFarmacias\Programa"
$expectedUserSid = "S-1-5-21-1664616495-3062778491-3524446278-1001"
$guardPath = Join-Path $PSScriptRoot "ejecucion_unica_aceptada.guard"
$resultPath = Join-Path $PSScriptRoot "resultado_lanzamiento.txt"
$errorPath = Join-Path $PSScriptRoot "error_lanzamiento.txt"

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
if (Test-Path -LiteralPath $guardPath) {
    throw "Guard anti-repeticion presente."
}

$service = New-Object -ComObject "Schedule.Service"
$service.Connect()
$folder = $service.GetFolder("\")
$tasks = @($folder.GetTasks(1) | Where-Object {
    ([xml]$_.Xml).Task.Actions.Exec.Command -eq $expectedCommand
})
if ($tasks.Count -ne 1) { throw "Tarea no identificada de forma unica." }
$task = $tasks[0]
$xml = [xml]$task.Xml
$now = Get-Date
$nextRun = [datetime]$task.NextRunTime

if ($task.Enabled) { throw "FAIL_CLOSED: tarea ya habilitada." }
if ($task.State -eq 4 -or @($task.GetInstances(0)).Count -ne 0) {
    throw "FAIL_CLOSED: existe una instancia activa."
}
if (($nextRun - $now).TotalMinutes -lt 60) {
    throw "FAIL_CLOSED: trigger automatico demasiado proximo."
}
if ($xml.Task.Principals.Principal.UserId -ne $expectedUserSid) {
    throw "FAIL_CLOSED: principal inesperado."
}
if ($xml.Task.Actions.Exec.Command -ne $expectedCommand -or
    $xml.Task.Actions.Exec.WorkingDirectory -ne $expectedWorkingDirectory) {
    throw "FAIL_CLOSED: accion o StartIn inesperados."
}

$accepted = $false
$instance = $null
try {
    $task.Enabled = $true
    $instance = $task.Run($null)
    $accepted = $true
    $guard = @(
        "RUN_CALL_ACCEPTED=True"
        "ACCEPTED_AT=$((Get-Date).ToString('o'))"
        "INSTANCE_GUID=$($instance.InstanceGuid)"
    ) -join [Environment]::NewLine
    [IO.File]::WriteAllText($guardPath, $guard, [Text.UTF8Encoding]::new($false))
}
finally {
    $task.Enabled = $false
    $result = @(
        "FINISHED_AT=$((Get-Date).ToString('o'))"
        "RUN_CALL_ACCEPTED=$accepted"
        "INSTANCE_GUID=$($instance.InstanceGuid)"
        "FINAL_ENABLED=$($task.Enabled)"
        "NEXT_RUN_BEFORE_ENABLE=$nextRun"
    ) -join [Environment]::NewLine
    [IO.File]::WriteAllText($resultPath, $result, [Text.UTF8Encoding]::new($false))
}

if (-not $accepted) { throw "La llamada Run no fue aceptada." }
