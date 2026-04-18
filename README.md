# Mini Data Platform CLI Agent

## Purpose

This repository demonstrates a CLI analytics agent for ad-hoc platform questions over a DuckDB warehouse.

The agent answers prompts such as:

- How much in sales did we do this quarter?
- Which two products are most frequently bought together?
- Are there any anomalies with how we sell products?
- What's our average customer lifetime value?

It was built to show a practical, safe, and reusable pattern for turning natural language into reliable SQL answers with minimal setup.

## Core approach

We kept the implementation deterministic and metadata-driven.

1. Load context from warehouse metadata and dbt project structure.
2. Classify intent from the user question with confidence-aware rules.
3. Select a SQL template for the inferred intent.
4. Validate SQL against discovered schema and read-only constraints.
5. Execute through an adapter layer with bounded row/window limits.
6. Present a stable response payload for terminal and JSON.

This is implemented as a single command flow:

- `mini-agent ask "<question>"`.
- Optional `--json` output for machine consumption.
- Optional `--limit` for result cap.
- One execution mode only, as requested.

## Technical decisions and tradeoffs

1. Template-first SQL generation
1. It gives predictable behavior for high-value question archetypes.
2. It avoids brittle prompt-to-SQL errors under time constraints.
3. It is easier to harden, test, and explain.

1. Deterministic metadata discovery
1. Context is inferred from DuckDB `information_schema` and dbt model files.
1. This avoids hardcoding e-commerce-specific assumptions.
1. It supports reuse on other mini data platforms with similar artifacts.

1. Explicit safety layer
1. SQL validation blocks non-SELECT operations.
1. Table and column references are checked against discovered metadata.
1. Limits are enforced and capped to configured boundaries.
1. This keeps execution low risk for read-only usage.

1. Adapter abstraction
1. A small platform adapter interface isolates storage details.
1. The code remains portable toward other warehouses later.

1. Strict test-first process
1. Unit tests cover adapter, validator, metadata, templates, presenter, and CLI behavior.
1. Shared deterministic fixtures keep tests stable across runs.
1. Integration tests validate end-to-end prompt archetypes and output contracts.

## Why not full free-form SQL generation

In assessment time, deterministic templates provide the best reliability.

Tradeoff:

1. Strong correctness and explainability for known patterns.
2. Reduced flexibility for fully arbitrary natural language.

This is a deliberate baseline for safe production hardening and easy extensibility.

## Test coverage added

1. Unit suite
1. [tests/unit/test_bootstrap.py](/Users/sameerauf/.codex/worktrees/d609/mini-data-platform/tests/unit/test_bootstrap.py)
1. [tests/unit/test_config.py](/Users/sameerauf/.codex/worktrees/d609/mini-data-platform/tests/unit/test_config.py)
1. [tests/unit/test_types.py](/Users/sameerauf/.codex/worktrees/d609/mini-data-platform/tests/unit/test_types.py)
1. [tests/unit/test_adapter_base.py](/Users/sameerauf/.codex/worktrees/d609/mini-data-platform/tests/unit/test_adapter_base.py)
1. [tests/unit/test_adapter_duckdb.py](/Users/sameerauf/.codex/worktrees/d609/mini-data-platform/tests/unit/test_adapter_duckdb.py)
1. [tests/unit/test_metadata.py](/Users/sameerauf/.codex/worktrees/d609/mini-data-platform/tests/unit/test_metadata.py)
1. [tests/unit/test_patterns.py](/Users/sameerauf/.codex/worktrees/d609/mini-data-platform/tests/unit/test_patterns.py)
1. [tests/unit/test_intent.py](/Users/sameerauf/.codex/worktrees/d609/mini-data-platform/tests/unit/test_intent.py)
1. [tests/unit/test_templates.py](/Users/sameerauf/.codex/worktrees/d609/mini-data-platform/tests/unit/test_templates.py)
1. [tests/unit/test_sql_validator.py](/Users/sameerauf/.codex/worktrees/d609/mini-data-platform/tests/unit/test_sql_validator.py)
1. [tests/unit/test_executor.py](/Users/sameerauf/.codex/worktrees/d609/mini-data-platform/tests/unit/test_executor.py)
1. [tests/unit/test_agent_graph.py](/Users/sameerauf/.codex/worktrees/d609/mini-data-platform/tests/unit/test_agent_graph.py)
1. [tests/unit/test_presenter.py](/Users/sameerauf/.codex/worktrees/d609/mini-data-platform/tests/unit/test_presenter.py)
1. [tests/unit/test_cli.py](/Users/sameerauf/.codex/worktrees/d609/mini-data-platform/tests/unit/test_cli.py)
1. [tests/unit/test_fixtures.py](/Users/sameerauf/.codex/worktrees/d609/mini-data-platform/tests/unit/test_fixtures.py)
1. [tests/integration/test_prompts.py](/Users/sameerauf/.codex/worktrees/d609/mini-data-platform/tests/integration/test_prompts.py)

## Fixture strategy

1. Deterministic fixture SQL: [tests/fixtures/miniplatform_fixture.sql](/Users/sameerauf/.codex/worktrees/d609/mini-data-platform/tests/fixtures/miniplatform_fixture.sql)
1. Shared fixture helpers in `tests/conftest.py`
1. Tests validate idempotency and schema stability for long-running reliability.

## Runbook

1. Install dependencies
1. Run setup for base data platform
1. Ask a question with the CLI

Example:

```bash
uv sync
./setup.sh
uv run mini-agent ask "How much in sales did we do last quarter?"
```

JSON mode:

```bash
uv run mini-agent ask "Which two products are most frequently bought together?" --json
```

Run tests:

```bash
uv run pytest tests/unit
uv run pytest tests/integration
```

## What I would do with more time

1. I would add a retrieval layer powered by embeddings so intent classification can use semantically similar examples from evidence pages, prior successful SQL, and data docs.
1. I would build a hybrid planner: metadata-first templates first, and fallback to retrieval-augmented generation only when confidence is low.
1. I would add richer semantic context from dbt `manifest.json`, model docs, and glossary metadata to improve column/table intent mapping.
1. I would implement query-plan ranking and reranking for ambiguous prompts before execution.
1. I would add explainability output with provenance, retrieved context, and ranking reasons for each planned query.
1. I would add caching for platform context discovery, semantic search hits, and compiled plans to reduce repeated latency.
1. I would add richer telemetry, query history, and safety dashboards for operator observability.
