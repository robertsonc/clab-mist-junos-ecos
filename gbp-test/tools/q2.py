import sys; sys.path.insert(0,"scripts"); import junos
c=junos.connect("172.30.46.21"); sh=junos.shell(c)
out=junos.send(sh,"configure private",3)
sh.send("set forwarding-options evpn-vxlan host-originated-packets ?"); out+=junos._drain(sh,3); sh.send("\x15"); junos._drain(sh,1)
sh.send("set forwarding-options evpn-vxlan host-originated-packets gbp-src-tag ?"); out+=junos._drain(sh,3); sh.send("\x15"); junos._drain(sh,1)
out+=junos.send(sh,"exit configuration-mode",3); c.close()
print(out)
print(junos.cli("172.30.46.21",["show interfaces terse routing-instance corp_vrf | match inet","show route table corp_vrf.inet.0 10.5.10.0/24 | match \"via|>\""]))
