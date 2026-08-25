# Settlement Reconciliation Agent — Implementation Plan

Status: Proposed; blocked until architecture approval  
Planning principle: each phase has an exit gate, and later polish cannot bypass correctness gates.

## Phase 0 — Repository foundation and contracts

Deliverables:

- Initialize repository/tooling only after approval: Python and web workspaces, lint/type/test commands, Docker Compose, PostgreSQL, CI, `.env.example`.
- Create ADR template, contribution guide, data-contract documentation, migration baseline, and OpenAPI conventions.
- Encode official-shaped golden fixtures for Razorpay orders, payments, refunds, settlement entities, combined settlement recon lines, and one bank format.
- Freeze V1 sign conventions, source status mappings, currency metadata, and timestamp rules after fixture review.

Exit gate: clean setup from README, strict checks run, migration round-trip succeeds, and owner accepts the data contracts. No UI work yet.

## Phase 1 — Financial domain kernel

Deliverables:

- Money/currency value objects, rate rounding service, source references, signed ledger effect, rule result, confidence tier, and outcome dimensions.
- Pure settlement aggregation and delta calculations.
- Exception enums and audit/evidence schemas.
- Unit and property tests for conservation, sign, rounding, currency isolation, order independence, and overflow boundaries.

Exit gate: 100% passing golden arithmetic/invariant suite; no floats in money paths.

## Phase 2 — Synthetic world and private ground truth

Deliverables:

- Seeded valid-world generator for orders, attempts, refunds, adjustments, ledger lines, settlements, and bank activity.
- Independent public-source renderers and private truth model.
- Composable anomaly mutations with preconditions and causal expected outcomes.
- Small deterministic regression seeds and a configurable 500+ order demo profile.

Exit gate: public records conserve money before mutation; same seed/config is byte-reproducible or semantically hash-identical; truth cannot be reached through product paths.

## Phase 3 — Import, validation, normalization, and lineage

Deliverables:

- Import session/row persistence and versioned adapters for generated contracts.
- Validation, quarantine, date/reference normalization, payload fingerprints, conflict detection, idempotency, and spreadsheet-injection defenses.
- Import summaries and contract/integration tests.

Exit gate: all generated sources round-trip into canonical facts; repeat imports do not amplify facts; malformed rows are safely quarantined with complete lineage.

## Phase 4 — Commercial and settlement reconciliation engine

Deliverables:

- Exact order/payment/refund/ledger links.
- Payment-attempt/commercial completeness rules.
- Settlement ledger aggregation, later-refund attribution, holds/unsettled handling, source cross-checks, and persisted calculation proofs.
- Immutable run orchestration with ruleset/config snapshots.

Exit gate: scenario suite proves normal, many-to-one, partial/multiple/later refunds, fee/tax, adjustment, and missing/conflicting record cases; exact calculation accuracy is 100% on valid truth.

## Phase 5 — Bank matching, confidence, and exceptions

Deliverables:

- UTR/reference normalization, working-day window policy, candidate generation/features, exclusivity constraints, deterministic tiers, and ambiguity handling.
- Complete exception taxonomy, severity/materiality, primary-cause linking, review lifecycle, and status projection.
- Candidate/rule traces persisted for every decision.

Exit gate: adversarial equal-amount, duplicate, missing-UTR, wrong-UTR, delayed, and reused-credit tests yield zero false automatic matches.

## Phase 6 — Evaluation framework

Deliverables:

- Link/outcome/exception confusion matrices; precision, recall, review rate, amount-weighted coverage, false `RECONCILED`, runtime, and causal attribution.
- Multi-seed evaluation runner, report persistence, metric gates, and regression baselines.
- Clear separation between product queries and hidden truth.

Exit gate: all metrics are computed from decisions/truth, no hardcoded values, release gates execute automatically, and failures identify exact cases.

## Phase 7 — Backend API and audit trail

Deliverables:

- FastAPI import, run, outcome, settlement detail, exception/review, evidence, audit, analytics, synthetic, and evaluation endpoints.
- Cursor pagination, typed errors, tenant scope, request limits, idempotency keys, structured safe logging, and OpenAPI contract.
- Append-only audit events and evidence bundle generation.

Exit gate: integration and authorization tests pass; every API conclusion resolves to source evidence and versioned rules.

## Phase 8 — Finance operations dashboard

Deliverables:

- Run/import health, overview, settlement workbench, detailed money trail/equation, exception inbox/review, evidence/audit, and evaluation pages.
- Generated API types, correct minor-unit display, accessible states, filters, and loading/error/empty states.
- Primary e2e flow from import to review.

Exit gate: UI never recomputes financial conclusions, all displayed totals match API fixtures, and the end-to-end flow works without AI configured.

## Phase 9 — AI finance controller

Deliverables:

- Provider-neutral interface, mock provider, allow-listed read tools, redacted evidence projection, structured response schema, citation validator, and investigation audit.
- Curated finance questions from the brief and provider-outage/insufficient-evidence behavior.
- Prompt-injection and unsupported-claim tests.

Exit gate: every answer's financial claims/citations resolve exactly to tool evidence; the AI has no write path and cannot access hidden truth/raw sensitive fields.

## Phase 10 — Hardening and demo preparation

Deliverables:

- Performance profiling against target data, indexes/query plans, upload and tenant security review, dependency scanning, backup/reset instructions for demo data, accessibility pass.
- Fixed demo seed plus two backup seeds, optional mock/cached provider mode clearly labelled, rehearsal script, and automated preflight.
- Final multi-seed evaluation report generated by the application.

Exit gate: clean-machine rehearsal completes in 3–5 minutes, external AI failure has a graceful fallback, adversarial metric gates pass, and no result is fabricated.

## Suggested milestone cuts

- **M1 — Truthful engine:** Phases 0–4. CLI/test output can prove a settlement end to end.
- **M2 — Measurable controller core:** Phases 5–7. Safe matching, exceptions, evaluation, API, and audit are complete.
- **M3 — Demonstrable product:** Phases 8–10. Finance UX and grounded AI are added without changing arithmetic.

If schedule contracts, cut live integrations, advanced review workflow, multiple bank adapters, and visual polish first. Do not cut the ledger fixtures, hidden truth, conservative matching, evidence, or false-positive tests.

## Approval checkpoint

Implementation remains intentionally stopped. After reviewing `docs/architecture.md`, the owner should either:

- explicitly approve the architecture and defaults;
- approve with named changes; or
- answer the open questions that materially change the design.

