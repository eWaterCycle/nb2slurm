# nb2slurm

[![Documentation](https://readthedocs.org/projects/nb2slurm/badge/?version=latest)](https://nb2slurm.readthedocs.io/en/latest/)
[![Lint](https://github.com/eWaterCycle/nb2slurm/actions/workflows/lint.yml/badge.svg)](https://github.com/eWaterCycle/nb2slurm/actions/workflows/lint.yml)
[![PyPI](https://img.shields.io/pypi/v/nb2slurm.svg)](https://pypi.org/project/nb2slurm/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Take a notebook workflow that runs for **one subject** — one catchment, one
region, one number — and run it for **many subjects** on a SLURM cluster, driven
entirely from a notebook. No command line, no rewriting your science into a
pipeline DSL.

> **Status: alpha.** The Monte Carlo example works end to end, but the API can
> still change between versions. Pin what you install.

## The problem

Scaling a notebook study to a cluster usually means abandoning notebooks: someone
hand-writes a `run_*.slurm`, a `submit_*.sh` and a driver script, then keeps them
in sync with the notebooks by hand. The scripts drift, the notebooks stop being
runnable on a laptop, and the whole thing is one person's private knowledge.

nb2slurm generates those files instead. Your notebooks stay ordinary notebooks —
the same ones you open in Jupyter are the ones SLURM executes, with
[papermill](https://papermill.readthedocs.io) injecting a different subject per
job.

## Install

```bash
pip install nb2slurm
```

Python 3.9+. You also need `rsync` locally for the file transfer helpers, and
SSH access to a cluster.
See [Installation](https://nb2slurm.readthedocs.io/en/latest/installation.html)
for the cluster-side requirements.

## Example

```python
import nb2slurm

wf = nb2slurm.Workflow(
    name="myproject",
    notebooks=[
        "notebooks/0_settings.ipynb",       # writes settings.json
        "notebooks/1_computations.ipynb",   # reads settings.json
    ],
    kernel="myenv",                         # a Jupyter kernel on the cluster
    varying=["country", "region"],          # what changes per job
    jobs_json="jobs.json",                  # the jobs, and the output tree
    resources=dict(nodes=1, cpus=2, time="04:00:00"),
    conda_env="myenv",
    concurrency=3,
)

wf.build()                                  # render scripts/ into the project

cfg = nb2slurm.SSHConfig(host="spider.surfsara.nl", user="me",
                         remote_dir="/home/me/myproject")

wf.push(ssh=cfg)        # upload source — never output/
wf.check(ssh=cfg)       # preflight: dir, notebooks, scripts, env, kernel
wf.submit(ssh=cfg)      # one SLURM job per job in jobs.json
wf.status(ssh=cfg)      # parsed squeue
wf.pull(ssh=cfg)        # download results — never your notebooks
```

Every method works without `ssh=` too, running locally instead — that is the path
when you drive this from a login or Jupyter node on the cluster itself, and
`dry_run=True` prints the exact `rsync`/`sbatch` commands without running them.

## How it works

- **A package and a scaffolder.** The importable `nb2slurm` holds the logic;
  bundled Jinja2 templates are rendered by `build()` into a concrete `scripts/`
  directory you can read, review and commit.
- **`jobs.json` defines the jobs *and* the output tree.** Each root-to-leaf path
  in the nested JSON is one SLURM job and one output directory, so the job list
  and the folder layout cannot drift apart.
- **Transfers are one-directional by design.** `push` never uploads `output/`,
  `pull` never fetches `notebooks/`. Neither direction can destroy the other
  side's work.
- **Re-running is cheap.** Finished subjects are recorded in `done.csv`, so
  re-submitting the whole set only runs what is missing.

## Documentation

Full documentation: **<https://nb2slurm.readthedocs.io>**

| | |
|---|---|
| [Quickstart](https://nb2slurm.readthedocs.io/en/latest/quickstart.html) | the whole cycle in five steps |
| [HPC for notebook users](https://nb2slurm.readthedocs.io/en/latest/hpc-for-beginners.html) | plain-language primer if SLURM and conda are new |
| [The notebook contract](https://nb2slurm.readthedocs.io/en/latest/notebook-contract.html) | the two rules your notebooks must follow |
| [jobs.json](https://nb2slurm.readthedocs.io/en/latest/jobs-json.html) | the job grid and the output tree |
| [Environments and kernels](https://nb2slurm.readthedocs.io/en/latest/environments.html) | build one on the cluster, or use what is there |
| [Connecting to the cluster](https://nb2slurm.readthedocs.io/en/latest/ssh.html) | SSH keys, passphrases, `test_connection()` |
| [Generated files](https://nb2slurm.readthedocs.io/en/latest/generated-files.html) | what `build()` writes, and why |
| [Control notebooks](https://nb2slurm.readthedocs.io/en/latest/control-notebooks.html) | the four-notebook control surface |
| [Monte Carlo π example](https://nb2slurm.readthedocs.io/en/latest/examples.html) | a complete, runnable workflow |
| [API reference](https://nb2slurm.readthedocs.io/en/latest/api.html) | every public class and function |

Converting an existing local-only workflow? `docs/setup_notebooks.ipynb` walks
through the in-notebook changes with before/after snippets.

## Development

```bash
git clone https://github.com/eWaterCycle/nb2slurm
cd nb2slurm
pip install -e ".[dev,docs]"

pytest
ruff check . && ruff format --check .
sphinx-build -b html docs docs/_build/html
```

Ruff runs in CI on every pull request. Issues and pull requests are welcome.

## About

nb2slurm is the reusable generalisation of the eWaterCycle
[CCI-analysis-seamless](https://github.com/eWaterCycle/CCI-analysis-seamless)
project — its hardcoded `cci.py`, `run_cci.slurm` and `submit_*.sh`, turned into
something any notebook workflow can use.

Licensed under [Apache-2.0](LICENSE).
