@echo off
cd /d "%~dp0"
call ".\stop-word-answer.cmd"
call ".\start-word-answer.cmd"
