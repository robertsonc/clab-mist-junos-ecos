"""Redact the raw pull (argv[1]) into a committable copy (argv[2]): password/key hashes,
SSH public keys, Mist outbound-ssh device-ids, MAC addresses and email addresses."""
import re, sys, os, glob
src, dst = sys.argv[1], sys.argv[2]; os.makedirs(dst, exist_ok=True)
RULES = [
    (re.compile(r'"\$\d+\$[^"]*"'), '"<redacted>"'),                       # $9$/$6$/$1$ hashes
    (re.compile(r'(ssh-(?:rsa|ed25519|dss|ecdsa[^ ]*)) "?[^";]+"?'), r'\1 "<redacted>"'),
    (re.compile(r'(device-id )\S+?(;|$)', re.M), r'\1<redacted>\2'),
    (re.compile(r'\b(?![0:]{17})(?!00:00:5e)([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}\b'), '<mac>'),
    (re.compile(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b'), '<uuid>'),
    (re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'), '<email>'),
]
n = {}
for f in sorted(glob.glob(src + "/*")):
    t = open(f).read()
    for i, (rx, rep) in enumerate(RULES):
        t, k = rx.subn(rep, t); n[i] = n.get(i, 0) + k
    open(os.path.join(dst, os.path.basename(f)), "w").write(t)
print("redactions per rule:", n)
