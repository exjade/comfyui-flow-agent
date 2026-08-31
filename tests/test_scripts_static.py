from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
START = (ROOT / "scripts" / "internal" / "start-flow-local.ps1").read_text(encoding="utf-8")
STOP = (ROOT / "scripts" / "internal" / "stop-flow-local.ps1").read_text(encoding="utf-8")
SETUP = (ROOT / "scripts" / "internal" / "setup-flow-local.ps1").read_text(encoding="utf-8")


def test_start_recovers_managed_backend_and_bridge_listeners():
    assert 'Get-DotEnvValue "WS_PORT"' in START
    assert "Stop-ManagedListener" in START
    assert "@($Port, $BridgePort)" in START
    assert "Test-ManagedFlowProcess" in START


def test_stop_cleans_stale_ports_even_without_a_state_file():
    assert "No automated-run state file exists" not in STOP
    assert "@($BackendPort, $BridgePort, 4040)" in STOP
    assert "Test-ManagedFlowProcess" in STOP
    assert "Test-ManagedNgrokProcess" in STOP
    assert "Skipped unrelated process" in STOP


def test_setup_installs_media_and_conditioned_video_backend_fixes():
    assert "flow-agent-media-reuse.patch" in SETUP
    assert "flow-agent-video-reference.patch" in SETUP
    assert "Apply-BackendPatches" in SETUP
