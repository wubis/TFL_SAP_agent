"""Record the settings and code version a run used, so results can be checked against a frozen configuration."""

import hashlib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Everything whose content decides how a run behaves, is checked, or is scored: the agent package, the
# schema, every benchmark script and record (reference annotations included), the manifest, and the
# pinned dependencies. Documentation is left out. So are the frozen configuration and the record of the
# final run, which are written after the freeze and must not change the fingerprint.
PROTECTED_PREFIXES = ("traceability/", "schemas/", "benchmark/")
PROTECTED_FILES = ("data/source-manifest.json", "requirements.txt")
NOT_PROTECTED = re.compile(r"^benchmark/(frozen-config-[^/]*\.json|final-evaluation-record\.json)$|\.md$")
PROTECTED_DESCRIPTION = [*PROTECTED_PREFIXES, *PROTECTED_FILES,
                         "except Markdown files, benchmark/frozen-config-*.json, and benchmark/final-evaluation-record.json"]


def is_protected(path):
    return (path.startswith(PROTECTED_PREFIXES) or path in PROTECTED_FILES) and not NOT_PROTECTED.search(path)


def git(root, *arguments):
    return subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, text=True, check=True).stdout


def code_state(root=ROOT):
    """The commit, a fingerprint of the protected files at that commit, and whether any of them has local changes.

    The fingerprint depends only on the content of the protected files, so two commits that differ
    elsewhere, for example by adding the frozen configuration, have the same fingerprint.
    """
    try:
        entries = []
        for line in git(root, "ls-tree", "-r", "HEAD").splitlines():
            meta, _, path = line.partition("\t")
            if is_protected(path):
                entries.append(f"{meta.split()[2]} {path}")
        changed = [line[3:].split(" -> ")[-1].strip('"') for line in git(root, "status", "--porcelain").splitlines()]
        return {"code_commit": git(root, "rev-parse", "HEAD").strip(),
                "code_fingerprint": hashlib.sha256("\n".join(sorted(entries)).encode("utf-8")).hexdigest(),
                "uncommitted_changes": any(is_protected(path) for path in changed)}
    except (subprocess.CalledProcessError, OSError):
        return {"code_commit": None, "code_fingerprint": None, "uncommitted_changes": None}


def run_settings(system, root=ROOT, **settings):
    """The record every run writes beside its results."""
    return {"system": system, **settings, **code_state(root)}
