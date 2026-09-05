@echo off
title AutoGrade - Backup
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\autograde.ps1" -Command backup
echo.
pause
