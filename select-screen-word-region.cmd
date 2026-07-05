@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "& {
  $py = Get-Command pythonw -ErrorAction SilentlyContinue
  if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue }
  if (-not $py) { throw 'python not found' }
  $script = Join-Path $PSScriptRoot 'select-screen-word-region.py'
  Start-Process -FilePath $py.Source -ArgumentList @($script) -WindowStyle Normal | Out-Null
}"
