# ComfyUI Flow Agent

ComfyUI nodes for using Google Flow from a remote RunPod through a local Flow Agent instance and ngrok.

API contracts were verified against `kodelyx/flow-agent` revision `206285a47d15018765df5b16bce1d72198b1bb29` (Flow Agent 2.0.7).

## Included nodes

| Node | Purpose |
|---|---|
| `Flow / Nano Banana` | Generate images from text, ingredients, or references |
| `Flow / Omni Flash Video` | Generate or edit video from text, frames, or ingredients |
| `Flow / Upload Media` | Upload an image or video and return a reusable `media_id` |
| `Flow / Upsample Video` | Upsample generated video to 1080p or 4K |

## Confirmed capabilities

Images support `harbor_seal`, `narwhal`, and `gem_pix_2`; 1:1, 16:9, 9:16, 4:3, and 3:4; `count` 1-20; up to 10 references through `ref_media_ids`; and seeds from 0 to 4294967295. `gem_pix_2` may create extra internal candidates, but this client strictly limits ComfyUI output to the requested `count`.

Video supports text-to-video, start image, first/last frames, up to 10 ingredient images, and editing with one source video plus optional references. Durations are 4, 6, 8, or 10 seconds in landscape or portrait. Delivery supports native 720p and upsample to 1080p or account-dependent 4K. The current upstream schema accepts only one source video.

## Verified HTTP endpoints

- `GET /health`
- `GET /v1/models`
- `POST /v1/upload` with `{"image_base64":"data:...;base64,..."}`
- `POST /v1/images/generations`
- `POST /v1/videos/generations`
- `GET /v1/videos/generations/{job_id}`
- `POST /v1/videos/upsample`
- `GET /download/{filename}`

Generation and upsample requests reuse one `Idempotency-Key` across retries. Video jobs are polled until `succeeded` or `failed`. Uploads are not retried automatically because the upstream upload contract does not define idempotency.

## RunPod configuration

```env
FLOW_AGENT_BASE_URL=https://your-tunnel.ngrok-free.app
FLOW_AGENT_API_KEY=same-value-as-SERVER_API_KEY
```

Optional settings:

```env
FLOW_AGENT_CONNECT_TIMEOUT_SECONDS=10
FLOW_AGENT_MAX_DOWNLOAD_MB=64
FLOW_AGENT_MAX_VIDEO_DOWNLOAD_MB=2048
FLOW_AGENT_MAX_UPLOAD_MB=2048
```

Install on RunPod:

```bash
bash /workspace/ComfyUI/custom_nodes/comfyui-flow-agent/scripts/INSTALL-RUNPOD.sh
```

Restart ComfyUI and verify registration:

```bash
python - <<'PY'
import requests
for node in ("FlowNanoBanana", "FlowOmniFlashVideo", "FlowUploadMedia", "FlowVideoUpsample"):
    response = requests.get(f"http://127.0.0.1:8188/object_info/{node}", timeout=15)
    print(node, response.status_code, list(response.json()))
PY
```

Videos are saved to `ComfyUI/output/flow_agent`. Video nodes return an inline preview, native `VIDEO`, Video Helper Suite-compatible `VHS_FILENAMES`, paths, media IDs, source URLs, and job JSON. `source_video_path` must point to a RunPod file, not a Windows path.

## Guided Windows setup

On a new Windows computer, download or clone this repository and double-click:

```text
scripts\INSTALL-FLOW.cmd
```

The assistant installs missing tools, clones and prepares Flow Agent in an isolated environment, configures ngrok, guides extension loading, collects a Google Flow project URL, generates a secure API key, creates private local configuration and a desktop shortcut, and starts the services.

The user must still sign in to Google, load the unpacked extension, provide their own ngrok authtoken, and save the API key and public URL in RunPod.

Start Flow Agent through the desktop shortcut or:

```text
scripts\START-FLOW.cmd
```

The launcher starts or reuses ngrok, updates `PUBLIC_BASE_URL`, starts Flow Agent when needed, opens the configured project, and copies the public URL. Paste it into `FLOW_AGENT_BASE_URL` and restart ComfyUI.

Status and shutdown:

```powershell
.\scripts\status-flow-local.ps1
.\scripts\stop-flow-local.ps1
```

## Safe local uninstall

Double-click:

```text
scripts\UNINSTALL-FLOW.cmd
```

The exact word `UNINSTALL` is required. The Flow Agent copy is removed only when a private ownership marker proves that this installer created it. Manual or older installations without that marker are preserved.

The uninstaller never removes or modifies Windows Python, external environments, shared packages or caches, Google Chrome, browser data or extension settings, Google Flow projects, Git, uv, ngrok, shared ngrok credentials, ComfyUI, models, workflows, or ComfyUI-generated files. The unpacked extension entry remains in the browser and may be removed manually.

## Reference media

- `Flow / Nano Banana`: use `reference_image` and `reference_image_2` through `reference_image_10`. The combined maximum is 10.
- `Flow / Omni Flash Video` modes:
  - `start image to video` requires `start_image`.
  - `first + last frame` requires `start_image` and `end_image`.
  - `ingredients / reference images` requires at least one reference input.
  - `edit source video` requires `source_video_media_id` or `source_video_path`.
- Preserve returned `media_id` values to reuse media without uploading again.

## Tests

```bash
python -m pytest -q
```

Tests use simulated network responses and cover authentication, payload contracts, idempotency, polling, strict output limits, references, image conversion, and native video output.

## Security

- The Bearer token is sent only to the `FLOW_AGENT_BASE_URL` origin.
- `/v1/upload` is not automatically retried because upstream does not define upload idempotency.
- Upload and download limits are configurable.
- Never store `FLOW_AGENT_API_KEY` in a workflow or Git.
