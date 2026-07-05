param(
    [string]$Ip,
    [int]$Port = 5555
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
        throw "scrcpy.exe not found. Install scrcpy first: winget install --id Genymobile.scrcpy --exact"
    }

    return $scrcpy
}

$scrcpy = Find-Scrcpy

if ([string]::IsNullOrWhiteSpace($Ip)) {
    Write-Host "No IP provided. USB must be connected and authorized; scrcpy will enable TCP/IP and connect automatically."
    & $scrcpy --tcpip --window-title "Android Remote Wi-Fi"
} else {
    $target = "${Ip}:$Port"
    Write-Host "Connecting over Wi-Fi to $target"
    & $scrcpy --tcpip=$target --window-title "Android Remote Wi-Fi"
}
