# CodeTrust

[![CI](https://github.com/JadeBear-09/codetrust-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/JadeBear-09/codetrust-agent/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Evidence-first repository understanding for pull requests.

CodeTrust reads a pull request and its exact base repository revision, reconstructs the repository baseline, explains how the change differs, and runs deterministic risk checks. It produces a cited scope comparison and evidence pack without checking out or executing pull-request code.

> CodeTrust verifies changes. It never merges, deploys, closes, or modifies pull requests.

## What it returns

- repository purpose inferred from base-repository evidence;
- concise summary of proposed PR behavior;
- material differences between baseline and change;
- cited base paths supporting each scope inference;
- relationship: `aligned`, `adjacent`, `divergent`, or `insufficient`;
- scope distance from `0` to `100`;
- deterministic findings with file, line, evidence, impact, and suggested verification;
- JSON, Markdown, HTML, and adversarial-test artifacts.

```text
Pull-request URL
      │
      ├── PR title/body/diff ───────────── untrusted change claim
      │
      └── exact base SHA
              ├── metadata and history
              ├── docs and manifests
              ├── changed/nearby source and tests
              └── repository structure
                       │
                       ▼
             Repository ↔ PR comparison
                       │
                       ▼
             Deterministic risk gates
                       │
                       ▼
                 Evidence pack
```

## Scope distance

Scope distance measures how far proposed behavior moves from evidence visible in base repository. Lower means closer.

| Distance | Relationship | Meaning |
|---:|---|---|
| `0–20` | `aligned` | Fits established repository purpose or behavior. |
| `21–50` | `adjacent` | Extends nearby behavior or ownership. |
| `51–100` | `divergent` | Expands or conflicts with established purpose or boundaries. |

Scope distance is not approval probability, code quality, safety, or maintainer intent. Low distance does not mean maintainers will accept a PR. Roadmap, governance, design preference, and unwritten product decisions may not exist in repository evidence.

Technical risk remains separate. A scope-aligned change can still `BLOCK` because implementation is unsafe; an adjacent change can have low deterministic risk.

## Quick start

Requirements:

- Python 3.11 or newer;
- [uv](https://docs.astral.sh/uv/);
- authenticated [GitHub CLI](https://cli.github.com/);
- Gemini or OpenAI API key for live repository inference.

```bash
git clone https://github.com/JadeBear-09/codetrust-agent.git
cd codetrust-agent
uv sync --extra dev
cp .env.example .env
gh auth login
uv run codetrust serve
```

Set one provider key in `.env`:

```dotenv
GEMINI_API_KEY=your_key
```

Open [http://127.0.0.1:8787](http://127.0.0.1:8787), paste a GitHub pull-request URL, then select **Verify pull request**.

Alternative launcher:

```bash
python3 start.py
```

## CLI

Verify live pull request:

```bash
uv run codetrust verify \
  --github-pr https://github.com/OWNER/REPOSITORY/pull/123 \
  --output-dir reports
```

Verify local scope and unified diff without model calls:

```bash
uv run codetrust verify \
  --ticket path/to/scope.md \
  --diff path/to/change.diff \
  --offline \
  --output-dir reports
```

Generated files:

- `latest.json` — machine-readable report and provenance;
- `latest.md` — review-ready evidence report;
- `latest.html` — visual report;
- `adversarial-tests.md` — suggested missing proof.

Exit code `0` means verification completed (`PASS` or `NEEDS_REVIEW`), `1` means `BLOCK`, and `2` means invalid input or verification failure. Exact verdict remains in report.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Service health. |
| `GET /api/config` | Safe provider configuration metadata. |
| `POST /api/github` | Verify live GitHub pull request. |
| `POST /api/verify` | Verify supplied scope and unified diff. |
| `GET /api/runs` | Read bounded local run history. |
| `GET /api/runs/{run_id}` | Read stored report. |
| `GET /docs` | OpenAPI documentation. |

```bash
curl http://127.0.0.1:8787/api/github \
  -H 'content-type: application/json' \
  -d '{
    "reference":"https://github.com/OWNER/REPOSITORY/pull/123",
    "model_mode":"required"
  }'
```

## Evidence and trust model

- Repository evidence comes from exact PR base SHA through bounded read-only GitHub API calls.
- PR title, description, and diff describe proposed behavior but never establish trusted baseline.
- Live verification sends bounded repository evidence and PR diff to configured model provider. Do not analyze sensitive private repositories unless provider processing is permitted.
- Model citations must match supplied base-repository paths.
- Model output cannot overwrite deterministic findings or risk score.
- Unsupported evidence routes scope to `insufficient` and verdict to `NEEDS_REVIEW`.
- Low-risk warnings remain visible without automatically forcing review.
- Evidence hash detects report-input mutation; it does not prove authorship.

See [architecture](docs/ARCHITECTURE.md) and [security model](SECURITY.md).

## Offline proof

Repository includes one deterministic unsafe-payment fixture for development:

```bash
make demo-offline
make proof
```

Fixture never loads in website and never executes code from external pull requests.

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv build
```

Contribution rules: [CONTRIBUTING.md](CONTRIBUTING.md). Disposable PR workflow: [docs/DRAFT_PR_WORKFLOW.md](docs/DRAFT_PR_WORKFLOW.md).

## Limitations

- Current deterministic rules cover selected risk patterns, not full semantic correctness.
- Scope inference depends on evidence available in repository and may miss unwritten decisions.
- Current release does not redact secrets before model calls. Use only repositories and diffs safe to share with configured provider.
- Dashboard is local-first and has no authentication; keep it bound to `127.0.0.1` unless protected by trusted gateway.
- Live verification requires provider and GitHub availability.
- `PASS` means no configured review-level blocker was found. It never means universally safe or maintainer-approved.

## License

[MIT](LICENSE)
