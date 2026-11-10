import sys, json
sys.path.insert(0, "scripts"); import orch_api
env = orch_api.load_env()
for ne in sys.argv[1:]:
    row = []
    for seg, name in ((3, "CORP"), (6, "GUEST"), (7, "IOT")):
        r = orch_api.call(env, "GET", "appliance/rest?nePk=%s&url=/subnets3/all/vrfs/%d" % (ne, seg))
        ents = (r.get("subnets") or {}).get("entries", []) if isinstance(r, dict) else []
        bgp = sorted({e["state"]["prefix"] for e in ents if "bgp" in json.dumps(e).lower() or "evpn" in json.dumps(e).lower()})
        row.append("%s %d total/%d bgp %s" % (name, len(ents), len(bgp), bgp[:8]))
    print(ne, " | ".join(row))
