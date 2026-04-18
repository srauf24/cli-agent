# Mini Data Platform CLI Agent

I built a CLI agent that answers ad-hoc analytics questions over a DuckDB-based mini data platform.

### Example questions

- “How much in sales did we do last quarter?”
- “Which two products are most frequently bought together?”
- “Are there any anomalies with how we sell products?”
- “What’s our average customer lifetime value?”

## What I built

I implemented a read-only question-answering pipeline with one CLI entrypoint:

`mini-agent ask "<question>"`

Optional flags:

- `--json`: machine-friendly output
- `--limit`: result row cap (safety-enforced)

The request flow is:

1. Build execution context from warehouse metadata + dbt artifacts.
2. Classify user intent with deterministic rules + confidence.
3. Select a SQL template for the inferred intent.
4. Validate SQL for safety and schema compliance.
5. Execute with bounded rows/time and map errors to user-facing messages.
6. Return interpreted SQL, rows, and caveats in one stable payload.

## Why this architecture

I optimized for reliability and explainability because this is a take-home assessment with unknown evaluator prompts.

- **Metadata-first context**: I avoid hardcoded business assumptions and infer tables, columns, and likely layer roles from `information_schema` and dbt files.
- **Template-first SQL**: I generate deterministic SQL for high-value question types, which is safer and easier to test than free-form generation.
- **Explicit safety**: I enforce read-only SQL only, allowlist validation, and hard caps on query volume before execution.
- **Small adapter layer**: I isolate platform access behind an adapter interface so the core agent is not locked to DuckDB.
- **Structured responses**: I return both human-readable and machine-readable output with explicit assumptions/caveats.
- **Test-driven implementation**: I wrote each layer with unit tests first, then integration prompts that mirror real user questions.

## Trade-offs I accepted

- **Lower flexibility up front** in exchange for **higher predictability**.
- **Less semantic trickery** (no embeddings/vector search in this version) in exchange for a **clear audit trail and safer behavior**.
- **Simple CLI command surface** (single mode) in exchange for reduced complexity and easier evaluation.

## What I added

- Adapter abstraction (`duckdb`, `base`) with contract and behavior tests.
- Metadata extraction for schemas, tables, and role inference from naming/column signatures.
- Optional evidence page pattern scan as weak signal only (non-authoritative).
- Intent classifier for top archetypes: sales trend, co-purchase, anomalies, CLV, top-N, and fallback.
- SQL templating + strict SQL validation (read-only, allowlist, limit enforcement).
- Query executor with timing + bounded results + friendly error mapping.
- Presenter model for JSON and terminal outputs.
- CLI integration and deterministic fixtures for repeatable tests.
- Integration tests for all four assessment prompts.

## Runbook

```bash
uv sync
./setup.sh
uv run mini-agent ask "How much in sales did we do last quarter?"
uv run mini-agent ask "Which two products are most frequently bought together?" --json
uv run pytest tests/unit
uv run pytest tests/integration
```

## What I would do with more time

I would add a hybrid retrieval-augmented planner that uses embeddings as a secondary signal for ambiguous questions, while keeping metadata + templates as primary authority.
I would also improve cross-warehouse support, enrich dbt-semantic context from manifests/docs, and add ranking/observability for generated plans.
