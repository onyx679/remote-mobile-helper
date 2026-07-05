param()

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

$adb = Find-Adb
Write-Host "Using adb: $adb"
& $adb devices -l
