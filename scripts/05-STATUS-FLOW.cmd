@echo off
title Flow Agent Status
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0internal\status-flow-local.ps1"
pause
