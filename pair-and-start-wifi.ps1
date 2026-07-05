param(
    [Parameter(Mandatory = $true)]
    [string]$PairAddress,

    [Parameter(Mandatory = $true)]
    [string]$PairCode,

    [Parameter(Mandatory = $true)]
    [string]$ConnectAddress
)

$ErrorActionPreference = "Stop"

function Find-ScrcpyDir {
    $cmd = Get-Command scrcpy -ErrorAction SilentlyContinue
    if ($cmd) {
        return Split-Path -Parent $cmd.Source
    }

    $wingetRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    $scrcpy = Get-ChildItem -Path $wingetRoot -Recurse -Filter scrcpy.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -like "*Genymobile.scrcpy*" } |
        Select-Object -First 1 -ExpandProperty FullName

    if (-not $scrcpy) {
        throw "scrcpy.exe not found. Install scrcpy first: winget install --id Genymobile.scrcpy --exact"
    }

    return Split-Path -Parent $scrcpy
}

$scrcpyDir = Find-ScrcpyDir
$adb = Join-Path $scrcpyDir "adb.exe"
$scrcpy = Join-Path $scrcpyDir "scrcpy.exe"

Write-Host "Using adb: $adb"
Write-Host "Pairing with $PairAddress"
& $adb pair $PairAddress $PairCode

Write-Host "Connecting to $ConnectAddress"
& $adb connect $ConnectAddress

Write-Host "Starting remote control for $ConnectAddress"
& $scrcpy --serial $ConnectAddress --window-title "Android Remote Wi-Fi"
