"""Record a teammate's sign-off of one family's reference annotations in the source manifest.

A second teammate, who did not write the annotations, signs off each family. A third person or the
group settles disagreements. Names and dates go in the manifest. Sign off before the freeze: the
manifest is one of the frozen files.

    python3 benchmark/sign_off.py --family NCT03469934 --reviewer "Name" --date 2026-11-20
    python3 benchmark/sign_off.py --family NCT03469934 --reviewer "Name" --date 2026-11-20 --settled-by "Other name"
    python3 benchmark/sign_off.py --status
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "data/source-manifest.json"


def sign_off_problems(manifest, partition=None):
    """Families whose annotations lack a valid sign-off."""
    found = []
    for family in manifest["families"]:
        if partition and family["partition"] != partition:
            continue
        review = family.get("annotation_review") or {}
        name = review.get("signed_off_by")
        if not name or not review.get("signed_off_on"):
            found.append(f"{family['family_id']}: the reference annotations have no recorded sign-off")
        elif name.strip().casefold() == (review.get("annotated_by") or "").strip().casefold():
            found.append(f"{family['family_id']}: the annotator cannot sign off their own annotations")
    return found


def sign_off(root, family_id, reviewer, date, settled_by=None):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ValueError("Give the date as YYYY-MM-DD")
    if not reviewer.strip():
        raise ValueError("Give the reviewer's name")
    path = root / MANIFEST
    text = path.read_text(encoding="utf-8")
    manifest = json.loads(text)
    family = next((item for item in manifest["families"] if item["family_id"] == family_id), None)
    if family is None:
        raise ValueError(f"{family_id} is not in the manifest")
    review = family.setdefault("annotation_review", {"annotated_by": None})
    if reviewer.strip().casefold() == (review.get("annotated_by") or "").strip().casefold():
        raise ValueError("The annotator cannot sign off their own annotations")
    if settled_by and settled_by.strip().casefold() == reviewer.strip().casefold():
        raise ValueError("Disagreements are settled by a third person or the group, not the reviewer")
    review.update(signed_off_by=reviewer.strip(), signed_off_on=date,
                  disagreements_settled_by=settled_by.strip() if settled_by else None)
    indent = len(re.search(r'\n( +)"', text).group(1))
    path.write_text(json.dumps(manifest, indent=indent, ensure_ascii=False) + "\n", encoding="utf-8")
    return review


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--family")
    parser.add_argument("--reviewer")
    parser.add_argument("--date")
    parser.add_argument("--settled-by", help="Who settled disagreements, if any")
    parser.add_argument("--status", action="store_true", help="List families that still need sign-off")
    args = parser.parse_args()
    try:
        if args.status:
            problems = sign_off_problems(json.loads((ROOT / MANIFEST).read_text(encoding="utf-8")))
            print("\n".join(problems) if problems else "Every family's annotations are signed off.")
            sys.exit(1 if problems else 0)
        if not (args.family and args.reviewer and args.date):
            parser.error("Give --family, --reviewer, and --date, or use --status")
        print(json.dumps(sign_off(ROOT, args.family, args.reviewer, args.date, args.settled_by), indent=1))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
