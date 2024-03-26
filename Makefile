
# Find OS and ARCH to download the correct micromamba
OSNAME := $(shell uname -s)
ifeq (${OSNAME}, Linux)
	OS := linux
else ifeq (${OSNAME}, Darwin)
	OS := osx
endif
ARCH := $(shell uname -m)
ifeq (${ARCH}, x86_64)
	ARCH := 64
endif

default: run

.bin/micromamba: ## download micromamba
	mkdir -p .bin
	cp etc/.mambarc .bin/.mambarc
	curl -Ls https://micro.mamba.pm/api/micromamba/${OS}-${ARCH}/latest | tar -xvj --strip-components=1 -C .bin bin/micromamba

.bin/envs/sv: .bin/micromamba etc/environment.yml ## create micromamba env
	.bin/micromamba --no-env -r ${PWD}/.bin create -f etc/environment.yml

.PHONY: bash
	bash

clean: ## delete micromamba env
	rm -rf .bin/

run: .bin/envs/sv ## [DEFAULT] run the stream viewer
	.bin/envs/sv/bin/python stream-viewer.py 

help: # from compiler explorer
	@grep -E '^[0-9a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'