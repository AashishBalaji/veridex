import type { CandidatePair, ClusterMember, PairStatus, Stats } from "./types";

// A plain fetch-based client, same pattern used for the other
// projects in this portfolio -- no generated client, no extra
// dependency, just a thin typed wrapper so components never build
// URLs or parse JSON themselves.
let apiBase = "http://127.0.0.1:8080";

export function setApiBase(base: string): void {
  apiBase = base.replace(/\/$/, "");
}

export function getApiBase(): string {
  return apiBase;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${apiBase}${path}`, init);
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    throw new ApiError(resp.status, body || resp.statusText);
  }
  return (await resp.json()) as T;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function fetchStats(): Promise<Stats> {
  return request<Stats>("/api/stats");
}

export function fetchQueue(status: PairStatus = "PENDING", limit = 100): Promise<CandidatePair[]> {
  return request<CandidatePair[]>(`/api/review-queue?status=${status}&limit=${limit}`);
}

export function fetchPair(id: number): Promise<CandidatePair> {
  return request<CandidatePair>(`/api/review-queue/${id}`);
}

export function submitDecision(id: number, decision: "MERGE" | "REJECT", reviewer: string): Promise<CandidatePair> {
  return request<CandidatePair>(`/api/review-queue/${id}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, reviewer }),
  });
}

export function fetchCluster(recordId: string): Promise<ClusterMember[]> {
  return request<ClusterMember[]>(`/api/clusters/${encodeURIComponent(recordId)}`);
}
