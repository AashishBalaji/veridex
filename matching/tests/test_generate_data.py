import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generate_data import generate  # noqa: E402


def test_generation_is_deterministic_given_the_same_seed():
    records_a, meta_a = generate(n_entities=50, n_confusable_pairs=10, seed=7)
    records_b, meta_b = generate(n_entities=50, n_confusable_pairs=10, seed=7)
    assert [r.__dict__ for r in records_a] == [r.__dict__ for r in records_b]
    assert meta_a == meta_b


def test_every_record_belongs_to_a_known_entity():
    records, meta = generate(n_entities=50, n_confusable_pairs=10, seed=1)
    entity_ids = set(meta.keys())
    assert all(r.entity_id in entity_ids for r in records)


def test_some_entities_have_multiple_records_and_some_have_one():
    records, _ = generate(n_entities=200, n_confusable_pairs=20, seed=2)
    counts: dict[int, int] = {}
    for r in records:
        counts[r.entity_id] = counts.get(r.entity_id, 0) + 1
    assert any(c == 1 for c in counts.values())
    assert any(c >= 2 for c in counts.values())


def test_confusable_negative_entities_exist_and_overlap_surname_and_zip_with_a_distinct_entity():
    """
    The generator's whole point for these entities is to produce
    "two different people, same surname and address" cases. Checked
    at the dataset level rather than per-twin-record, since any
    individual record can itself carry an independent typo in last
    name or ZIP (that's deliberate -- see _variant_record) and
    shouldn't make this check flaky.
    """
    records, meta = generate(n_entities=100, n_confusable_pairs=40, seed=3)
    twin_entity_ids = {eid for eid, m in meta.items() if m["is_twin_negative"]}
    assert len(twin_entity_ids) > 0

    by_surname_zip: dict[tuple[str, str], set[int]] = {}
    for r in records:
        key = (r.last_name, r.zip[:5])
        by_surname_zip.setdefault(key, set()).add(r.entity_id)

    n_groups_with_multiple_entities = sum(1 for entity_ids in by_surname_zip.values() if len(entity_ids) >= 2)
    assert n_groups_with_multiple_entities > 0


def test_noisy_source_records_have_a_degraded_field_at_higher_rate():
    """
    Not a guarantee for any single record (corruption is probabilistic),
    but over enough noisy vs. non-noisy records, missing/blank fields
    should be meaningfully more common in the noisy group -- otherwise
    the "legacy source" noise this pipeline relies on for honest
    metrics isn't actually doing anything.
    """
    records, meta = generate(n_entities=600, n_confusable_pairs=0, seed=4)
    noisy_entities = {eid for eid, m in meta.items() if m["is_noisy_source"]}

    noisy_records = [r for r in records if r.entity_id in noisy_entities]
    assert len(noisy_records) > 20

    def blank_rate(recs):
        fields = ["phone", "email", "dob"]
        blanks = sum(1 for r in recs for f in fields if not getattr(r, f))
        return blanks / (len(recs) * len(fields))

    all_entities_with_records = {r.entity_id for r in records}
    clean_entities = all_entities_with_records - noisy_entities
    clean_records = [r for r in records if r.entity_id in clean_entities]

    assert blank_rate(noisy_records) > blank_rate(clean_records)
