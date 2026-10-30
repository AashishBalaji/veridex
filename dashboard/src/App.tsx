import { useEffect, useState } from "react";
import "./App.css";
import { ApiError, fetchPair, fetchQueue, fetchStats, getApiBase, setApiBase, submitDecision } from "./api/client";
import type { CandidatePair, PairStatus, Stats } from "./api/types";
import { StatsBar } from "./components/StatsBar";
import { QueueList } from "./components/QueueList";
import { PairDetail } from "./components/PairDetail";
import { ClusterLookup } from "./components/ClusterLookup";

type Tab = "queue" | "clusters";

function App() {
  const [apiBaseInput, setApiBaseInput] = useState(getApiBase());
  const [tab, setTab] = useState<Tab>("queue");
  const [status, setStatus] = useState<PairStatus>("PENDING");
  const [stats, setStats] = useState<Stats | null>(null);
  const [pairs, setPairs] = useState<CandidatePair[]>([]);
  const [selected, setSelected] = useState<CandidatePair | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deciding, setDeciding] = useState(false);

  async function refresh() {
    setError(null);
    try {
      const [s, q] = await Promise.all([fetchStats(), fetchQueue(status)]);
      setStats(s);
      setPairs(q);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.status}: ${e.message}` : String(e));
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  async function selectPair(id: number) {
    try {
      const detail = await fetchPair(id);
      setSelected(detail);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.status}: ${e.message}` : String(e));
    }
  }

  async function decide(decision: "MERGE" | "REJECT", reviewer: string) {
    if (!selected) return;
    setDeciding(true);
    setError(null);
    try {
      await submitDecision(selected.id, decision, reviewer);
      setSelected(null);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? `${e.status}: ${e.message}` : String(e));
    } finally {
      setDeciding(false);
    }
  }

  return (
    <div className="app">
      <header>
        <h1>Veridex</h1>
        <p className="subtitle">Identity resolution review</p>
        <label className="api-base-label">
          API base
          <input
            value={apiBaseInput}
            onChange={(e) => setApiBaseInput(e.target.value)}
            onBlur={() => {
              setApiBase(apiBaseInput);
              refresh();
            }}
          />
        </label>
      </header>

      <nav className="tabs">
        <button className={tab === "queue" ? "active" : ""} onClick={() => setTab("queue")}>
          Review queue
        </button>
        <button className={tab === "clusters" ? "active" : ""} onClick={() => setTab("clusters")}>
          Resolved identities
        </button>
      </nav>

      <StatsBar stats={stats} />
      {error && <p className="status-msg err">{error}</p>}

      {tab === "queue" ? (
        <main className="queue-layout">
          <section className="queue-panel">
            <div className="panel-header">
              <h2>Candidate pairs</h2>
              <select value={status} onChange={(e) => setStatus(e.target.value as PairStatus)}>
                <option value="PENDING">Pending</option>
                <option value="MERGED">Merged</option>
                <option value="REJECTED">Rejected</option>
              </select>
            </div>
            <QueueList pairs={pairs} selectedId={selected?.id ?? null} onSelect={selectPair} />
          </section>
          <section className="detail-panel">
            {selected ? (
              <PairDetail pair={selected} onDecide={decide} deciding={deciding} />
            ) : (
              <p className="empty-state">Select a pair from the queue to review it.</p>
            )}
          </section>
        </main>
      ) : (
        <main className="clusters-layout">
          <ClusterLookup />
        </main>
      )}
    </div>
  );
}

export default App;
