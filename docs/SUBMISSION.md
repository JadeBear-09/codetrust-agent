# Talent Hack submission draft

## Project name

CodeTrust — Autonomous verification agent for AI-generated software changes

## One-line pitch

Coding agents create pull requests. CodeTrust decides which pull requests deserve human attention.

## Problem

AI coding agents scale code output, but trust does not scale with it. Senior engineers must inspect more generated changes, while ordinary tests often miss architectural failures such as duplicate retries, contract breaks, unsafe concurrency, and incomplete rollback. The bottleneck moves from writing code to proving that code is safe.

## Solution

CodeTrust acts as a verification firewall between coding agents and production. It ingests a real GitHub pull request, reconstructs ticket intent, maps affected business domains, selects risk-specific checks, challenges unsafe assumptions, generates adversarial tests, and produces an evidence pack. Deterministic gates own factual findings; model reasoning explains intent and uncertainty. Humans receive only unresolved business decisions.

## Demo scenarios

1. **External policy validation:** CodeTrust checks public `Gnucash/gnucash#2262` against an explicit appearance-policy boundary and returns `BLOCK 100/100`. The recorded maintainer outcome is then revealed: closed unmerged as out of scope.
2. **Private technical verification:** CodeTrust checks private `JadeBear-09/codetrust-agent#2` and returns `BLOCK 94/100` for missing idempotency, blocking I/O in an async path, rollback risk, and absent failure-path coverage.

The external example demonstrates one policy-verdict match. It is not claimed as blind prediction or universal accuracy.

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

CodeTrust accepts approved intent plus a unified diff, git range, or GitHub pull request. A scope mapper extracts changed lines and checks explicit boundaries. An impact mapper identifies business and technical blast radius. A router selects async, payment, API, database, and test gates. A test designer creates missing adversarial proof. Findings drive deterministic risk score and verdict. Gemini or an OpenAI-compatible provider reconstructs intent and unresolved questions without controlling verdict. FastAPI serves the focused dashboard and API; CodeTrust emits HTML, Markdown, generated tests, and integrity-hashed JSON artifacts.

## Responsible AI

CodeTrust does not silently merge or deploy. It treats tickets and code as untrusted inputs, prevents model output from executing arbitrary commands, labels uncertainty, and never equates absence of findings with proof of safety. Human owners retain decisions requiring business context.

## Current status

- Working CLI and focused responsive PR-verification dashboard.
- Live FastAPI service and OpenAPI documentation.
- Real GitHub pull-request ingestion.
- Explicit product-scope alignment and drift evidence.
- Business-domain impact mapping.
- Generated adversarial proof templates.
- Executable duplicate-payment failure proof.
- Five verification gates.
- Offline and Gemini-assisted modes with transient retry and fallback.
- Thirty-two automated tests plus lint and GitHub CI.
- Non-root Docker packaging and health check.
- Public external validation: GnuCash PR `BLOCK 100/100`, matching closed-unmerged out-of-scope maintainer decision.
- Real private PR: risky candidate `BLOCK 94/100`.

## Roadmap

Next steps are GitHub App installation flow, call-graph impact mapping, isolated target-repository test execution, repository-adapted test patches, and pre-fix versus post-fix evidence comparison.

## Submission warning

Final pitch and scope must match official hackathon problem statement and judging rubric. Working software alone cannot guarantee ranking or a win.

## Closing

CodeTrust lets engineering agents scale without turning senior engineers into full-time AI code inspectors.
