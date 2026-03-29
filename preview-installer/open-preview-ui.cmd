@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0open-preview-ui.ps1" %*
endlocal
