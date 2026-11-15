"""Summarize reviewer effort from a review file and its timing sidecar.

Reports decisions by action, how corrections changed the proposals (status changes, links added
and removed), and time per component. Pair it with score_development_mappings.py --reviews to see
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


def effort(entries, store):
    by_mapping = {entry["mapping"]["mapping_id"]: entry for entry in entries}
    history = list(read_jsonl(store.path)) if store.path.exists() else []
    seconds = Counter()
    if store.timing_path.exists():
        for event in read_jsonl(store.timing_path):
            if event.get("event") == "saved" and event.get("mapping_id") in by_mapping:
                seconds[event["mapping_id"]] += float(event.get("elapsed_seconds", 0))
    actions = Counter(record["action"] for record in store.current.values())
    actions["pending"] += len(entries) - len(store.current)
    changes = Counter()
    for mapping_id, record in store.current.items():
        if record["action"] != "correct":
            continue
        proposal, corrected = by_mapping[mapping_id]["mapping"]["assessment"], record["corrected_assessment"]
        changes["status_changed"] += proposal["status"] != corrected["status"]
        changes["links_added"] += len(links(corrected) - links(proposal))
        changes["links_removed"] += len(links(proposal) - links(corrected))
        changes["rationale_changed"] += proposal["rationale"] != corrected["rationale"]
    timed = [value for mapping_id, value in seconds.items() if mapping_id in store.current]
    return {
        "components": len(entries), "decisions": {action: actions[action] for action in ("accept", "correct", "reject", "pending")},
        "decisions_revised": len(history) - len({record["mapping_id"] for record in history}),
        "corrections": dict(changes),
        "components_timed": len(timed), "total_seconds": round(sum(timed), 1),
        "median_seconds_per_component": round(statistics.median(timed), 1) if timed else None,
        "mean_seconds_per_component": round(statistics.fmean(timed), 1) if timed else None,
    }


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
