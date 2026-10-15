#!/bin/sh
# Continuous traffic generator for the greek-fabric test hosts.
#
# Ported from mist_and_ec_fabric/scripts/vm_trafgen.sh. Same purpose: keep
# frames flowing so the fabric has something to learn and forward (a switch
# only learns a MAC when it sees a frame, and an idle host emits nothing), and
# leave a live reachability matrix in the log while the fabric is worked on.
#
# Targets are derived from the host's own eth1 address, so the same script runs
# unmodified on every VM:
#
#   gw        local anycast gateway, 10.<site>.<net>.1   (fabric IRB)
#   <vm>      every OTHER VM in VMS that shares this VM's VRF - same site
#             (intra-VLAN, L2) and remote sites (EVPN -> EC -> SD-WAN overlay)
#   net8/net1 8.8.8.8 and 1.1.1.1, two targets so an ECMP split between the
#             borders shows up as one ok and one ..
#
# Differences from the sister lab's script:
#
# * Sites are 5/6/7 (THERMOPYLAE/TROY/MARATHON), still read from the SECOND
#   octet of the host address.
# * The gateway comes from this VM's own subnet, not a hardcoded .10: a VM on
#   the GUEST VLAN (10.<site>.12.0/24) has its gateway at 10.<site>.12.1.
# * Peers come from the explicit VMS list and are filtered to the same VRF
#   (same third octet - .10 corp, .11 iot, .12 guest). Probing across VRFs
#   would only ever print .., since CORP and GUEST do not route to each other.
# * No cec1/cec2: the greek EC-Vs have no address inside the CORP segment
#   (their only loopback is lo0 in Default), so there is nothing to probe.
# * net8/net1 print -- unless the default route is via eth1. As deployed the
#   VMs default via eth0 (management), where an internet ping succeeds whether
#   or not the fabric works - the false positive the sister lab hit on
#   2026-08-13. Flip a VM with mist_and_ec_fabric/scripts/vm_default_via_fabric.sh
#   if the breakout path should be tested.
#
# Writes a timestamped one-line matrix to LOG each cycle. Run detached; stop
# with:  pkill -f '[v]m_trafgen'
# (the bracket stops pkill matching the shell that typed the command)
#
#   ok = reply   .. = no reply   -- = not probed
set -u
LOG=${LOG:-/tmp/trafgen.log}
INTERVAL=${INTERVAL:-5}

# Every lab VM, by eth1 address. Add a VM here and on every host it should
# reach. Order sets the column order in the log.
VMS=${VMS:-"10.5.10.11 10.5.10.12 10.6.10.11 10.6.10.12 10.7.10.11 10.7.10.12 10.7.12.11"}

MYIP=$(ip -4 -o addr show eth1 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
[ -z "$MYIP" ] && { echo "no eth1 address - is this a lab VM?" >&2; exit 1; }

SITE=$(echo "$MYIP" | cut -d. -f2)
NET=$(echo "$MYIP" | cut -d. -f3)
case "$SITE" in
  5|6|7) ;;
  *) echo "address $MYIP implies site $SITE, not one of 5/6/7" >&2; exit 1 ;;
esac
GW="10.$SITE.$NET.1"

# Peers: everyone in VMS except me, same VRF only.
PEERS=""
for v in $VMS; do
    [ "$v" = "$MYIP" ] && continue
    [ "$(echo "$v" | cut -d. -f3)" = "$NET" ] && PEERS="$PEERS $v"
done

# Short column label: 10.6.10.12 -> 6.12
label() { echo "$1" | awk -F. '{print $2"."$4}'; }

p() { ping -c1 -W1 "$1" >/dev/null 2>&1 && printf ok || printf '..'; }

if ip -4 route show default | grep -q 'dev eth1'; then NETTEST=yes; else NETTEST=no; fi

echo "$(date +%T) trafgen start on $MYIP (site $SITE) -> gw=$GW peers=${PEERS:- none} net=$([ $NETTEST = yes ] && echo 8.8.8.8,1.1.1.1 || echo 'skipped, default via eth0')" >> "$LOG"

while :; do
    line="$(date +%T)  gw:$(p $GW) "
    for v in $PEERS; do
        line="$line $(label $v):$(p $v)"
    done
    if [ $NETTEST = yes ]; then
        line="$line  net8:$(p 8.8.8.8) net1:$(p 1.1.1.1)"
    else
        line="$line  net8:-- net1:--"
    fi
    echo "$line" >> "$LOG"
    # keep the log from growing without bound over a long soak
    if [ "$(wc -l < "$LOG")" -gt 5000 ]; then tail -2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"; fi
    sleep "$INTERVAL"
done
