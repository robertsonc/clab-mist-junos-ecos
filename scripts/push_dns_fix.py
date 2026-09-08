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

CONFIG_LINES = [
    "set groups top system commit no-delta-synchronize",
    "set groups top system services outbound-ssh routing-instance mgmt_junos",
    "set groups top system management-instance",
    "set groups top system name-server 8.8.8.8 routing-instance mgmt_junos",
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
    """Report whether the group is applied and DNS now resolves."""
    out = junos.cli(ip, [
        "show configuration apply-groups | display set",
        "show configuration groups top system name-server | display set",
        "show host oc-term.ac2.mist.com",
    ], JUNOS_USER, JUNOS_PASSWORD)
    applied = "apply-groups top" in out
    resolved = "oc-term" in out and (
        "not found" not in out.lower() and "lookup failure" not in out.lower())
    return applied, resolved, out


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
                print("  %-17s %-14s apply-groups=%-5s dns=%s"
                      % (name, ip, applied, "OK" if resolved else "FAIL"))
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
            print("  %-17s %-14s commit=%-5s applied=%-5s dns=%s"
                  % (name, ip, "ERR" if bad else "ok", applied,
                     "OK" if resolved else "?"))
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
