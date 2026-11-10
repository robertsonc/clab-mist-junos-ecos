import sys, subprocess; sys.path.insert(0,'scripts'); import junos
from concurrent.futures import ThreadPoolExecutor
rows = subprocess.run(['docker','ps','--format','{{.Names}}','--filter','name=vjunos'],capture_output=True,text=True).stdout.split()
def q(n):
    ip = subprocess.run(['docker','inspect','-f','{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}',n],capture_output=True,text=True).stdout.strip()
    try:
        o = junos.cli(ip, ['show configuration | display inheritance | display set | match vrrp | count', 'show vrrp summary | count'])
        c = [l.split()[-2] for l in o.splitlines() if l.startswith('Count:')]
        return n.split('-',2)[-1], c
    except Exception as e: return n, str(e)[:60]
with ThreadPoolExecutor(8) as ex:
    for r in ex.map(q, sorted(rows)): print(r)
