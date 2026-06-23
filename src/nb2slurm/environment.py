"""Create the conda environment + Jupyter kernel the workflow runs in.

Most users of nb2slurm are not Linux/conda experts, but the generated SLURM job
does ``conda activate <env>`` and papermill needs a *registered Jupyter kernel*
to execute the notebooks. This module writes an ``environment.yml`` and creates
the environment + kernel on the cluster (or locally), so the user never touches
the command line.

    from nb2slurm import Environment

    env = Environment(
        name="myenv",
        kernel="myenv",                       # must match Workflow(kernel=...)
        conda_packages=["xarray", "numpy"],
        pip_packages=["nb2slurm", "ewatercycle"],
    )
    env.write()                # -> environment.yml
    env.create(ssh=cfg)        # build env + register kernel on the HPC
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .ssh import CommandResult, SSHConfig, run_shell


@dataclass
class Environment:
    name: str
    kernel: str
    python: str = "3.11"
    channels: list[str] = field(default_factory=lambda: ["conda-forge"])
    conda_packages: list[str] = field(default_factory=list)
    pip_packages: list[str] = field(default_factory=lambda: ["nb2slurm"])

    def to_yaml(self) -> str:
        """Render an ``environment.yml`` for conda/mamba."""
        lines = [f"name: {self.name}", "channels:"]
        lines += [f"  - {c}" for c in self.channels]
        lines.append("dependencies:")
        lines.append(f"  - python={self.python}")
        lines.append("  - pip")
        lines.append("  - ipykernel")  # required so papermill can run the notebooks
        lines += [f"  - {p}" for p in self.conda_packages]
        if self.pip_packages:
            lines.append("  - pip:")
            lines += [f"      - {p}" for p in self.pip_packages]
        return "\n".join(lines) + "\n"

    def write(self, project_dir: str | Path = ".", filename: str = "environment.yml") -> Path:
        """Write the ``environment.yml`` into the project directory."""
        path = Path(project_dir) / filename
        path.write_text(self.to_yaml(), encoding="utf-8")
        return path

    def _create_command(self, filename: str = "environment.yml") -> str:
        # mamba is much faster than conda; use it when available.
        return (
            "set -e; "
            "CONDA=conda; command -v mamba >/dev/null 2>&1 && CONDA=mamba; "
            f'echo "Creating environment {self.name} with $CONDA..."; '
            f"$CONDA env create -f {filename} || $CONDA env update -f {filename}; "
            f"conda run -n {self.name} python -m ipykernel install --user "
            f'--name {self.kernel} --display-name "{self.kernel}"; '
            f'echo "Environment {self.name} ready; kernel {self.kernel} registered."'
        )

    def create(
        self,
        ssh: Optional[SSHConfig] = None,
        project_dir: str | Path = ".",
        filename: str = "environment.yml",
    ) -> CommandResult:
        """Create the env and register the kernel — on the HPC (ssh) or locally.

        Writes ``environment.yml`` first if it is missing.
        """
        if not (Path(project_dir) / filename).exists():
            self.write(project_dir, filename)
        command = self._create_command(filename)
        return run_shell(command, ssh, str(project_dir)).check()
