"""Assessor command that asks Claude whether retrieved SAP passages support one shell component.

Reads the pipeline's JSON request from standard input and writes one assessment object to standard
output, so it plugs into ``python3 -m traceability.shell_pipeline ... --assessor``:

    python3 -m traceability.shell_pipeline --pdf SAP_001.pdf --ocr \
      --assessor-timeout 300 --assessor python3 -m traceability.claude_assessor --log runs/assessor-log.jsonl

Credentials come from the environment (ANTHROPIC_API_KEY or an ``ant auth login`` profile). The
command sees the component, the candidate passages, and any display conventions the pipeline sends.
It never reads reference annotations. Quotations are checked against the candidate text before the
answer is returned; after a bounded number of attempts the component is handed to a reviewer.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import anthropic


DEFAULT_MODEL = "claude-opus-5-5"
STATUSES = ["supported", "partially_supported", "not_found_in_supplied_sap", "needs_review"]
ASSESSMENT_FORMAT = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "rationale", "evidence", "open_questions", "convention_ids"],
        "properties": {
            "status": {"type": "string", "enum": STATUSES},
            "rationale": {"type": "string"},
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["passage_id", "quote"],
                    "properties": {"passage_id": {"type": "string"}, "quote": {"type": "string"}},
                },
            },
            "open_questions": {"type": "array", "items": {"type": "string"}},
            "convention_ids": {"type": "array", "items": {"type": "string"}},
        },
    },
}
QUOTING_RULES = """
Quotations are verified by exact string match. Copy each quote character for character from the
`text` of the passage whose `passage_id` you cite, as one continuous stretch, with no ellipsis and
no words from another passage. Quote the smallest span that carries the claim and keep any qualifier
it depends on. Passages marked `ocr` come from scanned pages and may contain recognition errors;
quote them as given and say so in the rationale when a misread character affects the meaning.
"""


def problems(decision, request):
    """Return the reasons a decision would fail the pipeline's own checks, in plain words."""
    candidates = {passage["passage_id"]: passage["text"] for passage in request["candidates"]}
    conventions = {rule["convention_id"] for rule in request.get("display_conventions", [])}
    found = []
    status, evidence = decision["status"], decision["evidence"]
    if not decision["rationale"].strip():
        found.append("The rationale is empty.")
    for item in evidence:
        text = candidates.get(item["passage_id"])
        if text is None:
            found.append(f"passage_id {item['passage_id']!r} is not one of the supplied candidates.")
        elif not item["quote"].strip() or " ".join(item["quote"].split()) not in text:
            found.append(f"The quote {item['quote']!r} is not an exact continuous substring of passage {item['passage_id']}.")
    if len({(item["passage_id"], " ".join(item["quote"].split())) for item in evidence}) != len(evidence):
        found.append("The same quotation is listed twice.")
    if status in ("supported", "partially_supported") and not evidence:
        found.append(f"{status} needs at least one quotation.")
    if status == "not_found_in_supplied_sap" and evidence:
        found.append("not_found_in_supplied_sap must have empty evidence.")
    if status in ("partially_supported", "needs_review") and not [q for q in decision["open_questions"] if q.strip()]:
        found.append(f"{status} needs at least one open question.")
    for convention_id in decision["convention_ids"]:
        if convention_id not in conventions:
            found.append(f"convention_id {convention_id!r} was not supplied for this component.")
    if decision["convention_ids"] and status != "not_found_in_supplied_sap":
        found.append("A display convention is recorded with not_found_in_supplied_sap and no SAP evidence.")
    return found


def handoff(reasons):
    """The record written when the attempts run out. The status carries the verdict."""
    return {
        "status": "needs_review",
        "rationale": "The automated assessor did not return a verifiable assessment within its attempt limit.",
        "evidence": [], "convention_ids": [],
        "open_questions": ["Which candidate passages, if any, support this component in its analysis context?",
                           *[f"Assessor check failed: {reason}" for reason in reasons[:3]]],
    }


def clean(decision):
    decision["open_questions"] = list(dict.fromkeys(q.strip() for q in decision["open_questions"] if q.strip()))
    decision["convention_ids"] = list(dict.fromkeys(decision["convention_ids"]))
    return decision


def assess(request, client, model, effort, attempts, log=None):
    system = request["instructions"].strip() + "\n" + QUOTING_RULES
    payload = {key: value for key, value in request.items() if key != "instructions"}
    messages = [{"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=1)}]
    reasons = []
    for attempt in range(1, attempts + 1):
        # Fallbacks let a safety-classifier decline be rerun on another model inside the same call.
        response = client.beta.messages.create(
            model=model, max_tokens=16000, system=system, messages=messages,
            output_config={"effort": effort, "format": ASSESSMENT_FORMAT},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
        text = next((block.text for block in response.content if block.type == "text"), None)
        record = {"at": round(time.time(), 3), "attempt": attempt, "requested_model": model,
                  "served_model": response.model, "effort": effort, "system": system, "messages": messages,
                  "stop_reason": response.stop_reason, "output": text, "usage": response.usage.model_dump()}
        decision = None
        if response.stop_reason == "refusal":
            reasons = ["The model declined the request."]
        elif response.stop_reason == "max_tokens" or text is None:
            reasons = ["The response was cut off before a complete answer."]
        else:
            decision = json.loads(text)
            reasons = problems(decision, request)
        record["check_failures"] = reasons
        if log is not None:
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        if decision is not None and not reasons:
            return clean(decision)
        if decision is None:
            break
        # Keep the full assistant turn, thinking blocks included, and name what failed.
        messages = [*messages, {"role": "assistant", "content": response.content},
                    {"role": "user", "content": "Your answer failed these checks:\n- " + "\n- ".join(reasons)
                     + "\nReturn a corrected assessment. If the passages cannot support a compliant answer, use needs_review."}]
    return handoff(reasons)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=os.environ.get("TRACEABILITY_MODEL", DEFAULT_MODEL))
    parser.add_argument("--effort", default="medium", choices=("low", "medium", "high", "xhigh", "max"))
    parser.add_argument("--attempts", type=int, default=2, help="Maximum model calls per component, including retries")
    parser.add_argument("--log", type=Path, help="Append the model, full prompt, output, and usage of every call to this JSONL file")
    args = parser.parse_args()
    if args.attempts < 1:
        parser.error("--attempts must be at least 1")
    try:
        request = json.load(sys.stdin)
        decision = assess(request, anthropic.Anthropic(), args.model, args.effort, args.attempts, args.log)
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        if "authentication method" in str(exc):
            parser.exit(1, "Anthropic credentials are missing. Set ANTHROPIC_API_KEY.\n")
        parser.exit(1, f"Invalid assessment request or response: {exc}\n")
    except anthropic.AuthenticationError:
        parser.exit(1, "Anthropic credentials are missing or invalid. Set ANTHROPIC_API_KEY.\n")
    except anthropic.RateLimitError:
        parser.exit(1, "Rate limited by the Anthropic API after retries.\n")
    except anthropic.APIStatusError as exc:
        parser.exit(1, f"Anthropic API error {exc.status_code}: {exc.message}\n")
    except anthropic.APIConnectionError:
        parser.exit(1, "Could not reach the Anthropic API.\n")
    json.dump(decision, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
