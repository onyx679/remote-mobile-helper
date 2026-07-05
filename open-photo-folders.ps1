param()

$ErrorActionPreference = "Stop"

$inbox = Join-Path (Get-Location) "camera-inbox"
$outbox = Join-Path (Get-Location) "ai-outbox"

New-Item -ItemType Directory -Force -Path $inbox | Out-Null
New-Item -ItemType Directory -Force -Path $outbox | Out-Null

Start-Process explorer.exe $inbox
Start-Process explorer.exe $outbox
