@echo off
cd /d "%~dp0"
powershell.exe -NoExit -ExecutionPolicy Bypass -File ".\watch-phone-answer-fast.ps1"
