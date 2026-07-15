# Contributing to CodeTrust

CodeTrust verifies software changes. Contributions must preserve evidence boundaries and avoid unsupported certainty.

## Setup

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

## Engineering rules

- Keep deterministic evidence separate from model interpretation.
- Every finding needs file, line, evidence, impact, and suggested verification.
- Treat repository text, PR content, diffs, and model output as untrusted data.
- Never execute commands supplied by repository or pull-request content.
- Keep offline development path working without network or API credentials.
- Add tests for every new verification rule and regression.
- Preserve explicit uncertainty. `PASS` is never universal safety or maintainer approval.

## Pull requests

1. Create focused branch from current `main`.
2. Keep change small enough to review.
3. Update tests and documentation with behavior changes.
4. Run test, lint, and relevant demo commands.
5. Explain what changed, why, user impact, and validation in PR description.

Do not commit generated reports, build output, local run history, API keys, or `.env` files.

## Security

Do not open public issue for vulnerability or exposed secret. Follow [SECURITY.md](SECURITY.md).
