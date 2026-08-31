# ADR 0001: Next-Generation Autonomous SDLC Fleet Architecture & Governance

* **Status**: Accepted
* **Date**: 2026-08-31
* **Deciders**: Autonomous SDLC Core Team

## Context

`agentic-fleet` is a multi-agent software engineering framework providing automated end-to-end SDLC capabilities across specification authoring (`pm-agent`), implementation (`dev-agent`), security audits (`security-agent`), adversarial QA verification (`qa-agent`), and architectural sign-off (`senior-reviewer-agent`).

To scale from Level 3 (Reactive Multi-Agent) to Level 4 (Proactive Self-Healing & Distributed Consensus), the system requires:
1. Pre-commit test sandboxing to eliminate broken commits.
2. Multi-model tiering to optimize speed, cost, and reasoning depth.
3. Dedicated reviewer bot identity to satisfy GitHub enterprise branch protection rules.
4. Native inline code suggestions on PR diffs.
5. Observability and executive metrics in `$GITHUB_STEP_SUMMARY`.

## Decision

We adopt the following architectural standards across `agentic-fleet`:
1. **Pre-Commit Self-Healing Sandbox**: `dev-agent` must run `pytest` locally inside the runner and auto-remediate syntax, import, and logic errors before executing `git commit` and `git push`.
2. **Dedicated Reviewer Bot Token (`REVIEWER_GITHUB_TOKEN`)**: Provide dual-token support so `senior-reviewer-agent` can submit official `APPROVE` reviews from an independent bot identity.
3. **Multi-Model Tiering**:
   - `Fast Tier` (`gemini-2.5-flash` / `gemini-2.0-flash`): `pm-agent`, `dev-agent`, `qa-agent`.
   - `Deep Tier` (`gemini-2.5-pro` / `gemini-3.1-pro`): `security-agent`, `senior-reviewer-agent`.
4. **Native Inline PR Suggestions**: Parse code suggestion blocks and submit them to GitHub's Pull Request review comments API.
5. **Observability**: Automatically format and write complete execution summaries into `$GITHUB_STEP_SUMMARY`.

## Consequences

### Positive
- **Clean Git History**: PR branches only receive 100% green commits.
- **Enterprise Ready**: Full compliance with GitHub branch protections and required PR approval rules.
- **High-Impact Reviews**: Developers can accept security suggestions with one click.
- **Cost & Speed Optimized**: Flash models handle rapid iterations while Pro models perform deep audits.

### Negative / Trade-offs
- Setting up a secondary reviewer token or GitHub App is required for official `APPROVE` badge compliance.
