@echo off
title Safe Flow Agent Uninstaller
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall-flow-local.ps1"
pause
