import sys; sys.path.insert(0,'scripts'); import junos
out = junos.cli("172.30.46.27", ['show configuration routing-instances | display inheritance no-comments | display set | match "corp_vrf|evpn_vs" | except "description|static|route-distinguisher|vrf-target|interface ge|vlan-id"',
  'show configuration policy-options | display inheritance no-comments | display set | match "evpn|EVPN|T5|type5|host"'])
print(out)
