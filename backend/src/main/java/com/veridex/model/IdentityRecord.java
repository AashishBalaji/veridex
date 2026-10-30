package com.veridex.model;

/** A single source record, as loaded from the pipeline's records.csv. */
public record IdentityRecord(
        String recordId,
        String sourceSystem,
        String firstName,
        String lastName,
        String addressLine1,
        String city,
        String state,
        String zip,
        String phone,
        String email,
        String dob
) {
}
