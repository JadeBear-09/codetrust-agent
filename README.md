# CodeTrust

> Coding agents create pull requests. CodeTrust decides which pull requests deserve human attention.

CodeTrust is an evidence-first verification agent for AI-generated software changes. It reconstructs intent, maps changed surfaces, runs targeted risk gates, challenges unsafe assumptions, and produces a traceable evidence pack. Humans receive unresolved decisions instead of a second generic code review.

Version 0.2 adds real GitHub pull-request ingestion, domain-impact mapping, adversarial test generation, executable failure proof, FastAPI endpoints, responsive dashboard, and non-root container packaging.

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
make proof
make serve
```

Open [http://127.0.0.1:8787](http://127.0.0.1:8787), select **Load demo**, then run verification.

Generated evidence remains available without server:

```bash
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

Verify a real GitHub pull request through authenticated GitHub CLI:

```bash
uv run codetrust verify \
  --github-pr OWNER/REPOSITORY#123 \
  --offline \
  --output-dir reports
```

Reproduce live before/after demonstration from this private repository:

```bash
# Intentionally risky candidate: expected BLOCK 94/100
uv run codetrust verify --github-pr JadeBear-09/codetrust-agent#2 --offline

# Remediated candidate: expected PASS 0/100
uv run codetrust verify --github-pr JadeBear-09/codetrust-agent#3 --offline
```

Artifacts:

- `latest.html`: visual decision dashboard for demo and judges.
- `latest.md`: review-ready evidence report.
- `latest.json`: integrity-hashed, machine-readable policy-gate output.
- `adversarial-tests.md`: generated proof templates for top findings.

Exit code is `1` for `BLOCK`, enabling CI enforcement.

## Architecture

```text
Ticket + diff / GitHub PR
    │
    ├─ Scope mapper ── changed files and line evidence
    ├─ Impact mapper ── business and technical blast radius
    ├─ Risk router ── selects relevant verification gates
    ├─ Challenge engine ── deterministic safety rules
    ├─ Test designer ── generates adversarial proof
    └─ Intent synthesizer ── model or offline fallback
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
- GitHub PR input requires authenticated `gh` CLI.
- Five deterministic rules cover demo-critical risks.
- CodeTrust does not merge or deploy.
- It does not execute commands found inside tickets or diffs.
- Generated tests are templates; one dedicated demo test is executable through `make proof`.
- `PASS` means no configured gate blocked the change; it never means “proven safe.”

See [Talent Hack strategy](docs/TALENT_HACK_STRATEGY.md), [measured demo results](docs/DEMO_RESULTS.md), [POC guide](docs/POC_GUIDE.md), [architecture](docs/ARCHITECTURE.md), [delivery plan](docs/PLAN.md), [research](docs/RESEARCH.md), [security](SECURITY.md), and [submission draft](docs/SUBMISSION.md).

## Container

```bash
docker build -t codetrust .
docker run --rm -p 8787:8787 codetrust
```

## Development

```bash
make test
make lint
```

## License

MIT
