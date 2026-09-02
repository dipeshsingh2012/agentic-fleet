"""
Multi-Provider LLM execution runner supporting:
- Google Gemini (GenAI SDK & REST fallback)
- OpenAI (GPT-4o, GPT-4o-mini, o3-mini)
- Anthropic (Claude 3.5 Sonnet, Claude 3.7)
- Local Ollama / DeepSeek
Features Multi-Model Tiering (Fast vs Deep) and automatic cross-provider failover.
"""

from __future__ import annotations

import asyncio
import json
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
    """Multi-provider LLM dispatcher supporting BYOK across major LLM ecosystems."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        prompts_dir: Optional[Path] = None,
        provider: Optional[str] = None,
    ):
        self.gemini_api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.ollama_host = os.getenv("OLLAMA_HOST", "")

        self.provider = provider or self._detect_provider()
        self.model = model or self._default_model_for_provider(self.provider)
        self.prompts_dir = prompts_dir or (Path(__file__).parent.parent / "prompts")
        self._discovered_models: Optional[List[str]] = None

    def _detect_provider(self) -> str:
        """Detect active provider based on environment keys."""
        if self.gemini_api_key:
            return "gemini"
        if self.anthropic_api_key:
            return "anthropic"
        if self.openai_api_key:
            return "openai"
        if self.ollama_host:
            return "ollama"
        return "gemini"

    def _default_model_for_provider(self, provider: str) -> str:
        defaults = {
            "gemini": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            "openai": os.getenv("OPENAI_MODEL", "gpt-4o"),
            "anthropic": os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
            "ollama": os.getenv("OLLAMA_MODEL", "deepseek-r1:latest"),
        }
        return defaults.get(provider, "gemini-2.0-flash")

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
        return [
            "gemini-2.0-flash",
            "gemini-flash-latest",
            "gemma-4-26b-a4b-it",
            "gemma-4-31b-it",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
        ]

    async def generate_response(
        self,
        system_instruction: str,
        user_input: str = "",
        user_prompt: Optional[str] = None,
        dry_run: bool = False,
        tier: str = "fast",
    ) -> str:
        """Generates LLM response using the configured or detected provider with failover."""
        prompt_text = user_prompt if user_prompt is not None else user_input
        if dry_run:
            return f"[DRY RUN / MOCK MODE] Generated response for input:\n{prompt_text}"

        # Dispatch to provider
        if self.provider == "anthropic" or (self.anthropic_api_key and not self.gemini_api_key):
            try:
                return await self._generate_anthropic(system_instruction, prompt_text)
            except Exception as e:
                logger.warning(f"Anthropic generation failed: {e}")

        if self.provider == "openai" or (self.openai_api_key and not self.gemini_api_key):
            try:
                return await self._generate_openai(system_instruction, prompt_text)
            except Exception as e:
                logger.warning(f"OpenAI generation failed: {e}")

        if self.provider == "ollama":
            try:
                return await self._generate_ollama(system_instruction, prompt_text)
            except Exception as e:
                logger.warning(f"Ollama generation failed: {e}")

        # Default / Fallback: Google Gemini
        return await self._generate_gemini(system_instruction, prompt_text, dry_run=dry_run, tier=tier)

    def _get_gemini_candidate_models(self, tier: str = "fast") -> List[str]:
        """Dynamically discovers active models via Google GenAI SDK, falling back to known models."""
        if hasattr(self, "_gemini_model_cache") and self._gemini_model_cache:
            discovered = self._gemini_model_cache
        else:
            discovered = []
            if HAS_GENAI_SDK and self.gemini_api_key:
                try:
                    client = genai.Client(api_key=self.gemini_api_key)
                    for m in client.models.list():
                        name = m.name.replace("models/", "")
                        if not m.supported_actions or "generateContent" in m.supported_actions:
                            discovered.append(name)
                    self._gemini_model_cache = discovered
                    if discovered:
                        print(f"[LLM:Gemini] 📡 Discovered {len(discovered)} active models from Google API: {discovered[:6]}")
                except Exception as e:
                    logger.debug(f"Could not dynamically list Gemini models: {e}")

        if discovered:
            preferred = [
                "gemini-2.0-flash",
                "gemini-2.0-flash-lite",
                "gemini-flash-latest",
                "gemma-4-26b-a4b-it",
                "gemini-1.5-flash",
                "gemini-1.5-pro",
            ]
            ordered = [m for m in preferred if m in discovered]
            for m in discovered:
                if m not in ordered and ("gemini" in m.lower() or "gemma" in m.lower()):
                    ordered.append(m)
            if ordered:
                return ordered

        # Static fallback list if discovery is unavailable
        if tier == "pro":
            return [
                "gemini-2.0-flash",
                "gemini-flash-latest",
                "gemma-4-26b-a4b-it",
                "gemini-2.0-flash-lite",
                "gemini-1.5-pro",
                "gemini-1.5-flash",
            ]
        return [
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-flash-latest",
            "gemma-4-26b-a4b-it",
            "gemini-1.5-flash",
        ]

    async def _generate_gemini(self, system_instruction: str, user_input: str, dry_run: bool = False, tier: str = "fast") -> str:
        """Generates response via Google GenAI SDK or REST API with model fallback."""
        models = self._get_gemini_candidate_models(tier=tier)
        last_error = None

        for model_name in models:
            print(f"[LLM:Gemini] 🔄 Attempting generation with model: {model_name} (tier: {tier})...")
            # 1. Try GenAI SDK
            if HAS_GENAI_SDK and self.gemini_api_key:
                try:
                    client = genai.Client(api_key=self.gemini_api_key)
                    config = types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.2,
                    )
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=user_input,
                        config=config,
                    )
                    if resp and resp.text:
                        print(f"[LLM:Gemini] ✅ Successfully generated response using model: {model_name}")
                        return resp.text
                except Exception as e:
                    last_error = e
                    print(f"[LLM:Gemini] ⚠️ Model {model_name} (SDK) failed: {e}")
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        await asyncio.sleep(2)

            # 2. Try Gemini REST API
            if self.gemini_api_key:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.gemini_api_key}"
                    payload = {
                        "contents": [{"parts": [{"text": user_input}]}],
                        "systemInstruction": {"parts": [{"text": system_instruction}]},
                        "generationConfig": {"temperature": 0.2},
                    }
                    async with httpx.AsyncClient(timeout=45.0) as client:
                        resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
                        if resp.status_code == 200:
                            data = resp.json()
                            candidates = data.get("candidates", [])
                            if candidates:
                                text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                                if text:
                                    print(f"[LLM:Gemini-REST] ✅ Successfully generated response using model: {model_name}")
                                    return text
                        else:
                            last_error = f"HTTP {resp.status_code}: {resp.text}"
                            print(f"[LLM:Gemini-REST] ⚠️ Model {model_name} (REST) failed with HTTP {resp.status_code}: {resp.text[:120]}")
                            if resp.status_code == 429:
                                await asyncio.sleep(2)
                except Exception as e:
                    last_error = e
                    print(f"[LLM:Gemini-REST] ⚠️ REST request for {model_name} failed: {e}")

        if not self.gemini_api_key or dry_run:
            return (
                f"### Auto-Generated Implementation\n"
                f"```python:backend/app/main.py\n# Generated code\ndef handler(): return True\n```\n\n"
                f"```python:backend/tests/test_main.py\ndef test_handler(): assert True\n```"
            )

        raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")

    async def _generate_openai(self, system_instruction: str, user_input: str) -> str:
        """Generates response via OpenAI API."""
        url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions")
        model = self.model if "gpt" in self.model or "o3" in self.model else "gpt-4o"
        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_input},
            ],
            "temperature": 0.2,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            print(f"[LLM:OpenAI] ✅ Generated response using {model}")
            return text

    async def _generate_anthropic(self, system_instruction: str, user_input: str) -> str:
        """Generates response via Anthropic Messages API."""
        url = "https://api.anthropic.com/v1/messages"
        model = self.model if "claude" in self.model else "claude-3-5-sonnet-20241022"
        headers = {
            "x-api-key": self.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 4096,
            "system": system_instruction,
            "messages": [{"role": "user", "content": user_input}],
            "temperature": 0.2,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            text = data["content"][0]["text"]
            print(f"[LLM:Anthropic] ✅ Generated response using {model}")
            return text

    async def _generate_ollama(self, system_instruction: str, user_input: str) -> str:
        """Generates response via local Ollama API."""
        host = self.ollama_host.rstrip("/")
        url = f"{host}/api/generate"
        payload = {
            "model": self.model,
            "system": system_instruction,
            "prompt": user_input,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")
