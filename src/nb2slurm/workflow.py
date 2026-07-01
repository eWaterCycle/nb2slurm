"""The single public class: Workflow.

A Workflow describes a notebook chain plus the resources it needs. ``build()``
renders the runner + SLURM + submit/cancel scripts; ``submit()/status()/cancel()``
drive SLURM over SSH (or locally) so the whole thing works from a notebook.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence, Union

from .environment import Environment
from .render import write_rendered
from .ssh import CommandResult, SSHConfig, run_shell
from .structure import Structure

# local cruft never worth uploading (the output dirs are excluded dynamically in push)
PUSH_EXCLUDES = [".git", "__pycache__", ".ipynb_checkpoints"]

Item = Union[Any, Sequence[Any], Mapping[str, Any]]


@dataclass
class Workflow:
    name: str
    notebooks: list[str]
    kernel: str
    varying: list[str]
    resources: dict = field(default_factory=lambda: {"nodes": 1, "cpus": 1, "time": "01:00:00"})
    project_dir: str = "."
    conda_env: Optional[str] = None
    setup: list[str] = field(default_factory=list)  # raw shell lines run before the job, e.g. `module load Python/3.11`
    mounts: list[dict] = field(default_factory=list)
    runner_name: str = "run_workflow.py"
    concurrency: int = 3
    output_dir: str = "output"        # root for per-subject outputs (relative to project root)
    done_csv: str = "done/done.csv"   # idempotency ledger (relative to project root)
    jobs_json: str = "jobs.json"      # nested JSON describing the jobs to run (one leaf path = one job)
    environment: Optional[Environment] = None  # primary conda env + kernel to run in
    kernels: dict = field(default_factory=dict)  # per-notebook kernel overrides {notebook_path: kernel}
    extra_environments: list[Environment] = field(default_factory=list)  # extra envs to also create

    # job ids we have submitted this session (used by status/cancel)
    submitted_jobs: list[str] = field(default_factory=list, repr=False)

    def __post_init__(self):
        # If an Environment is given, keep names consistent so the SLURM job's
        # `conda activate` and papermill's kernel match what was actually created.
        if self.environment is not None:
            if self.conda_env is None:
                self.conda_env = self.environment.name
            if self.conda_env != self.environment.name:
                raise ValueError(
                    f"conda_env={self.conda_env!r} != environment.name={self.environment.name!r}"
                )
            if self.kernel != self.environment.kernel:
                raise ValueError(
                    f"kernel={self.kernel!r} != environment.kernel={self.environment.kernel!r}"
                )
        # kernel overrides must point at notebooks actually in the chain
        unknown = set(self.kernels) - set(self.notebooks)
        if unknown:
            raise ValueError(f"kernels keys not in notebooks: {sorted(unknown)}")

    # ----- paths -------------------------------------------------------------
    @property
    def _project(self) -> Path:
        return Path(self.project_dir)

    @property
    def scripts_dir(self) -> Path:
        return self._project / "scripts"

    @property
    def runner_path(self) -> Path:
        return self.scripts_dir / self.runner_name

    @property
    def slurm_path(self) -> Path:
        return self.scripts_dir / "job.slurm"

    # ----- helpers -----------------------------------------------------------
    def _context(self) -> dict:
        v = self.varying
        return {
            "name": self.name,
            "notebooks": self.notebooks,
            "kernel": self.kernel,
            "kernels": self.kernels,
            "varying": v,
            "varying_env": [name.upper() for name in v],
            "resources": self.resources,
            "conda_env": self.conda_env,
            "setup": self.setup,
            "mounts": self.mounts,
            "runner_name": self.runner_name,
            "concurrency": self.concurrency,
            "output_dir": self.output_dir,
            "done_csv": self.done_csv,
            # pre-built bash fragments so the shell templates stay readable
            "read_vars": " ".join(v),
            "first_var_ref": "${%s}" % v[0],
            "key_expr": "_".join("${%s}" % name for name in v),
            "outdir_expr": self.output_dir.rstrip("/") + "/" + "/".join("${%s}" % name for name in v),
            "export_expr": ",".join("%s=${%s}" % (name.upper(), name) for name in v),
        }

    def _normalise_item(self, item: Item) -> dict[str, str]:
        """Turn an item into {varying_name: str_value}."""
        if isinstance(item, Mapping):
            values = {k: str(item[k]) for k in self.varying}
        elif isinstance(item, (list, tuple)):
            if len(item) != len(self.varying):
                raise ValueError(f"item {item!r} does not match varying={self.varying}")
            values = {k: str(v) for k, v in zip(self.varying, item)}
        else:
            if len(self.varying) != 1:
                raise ValueError(
                    f"scalar item {item!r} but varying has {len(self.varying)} names"
                )
            values = {self.varying[0]: str(item)}
        return values

    @staticmethod
    def _key(values: Mapping[str, str]) -> str:
        return "_".join(values.values())

    def _outdir(self, values: Mapping[str, str]) -> str:
        return self.output_dir.rstrip("/") + "/" + "/".join(values.values())

    # ----- build -------------------------------------------------------------
    def build(self) -> dict[str, Path]:
        """Render the generated scripts into ``<project>/scripts/``."""
        ctx = self._context()
        written = {
            "runner": write_rendered("run_workflow.py.j2", self.runner_path, ctx),
            "slurm": write_rendered("job.slurm.j2", self.slurm_path, ctx),
            "submit_batch": write_rendered("submit_batch.sh.j2", self.scripts_dir / "submit_batch.sh", ctx, executable=True),
            "submit_jobs": write_rendered("submit_jobs.sh.j2", self.scripts_dir / "submit_jobs.sh", ctx, executable=True),
            "cancel": write_rendered("cancel_jobs.sh.j2", self.scripts_dir / "cancel_jobs.sh", ctx, executable=True),
        }
        structure = self.scripts_dir / "structure.json"
        structure.write_text(json.dumps(ctx, indent=2, default=str), encoding="utf-8")
        written["structure"] = structure
        if self.environment is not None:
            written["environment"] = self.environment.write(self.project_dir)
        # the bash scripts loop over a flat jobs.txt; generate it from jobs.json
        if (self._project / self.jobs_json).exists():
            written["jobs_txt"] = self.write_jobs_txt()
        return written

    def write_jobs_txt(self, jobs_json: Optional[str] = None) -> Path:
        """Flatten the jobs JSON into ``scripts/jobs.txt`` (one job per line).

        This is what the generated bash submitters read, so they never have to
        parse JSON. The order matches ``varying``.
        """
        jobs = self.jobs_from_json(jobs_json)
        path = self.scripts_dir / "jobs.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# one job per line, values: " + " ".join(self.varying)]
        lines += [" ".join(job) for job in jobs]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def _environments(self) -> list[Environment]:
        envs = ([self.environment] if self.environment else []) + list(self.extra_environments)
        if not envs:
            raise ValueError("no environment configured on this Workflow")
        return envs

    def create_environment(self, ssh: Optional[SSHConfig] = None,
                           overwrite: bool = False):
        """Create the conda env(s) + Jupyter kernel(s) on the HPC (or locally).

        Creates the primary ``environment`` plus any ``extra_environments`` (each
        to its own ``environment_<name>.yml``). Run once before the first submit;
        re-running updates the env in place. Pass ``overwrite=True`` to delete and
        rebuild from scratch. Returns a list of results.
        """
        results = []
        for env in self._environments():
            fname = "environment.yml" if env is self.environment else f"environment_{env.name}.yml"
            results.append(env.create(ssh=ssh, project_dir=self.project_dir,
                                       filename=fname, overwrite=overwrite))
        return results

    def remove_environment(self, ssh: Optional[SSHConfig] = None):
        """Delete the conda env(s) + Jupyter kernel(s) on the HPC (or locally).

        Removes the primary ``environment`` and any ``extra_environments``. Safe
        when nothing is there (a missing env/kernel is ignored) — handy to recover
        from a half-built env. Returns a list of results.
        """
        return [env.remove(ssh=ssh, project_dir=self.project_dir)
                for env in self._environments()]

    # ----- jobs from JSON ----------------------------------------------------
    def _structure(self, jobs_json: Optional[str] = None) -> Structure:
        path = self._project / (jobs_json or self.jobs_json)
        return Structure.from_json(path)

    def jobs_from_json(self, jobs_json: Optional[str] = None) -> list[tuple[str, ...]]:
        """Read the jobs JSON and return one tuple of varying values per job."""
        return self._structure(jobs_json).jobs()

    def build_outputs(self, jobs_json: Optional[str] = None) -> dict[str, Path]:
        """Pre-create the full output tree from the jobs JSON, under ``output_dir``."""
        base = self._project / self.output_dir
        return self._structure(jobs_json).build(base)

    # ----- run commands (ssh or local) --------------------------------------
    def _run(self, command: str, ssh: Optional[SSHConfig]):
        return run_shell(command, ssh, self._project)

    # ----- submit ------------------------------------------------------------
    def submit(self, items: Optional[Iterable[Item]] = None,
               ssh: Optional[SSHConfig] = None, dry_run: bool = False,
               jobs_json: Optional[str] = None,
               concurrency: Optional[int] = None) -> list[str]:
        """Submit one SLURM job per item. Returns the submitted job ids.

        By default the jobs are read from the nested JSON (``self.jobs_json``):
        each root-to-leaf path becomes one job. Override by passing an explicit
        ``items`` list, or a different ``jobs_json`` path.

        Concurrency is throttled with SLURM dependencies: job N waits for job
        N-``concurrency`` to finish (afterany), so at most ``concurrency`` run at
        once without holding the queue open. Pass ``concurrency`` here to override
        ``self.concurrency`` for this call; set it to ``0`` (or ``None`` on the
        workflow) to submit every job at once with **no dependencies** — handy for
        a handful of quick, independent jobs.
        """
        if items is None:
            items = self.jobs_from_json(jobs_json)
        limit = self.concurrency if concurrency is None else concurrency
        job_ids: list[str] = []
        for item in items:
            values = self._normalise_item(item)
            key = self._key(values)
            outdir = self._outdir(values)
            exports = ",".join(f"{k.upper()}={v}" for k, v in values.items())

            dep = ""
            if limit and len(job_ids) >= limit:
                dep = f"--dependency=afterany:{job_ids[-limit]} "

            cmd = (
                f"mkdir -p {outdir} && "
                f"sbatch --parsable {dep}"
                f"--job-name={key} "
                f"--output={outdir}/{key}.out "
                f"--error={outdir}/{key}.err "
                f"--export=ALL,{exports} "
                f"scripts/job.slurm"
            )
            if dry_run:
                print(cmd)
                job_ids.append(f"<job{len(job_ids)}>")  # placeholder so chaining shows
                continue
            result = self._run(cmd, ssh).check()
            job_id = result.stdout.strip().split(";")[0]
            job_ids.append(job_id)
            print(f"submitted {key} -> job {job_id}")

        if not dry_run:
            self.submitted_jobs.extend(job_ids)
        return job_ids

    # ----- preflight ---------------------------------------------------------
    def _preflight_checks(self) -> list[tuple[str, str, str]]:
        """(name, shell test command, hint) tuples; exit 0 means the check passed."""
        nbs = " ".join(f'"{n}"' for n in self.notebooks)
        # conda/jupyter usually aren't on a non-login shell's PATH; pull in the
        # user's profile (where `conda init` writes) before checking for them.
        prof = "source ~/.bashrc 2>/dev/null; "
        checks = [
            ("project directory", "pwd",
             f"create {self.project_dir!r} on the cluster (remote_dir) and upload your project"),
            ("notebooks present",
             f'ok=1; for f in {nbs}; do [ -f "$f" ] || {{ echo "missing $f"; ok=0; }}; done; [ "$ok" = 1 ]',
             "upload your notebooks/ folder into remote_dir"),
            ("scripts built",
             f"test -f scripts/job.slurm && test -f scripts/{self.runner_name}",
             "run wf.build() and upload the scripts/ folder"),
        ]
        if self.conda_env:
            checks.append((
                f"conda env '{self.conda_env}'",
                prof + f'conda env list | grep -E "[/ ]{self.conda_env}([ /]|$)"',
                "run wf.create_environment(ssh=cfg) first",
            ))
        checks.append((
            f"kernel '{self.kernel}'",
            prof + f'test -d "$HOME/.local/share/jupyter/kernels/{self.kernel}" || '
                   f'jupyter kernelspec list 2>/dev/null | grep -qw "{self.kernel}"',
            "run wf.create_environment(ssh=cfg) to register the kernel",
        ))
        return checks

    def check(self, ssh: Optional[SSHConfig] = None,
              raise_on_error: bool = True) -> list[dict]:
        """Verify the cluster is ready before submitting.

        Confirms remote_dir, the notebooks, the built scripts, the conda env and
        the Jupyter kernel all exist — so a missing piece is a clear message here
        rather than a cryptic SLURM failure later. Returns a list of result dicts;
        raises RuntimeError on the first failure unless ``raise_on_error=False``.
        """
        results = []
        for name, command, hint in self._preflight_checks():
            res = self._run(command, ssh)
            ok = res.exit_status == 0
            print(f"  {'OK ' if ok else 'FAIL'} {name}" + ("" if ok else f"  -> {hint}"))
            results.append({"name": name, "ok": ok,
                            "detail": (res.stdout or res.stderr).strip(), "hint": hint})
        failed = [r["name"] for r in results if not r["ok"]]
        if failed and raise_on_error:
            raise RuntimeError("preflight check failed: " + ", ".join(failed))
        return results

    # ----- status ------------------------------------------------------------
    def status(self, ssh: Optional[SSHConfig] = None,
               user: Optional[str] = None) -> list[dict]:
        """Return current queue entries as a list of dicts (parsed squeue)."""
        who = user or (ssh.user if ssh else "$USER")
        fmt = "%i|%j|%T|%M|%R"
        result = self._run(f'squeue -u {who} -h -o "{fmt}"', ssh).check()
        rows = []
        for line in result.stdout.strip().splitlines():
            if not line.strip():
                continue
            jid, name, state, t, reason = line.split("|")
            rows.append({"job_id": jid, "name": name, "state": state,
                         "time": t, "reason": reason})
        return rows

    # ----- cancel ------------------------------------------------------------
    def cancel(self, ssh: Optional[SSHConfig] = None,
               job_ids: Optional[Sequence[str]] = None) -> None:
        """Cancel jobs. Defaults to the ones submitted this session."""
        targets = list(job_ids) if job_ids is not None else list(self.submitted_jobs)
        if not targets:
            print("no tracked jobs to cancel; pass job_ids=[...] explicitly")
            return
        self._run("scancel " + " ".join(targets), ssh).check()
        print(f"cancelled {len(targets)} job(s)")

    # ----- rsync (push source up / pull results down) ------------------------
    def _rsync(self, src: str, dst: str, ssh: SSHConfig,
               excludes: Sequence[str] = (), delete: bool = False,
               dry_run: bool = False):
        cmd = ["rsync", "-az", "-e", ssh.rsync_ssh()]
        if delete:
            cmd.append("--delete")
        for e in excludes:
            cmd += ["--exclude", e]
        cmd += [src, dst]
        if dry_run:
            print(" ".join(cmd))
            return cmd
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return CommandResult(" ".join(cmd), proc.returncode, proc.stdout, proc.stderr).check()

    def push(self, ssh: SSHConfig, delete: bool = False, dry_run: bool = False):
        """Upload the project to the cluster (source only — never outputs).

        Syncs notebooks/, scripts/, jobs.json, environment.yml, ... up to
        ``remote_dir``. The output dir (``output/`` by default) and ``done/`` are
        excluded, so pushing your latest notebook edits can never wipe results
        already on the cluster.
        """
        done_dir = str(Path(self.done_csv).parent).replace("\\", "/").rstrip("/")
        excludes = list(PUSH_EXCLUDES) + [self.output_dir.rstrip("/"), done_dir]
        return self._rsync(
            src=str(self._project).rstrip("/\\") + "/",
            dst=ssh.rsync_target(),
            ssh=ssh, excludes=excludes, delete=delete, dry_run=dry_run,
        )

    def pull(self, ssh: SSHConfig, delete: bool = False, dry_run: bool = False):
        """Download results from the cluster (outputs only).

        Pulls **only** the output dir (``output/`` by default) and the ``done/``
        ledger back to the project. It never fetches notebooks/ or scripts/, so a
        results-sync can't overwrite a notebook you changed locally while jobs
        were running.
        """
        done_dir = str(Path(self.done_csv).parent).replace("\\", "/").rstrip("/")
        subs = [self.output_dir.rstrip("/"), done_dir]
        # The remote output/done dirs may not exist yet (e.g. jobs are still
        # queued, or none has written a done ledger). Create them first so rsync
        # doesn't fail with "change_dir ... No such file or directory" (exit 23).
        if not dry_run:
            self._run("mkdir -p " + " ".join(subs), ssh)
        results = []
        for sub in subs:
            results.append(self._rsync(
                src=ssh.rsync_target(sub + "/"),
                dst=str(self._project / sub).rstrip("/\\") + "/",
                ssh=ssh, delete=delete, dry_run=dry_run,
            ))
        return results
