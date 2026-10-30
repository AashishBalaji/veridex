package com.veridex.api;

import com.veridex.db.ClusterDao;
import com.veridex.model.ClusterMember;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;

@RestController
public class ClusterController {

    private final ClusterDao clusterDao;

    public ClusterController(ClusterDao clusterDao) {
        this.clusterDao = clusterDao;
    }

    @GetMapping("/api/clusters/{recordId}")
    public List<ClusterMember> cluster(@PathVariable String recordId) {
        String root = clusterDao.findRoot(recordId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "no record " + recordId));
        return clusterDao.findMembers(root);
    }
}
