@echo off
title Step 4.1 - Start Flow Agent for Local ComfyUI
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0internal\start-flow-local.ps1" -Mode Local
pause
