# Monte Carlo π example

A complete, runnable workflow: estimate π by throwing random darts at the unit
square. Each `(n_samples, seed)` pair is one SLURM job.

- [`monte_carlo2slurm.ipynb`](example_monte_carlo_pi/monte_carlo2slurm.ipynb) —
  the all-in-one control notebook: describe, build, dry-run, push, submit, pull.
- [`analyse_subsets.ipynb`](example_monte_carlo_pi/analyse_subsets.ipynb) —
  gathers every subset into one conclusion: π per seed, and $1/\sqrt{n}$
  convergence across sample sizes.
- The workflow itself: [`0_settings`](example_monte_carlo_pi/notebooks/0_settings.ipynb),
  [`1_simulate`](example_monte_carlo_pi/notebooks/1_simulate.ipynb),
  [`2_plot`](example_monte_carlo_pi/notebooks/2_plot.ipynb), with the helper in
  `scripts/montecarlo.py`.

The workflow notebooks run **locally** too — open them in Jupyter from
`notebooks/` and run top to bottom. Their parameters cells default to
`n_samples=1000`, `seed=1` and a local `outdir`. These are the same notebooks
SLURM executes; nb2slurm only injects a different `(n_samples, seed)` and points
`outdir` at `output/<n_samples>/<seed>/`.

The jobs come from a `jobs.json` generated in the control notebook:

```python
jobs = {str(n): [str(s) for s in seeds] for n in n_samples}
```

Results are kept out of this branch — see the
[example-results branch](https://github.com/eWaterCycle/nb2slurm/tree/example-results/docs/example_monte_carlo_pi)
for a run with output.

```{toctree}
:hidden:

example_monte_carlo_pi/README
example_monte_carlo_pi/monte_carlo2slurm
example_monte_carlo_pi/notebooks/0_settings
example_monte_carlo_pi/notebooks/1_simulate
example_monte_carlo_pi/notebooks/2_plot
example_monte_carlo_pi/analyse_subsets
```
