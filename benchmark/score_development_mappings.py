"""Score proposed or reviewed mappings for a development family against its reference annotations.

Reports, overall, by shell type, and by tagged challenge case: support-status accuracy, link precision and recall against the
reference citation anchors, complete evidence-group coverage, and abstention on components whose
reference status is not_found_in_supplied_sap.

A proposed link counts as matched when its quotation is found in the SAP passage it cites, it cites
the reference page, and that passage contains the reference anchor. A link with no saved source
passage, or whose quotation is not in the passage, is reported as unverified and never matched.
That is a passage-level proxy. A link it leaves unmatched may still
be an equivalent valid span, so unmatched links need a human check before they are called unsupported.
Links on components whose reference has no SAP evidence are reported separately.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from traceability.review import ReviewStore, load_run, read_jsonl, resolve  # noqa: E402


def matched_reference_ids(assessment, reference, sources):
    """Return matched reference passage IDs, links that matched one, and links with no verifiable source.

    `sources` maps passage IDs to passage text taken from the SAP. A link earns credit only when its
    passage is there and the quotation occurs in that text. A link whose passage is unknown, or whose
    quotation is not in the passage, is counted as unverified and never matched.
    """
    matched, hits, unverified = set(), 0, 0
    for link in assessment["evidence"]:
        text = sources.get(link["passage_id"])
        if text is None or " ".join(link["quote"].split()) not in text:
            unverified += 1
            continue
        found = {passage["passage_id"] for passage in reference["assessment"]["evidence"]
                 if passage["page"] == link["page"] and passage["quote"] in text}
        hits += bool(found)
        matched |= found
    return matched, hits, unverified


def score(entries, references, shell_types, reviews=None, extra_passages=None):
    ids = {entry["component"]["component_id"] for entry in entries}
    if ids != references.keys():
        missing, extra = sorted(references.keys() - ids), sorted(ids - references.keys())
        raise ValueError(f"Run and reference components differ (missing {missing[:3]}, unexpected {extra[:3]})")
    groups = {}
    for entry in entries:
        component = entry["component"]
        reference = references[component["component_id"]]
        mapping = entry["mapping"]
        if any(mapping[key] != reference[key] for key in ("sap_id", "sap_version")):
            raise ValueError(f"Mismatched SAP for {component['component_id']}")
        review = (reviews or {}).get(mapping["mapping_id"])
        action, assessment, _ = resolve(entry, review)
        if reviews is not None and action == "reject":
            # A rejected proposal leaves no standing status or link.
            assessment = {**assessment, "status": "rejected", "evidence": []}
        sources = {passage["passage_id"]: passage["text"] for passage in entry["retrieval"]["candidates"]}
        if reviews is not None and action == "correct":
            # Reviewer-found passages count only when their text was saved with the review.
            sources.update({pid: passage["text"] for pid, passage in (extra_passages or {}).items()})
        matched, hits, unverified = matched_reference_ids(assessment, reference, sources)
        expected = reference["assessment"]
        cases = [f"case: {tag}" for tag in reference.get("challenge_cases", [])]
        for name in ("all", shell_types.get(component["shell_id"], "unknown"), *cases):
            tally = groups.setdefault(name, Counter())
            tally["components"] += 1
            tally["status_correct"] += assessment["status"] == expected["status"]
            tally[f"confusion:{expected['status']}->{assessment['status']}"] += 1
            tally["proposed_links"] += len(assessment["evidence"])
            tally["matched_links"] += hits
            tally["unverified_links"] += unverified
            tally["reference_anchors"] += len(expected["evidence"])
            tally["matched_anchors"] += len(matched)
            if expected["evidence"]:
                tally["components_with_citations"] += 1
                tally["complete_components"] += all(
                    any(set(option) <= matched for option in group["alternatives"])
                    for group in reference["evidence_groups"])
            else:
                tally["links_where_reference_has_none"] += len(assessment["evidence"])
            if expected["status"] == "not_found_in_supplied_sap":
                tally["reference_not_found"] += 1
                tally["correct_abstentions"] += assessment["status"] == "not_found_in_supplied_sap"
                # needs_review with no evidence defers to a person without asserting a link.
                tally["deferred_without_links"] += assessment["status"] == "needs_review" and not assessment["evidence"]
    return groups


def report(name, tally):
    def rate(top, bottom):
        return round(tally[top] / tally[bottom], 3) if tally[bottom] else None
    confusion = {key.split(":", 1)[1]: value for key, value in sorted(tally.items()) if key.startswith("confusion:")}
    return {
        "group": name, "components": tally["components"],
        "status_correct": tally["status_correct"], "status_accuracy": rate("status_correct", "components"),
        "proposed_links": tally["proposed_links"], "matched_links": tally["matched_links"],
        "unverified_links": tally["unverified_links"],
        "link_precision_proxy": rate("matched_links", "proposed_links"),
        "reference_anchors": tally["reference_anchors"], "matched_anchors": tally["matched_anchors"],
        "anchor_recall": rate("matched_anchors", "reference_anchors"),
        "complete_components": tally["complete_components"],
        "components_with_citations": tally["components_with_citations"],
        "links_where_reference_has_none": tally["links_where_reference_has_none"],
        "reference_not_found": tally["reference_not_found"], "correct_abstentions": tally["correct_abstentions"],
        "deferred_without_links": tally["deferred_without_links"],
        "status_confusion_reference_to_proposed": confusion,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--family", required=True)
    parser.add_argument("--run", type=Path, required=True, help="Run file from the shell pipeline or the bundle command")
    parser.add_argument("--reviews", type=Path, help="Score the assessments that stand after these review decisions")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "data/source-manifest.json").read_text(encoding="utf-8"))
    family = next((item for item in manifest["families"]
                   if item["family_id"] == args.family and item["partition"] == "development"), None)
    if family is None:
        parser.error("Select a development family")
    path = ROOT / "benchmark" / "development" / args.family / "reference-annotations.jsonl"
    try:
        references = {record["component_id"]: record for record in read_jsonl(path)}
        entries = load_run(args.run)
        store = ReviewStore(args.reviews, entries) if args.reviews else None
        shell_types = {shell["document_id"]: shell["type"] for shell in family["shells"]}
        groups = score(entries, references, shell_types, store.current if store else None,
                       store.extra_passages if store else None)
        for name in ("all", *sorted(set(groups) - {"all"})):
            print(json.dumps(report(name, groups[name])))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
