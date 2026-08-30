export type OutcomeStatus =
  | "RECONCILED"
  | "RECONCILED_WITH_WARNINGS"
  | "PARTIALLY_RECONCILED"
  | "UNRECONCILED"
  | "REQUIRES_REVIEW"
  | "INVALID_DATA";

export interface EvaluationMetric {
  metric: string;
  value: number;
  detail: string;
  target: number | null;
}

export interface Analytics {
  run_id: string;
  currency: string;
  total_processed_minor: number;
  reconciled_minor: number;
  unresolved_minor: number;
  reconciliation_rate: number;
  settlement_count: number;
  automatically_reconciled: number;
  review_count: number;
  unreconciled_count: number;
  exception_count: number;
  ruleset_version: string;
  evaluation: {
    outcome_accuracy: number;
    auto_reconcile_precision: number;
    false_reconciled: number;
    correct_outcomes: number;
    scorecard: EvaluationMetric[];
  } | null;
}

export interface Outcome {
  settlement_id: string;
  status: OutcomeStatus;
  confidence: "HIGH" | "MEDIUM" | "LOW" | "NONE";
  calculation: {
    currency: string;
    payment_credits_minor: number;
    refund_debits_minor: number;
    adjustment_net_minor: number;
    fees_minor: number;
    tax_minor: number;
    expected_net_minor: number;
    reported_minor: number;
    gateway_delta_minor: number;
  };
  bank_match: {
    bank_transaction_id: string | null;
    accepted: boolean;
    reason: string;
  };
  exceptions: Array<{
    code: string;
    message: string;
    affected_amount_minor: number;
    severity: string;
  }>;
}

export interface Evidence {
  subject: { type: string; id: string };
  outcome: { status: OutcomeStatus; confidence: string };
  calculation: {
    currency: string;
    payment_credits_minor: number;
    refund_debits_minor: number;
    adjustment_net_minor: number;
    fees_minor: number;
    tax_minor: number;
    expected_net_minor: number;
    reported_settlement_minor: number;
    gateway_delta_minor: number;
  };
  bank_match: {
    bank_transaction_id: string | null;
    confidence: string;
    reason: string;
    candidate_ids: string[];
  };
  exceptions: Array<{
    code: string;
    message: string;
    affected_amount_minor: number;
    severity: string;
    evidence_ids: string[];
  }>;
  source_refs: Array<{ type: string; id: string }>;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    throw new Error(`API request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function createDemoRun(seed = 20260825, orderCount = 500) {
  return request<{ run_id: string }>("/reconciliation-runs/demo", {
    method: "POST",
    body: JSON.stringify({ seed, order_count: orderCount }),
  });
}

export function getAnalytics(runId: string) {
  return request<Analytics>(`/reconciliation-runs/${runId}/analytics`);
}

export function getOutcomes(runId: string) {
  return request<Outcome[]>(`/reconciliation-runs/${runId}/outcomes`);
}

export function getEvidence(runId: string, settlementId: string) {
  return request<Evidence>(`/reconciliation-runs/${runId}/settlements/${settlementId}`);
}

export function askController(runId: string, settlementId: string, question: string) {
  return request<{
    answer: string;
    evidence_ids: string[];
    provider: string;
    model: string;
    advisory: boolean;
    requires_human_review: boolean;
    fallback_reason: string | null;
    attempted_provider: string | null;
    attempted_model: string | null;
  }>(
    "/ai/queries",
    {
      method: "POST",
      body: JSON.stringify({ run_id: runId, settlement_id: settlementId, question }),
    },
  );
}
