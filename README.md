# Settlewise

**Evidence-first settlement reconciliation for Razorpay merchants.**

Settlewise helps finance teams answer one critical question:

> Can every settlement received in the bank be explained by the merchant's orders, captured payments, refunds, fees, taxes, adjustments, and Razorpay settlement records?

It connects the complete money trail—from merchant activity to the final bank credit—and produces a deterministic, auditable conclusion for every settlement. An optional Gemini-powered finance controller explains those conclusions using stored evidence, but it cannot calculate money, create facts, or change reconciliation results.

## The problem

Receiving a settlement does not prove that it is correct. Finance teams often need to compare data spread across several systems:

- merchant orders and expected collections;
- captured and failed payment attempts;
- full or partial refunds;
- Razorpay fees and GST;
- settlement reconciliation transaction lines;
- settlement batch totals and UTRs; and
- credits appearing in the merchant's bank account.

These sources use different schemas, identifiers, timestamps, and sign conventions. Missing UTRs, duplicate records, delayed refunds, incorrect amounts, ambiguous bank credits, and malformed rows make spreadsheet-based reconciliation slow and risky. A simple amount match can also create a false positive—making missing money appear reconciled.

The result is a month-end process that is difficult to reproduce, explain, review, and audit.

## How Settlewise solves it

Settlewise turns disconnected source records into a verifiable settlement evidence trail:

```text
Merchant orders
      │
      ▼
Payments and refunds ──► Razorpay signed settlement ledger
                                      │
                                      ▼
                            Expected settlement net
                                      │
                         compare with reported batch
                                      │
                                      ▼
                         Match to the bank credit
                                      │
                                      ▼
                 Outcome + exceptions + evidence + audit
                                      │
                                      ▼
                     Optional Gemini explanation
```

### 1. Ingest and normalize

Settlewise imports six versioned data contracts: merchant orders, Razorpay payments, refunds, settlements, settlement reconciliation ledger lines, and bank transactions. It validates every row, suppresses duplicates, quarantines malformed data, and retains source IDs, row numbers, file hashes, parser versions, and original values for lineage.

Provider-specific column names stop at the adapter boundary. The reconciliation domain operates on typed canonical records instead of depending on CSV spelling.

### 2. Reconstruct the settlement deterministically

Razorpay settlement reconciliation lines are treated as a signed ledger. Settlewise calculates the expected settlement using captured-payment credits, refund debits, fees, GST, and adjustments without double counting them.

Money is stored and calculated as signed integer minor units—not binary floating point. Currency is always explicit, exact equality is the default, and cross-currency values are never silently compared.

### 3. Match the settlement to the bank conservatively

Candidate bank credits are checked using:

- normalized UTR/reference;
- amount and currency;
- credit direction;
- valid date window; and
- candidate uniqueness.

Fuzzy text or amount alone cannot authorize an automatic match. When evidence is missing, tied, or conflicting, Settlewise fails closed and routes the case to human review instead of claiming a potentially false reconciliation.

### 4. Produce an evidence-backed outcome

Each settlement receives a deterministic status, confidence tier, calculation proof, bank-match explanation, exception list, and source references. The dashboard lets an operator expand a settlement inline and inspect:

- captured payments, refunds, fees, GST, and adjustments;
- expected net versus Razorpay's reported settlement;
- gateway and bank differences;
- accepted or rejected bank evidence;
- exception codes and reasons; and
- the rule version and source lineage behind the conclusion.

Completed reconciliation runs are immutable snapshots. Corrections create a new run; they do not rewrite historical evidence.

### 5. Explain findings safely with Gemini

The optional AI controller receives only a bounded, redacted evidence bundle produced by deterministic query tools. Gemini may summarize the evidence, explain an exception, and suggest investigation steps. It may not calculate amounts, select matches, manufacture identifiers, or mark a settlement as reconciled.

AI responses are advisory, validated against the supplied evidence, and displayed separately from deterministic findings. If Gemini is unavailable or returns an unsafe response, Settlewise falls back to a local evidence narrator so reconciliation remains fully usable.

## What the product delivers

- An end-to-end trail from merchant order to bank credit.
- Exact minor-unit settlement arithmetic with explicit currency.
- Order, payment, and refund completeness checks.
- Razorpay-style signed ledger aggregation without fee or tax double counting.
- Conservative one-to-one settlement-to-bank matching.
- Review-safe outcomes for missing, conflicting, or ambiguous evidence.
- Inline settlement evidence and exception inspection in the UI.
- Append-only human review, investigation, and audit records.
- Seeded synthetic datasets containing realistic anomalies and hidden truth.
- Honest evaluation of precision, recall, false reconciliations, exception quality, value coverage, and runtime.
- PostgreSQL persistence with tenant-scoped queries and restart recovery.
- A deterministic local mode that works without PostgreSQL or an AI account.

## Why the design is safe for financial reconciliation

Settlewise deliberately separates deterministic finance logic from AI assistance:

| Responsibility | Deterministic engine | Gemini controller |
|---|:---:|:---:|
| Parse and validate source records | Yes | No |
| Calculate fees, tax, net settlement, and differences | Yes | No |
| Generate and accept bank-match candidates | Yes | No |
| Assign status and confidence | Yes | No |
| Raise exceptions and require review | Yes | No |
| Explain stored evidence | Yes | Yes |
| Recommend evidence-backed investigation steps | No | Yes |
| Change facts or approve reconciliation | No | No |

This boundary ensures the product remains reproducible and auditable even when AI is disabled.

## Demo and evaluation

The built-in demo generates a reproducible 500-order dataset with normal settlements and deliberately injected anomalies such as missing references, amount mismatches, ambiguous matches, duplicate data, refund issues, and commercial completeness failures.

The reference seed (`20260825`) currently produces 48 settlement batches: 39 automatically reconciled, five review cases, and four unreconciled cases, with zero false automatic reconciliations. Evaluation is performed against evaluator-only hidden ground truth—not model opinion—and reports metrics including:

- automatic-reconciliation precision and recall;
- forced-match rate;
- link precision and recall across confidence tiers;
- exception recall, precision, and code accuracy;
- value coverage and unresolved exposure; and
- amount-weighted results and runtime.

Generate the same dataset from the command line:

```bash
.venv/bin/recon-demo --orders 500 --seed 20260825 --output data/generated/demo
```

The generated directory contains the six public import files and a dot-prefixed evaluator-only truth file. The truth file is intentionally excluded from product APIs and the frontend.

## Architecture

Settlewise is a modular monolith: one Python backend, one Next.js frontend, and one PostgreSQL database.

```text
apps/api                 FastAPI composition and HTTP boundary
apps/web                 Next.js finance operations dashboard
src/recon/domain         Money values, source records, and invariants
src/recon/ingestion      CSV contracts, validation, and quarantine
src/recon/reconciliation Commercial and settlement rules
src/recon/matching       Conservative bank candidate decisions
src/recon/evidence       Structured, source-linked evidence bundles
src/recon/ai             Gemini/OpenAI adapters and safe local fallback
src/recon/evaluation     Hidden-ground-truth metrics
src/recon/synthetic      Reproducible datasets and anomaly injection
src/recon/persistence    PostgreSQL mappings and repositories
tests                    Unit, contract, scenario, integration, and evaluation tests
```

The dependency direction is inward: HTTP, persistence, file, and AI adapters depend on the application and domain modules; the financial domain does not depend on FastAPI, SQLAlchemy, CSV parsers, or an AI SDK.

For the complete design, see [architecture](docs/architecture.md), [implementation plan](docs/implementation-plan.md), and [project constitution](AGENTS.md).

## Quick start

### Prerequisites

- Python 3.12
- Node.js 22 or newer
- [`uv`](https://docs.astral.sh/uv/)
- Docker, only if using PostgreSQL or the full Compose stack

### Install dependencies

```bash
uv sync --frozen --extra dev
cd apps/web
npm ci
cd ../..
cp .env.example .env
```

Keep real API keys in `.env`; never add them to `.env.example` or commit them.

### Option A: fast local demo

Run the backend in in-memory mode:

```bash
RECON_PERSISTENCE=memory DATABASE_URL= \
  .venv/bin/uvicorn apps.api.main:app --reload --port 8000
```

Run the dashboard in a second terminal:

```bash
cd apps/web
npm run dev
```

Open `http://localhost:3000`. If port 3000 is occupied, Next.js may select 3001; both origins are allowed by the local API.

Check backend health using only this URL:

```bash
curl http://localhost:8000/health
```

Expected shape:

```json
{
  "status": "ok",
  "ruleset": "RECON_RULESET_V1",
  "persistence": "memory",
  "ai_provider": "deterministic-evidence"
}
```

### Option B: full PostgreSQL stack

```bash
docker compose up --build
```

Compose starts PostgreSQL, applies the Alembic migrations, and serves the API and dashboard on ports 8000 and 3000.

When operating PostgreSQL outside Compose, apply the schema with:

```bash
DATABASE_URL=postgresql+psycopg://recon:recon@localhost:5432/recon \
  .venv/bin/alembic upgrade head
```

## Enable Gemini explanations

The financial workflow does not require Gemini. To enable the advisory controller, set the following values in `.env` or in the API process environment:

```dotenv
AI_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.6-flash
```

Then restart the API and confirm that `/health` reports `"ai_provider": "gemini"`. API keys, raw bank descriptions, customer PII, and complete imported files are not sent to the model.

Set `AI_PROVIDER=disabled` to use the safe local narrator. An OpenAI adapter is also available behind the same provider interface, but it is not required for the demo.

## API surface

FastAPI exposes interactive documentation at `http://localhost:8000/docs`.

Primary endpoints include:

- `GET /health` — service, ruleset, persistence, and AI-provider status.
- `POST /api/v1/reconciliation-runs/demo` — generate and reconcile a seeded dataset.
- `POST /api/v1/imports/reconcile` — validate and reconcile the six-file import contract.
- `GET /api/v1/reconciliation-runs` — list persisted runs.
- `GET /api/v1/reconciliation-runs/{run_id}/analytics` — run totals and evaluation.
- `GET /api/v1/reconciliation-runs/{run_id}/outcomes` — filterable settlement outcomes.
- `GET /api/v1/reconciliation-runs/{run_id}/settlements/{settlement_id}` — full evidence bundle.
- `GET /api/v1/reconciliation-runs/{run_id}/exceptions` — settlement and commercial exceptions.
- `POST /api/v1/reconciliation-runs/{run_id}/settlements/{settlement_id}/reviews` — append a human review.
- `GET /api/v1/audit-events` — query append-only audit events.
- `POST /api/v1/ai/queries` — request an evidence-grounded advisory explanation.

## Verification

Run the backend checks from the repository root:

```bash
.venv/bin/ruff check src apps/api tests migrations
.venv/bin/mypy
.venv/bin/pytest --cov=src/recon
```

Run the frontend checks separately:

```bash
cd apps/web
npm run lint
npm run build
npm audit
```

Integration tests do not require a live Razorpay or AI account. The deterministic application and AI fallback are tested independently of external provider availability.

## Scope

Settlewise V1 is a settlement reconciliation and investigation product. It does not move money, capture payments, issue refunds, post accounting journals, file GST returns, perform currency conversion, or autonomously resolve financial exceptions. Human reviewers remain responsible for operational decisions when the evidence is incomplete or conflicting.
