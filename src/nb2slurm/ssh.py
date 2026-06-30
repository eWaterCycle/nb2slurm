"""Minimal SSH transport so the managing notebook can drive SLURM with no CLI.

This mimics the command line / ssh that the paper says should be hidden from the
user: sbatch/squeue/scancel run on the cluster, but the user only writes Python.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CommandResult:
    command: str
    exit_status: int
    stdout: str
    stderr: str

    def check(self) -> "CommandResult":
        if self.exit_status != 0:
            raise RuntimeError(
                f"Remote command failed ({self.exit_status}): {self.command}\n{self.stderr}"
            )
        return self


@dataclass
class SSHConfig:
    """Connection details for the HPC login node.

    Provide either ``key_filename`` or ``password`` (or rely on an agent/known
    config). ``remote_dir`` is the project directory on the cluster that the
    generated scripts live in; commands are run from there.
    """

    host: str
    user: str
    remote_dir: str
    port: int = 22
    key_filename: Optional[str] = None
    password: Optional[str] = None
    extra_connect_kwargs: dict = field(default_factory=dict)

    def key_path(self) -> Optional[str]:
        """The private key path with ``~`` expanded, or ``None`` if unset.

        paramiko opens ``key_filename`` directly and does **not** expand ``~``,
        so we resolve it here (e.g. ``~/.ssh/id_rsa`` -> the absolute path).
        """
        return os.path.expanduser(self.key_filename) if self.key_filename else None

    def rsync_ssh(self) -> str:
        """The ``-e`` transport string rsync should use (ssh + port + key)."""
        parts = ["ssh"]
        if self.port != 22:
            parts += ["-p", str(self.port)]
        if self.key_filename:
            parts += ["-i", self.key_path()]
        return " ".join(parts)

    def rsync_target(self, subpath: str = "") -> str:
        """A ``user@host:remote_dir/<subpath>`` spec for rsync."""
        base = self.remote_dir.rstrip("/")
        return f"{self.user}@{self.host}:{base}/{subpath}" if subpath else f"{self.user}@{self.host}:{base}/"

    def run(self, command: str, cwd: Optional[str] = None,
            stream: bool = False) -> CommandResult:
        """Run a single command on the cluster and return its result.

        Output is drained continuously while the command runs, so a chatty
        command (``conda env create``, ``pip install``) can't fill paramiko's
        channel window and deadlock against ``recv_exit_status``. Pass
        ``stream=True`` to also echo output live — useful for long-running
        builds where you'd otherwise see nothing until they finish.
        """
        import paramiko  # imported lazily so the package imports without a cluster

        cwd = cwd or self.remote_dir
        wrapped = f"cd {cwd} && {command}" if cwd else command

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=self.host,
                port=self.port,
                username=self.user,
                key_filename=self.key_path(),
                password=self.password,
                **self.extra_connect_kwargs,
            )
            chan = client.get_transport().open_session()
            chan.exec_command(wrapped)

            out_parts: list[str] = []
            err_parts: list[str] = []

            def _drain() -> bool:
                got = False
                while chan.recv_ready():
                    chunk = chan.recv(32768).decode("utf-8", "replace")
                    out_parts.append(chunk)
                    if stream:
                        print(chunk, end="", flush=True)
                    got = True
                while chan.recv_stderr_ready():
                    chunk = chan.recv_stderr(32768).decode("utf-8", "replace")
                    err_parts.append(chunk)
                    if stream:
                        print(chunk, end="", flush=True)
                    got = True
                return got

            # keep reading so the remote side never blocks on a full window
            while not chan.exit_status_ready():
                if not _drain():
                    time.sleep(0.05)
            while _drain():  # whatever is left after exit
                pass
            status = chan.recv_exit_status()
        finally:
            client.close()
        return CommandResult(wrapped, status, "".join(out_parts), "".join(err_parts))


def run_shell(command: str, ssh: Optional[SSHConfig] = None,
              cwd: str = ".", stream: bool = False) -> CommandResult:
    """Run a shell command on the cluster (via ``ssh``) or locally (subprocess).

    Shared by Workflow and Environment so the ssh-vs-local branch lives in one
    place. ``stream=True`` echoes output live (for long-running commands).
    """
    if ssh is not None:
        return ssh.run(command, stream=stream)
    if stream:
        proc = subprocess.Popen(command, shell=True, cwd=str(cwd), text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        parts: list[str] = []
        for line in proc.stdout:  # tee: capture and echo
            parts.append(line)
            print(line, end="", flush=True)
        proc.wait()
        return CommandResult(command, proc.returncode, "".join(parts), "")
    proc = subprocess.run(command, shell=True, cwd=str(cwd),
                          capture_output=True, text=True)
    return CommandResult(command, proc.returncode, proc.stdout, proc.stderr)
