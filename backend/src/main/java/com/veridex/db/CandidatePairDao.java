package com.veridex.db;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.veridex.model.CandidatePair;
import com.veridex.model.FeatureContribution;
import com.veridex.model.IdentityRecord;
import com.veridex.model.PairStatus;
import org.postgresql.util.PGobject;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

import java.sql.SQLException;
import java.sql.Timestamp;
import java.sql.Types;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

@Repository
public class CandidatePairDao {

    private final JdbcTemplate jdbc;
    private final RecordDao recordDao;
    private final ObjectMapper objectMapper;

    public CandidatePairDao(JdbcTemplate jdbc, RecordDao recordDao, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.recordDao = recordDao;
        this.objectMapper = objectMapper;
    }

    /** One row as staged for a batch insert, before the join to records. */
    public record StagedPair(
            String recordIdA,
            String recordIdB,
            double matchProbability,
            String narrative,
            List<FeatureContribution> contributions
    ) {
    }

    public long count() {
        Long n = jdbc.queryForObject("SELECT COUNT(*) FROM candidate_pairs", Long.class);
        return n == null ? 0 : n;
    }

    public long countByStatus(PairStatus status) {
        Long n = jdbc.queryForObject(
                "SELECT COUNT(*) FROM candidate_pairs WHERE status = ?", Long.class, status.name());
        return n == null ? 0 : n;
    }

    public void insertAll(List<StagedPair> pairs) {
        jdbc.batchUpdate(
                """
                INSERT INTO candidate_pairs
                    (record_id_a, record_id_b, match_probability, narrative, contributions, status)
                VALUES (?, ?, ?, ?, ?, 'PENDING')
                ON CONFLICT (record_id_a, record_id_b) DO NOTHING
                """,
                pairs,
                pairs.size(),
                (ps, p) -> {
                    ps.setString(1, p.recordIdA());
                    ps.setString(2, p.recordIdB());
                    ps.setDouble(3, p.matchProbability());
                    ps.setString(4, p.narrative());
                    ps.setObject(5, toJsonb(p.contributions()), Types.OTHER);
                }
        );
    }

    private PGobject toJsonb(List<FeatureContribution> contributions) {
        try {
            PGobject jsonObject = new PGobject();
            jsonObject.setType("jsonb");
            jsonObject.setValue(objectMapper.writeValueAsString(contributions));
            return jsonObject;
        } catch (JsonProcessingException | SQLException e) {
            throw new IllegalStateException("failed to serialize contributions to jsonb", e);
        }
    }

    public Optional<CandidatePair> findById(long id) {
        List<CandidatePair> rows = jdbc.query(
                "SELECT * FROM candidate_pairs WHERE id = ?", this::mapRow, id);
        return rows.stream().findFirst();
    }

    public List<CandidatePair> findByStatus(PairStatus status, int limit) {
        return jdbc.query(
                "SELECT * FROM candidate_pairs WHERE status = ? ORDER BY match_probability DESC LIMIT ?",
                this::mapRow, status.name(), limit);
    }

    /**
     * Atomic decision apply: only succeeds if the pair is still
     * PENDING, mirroring Vigil's record_disposition / OpsPilot's
     * governance-gate concurrency invariant (two reviewers racing on
     * the same pair must not both "win").
     *
     * @return the updated pair, or empty if it was no longer PENDING
     */
    public Optional<CandidatePair> applyDecision(long id, PairStatus newStatus, String reviewer) {
        int updated = jdbc.update(
                """
                UPDATE candidate_pairs
                SET status = ?, decided_by = ?, decided_at = ?
                WHERE id = ? AND status = 'PENDING'
                """,
                newStatus.name(), reviewer, Timestamp.from(Instant.now()), id);
        if (updated == 0) {
            return Optional.empty();
        }
        return findById(id);
    }

    private CandidatePair mapRow(java.sql.ResultSet rs, int rowNum) throws SQLException {
        IdentityRecord recordA = recordDao.findById(rs.getString("record_id_a"))
                .orElseThrow(() -> new IllegalStateException("dangling record_id_a on candidate_pairs row"));
        IdentityRecord recordB = recordDao.findById(rs.getString("record_id_b"))
                .orElseThrow(() -> new IllegalStateException("dangling record_id_b on candidate_pairs row"));

        List<FeatureContribution> contributions;
        try {
            contributions = objectMapper.readValue(
                    rs.getString("contributions"),
                    objectMapper.getTypeFactory().constructCollectionType(List.class, FeatureContribution.class));
        } catch (Exception e) {
            throw new SQLException("failed to deserialize contributions jsonb", e);
        }

        Timestamp decidedAt = rs.getTimestamp("decided_at");
        return new CandidatePair(
                rs.getLong("id"),
                recordA,
                recordB,
                rs.getDouble("match_probability"),
                PairStatus.valueOf(rs.getString("status")),
                rs.getString("narrative"),
                contributions,
                rs.getString("decided_by"),
                decidedAt == null ? null : decidedAt.toInstant()
        );
    }
}
