import sys, time; sys.path.insert(0,"scripts"); import junos
for m in sys.argv[1:]:
    c=junos.connect("172.30.46.27"); sh=junos.shell(c)
    junos.send(sh,"configure private",3)
    o=junos.send(sh,f"set policy-options community T_GBP members {m}",2)
    o+=junos.send(sh,"set policy-options policy-statement T_POL term t then community add T_GBP",2)
    sh.send("commit check\n"); out=""; end=time.time()+150
    while time.time()<end and not any(k in out for k in ("succeeds","error:")):
        out+=junos._drain(sh,2)
    junos.send(sh,"rollback 0",3); junos.send(sh,"exit configuration-mode",3); c.close()
    res=[l for l in (o+out).splitlines() if any(k in l for k in ("succeeds","error","invalid","Unknown","syntax"))]
    print(m, "->", res or "no result in 150s")
