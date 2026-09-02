import pytest


@pytest.fixture(autouse=True)
def isolate_fleet_state(tmp_path, monkeypatch):
    """Ensure every test runs with an isolated ephemeral StateManager state file."""
    state_file = tmp_path / ".agentic_fleet_state.json"
    monkeypatch.setenv("FLEET_STATE_FILE", str(state_file))
