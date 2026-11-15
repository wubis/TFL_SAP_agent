"""Report what the development benchmark covers: shell types, component kinds, statuses, and challenge cases.

Counts only what the records state. Paraphrased labels and similar-population traps are not tagged
in the records, so they cannot be counted here.

    python3 benchmark/coverage_report.py
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from traceability.review import read_jsonl  # noqa: E402


def coverage(manifest):
    totals, by_family = Counter(), {}
    for family in manifest["families"]:
        if family["partition"] != "development":
            continue
        folder = ROOT / "benchmark" / "development" / family["family_id"]
        components = {record["component_id"]: record for record in read_jsonl(folder / "components.jsonl")}
        shells = {shell["document_id"]: shell for shell in family["shells"]}
        tally = Counter()
        for annotation in read_jsonl(folder / "reference-annotations.jsonl"):
            component = components[annotation["component_id"]]
            shell = shells[component["shell_id"]]
            assessment = annotation["assessment"]
            evidence = assessment["evidence"]
            tally["components"] += 1
            tally[f"shell_type:{shell['type']}"] += 1
            tally[f"authenticity:{shell['authenticity']}"] += 1
            tally[f"kind:{component['kind']}"] += 1
            tally[f"status:{assessment['status']}"] += 1
            tally["case:multi_passage_support"] += any(
                len(option) > 1 for group in annotation["evidence_groups"] for option in group["alternatives"]) \
                or len(annotation["evidence_groups"]) > 1
            tally["case:multi_section_evidence"] += len({passage["section"] for passage in evidence}) > 1
            tally["case:alternative_passages_accepted"] += any(len(group["alternatives"]) > 1 for group in annotation["evidence_groups"])
            tally["case:convention_only"] += bool(assessment["convention_ids"])
            tally["case:unsupported_footnote"] += component["kind"] == "footnote" and assessment["status"] == "not_found_in_supplied_sap"
            tally["case:incomplete_specification"] += assessment["status"] == "partially_supported"
            tally["case:ambiguity_or_contradiction"] += assessment["status"] == "needs_review"
            tally["case:scanned_evidence"] += any(passage.get("extraction") == "ocr" for passage in evidence)
        by_family[family["family_id"]] = dict(sorted(tally.items()))
        totals.update(tally)
    return {"partition": "development", "total": dict(sorted(totals.items())), "by_family": by_family,
            "not_countable_from_records": ["paraphrased labels", "similar analyses for different populations",
                                           "general conventions with endpoint-specific exceptions"]}


def main():
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    manifest = json.loads((ROOT / "data/source-manifest.json").read_text(encoding="utf-8"))
    print(json.dumps(coverage(manifest), indent=1))


if __name__ == "__main__":
    main()
