@echo off
title AutoGrade - Restore
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\autograde.ps1" -Command restore
echo.
pause
