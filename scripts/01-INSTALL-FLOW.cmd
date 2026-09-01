@echo off
title Step 1 - Install Flow Agent
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0internal\setup-flow-local.ps1" %*
pause
