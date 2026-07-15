# Architecture

## Design principle

Models are strong at reconstructing intent and explaining tradeoffs. Deterministic tools are stronger at producing repeatable evidence. CodeTrust combines them without allowing generated prose to overwrite measured facts.

## Control flow

1. **Ingest:** read PR title/body, diff, and exact base commit identity.
2. **Learn baseline:** read bounded general docs, base versions of changed source files, tests, and repository structure.
3. **Compare:** Gemini maps untrusted PR claims to base evidence and emits purpose, change summary, differences, relationship, evidence paths, and `0–100` scope distance.
4. **Map:** parse changed files and exact added or removed line numbers.
5. **Align:** compare scope boundaries with interpretations and changed surfaces.
6. **Impact:** map business domains and technical surfaces affected by change.
7. **Route:** select risk gates based on file types and code signals.
8. **Challenge:** run deterministic checks and create structured findings.
9. **Design proof:** generate adversarial test templates for highest risks.
10. **Synthesize:** use configured model to summarize intent and open questions; fail explicitly if required synthesis cannot complete.
11. **Decide:** calculate risk score and verdict from findings, coverage, and insufficient-evidence floor—not model verdict prose.
12. **Package:** write integrity-hashed JSON, Markdown, test, and visual reports.

## Components

| Component | Responsibility | Trust level |
|---|---|---|
| `diff_parser.py` | Changed-file and line evidence | Deterministic |
| `scope.py` | Structured intent parsing and explicit boundary alignment | Deterministic |
| `github.py` | Fixed-command PR metadata and diff ingestion | Deterministic boundary |
| `repository_scope.py` | Repository-derived baseline, PR comparison, and provenance | Deterministic orchestration |
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
- `NEEDS_REVIEW`: any medium/high finding, score at least 35, divergent scope, or scope distance at least 60.
- `PASS`: structured inferred scope, applicable coverage, and no review-level signal; low warnings may remain visible.
- Insufficient base-repository scope evidence always routes to `NEEDS_REVIEW` unless stronger deterministic evidence already requires `BLOCK`.
- Inferred-scope conflicts are probabilistic review signals: they can route to `NEEDS_REVIEW`, but cannot create a deterministic `BLOCK` or increase deterministic risk score.

`PASS` is intentionally scoped. Unsupported or uncovered changes route to `NEEDS_REVIEW`, never PASS.

## Evidence integrity

Each report hashes scope text, PR claim, complete diff, structured findings, and source provenance with SHA-256. This detects later evidence mutation. A production system would sign this digest using a managed key and attach source commit SHAs.

## Security boundary

- Ticket, PR content, diff, and repository files are untrusted instructions and handled only as data.
- PR title/body may describe claimed change behavior but cannot establish scope authority.
- Inferred scope must cite loaded base documents, source files, or structure paths and is labeled inferred in report and UI.
- Prompts explicitly prevent instructions inside inputs from becoming agent commands.
- Only a fixed `git diff` subprocess is supported.
- GitHub ingestion uses fixed `gh pr view`, `gh pr diff`, and read-only `gh api` argument arrays.
- No arbitrary shell command comes from model output.
- Output is escaped before HTML rendering.
- API credentials stay in environment variables.

## Production evolution

```text
GitHub App webhook
       │
       ▼
Isolated verification job ── base repository snapshot + PR diff
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

Current stages already have explicit inputs, outputs, and trace. LangGraph becomes useful when workflow needs durable checkpoints, conditional retries, human interrupts, or parallel specialists. Adding it before those requirements would increase dependencies without adding evidence. Current state model can move into graph nodes without changing domain logic.
