# Hito 2AJ: neutraliza exclusivamente el trigger del importador.
# No ejecuta la tarea, BAT, Python ni ningun flujo productivo.

$ErrorActionPreference = "Stop"
$expectedCommand = "C:\ControlFarmacias\Programa\ejecutar_importacion_facturas.bat"
$resultPath = Join-Path $PSScriptRoot "resultado_deshabilitacion.txt"

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
$now = Get-Date
$nextRun = [datetime]$task.NextRunTime
if (-not $task.Enabled) { throw "La tarea ya estaba deshabilitada." }
if ($task.State -eq 4 -or @($task.GetInstances(0)).Count -ne 0) {
    throw "Existe una instancia activa."
}
if (($nextRun - $now).TotalMinutes -lt 60) {
    throw "Trigger demasiado proximo para neutralizacion segura."
}

$task.Enabled = $false
$result = @(
    "DISABLED_AT=$($now.ToString('o'))"
    "ENABLED=$($task.Enabled)"
    "INSTANCES=$(@($task.GetInstances(0)).Count)"
    "NEXT_RUN_BEFORE_DISABLE=$nextRun"
    "RUN_METHOD_USED=False"
) -join [Environment]::NewLine
[IO.File]::WriteAllText($resultPath, $result, [Text.UTF8Encoding]::new($false))
