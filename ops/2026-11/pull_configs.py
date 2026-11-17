"""Pull the running config of all 24 vJunos switches (raw + flattened set form) and the
Mist additional_config_cmds of each border. Raw output goes to argv[1] (keep it out of git);
redact_configs.py writes the committable copy."""
import sys, os, json
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "scripts"); import junos, labnodes, mist_api as m
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
CMDS = {"conf": "show configuration | no-more",
        "set": "show configuration | display inheritance no-comments | display set | no-more"}
def pull(node):
    name, ip = node[0], node[1]
    c = junos.connect(ip, labnodes.JUNOS_USER, labnodes.JUNOS_PASSWORD)
    try:
        for ext, cmd in CMDS.items():
            _, so, _ = c.exec_command(cmd, timeout=180)
            open("%s/%s.%s" % (out, name, ext), "w").write(so.read().decode(errors="replace"))
    finally: c.close()
    return name, sum(1 for _ in open("%s/%s.set" % (out, name)))
with ThreadPoolExecutor(8) as ex:
    for r in ex.map(pull, labnodes.SWITCHES): print(*r)
env = m.load_env(); sites = m.sites(env)
for s in ("CF - THERMOPYLAE", "CF - TROY", "CF - MARATHON"):
    st = m.call(env, "GET", "/sites/%s/setting" % sites[s])
    open("%s/site-%s-additional-cli.set" % (out, s[5:]), "w").write("\n".join(st.get("additional_config_cmds") or []) + "\n")
    for d in m.call(env, "GET", "/sites/%s/devices?type=switch" % sites[s]):
        if "-bd-" in d["name"]:
            cmds = d.get("additional_config_cmds") or []
            open("%s/%s-additional-cli.set" % (out, d["name"]), "w").write("\n".join(cmds) + "\n")
            print(d["name"], "additional_config_cmds:", len(cmds), "| site", s[5:], len(st.get("additional_config_cmds") or []))
