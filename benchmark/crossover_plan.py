"""Build the reviewer crossover plan for measuring review time with and without agent proposals.

Two reviewers work through the same components from one table, one figure, and one listing. Each
reviews half with the agent's proposals and half without, and the halves swap between reviewers,
so every component is reviewed once in each condition.

    python3 benchmark/crossover_plan.py --run runs/agent-run.jsonl --reviewers R1 R2 \
      --per-reviewer 24 --seed 7 > runs/crossover-plan.json

Reviewers should not have annotated the family they review. Pass the plan and a reviewer name to
the reviewer interface with --plan and --reviewer.
"""

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from traceability.review import load_run  # noqa: E402


def build_plan(entries, shell_types, reviewers, per_reviewer, seed):
    if len(reviewers) != 2 or reviewers[0] == reviewers[1]:
        raise ValueError("The crossover needs exactly two different reviewers")
    if per_reviewer < 2 or per_reviewer % 2:
        raise ValueError("--per-reviewer must be an even number of at least 2")
    rng = random.Random(seed)
    by_type = {}
    for entry in entries:
        component = entry["component"]
        by_type.setdefault(shell_types.get(component["shell_id"], "unknown"), []).append(component["component_id"])
    for ids in by_type.values():
        rng.shuffle(ids)
    # Draw from the shell types in turn so tables, figures, and listings are all represented.
    chosen, order = [], sorted(by_type)
    while len(chosen) < per_reviewer and any(by_type.values()):
        for shell_type in order:
            if by_type[shell_type] and len(chosen) < per_reviewer:
                chosen.append((shell_type, by_type[shell_type].pop()))
    if len(chosen) < per_reviewer:
        raise ValueError(f"The run has only {len(chosen)} components")
    # Alternate within each shell type so both halves hold the same mix.
    halves = ([], [])
    for shell_type in order:
        for _, component_id in (item for item in chosen if item[0] == shell_type):
            halves[len(halves[0]) > len(halves[1])].append(component_id)
    first, second = halves
    assignments = {
        reviewers[0]: {**dict.fromkeys(first, "with_proposals"), **dict.fromkeys(second, "without_proposals")},
        reviewers[1]: {**dict.fromkeys(first, "without_proposals"), **dict.fromkeys(second, "with_proposals")},
    }
    orders = {}
    for reviewer in reviewers:
        sequence = [component_id for _, component_id in chosen]
        rng.shuffle(sequence)
        orders[reviewer] = sequence
    return {"seed": seed, "per_reviewer": per_reviewer, "shell_types": {t: sum(1 for s, _ in chosen if s == t) for t in order},
            "assignments": assignments, "order": orders}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--reviewers", nargs=2, required=True, metavar=("FIRST", "SECOND"))
    parser.add_argument("--per-reviewer", type=int, default=24)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    try:
        manifest = json.loads((ROOT / "data/source-manifest.json").read_text(encoding="utf-8"))
        shell_types = {shell["document_id"]: shell["type"] for family in manifest["families"] for shell in family["shells"]}
        print(json.dumps(build_plan(load_run(args.run), shell_types, args.reviewers, args.per_reviewer, args.seed), indent=1))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
