import os
MODE = os.environ.get("MODE", "check")
lines = [l for l in open(os.environ["CFG"]).read().splitlines() if l.strip()]
out = junos.send(sh, "configure private", 3)
for l in lines: out += junos.send(sh, l, 1.2)
out += junos.send(sh, "show | compare", 4)
cmd = {"check": "commit check", "confirmed": "commit confirmed 10 comment GBPT-stage", "commit": "commit comment GBPT-stage"}[MODE]
sh.send(cmd + "\n"); r = ""; end = time.time() + 240
while time.time() < end and not any(k in r for k in ("succeeds", "commit complete", "error:", "failed")):
    r += junos._drain(sh, 2)
r += junos._drain(sh, 3)
out += r
out += junos.send(sh, "rollback 0", 3) + junos.send(sh, "exit configuration-mode", 3)
print(out)
