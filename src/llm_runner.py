"""
LLM execution runner for dispatching tasks to Gemini models.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional
import httpx


class LLMRunner:
    """Runner for prompt management and Gemini API communication."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-pro",
        prompts_dir: Optional[Path] = None,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model
        self.prompts_dir = prompts_dir or (Path(__file__).parent.parent / "prompts")

    def load_prompt(self, agent_name: str, variables: Optional[Dict[str, Any]] = None) -> str:
        """Load and render an agent system prompt template with variable substitution."""
        prompt_filename = f"{agent_name}.prompt.md"
        prompt_path = self.prompts_dir / prompt_filename

        if not prompt_path.exists():
            # Try alternate naming (e.g. senior-reviewer -> senior-reviewer-agent)
            prompt_filename = f"{agent_name}-agent.prompt.md"
            prompt_path = self.prompts_dir / prompt_filename

        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found for agent '{agent_name}' at {self.prompts_dir}")

        content = prompt_path.read_text(encoding="utf-8")

        if variables:
            for key, val in variables.items():
                pattern = re.compile(r"\{\{\s*" + re.escape(key) + r"\s*\}\}")
                content = pattern.sub(str(val), content)

        return content

    async def generate_response(
        self,
        system_instruction: str,
        user_prompt: str,
        temperature: float = 0.2,
        dry_run: bool = False,
    ) -> str:
        """Generate response from Gemini API or return simulated output during dry run."""
        if dry_run or not self.api_key:
            return (
                f"### [DRY RUN / MOCK MODE]\n\n"
                f"**System Role Instructions Loaded** ({len(system_instruction)} chars).\n\n"
                f"**Processed User Input**:\n{user_prompt}\n\n"
                f"**Simulated Agent Verdict**: STATUS: PASSED / COMPLETED"
            )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "system_instruction": {
                "parts": [{"text": system_instruction}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 8192,
            }
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

            try:
                candidate = data["candidates"][0]
                text = candidate["content"]["parts"][0]["text"]
                return text
            except (KeyError, IndexError) as e:
                raise RuntimeError(f"Unexpected response format from Gemini API: {data}") from e
