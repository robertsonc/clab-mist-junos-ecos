"""Add the CORP-segment (3) default route on greek ECs, same form as their
Default-segment one. Refuses if CORP already has any configured route, since
POST /subnets3/configured/vrfs/3 replaces the whole list."""
import sys, json
sys.path.insert(0, 'scripts'); import orch_api
env = orch_api.load_env()
NE = {'TH-ecv-01': '22.NE', 'TH-ecv-02': '23.NE', 'TR-ecv-01': '24.NE', 'TR-ecv-02': '25.NE',
      'MA-ecv-01': '27.NE', 'MA-ecv-02': '26.NE'}
BODY = {"prefix": {"0.0.0.0/0": {"nhop": {"0.0.0.0": {"interface": {"default": {
    "metric": 50, "dir": "ANY", "comment": "Default route - CORP", "zone_id": 65534, "label": 1}}}}}}}
for h in sys.argv[1:]:
    ne = NE[h]
    cur = orch_api.call(env, 'GET', 'appliance/rest?nePk=%s&url=/subnets3/all/vrfs/3' % ne)
    cfg = [e['config'] for e in cur['subnets']['entries'] if e.get('state', {}).get('configured')]
    if cfg:
        print(h, 'SKIP - CORP already has configured routes:', cfg); continue
    r = orch_api.call(env, 'POST', 'appliance/rest?nePk=%s&url=/subnets3/configured/vrfs/3' % ne, BODY)
    after = orch_api.call(env, 'GET', 'appliance/rest?nePk=%s&url=/subnets3/all/vrfs/3' % ne)
    got = [e['config'] for e in after['subnets']['entries'] if e.get('state', {}).get('configured')]
    print(h, r, '->', [(g['prefix'], g['ifName'], g['metric'], g['label']) for g in got])
