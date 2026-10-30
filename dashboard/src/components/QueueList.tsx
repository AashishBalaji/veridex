import type { CandidatePair } from "../api/types";

export function QueueList({
  pairs,
  selectedId,
  onSelect,
}: {
  pairs: CandidatePair[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  if (pairs.length === 0) {
    return <p className="empty-state">No pairs in this queue right now.</p>;
  }
  return (
    <table className="queue-table">
      <thead>
        <tr>
          <th>Pair</th>
          <th>Record A</th>
          <th>Record B</th>
          <th>Confidence</th>
        </tr>
      </thead>
      <tbody>
        {pairs.map((p) => (
          <tr
            key={p.id}
            className={`queue-row ${p.id === selectedId ? "selected" : ""}`}
            onClick={() => onSelect(p.id)}
          >
            <td>#{p.id}</td>
            <td>
              {p.recordA.firstName} {p.recordA.lastName}
              <span className="source-tag">{p.recordA.sourceSystem}</span>
            </td>
            <td>
              {p.recordB.firstName} {p.recordB.lastName}
              <span className="source-tag">{p.recordB.sourceSystem}</span>
            </td>
            <td>
              <span
                className={`confidence-badge ${
                  p.matchProbability >= 0.9 ? "high" : p.matchProbability >= 0.6 ? "moderate" : "low"
                }`}
              >
                {(p.matchProbability * 100).toFixed(0)}%
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
