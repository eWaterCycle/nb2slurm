# Quickstart

Everything below runs in a notebook. Nothing needs a terminal.

## 1. Describe the workflow

```python
import nb2slurm

wf = nb2slurm.Workflow(
    name="myproject",
    notebooks=[
        "notebooks/0_settings.ipynb",      # first notebook writes settings.json
        "notebooks/1_computations.ipynb",  # all other notebooks read settings.json
    ],
    kernel="myenv",                        # a Jupyter kernel on the cluster
    varying=["country", "region"],         # what changes per job (name these yourself)
    resources=dict(nodes=1, cpus=2, time="04:00:00"),
    conda_env="myenv",                     # activated in the SLURM job
    mounts=[                               # optional rclone mounts
        {"remote": "dcache:/climate-data/caravan", "mountpoint": "/scratch/caravan"},
    ],
    concurrency=3,                         # max jobs running at once per submit
    # output_dir="output",                 # where per-subject outputs go
    # done_csv="done/done.csv",            # idempotency ledger
)
```

See [The notebook contract](notebook-contract.md) for what the notebooks
themselves must look like, and the {class}`~nb2slurm.Workflow` reference for
every option.

## 2. Build, and prove it on one subject

```python
wf.build()      # render scripts/ into the project
```

Before involving the cluster, prove the chain works for one subject. The simplest
way is the one you already know: **open your notebooks in Jupyter and run them
top to bottom**, in order. Their `parameters` cells hold ordinary defaults, so
`0_settings.ipynb` writes a `settings.json` the later notebooks read, exactly as
they will on the cluster. If the chain works in Jupyter, it will work under
SLURM — nb2slurm only swaps in a different subject and `outdir` per job.

To exercise the generated driver itself — skip-if-done, the settings hand-off,
the notebook order — run it for one subject instead:

```bash
python scripts/run_workflow.py NL north      # values in varying order
```

What `build()` writes is listed in [Generated files](generated-files.md).

## 3. Point at the cluster

```python
cfg = nb2slurm.SSHConfig(
    host="spider.surfsara.nl",
    user="me",
    remote_dir="/home/me/myproject",
    # key_filename="~/.ssh/id_ed25519",   # optional
)

wf.push(ssh=cfg)        # upload notebooks/, scripts/, jobs.json, ...
wf.check(ssh=cfg)       # preflight: is everything there to submit?
```

`check()` prints an `OK`/`FAIL` line per check (remote dir, notebooks, built
scripts, conda env, kernel) and raises on the first failure — it turns a cryptic
SLURM error into a clear message. Pass `raise_on_error=False` to get the full
report back as a list instead.

## 4. Submit and watch

```python
wf.submit(ssh=cfg)                                  # reads jobs.json: one job per leaf
wf.submit([("NL", "north"), ("DE", "south")], ssh=cfg)       # or an explicit subset
wf.status(ssh=cfg)                                  # parsed squeue
wf.cancel(ssh=cfg)                                  # scancel what we submitted
```

`submit(dry_run=True)` prints the exact `sbatch` commands without running them.
Omit `ssh=` entirely to use a local `subprocess` — that is the path when you run
this from a login or Jupyter node on the cluster itself.

## 5. Get the results back

```python
wf.pull(ssh=cfg)        # output/ and done/ only — never your notebooks
```

See [Moving files](transfer.md). Finished subjects are recorded in `done.csv`, so
re-submitting the whole set only runs what is missing.

That ledger tracks *inputs*, not logic: if you change what a notebook actually
does, finished subjects won't rerun on their own. Clear the ledger to force them
to:

```python
wf.reset_done(ssh=cfg)   # delete done.csv; the next submit() reruns everything
```

To rerun only part of the set, pass an explicit `items=` list to `submit()`
instead.

## Where the jobs come from

`submit()` with no arguments reads `jobs.json`, a nested file that defines both
the job list and the output tree — see [jobs.json](jobs-json.md).

For day-to-day use, split this into the four
[control notebooks](control-notebooks.md) instead of one long cell.
