@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-Weekly.ps1" %*
pause
