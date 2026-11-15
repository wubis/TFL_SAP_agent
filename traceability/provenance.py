"""Record the settings and code version a run used, so results can be checked against a frozen configuration."""

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Files whose content decides how a run behaves and is scored. The frozen configuration file is not
# among them, so committing it after the freeze leaves the fingerprint unchanged.
PROTECTED_PATHS = ("traceability", "schemas", "benchmark/evaluate.py", "benchmark/score_development_mappings.py",
                   "benchmark/score_development_retrieval.py", "benchmark/display-conventions.json",
                   "data/source-manifest.json")


def git(root, *arguments):
    return subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, text=True, check=True).stdout


def code_state(root=ROOT):
    """The commit, a fingerprint of the protected files at that commit, and whether any of them has local changes.

    The fingerprint depends only on the content of the protected files, so two commits that differ
    elsewhere, for example by adding the frozen configuration, have the same fingerprint.
    """
    try:
        tree = git(root, "ls-tree", "-r", "HEAD", "--", *PROTECTED_PATHS)
        return {"code_commit": git(root, "rev-parse", "HEAD").strip(),
                "code_fingerprint": hashlib.sha256(tree.encode("utf-8")).hexdigest(),
                "uncommitted_changes": bool(git(root, "status", "--porcelain", "--", *PROTECTED_PATHS).strip())}
    except (subprocess.CalledProcessError, OSError):
        return {"code_commit": None, "code_fingerprint": None, "uncommitted_changes": None}


def run_settings(system, root=ROOT, **settings):
    """The record every run writes beside its results."""
    return {"system": system, **settings, **code_state(root)}
