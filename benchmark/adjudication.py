"""Blind adjudication of proposed links that did not match a reference anchor.

A link the scorer leaves unmatched may still be an equivalent valid span. Before it is counted as
unsupported, a person who built none of the systems rules on it without knowing which system
proposed it. A second person rules on anything the first marks unsure. Every ruling carries a reason.

    python3 benchmark/adjudication.py export --partition development \
      --run agent:NCT03469934:runs/agent-run.jsonl --run llm-baseline:NCT03469934:runs/baseline-run.jsonl \
      --items runs/adjudication-items.csv --key runs/adjudication-key.json

Give the adjudicator the items file only. They fill decision (equivalent or unsupported, or unsure),
reason, and adjudicator. For unsure rows a second person fills second_decision, second_reason, and
second_adjudicator. Then:

    python3 benchmark/adjudication.py apply --items runs/adjudication-items.csv --key runs/adjudication-key.json
"""

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from traceability.review import load_run, read_jsonl  # noqa: E402

COLUMNS = ("item_id", "family_id", "component_kind", "component_label", "population", "endpoint", "visit",
           "treatment_groups", "proposed_section", "proposed_page", "proposed_quote", "passage_text",
           "reference_status", "reference_rationale", "reference_quotes",
           "decision", "reason", "adjudicator", "second_decision", "second_reason", "second_adjudicator")
RULINGS = ("equivalent", "unsupported")


def scorer():
    spec = importlib.util.spec_from_file_location("score_development_mappings", ROOT / "benchmark/score_development_mappings.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unmatched_items(runs, references_for):
    """Collect unmatched links from every run, merged across systems so the adjudicator sees each once."""
    matching = scorer()
    items, key = {}, {}
    for system, family_id, path in runs:
        references = references_for(family_id)
        for entry in load_run(path):
            component, assessment = entry["component"], entry["mapping"]["assessment"]
            reference = references[component["component_id"]]
            candidates = {passage["passage_id"]: passage["text"] for passage in entry["retrieval"]["candidates"]}
            for link in assessment["evidence"]:
                _, hits, unverified = matching.matched_reference_ids({"evidence": [link]}, reference, candidates)
                if hits or unverified:
                    # A quotation that fails verification is already unsupported. Only verified links are adjudicated.
                    continue
                identity = "|".join((family_id, component["component_id"], str(link["page"]), link["quote"]))
                item_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
                context = component["context"]
                items[item_id] = {
                    "item_id": item_id, "family_id": family_id, "component_kind": component["kind"],
                    "component_label": component["label"], "population": context["population"] or "",
                    "endpoint": context["endpoint"] or "", "visit": context["visit"] or "",
                    "treatment_groups": "; ".join(context["treatment_groups"]),
                    "proposed_section": link["section"], "proposed_page": link["page"], "proposed_quote": link["quote"],
                    "passage_text": candidates.get(link["passage_id"], ""),
                    "reference_status": reference["assessment"]["status"],
                    "reference_rationale": reference["assessment"]["rationale"],
                    "reference_quotes": " | ".join(f"p{passage['page']} §{passage['section']}: {passage['quote']}"
                                                   for passage in reference["assessment"]["evidence"]),
                    **dict.fromkeys(COLUMNS[-6:], ""),
                }
                key.setdefault(item_id, []).append({"system": system, "mapping_id": entry["mapping"]["mapping_id"]})
    # Hash order carries no information about the system or the component.
    return [items[item_id] for item_id in sorted(items)], key


def final_ruling(row):
    """Return the ruling that stands for one row, or raise if the row breaks the procedure."""
    first, second = row["decision"].strip().lower(), row["second_decision"].strip().lower()
    if not first:
        return None
    if first not in (*RULINGS, "unsure"):
        raise ValueError(f"{row['item_id']}: decision must be equivalent, unsupported, or unsure")
    if not row["reason"].strip() or not row["adjudicator"].strip():
        raise ValueError(f"{row['item_id']}: every decision needs a reason and the adjudicator's name")
    if first != "unsure":
        return first
    if not second:
        return None
    if second not in RULINGS or not row["second_reason"].strip() or not row["second_adjudicator"].strip():
        raise ValueError(f"{row['item_id']}: a second ruling is equivalent or unsupported, with a reason and a name")
    if row["second_adjudicator"].strip() == row["adjudicator"].strip():
        raise ValueError(f"{row['item_id']}: the second ruling must come from a different person")
    return second


def apply(rows, key):
    if {row["item_id"] for row in rows} != key.keys():
        raise ValueError("The items file and the key do not describe the same items")
    systems = {}
    for row in rows:
        ruling = final_ruling(row) or "undecided"
        for owner in key[row["item_id"]]:
            systems.setdefault(owner["system"], Counter())[ruling] += 1
    return {system: {"unmatched_links": sum(tally.values()), "ruled_equivalent": tally["equivalent"],
                     "ruled_unsupported": tally["unsupported"], "undecided": tally["undecided"]}
            for system, tally in sorted(systems.items())}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("--partition", choices=("development", "held_out"), required=True)
    export.add_argument("--run", action="append", required=True, help="SYSTEM:FAMILY_ID:PATH. Repeat as needed.")
    for command in (export, commands.add_parser("apply")):
        command.add_argument("--items", type=Path, required=True)
        command.add_argument("--key", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "apply":
            with args.items.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            print(json.dumps(apply(rows, json.loads(args.key.read_text(encoding="utf-8"))), indent=1))
            return
        if args.items.exists() or args.key.exists():
            raise ValueError("The items or key file already exists. Choose new paths so rulings are not overwritten")
        if args.partition == "held_out":
            # Held-out reference quotations leave the repository here, so this waits for the one final evaluation.
            record = ROOT / "benchmark/final-evaluation-record.json"
            if not record.exists() or json.loads(record.read_text(encoding="utf-8")).get("status") != "completed":
                raise ValueError("Held-out links are adjudicated only after the frozen held-out evaluation has completed")
        manifest = json.loads((ROOT / "data/source-manifest.json").read_text(encoding="utf-8"))
        allowed = {family["family_id"] for family in manifest["families"] if family["partition"] == args.partition}
        runs = []
        for value in args.run:
            system, family_id, path = value.split(":", 2)
            if family_id not in allowed:
                raise ValueError(f"{family_id} is not a {args.partition} family")
            runs.append((system, family_id, Path(path)))

        def references_for(family_id):
            path = ROOT / "benchmark" / args.partition / family_id / "reference-annotations.jsonl"
            return {record["component_id"]: record for record in read_jsonl(path)}

        items, key = unmatched_items(runs, references_for)
        with args.items.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(items)
        args.key.write_text(json.dumps(key, indent=1) + "\n", encoding="utf-8")
        print(f"Wrote {len(items)} unmatched links to {args.items}. Keep {args.key} away from the adjudicator.")
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
