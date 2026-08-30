"use client";

import { FormEvent, Fragment, useMemo, useState } from "react";
import Image from "next/image";
import {
  Analytics,
  Evidence,
  Outcome,
  OutcomeStatus,
  askController,
  createDemoRun,
  getAnalytics,
  getEvidence,
  getOutcomes,
} from "@/lib/api";

const STATUS_LABELS: Record<OutcomeStatus, string> = {
  RECONCILED: "Reconciled",
  RECONCILED_WITH_WARNINGS: "Reconciled · warning",
  PARTIALLY_RECONCILED: "Partially reconciled",
  UNRECONCILED: "Unreconciled",
  REQUIRES_REVIEW: "Review required",
  INVALID_DATA: "Invalid data",
};

function money(amountMinor: number, currency = "INR") {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(amountMinor / 100);
}

function percent(value: number) {
  return new Intl.NumberFormat("en-IN", { style: "percent", maximumFractionDigits: 1 }).format(value);
}

export default function Dashboard() {
  const [runId, setRunId] = useState<string>();
  const [analytics, setAnalytics] = useState<Analytics>();
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);
  const [selected, setSelected] = useState<Evidence>();
  const [loadingSettlementId, setLoadingSettlementId] = useState<string>();
  const [filter, setFilter] = useState<OutcomeStatus | "ALL">("ALL");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [question, setQuestion] = useState("Why did this settlement receive this status?");
  const [answer, setAnswer] = useState<string>();

  const filtered = useMemo(
    () => outcomes.filter((item) => filter === "ALL" || item.status === filter),
    [filter, outcomes],
  );

  async function startDemo() {
    setBusy(true);
    setError(undefined);
    setAnswer(undefined);
    try {
      const created = await createDemoRun();
      const [summary, rows] = await Promise.all([
        getAnalytics(created.run_id),
        getOutcomes(created.run_id),
      ]);
      setRunId(created.run_id);
      setAnalytics(summary);
      setOutcomes(rows);
      const attention = rows.find((item) => item.status !== "RECONCILED") ?? rows[0];
      if (attention) setSelected(await getEvidence(created.run_id, attention.settlement_id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to start reconciliation");
    } finally {
      setBusy(false);
    }
  }

  async function openSettlement(settlementId: string) {
    if (!runId) return;
    if (selected?.subject.id === settlementId) {
      setSelected(undefined);
      setAnswer(undefined);
      return;
    }
    setAnswer(undefined);
    setError(undefined);
    setSelected(undefined);
    setLoadingSettlementId(settlementId);
    try {
      setSelected(await getEvidence(runId, settlementId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load settlement evidence");
    } finally {
      setLoadingSettlementId(undefined);
    }
  }

  async function ask(event: FormEvent) {
    event.preventDefault();
    if (!runId || !selected || !question.trim()) return;
    setBusy(true);
    try {
      const response = await askController(runId, selected.subject.id, question);
      const review = response.requires_human_review ? "Human review required" : "No review flag";
      const fallback = response.fallback_reason ? `\nFallback: ${response.fallback_reason}` : "";
      const attempted = response.attempted_provider
        ? `\nAttempted: ${response.attempted_provider} · ${response.attempted_model}`
        : "";
      setAnswer(`${response.answer}\n\nEvidence: ${response.evidence_ids.join(", ")}\nSource: ${response.provider} · ${response.model}\n${review}${attempted}${fallback}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Controller query failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <Image src="/brand/settlewise-mark.png" alt="" width={39} height={39} priority />
          </span>
          <div><strong>SETTLEWISE</strong><small>Finance control</small></div>
        </div>
        <div className="top-actions">
          <span className="system-state"><i /> Deterministic engine</span>
          <button className="primary" onClick={startDemo} disabled={busy}>
            {busy && !runId ? "Reconciling…" : runId ? "Run fresh dataset" : "Start demo reconciliation"}
          </button>
        </div>
      </header>

      <section className="shell">
        <aside className="sidebar" aria-label="Primary navigation">
          <nav>
            <a className="active" href="#overview"><span>⌁</span>Overview</a>
            <a href="#settlements"><span>⇄</span>Settlements</a>
            <a href="#exceptions"><span>!</span>Exception inbox</a>
            <a href="#evaluation"><span>✓</span>Evaluation</a>
            <a href="#controller"><span>✦</span>AI controller</a>
          </nav>
          <div className="sidebar-foot">
            <p>Ruleset</p><strong>{analytics?.ruleset_version ?? "RECON_RULESET_V1"}</strong>
            <p className="muted">Amounts are calculated in integer minor units.</p>
          </div>
        </aside>

        <div className="content">
          <section className="heading" id="overview">
            <div><p className="eyebrow">MONTH-END CONTROL ROOM</p><h1>Settlement overview</h1><p>Trace every rupee from captured payment to bank credit.</p></div>
            {runId && <div className="run-pill"><span>Run complete</span><code>{runId.slice(0, 18)}…</code></div>}
          </section>

          {error && <div className="error" role="alert">{error}</div>}

          {!analytics ? (
            <section className="empty-state">
              <div className="empty-icon"><Image src="/brand/settlewise-mark.png" alt="" width={96} height={96} priority /></div>
              <h2>Your evidence workspace is ready</h2>
              <p>Generate 500 merchant orders, reconcile every settlement, inject realistic exceptions, and score the result against hidden truth.</p>
              <button className="primary large" onClick={startDemo} disabled={busy}>Run the 500-order demo</button>
              <div className="assurances"><span>✓ No floating point</span><span>✓ Hidden ground truth</span><span>✓ AI cannot change results</span></div>
            </section>
          ) : (
            <>
              <section className="metrics" aria-label="Reconciliation summary">
                <article><div className="metric-label">Total processed <span>ⓘ</span></div><strong>{money(analytics.total_processed_minor, analytics.currency)}</strong><small>{analytics.settlement_count} settlement batches</small></article>
                <article><div className="metric-label">Proven reconciled <span className="up">↗</span></div><strong>{money(analytics.reconciled_minor, analytics.currency)}</strong><small className="good">{percent(analytics.reconciliation_rate)} coverage</small></article>
                <article className="attention"><div className="metric-label">Unresolved exposure</div><strong>{money(analytics.unresolved_minor, analytics.currency)}</strong><small>{analytics.unreconciled_count} mismatches · {analytics.review_count} reviews</small></article>
                <article><div className="metric-label">Auto-match precision</div><strong>{analytics.evaluation ? percent(analytics.evaluation.auto_reconcile_precision) : "Not scored"}</strong><small className="good">{analytics.evaluation?.false_reconciled ?? "—"} false reconciliations</small></article>
              </section>

              <section className="workspace" id="settlements">
                <div className="table-panel">
                  <div className="panel-head"><div><h2>Settlement workbench</h2><p>Expected, reported, and bank values remain separate.</p></div><select value={filter} onChange={(event) => setFilter(event.target.value as OutcomeStatus | "ALL")} aria-label="Filter settlements"><option value="ALL">All statuses</option>{Object.entries(STATUS_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></div>
                  <div className="table-wrap"><table><thead><tr><th>Settlement</th><th>Gross</th><th>Fees + tax</th><th>Expected net</th><th>Delta</th><th>Status</th><th>Confidence</th></tr></thead><tbody>{filtered.map((item) => {
                    const isSelected = selected?.subject.id === item.settlement_id;
                    const isLoading = loadingSettlementId === item.settlement_id;
                    return <Fragment key={item.settlement_id}>
                      <tr onClick={() => openSettlement(item.settlement_id)} className={isSelected ? "selected" : ""} aria-expanded={isSelected}>
                        <td><button className="text-button" aria-label={`${isSelected ? "Hide" : "Show"} details for ${item.settlement_id}`} aria-expanded={isSelected}>{item.settlement_id}<span className="row-chevron" aria-hidden="true">{isSelected ? "⌃" : "⌄"}</span></button></td>
                        <td>{money(item.calculation.payment_credits_minor)}</td>
                        <td className="negative">−{money(item.calculation.fees_minor + item.calculation.tax_minor)}</td>
                        <td>{money(item.calculation.expected_net_minor)}</td>
                        <td className={item.calculation.gateway_delta_minor ? "negative" : "muted"}>{money(item.calculation.gateway_delta_minor)}</td>
                        <td><span className={`status ${item.status.toLowerCase()}`}>{STATUS_LABELS[item.status]}</span></td>
                        <td><span className={`confidence ${item.confidence.toLowerCase()}`}>{item.confidence}</span></td>
                      </tr>
                      {isLoading && <tr className="inline-detail-row"><td colSpan={7}><div className="inline-detail-loading" role="status">Loading settlement evidence…</div></td></tr>}
                      {isSelected && <tr className="inline-detail-row"><td colSpan={7}><div className="inline-detail" aria-live="polite"><SettlementDetail evidence={selected} /></div></td></tr>}
                    </Fragment>;
                  })}</tbody></table></div>
                  <div className="table-foot">Showing {filtered.length} of {outcomes.length} settlements <span>Generated live from seed 20260825</span></div>
                </div>
              </section>

              <section className="controller" id="controller">
                <div className="controller-title"><span>✦</span><div><h2>Finance controller</h2><p>Read-only explanations grounded in the selected settlement’s evidence.</p></div><em>ADVISORY</em></div>
                <form onSubmit={ask}><input value={question} onChange={(event) => setQuestion(event.target.value)} aria-label="Question for finance controller" /><button className="primary" disabled={busy || !selected}>Investigate</button></form>
                {answer && <pre className="answer">{answer}</pre>}
              </section>

              <section className="scorecard" id="evaluation">
                <div className="scorecard-head">
                  <div>
                    <p className="eyebrow">GROUND-TRUTH EVALUATION</p>
                    <h2>The baseline, honestly measured.</h2>
                    <p>Deterministic scores calculated from hidden synthetic truth—not model opinion.</p>
                  </div>
                  <div className="scorecard-summary" aria-label="Evaluation summary">
                    <span><strong>{analytics.evaluation?.correct_outcomes ?? "—"}/{analytics.settlement_count}</strong> correct outcomes</span>
                    <span><strong>{analytics.evaluation?.false_reconciled ?? "—"}</strong> false reconciliations</span>
                  </div>
                </div>
                {analytics.evaluation ? (
                  <div className="evaluation-table-wrap">
                    <table className="evaluation-table">
                      <caption>Ground-truth reconciliation evaluation metrics</caption>
                      <thead><tr><th>Metric</th><th>Value</th><th>Interpretation</th></tr></thead>
                      <tbody>
                        {analytics.evaluation.scorecard.map((item) => (
                          <tr key={item.metric}>
                            <td><code>{item.metric}</code></td>
                            <td className="metric-value">{item.value.toFixed(3)}</td>
                            <td>
                              {item.target !== null && <span className="metric-target">target {item.target.toFixed(3)}</span>}
                              <span>{item.detail}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="scorecard-empty">This imported run has no evaluator-only ground truth, so no score is claimed.</div>
                )}
              </section>
            </>
          )}
        </div>
      </section>
    </main>
  );
}

function SettlementDetail({ evidence }: { evidence: Evidence }) {
  const calc = evidence.calculation;
  return <>
    <div className="detail-head"><div><p>Settlement evidence</p><h2>{evidence.subject.id}</h2></div><span className={`status ${evidence.outcome.status.toLowerCase()}`}>{STATUS_LABELS[evidence.outcome.status]}</span></div>
    <div className="equation"><div><span>Captured payments</span><strong>{money(calc.payment_credits_minor, calc.currency)}</strong></div><div><span>Refunds</span><strong>−{money(calc.refund_debits_minor, calc.currency)}</strong></div><div><span>Gateway fees</span><strong>−{money(calc.fees_minor, calc.currency)}</strong></div><div><span>GST on fees</span><strong>−{money(calc.tax_minor, calc.currency)}</strong></div>{calc.adjustment_net_minor !== 0 && <div><span>Adjustments</span><strong>{money(calc.adjustment_net_minor, calc.currency)}</strong></div>}<div className="total"><span>Expected net</span><strong>{money(calc.expected_net_minor, calc.currency)}</strong></div><div><span>Reported settlement</span><strong>{money(calc.reported_settlement_minor, calc.currency)}</strong></div><div className="delta"><span>Gateway difference</span><strong>{money(calc.gateway_delta_minor, calc.currency)}</strong></div></div>
    <div className="bank-proof"><p>Bank evidence</p><strong>{evidence.bank_match.bank_transaction_id ?? "No accepted bank credit"}</strong><span>{evidence.bank_match.reason}</span></div>
    {evidence.exceptions.length > 0 && <div className="exceptions" id="exceptions"><p>Exceptions</p>{evidence.exceptions.map((item) => <article key={`${item.code}-${item.message}`}><span>!</span><div><strong>{item.code.replaceAll("_", " ")}</strong><p>{item.message}</p><small>Evidence: {item.evidence_ids.join(", ")}</small></div></article>)}</div>}
    <div className="lineage"><span>{evidence.source_refs.length} ledger lines</span><span>{evidence.outcome.confidence} confidence</span><span>Rule evidence stored</span></div>
  </>;
}
