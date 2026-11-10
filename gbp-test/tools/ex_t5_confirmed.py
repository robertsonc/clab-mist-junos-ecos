LINES = 'set interfaces irb unit 777 description "GBPT type-5 test gateway"\nset interfaces irb unit 777 family inet address 192.168.177.254/24\nset routing-instances GBPT vlans GBPT l3-interface irb.777\nset routing-instances GBPT protocols evpn default-gateway do-not-advertise\nset policy-options policy-statement GBPT_T5_EXPORT term 01_ipv4 from protocol evpn\nset policy-options policy-statement GBPT_T5_EXPORT term 01_ipv4 from route-filter 0.0.0.0/0 prefix-length-range /32-/32\nset policy-options policy-statement GBPT_T5_EXPORT term 01_ipv4 then accept\nset policy-options policy-statement GBPT_T5_EXPORT term 03_direct from protocol direct\nset policy-options policy-statement GBPT_T5_EXPORT term 03_direct then accept\nset routing-instances GBPT_VRF instance-type vrf\nset routing-instances GBPT_VRF interface irb.777\nset routing-instances GBPT_VRF route-distinguisher 10.77.77.1:2\nset routing-instances GBPT_VRF vrf-target target:65477:2\nset routing-instances GBPT_VRF routing-options multipath\nset routing-instances GBPT_VRF protocols evpn ip-prefix-routes advertise direct-nexthop\nset routing-instances GBPT_VRF protocols evpn ip-prefix-routes encapsulation vxlan\nset routing-instances GBPT_VRF protocols evpn ip-prefix-routes vni 77999\nset routing-instances GBPT_VRF protocols evpn ip-prefix-routes export GBPT_T5_EXPORT\n'
import os
MODE = "confirmed"
lines = [l for l in LINES.splitlines() if l.strip()]
out = junos.send(sh, "configure exclusive", 3)
for l in lines: out += junos.send(sh, l, 1.2)
out += junos.send(sh, "show | compare", 4)
cmd = {"check": "commit check", "confirmed": "commit confirmed 10 comment GBPT-stage", "commit": "commit comment GBPT-stage"}[MODE]
sh.send(cmd + "\n"); r = ""; end = time.time() + 240
while time.time() < end and not any(k in r for k in ("succeeds", "commit complete", "error:", "failed")):
    r += junos._drain(sh, 2)
r += junos._drain(sh, 3)
out += r
out += junos.send(sh, "exit configuration-mode", 3)
print(out)
