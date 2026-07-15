# Security policy and threat model

## Supported version

Only latest commit on `main` receives fixes.

## Trust boundaries

Ticket text, diffs, repository files, pull-request metadata, and model responses are untrusted. They may contain prompt injection, secrets, malformed data, or content designed to trigger unsafe tool use.

## Current controls

- Model receives scope evidence, PR claim, and diff as data with explicit instruction-boundary language.
- PR author text is isolated as an untrusted change claim and cannot satisfy inferred-scope evidence citations. Only supplied base-repository paths can.
- Repository context is read from exact base SHA through bounded, read-only GitHub API calls; no repository content is executed.
- Deterministic findings, risk score, and verdict cannot be overwritten by model output.
- Pull-request references must match `OWNER/REPO#NUMBER` or canonical GitHub PR URL.
- GitHub ingestion uses fixed `gh pr view`, `gh pr diff`, and read-only `gh api` argument arrays without shell execution.
- Local git ingestion uses fixed `git diff` arguments without shell execution.
- Dashboard limits request sizes and escapes rendered result content through DOM text nodes.
- API key remains in environment variables and is excluded from version control.
- Configuration endpoint exposes provider and model metadata but never credentials.
- Local run history stores structured reports, not raw ticket or diff input.
- Container runs as non-root user.
- Evidence pack hashes scope text, PR claim, diff, findings, and source provenance with SHA-256.

## Known limitations

- Dashboard has no authentication. Bind to `127.0.0.1` unless placed behind trusted gateway.
- API requests are synchronous and intended for one trusted local operator.
- GitHub CLI inherits local user permissions.
- Live mode sends bounded repository evidence and PR diff to configured model provider; current release does not perform pre-model secret redaction.
- CodeTrust does not clone or execute arbitrary pull-request code.
- Generated test templates require repository-specific fixture adaptation.
- SHA-256 digest detects mutation but is not cryptographic authorship proof.
- Rules are intentionally narrow and can produce false positives or false negatives.

## Production controls required

- Ephemeral containers with CPU, memory, process, and time limits.
- Read-only source mounts and network deny-by-default.
- Short-lived GitHub App tokens with repository-scoped permissions.
- Secret scanning and redaction before model calls.
- Signed evidence digests using managed keys.
- Authentication, authorization, rate limiting, audit logs, and CSRF controls.
- Evaluated repository-understanding regression corpus across languages and domains.

## Reporting

Do not publish vulnerabilities or secrets in public issues. Use private repository security reporting or contact repository owner directly.
