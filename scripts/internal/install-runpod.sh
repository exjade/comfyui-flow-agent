#!/usr/bin/env bash
# This internal script is designed to be piped from the public bootstrap URL.
set -euo pipefail

REPOSITORY="https://github.com/exjade/comfyui-flow-agent.git"

if ! command -v git >/dev/null 2>&1; then
    echo "Required command not found: git" >&2
    exit 1
fi

is_comfy_root() {
    local candidate="$1"
    [[ -f "$candidate/main.py" && -f "$candidate/execution.py" && -f "$candidate/folder_paths.py" ]]
}

add_comfy_candidate() {
    local candidate="$1"
    local existing
    candidate="$(readlink -f "$candidate" 2>/dev/null || true)"
    [[ -n "$candidate" ]] || return 0
    is_comfy_root "$candidate" || return 0
    for existing in "${COMFY_CANDIDATES[@]:-}"; do
        [[ "$existing" == "$candidate" ]] && return 0
    done
    COMFY_CANDIDATES+=("$candidate")
}

COMFY_DIR="${1:-${COMFYUI_PATH:-}}"
COMFY_CANDIDATES=()

if [[ -n "$COMFY_DIR" ]]; then
    COMFY_DIR="$(readlink -f "$COMFY_DIR" 2>/dev/null || printf '%s' "$COMFY_DIR")"
    if ! is_comfy_root "$COMFY_DIR"; then
        echo "ComfyUI was not found at: $COMFY_DIR" >&2
        echo "The selected folder must contain main.py, execution.py, and folder_paths.py." >&2
        exit 1
    fi
else
    while IFS= read -r pid; do
        [[ -n "$pid" && -d "/proc/$pid" ]] || continue
        add_comfy_candidate "$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
    done < <(pgrep -f 'python[^ ]* .*main\.py|python[^ ]* main\.py' 2>/dev/null || true)

    add_comfy_candidate "/workspace/ComfyUI"
    add_comfy_candidate "/workspace/runpod-slim/ComfyUI"
    while IFS= read -r -d '' main_file; do
        add_comfy_candidate "$(dirname "$main_file")"
    done < <(find /workspace -maxdepth 6 -type f -name main.py -print0 2>/dev/null || true)

    if [[ ${#COMFY_CANDIDATES[@]} -eq 0 ]]; then
        echo "ComfyUI was not found automatically under /workspace." >&2
        echo "Re-run with the folder containing main.py:" >&2
        echo "  curl -fsSL <installer-url> | bash -s -- /path/to/ComfyUI" >&2
        exit 1
    fi
    if [[ ${#COMFY_CANDIDATES[@]} -gt 1 ]]; then
        echo "Multiple ComfyUI installations were found:" >&2
        printf '  %s\n' "${COMFY_CANDIDATES[@]}" >&2
        echo "Re-run and select one explicitly:" >&2
        echo "  curl -fsSL <installer-url> | bash -s -- /path/to/ComfyUI" >&2
        exit 1
    fi
    COMFY_DIR="${COMFY_CANDIDATES[0]}"
fi

echo "ComfyUI detected at: $COMFY_DIR"

CUSTOM_NODES_DIR="$COMFY_DIR/custom_nodes"
NODE_DIR="$CUSTOM_NODES_DIR/comfyui-flow-agent"

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

COMFY_PY=""
while IFS= read -r pid; do
    [[ -n "$pid" && -e "/proc/$pid/exe" ]] || continue
    process_cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
    if [[ "$process_cwd" == "$COMFY_DIR" ]]; then
        COMFY_PY="$(readlink -f "/proc/$pid/exe")"
        break
    fi
done < <(pgrep -f 'python[^ ]* .*main\.py|python[^ ]* main\.py' 2>/dev/null || true)

if [[ -z "$COMFY_PY" ]]; then
    for python_candidate in \
        "$COMFY_DIR/.venv/bin/python" \
        "$COMFY_DIR/venv/bin/python" \
        "$COMFY_DIR"/.venv*/bin/python; do
        if [[ -x "$python_candidate" ]]; then
            COMFY_PY="$(readlink -f "$python_candidate")"
            break
        fi
    done
fi
if [[ -z "$COMFY_PY" ]]; then
    COMFY_PY="$(command -v python 2>/dev/null || command -v python3 2>/dev/null || true)"
fi
if [[ -z "$COMFY_PY" ]]; then
    echo "Python was not found in ComfyUI or on PATH." >&2
    echo "On a minimal Ubuntu Pod, install it with:" >&2
    echo "  apt update && apt install -y python3 python3-pip" >&2
    exit 1
fi

echo "Using ComfyUI Python: $COMFY_PY"
"$COMFY_PY" -m pip install -r "$NODE_DIR/requirements.txt"

cat <<'MESSAGE'

RUNPOD INSTALLATION COMPLETE

Configure these Pod environment variables:
  FLOW_AGENT_BASE_URL=https://your-url.ngrok-free.dev
  FLOW_AGENT_API_KEY={{ RUNPOD_SECRET_flow_agent_api_key }}

The custom node is installed at:
MESSAGE
printf '  %s\n\n' "$NODE_DIR"

if [[ -n "${FLOW_AGENT_BASE_URL:-}" ]]; then
    echo "FLOW_AGENT_BASE_URL is available to this installer."
else
    echo "WARNING: FLOW_AGENT_BASE_URL is not available in this Pod environment."
fi
if [[ -z "${FLOW_AGENT_API_KEY:-}" ]]; then
    echo "WARNING: FLOW_AGENT_API_KEY is not available in this Pod environment."
elif [[ "$FLOW_AGENT_API_KEY" == '{{'*'}}' ]]; then
    echo "WARNING: FLOW_AGENT_API_KEY contains an unresolved secret reference."
else
    echo "FLOW_AGENT_API_KEY is available (value hidden, ${#FLOW_AGENT_API_KEY} characters)."
fi

echo "Save both variables, then restart the Pod or the ComfyUI process."
