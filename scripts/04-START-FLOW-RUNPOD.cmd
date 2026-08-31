@echo off
title Step 4 - Start Flow Agent for RunPod
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0internal\start-flow-local.ps1" -Mode RunPod
pause
