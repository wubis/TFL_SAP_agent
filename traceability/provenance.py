"""Record the settings and code version a run used, so results can be checked against a frozen configuration."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def code_state(root=ROOT):
    try:
        run = lambda *arguments: subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, text=True, check=True).stdout
        return {"code_commit": run("rev-parse", "HEAD").strip(),
                "uncommitted_changes": bool(run("status", "--porcelain", "--untracked-files=no").strip())}
    except (subprocess.CalledProcessError, OSError):
        return {"code_commit": None, "uncommitted_changes": None}


def run_settings(system, **settings):
    """The record every run writes beside its results."""
    return {"system": system, **settings, **code_state()}
