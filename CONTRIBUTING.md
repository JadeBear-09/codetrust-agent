# Contributing

Contributions must keep prototype safe, repeatable, and honest.

## Before change

1. Read `README.md`, `architecture.md`, and `docs/threat-model.md`.
2. Never add real subscriber data, operator telemetry, credentials, or controller endpoints.
3. Put tunable scenario, twin, and policy values in config instead of UI or verdict branches.
4. Preserve truth labels: real event context, simulated RAN/controller, executed safety logic.

## Code guidance

- Add comments for authority boundaries, invariants, non-obvious safety behavior, or intentional compromises.
- Do not comment obvious syntax.
- Keep Pydantic inputs `extra="forbid"` at trust boundaries.
- Keep write operations typed, bounded, idempotent, verified, and reversible.
- Never let model or scenario name directly select `PASS`, `BLOCK`, or `ROLLBACK`.
- Do not log secrets, authorization headers, raw API URLs containing keys, or raw prompts.
- Keep frontend focused on presenter actions; put deep evidence behind progressive disclosure.

## Required checks

```bash
cd backend
uv sync --extra dev --locked
uv run ruff check src tests
uv run mypy src
uv run pytest

cd ..
npm ci
npm run lint
npm test
```

Add test for every new fault, policy branch, controller mutation, rollback condition, and public API shape.

## Pull request

Describe:

- problem and user-visible outcome;
- safety boundary affected;
- configuration/schema changes;
- tests and manual demo path;
- honest limitations.

Do not combine unrelated dependency, formatting, and product changes without reason.
