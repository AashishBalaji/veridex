package com.veridex.model;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record DecisionRequest(
        @NotBlank
        @Pattern(regexp = "MERGE|REJECT", message = "decision must be MERGE or REJECT")
        String decision,

        @NotBlank
        String reviewer
) {
}
