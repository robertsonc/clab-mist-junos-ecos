#!/bin/bash
# like exrun.py raw, but no redaction; stdout goes straight to a 600 file
S=$(dirname "$0")
python3 - "$S/ex_dump.py" <<'PY'
import os, sys, subprocess
env = {}
for l in open("/home/crobertson/labs/greek-fabric/.env"):
    l = l.strip().removeprefix("export ").strip()
    if "=" in l and not l.startswith("#"):
        k, v = l.split("=", 1); env[k] = v.strip().strip('"').strip("'")
code = "import sys,time; sys.path.insert(0,'scripts'); import junos\nc=junos.connect('10.32.99.41',%r,%r); sh=junos.shell(c)\n" % (env["EX4400_USERNAME"], env["EX4400_PASSWORD"]) + open(sys.argv[1]).read() + "\nc.close()\n"
r = subprocess.run(["ssh","-o","BatchMode=yes","t430-srv-03","cd ~/labs/greek-fabric && .venv/bin/python -"], input=code, text=True, capture_output=True)
t = r.stdout; t = t[t.find("@@BEGIN@@")+9:t.find("@@END@@")]
sys.stdout.write("\n".join(l for l in t.splitlines() if l.startswith(("set ","deactivate ","delete ","activate ","protect ","insert "))) + "\n")
PY
