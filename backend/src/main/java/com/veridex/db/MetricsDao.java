package com.veridex.db;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

/** The single pipeline-run metric the dashboard shows alongside live counts. */
@Repository
public class MetricsDao {

    private final JdbcTemplate jdbc;

    public MetricsDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void setReviewQueueReductionAt95Recall(double value) {
        jdbc.update(
                """
                INSERT INTO pipeline_run_metadata (id, review_queue_reduction_at_95pct_recall)
                VALUES (1, ?)
                ON CONFLICT (id) DO UPDATE SET review_queue_reduction_at_95pct_recall = EXCLUDED.review_queue_reduction_at_95pct_recall
                """,
                value);
    }

    public double getReviewQueueReductionAt95Recall() {
        List<Double> rows = jdbc.query(
                "SELECT review_queue_reduction_at_95pct_recall FROM pipeline_run_metadata WHERE id = 1",
                (rs, n) -> rs.getDouble("review_queue_reduction_at_95pct_recall"));
        return Optional.ofNullable(rows.isEmpty() ? null : rows.get(0)).orElse(0.0);
    }
}
