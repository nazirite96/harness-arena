"""PRD §0.5 / §7.4: private task ids must never appear in public paths."""

import json
from pathlib import Path

from arena.config import REPO_ROOT


def test_private_dataset_dir_absent():
    assert not (REPO_ROOT / "datasets" / "private").exists()


def test_public_and_private_ids_disjoint():
    public = REPO_ROOT / "datasets" / "public" / "task_ids.json"
    private = Path.home() / ".cache" / "harness-arena" / "private_task_ids.json"
    if not (public.exists() and private.exists()):
        return  # populated by `arena curate` (M3)
    pub = set(json.loads(public.read_text()))
    priv = set(json.loads(private.read_text()))
    assert not (pub & priv)
