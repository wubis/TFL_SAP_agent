"""Freeze the evaluation configuration before the held-out run.

Run once, on a clean working tree, after development is finished:

    python3 benchmark/freeze_config.py --date 2026-12-01

It copies benchmark/evaluation-config.draft.json to benchmark/frozen-config-<date>.json with the
commit of the code being frozen. Commit that file alone, tag the commit, and pass the file to
benchmark/evaluate.py --partition held_out --frozen-config. After the freeze nobody changes the agent.
"""

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE_PATHS = ("traceability", "schemas", "benchmark/evaluate.py", "benchmark/score_development_mappings.py",
              "benchmark/score_development_retrieval.py", "benchmark/display-conventions.json", "data/source-manifest.json")


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
    frozen = {**draft, "status": "frozen", "frozen_on": date, "code_commit": git(root, "rev-parse", "HEAD"),
              "model_identifiers": models,
              "note": "Frozen settings for the held-out evaluation. The limits were set on development families only."}
    target.write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8")
    return target


def freeze_problems(root, frozen):
    """Reasons the current checkout is not the frozen, tagged state the held-out run requires."""
    found = []
    if frozen.get("status") != "frozen" or not frozen.get("code_commit") or not frozen.get("model_identifiers"):
        return ["The configuration is not a frozen file written by benchmark/freeze_config.py"]
    try:
        if subprocess.run(["git", "-C", str(root), "diff", "--quiet", frozen["code_commit"], "--", *CODE_PATHS]).returncode:
            found.append("Code, schema, conventions, or manifest changed since the freeze")
        if git(root, "status", "--porcelain", "--", *CODE_PATHS):
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
