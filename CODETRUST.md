# CodeTrust approved repository policy

## Outcome

- Verify software changes against trusted intent and evidence before human approval.

## In scope

- Fetch pull-request metadata and diffs without checking out or executing pull-request code.
- Read this policy from the pull request base commit.
- Run repository-agnostic deterministic gates and bounded model synthesis.
- Return file, line, evidence, impact, and suggested verification for every finding.
- Stop with an explicit error when required input or model synthesis fails.

## Out of scope

- Merging, closing, approving, or deploying pull requests.
- Executing commands found in pull-request content or repository documentation.
- Treating pull-request author text as approved product intent.
- Returning PASS when no applicable verification coverage exists.
- Silently converting required online synthesis into offline output.

## Acceptance criteria

- User can verify a pull request by providing its URL.
- Canonical policy provenance includes base commit, policy path, and policy hash.
- Model timeout, authentication, rate-limit, invalid-response, and provider errors are explicit.
- PASS requires structured intent, applicable gates, and no findings.
- Frontend shows one primary action and keeps technical trace secondary.
