.PHONY: build push run run_bash

REGISTRY       ?= docker.io
DOCKER_REPO     = tknorris
IMAGE           = tknorris/dyndns-updater
GIT_REVISION   ?= $(shell git rev-parse --short=8 HEAD)
IMAGE_TAG       = $(REGISTRY)/$(IMAGE):$(GIT_REVISION)
IMAGE_LATEST    = $(REGISTRY)/$(IMAGE):latest

default: latest

latest: build staging
staging: tag-version push-version push

build:
	docker build -t $(IMAGE_LATEST) .

build-nc:
	docker build --no-cache -t $(IMAGE_LATEST) .

tag-version:
	docker tag $(IMAGE_LATEST) $(IMAGE_TAG)

push:
	docker push $(IMAGE_LATEST)

push-version:
	docker push $(IMAGE_TAG)

run:
	docker run -it -p 8000:8000 --env-file ./updater.env --rm -v ${PWD}:/config:ro $(IMAGE_LATEST)

run_bash:
	docker run -it -p 8000:8000 --env-file ./updater.env --rm -v ${PWD}:/config:ro $(IMAGE_LATEST) bash

version:
	@echo $(GIT_REVISION)

registry:
	@echo $(REGISTRY)
	
image:
	@echo $(IMAGE_TAG)
