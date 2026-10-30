import type { Stats } from "../api/types";

export function StatsBar({ stats }: { stats: Stats | null }) {
  if (!stats) return <div className="stats-bar stats-bar-empty">Loading stats…</div>;
  return (
    <div className="stats-bar">
      <div className="stat">
        <span className="stat-value">{stats.totalRecords.toLocaleString()}</span>
        <span className="stat-label">records</span>
      </div>
      <div className="stat">
        <span className="stat-value">{stats.totalCandidatePairs.toLocaleString()}</span>
        <span className="stat-label">candidate pairs</span>
      </div>
      <div className="stat">
        <span className="stat-value stat-pending">{stats.pending.toLocaleString()}</span>
        <span className="stat-label">pending review</span>
      </div>
      <div className="stat">
        <span className="stat-value stat-merged">{stats.merged.toLocaleString()}</span>
        <span className="stat-label">merged</span>
      </div>
      <div className="stat">
        <span className="stat-value stat-rejected">{stats.rejected.toLocaleString()}</span>
        <span className="stat-label">rejected</span>
      </div>
      <div className="stat">
        <span className="stat-value">{(stats.reviewQueueReductionAt95Recall * 100).toFixed(0)}%</span>
        <span className="stat-label">auto-resolved at 95% recall</span>
      </div>
    </div>
  );
}
