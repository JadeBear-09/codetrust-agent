# Talent Hack submission draft

## Project name

CodeTrust — Autonomous verification agent for AI-generated software changes

## One-line pitch

Coding agents create pull requests. CodeTrust decides which pull requests deserve human attention.

## Problem

AI coding agents scale code output, but trust does not scale with it. Senior engineers must inspect more generated changes, while ordinary tests often miss architectural failures such as duplicate retries, contract breaks, unsafe concurrency, and incomplete rollback. The bottleneck moves from writing code to proving that code is safe.

## Solution

CodeTrust acts as a verification firewall between coding agents and production. It ingests a real GitHub pull request, reconstructs ticket intent, maps affected business domains, selects risk-specific checks, challenges unsafe assumptions, generates adversarial tests, and produces an evidence pack. Deterministic gates own factual findings; model reasoning explains intent and uncertainty. Humans receive only unresolved business decisions.

## Demo scenario

An agent adds asynchronous payment reconciliation. Code looks correct and a success test passes. CodeTrust discovers blocking I/O, duplicate-payment risk, a broken market-adapter contract, a missing rollback, and absent failure coverage. It blocks the change, proposes missing adversarial tests, and asks one human question about the idempotency key.

## Differentiation

- Not another coding agent or chatbot.
- Evidence before explanation.
- Exact file and line references for each risk.
- Hybrid deterministic and model architecture.
- Executable failure proof: timeout-after-success produces two payment side effects.
- Offline-resilient demonstration and local-first dashboard.
- Explicit human boundary for business judgment.
- Machine-readable result suitable for CI and policy gates.

## Technical architecture

CodeTrust accepts ticket text plus a unified diff, git range, or GitHub pull request. A scope mapper extracts changed lines. An impact mapper identifies business and technical blast radius. A router selects async, payment, API, database, and test gates. A test designer creates missing adversarial proof. Findings drive deterministic risk score and verdict. OpenAI Responses API reconstructs intent and unresolved questions. FastAPI serves dashboard and API; CodeTrust emits HTML, Markdown, generated tests, and integrity-hashed JSON artifacts.

## Responsible AI

CodeTrust does not silently merge or deploy. It treats tickets and code as untrusted inputs, prevents model output from executing arbitrary commands, labels uncertainty, and never equates absence of findings with proof of safety. Human owners retain decisions requiring business context.

## Current status

- Working CLI and visual evidence dashboard.
- Live FastAPI service and OpenAPI documentation.
- Real GitHub pull-request ingestion.
- Business-domain impact mapping.
- Generated adversarial proof templates.
- Executable duplicate-payment failure proof.
- Five verification gates.
- Offline and API-assisted modes.
- Thirteen automated tests plus lint and GitHub CI.
- Non-root Docker packaging and health check.
- Seeded payment demo detecting all five target failures.
- Real private PR comparison: risky candidate `BLOCK 94/100`; remediated candidate `PASS 0/100`.

## Roadmap

Next steps are GitHub App installation flow, call-graph impact mapping, isolated target-repository test execution, repository-adapted test patches, and pre-fix versus post-fix evidence comparison.

## Event-specific note

DTDL will issue a new problem statement to finalists at the July 24–25 build event. This draft must be adapted to that problem. CodeTrust components remain reusable even if final product changes.

## Closing

CodeTrust lets engineering agents scale without turning senior engineers into full-time AI code inspectors.
