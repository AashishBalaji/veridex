import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from explain import contributions, explain_match  # noqa: E402

COEFFICIENTS = {
    "name_jaro_winkler": 7.1,
    "address_token_jaccard": -0.03,  # deliberately near-zero, see explain.py's _MIN_CONTRIBUTION
    "zip5_match": 2.2,
    "dob_exact_match": 2.2,
    "phone_exact_match": 1.5,
    "email_exact_match": 2.8,
}


def test_contributions_are_sorted_by_absolute_magnitude():
    features = {"name_jaro_winkler": 0.9, "zip5_match": 1.0, "phone_exact_match": 0.0}
    result = contributions(features, COEFFICIENTS)
    mags = [abs(c["contribution"]) for c in result]
    assert mags == sorted(mags, reverse=True)


def test_contribution_is_exactly_coefficient_times_value():
    features = {"dob_exact_match": 1.0}
    result = contributions(features, COEFFICIENTS)
    assert result[0]["contribution"] == COEFFICIENTS["dob_exact_match"] * 1.0


def test_negligible_coefficient_does_not_appear_as_a_misleading_opposing_reason():
    """
    The real bug this guards: address_token_jaccard's coefficient came
    out of training near zero. Before filtering by magnitude, a
    *perfect* address match (value=1.0) could still show up as
    "working against" a match purely from that tiny coefficient,
    which reads as self-contradictory. See explain.py's _MIN_CONTRIBUTION.
    """
    features = {
        "name_jaro_winkler": 0.95,
        "address_token_jaccard": 1.0,  # perfect overlap
        "zip5_match": 1.0,
        "dob_exact_match": 0.0,
        "phone_exact_match": 0.0,
        "email_exact_match": 0.0,
    }
    narrative = explain_match(features, probability=0.9, coefficients=COEFFICIENTS)["narrative"]
    assert "address overlap" not in narrative.lower() or "working against" not in narrative.lower()


def test_low_confidence_explanation_names_what_failed_to_confirm_it():
    features = {
        "name_jaro_winkler": 0.8,
        "address_token_jaccard": 0.0,
        "zip5_match": 0.0,
        "dob_exact_match": 0.0,
        "phone_exact_match": 0.0,
        "email_exact_match": 0.0,
    }
    result = explain_match(features, probability=0.1, coefficients=COEFFICIENTS)
    assert "did not confirm" in result["narrative"]


def test_narrative_always_states_the_probability():
    features = {"name_jaro_winkler": 0.5}
    narrative = explain_match(features, probability=0.42, coefficients=COEFFICIENTS)["narrative"]
    assert "42%" in narrative
