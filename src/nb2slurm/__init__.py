"""nb2slurm: scale a single-subject notebook workflow to many subjects on SLURM.

The public surface is intentionally tiny so the whole workflow can be driven
from a notebook with no command line:

    import nb2slurm

    wf = nb2slurm.Workflow(
        name="square",
        notebooks=["notebooks/0_settings.ipynb", "notebooks/1_compute.ipynb"],
        kernel="python3",
        varying=["item_id"],
        resources=dict(nodes=1, cpus=2, time="00:10:00"),
    )
    wf.build()                       # render scripts/ into the project
    wf.submit([1, 2, 3], ssh=cfg)    # sbatch one job per item, over SSH
    wf.status(ssh=cfg)               # squeue -> list of dicts
    wf.cancel(ssh=cfg)              # scancel the jobs we submitted

Inside the notebooks themselves, use the Settings helper:

    nb2slurm.Settings.write(outdir, {...})   # first notebook
    settings = nb2slurm.Settings.load(path)  # later notebooks
"""

from .workflow import Workflow
from .environment import Environment
from .ssh import SSHConfig
from .settings import Settings
from .done import Done
from .structure import Structure
from .config import save_config, load_config

__all__ = ["Workflow", "Environment", "SSHConfig", "Settings", "Done",
           "Structure", "save_config", "load_config"]
__version__ = "0.1.0"
