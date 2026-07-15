# Judge questions and answers

## “Is this only static analysis with an LLM wrapper?”

The baseline uses deterministic rules because evidence must be repeatable. Agent behavior appears in autonomous PR ingestion, scope mapping, impact routing, intent reconstruction, challenge selection, adversarial test design, uncertainty handling, and verdict packaging. One adversarial test executes against the demo and proves duplicate payment. The model never gets authority to invent evidence.

## “Why will existing linters not solve this?”

Linters detect local code patterns. CodeTrust evaluates change intent, business invariants, contract compatibility, rollback, failure behavior, and human decisions across files. It can compose linters as tools, but its output is a change-level evidence decision.

## “How do you control hallucinations?”

Findings come from deterministic gates and exact diff lines. Model output is restricted to intent, summary, and questions. Verdict and score ignore model opinion. Reports state confidence and uncertainty.

## “What if CodeTrust misses a risk?”

`PASS` requires structured approved intent, at least one applicable gate, and no finding. It is not guaranteed safety. Production rollout still needs calibrated evaluations, defense in depth, and human review for high-impact changes.

## “How does this scale across repositories?”

Core workflow stays constant; policy bundles vary by language, service, and domain. Repository metadata defines ownership, contracts, test commands, and critical invariants. Execution runs in isolated jobs triggered by pull requests.

## “Why use a model at all?”

Tickets are incomplete and architectural intent spans many artifacts. Model reasoning helps reconstruct intent, choose useful challenges, and explain residual uncertainty. Deterministic tools remain source of proof.

## “Why did you not use LangGraph?”

Current workflow is short, deterministic, and requires no durable checkpoint or human interrupt. Introducing framework machinery would not improve proof. Stages have typed boundaries and map directly to future LangGraph nodes when conditional retries, parallel specialists, or resumable runs become necessary.

## “Can it analyze a real pull request?”

Yes. `--github-pr OWNER/REPO#NUMBER` uses authenticated GitHub CLI to fetch title, description, commit identities, and unified diff. It never checks out or executes untrusted PR code in current POC.

## “What proof is executable?”

`make proof` runs timeout-after-success scenario. Provider commits first payment side effect, response is lost, retry commits second. Test fails at `assert 2 == 1`. Harness treats this expected failure as confirmed evidence.

## “What is the business value?”

CodeTrust reduces senior-review load, catches expensive failures earlier, and enables coding-agent throughput without proportionally increasing risk. Production evaluation would measure review time saved, escaped defects, finding precision, and time to remediation.

## “Would it automatically block deployment?”

Policy decides. Current POC blocks on critical findings but does not merge or deploy. A production deployment can start in advisory mode, measure precision, then enforce only calibrated high-confidence gates.

## “What makes this relevant to Deutsche Telekom Digital Labs?”

The scenario reflects distributed systems, multiple market adapters, backward compatibility, payments, production guardrails, and humans retaining business judgment. These are enterprise engineering concerns, not chatbot features.

## “Can you explain every line?”

Use this map:

- `diff_parser.py`: converts unified diff text into typed changed-line evidence.
- `github.py`: loads real PR metadata, diff, and base-commit policy through fixed GitHub CLI calls.
- `impact.py`: maps affected business and technical surfaces.
- `rules.py`: repository-agnostic core gates plus conditional domain gates and transparent scoring.
- `testgen.py`: generates missing adversarial proof templates.
- `llm.py`: bounded model synthesis with retries, fallback model, explicit errors, and latency metadata.
- `agent.py`: orchestration, trace, verdict, and evidence hash.
- `report.py`: JSON, Markdown, and escaped HTML evidence artifacts.
- `cli.py`: fixed local interface and constrained `git diff` tool.
- `web.py`: FastAPI endpoints and responsive local dashboard.
