"""
Security audit and hardening unit tests.
Verifies path traversal guards, token redaction, and credential protection.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from src.event_router import EventRouter
from src.test_harness import TestHarness


def test_path_traversal_blocked_in_file_materialization(tmp_path: Path):
    router = EventRouter(dry_run=True)
    malicious_output = (
        "```python:../../etc/shadow\nroot:x:0:0:root:/root:/bin/bash\n```\n"
        "```python:../outside.py\n# outside workspace\n```\n"
        "```python:src/valid.py\ndef hello(): pass\n```"
    )

    workspace = tmp_path / "target_repo"
    workspace.mkdir()

    materialized = router._materialize_code_files(workspace, malicious_output)

    # Valid relative file must be written
    assert "src/valid.py" in materialized
    assert (workspace / "src" / "valid.py").exists()

    # Traversal files must be rejected and never created
    assert "../../etc/shadow" not in materialized
    assert "../outside.py" not in materialized
    assert not (tmp_path / "outside.py").exists()


@pytest.mark.asyncio
async def test_secret_redaction_in_test_harness():
    harness = TestHarness()
    raw_text = "pushing to https://x-access-token:ghs_SecretToken1234567890@github.com/owner/repo.git with Bearer sk-ant-api03-abcdef1234567890"
    redacted = harness._redact_secrets(raw_text)

    assert "ghs_SecretToken1234567890" not in redacted
    assert "sk-ant-api03-abcdef1234567890" not in redacted
    assert "https://x-access-token:***@github.com/owner/repo.git" in redacted
    assert "Bearer ***" in redacted
