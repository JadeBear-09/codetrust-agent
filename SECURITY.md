# Security policy and POC threat model

## Supported version

Only latest commit on `main` receives fixes during Talent Hack development.

## Trust boundaries

Ticket text, diffs, repository files, pull-request metadata, and model responses are untrusted. They may contain prompt injection, secrets, malformed data, or content designed to trigger unsafe tool use.

## Current controls

- Model receives ticket and diff as data with explicit instruction-boundary language.
- Deterministic findings, risk score, and verdict cannot be overwritten by model output.
- Pull-request references must match `OWNER/REPO#NUMBER`.
- GitHub ingestion uses fixed `gh pr view` and `gh pr diff` argument arrays without shell execution.
- Local git ingestion uses fixed `git diff` arguments without shell execution.
- Dashboard limits request sizes and escapes rendered result content through DOM text nodes.
- API key remains in environment variables and is excluded from version control.
- Container runs as non-root user.
- Evidence pack hashes ticket, diff, and findings with SHA-256.

## Known POC limitations

- Dashboard has no authentication. Bind to `127.0.0.1` unless placed behind trusted gateway.
- GitHub CLI inherits local user permissions.
- POC does not clone or execute arbitrary pull-request code.
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
- Evaluated policy bundles per repository and business domain.

## Reporting

Do not publish vulnerabilities or secrets in public issues. Use private repository security reporting or contact repository owner directly.

