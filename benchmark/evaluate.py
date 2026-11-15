"""Evaluation runner: score every system's saved runs for one partition and write a report.

Each --run names a system, a family, and a run file. Each --retrieval names a system, a family, and
a retrieval results file. Results are pooled over the partition's families and reported per system,
overall and by shell type, with per-family rows.

    python3 benchmark/evaluate.py --partition development \
      --retrieval bm25:NCT03469934:runs/bm25-NCT03469934.jsonl \
      --run agent:NCT03469934:runs/agent-NCT03469934.jsonl \
      --run llm-baseline:NCT03469934:runs/baseline-NCT03469934.jsonl \
      --out-json runs/evaluation.json --out-md runs/evaluation.md

The held-out partition is for the final evaluation only, run once by one person. It requires a
frozen configuration written by benchmark/freeze_config.py, no change to code since the freeze, a tag
on the current commit, and a run for every held-out family from each system. It then writes
benchmark/final-evaluation-record.json and refuses to run again while that record exists. Runs must
cover exactly the systems the frozen configuration names, and each run file's recorded settings
(model, effort, limits, retrieval, OCR, code fingerprint) must equal the frozen ones. Every held-out
family's reference annotations must be signed off in the manifest by someone other than the annotator.
"""

import argparse
import datetime
import hashlib
import importlib.util
import json
import subprocess
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
freezing = load("freeze_config")
signing = load("sign_off")
RECORD = "benchmark/final-evaluation-record.json"


def citation_counts(entries, sap=None):
    """Quotations found where they are cited.

    With the SAP at hand, a quotation counts when it occurs in the SAP text of the cited page. Without
    it, the check is against the passage text in the run file. A run file's own claims are never used.
    """
    counts = Counter()
    for entry in entries:
        texts = {passage["passage_id"]: passage["text"] for passage in entry["retrieval"]["candidates"]}
        for link in entry["mapping"]["assessment"]["evidence"]:
            quote = " ".join(link["quote"].split())
            where = sap[1].get(link["page"], "") if sap else texts.get(link["passage_id"], "")
            counts["citations"] += 1
            counts["verified_citations"] += quote in where
    return counts


def recorded_settings(records, path):
    """The settings a run file recorded. Every record in a file must carry the same ones."""
    found = {json.dumps(record.get("run_settings"), sort_keys=True) for record in records}
    if len(found) != 1:
        raise ValueError(f"{path}: records carry different run settings")
    return json.loads(found.pop())


def served_models(records):
    return sorted({model for record in records for part in ("agent", "baseline")
                   for model in record.get(part, {}).get("served_models", [])})


def setting_mismatches(system, settings, frozen):
    """Ways one run's recorded settings differ from the frozen configuration."""
    if settings is None:
        return ["the run file records no settings"]
    expected = frozen["systems"][system]
    found = []
    if settings.get("system") != system:
        found.append(f"the file was produced as {settings.get('system')!r}")
    for key, value in expected.items():
        if key == "command":
            continue
        if key == "top_k":
            if not isinstance(settings.get("top_k"), int) or settings["top_k"] < max(value):
                found.append(f"top_k is {settings.get('top_k')}, frozen needs at least {max(value)}")
        elif settings.get(key) != value:
            found.append(f"{key} is {settings.get(key)!r}, frozen is {value!r}")
    ocr = frozen["sap_text"]["ocr_for_pages_without_text"]
    if settings.get("ocr") != ocr:
        found.append(f"ocr is {settings.get('ocr')!r}, frozen is {ocr!r}")
    # Fingerprints compare the protected files' content. Commit IDs would differ once the frozen file is committed.
    if not settings.get("code_fingerprint") or settings.get("code_fingerprint") != frozen["code_fingerprint"]:
        found.append("the run was produced by code that differs from the frozen code")
    if settings.get("uncommitted_changes") is not False:
        found.append("the run was produced with uncommitted code changes")
    if settings.get("limit") is not None:
        found.append(f"the run was limited to its first {settings['limit']} components")
    return found


def held_out_problems(frozen, runs, retrievals, held, inventory=None):
    """Everything wrong with a held-out submission, found without opening any reference file."""
    problems = []
    given = {}
    for system, family_id, path in runs:
        entries = load_run(path)
        settings = recorded_settings(entries, path)
        other = sorted(set(served_models(entries)) - {(settings or {}).get("model")})
        if other:
            problems.append(f"{system} on {family_id}: calls were served by {', '.join(other)}, not the frozen model")
        given.setdefault(system, []).append((family_id, settings, {entry["component"]["component_id"] for entry in entries}))
    for system, family_id, path in retrievals:
        records = retrieval.read_records(path)
        given.setdefault(system, []).append((family_id, recorded_settings(list(records.values()), path), set(records)))
    roster = sorted(frozen["systems"])
    if sorted(given) != roster:
        problems.append(f"the frozen configuration names systems {roster}, and runs were given for {sorted(given)}")
    for system, files in sorted(given.items()):
        if sorted(family for family, _, _ in files) != held:
            problems.append(f"{system} needs exactly one run for every held-out family")
        for family_id, settings, component_ids in files:
            if system in frozen["systems"]:
                problems += [f"{system} on {family_id}: {issue}" for issue in setting_mismatches(system, settings, frozen)]
            # The component inventory is an input, not an answer. A partial or padded run is caught here.
            expected = (inventory or {}).get(family_id)
            if expected is not None and component_ids != expected:
                problems.append(f"{system} on {family_id}: the run has {len(component_ids)} components and does not "
                                f"cover exactly the {len(expected)} in the inventory")
    return problems


def writable_problems(paths):
    """Output paths that cannot be written, found before the single held-out run is spent."""
    found = []
    for path in paths:
        if path is None:
            continue
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8"):
                pass
        except OSError as exc:
            found.append(f"cannot write {path}: {exc.strerror or exc}")
    return found


def parse_triples(values, label):
    triples = []
    for value in values or []:
        parts = value.split(":", 2)
        if len(parts) != 3 or not all(parts):
            raise ValueError(f"{label} expects SYSTEM:FAMILY_ID:PATH, got {value!r}")
        triples.append((parts[0], parts[1], Path(parts[2])))
    return triples


def evaluate(manifest, partition, runs, retrievals, pdfs=None):
    families = {family["family_id"]: family for family in manifest["families"] if family["partition"] == partition}
    references = {}

    def reference(family_id):
        if family_id not in families:
            raise ValueError(f"{family_id} is not a {partition} family in the frozen manifest")
        if family_id not in references:
            path = ROOT / "benchmark" / partition / family_id / "reference-annotations.jsonl"
            references[family_id] = {record["component_id"]: record for record in read_jsonl(path)}
        return references[family_id]

    results = {"partition": partition, "systems": {}, "retrieval": {}, "run_settings": {}}
    sap_text = {}
    for system, family_id, path in runs:
        entries = load_run(path)
        results["run_settings"].setdefault(system, {})[family_id] = {
            "settings": recorded_settings(entries, path), "served_models": served_models(entries)}
        shell_types = {shell["document_id"]: shell["type"] for shell in families.get(family_id, {}).get("shells", [])}
        if family_id not in families:
            raise ValueError(f"{family_id} is not a {partition} family in the frozen manifest")
        if family_id in (pdfs or {}) and family_id not in sap_text:
            sap_text[family_id] = mappings.sap_sources(families[family_id], pdfs[family_id])
        sap = sap_text.get(family_id)
        groups = mappings.score(entries, reference(family_id), shell_types, sap=sap)
        record = results["systems"].setdefault(system, {"families": {}, "pooled": {}, "citations": Counter(),
                                                         "checked_against": set()})
        if family_id in record["families"]:
            raise ValueError(f"Two runs were given for {system} on {family_id}")
        record["families"][family_id] = mappings.report(family_id, groups["all"])
        for name, tally in groups.items():
            record["pooled"].setdefault(name, Counter()).update(tally)
        record["citations"].update(citation_counts(entries, sap))
        record["checked_against"].add("the SAP PDF" if sap else "passage text in the run file")
    for record in results["systems"].values():
        record["pooled"] = {name: mappings.report(name, tally) for name, tally in sorted(record["pooled"].items())}
        counts = record.pop("citations")
        record["citation_accuracy"] = {
            "checked_against": sorted(record.pop("checked_against")),
            "citations": counts["citations"], "verified": counts["verified_citations"],
            "rate": round(counts["verified_citations"] / counts["citations"], 3) if counts["citations"] else None}
    for system, family_id, path in retrievals:
        saved = retrieval.read_records(path)
        results["run_settings"].setdefault(system, {})[family_id] = {
            "settings": recorded_settings(list(saved.values()), path), "served_models": []}
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
        for system, record in results["systems"].items():
            lines.append(f"\nQuotations for {system} were checked against {' and '.join(record['citation_accuracy']['checked_against'])}.")
        lines += ["", "### Status confusion, reference to proposed", ""]
        for system, record in results["systems"].items():
            confusion = record["pooled"]["all"]["status_confusion_reference_to_proposed"]
            lines.append(f"- {system}: " + ", ".join(f"{pair} {count}" for pair, count in confusion.items()))
        lines.append("")
    lines += ["## Run settings", ""]
    for system, families in results["run_settings"].items():
        distinct = {json.dumps(record["settings"], sort_keys=True) for record in families.values()}
        for text in sorted(distinct):
            settings = json.loads(text)
            if settings is None:
                lines.append(f"- {system}: no settings were recorded with the run.")
            else:
                lines.append(f"- {system}: " + ", ".join(f"{key} {value}" for key, value in settings.items() if key != "system"))
        requested = {(record["settings"] or {}).get("model") for record in families.values()}
        other = sorted({model for record in families.values() for model in record["served_models"]} - requested)
        if other:
            lines.append(f"- {system}: some calls were served by {', '.join(other)}, not the requested model. "
                         "Results for this system mix models.")
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
    parser.add_argument("--pdf", action="append", help="FAMILY_ID:PATH to the original SAP PDF. Quotations and passage text "
                                                       "are then checked against the SAP. Required for held_out.")
    parser.add_argument("--frozen-config", type=Path, help="Settings frozen after development. Required for held_out.")
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-md", type=Path)
    args = parser.parse_args()
    held_out = args.partition == "held_out"
    record_path = ROOT / RECORD
    try:
        runs, retrievals = parse_triples(args.run, "--run"), parse_triples(args.retrieval, "--retrieval")
        if not runs and not retrievals:
            raise ValueError("Give at least one --run or --retrieval")
        pdfs = {}
        for value in args.pdf or []:
            family_id, _, path = value.partition(":")
            if not family_id or not path:
                raise ValueError(f"--pdf expects FAMILY_ID:PATH, got {value!r}")
            pdfs[family_id] = Path(path)
        manifest = json.loads((ROOT / "data/source-manifest.json").read_text(encoding="utf-8"))
        if manifest["partition_status"] != "frozen":
            raise ValueError("The partition manifest is not frozen")
        frozen = None
        if args.frozen_config:
            frozen = {"path": str(args.frozen_config), "sha256": hashlib.sha256(args.frozen_config.read_bytes()).hexdigest()}
        if held_out:
            # Every gate is checked before any held-out reference is opened.
            if frozen is None:
                raise ValueError("The held-out evaluation requires --frozen-config")
            if record_path.exists():
                status = json.loads(record_path.read_text(encoding="utf-8")).get("status", "completed")
                raise ValueError(f"The held-out evaluation has already been run (status: {status}). See {RECORD}. "
                                 "It runs once. A rerun is a team decision.")
            config = json.loads(args.frozen_config.read_text(encoding="utf-8"))
            held = sorted(family["family_id"] for family in manifest["families"] if family["partition"] == "held_out")
            inventory = {}
            for family_id in held:
                path = ROOT / "benchmark" / "held_out" / family_id / "components.jsonl"
                inventory[family_id] = {record["component_id"] for record in read_jsonl(path)}
            problems = [*freezing.frozen_file_problems(ROOT, args.frozen_config), *freezing.freeze_problems(ROOT, config)]
            if not problems:
                problems = [*signing.sign_off_problems(manifest, "held_out"),
                            *held_out_problems(config, runs, retrievals, held, inventory),
                            *[f"{family_id}: give the original SAP PDF with --pdf so quotations are checked against the source"
                              for family_id in held if family_id not in pdfs and runs],
                            *writable_problems([args.out_json, args.out_md])]
            if problems:
                raise ValueError("The held-out evaluation cannot run:\n- " + "\n- ".join(problems))
            # From here references are opened, so the single run is spent whatever happens next.
            record = {"status": "started", "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                      "frozen_config": frozen, "code_commit": freezing.git(ROOT, "rev-parse", "HEAD"),
                      "systems": sorted({name for name, _, _ in [*runs, *retrievals]})}
            record_path.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
            try:
                results = evaluate(manifest, args.partition, runs, retrievals, pdfs)
            except Exception as exc:
                record.update(status="failed after references were opened", error_type=type(exc).__name__)
                record_path.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
                # The message is withheld: it can name held-out components.
                parser.exit(1, f"The held-out evaluation failed after references were opened ({type(exc).__name__}). "
                               f"{RECORD} marks the run as spent. A rerun is a team decision.\n")
            results["frozen_config"] = frozen
            report = markdown(results, frozen)
            # The record holds the full results, so nothing is lost if an output file cannot be written.
            record.update(status="completed", systems=results["families_scored"], results=results)
            record_path.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
        else:
            results = evaluate(manifest, args.partition, runs, retrievals, pdfs)
            results["frozen_config"] = frozen
            report = markdown(results, frozen)
        print(report, end="")
        for path, text in ((args.out_json, json.dumps(results, indent=1) + "\n"), (args.out_md, report)):
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
