import json, sys
sys.path.insert(0, "scripts")
import orch_api as o
env = o.load_env(); out = sys.argv[1]
apps = o.call(env, "GET", "appliance")
mine = {a["hostName"]: a for a in apps if a.get("hostName") in o.ALLOWED_HOSTNAMES}
for h, a in sorted(mine.items()):
    ne = a["nePk"]
    print(h, ne, "state", a.get("state"), a.get("softwareVersion"), a.get("group"))
    for name, url in [("bgp", "/bgp/config/system"), ("bgpstate", "/bgp/state"), ("segs", "/vrf/config/segments"),
                      ("lo", "/virtualif/loopback"), ("vxlan", "/vxlan/config"), ("routes", "/subnets3/configured"),
                      ("vrfbgp", "/bgp/config/vrf")]:
        r = o.call(env, "GET", "appliance/rest?nePk=%s&url=%s" % (ne, url))
        json.dump(r, open("%s/%s-%s.json" % (out, h, name), "w"), indent=1)
        print("   ", name, str(r)[:160])
