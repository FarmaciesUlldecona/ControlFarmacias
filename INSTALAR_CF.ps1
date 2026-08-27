param(
    # Se conserva por compatibilidad con las instrucciones de versiones anteriores.
    [switch]$AgregarPathUsuario
)

$ErrorActionPreference = 'Stop'
$origen = Join-Path $PSScriptRoot 'cf.cmd'
$destinoDir = Join-Path $env:LOCALAPPDATA 'ControlFarmacias\bin'
$destino = Join-Path $destinoDir 'cf.cmd'

New-Item -ItemType Directory -Force -Path $destinoDir | Out-Null
Copy-Item -LiteralPath $origen -Destination $destino -Force

$pathUsuario = [Environment]::GetEnvironmentVariable('Path', 'User')
$partes = @($pathUsuario -split ';' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$destinoNormalizado = $destinoDir.TrimEnd('\')
$pathContieneDestino = @($partes | Where-Object {
    $_.TrimEnd('\').Equals($destinoNormalizado, [StringComparison]::OrdinalIgnoreCase)
}).Count -gt 0

if (-not $pathContieneDestino) {
    [Environment]::SetEnvironmentVariable(
        'Path',
        (($partes + $destinoDir) -join ';'),
        'User'
    )
}

$pathProcesoContieneDestino = @(($env:Path -split ';') | Where-Object {
    $_.Trim().TrimEnd('\').Equals($destinoNormalizado, [StringComparison]::OrdinalIgnoreCase)
}).Count -gt 0

if (-not $pathProcesoContieneDestino) {
    $env:Path = "$env:Path;$destinoDir"
}

Write-Host "Launcher instalado en: $destino"
Write-Host 'Abre una PowerShell nueva y usa: cf "estado"'
