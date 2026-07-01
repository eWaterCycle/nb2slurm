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

    def _exists_test(self) -> str:
        """A shell test (exit 0 = env exists). Matches the name as a whole path
        component so ``montecarlo`` doesn't match ``montecarlo2``."""
        return f'conda env list | grep -qE "[/ ]{self.name}([ /]|$)"'

    def _create_command(self, filename: str = "environment.yml") -> str:
        # mamba is much faster than conda; use it when available.
        return (
            "set -e; "
            # There's no TTY over ssh, so any interactive prompt would hang the
            # build forever. Belt and suspenders: set always-yes AND pipe `yes`
            # into conda (CONDA_ALWAYS_YES alone is ignored by some mamba builds
            # for the 'Confirm changes? [Y/n]' transaction prompt).
            "export CONDA_ALWAYS_YES=yes; "
            "CONDA=conda; command -v mamba >/dev/null 2>&1 && CONDA=mamba; "
            # update an existing env in place rather than hitting the interactive
            # 'Found conda-prefix ... Overwrite? [y/N]' prompt.
            f"if {self._exists_test()}; then "
            f'  echo "Updating existing environment {self.name} with $CONDA..."; '
            f"  yes | $CONDA env update -f {filename}; "
            f"else "
            f'  echo "Creating environment {self.name} with $CONDA..."; '
            f"  yes | $CONDA env create -f {filename}; "
            f"fi; "
            f"conda run -n {self.name} python -m ipykernel install --user "
            f'--name {self.kernel} --display-name "{self.kernel}"; '
            f'echo "Environment {self.name} ready; kernel {self.kernel} registered."'
        )

    def _remove_command(self) -> str:
        return (
            "export CONDA_ALWAYS_YES=yes; "
            f'echo "Removing environment {self.name} and kernel {self.kernel}..."; '
            # `|| true`: removing a non-existent env/kernel is not an error here
            f"conda env remove -n {self.name} || true; "
            f"jupyter kernelspec remove -f {self.kernel} 2>/dev/null || true; "
            f'echo "Removed {self.name}."'
        )

    def exists(
        self,
        ssh: Optional[SSHConfig] = None,
        project_dir: str | Path = ".",
    ) -> bool:
        """Return True if the conda env already exists — on the HPC (ssh) or locally."""
        return run_shell(self._exists_test(), ssh, str(project_dir)).exit_status == 0

    def remove(
        self,
        ssh: Optional[SSHConfig] = None,
        project_dir: str | Path = ".",
        stream: bool = True,
    ) -> CommandResult:
        """Delete the conda env and its Jupyter kernel — on the HPC (ssh) or locally.

        Safe to call when nothing is there yet (a missing env/kernel is ignored).
        Use it to recover from a half-built env or to force a clean rebuild.
        """
        return run_shell(self._remove_command(), ssh, str(project_dir), stream=stream).check()

    def create(
        self,
        ssh: Optional[SSHConfig] = None,
        project_dir: str | Path = ".",
        filename: str = "environment.yml",
        stream: bool = True,
        overwrite: bool = False,
    ) -> CommandResult:
        """Create the env and register the kernel — on the HPC (ssh) or locally.

        Writes ``environment.yml`` first if it is missing. If the env already
        exists it is *updated* in place; pass ``overwrite=True`` to delete and
        rebuild it from scratch. ``stream=True`` (the default) echoes conda/pip
        output live, since a solve + downloads can take minutes and would
        otherwise look like a hang.
        """
        if not (Path(project_dir) / filename).exists():
            self.write(project_dir, filename)
        if overwrite:
            self.remove(ssh=ssh, project_dir=project_dir, stream=stream)
        command = self._create_command(filename)
        return run_shell(command, ssh, str(project_dir), stream=stream).check()
