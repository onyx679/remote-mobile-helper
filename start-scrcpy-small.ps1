param(
    [string]$Serial = "adb-2252475e-baGT88._adb-tls-connect._tcp",
    [int]$X = 0,
    [int]$Y = 0,
    [int]$Width = 560,
    [int]$Height = 1000,
    [string]$VideoBitRate = "1M",
    [int]$MaxFps = 15,
    [ValidateSet(0, 90, 180, 270)]
    [int]$DisplayOrientation = 0
)

$ErrorActionPreference = "Stop"

function Find-Scrcpy {
    $cmd = Get-Command scrcpy -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $wingetRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    $scrcpy = Get-ChildItem -Path $wingetRoot -Recurse -Filter scrcpy.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -like "*Genymobile.scrcpy*" } |
        Select-Object -First 1 -ExpandProperty FullName

    if (-not $scrcpy) {
        throw "scrcpy.exe not found."
    }

    return $scrcpy
}

Get-Process scrcpy -ErrorAction SilentlyContinue | Stop-Process -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800

$scrcpy = Find-Scrcpy
Start-Process -FilePath $scrcpy -ArgumentList @(
    "--serial", $Serial,
    "--window-title=Android-Remote-WiFi",
    "--window-x=$X",
    "--window-y=$Y",
    "--window-width=$Width",
    "--window-height=$Height",
    "--video-bit-rate=$VideoBitRate",
    "--max-fps=$MaxFps",
    "--display-orientation=$DisplayOrientation",
    "--always-on-top",
    "--no-audio",
    "--render-driver=software",
    "--pause-on-exit=if-error"
)

Write-Host "Started scrcpy small window for $Serial"
