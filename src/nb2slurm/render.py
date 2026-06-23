"""Render the bundled Jinja2 templates into a project's scripts/ directory."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any, Mapping

from jinja2 import Environment


def _env() -> Environment:
    # No autoescaping: these are shell/python scripts, not HTML.
    # Move the comment delimiters off the default "{# #}" so bash parameter
    # expansions like ${#arr[@]} don't get mistaken for Jinja comments.
    return Environment(
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        comment_start_string="<#nb2slurm#",
        comment_end_string="#nb2slurm#>",
    )


def render_template(template_name: str, context: Mapping[str, Any]) -> str:
    """Render one bundled template (e.g. 'run_workflow.py.j2') to a string."""
    source = (
        resources.files("nb2slurm.templates")
        .joinpath(template_name)
        .read_text(encoding="utf-8")
    )
    return _env().from_string(source).render(**context)


def write_rendered(
    template_name: str,
    out_path: str | Path,
    context: Mapping[str, Any],
    executable: bool = False,
) -> Path:
    """Render a template and write it to ``out_path``."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_template(template_name, context), encoding="utf-8")
    if executable:
        mode = out_path.stat().st_mode
        out_path.chmod(mode | 0o111)
    return out_path
