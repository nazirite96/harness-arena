"""Queue consumer.

  python -m worker.main dev       loop: run queued dev submissions on datasets/dev as they arrive
  python -m worker.main official  one nightly batch: run every queued official submission on datasets/public
                                  (cron: 0 23 * * *  KST)
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime

from arena.config import load_settings
from arena.db import Store, official_day_for
from worker.runner import run_submission


def dev_loop(poll_sec: int = 10) -> None:
    s = load_settings()
    store = Store(s.db_path)
    print("[worker] dev loop started")
    while True:
        sub = store.next_queued("dev")
        if not sub:
            time.sleep(poll_sec)
            continue
        print(f"[worker] dev submission #{sub['id']}")
        try:
            run_submission(store, s, sub, dataset="dev", n_concurrent=min(5, s.n_concurrent))
        except Exception as exc:
            print(f"[worker] dev submission #{sub['id']} failed: {exc}")


def official_batch(day: str | None = None) -> int:
    s = load_settings()
    store = Store(s.db_path)
    day = day or official_day_for(datetime.now(UTC))
    subs = store.queued("official", official_day=day)
    print(f"[worker] official batch {day}: {len(subs)} submission(s)")
    failures = 0
    for sub in subs:
        try:
            run_submission(store, s, sub, dataset="public")
        except Exception as exc:
            failures += 1
            print(f"[worker] official submission #{sub['id']} failed: {exc}")
    return failures


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "dev"
    if mode == "dev":
        dev_loop()
    elif mode == "official":
        raise SystemExit(1 if official_batch(sys.argv[2] if len(sys.argv) > 2 else None) else 0)
    else:
        raise SystemExit(f"unknown mode {mode}")
