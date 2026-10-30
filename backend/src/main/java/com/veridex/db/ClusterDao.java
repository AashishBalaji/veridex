package com.veridex.db;

import com.veridex.model.ClusterMember;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

/**
 * Union-find via LEAST/GREATEST root merging, kept flat (every row's
 * cluster_root points straight at the current root, never a chain) so
 * a lookup is always one row. Correct and simple at this project's
 * scale -- thousands of records, not a scalable union-find with path
 * compression for millions.
 */
@Repository
public class ClusterDao {

    private final JdbcTemplate jdbc;

    public ClusterDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private static final RowMapper<ClusterMember> MEMBER_MAPPER = (rs, rowNum) -> new ClusterMember(
            rs.getString("record_id"),
            rs.getString("source_system"),
            rs.getString("first_name"),
            rs.getString("last_name")
    );

    /** Seeds every record as its own singleton cluster. Call once at load time. */
    public void initializeIdentity(List<String> recordIds) {
        jdbc.batchUpdate(
                "INSERT INTO record_cluster (record_id, cluster_root) VALUES (?, ?) ON CONFLICT (record_id) DO NOTHING",
                recordIds,
                recordIds.size(),
                (ps, id) -> {
                    ps.setString(1, id);
                    ps.setString(2, id);
                }
        );
    }

    public Optional<String> findRoot(String recordId) {
        List<String> roots = jdbc.query(
                "SELECT cluster_root FROM record_cluster WHERE record_id = ?",
                (rs, n) -> rs.getString("cluster_root"), recordId);
        return roots.stream().findFirst();
    }

    /**
     * Merges the clusters containing recordIdA and recordIdB: both
     * clusters' members end up pointing at LEAST(rootA, rootB), chosen
     * so the merge is deterministic regardless of which side a future
     * second merge comes from.
     */
    public void union(String recordIdA, String recordIdB) {
        String rootA = findRoot(recordIdA).orElseThrow(() -> new IllegalStateException("no cluster for " + recordIdA));
        String rootB = findRoot(recordIdB).orElseThrow(() -> new IllegalStateException("no cluster for " + recordIdB));
        if (rootA.equals(rootB)) {
            return; // already in the same cluster
        }
        String newRoot = rootA.compareTo(rootB) <= 0 ? rootA : rootB;
        String oldRoot = newRoot.equals(rootA) ? rootB : rootA;
        jdbc.update("UPDATE record_cluster SET cluster_root = ? WHERE cluster_root = ?", newRoot, oldRoot);
    }

    public List<ClusterMember> findMembers(String clusterRoot) {
        return jdbc.query(
                """
                SELECT r.record_id, r.source_system, r.first_name, r.last_name
                FROM record_cluster c
                JOIN records r ON r.record_id = c.record_id
                WHERE c.cluster_root = ?
                ORDER BY r.record_id
                """,
                MEMBER_MAPPER, clusterRoot);
    }
}
