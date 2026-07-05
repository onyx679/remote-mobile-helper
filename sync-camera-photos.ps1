param(
    [string]$Serial = "adb-2252475e-baGT88._adb-tls-connect._tcp",
    [string]$RemoteDir = "/sdcard/DCIM/Camera",
    [string]$LocalDir = ".\camera-inbox",
    [string]$RotatedDir = ".\camera-rotated",
    [double]$PollSeconds = 0.5,
    [ValidateSet(0, 90, 180, 270)]
    [int]$RotateDegrees = 0,
    [switch]$PullExisting,
    [switch]$PromptForAi,
    [switch]$CopyToClipboard,
    [switch]$Once
)

$ErrorActionPreference = "Stop"

function Find-Adb {
    $cmd = Get-Command adb -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $wingetRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    $adb = Get-ChildItem -Path $wingetRoot -Recurse -Filter adb.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -like "*Genymobile.scrcpy*" } |
        Select-Object -First 1 -ExpandProperty FullName

    if (-not $adb) {
        throw "adb.exe not found. Install scrcpy first: winget install --id Genymobile.scrcpy --exact"
    }

    return $adb
}

function Get-RemoteImages {
    param(
        [string]$Adb,
        [string]$DeviceSerial,
        [string]$Directory
    )

    $escapedDir = $Directory.Replace("'", "'\''")
    $findCommand = "find '$escapedDir' -maxdepth 1 -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.heic' -o -iname '*.webp' \)"

    & $Adb -s $DeviceSerial shell $findCommand |
        ForEach-Object { $_.Trim() } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) -and $_ -like "$Directory/*" }
}

function Get-RemoteFileSize {
    param(
        [string]$Adb,
        [string]$DeviceSerial,
        [string]$RemotePath
    )

    $escapedPath = $RemotePath.Replace("'", "'\''")
    $size = (& $Adb -s $DeviceSerial shell "stat -c %s '$escapedPath' 2>/dev/null").Trim()
    if ($size -match '^\d+$') {
        return [int64]$size
    }

    return -1
}

function Wait-RemoteFileStable {
    param(
        [string]$Adb,
        [string]$DeviceSerial,
        [string]$RemotePath
    )

    $previous = Get-RemoteFileSize -Adb $Adb -DeviceSerial $DeviceSerial -RemotePath $RemotePath
    Start-Sleep -Milliseconds 250
    $current = Get-RemoteFileSize -Adb $Adb -DeviceSerial $DeviceSerial -RemotePath $RemotePath

    return ($previous -gt 0 -and $previous -eq $current)
}

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

function Convert-RotatedPhoto {
    param(
        [string]$PhotoPath,
        [string]$OutputDir,
        [int]$Degrees
    )

    if ($Degrees -eq 0) {
        return $PhotoPath
    }

    Add-Type -AssemblyName System.Drawing

    $format = Get-ImageFormat -Path $PhotoPath
    if (-not $format) {
        Write-Warning "Rotation skipped for unsupported image type: $PhotoPath"
        return $PhotoPath
    }

    $resolvedOutputDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDir)
    New-Item -ItemType Directory -Force -Path $resolvedOutputDir | Out-Null

    $sourcePath = (Resolve-Path -LiteralPath $PhotoPath).Path
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($sourcePath)
    $extension = [System.IO.Path]::GetExtension($sourcePath)
    $outputPath = Join-Path $resolvedOutputDir "$baseName-rot$Degrees$extension"

    $image = [System.Drawing.Image]::FromFile($sourcePath)
    try {
        switch ($Degrees) {
            90 { $image.RotateFlip([System.Drawing.RotateFlipType]::Rotate90FlipNone) }
            180 { $image.RotateFlip([System.Drawing.RotateFlipType]::Rotate180FlipNone) }
            270 { $image.RotateFlip([System.Drawing.RotateFlipType]::Rotate270FlipNone) }
        }

        $image.Save($outputPath, $format)
    } finally {
        $image.Dispose()
    }

    Write-Host "Rotated photo: $outputPath"
    return $outputPath
}

function Copy-ToAiOutbox {
    param(
        [string]$PhotoPath
    )

    $outbox = Join-Path (Get-Location) "ai-outbox"
    New-Item -ItemType Directory -Force -Path $outbox | Out-Null

    $destination = Join-Path $outbox (Split-Path -Leaf $PhotoPath)
    Copy-Item -LiteralPath $PhotoPath -Destination $destination -Force

    $record = [ordered]@{
        queuedAt = (Get-Date).ToString("o")
        source = (Resolve-Path -LiteralPath $PhotoPath).Path
        outbox = (Resolve-Path -LiteralPath $destination).Path
        status = "queued-not-sent"
    }

    $record | ConvertTo-Json -Compress | Add-Content -Path (Join-Path $outbox "queue.jsonl")
    Write-Host "Queued for AI review: $destination"
}

function Set-PhotoClipboard {
    param(
        [string]$PhotoPath
    )

    $resolvedPath = (Resolve-Path -LiteralPath $PhotoPath).Path

    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

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
}

function Test-ImageReadable {
    param(
        [string]$PhotoPath
    )

    $extension = [System.IO.Path]::GetExtension($PhotoPath).ToLowerInvariant()
    if ($extension -notin @(".jpg", ".jpeg", ".png", ".bmp", ".gif")) {
        return $true
    }

    Add-Type -AssemblyName System.Drawing
    $stream = $null
    $image = $null
    try {
        $stream = [System.IO.File]::Open($PhotoPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        $image = [System.Drawing.Image]::FromStream($stream)
        return $true
    } catch {
        return $false
    } finally {
        if ($image) {
            $image.Dispose()
        }
        if ($stream) {
            $stream.Dispose()
        }
    }
}

$adb = Find-Adb
$resolvedLocalDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($LocalDir)
New-Item -ItemType Directory -Force -Path $resolvedLocalDir | Out-Null

Write-Host "Using adb: $adb"
Write-Host "Watching $RemoteDir on $Serial"
Write-Host "Saving photos to $resolvedLocalDir"
if ($RotateDegrees -ne 0) {
    Write-Host "Rotating clipboard output by $RotateDegrees degrees"
}

$known = @{}
if (-not $PullExisting) {
    foreach ($photo in Get-RemoteImages -Adb $adb -DeviceSerial $Serial -Directory $RemoteDir) {
        $known[$photo] = $true
    }

    Write-Host "Existing photos were marked as already seen. Only new photos will be copied."
} else {
    Write-Host "PullExisting is enabled. Existing photos will also be copied."
}

Write-Host "Press Ctrl+C to stop."

while ($true) {
    try {
        $photos = Get-RemoteImages -Adb $adb -DeviceSerial $Serial -Directory $RemoteDir
        foreach ($remotePhoto in $photos) {
            if ($known.ContainsKey($remotePhoto)) {
                continue
            }

            if (-not (Wait-RemoteFileStable -Adb $adb -DeviceSerial $Serial -RemotePath $remotePhoto)) {
                continue
            }

            $fileName = ($remotePhoto -split '/')[-1]
            $localPath = Join-Path $resolvedLocalDir $fileName
            $partialPath = "$localPath.part"

            Write-Host "Copying $remotePhoto"
            Remove-Item -LiteralPath $partialPath -Force -ErrorAction SilentlyContinue
            & $adb -s $Serial pull $remotePhoto $partialPath | Out-Host
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $partialPath)) {
                Write-Warning "Pull failed; will retry next poll: $remotePhoto"
                Remove-Item -LiteralPath $partialPath -Force -ErrorAction SilentlyContinue
                continue
            }

            $partialItem = Get-Item -LiteralPath $partialPath -ErrorAction SilentlyContinue
            if (-not $partialItem -or $partialItem.Length -lt 10240 -or -not (Test-ImageReadable -PhotoPath $partialPath)) {
                Write-Warning "Pulled file is incomplete or unreadable; will retry next poll: $remotePhoto"
                Remove-Item -LiteralPath $partialPath -Force -ErrorAction SilentlyContinue
                continue
            }

            Move-Item -LiteralPath $partialPath -Destination $localPath -Force
            $known[$remotePhoto] = $true

            if (Test-Path -LiteralPath $localPath) {
                Write-Host "Saved: $localPath"

                if ($CopyToClipboard) {
                    $clipboardPath = Convert-RotatedPhoto -PhotoPath $localPath -OutputDir $RotatedDir -Degrees $RotateDegrees
                    Set-PhotoClipboard -PhotoPath $clipboardPath
                }

                if ($PromptForAi) {
                    $answer = Read-Host "Queue this photo for AI? [y/N]"
                    if ($answer -match '^(y|yes)$') {
                        Copy-ToAiOutbox -PhotoPath $localPath
                    }
                }
            }
        }
    } catch {
        Write-Warning $_.Exception.Message
    }

    if ($Once) {
        break
    }

    Start-Sleep -Milliseconds ([int]($PollSeconds * 1000))
}
