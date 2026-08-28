# Atajos. Todo funciona igual escribiendo los comandos a mano.
VENV := .venv/bin

.PHONY: install test run dash clean

install:            ## crea el entorno e instala todo, incluido el dashboard
	uv venv --python 3.12 .venv
	uv pip install --python $(VENV)/python -e ".[dashboard,dev]"

test:               ## 91 tests: capas 0 a 4, CLI y contrato de datos
	$(VENV)/python -m pytest

run:                ## análisis de los dos perfiles por consola
	$(VENV)/python -m balance.run

json:               ## el mismo análisis en JSON
	$(VENV)/python -m balance.run --format json

csv:                ## vuelca los frames diario y semanal a out/
	$(VENV)/python -m balance.run --csv out

dash:               ## dashboard
	$(VENV)/streamlit run app.py

clean:
	rm -rf .pytest_cache out **/__pycache__
