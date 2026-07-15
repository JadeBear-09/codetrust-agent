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
        Optional model synthesis
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

Open <http://127.0.0.1:8787>. Paste a full GitHub pull-request URL, optionally provide approved intent, and select **Verify pull request**.

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
```

Secrets remain in backend environment. Browser receives only safe provider name, model name, and configured/unconfigured status.

Transient provider failures are retried. Gemini high-demand failures fall back to configured stable fallback model; report records exact model used.

OpenAI-compatible configuration is also supported:

```dotenv
OPENAI_API_KEY=your_key
CODETRUST_MODEL=gpt-5.4
```

Without a provider key, deterministic verification still works in offline mode.

## Verify from CLI

Live pull request:

```bash
uv run codetrust verify \
  --github-pr https://github.com/OWNER/REPOSITORY/pull/123 \
  --ticket path/to/approved-scope.md \
  --output-dir reports
```

Use PR description as intent by omitting `--ticket`:

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
    "offline":false
  }'
```

## Draft-PR verification workflow

Create a disposable draft PR, paste its URL into CodeTrust, inspect verdict, then close it in GitHub. CodeTrust intentionally never mutates PR state.

See [draft PR workflow](docs/DRAFT_PR_WORKFLOW.md) for exact commands.

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
