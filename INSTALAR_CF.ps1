param(
    [switch]$AgregarPathUsuario
)

$ErrorActionPreference = 'Stop'
$origen = Join-Path $PSScriptRoot 'cf.cmd'
$destinoDir = Join-Path $env:LOCALAPPDATA 'ControlFarmacias\bin'
$destino = Join-Path $destinoDir 'cf.cmd'

New-Item -ItemType Directory -Force -Path $destinoDir | Out-Null
Copy-Item -LiteralPath $origen -Destination $destino -Force

if ($AgregarPathUsuario) {
    $pathUsuario = [Environment]::GetEnvironmentVariable('Path', 'User')
    $partes = @($pathUsuario -split ';' | Where-Object { $_ })
    if ($destinoDir -notin $partes) {
        [Environment]::SetEnvironmentVariable(
            'Path',
            (($partes + $destinoDir) -join ';'),
            'User'
        )
    }
    if ($destinoDir -notin ($env:Path -split ';')) {
        $env:Path = "$env:Path;$destinoDir"
    }
    Write-Host 'Instalado. Abre una PowerShell nueva y usa: cf "estado"'
} else {
    Write-Host "Launcher copiado en: $destino"
    Write-Host "Puedes usarlo por ruta o repetir con -AgregarPathUsuario."
}
