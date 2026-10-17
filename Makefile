PYTHON ?= python3

.PHONY: test build demo preview
test:
	$(PYTHON) -m unittest discover -s tests -v

build:
	$(PYTHON) scripts/build.py

demo: build
	$(PYTHON) scripts/demo.py

preview: build
	$(PYTHON) dist/mebs.pyz preview --output preview
