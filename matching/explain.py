"""
A pluggable match-explanation layer.

Why this exists as an interface rather than one hardcoded function:
the JD this project targets explicitly values "GenAI/LLM-based
applications" and "prompt engineering" alongside "RAG and semantic
search." A real production version of this would plausibly swap in
a hosted LLM call to phrase the explanation more naturally. This
sandbox has no LLM API credentials to give this project of its own
(the harness's own model access is Claude Code's, not something an
application built inside it should borrow or embed), so the default
explainer is a deterministic, template-based natural-language
generator -- but it is grounded in the exact same real, numeric
feature contributions a real LLM-backed implementation would be
handed, through the same `Explainer` interface. Swapping in a real
LLM call later is a new class implementing one method, not a
rewrite.

This also reuses the explainability discipline from Vigil (this
portfolio's AML-triage project): the model decides, something else
explains the decision in terms of the features that actually drove
it -- never free-form, never inventing a reason the model didn't
actually use.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

# For a linear model (logistic regression here), the per-feature
# contribution to the log-odds is exactly coefficient * feature_value
# -- this is not an approximation the way SHAP's KernelExplainer is
# for an arbitrary model; it's the literal decomposition of the
# model's own decision function, sometimes called "linear SHAP"
# because it coincides exactly with the Shapley value for a linear
# model. Vigil used SHAP's TreeExplainer because its model was a
# tree ensemble; here, the model is linear, so the exact
# decomposition is simpler to compute and does not need an
# approximation library at all.
FEATURE_LABELS = {
    "name_jaro_winkler": "name similarity",
    "address_token_jaccard": "address overlap",
    "zip5_match": "ZIP code match",
    "dob_exact_match": "date of birth match",
    "dob_day_month_swapped_match": "date of birth (day/month swapped)",
    "phone_exact_match": "phone number match",
    "email_exact_match": "email match",
    "email_local_part_match": "email username match",
    "faiss_cosine_sim": "overall name/address text similarity",
}


def contributions(features: dict[str, float], coefficients: dict[str, float]) -> list[dict]:
    """
    Exact per-feature log-odds contributions for this candidate pair,
    sorted by absolute magnitude -- the same shape of object Vigil's
    SHAP explanations return, so the dashboard can render both the
    same way.
    """
    items = [
        {"feature": name, "label": FEATURE_LABELS.get(name, name), "value": features[name], "contribution": features[name] * coefficients[name]}
        for name in features
        if name in coefficients
    ]
    return sorted(items, key=lambda c: abs(c["contribution"]), reverse=True)


class Explainer(ABC):
    @abstractmethod
    def explain(self, features: dict[str, float], probability: float, coefficients: dict[str, float]) -> str:
        """Return a short natural-language explanation of the match decision."""


class TemplateExplainer(Explainer):
    """
    Default implementation. Builds its sentence only from the
    top-contributing real features for this pair -- it cannot drift
    into a plausible-sounding reason the model didn't actually rely
    on, because there is no free text generation step at all.
    """

    # Below this magnitude, a feature's effect on the log-odds is
    # noise, not a real reason -- the address-overlap feature's
    # coefficient came out of training near zero (other features
    # already cover what it would tell us), and without this filter
    # a *perfect* address match could show up as "working against"
    # a match purely because of that tiny, practically-meaningless
    # coefficient. That reads as self-contradictory, so it's cut.
    _MIN_CONTRIBUTION = 0.3

    def explain(self, features: dict[str, float], probability: float, coefficients: dict[str, float]) -> str:
        top = contributions(features, coefficients)
        top = [c for c in top if abs(c["contribution"]) >= self._MIN_CONTRIBUTION]
        supporting = [c for c in top if c["contribution"] > 0][:3]
        opposing = [c for c in top if c["contribution"] < 0][:2]

        confidence = "high" if probability >= 0.9 else "moderate" if probability >= 0.6 else "low"
        parts = [f"{probability:.0%} match confidence ({confidence})."]

        if supporting:
            reasons = ", ".join(_describe(c) for c in supporting)
            parts.append(f"Supporting this: {reasons}.")
        if opposing:
            reasons = ", ".join(_describe(c) for c in opposing)
            parts.append(f"Working against it: {reasons}.")
        if not supporting and not opposing:
            parts.append("No individual feature stood out; the decision reflects the combination of weak signals.")
        elif supporting and not opposing and probability < 0.5:
            # Not every reason against a match is a feature that
            # actively contradicts it -- often it's that nothing else
            # confirmed it either. Saying so honestly beats a
            # one-sided explanation that only lists the supporting
            # evidence while the probability itself stayed low.
            unconfirmed = [
                FEATURE_LABELS[name] for name in ("phone_exact_match", "email_exact_match", "dob_exact_match", "zip5_match")
                if features.get(name, 0) < 0.5 and FEATURE_LABELS[name] not in reasons
            ]
            if unconfirmed:
                parts.append(f"But {', '.join(unconfirmed)} did not confirm it, so overall confidence stayed low.")

        return " ".join(parts)


def _describe(c: dict) -> str:
    label = c["label"]
    value = c["value"]
    if label.endswith("match") or "match" in label:
        return f"{label}" if value >= 0.5 else f"{label} is absent"
    return f"{label} is {value:.2f}"


_DEFAULT_EXPLAINER = TemplateExplainer()


def explain_match(features: dict[str, float], probability: float, coefficients: dict[str, float], explainer: Explainer | None = None) -> dict:
    explainer = explainer or _DEFAULT_EXPLAINER
    return {
        "narrative": explainer.explain(features, probability, coefficients),
        "contributions": contributions(features, coefficients),
    }
