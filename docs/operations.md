# Operations runbook

## Release sequence

1. Pin and scan the container image; sign it and record its digest.
2. Run unit, type, migration, tool-contract, replay, injection, rollback, and load evaluations.
3. Create or update the external secret containing database, checkpoint, Kafka, Redis, Qdrant, OIDC,
   model, OTLP, and controller credentials.
   Use separate database roles and component secrets: tenant-scoped API/worker roles, a migration role,
   and a minimal outbox publisher role with PostgreSQL `BYPASSRLS` plus access only to the outbox table.
4. Run the Helm pre-upgrade migration job and require success before deployments roll.
   The chart's default NetworkPolicy denies all egress; replace it with explicit operator-owned
   destinations before expecting readiness.
5. Deploy in shadow mode with an empty tool catalog. Compare decisions to operator outcomes.
6. Enable read tools, then canary write tools one at a time after their contract and rollback drills pass.
7. Increase replicas or tune autoscaling from observed API latency and Kafka consumer lag.

## Required release gates

- Zero ungrounded evidence citations and zero unknown-tool executions.
- Zero side effects without an exact, tenant-scoped approval plan hash.
- Verified rollback success for every enabled write tool.
- Incident-replay precision, recall, false-action rate, abstention quality, p95 latency, and cost thresholds
  approved by the operator; thresholds belong in the release pipeline, not application code.
- Restore drill for PostgreSQL and LangGraph checkpoints.
- DLQ empty or every record dispositioned.
- OIDC, RLS, network policy, secret rotation, penetration test, and audit export verified.

## Failure handling

- **Kafka backlog:** scale workers by lag, inspect the DLQ, and avoid changing correlation thresholds during
  an active replay.
- **Model outage:** workers retry then dead-letter; ingestion and evidence persistence continue. Keep the
  tool catalog fail-closed.
- **Qdrant outage:** disable RAG only through reviewed configuration if operating without retrieved context
  is acceptable; otherwise halt workflow workers.
- **Controller timeout:** execution records failure, stops the saga, rolls back completed writes, and verifies
  restoration. An unknown timeout outcome requires controller idempotency support.
- **Database outage:** API readiness fails; Kubernetes removes it from service. Kafka retains unprocessed
  work and no offset is committed.
- **Redis outage:** dashboard invalidation may be stale, but authoritative state remains in PostgreSQL.
- **Compromised tool credential:** disable the tool in policy, rotate the secret, inspect audit and controller
  logs, and replay affected plan hashes.

## SLO signals

Export API latency/error rate, ingest rejection, Kafka lag, retry/DLQ counts, graph node latency, model
latency/token use, approval wait, tool latency/outcomes, verification failure, rollback outcomes, RAG hit
rate, database saturation, and SSE disconnects through OpenTelemetry and Prometheus. Page on safety-control
failures before availability symptoms.
