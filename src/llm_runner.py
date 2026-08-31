"""
LLM execution runner for dispatching tasks to Gemini models via Google GenAI SDK and REST fallback.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

try:
    from google import genai
    from google.genai import types
    HAS_GENAI_SDK = True
except ImportError:
    HAS_GENAI_SDK = False

logger = logging.getLogger("agentic-fleet.llm_runner")


class LLMRunner:
    """Runner for prompt management and Gemini API communication."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        prompts_dir: Optional[Path] = None,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        self.prompts_dir = prompts_dir or (Path(__file__).parent.parent / "prompts")

    def load_prompt(self, agent_name: str, variables: Optional[Dict[str, Any]] = None) -> str:
        """Load and render an agent system prompt template with variable substitution."""
        prompt_filename = f"{agent_name}.prompt.md"
        prompt_path = self.prompts_dir / prompt_filename

        if not prompt_path.exists():
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
        """Generate response from Gemini API using Google GenAI SDK with REST fallback."""
        if dry_run or not self.api_key:
            return (
                f"### [DRY RUN / MOCK MODE]\n\n"
                f"**System Role Instructions Loaded** ({len(system_instruction)} chars).\n\n"
                f"**Processed User Input**:\n{user_prompt}\n\n"
                f"**Simulated Agent Verdict**: STATUS: PASSED / COMPLETED"
            )

        # Build candidate list with gemini-3.5-flash first
        ordered_candidates = [
            self.model,
            "gemini-3.5-flash",
            "gemini-3.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ]
        candidate_models: List[str] = []
        for m in ordered_candidates:
            if m and m not in candidate_models:
                candidate_models.append(m)

        # Strategy 1: Official Google GenAI SDK
        if HAS_GENAI_SDK:
            for model_name in candidate_models:
                try:
                    client = genai.Client(api_key=self.api_key)
                    config = types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=temperature,
                        max_output_tokens=8192,
                    )
                    resp = await client.aio.models.generate_content(
                        model=model_name,
                        contents=user_prompt,
                        config=config,
                    )
                    if resp.text:
                        return resp.text
                except Exception as e:
                    print(f"[WARN] GenAI SDK model '{model_name}' attempt: {e}")

        # Strategy 2: Direct REST across API versions and auth header formats
        auth_headers_variants = [
            {"x-goog-api-key": self.api_key},
            {"Authorization": f"Bearer {self.api_key}"},
            {},  # Query parameter fallback
        ]

        api_versions = ["v1beta", "v1"]
        last_error = None

        for api_ver in api_versions:
            for model_name in candidate_models:
                clean_model = model_name.replace("models/", "")
                for headers in auth_headers_variants:
                    url = f"https://generativelanguage.googleapis.com/{api_ver}/models/{clean_model}:generateContent"
                    if not headers:
                        url += f"?key={self.api_key}"

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

                    req_headers = {"Content-Type": "application/json"}
                    req_headers.update(headers)

                    try:
                        async with httpx.AsyncClient(timeout=60.0) as client:
                            resp = await client.post(url, json=payload, headers=req_headers)
                            if resp.status_code == 200:
                                data = resp.json()
                                candidate = data["candidates"][0]
                                return candidate["content"]["parts"][0]["text"]
                            else:
                                last_error = f"HTTP {resp.status_code} on {api_ver}/models/{clean_model}: {resp.text}"
                                print(f"[WARN] REST {clean_model} ({api_ver}): HTTP {resp.status_code}")
                    except Exception as e:
                        last_error = str(e)

        raise RuntimeError(f"All Gemini generation attempts failed. Last error: {last_error}")
