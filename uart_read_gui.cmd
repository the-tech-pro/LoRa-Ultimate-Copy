@echo off
setlocal

set "PORT=%~1"
if "%PORT%"=="" set "PORT=COM5"
set "BAUD=%~2"
if "%BAUD%"=="" set "BAUD=115200"

start "eChook UART Console" powershell -NoExit -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0uart_read.ps1" -Port "%PORT%" -Baud "%BAUD%"
