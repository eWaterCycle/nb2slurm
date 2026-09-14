# The notebook contract

nb2slurm runs your notebooks with [papermill](https://papermill.readthedocs.io),
one chain per subject. Two small rules make that work.

## 1. The first notebook writes the settings

It has a cell tagged `parameters`. nb2slurm injects the `varying` values plus
`outdir` into that cell, and the notebook writes them to `settings.json`:

```python
# cell tagged: parameters
region_id = "north_1"
country = "NL"
outdir = "output/NL/north_1"
```

```python
import nb2slurm
nb2slurm.Settings.write(outdir, {"region_id": region_id, "country": country, "outdir": outdir})
```

`outdir` is handed to the notebook by the generated runner, so you never build
paths yourself — the output tree comes from [jobs.json](jobs-json.md).

## 2. Every later notebook reads it

Each has a `parameters` cell with just `settings_path`, and loads it:

```python
# cell tagged: parameters
settings_path = "output/NL/north_1/settings.json"
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
