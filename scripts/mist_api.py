"""Thin Mist API helper - stdlib only, no pip dependencies.

This org lives on the AC2 cloud (the switches dial oc-term.ac2.mist.com), so the
API base is api.ac2.mist.com. api.mist.com returns 401 for these credentials.

Credentials come from .env at the repo root:
    MIST_ORG_ID="..."
    MIST_API_KEY="..."
"""
import json
import os
import urllib.error
import urllib.request

BASE = "https://api.ac2.mist.com/api/v1"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env(path=None):
    """Parse .env without needing the caller to have sourced it."""
    path = path or os.path.join(ROOT, ".env")
    env = {}
    if not os.path.exists(path):
        raise SystemExit("missing %s - need MIST_ORG_ID and MIST_API_KEY" % path)
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:]
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    for key in ("MIST_ORG_ID", "MIST_API_KEY"):
        if not env.get(key):
            raise SystemExit("%s not set in %s" % (key, path))
    return env


def call(env, method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Token " + env["MIST_API_KEY"])
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as exc:
        raise SystemExit("HTTP %s on %s %s: %s"
                         % (exc.code, method, path, exc.read().decode()[:300]))
    return json.loads(raw) if raw else {}


def org(env, method, path, body=None):
    return call(env, method, "/orgs/%s%s" % (env["MIST_ORG_ID"], path), body)


def sites(env):
    """name -> site_id"""
    return {s["name"]: s["id"] for s in org(env, "GET", "/sites")}


def inventory(env, vjunos_only=True):
    devs = org(env, "GET", "/inventory")
    if vjunos_only:
        # Lab switches all claim under a 02:00:04:* locally-administered MAC.
        # Other labs in this org (hub/spoke SSRs) must not be touched.
        devs = [d for d in devs if str(d.get("mac", "")).startswith("020004")]
    return devs


def device_id(mac):
    return "00000000-0000-0000-1000-" + mac.replace(":", "").lower()
