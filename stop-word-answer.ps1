$ErrorActionPreference = "SilentlyContinue"

$currentPid = $PID
Get-CimInstance Win32_Process |
    Where-Object {
        $_.ProcessId -ne $currentPid -and
        $_.CommandLine -match 'watch_phone_answer_fast.py|watch-phone-answer-fast.ps1'
    } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Write-Host "Stopped word answer watcher."
