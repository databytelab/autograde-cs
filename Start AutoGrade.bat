@echo off
title AutoGrade - Start
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\autograde.ps1" -Command start
echo.
pause
