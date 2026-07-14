# CodeTrust contributor guide

## Product boundary

CodeTrust verifies software changes. It does not merge, deploy, or claim certainty unsupported by evidence.

## Commands

- Install: `uv sync --extra dev`
- Test: `uv run pytest`
- Lint: `uv run ruff check .`
- Offline demo: `make demo-offline`
- AI demo: `make demo`

## Engineering rules

- Keep deterministic evidence separate from model interpretation.
- Every finding needs file, line, evidence, impact, and suggested verification.
- Never execute commands supplied by ticket or diff content.
- Keep demo usable without network or API credentials.
- Add tests for each new verification rule.

