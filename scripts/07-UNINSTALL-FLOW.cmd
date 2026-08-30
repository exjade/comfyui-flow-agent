@echo off
title Step 7 - Safe Flow Agent Uninstaller
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0internal\uninstall-flow-local.ps1"
pause
