param(
    [string]$OutputDirectory = (Join-Path (Get-Location) "portable-release"),
    [string]$PackageName = "remote-mobile-helper",
    [switch]$OpenFolder
)

$ErrorActionPreference = "Stop"

$coreFiles = @(
    "README.md",
    "requirements.txt",
    "当前工作流程.md",
    "迁移清单.md",
    "check-devices.ps1",
    "start-usb.ps1",
    "start-wifi.ps1",
    "pair-and-start-wifi.ps1",
    "start-scrcpy-small.ps1",
    "status.cmd",
    "start-word-answer.cmd",
    "stop-word-answer.cmd",
    "restart-word-answer.cmd",
    "watch-phone-answer-fast.ps1",
    "watch-phone-answer.ps1",
    "start-live-answer.ps1",
    "show-answer-window.ps1",
    "watch_phone_answer_fast.py",
    "watch-answer-from-photos.ps1",
    "answer-photo.ps1",
    "judge-word.ps1",
    "judge-current-screen-word.ps1",
    "judge_english_word.py",
    "det_word_bank.py",
    "ocr_answer_photo.py",
    "select-ocr-crop.cmd",
    "select-ocr-crop.py",
    "show-ocr-crop.cmd",
    "show-ocr-crop.py",
    "select-screen-word-region.cmd",
    "show-screen-word-region.cmd",
    "start-photo-clipboard.cmd",
    "stop-photo-clipboard.cmd",
    "start-photo-clipboard.ps1",
    "stop-photo-clipboard.ps1",
    "sync-camera-photos.ps1",
    "copy-photo-to-clipboard.ps1",
    "queue-photo-for-ai.ps1",
    "open-photo-folders.ps1",
    "tests\\test_capture_source.py",
    "setup-new-pc.ps1"
)

$optionalFiles = @(
    "transfer-test-IMG_20260621_204340.jpg",
    "validate_det_word_bank.py",
    ".gitignore",
    "scrcpy-stream-test.mkv",
    "watch-answer.log",
    "scrcpy-small.out.log",
    "scrcpy-small.err.log"
)

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$packageRoot = Join-Path $OutputDirectory $PackageName
$artifactRoot = Join-Path $packageRoot "artifact-$stamp"

if (Test-Path $artifactRoot) {
    Remove-Item -LiteralPath $artifactRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null

$missing = @()
foreach ($file in $coreFiles) {
    if (Test-Path $file) {
        $destination = Join-Path $artifactRoot $file
        $destDir = Split-Path $destination
        if (-not (Test-Path $destDir)) {
            New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        }
        Copy-Item -LiteralPath $file -Destination $destination -Force
    } else {
        $missing += $file
    }
}

foreach ($file in $optionalFiles) {
    if (Test-Path $file) {
        $destination = Join-Path $artifactRoot $file
        $destDir = Split-Path $destination
        if (-not (Test-Path $destDir)) {
            New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        }
        Copy-Item -LiteralPath $file -Destination $destination -Force
    }
}

$requiredDirs = @("camera-inbox", "camera-rotated", "ai-outbox")
foreach ($dir in $requiredDirs) {
    $dirPath = Join-Path $artifactRoot $dir
    if (-not (Test-Path $dirPath)) {
        New-Item -ItemType Directory -Path $dirPath | Out-Null
    }
}

$missingNotice = if ($missing.Count -gt 0) {
    @"
Missing files:
$([string]::Join("`n", $missing))
"@
} else {
    "All required files found."
}

$readme = @"
Portable package generated: $stamp

1. Copy this folder to another PC.
2. Install dependencies:
   - scrcpy (includes adb)
   - Tesseract OCR
   - Python 3.10+
3. Run:
   pip install -r requirements.txt
4. Pair/connect phone then update serial in:
   - start-scrcpy-small.ps1
   - watch-phone-answer-fast.ps1
   - start-photo-clipboard.ps1
5. Startup:
   .\start-scrcpy-small.ps1 -Serial <serial>
   start-word-answer.cmd
   start-photo-clipboard.cmd
6. Check status:
   status.cmd

$missingNotice
"@
$readmePath = Join-Path $artifactRoot "portable-readme.txt"
Set-Content -Path $readmePath -Value $readme -Encoding UTF8

$zipPath = Join-Path $OutputDirectory "$PackageName-$stamp.zip"
if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -Path (Join-Path $artifactRoot "*") -DestinationPath $zipPath -Force

Write-Host "Package ready:"
Write-Host "  Folder: $artifactRoot"
Write-Host "  ZIP:    $zipPath"

if ($OpenFolder) {
    Invoke-Item -Path $artifactRoot
}
