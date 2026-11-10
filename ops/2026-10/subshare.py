"""Set auto_subnet (redistribute to SD-WAN fabric) on segments 3/6/7 to match
MA-ecv-02: rtmap ec0N_to_sdwan, add_local_lan, add_local_asn, local_asn_filter."""
import sys, json, copy, os
sys.path.insert(0, 'scripts'); import orch_api
env = orch_api.load_env()
NE = {'TH-ecv-01': '22.NE', 'TH-ecv-02': '23.NE', 'TR-ecv-01': '24.NE', 'TR-ecv-02': '25.NE',
      'MA-ecv-01': '27.NE', 'MA-ecv-02': '26.NE'}
names = sys.argv[1:]
out = 'configs/ecv-subshare-2026-10-15'; os.makedirs(out, exist_ok=True)
for h in names:
    ne = NE[h]; n = h[-1]
    before = orch_api.call(env, 'GET', 'appliance/rest?nePk=%s&url=/system' % ne)
    json.dump(before, open('%s/%s-system-before.json' % (out, h), 'w'), indent=1)
    a = copy.deepcopy(before['auto_subnet'])
    for seg in ('3', '6', '7'):
        a['vrf'][seg].update({'rtmap_to_subshare': 'ec0%s_to_sdwan' % n, 'add_local_lan': True,
                              'add_local_wan': False, 'add_local_metric': 50, 'add_local_asn': True,
                              'local_asn_filter': True, 'add_local_communities': False,
                              'local_communities': ''})
    if a == before['auto_subnet']:
        print(h, 'already set'); continue
    r = orch_api.call(env, 'POST', 'appliance/rest?nePk=%s&url=/system' % ne, {'auto_subnet': a})
    after = orch_api.call(env, 'GET', 'appliance/rest?nePk=%s&url=/system' % ne)
    others = sorted(k for k in set(before) | set(after) if k != 'auto_subnet' and before.get(k) != after.get(k))
    print(h, 'POST', r, '| auto_subnet match:', after['auto_subnet'] == a, '| other keys changed:', others)
