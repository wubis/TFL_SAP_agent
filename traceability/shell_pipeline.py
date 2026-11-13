"""Parse the registered FEV1 Markdown shell and run retrieval and mapping."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from traceability.mapping import build_mappings, read_jsonl
from traceability.retrieval import ROOT, retrieve_components, select_family


SHELL_ID = "NCT03469934-CHALLENGE-FEV1"


def cells(line):
    if not line.startswith("|") or not line.endswith("|"):
        raise ValueError("Expected a Markdown table row")
    fields = [cell.strip() for cell in line[1:-1].split("|")]
    if len(fields) != 3 or not all(fields):
        raise ValueError("Expected one statistic and two treatment columns")
    return fields


def parse_shell(family, shell, path):
    if shell["document_id"] != SHELL_ID or shell["version"] != "1.0":
        raise ValueError("This parser supports the registered FEV1 Markdown shell v1.0")
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != shell["source_sha256"]:
        raise ValueError("Shell checksum does not match the registered version")
    lines = [(number, text.strip()) for number, text in enumerate(source.decode("utf-8").splitlines(), 1) if text.strip()]
    start = next((index for index, (_, text) in enumerate(lines) if text.startswith("## ")), None)
    if start is None or len(lines[start:]) != 7:
        raise ValueError("Expected a summary heading, two-row table, and two notes")

    (title_line, heading), (header_line, header), (_, separator), *body = lines[start:]
    title = heading.removeprefix("## ")
    statistic, *arm_labels = cells(header)
    if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells(separator)):
        raise ValueError("Expected a Markdown table separator")
    context = {
        "population": "Full Analysis Set" if "full analysis population" in title.casefold() else None,
        "endpoint": "Spirometry (FEV1)" if "FEV1" in title else None,
        "visit": "Assessed visits" if "study visits" in title.casefold() else None,
        "treatment_groups": family["arms"],
        "surrounding_labels": [statistic, "FEV1", *arm_labels],
    }

    # These layout slots retain the IDs assigned to this version during annotation.
    # Both possible trial arms remain context for dummy headers until SAP evidence resolves them.
    entries = [("title", "title", title, f"line {title_line}"),
               ("anb020", "table_column", arm_labels[0], f"line {header_line}, column 2"),
               ("placebo", "table_column", arm_labels[1], f"line {header_line}, column 3")]
    for (number, line), key in zip(body[:2], ("mean-change", "standard-deviation"), strict=True):
        entries.append((key, "table_row", cells(line)[0], f"line {number}, row label"))
    for (number, line), key in zip(body[2:], ("not-applicable-style", "invented-minimum"), strict=True):
        entries.append((key, "footnote", line, f"line {number}"))
    return [
        {"record_type": "component", "component_id": f"{shell['document_id']}:{key}",
         "family_id": family["family_id"], "shell_id": shell["document_id"], "shell_version": shell["version"],
         "locator": f"{path.name}, {locator}", "kind": kind, "label": label, "context": context}
        for key, kind, label, locator in entries
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path, help="Original paired SAP bundle")
    parser.add_argument("--shell", type=Path, help="Original registered Markdown shell, defaults to the repository copy")
    parser.add_argument("--assessments", type=Path, help="Optional reviewer judgments indexed by component ID")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--ocr", action="store_true")
    args = parser.parse_args()
    try:
        manifest = json.loads((ROOT / "data/source-manifest.json").read_text(encoding="utf-8"))
        family = select_family(manifest, "NCT03469934")
        shell = next(item for item in family["shells"] if item["document_id"] == SHELL_ID)
        components = parse_shell(family, shell, args.shell or ROOT / shell["local_path"])
        retrieved = retrieve_components(family, args.pdf, components, args.top_k, ocr=args.ocr)
        results = {item["component_id"]: item for item in retrieved}
        decisions = read_jsonl(args.assessments) if args.assessments else {}
        schema = json.loads((ROOT / "schemas/traceability.schema.json").read_text(encoding="utf-8"))
        rules = json.loads((ROOT / "benchmark/display-conventions.json").read_text(encoding="utf-8"))
        mappings = build_mappings(results, decisions, {rule["convention_id"] for rule in rules["conventions"]}, schema)
        for component, mapping in zip(components, mappings, strict=True):
            print(json.dumps({"component": component, "retrieval": results[component["component_id"]],
                              "mapping": mapping}, ensure_ascii=False))
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
