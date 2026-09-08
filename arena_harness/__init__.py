"""Harbor agent adapters for Harness Arena.

`OpenCodeBundleAgent` (M2) installs a pinned opencode, injects a team's config
bundle, forces the proxy model, and runs the bundle's main agent headlessly.
Trajectory parsing is inherited from Harbor's builtin OpenCode agent.
"""

from arena_harness.bundle_agent import OpenCodeBundleAgent

__all__ = ["OpenCodeBundleAgent"]
