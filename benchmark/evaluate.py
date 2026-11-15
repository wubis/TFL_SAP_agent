"""Evaluation runner: score every system's saved runs for one partition and write a report.

Each --run names a system, a family, and a run file. Each --retrieval names a system, a family, and
a retrieval results file. Results are pooled over the partition's families and reported per system,
overall and by shell type, with per-family rows.

    python3 benchmark/evaluate.py --partition development \
      --retrieval bm25:NCT03469934:runs/bm25-NCT03469934.jsonl \
      --run agent:NCT03469934:runs/agent-NCT03469934.jsonl \
      --run llm-baseline:NCT03469934:runs/baseline-NCT03469934.jsonl \
      --out-json runs/evaluation.json --out-md runs/evaluation.md

The held-out partition is for the final evaluation only. It requires --frozen-config, a file that
records the settings fixed after development, and a run for every held-out family from each system.
"""

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from traceability.review import load_run, read_jsonl  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "benchmark" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mappings, retrieval = load("score_development_mappings"), load("score_development_retrieval")


def citation_counts(entries):
    """Quotations found in the passage they cite. The baseline records its own page-level check."""
    counts = Counter()
    for entry in entries:
        if "baseline" in entry:
            for check in entry["baseline"]["citations"]:
                counts["citations"] += 1
                counts["verified_citations"] += check["outcome"] == "verified"
            continue
        texts = {passage["passage_id"]: passage["text"] for passage in entry["retrieval"]["candidates"]}
        for link in entry["mapping"]["assessment"]["evidence"]:
            counts["citations"] += 1
            counts["verified_citations"] += link["quote"] in texts.get(link["passage_id"], "")
    return counts


def parse_triples(values, label):
    triples = []
    for value in values or []:
        parts = value.split(":", 2)
        if len(parts) != 3 or not all(parts):
            raise ValueError(f"{label} expects SYSTEM:FAMILY_ID:PATH, got {value!r}")
        triples.append((parts[0], parts[1], Path(parts[2])))
    return triples


def evaluate(manifest, partition, runs, retrievals):
    families = {family["family_id"]: family for family in manifest["families"] if family["partition"] == partition}
    references = {}

    def reference(family_id):
        if family_id not in families:
            raise ValueError(f"{family_id} is not a {partition} family in the frozen manifest")
        if family_id not in references:
            path = ROOT / "benchmark" / partition / family_id / "reference-annotations.jsonl"
            references[family_id] = {record["component_id"]: record for record in read_jsonl(path)}
        return references[family_id]

    results = {"partition": partition, "systems": {}, "retrieval": {}}
    for system, family_id, path in runs:
        entries = load_run(path)
        shell_types = {shell["document_id"]: shell["type"] for shell in families.get(family_id, {}).get("shells", [])}
        groups = mappings.score(entries, reference(family_id), shell_types)
        record = results["systems"].setdefault(system, {"families": {}, "pooled": {}, "citations": Counter()})
        if family_id in record["families"]:
            raise ValueError(f"Two runs were given for {system} on {family_id}")
        record["families"][family_id] = mappings.report(family_id, groups["all"])
        for name, tally in groups.items():
            record["pooled"].setdefault(name, Counter()).update(tally)
        record["citations"].update(citation_counts(entries))
    for record in results["systems"].values():
        record["pooled"] = {name: mappings.report(name, tally) for name, tally in sorted(record["pooled"].items())}
        counts = record.pop("citations")
        record["citation_accuracy"] = {
            "citations": counts["citations"], "verified": counts["verified_citations"],
            "rate": round(counts["verified_citations"] / counts["citations"], 3) if counts["citations"] else None}
    for system, family_id, path in retrievals:
        saved = retrieval.read_records(path)
        record = results["retrieval"].setdefault(system, {"families": {}, "pooled": {}})
        for top_k in (1, 5, 10):
            row = retrieval.coverage(reference(family_id), saved, top_k)
            record["families"].setdefault(family_id, []).append(row)
            pooled = record["pooled"].setdefault(str(top_k), Counter())
            pooled.update({key: value for key, value in row.items() if key != "k"})
    for record in results["retrieval"].values():
        record["pooled"] = {top_k: dict(tally) for top_k, tally in record["pooled"].items()}
    results["families_scored"] = {
        system: sorted(record["families"]) for system, record in {**results["systems"], **results["retrieval"]}.items()}
    results["partition_families"] = sorted(families)
    return results


def fraction(top, bottom):
    return f"{top}/{bottom}" + (f" ({top / bottom:.0%})" if bottom else "")


def markdown(results, frozen=None):
    lines = [f"# Evaluation results: {results['partition']} partition", ""]
    lines.append("Generated by `benchmark/evaluate.py` from saved run files. Every number below was computed by that script.")
    if frozen:
        lines.append(f"Frozen configuration: `{frozen['path']}` (SHA-256 `{frozen['sha256']}`).")
    lines += ["", f"Families in this partition: {', '.join(results['partition_families'])}.", ""]
    if results["retrieval"]:
        lines += ["## Retrieval on reference components", "",
                  "| System | k | Citation anchors found | Components with every evidence group covered | Families |",
                  "| --- | ---: | --- | --- | --- |"]
        for system, record in results["retrieval"].items():
            for top_k, tally in record["pooled"].items():
                lines.append(f"| {system} | {top_k} | {fraction(tally['matched_citation_anchors'], tally['total_citation_anchors'])} | "
                             f"{fraction(tally['complete_components'], tally['components_with_citations'])} | {len(record['families'])} |")
        lines.append("")
    if results["systems"]:
        lines += ["## Mappings", "",
                  "Link precision is a passage-level proxy. Unmatched links need a human equivalent-span check before "
                  "they are called unsupported.", "",
                  "| System | Group | Components | Status correct | Links matched | Anchors found | Complete evidence | "
                  "Links where the reference has none | Correct abstentions | Quotations verified |",
                  "| --- | --- | ---: | --- | --- | --- | --- | ---: | --- | --- |"]
        for system, record in results["systems"].items():
            cited = record["citation_accuracy"]
            for name, row in record["pooled"].items():
                lines.append(
                    f"| {system} | {name} | {row['components']} | {fraction(row['status_correct'], row['components'])} | "
                    f"{fraction(row['matched_links'], row['proposed_links'])} | "
                    f"{fraction(row['matched_anchors'], row['reference_anchors'])} | "
                    f"{fraction(row['complete_components'], row['components_with_citations'])} | "
                    f"{row['links_where_reference_has_none']} | "
                    f"{fraction(row['correct_abstentions'], row['reference_not_found'])} | "
                    f"{fraction(cited['verified'], cited['citations']) if name == 'all' else ''} |")
        lines += ["", "### Status confusion, reference to proposed", ""]
        for system, record in results["systems"].items():
            confusion = record["pooled"]["all"]["status_confusion_reference_to_proposed"]
            lines.append(f"- {system}: " + ", ".join(f"{pair} {count}" for pair, count in confusion.items()))
        lines.append("")
    for system, families in results["families_scored"].items():
        missing = sorted(set(results["partition_families"]) - set(families))
        if missing:
            lines.append(f"{system} has no run for: {', '.join(missing)}.")
    return "\n".join(lines).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--partition", choices=("development", "held_out"), required=True)
    parser.add_argument("--run", action="append", help="SYSTEM:FAMILY_ID:PATH to a run file. Repeat as needed.")
    parser.add_argument("--retrieval", action="append", help="SYSTEM:FAMILY_ID:PATH to retrieval results. Repeat as needed.")
    parser.add_argument("--frozen-config", type=Path, help="Settings frozen after development. Required for held_out.")
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-md", type=Path)
    args = parser.parse_args()
    try:
        runs, retrievals = parse_triples(args.run, "--run"), parse_triples(args.retrieval, "--retrieval")
        if not runs and not retrievals:
            raise ValueError("Give at least one --run or --retrieval")
        manifest = json.loads((ROOT / "data/source-manifest.json").read_text(encoding="utf-8"))
        if manifest["partition_status"] != "frozen":
            raise ValueError("The partition manifest is not frozen")
        frozen = None
        if args.frozen_config:
            frozen = {"path": str(args.frozen_config), "sha256": hashlib.sha256(args.frozen_config.read_bytes()).hexdigest()}
        results = evaluate(manifest, args.partition, runs, retrievals)
        if args.partition == "held_out":
            if frozen is None:
                raise ValueError("The held-out evaluation requires --frozen-config")
            incomplete = {system: families for system, families in results["families_scored"].items()
                          if families != results["partition_families"]}
            if incomplete:
                raise ValueError(f"Every system needs a run for every held-out family: {sorted(incomplete)}")
        results["frozen_config"] = frozen
        report = markdown(results, frozen)
        for path, text in ((args.out_json, json.dumps(results, indent=1) + "\n"), (args.out_md, report)):
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
        print(report, end="")
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
