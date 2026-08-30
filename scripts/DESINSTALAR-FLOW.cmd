@echo off
title Desinstalador seguro de Flow Agent
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall-flow-local.ps1"
pause
