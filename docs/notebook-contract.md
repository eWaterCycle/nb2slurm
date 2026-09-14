# The notebook contract

nb2slurm runs your notebooks with [papermill](https://papermill.readthedocs.io),
one chain per subject. Two small rules make that work.

## 1. The first notebook writes the settings

It needs one cell tagged `parameters`. **The tag is the mechanism**, not the
contents: papermill finds the tagged cell and inserts a new cell directly after
it that re-assigns those variables, so the injected values win. In JupyterLab you
add it from *Property Inspector → Cell Tags*; in VS Code, *Add Cell Tag*. Without
the tag, nothing is injected and every job runs identical work.

In that cell, declare **one variable per entry in your `varying` list, named
exactly as you named it there**, plus `outdir`.

The names below are only this page's example. If your workflow says
`varying=["basin", "model"]`, then your cell declares `basin` and `model` —
nb2slurm has no opinion about what you call them:

```python
# cell tagged: parameters        <- example, for varying=["country", "region"]
country = "NL"
region = "north"
outdir = "output/NL/north"
```

The values you type there are **defaults for running the notebook yourself**, and
nothing more. Open it in Jupyter and it runs for that one subject; on the cluster
papermill overrides all of them per job, so these literals never reach a SLURM
run. Pick whatever makes a sensible local test.

Then write them out, so the rest of the chain can read them back:

```python
import nb2slurm
nb2slurm.Settings.write(outdir, {"country": country, "region": region, "outdir": outdir})
```

`outdir` is handed in by the generated runner — you never build paths yourself.
The output tree comes from [jobs.json](jobs-json.md).

## 2. Every later notebook reads it

Each has a `parameters` cell with just `settings_path`, and loads it. Same rule:
the tag matters, the literal is only a local default that the runner overrides
with this job's real path.

```python
# cell tagged: parameters
settings_path = "output/NL/north/settings.json"
```

```python
import nb2slurm
settings = nb2slurm.Settings.load(settings_path)
```

That keeps the per-run details in one place: only the first notebook is
parameterised with your varying variables, the rest just read the JSON.

## Laptop vs. cluster: `on_hpc()`

For the things that genuinely differ between an interactive run and a batch run
(shared data directories, `!pip install` cells), branch on
{func}`~nb2slurm.on_hpc`. It detects a batch run from the SLURM environment plus
an `NB2SLURM` sentinel, so it works for any user — unlike grepping `Path.home()`:

```python
import nb2slurm
data_dir = "/project/ewater/Data" if nb2slurm.on_hpc() else "/data/shared"
```

It also helps when importing a helper from `scripts/`. On the cluster the job runs
from the project root, so `from scripts.foo import bar` just works; opened
interactively from a `notebooks/` subfolder it does not, so add the project root
only when running locally:

```python
import sys
from pathlib import Path
import nb2slurm

if not nb2slurm.on_hpc():
    sys.path.append(str(Path().resolve().parent))
from scripts.montecarlo import estimate_pi
```

## Converting a local-only workflow

[`setup_notebooks.ipynb`](setup_notebooks.ipynb) walks through the in-notebook
changes with before/after snippets.

```{toctree}
:hidden:

setup_notebooks
```
