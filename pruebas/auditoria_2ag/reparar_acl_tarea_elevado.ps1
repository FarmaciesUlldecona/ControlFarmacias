# Correccion manual y minima para Hito 2AG.
# Ejecutar EXCLUSIVAMENTE desde PowerShell "Ejecutar como administrador".
# Este script no inicia la tarea, no ejecuta el BAT y deja la tarea deshabilitada.

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$taskName = "Sincronizaci$([char]0xF3)n ControlFarmacias"
$operatorSid = "S-1-5-21-1664616495-3062778491-3524446278-1001"
$taskExecute = 0x20
$expectedReadMask = 0x00120089
$expectedRunMask = 0x001200A9

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
$administrators = [Security.Principal.WindowsBuiltInRole]::Administrator
if (-not $principal.IsInRole($administrators)) {
    throw "Se requiere una consola elevada. No se ha modificado la tarea."
}

$service = New-Object -ComObject "Schedule.Service"
$service.Connect()
$folder = $service.GetFolder("\")
$task = $folder.GetTask("\$taskName")

if ($task.State -eq 4) {
    throw "La tarea esta ejecutandose. No se ha modificado la tarea."
}

# Primera medida: impedir una ejecucion automatica mientras se corrige la ACL.
$task.Enabled = $false

$sddlBefore = $task.GetSecurityDescriptor(0xF)
$backupPath = Join-Path $PSScriptRoot "task_sddl_pre_correccion.txt"
[IO.File]::WriteAllText($backupPath, $sddlBefore, [Text.UTF8Encoding]::new($false))

$descriptor = [Security.AccessControl.RawSecurityDescriptor]::new($sddlBefore)
$oldAcl = $descriptor.DiscretionaryAcl
$newAcl = [Security.AccessControl.RawAcl]::new($oldAcl.Revision, $oldAcl.Count)
$found = $false

foreach ($ace in $oldAcl) {
    if (
        $ace -is [Security.AccessControl.CommonAce] -and
        $ace.AceQualifier -eq [Security.AccessControl.AceQualifier]::AccessAllowed -and
        $ace.SecurityIdentifier.Value -eq $operatorSid
    ) {
        if (($ace.AccessMask -band $expectedReadMask) -ne $expectedReadMask) {
            throw "La ACE del operador no conserva el permiso READ esperado. No se cambia la ACL."
        }

        $newMask = $ace.AccessMask -bor $taskExecute
        if ($newMask -ne $expectedRunMask) {
            throw ("Mascara inesperada para el operador: 0x{0:X8}. No se cambia la ACL." -f $newMask)
        }

        $replacement = [Security.AccessControl.CommonAce]::new(
            $ace.AceFlags,
            $ace.AceQualifier,
            $newMask,
            $ace.SecurityIdentifier,
            $ace.IsCallback,
            $ace.GetOpaque()
        )
        $newAcl.InsertAce($newAcl.Count, $replacement)
        $found = $true
    }
    else {
        $newAcl.InsertAce($newAcl.Count, $ace)
    }
}

if (-not $found) {
    throw "No se encontro la ACE READ preexistente de MOSTRADOR\Usuari. No se cambia la ACL."
}

$descriptor.DiscretionaryAcl = $newAcl
$sddlAfter = $descriptor.GetSddlForm([Security.AccessControl.AccessControlSections]::All)
$task.SetSecurityDescriptor($sddlAfter, 0)

$verifiedSddl = $task.GetSecurityDescriptor(0xF)
$verified = [Security.AccessControl.RawSecurityDescriptor]::new($verifiedSddl)
$operatorAce = $verified.DiscretionaryAcl | Where-Object {
    $_ -is [Security.AccessControl.CommonAce] -and
    $_.AceQualifier -eq [Security.AccessControl.AceQualifier]::AccessAllowed -and
    $_.SecurityIdentifier.Value -eq $operatorSid
}

if ($operatorAce.Count -ne 1 -or $operatorAce[0].AccessMask -ne $expectedRunMask) {
    throw "La verificacion posterior de la ACL no coincide con READ+RUN (0x001200A9)."
}

Write-Output "CORRECCION_OK"
Write-Output "Tarea habilitada: $($task.Enabled)"
Write-Output ("Mascara MOSTRADOR\Usuari: 0x{0:X8}" -f $operatorAce[0].AccessMask)
Write-Output "No se ha ejecutado la tarea."
