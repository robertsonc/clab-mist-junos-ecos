import json, sys
sys.path.insert(0, "scripts"); import mist_api as m
env = m.load_env(); sites = m.sites(env)
out = "configs/mist-nac-2026-10-15"
for sname in ("CF - THERMOPYLAE", "CF - TROY", "CF - MARATHON"):
    sid = sites[sname]
    s = m.call(env, "GET", "/sites/%s/setting" % sid)
    json.dump(s, open("%s/setting-%s.json" % (out, sname.split()[-1]), "w"), indent=1)
    print(sname, sid, "mist_nac=", s.get("mist_nac"), "acl_tags=", list((s.get("acl_tags") or {}).keys()),
          "networks=", list((s.get("networks") or {}).keys()), "usages=", list((s.get("port_usages") or {}).keys()))
    for d in m.call(env, "GET", "/sites/%s/devices?type=switch" % sid):
        if "-ac-" in d["name"]:
            json.dump(d, open("%s/device-%s.json" % (out, d["name"]), "w"), indent=1)
            print("  ", d["name"], d["id"], "acc=", len(d.get("additional_config_cmds") or []),
                  "ports=", {k: v.get("usage") for k, v in (d.get("port_config") or {}).items()})
