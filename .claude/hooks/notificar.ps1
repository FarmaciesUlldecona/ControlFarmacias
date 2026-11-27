# Hook Notification de Claude Code (PERMISOS-1, decision de Pio del 2026-11-27): aviso de Windows sin modulos.
# Usa WinRT desde Windows PowerShell 5.1 (sin modulos de terceros ni dependencias). Lee el JSON del hook por stdin y
# muestra su "message", recortado a 200 caracteres y sin rutas. Nunca bloquea: ante cualquier error, sale con 0.
$ErrorActionPreference = 'Stop'
try {
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    $mensaje = ''
    $texto = [Console]::In.ReadToEnd()
    if ($texto) {
        $entrada = $texto | ConvertFrom-Json
        if ($entrada.message) { $mensaje = [string]$entrada.message }
    }
    if (-not $mensaje) { $mensaje = 'Claude Code necesita tu respuesta.' }
    $mensaje = $mensaje -replace '[A-Za-z]:[\\/][^\s"'']*', '<ruta>'
    $mensaje = $mensaje -replace '(?<![\w.])(?:\.{0,2}/)?(?:[\w.-]+/){1,}[\w.-]+', '<ruta>'
    if ($mensaje.Length -gt 200) { $mensaje = $mensaje.Substring(0, 200) }

    $null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
    $tipo = [Windows.UI.Notifications.ToastTemplateType]::ToastText02
    $plantilla = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($tipo)
    $textos = $plantilla.GetElementsByTagName('text')
    $null = $textos.Item(0).AppendChild($plantilla.CreateTextNode('Claude Code'))
    $null = $textos.Item(1).AppendChild($plantilla.CreateTextNode($mensaje))
    $aviso = [Windows.UI.Notifications.ToastNotification]::new($plantilla)
    $aplicacion = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($aplicacion).Show($aviso)
} catch {
}
exit 0
