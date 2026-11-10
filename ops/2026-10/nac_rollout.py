import sys, copy
sys.path.insert(0, "scripts"); import mist_api as m
env = m.load_env(); sites = m.sites(env)
SN = {"TH": "CF - THERMOPYLAE", "TR": "CF - TROY", "MA": "CF - MARATHON"}
LO = {"TH-vjunos-ac-01": "172.17.0.1", "TH-vjunos-ac-02": "172.17.0.2", "TR-vjunos-ac-01": "172.17.3.2",
      "TR-vjunos-ac-02": "172.17.3.1", "MA-vjunos-ac-01": "172.17.6.2", "MA-vjunos-ac-02": "172.17.6.1"}
TAGS = {"MANAGED": {"type": "dynamic_gbp", "gbp_tag": 10001}, "UNMANAGED": {"type": "dynamic_gbp", "gbp_tag": 10002}}
# 1. site settings
for p in ("TH", "TR"):
    sid = sites[SN[p]]; s = m.call(env, "GET", "/sites/%s/setting" % sid)
    u = copy.deepcopy(s["port_usages"]["corp_lan_access"])
    u.update({"port_auth": "dot1x", "enable_mac_auth": True, "mac_auth_only": True, "description": "corp_lan_access + MAB (Mist NAC)"})
    pu = s["port_usages"]; pu["corp_lan_mab"] = u
    r = m.call(env, "PUT", "/sites/%s/setting" % sid, {"mist_nac": {"enabled": True, "network": "corp_lan"}, "acl_tags": TAGS, "port_usages": pu})
    print(p, r["mist_nac"], list(r["acl_tags"]), "corp_lan_mab" in r["port_usages"])
# 2. rules -> all three sites
ids = [sites[v] for v in SN.values()]
for rid in ("763f0752-32ba-4128-a391-669a4d7a2661", "bf9d2e5c-82a1-425f-ac41-af205b7944a0"):
    r = m.org(env, "GET", "/nacrules/%s" % rid); mt = r["matching"]; mt["site_ids"] = ids
    x = m.org(env, "PUT", "/nacrules/%s" % rid, {"matching": mt}); print(x["name"], len(x["matching"]["site_ids"]), "sites", x["apply_tags"])
# 3. switches
for p in ("TH", "TR", "MA"):
    sid = sites[SN[p]]
    for d in m.call(env, "GET", "/sites/%s/devices?type=switch" % sid):
        if d["name"] not in LO: continue
        src = LO[d["name"]]
        acc = [c for c in (d.get("additional_config_cmds") or []) if not c.startswith(("set access radsec", "set access radius-server"))]
        acc += ["set access radsec destination %s source-address %s" % (i, src) for i in (895, 896)]
        acc += ["set access radius-server %s source-address %s" % (ip, src) for ip in ("3.33.153.159", "15.197.139.214")]
        pc = d["port_config"]; pc["ge-0/0/2"]["usage"] = "corp_lan_mab"; pc.pop("ge-0/0/4", None)
        r = m.call(env, "PUT", "/sites/%s/devices/%s" % (sid, d["id"]), {"additional_config_cmds": acc, "port_config": pc})
        cli = m.call(env, "GET", "/sites/%s/devices/%s/config_cmd" % (sid, d["id"])).get("cli") or []
        ok = sum(("radsec destination %d address" % i) in l for l in cli for i in (895, 896))
        print(d["name"], src, {k: v.get("usage") for k, v in r["port_config"].items()}, "acc=%d" % len(r["additional_config_cmds"]), "radsec dests in generated=%d" % ok)
