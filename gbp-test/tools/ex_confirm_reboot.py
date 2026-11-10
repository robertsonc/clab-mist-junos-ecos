out = junos.send(sh, "configure exclusive", 3)
sh.send("commit comment GBPT-confirm\n"); r = ""; end = time.time() + 200
while time.time() < end and "commit complete" not in r and "error" not in r: r += junos._drain(sh, 2)
out += r + junos.send(sh, "exit configuration-mode", 3)
out += junos.send(sh, "show system commit | match \"^[0-1] \"", 3)
if "commit complete" in r:
    out += junos.send(sh, "request system reboot", 4)
    out += junos.send(sh, "yes", 6)
print(out)
