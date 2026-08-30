#!/usr/bin/env bash
# This internal script is designed to be piped from the public bootstrap URL.
set -euo pipefail

COMFY_DIR="${1:-/workspace/ComfyUI}"
CUSTOM_NODES_DIR="$COMFY_DIR/custom_nodes"
NODE_DIR="$CUSTOM_NODES_DIR/comfyui-flow-agent"
REPOSITORY="https://github.com/exjade/comfyui-flow-agent.git"

for command in git python; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "Required command not found: $command" >&2
        exit 1
    fi
done

if [[ ! -d "$COMFY_DIR" ]]; then
    echo "ComfyUI was not found at: $COMFY_DIR" >&2
    exit 1
fi

mkdir -p "$CUSTOM_NODES_DIR"
if [[ -d "$NODE_DIR/.git" ]]; then
    if ! git -C "$NODE_DIR" diff --quiet \
        || ! git -C "$NODE_DIR" diff --cached --quiet \
        || [[ -n "$(git -C "$NODE_DIR" ls-files --others --exclude-standard)" ]]; then
        BACKUP_LABEL="comfyui-flow-agent installer backup $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo "Local changes detected. Saving a recoverable Git stash before updating."
        git -C "$NODE_DIR" stash push --include-untracked -m "$BACKUP_LABEL"
        echo "Backup created. List it later with: git -C $NODE_DIR stash list"
    fi
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

The custom node is installed at:
  /workspace/ComfyUI/custom_nodes/comfyui-flow-agent

Save both variables, then restart the Pod or the ComfyUI process.
MESSAGE
