param()

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
        throw "scrcpy.exe not found. Install scrcpy first: winget install --id Genymobile.scrcpy --exact"
    }

    return $scrcpy
}

$scrcpy = Find-Scrcpy
Write-Host "Starting USB remote control with: $scrcpy"
& $scrcpy --select-usb --window-title "Android Remote"
