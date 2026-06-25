# HPC for notebook users (no Linux required)

If you have only ever run notebooks on your laptop or a cloud server, an HPC
("supercomputer") works a little differently. This page explains just enough to
use nb2slurm. The idea is that you will **not** need to learn Linux or the command line — nb2slurm
does that for you — but it helps to know what is happening underneath.
These docs give you the most common Linux and SLURM commands.
Yet, I cannot promise that you can omit commandline.

## The one-sentence summary

An HPC is a big shared computer where you don't run your work directly; you
**describe a job** (what to run, how much memory/time it needs) and a scheduler
runs it for you when resources are free. nb2slurm writes that job description and
submits it.

## The pieces

### Login node vs. compute nodes
When you connect to an HPC you land on a **login node**. This is a shared waiting
room — fine for editing files and submitting work, **not** for heavy computation.
The actual work runs on **compute nodes**, which you never log into directly. You
reach them only by submitting a job.

### SLURM (the scheduler)
**SLURM** is the program that decides which job runs on which compute node and
when. You hand it a job that says *"run this script; I need 1 node, 2 CPUs, 4
hours"* and it queues it. When resources are free, it runs. Key ideas:

- **`sbatch`** — submit a job (nb2slurm calls this for you).
- **`squeue`** — see what's queued/running (`wf.status()`).
- **`scancel`** — cancel jobs (`wf.cancel()`).
- A job that asks for less time/memory usually starts sooner.

### Resources
Every job declares what it needs. The common ones (set via `Workflow(resources=...)`):

| field | meaning | typical               |
|-------|---------|-----------------------|
| `nodes` | how many machines | `1`                   |
| `cpus` | CPU cores | `1`–`8`               |
| `time` | wall-clock limit `HH:MM:SS`; job is killed if exceeded | start generous        |
| `memory` | RAM, e.g. `"16G"` (optional) | depends on data       |
| `partition` | which queue to use, cluster-specific (optional) | consult documentation |

Ask for too little time and your job is killed mid-run; too much and it waits
longer in the queue. Start generous, then tighten once you know how long one
subject takes.

### Conda environments and Jupyter kernels
Your code needs its libraries installed **on the cluster**, not just your laptop.
On HPC this is almost always done with **conda** (or the faster `mamba`): a named
**environment** holds a specific Python plus your packages.

papermill (which runs your notebooks) needs that environment registered as a
**Jupyter kernel** — a named entry papermill can pick. nb2slurm creates both for
you:

```python
from nb2slurm import Environment
env = Environment(name="myenv", kernel="myenv",
                  conda_packages=["xarray", "numpy"],
                  pip_packages=["nb2slurm"])
env.create(ssh=cfg)        # builds the env + registers the kernel on the HPC
```

The `kernel` name here must match `Workflow(kernel="myenv")`, and `name` must
match `Workflow(conda_env="myenv")`. If you pass `environment=env` to `Workflow`,
nb2slurm keeps them in sync and errors if they disagree.

### Filesystems
HPCs have more than one place to store files, and they behave differently:

- **Home** (`$HOME`) — small, backed up. Keep code/notebooks here.
- **Project / scratch** — large, fast, often **not** backed up and sometimes
  auto-deleted after a while. Keep big outputs and data here. But keep in mind that it might be deleted!

This is why `output_dir` and `done_csv` are configurable in nb2slurm: point big
outputs at scratch/project, keep your notebooks in home.

### Data mounts (rclone)
Big shared datasets (climate data, Caravan) often live on remote storage that is
**mounted** into the job at runtime with `rclone`. nb2slurm puts these mounts in
the SLURM script for you:

```python
Workflow(..., mounts=[
    {"remote": "dcache:/climate-data/caravan", "mountpoint": "/scratch/caravan"},
])
```

## What you need before you start

Collect these (usually from your HPC's docs or support desk):

1. **An account** on the cluster and your **username**.
2. **SSH access** — ideally an SSH key (so nb2slurm can connect without a password
   prompt). Your cluster's docs explain how to upload your public key.
3. The **login hostname** (e.g. `spider.surf.nl`).
4. A **project directory** on the cluster to hold your notebooks (`remote_dir`). (Optional, but nice to have)
5. Which **partition** (queue) to use, if any, and sensible resource limits.
6. How to reach your **data** (rclone remote names / mountpoints), if needed.

## How nb2slurm hides all of this

You stay in a notebook and write Python:

```python
from nb2slurm import Workflow, Environment, SSHConfig

cfg = SSHConfig(host="spider.surf.nl", user="me",
                remote_dir="/home/me/myproject", key_filename="~/.ssh/id_ed25519")

env = Environment(name="myenv", kernel="myenv", conda_packages=["xarray"])
wf  = Workflow(name="myproject", notebooks=[...], kernel="myenv",
               varying=["region_id"], environment=env)

wf.create_environment(ssh=cfg)   # one-time: build env + kernel on the HPC
wf.build()                       # write the SLURM/runner scripts
wf.submit(["123", "456"], ssh=cfg)  # sbatch, behind the scenes
wf.status(ssh=cfg)               # squeue, behind the scenes
```

No terminal, no Linux commands. The only thing that is genuinely yours to set up
once is the SSH key and the account — everything after that is Python.

## Mini-glossary

- **Node** — one physical machine in the cluster.
- **Job** — a unit of work you submit to SLURM.
- **Queue / partition** — a named pool of nodes with its own rules/limits.
- **Wall-clock time** — real elapsed time (vs. CPU time); your `time` limit.
- **Kernel** — the named Python environment papermill runs a notebook in.
- **Mount** — making remote storage appear as a local folder inside the job.
