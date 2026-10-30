package com.veridex.db;

import com.veridex.model.IdentityRecord;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

/**
 * Plain JdbcTemplate DAO, not Spring Data JPA -- keeps the SQL
 * explicit and visible, matching this portfolio's established style
 * (Vigil used raw psycopg2 for the same reason).
 */
@Repository
public class RecordDao {

    private final JdbcTemplate jdbc;

    public RecordDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private static final RowMapper<IdentityRecord> MAPPER = (rs, rowNum) -> new IdentityRecord(
            rs.getString("record_id"),
            rs.getString("source_system"),
            rs.getString("first_name"),
            rs.getString("last_name"),
            rs.getString("address_line1"),
            rs.getString("city"),
            rs.getString("state"),
            rs.getString("zip"),
            rs.getString("phone"),
            rs.getString("email"),
            rs.getString("dob")
    );

    public long count() {
        Long n = jdbc.queryForObject("SELECT COUNT(*) FROM records", Long.class);
        return n == null ? 0 : n;
    }

    public void insertAll(List<IdentityRecord> records) {
        jdbc.batchUpdate(
                """
                INSERT INTO records
                    (record_id, source_system, first_name, last_name, address_line1,
                     city, state, zip, phone, email, dob)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (record_id) DO NOTHING
                """,
                records,
                records.size(),
                (ps, r) -> {
                    ps.setString(1, r.recordId());
                    ps.setString(2, r.sourceSystem());
                    ps.setString(3, r.firstName());
                    ps.setString(4, r.lastName());
                    ps.setString(5, r.addressLine1());
                    ps.setString(6, r.city());
                    ps.setString(7, r.state());
                    ps.setString(8, r.zip());
                    ps.setString(9, r.phone());
                    ps.setString(10, r.email());
                    ps.setString(11, r.dob());
                }
        );
    }

    public Optional<IdentityRecord> findById(String recordId) {
        List<IdentityRecord> rows = jdbc.query(
                "SELECT * FROM records WHERE record_id = ?", MAPPER, recordId);
        return rows.stream().findFirst();
    }

    public List<IdentityRecord> findByIds(List<String> recordIds) {
        if (recordIds.isEmpty()) {
            return List.of();
        }
        String placeholders = String.join(",", recordIds.stream().map(id -> "?").toList());
        return jdbc.query(
                "SELECT * FROM records WHERE record_id IN (" + placeholders + ") ORDER BY record_id",
                MAPPER,
                recordIds.toArray());
    }
}
