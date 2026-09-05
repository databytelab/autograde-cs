@echo off
title AutoGrade - Update
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\autograde.ps1" -Command update
echo.
pause
