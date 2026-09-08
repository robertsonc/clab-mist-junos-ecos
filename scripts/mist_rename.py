#!/usr/bin/env python3
"""Push the clab node names back into Mist, and put each switch in its site.

On adoption Mist overwrites the device hostname with its MAC (020004519d78), so
the S1-/S2- names disappear from the boxes and the portal is a wall of hex. The
reliable way to recover the mapping is to ask each switch what MAC Mist gave it:
Mist rewrites the local config to

    set system services outbound-ssh client mist device-id <org-uuid>.<mac>

so the box itself carries the join key. Chassis MAC and fxp0 MAC are both
unrelated to what Mist displays - do not try to match on those.

    python3 scripts/mist_rename.py --site troy          # dry run
    python3 scripts/mist_rename.py --site troy --yes

--site is REQUIRED here. The upstream version allowed an unscoped run because
each host could only reach its own switches; this host reaches all three, and
the Mist API key is org-wide, so an unscoped run could reassign or rename
switches belonging to Sites 1/2/3 in the portal. It refuses instead.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import junos
import mist_api
from labnodes import SWITCHES, JUNOS_USER, JUNOS_PASSWORD

# The only site labels this tool may ever act on. labnodes.py for this fabric
# lists nothing else, so this is belt-and-braces - but the Mist API key is
# org-wide and would happily rename a Site 1 switch, so assert it anyway.
SITES = ["thermopylae", "troy", "marathon"]
ALLOWED = {s.upper() for s in SITES}


def mist_mac(ip):
    """The MAC Mist assigned, read out of the device-id it wrote back."""
    out = junos.cli(ip,
                    ["show configuration system services outbound-ssh "
                     "| display set | match device-id"],
                    JUNOS_USER, JUNOS_PASSWORD)
    for line in out.splitlines():
        if "device-id" in line and "match" not in line:
            m = re.search(r"device-id\s+[0-9a-f-]+\.([0-9a-f]{12})", line)
            if m:
                return m.group(1)
    return None


def resolve_site(site_ids, label):
    """Map a labnodes site label onto the real Mist site id.

    labnodes calls them Site1/Site2/Site3 but the portal names drift - they
    have been 'CF - Site1' and 'CF - Site2'. Exact match first, then any site
    whose name ends with the label once spaces and dashes are stripped.

    A new site has to EXIST in the portal first. If Site 3 was never created
    there, this returns None and the run reports it rather than silently
    assigning nothing.

    Returns None if it cannot be resolved unambiguously. Do NOT fall back to
    site_ids.get(label): that yields None, which compares equal to the missing
    site_id of an unassigned device and makes a broken run print 'site=ok'.
    """
    if label in site_ids:
        return site_ids[label]
    norm = lambda s: s.replace(" ", "").replace("-", "").lower()
    want = norm(label)
    hits = [sid for name, sid in site_ids.items() if norm(name).endswith(want)]
    return hits[0] if len(hits) == 1 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="apply the changes")
    ap.add_argument("--site", choices=SITES, required=True,
                    help="which site to act on. REQUIRED and deliberately has "
                         "no 'all': an unscoped run over an org-wide API key is "
                         "how you touch devices you did not mean to.")
    args = ap.parse_args()

    env = mist_api.load_env()
    site_ids = mist_api.sites(env)
    inv = {d["mac"]: d for d in mist_api.inventory(env)}

    stray = {s[2] for s in SWITCHES} - ALLOWED
    if stray:
        print("REFUSING TO RUN: labnodes.py contains out-of-scope sites: %s"
              % ", ".join(sorted(stray)))
        return 2

    targets = SWITCHES
    if args.site:
        want = args.site.upper()
        targets = [s for s in SWITCHES if s[2] == want]
        print("limiting to %s (%d switches)\n" % (want, len(targets)))

    # Resolve every site label up front so a naming mismatch fails here, loudly,
    # instead of halfway through the apply loop.
    wanted = sorted({s[2] for s in targets})
    resolved = {}
    for label in wanted:
        sid = resolve_site(site_ids, label)
        if not sid:
            print("cannot resolve site %r in Mist. Sites present: %s"
                  % (label, ", ".join(sorted(site_ids))))
            return 1
        resolved[label] = sid
        print("  site %-6s -> %s" % (label, sid))
    print()

    plan = []
    for name, ip, site in targets:
        try:
            mac = mist_mac(ip)
        except Exception as exc:
            print("  %-17s %-14s UNREACHABLE (%s)" % (name, ip, type(exc).__name__))
            continue
        if not mac:
            print("  %-17s %-14s not adopted yet (no device-id)" % (name, ip))
            continue
        if mac not in inv:
            print("  %-17s %-14s %s not in Mist inventory" % (name, ip, mac))
            continue
        cur = inv[mac]
        need_site = cur.get("site_id") != resolved[site]
        need_name = cur.get("name") != name
        print("  %-17s %-14s %s  site=%s name=%s" % (
            name, ip, mac,
            "MOVE" if need_site else "ok", "SET" if need_name else "ok"))
        if need_site or need_name:
            plan.append((name, mac, site))
        sys.stdout.flush()

    if not plan:
        print("\nnothing to change")
        return 0
    if not args.yes:
        print("\ndry run - re-run with --yes to apply %d change(s)" % len(plan))
        return 0

    for name, mac, site in plan:
        sid = resolved[site]
        # A device with no site cannot be named, so assign first.
        mist_api.org(env, "PUT", "/inventory",
                     {"op": "assign", "site_id": sid, "macs": [mac], "managed": True})
        res = mist_api.call(env, "PUT", "/sites/%s/devices/%s"
                            % (sid, mist_api.device_id(mac)), {"name": name})
        print("  %-17s -> %s (%s)" % (name, res.get("name"), site))
    return 0


if __name__ == "__main__":
    sys.exit(main())
