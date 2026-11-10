"""Append the VXLAN-GBP globals to a MARATHON switch's Mist additional CLI. Usage: gbp_on.py <device-name>"""
import sys, json
sys.path.insert(0, "scripts"); import mist_api as m
GBP = ["set chassis forwarding-options vxlan-gbp-profile",
       "set forwarding-options evpn-vxlan gbp ingress-enforcement",
       "set forwarding-options evpn-vxlan gbp mac-ip-inter-tagging"]
env = m.load_env(); sid = m.sites(env)["CF - MARATHON"]
d = [x for x in m.call(env, "GET", "/sites/%s/devices?type=switch" % sid) if x["name"] == sys.argv[1]][0]
bk = "configs/mist-nac-2026-10-15/device-%s-pre-gbp.json" % d["name"]
json.dump(d, open(bk, "w"), indent=1)
acc = [c for c in (d.get("additional_config_cmds") or []) if c not in GBP] + GBP
r = m.call(env, "PUT", "/sites/%s/devices/%s" % (sid, d["id"]), {"additional_config_cmds": acc})
print(d["name"], "acc %d -> %d" % (len(d.get("additional_config_cmds") or []), len(r["additional_config_cmds"])), "backup", bk)
