# Verification walkthrough

## Live pull request

1. Start CodeTrust with `python3 start.py`.
2. Open <http://127.0.0.1:8787>.
3. Paste real draft pull-request URL.
4. Leave Advanced intent blank when base branch contains `CODETRUST.md`; otherwise paste separately approved intent and boundaries.
5. Confirm model status says configured. Website model synthesis is required.
6. Select **Verify pull request**.
7. Lead with verdict and score.
8. Review findings in risk order. Each finding must show file, line, evidence, impact, and suggested verification.
9. Review human decisions and scope alignment.
10. Open source PR from result, then close disposable PR in GitHub when finished.

## Offline recovery

```bash
make demo-offline
open reports/latest.html
```

Offline fixture proves deterministic pipeline without network or provider key. Website never loads it automatically.

## What not to claim

- Do not claim replacement of engineers.
- Do not claim universal safety.
- Do not call model-generated prose evidence.
- Do not claim proof for risks skipped by current gates.
- Do not say CodeTrust merges, deploys, closes, or executes pull-request code.
