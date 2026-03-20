@echo off
setlocal

set "PORT=%~1"
if "%PORT%"=="" set "PORT=COM5"
set "BAUD=%~2"
if "%BAUD%"=="" set "BAUD=115200"

powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -STA -File "%~dp0uart_read.ps1" -Port "%PORT%" -Baud "%BAUD%"
