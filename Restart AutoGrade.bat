@echo off
title AutoGrade - Restart
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\autograde.ps1" -Command restart
echo.
pause
