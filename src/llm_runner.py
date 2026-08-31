"""
LLM execution runner for dispatching tasks to Gemini models via Google GenAI SDK and REST fallback.
Features Multi-Model Tiering (Fast vs Deep) and dynamic model discovery with specialized model filtering.
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
    """Runner for prompt management, model discovery, and multi-tier Gemini API communication."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        prompts_dir: Optional[Path] = None,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
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
        """Query Google API for active generateContent models, filtering non-text models."""
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
                            
                            # Filter out non-general text models (tts, robotics, image, transcribe, clip)
                            is_excluded = any(
                                tag in name.lower()
                                for tag in ["tts", "robotics", "image", "transcribe", "clip", "banana", "embed", "1.0", "1.5"]
                            )
                            if "generateContent" in methods and not is_excluded:
                                discovered.append(name)
                        print(f"[LLM] 🔍 Discovered {len(discovered)} active text models: {discovered[:6]}")
            except Exception as e:
                print(f"[WARN] Dynamic model discovery failed: {e}")

        # Modern fallbacks prioritized by stability
        defaults = [
            "gemini-2.0-flash",
            "gemini-flash-latest",
            "gemma-4-26b-a4b-it",
            "gemma-4-31b-it",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-pro-latest",
            "gemini-2.0-flash-lite",
        ]

        final_list: List[str] = []
        for m in (discovered or defaults):
            clean = m.replace("models/", "")
            if clean and clean not in final_list:
                final_list.append(clean)

        self._discovered_models = final_list
        return final_list

    def get_tiered_candidates(self, available_models: List[str], tier: str = "fast") -> List[str]:
        """Order candidate models based on performance tier (fast vs deep)."""
        if tier == "deep":
            # Prioritize large reasoning models
            deep_priority = ["pro", "31b", "26b", "2.5-pro", "gemini-pro-latest", "gemini-2.0-flash"]
            sorted_models = sorted(
                available_models,
                key=lambda m: any(p in m.lower() for p in deep_priority),
                reverse=True,
            )
            return sorted_models
        else:
            # Prioritize fast, high-throughput models
            fast_priority = ["2.0-flash", "flash-latest", "flash-lite", "26b", "gemini-2.5-flash"]
            sorted_models = sorted(
                available_models,
                key=lambda m: any(p in m.lower() for p in fast_priority),
                reverse=True,
            )
            return sorted_models

    async def generate_response(
        self,
        system_instruction: str,
        user_prompt: str,
        temperature: float = 0.2,
        dry_run: bool = False,
        tier: str = "fast",
    ) -> str:
        """Generate response using GenAI SDK with REST fallback and multi-model tiering."""
        if dry_run or not self.api_key:
            return (
                f"### [DRY RUN / MOCK MODE]\n\n"
                f"**System Role Instructions Loaded** ({len(system_instruction)} chars).\n\n"
                f"**Processed User Input**:\n{user_prompt}\n\n"
                f"**Simulated Agent Verdict**: STATUS: PASSED / COMPLETED"
            )

        all_models = await self.discover_active_models()
        candidate_models = self.get_tiered_candidates(all_models, tier=tier)
        print(f"[LLM] 🚀 Attempting [{tier.upper()} TIER] generation with models: {candidate_models[:5]}")

        # 1. Google GenAI Official SDK
        if HAS_GENAI_SDK:
            for model_name in candidate_models:
                try:
                    client = genai.Client(api_key=self.api_key)
                    config = types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=temperature,
                    )
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=user_prompt,
                        config=config,
                    )
                    if resp.text:
                        print(f"[LLM] ✅ Successfully generated response using SDK model: {model_name}")
                        return resp.text
                except Exception as e:
                    err_str = str(e)
                    if "404" in err_str or "NOT_FOUND" in err_str:
                        print(f"[WARN] Model '{model_name}' 404 Not Found. Skipping.")
                    elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        print(f"[WARN] Model '{model_name}' quota exhausted. Trying next model...")
                    else:
                        print(f"[WARN] GenAI SDK model '{model_name}' attempt failed: {e}")

        # 2. REST API Fallback
        for model_name in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
            payload = {
                "systemInstruction": {"parts": [{"text": system_instruction}]},
                "contents": [{"parts": [{"text": user_prompt}]}],
                "generationConfig": {"temperature": temperature},
            }
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates and "content" in candidates[0]:
                            parts = candidates[0]["content"].get("parts", [])
                            if parts and "text" in parts[0]:
                                print(f"[LLM] ✅ Successfully generated response using REST model: {model_name}")
                                return parts[0]["text"]
                    elif resp.status_code == 404:
                        continue
            except Exception as e:
                print(f"[WARN] REST API fallback error for model '{model_name}': {e}")

        raise RuntimeError("All Gemini generation attempts failed across all discovered models.")
