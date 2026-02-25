.PHONY: test regression lint

test: regression
	@echo "✅ All checks passed"

regression:
	python scripts/replay.py --cases scripts/safety_regression_cases.json

lint:
	python -m compileall app
