# Architecture

## Design principle

Models are strong at reconstructing intent and explaining tradeoffs. Deterministic tools are stronger at producing repeatable evidence. CodeTrust combines them without allowing generated prose to overwrite measured facts.

## Control flow

1. **Ingest:** read approved intent, role interpretations, and local or GitHub change.
2. **Map:** parse changed files and exact added or removed line numbers.
3. **Align:** compare explicit product boundaries with interpretations and changed surfaces.
4. **Impact:** map business domains and technical surfaces affected by change.
5. **Route:** select risk gates based on file types and code signals.
6. **Challenge:** run deterministic checks and create structured findings.
7. **Design proof:** generate adversarial test templates for highest risks.
8. **Synthesize:** use the configured model to summarize intent and open questions; fail explicitly if required synthesis cannot complete.
9. **Decide:** calculate risk score and verdict from findings, not model opinion.
10. **Package:** write integrity-hashed JSON, Markdown, test, and visual reports.

## Components

| Component | Responsibility | Trust level |
|---|---|---|
| `diff_parser.py` | Changed-file and line evidence | Deterministic |
| `scope.py` | Structured intent parsing and explicit boundary alignment | Deterministic |
| `github.py` | Fixed-command PR metadata and diff ingestion | Deterministic boundary |
| `impact.py` | Business and technical blast-radius map | Deterministic |
| `rules.py` | Targeted verification checks | Deterministic |
| `testgen.py` | Missing adversarial proof templates | Deterministic |
| `llm.py` | Intent and uncertainty synthesis | Probabilistic, bounded |
| `agent.py` | Workflow, scoring, verdict, trace | Deterministic orchestration |
| `report.py` | Evidence artifacts and dashboard | Deterministic rendering |
| `cli.py` | Local diff and git-range interface | Constrained tool boundary |
| `web.py` | FastAPI, request validation, live PR API | Local service boundary |
| `ui.py` | Focused PR verification dashboard | Browser boundary |
| `run_store.py` | Bounded report history without raw ticket or diff | Local persistence |

## Verdict policy

- `BLOCK`: any critical finding or score at least 70.
- `NEEDS_REVIEW`: any high finding or score at least 35.
- `PASS`: structured intent exists, at least one gate applies, and no finding exists.

`PASS` is intentionally scoped. Unsupported or uncovered changes route to `NEEDS_REVIEW`, never PASS.

## Evidence integrity

Each report hashes ticket text, complete diff, and structured findings with SHA-256. This detects later evidence mutation. A production system would sign this digest using a managed key and attach source commit SHAs.

## Security boundary

- Ticket and diff are untrusted data.
- Prompts explicitly prevent instructions inside inputs from becoming agent commands.
- Only a fixed `git diff` subprocess is supported.
- GitHub PR ingestion uses fixed `gh pr view` and `gh pr diff` commands.
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

## Why no framework-heavy agent graph yet

POC stages already have explicit inputs, outputs, and trace. LangGraph becomes useful when workflow needs durable checkpoints, conditional retries, human interrupts, or parallel specialists. Adding it before those requirements would increase dependencies without adding evidence. Current state model can move into LangGraph nodes without changing domain logic.
