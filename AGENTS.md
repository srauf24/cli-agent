# AGENTS.md

## Mission
Build an ad-hoc analytics agent with a CLI (`ask` mode) for the mini data platform.

## Hard constraints
- Use one interaction mode: `ask` only.
- Read-only data execution only (no mutation statements).
- No assumptions about a fixed e-commerce schema should be hardcoded in core logic.
- The solution should infer structure from available warehouse and pipeline metadata.
- Keep implementation generic enough to swap the underlying mini data platform later.

## Functional expectations
- Natural language questions should be interpreted and answered using SQL over DuckDB.
- Must support examples like:
  - last quarter sales/revenue
  - products frequently bought together
  - sales anomalies
  - average customer lifetime value
- Return clear response that includes:
  - interpreted intent
  - SQL used
  - key result summary
  - assumptions / caveats

## Recommended stack
- Python CLI: `typer`
- Agent orchestration: Google ADK
- Data contracts: `pydantic`
- Execution: DuckDB connection via adapter abstraction
- Optional/optional formatting: concise terminal output + `--json` mode

## Layered design to follow
1. CLI layer
2. Agent/orchestration layer (intent -> plan -> validate -> execute)
3. Metadata + schema/context layer (duckdb information schema + dbt model hints)
4. Query generation layer (template-first, schema-aware fallback)
5. Validation/safety layer (read-only enforcement + allowlisted schemas)
6. Execution layer
7. Presenter layer

## Safety policy
- Block all non-SELECT statements.
- Enforce table/column allowlist from discovered context.
- Apply `LIMIT` guardrails and cap by config.
- Surface explicit, actionable errors for blocked SQL.

## Prompt handling policy
- Use deterministic intent classification first.
- Use templates for common patterns.
- Use constrained LLM fallback only when templates do not match.
- Preserve user intent but keep assumptions explicit in responses.

## Evidence pages usage
- `evidence/pages/*.md` can be used as optional query pattern examples only.
- Do not encode those page-level details as hardcoded business rules.

## README requirement
- Add/update README to document:
  - approach
  - architecture
  - tradeoffs
  - constraints and assumptions
  - what to build next with more time

## Time-boxing guidance (3-hour assessment)
- Prioritize shipping functional `ask` path before adding optional improvements.
- Keep changes incremental and scoped to backend-first behavior.
- Quality bar: correctness, safety, clarity, and generic metadata-driven behavior.

