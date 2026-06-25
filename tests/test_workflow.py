import json
from pathlib import Path

import pytest

from nb2slurm import Done, Environment, Settings, Structure, Workflow
from nb2slurm.ssh import CommandResult


class FakeSSH:
    """Stand-in for SSHConfig: pass a predicate deciding which commands succeed."""

    user = "tester"

    def __init__(self, succeeds):
        self.succeeds = succeeds
        self.commands = []

    def run(self, command, cwd=None):
        self.commands.append(command)
        ok = self.succeeds(command)
        return CommandResult(command, 0 if ok else 1, "out" if ok else "", "" if ok else "err")


def make_wf(tmp_path, **kw):
    return Workflow(
        name="square",
        notebooks=kw.pop("notebooks", ["notebooks/0_settings.ipynb", "notebooks/1_compute.ipynb"]),
        kernel=kw.pop("kernel", "python3"),
        varying=kw.pop("varying", ["item_id"]),
        resources=dict(nodes=1, cpus=2, time="00:05:00"),
        project_dir=str(tmp_path),
        **kw,
    )


def test_build_writes_all_scripts(tmp_path):
    wf = make_wf(tmp_path)
    written = wf.build()
    for kind in ("runner", "slurm", "submit_batch", "submit_jobs", "cancel", "structure"):
        assert written[kind].exists()
    assert wf.runner_path.name == "run_workflow.py"


def test_runner_template_contents(tmp_path):
    wf = make_wf(tmp_path, conda_env="myenv")
    wf.build()
    runner = wf.runner_path.read_text()
    assert "VARYING = ['item_id']" in runner
    assert "notebooks/0_settings.ipynb" in runner
    slurm = wf.slurm_path.read_text()
    assert "conda activate myenv" in slurm
    assert "python scripts/run_workflow.py $ITEM_ID" in slurm


def test_on_hpc_detects_batch_env(monkeypatch):
    from nb2slurm import on_hpc
    for var in ("NB2SLURM", "SLURM_JOB_ID", "SLURM_JOBID"):
        monkeypatch.delenv(var, raising=False)
    assert on_hpc() is False
    monkeypatch.setenv("SLURM_JOB_ID", "12345")
    assert on_hpc() is True


def test_on_hpc_nb2slurm_sentinel(monkeypatch):
    from nb2slurm import on_hpc
    for var in ("NB2SLURM", "SLURM_JOB_ID", "SLURM_JOBID"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NB2SLURM", "1")
    assert on_hpc() is True


def test_slurm_script_exports_sentinel(tmp_path):
    wf = make_wf(tmp_path)
    wf.build()
    assert "export NB2SLURM=1" in wf.slurm_path.read_text()


def test_no_environment_no_conda_activate(tmp_path):
    # cluster provides its own Python: no environment, no conda_env
    wf = make_wf(tmp_path, kernel="cluster_kernel")
    wf.build()
    slurm = wf.slurm_path.read_text()
    assert "conda activate" not in slurm
    assert "python scripts/run_workflow.py $ITEM_ID" in slurm


def test_setup_lines_for_module_clusters(tmp_path):
    wf = make_wf(tmp_path, kernel="cluster_kernel",
                 setup=["module load 2023", "module load Python/3.11"])
    wf.build()
    slurm = wf.slurm_path.read_text()
    assert "module load 2023" in slurm
    assert "module load Python/3.11" in slurm
    # setup runs before the workflow
    assert slurm.index("module load Python/3.11") < slurm.index("python scripts/run_workflow.py")


def test_per_notebook_kernel_override(tmp_path):
    wf = make_wf(
        tmp_path,
        notebooks=["notebooks/0_settings.ipynb", "notebooks/1_compute.ipynb"],
        kernel="myenv1",
        kernels={"notebooks/1_compute.ipynb": "myenv2"},
    )
    wf.build()
    runner = wf.runner_path.read_text()
    assert 'KERNEL = "myenv1"' in runner
    assert "'notebooks/1_compute.ipynb': 'myenv2'" in runner
    assert "kernel_name=KERNELS.get(nb, KERNEL)" in runner
    assert "kernel_name=KERNELS.get(first, KERNEL)" in runner


def test_kernels_unknown_notebook_rejected(tmp_path):
    with pytest.raises(ValueError, match="kernels keys not in notebooks"):
        make_wf(tmp_path, notebooks=["notebooks/a.ipynb"],
                kernels={"notebooks/typo.ipynb": "myenv2"})


def test_slurm_mounts(tmp_path):
    wf = make_wf(tmp_path, mounts=[{"remote": "dcache:/x", "mountpoint": "/scratch/x"}])
    wf.build()
    slurm = wf.slurm_path.read_text()
    assert "rclone mount --read-only --allow-non-empty dcache:/x /scratch/x" in slurm


def test_submit_dry_run_multikey(tmp_path, capsys):
    wf = make_wf(tmp_path, varying=["region_id", "country"], concurrency=2)
    wf.build()
    wf.submit([("123", "NL"), ("456", "DE"), ("789", "FR")], dry_run=True)
    out = capsys.readouterr().out
    assert "--job-name=123_NL" in out
    assert "output/456/DE/456_DE.out" in out
    assert "REGION_ID=789,COUNTRY=FR" in out
    # 3rd job (index 2) chains on job 0 (concurrency=2)
    assert "--dependency=afterany:" in out


def test_output_paths_default_to_root(tmp_path, capsys):
    wf = make_wf(tmp_path)
    wf.build()
    runner = wf.runner_path.read_text()
    assert 'Path("output", *values.values())' in runner
    assert 'Done("done/done.csv")' in runner
    wf.submit([5], dry_run=True)
    assert "output/5/5.out" in capsys.readouterr().out


def test_output_paths_configurable(tmp_path, capsys):
    wf = make_wf(tmp_path, output_dir="/scratch/me/out", done_csv="/scratch/me/done.csv")
    wf.build()
    runner = wf.runner_path.read_text()
    assert 'Path("/scratch/me/out", *values.values())' in runner
    assert 'Done("/scratch/me/done.csv")' in runner
    submit_sh = (wf.scripts_dir / "submit_jobs.sh").read_text()
    assert "/scratch/me/out/${item_id}" in submit_sh
    wf.submit([5], dry_run=True)
    out = capsys.readouterr().out
    assert "mkdir -p /scratch/me/out/5" in out
    assert "/scratch/me/out/5/5.out" in out


def test_normalise_item_validation(tmp_path):
    wf = make_wf(tmp_path, varying=["a", "b"])
    with pytest.raises(ValueError):
        wf.submit([1], dry_run=True)


def test_environment_yaml():
    env = Environment(name="myenv", kernel="myenv", python="3.11",
                      conda_packages=["xarray", "numpy"],
                      pip_packages=["nb2slurm", "ewatercycle"])
    y = env.to_yaml()
    assert "name: myenv" in y
    assert "- python=3.11" in y
    assert "- ipykernel" in y          # required for papermill
    assert "  - xarray" in y
    assert "      - ewatercycle" in y  # under pip:


def test_environment_create_command_mentions_kernel():
    env = Environment(name="myenv", kernel="mykern")
    cmd = env._create_command()
    assert "env create -f environment.yml" in cmd
    assert "ipykernel install --user --name mykern" in cmd


def test_workflow_writes_environment_and_validates(tmp_path):
    env = Environment(name="myenv", kernel="myenv")
    wf = make_wf(tmp_path, kernel="myenv", environment=env)
    written = wf.build()
    assert written["environment"].exists()
    assert wf.conda_env == "myenv"          # derived from environment
    slurm = wf.slurm_path.read_text()
    assert "conda activate myenv" in slurm


def test_workflow_environment_kernel_mismatch(tmp_path):
    env = Environment(name="myenv", kernel="kernA")
    with pytest.raises(ValueError):
        make_wf(tmp_path, kernel="kernB", environment=env)


def test_check_all_pass(tmp_path, capsys):
    wf = make_wf(tmp_path, kernel="myenv", conda_env="myenv")
    ssh = FakeSSH(lambda c: True)
    results = wf.check(ssh=ssh)
    assert all(r["ok"] for r in results)
    names = {r["name"] for r in results}
    assert "project directory" in names
    assert "conda env 'myenv'" in names
    assert "kernel 'myenv'" in names
    assert "FAIL" not in capsys.readouterr().out


def test_check_reports_missing_kernel(tmp_path):
    wf = make_wf(tmp_path, kernel="myenv", conda_env="myenv")
    # everything passes except the kernel check
    ssh = FakeSSH(lambda c: "jupyter/kernels" not in c)
    with pytest.raises(RuntimeError, match="kernel 'myenv'"):
        wf.check(ssh=ssh)
    results = wf.check(ssh=ssh, raise_on_error=False)
    failed = [r for r in results if not r["ok"]]
    assert [r["name"] for r in failed] == ["kernel 'myenv'"]
    assert failed[0]["hint"].startswith("run wf.create_environment")


def test_check_remote_dir_missing(tmp_path):
    wf = make_wf(tmp_path, kernel="myenv", conda_env="myenv")
    ssh = FakeSSH(lambda c: c != "pwd")  # remote_dir absent -> pwd fails
    results = wf.check(ssh=ssh, raise_on_error=False)
    pd = next(r for r in results if r["name"] == "project directory")
    assert not pd["ok"]
    assert "remote_dir" in pd["hint"]


SPEC = {
    "NL": {"123": ["ssp126", "ssp245"]},
    "DE": {"789": ["ssp585"]},
}


def test_structure_jobs():
    assert Structure(SPEC).jobs() == [
        ("NL", "123", "ssp126"),
        ("NL", "123", "ssp245"),
        ("DE", "789", "ssp585"),
    ]


def test_structure_paths_and_build(tmp_path):
    struct = Structure(SPEC)
    rels = set(struct.paths(tmp_path))
    assert rels == {"NL/123/ssp126", "NL/123/ssp245", "DE/789/ssp585"}
    assert not (tmp_path / "NL").exists()          # paths() does no I/O

    paths = struct.build(tmp_path)
    for rel, p in paths.items():
        assert p.is_dir()
        assert p == tmp_path.joinpath(*rel.split("/"))
    struct.build(tmp_path)                          # idempotent


def test_structure_from_json(tmp_path):
    f = tmp_path / "jobs.json"
    f.write_text(json.dumps(SPEC))
    assert Structure.from_json(f).jobs() == Structure(SPEC).jobs()


def test_structure_empty_and_validation():
    assert Structure().paths("x") == {}
    assert Structure({}).jobs() == []
    with pytest.raises(TypeError):
        Structure(["not", "a", "dict"])


def test_submit_reads_jobs_json_by_default(tmp_path, capsys):
    wf = make_wf(tmp_path, varying=["country", "region", "scenario"])
    wf.build()
    (tmp_path / "jobs.json").write_text(json.dumps(SPEC))
    wf.submit(dry_run=True)                          # no items -> reads jobs.json
    out = capsys.readouterr().out
    assert "--job-name=NL_123_ssp126" in out
    assert "output/DE/789/ssp585/DE_789_ssp585.out" in out
    assert "COUNTRY=NL,REGION=123,SCENARIO=ssp126" in out


def test_build_generates_jobs_txt_from_json(tmp_path):
    wf = make_wf(tmp_path, varying=["country", "region", "scenario"])
    (tmp_path / "jobs.json").write_text(json.dumps(SPEC))
    written = wf.build()
    jobs_txt = written["jobs_txt"].read_text().splitlines()
    assert jobs_txt[0].startswith("# one job per line")
    assert "NL 123 ssp126" in jobs_txt
    assert "DE 789 ssp585" in jobs_txt


def test_build_skips_jobs_txt_without_json(tmp_path):
    wf = make_wf(tmp_path)               # no jobs.json present
    written = wf.build()
    assert "jobs_txt" not in written


def test_submit_batch_script_is_simple(tmp_path):
    wf = make_wf(tmp_path, varying=["country", "region", "scenario"])
    wf.build()
    batch = (wf.scripts_dir / "submit_batch.sh").read_text()
    jobs = (wf.scripts_dir / "submit_jobs.sh").read_text()
    # the basic one has no concurrency/dependency machinery
    assert "dependency" not in batch
    assert "jobids" not in batch
    assert "read -r country region scenario" in batch
    assert "scripts/job.slurm" in batch
    # the throttled one still does
    assert "dependency=afterany" in jobs


def test_build_outputs_from_json(tmp_path):
    wf = make_wf(tmp_path, varying=["country", "region", "scenario"])
    (tmp_path / "jobs.json").write_text(json.dumps(SPEC))
    paths = wf.build_outputs()
    assert (tmp_path / "output" / "NL" / "123" / "ssp126").is_dir()
    assert (tmp_path / "output" / "DE" / "789" / "ssp585").is_dir()
    assert set(paths) == {"NL/123/ssp126", "NL/123/ssp245", "DE/789/ssp585"}


def _ssh():
    from nb2slurm import SSHConfig
    return SSHConfig(host="hpc", user="me", remote_dir="/home/me/proj",
                     key_filename="~/.ssh/id_ed25519")


def test_push_uploads_source_not_outputs(tmp_path):
    wf = make_wf(tmp_path)
    cmd = wf.push(_ssh(), dry_run=True)
    assert cmd[0] == "rsync"
    assert "ssh -i ~/.ssh/id_ed25519" in cmd        # -e transport
    # outputs are excluded so push can't wipe remote results
    for ex in ("output", "done", ".git"):
        assert ex in cmd
    assert cmd[-1] == "me@hpc:/home/me/proj/"        # dst is the remote project root
    assert cmd[-2].endswith("/")                      # src is the local project


def test_pull_fetches_only_outputs(tmp_path):
    wf = make_wf(tmp_path)
    cmds = wf.pull(_ssh(), dry_run=True)
    flat = " ".join(" ".join(c) for c in cmds)
    # the whole point: pull never touches source, so local notebook edits survive
    assert "notebooks" not in flat
    assert "scripts" not in flat
    assert "jobs.json" not in flat
    # it does fetch output/ and done/
    assert "me@hpc:/home/me/proj/output/" in flat
    assert "me@hpc:/home/me/proj/done/" in flat


def test_config_save_load_roundtrip(tmp_path):
    from nb2slurm import save_config, load_config, SSHConfig
    env = Environment(name="e", kernel="e", conda_packages=["xarray"])
    wf = make_wf(tmp_path, kernel="e", varying=["country", "region"],
                 jobs_json="jobs.json", environment=env, conda_env="e")
    cfg = SSHConfig(host="h", user="u", remote_dir="/r",
                    key_filename="k", password="secret")

    path = save_config(tmp_path / "control_config.json", workflow=wf, ssh=cfg)

    # secrets are not written to disk
    assert "secret" not in path.read_text()

    wf2, cfg2 = load_config(path)
    assert wf2.name == wf.name
    assert wf2.varying == ["country", "region"]
    assert wf2.jobs_json == "jobs.json"
    assert wf2.environment.name == "e"
    assert wf2.environment.conda_packages == ["xarray"]
    assert wf2.kernels == wf.kernels
    assert (cfg2.host, cfg2.user, cfg2.remote_dir) == ("h", "u", "/r")
    assert cfg2.password is None


def test_config_load_without_ssh(tmp_path):
    from nb2slurm import save_config, load_config
    wf = make_wf(tmp_path)
    path = save_config(tmp_path / "c.json", workflow=wf)   # no ssh
    wf2, cfg2 = load_config(path)
    assert cfg2 is None
    assert wf2.name == wf.name


def test_done_roundtrip(tmp_path):
    done = Done(tmp_path / "done.csv")
    assert not done.is_done("k1")
    done.mark("k1")
    assert done.is_done("k1")
    done.mark("k1")  # idempotent
    assert done.is_done("k1")
    assert not done.is_done("k2")


def test_settings_roundtrip(tmp_path):
    outdir = tmp_path / "output" / "123"
    path = Settings.write(outdir, {"region_id": "123", "outdir": str(outdir)})
    assert path == outdir / "settings.json"
    loaded = Settings.load(path)
    assert loaded["region_id"] == "123"
