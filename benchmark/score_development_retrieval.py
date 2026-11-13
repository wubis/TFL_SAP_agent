"""Score development citation and evidence-group coverage from saved retrieval results."""

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_records(path):
    records = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        component_id = record["component_id"]
        if component_id in records:
            raise ValueError(f"Duplicate component ID {component_id} in {path}")
        records[component_id] = record
    return records


def coverage(annotations, results, top_k):
    if annotations.keys() != results.keys():
        raise ValueError("Retrieval results must include exactly the annotated component IDs")
    matched_passages = total_passages = matched_components = total_components = 0
    for component_id, annotation in annotations.items():
        result = results[component_id]
        if any(result[key] != annotation[key] for key in ("sap_id", "sap_version")):
            raise ValueError(f"Mismatched SAP for {component_id}")
        passages = annotation["assessment"]["evidence"]
        if not passages:
            continue
        candidates = result["candidates"][:top_k]
        matched_ids = {
            passage["passage_id"] for passage in passages
            if any(candidate["page"] == passage["page"] and passage["quote"] in candidate["text"]
                   for candidate in candidates)
        }
        matched_passages += len(matched_ids)
        total_passages += len(passages)
        total_components += 1
        matched_components += all(any(set(option) <= matched_ids for option in group["alternatives"])
                                  for group in annotation["evidence_groups"])
    return {
        "k": top_k,
        "matched_citation_anchors": matched_passages,
        "total_citation_anchors": total_passages,
        "complete_components": matched_components,
        "components_with_citations": total_components,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", required=True)
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((ROOT / "data/source-manifest.json").read_text(encoding="utf-8"))
    if not any(family["family_id"] == args.family and family["partition"] == "development"
               for family in manifest["families"]):
        parser.error("Select a development family")
    path = ROOT / "benchmark" / "development" / args.family / "reference-annotations.jsonl"
    try:
        references = read_records(path)
        results = read_records(args.results)
        for top_k in (1, 5, 10):
            print(json.dumps(coverage(references, results, top_k)))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
