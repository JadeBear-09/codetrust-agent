# CodeTrust delivery plan

## Goal

Deliver a credible Talent Hack proof of concept showing autonomous, evidence-backed verification of AI-generated code. Optimize for a live five-minute demo, architectural clarity, and deep judge questioning.

## Product thesis

Coding agents are not constrained by code generation. They are constrained by trusted verification. CodeTrust becomes the verification firewall between autonomous coding and production.

## Phase 0 — Scope lock

Status: complete.

- Use payment reconciliation as the main business-critical scenario.
- Produce evidence, not generic prose.
- Keep deterministic checks and model reasoning separate.
- Require a human only for unresolved business judgment.
- Keep an offline demo path.

## Phase 1 — Working POC

Status: complete for baseline.

- Parse unified diffs with exact changed-line evidence.
- Route changes through risk-specific checks.
- Detect async blocking, missing payment idempotency, API removal, rollback gaps, and missing failure tests.
- Generate risk score and `BLOCK`, `NEEDS_REVIEW`, or `PASS` verdict.
- Emit HTML, Markdown, and JSON evidence artifacts.
- Add optional OpenAI-assisted intent reconstruction.

## Phase 2 — Real repository depth

Status: in progress.

- [x] Add GitHub pull-request ingestion.
- [x] Map business and technical impact areas.
- [x] Generate adversarial test templates.
- [x] Execute dedicated timeout-after-success failure proof.
- [ ] Map imports, callers, API consumers, and database ownership.
- Run project tests inside a constrained container.
- Generate repository-adapted test patch for top finding.
- Compare pre-fix and post-fix reports.

Exit criteria: CodeTrust analyzes one real PR and proves at least one risk with an executable failing test.

## Phase 3 — Demo product

Status: baseline complete.

- [x] Add “run verification” web action and visible progress stages.
- [x] Show impact map.
- [x] Add FastAPI endpoints, health check, and responsive dashboard.
- [x] Add non-root Docker packaging.
- Add before/after remediation comparison.
- Add managed-key evidence signature and downloadable report.
- Time complete demo below five minutes.

Exit criteria: fresh laptop setup to verdict in under three minutes; full spoken demo in under five.

## Phase 4 — Submission and defense

Target: final day.

- Record 90-second backup video.
- Capture screenshots after clean demo run.
- Replace placeholder metrics with measured results.
- Rehearse judge questions in `JUDGE_QA.md`.
- Run dependency, secret, and license checks.
- Tag immutable submission commit.

## Priority order under time pressure

1. Working end-to-end demo.
2. Evidence-backed idempotency failure.
3. Generated failing test and corrected rerun.
4. Clear architecture and human boundary.
5. UI polish.
6. Extra rules and integrations.

## Success metrics

- Demo finds all five seeded defects.
- Every finding contains location, evidence, impact, challenge, and missing proof.
- Offline run succeeds with no network.
- Test suite and lint pass.
- Judge can understand value in 20 seconds.
- Presenter can explain every source file and tradeoff.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| API or Wi-Fi failure | Deterministic offline mode and pre-generated evidence pack |
| “This is static analysis” objection | Show autonomous routing, intent reconstruction, adversarial test generation, and iterative rerun roadmap |
| False confidence | Evidence lines, confidence values, explicit uncertainty, and human decision boundary |
| Demo looks scripted | Analyze an unseen small diff after main scenario |
| Too much scope | Protect payment scenario; defer broad language coverage |
