# ComfyUI Flow Agent — Version 1

ComfyUI nodes for using Google Flow from either ComfyUI on the same Windows PC or a remote RunPod through a local Flow Agent instance.

**Guía para usuarios en español:** [ComfyUI local y RunPod](docs/GUIA-USUARIO-LOCAL-Y-RUNPOD.md)

API contracts were verified against `kodelyx/flow-agent` revision `206285a47d15018765df5b16bce1d72198b1bb29` (Flow Agent 2.0.7).

## Included nodes

| Node | Purpose |
|---|---|
| `Flow / Nano Banana` | Generate images from text, ingredients, or references |
| `Flow / Custom Character Creator` | Generate a labeled character dataset with inline previews |
| `Flow / 1. Choose Character Shot` | Browse saved Character Creator datasets and select an existing image |
| `Flow / 2. Regenerate Chosen Shot` | Step 2: create a new version using that shot's saved prompt and references |
| `Flow / Omni Flash Video` | Generate or edit video from text, frames, image/video ingredients, or a source video |
| `Flow / Upload Media` | Upload an image or video and return a reusable `media_id` |
| `Flow / Video Library` | Visually browse tracked videos and reuse their `media_id` |

## Confirmed capabilities

Images support `harbor_seal`, `narwhal`, and `gem_pix_2`; 1:1, 16:9, 9:16, 4:3, and 3:4; `count` 1-20; and up to 10 references through `ref_media_ids`. Nano Banana and Character Creator use the stable seed `43`. `gem_pix_2` may create extra internal candidates, but this client strictly limits ComfyUI output to the requested `count`.

Video supports text-to-video, start image, first/last frames, mixed image/video ingredients, and editing with one source video plus optional visual references. Ingredient inputs accept up to 10 combined media IDs. Durations are 4, 6, 8, or 10 seconds in landscape or portrait, with 1-4 outputs per generation request and one output per video-edit request. Base generation currently uses 720p; selecting 1080p generates at 720p and then runs Flow's free upsample. Google Flow's newer 360p option is temporarily hidden because its internal generation schema has not yet been captured; sending the upsampler-only `resolution` field to a generation endpoint is rejected. The current upstream schema accepts only one source video.

## Version 1 end-user workflow

The seven registered nodes have separate responsibilities. Library and selector nodes are read-only: they do not spend credits or regenerate their upstream source.

| Node | What the user does | What contacts Google Flow |
|---|---|---|
| `Flow / Upload Media` | Choose image or video, then connect the matching native socket or provide one local path | One upload when the content is not already cached |
| `Flow / Nano Banana` | Write an image prompt and optionally connect up to ten reference images | One image-generation request using seed `43` and the requested `count` |
| `Flow / Custom Character Creator` | Provide one identity, optional wardrobe references, and choose a shot preset | One image-generation request per requested character shot |
| `Flow / 1. Choose Character Shot` | Browse already saved character datasets and select the exact original image | Nothing; it reads local manifests and previews only |
| `Flow / 2. Regenerate Chosen Shot` | Create one new alternative from the selected shot's saved prompt and references | Exactly one new image generation, plus retries only after failure |
| `Flow / Omni Flash Video` | Generate or edit video using the mode selected in the node | One video job per request; 1080p adds Flow's internal upscale pass |
| `Flow / Video Library` | Browse videos already tracked by Flow Agent and output the selected `media_id` | Nothing; it reads the local video history only |

### Image editing

To edit an existing image, connect the chosen IMAGE output to `Flow / Nano Banana.reference_image` and write the desired change in Nano Banana's prompt. Nano Banana performs the new edit/generation; the character selector itself never modifies an image. Seed is always `43` and control-after-generation is forced to `fixed`, including workflows saved with older values.

### Character selection and regeneration

Character Creator is the batch generator. After it finishes, its images and `manifest.json` remain in the local character library. `1. Choose Character Shot` selects one existing result without queuing Character Creator. `2. Regenerate Chosen Shot` then creates one alternative from the stored specification. The old image and its `media_id` remain unchanged.

### Video generation and editing

Choose the mode before connecting inputs: text-to-video needs only a prompt; start-image mode uses `start_image`; first/last-frame mode uses both frame inputs; ingredients mode accepts reference images, native ComfyUI `VIDEO` connections, video media IDs, or reachable video paths. `edit source video` accepts exactly one source and disables every reference input. `video to video` accepts exactly one source plus optional image references; additional video references remain exclusive to ingredients mode. Omni Flash always sends seed `43`. Its separate mode UI hides irrelevant widgets, dims inactive sockets, explains the active limits in English, and forces edit count to one. The backend rejects incompatible retained inputs before a paid request is sent.

`Flow / Upload Media` has an `image`/`video` selector. It enables the matching native socket and disables the other one; connect that socket or provide one `media_path`, never both. Native `VIDEO` values are exported through a small independent adapter module, so the upload and Omni nodes do not duplicate ComfyUI video handling.

Google Flow rejects source-video speech editing with `SPEECH_EDIT_BLOCKED`. For native `VIDEO` connections and `source_video_path`, the adapter therefore creates a temporary video-only copy with FFmpeg, uploads that silent copy, and removes it afterward; the user's original file is never modified. An already uploaded `source_video_media_id` cannot be sanitized locally, so connect the corresponding Video Library `video` output or load the original file when speech is present.

For `edit source video` and `video to video`, the source clip determines the effective edit window (capped at Flow's supported 10 seconds). The duration selector is hidden in those modes and the backend reads native `VIDEO.get_duration()` before submitting. Because live Flow pricing can differ from the static generation table, the preflight label deliberately reports that edit cost depends on source length instead of presenting a potentially wrong fixed amount.

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

Add exactly these two rows in the RunPod environment-variable editor:

| Key | Value |
|---|---|
| `FLOW_AGENT_BASE_URL` | The current HTTPS URL printed by `04-START-FLOW-RUNPOD.cmd` |
| `FLOW_AGENT_API_KEY` | `{{ RUNPOD_SECRET_flow_agent_api_key }}` |

First create the private RunPod secret `flow_agent_api_key` and paste the actual API key generated by the Windows installer as its value. Then use `{{ RUNPOD_SECRET_flow_agent_api_key }}` as the `FLOW_AGENT_API_KEY` environment-variable value. This expression is only a secure reference: RunPod replaces it with the stored private value when the Pod starts. Do not save the reference expression as the secret value itself.

An HTTP 401 response saying `Invalid or missing API key` means the Pod reached Flow Agent but the ComfyUI process received an empty, unresolved, or different key. Confirm the secret contains the actual key, keep only its reference in `FLOW_AGENT_API_KEY`, and restart the Pod so ComfyUI inherits the corrected environment. The RunPod installer reports whether both variables are visible without printing the secret value.

To recover the actual key later without displaying it, double-click `scripts\02-COPY-API-KEY.cmd`. It reads `SERVER_API_KEY` from the configured local Flow Agent `.env` and copies the value to the clipboard.

Optional settings:

```env
FLOW_AGENT_CONNECT_TIMEOUT_SECONDS=10
FLOW_AGENT_MAX_DOWNLOAD_MB=64
FLOW_AGENT_MAX_VIDEO_DOWNLOAD_MB=2048
FLOW_AGENT_MAX_UPLOAD_MB=2048
```

Install on RunPod:

```bash
curl -fsSL https://raw.githubusercontent.com/exjade/comfyui-flow-agent/main/scripts/internal/install-runpod.sh | bash
```

This command works before the repository exists on RunPod. It discovers a valid ComfyUI folder under `/workspace` (including layouts such as `/workspace/runpod-slim/ComfyUI`), clones or updates the project in that installation's `custom_nodes` folder, selects ComfyUI's own Python environment when available, and installs the required packages. Save the two environment variables and restart the Pod or ComfyUI afterward.

If more than one ComfyUI installation exists, select one explicitly:

```bash
curl -fsSL https://raw.githubusercontent.com/exjade/comfyui-flow-agent/main/scripts/internal/install-runpod.sh | bash -s -- /path/to/ComfyUI
```

If an older RunPod installation contains local modifications, the installer preserves them in a recoverable Git stash before pulling. It never discards them. The installer prints the actual custom-node path; inspect its backups with `git -C /actual/ComfyUI/custom_nodes/comfyui-flow-agent stash list`.

Restart ComfyUI and verify registration:

```bash
python - <<'PY'
import requests
for node in (
    "FlowNanoBanana",
    "FlowCharacterCreator",
    "FlowCharacterShotSelector",
    "FlowGenerateCharacterShot",
    "FlowOmniFlashVideo",
    "FlowUploadMedia",
    "FlowVideoLibrary",
):
    response = requests.get(f"http://127.0.0.1:8188/object_info/{node}", timeout=15)
    print(node, response.status_code, list(response.json()))
PY
```

Videos are saved to `ComfyUI/output/flow_agent`. Video nodes return an inline preview, native `VIDEO`, Video Helper Suite-compatible `VHS_FILENAMES`, paths, media IDs, source URLs, and job JSON. `source_video_path` must point to a RunPod file, not a Windows path.

`Flow / Video Library` provides an end-user browser for videos tracked by Flow Agent. Click **Refresh videos**, filter generated/uploaded/upscaled items, preview one video, and select it. Connect its plain `media_id` output directly to `Flow / Omni Flash Video.source_video_media_id`; users do not need to inspect JSON or copy UUIDs. `original_prompt` is read-only historical metadata; type the new editing instruction in Omni Flash Video's prompt field. The library is an independent module and does not alter generation behavior in Nano Banana, Character Creator, Omni Flash, or Upload Media.

The selected video mode determines which image sockets are used. The node rejects connected inputs that the selected mode would ignore, before contacting the paid generation endpoint. For identity work, connect individual character shots (or the `images` batch from Character Creator) to `reference_images` and select `ingredients / reference images`. A flattened contact sheet is treated as one composite picture, not as six independent character references. `start image to video` animates one specific first frame and should receive a single shot.

The node displays the estimated Flow cost before generation and updates it when duration, count, or resolution changes. The verified 720p Omni 1.1 Flash cost per clip is `7/10/12/15` credits for `4/6/8/10` seconds respectively; the total is multiplied by count. Selecting 1080p uses the 720p generation cost and then runs Flow's internal free upsample pass. Flow's cheaper 360p tier remains documented upstream but is intentionally unavailable here until its internal request field is verified. There is no standalone upscale node because Google Flow's historical-video upsample contract is not stable enough for an end-user workflow.

## Character datasets

`Flow / Custom Character Creator` reproduces the community Character Persona workflow with 22 stable shots: eight face angles, six expressions, and eight body poses. It accepts one identity image plus optional `top_reference`, `bottom_reference`, `accessories_reference`, and `shoes_reference` inputs. Each wardrobe input may be a small IMAGE batch, with a hard combined limit of 10 references. The node sends Flow's real ordered `ref_media_ids` list and adds explicit role assignments to each shot prompt; the upstream API has no separate top/bottom/shoes fields.

Reference uploads are content-addressed. Re-running with identical image bytes and the same Flow project reuses the stored `media_id` instead of creating another Flow upload or random local `upload_*` file. A changed image or project creates a new upload. The compatibility patch installed by the Windows setup also preserves old media-ID aliases when Flow refreshes an ID, preventing the first-shot-only failure in long character batches.

`aspect_ratio` supports 1:1, 16:9, 9:16, 4:3, and 3:4. The current Flow Agent image contract uses the supplied `size` only to select one of those aspect-ratio enums; it does not expose native image resolution or image upsampling. Values such as `1792x1024` therefore do not prove a 1792-pixel Flow result. Use a separate ComfyUI upscale workflow when pixels above Flow's native output are required.

Flow's own `@` picker can select a different project and then choose a character such as `stacy`, so cross-project character reuse is available in the Google UI. Plain text such as `@stacy` is not yet an equivalent character reference in this integration: the UI chip contains project/character metadata, while the repository currently sends only prompt text plus image `media_id` values. Add the character's source images through the reference inputs until a captured and tested character-entity request contract is implemented.

Every successful image is saved immediately under `ComfyUI/output/flow_agent/characters/<dataset_id>`. The node shows a contact sheet plus every individual result in ComfyUI, and returns an IMAGE batch and a JSON manifest. Each manifest entry has a stable `shot_id`, the generated Flow `media_id`, its full prompt, saved path, status, and batch index. Partial results remain available when `continue_on_error` is enabled.

Character Creator saves every completed dataset under `ComfyUI/output/flow_agent/characters/<dataset_id>/`, including a persistent `manifest.json`. Once generation finishes, Creator can be bypassed or removed from the active workflow.

To create a new version of one saved result without rebuilding the complete dataset:

1. Add `Flow / 1. Choose Character Shot`; it does not connect to Character Creator.
2. Click **Refresh datasets**, choose a saved dataset, and choose the desired shot in its visual preview.
3. Connect `shot_spec_json` to `Flow / 2. Regenerate Chosen Shot`.
4. Keep `reuse_manifest_references=true` to reuse the original identity and wardrobe references. The original `reference_image` connection is optional for newly saved datasets; connect it only for an older manifest without reusable IDs or when replacing references.

The library node only reads local manifests and image files; it never queues Character Creator or contacts Google Flow. The second node submits one new image generation with the saved shot prompt; it does not alter the previous image or send its `media_id` as an image-edit input.

Character Creator uses a stable seed of `43` and allows ComfyUI to cache its completed dataset. Running the selector or the single-shot regenerator therefore does not rebuild the upstream dataset. To intentionally create a new complete dataset, change a real Creator input (for example its reference image, preset, shot count, subject, wardrobe, or dataset name) and queue it again.

`shot_id` identifies the logical pose and remains stable. `media_id` identifies one concrete Google Flow result and changes after regeneration. Retries reuse one idempotency key per shot so a transient retry does not intentionally create duplicate paid generations.

## Guided Windows setup

The `scripts` folder contains only numbered user-facing launchers:

| Step | Launcher | Action |
|---:|---|---|
| 1 | `01-INSTALL-FLOW.cmd` | Install and configure the local Flow Agent stack |
| 2 | `02-COPY-API-KEY.cmd` | Copy the real API key without displaying it |
| 3 | `03-SHOW-RUNPOD-INSTALL.cmd` | Show and copy the command to run in the RunPod terminal |
| 3.1 | `03.1-GITHUB-INSTALL-OR-UPDATE-CUSTOM-NODE-LOCAL.cmd` | Install or update this custom node from GitHub in ComfyUI Desktop |
| 4 | `04-START-FLOW-RUNPOD.cmd` | Start Flow Agent with ngrok for a remote RunPod |
| 4.1 | `04.1-START-FLOW-LOCAL.cmd` | Start Flow Agent directly for ComfyUI on this Windows PC |
| 5 | `05-STATUS-FLOW.cmd` | Display local health and tunnel status |
| 6 | `06-STOP-FLOW.cmd` | Stop Flow Agent and ngrok |
| 7 | `07-UNINSTALL-FLOW.cmd` | Safely remove installer-owned local data |

On a new Windows computer, begin with step 1. The assistant installs missing tools, clones and prepares Flow Agent in an isolated environment, configures ngrok, guides extension loading, collects a Google Flow project URL, generates a secure API key, and creates private local configuration and a desktop shortcut.

For RunPod, run steps 2, 3, and 4 in order. Step 3 copies the RunPod terminal command to the clipboard and does not execute it on Windows. The user must still sign in to Google, load the unpacked extension, provide their own ngrok authtoken, and save the two RunPod environment variables.

For a local ComfyUI Desktop installation, run steps 1, 3.1, and 4.1. Step 3.1 reads Comfy Desktop's installation registry, selects the installed local instance, clones or safely updates this repository under `custom_nodes`, and installs requirements with that instance's own Python. Existing local modifications are saved in a recoverable Git stash before updating. Step 4.1 uses `http://127.0.0.1:8001`, does not start ngrok, and securely configures `FLOW_AGENT_BASE_URL` and `FLOW_AGENT_API_KEY` as Windows user variables. Fully close and reopen ComfyUI Desktop after the first local start so it inherits those variables.

After initial local setup, the normal daily action is only `04.1-START-FLOW-LOCAL.cmd`. Run step 3.1 again when updating the custom node from GitHub. Step 3.1 updates the ComfyUI node only; rerun step 1 when an update includes Flow Agent backend compatibility patches. The step 4 launchers verify both required backend patches before starting, preventing a partially updated installation from reaching a paid generation request.

Start Flow Agent through the desktop shortcut or:

```text
scripts\04-START-FLOW-RUNPOD.cmd
```

The RunPod launcher starts or reuses ngrok, updates `PUBLIC_BASE_URL`, starts Flow Agent when needed, opens the configured project, and copies the public URL. Paste it into `FLOW_AGENT_BASE_URL` and restart the remote ComfyUI.

For local ComfyUI use:

```text
scripts\04.1-START-FLOW-LOCAL.cmd
```

Both launchers share the same backend, project, status, and stop scripts. Switching modes updates `PUBLIC_BASE_URL` and safely restarts the managed backend when required. `05-STATUS-FLOW.cmd` reports the selected mode; `06-STOP-FLOW.cmd` works for either mode and closes an existing managed ngrok tunnel only when one is present.

The upstream extension's **Generate with Flow** button currently calls the protected HTTP endpoint without `SERVER_API_KEY`. With authentication enabled, that convenience button returns HTTP 401. This does not prevent the extension from acting as the Flow bridge; submit protected generation requests through this ComfyUI integration instead. Do not disable authentication on an internet-exposed ngrok endpoint to make that button work.

Implementation scripts live under `scripts\internal`. Runtime configuration, state, and logs live under `%LOCALAPPDATA%\ComfyUIFlowAgent`, so the repository remains clean. Existing runtime files from older versions are migrated automatically the next time step 4 runs.

Status and shutdown:

```powershell
.\scripts\05-STATUS-FLOW.cmd
.\scripts\06-STOP-FLOW.cmd
```

## Safe local uninstall

Double-click:

```text
scripts\07-UNINSTALL-FLOW.cmd
```

The exact word `UNINSTALL` is required. The Flow Agent copy is removed only when a private ownership marker proves that this installer created it. Manual or older installations without that marker are preserved.

The uninstaller never removes or modifies Windows Python, external environments, shared packages or caches, Google Chrome, browser data or extension settings, Google Flow projects, Git, uv, ngrok, shared ngrok credentials, ComfyUI, models, workflows, or ComfyUI-generated files. The unpacked extension entry remains in the browser and may be removed manually.

## Reference media

- `Flow / Nano Banana`: use `reference_image` and `reference_image_2` through `reference_image_10`. The combined maximum is 10.
- `Flow / Custom Character Creator`: one identity image plus labeled top, bottom, accessories, and shoes references, combined maximum 10. Identical bytes are reused by fingerprint.
- `Flow / Omni Flash Video` modes:
  - `start image to video` requires `start_image`.
  - `first + last frame` requires `start_image` and `end_image`.
  - `ingredients / reference images` accepts image references plus `reference_video_media_ids` and `reference_video_paths`, with 10 combined ingredients maximum.
  - `edit source video` requires exactly one source and disables references.
  - `video to video` requires exactly one source and accepts optional image references; additional video references are disabled.
  - A source video is the clip being transformed. A reference video is an ingredient used for motion, lighting, style, subject, or scene guidance.
  - Leave `video_model_override` blank to select the correct Flow model for the chosen mode and orientation. Text-to-video and image-conditioned modes do not share the same model key.
  - A requested upscale returns one final delivery to ComfyUI. The native 720p source remains in Flow Agent history instead of appearing as a second generated video.
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
