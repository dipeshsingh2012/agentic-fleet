#!/usr/bin/env bash
# 🛸 Agentic Fleet Instant Installer for Any Repository
set -e

echo "🛸 Initializing Agentic Fleet for this repository..."
mkdir -p .github/workflows

WORKFLOW_FILE=".github/workflows/agentic-sdlc.yml"

cat << 'YAML' > "$WORKFLOW_FILE"
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
YAML

chmod +x "$0" 2>/dev/null || true

echo "✅ Created $WORKFLOW_FILE"
echo ""
echo "🎉 Agentic Fleet is ready! Just 2 steps to activate:"
echo "  1. Add GEMINI_API_KEY (or OPENAI_API_KEY / ANTHROPIC_API_KEY) in Repo Settings -> Secrets and variables -> Actions"
echo "  2. In Settings -> Actions -> General: Under 'Workflow permissions', select 'Read and write' and check 'Allow GitHub Actions to create and approve pull requests'"
echo ""
echo "🚀 Open an issue or comment '@fleet' on any PR to engage the 5-Agent SDLC!"
