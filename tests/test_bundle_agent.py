from arena_harness.bundle_agent import install_bundle_command


def test_install_command_expands_home_and_verifies_layout():
    cmd = install_bundle_command()
    assert "'~" not in cmd and '"~' not in cmd  # a quoted tilde would create a literal '~' directory
    assert 'CFG="$HOME/.config/opencode"' in cmd
    assert "/testbed/AGENTS.md" in cmd
    assert "bun install" in cmd
    assert 'test -d "$CFG"/agents' in cmd
