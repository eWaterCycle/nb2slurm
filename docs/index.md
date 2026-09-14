# nb2slurm

nb2slurm takes a notebook workflow that runs for **one subject** (one catchment,
one region, one number, ...) and generates everything needed to run it for **many
subjects** on a SLURM HPC — driven entirely from a notebook, no command line.

```{admonition} Still in development
:class: warning
Nothing is guaranteed yet. The Monte Carlo example works; the API can still change.
```

It is both a package and a scaffolder:

- **Package (logic):** the importable `nb2slurm` — the {class}`~nb2slurm.Workflow`
  class plus helpers for settings, done-tracking, environments and an SSH transport.
- **Scaffolder (templates):** bundled Jinja2 templates that
  {meth}`Workflow.build() <nb2slurm.Workflow.build>` renders into a concrete
  `scripts/` directory for your project.

nb2slurm is the reusable generalisation of the eWaterCycle
[CCI-analysis-seamless](https://github.com/eWaterCycle/CCI-analysis-seamless)
project (its hardcoded `cci.py` + `run_cci.slurm` + `submit_*.sh`).

## Where to start

- New to HPC, SLURM or conda? Read [HPC for notebook users](hpc-for-beginners.md) first.
- Want the short version? [Quickstart](quickstart.md).
- Converting notebooks you already have? [The notebook contract](notebook-contract.md).
- Want to see it end to end? [Monte Carlo example](examples.md).

```{toctree}
:caption: Getting started
:maxdepth: 2

installation
quickstart
hpc-for-beginners
```

```{toctree}
:caption: Guide
:maxdepth: 2

notebook-contract
jobs-json
environments
generated-files
transfer
control-notebooks
```

```{toctree}
:caption: Examples
:maxdepth: 2

walkthrough
examples
```

```{toctree}
:caption: Reference
:maxdepth: 2

api
```
