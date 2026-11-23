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

.PHONY: install lint test validate gate build publish up version ci train register champion ask profile kg-version \
	kg-release kg-load kg-count kg-ask kg-clean kg-check

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
	docker build --build-arg APP_VERSION=$(VERSION) -t $(IMAGE):$(VERSION) -t $(IMAGE):$(VERSION)-$(GIT_SHA) $(LABELS) .

publish:
	docker push $(IMAGE):$(VERSION)
	docker push $(IMAGE):$(VERSION)-$(GIT_SHA)

up:
	APP_VERSION=$(VERSION) docker compose up -d --build

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

# Session 7: the staff questions, answered through the log alone and through the operator's knowledge.
# ROUTE=keyword or ROUTE=knowledge runs one route; SHOW=--show lists what each route counted.
ROUTE ?= both
SHOW ?=
ask:
	gozo-ask questions --route $(ROUTE) $(SHOW)

profile:
	gozo-ask profile

# Session 7: the knowledge has a version of its own, kept in one place, kg/schema.yaml, and separate from the code's.
# A release of the knowledge is an annotated git tag on a commit whose tests pass, and a tag is never reused:
# git refuses to create one that exists. Push it with: git push origin kg-v$(KG_VERSION)
KG_VERSION := $(shell sed -n 's/^version: "\(.*\)"$$/\1/p' kg/schema.yaml)
kg-version:
	@echo $(KG_VERSION)

# The tag records the fingerprint of the store the release gives.
STORE_SHA = $$(sha256sum kg/build/gozo.nt | cut -c1-16)
kg-release: test kg-check
	@git diff --quiet HEAD || \
		{ echo "Commit your changes before releasing the knowledge."; exit 1; }
	git tag -a kg-v$(KG_VERSION) \
		-m "Gozo ferry knowledge $(KG_VERSION); store sha256 $(STORE_SHA)"
	@echo "Push the tag with: git push origin kg-v$(KG_VERSION)"

# Session 7, Stage 17: the knowledge layer as an RDF graph, in the store kg/build/gozo.nt.
# kg-load is safe to run again; kg-clean empties the store, for a rebuild from the files.
kg-load:
	gozo-kg load

kg-count:
	gozo-kg count

kg-ask:
	gozo-kg ask

kg-clean:
	rm -f kg/build/gozo.nt

# What make ci checks: the store built from nothing, loaded a second time without change, and the questions
# answered from the store as written. It leaves that store in kg/build/gozo.nt, the artefact that was checked.
kg-check:
	gozo-kg check

version:
	@echo $(VERSION)

# The whole pipeline, in order. make stops at the first command that exits non-zero.
ci: lint test validate gate kg-check build
