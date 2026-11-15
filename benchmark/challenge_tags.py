"""Fill the challenge-case tags that follow from a reference record itself, and report tag coverage.

Five of the eight tags are facts about the record: an unsupported footnote, an incomplete
specification, evidence across several sections, alternative valid passages, and a convention-only
component. This script sets those. The other three need an annotator's judgment and are left alone:
a paraphrased label, a similar analysis for a different population, and a general convention with
an endpoint-specific exception.

    python3 benchmark/challenge_tags.py --partition development            # report only
    python3 benchmark/challenge_tags.py --partition development --write    # add the derivable tags

For the held-out partition it prints counts only, never records. Held-out tagging is done by an
annotator who is not tuning the agent, before any held-out run.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from traceability.review import read_jsonl  # noqa: E402

JUDGED = ("paraphrased_label", "similar_analysis_different_population", "general_convention_with_exception")
DERIVED = ("unsupported_footnote", "incomplete_specification", "evidence_across_multiple_sections",
           "alternative_valid_passages", "convention_only_component")


def derived_tags(annotation, component):
    assessment = annotation["assessment"]
    facts = {
        "unsupported_footnote": component["kind"] == "footnote" and assessment["status"] == "not_found_in_supplied_sap"
                                and not assessment["convention_ids"],
        "incomplete_specification": assessment["status"] == "partially_supported",
        "evidence_across_multiple_sections": len({passage["section"] for passage in assessment["evidence"]}) > 1,
        "alternative_valid_passages": any(len(group["alternatives"]) > 1 for group in annotation["evidence_groups"]),
        "convention_only_component": bool(assessment["convention_ids"]),
    }
    return [tag for tag in DERIVED if facts[tag]]


def process(folder, write):
    components = {record["component_id"]: record for record in read_jsonl(folder / "components.jsonl")}
    path = folder / "reference-annotations.jsonl"
    annotations, counts, changed = list(read_jsonl(path)), Counter(), 0
    for annotation in annotations:
        existing = annotation.get("challenge_cases", [])
        judged = [tag for tag in existing if tag in JUDGED]
        tags = [*judged, *derived_tags(annotation, components[annotation["component_id"]])]
        counts.update(tags)
        counts["records"] += 1
        counts["records_with_a_judged_tag"] += bool(judged)
        if write and tags != existing:
            annotation["challenge_cases"] = tags
            changed += 1
    if write and changed:
        path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in annotations), encoding="utf-8")
    return counts, changed


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--partition", choices=("development", "held_out"), required=True)
    parser.add_argument("--write", action="store_true", help="Write the derivable tags into the records")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "data/source-manifest.json").read_text(encoding="utf-8"))
    total, report = Counter(), {}
    for family in manifest["families"]:
        if family["partition"] != args.partition:
            continue
        counts, changed = process(ROOT / "benchmark" / args.partition / family["family_id"], args.write)
        total.update(counts)
        report[family["family_id"]] = {"records": counts["records"], "records_changed": changed}
    print(json.dumps({
        "partition": args.partition, "families": report, "records": total["records"],
        "derived_tags": {tag: total[tag] for tag in DERIVED},
        "judged_tags": {tag: total[tag] for tag in JUDGED},
        "records_with_a_judged_tag": total["records_with_a_judged_tag"],
        "note": "Judged tags are assigned by an annotator. A zero there means not yet tagged, not absent.",
    }, indent=1))


if __name__ == "__main__":
    main()
