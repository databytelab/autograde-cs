@echo off
title AutoGrade dev - Stop
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dev.ps1" -Command stop
echo.
pause
