@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
"$p = Get-CimInstance Win32_Process; ^
Write-Host ''; ^
Write-Host '=== STATUS ==='; ^
if ($p | Where-Object { $_.CommandLine -match 'watch_phone_answer_fast.py|watch-phone-answer-fast.ps1' }) { Write-Host 'Word answer: ON' } else { Write-Host 'Word answer: OFF' }; ^
if ($p | Where-Object { $_.CommandLine -match 'sync-camera-photos.ps1|start-photo-clipboard.ps1' }) { Write-Host 'Photo clipboard: ON' } else { Write-Host 'Photo clipboard: OFF' }; ^
if ($p | Where-Object { $_.CommandLine -match 'scrcpy.exe' }) { Write-Host 'scrcpy: ON' } else { Write-Host 'scrcpy: OFF' }; ^
Write-Host ''; ^
pause"
