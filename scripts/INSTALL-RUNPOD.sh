#!/usr/bin/env bash
set -euo pipefail

COMFY_DIR="${1:-/workspace/ComfyUI}"
CUSTOM_NODES_DIR="$COMFY_DIR/custom_nodes"
NODE_DIR="$CUSTOM_NODES_DIR/comfyui-flow-agent"
REPOSITORY="https://github.com/exjade/comfyui-flow-agent.git"

if [[ ! -d "$COMFY_DIR" ]]; then
    echo "ComfyUI was not found at: $COMFY_DIR" >&2
    exit 1
fi

mkdir -p "$CUSTOM_NODES_DIR"
if [[ -d "$NODE_DIR/.git" ]]; then
    git -C "$NODE_DIR" pull --ff-only
elif [[ -e "$NODE_DIR" ]]; then
    echo "The path exists but is not a Git repository: $NODE_DIR" >&2
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

RUNPOD INSTALLATION COMPLETE

Configure these Pod environment variables:
  FLOW_AGENT_BASE_URL=https://your-url.ngrok-free.dev
  FLOW_AGENT_API_KEY={{ RUNPOD_SECRET_flow_agent_api_key }}

Then restart the Pod or the ComfyUI process.
MESSAGE
