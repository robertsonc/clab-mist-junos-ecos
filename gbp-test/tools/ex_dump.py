import paramiko
o = junos.send(sh, "set cli screen-length 0", 1) + junos.send(sh, "set cli screen-width 0", 1)
sh.send("show configuration | display set | no-more\n"); out = junos._drain(sh, 6)
print("@@BEGIN@@"); print(out); print("@@END@@")
