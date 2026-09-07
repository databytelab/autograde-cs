@echo off
title AutoGrade dev - Start
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dev.ps1" -Command start
echo.
pause
