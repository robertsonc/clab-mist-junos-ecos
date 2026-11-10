ssh -o BatchMode=yes t430-srv-03 'cd ~/labs/greek-fabric && .venv/bin/python -c "
import sys, re; sys.path.insert(0,\"scripts\"); import junos
for n, ip in ((\"TH-ac-01\",\"172.30.44.27\"),(\"TH-ac-02\",\"172.30.44.28\"),(\"TR-ac-01\",\"172.30.45.27\"),(\"TR-ac-02\",\"172.30.45.28\"),(\"MA-ac-01\",\"172.30.46.27\"),(\"MA-ac-02\",\"172.30.46.28\")):
    o = junos.cli(ip, [\"show dot1x interface ge-0/0/2.0 detail\", \"show network-access radsec state\", \"show configuration access | display inheritance | display set | match source-address\"])
    st = re.findall(r\"Operational state: (\\S+)\", o); held = re.findall(r\"Held state Reason: (.*)\", o)
    rs = re.findall(r\"^\\s+state\\s+(\\S+)\", o, re.M); src = sorted(set(re.findall(r\"source-address (\\S+)\", o)))
    print(n, \"dot1x=\", st or \"-\", held, \"radsec=\", rs, \"src=\", src)
"'
