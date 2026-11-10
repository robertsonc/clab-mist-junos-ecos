import sys, json, time
sys.path.insert(0,'scripts'); import orch_api
env=orch_api.load_env()
nes=['22.NE','23.NE','24.NE','25.NE','26.NE','27.NE']
al=orch_api.call(env,'POST','alarm/appliance?view=all',{'neIds':nes,'nePks':nes})
items=al if isinstance(al,list) else al.get('data',[]) if isinstance(al,dict) else []
if isinstance(al,dict) and not items: print('alarm resp', str(al)[:300])
now=time.time()*1000
for a in sorted(items,key=lambda a:-a.get('timeOccurredInMills',0)):
    t=a.get('timeOccurredInMills',0)
    if now-t<20*60*1000:
        print(a.get('hostName'),a.get('type'),a.get('severity'),time.strftime('%H:%M:%S',time.localtime(t/1000)),'ack' if a.get('acknowledged') else '', (a.get('description') or '')[:160])
for ne in nes:
    print(ne, json.dumps(orch_api.call(env,'GET','appliance/rest?nePk=%s&url=/vxlan/config'%ne)),
          sorted(orch_api.call(env,'GET','appliance/rest?nePk=%s&url=/vxlan/segVniMap'%ne)))
print(time.strftime('%H:%M:%S'))
