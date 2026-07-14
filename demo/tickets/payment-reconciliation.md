# Add asynchronous payment reconciliation

## Goal

Reconcile pending payments concurrently so regional market adapters finish within the five-minute settlement window.

## Acceptance criteria

- Retry transient provider timeouts up to three times.
- Never charge or reconcile one payment more than once.
- Preserve compatibility with existing market adapters.
- Support safe rollback without losing in-flight payment state.
- Add tests for success, timeout, duplicate delivery, and rollback behavior.

