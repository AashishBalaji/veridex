package com.veridex.model;

import java.time.Instant;
import java.util.List;

public record CandidatePair(
        long id,
        IdentityRecord recordA,
        IdentityRecord recordB,
        double matchProbability,
        PairStatus status,
        String narrative,
        List<FeatureContribution> contributions,
        String decidedBy,
        Instant decidedAt
) {
}
