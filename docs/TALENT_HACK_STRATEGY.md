# Talent Hack strategy

## Verified event facts

Source: [official HackerEarth Talent Hack page](https://www.hackerearth.com/community/challenges/hackathon/the-talent-hack-build-compete-get-hired/), reviewed July 14, 2026.

- Online Technical Challenge runs July 10–15, 2026.
- Participation is individual; team size is one.
- Public page shows about 8,200 registrations and 202 submissions.
- Round 1 is invite-only after registration screening.
- Highest performers attend DTDL Gurugram build event on July 24–25.
- Finalists receive a new DTDL problem statement and build a POC under real-world conditions.
- Hiring continues through two technical rounds and one HR discussion.

## Role-alignment matrix

| DTDL signal | CodeTrust evidence |
|---|---|
| Strong Python | Typed Python package, CLI, API, tests |
| Agentic AI | Multi-stage scope, impact, challenge, test-design, decision workflow |
| Production AI | Deterministic evidence boundary, explicit provider failures, CI, container, health check |
| Multi-agent orchestration | Specialist stages with explicit trace and bounded responsibilities |
| RAG/knowledge systems | Future adapter point; do not add fake RAG where repository context is sufficient |
| API development | FastAPI verification endpoints and OpenAPI docs |
| Cloud technologies | Non-root Docker image and stateless service boundary |
| Reliability/scalability | Timeout controls, deterministic gates, request limits, failure proof |
| Full stack | Responsive dashboard connected to live verification API |
| Security/privacy | Threat model, no arbitrary shell, local-first default, secret isolation |

## Competitive position

Public submissions include generic customer assistants, sentiment tools, telecom copilots, a deterministic agentic layer, and legacy-code modernization. CodeTrust must not compete on broad chatbot features. It wins attention through visible proof:

1. Analyze a real pull request.
2. Show exact evidence and affected business domains.
3. Generate adversarial test.
4. Execute one failure proof.
5. Explain human decision boundary.

## What can be finished before July 24

- Reusable verification workflow.
- Real GitHub PR demo.
- Offline and API-assisted modes.
- Failure-proof scenario.
- Dockerized dashboard.
- Pitch, architecture, and judge defense.

## What cannot be finalized early

Final problem-specific product, metrics, and submission claims. DTDL will issue a new problem statement at the in-person event. Reuse CodeTrust architecture or adapt components only when they fit that statement. Do not force current idea onto unrelated problem.

## Event-day decision rule

Within first 30 minutes:

1. Extract user, pain, invariant, input, output, and judge-visible success condition.
2. Decide whether CodeTrust directly solves problem, becomes verification layer, or should be replaced.
3. Preserve reusable assets: agent trace, evidence model, FastAPI shell, dashboard, Docker, CI, test harness.
4. Build narrow end-to-end path before extra agents, RAG, or polish.

## Winning demo sequence

```text
Real PR → autonomous trace → hidden production failure → generated proof fails
       → minimal fix → proof passes → risk score drops → one human decision
```

## Personal readiness blocker

Confirm Round 1 invitation from `support@hackerearth.com`. Public page states non-invited registrants cannot take Round 1.
