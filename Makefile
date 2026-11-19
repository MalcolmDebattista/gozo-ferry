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
# Session 6: another training window for one run, e.g. make register TRAIN_START=2025-03-01 (none = every day)
TRAIN_START ?=

.PHONY: install lint test validate gate build publish up version ci train register champion

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

# Session 6: train and track a run, then register it only if it passed the gate and came from committed code.
train:
	gozo-train $(if $(TRAIN_START),--train-start $(TRAIN_START))

register: train
	gozo-registry register

# Point the champion alias at version V and restart the API, which loads it at start-up.
# Rolling back is the same command with the previous version: make champion V=1
champion:
	gozo-registry alias champion $(V)
	docker compose restart api

version:
	@echo $(VERSION)

# The whole pipeline, in order. make stops at the first command that exits non-zero.
ci: lint test validate gate build
