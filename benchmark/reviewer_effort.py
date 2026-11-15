"""Summarize reviewer effort from a review file and its timing sidecar.

Reports decisions by action, how corrections changed the proposals (status changes, links added
and removed), and minutes per component, split by review condition when a crossover plan was used. Pair it with score_development_mappings.py --reviews to see
which links remain unmatched after review.

    python3 benchmark/reviewer_effort.py --run runs/agent-run.jsonl --reviews runs/reviews.jsonl
"""

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from traceability.review import ReviewStore, load_run, read_jsonl  # noqa: E402


def links(assessment):
    return {(item["passage_id"], item["quote"]) for item in assessment["evidence"]}


def minutes(values):
    return {"components_timed": len(values), "total_minutes": round(sum(values) / 60, 2),
            "median_minutes_per_component": round(statistics.median(values) / 60, 2) if values else None,
            "mean_minutes_per_component": round(statistics.fmean(values) / 60, 2) if values else None}


def effort(entries, store):
    by_mapping = {entry["mapping"]["mapping_id"]: entry for entry in entries}
    history = list(read_jsonl(store.path)) if store.path.exists() else []
    seconds, condition, reviewers = Counter(), {}, set()
    if store.timing_path.exists():
        for event in read_jsonl(store.timing_path):
            if event.get("event") == "saved" and event.get("mapping_id") in by_mapping:
                seconds[event["mapping_id"]] += float(event.get("elapsed_seconds", 0))
                condition[event["mapping_id"]] = event.get("condition", "with_proposals")
                reviewers.add(event.get("reviewer"))
    actions = Counter(record["action"] for record in store.current.values())
    actions["pending"] += len(entries) - len(store.current)
    changes = Counter()
    for mapping_id, record in store.current.items():
        # A correction is a change to a proposal the reviewer saw. Without proposals there is nothing to correct.
        if record["action"] != "correct" or condition.get(mapping_id) == "without_proposals":
            continue
        proposal, corrected = by_mapping[mapping_id]["mapping"]["assessment"], record["corrected_assessment"]
        changes["corrections"] += 1
        changes["status_changed"] += proposal["status"] != corrected["status"]
        changes["links_added"] += len(links(corrected) - links(proposal))
        changes["links_removed"] += len(links(proposal) - links(corrected))
        changes["rationale_changed"] += proposal["rationale"] != corrected["rationale"]
    decided = [mapping_id for mapping_id in seconds if mapping_id in store.current]
    summary = {
        "reviewers": sorted(name for name in reviewers if name), "components": len(entries),
        "decisions": {action: actions[action] for action in ("accept", "correct", "reject", "pending")},
        "decisions_revised": len(history) - len({record["mapping_id"] for record in history}),
        "corrections_to_proposals": {key: changes[key] for key in
                                     ("corrections", "status_changed", "links_added", "links_removed", "rationale_changed")},
        "time": minutes([seconds[mapping_id] for mapping_id in decided]),
        "by_condition": {},
    }
    for name in sorted(set(condition.values())):
        chosen = [mapping_id for mapping_id in decided if condition[mapping_id] == name]
        summary["by_condition"][name] = {
            **minutes([seconds[mapping_id] for mapping_id in chosen]),
            "decisions": dict(Counter(store.current[mapping_id]["action"] for mapping_id in chosen))}
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    args = parser.parse_args()
    try:
        entries = load_run(args.run)
        print(json.dumps(effort(entries, ReviewStore(args.reviews, entries)), indent=1))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
