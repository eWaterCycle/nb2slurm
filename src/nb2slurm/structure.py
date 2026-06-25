"""The job/output hierarchy, described as one nested JSON.

A single nested dict is the source of truth for a run. Each root-to-leaf path is
one SLURM job, and the output directory mirrors that path. Dict levels are the
``varying`` dimensions; a list at the bottom means several jobs that share the
same parent path; ``None``/``[]``/``{}`` means the path ends there.

    import nb2slurm

    spec = {
        "NL": {"123": ["ssp126", "ssp245"]},
        "DE": {"789": ["ssp585"]},
    }
    struct = nb2slurm.Structure(spec)          # or Structure.from_json("jobs.json")

    struct.jobs()
    # [("NL", "123", "ssp126"), ("NL", "123", "ssp245"), ("DE", "789", "ssp585")]

    struct.build("output")                      # creates output/NL/123/ssp126, ... and returns paths

The same file is read by ``Workflow.submit`` to decide which jobs to launch, so
the directory tree and the job list can never drift apart.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


class Structure:
    """A nested-dict description of the jobs (and their output folders) for a run."""

    def __init__(self, spec: Mapping[str, Any] | None = None):
        if spec is not None and not isinstance(spec, Mapping):
            raise TypeError("Structure spec must be a dict (nested job/output hierarchy)")
        self.spec: dict[str, Any] = dict(spec or {})

    @classmethod
    def from_json(cls, path: str | Path) -> "Structure":
        """Load the hierarchy from a JSON file."""
        with open(path) as f:
            return cls(json.load(f))

    # ----- internal ----------------------------------------------------------
    @staticmethod
    def _walk(node: Any, prefix: str) -> list[str]:
        """Flatten a node into a list of relative root-to-leaf paths."""
        if node is None or node == {} or node == []:
            return [prefix] if prefix else []
        if isinstance(node, Mapping):
            leaves: list[str] = []
            for name, child in node.items():
                sub = f"{prefix}/{name}" if prefix else str(name)
                leaves.extend(Structure._walk(child, sub))
            return leaves
        if isinstance(node, (list, tuple, set)):
            leaves = []
            for item in node:
                sub = f"{prefix}/{item}" if prefix else str(item)
                leaves.extend(
                    Structure._walk(item, prefix) if isinstance(item, (Mapping, list, tuple, set))
                    else [sub]
                )
            return leaves
        # a bare scalar leaf
        sub = f"{prefix}/{node}" if prefix else str(node)
        return [sub]

    def _leaves(self) -> list[str]:
        """Ordered, de-duplicated list of relative leaf paths."""
        return list(dict.fromkeys(self._walk(self.spec, "")))

    # ----- public ------------------------------------------------------------
    def jobs(self) -> list[tuple[str, ...]]:
        """Return one tuple of path components per job (root-to-leaf)."""
        return [tuple(rel.split("/")) for rel in self._leaves()]

    def paths(self, base: str | Path = ".") -> dict[str, Path]:
        """Return ``{relative/path: Path}`` for every leaf. No I/O."""
        base = Path(base)
        return {rel: base.joinpath(*rel.split("/")) for rel in self._leaves()}

    def build(self, base: str | Path = ".") -> dict[str, Path]:
        """Create every leaf folder under ``base`` and return ``{relative/path: Path}``."""
        paths = self.paths(base)
        for p in paths.values():
            p.mkdir(parents=True, exist_ok=True)
        return paths
