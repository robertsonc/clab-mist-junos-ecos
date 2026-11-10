"""Load gbpt-vjunos.set onto the far-end vJunos (172.30.49.11) and commit.
Run on t430-srv-03 from ~/labs/greek-fabric:  .venv/bin/python gbp-test/gbpt_vjunos_cfg.py"""
import sys, time
sys.path.insert(0, "scripts"); import junos
lines = [l for l in open("gbp-test/gbpt-vjunos.set").read().splitlines() if l.strip()]
c = junos.connect("172.30.49.11"); sh = junos.shell(c)
out = junos.send(sh, "configure", 3)
for l in lines: out += junos.send(sh, l, 1.0)
sh.send("commit and-quit\n"); r = ""; end = time.time() + 300
while time.time() < end and not any(k in r for k in ("commit complete", "error:", "failed")):
    r += junos._drain(sh, 2)
print("\n".join(x for x in (out + r).splitlines() if any(k in x for k in ("error", "warning", "commit", "invalid", "syntax"))))
c.close()
