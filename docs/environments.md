# Environments and kernels

The generated SLURM job does `conda activate <env>`, and papermill needs a
registered Jupyter kernel to execute the notebooks. Both must exist on the
cluster before the first submit. There are three ways to get there.

## 1. Let nb2slurm create the environment

```python
import nb2slurm

user = "me"
cfg = nb2slurm.SSHConfig(host="spider.surfsara.nl", user=user,
                         remote_dir=f"/home/{user}/myproject")

env = nb2slurm.Environment(
    name="myenv",
    kernel="myenv",                        # must match Workflow(kernel=...)
    conda_packages=["xarray", "numpy"],        # EXAMPLE — your notebooks' imports
    pip_packages=["nb2slurm", "ewatercycle"],  # EXAMPLE — keep nb2slurm, swap the rest
)

wf = nb2slurm.Workflow(name="myproject", notebooks=[...], kernel="myenv",
                       varying=["region_id"], environment=env)

wf.create_environment(ssh=cfg)   # one-time: env + kernel on the HPC
```

```{admonition} The package lists are an example, not a requirement
:class: important
`xarray`, `numpy` and `ewatercycle` are just this example's stack — nb2slurm is
domain-agnostic and has nothing to do with hydrology. List whatever **your**
notebooks import.

Two things you don't have to think about: `python` defaults to `3.11` (set
`python="3.12"` to change it), and `ipykernel` is always added for you, since
papermill needs the kernel to exist.

The one entry to keep is **`nb2slurm` itself** — the generated runner and your
notebooks import it inside the job. It is the default value of `pip_packages`, so
it is easy to lose by accident: the moment you pass your own `pip_packages` list,
you replace that default and must include `nb2slurm` again.
```

Passing `environment=env` keeps the names in sync (it raises if `kernel` or
`conda_env` disagree with the `Environment`) and makes `build()` also write
`environment.yml`.

{meth}`~nb2slurm.Workflow.create_environment` uses `mamba` when available, falls
back to `conda`, and registers the kernel through `ipykernel`. Omit `ssh=` to
build the same environment locally. It runs **non-interactively** (it never
stalls on a conda `[Y/n]` prompt over SSH) and **streams** conda/mamba output
live, so a multi-minute solve doesn't look like a hang.

It is also idempotent: re-running *updates the environment in place*. To recover
from a half-built environment, or to force a clean slate:

```python
wf.environment.exists(ssh=cfg)                  # True/False, changes nothing
wf.remove_environment(ssh=cfg)                  # delete the env + its Jupyter kernel
wf.create_environment(ssh=cfg, overwrite=True)  # remove-then-create in one go
```

## 2. Use an environment the cluster already has

`environment` is **optional**. Many clusters provide Python through a module
system or a shared environment; then skip {class}`~nb2slurm.Environment`:

```python
# an existing conda env on the cluster
wf = nb2slurm.Workflow(..., kernel="hydro_kernel", conda_env="hydro")

# a module-based cluster (no conda): raw shell lines run before the job
wf = nb2slurm.Workflow(..., kernel="hydro_kernel",
                       setup=["module load 2023", "source /opt/envs/hydro/bin/activate"])
```

`setup` lines are emitted at the top of the SLURM script, before the mounts and
the runner. With no `environment` and no `conda_env`, no `conda activate` is
generated — the job uses whatever Python your `setup` puts on the `PATH`. The one
hard requirement is that `kernel` names a Jupyter kernel that exists on the
cluster.

## 3. Different environments for different notebooks

Most notebooks share one kernel, but a step may need another (a calibration
library, say). Set per-notebook overrides with `kernels`, and list the extra
environments to create with `extra_environments`:

```python
env1 = nb2slurm.Environment(name="myenv1", kernel="myenv1", conda_packages=["xarray"])
env2 = nb2slurm.Environment(name="myenv2", kernel="myenv2", pip_packages=["sceua"])

wf = nb2slurm.Workflow(
    name="proj", notebooks=nbs, kernel="myenv1", varying=["region"],
    environment=env1,                                 # default for most notebooks
    kernels={"notebooks/step_8.ipynb": "myenv2"},     # this one runs under myenv2
    extra_environments=[env2],                        # so myenv2 is created too
)

wf.create_environment(ssh=cfg)   # builds BOTH envs + registers BOTH kernels
```

The runner picks `kernels.get(notebook, kernel)` per notebook. Drop
`extra_environments` if `myenv2` already exists on the cluster — then the
`kernels` mapping is all you need.

## Checking before you submit

```python
wf.check(ssh=cfg)
```

{meth}`~nb2slurm.Workflow.check` confirms that `remote_dir`, your notebooks, the
built `scripts/`, the conda environment and the Jupyter kernel all exist, so a
missing piece is a clear message here instead of a failed job later.
