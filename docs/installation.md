# Installation

```bash
pip install nb2slurm
```

Python 3.9 or newer. The dependencies (`papermill`, `filelock`, `jinja2`,
`paramiko`) are installed with it.

## What you need besides the package

On your **own machine** (laptop, or a Jupyter server):

- nb2slurm and Jupyter, to run your workflow for one subject and drive the cluster.
- `rsync`, used by {meth}`~nb2slurm.Workflow.push` and
  {meth}`~nb2slurm.Workflow.pull`. On Windows use WSL, Git Bash or conda's
  `rsync` — [the WSL notebook](FOR_WINDOWS_USERS.ipynb) installs one for you.
- SSH access to the cluster — a key is easiest:

  ```python
  import nb2slurm
  nb2slurm.generate_key(key_type="ed25519")          # only once, if you have no key yet
  print(nb2slurm.public_key("~/.ssh/id_ed25519"))    # paste this into your HPC account
  ```

  See [Connecting to the cluster](ssh.md) for registering the key, passphrases
  and `test_connection()`.

On the **cluster**:

- nb2slurm installed in the environment the jobs run in, and a registered Jupyter
  kernel for papermill to execute the notebooks with. nb2slurm can create both for
  you — see [Environments and kernels](environments.md).
- `rclone`, only if you use `mounts=[...]`.

{meth}`Workflow.check() <nb2slurm.Workflow.check>` verifies the cluster side for
you before the first submit.

## Development install

Working on nb2slurm itself rather than using it? The clone, test, lint and
docs-build steps live in the
[README](https://github.com/eWaterCycle/nb2slurm#development).
