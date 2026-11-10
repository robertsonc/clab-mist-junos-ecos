"""Set wan0/wan1 zone -> WAN (id 44, Default segment) on greek ECs via
/deployment. Validate first; --apply to POST. Only the zone field changes."""
import sys, json, copy, os
sys.path.insert(0, 'scripts'); import orch_api
env = orch_api.load_env()
NE = {'TH-ecv-01': '22.NE', 'TH-ecv-02': '23.NE', 'TR-ecv-01': '24.NE', 'TR-ecv-02': '25.NE',
      'MA-ecv-01': '27.NE', 'MA-ecv-02': '26.NE'}
WAN_ZONE = 44
apply = '--apply' in sys.argv
out = 'configs/ecv-wanzone-2026-10-15'; os.makedirs(out, exist_ok=True)

def paths(d):
    return [(m['ifName'], ip.get('ip'), ip.get('zone')) for m in d['modeIfs'] for ip in m.get('applianceIPs') or []]

for h in [a for a in sys.argv[1:] if not a.startswith('--')]:
    ne = NE[h]
    cur = orch_api.call(env, 'GET', 'appliance/rest?nePk=%s&url=/deployment' % ne)
    new = copy.deepcopy(cur)
    n = 0
    for m in new['modeIfs']:
        for ip in m.get('applianceIPs') or []:
            if m['ifName'] in ('wan0', 'wan1') and ip.get('wanSide') is not False and ip.get('zone') != WAN_ZONE:
                ip['zone'] = WAN_ZONE; n += 1
    print('==', h, 'before', paths(cur))
    if not n:
        print('   already WAN'); continue
    # everything but the zone must be identical
    def strip(d):
        d = copy.deepcopy(d)
        for m in d['modeIfs']:
            for ip in m.get('applianceIPs') or []: ip.pop('zone', None)
        return d
    assert strip(cur) == strip(new)
    v = orch_api.call(env, 'POST', 'appliance/rest?nePk=%s&url=/deployment/validate' % ne, new)
    print('   validate ->', json.dumps(v)[:500])
    if apply:
        json.dump(cur, open('%s/%s-deployment-before.json' % (out, h), 'w'), indent=1)
        r = orch_api.call(env, 'POST', 'appliance/rest?nePk=%s&url=/deployment' % ne, new)
        after = orch_api.call(env, 'GET', 'appliance/rest?nePk=%s&url=/deployment' % ne)
        print('   apply ->', json.dumps(r)[:300])
        print('   after', paths(after), '| non-zone unchanged:', strip(after)['modeIfs'] == strip(cur)['modeIfs'])
