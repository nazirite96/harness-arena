#!/usr/bin/env bash
# Create the uv venv with the pinned Harbor and the arena CLI.
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --all-extras
uv run harbor --version
uv run arena env
