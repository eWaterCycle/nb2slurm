"""Idempotent 'already done?' bookkeeping, as an object.

Generalised from cci.py: a single CSV records which subjects have completed, so
re-submitting the whole set skips finished work. A file lock makes it safe when
many jobs write concurrently on a shared filesystem.

    done = nb2slurm.Done("done/done.csv")
    if done.is_done(key):
        ...
    done.mark(key)
"""

from __future__ import annotations

import csv
from pathlib import Path

from filelock import FileLock

LOCK_TIMEOUT = 60 * 3


class Done:
    """A CSV ledger of completed subjects, with concurrency-safe writes."""

    def __init__(self, csv_file: str | Path):
        self.csv_file = Path(csv_file)

    @property
    def _lock(self) -> str:
        return str(self.csv_file) + ".lock"

    def is_done(self, key: str) -> bool:
        """Return True if ``key`` is already recorded."""
        if not self.csv_file.exists():
            return False
        with FileLock(self._lock, timeout=LOCK_TIMEOUT):
            with open(self.csv_file, newline="") as f:
                reader = csv.reader(f)
                next(reader, None)  # header
                for row in reader:
                    if row and row[0] == str(key):
                        return True
        return False

    def mark(self, key: str) -> None:
        """Record ``key`` as done (no-op if already present)."""
        self.csv_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.csv_file.exists():
            with open(self.csv_file, "w", newline="") as f:
                csv.writer(f).writerow(["key"])
        with FileLock(self._lock, timeout=LOCK_TIMEOUT):
            existing = set()
            with open(self.csv_file, newline="") as f:
                reader = csv.reader(f)
                next(reader, None)
                for row in reader:
                    if row:
                        existing.add(row[0])
            if str(key) not in existing:
                with open(self.csv_file, "a", newline="") as f:
                    csv.writer(f).writerow([key])
                print(f"Marked {key} as done.")
            else:
                print(f"{key} already recorded as done.")
