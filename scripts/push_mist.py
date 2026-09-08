#!/usr/bin/env python3
"""Push the Mist claim config to the lab's vJunos switches.

The stock claim snippet does not work unmodified on a vrnetlab-built node.
vrnetlab's init.conf sets `system management-instance`, which parks fxp0 in the
mgmt_junos VRF and leaves inet.0 with a *reject* default, so outbound-ssh cannot
reach Mist and DNS fails.

THE FIX IS ONE LINE:

    set system services outbound-ssh routing-instance mgmt_junos

The knob lives at `system services outbound-ssh`, NOT under
`client <name>` or under the client's address - which is where it is natural to
look for it, and why it is easy to conclude (wrongly) that outbound-ssh cannot
be pointed at a routing instance at all. Mist sets exactly this when you enable
**Dedicated Management VRF**, applied via configuration group `top`.

Keep `management-instance`. An earlier version of this script deleted it and
moved the default route into inet.0 instead. That works, but it rebuilds the
whole management model to solve a routing-instance binding, and it fights Mist
once the switch is adopted.

Each switch still gets two commits - the fixup, then the claim snippet -
because Junos auto-inserts the outbound-ssh routing-instance statement at
commit time while management-instance is active, and bundling both into one
commit races that insertion and trips the constraint check on some nodes.

Usage:
    python3 scripts/push_mist.py --all
    python3 scripts/push_mist.py 172.30.40.29 172.30.40.30
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import junos
from labnodes import SWITCHES, JUNOS_USER, JUNOS_PASSWORD, MGMT_DNS, MGMT_VRF

CLAIM = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "mist_claim_set.cfg")

# Present in the stock snippet but not on a vrnetlab image, where init.conf has
# already provisioned the box. Leaving it in just throws a syntax error.
SKIP = {"delete system phone-home"}

FIXUP = [
    "delete system services outbound-ssh",
    # The whole fix: bind outbound-ssh to the management VRF so it can route out
    # of fxp0. management-instance stays exactly as vrnetlab configured it.
    "set system services outbound-ssh routing-instance " + MGMT_VRF,
    # Resolver: SLIRP's built-in forwarder. External resolvers are unreachable
    # over QEMU user-mode networking by design.
    "delete system name-server",
    "set system name-server " + MGMT_DNS,
]


def claim_lines():
    out = []
    with open(CLAIM) as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and line not in SKIP:
                out.append(line)
    if not out:
        raise SystemExit("no usable lines in %s" % CLAIM)
    return out


def commit_batch(ip, cmds, label):
    c = junos.connect(ip, JUNOS_USER, JUNOS_PASSWORD)
    try:
        sh = junos.shell(c)
        junos.send(sh, "set cli screen-length 0", 1)
        junos.send(sh, "configure", 2)
        for cmd in cmds:
            reply = junos.send(sh, cmd, 1.2)
            if "syntax error" in reply or "unknown command" in reply:
                print("    %-8s config error on %r" % (label, cmd))
        reply = junos.send(sh, "commit and-quit", 30)
        if "commit complete" not in reply:
            print("    %-8s COMMIT FAILED: %s" % (label, reply.strip()[-300:]))
            return False
        return True
    finally:
        c.close()


def push(ip):
    if not commit_batch(ip, FIXUP, "routing"):
        return False
    return commit_batch(ip, claim_lines(), "claim")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hosts", nargs="*", help="mgmt IPs; omit with --all")
    ap.add_argument("--all", action="store_true", help="every switch in labnodes")
    args = ap.parse_args()

    if args.all:
        targets = [(n, ip) for n, ip, _ in SWITCHES]
    elif args.hosts:
        lookup = {ip: n for n, ip, _ in SWITCHES}
        targets = [(lookup.get(h, "?"), h) for h in args.hosts]
    else:
        ap.error("give one or more IPs, or --all")

    failed = []
    for name, ip in targets:
        try:
            ok = push(ip)
        except Exception as exc:
            print("  %-17s %-14s EXC %s: %s" % (name, ip, type(exc).__name__, exc))
            failed.append(name)
            continue
        print("  %-17s %-14s %s" % (name, ip, "OK" if ok else "FAILED"))
        if not ok:
            failed.append(name)
        sys.stdout.flush()

    print("\n%d/%d claimed" % (len(targets) - len(failed), len(targets)))
    if failed:
        print("failed: " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
