param(
    [Parameter(Mandatory = $true)]
    [string]$PhotoPath,

    [string]$RotatedDir = ".\camera-rotated",

    [ValidateSet(0, 90, 180, 270)]
    [int]$RotateDegrees = 0
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $PhotoPath)) {
    throw "Photo not found: $PhotoPath"
}

$resolvedPath = (Resolve-Path -LiteralPath $PhotoPath).Path

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function Get-ImageFormat {
    param(
        [string]$Path
    )

    $extension = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
    switch ($extension) {
        ".jpg" { return [System.Drawing.Imaging.ImageFormat]::Jpeg }
        ".jpeg" { return [System.Drawing.Imaging.ImageFormat]::Jpeg }
        ".png" { return [System.Drawing.Imaging.ImageFormat]::Png }
        ".bmp" { return [System.Drawing.Imaging.ImageFormat]::Bmp }
        ".gif" { return [System.Drawing.Imaging.ImageFormat]::Gif }
        default { return $null }
    }
}

if ($RotateDegrees -ne 0) {
    $format = Get-ImageFormat -Path $resolvedPath
    if ($format) {
        $resolvedOutputDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($RotatedDir)
        New-Item -ItemType Directory -Force -Path $resolvedOutputDir | Out-Null

        $baseName = [System.IO.Path]::GetFileNameWithoutExtension($resolvedPath)
        $extension = [System.IO.Path]::GetExtension($resolvedPath)
        $outputPath = Join-Path $resolvedOutputDir "$baseName-rot$RotateDegrees$extension"

        $sourceImage = [System.Drawing.Image]::FromFile($resolvedPath)
        try {
            switch ($RotateDegrees) {
                90 { $sourceImage.RotateFlip([System.Drawing.RotateFlipType]::Rotate90FlipNone) }
                180 { $sourceImage.RotateFlip([System.Drawing.RotateFlipType]::Rotate180FlipNone) }
                270 { $sourceImage.RotateFlip([System.Drawing.RotateFlipType]::Rotate270FlipNone) }
            }

            $sourceImage.Save($outputPath, $format)
        } finally {
            $sourceImage.Dispose()
        }

        $resolvedPath = $outputPath
    } else {
        Write-Warning "Rotation skipped for unsupported image type: $resolvedPath"
    }
}

$files = New-Object System.Collections.Specialized.StringCollection
[void]$files.Add($resolvedPath)

$data = New-Object System.Windows.Forms.DataObject
$data.SetFileDropList($files)
$data.SetText($resolvedPath)

$extension = [System.IO.Path]::GetExtension($resolvedPath).ToLowerInvariant()
if ($extension -in @(".jpg", ".jpeg", ".png", ".bmp", ".gif")) {
    $stream = [System.IO.File]::Open($resolvedPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    try {
        $image = [System.Drawing.Image]::FromStream($stream)
        $bitmap = New-Object System.Drawing.Bitmap $image
        $data.SetImage($bitmap)
    } finally {
        if ($image) {
            $image.Dispose()
        }
        $stream.Dispose()
    }
}

[System.Windows.Forms.Clipboard]::SetDataObject($data, $true)
Write-Host "Copied to clipboard: $resolvedPath"
