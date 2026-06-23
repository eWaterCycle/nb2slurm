"""Save / load a run's control settings to one JSON file.

The config notebook builds a Workflow (+ SSHConfig) and calls ``save_config``;
the build / submit / sync notebooks call ``load_config`` to get them back. This
keeps a single source of truth on disk, so the notebooks never duplicate settings.

    # in 0_config.ipynb
    nb2slurm.save_config("control_config.json", workflow=wf, ssh=cfg)

    # in 1_build / 2_submit / 3_sync
    wf, cfg = nb2slurm.load_config("control_config.json")
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .environment import Environment
from .ssh import SSHConfig
from .workflow import Workflow


def _workflow_to_dict(wf: Workflow) -> dict:
    d = asdict(wf)               # recurses Environment, resources, mounts
    d.pop("submitted_jobs", None)  # runtime state, not configuration
    return d


def _workflow_from_dict(d: dict) -> Workflow:
    d = dict(d)
    d.pop("submitted_jobs", None)
    env = d.pop("environment", None)
    return Workflow(**d, environment=Environment(**env) if env else None)


def _ssh_to_dict(ssh: SSHConfig) -> dict:
    d = asdict(ssh)
    d.pop("password", None)      # never persist secrets to disk
    return d


def save_config(path: str | Path, *, workflow: Workflow,
                ssh: Optional[SSHConfig] = None) -> Path:
    """Write the workflow (and optional SSH) config to ``path`` as JSON."""
    data = {"workflow": _workflow_to_dict(workflow)}
    if ssh is not None:
        data["ssh"] = _ssh_to_dict(ssh)
    path = Path(path)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load_config(path: str | Path) -> tuple[Workflow, Optional[SSHConfig]]:
    """Read a config file back into ``(workflow, ssh)``.

    ``ssh`` is ``None`` if none was saved. Passwords are never stored, so set
    ``ssh.password`` yourself afterwards if your cluster needs one.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    wf = _workflow_from_dict(data["workflow"])
    ssh = SSHConfig(**data["ssh"]) if data.get("ssh") else None
    return wf, ssh
