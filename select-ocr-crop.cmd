@echo off
cd /d "%~dp0"
python ".\select-ocr-crop.py" --no-rotate-180
if errorlevel 1 goto done
echo.
echo Finished. Restarting OCR with the new crop...
call ".\stop-word-answer.cmd"
start "" ".\start-word-answer.cmd"
:done
pause
