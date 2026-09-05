@echo off
title AutoGrade - Logs
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\autograde.ps1" -Command logs
echo.
pause
