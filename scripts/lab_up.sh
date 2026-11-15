#!/usr/bin/env bash
# Deploy one or more topologies and make sure the containerlab web GUI is up.
#
#   scripts/lab_up.sh interop/ecos-junos-srx.clab.yml
#   scripts/lab_up.sh greek-fabric-{thermopylae,troy,marathon}.clab.yml
#
# The GUI is on by default. LAB_GUI=0 skips it.
# Topologies deploy one after another: booting them in parallel makes the VMs
# contend and none of them come up cleanly.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUI_PORT="${CLAB_WEB_PORT:-3001}"
API_URL="${CLAB_API_URL:-https://localhost:8090}"

log() { printf '%s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

[ "$#" -ge 1 ] || die "usage: $0 <topology.clab.yml> [more.clab.yml ...]"
for topo in "$@"; do
    [ -f "$topo" ] || die "topology not found: $topo"
done
command -v containerlab >/dev/null || die "containerlab is not installed"
command -v docker >/dev/null || die "docker is not installed"

start_gui() {
    docker compose version >/dev/null 2>&1 \
        || { log "WARN: docker compose plugin missing; web GUI not started"; return; }
    docker compose -f "$ROOT/gui/compose.yml" up -d \
        || { log "WARN: web GUI failed to start; continuing with the deploy"; return; }
    log "web GUI: https://$(hostname -f 2>/dev/null || hostname):${GUI_PORT}"

    # The GUI is only a front end. Without clab-api-server it shows a login
    # page that cannot log in, so say so instead of leaving that to be found.
    # -k: the API server's default certificate is self-signed.
    if ! curl -ksS --max-time 5 -o /dev/null "${API_URL}/health"; then
        log "WARN: clab-api-server is not answering at ${API_URL}."
        log "      The GUI cannot log in until it is. See README, 'Web GUI'."
    fi
}

if [ "${LAB_GUI:-1}" != "0" ]; then
    start_gui
fi

for topo in "$@"; do
    log "deploying ${topo}"
    sudo containerlab deploy -t "$topo"
done
