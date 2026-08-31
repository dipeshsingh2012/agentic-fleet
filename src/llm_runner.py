"""
LLM execution runner for dispatching tasks to Gemini models via Google GenAI SDK and REST fallback.
Includes dynamic model discovery to automatically query active Google AI Studio models and filter deprecated versions.
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
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.prompts_dir = prompts_dir or (Path(__file__).parent.parent / "prompts")
        self._discovered_models: Optional[List[str]] = None

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

    async def discover_active_models(self) -> List[str]:
        """Query Google API for the list of currently active and supported generateContent models."""
        if self._discovered_models:
            return self._discovered_models

        discovered: List[str] = []
        if self.api_key:
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={self.api_key}"
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.get(url, headers={"x-goog-api-key": self.api_key})
                    if resp.status_code == 200:
                        data = resp.json()
                        for item in data.get("models", []):
                            methods = item.get("supportedGenerationMethods", [])
                            name = item.get("name", "").replace("models/", "")
                            # Filter out deprecated 1.0 / 1.5 models and ensure generateContent is supported
                            if "generateContent" in methods and not name.startswith("gemini-1.") and not name.startswith("text-embedding"):
                                discovered.append(name)
                        print(f"[LLM] 🔍 Discovered {len(discovered)} active models from Google API: {discovered[:5]}")
            except Exception as e:
                print(f"[WARN] Dynamic model discovery failed: {e}")

        # Built-in modern fallback candidates (excluding deprecated 1.5)
        defaults = [
            self.model,
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash-lite",
            "gemini-2.0-pro-exp",
        ]
        
        final_list: List[str] = []
        for m in (discovered or defaults):
            clean = m.replace("models/", "")
            if clean and clean not in final_list and not clean.startswith("gemini-1."):
                final_list.append(clean)

        self._discovered_models = final_list
        return final_list

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

        candidate_models = await self.discover_active_models()
        print(f"[LLM] 🚀 Attempting generation with candidate models: {candidate_models}")

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
                        print(f"[LLM] ✅ Successfully generated response using GenAI SDK model: {model_name}")
                        return resp.text
                except Exception as e:
                    print(f"[WARN] GenAI SDK model '{model_name}' attempt failed: {e}")

        # Strategy 2: Direct REST with valid Google AI Studio headers and parameters
        last_error = None

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

        for model_name in candidate_models:
            clean_model = model_name.replace("models/", "")
            urls = [
                f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={self.api_key}",
                f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent",
            ]

            for url in urls:
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key,
                }

                try:
                    async with httpx.AsyncClient(timeout=90.0) as client:
                        resp = await client.post(url, json=payload, headers=headers)
                        if resp.status_code == 200:
                            data = resp.json()
                            candidate = data["candidates"][0]
                            text = candidate["content"]["parts"][0]["text"]
                            print(f"[LLM] ✅ Successfully generated response using REST model: {clean_model}")
                            return text
                        else:
                            last_error = f"HTTP {resp.status_code} for {clean_model}: {resp.text}"
                            print(f"[WARN] REST {clean_model}: HTTP {resp.status_code}")
                except Exception as e:
                    last_error = str(e)

        raise RuntimeError(f"All Gemini generation attempts failed. Last error: {last_error}")
