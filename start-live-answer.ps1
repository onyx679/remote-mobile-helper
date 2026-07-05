param(
    [string]$Serial = "192.168.0.100:41965",
    [double]$SyncPollSeconds = 0.2,
    [double]$AnswerPollSeconds = 0.2,
    [string]$Crop = "0.30,0.42,0.75,0.60"
)

$ErrorActionPreference = "Stop"

$cwd = (Get-Location).Path

Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -like "*sync-camera-photos.ps1*" -or
        $_.CommandLine -like "*watch-answer-from-photos.ps1*" -or
        $_.CommandLine -like "*show-answer-window.ps1*"
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
    }

Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    "Set-Location '$cwd'; .\sync-camera-photos.ps1 -Serial '$Serial' -PollSeconds $SyncPollSeconds"
)

Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    "Set-Location '$cwd'; .\watch-answer-from-photos.ps1 -CopyAnswer -PollSeconds $AnswerPollSeconds -Crop '$Crop'"
)

Start-Process powershell.exe -ArgumentList @(
    "-STA",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    "Set-Location '$cwd'; .\show-answer-window.ps1"
)

Write-Host "Live answer pipeline started."
Write-Host "Sync: camera-inbox"
Write-Host "Answer files: latest-answer.txt, latest-result.json"
