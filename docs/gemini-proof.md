# Gemini proof

Current proof is live mission UI and JSONL trace.

## Claim

Every mission makes six live Gemini calls:

1. telemetry specialist;
2. topology specialist;
3. change-history specialist;
4. security specialist;
5. adjudicator;
6. response planner.

Specialists run in parallel. Adjudicator receives their findings. Planner receives adjudicated state.
No expected-label comparison, baseline call, sandbox execution, or canned replay runs in this path.

## Evidence

Open latest directory under `outputs/agent-missions/`:

- `run.jsonl` — chronological inputs, receipts, and structured outputs;
- `summary.json` — final findings, decision, recommendation, and usage;
- `report.md` — readable mission result.

UI exposes same run through `/api/proof/runs/<run-id>` and downloadable JSONL.

## Validation boundary

Schema, citation, and resource-scope checks reject invalid output. They do not choose root cause or
recommendation. Gemini owns displayed result.

## Safety boundary

Mission is advisory. No production network or controller executes recommendation.
