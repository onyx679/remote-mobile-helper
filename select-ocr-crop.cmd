@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "& {
  $py = Get-Command pythonw -ErrorAction SilentlyContinue
  if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue }
  if (-not $py) { throw 'python not found' }

  $script = Join-Path $PSScriptRoot 'select-ocr-crop.py'
  $proc = Start-Process -FilePath $py.Source -ArgumentList @($script, '--no-rotate-180') -PassThru -WindowStyle Normal
  $proc.WaitForExit()
  if ($proc.ExitCode -eq 0) {
    & (Join-Path $PSScriptRoot 'stop-word-answer.cmd')
    Start-Process -FilePath (Join-Path $PSScriptRoot 'start-word-answer.cmd') -WindowStyle Normal
  }
}"
