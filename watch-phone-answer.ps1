param(
    [string]$Serial = "192.168.0.100:41965",
    [string]$RemoteDir = "/sdcard/DCIM/Camera",
    [string]$LocalDir = ".\camera-inbox",
    [string]$Crop = "0.30,0.42,0.75,0.60",
    [double]$PollSeconds = 0.2,
    [ValidateSet("photo", "screencap")]
    [string]$Mode = "screencap",
    [switch]$CopyAnswer,
    [switch]$PullExisting
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
        throw "adb.exe not found. Install scrcpy first."
    }

    return $adb
}

function Get-RemotePhotos {
    param(
        [string]$Adb,
        [string]$DeviceSerial,
        [string]$Directory
    )

    $cmd = "find '$Directory' -maxdepth 1 -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \) -printf '%T@ %p\n' 2>/dev/null | sort -n"
    & $Adb -s $DeviceSerial shell $cmd |
        ForEach-Object {
            $line = $_.Trim()
            if ($line -match '^(?<ts>\d+(\.\d+)?)\s+(?<path>.+)$') {
                [pscustomobject]@{
                    Timestamp = [double]$Matches.ts
                    Path = $Matches.path
                    Name = Split-Path -Leaf $Matches.path
                }
            }
        }
}

function Get-RemoteSize {
    param(
        [string]$Adb,
        [string]$DeviceSerial,
        [string]$RemotePath
    )

    $escaped = $RemotePath.Replace("'", "'\''")
    $size = (& $Adb -s $DeviceSerial shell "stat -c %s '$escaped' 2>/dev/null").Trim()
    if ($size -match '^\d+$') {
        return [int64]$size
    }

    return -1
}

function Wait-RemoteStable {
    param(
        [string]$Adb,
        [string]$DeviceSerial,
        [string]$RemotePath
    )

    $a = Get-RemoteSize -Adb $Adb -DeviceSerial $DeviceSerial -RemotePath $RemotePath
    Start-Sleep -Milliseconds 150
    $b = Get-RemoteSize -Adb $Adb -DeviceSerial $DeviceSerial -RemotePath $RemotePath
    return ($a -gt 0 -and $a -eq $b)
}

$adb = Find-Adb
$resolvedLocalDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($LocalDir)
New-Item -ItemType Directory -Force -Path $resolvedLocalDir | Out-Null

Write-Host "Watching phone camera photos directly." -ForegroundColor Cyan
Write-Host "ADB: $adb"
Write-Host "Device: $Serial"
Write-Host "Mode: $Mode"
Write-Host "Remote: $RemoteDir"
Write-Host "Local: $resolvedLocalDir"
Write-Host "Crop: $Crop"
Write-Host "Press Ctrl+C to stop."
Write-Host ""

if ($Mode -eq "photo") {
    $known = @{}
    if (-not $PullExisting) {
        foreach ($photo in Get-RemotePhotos -Adb $adb -DeviceSerial $Serial -Directory $RemoteDir) {
            $known[$photo.Path] = $true
        }
        Write-Host "Existing phone photos marked as seen. Waiting for the next shot..." -ForegroundColor DarkGray
    } else {
        Write-Host "PullExisting enabled. Existing phone photos will be processed." -ForegroundColor Yellow
    }
} else {
    Write-Host "Screencap mode reads the current phone screen repeatedly. It does not wait for camera photos." -ForegroundColor DarkGray
    $lastWord = ""
    $lastAnswerAt = Get-Date "2000-01-01"
}

while ($true) {
    try {
        if ($Mode -eq "screencap") {
            $overall = [Diagnostics.Stopwatch]::StartNew()
            $localPath = Join-Path $resolvedLocalDir "current-screen.png"
            & $adb -s $Serial exec-out screencap -p > $localPath

            $json = & python .\ocr_answer_photo.py $localPath --crop $Crop --json-out .\latest-result.json --txt-out .\latest-answer.txt --save-crop .\latest-crop.png
            $result = $json | ConvertFrom-Json

            if ($result.word -and ($result.word -ne $lastWord -or ((Get-Date) - $lastAnswerAt).TotalSeconds -ge 2)) {
                $lastWord = $result.word
                $lastAnswerAt = Get-Date
                if ($CopyAnswer) {
                    Set-Clipboard -Value $result.answer.ToUpperInvariant()
                }

                $overall.Stop()
                $answer = $result.answer.ToUpperInvariant()
                $color = if ($answer -eq "YES") { "Green" } elseif ($answer -eq "NO") { "Red" } else { "Yellow" }
                Write-Host ("[{0}] ANSWER: {1}    WORD: {2}    OCR: {3} ms    TOTAL: {4} ms" -f (Get-Date -Format HH:mm:ss.fff), $answer, $result.word, $result.elapsedMs, $overall.ElapsedMilliseconds) -ForegroundColor $color
                Write-Host ""
            }

            Start-Sleep -Milliseconds ([int]($PollSeconds * 1000))
            continue
        }

        $photos = Get-RemotePhotos -Adb $adb -DeviceSerial $Serial -Directory $RemoteDir
        foreach ($photo in $photos) {
            if ($known.ContainsKey($photo.Path)) {
                continue
            }

            if (-not (Wait-RemoteStable -Adb $adb -DeviceSerial $Serial -RemotePath $photo.Path)) {
                continue
            }

            $known[$photo.Path] = $true
            $localPath = Join-Path $resolvedLocalDir $photo.Name

            $overall = [Diagnostics.Stopwatch]::StartNew()
            Write-Host "[$(Get-Date -Format HH:mm:ss.fff)] New photo: $($photo.Name)" -ForegroundColor Gray

            & $adb -s $Serial pull $photo.Path $localPath | Out-Null

            $json = & python .\ocr_answer_photo.py $localPath --crop $Crop --json-out .\latest-result.json --txt-out .\latest-answer.txt --save-crop .\latest-crop.png
            $result = $json | ConvertFrom-Json

            if ($CopyAnswer) {
                Set-Clipboard -Value $result.answer.ToUpperInvariant()
            }

            $overall.Stop()
            $answer = $result.answer.ToUpperInvariant()
            $color = if ($answer -eq "YES") { "Green" } elseif ($answer -eq "NO") { "Red" } else { "Yellow" }
            Write-Host ("ANSWER: {0}    WORD: {1}    OCR: {2} ms    TOTAL: {3} ms" -f $answer, $result.word, $result.elapsedMs, $overall.ElapsedMilliseconds) -ForegroundColor $color
            Write-Host ""
        }
    } catch {
        Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    }

    Start-Sleep -Milliseconds ([int]($PollSeconds * 1000))
}
