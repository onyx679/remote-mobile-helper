$ErrorActionPreference = "SilentlyContinue"

$currentPid = $PID
Get-CimInstance Win32_Process |
    Where-Object {
        $_.ProcessId -ne $currentPid -and
        $_.CommandLine -match 'sync-camera-photos.ps1|start-photo-clipboard.ps1'
    } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Write-Host "Stopped photo clipboard watcher."
