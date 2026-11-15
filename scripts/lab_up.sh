#!/usr/bin/env bash
# Deploy one or more topologies and make sure the containerlab web GUI is up.
#
#   scripts/lab_up.sh interop/ecos-junos-srx.clab.yml
#   scripts/lab_up.sh greek-fabric-{thermopylae,troy,marathon}.clab.yml
#
# Environment:
#   LAB_GUI=0            skip the web GUI
#   LAB_BOOT_SLOTS=4     start the next topology once fewer than this many VM
#                        nodes on the host are still booting
#   LAB_WAIT=0           return after the last deploy instead of waiting for
#                        every VM node to report healthy
#   LAB_TIMEOUT_SECS     give up waiting after this long (default 1800)
#
# Why the gate: `containerlab deploy` returns once the containers exist, not
# once the VMs inside them have booted. Deploying topologies back to back
# therefore boots every VM on the host at once, and they starve each other.
# Waiting for a full "all healthy" is the other extreme and leaves the host
# idle while one slow node finishes. The gate sits between the two.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUI_PORT="${CLAB_WEB_PORT:-3001}"
API_URL="${CLAB_API_URL:-https://localhost:8090}"
BOOT_SLOTS="${LAB_BOOT_SLOTS:-4}"
TIMEOUT="${LAB_TIMEOUT_SECS:-1800}"
HELPER_IMAGES=(lab-host lab-isp)
HELPER_TAG=1

log() { printf '%s %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

[ "$#" -ge 1 ] || die "usage: $0 <topology.clab.yml> [more.clab.yml ...]"
for topo in "$@"; do
    [ -f "$topo" ] || die "topology not found: $topo"
done
case "$BOOT_SLOTS" in ''|*[!0-9]*|0) die "LAB_BOOT_SLOTS must be a positive integer" ;; esac
case "$TIMEOUT" in ''|*[!0-9]*) die "LAB_TIMEOUT_SECS must be an integer" ;; esac
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

# Hosts and ISP routers run from small local images instead of installing
# packages on every deploy. Build them once; later runs find them and move on.
build_helper_images() {
    local name
    for name in "${HELPER_IMAGES[@]}"; do
        if ! docker image inspect "clab-${name}:${HELPER_TAG}" >/dev/null 2>&1; then
            log "building clab-${name}:${HELPER_TAG}"
            docker build -q -t "clab-${name}:${HELPER_TAG}" "$ROOT/images/${name}" >/dev/null \
                || die "could not build clab-${name}:${HELPER_TAG}"
        fi
    done
}

# containerlab refuses a bind whose host path is missing. EC-V nodes bind a
# per-node directory at /disk for their VM disk, so create those up front.
make_disk_dirs() {
    local topo="$1" dir src
    dir="$(cd "$(dirname "$topo")" && pwd)"
    while read -r src; do
        case "$src" in /*) mkdir -p "$src" ;; *) mkdir -p "$dir/$src" ;; esac
    done < <(sed -n 's/^[[:space:]]*-[[:space:]]*\([^:[:space:]]*\):\/disk\([[:space:]].*\)\{0,1\}$/\1/p' "$topo")
}

# VM nodes carry a Docker healthcheck that stays "starting" until the guest is
# up. Plain linux nodes have none, so they are never counted.
count_health() {
    docker ps -q --filter label=containerlab --filter "health=$1" | wc -l
}

# Wait until fewer than $1 VM nodes are booting. Returns 1 on timeout.
wait_booting_below() {
    local limit="$1" waited=0 n
    while :; do
        n="$(count_health starting)"
        [ "$n" -lt "$limit" ] && return 0
        [ "$waited" -ge "$TIMEOUT" ] && return 1
        sleep 10
        waited=$((waited + 10))
    done
}

START=$SECONDS
[ "${LAB_GUI:-1}" = "0" ] || start_gui
build_helper_images

first=1
for topo in "$@"; do
    if [ "$first" -eq 0 ]; then
        log "waiting for fewer than ${BOOT_SLOTS} VM nodes booting before ${topo}"
        wait_booting_below "$BOOT_SLOTS" \
            || die "still $(count_health starting) VM nodes booting after ${TIMEOUT}s; not starting ${topo}"
    fi
    first=0
    make_disk_dirs "$topo"
    log "deploying ${topo}"
    sudo containerlab deploy -t "$topo"
done

if [ "${LAB_WAIT:-1}" != "0" ]; then
    log "waiting for every VM node to report healthy"
    if wait_booting_below 1; then
        log "all VM nodes up in $((SECONDS - START))s; unhealthy: $(count_health unhealthy)"
    else
        log "WARN: $(count_health starting) VM nodes still booting after ${TIMEOUT}s:"
        docker ps --filter label=containerlab --filter health=starting --format '  {{.Names}}' >&2
        exit 1
    fi
fi
