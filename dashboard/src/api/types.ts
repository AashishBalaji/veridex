export interface IdentityRecord {
  recordId: string;
  sourceSystem: string;
  firstName: string;
  lastName: string;
  addressLine1: string;
  city: string;
  state: string;
  zip: string;
  phone: string;
  email: string;
  dob: string;
}

export interface FeatureContribution {
  feature: string;
  label: string;
  value: number;
  contribution: number;
}

export type PairStatus = "PENDING" | "MERGED" | "REJECTED";

export interface CandidatePair {
  id: number;
  recordA: IdentityRecord;
  recordB: IdentityRecord;
  matchProbability: number;
  status: PairStatus;
  narrative: string;
  contributions: FeatureContribution[];
  decidedBy?: string | null;
  decidedAt?: string | null;
}

export interface Stats {
  totalRecords: number;
  totalCandidatePairs: number;
  pending: number;
  merged: number;
  rejected: number;
  reviewQueueReductionAt95Recall: number;
}

export interface ClusterMember {
  recordId: string;
  sourceSystem: string;
  firstName: string;
  lastName: string;
}
