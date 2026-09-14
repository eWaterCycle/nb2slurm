# Connecting to the cluster

{class}`~nb2slurm.SSHConfig` is how nb2slurm reaches the HPC: paramiko for
commands (`sbatch`, `squeue`, `scancel`), `rsync` for file sync. You need an SSH
key registered on the cluster.

```python
import nb2slurm

cfg = nb2slurm.SSHConfig(
    host="snellius.surf.nl",
    user="me",
    remote_dir="/home/me/myproject",
    key_filename="~/.ssh/id_ed25519",
)

cfg.test_connection()   # runs hostname/whoami, prints a clear OK/FAIL
```

{meth}`~nb2slurm.SSHConfig.test_connection` is the cheapest first check: it fails
fast on an unreachable host instead of hanging, and on an encrypted key it tells
you exactly what to do about it. Run it before `push` or `submit`.

## Getting a key registered

nb2slurm can create the key, but **you** register it — most clusters disable
password login, so no tool can install it for you.

```python
nb2slurm.generate_key(key_type="ed25519")   # -> ~/.ssh/id_ed25519 (+ .pub)
print(nb2slurm.public_key("~/.ssh/id_ed25519"))   # reprint any time
```

`key_type` is `"ed25519"` (recommended — modern and fixed-size, sidestepping the
legacy RSA/DSA baggage some setups trip over) or `"rsa"` (the default, `bits`
wide). An existing key is left alone unless you pass `overwrite=True`, so this is
safe to re-run.

Then add the printed **public** key on the cluster's side:

- **SURF / Spider / Snellius** and many academic clusters: paste it into the
  key-upload page of their portal, or send it to the service desk — look for
  *"add SSH public key"* in your HPC's docs.
- If your cluster still allows password login, append it to
  `~/.ssh/authorized_keys` on a login node yourself.

## Passphrase-protected keys

The "password" most clusters prompt for is your key's **passphrase**, decrypted
locally — not a server account password. Two ways to handle it:

- **ssh-agent (recommended).** Run `ssh-add ~/.ssh/id_ed25519` once in a
  terminal. Both nb2slurm *and* `rsync` then authenticate through the agent, with
  no secret in the notebook and no prompts to hang on.
- **`passphrase=` on the config.** `SSHConfig(..., passphrase="…")` unlocks the
  paramiko calls ({meth}`~nb2slurm.SSHConfig.test_connection`,
  {meth}`~nb2slurm.Workflow.submit`, {meth}`~nb2slurm.Workflow.status`,
  {meth}`~nb2slurm.Workflow.check`), but {meth}`~nb2slurm.Workflow.push` and
  {meth}`~nb2slurm.Workflow.pull` shell out to the `rsync` CLI and still need the
  agent — so prefer `ssh-add` for the full workflow.

`password` is for actual password authentication, which is rare on HPC.

```{admonition} Secrets are never written to disk
:class: tip
{func}`~nb2slurm.save_config` strips `password` and `passphrase` before writing
`control_config.json`, so the control notebooks can share a config file without
leaking credentials. Set them again after {func}`~nb2slurm.load_config` if your
cluster needs them.
```
