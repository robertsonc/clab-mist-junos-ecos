#!/usr/bin/env python3
"""Create the THERMOPYLAE / TROY / MARATHON sites in Mist.

Nothing else in this toolset creates sites - mist_api.sites() only GETs a
name -> id map, and mist_rename.py refuses (correctly) when a site is missing
rather than silently assigning nothing. This fills that gap.

CREATE ONLY. It never updates or deletes, and it will not touch a site that
already exists - a second run is a no-op. Combined with the allow-list below
that means it cannot affect CF - Site1/2/3 or the SSR labs sharing this org,
even though the API key is org-wide.

Naming follows the org convention (`CF - Site1`), so these become
`CF - THERMOPYLAE` etc. mist_rename.py normalises spaces and dashes and
suffix-matches, so that resolves against the plain labels in labnodes.py.

    .venv/bin/python scripts/mist_site_create.py              # dry run, all three
    .venv/bin/python scripts/mist_site_create.py --yes
    .venv/bin/python scripts/mist_site_create.py --site troy --yes
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mist_api

# The ONLY sites this tool may create. Anything not here is refused.
SITES = ["thermopylae", "troy", "marathon"]

# Match the existing lab sites in this org.
PREFIX = "CF - "
TIMEZONE = "America/Los_Angeles"
COUNTRY = "US"


def site_name(label, prefix):
    return "%s%s" % (prefix, label.upper())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", choices=SITES,
                    help="just this one (default: all three)")
    ap.add_argument("--prefix", default=PREFIX,
                    help="name prefix, default %r to match the org" % PREFIX)
    ap.add_argument("--timezone", default=TIMEZONE)
    ap.add_argument("--country", default=COUNTRY)
    ap.add_argument("--yes", action="store_true", help="actually create")
    args = ap.parse_args()

    wanted = [args.site] if args.site else SITES
    assert set(wanted) <= set(SITES), "out-of-scope site requested"

    env = mist_api.load_env()
    existing = mist_api.sites(env)
    print("sites already in this org:")
    for n in sorted(existing):
        print("    %s" % n)
    print()

    plan = []
    for label in wanted:
        name = site_name(label, args.prefix)
        if name in existing:
            print("  %-22s EXISTS (%s) - leaving alone" % (name, existing[name]))
        else:
            print("  %-22s will CREATE" % name)
            plan.append(name)

    if not plan:
        print("\nnothing to do")
        return 0
    if not args.yes:
        print("\ndry run - re-run with --yes to create %d site(s)" % len(plan))
        return 0

    print()
    for name in plan:
        res = mist_api.org(env, "POST", "/sites", {
            "name": name,
            "timezone": args.timezone,
            "country_code": args.country,
        })
        print("  created %-22s id=%s" % (res.get("name"), res.get("id")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
