param(
    [Parameter(Mandatory = $true)]
    [System.Management.Automation.PSCredential]$Credential
)

$ErrorActionPreference = "Stop"
$backup = Split-Path -Parent $MyInvocation.MyCommand.Path
$password = $Credential.GetNetworkCredential().Password

Register-ScheduledTask `
    -TaskName "ControlFarmacias - Importar facturas" `
    -Xml (Get-Content -LiteralPath (Join-Path $backup "ControlFarmacias_-_Importar_facturas.xml") -Raw) `
    -User "MOSTRADOR\Usuari" `
    -Password $password `
    -Force

Register-ScheduledTask `
    -TaskName "Sincronización ControlFarmacias" `
    -Xml (Get-Content -LiteralPath (Join-Path $backup "Sincronizacion_ControlFarmacias.xml") -Raw) `
    -User "MOSTRADOR\Usuari" `
    -Password $password `
    -Force
