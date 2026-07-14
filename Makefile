.PHONY: install test lint demo demo-offline proof serve clean

install:
	uv sync --extra dev

test:
	uv run pytest

lint:
	uv run ruff check .

demo:
	uv run codetrust verify --ticket demo/tickets/payment-reconciliation.md --diff demo/patches/risky-payment.diff --output-dir reports

demo-offline:
	uv run codetrust verify --offline --ticket demo/tickets/payment-reconciliation.md --diff demo/patches/risky-payment.diff --output-dir reports

proof:
	uv run python scripts/prove_demo.py

serve:
	uv run codetrust serve

clean:
	rm -f reports/*.json reports/*.md reports/*.html
