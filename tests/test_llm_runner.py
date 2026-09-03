import pytest
from pathlib import Path
from unittest.mock import AsyncMock
from src.llm_runner import LLMRunner


def test_load_prompt_and_substitute():
    runner = LLMRunner()
    prompt = runner.load_prompt(
        "pm-agent",
        {"issue_title": "Custom Feature", "issue_body": "Custom Body text"},
    )
    assert "pm-agent" in prompt
    assert "User Story" in prompt


def test_load_all_prompts():
    runner = LLMRunner()
    agents = ["pm-agent", "dev-agent", "security-agent", "qa-agent", "senior-reviewer-agent"]
    for agent in agents:
        prompt = runner.load_prompt(agent)
        assert len(prompt) > 50


@pytest.mark.asyncio
async def test_generate_response_dry_run():
    runner = LLMRunner()
    response = await runner.generate_response(
        system_instruction="You are pm-agent",
        user_prompt="Format issue #12",
        dry_run=True,
    )
    assert "DRY RUN" in response
    assert "Format issue #12" in response


@pytest.mark.asyncio
async def test_gemini_quota_fails_over_to_configured_provider():
    runner = LLMRunner(provider="gemini")
    runner.gemini_api_key = "gemini-key"
    runner.openai_api_key = "openai-key"
    runner._generate_gemini = AsyncMock(side_effect=RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded"))
    runner._generate_openai = AsyncMock(return_value="OpenAI fallback response")

    response = await runner.generate_response("system", "input")

    assert response == "OpenAI fallback response"
    runner._generate_gemini.assert_awaited_once()
    runner._generate_openai.assert_awaited_once()
