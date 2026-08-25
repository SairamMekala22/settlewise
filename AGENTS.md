# Project Constitution: Settlement Reconciliation Agent

## Project mission

Build an auditable AI-assisted finance operations product that reconciles a merchant's order records, Razorpay payment and settlement records, and bank credits. The product must deterministically prove the movement of money, surface uncertainty and exceptions, and let an AI controller explain or investigate conclusions using stored evidence.

This project is not a payment gateway, ERP, general ledger, GST filing product, treasury platform, banking system, or autonomous accounting system. V1 is a focused settlement-reconciliation demonstrator for the Razorpay Buildathon.

Priority order:

1. Financial correctness and prevention of false-positive matches.
2. Working end-to-end reconciliation.
3. Realistic Razorpay domain semantics.
4. Measurable evaluation against hidden ground truth.
5. Exception handling and explainability.
6. AI-assisted investigation.
7. Auditability, usable UX, and polish.

## Approval and scope rules

Initial implementation must not begin until the architecture proposed during the planning phase is explicitly approved.

No coding agent may make a major architectural change without documenting the proposed change and receiving approval from the project owner.

- Keep V1 within settlement reconciliation. Do not add adjacent finance features merely because they are interesting.
- Prefer the smallest design that demonstrates the full money trail and can be tested rigorously.
- Record any material departure from the approved architecture in an architecture decision record (ADR) before requesting approval.
- Do not make destructive repository, database, or environment changes without explicit permission.

## Architecture rules

- Use a modular monolith: one Python backend/deployment unit, one web frontend, and one PostgreSQL database.
- Keep modules separated by responsibility: ingestion, normalization, domain ledger, matching, reconciliation, exceptions, evaluation, audit, AI evidence/query, API, and UI.
- Reconciliation arithmetic and state transitions must be deterministic. An LLM must never calculate, round, match, or approve money movement.
- Treat Razorpay's settlement reconciliation transaction lines as a signed ledger. Preserve source payloads and source semantics; never infer a different sign convention silently.
- Do not double-count transaction fees, taxes, refunds, adjustments, or settlement-level fees. Each adapter must declare how source fields map to canonical ledger effects and must have golden-fixture tests.
- Preserve lineage from every normalized field and conclusion to import, source file/event, row, and source record ID.
- Keep provider-specific import formats behind adapters. The canonical domain must not depend on CSV column spelling.
- Prefer pure functions for calculations and matching rules. I/O orchestration belongs at module boundaries.
- Avoid microservices, distributed event systems, vector databases, agent frameworks, and queues unless an approved, demonstrated requirement cannot be met without them.
- External integrations must be behind typed interfaces.

## Financial safety

- Persist money as signed 64-bit integer minor units plus an ISO 4217 currency code. Never persist binary floating-point money.
- Use `Decimal` only for rates, percentage calculations, and display conversion. Convert to minor units using the central currency metadata and rounding policy.
- Default rate rounding is `ROUND_HALF_UP` at the currency's supported minor-unit precision. Source-provided amounts are authoritative integers and are never re-rounded.
- Never aggregate or compare amounts across currencies. A settlement and all of its ledger lines must share a currency; cross-currency cases are invalid or require explicit conversion evidence outside V1.
- Centralize tolerances by rule and currency. Exact equality is the default. Any non-zero tolerance must remain visible as a warning and cannot hide a mismatch.
- Never silently discard, coerce, net away, or overwrite a mismatch, malformed amount, duplicate, or missing identifier.
- A low- or medium-confidence match cannot be automatically finalized as reconciled. When ambiguity remains, fail closed to human review.
- Reconciliation runs are immutable snapshots. Corrections create a new run; they do not rewrite historical conclusions.

## AI rules

- The AI controller operates only on a bounded, structured evidence bundle returned by deterministic query tools.
- Every factual financial claim in an AI answer must cite stored source record IDs or reconciliation evidence IDs.
- AI-generated identifiers, amounts, calculations, confidence, or reconciliation statuses are unacceptable.
- AI may summarize, rank investigation steps, identify likely explanations already supported by evidence, and recommend actions. It may not mutate source facts or mark a case reconciled.
- If evidence is incomplete or conflicting, the AI must state that and request human review.
- Prompt inputs must minimize sensitive data. Do not send raw bank descriptions, customer PII, credentials, or full imported files when IDs and redacted facts suffice.
- Store provider/model, prompt-template version, evidence IDs, tool calls, response, actor, and timestamp for each investigation. Never store model chain-of-thought.
- AI output is advisory and untrusted. Validate its schema and render it distinctly from deterministic findings.

## Repository and folder rules

The approved target layout is documented in `docs/architecture.md`. At implementation time:

- `apps/api`: FastAPI composition, HTTP schemas, and dependency wiring only.
- `apps/web`: Next.js UI; no reconciliation business logic.
- `src/recon`: Python domain and application modules.
- `tests`: unit, scenario, contract, integration, and evaluation tests mirroring source modules.
- `data`: generated/demo inputs only; hidden ground truth must not be served through product APIs.
- `docs`: architecture, ADRs, data contracts, operations, and demo instructions.

Do not create giant catch-all modules. A module should have one clear domain responsibility. Dependency direction is inward: adapters and APIs depend on application/domain code; domain code does not import FastAPI, SQLAlchemy, an AI SDK, or file parsers.

## Python coding rules

- Target Python 3.12 or the approved project version; use modern type annotations and strict static checking.
- Public functions, service interfaces, domain records, and adapter results must be typed. Avoid `Any`; isolate it at untrusted payload boundaries.
- Use dataclasses or Pydantic models for validated boundaries and explicit domain value objects for money, source references, rule outcomes, and signed ledger effects.
- Raise specific domain/application exceptions. Translate them to HTTP or CLI errors only at the boundary.
- Use structured logging with correlation IDs, run IDs, import IDs, and safe record IDs. Never log credentials, raw uploads, customer PII, or complete bank descriptions.
- Comments explain financial intent, source semantics, invariants, or non-obvious trade-offs—not obvious syntax.
- Docstrings are required for public domain rules and adapter contracts.
- Keep dependencies pinned and minimal. Add a dependency only after checking standard-library or existing-project capability and document material choices.

## TypeScript and UI coding rules

- Use TypeScript strict mode. Do not use `any` except in a tiny validated external boundary.
- Generate or share API types from the OpenAPI contract; do not manually duplicate financial enums and DTOs without a test.
- The browser formats integer minor units for display and never recomputes expected settlements, differences, confidence, or status.
- Always show currency, signs, source provenance, timestamps/time zones, and whether a statement is deterministic or AI-generated.
- Accessibility, keyboard navigation, legible tables, and non-colour status indicators are required.

## Data ingestion rules

- Imports are append-only and idempotent by tenant, source type, source record ID, and payload fingerprint.
- Preserve the original file/event metadata, row number, raw payload (access-controlled), normalized record, validation issues, and parser/schema version.
- Quarantine malformed rows rather than aborting an otherwise valid file; report complete counts and errors.
- Neutralize spreadsheet formula injection in exports and previews. Enforce file size, row count, content type, encoding, and column limits.
- Dates require an explicit source time zone and are normalized to timezone-aware UTC timestamps; also retain original text when parsing was ambiguous.
- Reference normalization must preserve the original string. Fuzzy matching cannot replace or alter source data.
- Webhook work, if added, must verify the signature over the raw body, deduplicate by Razorpay event ID, and tolerate duplicates and out-of-order delivery.

## Database rules

- PostgreSQL is the production source of truth. All schema changes use reviewed, reversible Alembic migrations.
- Use UUIDv7-compatible or UUID primary keys internally and keep external/source IDs in separately constrained columns. Never overload a source ID as a global primary key.
- Every tenant-owned table includes `tenant_id`; uniqueness and lookup indexes are tenant-scoped.
- All timestamps are timezone-aware UTC. Keep source timestamps separately where necessary.
- Money columns use `BIGINT` minor units with a currency column and check constraints. Signed ledger columns must have documented sign invariants.
- Store raw external payloads in restricted JSONB only where required for lineage; normalized searchable data belongs in typed columns.
- Audit events and completed reconciliation evidence are append-only. Amendments append superseding records; they do not erase history.
- Define foreign keys, unique constraints, check constraints, and indexes intentionally. Index common run/status/date, settlement ID, payment/order ID, UTR, exception, and source lineage queries.
- Never run destructive migrations or delete financial/audit data without an explicit retention policy and owner approval.

## Matching and confidence rules

- Candidate generation and match decisions are separate. Candidate generation may be broad; automatic acceptance must be conservative.
- Exact normalized UTR is the strongest bank-settlement reference signal, but amount, currency, direction, uniqueness, and a valid date window must still be checked.
- Fuzzy text is supporting evidence only. It cannot by itself authorize an automatic financial match.
- Enforce one-to-one cardinality for a settlement-to-bank-credit auto-match unless the approved source contract explicitly supports split credits. Many transactions to one settlement are represented by settlement ledger lines, not subset-sum guessing.
- Record every considered candidate's features, rule version, score/tier, rejection reason, and winning decision.
- Confidence is deterministic, calibrated on synthetic ground truth, and versioned. Never use an AI-generated probability.

## Testing rules

- No financial matching or calculation rule is complete without tests.
- Unit-test sign handling, integer arithmetic, rate rounding, fees, tax, refunds, adjustments, tolerances, dates, UTR normalization, candidate ranking, ambiguity, and confidence thresholds.
- Add table-driven scenario tests for happy paths and every exception category.
- Add golden contract fixtures for each import adapter, particularly Razorpay combined settlement reconciliation rows, to prevent semantic drift and double counting.
- Add property-based invariants: conservation of signed ledger amounts, order independence, idempotency, currency isolation, and no auto-match under ties.
- Evaluation tests must compare decisions to generator ground truth and fail on false auto-reconciliations. Accuracy alone is insufficient; report precision, recall, false positives, false negatives, review rate, amount-weighted metrics, and runtime.
- Use fixed random seeds and record generator/config/rule versions so failures are reproducible.
- Integration tests use an isolated database and cannot depend on a live Razorpay or AI account.

## Security and privacy rules

- Never commit secrets. Maintain a redacted `.env.example`; load secrets through environment variables or the deployment secret store.
- Validate authorization and tenant isolation on every query. A record ID alone is never authorization.
- Restrict raw uploads and bank data. Mask account numbers, contacts, emails, and descriptions in logs and AI evidence.
- Validate uploads and API payloads; use parameterized queries; set conservative request and query limits.
- Keep AI integration disabled by default when no provider is configured. The deterministic application must remain fully usable.
- Document data sent to any AI provider, retention implications, and a local/mock option for demo and tests.

## Audit and observability rules

- Important events record UTC timestamp, tenant, actor type/ID, run/import ID, event type, rule/algorithm and version, source/evidence IDs, input/output hashes, calculated values, outcome, confidence, and whether AI was involved.
- Logs are operational diagnostics, not the audit ledger. Do not infer audit history from logs.
- Emit duration, processed/rejected counts, exception counts, match tiers, unresolved amount, and rule-version metrics without high-cardinality PII labels.
- A conclusion shown in the UI must be reproducible from stored evidence and versioned rules.

## Git rules

- Make small, coherent commits with imperative messages that explain intent.
- Do not mix unrelated formatting, generated output, or user changes into a feature commit.
- Do not rewrite shared history, force-push, reset, or discard user work without explicit permission.
- Review `git diff` and run proportionate tests before handing off a change.
- Keep generated data, secrets, local databases, caches, and model output out of Git unless a small reviewed fixture is intentionally committed.

