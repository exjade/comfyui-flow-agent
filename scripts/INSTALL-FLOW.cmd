@echo off
title Flow Agent Installer for ComfyUI
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-flow-local.ps1"
pause
