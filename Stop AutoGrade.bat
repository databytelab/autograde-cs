@echo off
title AutoGrade - Stop
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\autograde.ps1" -Command stop
echo.
pause
