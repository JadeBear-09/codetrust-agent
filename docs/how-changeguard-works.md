# How ChangeGuard works

ChangeGuard turns multi-source telecom evidence into visible Gemini multi-agent judgment.

## Mission sequence

1. Operator selects incident JSON.
2. Backend loads telemetry, topology, change-history, and security evidence.
3. Four Gemini specialists run concurrently, each with one evidence source.
4. Each returns candidate causes, citations, confidence, summary, and uncertainty.
5. Gemini adjudicator reconciles findings and selects root cause.
6. Gemini response planner creates bounded operator recommendation.
7. UI polls mission state and renders every JSONL event.
8. Backend saves `run.jsonl`, `summary.json`, and `report.md`.

## Why role separation matters

Telemetry agent cannot claim security facts it never received. Security agent cannot infer deployment
history. Adjudicator sees explicit findings and citations. This makes evidence handoffs inspectable and
limits source mixing.

## What application checks

- response matches structured schema;
- specialist citations belong to assigned source;
- adjudicator citations exist in specialist outputs;
- planner targets remain inside incident scope.

These are integrity checks. They stop invalid mission; they do not choose answer.

## What Gemini decides

- specialist candidate causes;
- confidence and uncertainty;
- final root cause;
- whether planning is safe;
- final response mode, recommendation, steps, signals, and stop conditions.

## What logs show

- evidence received by each specialist;
- model, provider, attempt, timing, quota wait, and tokens;
- full structured response from every agent;
- mission completion or failure.

Credentials and hidden system prompts are excluded.

## Real-world boundary

Incident records model telecom operations and use DTDL-style observer attribution. Gemini calls are
live. Network and controller access are not connected. Output is recommendation requiring human
approval before mutation.

See [`../architecture.md`](../architecture.md) for full contracts and failure semantics.
