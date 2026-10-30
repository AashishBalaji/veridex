package com.veridex.model;

public record ClusterMember(
        String recordId,
        String sourceSystem,
        String firstName,
        String lastName
) {
}
