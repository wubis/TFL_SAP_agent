"""Report what the development benchmark covers: shell types, component kinds, statuses, and challenge cases.

Challenge cases are counted from each record's challenge_cases tags. Five tags follow from the
record and are filled by benchmark/challenge_tags.py. Three need an annotator and read zero until
the records are tagged.

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

CASES = ("paraphrased_label", "similar_analysis_different_population", "general_convention_with_exception",
         "unsupported_footnote", "incomplete_specification", "evidence_across_multiple_sections",
         "alternative_valid_passages", "convention_only_component")


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
            tally["records_with_challenge_tags"] += "challenge_cases" in annotation
            for tag in annotation.get("challenge_cases", []):
                tally[f"case:{tag}"] += 1
            tally["feature:multi_passage_support"] += any(
                len(option) > 1 for group in annotation["evidence_groups"] for option in group["alternatives"]) \
                or len(annotation["evidence_groups"]) > 1
            tally["feature:ambiguity_or_contradiction"] += assessment["status"] == "needs_review"
            tally["feature:scanned_evidence"] += any(passage.get("extraction") == "ocr" for passage in evidence)
        by_family[family["family_id"]] = dict(sorted(tally.items()))
        totals.update(tally)
    for tag in CASES:
        totals.setdefault(f"case:{tag}", 0)
    thin = sorted(tag for tag in CASES if totals[f"case:{tag}"] <= 2)
    return {"partition": "development", "total": dict(sorted(totals.items())), "by_family": by_family,
            "cases_with_two_or_fewer_records": thin,
            "note": "The three tags an annotator sets read zero until annotators tag the records. "
                    "Zero there means not yet tagged, not absent."}


def main():
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    manifest = json.loads((ROOT / "data/source-manifest.json").read_text(encoding="utf-8"))
    print(json.dumps(coverage(manifest), indent=1))


if __name__ == "__main__":
    main()
