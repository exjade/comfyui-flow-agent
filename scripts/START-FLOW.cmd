@echo off
title Start Flow Agent
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-flow-local.ps1"
pause
