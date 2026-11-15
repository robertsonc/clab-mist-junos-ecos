# The base image already carries vrnetlab.py, healthcheck.py, qemu, genisoimage,
# HEALTHCHECK and ENTRYPOINT (`uv run /launch.py`), so nothing is installed here.
FROM ghcr.io/srl-labs/vrnetlab-base:0.3.0

ARG IMAGE
COPY $IMAGE /
COPY launch.py /

# ssh, Appliance Manager / REST, serial console
EXPOSE 22 80 443 5000
