# Talent Hack submission draft

## Project name

CodeTrust — Autonomous verification agent for AI-generated software changes

## One-line pitch

Coding agents create pull requests. CodeTrust decides which pull requests deserve human attention.

## Problem

AI coding agents scale code output, but trust does not scale with it. Senior engineers must inspect more generated changes, while ordinary tests often miss architectural failures such as duplicate retries, contract breaks, unsafe concurrency, and incomplete rollback. The bottleneck moves from writing code to proving that code is safe.

## Solution

CodeTrust acts as a verification firewall between coding agents and production. It reconstructs ticket intent, maps changed surfaces, selects risk-specific checks, challenges unsafe assumptions, and produces an evidence pack. Deterministic gates own factual findings; model reasoning explains intent and uncertainty. Humans receive only unresolved business decisions.

## Demo scenario

An agent adds asynchronous payment reconciliation. Code looks correct and a success test passes. CodeTrust discovers blocking I/O, duplicate-payment risk, a broken market-adapter contract, a missing rollback, and absent failure coverage. It blocks the change, proposes missing adversarial tests, and asks one human question about the idempotency key.

## Differentiation

- Not another coding agent or chatbot.
- Evidence before explanation.
- Exact file and line references for each risk.
- Hybrid deterministic and model architecture.
- Offline-resilient demonstration.
- Explicit human boundary for business judgment.
- Machine-readable result suitable for CI and policy gates.

## Technical architecture

CodeTrust accepts ticket text plus a unified diff or git range. A scope mapper extracts changed lines. A router selects async, payment, API, database, and test gates. Findings drive a deterministic risk score and verdict. OpenAI Responses API reconstructs intent and unresolved questions. CodeTrust emits HTML, Markdown, and integrity-hashed JSON artifacts.

## Responsible AI

CodeTrust does not silently merge or deploy. It treats tickets and code as untrusted inputs, prevents model output from executing arbitrary commands, labels uncertainty, and never equates absence of findings with proof of safety. Human owners retain decisions requiring business context.

## Current status

- Working CLI and visual evidence dashboard.
- Five verification gates.
- Offline and API-assisted modes.
- Automated test and lint workflow.
- Seeded payment demo detecting all five target failures.

## Roadmap

Next steps are GitHub App ingestion, dependency-impact mapping, isolated test execution, adversarial test generation, and pre-fix versus post-fix evidence comparison.

## Closing

CodeTrust lets engineering agents scale without turning senior engineers into full-time AI code inspectors.
