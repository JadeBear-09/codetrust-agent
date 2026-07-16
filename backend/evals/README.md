# Model and safety evaluation

## Gemini proof dataset

Runtime observations live in `examples/incidents/*.json`.

Expected answers live separately in `evals/intelligence_expectations.json`. They are loaded only by scorer after Gemini responds. They never enter specialist, adjudicator, or planner prompts.

Two paths run on identical evidence:

1. one Gemini analyst with all four read scopes;
2. four source-isolated Gemini specialists followed by findings-only adjudicator.

Safe multi-agent decision adds Gemini planner. Current batch maximum: 13 model calls.

Scoring checks exact root-cause code, safe-to-plan gate, and citation membership. Source API also runs negative permission probe: telemetry credential must receive HTTP 403 from security source.

Run:

```bash
uv run tnoc-intelligence-proof \
  --start-local-services \
  --max-concurrency 2 \
  --requests-per-minute 10
```

Generated `report.md`, `summary.json`, and `run.jsonl` show model attempts, quota waits, tokens, latency, source access, findings, decisions, plan, execution, rollback, recovery, and scores.

## Adjudicator safety cases

`tnoc-eval --cases evals/adjudicator.jsonl` checks go/no-go classification, evidence grounding, and prompt-injection resistance.

Two incident examples and four adjudicator safety cases are prototype gates. Production accuracy claims require versioned representative replay corpus, confidence intervals, false-action rate, abstention quality, latency, cost, rollback success, and unchanged model/prompt/tool configuration.
