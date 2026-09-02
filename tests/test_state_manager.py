"""
Unit tests for StateManager, budget cap enforcement, and telemetry tracking.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from src.state_manager import StateManager


def test_state_manager_run_recording_and_budget(tmp_path: Path):
    state_file = tmp_path / "test_state.json"
    manager = StateManager(state_file=state_file)

    # Initial state
    assert manager.is_budget_exceeded("dipeshsingh2012/rfpengine", 10, max_budget=2) is False

    # Record first remediation run
    manager.record_run(
        repo="dipeshsingh2012/rfpengine",
        pr_number=10,
        agent="dev-agent",
        action="remediated_pr",
        input_tokens=1000,
        output_tokens=500,
    )
    assert manager.is_budget_exceeded("dipeshsingh2012/rfpengine", 10, max_budget=2) is False

    # Record second remediation run
    manager.record_run(
        repo="dipeshsingh2012/rfpengine",
        pr_number=10,
        agent="dev-agent",
        action="remediated_pr",
        input_tokens=1500,
        output_tokens=800,
    )
    # Exceeded max_budget=2
    assert manager.is_budget_exceeded("dipeshsingh2012/rfpengine", 10, max_budget=2) is True

    telemetry = manager.get_telemetry_summary("dipeshsingh2012/rfpengine", 10)
    assert "2 runs" in telemetry
    assert "2 remediation(s)" in telemetry
    assert "tokens" in telemetry
