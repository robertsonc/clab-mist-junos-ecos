import sys; sys.path.insert(0,"scripts"); import junos
c=junos.connect("172.30.46.27"); sh=junos.shell(c)
out=junos.send(sh,"configure private",3)
sh.send("set policy-options policy-statement T term t from ?"); out+=junos._drain(sh,3)
sh.send("\x15"); junos._drain(sh,1)
sh.send("set policy-options policy-statement T term t from evpn-mac-route ?"); out+=junos._drain(sh,3)
sh.send("\x15"); junos._drain(sh,1)
out+=junos.send(sh,"exit configuration-mode",3)
print(out); c.close()
