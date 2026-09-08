#!/usr/bin/env bash
# Install the pinned opencode version on this host (for operators / smoke tests).
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=$(grep '^OPENCODE_VERSION=' versions.lock | cut -d= -f2)
echo "installing opencode-ai@${VERSION} via npm -g"
npm install -g "opencode-ai@${VERSION}"
opencode --version
