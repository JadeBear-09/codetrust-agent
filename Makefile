.PHONY: setup start check install test lint demo demo-offline demo-pr proof serve clean

setup:
	python3 start.py --setup-only --no-open

start:
	python3 start.py

check:
	python3 start.py --check

install:
	uv sync --extra dev

test:
	uv run pytest

lint:
	uv run ruff check .

demo:
	@status=0; uv run codetrust verify --ticket demo/tickets/payment-reconciliation.md --diff demo/patches/risky-payment.diff --output-dir reports || status=$$?; [ $$status -le 1 ]

demo-offline:
	@status=0; uv run codetrust verify --offline --ticket demo/tickets/payment-reconciliation.md --diff demo/patches/risky-payment.diff --output-dir reports || status=$$?; [ $$status -le 1 ]

demo-pr:
	@test -n "$(PR)" || (echo "Usage: make demo-pr PR=OWNER/REPO#NUMBER" && exit 2)
	@status=0; uv run codetrust verify --github-pr "$(PR)" --ticket demo/policies/codetrust-scope.md --offline --output-dir reports/public-pr || status=$$?; [ $$status -le 1 ]

proof:
	uv run python scripts/prove_demo.py

serve:
	uv run codetrust serve

clean:
	rm -f reports/*.json reports/*.md reports/*.html
