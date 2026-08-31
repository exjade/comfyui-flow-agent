from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
START = (ROOT / "scripts" / "internal" / "start-flow-local.ps1").read_text(encoding="utf-8")
STOP = (ROOT / "scripts" / "internal" / "stop-flow-local.ps1").read_text(encoding="utf-8")
SETUP = (ROOT / "scripts" / "internal" / "setup-flow-local.ps1").read_text(encoding="utf-8")
STATUS = (ROOT / "scripts" / "internal" / "status-flow-local.ps1").read_text(encoding="utf-8")
UNINSTALL = (ROOT / "scripts" / "internal" / "uninstall-flow-local.ps1").read_text(encoding="utf-8")
RUNPOD_LAUNCHER = (ROOT / "scripts" / "04-START-FLOW-RUNPOD.cmd").read_text(encoding="utf-8")
LOCAL_LAUNCHER = (ROOT / "scripts" / "04.1-START-FLOW-LOCAL.cmd").read_text(encoding="utf-8")
LOCAL_INSTALLER_LAUNCHER = (ROOT / "scripts" / "03.1-INSTALL-OR-UPDATE-CUSTOM-NODE-LOCAL.cmd").read_text(encoding="utf-8")
LOCAL_INSTALLER = (ROOT / "scripts" / "internal" / "install-comfyui-local.ps1").read_text(encoding="utf-8")
VIDEO_PATCH = (ROOT / "patches" / "flow-agent-video-reference.patch").read_text(encoding="utf-8")


def test_start_recovers_managed_backend_and_bridge_listeners():
    assert 'Get-DotEnvValue "WS_PORT"' in START
    assert "Stop-ManagedListener" in START
    assert "@($Port, $BridgePort)" in START
    assert "Test-ManagedFlowProcess" in START


def test_launchers_select_explicit_runpod_and_local_modes():
    assert "-Mode RunPod" in RUNPOD_LAUNCHER
    assert "-Mode Local" in LOCAL_LAUNCHER
    assert not (ROOT / "scripts" / "04-START-FLOW.cmd").exists()


def test_local_custom_node_installer_detects_updates_and_uses_comfy_python():
    assert "install-comfyui-local.ps1" in LOCAL_INSTALLER_LAUNCHER
    assert 'Comfy Desktop\\installations.json' in LOCAL_INSTALLER
    assert 'stash push --include-untracked' in LOCAL_INSTALLER
    assert 'pull --ff-only' in LOCAL_INSTALLER
    assert '.venv\\Scripts\\python.exe' in LOCAL_INSTALLER
    assert '-m pip install -r' in LOCAL_INSTALLER


def test_local_mode_configures_comfyui_without_ngrok():
    assert '[ValidateSet("RunPod", "Local")]' in START
    assert '$BaseUrl = "http://127.0.0.1:$Port"' in START
    assert '[Environment]::SetEnvironmentVariable("FLOW_AGENT_BASE_URL", $BaseUrl, "User")' in START
    assert '[Environment]::SetEnvironmentVariable("FLOW_AGENT_API_KEY", $CurrentApiKey, "User")' in START
    assert 'if ($Mode -eq "RunPod")' in START
    assert "Stop-ManagedNgrokTunnel" in START


def test_stop_cleans_stale_ports_even_without_a_state_file():
    assert "No automated-run state file exists" not in STOP
    assert "@($BackendPort, $BridgePort, 4040)" in STOP
    assert "Test-ManagedFlowProcess" in STOP
    assert "Test-ManagedNgrokProcess" in STOP
    assert "Skipped unrelated process" in STOP


def test_status_setup_and_uninstall_support_both_modes():
    assert '$Mode -eq "local"' in STATUS
    assert "ngrok: not used in Local mode" in STATUS
    assert "04-START-FLOW-RUNPOD.cmd" in SETUP
    assert "04.1-START-FLOW-LOCAL.cmd" in SETUP
    assert "04-START-FLOW-RUNPOD.cmd" in UNINSTALL
    assert "04.1-START-FLOW-LOCAL.cmd" in UNINSTALL
    assert 'SetEnvironmentVariable("FLOW_AGENT_BASE_URL", $null, "User")' in UNINSTALL


def test_setup_installs_media_and_conditioned_video_backend_fixes():
    assert "flow-agent-media-reuse.patch" in SETUP
    assert "flow-agent-video-reference.patch" in SETUP
    assert "Apply-BackendPatches" in SETUP
    assert '-C $FlowRepoDir apply' in SETUP
    assert '--directory=flow-agent' in SETUP


def test_local_installer_enumerates_comfy_desktop_json_in_windows_powershell():
    installer = (ROOT / "scripts" / "internal" / "install-comfyui-local.ps1").read_text(
        encoding="utf-8"
    )
    assert "$Installations = Get-Content" in installer
    assert "$Installations = @(Get-Content" not in installer
    assert "ComfyUI detectado / detected:" in installer
    assert "Presiona Enter para usarlo" in installer
    assert "return Resolve-ComfyUIRoot -RequestedRoot $RequestedPath" in installer


def test_start_refuses_to_run_without_required_backend_fixes():
    assert "flow-agent-media-reuse.patch" in START
    assert "flow-agent-video-reference.patch" in START
    assert "apply --recount --reverse --check --unidiff-zero" in START
    assert "Flow Agent compatibility fixes are not installed" in START
    assert '-C $FlowAgentRepositoryDir apply' in START
    assert '"--directory=$FlowAgentRepositorySubdir"' in START


def test_conditioned_video_patch_tracks_current_omni_request_contract():
    assert '"reference": "abra_r2v"' in VIDEO_PATCH
    assert '"i2v": "abra_i2v"' in VIDEO_PATCH
    assert '+            "textInput": {"prompt": prompt}' in VIDEO_PATCH
    assert '+            "resolution": resolution' not in VIDEO_PATCH
    assert "veo_3_0_r2v_fast" not in VIDEO_PATCH
    assert "veo_3_1_i2v_s_fast" not in VIDEO_PATCH
    assert "cached_image = None if is_video_input" not in VIDEO_PATCH
    assert "from flow_server.media_history import find_uploaded_file" not in VIDEO_PATCH


def test_video_patch_preserves_async_failures_and_exposes_read_only_diagnostics():
    assert "VideoGenerationFailedError" in VIDEO_PATCH
    assert "/v1/media/{media_id}/status" in VIDEO_PATCH
    assert "/v1/flow-app-config" in VIDEO_PATCH
