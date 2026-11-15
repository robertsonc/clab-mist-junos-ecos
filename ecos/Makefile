# Build vrnetlab/aruba_ecos:<version> from an ECV-*.qcow2 placed in this directory.
#
#   make                               # uses the only ECV-*.qcow2 here
#   make IMAGE=ECV-9.6.3.0_107217.qcow2
#
# Standalone: no vrnetlab checkout is needed, the base image carries vrnetlab.py.

IMAGE   ?= $(firstword $(wildcard ECV-*.qcow2))
VERSION  = $(patsubst ECV-%.qcow2,%,$(IMAGE))
TAG     ?= vrnetlab/aruba_ecos:$(VERSION)

.PHONY: build clean test

build:
	@test -n "$(IMAGE)" || { echo "ERROR: put an ECV-<version>.qcow2 in $(CURDIR)"; exit 1; }
	@test -f "$(IMAGE)" || { echo "ERROR: $(IMAGE) not found"; exit 1; }
	@# hardlink into the build context when possible: no multi-GB copy
	ln -f "$(IMAGE)" docker/ 2>/dev/null || cp "$(IMAGE)" docker/
	docker build --build-arg IMAGE="$(IMAGE)" -t "$(TAG)" docker; \
	  rc=$$?; rm -f "docker/$(IMAGE)"; exit $$rc
	@echo "built $(TAG)"

test:
	python3 -m unittest discover -s tests -v

clean:
	rm -f docker/*.qcow2
