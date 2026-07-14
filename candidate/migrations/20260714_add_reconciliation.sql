-- UP
ALTER TABLE payments ADD COLUMN reconciliation_state VARCHAR(32);
ALTER TABLE payments ADD COLUMN reconciliation_attempts INTEGER DEFAULT 0;
CREATE INDEX idx_payments_reconciliation ON payments(reconciliation_state);

-- ROLLBACK
DROP INDEX idx_payments_reconciliation;
ALTER TABLE payments DROP COLUMN reconciliation_attempts;
ALTER TABLE payments DROP COLUMN reconciliation_state;

