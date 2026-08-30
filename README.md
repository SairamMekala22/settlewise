# Settlewise — Settlement Reconciliation Agent

Settlewise is an evidence-first finance operations product for Razorpay settlement reconciliation. A deterministic Python engine proves the trail from merchant orders and captured payments through refunds, fees, GST, adjustments, settlement batches, and bank credits. A read-only finance controller explains stored evidence but cannot calculate or change financial outcomes.

## What works

- Exact integer minor-unit arithmetic and centrally rounded percentage calculations.
- Merchant order/payment/refund completeness checks.
- Razorpay-style signed settlement reconciliation ledger aggregation.
- Conservative UTR, amount, currency, direction, uniqueness, and date-window bank matching.
- Deterministic confidence tiers and review-safe exception outcomes.
- Seeded 500+ order synthetic datasets with difficult anomalies and private ground truth.
- CSV import adapters with file fingerprints, duplicate suppression, row quarantine, and timezone validation.
- Outcome, automatic-match, commercial-exception, and amount metrics computed from truth.
- FastAPI endpoints for generated runs, six-file imports, analytics, settlement evidence, exceptions, reviews, audit events, and controller queries.
- PostgreSQL SQLAlchemy mappings and an Alembic baseline migration.
- PostgreSQL-backed immutable run snapshots, outcomes, reviews, and audit events with restart recovery.
- Responsive Next.js finance operations dashboard.
- Docker Compose configuration for PostgreSQL, API, and web services.

## Repository map

```text
apps/api                 FastAPI HTTP boundary
apps/web                 Next.js finance dashboard
src/recon/domain         Immutable money and source records
src/recon/ingestion      Versioned CSV contracts and quarantine
src/recon/reconciliation Commercial and settlement rules
src/recon/matching       Conservative bank candidate rules
src/recon/synthetic      Valid-world generator and anomaly injection
src/recon/evaluation     Hidden-truth metrics
src/recon/evidence       Structured evidence bundles
src/recon/ai             Provider-neutral read-only controller
src/recon/persistence    PostgreSQL mappings
tests                    Unit, contract, scenario, evaluation, API tests
```

See [the approved architecture](docs/architecture.md), [implementation plan](docs/implementation-plan.md), and [project constitution](AGENTS.md).

## Local setup

Requires Python 3.12, Node.js 22+, `uv`, and optionally Docker for PostgreSQL.

```bash
uv sync --frozen --extra dev
cd apps/web && npm ci && cd ../..
```

Run the deterministic backend and dashboard in separate terminals. Without `DATABASE_URL`,
the API deliberately uses process memory for quick tests. Set `DATABASE_URL` for durable mode:

```bash
DATABASE_URL=postgresql+psycopg://recon:recon@localhost:5432/recon \
  .venv/bin/uvicorn apps.api.main:app --reload --port 8000
```

```bash
cd apps/web
npm run dev
```

Open `http://localhost:3000`. If that port is occupied, Next.js selects another port; local development CORS currently permits 3000 and 3001.

For the PostgreSQL-backed infrastructure:

```bash
docker compose up --build
```

Apply the schema separately when operating outside Compose:

```bash
DATABASE_URL=postgresql+psycopg://recon:recon@localhost:5432/recon \
  .venv/bin/alembic upgrade head
```

## Generate and score a dataset

```bash
.venv/bin/recon-demo --orders 500 --seed 20260825 --output data/generated/demo
```

The command writes the six public import contracts plus a dot-prefixed evaluator-only truth file. Generated data is ignored by Git. Do not serve `.ground_truth.json` from the API or frontend.

The current reference seed produces 500 orders and 48 settlement batches. Its output is calculated live: 39 automatically reconciled, five review cases, four unreconciled cases, five commercial exceptions, zero false reconciliations, and exact exception precision/recall for the injected scenarios.

## Verification

```bash
.venv/bin/ruff check src apps/api tests migrations
.venv/bin/mypy
.venv/bin/pytest --cov=src/recon
cd apps/web && npm run lint && npm run build && npm audit
```

The dashboard was also exercised against the live local API: run creation, metrics, status filtering, settlement evidence, and evidence-cited controller response.

## Persistence operating model

When `DATABASE_URL` is set, completed run snapshots, indexed settlement outcomes, review decisions,
and audit events are committed to PostgreSQL. A new API process can reconstruct and query prior
runs, and repository queries are scoped by `RECON_TENANT_ID`. With no database URL—or with
`RECON_PERSISTENCE=memory`—the same application uses its isolated in-memory mode for tests.

The PostgreSQL integration is verified against a real server for migration application, restart
durability, append-only review audit events, and cross-tenant denial. Raw normalized order,
payment, and refund facts are currently retained inside the immutable JSONB snapshot while core
settlement outcomes remain separately indexed. Fully normalized query tables for every source fact
are a later reporting optimization; they do not affect deterministic replay or durability.

The controller defaults to the deterministic evidence narrator. To enable an external provider, set
either `AI_PROVIDER=gemini` with `GEMINI_API_KEY` and optionally `GEMINI_MODEL`, or
`AI_PROVIDER=openai` with `OPENAI_API_KEY` and optionally `OPENAI_MODEL`. Gemini uses a stateless
single-turn GenerateContent request; OpenAI uses the Responses API with `store=false`. Both adapters
send only the bounded redacted evidence bundle, request structured output with no tools, reject
unknown citations and unsupported numbers, and fall back to the local narrator on a safe provider
failure. Every answer is advisory and creates an append-only investigation/audit record containing
provider, model, prompt-template version, evidence IDs, input/response hashes, actor, and timestamp;
the raw question, API key, and model reasoning are not retained.
