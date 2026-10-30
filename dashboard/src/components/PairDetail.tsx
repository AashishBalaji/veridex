import { useState } from "react";
import type { CandidatePair, IdentityRecord } from "../api/types";

const FIELDS: { key: keyof IdentityRecord; label: string }[] = [
  { key: "firstName", label: "First name" },
  { key: "lastName", label: "Last name" },
  { key: "addressLine1", label: "Address" },
  { key: "city", label: "City" },
  { key: "state", label: "State" },
  { key: "zip", label: "ZIP" },
  { key: "phone", label: "Phone" },
  { key: "email", label: "Email" },
  { key: "dob", label: "DOB" },
];

export function PairDetail({
  pair,
  onDecide,
  deciding,
}: {
  pair: CandidatePair;
  onDecide: (decision: "MERGE" | "REJECT", reviewer: string) => void;
  deciding: boolean;
}) {
  const [reviewer, setReviewer] = useState("");

  const maxAbs = Math.max(...pair.contributions.map((c) => Math.abs(c.contribution)), 0.1);

  return (
    <div className="pair-detail">
      <h2>
        Pair #{pair.id}{" "}
        <span
          className={`confidence-badge ${
            pair.matchProbability >= 0.9 ? "high" : pair.matchProbability >= 0.6 ? "moderate" : "low"
          }`}
        >
          {(pair.matchProbability * 100).toFixed(0)}% match confidence
        </span>
      </h2>

      <table className="compare-table">
        <thead>
          <tr>
            <th></th>
            <th>
              Record A <span className="source-tag">{pair.recordA.sourceSystem}</span>
            </th>
            <th>
              Record B <span className="source-tag">{pair.recordB.sourceSystem}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {FIELDS.map(({ key, label }) => {
            const a = pair.recordA[key] || "—";
            const b = pair.recordB[key] || "—";
            const differs = pair.recordA[key] !== pair.recordB[key];
            return (
              <tr key={key}>
                <td className="field-label">{label}</td>
                <td className={differs ? "differs" : ""}>{a}</td>
                <td className={differs ? "differs" : ""}>{b}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <h3>Why this score</h3>
      <p className="narrative">{pair.narrative}</p>
      <div className="explanation-bars">
        {pair.contributions.map((c) => {
          const pct = (Math.abs(c.contribution) / maxAbs) * 50;
          const positive = c.contribution >= 0;
          return (
            <div className="bar-row" key={c.feature}>
              <span>{c.label}</span>
              <span className="bar-track">
                <span className={`bar-fill ${positive ? "positive" : "negative"}`} style={{ width: `${pct}%` }} />
              </span>
              <span>{c.contribution.toFixed(2)}</span>
            </div>
          );
        })}
      </div>

      {pair.status === "PENDING" ? (
        <div className="decision-panel">
          <label>
            Reviewer
            <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="your.name" />
          </label>
          <div className="decision-buttons">
            <button
              className="merge-btn"
              disabled={!reviewer || deciding}
              onClick={() => onDecide("MERGE", reviewer)}
            >
              Merge — same identity
            </button>
            <button
              className="reject-btn"
              disabled={!reviewer || deciding}
              onClick={() => onDecide("REJECT", reviewer)}
            >
              Reject — different people
            </button>
          </div>
        </div>
      ) : (
        <p className="decided-note">
          Already decided: <strong>{pair.status}</strong> by {pair.decidedBy} at{" "}
          {pair.decidedAt ? new Date(pair.decidedAt).toLocaleString() : ""}
        </p>
      )}
    </div>
  );
}
