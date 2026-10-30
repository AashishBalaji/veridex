package com.veridex.api;

import com.veridex.db.CandidatePairDao;
import com.veridex.db.ClusterDao;
import com.veridex.model.CandidatePair;
import com.veridex.model.DecisionRequest;
import com.veridex.model.PairStatus;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;

@RestController
@RequestMapping("/api/review-queue")
public class ReviewQueueController {

    private final CandidatePairDao candidatePairDao;
    private final ClusterDao clusterDao;

    public ReviewQueueController(CandidatePairDao candidatePairDao, ClusterDao clusterDao) {
        this.candidatePairDao = candidatePairDao;
        this.clusterDao = clusterDao;
    }

    @GetMapping
    public List<CandidatePair> queue(
            @RequestParam(defaultValue = "PENDING") PairStatus status,
            @RequestParam(defaultValue = "100") int limit
    ) {
        int cappedLimit = Math.min(Math.max(limit, 1), 500);
        return candidatePairDao.findByStatus(status, cappedLimit);
    }

    @GetMapping("/{id}")
    public CandidatePair get(@PathVariable long id) {
        return candidatePairDao.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "no candidate pair with id " + id));
    }

    /**
     * Applies a reviewer's decision. The DAO's UPDATE ... WHERE status
     * = 'PENDING' is the concurrency gate: a pair already decided by
     * someone else returns 409, never a silent double-apply.
     */
    @PostMapping("/{id}/decision")
    public CandidatePair decide(@PathVariable long id, @Valid @RequestBody DecisionRequest request) {
        PairStatus newStatus = "MERGE".equals(request.decision()) ? PairStatus.MERGED : PairStatus.REJECTED;

        CandidatePair updated = candidatePairDao.applyDecision(id, newStatus, request.reviewer())
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.CONFLICT, "candidate pair " + id + " was already decided"));

        if (newStatus == PairStatus.MERGED) {
            clusterDao.union(updated.recordA().recordId(), updated.recordB().recordId());
        }
        return updated;
    }
}
