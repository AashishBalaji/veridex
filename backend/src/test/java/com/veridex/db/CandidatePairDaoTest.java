package com.veridex.db;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.veridex.model.FeatureContribution;
import com.veridex.model.IdentityRecord;
import com.veridex.model.PairStatus;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Runs against a real local Postgres database (veridex_test), not an
 * in-memory substitute -- the JSONB column and PGobject handling in
 * CandidatePairDao are Postgres-specific and an H2-style fake would
 * hide bugs in exactly that code. Mirrors this portfolio's standing
 * "verify against a real running service" discipline.
 */
@SpringBootTest
@ActiveProfiles("test")
class CandidatePairDaoTest {

    @Autowired
    private JdbcTemplate jdbc;
    @Autowired
    private RecordDao recordDao;
    @Autowired
    private CandidatePairDao candidatePairDao;
    @Autowired
    private ClusterDao clusterDao;
    @Autowired
    private ObjectMapper objectMapper;

    private static final IdentityRecord RECORD_A = new IdentityRecord(
            "r-1", "crm", "Robert", "Smith", "123 Maple St", "Chicago", "IL", "60601",
            "555-111-2222", "rob@example.com", "1980-05-10");
    private static final IdentityRecord RECORD_B = new IdentityRecord(
            "r-2", "billing", "Bob", "Smith", "123 Maple Street", "Chicago", "IL", "60601",
            "555-111-2222", "", "1980-05-10");

    @BeforeEach
    void cleanDatabase() {
        jdbc.update("DELETE FROM candidate_pairs");
        jdbc.update("DELETE FROM record_cluster");
        jdbc.update("DELETE FROM pipeline_run_metadata");
        jdbc.update("DELETE FROM records");
    }

    @Test
    void insertedPairRoundTripsItsContributionsExactly() {
        recordDao.insertAll(List.of(RECORD_A, RECORD_B));
        clusterDao.initializeIdentity(List.of("r-1", "r-2"));

        List<FeatureContribution> contributions = List.of(
                new FeatureContribution("name_jaro_winkler", "Name similarity", 0.95, 6.7),
                new FeatureContribution("email_exact_match", "Email match", 0.0, 0.0)
        );
        candidatePairDao.insertAll(List.of(
                new CandidatePairDao.StagedPair("r-1", "r-2", 0.87, "87% match confidence (high).", contributions)
        ));

        var pairs = candidatePairDao.findByStatus(PairStatus.PENDING, 10);
        assertThat(pairs).hasSize(1);
        var pair = pairs.get(0);
        assertThat(pair.recordA().recordId()).isEqualTo("r-1");
        assertThat(pair.recordB().recordId()).isEqualTo("r-2");
        assertThat(pair.matchProbability()).isEqualTo(0.87);
        assertThat(pair.contributions()).hasSize(2);
        assertThat(pair.contributions().get(0).feature()).isEqualTo("name_jaro_winkler");
        assertThat(pair.status()).isEqualTo(PairStatus.PENDING);
    }

    @Test
    void secondDecisionOnAnAlreadyDecidedPairIsRejected() {
        recordDao.insertAll(List.of(RECORD_A, RECORD_B));
        clusterDao.initializeIdentity(List.of("r-1", "r-2"));
        candidatePairDao.insertAll(List.of(
                new CandidatePairDao.StagedPair("r-1", "r-2", 0.9, "narrative", List.of())
        ));
        long id = candidatePairDao.findByStatus(PairStatus.PENDING, 10).get(0).id();

        Optional<com.veridex.model.CandidatePair> first = candidatePairDao.applyDecision(id, PairStatus.MERGED, "alice");
        assertThat(first).isPresent();
        assertThat(first.get().status()).isEqualTo(PairStatus.MERGED);

        // The whole point of the WHERE status = 'PENDING' guard: a
        // second reviewer deciding the same pair must not silently
        // overwrite the first reviewer's decision.
        Optional<com.veridex.model.CandidatePair> second = candidatePairDao.applyDecision(id, PairStatus.REJECTED, "bob");
        assertThat(second).isEmpty();

        var stillMerged = candidatePairDao.findById(id).orElseThrow();
        assertThat(stillMerged.status()).isEqualTo(PairStatus.MERGED);
        assertThat(stillMerged.decidedBy()).isEqualTo("alice");
    }

    @Test
    void mergingTwoRecordsPutsThemInTheSameCluster() {
        recordDao.insertAll(List.of(RECORD_A, RECORD_B));
        clusterDao.initializeIdentity(List.of("r-1", "r-2"));

        assertThat(clusterDao.findRoot("r-1")).isNotEqualTo(Optional.empty());
        String rootBefore1 = clusterDao.findRoot("r-1").orElseThrow();
        String rootBefore2 = clusterDao.findRoot("r-2").orElseThrow();
        assertThat(rootBefore1).isNotEqualTo(rootBefore2); // distinct singleton clusters

        clusterDao.union("r-1", "r-2");

        String rootAfter1 = clusterDao.findRoot("r-1").orElseThrow();
        String rootAfter2 = clusterDao.findRoot("r-2").orElseThrow();
        assertThat(rootAfter1).isEqualTo(rootAfter2);

        var members = clusterDao.findMembers(rootAfter1);
        assertThat(members).extracting("recordId").containsExactlyInAnyOrder("r-1", "r-2");
    }
}
