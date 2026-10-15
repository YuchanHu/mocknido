@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0runtime\python.exe" (
  echo Runtime missing. Extract the entire portable ZIP before starting.
  pause
  exit /b 1
)
"%~dp0runtime\python.exe" -X utf8 "%~dp0launch.py"
if errorlevel 1 pause
