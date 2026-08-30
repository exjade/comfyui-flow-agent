@echo off
title Step 3 - RunPod Installation Command
echo.
echo RUN THIS COMMAND IN THE RUNPOD TERMINAL:
echo.
echo curl -fsSL https://raw.githubusercontent.com/exjade/comfyui-flow-agent/main/scripts/internal/install-runpod.sh ^| bash
echo.
powershell.exe -NoProfile -Command "Set-Clipboard -Value 'curl -fsSL https://raw.githubusercontent.com/exjade/comfyui-flow-agent/main/scripts/internal/install-runpod.sh | bash'"
echo The command was also copied to the clipboard.
echo Do not run it in this Windows window.
echo.
pause
