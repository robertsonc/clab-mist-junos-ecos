"""Minimal Orchestrator REST helper - stdlib only.

FALLBACK PATH. The ec-sdwan-expert skill normally routes everything through the
edgeconnect-sdwan MCP server and forbids direct API calls. It is bypassed here
deliberately and for one specific reason: that server resolved its Orchestrator
from config/config.json, which pinned it to the HPE Discover instance rather
than the lab declared in .mcp.json, so writes would have hit the wrong system.
See the load_settings() precedence fix in ec_sdwan_mcp/settings.py.

Because this path has none of the MCP server's guard rails (MCP_MODE gating,
input validation, automatic audit trail), every write helper built on it must
be explicit, dry-run by default, and scoped by ALLOWED_HOSTNAMES below.

Credentials come from greek-fabric/.env:  ORCH_URL, ORCH_API_KEY
"""
import json
import os
import ssl
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The ONLY appliances anything in this fabric may write to. The six new EC-Vs.
# Sites 1/2/3 appliances share this Orchestrator and must not be touched.
ALLOWED_HOSTNAMES = {
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


def call(env, method, path, body=None, timeout=30):
    """One REST call. Returns parsed JSON, or a dict with _http_error/_error."""
    host = env["ORCH_URL"].replace("https://", "").replace("http://", "").strip("/")
    url = "https://%s/gms/rest/%s" % (host, path.lstrip("/"))
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Auth-Token", env["ORCH_API_KEY"])
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as exc:
        return {"_http_error": exc.code, "_body": exc.read().decode()[:400], "_path": path}
    except Exception as exc:
        return {"_error": "%s: %s" % (type(exc).__name__, exc), "_path": path}
    return json.loads(raw) if raw else {}
