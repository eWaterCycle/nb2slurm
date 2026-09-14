# Moving files: push up, pull down

nb2slurm wraps `rsync` (so it must be available locally) in two deliberately
one-directional helpers:

```python
wf.push(ssh=cfg)   # local project  -> cluster:  notebooks/, scripts/, jobs.json, ...
wf.pull(ssh=cfg)   # cluster results -> local:   output/ and done/ only
```

The split is the safety mechanism:

- **`push` never uploads `output/` or `done/`** — re-uploading your latest notebook
  edits cannot wipe results already produced on the cluster.
- **`pull` never fetches `notebooks/`, `scripts/` or `jobs.json`** — syncing results
  back cannot overwrite a notebook you changed locally while jobs were running.

Local cruft (`.git`, `__pycache__`, `.ipynb_checkpoints`, virtualenvs, caches, IDE
folders) is excluded from `push` automatically.

So the normal loop after editing a notebook is:

```python
wf.push(ssh=cfg)     # send the change
wf.submit(ssh=cfg)   # finished subjects are skipped via done.csv
wf.pull(ssh=cfg)     # bring results back when you want them
```

Both accept `dry_run=True` to see the `rsync` command without running it, and
`delete=True` to mirror deletions (off by default).
