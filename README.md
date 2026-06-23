# nb2slurm

nb2slurm seamlessly makes your notebook workflow ready for SLURM upscaling.

It takes a notebook workflow that runs for **one subject** (one catchment, one
region, one number...) and generates everything needed to run it for **many
subjects** on a SLURM HPC — driven entirely from a notebook, no command line.

This is the reusable generalisation of the eWaterCycle
[CCI-analysis-seamless](https://github.com/eWaterCycle/CCI-analysis-seamless)
project (its hardcoded `cci.py` + `run_cci.slurm` + `submit_*.sh`).

## What it is

nb2slurm is **a package and a scaffolder**:

- **Package (logic):** the importable `nb2slurm` — the `Workflow` class plus
  helpers for settings, done-tracking, and an SSH transport.
- **Scaffolder (templates):** bundled Jinja2 templates that `Workflow.build()`
  renders into a concrete `scripts/` directory for your project.

The project *starter* (notebooks + a control notebook) is intended to live in a
separate template repository that you clone and fill in; it imports this package.

## Install

```bash
pip install -e ".[dev]"   # from a clone
```

Dependencies: `papermill`, `filelock`, `jinja2`, `paramiko`.

## Usage — all from a notebook

```python
import nb2slurm

wf = nb2slurm.Workflow(
    name="myproject",
    notebooks=[
        "notebooks/0_settings.ipynb",   # first nb writes settings.json
        "notebooks/1_analysis.ipynb",   # later nbs read settings.json
    ],
    kernel="myenv",
    varying=["region_id", "country"],   # what changes per job
    resources=dict(nodes=1, cpus=2, time="04:00:00"),
    conda_env="myenv",                  # activated in the SLURM job
    mounts=[                            # optional rclone mounts
        {"remote": "dcache:/climate-data/caravan", "mountpoint": "/scratch/caravan"},
    ],
    concurrency=3,                      # max jobs running at once per submit
    # output_dir="runs",              # where per-subject outputs go (root-relative by default)
    # done_csv="done/done.csv",       # idempotency ledger (root-relative by default)
)

wf.build()                              # render scripts/ into the project

# prove it works on one subject locally first:
#   python scripts/run_workflow.py 123 NL

cfg = nb2slurm.SSHConfig(host="spider.surf.nl", user="me",
                         remote_dir="/home/me/myproject", key_filename="~/.ssh/id_ed25519")

wf.check(ssh=cfg)                                     # preflight: ready to submit?
wf.submit([("123", "NL"), ("456", "DE")], ssh=cfg)   # sbatch one job per subject
wf.status(ssh=cfg)                                     # parsed squeue
wf.cancel(ssh=cfg)                                     # scancel what we submitted
```

## Creating the conda environment + kernel

The SLURM job does `conda activate <env>` and papermill needs a registered
Jupyter kernel — both must exist on the cluster first. nb2slurm can build them for
you so you never touch conda or the command line:

```python
import nb2slurm

env = nb2slurm.Environment(
    name="myenv",
    kernel="myenv",                       # must match Workflow(kernel=...)
    conda_packages=["xarray", "numpy"],
    pip_packages=["nb2slurm", "ewatercycle"],
)

wf = nb2slurm.Workflow(name="myproject", notebooks=[...], kernel="myenv",
                       varying=["region_id"], environment=env)

wf.create_environment(ssh=cfg)   # one-time: env + kernel on the HPC (writes environment.yml)
```

Passing `environment=env` to `Workflow` keeps the names in sync (it errors if
`kernel`/`conda_env` disagree) and makes `build()` also write `environment.yml`.
`create_environment()` uses `mamba` when available, falls back to `conda`, and
registers the kernel via `ipykernel`. Omit `ssh=` to build the env locally instead.

### Using a cluster's existing environment (no env creation)

`environment` is **optional**. Many clusters already provide Python via a module
system or a shared environment. In that case skip `Environment` entirely and
either point at an existing conda env or run setup commands yourself:

```python
# existing conda env on the cluster
wf = nb2slurm.Workflow(..., kernel="hydro_kernel", conda_env="hydro")

# module-based cluster (no conda): raw shell lines run before the job
wf = nb2slurm.Workflow(..., kernel="hydro_kernel",
                       setup=["module load 2023", "source /opt/envs/hydro/bin/activate"])
```

`setup` lines are emitted at the top of the SLURM script (before mounts and the
runner). With no `environment`/`conda_env`, no `conda activate` is generated —
the job just uses whatever Python your `setup` puts on the `PATH`. The only hard
requirement is that `kernel` names a Jupyter kernel that exists on the cluster.

New to HPC/SLURM/conda? See **[docs/hpc-for-beginners.md](docs/hpc-for-beginners.md)**
for a plain-language primer (no Linux required).

`submit` also accepts `dry_run=True` to print the exact `sbatch` commands without
running them, and works without `ssh=` (local `subprocess`) when run on a cluster
login/Jupyter node.

`check(ssh=cfg)` is an optional preflight: it verifies that `remote_dir`, your
notebooks, the built `scripts/`, the conda env and the Jupyter kernel all exist,
printing an `OK`/`FAIL` line per check and raising on the first failure (pass
`raise_on_error=False` to get the full report back as a list instead). Run it once
before your first submit to turn a cryptic SLURM failure into a clear message.

## What `build()` generates

Into `<project>/scripts/`:

| file | role |
|------|------|
| `run_workflow.py` | papermill driver: skip-if-done → run nb 0 (makes `settings.json`) → run the rest → mark done |
| `job.slurm` | `#SBATCH` resources, conda activate, rclone mounts, then runs the driver |
| `submit_batch.sh` | CLI fallback: submit every job at once (simple, no concurrency — easy to read) |
| `submit_jobs.sh` | CLI fallback: same, but throttles how many run concurrently |
| `cancel_jobs.sh` | CLI fallback: cancel jobs by name |
| `jobs.txt` | flat one-job-per-line list generated from `jobs.json` (what the bash scripts read) |
| `structure.json` | the resolved config used to render everything |

The notebook (`wf.submit(...)`) is the primary path; the bash scripts are a
fallback for when you're SSH'd into the cluster. They never parse JSON — nb2slurm
flattens `jobs.json` into `jobs.txt` for them, so they stay short and readable.

## The contract your notebooks follow

- The **first** notebook has a papermill `parameters` cell; nb2slurm injects the
  `varying` values plus `outdir`. It should call `nb2slurm.Settings.write(outdir, {...})`.
- Every **later** notebook has a `parameters` cell with `settings_path`, and starts
  with `settings = nb2slurm.Settings.load(settings_path)`.

This keeps per-run details in one place (`settings.json`) and means only the first
notebook is parameterised.

## jobs.json — one file defines the jobs *and* the output tree

Instead of a flat subject list, the jobs to run live in a nested JSON file. Each
root-to-leaf path is one SLURM job, and the levels line up with `varying`. The
output directory mirrors that hierarchy, so the job list and the folder tree can
never drift apart.

```json
{
  "NL": { "123": ["ssp126", "ssp245"] },
  "DE": { "789": ["ssp585"] }
}
```

With `varying=["country", "region", "scenario"]` this means:

```
jobs:  (NL,123,ssp126)  (NL,123,ssp245)  (DE,789,ssp585)
dirs:  runs/NL/123/ssp126  runs/NL/123/ssp245  runs/DE/789/ssp585
```

**Format rules** (so you can generate the file however you like — a literal dict,
a comprehension, from a CSV, ...):

- a **dict** nests one more level (its keys are the values of the next `varying` dimension);
- a **list** at the bottom means several jobs sharing the same parent path;
- **`null`** / `[]` / `{}` ends the path there (a job/leaf with no deeper level).

It's just JSON, so build it any way that suits you and write it to `jobs.json`.
For example, in Python:

```python
import json
countries = {"NL": ["123", "456"], "DE": ["789"]}
scenarios = ["ssp126", "ssp245", "ssp585"]
jobs = {c: {r: scenarios for r in regions} for c, regions in countries.items()}
json.dump(jobs, open("jobs.json", "w"), indent=2)
```

`submit()` reads this file by default (no arguments needed):

```python
wf = nb2slurm.Workflow(..., varying=["country","region","scenario"], jobs_json="jobs.json")

wf.build_outputs()                  # optional: pre-create the whole runs/... tree from the JSON
wf.submit(ssh=cfg)                  # reads jobs.json, one job per leaf path
wf.submit([("NL","123","ssp126")], ssh=cfg)   # override: run an explicit subset instead
wf.submit(ssh=cfg, jobs_json="rerun.json")    # override: use a different file
```

Because each job's output dir is built from the JSON, your first notebook never
builds folders — it just receives `outdir` and writes `settings.json`. The
underlying parser is exposed as `nb2slurm.Structure` if you want it directly
(`Structure.from_json(path).jobs()` / `.build(base)`).

## Moving files: push source up, pull results down

nb2slurm wraps `rsync` (so you need `rsync` available locally) with two
deliberately one-directional helpers:

```python
wf.push(ssh=cfg)   # local project  -> cluster:  notebooks/, scripts/, jobs.json, ...
wf.pull(ssh=cfg)   # cluster results -> local:    runs/ and done/ only
```

The split is the safety mechanism:

- **`push` never uploads `runs/`/`done/`** — re-uploading your latest notebook
  edits can't wipe results already produced on the cluster.
- **`pull` never fetches `notebooks/`/`scripts/`/`jobs.json`** — syncing results
  back can't overwrite a notebook you changed locally while jobs were running.

So the normal loop after editing a notebook is: `push` the change, submit again
(finished work is skipped via `done.csv`), then `pull` results when ready.

## Control notebooks

For real use the control surface is split into four notebooks (see
`docs/control/`):

| notebook | does |
|----------|------|
| `0_config.ipynb` | guided settings; saves `control_config.json` + `jobs.json` |
| `1_build.ipynb` | `wf.build()` → `wf.push()` → `wf.create_environment()` → `wf.check()` |
| `2_submit.ipynb` | `wf.submit()` / `wf.status()` / `wf.cancel()` |
| `3_sync.ipynb` | `wf.pull()` — results only, never your notebooks |

You only edit `0_config.ipynb`. It builds the objects from your settings and
saves them with `nb2slurm.save_config(...)`; the other three start with
`wf, cfg = nb2slurm.load_config("control_config.json")`, so they always share one
source of truth and never duplicate settings.

`docs/walkthrough.ipynb` is the single-notebook narrative overview of the whole
flow; the four above are the practical, modular version.

## Development

```bash
python -m pytest -q
```
