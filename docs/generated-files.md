# Generated files

{meth}`~nb2slurm.Workflow.build` renders the bundled templates into your project
and returns a `{kind: path}` dict, so you can see exactly what was written:

```python
for kind, path in wf.build().items():
    print(f"{kind:13s} -> {path}")
```

Into `<project>/scripts/`:

| file | role |
|------|------|
| `run_workflow.py` | papermill driver: skip-if-done → run notebook 0 (writes `settings.json`) → run the rest → mark done |
| `job.slurm` | `#SBATCH` resources, `conda activate`, rclone mounts, then the driver |
| `submit_batch.sh` | CLI fallback: submit every job at once (simple, no concurrency) |
| `submit_jobs.sh` | CLI fallback: same, but throttles how many run concurrently |
| `cancel_jobs.sh` | CLI fallback: cancel jobs by name |
| `jobs.txt` | flat one-job-per-line list, generated from `jobs.json` |
| `structure.json` | the resolved config used to render everything |

Into the project root, only when the workflow has an
{class}`~nb2slurm.Environment`: `environment.yml`, plus one
`environment_<name>.yml` per entry in `extra_environments`.

`jobs.txt` is written only if `jobs.json` exists — the bash scripts read it so
they never have to parse JSON, which keeps them short and readable.

The notebook path (`wf.submit(...)`) is the primary one; the bash scripts are
there for when you are SSH'd into the cluster instead. Nothing here is meant to
be edited by hand — every `build()` overwrites it. Change the
{class}`~nb2slurm.Workflow` arguments and rebuild.
