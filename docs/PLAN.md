# CodeTrust delivery plan

## Product objective

CodeTrust is verification firewall between software agents and production. It converts approved intent plus changed code into evidence-backed verdict and preserves human ownership of unresolved decisions.

## Current local product

- [x] Accept live GitHub PR URL.
- [x] Load approved intent from exact base-commit policy or explicit input.
- [x] Parse exact changed-file and line evidence.
- [x] Map scope alignment and business/technical impact.
- [x] Run deterministic risk gates.
- [x] Generate adversarial verification suggestions.
- [x] Require bounded Gemini or OpenAI-compatible synthesis in website flows.
- [x] Return `BLOCK`, `NEEDS_REVIEW`, or `PASS`.
- [x] Persist bounded local report history without raw ticket or diff.
- [x] Provide focused responsive website with no auto-loaded sample data.
- [x] Preserve offline verification path.
- [x] Fail explicitly when required intent or model synthesis is unavailable.
- [x] Cover common source languages with generic gates and report skipped gates.

## Production service work

- [ ] Replace local GitHub CLI with GitHub App installation tokens.
- [ ] Trigger verification from GitHub webhooks and publish check results.
- [ ] Add identity, authorization, organization and repository boundaries.
- [ ] Move run history to durable database and object storage.
- [ ] Execute repository-specific verification in isolated workers.
- [ ] Add resource limits, network allowlists, secret scanning, and audit logs.
- [ ] Sign evidence digests with managed keys.
- [ ] Add evaluated repository policy bundles and regression corpus.
- [ ] Deploy frontend, API, worker, and persistence on managed infrastructure.

## Product boundary

CodeTrust verifies changes. It does not merge, deploy, close pull requests, or claim certainty unsupported by configured evidence.
