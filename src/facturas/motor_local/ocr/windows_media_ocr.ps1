param(
    [Parameter(Mandatory = $true)][string]$ImagePath,
    [string]$LanguageTag = "es-ES"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime

function Await-WinRt {
    param($Operation, [Type]$ResultType)
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object { $_.Name -eq "AsTask" -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 } |
        Select-Object -First 1
    $task = $method.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.Wait()
    return $task.Result
}

$language = [Windows.Globalization.Language, Windows.Foundation, ContentType=WindowsRuntime]::new($LanguageTag)
$engine = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]::TryCreateFromLanguage($language)
if ($null -eq $engine) { throw "OCR language unavailable: $LanguageTag" }

$storageFileType = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$streamType = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
$decoderType = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType=WindowsRuntime]
$bitmapType = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType=WindowsRuntime]
$resultType = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType=WindowsRuntime]

$file = Await-WinRt ($storageFileType::GetFileFromPathAsync((Resolve-Path -LiteralPath $ImagePath).Path)) $storageFileType
$stream = Await-WinRt ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) $streamType
try {
    $decoder = Await-WinRt ($decoderType::CreateAsync($stream)) $decoderType
    $bitmap = Await-WinRt ($decoder.GetSoftwareBitmapAsync()) $bitmapType
    try {
        $result = Await-WinRt ($engine.RecognizeAsync($bitmap)) $resultType
        $lines = @(
            foreach ($line in $result.Lines) {
                [ordered]@{
                    text = $line.Text
                    words = @(
                        foreach ($word in $line.Words) {
                            $rect = $word.BoundingRect
                            [ordered]@{
                                text = $word.Text
                                x = [double]$rect.X
                                y = [double]$rect.Y
                                width = [double]$rect.Width
                                height = [double]$rect.Height
                                confidence = $null
                            }
                        }
                    )
                }
            }
        )
        [ordered]@{
            engine = "Windows.Media.Ocr"
            language = $engine.RecognizerLanguage.LanguageTag
            text_angle = if ($null -eq $result.TextAngle) { $null } else { [double]$result.TextAngle }
            confidence_available = $false
            lines = $lines
        } | ConvertTo-Json -Depth 8 -Compress
    }
    finally { if ($null -ne $bitmap) { $bitmap.Dispose() } }
}
finally { if ($null -ne $stream) { $stream.Dispose() } }
