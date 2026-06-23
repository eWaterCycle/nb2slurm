"""The per-run settings file, as an object.

The paper's notebook structure has the *first* notebook write a settings file
(JSON) that every later notebook reads. This keeps the varying parameters in one
place: only notebook 0 is parameterised by papermill, the rest just load it.

    import nb2slurm

    # first notebook (parameterised by nb2slurm):
    nb2slurm.Settings.write(outdir, {"region_id": region_id, "outdir": outdir})

    # every later notebook:
    settings = nb2slurm.Settings.load(settings_path)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


class Settings:
    """Read/write the per-run ``settings.json``."""

    filename = "settings.json"

    @staticmethod
    def write(outdir: str | Path, settings: Mapping[str, Any]) -> Path:
        """Write ``settings`` to ``<outdir>/settings.json`` and return the path.

        Call this from your first notebook. ``outdir`` is supplied to that
        notebook by the generated runner, so you never hardcode a path.
        """
        outdir = Path(outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / Settings.filename
        with open(path, "w") as f:
            json.dump(dict(settings), f, indent=2)
        return path

    @staticmethod
    def load(settings_path: str | Path) -> dict[str, Any]:
        """Load a settings file. Call this at the top of every later notebook."""
        with open(settings_path) as f:
            return json.load(f)
