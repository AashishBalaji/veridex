package com.veridex.model;

public record Stats(
        long totalRecords,
        long totalCandidatePairs,
        long pending,
        long merged,
        long rejected,
        double reviewQueueReductionAt95Recall
) {
}
