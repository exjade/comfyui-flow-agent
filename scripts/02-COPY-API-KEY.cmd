@echo off
title Step 2 - Copy Flow Agent API Key
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0internal\copy-flow-api-key.ps1"
pause
