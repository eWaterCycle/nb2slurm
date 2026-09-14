# jobs.json — jobs and the output tree in one file

Instead of a flat subject list, the jobs live in a nested JSON file. Each
root-to-leaf path is one SLURM job, and the levels line up with `varying`. The
output directory mirrors that hierarchy, so the job list and the folder tree can
never drift apart.

```json
{
    "Netherlands": {"north": ["green_climate", "climate_as_we_are", "heavy_industrialization"],
                    "south": ["green_climate", "climate_as_we_are", "heavy_industrialization"]
                   },
    "Germany":     {"north": ["green_climate", "climate_as_we_are", "heavy_industrialization"],
                    "south": ["green_climate", "climate_as_we_are", "heavy_industrialization"],
                    "east":  ["green_climate", "climate_as_we_are", "heavy_industrialization"],
                    "west":  ["green_climate", "climate_as_we_are", "heavy_industrialization"]
                   }
}
```

With `varying=["country", "region", "scenario"]` this means:

```text
jobs:  (Netherlands, north, green_climate)   (Netherlands, south, climate_as_we_are)   (Germany, north, heavy_industrialization)
dirs:  output/Netherlands/north/green_climate output/Netherlands/south/climate_as_we_are output/Germany/north/heavy_industrialization
```

## Format rules

- a **dict** nests one more level — its keys are the values of the next `varying`
  dimension;
- a **list** at the bottom means several jobs sharing the same parent path;
- **`null`**, `[]` or `{}` ends the path there (a leaf with no deeper level).

It is just JSON, so build it however suits you — a literal dict, a comprehension,
from a CSV:

```python
import json

countries = {"NL": ["north", "south"], "DE": ["north"]}
scenarios = ["green", "normal", "worse"]
jobs = {c: {r: scenarios for r in regions} for c, regions in countries.items()}
json.dump(jobs, open("jobs.json", "w"), indent=2)
```

## Using it

```python
wf = nb2slurm.Workflow(..., varying=["country", "region", "scenario"], jobs_json="jobs.json")

wf.build_outputs()                             # optional: pre-create the output/... tree
wf.submit(ssh=cfg)                             # one job per leaf path
wf.submit([("NL", "123", "ssp126")], ssh=cfg)  # override: an explicit subset
wf.submit(ssh=cfg, jobs_json="rerun.json")     # override: a different file
```

Because each job's output directory is built from the JSON, your first notebook
never creates folders — it just receives `outdir` and writes `settings.json`.

The parser is exposed as {class}`~nb2slurm.Structure` if you want it directly:

```python
nb2slurm.Structure.from_json("jobs.json").jobs()    # [(country, region, scenario), ...]
nb2slurm.Structure.from_json("jobs.json").build("output")
```

`build()` also flattens the file into `scripts/jobs.txt`, one job per line, so the
generated bash fallbacks never have to parse JSON.
