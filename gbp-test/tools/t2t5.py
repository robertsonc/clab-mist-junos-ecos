import sys; sys.path.insert(0,'scripts'); import junos
for ip in sys.argv[1:]:
    print(junos.cli(ip, ['show route 10.7.10.11 table corp_vrf.inet.0 extensive | match "^10.7|entr|\\*?EVPN|Preference|Protocol next hop|Next hop:|Communities|State:|Route Label|Inactive reason|Age:"',
                         'show route 10.7.10.11 table corp_vrf.inet.0']))
