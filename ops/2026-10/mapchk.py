import sys
sys.path.insert(0,'scripts'); import orch_api
env=orch_api.load_env()
n=0
for ne in ('22.NE','23.NE','24.NE','25.NE','26.NE','27.NE'):
    m=orch_api.call(env,'GET','appliance/rest?nePk=%s&url=/redistributionMaps'%ne)
    ok=all(k in m for k in ('ec01_to_campus','ec02_to_campus')); n+=ok
    print(ne, ok)
sys.exit(0 if n==6 else 1)
