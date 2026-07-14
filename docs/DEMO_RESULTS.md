# Measured demo results

Measured July 14, 2026 against private repository `JadeBear-09/codetrust-agent`.

## Real pull-request comparison

| Measure | Risky PR #2 | Remediated PR #3 |
|---|---:|---:|
| Verdict | `BLOCK` | `PASS` |
| Risk score | 94/100 | 0/100 |
| Findings | 4 | 0 |
| Critical impact area | Payments | Payments |
| Async impact | High | High |
| Database impact | High | High |

Risky PR findings:

1. `CT-PAY-001`: retry lacks idempotency evidence.
2. `CT-DB-001`: migration lacks rollback path.
3. `CT-ASYNC-001`: blocking HTTP call inside async path.
4. `CT-TEST-001`: failure-path coverage missing.

Remediated PR retains high-impact payment, async, database, and test surfaces but supplies configured safety evidence: async client, stable idempotency key, rollback statements, and adversarial test cases.

## Executable failure proof

Command:

```bash
make proof
```

Observed assertion:

```text
assert 2 == 1
```

Interpretation: provider committed first operation, client saw timeout, retry created second side effect. Harness confirms expected failure reason and exits successfully only when duplicate-payment proof appears.

## Quality gates

- 13 automated tests pass.
- Ruff lint passes.
- Ruff formatting check passes.
- Python source distribution and wheel build successfully.
- FastAPI health endpoint returns `{"status":"ok","service":"codetrust"}`.
- Browser workflow loads sample, runs verification, and renders findings plus generated tests.
- GitHub CI passes on upgrade branch and merged main.

## Environment limitation

Dockerfile was statically reviewed but not built locally because Docker client is unavailable in current workstation environment. Do not claim runtime Docker validation until image builds on another machine or CI.

