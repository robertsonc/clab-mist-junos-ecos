import sys,json,time; sys.path.insert(0,'scripts'); import orch_api as o
env=o.load_env()
ne=sys.argv[1]; cmds=sys.argv[2:]
g=o.call(env,"POST","broadcastCli",{"nePks":[ne],"cmdList":cmds})
guid=g.get("_raw",g) if isinstance(g,dict) else g
guid=str(guid).strip().strip('"')
for _ in range(60):
    time.sleep(2)
    st=o.call(env,"GET","action/status?key=%s"%guid)
    items=st if isinstance(st,list) else [st]
    if all(i.get("taskStatus") in (3,"COMPLETED") or i.get("endTime") for i in items if isinstance(i,dict)):
        break
for i in items:
    res=i.get("result")
    try: res=json.loads(res)
    except Exception: pass
    if isinstance(res,dict):
        for k,v in res.items(): print("###",k); print(v if isinstance(v,str) else json.dumps(v,indent=1))
    else: print(res if res else json.dumps(i)[:1500])
