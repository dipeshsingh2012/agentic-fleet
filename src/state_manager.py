"""
Persistent State Continuity, Run Counter, and Cost Telemetry Manager.
Stores structured run metadata, loop budget tracking, and token usage statistics.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agentic-fleet.state_manager")


@dataclass
class AgentRunRecord:
    agent: str
    action: str
    verdict: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class PRStateRecord:
    pr_number: int
    repo: str
    current_stage: str = "initialized"
    remediations_count: int = 0
    is_blocked: bool = False
    blocked_reason: Optional[str] = None
    runs: List[Dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class StateManager:
    """Manages deterministic state continuity across multi-webhook invocations."""

    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file or Path(os.getenv("FLEET_STATE_FILE", ".agentic_fleet_state.json"))
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Failed to load state file: {e}")
        return {"prs": {}, "issues": {}, "telemetry": {"total_runs": 0, "total_cost_usd": 0.0}}

    def _save(self) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to save state file: {e}")

    def _key(self, repo: str, pr_number: int) -> str:
        return f"{repo}#{pr_number}"

    def get_pr_state(self, repo: str, pr_number: int) -> PRStateRecord:
        key = self._key(repo, pr_number)
        raw = self._data.get("prs", {}).get(key)
        if raw:
            return PRStateRecord(**raw)
        return PRStateRecord(pr_number=pr_number, repo=repo)

    def record_run(
        self,
        repo: str,
        pr_number: int,
        agent: str,
        action: str,
        verdict: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> PRStateRecord:
        """Records an agent execution step, tracks loop counts, and updates telemetry."""
        key = self._key(repo, pr_number)
        state = self.get_pr_state(repo, pr_number)

        # Standard token pricing (approx $0.15/1M input, $0.60/1M output for flash-tier models)
        cost = (input_tokens * 0.00000015) + (output_tokens * 0.00000060)

        record = AgentRunRecord(
            agent=agent,
            action=action,
            verdict=verdict,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
        )

        state.runs.append(asdict(record))
        state.total_tokens += (input_tokens + output_tokens)
        state.total_cost_usd += cost
        state.current_stage = f"{agent}:{action}"
        state.updated_at = time.time()

        if action in ["remediated_pr", "remediation_update"]:
            state.remediations_count += 1

        self._data.setdefault("prs", {})[key] = asdict(state)
        self._data.setdefault("telemetry", {})["total_runs"] = self._data["telemetry"].get("total_runs", 0) + 1
        self._data["telemetry"]["total_cost_usd"] = self._data["telemetry"].get("total_cost_usd", 0.0) + cost
        self._save()
        return state

    def is_budget_exceeded(self, repo: str, pr_number: int, max_budget: int = 4) -> bool:
        """Checks if remediation iterations exceeded the allowed limit."""
        state = self.get_pr_state(repo, pr_number)
        return state.remediations_count >= max_budget

    def get_telemetry_summary(self, repo: str, pr_number: int) -> str:
        """Returns human-readable telemetry summary for PR comments."""
        state = self.get_pr_state(repo, pr_number)
        return (
            f"**Agentic Fleet Telemetry**: {len(state.runs)} runs | "
            f"{state.remediations_count} remediation(s) | "
            f"~{state.total_tokens:,} tokens (~${state.total_cost_usd:.4f} USD)"
        )
