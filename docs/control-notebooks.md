# Control notebooks

For real use, split the control surface into four notebooks instead of one long
cell. Each one is a step of the cycle, and together they are the practical
version of what [the walkthrough](walkthrough.ipynb) narrates in one go.

| notebook | does |
|----------|------|
| [`0_config.ipynb`](control_notebooks/0_config.ipynb) | guided settings; saves `control_config.json` + `jobs.json` |
| [`1_build.ipynb`](control_notebooks/1_build.ipynb) | `wf.build()` → `wf.push()` → `wf.create_environment()` → `wf.check()` |
| [`2_submit.ipynb`](control_notebooks/2_submit.ipynb) | `wf.submit()` / `wf.status()` / `wf.cancel()` |
| [`3_sync.ipynb`](control_notebooks/3_sync.ipynb) | `wf.pull()` — results only, never your notebooks |

## One source of truth

You only ever edit `0_config.ipynb`. It builds the objects from your settings and
saves them:

```python
nb2slurm.save_config("control_config.json", workflow=wf, ssh=cfg)
```

The other three start with

```python
wf, cfg = nb2slurm.load_config("control_config.json")
```

so they can never drift apart, and no setting is written down twice. Re-run
`0_config.ipynb` whenever something changes.

## The loop afterwards

Edited a notebook while jobs were running? Re-run the `wf.push()` step in
`1_build.ipynb`, then submit again from `2_submit.ipynb` — finished subjects are
recorded in `done/done.csv`, so only what is new or unfinished actually runs.

```{toctree}
:hidden:

control_notebooks/0_config
control_notebooks/1_build
control_notebooks/2_submit
control_notebooks/3_sync
```
