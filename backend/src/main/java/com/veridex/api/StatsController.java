package com.veridex.api;

import com.veridex.db.CandidatePairDao;
import com.veridex.db.MetricsDao;
import com.veridex.db.RecordDao;
import com.veridex.model.PairStatus;
import com.veridex.model.Stats;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatsController {

    private final RecordDao recordDao;
    private final CandidatePairDao candidatePairDao;
    private final MetricsDao metricsDao;

    public StatsController(RecordDao recordDao, CandidatePairDao candidatePairDao, MetricsDao metricsDao) {
        this.recordDao = recordDao;
        this.candidatePairDao = candidatePairDao;
        this.metricsDao = metricsDao;
    }

    @GetMapping("/api/stats")
    public Stats stats() {
        return new Stats(
                recordDao.count(),
                candidatePairDao.count(),
                candidatePairDao.countByStatus(PairStatus.PENDING),
                candidatePairDao.countByStatus(PairStatus.MERGED),
                candidatePairDao.countByStatus(PairStatus.REJECTED),
                metricsDao.getReviewQueueReductionAt95Recall()
        );
    }
}
