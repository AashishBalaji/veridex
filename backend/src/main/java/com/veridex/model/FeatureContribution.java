package com.veridex.model;

/**
 * One feature's exact contribution to the match-probability decision,
 * as computed by matching/explain.py (coefficient * value, for a
 * linear model -- no SHAP library needed). Loaded verbatim from
 * candidate_pairs.jsonl; the Java backend never recomputes this.
 */
public record FeatureContribution(
        String feature,
        String label,
        double value,
        double contribution
) {
}
