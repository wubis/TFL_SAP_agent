"""Check that the language-model commands work against the live API, on a few development components.

Unit tests use a stand-in client, so they cannot show that real calls and real model responses behave
as intended. This script makes a small number of real calls and checks what came back.

    python3 benchmark/live_check.py --family NCT03469934 --pdf SAP_001.pdf --ocr --limit 3 --max-usd 2

It runs the agent, the general-purpose LLM baseline, and the single-call assessor on the first
components of a development family, then checks: the run files load and validate, every component
has a record, settings were recorded, the requested model served every call, every quotation the
agent or assessor cited is in the passage it cites, token usage was logged, and the prompt log holds
the full prompt. It prints one line per check and exits non-zero if any fails. It needs
ANTHROPIC_API_KEY and spends real money, so set --max-usd.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from traceability.review import load_run, read_jsonl  # noqa: E402


def checks_for_run(name, path, log, limit, model):
    entries = load_run(path)
    part = "agent" if name == "agent" else "baseline"
    logged = list(read_jsonl(log)) if log.exists() else []
    settings = {json.dumps(entry.get("run_settings"), sort_keys=True) for entry in entries}
    served = {served for entry in entries for served in entry[part].get("served_models", [])}
    verified = all(link["quote"] in {p["passage_id"]: p["text"] for p in entry["retrieval"]["candidates"]}.get(link["passage_id"], "")
                   for entry in entries for link in entry["mapping"]["assessment"]["evidence"])
    yield f"{name}: one valid record per component", len(entries) == limit
    yield f"{name}: run settings recorded and identical", len(settings) == 1 and "null" not in settings
    yield f"{name}: requested model served every call ({sorted(served)})", served == {model}
    yield f"{name}: token usage recorded", all(entry[part].get("usage", {}).get("output_tokens") for entry in entries)
    yield f"{name}: prompt log has the full prompt and model for every call", bool(logged) and all(
        record.get("system") and record.get("messages") and record.get("served_model") for record in logged)
    if name == "agent":
        yield "agent: every cited quotation is in the passage it cites", verified
        yield "agent: at least one component reached a verdict without hand-off", any(not entry["agent"]["handed_off"] for entry in entries)
        yield "agent: the model used a lookup tool at least once", any(entry["agent"]["lookups"] for entry in entries)
    else:
        outcomes = [check["outcome"] for entry in entries for check in entry["baseline"]["citations"]]
        yield f"llm_baseline: citations checked ({len(outcomes)} cited, {outcomes.count('verified')} verified)", True
        yield "llm_baseline: no answer was rejected by the record rules", not any(entry["baseline"]["rule_failures"] for entry in entries)
    yield f"{name}: statuses returned {sorted({entry['mapping']['assessment']['status'] for entry in entries})}", True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--family", required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--ocr", action="store_true")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--max-usd", type=float, required=True, help="Spending cap for each of the agent and baseline runs")
    parser.add_argument("--model", default="claude-opus-5-5")
    parser.add_argument("--keep", type=Path, help="Folder to keep the run files and logs in")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "data/source-manifest.json").read_text(encoding="utf-8"))
    if not any(family["family_id"] == args.family and family["partition"] == "development" for family in manifest["families"]):
        parser.error("Select a development family")
    folder = args.keep or Path(tempfile.mkdtemp(prefix="live-check-"))
    folder.mkdir(parents=True, exist_ok=True)
    components = ROOT / "benchmark" / "development" / args.family / "components.jsonl"
    common = ["--family", args.family, "--pdf", str(args.pdf), "--components", str(components), "--limit", str(args.limit),
              "--model", args.model, "--max-usd", str(args.max_usd), *(["--ocr"] if args.ocr else [])]
    results, failed = [], False
    for name, module in (("agent", "traceability.agent"), ("llm_baseline", "traceability.llm_baseline")):
        run, log = folder / f"{name}-run.jsonl", folder / f"{name}-log.jsonl"
        log.unlink(missing_ok=True)
        with run.open("w", encoding="utf-8") as output:
            done = subprocess.run([sys.executable, "-m", module, *common, "--log", str(log)], cwd=ROOT, stdout=output,
                                  stderr=subprocess.PIPE, text=True)
        results.append((f"{name}: command finished (exit {done.returncode})", done.returncode == 0))
        if done.returncode != 0:
            print(done.stderr.strip().splitlines()[-1] if done.stderr.strip() else "no error text", file=sys.stderr)
            continue
        try:
            results.extend(checks_for_run(name, run, log, args.limit, args.model))
        except (OSError, ValueError, KeyError) as exc:
            results.append((f"{name}: output could not be checked ({exc})", False))
    # The single-call assessor, on the first agent entry's component and candidates.
    try:
        from traceability.assessment import INSTRUCTIONS
        entry = load_run(folder / "agent-run.jsonl")[0]
        request = {"instructions": INSTRUCTIONS, "component": {key: entry["component"][key] for key in ("kind", "label", "context")},
                   "sap_version": entry["mapping"]["sap_version"], "constructed_shell": entry["retrieval"]["constructed_shell"],
                   "candidates": [{key: passage[key] for key in ("passage_id", "page", "section", "text", "extraction")}
                                  for passage in entry["retrieval"]["candidates"]], "display_conventions": []}
        done = subprocess.run([sys.executable, "-m", "traceability.claude_assessor", "--model", args.model,
                               "--log", str(folder / "assessor-log.jsonl")], cwd=ROOT, input=json.dumps(request),
                              capture_output=True, text=True)
        answer = json.loads(done.stdout) if done.returncode == 0 else {}
        results.append((f"assessor: returned a {answer.get('status')} assessment (exit {done.returncode})",
                        done.returncode == 0 and "status" in answer))
    except (OSError, ValueError, KeyError, IndexError) as exc:
        results.append((f"assessor: could not run ({exc})", False))
    for label, passed in results:
        failed = failed or not passed
        print(("PASS  " if passed else "FAIL  ") + label)
    print(f"Run files and logs are in {folder}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
