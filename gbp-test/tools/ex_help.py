out = junos.send(sh, "configure private", 3)
for q in ["set chassis forwarding-options ?", "set forwarding-options evpn-vxlan ?",
          "set firewall family any filter X ?", "set firewall family any filter X term t then ?",
          "set routing-instances X instance-type ?", "set routing-instances X service-type ?"]:
    sh.send(q); out += junos._drain(sh, 3); sh.send("\x15"); junos._drain(sh, 1)
out += junos.send(sh, "exit configuration-mode", 3)
print(out)
