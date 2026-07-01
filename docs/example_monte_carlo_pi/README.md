# Example: Monte Carlo Simulation of Pi

In this basic example we will show what is needed for nb2slurm to work. Along with niceties.
Provided you have access to HPC the user should be able to run [this notebook](monte_carlo2slurm.ipynb) after changing the parameters in the first cell.
The resulting output will be shown in [this branch]() to keep it clean here.
Note that the notebooks have been run already, that is because we put emphasis on the fact that they work locally as well!

## Requirements

### before
- access to HPC
  - SSH setup (we provide a function to generate the ssh key here, but the HPC docs guide you through the setup)

- jobs.json
  - we provide a simple one, but the code is provided to change it, feel free to play around with it
- notebooks for the montecarlo simulation workflow
- a notebook that runs the nb2slurm setup 
- a notebook that analyses the output

That is it...

The montecarlo function is imported to serve as an example here. 
But this simple function could be included into the 1_simulate.ipynb.

### Notebooks

0. settings file
1. the simulation
2. plotting