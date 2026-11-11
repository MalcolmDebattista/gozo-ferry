# The pipeline as a program (Session 5). Every target is a command you already know.
# Recipes must start with a TAB, not spaces.

# One version, in one place: pyproject.toml. Everything else reads it.
VERSION := $(shell python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])")
IMAGE ?= gozo-ferry
# Each image also carries the commit it was built from, so a tag is never reused for different code.
GIT_SHA := $(shell git rev-parse --short HEAD 2>/dev/null || echo nogit)
# On GitHub the workflow passes SOURCE, the repository address. The label links the image to the repository,
# and ghcr.io refuses a push from the workflow without it.
SOURCE ?=
LABELS := $(if $(SOURCE),--label org.opencontainers.image.source=$(SOURCE))
GATE_SPLIT ?= holdout

.PHONY: install lint test validate gate build publish up version ci

install:
	python3 -m pip install -r requirements.txt
	python3 -m pip install --no-deps -e ".[dev]"

lint:
	ruff check src tests

test:
	pytest -q

validate:
	gozo-validate

gate:
	gozo-gate --split $(GATE_SPLIT)

build:
	docker build --build-arg MODEL_VERSION=$(VERSION) -t $(IMAGE):$(VERSION) -t $(IMAGE):$(VERSION)-$(GIT_SHA) $(LABELS) .

publish:
	docker push $(IMAGE):$(VERSION)
	docker push $(IMAGE):$(VERSION)-$(GIT_SHA)

up:
	MODEL_VERSION=$(VERSION) docker compose up -d --build

version:
	@echo $(VERSION)

# The whole pipeline, in order. make stops at the first command that exits non-zero.
ci: lint test validate gate build
