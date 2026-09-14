"""Sphinx configuration for the nb2slurm documentation.

Read the Docs builds this via ``.readthedocs.yaml``. Locally:

    pip install -e ".[docs]"
    sphinx-build -b html docs docs/_build/html
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# import nb2slurm straight from the repo, so autodoc also works uninstalled
sys.path.insert(0, str(ROOT / "src"))


def _version() -> str:
    """Read ``__version__`` from the package source (the single source of truth)."""
    text = (ROOT / "src" / "nb2slurm" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else "0.0.0"


# ----- project -----------------------------------------------------------------
project = "nb2slurm"
author = "Mark Melotto"
copyright = f"{date.today().year}, Mark Melotto and the eWaterCycle project"
release = _version()
version = release

# ----- general -----------------------------------------------------------------
extensions = [
    "myst_nb",  # parses both .md and .ipynb sources
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx_copybutton",
]

exclude_patterns = [
    "_build",
    "**/.ipynb_checkpoints",
    "**/scripts",  # generated example output, not documentation
]

# ----- MyST / notebooks --------------------------------------------------------
myst_enable_extensions = ["colon_fence", "deflist", "fieldlist"]
myst_heading_anchors = 3
# The notebooks need a cluster (SSH + SLURM), so never execute them on a builder.
nb_execution_mode = "off"

# ----- autodoc -----------------------------------------------------------------
autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
}
intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}

# ----- HTML --------------------------------------------------------------------
html_theme = "furo"
html_title = f"nb2slurm {release}"
html_static_path = ["_static"]
html_theme_options = {
    "source_repository": "https://github.com/eWaterCycle/nb2slurm/",
    "source_branch": "main",
    "source_directory": "docs/",
}
