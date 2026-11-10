"""Copy THERMOPYLAE's EC-facing border config pattern to TROY and MARATHON.
Device-level: networks, other_ip_configs, port_config (usage inet), extra_routes.
MA-bd-01: additional_config_cmds from TR-bd-01, TROY values -> MARATHON values."""
import json, sys, copy, os
sys.path.insert(0, "scripts"); import mist_api as m
APPLY = "--yes" in sys.argv
env = m.load_env(); sites = m.sites(env)
SITE = {"TR": ("CF - TROY", 6), "MA": ("CF - MARATHON", 7)}
devs = {}
for p, (sname, idx) in list(SITE.items()) + [("TH", ("CF - THERMOPYLAE", 5))]:
    for d in m.call(env, "GET", "/sites/%s/devices?type=switch" % sites[sname]):
        if "-bd-" in d["name"]:
            devs[d["name"]] = d
out = "configs/mist-ec-borders-2026-10-14"; os.makedirs(out, exist_ok=True)
th_port = devs["TH-vjunos-bd-01"]["port_config"]["ge-0/0/3"]

def plan(p, idx, b):
    d = devs["%s-vjunos-bd-%02d" % (p, b)]
    lan = b - 1
    body = {k: copy.deepcopy(d.get(k) or {}) for k in ("networks", "other_ip_configs", "port_config", "extra_routes")}
    for num, port in ((1, "ge-0/0/3"), (2, "ge-0/0/4")):
        third = (num - 1) * 2 + lan
        net = "to_%s-ecv-%02d_lan%d" % (p, num, lan)
        body["networks"][net] = {"vlan_id": "", "subnet": "10.%d.%d.1/31" % (idx, third), "subnet6": ""}
        body["other_ip_configs"][net] = {"type": "static", "ip": "10.%d.%d.1" % (idx, third), "netmask": "/31"}
        pc = copy.deepcopy(th_port); pc["port_network"] = net
        body["port_config"][port] = pc
        body["extra_routes"]["198.19.%d.%d/32" % (idx, num)] = {"via": ["10.%d.%d.0" % (idx, third)], "discard": False}
    return d, body

MAP = [("10.254.101.2", "10.254.102.2"), ("10.254.101.1", "10.254.102.1"),
       ("172.17.3.0/24", "172.17.6.0/24"), ("172.17.4.0/24", "172.17.7.0/24"), ("172.17.5.0/24", "172.17.8.0/24"),
       ("198.19.6.", "198.19.7."), ("64533", "64534"), ("65201", "65301"), ("65200", "65300")]
def tr2ma(lines):
    res = []
    for l in lines:
        for a, b in MAP: l = l.replace(a, b)
        res.append(l)
    return res
tr1, tr2 = devs["TR-vjunos-bd-01"]["additional_config_cmds"], devs["TR-vjunos-bd-02"]["additional_config_cmds"]
ma2 = devs["MA-vjunos-bd-02"]["additional_config_cmds"]
# sanity: mapping TR-bd-02 must reproduce MA-bd-02 exactly, else the mapping is incomplete
check_ok = [l for l in tr2ma(tr2) if l.strip()] == [l for l in ma2 if l.strip()]
print("TR-bd-02 mapped == MA-bd-02:", check_ok)
if not check_ok:
    a, b = tr2ma(tr2), ma2
    print(" len", len(a), len(b)); print(" first diffs", [(x, y) for x, y in zip(a, b) if x != y][:5])

for p, (sname, idx) in SITE.items():
    for b in (1, 2):
        d, body = plan(p, idx, b)
        if d["name"] == "MA-vjunos-bd-01":
            assert not d.get("additional_config_cmds")
            body["additional_config_cmds"] = tr2ma(tr1)
        json.dump(d, open("%s/%s-before.json" % (out, d["name"]), "w"), indent=1)
        print("==", d["name"], json.dumps({k: v for k, v in body.items() if k != "additional_config_cmds"}, indent=None)[:1500])
        if "additional_config_cmds" in body:
            print("   additional_config_cmds:", len(body["additional_config_cmds"]), "lines;",
                  [l for l in body["additional_config_cmds"] if "ec_sdwan local" in l or "neighbor" in l])
        if APPLY:
            if not check_ok: raise SystemExit("mapping check failed, not applying")
            r = m.call(env, "PUT", "/sites/%s/devices/%s" % (sites[sname], d["id"]), body)
            print("   PUT ->", "ok" if isinstance(r, dict) and r.get("id") == d["id"] else str(r)[:300])
