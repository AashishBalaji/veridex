"""
A real end-to-end run of the pipeline against a small synthetic
dataset -- generates records, runs blocking + FAISS + the classifier
+ explanation, and checks the artifacts it writes are internally
consistent. This is slower than the unit tests (it starts a real
local Spark session) so it's kept in its own file.

Uses pytest's own `tmp_path` (function-scoped) for both input and
output, passed explicitly to pipeline.run(records_csv=..., out_dir=...)
-- never the project's real artifacts/ directory, which holds the
actual dataset the dashboard/backend demo loads and must not be
clobbered by this test's much smaller synthetic run.
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import generate_data  # noqa: E402
import pipeline  # noqa: E402


def _run_pipeline_in(tmp_path: Path) -> Path:
    records, entity_meta = generate_data.generate(n_entities=120, n_confusable_pairs=20, seed=99)

    with open(tmp_path / "records.csv", "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "record_id", "source_system", "first_name", "last_name",
                "address_line1", "city", "state", "zip", "phone", "email", "dob",
            ],
        )
        writer.writeheader()
        for r in records:
            row = r.__dict__.copy()
            row.pop("entity_id")
            writer.writerow(row)

    with open(tmp_path / "ground_truth.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["record_id", "entity_id"])
        writer.writeheader()
        for r in records:
            writer.writerow({"record_id": r.record_id, "entity_id": r.entity_id})

    with open(tmp_path / "entity_meta.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["entity_id", "is_noisy_source", "is_twin_negative"])
        writer.writeheader()
        for entity_id, meta in entity_meta.items():
            writer.writerow({"entity_id": entity_id, **meta})

    pipeline.run(records_csv=str(tmp_path / "records.csv"), out_dir=str(tmp_path))
    return tmp_path


def test_metrics_json_has_the_expected_shape(tmp_path):
    out_dir = _run_pipeline_in(tmp_path)
    metrics = json.loads((out_dir / "metrics.json").read_text())
    assert metrics["n_records"] > 0
    assert 0.0 <= metrics["test_roc_auc"] <= 1.0
    assert 0.0 <= metrics["review_queue_reduction_at_95pct_recall"] <= 1.0
    assert set(metrics["model_coefficients"].keys()) == set(metrics["feature_names"])


def test_candidate_pairs_jsonl_every_row_has_a_narrative_and_contributions(tmp_path):
    out_dir = _run_pipeline_in(tmp_path)
    lines = (out_dir / "candidate_pairs.jsonl").read_text().strip().split("\n")
    assert len(lines) > 0
    for line in lines[:50]:  # a sample is enough; this file can be large
        row = json.loads(line)
        assert row["record_id_a"] < row["record_id_b"]  # canonical ordering, no reversed duplicates
        assert isinstance(row["narrative"], str) and len(row["narrative"]) > 0
        assert isinstance(row["contributions"], list) and len(row["contributions"]) > 0
        assert 0.0 <= row["match_probability"] <= 1.0


def test_no_duplicate_pairs_in_output(tmp_path):
    out_dir = _run_pipeline_in(tmp_path)
    lines = (out_dir / "candidate_pairs.jsonl").read_text().strip().split("\n")
    seen = set()
    for line in lines:
        row = json.loads(line)
        key = (row["record_id_a"], row["record_id_b"])
        assert key not in seen, f"duplicate pair {key}"
        seen.add(key)
