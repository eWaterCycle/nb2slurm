# API reference

The whole public surface is re-exported at the top level, so `import nb2slurm` is
the only import you need.

## Workflow

```{eval-rst}
.. autoclass:: nb2slurm.Workflow
   :members:
```

## Environment

```{eval-rst}
.. autoclass:: nb2slurm.Environment
   :members:
```

## SSH

```{eval-rst}
.. autoclass:: nb2slurm.SSHConfig
   :members:

.. autofunction:: nb2slurm.generate_key

.. autofunction:: nb2slurm.public_key
```

## Inside your notebooks

```{eval-rst}
.. autoclass:: nb2slurm.Settings
   :members:

.. autofunction:: nb2slurm.on_hpc
```

## Jobs, outputs and saved config

```{eval-rst}
.. autoclass:: nb2slurm.Structure
   :members:

.. autoclass:: nb2slurm.Done
   :members:

.. autofunction:: nb2slurm.save_config

.. autofunction:: nb2slurm.load_config
```
