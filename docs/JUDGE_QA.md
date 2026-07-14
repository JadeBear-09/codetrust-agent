# Judge questions and answers

## “Is this only static analysis with an LLM wrapper?”

The baseline uses deterministic rules because evidence must be repeatable. Agent behavior appears in autonomous scope mapping, risk routing, intent reconstruction, challenge selection, uncertainty handling, and verdict packaging. Next iteration adds executable adversarial tests and a verify-fix-rerun loop. The model never gets authority to invent evidence.

## “Why will existing linters not solve this?”

Linters detect local code patterns. CodeTrust evaluates change intent, business invariants, contract compatibility, rollback, failure behavior, and human decisions across files. It can compose linters as tools, but its output is a change-level evidence decision.

## “How do you control hallucinations?”

Findings come from deterministic gates and exact diff lines. Model output is restricted to intent, summary, and questions. Verdict and score ignore model opinion. Reports state confidence and uncertainty.

## “What if CodeTrust misses a risk?”

`PASS` means no configured gate found a blocker, not guaranteed safety. Production rollout needs calibrated evaluations, repository-specific policies, defense in depth, and human review for high-impact changes.

## “How does this scale across repositories?”

Core workflow stays constant; policy bundles vary by language, service, and domain. Repository metadata defines ownership, contracts, test commands, and critical invariants. Execution runs in isolated jobs triggered by pull requests.

## “Why use a model at all?”

Tickets are incomplete and architectural intent spans many artifacts. Model reasoning helps reconstruct intent, choose useful challenges, and explain residual uncertainty. Deterministic tools remain source of proof.

## “What is the business value?”

CodeTrust reduces senior-review load, catches expensive failures earlier, and enables coding-agent throughput without proportionally increasing risk. Production evaluation would measure review time saved, escaped defects, finding precision, and time to remediation.

## “Would it automatically block deployment?”

Policy decides. Current POC blocks on critical findings but does not merge or deploy. A production deployment can start in advisory mode, measure precision, then enforce only calibrated high-confidence gates.

## “What makes this relevant to Deutsche Telekom Digital Labs?”

The scenario reflects distributed systems, multiple market adapters, backward compatibility, payments, production guardrails, and humans retaining business judgment. These are enterprise engineering concerns, not chatbot features.

## “Can you explain every line?”

Use this map:

- `diff_parser.py`: converts unified diff text into typed changed-line evidence.
- `rules.py`: five independent verification gates plus transparent scoring.
- `llm.py`: bounded Responses API synthesis with offline fallback.
- `agent.py`: orchestration, trace, verdict, and evidence hash.
- `report.py`: JSON, Markdown, and escaped HTML evidence artifacts.
- `cli.py`: fixed local interface and constrained `git diff` tool.

