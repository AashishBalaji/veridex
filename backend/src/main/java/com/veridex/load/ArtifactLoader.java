package com.veridex.load;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.veridex.db.CandidatePairDao;
import com.veridex.db.ClusterDao;
import com.veridex.db.MetricsDao;
import com.veridex.db.RecordDao;
import com.veridex.model.FeatureContribution;
import com.veridex.model.IdentityRecord;
import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/**
 * Loads the artifacts the Python pipeline (matching/pipeline.py)
 * wrote -- records.csv, candidate_pairs.jsonl, metrics.json -- into
 * Postgres once at startup, if the records table is still empty.
 *
 * Deliberately loads the pipeline's *precomputed* narrative and
 * per-feature contributions from candidate_pairs.jsonl rather than
 * reimplementing matching/explain.py's explanation logic in Java:
 * one source of truth for "why this pair matched", not two
 * implementations that can quietly drift apart.
 */
@Component
public class ArtifactLoader implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(ArtifactLoader.class);

    private final RecordDao recordDao;
    private final CandidatePairDao candidatePairDao;
    private final ClusterDao clusterDao;
    private final MetricsDao metricsDao;
    private final ObjectMapper objectMapper;
    private final String artifactsDir;

    public ArtifactLoader(
            RecordDao recordDao,
            CandidatePairDao candidatePairDao,
            ClusterDao clusterDao,
            MetricsDao metricsDao,
            ObjectMapper objectMapper,
            @Value("${veridex.artifacts-dir}") String artifactsDir
    ) {
        this.recordDao = recordDao;
        this.candidatePairDao = candidatePairDao;
        this.clusterDao = clusterDao;
        this.metricsDao = metricsDao;
        this.objectMapper = objectMapper;
        this.artifactsDir = artifactsDir;
    }

    @Override
    public void run(String... args) throws IOException {
        if (recordDao.count() > 0) {
            log.info("records table already populated, skipping artifact load");
            return;
        }

        Path dir = Path.of(artifactsDir);
        if (!Files.isDirectory(dir)) {
            log.warn("artifacts directory {} not found -- starting with an empty database. "
                    + "Run matching/pipeline.py first, or set VERIDEX_ARTIFACTS_DIR.", dir.toAbsolutePath());
            return;
        }

        List<IdentityRecord> records = loadRecords(dir.resolve("records.csv"));
        recordDao.insertAll(records);
        clusterDao.initializeIdentity(records.stream().map(IdentityRecord::recordId).toList());
        log.info("loaded {} records", records.size());

        List<CandidatePairDao.StagedPair> pairs = loadCandidatePairs(dir.resolve("candidate_pairs.jsonl"));
        candidatePairDao.insertAll(pairs);
        log.info("loaded {} candidate pairs", pairs.size());

        loadMetrics(dir.resolve("metrics.json"));
    }

    private List<IdentityRecord> loadRecords(Path csvPath) throws IOException {
        List<IdentityRecord> records = new ArrayList<>();
        try (Reader reader = Files.newBufferedReader(csvPath, StandardCharsets.UTF_8);
             CSVParser parser = CSVFormat.DEFAULT.builder().setHeader().setSkipHeaderRecord(true).build().parse(reader)) {
            for (var row : parser) {
                records.add(new IdentityRecord(
                        row.get("record_id"),
                        row.get("source_system"),
                        row.get("first_name"),
                        row.get("last_name"),
                        row.get("address_line1"),
                        row.get("city"),
                        row.get("state"),
                        row.get("zip"),
                        row.get("phone"),
                        row.get("email"),
                        row.get("dob")
                ));
            }
        }
        return records;
    }

    private List<CandidatePairDao.StagedPair> loadCandidatePairs(Path jsonlPath) throws IOException {
        List<CandidatePairDao.StagedPair> pairs = new ArrayList<>();
        try (BufferedReader reader = Files.newBufferedReader(jsonlPath, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) {
                    continue;
                }
                JsonNode node = objectMapper.readTree(line);
                List<FeatureContribution> contributions = new ArrayList<>();
                for (JsonNode c : node.get("contributions")) {
                    contributions.add(new FeatureContribution(
                            c.get("feature").asText(),
                            c.get("label").asText(),
                            c.get("value").asDouble(),
                            c.get("contribution").asDouble()
                    ));
                }
                pairs.add(new CandidatePairDao.StagedPair(
                        node.get("record_id_a").asText(),
                        node.get("record_id_b").asText(),
                        node.get("match_probability").asDouble(),
                        node.get("narrative").asText(),
                        contributions
                ));
            }
        }
        return pairs;
    }

    private void loadMetrics(Path metricsPath) throws IOException {
        if (!Files.exists(metricsPath)) {
            log.warn("metrics.json not found at {}, review-queue-reduction stat will read as 0", metricsPath);
            return;
        }
        JsonNode node = objectMapper.readTree(Files.readString(metricsPath, StandardCharsets.UTF_8));
        double reduction = node.get("review_queue_reduction_at_95pct_recall").asDouble();
        metricsDao.setReviewQueueReductionAt95Recall(reduction);
    }
}
