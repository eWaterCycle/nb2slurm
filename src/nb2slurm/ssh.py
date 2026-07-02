"""Minimal SSH transport so the managing notebook can drive SLURM with no CLI.

This mimics the command line / ssh that the paper says should be hidden from the
user: sbatch/squeue/scancel run on the cluster, but the user only writes Python.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple


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

    Provide a ``key_filename`` (or rely on an agent/known config). ``remote_dir``
    is the project directory on the cluster that the generated scripts live in;
    commands are run from there.

    Auth notes:

    * ``passphrase`` decrypts a passphrase-protected private key (this is what
      Snellius and most clusters use — the "password" you type is your key's
      passphrase, not a server account password).
    * ``password`` is for actual password authentication (rare on HPC).
    * Best of all is loading the key into ``ssh-agent`` (``ssh-add``): then you
      need neither here, and rsync (``push``/``pull``) also works without prompts.
    """

    host: str
    user: str
    remote_dir: str
    port: int = 22
    key_filename: Optional[str] = None
    password: Optional[str] = None
    passphrase: Optional[str] = None
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

    def _connect(self):
        """Open an authenticated paramiko client.

        Translates paramiko's encrypted-key error into a clear hint: if the key
        needs a passphrase and none got it unlocked, tell the user to pass
        ``passphrase=`` (or use ssh-agent) rather than surfacing a cryptic error.
        """
        import paramiko  # imported lazily so the package imports without a cluster

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        # bound the connect so an unreachable host fails fast instead of hanging
        # forever; the user can override via extra_connect_kwargs.
        opts = {"timeout": 30, "auth_timeout": 30, "banner_timeout": 30}
        if self.key_filename:
            # An explicit key means "use this one" (plus ssh-agent). Don't also
            # scan ~/.ssh for other default keys: a stray/legacy id_dsa there makes
            # paramiko crash on modern cryptography backends
            # ("q must be exactly 160, 224, or 256 bits long"). Agent use stays on.
            opts["look_for_keys"] = False
        opts.update(self.extra_connect_kwargs)
        try:
            client.connect(
                hostname=self.host,
                port=self.port,
                username=self.user,
                key_filename=self.key_path(),
                password=self.password,
                passphrase=self.passphrase,
                **opts,
            )
        except paramiko.PasswordRequiredException as e:
            client.close()
            raise paramiko.PasswordRequiredException(
                f"private key {self.key_path()!r} is encrypted with a passphrase. "
                "Pass it with SSHConfig(passphrase=...), or (recommended) load the "
                "key into ssh-agent first with `ssh-add` so rsync push/pull work too."
            ) from e
        except Exception:
            client.close()
            raise
        return client

    def test_connection(self, command: str = "hostname && whoami") -> bool:
        """Try to connect and run a trivial command; print a clear ok/fail.

        A quick first check before push/submit. Returns True on success. On an
        encrypted key it prints the passphrase hint from ``_connect``.
        """
        # show the port only when it's non-default, so the message reads like a
        # normal ssh target (host:22 looks like a connection string and confuses)
        target = self.user + "@" + self.host + (f" (port {self.port})" if self.port != 22 else "")
        try:
            res = self.run(command, cwd="~")  # ~, not remote_dir (may not exist yet)
        except Exception as e:
            print(f"FAIL: could not connect to {target}\n  {type(e).__name__}: {e}")
            return False
        if res.exit_status == 0:
            print(f"OK: connected to {target}\n{res.stdout.strip()}")
            return True
        print(f"FAIL: connected to {target} but the command failed\n  {res.stderr.strip()}")
        return False

    def run(self, command: str, cwd: Optional[str] = None,
            stream: bool = False) -> CommandResult:
        """Run a single command on the cluster and return its result.

        Output is drained continuously while the command runs, so a chatty
        command (``conda env create``, ``pip install``) can't fill paramiko's
        channel window and deadlock against ``recv_exit_status``. Pass
        ``stream=True`` to also echo output live — useful for long-running
        builds where you'd otherwise see nothing until they finish.
        """
        cwd = cwd or self.remote_dir
        wrapped = f"cd {cwd} && {command}" if cwd else command

        client = self._connect()
        try:
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


def _pub_path(path: str) -> Path:
    """The ``.pub`` file for a key path (accepts the private path or the .pub)."""
    p = Path(os.path.expanduser(path))
    return p if p.suffix == ".pub" else Path(str(p) + ".pub")


def public_key(path: str = "~/.ssh/id_rsa") -> str:
    """Return the public key line for ``path`` (reads ``<path>.pub``).

    This is the text you paste into your HPC — ``print(nb2slurm.public_key())``
    then copy it into the cluster's key-upload page (or ``~/.ssh/authorized_keys``
    on a login node, if your HPC lets you edit it directly).
    """
    return _pub_path(path).read_text().strip()


def generate_key(path: str = "~/.ssh/id_rsa", bits: int = 4096,
                 comment: Optional[str] = None, overwrite: bool = False,
                 show: bool = True) -> Tuple[Path, Path]:
    """Create an RSA SSH keypair at ``path`` (+ ``<path>.pub``).

    Returns ``(private_path, public_path)``. The private key is written 0600 and
    the public key in ``authorized_keys`` format. An existing key is left alone
    unless ``overwrite=True``, so this is safe to call repeatedly. Point your
    ``SSHConfig(key_filename=...)`` at ``path``.

    nb2slurm can't install the key for you — many HPCs disable password login, so
    there's no way in. With ``show=True`` (default) the public key is printed so
    you can copy it into your cluster's key-upload page (or its
    ``~/.ssh/authorized_keys``); ``nb2slurm.public_key(path)`` reprints it later.
    """
    import paramiko  # lazy: keep the package importable without a crypto backend

    priv = Path(os.path.expanduser(path))
    pub = _pub_path(path)
    if priv.exists() and not overwrite:
        if show:
            print(f"key already exists at {priv}; its public key is:\n\n{public_key(path)}")
        return priv, pub
    priv.parent.mkdir(parents=True, exist_ok=True)

    key = paramiko.RSAKey.generate(bits)
    key.write_private_key_file(str(priv))
    pub.write_text(f"ssh-rsa {key.get_base64()} {comment or ''}".strip() + "\n")
    for p, mode in ((priv, 0o600), (pub, 0o644)):
        try:
            os.chmod(p, mode)
        except OSError:
            pass  # Windows without POSIX perms; OpenSSH there enforces via ACLs
    if show:
        print(
            f"created SSH key: {priv} (private) and {pub} (public)\n\n"
            "Add the PUBLIC key below to your HPC - via its key-upload page, or by\n"
            "appending it to ~/.ssh/authorized_keys on a login node. nb2slurm can't\n"
            "do this step for you (clusters usually disable password login):\n\n"
            f"{public_key(path)}"
        )
    return priv, pub


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
