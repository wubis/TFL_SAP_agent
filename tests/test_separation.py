"""Reference annotations and held-out files must stay out of everything the agent can read."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = ("reference-annotations", "held_out", "calibration-review")


def test_agent_package_never_names_benchmark_answer_files():
    offenders = [(path.name, word) for path in sorted((ROOT / "traceability").glob("*"))
                 if path.suffix in (".py", ".html") for word in FORBIDDEN if word in path.read_text(encoding="utf-8")]
    assert offenders == []


def test_only_scoring_scripts_open_reference_annotations():
    readers = sorted(path.name for path in (ROOT / "benchmark").glob("*.py")
                     if "reference-annotations" in path.read_text(encoding="utf-8"))
    assert readers == ["adjudication.py", "challenge_tags.py", "coverage_report.py", "evaluate.py", "score_development_mappings.py",
                       "score_development_retrieval.py", "validate_calibration.py"]
