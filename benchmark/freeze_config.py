"""Freeze the evaluation configuration before the held-out run.

Run once, on a clean working tree, after development is finished:

    python3 benchmark/freeze_config.py --date 2026-12-01

It copies benchmark/evaluation-config.draft.json to benchmark/frozen-config-<date>.json with a
fingerprint of the protected code, schema, conventions, and manifest. Commit that file alone, tag
the commit, produce the held-out runs from that tagged commit, and pass the file to
benchmark/evaluate.py --partition held_out --frozen-config. The fingerprint depends only on the
protected files, so the commit that adds the frozen file still matches. After the freeze nobody
changes the agent.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from traceability.provenance import PROTECTED_DESCRIPTION, code_state  # noqa: E402


def git(root, *arguments):
    return subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, text=True, check=True).stdout.strip()


def freeze(root, date):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ValueError("Give the freeze date as YYYY-MM-DD")
    if git(root, "status", "--porcelain"):
        raise ValueError("Commit or discard every change before freezing")
    draft = json.loads((root / "benchmark/evaluation-config.draft.json").read_text(encoding="utf-8"))
    target = root / f"benchmark/frozen-config-{date}.json"
    if target.exists():
        raise ValueError(f"{target.name} already exists")
    models = {name: system["model"] for name, system in draft["systems"].items() if "model" in system}
    state = code_state(root)
    frozen = {**draft, "status": "frozen", "frozen_on": date, "code_commit": state["code_commit"],
              "code_fingerprint": state["code_fingerprint"], "protected_paths": PROTECTED_DESCRIPTION,
              "model_identifiers": models,
              "note": "Frozen settings for the held-out evaluation. The limits were set on development families only. "
                      "code_fingerprint covers the protected paths, so later commits that leave them unchanged still match."}
    target.write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8")
    return target


def freeze_problems(root, frozen):
    """Reasons the current checkout is not the frozen, tagged state the held-out run requires."""
    if frozen.get("status") != "frozen" or not frozen.get("code_fingerprint") or not frozen.get("model_identifiers"):
        return ["The configuration is not a frozen file written by benchmark/freeze_config.py"]
    found = []
    try:
        state = code_state(root)
        if state["code_fingerprint"] is None:
            return ["Could not read the git history to confirm the freeze"]
        # Compare content, not commit IDs: the commit that adds the frozen file is later than the frozen code.
        if state["code_fingerprint"] != frozen["code_fingerprint"]:
            found.append("Code, schema, benchmark records, manifest, or dependencies changed since the freeze")
        if state["uncommitted_changes"]:
            found.append("There are uncommitted changes to frozen files")
        if not git(root, "tag", "--points-at", "HEAD"):
            found.append("Tag the commit that holds the frozen configuration before the held-out run")
    except (subprocess.CalledProcessError, OSError):
        found.append("Could not read the git history to confirm the freeze")
    return found


def frozen_file_problems(root, path):
    """Reasons a frozen configuration file cannot be trusted as the one that was frozen and tagged."""
    try:
        relative = Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return ["The frozen configuration must be the file committed in this repository"]
    if not re.fullmatch(r"benchmark/frozen-config-\d{4}-\d{2}-\d{2}\.json", relative):
        return ["The frozen configuration must be benchmark/frozen-config-<date>.json, as written by freeze_config.py"]
    try:
        if git(root, "status", "--porcelain", "--", relative):
            return ["The frozen configuration has uncommitted changes or is not committed"]
        commits = git(root, "log", "--format=%H", "--", relative).split()
    except (subprocess.CalledProcessError, OSError):
        return ["Could not read the git history of the frozen configuration"]
    if len(commits) != 1:
        return ["The frozen configuration was changed after it was first committed" if commits
                else "The frozen configuration is not committed"]
    return []


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", required=True, help="Freeze date, YYYY-MM-DD")
    args = parser.parse_args()
    try:
        target = freeze(ROOT, args.date)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"{exc}\n")
    print(f"Wrote {target.relative_to(ROOT)}.")
    print(f"Next: git add {target.relative_to(ROOT)} && git commit -m 'Freeze evaluation configuration' "
          f"&& git tag evaluation-freeze-{args.date}")


if __name__ == "__main__":
    main()
