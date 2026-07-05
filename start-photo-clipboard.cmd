@echo off
cd /d "%~dp0"
powershell.exe -Sta -NoExit -ExecutionPolicy Bypass -File ".\start-photo-clipboard.ps1"
