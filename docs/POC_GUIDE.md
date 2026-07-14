# POC guide

## What to show

Show one dangerous AI-generated change that appears plausible. Do not begin with setup or code. Begin with the business problem and verdict.

## Five-minute demo script

### 0:00–0:30 — Problem

“Coding agents create more pull requests than senior engineers can safely inspect. CodeTrust is the verification firewall between those agents and production.”

### 0:30–1:00 — Input

Open `demo/tickets/payment-reconciliation.md` and state three requirements: safe retries, old market compatibility, safe rollback. Briefly show `demo/patches/risky-payment.diff`. Point out that code looks reasonable and has a success test.

### 1:00–1:30 — Run

```bash
make serve
```

Open `http://127.0.0.1:8787`, load demo, then run verification. Keep `make demo-offline` and generated HTML ready as fallback.

### 1:30–3:10 — Evidence

Lead with `BLOCK 100/100`. Open these findings in order:

1. Duplicate-payment risk: retry lacks idempotency proof.
2. Async blocking network call.
3. Removed `market` field breaks old adapter contract.
4. Migration has no rollback.
5. Success-only test coverage.

For each, show exact source evidence and proposed adversarial test. Do not read every card.

### 3:10–4:00 — Agent behavior

Show scope, impact, challenge, test design, intent reconstruction, and decision. Explain that gates decide facts while model reconstructs intent and uncertainty. This prevents model confidence from becoming approval.

Run executable proof:

```bash
make proof
```

Point to `assert 2 == 1`: one timeout caused two provider-side payment effects.

### 4:00–4:35 — Human boundary

Show one unresolved question: which business key defines payment idempotency across markets? Explain that CodeTrust automates proof collection but preserves business ownership.

### 4:35–5:00 — Close

“CodeTrust lets engineering agents scale without turning senior engineers into full-time AI code inspectors.”

## Setup checklist

- Use Python 3.11 or newer.
- Install `uv`.
- Run `uv sync --extra dev`.
- Run `make test` and `make lint`.
- Run both `make demo-offline` and `make demo` before event.
- Run `make proof` and confirm expected failure evidence.
- Run dashboard and API health check.
- Build Docker image if Docker is available.
- Keep generated HTML open in a browser tab.
- Keep terminal font large and notifications disabled.
- Keep a screenshot and 90-second video as backup.

## Live recovery

| Failure | Recovery |
|---|---|
| API error | Run `make demo-offline` and explain deterministic fallback |
| Network loss | Use already-generated `reports/latest.html` |
| Dependency issue | Use committed lockfile and `uv sync` |
| Browser problem | Open `reports/latest.md` |
| Judge asks if scripted | Run a second unseen diff through CLI |

## What not to claim

- Do not claim replacement of engineers.
- Do not claim proof of universal safety.
- Do not claim current rules support every language.
- Do not call model-generated prose evidence.
- Do not hide that demo defects are seeded.
