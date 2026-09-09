#!/usr/bin/env python3
"""EC-V onboarding for the Greek fabric: preconfigs + approval, end to end.

Self-contained (stdlib only). Deliberately does NOT depend on the external
EC_SD-WAN_Expert repo - that tool was used to discover this API, but a lab that
has to be redeployed on other hosts should not need it installed.

    python3 scripts/ecv_onboard.py list                 # preconfigs + discovered
    python3 scripts/ecv_onboard.py validate             # check YAML, change nothing
    python3 scripts/ecv_onboard.py push                 # create/update preconfigs
    python3 scripts/ecv_onboard.py approve              # approve discovered EC-Vs
    python3 scripts/ecv_onboard.py approve --dry-run    # show what would be approved

Credentials: ORCH_URL and ORCH_API_KEY, from greek-fabric/.env.

=============================================================================
HARD-WON API NOTES - each of these cost a failed request to discover
=============================================================================

1. THE SCHEMA IS SELF-DOCUMENTING. Do not guess it.
       GET /gms/appliance/preconfiguration/default
   returns {"configData": "<base64>"} holding a ~3600-line YAML template with
   inline comments for every field. `ecv_onboard.py template` saves it.

2. VALIDATE BEFORE PUSHING. It names the exact offending field:
       POST /gms/appliance/preconfiguration/validate {name, configData}
       -> 400 'YAML invalid, Unrecognized field: "hostname"'
   That error loop is how this schema was mapped. Top-level keys are ONLY
   applianceInfo / deploymentInfo / templateGroups (+ the other documented
   sections). NOT: deployment, modeIfs, sysConfig, interfaces, hostname.

3. DHCP WAN INTERFACES need `addressingMode: dhcpv4` with ipAddressMask and
   nextHop left EMPTY. `ipAddressMask: dhcp` is rejected.

4. THE FIELD IS `behindNat`, lowercase "at" - even though the template's own
   comment block spells it `behindNAT`. The comment is wrong, the parser wins.

5. `interfaceLabel` is a label NAME that must already exist in Orchestrator
   (GET /gms/interfaceLabels), not a numeric id. Ours: wan INET1/INET2, lan Data.

6. APPROVAL REQUIRES AN EMPTY JSON BODY. This is the big one:
       POST /appliance/discovered/approve?id=<id>          -> HTTP 500
       POST /appliance/discovered/approve?id=<id>  body {} -> HTTP 200 "22.NE"
   Same URL, same headers. Without a body the server 500s with
   "There was an internal server error." - which reads like an Orchestrator
   fault rather than a malformed request. It returns the new nePk on success.
   The `id` comes from GET /appliance/discovered (NOT the serial or nePk).

7. autoApply ONLY FIRES AT DISCOVERY/APPROVAL TIME. If the appliance was
   discovered before the preconfig existed - or approved first - nothing ever
   binds. The preconfig sits at taskstatus=0, completionstatus=False,
   nepk=None, result=[] while the appliance reaches state=Normal carrying NO
   data-plane config at all. Nothing looks wrong until you inspect
   GET /deployment?nePk=X and find only mgmt0. Recovery is an explicit apply:
       POST /gms/appliance/preconfiguration/apply?preconfigId=X&nePk=Y  body {}
   (`ecv_onboard.py apply`). The `discovered` variant takes discoveredId.

8. UPDATING A PRECONFIG USES `preconfigId`, NOT `id`. PUT with ?id= returns 400.

9. APPLY IS MULTI-STAGE AND REBOOTS THE APPLIANCE. Watch it with
       GET /gms/appliance/preconfiguration/apply?preconfigId=X
   which returns a per-section result list. Order is: Appliance Info -> Zones/
   labels/Segments -> license -> deployment (interfaces) -> REBOOT -> template
   -> overlays -> routes -> BGP -> loopback. The top-level completionstatus
   stays False until every section finishes, and GET /deployment returns
   nothing at all while the appliance is rebooting - that is normal, not a
   failure. `ecv_onboard.py status --detail` shows the sections.

10. AFTER A containerlab destroy/redeploy, appliances re-register with NEW
   serials, so `discovered` accumulates ghosts. Match on discoveredTime against
   the container creation time; approving a ghost creates a dead appliance.
   This script refuses duplicates unless --allow-duplicates is given.
"""
import argparse
import base64
import glob
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRECONFIG_DIR = os.path.join(ROOT, "preconfigs")

# Only these appliances may ever be written to. Sites 1/2/3 share this
# Orchestrator and must not be touched by anything in this fabric.
ALLOWED = {
    "TH-ecv-01", "TH-ecv-02",
    "TR-ecv-01", "TR-ecv-02",
    "MA-ecv-01", "MA-ecv-02",
}


def load_env(path=None):
    path = path or os.path.join(ROOT, ".env")
    env = {}
    if not os.path.exists(path):
        raise SystemExit("missing %s" % path)
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    for key in ("ORCH_URL", "ORCH_API_KEY"):
        if not env.get(key):
            raise SystemExit("%s not set in %s" % (key, path))
    return env


def call(env, method, path, body=None, params=None, timeout=90):
    """One REST call. `body` may be {} - see note 6, that matters for approve."""
    host = env["ORCH_URL"].replace("https://", "").replace("http://", "").strip("/")
    url = "https://%s/gms/rest/%s" % (host, path.lstrip("/"))
    if params:
        url += "?" + "&".join("%s=%s" % (k, v) for k, v in params.items())
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Auth-Token", env["ORCH_API_KEY"])
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=ssl.create_default_context()) as r:
            raw = r.read().decode()
    except urllib.error.HTTPError as exc:
        return {"_http": exc.code, "_body": exc.read().decode()[:400]}
    except Exception as exc:
        return {"_error": "%s: %s" % (type(exc).__name__, exc)}
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        return {"_raw": raw}


def err(r):
    if isinstance(r, dict):
        return r.get("_http") or r.get("_error")
    return None


def local_preconfigs():
    out = {}
    for f in sorted(glob.glob(os.path.join(PRECONFIG_DIR, "*.yml"))):
        name = os.path.basename(f)[:-4]
        if name in ALLOWED:
            out[name] = open(f).read()
    return out


def cmd_template(env, args):
    r = call(env, "GET", "gms/appliance/preconfiguration/default")
    if err(r):
        print("  failed: %s" % err(r))
        return 1
    y = base64.b64decode(r["configData"]).decode()
    p = os.path.join(PRECONFIG_DIR, "_default_template.yml")
    os.makedirs(PRECONFIG_DIR, exist_ok=True)
    open(p, "w").write(y)
    print("  saved %s (%d lines) - the authoritative schema reference"
          % (os.path.relpath(p, ROOT), len(y.splitlines())))
    return 0


def cmd_validate(env, args):
    bad = 0
    for name, y in local_preconfigs().items():
        r = call(env, "POST", "gms/appliance/preconfiguration/validate",
                 {"name": name, "configData": base64.b64encode(y.encode()).decode()})
        e = err(r)
        print("  %-12s %s" % (name, ("INVALID %s %s" % (e, r.get("_body", "")[:110])) if e else "valid"))
        bad += bool(e)
    print("  ---- %d valid, %d invalid" % (len(local_preconfigs()) - bad, bad))
    return 1 if bad else 0


def cmd_list(env, args):
    pre = call(env, "GET", "gms/appliance/preconfiguration")
    print("  preconfigurations on Orchestrator:")
    for p in (pre if isinstance(pre, list) else []):
        print("    id=%-4s %-14s autoApply=%s tag=%s"
              % (p.get("id"), p.get("name"), p.get("autoApply"), p.get("tag")))
    disc = call(env, "GET", "appliance/discovered")
    print("  discovered (id is what approve wants):")
    for d in sorted(disc if isinstance(disc, list) else [],
                    key=lambda x: (x.get("applianceInfo", {}).get("hostname") or "")):
        a = d.get("applianceInfo", {})
        t = time.strftime("%Y-%m-%d %H:%M", time.localtime(d.get("discoveredTime") or 0))
        print("    id=%-4s %-14s serial=%-19s discovered=%s approved=%s"
              % (d.get("id"), a.get("hostname"), a.get("serial"), t, d.get("approved")))
    return 0


def cmd_push(env, args):
    existing = call(env, "GET", "gms/appliance/preconfiguration")
    by_name = {p.get("name"): p for p in (existing if isinstance(existing, list) else [])}
    for name, y in local_preconfigs().items():
        enc = base64.b64encode(y.encode()).decode()
        v = call(env, "POST", "gms/appliance/preconfiguration/validate",
                 {"name": name, "configData": enc})
        if err(v):
            print("  %-12s REFUSED - does not validate: %s" % (name, v.get("_body", "")[:120]))
            continue
        payload = {"name": name, "configData": enc, "autoApply": True,
                   "tag": name, "comment": "greek-fabric ecv_onboard.py"}
        if name in by_name:
            pid = by_name[name].get("id")
            # NOTE: the query param is `preconfigId`, NOT `id` - `id` returns 400.
            r = call(env, "PUT", "gms/appliance/preconfiguration",
                     payload, params={"preconfigId": pid})
            e = err(r)
            print("  %-12s updated (id=%s)%s" % (name, pid,
                  (" FAILED %s %s" % (e, r.get("_body", "")[:120])) if e else ""))
        else:
            r = call(env, "POST", "gms/appliance/preconfiguration", payload)
            print("  %-12s created -> %s" % (name, err(r) or r))
    return 0


def cmd_approve(env, args):
    disc = call(env, "GET", "appliance/discovered")
    if err(disc):
        print("  cannot read discovered: %s" % err(disc))
        return 1
    cand = [d for d in disc
            if (d.get("applianceInfo", {}).get("hostname") in ALLOWED)
            and not d.get("approved") and not d.get("denied")]

    # Ghost guard - see note 7. A redeploy leaves stale registrations behind and
    # approving one creates an appliance that can never connect.
    seen = {}
    for d in cand:
        seen.setdefault(d["applianceInfo"]["hostname"], []).append(d)
    dupes = {h: v for h, v in seen.items() if len(v) > 1}
    if dupes and not args.allow_duplicates:
        print("  REFUSING: duplicate discovered entries (stale registrations from a")
        print("  previous deploy). Newest is almost certainly the live one:")
        for h, v in sorted(dupes.items()):
            for d in sorted(v, key=lambda x: x.get("discoveredTime") or 0):
                t = time.strftime("%Y-%m-%d %H:%M", time.localtime(d.get("discoveredTime") or 0))
                print("    %-12s id=%-4s serial=%-19s discovered=%s"
                      % (h, d.get("id"), d["applianceInfo"].get("serial"), t))
        print("  Delete the stale ones, or re-run with --allow-duplicates to take newest.")
        return 2
    if dupes:
        keep = []
        for h, v in seen.items():
            keep.append(sorted(v, key=lambda x: x.get("discoveredTime") or 0)[-1])
        cand = keep

    if not cand:
        print("  nothing to approve")
        return 0
    for d in sorted(cand, key=lambda x: x["applianceInfo"]["hostname"]):
        name = d["applianceInfo"]["hostname"]
        if args.dry_run:
            print("  would approve id=%-4s %s" % (d.get("id"), name))
            continue
        # NOTE 6: the empty {} body is REQUIRED. Without it this 500s.
        r = call(env, "POST", "appliance/discovered/approve",
                 body={}, params={"id": d.get("id")})
        e = err(r)
        print("  approve id=%-4s %-12s %s" % (d.get("id"), name,
                                              ("FAILED %s" % e) if e else "-> nePk %s"
                                              % (r.get("_raw") or r)))
        time.sleep(3)
    return 0


def cmd_apply(env, args):
    """Apply preconfigs to ALREADY-APPROVED appliances.

    autoApply only fires when the appliance is discovered/approved while a
    matching preconfig already exists. If the appliance was discovered first -
    or approved before the preconfig was written - nothing ever binds, and the
    preconfig sits with taskstatus=0, completionstatus=False, nepk=None. The
    appliance reaches state=Normal while carrying no data-plane config at all,
    so nothing looks wrong until you go looking. This is the recovery path.
    """
    pre = {p.get("name"): p for p in (call(env, "GET", "gms/appliance/preconfiguration") or [])}
    apps = {a.get("hostName"): a for a in (call(env, "GET", "appliance") or [])}
    for name in sorted(ALLOWED):
        p, a = pre.get(name), apps.get(name)
        if not p or not a:
            print("  %-12s skipped (preconfig=%s appliance=%s)" % (name, bool(p), bool(a)))
            continue
        if args.dry_run:
            print("  would apply preconfigId=%s -> %s (%s)" % (p.get("id"), name, a.get("nePk")))
            continue
        r = call(env, "POST", "gms/appliance/preconfiguration/apply",
                 body={}, params={"preconfigId": p.get("id"), "nePk": a.get("nePk")})
        e = err(r)
        print("  %-12s preconfigId=%-3s nePk=%-7s %s"
              % (name, p.get("id"), a.get("nePk"),
                 ("FAILED %s %s" % (e, r.get("_body", "")[:120])) if e else "applied"))
        time.sleep(2)
    return 0


def cmd_status(env, args):
    pre = call(env, "GET", "gms/appliance/preconfiguration") or []
    for p in sorted(pre, key=lambda x: x.get("name") or ""):
        print("  %-12s taskstatus=%-4s completion=%-6s nepk=%s"
              % (p.get("name"), p.get("taskstatus"), p.get("completionstatus"),
                 p.get("nepk")))
        if not args.detail:
            continue
        # The per-section view is the only useful progress signal - the
        # top-level completionstatus stays False until the last section lands.
        r = call(env, "GET", "gms/appliance/preconfiguration/apply",
                 params={"preconfigId": p.get("id")})
        for sec in (r.get("result") or []):
            done = sec.get("completionStatus")
            print("      %-46s %s" % (str(sec.get("name"))[:46],
                                      "ok" if done else "pending/running"))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("template", help="fetch Orchestrator's documented default template")
    sub.add_parser("validate", help="validate local preconfig YAML, change nothing")
    sub.add_parser("list", help="list preconfigs and discovered appliances")
    sub.add_parser("push", help="create/update preconfigs (validates each first)")
    ap2 = sub.add_parser("apply", help="apply preconfigs to already-approved appliances")
    ap2.add_argument("--dry-run", action="store_true")
    st = sub.add_parser("status", help="show preconfig apply status")
    st.add_argument("--detail", action="store_true",
                    help="per-section progress (the useful view)")
    a = sub.add_parser("approve", help="approve discovered EC-Vs")
    a.add_argument("--dry-run", action="store_true")
    a.add_argument("--allow-duplicates", action="store_true",
                   help="take the newest when stale registrations exist")
    args = ap.parse_args()
    env = load_env()
    return {"template": cmd_template, "validate": cmd_validate, "list": cmd_list,
            "push": cmd_push, "approve": cmd_approve, "apply": cmd_apply,
            "status": cmd_status}[args.cmd](env, args)


if __name__ == "__main__":
    sys.exit(main())
