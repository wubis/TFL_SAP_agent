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

from traceability.provenance import PROTECTED_PATHS, code_state  # noqa: E402


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
              "code_fingerprint": state["code_fingerprint"], "protected_paths": list(PROTECTED_PATHS),
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
            found.append("Code, schema, conventions, or manifest changed since the freeze")
        if state["uncommitted_changes"]:
            found.append("There are uncommitted changes to frozen files")
        if not git(root, "tag", "--points-at", "HEAD"):
            found.append("Tag the commit that holds the frozen configuration before the held-out run")
    except (subprocess.CalledProcessError, OSError):
        found.append("Could not read the git history to confirm the freeze")
    return found


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
