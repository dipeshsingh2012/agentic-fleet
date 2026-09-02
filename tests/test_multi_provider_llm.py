"""
Unit tests for multi-provider LLM adapter (Gemini, OpenAI, Anthropic, Ollama).
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from src.llm_runner import LLMRunner


@pytest.mark.asyncio
async def test_llm_runner_dry_run_mode():
    runner = LLMRunner(provider="gemini")
    res = await runner.generate_response("System prompt", "User prompt", dry_run=True)
    assert "[DRY RUN / MOCK MODE]" in res


@pytest.mark.asyncio
async def test_llm_runner_openai_adapter(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    runner = LLMRunner(provider="openai")

    mock_resp = {"choices": [{"message": {"content": "OpenAI Response"}}]}
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = AsyncMock(status_code=200, json=lambda: mock_resp, raise_for_status=lambda: None)
        res = await runner.generate_response("System", "User", dry_run=False)
        assert res == "OpenAI Response"


@pytest.mark.asyncio
async def test_llm_runner_anthropic_adapter(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    runner = LLMRunner(provider="anthropic")

    mock_resp = {"content": [{"text": "Claude Response"}]}
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = AsyncMock(status_code=200, json=lambda: mock_resp, raise_for_status=lambda: None)
        res = await runner.generate_response("System", "User", dry_run=False)
        assert res == "Claude Response"


@pytest.mark.asyncio
async def test_llm_runner_ollama_adapter(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    runner = LLMRunner(provider="ollama")

    mock_resp = {"response": "DeepSeek R1 Response"}
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = AsyncMock(status_code=200, json=lambda: mock_resp, raise_for_status=lambda: None)
        res = await runner.generate_response("System", "User", dry_run=False)
        assert res == "DeepSeek R1 Response"
