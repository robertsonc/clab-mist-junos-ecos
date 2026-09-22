#!/usr/bin/env python3
"""Create the THERMOPYLAE / TROY / MARATHON sites in Mist.

Nothing else in this toolset creates sites - mist_api.sites() only GETs a
name -> id map, and mist_rename.py refuses (correctly) when a site is missing
rather than silently assigning nothing. This fills that gap.

It also writes the DNS/VRF lines from mist_site_cli.py into each site's
additional_config_cmds, so that Mist itself pushes them. Without them the first
Mist push after adoption strips the on-box bootstrap from push_dns_fix.py, and
every switch goes dark at its next session drop (README "Mist must own the
config"). Run it BEFORE claiming switches.

It never deletes, and it never renames or re-creates a site that already
exists. On an existing site it only CHECKS the CLI lines and reports drift;
`--fix-cli` is needed to write them. Combined with the allow-list below that
means it cannot affect CF - Site1/2/3 or the SSR labs sharing this org, even
though the API key is org-wide.

Naming follows the org convention (`CF - Site1`), so these become
`CF - THERMOPYLAE` etc. mist_rename.py normalises spaces and dashes and
suffix-matches, so that resolves against the plain labels in labnodes.py.

    .venv/bin/python scripts/mist_site_create.py              # dry run, all three
    .venv/bin/python scripts/mist_site_create.py --yes
    .venv/bin/python scripts/mist_site_create.py --site troy --yes
    .venv/bin/python scripts/mist_site_create.py --fix-cli --yes   # repair drift

The dry run exits 1 when any site's CLI lines have drifted, so it doubles as a
periodic Mist-side check alongside `push_dns_fix.py --all --verify-only`.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mist_api
import mist_site_cli

# The ONLY sites this tool may create. Anything not here is refused.
SITES = ["thermopylae", "troy", "marathon"]

# Match the existing lab sites in this org.
PREFIX = "CF - "
TIMEZONE = "America/Los_Angeles"
COUNTRY = "US"


def site_name(label, prefix):
    return "%s%s" % (prefix, label.upper())


def template_cmds(env):
    """additional_config_cmds of the org template, which a site list overrides."""
    for t in mist_api.org(env, "GET", "/networktemplates"):
        if t.get("name") == mist_site_cli.TEMPLATE_NAME:
            return t.get("additional_config_cmds") or []
    # Fail closed: writing without the template's lines would silently drop
    # them from every switch in the site.
    raise SystemExit("template %r not found - refusing to write site CLI"
                     % mist_site_cli.TEMPLATE_NAME)


def write_cli(env, site_id, current, tpl):
    """Set the site's CLI list and read it back. Returns True if it landed."""
    want = mist_site_cli.merged(tpl + list(current or []))
    mist_api.call(env, "PUT", "/sites/%s/setting" % site_id,
                  {"additional_config_cmds": want})
    got = mist_api.call(env, "GET", "/sites/%s/setting" % site_id)
    return got.get("additional_config_cmds") == want


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", choices=SITES,
                    help="just this one (default: all three)")
    ap.add_argument("--prefix", default=PREFIX,
                    help="name prefix, default %r to match the org" % PREFIX)
    ap.add_argument("--timezone", default=TIMEZONE)
    ap.add_argument("--country", default=COUNTRY)
    ap.add_argument("--fix-cli", action="store_true",
                    help="also write the DNS/VRF CLI lines to existing sites")
    ap.add_argument("--yes", action="store_true", help="actually write")
    args = ap.parse_args()

    wanted = [args.site] if args.site else SITES
    assert set(wanted) <= set(SITES), "out-of-scope site requested"

    env = mist_api.load_env()
    existing = mist_api.sites(env)
    tpl = template_cmds(env)
    print("sites already in this org:")
    for n in sorted(existing):
        print("    %s" % n)
    print()

    create, fix, drift = [], [], False
    for label in wanted:
        name = site_name(label, args.prefix)
        if name not in existing:
            print("  %-22s will CREATE (with DNS/VRF CLI)" % name)
            create.append(name)
            continue
        sid = existing[name]
        cur = mist_api.call(env, "GET", "/sites/%s/setting" % sid).get(
            "additional_config_cmds") or []
        gone = mist_site_cli.missing(cur)
        if not gone:
            print("  %-22s EXISTS  cli=ok" % name)
            continue
        drift = True
        print("  %-22s EXISTS  cli=MISSING %d line(s):" % (name, len(gone)))
        for line in gone:
            print("        %s" % line)
        if args.fix_cli:
            fix.append((name, sid, cur))

    if not create and not fix:
        if drift:
            print("\nCLI drift - re-run with --fix-cli --yes to repair")
            return 1
        print("\nnothing to do")
        return 0
    if not args.yes:
        print("\ndry run - re-run with --yes to create %d / fix %d site(s)"
              % (len(create), len(fix)))
        return 1 if drift else 0

    print()
    ok = True
    for name in create:
        res = mist_api.org(env, "POST", "/sites", {
            "name": name,
            "timezone": args.timezone,
            "country_code": args.country,
        })
        landed = write_cli(env, res["id"], [], tpl)
        ok &= landed
        print("  created %-22s id=%s cli=%s"
              % (res.get("name"), res.get("id"), "ok" if landed else "FAILED"))
    for name, sid, cur in fix:
        # Mist pushes to every connected switch in the site when this changes.
        landed = write_cli(env, sid, cur, tpl)
        ok &= landed
        print("  fixed   %-22s cli=%s" % (name, "ok" if landed else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
