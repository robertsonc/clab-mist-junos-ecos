"""Run on the EX4400 via t430-srv-03 (creds from .env, sent over stdin, never printed).
  exrun.py cli "cmd" ...            operational commands
  exrun.py raw <pyfile>             run a python body with `c` = paramiko client, `sh` = shell (junos module imported)"""
import os, sys, subprocess
env = {}
for l in open("/home/crobertson/labs/greek-fabric/.env"):
    l = l.strip().removeprefix("export ").strip()
    if "=" in l and not l.startswith("#"):
        k, v = l.split("=", 1); env[k] = v.strip().strip('"').strip("'")
U, P = env["EX4400_USERNAME"], env["EX4400_PASSWORD"]
hdr = "import sys,time; sys.path.insert(0,'scripts'); import junos\nU=%r; P=%r; H='10.32.99.41'\n" % (U, P)
if sys.argv[1] == "cli":
    code = hdr + "print(junos.cli(H, %r, user=U, password=P))\n" % sys.argv[2:]
else:
    code = hdr + "c=junos.connect(H,U,P); sh=junos.shell(c)\n" + open(sys.argv[2]).read() + "\nc.close()\n"
r = subprocess.run(["ssh", "-o", "BatchMode=yes", "t430-srv-03", "cd ~/labs/greek-fabric && .venv/bin/python -"], input=code, text=True, capture_output=True)
out = r.stdout + r.stderr
import re
out = re.sub(r'(\$9\$|\$6\$|\$5\$|\$1\$)[^";\s]*', r'\1<redacted>', out)
print("\n".join(l for l in out.splitlines() if l.strip() and "screen-" not in l and "Screen " not in l and l.strip() != "{master:0}"))
