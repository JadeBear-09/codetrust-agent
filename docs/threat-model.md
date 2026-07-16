# Threat model

## Protected assets

Production controller authority, operator identity, tenant data, telemetry integrity, runbook content,
workflow checkpoints, approval records, tool credentials, and the audit chain are protected assets.

## Trust boundaries

- Telemetry, topology, controller output, retrieved documents, and user-authored text are untrusted data.
- Prompt files, tool catalogs, policy files, deployment configuration, and identity-provider metadata are
  administrator-controlled inputs and require change review.
- LLM output is untrusted until strict schema validation, evidence-reference validation, and deterministic
  policy checks pass.
- The tool gateway is the only component allowed to cross into production controllers.

## Primary abuse cases and controls

| Abuse case | Control |
|---|---|
| Prompt injection in telemetry or RAG | Trusted instructions are separated from untrusted context; specialists cannot execute tools; schema and evidence-ID checks reject fabricated provenance. |
| Hallucinated controller action or target | Model sees only a redacted allowlist; registry rejects unknown names and fields; configured target argument fields must exactly bind observed incident/topology IDs inside declared blast radius; no shell or model-provided URL exists. |
| Approval replay or plan substitution | Approval is tenant-scoped and atomically claimed, binds a canonical SHA-256 plan hash, and is checked again at execution. |
| Duplicate delivery or worker crash | Transactional outbox, explicit Kafka offsets, LangGraph checkpoints, idempotency keys, bounded retry, terminal replay handling, and DLQ. |
| SSRF or redirect abuse | Base URL comes only from deployment environment; catalog paths reject hosts, schemes, traversal, query, fragment, and backslashes; redirects are disabled; production requires HTTPS. |
| Unsafe success inference | Verification tools must be read-only and have deterministic response JSON Schema; HTTP success alone is insufficient. |
| Failed or partial change | Sequential saga stops on first failure, runs reverse-order rollback, and independently verifies restored state. |
| Cross-tenant access | OIDC tenant claim, application filters, Kafka tenant envelope, Qdrant tenant filter, tool headers, and forced PostgreSQL RLS. API and workers use non-bypass roles; the outbox gets a separately scoped publisher role. |
| Oversized input/output | Configured ingest/document limits, controller response streaming limit, bounded context, strict schema, and ingress limits. |
| Credential disclosure | Credentials are environment/secret-manager values, omitted from model catalog and audit payloads, and sent only by the gateway. |
| Audit tampering | Per-tenant hash chain detects mutation; production should export to operator-owned WORM or signed storage. |

## Residual risk

The hash chain is tamper-evident, not externally immutable. A compromised database owner can rewrite both
records and heads. Export and sign audit batches outside this trust domain. RLS does not replace separate
databases where regulatory isolation requires them. JSON Schema expresses deterministic shape and values,
but controller-specific semantic predicates still require careful schema design and contract tests. Model
quality must be measured on representative incident replays before any automatic read or write policy is
relaxed.
