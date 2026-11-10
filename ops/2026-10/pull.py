import json, sys
sys.path.insert(0, "scripts")
import mist_api as m
env = m.load_env()
out = sys.argv[1]
sites = m.sites(env)
print({k:v for k,v in sites.items() if k in ("CF - THERMOPYLAE","CF - TROY","CF - MARATHON")})
for name in ("CF - THERMOPYLAE","CF - TROY","CF - MARATHON"):
    sid = sites[name]
    s = m.call(env,"GET","/sites/%s/setting"%sid)
    json.dump(s, open("%s/setting-%s.json"%(out,name[5:]),"w"), indent=1)
    devs = m.call(env,"GET","/sites/%s/devices?type=switch"%sid)
    for d in devs:
        if "-bd-" in d.get("name",""):
            json.dump(d, open("%s/%s.json"%(out,d["name"]),"w"), indent=1)
            print(d["name"], d.get("router_id"), "bgp_config=",bool(d.get("bgp_config")), "evpn role=", (d.get("evpn_config") or {}).get("role"))
    topos = m.call(env,"GET","/sites/%s/evpn_topologies"%sid)
    json.dump(topos, open("%s/evpntopo-%s.json"%(out,name[5:]),"w"), indent=1)
    for t in topos:
        full = m.call(env,"GET","/sites/%s/evpn_topologies/%s"%(sid,t["id"]))
        json.dump(full, open("%s/evpntopo-%s-full.json"%(out,name[5:]),"w"), indent=1)
