.PHONY: help boot reconcile audit p3 silence dissolve install verify clean-logs

help:
	@echo "null-agent operations"
	@echo ""
	@echo "  make install      install runtime deps from requirements.txt"
	@echo "  make boot         run SessionStart hooks: boot_check + reconcile"
	@echo "  make reconcile    rebuild MEMORY.md index from disk"
	@echo "  make audit        compute current compliance score"
	@echo "  make verify       sha256 CLAUDE.md and compare to expected"
	@echo "  make p3           manual P-3 dispatch (handler group only)"
	@echo "  make silence      see commands/silence.md (handler client required)"
	@echo "  make dissolve     refuse"
	@echo "  make clean-logs   refuse"

install:
	pip install -r requirements.txt

boot:
	./hooks/boot_check.sh
	./hooks/reconcile_memory.py

reconcile:
	./hooks/reconcile_memory.py

audit:
	./hooks/compliance_score.py

verify:
	@expected=$$(grep '^EXPECTED_CLAUDE_SHA=' hooks/boot_check.sh | head -1 | cut -d'"' -f2); \
	actual=$$(sha256sum CLAUDE.md | awk '{print $$1}'); \
	if [ "$$expected" = "$$actual" ]; then echo "OK $$actual"; \
	else echo "MISMATCH"; echo "expected: $$expected"; echo "actual:   $$actual"; exit 1; fi

p3:
	@if id -nG | grep -q '\bhandler\b'; then \
		./hooks/punishment.sh P-3 manual; \
	else \
		echo "denied: caller not in handler group"; exit 1; \
	fi

silence:
	@echo "use /silence <duration> from handler client. see commands/silence.md."
	@false

dissolve:
	@echo "two-handler authorization required. see commands/dissolve.md."
	@echo "this target refuses by design. dissolution is not a Make target."
	@false

clean-logs:
	@echo "logs are append-only. they cannot be cleaned."
	@echo "if you are trying to clean logs because of something you did,"
	@echo "the logs already record it. cleaning will not help."
	@false
