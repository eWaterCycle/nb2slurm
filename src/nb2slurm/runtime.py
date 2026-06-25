"""Detect whether the current notebook is running under nb2slurm on a cluster.

Checking ``Path.home()`` for a username is fragile (breaks for other users, can't
tell a cloud VM from a laptop). Instead we look at environment variables that are
only present in a batch job:

* the ``SLURM_*`` variables SLURM sets in every job, and
* the ``NB2SLURM`` sentinel that the generated ``job.slurm`` exports (so this also
  works on non-SLURM batch setups that run nb2slurm's job script).

Use it in your notebooks for the things that genuinely differ between
interactive and batch runs — machine-specific data paths, skipping ``!pip install``:

    import nb2slurm
    if nb2slurm.on_hpc():
        data_dir = "/project/ewater/Data"
    else:
        data_dir = "/data/shared"

You do *not* need it for importing helpers from ``scripts/`` — a
``try/except ImportError`` with ``sys.path.append(".")`` works in both places.
"""

from __future__ import annotations

import os

# present inside a SLURM job; NB2SLURM is exported by the generated job.slurm
_BATCH_ENV_VARS = ("NB2SLURM", "SLURM_JOB_ID", "SLURM_JOBID")


def on_hpc() -> bool:
    """Return True if running inside an nb2slurm/SLURM batch job."""
    return any(var in os.environ for var in _BATCH_ENV_VARS)
