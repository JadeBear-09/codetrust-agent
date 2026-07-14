# CodeTrust

> Coding agents create pull requests. CodeTrust decides which pull requests deserve human attention.

CodeTrust is an evidence-first verification agent for AI-generated software changes. It reconstructs intent, maps changed surfaces, runs targeted risk gates, challenges unsafe assumptions, and produces a traceable evidence pack. Humans receive unresolved decisions instead of a second generic code review.

## Why this exists

Coding agents scale code output faster than senior engineers can scale review. A change can pass ordinary tests yet remain architecturally unsafe: blocking I/O in async code, duplicate payment retries, broken contracts, or rollback gaps. CodeTrust sits between code generation and production.

## Killer demo

An agent-generated payment reconciliation change looks reasonable and includes a passing success test. CodeTrust finds five risks:

1. Blocking network I/O inside an async path.
2. Retried payment action without idempotency proof.
3. Removed API field that can break older market adapters.
4. Database migration without rollback.
5. No failure-path test coverage.

Result: `BLOCK`, evidence for every claim, and one business decision for a human.

## Run in two minutes

Requirements: Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
make demo-offline
open reports/latest.html
```

AI-assisted intent reconstruction:

```bash
export OPENAI_API_KEY="..."
make demo
```

CodeTrust uses `gpt-5.4` by default through OpenAI Responses API. Override with `CODETRUST_MODEL`.

## Verify a real branch

```bash
uv run codetrust verify \
  --ticket path/to/ticket.md \
  --repo path/to/repository \
  --git-range main...HEAD \
  --output-dir reports
```

Artifacts:

- `latest.html`: visual decision dashboard for demo and judges.
- `latest.md`: review-ready evidence report.
- `latest.json`: integrity-hashed, machine-readable policy-gate output.

Exit code is `1` for `BLOCK`, enabling CI enforcement.

## Architecture

```text
Ticket + diff
    │
    ├─ Scope mapper ── changed files and line evidence
    ├─ Risk router  ── selects relevant verification gates
    ├─ Challenge engine ─ deterministic safety rules
    └─ Intent synthesizer ─ model or offline fallback
              │
              ▼
       Evidence + risk score
              │
              ▼
      BLOCK / NEEDS_REVIEW / PASS
              │
              ├─ HTML dashboard
              ├─ Markdown report
              └─ JSON policy output
```

Deterministic checks own factual evidence. Model owns intent synthesis and explanation. This boundary prevents eloquent model output from becoming unverified proof.

## Current POC boundary

- Input is a local unified diff or git range.
- Five deterministic rules cover demo-critical risks.
- CodeTrust does not merge or deploy.
- It does not execute commands found inside tickets or diffs.
- `PASS` means no configured gate blocked the change; it never means “proven safe.”

See [POC guide](docs/POC_GUIDE.md), [architecture](docs/ARCHITECTURE.md), [delivery plan](docs/PLAN.md), [research](docs/RESEARCH.md), and [submission draft](docs/SUBMISSION.md).

## Development

```bash
make test
make lint
```

## License

MIT
