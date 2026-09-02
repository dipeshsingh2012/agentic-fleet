# 🛸 Agentic Fleet: Enterprise Autonomous Multi-Agent SDLC

[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-Agentic%20Fleet%20v1-blueviolet?logo=github)](https://github.com/marketplace/actions/agentic-fleet-autonomous-5-agent-sdlc)
[![CI Test Suite](https://github.com/dipeshsingh2012/agentic-fleet/actions/workflows/ci.yml/badge.svg)](https://github.com/dipeshsingh2012/agentic-fleet/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Multi-Provider LLM](https://img.shields.io/badge/LLM-Gemini%20|%20OpenAI%20|%20Claude%20|%20Ollama-purple.svg)](https://ai.google.dev/)
[![Polyglot](https://img.shields.io/badge/Polyglot-Python%20|%20TypeScript%20|%20Go%20|%20Rust%20|%20Java-brightgreen.svg)](#-polyglot-zero-config-discovery)

`agentic-fleet` is the centralized, polyglot agent orchestration engine and source of truth for the **Autonomous 5-Agent SDLC**. 

By adding **one workflow file**, any GitHub repository (Python, TypeScript/Node, Go, Rust, Java, Monorepo) instantly inherits an autonomous engineering department: product framing, architectural design gates, TDD code implementation, adversarial QA, multi-tenant security auditing, and human-in-the-loop sign-off.

---

## 🌟 The 5 Role-Bound Subagents & Separation of Powers

```
[Issue Opened / @fleet] 
         │
         ▼
 1. 📋 PM-Agent        ──► Clarifies requirements & writes Gherkin User Stories
         │
         ▼
 2. 🏛️ Architect-Gate  ──► Audits design against ADRs before code is written
         │
         ▼
 3. 🧑‍💻 Dev-Agent       ──► Implements code, tests & auto-installs dependencies
         │
         ▼
 4. 🛡️ Security-Gate   ──► Audits SQLi, multi-tenant isolation & secrets
         │
         ▼
 5. 🧪 QA-Gate         ──► Executes test suite & verifies edge cases
         │
         ▼
 6. 🧙‍♂️ Senior Reviewer ──► Signs off with final APPROVE & ready-for-merge
```

| Subagent | Persona & Focus | Trigger Event | Output Contract |
| :--- | :--- | :--- | :--- |
| **🎯 `pm-agent`** | **Product Strategy & Framing**<br>Frames user stories, Gherkin Acceptance Criteria (`Given/When/Then`), and RICE prioritization scores. | `issues.opened`, `@pm-agent` | Structured Issue Spec + label `agent:ready-for-design` |
| **📐 `architect-agent`** | **System Architecture & ADRs**<br>Audits proposed technical designs against Architecture Decision Records before code is written. | `agent:design-review`, `@architect-agent` | Design Approval Document + label `agent:ready-for-dev` |
| **🧑‍💻 `dev-agent`** | **TDD Full-Stack Engineer**<br>Creates isolated branch (`feat/<issue-id>-<slug>`), authors clean code + unit tests, auto-installs manifests, materializes files, and handles self-healing loops. | `agent:ready-for-dev`, `@dev-agent`, PR review feedback | Materialized source files, Pull Request, and detailed Remediation Summary |
| **🛡️ `security-agent`** | **Security & Compliance Auditor**<br>Audits git diffs for multi-tenant isolation leaks (`tenant_id` filters), hardcoded secrets, and OWASP vulnerabilities. | `pull_request.opened`, `pull_request.synchronize`, `@security-agent` | Security Audit Report (`STATUS: PASSED ✅` or `STATUS: BLOCKED 🛑`) |
| **🧪 `qa-agent`** | **Adversarial QA & Test Automation**<br>Executes live test suites in the local sandbox (`pytest`, `npm test`, `go test`, `cargo test`), tests edge cases, and verifies zero test collection errors. | `ready-for-qa`, `@qa-agent` | QA Verification Report (`100% PASS ✅` or `STATUS: FAILED ❌`) |
| **🧙‍♂️ `senior-reviewer-agent`** | **Principal Reviewer & Gatekeeper**<br>Audits diffs against ADRs, validates Sec + QA green checks, submits formal approval (**`LGTM ✅`**), and applies `ready-for-merge`. | Sec + QA passed, `@senior-reviewer-agent` | Architectural Review (`APPROVED LGTM ✅`) + `ready-for-merge` label |

---

## 🚀 5 Core Enterprise Pillars

### 1. 🌐 Polyglot Zero-Config Discovery
* Auto-detects project manifests:
  * **Python**: `pyproject.toml`, `requirements.txt` $\rightarrow$ `pytest -v`
  * **TypeScript / Node**: `package.json`, `tsconfig.json` $\rightarrow$ `npm test` / `vitest` / `jest`
  * **Go**: `go.mod` $\rightarrow$ `go test ./...`
  * **Rust**: `Cargo.toml` $\rightarrow$ `cargo test`
  * **Taskfile / Makefile**: `Taskfile.yml` (`task test`), `Makefile` (`make test`)
* Generates language-specific package markers (e.g., `__init__.py` for Python only, avoiding polluting Go/TypeScript repos).

### 2. 🔑 Multi-Provider Bring-Your-Own-Key (BYOK)
* Pluggable LLM execution layer supporting:
  * **Google Gemini**: `gemini-2.0-flash`, `gemini-2.5-pro` (`GEMINI_API_KEY`)
  * **OpenAI**: `gpt-4o`, `gpt-4o-mini`, `o3-mini` (`OPENAI_API_KEY`)
  * **Anthropic**: `claude-3-5-sonnet`, `claude-3-7-sonnet` (`ANTHROPIC_API_KEY`)
  * **Local Ollama / DeepSeek**: `deepseek-r1:latest` (`OLLAMA_HOST`)
* Automatic failover across models and providers during API rate limits.

### 3. 🧬 AST Code Symbol Graph & Compact Context
* `SymbolIndexer` parses Python AST and TypeScript/Go/Rust regex definitions.
* Builds a compact `< 1,000 token` outline of classes, methods, endpoints, and types.
* Scales effortlessly to large 100k+ line codebases without token bloat or context truncation.

### 4. 📊 Stateful Run Continuity & Cost Telemetry
* Deterministic state engine (`StateManager`) tracking PR execution history, remediation iterations, and hard budget caps (preventing runaway CI loops).
* Automatic token usage calculation and cost estimation ($ USD) posted directly on PRs.

### 5. 🛡️ Concurrency Locks & Git Conflict Recovery
* Optimistic concurrency with exponential fetch-rebase retry loops on git push conflicts.
* Path traversal security guards preventing LLM-generated code from writing outside the workspace.
* Token and secret redaction in all CI logs.

---

## 🔌 Universal 60-Second Integration Guide

To connect `agentic-fleet` to **any repository**:

### Step 1: Add Secrets in Target Repository
In **Settings $\rightarrow$ Secrets and variables $\rightarrow$ Actions**:
* Add `GEMINI_API_KEY` (or `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`).

### Step 2: Enable PR Creation Permissions
In **Settings $\rightarrow$ Actions $\rightarrow$ General**:
* Under *Workflow permissions*, select **"Read and write permissions"** and check **"Allow GitHub Actions to create and approve pull requests"**.

### Step 3: Add Workflow File
Create `.github/workflows/agentic-sdlc.yml` in your target repository:

```yaml
name: Autonomous Agentic SDLC

on:
  issues:
    types: [opened, labeled]
  issue_comment:
    types: [created, edited]
  pull_request:
    types: [opened, synchronize, labeled]
  pull_request_review:
    types: [submitted, edited]
  pull_request_review_comment:
    types: [created, edited]
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write
  issues: write

jobs:
  agentic-orchestrator:
    name: "Autonomous SDLC Fleet"
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Target Repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Run Agentic Fleet Action
        uses: dipeshsingh2012/agentic-fleet@v1
        with:
          gemini-api-key: ${{ secrets.GEMINI_API_KEY }}
          # Or OpenAI:
          # openai-api-key: ${{ secrets.OPENAI_API_KEY }}
          # Or Anthropic Claude:
          # anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

---

## 🧪 Development & Testing

```bash
# Clone the orchestration engine
git clone https://github.com/dipeshsingh2012/agentic-fleet.git
cd agentic-fleet

# Install dependencies
pip install -r requirements.txt

# Run full test suite (75+ unit & E2E tests in < 2 seconds)
pytest -v
```
