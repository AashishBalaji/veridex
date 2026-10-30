import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import _dob_day_month_swapped, _normalize_text, _pair_features, _soundex_block_key  # noqa: E402

RECORD_A = {
    "first_name": "Robert", "last_name": "Smith", "address_line1": "123 Maple St",
    "zip": "60601", "phone": "555-111-2222", "email": "rob.smith1@gmail.com", "dob": "1980-05-10",
}


def test_normalize_text_strips_punctuation_and_lowercases():
    assert _normalize_text("123 Maple St.") == "123 maple st"
    assert _normalize_text(None) == ""
    assert _normalize_text("") == ""


def test_dob_day_month_swapped_detects_the_real_transposition_not_any_mismatch():
    assert _dob_day_month_swapped("1980-05-10", "1980-10-05")
    assert not _dob_day_month_swapped("1980-05-10", "1980-05-10")  # identical, not swapped
    assert not _dob_day_month_swapped("1980-05-10", "1981-05-10")  # different year, not a swap
    assert not _dob_day_month_swapped("", "1980-05-10")


def test_soundex_block_key_is_stable_under_minor_typos():
    # The whole point of soundex is to survive this kind of typo.
    key_original = _soundex_block_key("Smith", "60601")
    key_typo = _soundex_block_key("Smyth", "60601")
    assert key_original == key_typo


def test_soundex_block_key_uses_zip_prefix_not_full_zip():
    key_a = _soundex_block_key("Smith", "60601")
    key_b = _soundex_block_key("Smith", "60601-4321")  # ZIP+4 format difference
    assert key_a == key_b


def test_pair_features_identical_record_scores_maximum_on_every_field():
    feats = _pair_features(RECORD_A, dict(RECORD_A), faiss_sim=1.0)
    assert feats["name_jaro_winkler"] == 1.0
    assert feats["zip5_match"] == 1.0
    assert feats["dob_exact_match"] == 1.0
    assert feats["phone_exact_match"] == 1.0
    assert feats["email_exact_match"] == 1.0


def test_pair_features_completely_different_record_scores_low():
    other = {
        "first_name": "Priya", "last_name": "Nair", "address_line1": "999 Oak Ave",
        "zip": "10001", "phone": "555-999-8888", "email": "priya.n@yahoo.com", "dob": "1992-01-01",
    }
    feats = _pair_features(RECORD_A, other, faiss_sim=0.1)
    assert feats["zip5_match"] == 0.0
    assert feats["dob_exact_match"] == 0.0
    assert feats["phone_exact_match"] == 0.0
    assert feats["email_exact_match"] == 0.0
    assert feats["name_jaro_winkler"] < 0.7


def test_pair_features_missing_zip_does_not_count_as_a_match():
    """
    Two records with equally blank ZIPs must not score a zip5_match --
    "both empty" is a false agreement a naive `(a[:5] == b[:5])` check
    would wrongly reward.
    """
    a = dict(RECORD_A, zip="")
    b = dict(RECORD_A, zip="")
    feats = _pair_features(a, b, faiss_sim=0.5)
    assert feats["zip5_match"] == 0.0
