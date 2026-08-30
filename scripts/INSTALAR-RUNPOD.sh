#!/usr/bin/env bash
set -euo pipefail

COMFY_DIR="${1:-/workspace/ComfyUI}"
CUSTOM_NODES_DIR="$COMFY_DIR/custom_nodes"
NODE_DIR="$CUSTOM_NODES_DIR/comfyui-flow-agent"
REPOSITORY="https://github.com/exjade/comfyui-flow-agent.git"

if [[ ! -d "$COMFY_DIR" ]]; then
    echo "No se encontró ComfyUI en: $COMFY_DIR" >&2
    exit 1
fi

mkdir -p "$CUSTOM_NODES_DIR"
if [[ -d "$NODE_DIR/.git" ]]; then
    git -C "$NODE_DIR" pull --ff-only
elif [[ -e "$NODE_DIR" ]]; then
    echo "La ruta existe pero no es un repositorio Git: $NODE_DIR" >&2
    exit 1
else
    git clone "$REPOSITORY" "$NODE_DIR"
fi

COMFY_PID="$(pgrep -f 'python.*main.py' | head -n 1 || true)"
if [[ -n "$COMFY_PID" && -e "/proc/$COMFY_PID/exe" ]]; then
    COMFY_PY="$(readlink -f "/proc/$COMFY_PID/exe")"
else
    COMFY_PY="$(command -v python)"
fi

"$COMFY_PY" -m pip install -r "$NODE_DIR/requirements.txt"

cat <<'MESSAGE'

INSTALACIÓN DE RUNPOD TERMINADA

Configura en el Pod:
  FLOW_AGENT_BASE_URL=https://tu-url.ngrok-free.dev
  FLOW_AGENT_API_KEY={{ RUNPOD_SECRET_flow_agent_api_key }}

Después reinicia el Pod o el proceso de ComfyUI.
MESSAGE
