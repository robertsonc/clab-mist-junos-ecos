# Helper images used by the topologies. Bump TAG when a Dockerfile changes,
# and update the tag in gen_greek_topology.py and interop/*.clab.yml to match.
TAG ?= 1

.PHONY: all lab-host lab-isp
all: lab-host lab-isp

lab-host lab-isp:
	docker build -t clab-$@:$(TAG) $@
