"""Add a static EVPN export policy tagging MA-vm-01's MAC+IP route gbp-tag 10001 on MA-vjunos-ac-01."""
import sys, json
sys.path.insert(0, "scripts"); import mist_api as m
P = "set policy-options policy-statement EVPN_GBP_EXPORT term ma_vm01 "
L = ["set policy-options mac-list MA_VM01 aa:c1:ab:de:7d:d4",
     "set policy-options community GBP_10001 members 0x0317:0.0.0.0:10001",
     P + "from family evpn",
     P + "from nlri-route-type 2",
     P + "from evpn-mac-route mac-ipv4",
     P + "from mac-filter-list MA_VM01",
     P + "then community add GBP_10001",
     "set protocols bgp group evpn_overlay export EVPN_GBP_EXPORT"]
env = m.load_env(); sid = m.sites(env)["CF - MARATHON"]
d = [x for x in m.call(env, "GET", "/sites/%s/devices?type=switch" % sid) if x["name"] == "MA-vjunos-ac-01"][0]
bk = "configs/mist-nac-2026-10-15/device-%s-pre-gbp-policy-hex.json" % d["name"]
json.dump(d, open(bk, "w"), indent=1)
acc = [c for c in (d.get("additional_config_cmds") or []) if c not in L] + L
r = m.call(env, "PUT", "/sites/%s/devices/%s" % (sid, d["id"]), {"additional_config_cmds": acc})
print(d["name"], "acc %d -> %d" % (len(d.get("additional_config_cmds") or []), len(r["additional_config_cmds"])), "backup", bk)
