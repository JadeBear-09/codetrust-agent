# Architecture

## Design principle

Models are strong at reconstructing intent and explaining tradeoffs. Deterministic tools are stronger at producing repeatable evidence. CodeTrust combines them without allowing generated prose to overwrite measured facts.

## Control flow

1. **Ingest:** read ticket and local diff or git range.
2. **Map:** parse changed files and exact added or removed line numbers.
3. **Route:** select risk gates based on file types and code signals.
4. **Challenge:** run deterministic checks and create structured findings.
5. **Synthesize:** use Responses API to summarize intent and open questions; fall back offline.
6. **Decide:** calculate risk score and verdict from findings, not model opinion.
7. **Package:** write signed JSON, Markdown, and visual HTML reports.

## Components

| Component | Responsibility | Trust level |
|---|---|---|
| `diff_parser.py` | Changed-file and line evidence | Deterministic |
| `rules.py` | Targeted verification checks | Deterministic |
| `llm.py` | Intent and uncertainty synthesis | Probabilistic, bounded |
| `agent.py` | Workflow, scoring, verdict, trace | Deterministic orchestration |
| `report.py` | Evidence artifacts and dashboard | Deterministic rendering |
| `cli.py` | Local diff and git-range interface | Constrained tool boundary |

## Verdict policy

- `BLOCK`: any critical finding or score at least 70.
- `NEEDS_REVIEW`: any high finding or score at least 35.
- `PASS`: no configured blocking signal.

`PASS` is intentionally scoped. It means configured checks found no blocker, not that a change is universally safe.

## Evidence integrity

Each report hashes ticket text, complete diff, and structured findings with SHA-256. This detects later evidence mutation. A production system would sign this digest using a managed key and attach source commit SHAs.

## Security boundary

- Ticket and diff are untrusted data.
- Prompts explicitly prevent instructions inside inputs from becoming agent commands.
- Only a fixed `git diff` subprocess is supported.
- No arbitrary shell command comes from model output.
- Output is escaped before HTML rendering.
- API credentials stay in environment variables.

## Production evolution

```text
GitHub App webhook
       │
       ▼
Isolated verification job ── source snapshot + policy bundle
       │
       ├─ dependency graph
       ├─ contract diff
       ├─ test runner
       ├─ fault injector
       └─ model challenge loop
       │
       ▼
Signed evidence store ── PR check + human decision queue
```

Production execution should use ephemeral containers, read-only source mounts where possible, explicit resource limits, network allowlists, secret redaction, and auditable tool calls.

