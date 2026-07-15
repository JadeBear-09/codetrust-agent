# CodeTrust

[![CI](https://github.com/JadeBear-09/codetrust-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/JadeBear-09/codetrust-agent/actions/workflows/ci.yml)

CodeTrust is an evidence-first verification agent for software pull requests. It compares approved intent with a live GitHub diff, runs deterministic risk gates, and returns a traceable `BLOCK`, `NEEDS_REVIEW`, or `PASS` verdict.

CodeTrust does not merge, deploy, close, or execute pull-request code.

## Product workflow

```text
Approved intent + GitHub pull request
                  │
                  ▼
        Scope and impact mapping
                  │
                  ▼
       Deterministic risk gates
                  │
                  ▼
        Required model synthesis
                  │
                  ▼
 BLOCK / NEEDS_REVIEW / PASS + evidence
```

Every finding includes file, line, evidence, impact, and suggested verification. Model output can explain deterministic findings but cannot change verdict evidence or score.

## Run locally

Requirements:

- Python 3.11 or newer
- Authenticated [GitHub CLI](https://cli.github.com/) for private pull requests

```bash
git clone https://github.com/JadeBear-09/codetrust-agent.git
cd codetrust-agent
gh auth login
python3 start.py
```

Open <http://127.0.0.1:8787>. Paste a full GitHub pull-request URL and select **Verify pull request**. CodeTrust reads canonical intent from the pull request's base commit. Use the Advanced field only when the repository has no policy file.

`start.py` installs dependencies and starts the application. It does not load or execute sample data.

Useful commands:

```bash
python3 start.py --setup-only
python3 start.py --check
python3 start.py --no-open
```

## Gemini configuration

Copy environment template and add Gemini key:

```bash
cp .env.example .env
```

```dotenv
GEMINI_API_KEY=your_key
CODETRUST_MODEL=gemini-3.5-flash
CODETRUST_FALLBACK_MODEL=gemini-3.1-flash-lite
CODETRUST_MODEL_TIMEOUT_SECONDS=30
CODETRUST_MODEL_MAX_ATTEMPTS=3
CODETRUST_MODEL_DIFF_CHARS=400000
CODETRUST_POLICY_PATHS=.codetrust/policy.md,CODETRUST.md,.github/CODETRUST.md,docs/CODETRUST.md,PRODUCT.md,docs/PRODUCT.md
```

Secrets remain in backend environment. Browser receives only safe provider name, model name, and configured/unconfigured status.

Transient provider failures and timeouts use bounded retries. Gemini high-demand failures can use the configured stable fallback model. If every attempt fails, the request fails explicitly; CodeTrust never labels failed online synthesis as offline success. Reports record exact model, attempts, and duration.

OpenAI-compatible configuration is also supported:

```dotenv
OPENAI_API_KEY=your_key
CODETRUST_MODEL=gpt-5.4
```

The website requires a provider key. Explicit offline verification remains available through the CLI for local recovery and deterministic development.

## Approved intent

CodeTrust searches the pull request's exact base commit in this order:

1. `.codetrust/policy.md`
2. `CODETRUST.md`
3. `.github/CODETRUST.md`
4. `docs/CODETRUST.md`
5. `PRODUCT.md`
6. `docs/PRODUCT.md`

Override this order with `CODETRUST_POLICY_PATHS` for repositories using different conventions. Policy needs an **Outcome**, **In scope**, **Out of scope**, or **Acceptance criteria** heading. Policy path, base commit, and content hash are saved with the report. Pull-request title and description are never treated as approved intent.

## Verify from CLI

Live pull request:

```bash
uv run codetrust verify \
  --github-pr https://github.com/OWNER/REPOSITORY/pull/123 \
  --ticket path/to/approved-scope.md \
  --output-dir reports
```

Use repository policy from the PR base commit by omitting `--ticket`:

```bash
uv run codetrust verify --github-pr OWNER/REPOSITORY#123
```

Local diff:

```bash
uv run codetrust verify \
  --ticket path/to/approved-scope.md \
  --diff path/to/change.diff \
  --offline
```

Generated artifacts:

- `latest.html` — human decision view
- `latest.md` — review-ready report
- `latest.json` — hashed machine-readable result
- `adversarial-tests.md` — suggested verification cases

Exit code `1` means `BLOCK`, suitable for CI policy gates.

## API

- `GET /api/health` — service health
- `GET /api/config` — safe provider configuration status
- `POST /api/github` — verify live GitHub PR
- `POST /api/verify` — verify supplied intent and unified diff
- `GET /api/runs` — bounded local verification history
- `GET /api/runs/{run_id}` — stored report
- `GET /docs` — OpenAPI documentation

Example request:

```bash
curl http://127.0.0.1:8787/api/github \
  -H 'content-type: application/json' \
  -d '{
    "reference":"https://github.com/OWNER/REPOSITORY/pull/123",
    "intent":"## Out of scope\n- Billing policy changes",
    "model_mode":"required"
  }'
```

## Draft-PR verification workflow

Create a disposable draft PR, paste its URL into CodeTrust, inspect verdict, then close it in GitHub. CodeTrust intentionally never mutates PR state.

See [draft PR workflow](docs/DRAFT_PR_WORKFLOW.md) for exact commands.

## Beginner demo and recording guide

For exact public and private PR links, copy-paste intent, expected verdicts, recording order, and beginner instructions, see [beginner demo guide](docs/BEGINNER_DEMO_GUIDE.md).

## Offline fixture

Repository keeps one deterministic offline fixture for development and recovery:

```bash
make demo-offline
```

Website never loads fixture automatically.

## Safety boundary

- Ticket, diff, PR metadata, and model output are untrusted data.
- GitHub ingestion uses fixed `gh` command arguments without shell execution.
- Pull-request code is fetched as diff and never checked out or executed.
- API keys remain in ignored `.env` files.
- Stored run history contains reports, not raw ticket or diff content.
- `PASS` means configured gates found no blocker; it does not prove universal safety.

See [SECURITY.md](SECURITY.md) and [architecture](docs/ARCHITECTURE.md).

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

## License

MIT
