@echo off
title Stop Flow Agent
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0internal\stop-flow-local.ps1"
pause
