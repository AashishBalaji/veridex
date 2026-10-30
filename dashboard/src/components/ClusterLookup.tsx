import { useState } from "react";
import { ApiError, fetchCluster } from "../api/client";
import type { ClusterMember } from "../api/types";

export function ClusterLookup() {
  const [recordId, setRecordId] = useState("");
  const [members, setMembers] = useState<ClusterMember[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function lookup() {
    if (!recordId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await fetchCluster(recordId.trim());
      setMembers(result);
    } catch (e) {
      setMembers(null);
      setError(e instanceof ApiError ? `${e.status}: ${e.message}` : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="cluster-lookup">
      <h2>Resolved identity lookup</h2>
      <p className="hint">
        Enter a record id to see every record resolved into the same identity so far (its merged cluster).
      </p>
      <div className="lookup-row">
        <input
          value={recordId}
          onChange={(e) => setRecordId(e.target.value)}
          placeholder="e.g. R000123"
          onKeyDown={(e) => e.key === "Enter" && lookup()}
        />
        <button onClick={lookup} disabled={loading}>
          {loading ? "Looking up…" : "Look up"}
        </button>
      </div>
      {error && <p className="status-msg err">{error}</p>}
      {members && (
        <table className="cluster-table">
          <thead>
            <tr>
              <th>Record ID</th>
              <th>Source</th>
              <th>Name</th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.recordId}>
                <td>{m.recordId}</td>
                <td>
                  <span className="source-tag">{m.sourceSystem}</span>
                </td>
                <td>
                  {m.firstName} {m.lastName}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
