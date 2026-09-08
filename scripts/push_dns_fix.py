#!/usr/bin/env python3
"""Apply the Mist DNS/VRF fix to the fabric's vJunos switches.

WHY THIS EXISTS
---------------
push_mist.py applies `set system services outbound-ssh routing-instance
mgmt_junos`, which correctly binds the outbound-ssh TRANSPORT to the management
VRF. But name resolution does not go through outbound-ssh - the system resolver
queries via inet.0, which on a stock vrnetlab node has no default route at all.
So oc-term.ac2.mist.com never resolves, outbound-ssh has nothing to dial, and
adoption never begins.

The fix puts everything in configuration group `top` - the same group Mist itself
uses for Dedicated Management VRF - and points the resolver at a PUBLIC address
reachable through the VRF, rather than the SLIRP forwarder that is only reachable
from inet.0:

    set groups top system commit no-delta-synchronize
    set groups top system services outbound-ssh routing-instance mgmt_junos
    set groups top system management-instance
    set groups top system name-server 8.8.8.8 routing-instance mgmt_junos
    set apply-groups top

Note this KEEPS `management-instance` rather than deleting it. Deleting the
instance and moving the default into inet.0 also makes DNS work, but it fights
Mist once the switch is adopted and Dedicated Management VRF is enabled.

THE STATIC HOST MAPPINGS ARE NOT OPTIONAL EITHER
------------------------------------------------
The name-server line gets the FIRST resolution done, so a switch adopts fine
and looks healthy. But outbound-ssh's reconnect path calls getaddrinfo(), which
is libc reading /var/etc/resolv.conf - a file with no routing-instance
annotation, so the query leaves via inet.0, which has no routes here. The first
connection therefore works and every reconnection fails:

    outbound_ssh_connect_to_server: (mist) Connecting to server: oc-term...:2200
    outbound_ssh_populate_address_info: (mist) getaddrinfo() failed for:
        oc-term.ac2.mist.com: error 8 (Name does not resolve)

The failure mode is nasty because it is invisible until something drops the
session - then every switch that lost its connection retries every 60s forever
and never recovers. Pinning the ELB addresses removes DNS from the reconnect
path entirely.

Diagnosing this needs /var/log/outbound-ssh.log (the traceoptions file Mist
configures), NOT /var/log/messages - outbound-ssh writes nothing to the latter.
Note also that `ping <host> routing-instance mgmt_junos` and `show host <host>`
both query via inet.0 and fail even on a perfectly healthy switch, so neither
is evidence of anything.

    python3 scripts/push_dns_fix.py 172.30.44.21          # one switch
    python3 scripts/push_dns_fix.py --all                 # every switch in labnodes
    python3 scripts/push_dns_fix.py --all --verify-only   # no config, just report
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import junos
from labnodes import SWITCHES, JUNOS_USER, JUNOS_PASSWORD

# oc-term.ac2.mist.com sits behind an AWS ELB with several addresses. They are
# pinned here as static host mappings because outbound-ssh's RECONNECT path
# cannot resolve DNS at all - see the long comment below.
OC_TERM = "oc-term.ac2.mist.com"
OC_TERM_IPS = ["3.218.167.152", "98.94.119.178", "44.218.238.151"]

CONFIG_LINES = [
    "set groups top system commit no-delta-synchronize",
    "set groups top system services outbound-ssh routing-instance mgmt_junos",
    "set groups top system management-instance",
    "set groups top system name-server 8.8.8.8 routing-instance mgmt_junos",
] + [
    "set groups top system static-host-mapping %s inet %s" % (OC_TERM, ip)
    for ip in OC_TERM_IPS
] + [
    "set apply-groups top",
]


def apply_fix(ip):
    """Push the group + apply-groups and commit. Returns commit output."""
    c = junos.connect(ip, JUNOS_USER, JUNOS_PASSWORD)
    sh = junos.shell(c)
    junos._drain(sh, 1.0)
    junos.send(sh, "configure", wait=3)
    for line in CONFIG_LINES:
        junos.send(sh, line, wait=1.5)
    out = junos.send(sh, "commit and-quit", wait=45)
    try:
        c.close()
    except Exception:
        pass
    return out


def verify(ip):
    """Report whether the group is applied and the Mist session is actually up.

    Checks the outbound-ssh SESSION, not DNS. Two earlier attempts at a DNS
    check were both worthless:

      * matching "oc-term" in the output matched the ECHOED COMMAND, so an
        empty result read as success - a false positive;
      * `ping <host> routing-instance mgmt_junos` is a false NEGATIVE. It uses
        the system resolver on inet.0, which is dead by design here, so it
        reports "cannot resolve" even on a switch with a healthy, ESTABLISHED
        session to Mist. It says nothing about what outbound-ssh can resolve
        inside the VRF.

    An ESTABLISHED connection to port 2200 is the only signal that means the
    thing we actually care about is working.
    """
    out = junos.cli(ip, [
        "show configuration apply-groups | display set | no-more",
        "show system connections inet | match 2200 | no-more",
    ], JUNOS_USER, JUNOS_PASSWORD)
    applied = "apply-groups top" in out
    session = "ESTABLISHED" in out
    return applied, session, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hosts", nargs="*", help="mgmt IPs")
    ap.add_argument("--all", action="store_true", help="every switch in labnodes")
    ap.add_argument("--verify-only", action="store_true",
                    help="check state, change nothing")
    args = ap.parse_args()

    if args.all:
        targets = [(n, ip) for n, ip, _ in SWITCHES]
    elif args.hosts:
        lookup = {ip: n for n, ip, _ in SWITCHES}
        unknown = [h for h in args.hosts if h not in lookup]
        if unknown:
            # labnodes.py holds only this fabric, so this also blocks any
            # attempt to point the script at a Site 1/2/3 switch.
            ap.error("not in this fabric's inventory: %s" % ", ".join(unknown))
        targets = [(lookup[h], h) for h in args.hosts]
    else:
        ap.error("give one or more IPs, or --all")

    for name, ip in targets:
        if args.verify_only:
            try:
                applied, resolved, _ = verify(ip)
                print("  %-17s %-14s apply-groups=%-5s mist-session=%s"
                      % (name, ip, applied, "UP" if resolved else "DOWN"))
            except Exception as exc:
                print("  %-17s %-14s UNREACHABLE (%s)" % (name, ip, type(exc).__name__))
            sys.stdout.flush()
            continue

        try:
            out = apply_fix(ip)
            bad = any(w in out.lower() for w in ("error", "failed", "invalid"))
            # Do NOT trust the commit output alone. A commit that runs past the
            # wait returns empty, which contains none of the words above and so
            # reads as success - that silently skipped a switch once, and the
            # only symptom was that node never adopting. Read the config back.
            applied, resolved, _ = verify(ip)
            ok = applied and not bad
            print("  %-17s %-14s commit=%-5s applied=%-5s mist-session=%s"
                  % (name, ip, "ERR" if bad else "ok", applied,
                     "UP" if resolved else "down"))
            if not ok:
                print("      NOT APPLIED - re-run this host")
                if bad:
                    print("      %s" % out.replace("\n", " ")[:200])
        except Exception as exc:
            print("  %-17s %-14s EXCEPTION (%s)" % (name, ip, type(exc).__name__))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
