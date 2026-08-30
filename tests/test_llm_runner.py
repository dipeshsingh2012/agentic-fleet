import pytest
from pathlib import Path
from src.llm_runner import LLMRunner


def test_load_prompt_and_substitute():
    runner = LLMRunner()
    prompt = runner.load_prompt(
        "pm-agent",
        {"issue_title": "Custom Feature", "issue_body": "Custom Body text"},
    )
    assert "pm-agent" in prompt
    assert "User Stories" in prompt


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
