# Shortcuts. Everything works the same typing the commands by hand.
VENV := .venv/bin

.PHONY: install test run json csv dash clean

install:            ## create the environment and install everything
	uv venv --python 3.12 .venv
	uv pip install --python $(VENV)/python -e ".[dashboard,dev]"

test:               ## 94 tests: layers 0 to 4, CLI and data contract
	$(VENV)/python -m pytest

run:                ## console analysis of both profiles
	$(VENV)/python -m balance.run

json:               ## the same analysis as JSON
	$(VENV)/python -m balance.run --format json

csv:                ## dump the daily and weekly frames into out/
	$(VENV)/python -m balance.run --csv out

dash:               ## dashboard
	$(VENV)/streamlit run app.py

clean:
	rm -rf .pytest_cache out **/__pycache__
