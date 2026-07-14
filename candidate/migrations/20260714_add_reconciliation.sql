ALTER TABLE payments ADD COLUMN reconciliation_state VARCHAR(32);
ALTER TABLE payments ADD COLUMN reconciliation_attempts INTEGER DEFAULT 0;
CREATE INDEX idx_payments_reconciliation ON payments(reconciliation_state);

